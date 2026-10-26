"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { validDesign, MAX_DESIGN_BYTES } = require("./design-contract.js");

// Each version keeps its descriptor in the state, so 100 large descriptors fit.
const MAX_STATE_BYTES = 4 * 1024 * 1024;
const MAX_HTML_BYTES = 2 * 1024 * 1024;
const MAX_WORKSPACE_BYTES = 64 * 1024 * 1024;
const MAX_REVISIONS = 100;
const HASH = /^[a-f0-9]{64}$/;
const FILENAME = /^[a-z0-9][a-z0-9-]{0,95}\.html$/;
const DESCRIPTOR = /^[a-z0-9][a-z0-9-]{0,95}\.design\.json$/;
const CLAIM = /^([1-9][0-9]*)-([a-f0-9]{32})\.json$/;
const MAX_CLAIMS = 128;

// Messages are fixed English text plus at most a validated revision filename,
// never a path or user content, so a client error can be shown as it is.
function fail(status, message, errorCode) { throw Object.assign(new Error(message), { status, expose: status < 500, ...(errorCode ? { errorCode } : {}) }); }
function sameFile(a, b) { return a.dev === b.dev && a.ino === b.ino; }
function digest(bytes) { return crypto.createHash("sha256").update(bytes).digest("hex"); }
function owned(stat) { return typeof process.getuid !== "function" || stat.uid === process.getuid(); }
function directory(filename, privateMode = false) {
  const stat = fs.lstatSync(filename);
  if (!stat.isDirectory() || stat.isSymbolicLink() || !owned(stat) || (privateMode && (stat.mode & 0o077))) fail(409, "Unsafe design workspace directory.");
  return stat;
}
function regular(fd, privateMode = false) {
  const stat = fs.fstatSync(fd);
  if (!stat.isFile() || stat.nlink !== 1 || !owned(stat) || (privateMode && (stat.mode & 0o077))) fail(409, "Unsafe design workspace file.");
  return stat;
}
function readFile(filename, maximum, privateMode = false) {
  const fd = fs.openSync(filename, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
  try {
    const before = regular(fd, privateMode);
    if (before.size > maximum) fail(413, "Design workspace file exceeds its size limit.");
    const buffer = Buffer.alloc(maximum + 1);
    let count = 0;
    while (count < buffer.length) {
      const received = fs.readSync(fd, buffer, count, buffer.length - count, null);
      if (!received) break;
      count += received;
    }
    const after = regular(fd, privateMode);
    const linked = fs.lstatSync(filename);
    if (count > maximum || count !== before.size || !sameFile(before, linked) || linked.isSymbolicLink()
        || after.size !== before.size || after.mtimeMs !== before.mtimeMs || after.ctimeMs !== before.ctimeMs) fail(409, "Design workspace file changed while reading.");
    return { bytes: buffer.subarray(0, count), stat: after };
  } finally { fs.closeSync(fd); }
}
function syncDirectory(filename) {
  const fd = fs.openSync(filename, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_DIRECTORY);
  try { fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
}
function writeExclusive(filename, bytes, assertParent) {
  const fd = fs.openSync(filename, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_NOFOLLOW, 0o600);
  let stat, complete = false;
  try {
    stat = regular(fd, true);
    assertParent();
    if (!sameFile(stat, fs.lstatSync(filename))) fail(409, "Design workspace file changed while opening.");
    fs.writeFileSync(fd, bytes);
    fs.fsyncSync(fd);
    complete = true;
    return stat;
  } finally {
    fs.closeSync(fd);
    if (!complete && stat) {
      try { assertParent(); removeExact(filename, stat); } catch { /* Never clean up through changed ancestors. */ }
    }
  }
}
function removeExact(filename, stat) {
  try {
    const current = fs.lstatSync(filename);
    if (sameFile(current, stat) && current.isFile() && !current.isSymbolicLink() && current.nlink === 1) fs.unlinkSync(filename);
  } catch (error) { if (error.code !== "ENOENT") throw error; }
}
function alive(pid) {
  try { process.kill(pid, 0); return true; }
  catch (error) { return error.code !== "ESRCH"; }
}
function validWorkspacePath(value) {
  if (typeof value !== "string" || Buffer.byteLength(value) > 240) return false;
  const parts = value.split("/");
  return parts.length >= 1 && parts.length <= 8 && parts.every(part =>
    /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/.test(part)
    && !/^(?:node_modules|__pycache__|con|prn|aux|nul|com[1-9]|lpt[1-9])$/i.test(part));
}

// Each contender owns a unique file forever: stale recovery never removes a
// pathname that another writer could have reused. The choosing/ticket protocol
// orders concurrent live contenders. A late arrival sees the holder's ticket
// and cannot overtake it; a contender still choosing makes acquisition fail
// conservatively rather than wait or guess. No clock-based lease steals a lock.
class WorkspaceClaim {
  constructor(workspace) {
    this.nonce = crypto.randomBytes(16).toString("hex");
    this.ticket = null;
    if (process.platform === "win32" || typeof process.getuid !== "function") fail(501, "Project design workspace locking requires a supported Unix host.");
    // Every local host process must contend in the same namespace, even when
    // its TMPDIR/HOME or the spelling/case of the project path is different.
    const identity = fs.lstatSync(workspace, { bigint: true });
    const root = path.join(fs.realpathSync("/tmp"), `grillmester-design-locks-${process.getuid()}`);
    this.directory = path.join(root, digest(Buffer.from(`${identity.dev}:${identity.ino}`)));
    this.filename = path.join(this.directory, `${process.pid}-${this.nonce}.json`);
    // A closing holder removes the room's lock directory when it is empty, so
    // creating it and the claim can race with that removal; retry briefly.
    for (let attempt = 0; !this.stat; attempt += 1) {
      try {
        for (const entry of [root, this.directory]) {
          try { fs.mkdirSync(entry, { mode: 0o700 }); } catch (error) { if (error.code !== "EEXIST") throw error; }
          directory(entry, true);
        }
        this.directoryStat = directory(this.directory, true);
        this.stat = writeExclusive(this.filename, this.content(), () => this.assertDirectory());
      } catch (error) { if (error.code !== "ENOENT" || attempt >= 2) throw error; }
    }
    try {
      const others = this.scan();
      this.ticket = 1 + Math.max(0, ...others.map(item => item.ticket || 0));
      if (!Number.isSafeInteger(this.ticket)) fail(409, "Design workspace lock capacity reached.");
      const fd = fs.openSync(this.filename, fs.constants.O_WRONLY | fs.constants.O_NOFOLLOW);
      try {
        if (!sameFile(regular(fd, true), this.stat)) fail(409, "Design workspace lock changed.");
        this.assertDirectory();
        fs.ftruncateSync(fd, 0);
        fs.writeFileSync(fd, this.content());
        fs.fsyncSync(fd);
      } finally { fs.closeSync(fd); }
      for (const other of this.scan()) {
        if (other.name === path.basename(this.filename)) continue;
        if (other.ticket === null) fail(409, "Another workspace opener is still acquiring its lock.");
        if (other.ticket < this.ticket || other.ticket === this.ticket && other.name < path.basename(this.filename)) {
          fail(409, `This design workspace is already open in process ${CLAIM.exec(other.name)[1]}. Close that session before opening it here. If no such session runs, remove ${path.join(this.directory, other.name)}.`);
        }
      }
    } catch (error) { this.close(); throw error; }
  }
  content() { return Buffer.from(`${JSON.stringify({ pid: process.pid, nonce: this.nonce, ticket: this.ticket })}\n`); }
  assertDirectory() {
    if (!sameFile(directory(this.directory, true), this.directoryStat)) fail(409, "Design workspace lock directory changed.");
  }
  scan() {
    this.assertDirectory();
    const names = fs.readdirSync(this.directory);
    if (names.length > MAX_CLAIMS * 2) fail(409, "Too many simultaneous workspace open attempts.");
    const result = [];
    for (const name of names) {
      const match = CLAIM.exec(name);
      if (!match || !Number.isSafeInteger(Number(match[1]))) fail(409, "Invalid design workspace lock record.");
      const filename = path.join(this.directory, name);
      let record;
      try { record = readFile(filename, 1024, true); }
      catch (error) { if (error.code === "ENOENT" || !fs.existsSync(filename)) continue; throw error; }
      const pid = Number(match[1]);
      if (!alive(pid)) {
        this.assertDirectory();
        removeExact(filename, record.stat);
        continue;
      }
      let value;
      try { value = JSON.parse(record.bytes.toString("utf8")); } catch { fail(409, "Another workspace opener is still acquiring its lock."); }
      if (!value || Object.keys(value).sort().join(",") !== "nonce,pid,ticket" || value.pid !== pid || value.nonce !== match[2]
          || !(value.ticket === null || Number.isSafeInteger(value.ticket) && value.ticket > 0)) fail(409, "Invalid active design workspace lock record.");
      result.push({ name, ticket: value.ticket });
    }
    if (result.length > MAX_CLAIMS) fail(409, "Too many simultaneous workspace open attempts.");
    return result;
  }
  assert() {
    this.assertDirectory();
    const record = readFile(this.filename, 1024, true);
    if (!sameFile(record.stat, this.stat) || !record.bytes.equals(this.content())) fail(409, "Design workspace lock ownership changed.");
  }
  close() {
    if (!this.stat) return;
    try { this.assertDirectory(); removeExact(this.filename, this.stat); }
    finally {
      this.stat = null;
      try { fs.rmdirSync(this.directory); } catch { /* Another claim or opener keeps the directory. */ }
    }
  }
}

class WorkspaceStore {
  constructor({ projectDir, workspacePath, create = false, title, validateState } = {}) {
    if (typeof projectDir !== "string" || !path.isAbsolute(projectDir) || !validWorkspacePath(workspacePath)
        || typeof create !== "boolean" || typeof validateState !== "function"
        || title != null && (typeof title !== "string" || !title.trim() || Buffer.byteLength(title) > 200 || /[\u0000-\u001f\u007f]/.test(title))) fail(400, "Invalid design workspace configuration.");
    this.workspacePath = workspacePath;
    this.projectDir = fs.realpathSync(projectDir);
    this.directory = path.join(this.projectDir, ...workspacePath.split("/"));
    this.revisionsDir = path.join(this.directory, "revisions");
    this.filename = path.join(this.directory, "workspace.json");
    this.validateState = validateState;
    this.ancestors = [];
    this.created = [];
    this.uncommitted = new Map();
    this.closed = false;
    this.lastBytes = null;
    try {
      this.ancestors.push({ filename: this.projectDir, stat: directory(this.projectDir) });
      let current = this.projectDir;
      for (const part of workspacePath.split("/")) {
        current = path.join(current, part);
        try { directory(current); }
        catch (error) {
          if (error.code !== "ENOENT" || !create) throw error;
          this.assertDirectories();
          fs.mkdirSync(current, { mode: 0o700 });
          this.created.push({ filename: current, stat: directory(current) });
        }
        this.ancestors.push({ filename: current, stat: directory(current) });
      }
      this.claim = new WorkspaceClaim(this.directory);
      this.assertDirectories();
      const inventory = fs.readdirSync(this.directory);
      const visible = names => names.filter(name => !name.startsWith("."));
      if (inventory.includes("revisions") && (create || !inventory.includes("workspace.json"))) directory(this.revisionsDir);
      // Sketch files without their register are never adopted by open or create.
      if (!inventory.includes("workspace.json") && inventory.includes("revisions") && !visible(inventory).some(name => name !== "revisions")
        && fs.readdirSync(this.revisionsDir).some(name => FILENAME.test(name) || DESCRIPTOR.test(name))) fail(409, "Design workspace has sketch revisions but no workspace.json. Restore workspace.json from version control, or move the revisions directory aside to start over.");
      if (create) {
        if (visible(inventory).some(name => name !== "revisions") || inventory.includes("revisions") && visible(fs.readdirSync(this.revisionsDir)).length) fail(409, "Create requires an empty design workspace directory.");
      } else if (!inventory.includes("workspace.json")) fail(404, "Design workspace was not found. Choose Create to start a new room.");
      try { directory(this.revisionsDir); }
      catch (error) {
        if (error.code !== "ENOENT" || !create) throw error;
        fs.mkdirSync(this.revisionsDir, { mode: 0o700 });
        this.created.push({ filename: this.revisionsDir, stat: directory(this.revisionsDir) });
      }
      this.ancestors.push({ filename: this.revisionsDir, stat: directory(this.revisionsDir) });
      const revisionInventory = this.inventory();
      this.initial = create ? null : this.readState();
      if (revisionInventory.bytes + (this.lastBytes?.length || 0) > MAX_WORKSPACE_BYTES) fail(429, "Design workspace storage limit reached.");
    } catch (error) {
      try { this.claim?.close(); } catch { /* Preserve the original failure. */ }
      for (const item of this.created.reverse()) {
        try { if (sameFile(directory(item.filename), item.stat)) fs.rmdirSync(item.filename); } catch { /* Only remove empty directories created by this attempt. */ }
      }
      throw error;
    }
  }
  assertDirectories() {
    for (const item of this.ancestors) if (!sameFile(directory(item.filename), item.stat)) fail(409, "Design workspace directory changed.");
  }
  assertOpen() {
    if (this.closed) fail(410, "Design workspace is closed.");
    this.assertDirectories();
    this.claim.assert();
  }
  readState() {
    this.assertOpen();
    const record = readFile(this.filename, MAX_STATE_BYTES);
    let state;
    try { state = JSON.parse(record.bytes.toString("utf8")); } catch { fail(409, "Design workspace state is not valid JSON."); }
    if (this.validateState(state) !== true) {
      // Kept choices were never released. Name them so such a room is not taken for damage.
      if (state && typeof state === "object" && ["decisions", "submittedDecisions"].some(key => Object.hasOwn(state, key))) {
        fail(409, "Design workspace state was saved by an unreleased build with kept choices, which are no longer supported. The files are unchanged; create a new workspace.");
      }
      fail(409, "Design workspace state is invalid or uses an unsupported version.");
    }
    this.lastBytes = record.bytes;
    return state;
  }
  load() {
    this.assertOpen();
    return this.initial === null ? null : JSON.parse(JSON.stringify(this.initial));
  }
  assertUnchanged() {
    let record;
    try { record = readFile(this.filename, MAX_STATE_BYTES); }
    catch (error) {
      if (error.code === "ENOENT" && this.lastBytes === null) return;
      if (error.code === "ENOENT") fail(409, "Design workspace state was removed outside this view.");
      throw error;
    }
    if (this.lastBytes === null || !this.lastBytes.equals(record.bytes)) fail(409, "Design workspace changed outside this view. Reopen it before saving.");
  }
  inventory() {
    this.assertDirectories();
    let bytes = 0;
    // Only names that can be registered are revision files. Finder, editor and
    // backup files (.DS_Store, ._x, .x.swp, x~) can never be referenced, so they
    // neither block the room nor count towards its limits. The registered
    // version count is enforced by the state; files left by an interrupted save
    // count towards bytes and this scan bound only.
    const names = fs.readdirSync(this.revisionsDir).filter(name => FILENAME.test(name) || DESCRIPTOR.test(name));
    if (names.length > MAX_REVISIONS * 4) fail(429, "Design workspace revision limit reached.");
    for (const name of names) {
      const isHtml = FILENAME.test(name);
      const fd = fs.openSync(path.join(this.revisionsDir, name), fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
      try {
        const stat = regular(fd);
        if (stat.size > (isHtml ? MAX_HTML_BYTES : MAX_DESIGN_BYTES)) fail(413, "Design workspace file exceeds its size limit.");
        bytes += stat.size;
      } finally { fs.closeSync(fd); }
    }
    if (bytes > MAX_WORKSPACE_BYTES) fail(429, "Design workspace storage limit reached.");
    return { bytes };
  }
  persist(nextState) {
    this.assertOpen();
    if (this.validateState(nextState) !== true) fail(400, "Invalid design workspace state.");
    const bytes = Buffer.from(`${JSON.stringify(nextState)}\n`);
    const snapshot = JSON.parse(bytes.toString("utf8"));
    if (bytes.length > MAX_STATE_BYTES) fail(429, "Design workspace state limit reached.");
    if (this.inventory().bytes + bytes.length > MAX_WORKSPACE_BYTES) fail(429, "Design workspace storage limit reached.");
    this.assertUnchanged();
    const temporary = path.join(this.directory, `.workspace-${crypto.randomBytes(16).toString("hex")}.tmp`);
    let stat, committed = false, failure;
    try {
      stat = writeExclusive(temporary, bytes, () => this.assertOpen());
      this.assertOpen();
      this.assertUnchanged();
      if (!sameFile(fs.lstatSync(temporary), stat)) fail(409, "Design workspace temporary file changed.");
      fs.renameSync(temporary, this.filename);
      // Rename is the commit boundary. A later fsync/cleanup failure must not
      // make a caller delete referenced revisions or retry a committed write.
      committed = true;
      this.lastBytes = bytes;
      this.initial = snapshot;
      for (const [filename, pending] of this.uncommitted) {
        if (snapshot.workspace?.revisions?.some(meta => ["filename", "hash", "designHash", "bytes"].every(key => meta[key] === pending.meta[key]))) this.uncommitted.delete(filename);
      }
      syncDirectory(this.directory);
    } catch (error) { failure = error; }
    finally {
      if (stat) {
        try { this.assertDirectories(); removeExact(temporary, stat); }
        catch (error) { failure ??= error; }
      }
    }
    if (failure) { if (committed) failure.committed = true; throw failure; }
  }
  writeRevision({ filename, html, design = null } = {}) {
    this.assertOpen();
    this.assertUnchanged();
    if (typeof filename !== "string" || !FILENAME.test(filename) || typeof html !== "string" || !html.trim()
        || design !== null && !validDesign(design)) fail(400, "Invalid immutable design revision.");
    const htmlBytes = Buffer.from(html);
    const designBytes = design === null ? null : Buffer.from(`${JSON.stringify(design)}\n`);
    if (htmlBytes.length > MAX_HTML_BYTES || designBytes && designBytes.length > MAX_DESIGN_BYTES) fail(413, "Design revision exceeds its size limit.");
    const inventory = this.inventory();
    if (inventory.bytes + htmlBytes.length + (designBytes?.length || 0) + (this.lastBytes?.length || 0) > MAX_WORKSPACE_BYTES) fail(429, "Design workspace storage limit reached.");
    const written = [];
    try {
      for (const name of [filename, filename.slice(0, -5) + ".design.json"]) {
        try { fs.lstatSync(path.join(this.revisionsDir, name)); fail(409, "Revision filenames are immutable. Use a new filename."); }
        catch (error) { if (error.code !== "ENOENT") throw error; }
      }
      for (const [name, bytes] of [[filename, htmlBytes], ...(designBytes ? [[filename.slice(0, -5) + ".design.json", designBytes]] : [])]) {
        const target = path.join(this.revisionsDir, name);
        const stat = writeExclusive(target, bytes, () => this.assertOpen());
        written.push({ filename: target, stat });
      }
      syncDirectory(this.revisionsDir);
      const meta = { filename, hash: digest(htmlBytes), designHash: designBytes ? digest(designBytes) : null, bytes: htmlBytes.length };
      this.uncommitted.set(filename, { meta, files: written });
      return meta;
    } catch (error) {
      for (const item of written.reverse()) { this.assertDirectories(); removeExact(item.filename, item.stat); }
      if (error.code === "EEXIST") fail(409, "Revision filenames are immutable. Use a new filename.");
      throw error;
    }
  }
  readRevision(meta) {
    this.assertOpen();
    if (!meta || !FILENAME.test(meta.filename) || !HASH.test(meta.hash) || !(meta.designHash === null || HASH.test(meta.designHash))
        || !Number.isSafeInteger(meta.bytes) || meta.bytes < 1 || meta.bytes > MAX_HTML_BYTES) fail(400, "Invalid revision reference.");
    const unavailable = (message) => fail(409, message, "revision-unavailable");
    const read = (name, maximum) => {
      try { return readFile(path.join(this.revisionsDir, name), maximum).bytes; }
      catch (error) { if (error.code === "ENOENT") unavailable(`Design revision file ${name} is missing.`); throw error; }
    };
    const html = read(meta.filename, MAX_HTML_BYTES);
    if (html.length !== meta.bytes || digest(html) !== meta.hash) unavailable(`Design revision ${meta.filename} no longer matches its saved hash.`);
    let design = null;
    if (meta.designHash !== null) {
      const descriptor = meta.filename.slice(0, -5) + ".design.json";
      const bytes = read(descriptor, MAX_DESIGN_BYTES);
      try { design = JSON.parse(bytes.toString("utf8")); } catch { unavailable(`Design descriptor ${descriptor} is not valid JSON.`); }
      // A repository formatter may re-indent JSON. The stored form is
      // JSON.stringify(value) + "\n", so the same value still has the same hash.
      if (digest(bytes) !== meta.designHash && digest(Buffer.from(`${JSON.stringify(design)}\n`)) !== meta.designHash) {
        unavailable(`Design descriptor ${descriptor} no longer matches its saved hash.`);
      }
      if (!validDesign(design)) unavailable(`Design descriptor ${descriptor} is invalid.`);
    }
    return { html: html.toString("utf8"), design };
  }
  discardRevision(meta) {
    this.assertOpen();
    const pending = this.uncommitted.get(meta?.filename);
    if (!pending || ["filename", "hash", "designHash", "bytes"].some(key => pending.meta[key] !== meta[key])) return;
    this.assertUnchanged();
    for (const item of pending.files) {
      this.assertDirectories();
      const html = item.filename.endsWith(".html");
      let record;
      try { record = readFile(item.filename, html ? MAX_HTML_BYTES : MAX_DESIGN_BYTES); }
      catch (error) { if (error.code === "ENOENT") continue; throw error; }
      if (sameFile(record.stat, item.stat) && digest(record.bytes) === (html ? pending.meta.hash : pending.meta.designHash)) removeExact(item.filename, item.stat);
    }
    this.uncommitted.delete(meta.filename);
  }
  close() {
    if (this.closed) return;
    this.closed = true;
    this.claim.close();
  }
}

module.exports = { WorkspaceStore, validWorkspacePath, MAX_STATE_BYTES, MAX_HTML_BYTES, MAX_DESIGN_BYTES, MAX_WORKSPACE_BYTES, MAX_REVISIONS };
