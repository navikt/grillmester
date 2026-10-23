"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { validDesign, validKey } = require("./design-contract.js");

const MAX_COMMENTS = 200;
const MAX_DECISIONS = 200;
const MAX_SCREENS = 100;
const MAX_STORE_BYTES = 2 * 1024 * 1024;
const MAX_BODY_BYTES = 16 * 1024;
const MAX_MUTATION_RECEIPTS = 2048;
const SCREEN = /^[a-f0-9]{32}$/;
const ID = /^[a-f0-9]{24}$/;
const ROLES = new Set(["", "button", "link", "textbox", "heading", "img", "navigation", "main", "region", "group", "list", "listitem", "checkbox", "radio", "combobox", "tab", "tabpanel", "table", "row", "cell", "alert", "status", "presentation", "none"]);

class FeedbackError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}
function canonicalJson(value, depth = 0) {
  if (depth > 32) throw new FeedbackError(400, "Feedback payload is too deeply nested.");
  if (Array.isArray(value)) return `[${value.map((entry) => canonicalJson(entry, depth + 1)).join(",")}]`;
  if (value !== null && typeof value === "object") return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key], depth + 1)}`).join(",")}}`;
  return JSON.stringify(value);
}

// Retry receipts live only for this server process. Never evict a receipt:
// an old retry must not become a new write after the capacity is reached.
class FeedbackMutationReceipts {
  constructor(limit = MAX_MUTATION_RECEIPTS) {
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > MAX_MUTATION_RECEIPTS) throw new Error("Invalid mutation receipt limit.");
    this.limit = limit;
    this.receipts = new Map();
  }
  run(id, method, pathname, value, operation) {
    if (id === undefined) { operation(value); return; }
    if (typeof id !== "string" || !/^[a-f0-9]{32}$/.test(id)) throw new FeedbackError(400, "Invalid feedback mutation identifier.");
    const fingerprint = crypto.createHash("sha256").update(canonicalJson([method, pathname, value])).digest("hex");
    if (this.receipts.has(id)) {
      if (this.receipts.get(id) !== fingerprint) throw new FeedbackError(409, "This feedback mutation identifier belongs to a different operation.");
      return;
    }
    if (this.receipts.size >= this.limit) throw new FeedbackError(429, "Feedback retry capacity reached. Start a new preview session.");
    operation(value);
    // All feedback operations persist synchronously. A failed commit must
    // leave the identifier available for a later retry of the same intent.
    this.receipts.set(id, fingerprint);
  }
}
function keys(value, required, optional = []) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  return required.every((key) => Object.hasOwn(value, key)) &&
    Object.keys(value).every((key) => required.includes(key) || optional.includes(key));
}
function boundedText(value, maximum = 2000) {
  return typeof value === "string" && Buffer.byteLength(value, "utf8") <= maximum &&
    !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value);
}
function number(value, minimum, maximum) {
  return typeof value === "number" && Number.isFinite(value) && value >= minimum && value <= maximum;
}
function validAnchor(value) {
  return keys(value, ["path", "role", "rect", "viewport"]) &&
    typeof value.path === "string" && value.path.length <= 512 &&
    /^[a-z][a-z0-9-]*:nth-of-type\([1-9][0-9]{0,5}\)(?: > [a-z][a-z0-9-]*:nth-of-type\([1-9][0-9]{0,5}\))*$/.test(value.path) &&
    ROLES.has(value.role) && keys(value.rect, ["x", "y", "width", "height"]) &&
    number(value.rect.x, 0, 1000000) && number(value.rect.y, 0, 1000000) &&
    number(value.rect.width, 0, 100000) && number(value.rect.height, 0, 100000) &&
    keys(value.viewport, ["width", "height"]) &&
    number(value.viewport.width, 1, 20000) && number(value.viewport.height, 1, 20000);
}
function validCreate(value) {
  if (!keys(value, ["screen", "kind", "anchor", "text"], ["proposal", "adjustment", "variant", "context"]) ||
      typeof value.screen !== "string" || !SCREEN.test(value.screen) ||
      !["point", "area", "edit", "adjustment", "variant"].includes(value.kind) || !validAnchor(value.anchor) ||
      !boundedText(value.text) || (!value.text.trim() && ["point", "area"].includes(value.kind))) return false;
  if (Object.hasOwn(value, "context") && (!["point", "area", "edit"].includes(value.kind) ||
      !keys(value.context, ["variant", "target", "values"]) || !validTargetIdentity(value.context) || !validValues(value.context.values))) return false;
  if (value.kind === "edit") return !Object.hasOwn(value, "adjustment") && !Object.hasOwn(value, "variant") &&
    keys(value.proposal, ["property", "value"]) && value.proposal.property === "text" && boundedText(value.proposal.value);
  if (value.kind === "adjustment") return !Object.hasOwn(value, "proposal") && !Object.hasOwn(value, "variant") &&
    keys(value.adjustment, ["variant", "target", "values"]) && validTargetIdentity(value.adjustment) && validValues(value.adjustment.values, false);
  if (value.kind === "variant") return !Object.hasOwn(value, "proposal") && !Object.hasOwn(value, "adjustment") && validKey(value.variant);
  return !["proposal", "adjustment", "variant"].some((key) => Object.hasOwn(value, key));
}
function validTargetIdentity(value) {
  return (value.variant === "" || validKey(value.variant)) && validKey(value.target);
}
function validValues(values, emptyAllowed = true) {
  return values !== null && typeof values === "object" && !Array.isArray(values) &&
    (emptyAllowed || Object.keys(values).length > 0) && Object.keys(values).length <= 8 &&
    Object.entries(values).every(([id, value]) => validKey(id) && validKey(value));
}
function validPatch(value) {
  return keys(value, [], ["status", "reply", "resubmit"]) && Object.keys(value).length > 0 &&
    (!Object.hasOwn(value, "status") || ["open", "fixed"].includes(value.status)) &&
    (!Object.hasOwn(value, "reply") || boundedText(value.reply)) &&
    (!Object.hasOwn(value, "resubmit") || (value.resubmit === true && value.status === "open"));
}
function assertOwned(stat) {
  if (typeof process.getuid === "function" && stat.uid !== process.getuid()) throw new Error("Feedback path is not owned by the current user.");
}
function privateDirectory(directory) {
  const stat = fs.lstatSync(directory);
  if (!stat.isDirectory() || stat.isSymbolicLink() || (stat.mode & 0o077)) throw new Error("Unsafe feedback state directory.");
  assertOwned(stat);
  if (fs.realpathSync(directory) !== path.resolve(directory)) throw new Error("Feedback directory must not contain symbolic links.");
  return stat;
}
function assertPrivateFile(filename, optional = false) {
  let stat;
  try { stat = fs.lstatSync(filename); } catch (error) { if (optional && error.code === "ENOENT") return null; throw error; }
  if (!stat.isFile() || stat.isSymbolicLink() || stat.nlink !== 1 || (stat.mode & 0o077)) throw new Error("Unsafe feedback state file.");
  assertOwned(stat);
  return stat;
}
function readPrivateJson(directory, filename, maxBytes = MAX_STORE_BYTES) {
  privateDirectory(directory);
  const target = path.join(directory, filename);
  const expected = assertPrivateFile(target);
  if (expected.size > maxBytes) throw new Error("Feedback state file is too large.");
  const fd = fs.openSync(target, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
  try {
    const stat = fs.fstatSync(fd);
    if (!stat.isFile() || stat.dev !== expected.dev || stat.ino !== expected.ino || stat.size !== expected.size) throw new Error("Feedback state file changed while opening.");
    const bytes = Buffer.alloc(maxBytes + 1);
    let size = 0;
    while (size < bytes.length) {
      const count = fs.readSync(fd, bytes, size, bytes.length - size, null);
      if (!count) break;
      size += count;
    }
    const after = fs.fstatSync(fd);
    if (size > maxBytes || size !== stat.size || after.size !== stat.size || after.mtimeMs !== stat.mtimeMs || after.ctimeMs !== stat.ctimeMs || after.nlink !== 1) throw new Error("Feedback state file changed while reading.");
    try { return JSON.parse(bytes.subarray(0, size).toString("utf8")); }
    catch { throw new Error("Invalid private preview state JSON."); }
  } finally { fs.closeSync(fd); }
}

class FeedbackStore {
  constructor(directory) {
    this.directory = directory;
    this.directoryStat = privateDirectory(directory);
    this.filename = path.join(directory, "comments.json");
    this.state = { schemaVersion: 1, revision: 0, submission: 0, screens: [], comments: [], decisions: [], submittedDecisions: [] };
    this.persist(this.state);
  }
  assertDirectory() {
    const directory = privateDirectory(this.directory);
    if (directory.dev !== this.directoryStat.dev || directory.ino !== this.directoryStat.ino) throw new Error("Feedback directory changed.");
  }
  persist(next) {
    this.assertDirectory();
    assertPrivateFile(this.filename, true);
    const content = `${JSON.stringify(next)}\n`;
    if (Buffer.byteLength(content) > MAX_STORE_BYTES) throw new FeedbackError(429, "Feedback storage limit reached.");
    const temporary = path.join(this.directory, `.comments-${crypto.randomBytes(12).toString("hex")}.tmp`);
    let fd;
    let opened;
    try {
      fd = fs.openSync(temporary, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_NOFOLLOW, 0o600);
      // O_NOFOLLOW protects the leaf only. Recheck its ancestors after opening,
      // before any feedback bytes can enter a replacement directory.
      this.assertDirectory();
      opened = fs.fstatSync(fd);
      assertOwned(opened);
      const linked = assertPrivateFile(temporary);
      if (!opened.isFile() || opened.nlink !== 1 || (opened.mode & 0o077) || opened.dev !== linked.dev || opened.ino !== linked.ino) throw new Error("Feedback temporary file changed while opening.");
      fs.writeFileSync(fd, content, "utf8");
      fs.fsyncSync(fd);
      fs.closeSync(fd); fd = undefined;
      this.assertDirectory();
      const beforeRename = assertPrivateFile(temporary);
      if (beforeRename.dev !== opened.dev || beforeRename.ino !== opened.ino) throw new Error("Feedback temporary file changed before commit.");
      assertPrivateFile(this.filename, true);
      this.assertDirectory();
      fs.renameSync(temporary, this.filename);
    } finally {
      if (fd !== undefined) fs.closeSync(fd);
      // If directory identity is uncertain, leave the uncommitted file alone.
      // Cleanup must never traverse the replacement path into another directory.
      if (opened) {
        try {
          this.assertDirectory();
          const remaining = assertPrivateFile(temporary, true);
          if (remaining && remaining.dev === opened.dev && remaining.ino === opened.ino) fs.unlinkSync(temporary);
        } catch { /* An altered path is not a safe cleanup target. */ }
      }
    }
    this.state = next;
  }
  change(update) {
    const next = JSON.parse(JSON.stringify(this.state));
    update(next);
    next.revision += 1;
    this.persist(next);
    return this.snapshot();
  }
  snapshot() {
    const { revision, submission, screens, comments, decisions, submittedDecisions } = this.state;
    return JSON.parse(JSON.stringify({ revision, submission, screens, comments, decisions, submittedDecisions }));
  }
  knowScreen(screen, filename, design = null) {
    if (design !== null && !validDesign(design)) throw new FeedbackError(400, "Invalid design descriptor.");
    if (!SCREEN.test(screen) || this.state.screens.some((item) => item.screen === screen)) return;
    if (this.state.screens.length >= MAX_SCREENS) throw new FeedbackError(429, "Screen limit reached. Start a new preview session.");
    this.change((state) => { state.screens.push({ screen, filename: path.basename(filename), ...(design === null ? {} : { design }) }); });
  }
  requireScreen(screen) {
    if (!this.state.screens.some((item) => item.screen === screen)) throw new FeedbackError(409, "Feedback belongs to an unknown screen.");
  }
  create(value) {
    if (!validCreate(value)) throw new FeedbackError(400, "Invalid comment.");
    this.requireScreen(value.screen);
    if (Object.hasOwn(value, "context")) this.requireTarget(value.screen, value.context);
    if (value.kind === "adjustment") this.requireTarget(value.screen, value.adjustment);
    if (value.kind === "variant" && !this.requireDesign(value.screen).variants.some((variant) => variant.key === value.variant)) throw new FeedbackError(400, "Unknown variant preference.");
    if (this.state.comments.length >= MAX_COMMENTS) throw new FeedbackError(429, "Comment limit reached. Delete older comments or start a new session.");
    return this.change((state) => {
      const now = new Date().toISOString();
      state.comments.push({ ...value, id: crypto.randomBytes(12).toString("hex"), status: "open", reply: "", createdAt: now, updatedAt: now, submission: 0 });
    });
  }
  patch(id, value) {
    if (!ID.test(id) || !validPatch(value)) throw new FeedbackError(400, "Invalid comment update.");
    if (!this.state.comments.some((item) => item.id === id)) throw new FeedbackError(404, "Comment not found.");
    const { resubmit, ...patch } = value;
    return this.change((state) => Object.assign(state.comments.find((item) => item.id === id), patch,
      ...(resubmit ? [{ submission: 0 }] : []), { updatedAt: new Date().toISOString() }));
  }
  delete(id, value) {
    if (!ID.test(id) || !keys(value, [])) throw new FeedbackError(400, "Invalid comment deletion.");
    if (!this.state.comments.some((item) => item.id === id)) throw new FeedbackError(404, "Comment not found.");
    return this.change((state) => { state.comments = state.comments.filter((item) => item.id !== id); });
  }
  requireDesign(screen) {
    this.requireScreen(screen);
    const design = this.state.screens.find((item) => item.screen === screen).design;
    if (!design) throw new FeedbackError(409, "This screen has no design controls.");
    return design;
  }
  requireTarget(screen, value) {
    const design = this.requireDesign(screen);
    const target = design.targets.find((item) => item.variant === value.variant && item.key === value.target);
    if (!target || !Object.entries(value.values).every(([id, option]) => target.controls.some((control) => control.id === id && control.options.some((item) => item.value === option)))) throw new FeedbackError(400, "Unknown design target or setting.");
    return target;
  }
  keep(value) {
    if (!keys(value, ["screen", "variant", "target", "values", "text"]) || typeof value.screen !== "string" || !SCREEN.test(value.screen) ||
        !validTargetIdentity(value) || !validValues(value.values) || !boundedText(value.text)) throw new FeedbackError(400, "Invalid design decision.");
    this.requireTarget(value.screen, value);
    // Re-keeping an unsent release cancels that pending change. Reuse its ID
    // so a scoped batch cannot publish a second active copy of the same hold.
    const existing = this.state.decisions.find((item) => item.variant === value.variant && item.target === value.target &&
      (item.state === "active" || (item.state === "released" && item.submission === 0)));
    if (!existing && this.state.decisions.length >= MAX_DECISIONS) throw new FeedbackError(429, "Decision limit reached. Start a new preview session.");
    return this.change((state) => {
      const now = new Date().toISOString();
      const changes = { ...value, state: "active", submission: 0, updatedAt: now };
      if (existing) Object.assign(state.decisions.find((item) => item.id === existing.id), changes);
      else state.decisions.push({ ...changes, id: crypto.randomBytes(12).toString("hex"), createdAt: now });
    });
  }
  release(id, value) {
    if (!ID.test(id) || !keys(value, [])) throw new FeedbackError(400, "Invalid decision release.");
    const existing = this.state.decisions.find((item) => item.id === id);
    if (!existing) throw new FeedbackError(404, "Decision not found.");
    if (existing.state !== "active") throw new FeedbackError(409, "Decision is already released.");
    return this.change((state) => Object.assign(state.decisions.find((item) => item.id === id), { state: "released", submission: 0, updatedAt: new Date().toISOString() }));
  }
  submit(value) {
    if (!keys(value, [], ["screen", "revision"]) || (Object.hasOwn(value, "screen") && (typeof value.screen !== "string" || !SCREEN.test(value.screen))) ||
        (Object.hasOwn(value, "revision") && (!Number.isSafeInteger(value.revision) || value.revision < 0))) throw new FeedbackError(400, "Invalid submission.");
    if (Object.hasOwn(value, "revision") && value.revision !== this.state.revision) throw new FeedbackError(409, "Feedback changed. Review the current feedback before submitting.");
    if (Object.hasOwn(value, "screen")) this.requireScreen(value.screen);
    const matches = (item) => (!Object.hasOwn(value, "screen") || item.screen === value.screen) && item.submission === 0;
    if (!this.state.comments.some(matches) && !this.state.decisions.some(matches)) throw new FeedbackError(409, "No unsent feedback to submit.");
    return this.change((state) => {
      state.submission += 1;
      for (const comment of state.comments) if (matches(comment)) comment.submission = state.submission;
      for (const decision of state.decisions) {
        if (!matches(decision)) continue;
        decision.submission = state.submission;
        // Pending edits and releases must not alter the accepted constraints
        // delivered to the working session before this explicit batch.
        const published = JSON.parse(JSON.stringify(decision));
        const index = state.submittedDecisions.findIndex((item) => item.id === decision.id);
        if (index === -1) state.submittedDecisions.push(published);
        else state.submittedDecisions[index] = published;
      }
    });
  }
}
module.exports = { FeedbackStore, FeedbackError, FeedbackMutationReceipts, MAX_MUTATION_RECEIPTS, MAX_BODY_BYTES, MAX_STORE_BYTES, MAX_COMMENTS, MAX_DECISIONS, validCreate, validPatch, keys, ID, SCREEN, readPrivateJson };
