"use strict";
const test = require("node:test"), assert = require("node:assert/strict"), fs = require("node:fs"), os = require("node:os"), path = require("node:path");
const { ApplicationWorkspace, validApplicationWorkspaceState } = require("../scripts/application-workspace.js");
const { ApplicationProposals } = require("../scripts/application-proposals.js");
const { FeedbackError } = require("../scripts/feedback-store.js");
function fixture(t, saved = false) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "proposal-registry-"))), projectDir = path.join(root, "project"), stateDir = path.join(root, "state");
  fs.mkdirSync(projectDir); fs.mkdirSync(stateDir, { mode: 0o700 });
  const workspace = new ApplicationWorkspace({ projectDir, stateDir, application: { name: "Møte", url: "http://localhost:32100/demo" }, ...(saved ? { workspacePath: "designs/app", create: true } : {}) });
  const state = { screen: "", revision: 0, workspace: { id: "a".repeat(24), version: 0 } }, calls = [], deliveries = [];
  let startCount = 0, observer;
  const backend = { closeView: async () => { calls.push("close"); }, retire: async () => { calls.push("retire"); }, readState: async () => structuredClone(state),
    publishRevision: async input => { calls.push("publish"); assert.equal(input.expectedScreen, state.screen); state.screen = "b".repeat(32); state.revision++; if (state.workspace) state.workspace.version++; return structuredClone(state); },
    saveWorkspace: async input => { calls.push("saveWorkspace"); if (!state.workspace) { state.workspace = { id: input.workspaceId, path: input.workspacePath, title: input.title, version: 1 }; state.revision++; } return structuredClone(state); },
    readSubmission: async input => ({ submission: input.submission, origin: "proposal" }),
    listHistory: async input => { calls.push("listHistory"); return { revisions: [state.workspace.version] }; },
    readRevision: async input => { calls.push("readRevision"); return { revisionId: input.revisionId, content: "<h1>Forbered møtet</h1>" }; },
    restoreRevision: async input => { calls.push("restoreRevision"); return structuredClone(state); },
    openView: async ({ embedding }) => { calls.push("open"); return { url: "http://127.0.0.1:32101/embedded/private", origin: "http://127.0.0.1:32101", activationKey: "c".repeat(64), leaseId: embedding.leaseId }; } };
  const registry = new ApplicationProposals({ workspace, projectDir, backendFactory: async options => { startCount++; observer = options.onSubmitted; if (!options.workspacePath) delete state.workspace; return backend; }, onSubmitted: (...args) => deliveries.push(args) });
  t.after(async () => { await registry.close(); workspace.close(); fs.rmSync(root, { recursive: true, force: true }); });
  return { registry, workspace, calls, deliveries, state, projectDir, root, backend, get starts() { return startCount; }, send: submission => observer(submission) };
}
const initial = { source: "conversation", title: "Et tydelig forslag", filename: "proposal.html", html: "<main><h1>Forbered møtet</h1></main>" };
test("conversation-first design creates no fake feedback and one retry-safe proposal", async t => {
  const f = fixture(t), first = await f.registry.publish(initial), retry = await f.registry.publish(initial);
  assert.equal(first.id, retry.id); assert.equal(first.source, "conversation"); assert.equal(first.sourceSubmission, undefined); assert.equal(f.workspace.feedback.state.submission, 0);
  assert.equal(first.storage, "temporary"); assert.equal(first.revisionId, undefined);
  assert.equal(f.starts, 1); assert.equal(f.calls.filter(value => value === "publish").length, 1);
  await assert.rejects(f.registry.publish({ ...initial, filename: "other.html" }), error => error.status === 409);
  assert.deepEqual(fs.readdirSync(f.projectDir), [], "temporary work does not write project files");
});
test("temporary proposal history has an authored diagnostic before child IPC, even in a saved app room", async t => {
  for (const savedApp of [false, true]) {
    const f = fixture(t, savedApp), first = await f.registry.publish(initial), before = JSON.stringify(f.workspace.feedback.state);
    const attempts = [["listHistory", {}], ["readRevision", { revisionId: 1, part: "html" }], ["restoreRevision", { revisionId: 1, expectedRevision: 1 }]];
    for (const [method, params] of attempts) await assert.rejects(f.registry.action(method, { proposalId: first.id, ...params }), error => {
      assert(error instanceof FeedbackError, "The app server must retain this authored diagnostic.");
      assert.equal(error.status, 409); assert.match(error.message, /midlertidig.*ingen lagret versjonshistorikk/);
      assert.doesNotMatch(error.message, /opptatt|endret utenfra|\/private|\/tmp/); return true;
    });
    assert.equal(f.calls.some(method => attempts.some(([attempt]) => attempt === method)), false, "No history command reaches the child.");
    assert.equal((await f.registry.action("readState", { proposalId: first.id })).screen, first.screen);
    assert.equal(JSON.stringify(f.workspace.feedback.state), before); assert.equal(f.workspace.feedback.state.workspace?.sketch, undefined);
    await assert.rejects(f.registry.action("listHistory", { proposalId: "f".repeat(24) }), error => error.status === 404);
  }
});
test("saved proposal history still routes to its child without changing the app room", async t => {
  const f = fixture(t, true), first = await f.registry.publish({ ...initial, workspacePath: "designs/proposal", create: true });
  const before = JSON.stringify(f.workspace.feedback.state);
  assert.equal(first.storage, "project"); assert.equal(first.revisionId, 1);
  assert.deepEqual(await f.registry.action("listHistory", { proposalId: first.id }), { revisions: [1] });
  assert.equal((await f.registry.action("readRevision", { proposalId: first.id, revisionId: 1, part: "html" })).revisionId, 1);
  assert.equal((await f.registry.action("restoreRevision", { proposalId: first.id, revisionId: 1, expectedRevision: 1 })).screen, first.screen);
  assert.deepEqual(f.calls.filter(method => ["listHistory", "readRevision", "restoreRevision"].includes(method)), ["listHistory", "readRevision", "restoreRevision"]);
  assert.equal(JSON.stringify(f.workspace.feedback.state), before);
});
test("invalid sources and controls fail before a child or saved relationship is created", async t => {
  const f = fixture(t, true);
  for (const input of [{ ...initial, sourceSubmission: 1 }, { ...initial, source: "app-feedback", sourceSubmission: 1, commentIds: ["a".repeat(24)] },
    { ...initial, design: { version: 500 } }, { ...initial, workspacePath: "../other", create: true }]) await assert.rejects(f.registry.publish(input), error => [400, 404].includes(error.status));
  assert.equal(f.starts, 0); assert.equal(f.workspace.feedback.state.workspace.sketch, undefined);
});
test("saved proposal relationship is portable, typed and contains no transport capabilities", async t => {
  const f = fixture(t, true), first = await f.registry.publish({ ...initial, workspacePath: "designs/proposal", create: true });
  const saved = f.workspace.feedback.state;
  assert(validApplicationWorkspaceState(saved)); assert.equal(saved.workspace.sketch.workspacePath, "designs/proposal"); assert.equal(saved.workspace.sketch.workspaceId, "a".repeat(24));
  assert.equal(saved.workspace.sketch.id, first.id); assert(!/token|activationKey|leaseId|http:/.test(JSON.stringify(saved.workspace.sketch)));
  for (const mutation of [value => { value.workspace.sketch.workspacePath = "../other"; }, value => { value.workspace.sketch.workspaceId = ["a".repeat(24)]; },
    value => { value.workspace.sketch.sourceSubmission = 1; }, value => { value.workspace.sketch.origin = "http://localhost:9000"; }]) {
    const changed = structuredClone(saved); mutation(changed); assert.equal(validApplicationWorkspaceState(changed), false);
  }
});
test("proposal route is explicit and display selection cannot redirect an action or delivery", async t => {
  const f = fixture(t), first = await f.registry.publish(initial); f.registry.select(first.id);
  assert.deepEqual(await f.registry.action("readSubmission", { proposalId: first.id, submission: 1 }), { submission: 1, origin: "proposal" });
  await assert.rejects(f.registry.action("readSubmission", { proposalId: "f".repeat(24), submission: 1 }), error => error.status === 404);
  await assert.rejects(f.registry.action("retire", { proposalId: first.id }), error => error.status === 400);
  f.send(1); assert.deepEqual(f.deliveries, [[1, first.id]]);
  const embedding = { parentOrigin: "http://127.0.0.1:32102", leaseId: "d".repeat(32) };
  assert.deepEqual(await f.registry.openView(first.id, embedding), await f.registry.openView(first.id, embedding)); assert.equal(f.calls.filter(value => value === "open").length, 1);
  await f.registry.closeViews(); await f.registry.openView(first.id, { ...embedding, leaseId: "e".repeat(32) }); assert.equal(f.calls.filter(value => value === "open").length, 2);
});
test("later save keeps the same proposal and backend, links only after commit, and retries once", async t => {
  const f = fixture(t, true), first = await f.registry.publish(initial);
  const input = { proposalId: first.id, workspacePath: "designs/proposal", expectedScreen: first.screen, expectedRevision: f.state.revision };
  const binding = structuredClone(f.registry.entry.binding);
  const saved = await f.registry.action("saveProposal", input), calls = f.calls.length;
  assert.equal(saved.id, first.id); assert.equal(saved.screen, first.screen); assert.equal(saved.storage, "project"); assert.equal(f.starts, 1);
  assert.equal(f.workspace.feedback.state.workspace.pendingSketchSave, undefined);
  assert.deepEqual(f.workspace.feedback.state.workspace.sketch, { ...binding, workspacePath: input.workspacePath, workspaceId: f.state.workspace.id });
  assert.deepEqual(await f.registry.action("saveProposal", input), saved); assert.equal(f.calls.length, calls);
  assert.equal(f.deliveries.length, 0); assert.equal(f.calls.filter(value => value === "close").length, 1, "Saving does not close/reopen the existing child.");
  await assert.rejects(f.registry.action("saveProposal", { ...input, workspacePath: "designs/other" }), error => error.status === 409);
});
test("temporary apps and stale guards fail before any save intent or child write", async t => {
  for (const savedApp of [false, true]) {
    const f = fixture(t, savedApp), first = await f.registry.publish(initial), before = JSON.stringify(f.workspace.feedback.state);
    const input = { proposalId: first.id, workspacePath: "designs/proposal", expectedScreen: first.screen, expectedRevision: f.state.revision };
    for (const value of [input, { ...input, expectedScreen: "f".repeat(32) }, { ...input, expectedRevision: input.expectedRevision + 1 }].slice(savedApp ? 1 : 0)) {
      await assert.rejects(f.registry.action("saveProposal", value), error => error.status === 409);
      assert.equal(JSON.stringify(f.workspace.feedback.state), before);
    }
    assert(!f.calls.includes("saveWorkspace"));
  }
});
test("definite precommit rejection preserves temporary work and permits a new guarded attempt", async t => {
  const f = fixture(t, true), first = await f.registry.publish(initial), original = f.backend.saveWorkspace;
  f.backend.saveWorkspace = async () => { throw Object.assign(new Error("/private/untrusted/detail"), { status: 409 }); };
  const input = { proposalId: first.id, workspacePath: "designs/proposal", expectedScreen: first.screen, expectedRevision: f.state.revision };
  await assert.rejects(f.registry.action("saveProposal", input), error => error.status === 409 && !error.message.includes("/private"));
  assert.equal(f.workspace.feedback.state.workspace.pendingSketchSave, undefined); assert.equal(f.state.workspace, undefined);
  assert.equal((await f.registry.action("readState", { proposalId: first.id })).screen, first.screen);
  f.backend.saveWorkspace = original;
  assert.equal((await f.registry.action("saveProposal", input)).storage, "project");
});
test("child commit with lost reply retains an exact intent and never creates a second proposal", async t => {
  const f = fixture(t, true), first = await f.registry.publish(initial), original = f.backend.saveWorkspace;
  let firstCall = true;
  f.backend.saveWorkspace = async input => { const value = await original(input); if (firstCall) { firstCall = false; throw Object.assign(new Error("Unconfirmed"), { status: 503 }); } return value; };
  const input = { proposalId: first.id, workspacePath: "designs/proposal", expectedScreen: first.screen, expectedRevision: f.state.revision };
  await assert.rejects(f.registry.action("saveProposal", input), error => error.status === 503);
  const pending = structuredClone(f.workspace.feedback.state.workspace.pendingSketchSave), identity = f.state.workspace.id;
  assert.equal(pending.binding.workspaceId, identity); assert.equal(f.workspace.feedback.state.workspace.sketch, undefined);
  assert.deepEqual((await f.registry.summary())[0].pendingSave, { workspacePath: input.workspacePath, expectedScreen: input.expectedScreen, expectedRevision: input.expectedRevision });
  await assert.rejects(f.registry.action("saveProposal", { ...input, expectedRevision: input.expectedRevision + 1 }), error => error.status === 409);
  assert.equal((await f.registry.action("saveProposal", input)).id, first.id); assert.equal(f.state.workspace.id, identity);
  assert.equal(f.starts, 1); assert.equal(f.calls.filter(value => value === "publish").length, 1); assert.equal(f.deliveries.length, 0);
});

test("a committed parent durability failure stays unconfirmed until an exact explicit retry", async t => {
  const f = fixture(t, true), first = await f.registry.publish(initial), finish = f.workspace.finishSketchSave.bind(f.workspace);
  f.workspace.finishSketchSave = input => { finish(input); throw Object.assign(new Error("Controlled parent durability failure"), { committed: true }); };
  const input = { proposalId: first.id, workspacePath: "designs/proposal", expectedScreen: first.screen, expectedRevision: f.state.revision };
  await assert.rejects(f.registry.action("saveProposal", input), error => error.status === 503);
  const savedRevision = f.workspace.feedback.state.revision;
  assert(f.workspace.feedback.state.workspace.sketch); assert.equal(f.workspace.feedback.state.workspace.pendingSketchSave, undefined);
  const unconfirmed = (await f.registry.summary())[0]; assert.equal(unconfirmed.storage, "temporary"); assert.equal(unconfirmed.pendingSave.expectedRevision, input.expectedRevision);
  await assert.rejects(f.registry.action("saveProposal", { ...input, expectedRevision: input.expectedRevision + 1 }), error => error.status === 409);
  let writes = 0; const persist = f.workspace.store.persist.bind(f.workspace.store);
  f.workspace.store.persist = state => { writes++; persist(state); };
  const confirmed = await f.registry.action("saveProposal", input);
  assert.equal(writes, 1); assert.equal(confirmed.storage, "project"); assert.equal(confirmed.pendingSave, undefined);
  assert.equal(f.workspace.feedback.state.revision, savedRevision); assert.equal(f.calls.filter(value => value === "saveWorkspace").length, 1);
  await f.registry.action("saveProposal", input); assert.equal(writes, 1); assert.deepEqual(f.deliveries, []);
});
test("parent binding failure is recoverable after reopen without automatically adopting or creating content", async t => {
  const f = fixture(t, true), first = await f.registry.publish(initial);
  const input = { proposalId: first.id, workspacePath: "designs/proposal", expectedScreen: first.screen, expectedRevision: f.state.revision };
  f.workspace.finishSketchSave = () => { throw new Error("Unconfirmed parent commit"); };
  await assert.rejects(f.registry.action("saveProposal", input), error => error.status === 503);
  const pending = structuredClone(f.workspace.feedback.state.workspace.pendingSketchSave);
  await f.registry.close(); f.workspace.close();
  const room = new ApplicationWorkspace({ projectDir: f.projectDir, workspacePath: "designs/app", stateDir: fs.mkdtempSync(path.join(f.root, "reopened-")), application: { name: "Møte", url: "http://localhost:32100/demo" } });
  let options;
  const registry = new ApplicationProposals({ workspace: room, projectDir: f.projectDir, backendFactory: async value => { options = value; return f.backend; } });
  t.after(async () => { await registry.close(); room.close(); });
  const before = fs.readFileSync(room.store.filename);
  assert.equal((await registry.summary())[0].id, first.id); assert.deepEqual(fs.readFileSync(room.store.filename), before);
  assert.equal(options.workspacePath, input.workspacePath); assert.equal(options.create, undefined);
  assert.equal((await registry.action("saveProposal", input)).storage, "project");
  assert.deepEqual(room.feedback.state.workspace.sketch, pending.binding); assert.equal(room.feedback.state.workspace.pendingSketchSave, undefined);
});

test("an unavailable pending target is never recreated, rebound or exposed as a private backend error", async t => {
  const f = fixture(t, true), first = await f.registry.publish(initial);
  const input = { proposalId: first.id, workspacePath: "designs/proposal", expectedScreen: first.screen, expectedRevision: f.state.revision };
  f.workspace.beginSketchSave({ binding: { ...f.registry.entry.binding, workspacePath: input.workspacePath, workspaceId: "d".repeat(24) },
    expectedScreen: input.expectedScreen, expectedRevision: input.expectedRevision });
  await f.registry.close();
  const before = fs.readFileSync(f.workspace.store.filename), attempts = [];
  const registry = new ApplicationProposals({ workspace: f.workspace, projectDir: f.projectDir, backendFactory: async options => {
    attempts.push(options); throw Object.assign(new Error("/private/unavailable/target"), { status: 404 });
  } });
  try {
    const state = (await registry.summary())[0]; assert.equal(state.available, false); assert(state.pendingSave);
    await assert.rejects(registry.action("saveProposal", input), error => error instanceof FeedbackError && error.status === 409 &&
      /Ingen erstatning er opprettet/.test(error.message) && !error.message.includes("/private"));
    assert.equal(attempts.length, 1); assert.equal(attempts[0].create, undefined); assert.equal(attempts[0].workspacePath, input.workspacePath);
    assert.deepEqual(fs.readFileSync(f.workspace.store.filename), before); assert.equal(fs.existsSync(path.join(f.projectDir, input.workspacePath)), false);
  } finally { await registry.close(); }
});
