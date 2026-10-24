"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { fork } = require("node:child_process");
const { once } = require("node:events");
const { WorkspaceStore } = require("../scripts/workspace-store.js");
const { WorkspaceState, validWorkspaceState } = require("../scripts/workspace-state.js");
const { FeedbackStore } = require("../scripts/feedback-store.js");

const scripts = path.resolve(__dirname, "../scripts");
const declaration = { version: 2, variants: [], targets: [], texts: [{ id: "heading", label: "Overskrift", value: "Velg tidspunkt" }] };
const html = '<h1><span data-vc-text="heading">Velg tidspunkt</span></h1><p>Original</p>';
const clone = value => JSON.parse(JSON.stringify(value));
const note = (screen, text) => ({ screen, kind: "point", text, anchor: { path: "h1:nth-of-type(1)", role: "heading",
  rect: { x: 0, y: 0, width: 100, height: 30 }, viewport: { width: 390, height: 844 } } });

function readOrNull(filename) {
  try { return fs.readFileSync(filename); }
  catch (error) { if (error.code === "ENOENT") return null; throw error; }
}

function open(projectDir, create = false) {
  const store = new WorkspaceStore({ projectDir, workspacePath: "designs/example", create, validateState: validWorkspaceState });
  try {
    const feedback = new FeedbackStore(fs.mkdtempSync(path.join(projectDir, "private-")), { canvas: true, persistence: store,
      initialWorkspace: { id: "a".repeat(24), title: "Timebestilling", version: 0, revisions: [] } });
    return { store, feedback, workspace: new WorkspaceState(feedback, store, { path: "designs/example", recovered: !create }) };
  } catch (error) { store.close(); throw error; }
}

function fixture(t) {
  const projectDir = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "workspace-interruption-")));
  t.after(() => fs.rmSync(projectDir, { recursive: true, force: true }));
  const room = open(projectDir, true);
  room.workspace.publish({ expectedScreen: "", filename: "initial.html", html, design: declaration });
  room.workspace.editorSave({ screen: room.workspace.current().screen, expectedRevision: room.feedback.state.revision,
    changes: [{ id: "text:heading", value: "Finn en tid som passer" }] });
  const screen = room.workspace.current().screen;
  room.feedback.create(note(screen, "Behold tydelig neste steg.")); room.feedback.submit({});
  room.feedback.create(note(screen, "Et usendt innspill."));
  room.store.close();
  // Establish a recovered baseline before interrupting a later publication.
  const recovered = open(projectDir);
  const state = clone(recovered.feedback.state), bytes = fs.readFileSync(recovered.store.filename);
  const sources = new Map(fs.readdirSync(recovered.store.revisionsDir).map(name => [name, fs.readFileSync(path.join(recovered.store.revisionsDir, name))]));
  recovered.store.close();
  return { projectDir, state, bytes, sources };
}

// Park an actual writer at an I/O boundary. The parent then kills the stopped
// process, so no catch/finally cleanup can simulate a successful recovery.
const worker = `"use strict";
const fs = require("node:fs"), path = require("node:path");
const { WorkspaceStore } = require(path.join(process.env.WORKSPACE_SCRIPTS, "workspace-store.js"));
const { WorkspaceState, validWorkspaceState } = require(path.join(process.env.WORKSPACE_SCRIPTS, "workspace-state.js"));
const { FeedbackStore } = require(path.join(process.env.WORKSPACE_SCRIPTS, "feedback-store.js"));
const [projectDir, phase, marker] = process.argv.slice(2);
const store = new WorkspaceStore({ projectDir, workspacePath: "designs/example", validateState: validWorkspaceState });
const feedback = new FeedbackStore(fs.mkdtempSync(path.join(projectDir, "private-")), { canvas: true, persistence: store });
const workspace = new WorkspaceState(feedback, store, { path: "designs/example", recovered: true });
const originalWrite = fs.writeFileSync, originalRename = fs.renameSync;
const park = () => { originalWrite(marker + ".tmp", phase); originalRename(marker + ".tmp", marker); process.kill(process.pid, "SIGSTOP"); throw new Error("The interrupted writer must not resume."); };
fs.writeFileSync = function (target, data, ...args) {
  const bytes = Buffer.isBuffer(data) ? data : Buffer.from(data);
  const partialHtml = phase === "partial-html" && bytes.toString().includes("New complete revision");
  const partialDesign = phase === "partial-design" && bytes.toString().startsWith('{"version":2,');
  const partialState = phase === "partial-state" && bytes.toString().startsWith('{"schemaVersion":');
  if (partialHtml || partialDesign || partialState) { originalWrite(target, bytes.subarray(0, Math.floor(bytes.length / 2)), ...args); park(); }
  return originalWrite(target, data, ...args);
};
fs.renameSync = function (source, target) {
  if (target === store.filename && phase === "before-rename") park();
  const result = originalRename(source, target);
  if (target === store.filename && phase === "after-rename") park();
  return result;
};
const current = workspace.current();
workspace.publish({ expectedScreen: current.screen, filename: "interrupted.html",
  html: current.content.replace("Original", "New complete revision"), design: current.design });
throw new Error("The expected interruption point was not reached.");
`;

async function interrupt(t, projectDir, phase) {
  const filename = path.join(projectDir, "worker.cjs"), marker = path.join(projectDir, "interrupted-at");
  fs.writeFileSync(filename, worker);
  const child = fork(filename, [projectDir, phase, marker], { env: { ...process.env, WORKSPACE_SCRIPTS: scripts }, stdio: ["ignore", "ignore", "pipe", "ipc"] });
  let stderr = ""; child.stderr.on("data", value => { stderr += value; });
  const exited = once(child, "exit");
  t.after(() => { if (child.exitCode === null && child.signalCode === null) child.kill("SIGKILL"); });
  const deadline = Date.now() + 8000;
  while (!fs.existsSync(marker) && child.exitCode === null && child.signalCode === null && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 10));
  assert.equal(fs.existsSync(marker), true, `Writer did not reach ${phase}: ${stderr}`);
  assert.equal(fs.readFileSync(marker, "utf8"), phase);
  child.kill("SIGKILL");
  const [code, signal] = await exited;
  assert.equal(code, null); assert.equal(signal, "SIGKILL");
}

for (const phase of ["partial-html", "partial-design", "partial-state", "before-rename", "after-rename"]) {
  test(`a real process killed at ${phase} preserves one complete publication boundary and all prior work`, { timeout: 12000 }, async t => {
    const seeded = fixture(t);
    await interrupt(t, seeded.projectDir, phase);
    const room = open(seeded.projectDir);
    t.after(() => room.store.close());
    const committed = phase === "after-rename";
    assert.equal(room.workspace.summary().version, seeded.state.workspace.version + Number(committed));
    for (const field of ["comments", "decisions", "submittedDecisions", "submissions", "canvas"]) assert.deepEqual(room.feedback.state[field], seeded.state[field], field);
    assert.deepEqual(room.feedback.state.workspace.holds, seeded.state.workspace.holds);
    for (const [name, bytes] of seeded.sources) assert.deepEqual(fs.readFileSync(path.join(room.store.revisionsDir, name)), bytes, name);
    if (!committed) assert.deepEqual(fs.readFileSync(room.store.filename), seeded.bytes, "An incomplete publication cannot rewrite the accepted room.");
    const current = room.workspace.current();
    assert.equal(current.content.includes("New complete revision"), committed);
    // Recovery must neither adopt orphaned files nor allow a reused filename to
    // replace them. A deliberate new publication can still advance the room.
    const orphan = path.join(room.store.revisionsDir, "interrupted.html"), orphanBytes = fs.readFileSync(orphan);
    assert.throws(() => room.workspace.publish({ expectedScreen: current.screen, filename: "interrupted.html", html: current.content, design: current.design }), error => error.status === 409);
    assert.deepEqual(fs.readFileSync(orphan), orphanBytes);
    room.workspace.publish({ expectedScreen: current.screen, filename: "continued.html", html: current.content, design: current.design });
    assert.equal(room.workspace.summary().version, seeded.state.workspace.version + Number(committed) + 1);
    assert.equal(room.feedback.state.submission, seeded.state.submission);
  });
}

for (const failure of ["missing older source", "changed older descriptor"]) {
  test(`recovery rejects ${failure} despite a valid latest revision and permits deliberate repair`, t => {
    const seeded = fixture(t), directory = path.join(seeded.projectDir, "designs/example");
    const name = failure === "missing older source" ? "initial.html" : "initial.design.json";
    const filename = path.join(directory, "revisions", name);
    const original = fs.readFileSync(filename);
    if (failure === "missing older source") fs.unlinkSync(filename);
    else fs.writeFileSync(filename, JSON.stringify({ ...declaration, texts: [{ ...declaration.texts[0], value: "Endret utenfor rommet" }] }));
    const damaged = readOrNull(filename);
    assert.throws(() => open(seeded.projectDir), error => error.status === 409 || error.code === "ENOENT");
    assert.deepEqual(fs.readFileSync(path.join(directory, "workspace.json")), seeded.bytes);
    assert.deepEqual(readOrNull(filename), damaged);
    fs.writeFileSync(filename, original);
    const restored = open(seeded.projectDir);
    t.after(() => restored.store.close());
    assert.equal(restored.workspace.summary().version, seeded.state.workspace.version);
    assert.deepEqual(restored.feedback.state, seeded.state);
  });
}
