"use strict";
const test = require("node:test"), assert = require("node:assert/strict");
const fs = require("node:fs"), os = require("node:os"), path = require("node:path");
const { FeedbackStore } = require("../scripts/feedback-store.js");
const { CanvasState } = require("../scripts/canvas-state.js");
const { WorkspaceStore, MAX_HTML_BYTES } = require("../scripts/workspace-store.js");
const { WorkspaceState, validWorkspaceState, screenIdentity } = require("../scripts/workspace-state.js");
const { promoteTemporaryWorkspace } = require("../scripts/workspace-promotion.js");
const copy = value => JSON.parse(JSON.stringify(value));
const reject = status => error => error.status === status;
const declaration = { version: 1, variants: [], targets: [{ key: "card", variant: "", label: "Oppsummering", controls: [
  { id: "density", label: "Luft", type: "select", initial: "roomy", options: [{ value: "roomy", label: "Romslig" }, { value: "compact", label: "Kompakt" }] }
] }] };
const note = (screen, text) => ({ screen, kind: "point", text, anchor: { path: "h1:nth-of-type(1)", role: "heading",
  rect: { x: 0, y: 0, width: 100, height: 30 }, viewport: { width: 390, height: 844 } } });

function fixture(t) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "sketch-promotion-")));
  const projectDir = path.join(root, "project"), runtime = path.join(root, "runtime"), content = path.join(root, "content");
  for (const directory of [projectDir, runtime, content]) fs.mkdirSync(directory, { mode: 0o700 });
  const feedback = new FeedbackStore(runtime, { canvas: true }), canvas = new CanvasState(feedback), stores = [];
  const add = (filename, html, design = null) => {
    fs.writeFileSync(path.join(content, filename), html);
    if (design) fs.writeFileSync(path.join(content, filename.slice(0, -5) + ".design.json"), JSON.stringify(design));
    const screen = screenIdentity(filename, html, design); feedback.knowScreen(screen, filename, design); return screen;
  };
  const first = add("first.html", '<h1>Velg møte</h1><section data-vc-key="card">Oppsummering</section>', declaration);
  feedback.create(note(first, "Gjør neste steg tydeligere.")); feedback.submit({});
  canvas.delivery({ submission: 1, status: "queued" });
  canvas.review({ submission: 1, status: "answered", reply: "Neste steg er tydeligere i forslaget." });
  const currentScreen = add("second.html", "<h1>Velg tidspunkt</h1>");
  feedback.create(note(currentScreen, "Et usendt innspill."));
  const readPair = screen => ({ html: fs.readFileSync(path.join(content, screen.filename), "utf8"),
    design: fs.existsSync(path.join(content, screen.filename.slice(0, -5) + ".design.json"))
      ? JSON.parse(fs.readFileSync(path.join(content, screen.filename.slice(0, -5) + ".design.json"), "utf8")) : null });
  const save = (overrides = {}) => promoteTemporaryWorkspace({ feedback, projectDir, workspacePath: "designs/proposal", workspaceId: "a".repeat(24),
    title: "Møteforslag", expectedScreen: currentScreen, currentScreen, expectedRevision: feedback.state.revision, readPair,
    storeFactory: options => { const store = new WorkspaceStore(options); stores.push(store); return store; }, ...overrides });
  t.after(() => { for (const store of stores) store.close(); fs.rmSync(root, { recursive: true, force: true }); });
  return { root, projectDir, runtime, content, feedback, canvas, first, currentScreen, readPair, stores, save };
}

test("promotion preserves all versions, full feedback and live routing, then reopens without replay", t => {
  const f = fixture(t), before = copy(f.feedback.state), privateBytes = fs.readFileSync(f.feedback.filename);
  const { store, workspaceState } = f.save();
  assert.equal(workspaceState.feedback, f.feedback); assert.equal(f.feedback.persistence, store);
  assert.equal(workspaceState.current().screen, f.currentScreen);
  assert.equal(workspaceState.summary().version, 2); assert.equal(f.feedback.state.revision, before.revision + 1);
  for (const field of ["screens", "comments", "submissions", "canvas"]) assert.deepEqual(f.feedback.state[field], before[field], field);
  assert.equal(f.feedback.state.submission, 1); assert(validWorkspaceState(f.feedback.state));
  assert.deepEqual(fs.readFileSync(f.feedback.filename), privateBytes, "Promotion does not rewrite or remove the temporary receipt.");
  f.canvas.review({ submission: 1, status: "answered", reply: "Svaret oppdateres i samme arbeid." });
  workspaceState.publish({ expectedScreen: f.currentScreen, filename: "third.html", html: "<h1>Bekreft tidspunkt</h1>" });
  assert.equal(f.feedback.state.submission, 1); assert.equal(workspaceState.summary().version, 3);
  const committed = copy(f.feedback.state); store.close();
  const reopenedStore = new WorkspaceStore({ projectDir: f.projectDir, workspacePath: "designs/proposal", validateState: validWorkspaceState });
  f.stores.push(reopenedStore);
  const runtime = fs.mkdtempSync(path.join(f.root, "reopen-"));
  const feedback = new FeedbackStore(runtime, { canvas: true, persistence: reopenedStore });
  const reopened = new WorkspaceState(feedback, reopenedStore, { path: "designs/proposal", recovered: true });
  assert.equal(reopened.current().filename, "third.html"); assert.equal(feedback.state.submission, 1);
  assert.deepEqual(feedback.state.comments, committed.comments); assert.deepEqual(feedback.state.submissions, committed.submissions);
  assert.equal(feedback.state.canvas.rounds[0].previousSession, true);
  assert.equal(feedback.state.canvas.rounds[0].reply, "Svaret oppdateres i samme arbeid.");
});

test("legacy temporary rounds acquire only missing previousSession markers", t => {
  const f = fixture(t);
  delete f.feedback.state.canvas.rounds[0].previousSession;
  const { workspaceState } = f.save();
  assert.equal(f.feedback.state.canvas.rounds[0].previousSession, false);
  assert.equal(f.feedback.state.canvas.rounds[0].delivery, "queued");
  assert.equal(workspaceState.summary().recovered, false);
});

test("stale guards, changed or missing source pairs fail before any target is created", t => {
  const f = fixture(t), original = copy(f.feedback.state);
  for (const overrides of [{ expectedScreen: "f".repeat(32) }, { expectedRevision: original.revision - 1 },
    { readPair: screen => ({ ...f.readPair(screen), html: "<h1>Endret utenfra</h1>" }) },
    { readPair: screen => ({ ...f.readPair(screen), design: null }) }]) {
    assert.throws(() => f.save(overrides), reject(409));
    assert.deepEqual(f.feedback.state, original); assert.equal(f.feedback.persistence, null);
    assert.deepEqual(fs.readdirSync(f.projectDir), []);
  }
  fs.unlinkSync(path.join(f.content, "first.html"));
  assert.throws(() => f.save(), error => error.code === "ENOENT");
  assert.deepEqual(fs.readdirSync(f.projectDir), []); assert.deepEqual(f.feedback.state, original);
});

test("duplicate filenames and oversized pairs are rejected before target writing", t => {
  const f = fixture(t);
  const original = copy(f.feedback.state);
  f.feedback.state.screens[1].filename = "first.html";
  assert.throws(() => f.save(), reject(409)); assert.deepEqual(fs.readdirSync(f.projectDir), []);
  f.feedback.state = original;
  assert.throws(() => f.save({ readPair: () => ({ html: "x".repeat(MAX_HTML_BYTES + 1), design: null }) }), reject(413));
  assert.deepEqual(fs.readdirSync(f.projectDir), []);
});

test("occupied and symlink destinations stay untouched and retain the temporary writer", t => {
  const f = fixture(t), original = copy(f.feedback.state), target = path.join(f.projectDir, "designs", "proposal");
  fs.mkdirSync(target, { recursive: true }); fs.writeFileSync(path.join(target, "owner.txt"), "behold");
  assert.throws(() => f.save(), reject(409)); assert.equal(fs.readFileSync(path.join(target, "owner.txt"), "utf8"), "behold");
  fs.symlinkSync(f.content, path.join(f.projectDir, "alias"));
  assert.throws(() => f.save({ workspacePath: "alias/proposal" }), reject(409));
  assert.equal(fs.existsSync(path.join(f.content, "proposal")), false);
  assert.equal(f.feedback.persistence, null); assert.deepEqual(f.feedback.state, original);
});

test("precommit failure discards only its own revisions and the old writer remains usable", t => {
  const f = fixture(t), before = copy(f.feedback.state);
  assert.throws(() => f.save({ storeFactory: options => {
    const store = new WorkspaceStore(options); f.stores.push(store);
    store.persist = () => { throw new Error("Controlled precommit failure"); };
    return store;
  } }), /precommit/);
  assert.equal(f.feedback.persistence, null); assert.deepEqual(f.feedback.state, before);
  const target = path.join(f.projectDir, "designs", "proposal");
  assert.equal(fs.existsSync(path.join(target, "workspace.json")), false);
  assert.deepEqual(fs.readdirSync(path.join(target, "revisions")), []);
  f.feedback.create(note(f.currentScreen, "Arbeidet fortsetter etter feilen."));
  assert.equal(JSON.parse(fs.readFileSync(f.feedback.filename, "utf8")).comments.length, 3);
  const saved = f.save(); assert.equal(saved.workspaceState.summary().version, 2);
});

test("a verified current pair failure before commit never adopts a partial workspace", t => {
  const f = fixture(t), before = copy(f.feedback.state);
  assert.throws(() => f.save({ storeFactory: options => {
    const store = new WorkspaceStore(options); f.stores.push(store);
    store.readRevision = () => { throw new Error("Controlled verification failure"); };
    return store;
  } }), /verification/);
  assert.equal(f.feedback.persistence, null); assert.deepEqual(f.feedback.state, before);
  assert.equal(fs.existsSync(path.join(f.projectDir, "designs/proposal/workspace.json")), false);
});

test("an earlier saved pair changed before commit blocks adoption and is never deleted as cleanup", t => {
  const f = fixture(t), before = copy(f.feedback.state);
  let changed;
  assert.throws(() => f.save({ storeFactory: options => {
    const store = new WorkspaceStore(options); f.stores.push(store);
    const write = store.writeRevision.bind(store);
    store.writeRevision = input => {
      const meta = write(input);
      if (input.filename === "second.html") {
        changed = path.join(store.revisionsDir, "first.html");
        fs.writeFileSync(changed, "Replaced while saving");
      }
      return meta;
    };
    return store;
  } }), reject(409));
  assert.equal(fs.readFileSync(changed, "utf8"), "Replaced while saving");
  assert.equal(f.feedback.persistence, null); assert.deepEqual(f.feedback.state, before);
  assert.equal(fs.existsSync(path.join(f.projectDir, "designs/proposal/workspace.json")), false);
  assert.equal(fs.existsSync(path.join(f.projectDir, "designs/proposal/revisions/second.html")), false);
});

test("postcommit directory sync failure returns live handles and keeps every committed byte", t => {
  const f = fixture(t), before = copy(f.feedback.state);
  const promoted = f.save({ storeFactory: options => {
    const store = new WorkspaceStore(options); f.stores.push(store);
    const persist = store.persist.bind(store);
    store.persist = value => {
      const sync = fs.fsyncSync, directory = fs.statSync(store.directory);
      fs.fsyncSync = fd => {
        const stat = fs.fstatSync(fd);
        if (stat.dev === directory.dev && stat.ino === directory.ino) throw new Error("Controlled durability failure");
        return sync(fd);
      };
      try { return persist(value); } finally { fs.fsyncSync = sync; store.persist = persist; }
    };
    return store;
  } });
  assert.equal(promoted.committedError.committed, true); assert.match(promoted.committedError.message, /durability/);
  assert.equal(f.feedback.persistence, promoted.store); assert.equal(promoted.workspaceState.feedback, f.feedback);
  assert.equal(promoted.workspaceState.current().screen, f.currentScreen);
  assert.deepEqual(promoted.store.load().submissions, before.submissions);
  assert.equal(fs.readdirSync(promoted.store.revisionsDir).length, 3);
  assert.throws(() => f.save(), reject(409), "The parent retries the adopted identity, not another create.");
  f.feedback.create(note(f.currentScreen, "Lagringen fortsetter i samme rom."));
  assert.equal(promoted.store.load().comments.length, 3);
});
