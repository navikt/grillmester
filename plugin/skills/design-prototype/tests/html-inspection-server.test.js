"use strict";
const test = require("node:test"), assert = require("node:assert/strict"), fs = require("node:fs"), os = require("node:os"), path = require("node:path"), crypto = require("node:crypto");
const { fork } = require("node:child_process");
const CHANNEL = "visual-companion-canvas", SERVER = path.resolve(__dirname, "../scripts/server.js");
const sha = value => crypto.createHash("sha256").update(value).digest("hex");
async function fixture(t, saved = false) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "html-inspection-")));
  const css = path.join(root, "node_modules/@navikt/ds-css"); fs.mkdirSync(css, { recursive: true });
  fs.writeFileSync(path.join(css, "package.json"), JSON.stringify({ name: "@navikt/ds-css", version: "8.19.2" }));
  fs.mkdirSync(path.join(css, "dist")); fs.writeFileSync(path.join(css, "dist/index.min.css"), ".aksel-button{padding:20px}");
  const child = fork(SERVER, ["--project-dir", root, ...(saved ? ["--workspace-dir", "designs/demo", "--workspace-create", "true"] : [])], { execArgv: [], stdio: ["ignore", "pipe", "pipe", "ipc"] });
  let output = "", errors = "", id = 0; const pending = new Map();
  child.stdout.on("data", bytes => { output += bytes; }); child.stderr.on("data", bytes => { errors += bytes; });
  const ended = new Promise(resolve => child.once("exit", resolve));
  t.after(async () => { if (child.exitCode === null) child.kill("SIGTERM"); await ended; fs.rmSync(root, { recursive: true, force: true }); });
  const ready = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Backend deadline: " + errors)), 6000);
    child.once("error", reject);
    child.on("message", message => {
      if (message.channel !== CHANNEL) return;
      if (message.event === "ready") { clearTimeout(timer); resolve(message.info); }
      else if (pending.has(message.id)) { const complete = pending.get(message.id); pending.delete(message.id); complete(message); }
    });
  });
  const rpc = (method, params = {}) => new Promise((resolve, reject) => {
    const requestId = ++id, timer = setTimeout(() => reject(new Error("IPC deadline")), 6000);
    pending.set(requestId, value => { clearTimeout(timer); value.ok ? resolve(value.result) : reject(Object.assign(new Error(value.error), { status: value.status })); });
    child.send({ channel: CHANNEL, version: 1, id: requestId, method, params });
  });
  return { rpc, root, ready, logs: () => output + errors };
}
const design = { version: 1, variants: [], targets: [{ key: "meeting", variant: "", label: "Møte", controls: [{ id: "stage", label: "Steg", type: "select", initial: "start", options: [{ value: "start", label: "Start" }, { value: "next", label: "Neste" }] }] }] };
const html = '<style>[data-vc-setting-stage="next"] h1{color:blue}</style><section data-vc-key="meeting"><h1>Forbered møtet</h1><button type="button" data-vc-control="stage" data-vc-value="next" onclick="window.bad=1">Neste</button></section><script>window.bad=1</script><iframe src="https://outside.invalid"></iframe>';
test("published HTML inspection freezes production rendering and never exposes workshop authority", async t => {
  const f = await fixture(t), state = await f.rpc("publishRevision", { expectedScreen: "", filename: "first.html", html, design });
  const before = await f.rpc("readState"), control = new URL(f.ready.url);
  await assert.rejects(f.rpc("openInspection", { expectedScreen: "b".repeat(32) }), error => error.status === 409);
  await assert.rejects(f.rpc("openInspection", { expectedScreen: state.screen, url: "http://outside.invalid" }), error => error.status === 400);
  const inspection = await f.rpc("openInspection", { expectedScreen: state.screen });
  assert.notEqual(new URL(inspection.url).origin, control.origin); assert.equal(inspection.screen, state.screen);
  assert.equal(inspection.filename, "first.html"); assert.equal(inspection.sourceHash, sha(html));
  assert.equal(inspection.designHash, sha(JSON.stringify(design))); assert.equal(inspection.styles.version, "8.19.2");
  assert(inspection.expiresAt > Date.now()); assert(inspection.expiresAt < Date.now() + 601000);
  const response = await fetch(inspection.url), rendered = await response.text();
  assert.equal(response.status, 200); assert.equal(sha(rendered), inspection.frameHash);
  assert(!rendered.includes(control.searchParams.get("token"))); assert(!rendered.includes(control.origin));
  assert.match(rendered, /__grillmesterVisualCompanionInspection=true/); assert.match(rendered, /__grillmesterInitializeWorkshop/);
  assert.equal(/window\.bad=1|onclick="|<iframe|__grillmesterInitializeEditor = \(/.test(rendered), false, "Untrusted code and editor implementation are omitted.");
  assert.match(rendered, /\.aksel-button\{padding:20px\}/); assert.equal(f.logs().includes(inspection.url), false);
  assert.deepEqual(await f.rpc("readState"), before);
  const next = await f.rpc("publishRevision", { expectedScreen: state.screen, filename: "second.html", html: "<h1>Oppdatert</h1>" });
  await assert.rejects(fetch(inspection.url));
  await f.rpc("closeView");
  const closedChild = await f.rpc("openInspection", { expectedScreen: next.screen });
  assert.equal((await fetch(closedChild.url)).status, 200, "Owned proposals can be inspected without selecting/opening their canvas.");
  await f.rpc("closeView"); await assert.rejects(fetch(closedChild.url));
  const pending = f.rpc("openInspection", { expectedScreen: next.screen }), close = f.rpc("closeView");
  const result = await pending.then(value => ({ value }), error => ({ error })); await close;
  if (result.value) await assert.rejects(fetch(result.value.url)); else assert.equal(result.error.status, 410);
});
test("saved inspection reports its revision and stays immutable if a source file changes", async t => {
  const f = await fixture(t, true), state = await f.rpc("publishRevision", { expectedScreen: "", filename: "saved.html", html: "<h1>Saved exact</h1>", design });
  const opened = await f.rpc("openInspection", { expectedScreen: state.screen }); assert.equal(opened.revisionId, 1);
  const before = await (await fetch(opened.url)).text(), workspace = JSON.parse(fs.readFileSync(path.join(f.root, "designs/demo/workspace.json")));
  assert.equal(opened.designHash, workspace.workspace.revisions[0].designHash);
  fs.writeFileSync(path.join(f.root, "designs/demo/revisions/saved.html"), "<h1>Changed outside</h1>");
  assert.equal(await (await fetch(opened.url)).text(), before, "GET never rereads files or switches the observed version.");
  await assert.rejects(f.rpc("openInspection", { expectedScreen: state.screen }), error => error.status === 409);
  await f.rpc("closeInspection", { inspectionId: opened.inspectionId }); await assert.rejects(fetch(opened.url));
});
test("a committed browser restore revokes inspection before acknowledging the mutation", async t => {
  const f = await fixture(t, true), first = await f.rpc("publishRevision", { expectedScreen: "", filename: "first.html", html: "<h1>First</h1>" });
  const second = await f.rpc("publishRevision", { expectedScreen: first.screen, filename: "second.html", html: "<h1>Second</h1>" });
  const opened = await f.rpc("openInspection", { expectedScreen: second.screen }), target = new URL(f.ready.url);
  target.pathname = "/workspace/restore";
  const response = await fetch(target, { method: "POST", headers: { Origin: target.origin, "Content-Type": "application/json", "X-Feedback-Mutation": "c".repeat(32) }, body: JSON.stringify({ revisionId: 1, expectedRevision: second.revision }) });
  assert.equal(response.status, 200); await assert.rejects(fetch(opened.url));
  assert.equal((await f.rpc("readState")).workspace.version, 3);
});
