"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { validDesign, validKey } = require("./design-contract.js");
const { normalizeApplicationRoute, validApplicationScreen, validApplicationContext, screenIdentity: applicationScreenIdentity } = require("./application-contract.js");

const MAX_COMMENTS = 200;
const MAX_SUBMISSIONS = 200;
const MAX_SCREENS = 100;
const MAX_STORE_BYTES = 2 * 1024 * 1024;
const MAX_BODY_BYTES = 16 * 1024;
const MAX_MUTATION_RECEIPTS = 2048;
// A saved project workspace keeps its journal when it is reopened.
const SAVED_LIMIT = "Reopening it in a new session keeps the same limit.";
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
    try { operation(value); }
    catch (error) {
      // A post-rename durability failure is uncertain to the caller, but the
      // operation already exists. Preserve its retry identity before surfacing it.
      if (error.committed === true) this.receipts.set(id, fingerprint);
      throw error;
    }
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
  if (!keys(value, ["screen", "kind", "anchor", "text"], ["proposal", "adjustment", "variant", "context", "applicationContext"]) ||
      typeof value.screen !== "string" || !SCREEN.test(value.screen) ||
      !["point", "area", "edit", "adjustment", "variant"].includes(value.kind) || !validAnchor(value.anchor) ||
      !boundedText(value.text) || (!value.text.trim() && ["point", "area"].includes(value.kind))) return false;
  if (Object.hasOwn(value, "applicationContext")) return ["point", "area"].includes(value.kind) &&
    !["context", "proposal", "adjustment", "variant"].some(key => Object.hasOwn(value, key)) && validApplicationContext(value.applicationContext);
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
function matchesScreenSource(value, screen) {
  if (!screen) return false;
  return screen.source?.kind === "application"
    ? Object.hasOwn(value, "applicationContext") && value.applicationContext.route === screen.source.route
    : !Object.hasOwn(value, "applicationContext");
}
function validPatch(value) {
  return keys(value, [], ["status", "reply", "resubmit", "expectedSubmission"]) &&
    ["status", "reply", "resubmit"].some((key) => Object.hasOwn(value, key)) &&
    (!Object.hasOwn(value, "status") || ["open", "fixed"].includes(value.status)) &&
    (!Object.hasOwn(value, "reply") || boundedText(value.reply)) &&
    (!Object.hasOwn(value, "expectedSubmission") || (Number.isSafeInteger(value.expectedSubmission) && value.expectedSubmission >= 0)) &&
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

// Project artifacts are user-editable data. Validate their complete shape
// before hydration; never turn saved data into session or tool authority.
function validPersistedFeedback(state) {
  const integer = (value, maximum = Number.MAX_SAFE_INTEGER) => Number.isSafeInteger(value) && value >= 0 && value <= maximum;
  const timestamp = value => typeof value === "string" && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(value) && Number.isFinite(Date.parse(value));
  const unique = (items, field) => new Set(items.map(item => item[field])).size === items.length;
  if (!keys(state, ["schemaVersion", "revision", "submission", "screens", "comments", "submissions"], ["canvas", "workspace"]) ||
      state.schemaVersion !== 1 || !integer(state.revision) || !integer(state.submission, MAX_SUBMISSIONS)) return false;
  for (const [field, limit] of [["screens", MAX_SCREENS], ["comments", MAX_COMMENTS], ["submissions", MAX_SUBMISSIONS]]) {
    if (!Array.isArray(state[field]) || state[field].length > limit || state[field].some(item => !item || typeof item !== "object" || Array.isArray(item))) return false;
  }
  if (!unique(state.screens, "screen") || !state.screens.every(item => validApplicationScreen(item) ||
      keys(item, ["screen", "filename"], ["design"]) && typeof item.screen === "string" && SCREEN.test(item.screen) &&
      typeof item.filename === "string" && /^[a-z0-9][a-z0-9-]{0,95}\.html$/i.test(item.filename) && (!Object.hasOwn(item, "design") || validDesign(item.design)))) return false;
  const screens = new Map(state.screens.map(item => [item.screen, item]));
  const target = (screen, value) => {
    const descriptor = screens.get(screen)?.design?.targets.find(item => item.key === value.target && item.variant === value.variant);
    return descriptor && Object.entries(value.values).every(([id, option]) => descriptor.controls.some(control => control.id === id && control.options.some(item => item.value === option)));
  };
  const comment = item => {
    if (!keys(item, ["screen", "kind", "anchor", "text", "id", "status", "reply", "createdAt", "updatedAt", "submission", "lastSubmission"], ["proposal", "adjustment", "variant", "context", "applicationContext"])) return false;
    const { id, status, reply, createdAt, updatedAt, submission, lastSubmission, ...input } = item;
    return validCreate(input) && matchesScreenSource(input, screens.get(item.screen)) && typeof id === "string" && ID.test(id) && ["open", "fixed"].includes(status) && boundedText(reply) &&
      timestamp(createdAt) && timestamp(updatedAt) && integer(submission, state.submission) && integer(lastSubmission, state.submission) && submission <= lastSubmission &&
      (!item.context || target(item.screen, item.context)) && (item.kind !== "adjustment" || target(item.screen, item.adjustment)) &&
      (item.kind !== "variant" || screens.get(item.screen)?.design?.variants.some(value => value.key === item.variant));
  };
  if (!unique(state.comments, "id") || !state.comments.every(comment) || state.submissions.length !== state.submission) return false;
  const journalComments = new Map();
  const immutableComment = ({ status, reply, updatedAt, submission, lastSubmission, ...source }) => canonicalJson(source);
  let previousRevision = 0;
  for (let index = 0; index < state.submissions.length; index += 1) {
    const batch = state.submissions[index];
    if (!keys(batch, ["submission", "revision", "submittedAt", "comments"]) || batch.submission !== index + 1 || !integer(batch.revision, state.revision) || !timestamp(batch.submittedAt) ||
        !Array.isArray(batch.comments) || batch.comments.length > MAX_COMMENTS ||
        !batch.comments.every(item => item && comment(item) && item.submission === batch.submission && item.lastSubmission === batch.submission) ||
        !unique(batch.comments, "id") || batch.revision <= previousRevision || batch.comments.length === 0) return false;
    previousRevision = batch.revision;
    for (const item of batch.comments) {
      const prior = journalComments.get(item.id);
      if (prior && immutableComment(prior) !== immutableComment(item)) return false;
      journalComments.set(item.id, item);
    }
  }
  if (!state.comments.every(item => {
    const last = journalComments.get(item.id);
    return (item.submission === 0 || item.submission === item.lastSubmission) &&
      (last ? item.lastSubmission === last.submission && immutableComment(item) === immutableComment(last) : item.lastSubmission === 0);
  })) return false;
  if (state.canvas !== undefined) {
    if (!keys(state.canvas, ["rounds"]) || !Array.isArray(state.canvas.rounds) || state.canvas.rounds.length !== state.submission || !state.canvas.rounds.every((item, index) =>
      keys(item, ["submission", "delivery", "review", "reply"], ["previousSession"]) && item.submission === index + 1 && ["sending", "queued", "unknown"].includes(item.delivery) &&
      ["unread", "working", "answered"].includes(item.review) && boundedText(item.reply) && (item.review !== "answered" || Boolean(item.reply.trim())) &&
      (!Object.hasOwn(item, "previousSession") || typeof item.previousSession === "boolean"))) return false;
  }
  return true;
}

class FeedbackStore {
  constructor(directory, { canvas = false, persistence = null, initialWorkspace = null } = {}) {
    this.directory = directory;
    this.directoryStat = privateDirectory(directory);
    this.filename = path.join(directory, "comments.json");
    this.persistence = persistence;
    const restored = persistence?.load();
    if (restored) {
      if (!validPersistedFeedback(restored) || !restored.canvas || !canvas) throw new FeedbackError(400, "Invalid saved feedback state.");
      this.state = JSON.parse(JSON.stringify(restored));
      return;
    }
    this.state = { schemaVersion: 1, revision: 0, submission: 0, screens: [], comments: [], submissions: [] };
    if (canvas) this.state.canvas = { rounds: [] };
    if (persistence && initialWorkspace) this.state.workspace = initialWorkspace;
    this.persist(this.state);
  }
  assertDirectory() {
    const directory = privateDirectory(this.directory);
    if (directory.dev !== this.directoryStat.dev || directory.ino !== this.directoryStat.ino) throw new Error("Feedback directory changed.");
  }
  persist(next) {
    if (this.persistence) {
      try { this.persistence.persist(next); }
      catch (error) { if (error.committed === true) this.state = next; throw error; }
      this.state = next;
      return;
    }
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
    if (this.state.revision >= Number.MAX_SAFE_INTEGER) throw new FeedbackError(429, "Feedback revision limit reached.");
    const next = JSON.parse(JSON.stringify(this.state));
    update(next);
    next.revision += 1;
    this.persist(next);
    return this.snapshot();
  }
  snapshot() {
    const { revision, submission, screens, comments } = this.state;
    return JSON.parse(JSON.stringify({ revision, submission, screens, comments,
      ...(this.state.canvas ? { canvas: this.state.canvas } : {}) }));
  }
  nextSubmission(after) {
    if (!Number.isSafeInteger(after) || after < 0) throw new FeedbackError(400, "Invalid submission cursor.");
    if (after > this.state.submission) throw new FeedbackError(409, "Submission cursor belongs to a different or newer preview session.");
    const batch = this.state.submissions.find((item) => item.submission > after);
    const comments = batch ? batch.comments : [];
    const screens = new Set(comments.map((item) => item.screen));
    const currentComments = comments.map(({ id }) => {
      const current = this.state.comments.find((item) => item.id === id);
      return current ? { id, present: true, status: current.status, submission: current.submission, reply: current.reply, updatedAt: current.updatedAt }
        : { id, present: false };
    });
    return JSON.parse(JSON.stringify({
      revision: batch ? batch.revision : this.state.revision,
      submission: batch ? batch.submission : this.state.submission,
      latestSubmission: this.state.submission,
      hasMore: Boolean(batch && batch.submission < this.state.submission),
      submittedAt: batch ? batch.submittedAt : null,
      screens: this.state.screens.filter((item) => screens.has(item.screen)),
      comments, currentComments,
    }));
  }
  knowScreen(screen, filename, design = null) {
    if (design !== null && !validDesign(design)) throw new FeedbackError(400, "Invalid design descriptor.");
    if (!SCREEN.test(screen) || this.state.screens.some((item) => item.screen === screen)) return;
    if (this.state.screens.length >= MAX_SCREENS) throw new FeedbackError(429, "Screen limit reached. Start a new preview session.");
    this.change((state) => { state.screens.push({ screen, filename: path.basename(filename), ...(design === null ? {} : { design }) }); });
  }
  knowApplicationScreen(value) {
    if (!keys(value, ["checkpoint", "route"])) throw new FeedbackError(400, "Invalid application screen.");
    const checkpoint = value.checkpoint, route = normalizeApplicationRoute(value.route, this.state.workspace?.source?.resourceQueryKeys || []);
    const screen = applicationScreenIdentity(checkpoint, route);
    const record = { screen, source: { kind: "application", checkpoint, route } };
    if (!validApplicationScreen(record)) throw new FeedbackError(400, "Invalid application screen.");
    const existing = this.state.screens.find(item => item.screen === screen);
    if (existing) {
      if (canonicalJson(existing) !== canonicalJson(record)) throw new FeedbackError(409, "This application screen has a different recorded source.");
      return screen;
    }
    if (this.state.screens.length >= MAX_SCREENS) throw new FeedbackError(429, this.state.workspace
      ? `Screen limit reached in this saved workspace. Create a new workspace. ${SAVED_LIMIT}`
      : "Screen limit reached. Start a new preview session.");
    this.change(state => { state.screens.push(record); });
    return screen;
  }
  requireScreen(screen) {
    if (!this.state.screens.some((item) => item.screen === screen)) throw new FeedbackError(409, "Feedback belongs to an unknown screen.");
  }
  create(value, applicationScreen = null) {
    if (!validCreate(value)) throw new FeedbackError(400, "Invalid comment.");
    const known = this.state.screens.find(item => item.screen === value.screen);
    if (applicationScreen !== null) {
      if (!validApplicationScreen(applicationScreen) || applicationScreen.screen !== value.screen ||
          !matchesScreenSource(value, applicationScreen) || known && canonicalJson(known) !== canonicalJson(applicationScreen)) {
        throw new FeedbackError(400, "Invalid application comment page.");
      }
      if (!known && this.state.screens.length >= MAX_SCREENS) throw new FeedbackError(429, "This room has feedback on 100 pages. Start a new room to comment on another page; existing feedback can still be sent.");
    } else this.requireScreen(value.screen);
    if (!matchesScreenSource(value, known || applicationScreen)) throw new FeedbackError(409, "The comment context does not match its recorded screen source and route.");
    if (Object.hasOwn(value, "context")) this.requireTarget(value.screen, value.context);
    if (value.kind === "adjustment") this.requireTarget(value.screen, value.adjustment);
    if (value.kind === "variant" && !this.requireDesign(value.screen).variants.some((variant) => variant.key === value.variant)) throw new FeedbackError(400, "Unknown variant preference.");
    if (this.state.comments.length >= MAX_COMMENTS) throw new FeedbackError(429, this.state.workspace
      ? `Comment limit reached in this saved workspace. Delete older comments or create a new workspace. ${SAVED_LIMIT}`
      : "Comment limit reached. Delete older comments or start a new session.");
    return this.change((state) => {
      if (!known && applicationScreen) state.screens.push(JSON.parse(JSON.stringify(applicationScreen)));
      const now = new Date().toISOString();
      state.comments.push({ ...JSON.parse(JSON.stringify(value)), id: crypto.randomBytes(12).toString("hex"), status: "open", reply: "", createdAt: now, updatedAt: now, submission: 0, lastSubmission: 0 });
    });
  }
  editDraft(id, value) {
    if (typeof id !== "string" || !ID.test(id) || !keys(value, ["text", "expectedRevision"])
        || !boundedText(value.text) || !value.text.trim() || !Number.isSafeInteger(value.expectedRevision) || value.expectedRevision < 0) throw new FeedbackError(400, "Invalid draft edit.");
    const current = this.state.comments.find(item => item.id === id);
    if (!current) throw new FeedbackError(404, "Comment not found.");
    if (current.submission !== 0 || current.lastSubmission !== 0) throw new FeedbackError(409, "A submitted comment cannot be rewritten. Add a new comment for a changed request.");
    if (value.expectedRevision !== this.state.revision) throw new FeedbackError(409, "Feedback changed. Read the current draft before editing it.");
    const text = value.text.trim();
    if (text === current.text) return this.snapshot();
    return this.change(state => Object.assign(state.comments.find(item => item.id === id), { text, updatedAt: new Date().toISOString() }));
  }
  patch(id, value) {
    if (!ID.test(id) || !validPatch(value)) throw new FeedbackError(400, "Invalid comment update.");
    const current = this.state.comments.find((item) => item.id === id);
    if (!current) throw new FeedbackError(404, "Comment not found.");
    if (Object.hasOwn(value, "expectedSubmission") && value.expectedSubmission !== current.submission) throw new FeedbackError(409, "This comment belongs to a different submission. Read its current status before replying.");
    const { resubmit, expectedSubmission, ...patch } = value;
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
  submit(value) {
    if (!keys(value, [], ["screen", "revision"]) || (Object.hasOwn(value, "screen") && (typeof value.screen !== "string" || !SCREEN.test(value.screen))) ||
        (Object.hasOwn(value, "revision") && (!Number.isSafeInteger(value.revision) || value.revision < 0))) throw new FeedbackError(400, "Invalid submission.");
    if (Object.hasOwn(value, "revision") && value.revision !== this.state.revision) throw new FeedbackError(409, "Feedback changed. Review the current feedback before submitting.");
    if (Object.hasOwn(value, "screen")) this.requireScreen(value.screen);
    if (this.state.canvas?.rounds.some((round) => !round.previousSession && round.review === "unread" && ["sending", "unknown"].includes(round.delivery))) {
      throw new FeedbackError(409, "The previous delivery must be acknowledged before another round is submitted.");
    }
    const matches = (item) => (!Object.hasOwn(value, "screen") || item.screen === value.screen) && item.submission === 0;
    if (!this.state.comments.some(matches)) throw new FeedbackError(409, "No unsent feedback to submit.");
    if (this.state.submissions.length >= MAX_SUBMISSIONS) throw new FeedbackError(429, this.state.workspace
      ? `Submission limit reached in this saved workspace. Create a new workspace to send more rounds. ${SAVED_LIMIT}`
      : "Submission limit reached. Start a new preview session.");
    return this.change((state) => {
      state.submission += 1;
      const batch = { submission: state.submission, revision: state.revision + 1, submittedAt: new Date().toISOString(), comments: [] };
      for (const comment of state.comments) {
        if (!matches(comment)) continue;
        comment.submission = state.submission;
        comment.lastSubmission = state.submission;
        batch.comments.push(JSON.parse(JSON.stringify(comment)));
      }
      state.submissions.push(batch);
      // Delivery metadata belongs to this same atomic commit. It never changes
      // the immutable batch, and only the bound parent transport can update it.
      if (state.canvas) state.canvas.rounds.push({ submission: state.submission, delivery: "sending", review: "unread", reply: "", ...(state.workspace ? { previousSession: false } : {}) });
    });
  }
}
module.exports = { FeedbackStore, FeedbackError, FeedbackMutationReceipts, MAX_MUTATION_RECEIPTS, MAX_BODY_BYTES, MAX_STORE_BYTES, MAX_COMMENTS, MAX_SUBMISSIONS, validCreate, validPatch, validPersistedFeedback, keys, ID, SCREEN, readPrivateJson };
