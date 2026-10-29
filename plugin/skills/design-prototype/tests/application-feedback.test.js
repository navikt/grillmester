"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { FeedbackStore, FeedbackMutationReceipts, validCreate, validPersistedFeedback } = require("../scripts/feedback-store.js");
const { CanvasState, PAGE_BYTES } = require("../scripts/canvas-state.js");
const { screenIdentity } = require("../scripts/application-contract.js");

const clone = value => JSON.parse(JSON.stringify(value));
const checkpoint = "a".repeat(64);
const route = "/syk/dialogmoter?view=kort";
const reject = status => error => error.status === status;
function note(screen, page = route) {
  return { screen, kind: "point", text: "Prøv radioknapper for møtevalg.",
    anchor: { path: "main:nth-of-type(1) > button:nth-of-type(1)", role: "button", rect: { x: 20, y: 120, width: 100, height: 40 }, viewport: { width: 375, height: 812 } },
    applicationContext: { route: page, target: { tag: "button", role: "button", name: "Neste", text: "Neste", path: "main:nth-of-type(1) > button:nth-of-type(1)" }, viewport: { width: 375, height: 812, scrollX: 0, scrollY: 20 } },
  };
}
function fixture(t) {
  const directory = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "application-feedback-")));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const feedback = new FeedbackStore(directory, { canvas: true });
  const canvas = new CanvasState(feedback);
  const register = (page = route, source = checkpoint) => feedback.knowApplicationScreen({ checkpoint: source, route: page });
  const hydrate = state => new FeedbackStore(directory, { canvas: true, persistence: { load: () => clone(state), persist: () => assert.fail("Opening saved feedback must not rewrite it.") } });
  return { directory, feedback, canvas, register, hydrate };
}

test("editing an unsent comment preserves its target, guards stale changes and never rewrites sent evidence", t => {
  const room = fixture(t), screen = room.register();
  room.feedback.create(note(screen));
  const original = clone(room.feedback.state.comments[0]), revision = room.feedback.state.revision;
  assert.throws(() => room.feedback.editDraft(original.id, { text: "Ny tekst", expectedRevision: revision - 1 }), reject(409));
  for (const text of [" ", "x".repeat(2001), "\u0000"]) assert.throws(() => room.feedback.editDraft(original.id, { text, expectedRevision: revision }), reject(400));
  room.feedback.editDraft(original.id, { text: " Behold de tre valgene, men prøv radioknapper. ", expectedRevision: revision });
  const edited = room.feedback.state.comments[0];
  assert.equal(edited.text, "Behold de tre valgene, men prøv radioknapper.");
  assert.equal(edited.id, original.id); assert.equal(edited.screen, original.screen);
  assert.deepEqual(edited.anchor, original.anchor); assert.deepEqual(edited.applicationContext, original.applicationContext);
  assert(validPersistedFeedback(room.feedback.state));
  room.feedback.submit({ revision: room.feedback.state.revision });
  assert.throws(() => room.feedback.editDraft(original.id, { text: "Endret etter sending", expectedRevision: room.feedback.state.revision }), reject(409));
  room.feedback.patch(original.id, { resubmit: true, status: "open", expectedSubmission: 1 });
  assert.throws(() => room.feedback.editDraft(original.id, { text: "Endret resendt tekst", expectedRevision: room.feedback.state.revision }), reject(409));
  assert.equal(room.feedback.state.submissions[0].comments[0].text, edited.text);
});

test("application registration records the actual source once and separates routes from checkpoints", t => {
  const room = fixture(t);
  const first = room.register();
  assert.equal(first, screenIdentity(checkpoint, route));
  assert.deepEqual(room.feedback.state.screens, [{ screen: first, source: { kind: "application", checkpoint, route } }]);
  const bytes = fs.readFileSync(room.feedback.filename, "utf8"), revision = room.feedback.state.revision;
  assert.equal(room.register(), first); assert.equal(room.feedback.state.revision, revision);
  assert.equal(fs.readFileSync(room.feedback.filename, "utf8"), bytes);
  assert.notEqual(room.register("/next"), first);
  assert.notEqual(room.register(route, "b".repeat(64)), first);
  assert.equal(room.feedback.state.screens.length, 3);
  assert(room.feedback.state.screens.every(item => !Object.hasOwn(item, "filename")));
  assert(validPersistedFeedback(room.feedback.state));
});

test("equivalent query encodings register one canonical route and retain exact context binding", t => {
  const room = fixture(t), screen = room.register("/app?q=to%20ord");
  const before = clone(room.feedback.state);
  assert.equal(before.screens[0].source.route, "/app?q=to+ord");
  assert.equal(room.register("/app?q=to+ord"), screen); assert.deepEqual(room.feedback.state, before);
  assert.throws(() => room.feedback.create(note(screen, "/app?q=to%20ord")), reject(409));
  room.feedback.create(note(screen, "/app?q=to+ord")); assert(validPersistedFeedback(room.feedback.state));
});

test("invalid registration and an existing source collision never modify feedback", t => {
  const room = fixture(t), screen = room.register();
  const before = JSON.stringify(room.feedback.state);
  for (const input of [null, {}, { checkpoint, route, url: "http://localhost" }, { checkpoint: "b", route }, { checkpoint, route: "/?token=private" }, { checkpoint, route: "/a/../b" }]) assert.throws(() => room.feedback.knowApplicationScreen(input), reject(400));
  assert.equal(JSON.stringify(room.feedback.state), before);
  const collision = fixture(t); collision.feedback.knowScreen(screen, "existing.html");
  const original = clone(collision.feedback.state);
  assert.throws(() => collision.register(), reject(409)); assert.deepEqual(collision.feedback.state, original);
});

test("point and area app comments use the existing round and canvas reader", t => {
  const room = fixture(t), screen = room.register();
  room.feedback.create(note(screen));
  room.feedback.create({ ...note(screen), kind: "area", text: "Gi dette området tydeligere inndeling." });
  room.feedback.submit({ screen, revision: room.feedback.state.revision });
  const batch = room.feedback.nextSubmission(0), page = room.canvas.read({ submission: 1 });
  assert.deepEqual(batch.screens, room.feedback.state.screens);
  assert.deepEqual(batch.comments.map(item => item.applicationContext), [note(screen).applicationContext, note(screen).applicationContext]);
  assert.equal(page.items[0].type, "screen"); assert.deepEqual(page.items[0].value.source, { kind: "application", checkpoint, route });
  assert.equal(page.items.filter(item => item.type === "comment").length, 2);
  assert.equal(page.round.delivery, "sending"); assert.equal(page.round.review, "unread");
  assert.equal(page.hasMore, false); assert(validPersistedFeedback(room.feedback.state));
});

test("app context cannot be mixed with sketch fields, kinds or unknown authority", t => {
  const room = fixture(t), screen = room.register();
  assert(validCreate(note(screen)));
  const mutations = [
    value => { value.context = { variant: "", target: "card", values: {} }; },
    value => { value.proposal = { property: "text", value: "Bytt" }; },
    value => { value.adjustment = { variant: "", target: "card", values: { density: "compact" } }; },
    value => { value.variant = "short"; },
    value => { value.kind = "edit"; }, value => { value.kind = "adjustment"; }, value => { value.kind = "variant"; },
    value => { value.applicationContext.target.file = "src/component.tsx"; },
    value => { value.applicationContext.target.value = "private"; },
    value => { value.applicationContext = null; }, value => { value.applicationContext.extra = true; },
  ];
  const before = clone(room.feedback.state);
  for (const mutate of mutations) { const value = note(screen); mutate(value); assert.equal(validCreate(value), false); assert.throws(() => room.feedback.create(value), reject(400)); }
  assert.deepEqual(room.feedback.state, before);
});

test("creation binds context to the registered source and exact recorded route", t => {
  const room = fixture(t), app = room.register(), html = "b".repeat(32);
  room.feedback.knowScreen(html, "sketch.html");
  const withoutContext = note(app); delete withoutContext.applicationContext;
  const before = clone(room.feedback.state);
  for (const value of [withoutContext, note(app, "/another-page"), note(html), note("c".repeat(32))]) assert.throws(() => room.feedback.create(value), reject(409));
  assert.deepEqual(room.feedback.state, before);
  const next = room.register("/next", "b".repeat(64));
  assert.throws(() => room.feedback.create({ ...note(app), screen: next }), reject(409));
  room.feedback.create(note(next, "/next"));
  const sketch = note(html); delete sketch.applicationContext; room.feedback.create(sketch);
  assert(validPersistedFeedback(room.feedback.state));
});

test("caller and read-result mutations cannot change retained application evidence", t => {
  const room = fixture(t), screen = room.register(), input = note(screen);
  room.feedback.create(input);
  const stored = clone(room.feedback.state.comments[0]);
  input.applicationContext.route = "/unexpected"; input.applicationContext.target.name = "Endret"; input.anchor.rect.x = 500;
  assert.deepEqual(room.feedback.state.comments[0], stored);
  room.feedback.submit({});
  const journal = JSON.stringify(room.feedback.state.submissions);
  const batch = room.feedback.nextSubmission(0); batch.comments[0].applicationContext.target.name = "Endret igjen"; batch.screens[0].source.route = "/wrong";
  const page = room.canvas.read({ submission: 1 }); page.items[1].value.applicationContext.viewport.width = 999;
  assert.equal(JSON.stringify(room.feedback.state.submissions), journal); assert(validPersistedFeedback(room.feedback.state));
});

test("saved application feedback hydrates without migration, rewriting or lost rounds", t => {
  const room = fixture(t), screen = room.register();
  room.feedback.create(note(screen)); room.feedback.submit({});
  room.canvas.delivery({ submission: 1, status: "queued" });
  room.canvas.review({ submission: 1, status: "answered", reply: "Radioknappene er prøvd." });
  room.feedback.create(note(screen));
  const saved = JSON.parse(fs.readFileSync(room.feedback.filename, "utf8"));
  assert.equal(saved.schemaVersion, 1); assert(validPersistedFeedback(saved));
  const reopened = room.hydrate(saved);
  assert.equal(JSON.stringify(reopened.state), JSON.stringify(saved));
  assert.deepEqual(new CanvasState(reopened).read({ submission: 1 }), room.canvas.read({ submission: 1 }));
  assert.equal(reopened.state.comments.filter(item => item.submission === 0).length, 1);
});

test("hydration rejects tampered source unions, route bindings and immutable submitted evidence", t => {
  const room = fixture(t), screen = room.register(); room.feedback.create(note(screen)); room.feedback.submit({});
  const saved = clone(room.feedback.state);
  const changes = [
    value => { value.screens[0].filename = "app.html"; }, value => { value.screens[0].source.url = "http://localhost"; },
    value => { value.screens[0].source.kind = "sketch"; }, value => { value.screens[0].source.checkpoint = "b".repeat(64); },
    value => { value.screens[0].source.route = "/other"; }, value => { value.screens[0].screen = "b".repeat(32); },
    value => { value.screens.push(clone(value.screens[0])); },
    value => { value.comments[0].applicationContext.route = "/other"; },
    value => { delete value.comments[0].applicationContext; },
    value => { value.comments[0].context = { variant: "", target: "card", values: {} }; },
    value => { value.comments[0].applicationContext.target.name = "Changed after submission"; },
    value => { value.submissions[0].comments[0].applicationContext.target.name = "Changed historical evidence"; },
    value => { value.submissions[0].comments[0].applicationContext.target.file = "src/main.tsx"; },
    value => { value.comments[0].kind = "variant"; },
  ];
  for (const change of changes) { const value = clone(saved); change(value); assert.equal(validPersistedFeedback(value), false, change.toString()); assert.throws(() => room.hydrate(value), reject(400)); }
  assert.deepEqual(room.feedback.state, saved);
});

test("app review, deletion and resubmission preserve exact historical contexts", t => {
  const room = fixture(t), screen = room.register(); room.feedback.create(note(screen)); room.feedback.submit({});
  const first = clone(room.feedback.state.submissions[0]), id = first.comments[0].id;
  room.canvas.delivery({ submission: 1, status: "queued" });
  room.canvas.updateComment({ id, submission: 1, status: "fixed", reply: "En ny komponent er prøvd." });
  room.canvas.review({ submission: 1, status: "answered", reply: "Prøv radiogruppen." });
  room.feedback.patch(id, { status: "open", resubmit: true, expectedSubmission: 1 });
  room.feedback.submit({});
  assert.deepEqual(room.feedback.state.submissions[0], first);
  assert.deepEqual(room.feedback.state.submissions[1].comments[0].applicationContext, first.comments[0].applicationContext);
  assert.throws(() => room.canvas.updateComment({ id, submission: 1, status: "fixed" }), reject(409));
  room.feedback.delete(id, {});
  assert.equal(room.canvas.read({ submission: 1 }).items[1].current.present, false);
  assert.deepEqual(room.feedback.state.submissions[0], first); assert(validPersistedFeedback(room.feedback.state));
});

test("large submitted application contexts paginate without truncation or changing item order", t => {
  const room = fixture(t), screen = room.register();
  for (let index = 0; index < 48; index += 1) {
    const value = note(screen); value.text = `${index}: ${"ø".repeat(990)}`; value.applicationContext.target.text = "ø".repeat(500);
    room.feedback.create(value);
  }
  room.feedback.submit({});
  let offset = 0, pages = 0; const entries = [];
  do {
    const page = room.canvas.read({ submission: 1, offset });
    assert(Buffer.byteLength(JSON.stringify(page)) <= PAGE_BYTES);
    assert(page.items.length > 0 && page.items.length <= 32);
    entries.push(...page.items); offset = page.nextOffset; pages += 1;
  } while (offset !== null);
  assert(pages >= 3); assert.equal(entries.length, 49); assert.equal(entries[0].type, "screen");
  assert.deepEqual(entries.slice(1).map(item => item.value), room.feedback.state.submissions[0].comments);
});

test("application registration respects bounded screens while existing registrations remain available", t => {
  const room = fixture(t);
  for (let index = 0; index < 100; index += 1) room.register(`/page/${index}`);
  const before = clone(room.feedback.state);
  assert.equal(room.register("/page/0"), before.screens[0].screen);
  assert.throws(() => room.register("/page/100"), reject(429));
  assert.deepEqual(room.feedback.state, before); assert(validPersistedFeedback(before));
});

test("legacy HTML payloads retain their exact schema and bytes on hydration", t => {
  const room = fixture(t), screen = "b".repeat(32);
  room.feedback.knowScreen(screen, "legacy.html");
  const value = note(screen); delete value.applicationContext;
  room.feedback.create(value); room.feedback.submit({});
  const bytes = fs.readFileSync(room.feedback.filename, "utf8"), saved = JSON.parse(bytes);
  assert.deepEqual(saved.screens, [{ screen, filename: "legacy.html" }]);
  assert(saved.comments.every(item => !Object.hasOwn(item, "applicationContext")));
  assert.equal(JSON.stringify(room.hydrate(saved).state) + "\n", bytes);
  assert.equal(fs.readFileSync(room.feedback.filename, "utf8"), bytes);
});

test("existing mutation receipts keep app feedback idempotent after a lost response", t => {
  const room = fixture(t), screen = room.register(), receipts = new FeedbackMutationReceipts(), input = note(screen), id = "d".repeat(32);
  receipts.run(id, "POST", "/comments", input, value => room.feedback.create(value));
  const before = clone(room.feedback.state);
  receipts.run(id, "POST", "/comments", clone(input), value => room.feedback.create(value));
  assert.deepEqual(room.feedback.state, before); assert.equal(room.feedback.state.comments.length, 1);
  const changed = clone(input); changed.applicationContext.viewport.width = 1280;
  assert.throws(() => receipts.run(id, "POST", "/comments", changed, value => room.feedback.create(value)), reject(409));
  assert.deepEqual(room.feedback.state, before);
});

test("failed persistence cannot register an application screen only in memory", t => {
  const room = fixture(t), before = clone(room.feedback.state);
  room.feedback.persistence = { persist() { throw new Error("Disk unavailable"); } };
  assert.throws(() => room.register(), /Disk unavailable/);
  assert.deepEqual(room.feedback.state, before);
  room.feedback.persistence = null; assert.equal(room.register(), screenIdentity(checkpoint, route));
  assert(validPersistedFeedback(room.feedback.state));
});
