"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { WorkspaceStore } = require("../scripts/workspace-store.js");
const { WorkspaceState, validWorkspaceState } = require("../scripts/workspace-state.js");
const { FeedbackStore } = require("../scripts/feedback-store.js");

const declaration = { version: 2, variants: [], targets: [], texts: [{ id: "heading", label: "Overskrift", value: "Velg tidspunkt" }] };
const html = '<h1><span data-vc-text="heading">Velg tidspunkt</span></h1>';
const note = screen => ({ screen, kind: "point", text: "Mer luft.", anchor: { path: "h1:nth-of-type(1)", role: "heading",
  rect: { x: 0, y: 0, width: 100, height: 30 }, viewport: { width: 390, height: 844 } } });

function fixture(t) {
  const projectDir = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "workspace-lifecycle-")));
  const stores = [];
  t.after(() => {
    for (const store of stores) { try { store.close(); } catch { /* Already closed. */ } }
    fs.chmodSync(path.join(projectDir, "designs/example"), 0o700);
    fs.rmSync(projectDir, { recursive: true, force: true });
  });
  const open = (create = false) => {
    const store = new WorkspaceStore({ projectDir, workspacePath: "designs/example", create, validateState: validWorkspaceState });
    stores.push(store);
    try {
      const recovered = store.load() !== null;
      const feedback = new FeedbackStore(fs.mkdtempSync(path.join(projectDir, "private-")), { canvas: true, persistence: store,
        initialWorkspace: { id: "c".repeat(24), title: "Livssyklus", version: 0, revisions: [] } });
      return { store, feedback, workspace: new WorkspaceState(feedback, store, { path: "designs/example", recovered }) };
    } catch (error) { store.close(); throw error; }
  };
  return { projectDir, open };
}

test("opening a room with earlier rounds writes nothing until the next real change", t => {
  const { projectDir, open } = fixture(t);
  const room = open(true);
  room.workspace.publish({ expectedScreen: "", filename: "first.html", html, design: declaration });
  room.feedback.create(note(room.workspace.current().screen));
  room.feedback.submit({});
  room.store.close();
  const filename = path.join(projectDir, "designs/example/workspace.json");
  const bytes = fs.readFileSync(filename), inode = fs.statSync(filename).ino;
  const directory = path.join(projectDir, "designs/example");
  fs.chmodSync(directory, 0o500);
  const reopened = open();
  assert.equal(reopened.feedback.state.canvas.rounds[0].previousSession, true);
  assert.deepEqual(fs.readFileSync(filename), bytes, "Opening never rewrites the room.");
  assert.equal(fs.statSync(filename).ino, inode);
  fs.chmodSync(directory, 0o700);
  reopened.feedback.create(note(reopened.workspace.current().screen));
  const saved = JSON.parse(fs.readFileSync(filename, "utf8"));
  assert.equal(saved.canvas.rounds[0].previousSession, true, "The next real write saves the earlier-session marker.");
});

test("a damaged older version is reported as unavailable and creates no version", t => {
  const { projectDir, open } = fixture(t);
  const room = open(true);
  room.workspace.publish({ expectedScreen: "", filename: "first.html", html, design: declaration });
  room.workspace.publish({ expectedScreen: room.workspace.current().screen, filename: "second.html", html: html.replace("<h1>", "<h1 class=\"a\">"), design: declaration });
  room.store.close();
  fs.appendFileSync(path.join(projectDir, "designs/example/revisions/first.html"), "\n");
  const reopened = open();
  assert.throws(() => reopened.workspace.restore({ revisionId: 1, expectedRevision: reopened.feedback.state.revision }),
    error => error.status === 409 && error.errorCode === "revision-unavailable" && /first\.html/.test(error.message));
  fs.rmSync(path.join(projectDir, "designs/example/revisions/first.html"));
  assert.throws(() => reopened.workspace.read({ revisionId: 1, part: "html" }),
    error => error.status === 409 && error.errorCode === "revision-unavailable" && /missing/.test(error.message));
  assert.equal(reopened.workspace.summary().version, 2);
});

test("a held room names its holder and lock file, and closing removes an empty lock directory", t => {
  const { open } = fixture(t);
  const first = open(true);
  assert.throws(() => open(), error => error.status === 409
    && new RegExp(`already open in process ${process.pid}\\. .*remove (/\\S+\\.json)\\.$`).test(error.message));
  const directory = first.store.claim.directory;
  assert.equal(fs.existsSync(directory), true);
  first.store.close();
  assert.equal(fs.existsSync(directory), false, "The last claim removes its empty lock directory.");
  const second = open();
  assert.equal(second.workspace.summary().version, 0);
});

test("sketch revisions without workspace.json are explained on open and create, and never adopted", t => {
  const { projectDir, open } = fixture(t);
  const revisions = path.join(projectDir, "designs/example/revisions");
  fs.mkdirSync(revisions, { recursive: true, mode: 0o700 });
  fs.writeFileSync(path.join(revisions, "first.html"), html);
  for (const create of [false, true]) {
    assert.throws(() => open(create), error => error.status === 409 && /sketch revisions but no workspace\.json\. Restore workspace\.json/.test(error.message));
  }
  assert.deepEqual(fs.readdirSync(path.join(projectDir, "designs/example")), ["revisions"]);
  assert.equal(fs.readFileSync(path.join(revisions, "first.html"), "utf8"), html, "The leftover file is preserved for review.");
});
