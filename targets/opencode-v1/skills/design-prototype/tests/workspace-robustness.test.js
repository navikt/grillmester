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

function open(projectDir, create = false) {
  const store = new WorkspaceStore({ projectDir, workspacePath: "designs/example", create, validateState: validWorkspaceState });
  try {
    const feedback = new FeedbackStore(fs.mkdtempSync(path.join(projectDir, "private-")), { canvas: true, persistence: store,
      initialWorkspace: { id: "b".repeat(24), title: "Robusthet", version: 0, revisions: [] } });
    return { store, feedback, workspace: new WorkspaceState(feedback, store, { path: "designs/example", recovered: !create }) };
  } catch (error) { store.close(); throw error; }
}

function seeded(t) {
  const projectDir = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "workspace-robustness-")));
  t.after(() => fs.rmSync(projectDir, { recursive: true, force: true }));
  const room = open(projectDir, true);
  room.workspace.publish({ expectedScreen: "", filename: "first.html", html, design: declaration });
  room.workspace.publish({ expectedScreen: room.workspace.current().screen, filename: "second.html", html, design: { ...declaration, texts: [{ ...declaration.texts[0], value: "Finn en tid" }] } });
  room.store.close();
  return { projectDir, revisions: path.join(projectDir, "designs/example/revisions") };
}

test("operating-system and editor files in revisions/ neither block opening nor saving", t => {
  const { projectDir, revisions } = seeded(t);
  for (const name of [".DS_Store", "._first.html", ".first.html.swp", "first.html~", "README.md"]) fs.writeFileSync(path.join(revisions, name), "x");
  const room = open(projectDir);
  t.after(() => room.store.close());
  room.workspace.publish({ expectedScreen: room.workspace.current().screen, filename: "third.html", html, design: declaration });
  assert.equal(room.workspace.summary().version, 3);
});

test("a re-indented descriptor with the same value keeps its recorded hash", t => {
  const { projectDir, revisions } = seeded(t);
  for (const name of ["first.design.json", "second.design.json"]) {
    const filename = path.join(revisions, name);
    fs.writeFileSync(filename, `${JSON.stringify(JSON.parse(fs.readFileSync(filename, "utf8")), null, 2)}\n`);
  }
  const room = open(projectDir);
  t.after(() => room.store.close());
  assert.equal(room.workspace.read({ revisionId: 1, part: "design" }).revisionId, 1);
  assert.equal(room.workspace.summary().version, 2);
});

test("a changed descriptor value is still rejected and named", t => {
  const { projectDir, revisions } = seeded(t);
  fs.writeFileSync(path.join(revisions, "second.design.json"), `${JSON.stringify({ ...declaration, texts: [{ ...declaration.texts[0], value: "Endret" }] })}\n`);
  assert.throws(() => open(projectDir), error => error.status === 409 && /second\.design\.json/.test(error.message));
});

test("a descriptor that is no longer JSON is named, for example after a merge conflict", t => {
  const { projectDir, revisions } = seeded(t);
  const filename = path.join(revisions, "second.design.json");
  fs.writeFileSync(filename, `<<<<<<< HEAD\n${fs.readFileSync(filename, "utf8")}=======\n>>>>>>> other\n`);
  assert.throws(() => open(projectDir), error => error.status === 409 && error.expose === true && /second\.design\.json is not valid JSON/.test(error.message));
});

test("one extra newline in an older revision leaves the room open and that version unavailable", t => {
  const { projectDir, revisions } = seeded(t);
  const filename = path.join(revisions, "first.html");
  fs.appendFileSync(filename, "\n");
  const damaged = fs.readFileSync(filename);
  const room = open(projectDir);
  t.after(() => room.store.close());
  assert.equal(room.workspace.current().filename, "second.html");
  const named = error => error.status === 409 && /first\.html no longer matches its saved hash/.test(error.message);
  assert.throws(() => room.workspace.read({ revisionId: 1, part: "html" }), named);
  assert.throws(() => room.workspace.restore({ revisionId: 1, expectedRevision: room.feedback.state.revision }), named);
  assert.equal(room.workspace.summary().version, 2);
  assert.deepEqual(fs.readFileSync(filename), damaged, "A damaged file is never repaired or rewritten.");
});

test("files that can never be revisions do not count towards the listing limit", t => {
  const { projectDir, revisions } = seeded(t);
  for (let index = 0; index < 250; index += 1) fs.writeFileSync(path.join(revisions, `._first-${index}.html`), "x");
  const room = open(projectDir);
  t.after(() => room.store.close());
  assert.equal(room.workspace.summary().version, 2);
});

test("operating-system dotfiles do not make a new room directory count as used", t => {
  const projectDir = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "workspace-robustness-")));
  t.after(() => fs.rmSync(projectDir, { recursive: true, force: true }));
  fs.mkdirSync(path.join(projectDir, "designs/example/revisions"), { recursive: true });
  for (const name of ["designs/example/.DS_Store", "designs/example/revisions/.DS_Store"]) fs.writeFileSync(path.join(projectDir, name), "x");
  const room = open(projectDir, true);
  t.after(() => room.store.close());
  assert.equal(room.workspace.summary().version, 0);
  fs.writeFileSync(path.join(projectDir, "designs/example/revisions/notes.txt"), "x");
  room.store.close();
  fs.rmSync(path.join(projectDir, "designs/example/workspace.json"));
  assert.throws(() => open(projectDir, true), error => error.status === 409 && /requires an empty/.test(error.message));
});
