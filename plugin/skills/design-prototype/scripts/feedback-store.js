"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const MAX_COMMENTS = 200;
const MAX_SCREENS = 100;
const MAX_STORE_BYTES = 2 * 1024 * 1024;
const MAX_BODY_BYTES = 16 * 1024;
const SCREEN = /^[a-f0-9]{32}$/;
const ID = /^[a-f0-9]{24}$/;
const ROLES = new Set(["", "button", "link", "textbox", "heading", "img", "navigation", "main", "region", "group", "list", "listitem", "checkbox", "radio", "combobox", "tab", "tabpanel", "table", "row", "cell", "alert", "status", "presentation", "none"]);

class FeedbackError extends Error {
  constructor(status, message) { super(message); this.status = status; }
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
  return keys(value, ["screen", "kind", "anchor", "text"], ["proposal"]) &&
    typeof value.screen === "string" && SCREEN.test(value.screen) &&
    ["point", "area", "edit"].includes(value.kind) && validAnchor(value.anchor) &&
    boundedText(value.text) && (value.text.trim().length > 0 || value.kind === "edit") &&
    (value.kind === "edit"
      ? keys(value.proposal, ["property", "value"]) && value.proposal.property === "text" && boundedText(value.proposal.value)
      : !Object.hasOwn(value, "proposal"));
}
function validPatch(value) {
  return keys(value, [], ["status", "reply"]) && Object.keys(value).length > 0 &&
    (!Object.hasOwn(value, "status") || ["open", "fixed"].includes(value.status)) &&
    (!Object.hasOwn(value, "reply") || boundedText(value.reply));
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
    this.state = { schemaVersion: 1, revision: 0, submission: 0, screens: [], comments: [] };
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
    const { revision, submission, screens, comments } = this.state;
    return JSON.parse(JSON.stringify({ revision, submission, screens, comments }));
  }
  knowScreen(screen, filename) {
    if (!SCREEN.test(screen) || this.state.screens.some((item) => item.screen === screen)) return;
    if (this.state.screens.length >= MAX_SCREENS) throw new FeedbackError(429, "Screen limit reached. Start a new preview session.");
    this.change((state) => { state.screens.push({ screen, filename: path.basename(filename) }); });
  }
  requireScreen(screen) {
    if (!this.state.screens.some((item) => item.screen === screen)) throw new FeedbackError(409, "Feedback belongs to an unknown screen.");
  }
  create(value) {
    if (!validCreate(value)) throw new FeedbackError(400, "Invalid comment.");
    this.requireScreen(value.screen);
    if (this.state.comments.length >= MAX_COMMENTS) throw new FeedbackError(429, "Comment limit reached. Delete older comments or start a new session.");
    return this.change((state) => {
      const now = new Date().toISOString();
      state.comments.push({ ...value, id: crypto.randomBytes(12).toString("hex"), status: "open", reply: "", createdAt: now, updatedAt: now, submission: 0 });
    });
  }
  patch(id, value) {
    if (!ID.test(id) || !validPatch(value)) throw new FeedbackError(400, "Invalid comment update.");
    if (!this.state.comments.some((item) => item.id === id)) throw new FeedbackError(404, "Comment not found.");
    return this.change((state) => Object.assign(state.comments.find((item) => item.id === id), value, { updatedAt: new Date().toISOString() }));
  }
  delete(id, value) {
    if (!ID.test(id) || !keys(value, [])) throw new FeedbackError(400, "Invalid comment deletion.");
    if (!this.state.comments.some((item) => item.id === id)) throw new FeedbackError(404, "Comment not found.");
    return this.change((state) => { state.comments = state.comments.filter((item) => item.id !== id); });
  }
  submit(value) {
    if (!keys(value, [], ["screen"]) || (Object.hasOwn(value, "screen") && (typeof value.screen !== "string" || !SCREEN.test(value.screen)))) throw new FeedbackError(400, "Invalid submission.");
    if (Object.hasOwn(value, "screen")) this.requireScreen(value.screen);
    const matches = (item) => (!Object.hasOwn(value, "screen") || item.screen === value.screen) && item.submission === 0;
    if (!this.state.comments.some(matches)) throw new FeedbackError(409, "No unsent comments to submit.");
    return this.change((state) => {
      state.submission += 1;
      for (const comment of state.comments) if (matches(comment)) comment.submission = state.submission;
    });
  }
}
module.exports = { FeedbackStore, FeedbackError, MAX_BODY_BYTES, MAX_STORE_BYTES, MAX_COMMENTS, validCreate, validPatch, keys, ID, SCREEN, readPrivateJson };
