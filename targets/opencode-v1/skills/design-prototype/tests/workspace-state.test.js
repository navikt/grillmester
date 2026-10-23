"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { WorkspaceStore } = require("../scripts/workspace-store.js");
const { FeedbackStore, FeedbackMutationReceipts } = require("../scripts/feedback-store.js");
const { WorkspaceState, validWorkspaceState } = require("../scripts/workspace-state.js");
const { CanvasState } = require("../scripts/canvas-state.js");
const { validDesign } = require("../scripts/design-contract.js");
const clone = value => JSON.parse(JSON.stringify(value));
const reject = status => error => error.status === status;
const design = () => ({ version: 2, variants: [], texts: [{ id: "heading", label: "Overskrift", value: "Velg tidspunkt" }], targets: [
  { key: "card", variant: "", label: "Oppsummering", controls: [{ id: "density", label: "Luft", type: "select", initial: "roomy", editable: true,
    options: [{ value: "roomy", label: "Romslig" }, { value: "compact", label: "Kompakt" }] }] }
] });
const html = '<h1><span data-vc-text="heading">Velg tidspunkt</span></h1><section data-vc-key="card" data-vc-setting-density="roomy"><p>Innhold</p></section>';
function note(screen, text = "Behold tydelig neste steg.") {
  return { screen, kind: "point", text, anchor: { path: "h1:nth-of-type(1)", role: "heading", rect: { x: 0, y: 0, width: 100, height: 30 }, viewport: { width: 390, height: 844 } } };
}
function fixture(t) {
  const projectDir = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "design-room-state-")));
  const stores = [];
  t.after(() => { for (const store of stores) store.close(); fs.rmSync(projectDir, { recursive: true, force: true }); });
  const open = (create = false) => {
    const store = new WorkspaceStore({ projectDir, workspacePath: "designs/example", create, validateState: validWorkspaceState });
    stores.push(store);
    const recovered = store.load() !== null;
    const privateDir = fs.mkdtempSync(path.join(projectDir, "private-"));
    const feedback = new FeedbackStore(privateDir, { canvas: true, persistence: store,
      initialWorkspace: { id: "a".repeat(24), title: "Timebestilling", version: 0, revisions: [] } });
    const workspace = new WorkspaceState(feedback, store, { path: "designs/example", recovered });
    return { store, feedback, workspace, canvas: new CanvasState(feedback) };
  };
  return { open, projectDir, ...open(true) };
}
function publish(room, filename = "initial.html", source = html, declaration = design()) {
  room.workspace.publish({ expectedScreen: room.workspace.current()?.screen ?? "", filename, html: source, design: declaration });
  return room.workspace.current().screen;
}

test("project recovery retains exact rounds, unsent notes and choices without replay or journal growth", t => {
  const room = fixture(t), { feedback, workspace, store, canvas } = room;
  const screen = publish(room);
  feedback.create(note(screen));
  feedback.keep({ screen, variant: "", target: "card", values: { density: "roomy" }, text: "Behold luft" });
  feedback.submit({});
  feedback.create(note(screen, "Et usendt innspill."));
  const original = clone(feedback.state), bytes = fs.statSync(store.filename).size;
  store.close();
  const reopened = room.open();
  assert.equal(reopened.feedback.state.revision, original.revision);
  assert(fs.statSync(store.filename).size <= bytes, "recovery must fit even when the journal was full");
  for (const field of ["comments", "decisions", "submissions", "submittedDecisions"]) assert.deepEqual(reopened.feedback.state[field], original[field]);
  assert.equal(reopened.feedback.state.canvas.rounds[0].delivery, "unknown");
  assert.equal(reopened.feedback.state.canvas.rounds[0].previousSession, true);
  assert.throws(() => reopened.canvas.delivery({ submission: 1, status: "queued" }), reject(409));
  reopened.feedback.submit({});
  assert.equal(reopened.feedback.state.submission, 2);
  assert.equal(reopened.feedback.state.canvas.rounds[1].previousSession, false);
  assert.equal(workspace.summary().id, reopened.workspace.summary().id);
  assert(validWorkspaceState(reopened.feedback.state));
});

test("restore is a new immutable version and preserves feedback, accepted choices and cursors", t => {
  const room = fixture(t), first = publish(room);
  room.feedback.create(note(first)); room.feedback.submit({});
  room.canvas.review({ submission: 1, status: "answered", reply: "Et tydeligere steg er klart." });
  publish(room, "next.html", html.replace("Innhold", "Annet innhold"));
  const journal = clone(room.feedback.state.submissions), comments = clone(room.feedback.state.comments);
  const before = room.feedback.state.revision;
  assert.throws(() => room.workspace.restore({ revisionId: 1, expectedRevision: before - 1 }), reject(409));
  room.workspace.restore({ revisionId: 1, expectedRevision: before });
  assert.equal(room.workspace.summary().version, 3);
  assert.notEqual(room.workspace.current().screen, first);
  assert.equal(room.workspace.current().content, html);
  assert.equal(room.workspace.history({}).items[0].restoredFrom, 1);
  assert.deepEqual(room.feedback.state.submissions, journal); assert.deepEqual(room.feedback.state.comments, comments);
  assert.equal(room.feedback.state.submission, 1);
});

test("hydration rejects malformed or cross-linked histories instead of resetting them", t => {
  const room = fixture(t), screen = publish(room);
  room.feedback.create(note(screen)); room.feedback.submit({});
  room.canvas.delivery({ submission: 1, status: "queued" });
  room.feedback.patch(room.feedback.state.comments[0].id, { status: "open", resubmit: true });
  room.feedback.submit({});
  const good = clone(room.feedback.state); assert(validWorkspaceState(good));
  const mutations = [
    state => { state.workspace.revisions[0].bytes = 2 * 1024 * 1024 + 1; },
    state => { state.workspace.revisions[0].filename = "Initial.html"; },
    state => { state.workspace.extra = true; },
    state => { state.workspace.version = 2; },
    state => { delete state.canvas.rounds[0].previousSession; },
    state => { state.submissions[1].revision = state.submissions[0].revision; },
    state => { state.submissions[0].comments = []; },
    state => { state.submissions[1].comments[0].text = "Endret betydning"; },
    state => { state.comments[0].text = "Annet innspill"; },
    state => { state.comments[0].submission = 1; },
    state => { state.comments[0].lastSubmission = 1; },
    state => { state.workspace.holds = [{ id: "text:heading", label: "Overskrift", value: "Annet", signature: "a".repeat(64) }]; },
  ];
  for (const mutate of mutations) { const candidate = clone(good); mutate(candidate); assert.equal(validWorkspaceState(candidate), false, mutate.toString()); }
  room.store.close();
  const bad = clone(good); mutations[7](bad);
  fs.writeFileSync(room.store.filename, JSON.stringify(bad));
  assert.throws(() => room.open(), reject(409));
  assert.deepEqual(JSON.parse(fs.readFileSync(room.store.filename)), bad);
});

test("content and history page without truncating multibyte characters or reordering versions", t => {
  const room = fixture(t), source = `<p>${"😀ø\\\"".repeat(20000)}</p>`;
  publish(room, "large.html", source, null);
  let offset = 0, actual = "", pages = 0;
  do {
    const page = room.workspace.read({ revisionId: 1, part: "html", offset });
    assert(Buffer.byteLength(JSON.stringify(page)) <= 64 * 1024);
    assert(!/^[\uDC00-\uDFFF]/.test(page.content)); assert(!/[\uD800-\uDBFF]$/.test(page.content));
    actual += page.content; offset = page.nextOffset; pages++;
  } while (offset !== null);
  assert.equal(actual, source); assert(pages > 2);
  assert.throws(() => room.workspace.read({ revisionId: 1, part: "html", offset: 4 }), reject(400));
  for (let index = 2; index <= 22; index++) publish(room, `v${index}.html`, `<p>${index}</p>`, null);
  const first = room.workspace.history({ limit: 20 });
  assert.deepEqual(first.items.map(item => item.revisionId), Array.from({ length: 20 }, (_, index) => 22 - index));
  assert.deepEqual(room.workspace.history({ after: first.nextAfter }).items.map(item => item.revisionId), [2, 1]);
});

test("failed precommit publication leaves the prior sketch, while a postcommit error keeps the new revision and retry receipt", t => {
  const room = fixture(t); publish(room);
  const original = room.store.persist.bind(room.store);
  room.store.persist = () => { throw new Error("Controlled precommit error"); };
  assert.throws(() => publish(room, "failed.html"), /precommit/);
  assert.equal(room.workspace.summary().version, 1);
  assert.equal(fs.existsSync(path.join(room.store.revisionsDir, "failed.html")), false);
  room.store.persist = original;
  const sync = fs.fsyncSync, directory = fs.statSync(room.store.directory);
  fs.fsyncSync = fd => {
    const stat = fs.fstatSync(fd);
    if (stat.dev === directory.dev && stat.ino === directory.ino) throw new Error("Controlled postcommit error");
    sync(fd);
  };
  const receipts = new FeedbackMutationReceipts(), id = "e".repeat(32), input = { filename: "committed.html" };
  try { assert.throws(() => receipts.run(id, "POST", "/test", input, () => publish(room, input.filename)), error => error.committed === true); }
  finally { fs.fsyncSync = sync; }
  assert.equal(room.workspace.summary().version, 2);
  assert.equal(room.workspace.current().filename, input.filename);
  receipts.run(id, "POST", "/test", input, () => assert.fail("A committed operation must not execute twice"));
  assert(validWorkspaceState(room.store.load()));
  room.store.close(); assert.equal(room.open().workspace.summary().version, 2);
});

test("source edits save one paired revision, survive restart and protect values until explicit release", t => {
  const room = fixture(t), screen = publish(room);
  const input = { screen, expectedRevision: room.feedback.state.revision, changes: [{ id: "text:heading", value: "Finn en tid som passer" }, { id: "control:/card/density", value: "compact" }] };
  const receipts = new FeedbackMutationReceipts(), id = "b".repeat(32);
  receipts.run(id, "POST", "/workspace/editor/save", input, value => room.workspace.editorSave(value));
  receipts.run(id, "POST", "/workspace/editor/save", input, value => room.workspace.editorSave(value));
  assert.equal(room.workspace.summary().version, 2); assert.equal(room.feedback.state.submission, 0);
  assert.equal(room.workspace.current().content, html, "The immutable HTML and revised descriptor form the source pair.");
  assert.equal(room.workspace.current().design.texts[0].value, input.changes[0].value);
  assert.equal(room.workspace.editorRead({}).fields.filter(item => item.locked).length, 2);
  const held = clone(room.workspace.current().design);
  assert.throws(() => publish(room, "overwritten.html"), error => error.errorCode === "editor-conflict");
  assert.throws(() => room.workspace.restore({ revisionId: 1, expectedRevision: room.feedback.state.revision }), error => error.errorCode === "editor-conflict");
  publish(room, "preserved.html", html.replace("Innhold", "Nytt innhold"), held);
  room.store.close();
  const reopened = room.open(), state = reopened.workspace.editorRead({});
  assert.equal(state.fields.find(item => item.id === "text:heading").value, input.changes[0].value);
  assert.equal(state.holds.length, 2);
  reopened.workspace.editorRelease({ screen: state.screen, expectedRevision: state.revision, ids: ["text:heading", "control:/card/density"] });
  assert.equal(reopened.workspace.summary().version, 3);
  reopened.workspace.restore({ revisionId: 1, expectedRevision: reopened.feedback.state.revision });
  assert.equal(reopened.workspace.summary().version, 4);
  assert.equal(reopened.feedback.state.submission, 0);
});

test("editor rejects stale, undeclared, invalid and contradictory choices without losing drafts or kept decisions", t => {
  const room = fixture(t), screen = publish(room);
  const input = { screen, expectedRevision: room.feedback.state.revision, changes: [{ id: "control:/card/density", value: "compact" }] };
  room.feedback.keep({ screen, variant: "", target: "card", values: { density: "roomy" }, text: "Behold luften" });
  assert.throws(() => room.workspace.editorSave(input), reject(409));
  input.expectedRevision = room.feedback.state.revision;
  assert.throws(() => room.workspace.editorSave(input), error => error.errorCode === "editor-conflict");
  for (const changes of [[{ id: "text:unknown", value: "No" }], [{ id: "control:/card/density", value: "arbitrary-css" }], [{ id: "text:heading", value: "ø".repeat(1001) }]]) {
    assert.throws(() => room.workspace.editorSave({ ...input, changes }), reject(400));
  }
  assert.equal(room.workspace.summary().version, 1);
  assert.equal(room.feedback.state.decisions[0].state, "active");
  const read = room.workspace.editorRead({}); assert(Buffer.byteLength(JSON.stringify(read)) <= 64 * 1024);
  const v1 = design(); v1.version = 1; delete v1.texts; delete v1.targets[0].controls[0].editable; assert(validDesign(v1));
});
