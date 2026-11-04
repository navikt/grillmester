"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { FeedbackStore, FeedbackMutationReceipts, MAX_COMMENTS, MAX_SUBMISSIONS, MAX_STORE_BYTES, validCreate, validPersistedFeedback } = require("../scripts/feedback-store.js");
const { CanvasState } = require("../scripts/canvas-state.js");

const SCREEN = "a".repeat(32);
const clone = value => JSON.parse(JSON.stringify(value));
const rejects = status => error => error.status === status;
function note(overrides = {}) {
  return { screen: SCREEN, kind: "point", text: "Gjør neste steg tydeligere.",
    anchor: { path: "main:nth-of-type(1) > button:nth-of-type(1)", role: "button", rect: { x: 20, y: 100, width: 120, height: 40 }, viewport: { width: 390, height: 844 } }, ...overrides };
}
function fixture(t, options = {}) {
  const directory = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "feedback-submit-draft-")));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const store = new FeedbackStore(directory, { canvas: true, ...options });
  store.knowScreen(SCREEN, "initial.html");
  return store;
}
function input(store, comment = note()) {
  return { comment, revision: store.state.revision, commentIds: store.state.comments.filter(item => item.submission === 0).map(item => item.id) };
}
function unchanged(store, action, expected) {
  const before = clone(store.state), disk = fs.readFileSync(store.filename, "utf8");
  assert.throws(action, expected);
  assert.deepEqual(store.state, before);
  assert.equal(fs.readFileSync(store.filename, "utf8"), disk);
}
test("direct sending commits one composer comment, immutable round and delivery together", t => {
  const store = fixture(t), value = input(store), persist = store.persist.bind(store);
  let writes = 0;
  store.persist = next => { writes++; persist(next); };
  const result = store.submitDraft(value);
  assert.equal(writes, 1);
  assert.equal(result.revision, value.revision + 1);
  assert.equal(result.submission, 1);
  assert.equal(result.comments.length, 1);
  assert.equal(result.comments[0].submission, 1);
  assert.equal(result.comments[0].lastSubmission, 1);
  assert.deepEqual(store.state.submissions[0].comments, result.comments);
  assert.equal(store.state.submissions[0].revision, result.revision);
  assert.deepEqual(result.canvas.rounds, [{ submission: 1, delivery: "sending", review: "unread", reply: "" }]);
  assert(validPersistedFeedback(store.state));
  assert.deepEqual(JSON.parse(fs.readFileSync(store.filename, "utf8")), store.state);
});

test("one saved comment and one composer comment send exactly two across their recorded screens", t => {
  const store = fixture(t), other = "b".repeat(32);
  store.knowScreen(other, "other.html");
  const saved = store.create(note({ screen: other, text: "Behold overskriften." })).comments[0];
  const value = input(store), result = store.submitDraft(value), batch = store.nextSubmission(0);
  assert.equal(result.comments.length, 2);
  assert.equal(batch.comments.length, 2);
  assert.equal(batch.comments.filter(item => item.id === saved.id).length, 1);
  assert.equal(batch.comments.filter(item => item.text === value.comment.text).length, 1);
  assert.deepEqual(new Set(batch.screens.map(item => item.screen)), new Set([SCREEN, other]));
  value.comment.text = "Changed after sending";
  assert.notEqual(batch.comments[1].text, value.comment.text);
  assert(validPersistedFeedback(store.state));
});

test("stale revision or an incomplete existing collection cannot add a comment or send unrelated feedback", t => {
  const store = fixture(t);
  store.create(note({ text: "Første innspill." }));
  const stale = input(store);
  store.create(note({ text: "Nyere innspill som ikke var vist." }));
  unchanged(store, () => store.submitDraft(stale), rejects(409));
  unchanged(store, () => store.submitDraft({ ...stale, revision: store.state.revision }), rejects(409));
  unchanged(store, () => store.submitDraft({ ...input(store), commentIds: [] }), rejects(409));
  unchanged(store, () => store.submitDraft({ ...input(store), commentIds: [store.state.comments[0].id, "f".repeat(24)] }), rejects(409));
  const reversed = input(store); reversed.commentIds.reverse();
  assert.equal(store.submitDraft(reversed).comments.length, 3, "The collection is a set, not an ordering instruction.");
});

test("direct sending has a closed shape and validates every composer field before writing", t => {
  const store = fixture(t);
  store.create(note());
  const value = input(store);
  const malformed = [null, {}, { ...value, revision: -1 }, { ...value, revision: 1.5 },
    { ...value, commentIds: null }, { ...value, commentIds: [null] }, { ...value, commentIds: ["x"] },
    { ...value, commentIds: [...value.commentIds, ...value.commentIds] },
    { ...value, commentIds: Array(MAX_COMMENTS + 1).fill("b".repeat(24)) },
    { ...value, screen: SCREEN }, { ...value, comment: { ...value.comment, text: " " } },
    { ...value, comment: { ...value.comment, text: "ø".repeat(1001) } },
    { ...value, comment: { ...value.comment, proposal: { property: "text", value: "Unexpected" } } }];
  for (const body of malformed) unchanged(store, () => store.submitDraft(body), rejects(400));
  unchanged(store, () => store.submitDraft(input(store, note({ screen: "c".repeat(32) }))), rejects(409));
  unchanged(store, () => store.submitDraft(input(store, note({ context: { variant: "", target: "missing", values: {} } }))), rejects(409));
});

test("pending delivery prevents direct sends while acknowledged processing permits a separate immutable round", t => {
  const store = fixture(t), canvas = new CanvasState(store);
  store.submitDraft(input(store));
  const first = clone(store.state.submissions[0]);
  unchanged(store, () => store.submitDraft(input(store)), rejects(409));
  canvas.delivery({ submission: 1, status: "unknown" });
  unchanged(store, () => store.submitDraft(input(store)), rejects(409));
  canvas.review({ submission: 1, status: "working", reply: "Arbeider med første innspill." });
  unchanged(store, () => store.submitDraft({ ...input(store), commentIds: [first.comments[0].id] }), rejects(409));
  store.submitDraft(input(store, note({ text: "Et nytt ønske." })));
  assert.equal(store.state.submission, 2);
  assert.deepEqual(store.state.submissions[0], first);
  assert.equal(store.state.submissions[1].comments.length, 1);
  assert.notEqual(store.state.submissions[1].comments[0].id, first.comments[0].id);
  assert(validPersistedFeedback(store.state));
});

test("failed commit leaves no composer or round, and a lost reply retry commits only once", t => {
  const store = fixture(t), receipts = new FeedbackMutationReceipts(), id = "e".repeat(32);
  store.create(note({ text: "Et lagret innspill." }));
  const value = input(store), persist = store.persist.bind(store);
  const send = body => receipts.run(id, "POST", "/comments/submit-draft", body, current => store.submitDraft(current));
  store.persist = () => { throw new Error("Controlled precommit failure"); };
  unchanged(store, () => send(value), /precommit/);
  store.persist = persist;
  send(value);
  const committed = clone(store.state), disk = fs.readFileSync(store.filename, "utf8");
  send(clone(value)); // The first response was lost; retry the unchanged request.
  assert.deepEqual(store.state, committed);
  assert.equal(fs.readFileSync(store.filename, "utf8"), disk);
  assert.equal(store.state.submission, 1);
  assert.equal(store.state.submissions[0].comments.length, 2);
  unchanged(store, () => send({ ...value, comment: { ...value.comment, text: "Different intent" } }), rejects(409));
  assert(validPersistedFeedback(store.state));
});

test("a durability error after commit retains the complete direct send and its retry receipt", t => {
  let persisted = null, failAfterCommit = false;
  const store = fixture(t, { persistence: { load: () => null, persist(next) {
    persisted = clone(next);
    if (failAfterCommit) throw Object.assign(new Error("Controlled postcommit failure"), { committed: true });
  } } });
  const receipts = new FeedbackMutationReceipts(), value = input(store), id = "d".repeat(32);
  const send = () => receipts.run(id, "POST", "/comments/submit-draft", value, body => store.submitDraft(body));
  failAfterCommit = true;
  assert.throws(send, error => error.committed === true);
  assert.equal(store.state.submission, 1);
  assert.equal(store.state.comments.length, 1);
  assert.deepEqual(store.state, persisted);
  send();
  assert.equal(store.state.submission, 1);
  assert(validPersistedFeedback(persisted));
});

test("comment and round limits reject direct sending before adding the composer", t => {
  const store = fixture(t, { canvas: false });
  const seed = store.create(note()).comments[0];
  store.change(state => { state.comments = Array.from({ length: MAX_COMMENTS }, (_, index) => ({ ...clone(seed), id: index.toString(16).padStart(24, "0") })); });
  unchanged(store, () => store.submitDraft(input(store)), error => error.status === 429 && /Comment limit/.test(error.message));
  store.change(state => { state.comments = [seed]; });
  for (let count = 0; count < MAX_SUBMISSIONS; count++) {
    store.submit({});
    store.patch(seed.id, { status: "open", resubmit: true });
  }
  unchanged(store, () => store.submitDraft(input(store)), error => error.status === 429 && /Submission limit/.test(error.message));
  assert(validPersistedFeedback(store.state));
});

test("saved HTML feedback keeps its exact schema and bytes on hydration", t => {
  const store = fixture(t);
  store.create(note()); store.submit({});
  const bytes = fs.readFileSync(store.filename, "utf8"), saved = JSON.parse(bytes);
  assert.deepEqual(saved.screens, [{ screen: SCREEN, filename: "initial.html" }]);
  const reopened = new FeedbackStore(store.directory, { canvas: true, persistence: { load: () => clone(saved), persist: () => assert.fail("Opening saved feedback must not rewrite it.") } });
  assert.equal(JSON.stringify(reopened.state) + "\n", bytes);
  assert.equal(fs.readFileSync(store.filename, "utf8"), bytes);
});

test("comments and saved state stay bound to a recorded HTML screen and carry no app evidence", t => {
  const store = fixture(t);
  store.create(note()); store.submit({});
  const saved = clone(store.state), page = { route: "/demo", target: { tag: "button", role: "button", name: "Neste", text: "Neste", path: "button:nth-of-type(1)" }, viewport: { width: 390, height: 844, scrollX: 0, scrollY: 0 } };
  assert.equal(validCreate(note({ applicationContext: page })), false);
  unchanged(store, () => store.create(note({ applicationContext: page })), rejects(400));
  assert(validPersistedFeedback(saved));
  const changes = [
    value => { value.comments[0].screen = value.submissions[0].comments[0].screen = "c".repeat(32); },
    value => { value.screens[0] = { screen: SCREEN, source: { kind: "application", checkpoint: "b".repeat(64), route: "/demo" } }; },
    value => { value.comments[0].applicationContext = page; },
    value => { value.submissions[0].comments[0].applicationContext = page; },
  ];
  for (const change of changes) { const value = clone(saved); change(value); assert.equal(validPersistedFeedback(value), false, change.toString()); }
});

test("storage exhaustion cannot leave a saved composer outside its intended round", t => {
  const store = fixture(t, { canvas: false });
  const large = note({ kind: "edit", text: "x".repeat(2000), proposal: { property: "text", value: "y".repeat(2000) } });
  const seed = store.create(large).comments[0];
  store.change(state => { state.comments = Array.from({ length: MAX_COMMENTS - 1 }, (_, index) => ({ ...clone(seed), id: index.toString(16).padStart(24, "0") })); });
  store.submit({});
  store.change(state => { for (const comment of state.comments) comment.submission = 0; });
  assert(Buffer.byteLength(fs.readFileSync(store.filename)) < MAX_STORE_BYTES);
  unchanged(store, () => store.submitDraft(input(store, large)), error => error.status === 429 && /storage limit/.test(error.message));
  assert.equal(store.state.submissions.length, 1);
  assert.equal(store.state.comments.length, MAX_COMMENTS - 1);
  assert(validPersistedFeedback(store.state));
});
