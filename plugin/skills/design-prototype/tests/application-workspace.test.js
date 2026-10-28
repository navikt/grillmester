"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { ApplicationWorkspace, validApplicationWorkspaceState } = require("../scripts/application-workspace.js");
const { validWorkspaceState } = require("../scripts/workspace-state.js");
const { WorkspaceStore } = require("../scripts/workspace-store.js");
const { screenIdentity } = require("../scripts/application-contract.js");
const checkpoint = "a".repeat(64);
const application = { name: "Møtevalg", url: "http://localhost:3000/start?view=kort" };
const copy = value => JSON.parse(JSON.stringify(value));
const rejected = status => error => error.status === status;
function fixture(t) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "application-workspace-")));
  const projectDir = path.join(root, "project"); fs.mkdirSync(projectDir, { mode: 0o700 });
  const rooms = [];
  t.after(() => { for (const room of rooms) room.close(); fs.rmSync(root, { recursive: true, force: true }); });
  const open = (options = {}) => {
    const stateDir = fs.mkdtempSync(path.join(root, "runtime-"));
    const room = new ApplicationWorkspace({ projectDir, workspacePath: "designs/meeting", stateDir, ...options });
    rooms.push(room); return room;
  };
  const create = (options = {}) => open({ create: true, application, checkpoint, ...options });
  return { root, projectDir, open, create };
}
function note(room, text = "Prøv radioknapper her.", route = room.current().source.route) {
  return { screen: screenIdentity(room.current().source.checkpoint, route), kind: "point", text,
    anchor: { path: "button:nth-of-type(1)", role: "button", rect: { x: 12, y: 40, width: 100, height: 40 }, viewport: { width: 375, height: 812 } },
    applicationContext: { route, target: { tag: "button", role: "button", name: "Neste", text: "Neste", path: "button:nth-of-type(1)" }, viewport: { width: 375, height: 812, scrollX: 0, scrollY: 0 } } };
}

test("saved feedback rooms have no source authority, source history or untracked empty directories", t => {
  const owner = fixture(t), room = owner.create();
  const saved = JSON.parse(fs.readFileSync(room.store.filename));
  assert(validApplicationWorkspaceState(saved)); assert.equal(saved.workspace.mode, "feedback");
  assert.deepEqual(Object.keys(saved.workspace.source).sort(), ["kind", "name", "startPath"]);
  assert.deepEqual(saved.screens, []); assert.deepEqual(fs.readdirSync(room.store.directory), ["workspace.json"]);
  for (const forbidden of ["http://", "localhost", "projectIdentity", "revisions", "proposals", "references", owner.projectDir]) assert(!JSON.stringify(saved).includes(forbidden));
  assert.equal(room.summary().storage, "project"); assert.equal(room.summary().path, "designs/meeting");
});

test("a pending proposal save is a strict portable intent, and reopening never completes it", t => {
  const owner = fixture(t), room = owner.create();
  const intent = { binding: { id: "b".repeat(24), title: "Tydeligere valg", workspacePath: "designs/proposal", workspaceId: "c".repeat(24),
    source: "conversation", requestHash: "d".repeat(64) }, expectedScreen: "e".repeat(32), expectedRevision: 7 };
  room.beginSketchSave(intent);
  const bytes = fs.readFileSync(room.store.filename), revision = room.feedback.state.revision;
  room.beginSketchSave(intent); assert.equal(room.feedback.state.revision, revision);
  assert(validApplicationWorkspaceState(room.feedback.state));
  for (const mutate of [state => { state.workspace.pendingSketchSave.secret = "x"; }, state => { state.workspace.pendingSketchSave.binding.workspacePath = "../outside"; },
    state => { state.workspace.pendingSketchSave.expectedScreen = "bad"; }, state => { state.workspace.pendingSketchSave.expectedRevision = -1; },
    state => { state.workspace.sketch = copy(intent.binding); }, state => { state.workspace.pendingSketchSave.binding.sourceSubmission = 1; }]) {
    const state = copy(room.feedback.state); mutate(state); assert.equal(validApplicationWorkspaceState(state), false);
  }
  room.close(); const reopened = owner.open();
  assert.deepEqual(fs.readFileSync(reopened.store.filename), bytes);
  assert.deepEqual(reopened.feedback.state.workspace.pendingSketchSave, intent);
  assert.equal(fs.existsSync(path.join(owner.projectDir, intent.binding.workspacePath)), false);
  assert.throws(() => reopened.finishSketchSave({ ...intent, expectedRevision: 8 }), rejected(409));
  assert.deepEqual(fs.readFileSync(reopened.store.filename), bytes);
  reopened.finishSketchSave(intent);
  assert.deepEqual(reopened.feedback.state.workspace.sketch, intent.binding);
  assert.equal(reopened.feedback.state.workspace.pendingSketchSave, undefined);
  assert(validApplicationWorkspaceState(reopened.feedback.state));
});

test("temporary is the default without touching even a nonexistent caller project", t => {
  const owner = fixture(t), absent = path.join(owner.root, "must-not-exist");
  const room = owner.open({ projectDir: absent, workspacePath: undefined, application });
  assert.equal(room.summary().storage, "temporary"); assert.equal(room.summary().path, undefined);
  assert.equal(room.summary().recovered, false); assert.equal(fs.existsSync(absent), false);
  assert.deepEqual(fs.readdirSync(owner.projectDir), []);
  room.createComment(note(room)); room.feedback.submit({});
  assert(validApplicationWorkspaceState(room.feedback.state)); assert.equal(fs.existsSync(absent), false);
  assert.throws(() => owner.open({ workspacePath: undefined, create: true, application }), rejected(400));
});

test("navigation storms and selections consume no revision, disk write or recorded-page capacity", t => {
  const room = fixture(t).create(), before = fs.readFileSync(room.store.filename);
  for (let index = 0; index < 1000; index++) room.observeRoute({ route: `/page/${index}`, expectedCheckpoint: checkpoint });
  assert.equal(room.current().source.route, "/page/999"); assert.equal(room.feedback.state.revision, 0);
  assert.deepEqual(room.feedback.state.screens, []); assert.deepEqual(fs.readFileSync(room.store.filename), before);
  room.createComment(note(room));
  assert.equal(room.feedback.state.revision, 1); assert.equal(room.feedback.state.screens.length, 1);
  assert.equal(room.feedback.state.comments[0].applicationContext.route, "/page/999");
});

test("saving an earlier selection after navigation binds page and comment atomically", t => {
  const room = fixture(t).create(), original = note(room);
  room.observeRoute({ route: "/later", expectedCheckpoint: checkpoint });
  let writes = 0; const persist = room.store.persist.bind(room.store);
  room.store.persist = state => { writes++; assert.equal(state.screens.length, state.comments.length); persist(state); };
  room.createComment(original);
  assert.equal(writes, 1); assert.equal(room.current().source.route, "/later");
  assert.equal(room.feedback.state.screens[0].source.route, "/start?view=kort");
  assert(validApplicationWorkspaceState(room.feedback.state));
});

test("invalid comments, routes and failed commits leave no orphan page or changed memory", t => {
  const room = fixture(t).create(), before = copy(room.feedback.state), bytes = fs.readFileSync(room.store.filename);
  for (const input of [{ ...note(room), text: "" }, { ...note(room), screen: "0".repeat(32) }, { ...note(room), kind: "edit" }, {}]) assert.throws(() => room.createComment(input));
  assert.throws(() => room.observeRoute({ route: "/later", expectedCheckpoint: "b".repeat(64) }), rejected(409));
  assert.throws(() => room.observeRoute({ route: "/?token=private", expectedCheckpoint: checkpoint }), rejected(400));
  const persist = room.store.persist.bind(room.store);
  room.store.persist = () => { throw new Error("disk unavailable"); };
  assert.throws(() => room.createComment(note(room)), /disk unavailable/);
  assert.deepEqual(room.feedback.state, before); assert.deepEqual(fs.readFileSync(room.store.filename), bytes);
  room.store.persist = persist; room.createComment(note(room));
  assert.equal(room.feedback.state.screens.length, 1); assert.equal(room.feedback.state.comments.length, 1);
});

test("a full page quota still allows existing-page feedback and sending", t => {
  const room = fixture(t).create();
  for (let index = 0; index < 100; index++) room.createComment(note(room, "Avklar valget.", `/page/${index}`));
  const before = copy(room.feedback.state);
  assert.throws(() => room.createComment(note(room, "Ny side", "/extra")), rejected(429));
  assert.deepEqual(room.feedback.state, before);
  room.observeRoute({ route: "/extra", expectedCheckpoint: checkpoint });
  room.createComment(note(room, "Et innspill til.", "/page/0")); room.feedback.submit({ revision: room.feedback.state.revision });
  assert.equal(room.feedback.state.submission, 1); assert.equal(room.feedback.state.submissions[0].comments.length, 101);
});

test("reopening keeps exact bytes and immutable rounds, without resending old feedback", t => {
  const owner = fixture(t), room = owner.create(); room.createComment(note(room)); room.feedback.submit({});
  room.createComment(note(room, "Usendt innspill."));
  const saved = copy(room.feedback.state), bytes = fs.readFileSync(room.store.filename); room.close();
  const reopened = owner.open();
  assert.equal(reopened.connection, null); assert.equal(reopened.summary().recovered, true);
  assert.deepEqual(fs.readFileSync(reopened.store.filename), bytes);
  assert.deepEqual(reopened.feedback.state.comments, saved.comments); assert.deepEqual(reopened.feedback.state.submissions, saved.submissions);
  assert.equal(reopened.canvas.read({ submission: 1 }).round.previousSession, true);
  assert.equal(reopened.canvas.read({ submission: 1 }).round.delivery, "unknown");
  assert.throws(() => reopened.canvas.delivery({ submission: 1, status: "queued" }), rejected(409));
});

test("portable checked-out feedback rooms reopen without private modes or revisions directory", t => {
  const owner = fixture(t), room = owner.create(); room.createComment(note(room)); room.feedback.submit({});
  const original = copy(room.feedback.state); room.close();
  const destination = path.join(owner.root, "checkout"), directory = path.join(destination, "designs/meeting");
  fs.mkdirSync(directory, { recursive: true, mode: 0o755 });
  fs.writeFileSync(path.join(directory, "workspace.json"), JSON.stringify(original) + "\n", { mode: 0o644 });
  const before = fs.readFileSync(path.join(directory, "workspace.json"));
  const reopened = owner.open({ projectDir: destination, application: { ...application, name: "Nytt visningsnavn", url: "http://localhost:4000/start?view=kort" } });
  assert.equal(reopened.current().name, "Nytt visningsnavn");
  assert.deepEqual(reopened.feedback.state.submissions, original.submissions);
  assert.deepEqual(fs.readFileSync(reopened.store.filename), before); assert.deepEqual(fs.readdirSync(directory), ["workspace.json"]);
});

test("reconnection guards start path and query policy, but name and physical folder are not identity", t => {
  const owner = fixture(t), room = owner.create(); room.close();
  assert.throws(() => owner.open({ application: { ...application, url: "http://localhost:4000/other" } }), rejected(409));
  assert.throws(() => owner.open({ application: { ...application, resourceQueryKeys: ["t"] } }), rejected(409));
  assert.throws(() => owner.open({ checkpoint: "f".repeat(64) }), rejected(409));
  const reopened = owner.open({ application: { ...application, name: "Ny etikett" } });
  assert.equal(reopened.current().name, "Ny etikett");
});

test("unreleased source-editing rooms reject without rewriting files or attempting recovery", t => {
  const owner = fixture(t), room = owner.create(); const filename = room.store.filename;
  const saved = copy(room.feedback.state); room.close();
  delete saved.workspace.mode; saved.workspace.proposals = []; saved.workspace.version = 1;
  const bytes = JSON.stringify(saved) + "\n"; fs.writeFileSync(filename, bytes);
  assert.throws(() => owner.open(), error => error.status === 409 && /unreleased build/.test(error.message) && /files were not changed/.test(error.message));
  assert.equal(fs.readFileSync(filename, "utf8"), bytes);
});

test("application schema rejects hidden source authority, extra state, tampered pages and contexts", t => {
  const room = fixture(t).create(); room.createComment(note(room)); room.feedback.submit({});
  const mutations = [state => { state.workspace.proposals = []; }, state => { state.workspace.source.projectIdentity = checkpoint; },
    state => { state.workspace.references = []; }, state => { state.workspace.currentRoute = "/unobserved"; },
    state => { state.workspace.mode = "edit"; }, state => { state.screens[0].source.checkpoint = "b".repeat(64); },
    state => { state.comments[0].applicationContext.route = "/other"; }, state => { state.canvas.rounds[0].previousSession = "yes"; }];
  for (const mutation of mutations) { const state = copy(room.feedback.state); mutation(state); assert.equal(validApplicationWorkspaceState(state), false); }
});

test("concurrent saved-room writers and external modifications are rejected", t => {
  const owner = fixture(t), room = owner.create();
  assert.throws(() => owner.open(), rejected(409));
  fs.appendFileSync(room.store.filename, " "); const bytes = fs.readFileSync(room.store.filename);
  assert.throws(() => room.createComment(note(room)), rejected(409));
  assert.deepEqual(room.feedback.state.screens, []); assert.deepEqual(fs.readFileSync(room.store.filename), bytes);
});

test("opening an app feedback room through the sketch path explains the correct mode", t => {
  const owner = fixture(t), room = owner.create(); const bytes = fs.readFileSync(room.store.filename); room.close();
  const stateDir = fs.mkdtempSync(path.join(owner.root, "sketch-runtime-"));
  assert.throws(() => new WorkspaceStore({ projectDir: owner.projectDir, workspacePath: "designs/meeting", validateState: validWorkspaceState }),
    error => error.status === 409 && /application feedback room/.test(error.message) && /saved start path/.test(error.message));
  assert.deepEqual(fs.readFileSync(room.store.filename), bytes);
  assert.deepEqual(fs.readdirSync(room.store.directory), ["workspace.json"]);
});
