"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { randomUUID } = require("node:crypto");
const { fork } = require("node:child_process");
const { once } = require("node:events");
const { WorkspaceStore, validWorkspacePath, MAX_STATE_BYTES, MAX_HTML_BYTES, MAX_WORKSPACE_BYTES, MAX_REVISIONS } = require("../scripts/workspace-store.js");

const modulePath = path.resolve(__dirname, "../scripts/workspace-store.js");
const validState = state => state?.schemaVersion === 1 && Number.isSafeInteger(state.revision) && state.revision >= 0;
const initial = () => ({ schemaVersion: 1, revision: 0, comments: [], workspace: { revisions: [] } });
const descriptor = { version: 1, variants: [], targets: [] };
function fixture(t) {
  const projectDir = fs.mkdtempSync(path.join(os.tmpdir(), "design-workspace-test-"));
  const stores = [];
  t.after(() => {
    for (const store of stores) { try { store.close(); } catch {} }
    fs.rmSync(projectDir, { recursive: true, force: true });
  });
  const open = (options = {}) => {
    const store = new WorkspaceStore({ projectDir, workspacePath: "designs/example", validateState: validState, ...options });
    stores.push(store);
    return store;
  };
  return { projectDir, open };
}
function rejectsStatus(status) { return error => error.status === status; }

test("ordinary project files survive close and reopen with exact comments and revisions", t => {
  const { open } = fixture(t);
  const store = open({ create: true, title: null });
  assert.equal(store.load(), null);
  const meta = store.writeRevision({ filename: "first.html", html: "<h1>Møte</h1>", design: descriptor });
  const state = initial();
  state.comments.push({ text: "Behold æ, ø og å." });
  state.workspace.revisions.push(meta);
  store.persist(state);
  assert.deepEqual(store.readRevision(meta), { html: "<h1>Møte</h1>", design: descriptor });
  store.close();
  for (const filename of [store.filename, path.join(store.revisionsDir, "first.html"), path.join(store.revisionsDir, "first.design.json")]) fs.chmodSync(filename, 0o644);
  fs.chmodSync(store.directory, 0o755);
  fs.chmodSync(store.revisionsDir, 0o755);
  const restored = open();
  assert.deepEqual(restored.load(), state);
  assert.deepEqual(restored.readRevision(meta), { html: "<h1>Møte</h1>", design: descriptor });
  assert.deepEqual(fs.readdirSync(store.directory).sort(), ["revisions", "workspace.json"]);
  assert.equal(fs.statSync(store.filename).mode & 0o777, 0o644, "opening never chmods existing user files");
  assert.throws(() => open({ create: true }), rejectsStatus(409));
});

test("an active writer cannot be stolen, while distinct worktree directories remain independent", t => {
  const { open, projectDir } = fixture(t);
  const first = open({ create: true }); first.persist(initial());
  assert.throws(() => open(), rejectsStatus(409));
  const secondRoot = path.join(projectDir, "other-worktree"); fs.mkdirSync(secondRoot);
  const second = open({ projectDir: secondRoot, create: true }); second.persist({ ...initial(), revision: 1 });
  assert.equal(first.load().revision, 0);
  assert.equal(second.load().revision, 1);
  first.close();
  assert.equal(open().load().revision, 0);
});

test("paths are bounded and cannot escape through traversal, hidden directories or symlinks", t => {
  const { open, projectDir } = fixture(t);
  for (const value of ["", "/absolute", "../escape", "designs/../escape", "designs//room", "designs\\room", ".git/room", "node_modules/room", "designs/NUL", "a/".repeat(9), "a".repeat(241)]) {
    assert.equal(validWorkspacePath(value), false, value);
    assert.throws(() => open({ workspacePath: value, create: true }), rejectsStatus(400));
  }
  const target = path.join(projectDir, "outside"); fs.mkdirSync(target);
  fs.symlinkSync(target, path.join(projectDir, "alias"));
  assert.throws(() => open({ workspacePath: "alias/room", create: true }));
  assert.deepEqual(fs.readdirSync(target), []);
  assert.equal(validWorkspacePath("designs/room_2"), true);
});

test("invalid existing state is never reset, and failed construction releases its claim", t => {
  const { open } = fixture(t);
  const store = open({ create: true }); store.persist(initial()); store.close();
  const malformed = Buffer.from('{"schemaVersion":99}');
  fs.writeFileSync(store.filename, malformed);
  assert.throws(() => open(), rejectsStatus(409));
  assert.deepEqual(fs.readFileSync(store.filename), malformed);
  fs.writeFileSync(store.filename, JSON.stringify(initial()));
  const restored = open();
  assert.deepEqual(restored.load(), initial());
});

test("external byte changes and replaced directories fail closed without overwriting", t => {
  const { open } = fixture(t);
  const store = open({ create: true }); store.persist(initial());
  const external = Buffer.from(JSON.stringify({ ...initial(), revision: 8 }));
  fs.writeFileSync(store.filename, external);
  assert.throws(() => store.persist({ ...initial(), revision: 1 }), rejectsStatus(409));
  assert.deepEqual(fs.readFileSync(store.filename), external);
  assert.throws(() => store.writeRevision({ filename: "new.html", html: "<p>New</p>" }), rejectsStatus(409));
  store.close();
  const restored = open();
  assert.equal(restored.load().revision, 8);
  fs.renameSync(restored.directory, restored.directory + "-old");
  fs.mkdirSync(restored.directory);
  assert.throws(() => restored.persist({ ...initial(), revision: 9 }), rejectsStatus(409));
  assert.deepEqual(fs.readdirSync(restored.directory), []);
});

test("revision filenames and content hashes are immutable; discard only removes this writer's unpublished files", t => {
  const { open } = fixture(t);
  const store = open({ create: true }); store.persist(initial());
  const first = store.writeRevision({ filename: "first.html", html: "<p>First</p>" });
  assert.equal(first.designHash, null);
  assert.throws(() => store.writeRevision({ filename: "first.html", html: "<p>Changed</p>" }), rejectsStatus(409));
  assert.equal(store.readRevision(first).html, "<p>First</p>");
  store.persist({ ...initial(), workspace: { revisions: [first] } });
  store.discardRevision(first);
  assert.equal(store.readRevision(first).html, "<p>First</p>");
  const pending = store.writeRevision({ filename: "pending.html", html: "<p>Pending</p>", design: descriptor });
  store.persist({ ...initial(), revision: 1, workspace: { revisions: [first] } });
  store.discardRevision({ ...pending, revisionId: 2 });
  assert.equal(fs.existsSync(path.join(store.revisionsDir, "pending.html")), false);
  assert.equal(fs.existsSync(path.join(store.revisionsDir, "pending.design.json")), false);
  fs.writeFileSync(path.join(store.revisionsDir, first.filename), "<p>Tampered</p>");
  assert.throws(() => store.readRevision(first), rejectsStatus(409));
});

test("discard cannot remove a replaced file or a revision from another writer", t => {
  const { open } = fixture(t);
  const store = open({ create: true }); store.persist(initial());
  const meta = store.writeRevision({ filename: "orphan.html", html: "<p>Original</p>" });
  const filename = path.join(store.revisionsDir, meta.filename);
  fs.renameSync(filename, filename + "-saved");
  fs.writeFileSync(filename, "<p>Replacement</p>");
  store.discardRevision(meta);
  assert.equal(fs.readFileSync(filename, "utf8"), "<p>Replacement</p>");
  fs.unlinkSync(filename + "-saved");
  store.close();
  const restored = open();
  restored.discardRevision(meta);
  assert.equal(fs.readFileSync(filename, "utf8"), "<p>Replacement</p>");
});

test("state and revision limits reject whole writes without changing the saved room", t => {
  const { open } = fixture(t);
  const store = open({ create: true }); store.persist(initial());
  const before = fs.readFileSync(store.filename);
  assert.throws(() => store.persist({ ...initial(), text: "x".repeat(MAX_STATE_BYTES) }), rejectsStatus(429));
  assert.throws(() => store.persist({ schemaVersion: 99 }), rejectsStatus(400));
  assert.throws(() => store.writeRevision({ filename: "large.html", html: "x".repeat(MAX_HTML_BYTES + 1) }), rejectsStatus(413));
  assert.deepEqual(fs.readFileSync(store.filename), before);
  assert.deepEqual(fs.readdirSync(store.revisionsDir), []);
  // Unregistered files left by interrupted saves never consume version slots;
  // the registered version count is enforced by the workspace state.
  for (let i = 0; i < MAX_REVISIONS; i++) fs.writeFileSync(path.join(store.revisionsDir, `revision-${i}.html`), "<p>x</p>");
  store.writeRevision({ filename: "after-orphans.html", html: "<p>x</p>" });
  store.persist({ ...initial(), text: "after orphans" });
  store.close();
  const reopened = open();
  assert.equal(reopened.load().text, "after orphans", "Saving and reopening rescan the files without counting orphans as versions.");
  for (let i = MAX_REVISIONS; i < MAX_REVISIONS * 4; i++) fs.writeFileSync(path.join(reopened.revisionsDir, `revision-${i}.html`), "<p>x</p>");
  assert.throws(() => reopened.writeRevision({ filename: "too-many.html", html: "<p>x</p>" }), rejectsStatus(429));
  assert.equal(fs.readdirSync(reopened.revisionsDir).length, MAX_REVISIONS * 4 + 1);
});

test("reopening applies the combined state and revision storage limit without changing files", t => {
  const { open } = fixture(t);
  const store = open({ create: true }); store.persist(initial()); store.close();
  const saved = fs.readFileSync(store.filename);
  let lastFile;
  for (let i = 0; i < MAX_WORKSPACE_BYTES / MAX_HTML_BYTES; i++) {
    lastFile = path.join(store.revisionsDir, `revision-${i}.html`);
    const fd = fs.openSync(lastFile, "wx", 0o600);
    try { fs.ftruncateSync(fd, MAX_HTML_BYTES); } finally { fs.closeSync(fd); }
  }
  assert.throws(() => open(), rejectsStatus(429));
  assert.deepEqual(fs.readFileSync(store.filename), saved);
  const fd = fs.openSync(lastFile, "r+");
  try { fs.ftruncateSync(fd, MAX_HTML_BYTES - saved.length); } finally { fs.closeSync(fd); }
  assert.deepEqual(open().load(), initial(), "an exact-boundary workspace can reopen after a failed constructor");
});

test("post-rename directory sync failure reports a committed write and cannot discard referenced content", t => {
  const { open } = fixture(t);
  const store = open({ create: true }); store.persist(initial());
  const meta = store.writeRevision({ filename: "committed.html", html: "<p>Keep this revision</p>" });
  const state = { ...initial(), revision: 1, workspace: { revisions: [meta] } };
  const sync = fs.fsyncSync;
  fs.fsyncSync = fd => {
    if (fs.fstatSync(fd).isDirectory()) throw Object.assign(new Error("Directory sync failed."), { code: "EIO" });
    return sync(fd);
  };
  try { assert.throws(() => store.persist(state), error => error.code === "EIO" && error.committed === true); }
  finally { fs.fsyncSync = sync; }
  assert.deepEqual(store.load(), state);
  assert.deepEqual(JSON.parse(fs.readFileSync(store.filename, "utf8")), state);
  store.discardRevision(meta);
  assert.equal(store.readRevision(meta).html, "<p>Keep this revision</p>");
  store.persist({ ...state, revision: 2 });
  store.close();
  assert.equal(open().load().revision, 2, "next compare-and-save uses the committed bytes");
});

test("discard preserves an in-place external edit and abandoned descriptors cannot be reused", t => {
  const { open } = fixture(t);
  const store = open({ create: true }); store.persist(initial());
  const meta = store.writeRevision({ filename: "edited.html", html: "<p>Original</p>" });
  const filename = path.join(store.revisionsDir, meta.filename);
  fs.writeFileSync(filename, "<p>External edit</p>");
  store.discardRevision(meta);
  assert.equal(fs.readFileSync(filename, "utf8"), "<p>External edit</p>");
  fs.writeFileSync(path.join(store.revisionsDir, "orphan.design.json"), JSON.stringify(descriptor));
  assert.throws(() => store.writeRevision({ filename: "orphan.html", html: "<p>New</p>" }), rejectsStatus(409));
  assert.equal(fs.existsSync(path.join(store.revisionsDir, "orphan.html")), false);
});

test("post-commit cleanup failure also preserves the committed state and revision", t => {
  const { open } = fixture(t);
  const store = open({ create: true }); store.persist(initial());
  const meta = store.writeRevision({ filename: "kept.html", html: "<p>Committed</p>" });
  const state = { ...initial(), revision: 1, workspace: { revisions: [meta] } };
  const rename = fs.renameSync, lstat = fs.lstatSync;
  let renamed = false;
  fs.renameSync = (...args) => { const result = rename(...args); if (args[1] === store.filename) renamed = true; return result; };
  fs.lstatSync = (...args) => {
    if (renamed && args[0] === store.directory) throw Object.assign(new Error("Cleanup directory check failed."), { code: "EIO" });
    return lstat(...args);
  };
  try { assert.throws(() => store.persist(state), error => error.code === "EIO" && error.committed === true); }
  finally { fs.renameSync = rename; fs.lstatSync = lstat; }
  assert.deepEqual(store.load(), state);
  store.discardRevision(meta);
  assert.equal(store.readRevision(meta).html, "<p>Committed</p>");
  store.persist({ ...state, revision: 2 });
});

test("state and revision reads reject symbolic and hard links", t => {
  const { open, projectDir } = fixture(t);
  const store = open({ create: true }); store.persist(initial());
  const meta = store.writeRevision({ filename: "first.html", html: "<h1>First</h1>" });
  const filename = path.join(store.revisionsDir, meta.filename);
  const external = path.join(projectDir, "external.html"); fs.writeFileSync(external, "<h1>Other</h1>");
  fs.unlinkSync(filename); fs.symlinkSync(external, filename);
  assert.throws(() => store.readRevision(meta));
  fs.unlinkSync(filename); fs.linkSync(external, filename);
  assert.throws(() => store.readRevision(meta), rejectsStatus(409));
  store.close();
  const stateCopy = path.join(projectDir, "state-copy.json"); fs.renameSync(store.filename, stateCopy); fs.symlinkSync(stateCopy, store.filename);
  assert.throws(() => open());
  assert.deepEqual(JSON.parse(fs.readFileSync(stateCopy, "utf8")), initial());
});

const workerSource = `"use strict";
const fs = require("node:fs");
const path = require("node:path");
const { performance } = require("node:perf_hooks");
const { WorkspaceStore } = require(process.env.WORKSPACE_STORE_MODULE);
const projectDir = process.argv[2], mode = process.argv[3];
const options = { projectDir, workspacePath: "designs/example", validateState: value => value?.schemaVersion === 1 && Number.isSafeInteger(value.revision) };
const pause = delay => new Promise(resolve => setTimeout(resolve, delay));
process.on("message", async message => {
  if (message !== "start") return;
  if (mode === "crash") {
    const store = new WorkspaceStore(options);
    process.send({ acquired: true });
    setInterval(() => store.load(), 1000);
    return;
  }
  // Acquisition deliberately fails fast while another opener is choosing.
  // Bound elapsed time, not retry count, so concurrent disk work cannot consume
  // the budget early; spread retries to avoid synchronized contenders.
  const deadline = performance.now() + 8000;
  for (let attempt = 0; performance.now() < deadline; attempt++) {
    let store;
    try { store = new WorkspaceStore(options); }
    catch (error) {
      if (error.status !== 409 && !["ENOENT", "EEXIST"].includes(error.code)) { process.send({ error: error.message }); process.exit(1); }
      await pause(Math.min(100, 5 + attempt * 3) + (process.pid * 17 + attempt * 13) % 19); continue;
    }
    const critical = path.join(projectDir, "writer-active");
    try {
      const fd = fs.openSync(critical, "wx"); fs.closeSync(fd);
      const state = store.load(); state.revision += 1; store.persist(state);
      await pause(20);
      fs.unlinkSync(critical); store.close();
      process.send({ completed: true }); process.exit(0);
    } catch (error) { process.send({ overlap: error.code === "EEXIST", error: error.message }); process.exit(1); }
  }
  process.send({ error: "No writer acquired the bounded lock." }); process.exit(1);
});
process.send({ ready: true });
`;
function spawnWorker(t, projectDir, mode, environment = {}) {
  const filename = path.join(projectDir, `lock-worker-${randomUUID()}.cjs`);
  fs.writeFileSync(filename, workerSource, { flag: "wx", mode: 0o600 });
  const child = fork(filename, [projectDir, mode], { env: { ...process.env, ...environment, WORKSPACE_STORE_MODULE: modulePath }, stdio: ["ignore", "pipe", "pipe", "ipc"] });
  child.stdout.resume(); child.stderr.resume();
  t.after(() => { if (child.exitCode === null && child.signalCode === null) child.kill("SIGKILL"); });
  return child;
}

test("eight real processes serialize concurrent opens and preserve every accepted update", { timeout: 20000 }, async t => {
  const { open, projectDir } = fixture(t);
  const setup = open({ create: true }); setup.persist(initial()); setup.close();
  const children = Array.from({ length: 8 }, () => spawnWorker(t, projectDir, "race"));
  await Promise.all(children.map(child => once(child, "message")));
  const outcomes = children.map(child => once(child, "message"));
  const exits = children.map(child => once(child, "exit"));
  children.forEach(child => child.send("start"));
  for (const [result] of await Promise.all(outcomes)) assert.deepEqual(result, { completed: true });
  for (const [code] of await Promise.all(exits)) assert.equal(code, 0);
  assert.equal(open().load().revision, children.length);
});

test("a killed writer is recoverable without replaying or changing saved state", { timeout: 10000 }, async t => {
  const { open, projectDir } = fixture(t);
  const setup = open({ create: true });
  const state = { ...initial(), submission: 3, canvas: { rounds: [{ submission: 3, delivery: "sending", review: "unread" }] } };
  setup.persist(state); setup.close();
  const child = spawnWorker(t, projectDir, "crash");
  await once(child, "message");
  const acquired = once(child, "message"); child.send("start");
  assert.deepEqual((await acquired)[0], { acquired: true });
  assert.throws(() => open(), rejectsStatus(409));
  const exited = once(child, "exit"); child.kill("SIGKILL"); await exited;
  const restored = open();
  assert.deepEqual(restored.load(), state, "storage restoration never delivers or rewrites rounds");
  restored.persist({ ...state, revision: 1 });
  assert.equal(restored.load().submission, 3);
});

test("different temporary-directory environments still serialize the same physical room", { timeout: 10000 }, async t => {
  const { open, projectDir } = fixture(t);
  const setup = open({ create: true }); setup.persist(initial()); setup.close();
  const children = ["temporary-a", "temporary-b"].map(name => {
    const temporary = path.join(projectDir, name); fs.mkdirSync(temporary);
    return spawnWorker(t, projectDir, "race", { TMPDIR: temporary, TMP: temporary, TEMP: temporary });
  });
  await Promise.all(children.map(child => once(child, "message")));
  const outcomes = children.map(child => once(child, "message"));
  const exits = children.map(child => once(child, "exit"));
  children.forEach(child => child.send("start"));
  for (const [result] of await Promise.all(outcomes)) assert.deepEqual(result, { completed: true });
  for (const [code] of await Promise.all(exits)) assert.equal(code, 0);
  assert.equal(open().load().revision, 2);
});

test("case aliases on a case-insensitive filesystem cannot acquire a second writer", t => {
  const { open, projectDir } = fixture(t);
  const store = open({ create: true }); store.persist(initial());
  const alias = path.join(projectDir, "designs/EXAMPLE");
  if (!fs.existsSync(alias)) { t.skip("This filesystem is case-sensitive."); return; }
  assert.equal(fs.statSync(alias).ino, fs.statSync(store.directory).ino);
  assert.throws(() => open({ workspacePath: "designs/EXAMPLE" }), rejectsStatus(409));
  store.close();
  assert.equal(open({ workspacePath: "designs/EXAMPLE" }).load().revision, 0);
});
