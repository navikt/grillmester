"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { Readable, PassThrough } = require("node:stream");
const { createConnectionState, INVITATION_MS, MAX_CANDIDATES } = require("../scripts/application-connection-state.js");
const { fork } = require("node:child_process");
const http = require("node:http");
const { ApplicationWorkspace } = require("../scripts/application-workspace.js");
const { createApplicationServer, createPreviewStatus, createApplicationRequestHandler, authorizedRequest, renderShell, validEnvelope, parseArguments } = require("../scripts/application-server.js");

const application = { name: "Møtevalg", url: "http://localhost:3000/start?view=kort" };
const authority = { origin: "http://127.0.0.1:34567", token: "a".repeat(64), openPath: "/open/" + "b".repeat(64), html: "<!doctype html><title>Arbeid</title>", csp: "default-src 'none'" };
const rejection = status => error => error.status === status;
// The native localhost origin uses the selected loopback socket in this
// Node harness; preserve Host so production authority checks are unchanged.
function fetchPreview(value, options = {}) {
  const url = new URL(value);
  return new Promise((resolve, reject) => {
    const req = http.get({ hostname: "127.0.0.1", port: url.port, path: url.pathname + url.search,
      headers: { Host: url.host, ...options.headers } }, res => {
      const chunks = []; res.on("data", chunk => chunks.push(chunk)); res.once("error", reject);
      res.once("end", () => resolve({ status: res.statusCode, headers: new Headers(res.headers), text: async () => Buffer.concat(chunks).toString("utf8") }));
    }); req.once("error", reject);
  });
}
async function externalView(panelUrl) {
  const html = await (await fetch(panelUrl)).text();
  const config = JSON.parse(/window\.__designApplication = (.*);/.exec(html)[1]);
  assert.equal(config.activationRequired, true); assert.equal(config.previewUrl, undefined);
  const origin = new URL(panelUrl).origin;
  const response = await fetch(origin + "/renderer/activate", { method: "POST", headers: { Origin: origin, "Content-Type": "application/json", "X-Designverksted-Token": config.token }, body: "{}" });
  assert.equal(response.status, 200);
  return { ...config, ...await response.json() };
}

function fixture(t) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "application-server-")));
  const projectDir = path.join(root, "project"); fs.mkdirSync(projectDir, { mode: 0o700 });
  const stateDir = fs.mkdtempSync(path.join(root, "state-")), cleanups = [];
  t.after(async () => { for (const cleanup of cleanups.reverse()) await cleanup(); fs.rmSync(root, { recursive: true, force: true }); });
  const room = () => {
    const value = new ApplicationWorkspace({ projectDir, workspacePath: "designs/meeting", create: true, stateDir, application, checkpoint: "c".repeat(64) });
    cleanups.push(() => value.close()); return value;
  };
  const server = options => {
    const value = createApplicationServer({ projectDir, workspacePath: "designs/meeting", application, ...options });
    cleanups.push(() => value.close()); return value;
  };
  return { root, projectDir, room, server, cleanups };
}
function note(room) {
  return { screen: room.current().screen, kind: "point", text: "Prøv radioknapper her.",
    anchor: { path: "button:nth-of-type(1)", role: "button", rect: { x: 12, y: 40, width: 100, height: 40 }, viewport: { width: 375, height: 812 } },
    applicationContext: { route: room.current().source.route, target: { tag: "button", role: "button", name: "Neste", text: "Neste", path: "button:nth-of-type(1)" }, viewport: { width: 375, height: 812, scrollX: 0, scrollY: 0 } } };
}
function requestShape(options = {}) {
  const headers = { host: "127.0.0.1:34567", "x-designverksted-token": authority.token, ...(options.method === "POST" ? { origin: authority.origin, "content-type": "application/json", "x-feedback-mutation": "d".repeat(32) } : {}), ...options.headers };
  for (const key of Object.keys(headers)) if (headers[key] === undefined) delete headers[key];
  return { method: options.method || "GET", url: options.url || "/state", headers,
    rawHeaders: Object.entries(headers).flat(), socket: { remoteAddress: "127.0.0.1" }, ...options, headers };
}
async function request(handler, options = {}) {
  const shape = requestShape(options), bytes = options.rawBody ?? Buffer.from(JSON.stringify(options.body ?? {}));
  const req = Object.assign(Readable.from(shape.method === "POST" ? [bytes] : []), shape);
  const response = { statusCode: null, headers: {}, setHeader(name, value) { this.headers[name.toLowerCase()] = value; }, end(value) { this.text = value; } };
  await handler(req, response);
  return { status: response.statusCode, text: response.text, headers: response.headers,
    body: response.headers["content-type"]?.startsWith("application/json") ? JSON.parse(response.text) : null };
}

test("control authority requires exact host, loopback peer, shell origin and token without cookie fallbacks", () => {
  assert(authorizedRequest(requestShape(), authority));
  assert(authorizedRequest(requestShape({ method: "POST" }), authority));
  for (const options of [
    { socket: { remoteAddress: "192.0.2.10" } }, { headers: { host: "localhost:34567" } },
    { headers: { host: "127.0.0.1:34568" } }, { headers: { "x-designverksted-token": undefined, cookie: "token=" + authority.token } },
    { headers: { "x-designverksted-token": "a".repeat(63) } }, { headers: { "x-designverksted-token": "c".repeat(64) } },
    { headers: { origin: "http://127.0.0.1:45678" } }, { method: "POST", headers: { origin: undefined } },
    { method: "POST", headers: { origin: "null" } },
    { rawHeaders: ["Host", "127.0.0.1:34567", "Host", "127.0.0.1:34567"] },
    { headers: { origin: authority.origin }, rawHeaders: ["Origin", authority.origin, "Origin", authority.origin] },
  ]) assert.equal(authorizedRequest(requestShape(options), authority), false, JSON.stringify(options));
});

test("only the exact private bootstrap serves a shell; no API accepts its path as authentication", async t => {
  const room = fixture(t).room(), handler = createApplicationRequestHandler({ workspace: room, authority });
  const result = await request(handler, { url: authority.openPath, headers: { "x-designverksted-token": undefined } });
  assert.equal(result.status, 200); assert.equal(result.text, authority.html);
  assert.equal(result.headers["set-cookie"], undefined); assert.equal(result.headers["cache-control"], "no-store");
  assert.equal(result.headers["referrer-policy"], "no-referrer");
  for (const url of ["/state", "/history", authority.openPath + "?next=/state", authority.openPath + "/"]) {
    assert.equal((await request(handler, { url, headers: { "x-designverksted-token": undefined } })).status, 403);
  }
  const denied = await request(handler, { method: "OPTIONS", headers: { origin: "http://127.0.0.1:45678" } });
  assert.equal(denied.status, 403); assert.equal(denied.headers["access-control-allow-origin"], undefined);
});

test("full HTTP state and route registration retain explicit application evidence and do not create feedback", async t => {
  const room = fixture(t).room(), handler = createApplicationRequestHandler({ workspace: room, authority });
  const first = await request(handler); assert.equal(first.status, 200); assert.deepEqual(first.body.comments, []);
  assert.equal(first.body.workspace.mode, "feedback"); assert.equal(first.body.application.snapshotAvailable, undefined);
  const moved = await request(handler, { method: "POST", url: "/view", headers: { "x-feedback-mutation": undefined }, body: { route: "/next?q=to%20ord", expectedCheckpoint: first.body.application.checkpoint } });
  assert.equal(moved.status, 200); assert.equal(moved.body.application.route, "/next?q=to+ord");
  assert.notEqual(first.body.screen, moved.body.screen); assert.equal(moved.body.comments.length, 0);
  assert.equal(moved.body.screens.length, 0); assert.equal(moved.body.revision, first.body.revision);
  const captured = await request(handler, { method: "POST", url: "/view", body: { route: "/next?q=to+ord", expectedCheckpoint: first.body.application.checkpoint, capture: true } });
  assert.equal(captured.status, 200); assert.equal(captured.body.screens.length, 0); assert.equal(captured.body.revision, first.body.revision);
  assert.equal((await request(handler, { method: "POST", url: "/view", body: { route: "/?token=secret", expectedCheckpoint: first.body.application.checkpoint } })).status, 400);
  assert.equal((await request(handler, { method: "POST", url: "/view", body: { route: "/wrong-version", expectedCheckpoint: "f".repeat(64) } })).status, 409);
  assert.equal((await request(handler, { method: "POST", url: "/view", body: { route: "/next", source: "anything" } })).status, 400);
  assert.equal(room.current().source.route, "/next?q=to+ord");
});

test("deliberate feedback receipts survive lost replies, reject mutation reuse and notify a submitted round once", async t => {
  const room = fixture(t).room(), notices = [], handler = createApplicationRequestHandler({ workspace: room, authority, onSubmitted: value => notices.push(value) });
  const create = { method: "POST", url: "/comments", body: note(room) };
  const first = await request(handler, create); assert.equal(first.status, 200); assert.equal(first.body.comments.length, 1);
  assert.equal((await request(handler, create)).body.comments.length, 1);
  assert.deepEqual(notices, []);
  assert.equal((await request(handler, { ...create, body: { ...note(room), text: "Annen tekst" } })).status, 409);
  const submit = { method: "POST", url: "/submit", headers: { "x-feedback-mutation": "e".repeat(32) }, body: { revision: first.body.revision } };
  assert.equal((await request(handler, submit)).status, 200); assert.equal((await request(handler, submit)).status, 200);
  assert.deepEqual(notices, [1]); assert.equal(room.feedback.state.submissions.length, 1);
  const deleted = await request(handler, { method: "POST", url: `/comments/${first.body.comments[0].id}/delete`, headers: { "x-feedback-mutation": "f".repeat(32) } });
  assert.equal(deleted.status, 409); assert.equal(room.feedback.state.comments.length, 1);
  assert.equal(room.canvas.read({ submission: 1 }).items.find(item => item.type === "comment").value.text, create.body.text);
});

test("editing a draft has a durable target and same-intent retry without duplicate comments", async t => {
  const room = fixture(t).room(), handler = createApplicationRequestHandler({ workspace: room, authority });
  const first = await request(handler, { method: "POST", url: "/comments", body: note(room) });
  const original = first.body.comments[0];
  const change = { method: "POST", url: `/comments/${original.id}/edit`, headers: { "x-feedback-mutation": "a".repeat(32) }, body: { text: "Bruk de samme tre valgene.", expectedRevision: first.body.revision } };
  const edited = await request(handler, change); assert.equal(edited.status, 200);
  const retry = await request(handler, change); assert.equal(retry.status, 200);
  assert.equal(retry.body.revision, edited.body.revision); assert.equal(retry.body.comments.length, 1);
  assert.equal(retry.body.comments[0].text, change.body.text);
  assert.deepEqual(retry.body.comments[0].applicationContext, original.applicationContext);
  const stale = await request(handler, { ...change, headers: { "x-feedback-mutation": "b".repeat(32) }, body: { ...change.body, text: "Gammelt grunnlag" } });
  assert.equal(stale.status, 409); assert.equal(room.feedback.state.comments[0].text, change.body.text);
});

test("a committed durability error still signals once and retry cannot duplicate its round", async t => {
  const room = fixture(t).room(); room.createComment(note(room));
  const persist = room.store.persist.bind(room.store);
  let uncertain = true;
  room.store.persist = state => { persist(state); if (uncertain) { uncertain = false; throw Object.assign(new Error("private path must stay private"), { committed: true }); } };
  const notices = [], handler = createApplicationRequestHandler({ workspace: room, authority, onSubmitted: number => { notices.push(number); throw new Error("observer failed"); } });
  const operation = { method: "POST", url: "/submit", body: { revision: room.feedback.state.revision } };
  const failed = await request(handler, operation);
  assert.equal(failed.status, 500); assert(!failed.text.includes("private path")); assert.deepEqual(notices, [1]);
  const retry = await request(handler, operation); assert.equal(retry.status, 200); assert.equal(retry.body.submission, 1); assert.deepEqual(notices, [1]);
});

test("rejected feedback and malformed bodies never alter persisted state", async t => {
  const room = fixture(t).room(), handler = createApplicationRequestHandler({ workspace: room, authority });
  const before = fs.readFileSync(room.store.filename, "utf8");
  const cases = [
    { status: 400, headers: { "x-feedback-mutation": undefined }, body: note(room) },
    { status: 400, headers: { "x-feedback-mutation": "wrong" }, body: note(room) },
    { status: 400, body: { ...note(room), screen: "0".repeat(32) } },
    { status: 400, body: { ...note(room), kind: "edit", proposal: { property: "text", value: "Bytt" } } },
    { status: 400, rawBody: Buffer.from("{") }, { status: 400, rawBody: Buffer.from([0xff]) },
    { status: 400, body: [] }, { status: 415, headers: { "content-type": "text/plain" } },
    { status: 413, rawBody: Buffer.alloc(16385, 32) }, { status: 413, headers: { "content-length": "99999" } },
  ];
  for (const { status, ...options } of cases) assert.equal((await request(handler, { method: "POST", url: "/comments", ...options })).status, status);
  assert.equal(fs.readFileSync(room.store.filename, "utf8"), before);
});

test("control paths and history query parsing reject aliases, duplicate values and extra fields", async t => {
  const room = fixture(t).room(), handler = createApplicationRequestHandler({ workspace: room, authority });
  const first = await request(handler, { url: "/history?after=0&limit=1" });
  assert.equal(first.status, 400);
  for (const url of ["//outside/state", "http://outside/state", "/state?token=hidden", "/state#fragment", "/history?after=0&after=1", "/history?limit=0", "/history?limit=1.5", "/history?unknown=yes"]) {
    assert.equal((await request(handler, { url })).status, 400, url);
  }
  assert.equal((await request(handler, { url: "/unavailable" })).status, 404);
  assert.equal((await request(handler, { method: "DELETE", url: "/state" })).status, 405);
});

test("rendering keeps control configuration in the privileged shell and escapes inline script delimiters", () => {
  const result = renderShell({ previewUrl: "http://127.0.0.1:45678/private", previewOrigin: "http://127.0.0.1:45678", token: authority.token, epoch: "e".repeat(32), title: "</script><script>alert(1)</script>" });
  assert(!result.html.includes("</script><script>alert(1)")); assert(result.html.includes("\\u003c/script\\u003e"));
  assert(result.csp.includes("frame-src 'self' http://127.0.0.1:45678")); assert(result.csp.includes("frame-ancestors 'none'"));
  assert(!result.csp.includes("127.0.0.1:*"), "live app navigation never gains access to arbitrary local ports");
  assert(!result.csp.includes("unsafe-inline")); assert(!result.html.includes("{{APPLICATION_"));
  assert(!result.html.includes("__DESIGN_INSPECTOR_CONFIG__"));
});

test("server commands open a persistent app room without sockets, expose summary only and reject HTML operations", async t => {
  const owner = fixture(t), server = owner.server({ create: true });
  const state = await server.command("readState");
  assert.equal(state.workspace.source.kind, "application"); assert.equal(state.workspace.source.snapshotAvailable, undefined);
  assert.equal(state.application.route, "/start?view=kort"); assert.equal(Object.hasOwn(state, "comments"), false);
  assert.match(state.application.checkpoint, /^[a-f0-9]{64}$/);
  for (const method of ["publishRevision", "readRevision", "restoreRevision", "listHistory"]) await assert.rejects(server.command(method, {}), rejection(409));
  await assert.rejects(server.command("readState", { extra: true }), rejection(400));
  await assert.rejects(server.command("unknown"), rejection(400));
  await assert.rejects(server.command("readSubmission", { submission: 1 }), rejection(404));
  assert.deepEqual(await server.command("closeView"), { closed: true });
  assert.equal((await server.command("readState")).screen, state.screen);
  await server.close();
  const reopened = owner.server();
  assert.equal((await reopened.command("readState")).screen, state.screen);
  assert.equal((await reopened.command("readState")).workspace.recovered, true);
  assert.deepEqual(await reopened.command("retire"), { retired: true });
  await assert.rejects(reopened.command("readState"), rejection(410));
});

test("agent read/review commands preserve submitted evidence and delivery ownership across reopen", async t => {
  const owner = fixture(t), room = owner.room(); room.createComment(note(room)); room.feedback.submit({});
  const original = room.canvas.read({ submission: 1 }); room.close();
  const server = owner.server(), read = await server.command("readSubmission", { submission: 1 });
  assert.equal(read.round.previousSession, true); assert.equal(read.round.delivery, "unknown");
  assert.equal(read.items.find(item => item.type === "comment").value.text, original.items.find(item => item.type === "comment").value.text);
  await assert.rejects(server.command("markDelivery", { submission: 1, status: "queued" }), rejection(409));
  const reviewed = await server.command("reviewSubmission", { submission: 1, status: "working", reply: "Ser på radiogruppen." });
  assert.equal(reviewed.canvas.rounds[0].review, "working"); assert.equal(reviewed.canvas.rounds[0].previousSession, false);
  const id = original.items.find(item => item.type === "comment").value.id;
  await server.command("updateComment", { submission: 1, id, status: "fixed", reply: "Prøvd i appkopien." });
  const next = await server.command("readSubmission", { submission: 1 });
  assert.equal(next.items.find(item => item.type === "comment").value.status, "open");
  assert.equal(next.items.find(item => item.type === "comment").current.status, "fixed");
});

test("IPC envelopes and CLI configuration remain closed and never echo application secrets", () => {
  const message = { channel: "visual-companion-canvas", version: 1, id: 1, method: "readState", params: {} };
  assert(validEnvelope(message));
  for (const value of [{ ...message, extra: true }, { ...message, params: [] }, { ...message, id: 0 }, { ...message, version: 2 }, { ...message, method: "x".repeat(65) }, { ...message, params: { large: "x".repeat(128 * 1024) } }]) assert.equal(validEnvelope(value), false);
  const args = ["--project-dir", "/temporary/project", "--workspace-dir", "designs/meeting", "--workspace-create", "true", "--application", JSON.stringify(application)];
  assert.deepEqual(parseArguments(args), { projectDir: "/temporary/project", workspacePath: "designs/meeting", create: true, application });
  for (const input of [[...args, "--unknown", "secret"], [...args, "--project-dir", "/other"], args.slice(0, -1), ["--application", "token=private"]]) {
    assert.throws(() => parseArguments(input), error => error.status === 400 && !error.message.includes("private") && !error.message.includes("secret"));
  }
});

test("application operation rejection diagnostics remain explicit while native paths stay private", async t => {
  const owner = fixture(t), server = owner.server({ create: true });
  await assert.rejects(server.command("readSource", { path: "missing/Component.tsx" }), error => error.status === 400 && !error.message.includes(owner.projectDir));
  const room = fixture(t).room(), handler = createApplicationRequestHandler({ workspace: room, authority });
  const result = await request(handler, { method: "POST", url: "/view", body: { route: "/?token=private-value", expectedCheckpoint: room.current().source.checkpoint } });
  assert.equal(result.status, 400); assert(!result.body.error.includes("private-value"));
  assert(!result.body.error.includes("kunne ikke bekreftes"));
});

test("the real IPC child becomes ready without binding a socket and retires its own lock cleanly", { timeout: 10000 }, async t => {
  const owner = fixture(t), filename = path.join(__dirname, "../scripts/application-server.js");
  const child = fork(filename, ["--project-dir", owner.projectDir, "--workspace-dir", "designs/meeting", "--workspace-create", "true", "--application", JSON.stringify(application)], { execArgv: [], stdio: ["ignore", "pipe", "pipe", "ipc"] });
  let output = ""; child.stdout.on("data", chunk => { output += chunk; }); child.stderr.on("data", chunk => { output += chunk; });
  const events = [], waiters = [];
  child.on("message", message => { const index = waiters.findIndex(waiter => waiter.match(message)); if (index < 0) events.push(message); else waiters.splice(index, 1)[0].resolve(message); });
  const receive = match => new Promise(resolve => { const index = events.findIndex(match); if (index >= 0) resolve(events.splice(index, 1)[0]); else waiters.push({ match, resolve }); });
  const exit = new Promise(resolve => child.once("exit", resolve));
  owner.cleanups.push(async () => { if (child.exitCode === null) child.kill("SIGTERM"); await exit; });
  const ready = await receive(message => message.event === "ready" || message.event === "startup-error");
  assert.equal(ready.event, "ready"); assert.deepEqual(ready.info, { type: "server-started" });
  child.send({ channel: "visual-companion-canvas", version: 1, id: 1, method: "readState", params: {} });
  const state = await receive(message => message.id === 1); assert.equal(state.ok, true); assert.equal(state.result.application.name, application.name);
  child.send({ channel: "visual-companion-canvas", version: 1, id: 2, method: "readState", params: {}, extra: true });
  assert.equal((await receive(message => message.id === 2)).status, 400);
  child.send({ channel: "visual-companion-canvas", version: 1, id: 3, method: "retire", params: {} });
  assert.equal((await receive(message => message.id === 3)).ok, true); assert.equal(await exit, 0);
  assert.equal(output, "");
  const reopened = owner.server(); assert.equal((await reopened.command("readState")).screen, state.result.screen);
});

test("native shell and app keep exact immutable origins and reopening requires a fresh server", { timeout: 10000 }, async t => {
  const upstream = http.createServer((req, res) => { res.setHeader("content-type", "text/html; charset=utf-8"); res.end("<!doctype html><html><head><title>Prøve</title></head><body><button>Neste</button></body></html>"); });
  await new Promise((resolve, reject) => { upstream.once("error", reject); upstream.listen(0, "127.0.0.1", resolve); });
  t.after(() => new Promise(resolve => { upstream.close(resolve); upstream.closeAllConnections?.(); }));
  const app = { name: "Møtevalg", url: `http://127.0.0.1:${upstream.address().port}/start?view=kort` };
  const owner = fixture(t), server = owner.server({ create: true, application: app });
  const first = await server.command("openView"), origin = new URL(first.url).origin;
  assert.deepEqual(await server.command("openView"), first);
  const config = await externalView(first.url);
  assert.equal(new URL(origin).hostname, "127.0.0.1"); assert.equal(new URL(config.previewOrigin).hostname, "localhost");
  assert.match(new URL(first.url).pathname, /^\/browser\/[a-f0-9]{64}$/); assert.equal(config.title, "Møtevalg");
  const authenticated = headers => ({ headers: { "X-Designverksted-Token": config.token, ...headers } });
  assert.equal((await fetch(origin + "/state")).status, 410);
  assert.equal((await fetch(origin + "/state", authenticated({ Origin: config.previewOrigin }))).status, 403);
  const state = await (await fetch(origin + "/state", authenticated())).json();
  assert.equal(state.application.route, "/start?view=kort");
  const bootstrap = await fetchPreview(config.previewUrl);
  assert.equal(bootstrap.status, 303);
  const cookie = bootstrap.headers.get("set-cookie").split(";")[0];
  const page = await fetchPreview(new URL(bootstrap.headers.get("location"), config.previewOrigin), { headers: { Cookie: cookie } });
  const pageHtml = await page.text(); assert.equal(page.status, 200); assert(pageHtml.includes("Neste"));
  assert(!pageHtml.includes(config.token));
  assert.equal((await fetch(origin + "/view", { method: "POST", headers: { ...authenticated().headers, Origin: origin, "Content-Type": "application/json" }, body: JSON.stringify({ route: "/next", expectedCheckpoint: state.application.checkpoint }) })).status, 200);
  await server.command("closeView");
  await assert.rejects(fetch(origin + "/state", authenticated()));
  await assert.rejects(fetchPreview(config.previewOrigin));
  assert.equal((await fetch(app.url)).status, 200);
  await assert.rejects(server.command("openView"), rejection(410));
  await server.close();
  const nextServer = owner.server({ application: app });
  const reopened = await nextServer.command("openView"), nextConfig = await externalView(reopened.url);
  assert.notEqual(nextConfig.token, config.token); assert.notEqual(nextConfig.epoch, config.epoch); assert.notEqual(new URL(reopened.url).pathname, new URL(first.url).pathname);
  const nextOrigin = new URL(reopened.url).origin;
  const resumedPage = await fetchPreview(nextConfig.previewUrl);
  assert.equal(resumedPage.headers.get("location"), "/start?view=kort", "Fresh workspaces start from their saved entry route");
  assert.equal((await fetch(nextOrigin + "/state", authenticated())).status, 410);
  const nextState = await (await fetch(nextOrigin + "/state", { headers: { "X-Designverksted-Token": nextConfig.token } })).json();
  assert.equal(nextState.application.route, "/start?view=kort"); assert.equal(nextState.workspace.id, state.workspace.id);
  await server.close(); assert.equal((await fetch(app.url)).status, 200);
});


test("no source, image or app history operation is exposed through HTTP or IPC", async t => {
  const owner = fixture(t), server = owner.server({ create: true });
  const source = path.join(owner.projectDir, "view.tsx"); fs.writeFileSync(source, "unfinished owner text");
  for (const method of ["readSource", "readSourceChanges", "prepareSourceChange", "applySourceChange", "restoreSourceChange", "abandonSourceChange", "registerReference", "listReferences"]) {
    await assert.rejects(server.command(method), rejection(400));
    await assert.rejects(server.command(method, { path: "view.tsx" }), rejection(400));
  }
  assert.equal(fs.readFileSync(source, "utf8"), "unfinished owner text");
  const room = fixture(t).room(), handler = createApplicationRequestHandler({ workspace: room, authority });
  const before = fs.readFileSync(room.store.filename);
  for (const url of ["/history", "/changes", "/references", "/references/" + "a".repeat(32), "/source/view.tsx"]) assert.equal((await request(handler, { url })).status, 404);
  for (const action of ["apply", "restore", "abandon"]) assert.equal((await request(handler, { method: "POST", url: `/changes/${"a".repeat(32)}/${action}` })).status, 404);
  assert.deepEqual(fs.readFileSync(room.store.filename), before);
});

test("temporary server requires no saved path and never creates a project artifact", async t => {
  const owner = fixture(t), server = owner.server({ workspacePath: undefined });
  const state = await server.command("readState");
  assert.equal(state.workspace.storage, "temporary"); assert.deepEqual(fs.readdirSync(owner.projectDir), []);
  assert.deepEqual(parseArguments(["--project-dir", owner.projectDir, "--application", JSON.stringify(application)]), { projectDir: owner.projectDir, application });
  await server.command("retire"); assert.deepEqual(fs.readdirSync(owner.projectDir), []);
});


test("preview diagnostics separate browser timeout from transport and guard report generations and order", () => {
  const preview = createPreviewStatus();
  assert.equal(preview.snapshot().previewStatus.reason, "view-closed");
  preview.open();
  const generation = preview.bootstrap();
  const report = (sequence, state, reason) => ({ generation, sequence, state, reason });
  assert.equal(preview.snapshot().previewStatus.state, "loading");
  preview.transport({ state: "ready", httpStatus: 200 });
  assert.equal(preview.snapshot().previewStatus.state, "loading", "HTML transport alone is not browser readiness");
  const timeout = report(2, "unavailable", "inspector-timeout");
  preview.report(timeout);
  assert.deepEqual(preview.snapshot(), { previewStatus: { state: "unavailable", reason: "inspector-timeout", retryAvailable: true }, transportStatus: { state: "ready", httpStatus: 200 } });
  preview.report(timeout); // Exact same report is safe after a lost reply.
  assert.throws(() => preview.report(report(1, "ready", "inspector-ready")), rejection(409));
  assert.throws(() => preview.report(report(2, "ready", "inspector-ready")), rejection(409));
  preview.report(report(3, "loading", "waiting-for-app"));
  assert.equal(preview.snapshot().previewStatus.state, "loading", "A retry is visible without a workspace mutation");
  preview.report(report(4, "ready", "inspector-ready"));
  assert.equal(preview.snapshot().previewStatus.state, "ready");
  preview.transport({ state: "unavailable", httpStatus: 502 });
  assert.equal(preview.snapshot().previewStatus.state, "unavailable", "Late browser readiness cannot conceal a transport failure");
  const freshGeneration = preview.bootstrap();
  assert.notEqual(freshGeneration, generation);
  assert.throws(() => preview.report(report(5, "ready", "inspector-ready")), rejection(409));
  preview.report({ generation: freshGeneration, sequence: 1, state: "loading", reason: "waiting-for-app" });
  preview.close();
  assert.throws(() => preview.report({ generation: freshGeneration, sequence: 2, state: "ready", reason: "inspector-ready" }), rejection(409));
  assert.equal(preview.snapshot().previewStatus.retryAvailable, false);
  preview.open(); preview.bootstrap();
  assert.throws(() => preview.report({ generation: freshGeneration, sequence: 3, state: "ready", reason: "inspector-ready" }), rejection(409));
});

test("preview status accepts no application authority and performs no workspace writes", async t => {
  const room = fixture(t).room(), preview = createPreviewStatus(); preview.open();
  const generation = preview.bootstrap();
  const boundAuthority = { ...authority, preview };
  const handler = createApplicationRequestHandler({ workspace: room, authority: boundAuthority });
  const before = fs.readFileSync(room.store.filename), beforeStat = fs.statSync(room.store.filename, { bigint: true });
  const feedbackBefore = room.feedback.snapshot();
  const body = { generation, sequence: 1, state: "unavailable", reason: "inspector-timeout" };
  const operation = { method: "POST", url: "/preview/status", headers: { "x-feedback-mutation": undefined }, body };
  assert.equal((await request(handler, operation)).status, 200);
  const state = (await request(handler)).body;
  assert.equal(state.application.previewStatus.state, "unavailable");
  assert.equal(state.application.previewStatus.reason, "inspector-timeout");
  assert.equal(state.application.transportStatus.state, "loading");
  assert.equal(JSON.stringify(state).includes(generation), false, "Report capability is not in agent-readable state");
  for (const headers of [
    { origin: "http://dv-foreign.localhost:45678" },
    { "x-designverksted-token": undefined },
    { "x-designverksted-token": undefined, cookie: "token=" + authority.token },
    { origin: undefined },
  ]) assert.equal((await request(handler, { ...operation, headers })).status, 403);
  for (const extra of [{ route: "/other" }, { text: "private application text" }, { action: "submit" }, { httpStatus: 200 }]) {
    assert.equal((await request(handler, { ...operation, body: { ...body, ...extra } })).status, 400);
  }
  for (const change of [{ generation: [generation] }, { state: ["unavailable"] }, { reason: "secret error content" }, { sequence: 0 }, { sequence: 1.5 }, { state: "ready" }, { reason: "inspector-ready" }]) {
    assert.equal((await request(handler, { ...operation, body: { ...body, ...change } })).status, 400);
  }
  assert.deepEqual(fs.readFileSync(room.store.filename), before);
  assert.equal(fs.statSync(room.store.filename, { bigint: true }).mtimeNs, beforeStat.mtimeNs);
  assert.deepEqual(room.feedback.snapshot(), feedbackBefore);
});

test("each shell bootstrap retires the old status reporter without changing feedback", async t => {
  const room = fixture(t).room(), preview = createPreviewStatus(); preview.open();
  const boundAuthority = { ...authority, preview, renderShell: () => ({ html: preview.bootstrap(), csp: authority.csp }) };
  const handler = createApplicationRequestHandler({ workspace: room, authority: boundAuthority });
  const load = () => request(handler, { url: authority.openPath, headers: { "x-designverksted-token": undefined } });
  const first = (await load()).text;
  const report = generation => request(handler, { method: "POST", url: "/preview/status", body: { generation, sequence: 1, state: "loading", reason: "waiting-for-app" } });
  assert.equal((await report(first)).status, 200);
  const second = (await load()).text;
  assert.notEqual(second, first);
  assert.equal((await report(first)).status, 409);
  assert.equal((await report(second)).status, 200);
  assert.equal(room.feedback.state.revision, 0);
});


test("known transport failure overrides stale loading and missing browser reports immediately", () => {
  const preview = createPreviewStatus(); preview.open();
  const generation = preview.bootstrap();
  preview.report({ generation, sequence: 1, state: "loading", reason: "waiting-for-app" });
  preview.transport({ state: "unavailable", httpStatus: 502 });
  const unavailable = { state: "unavailable", reason: "application-unavailable", retryAvailable: true };
  assert.deepEqual(preview.snapshot().previewStatus, unavailable, "Known failure must not remain loading until the next shell poll");
  assert.deepEqual(preview.snapshot().transportStatus, { state: "unavailable", httpStatus: 502 });
  const nextGeneration = preview.bootstrap();
  assert.deepEqual(preview.snapshot().previewStatus, unavailable, "No browser report must not obscure a known failure as waiting-for-view");
  preview.report({ generation: nextGeneration, sequence: 1, state: "unavailable", reason: "inspector-timeout" });
  assert.equal(preview.snapshot().previewStatus.reason, "inspector-timeout", "Retain the more precise observed timeout");
  preview.close();
  assert.deepEqual(preview.snapshot().previewStatus, { state: "unavailable", reason: "view-closed", retryAvailable: false });
});

test("bounded invitations never grant writes and only one candidate activates idempotently", () => {
  let now = 1000; const connection = createConnectionState({ now: () => now });
  const invitation = connection.prepare(), first = connection.candidate(invitation), second = connection.candidate(invitation);
  assert.equal(connection.status().state, "connecting");
  assert.throws(() => connection.authorize(first), rejection(410));
  let activations = 0; const bootstrap = () => ({ reportGeneration: ++activations });
  assert.deepEqual(connection.activate(second, bootstrap), { reportGeneration: 1 });
  assert.deepEqual(connection.activate(second, bootstrap), { reportGeneration: 1 });
  assert.equal(activations, 1); connection.authorize(second);
  assert.throws(() => connection.activate(first, bootstrap), rejection(410));
  assert.throws(() => connection.activate(connection.candidate(invitation), bootstrap), rejection(410));
  now += INVITATION_MS;
  assert.deepEqual(connection.status(), { state: "connected", invitationExpired: false }, "An active view must not look expired after the opening window closes");
  assert.throws(() => connection.candidate(invitation), rejection(410));
  assert.deepEqual(connection.activate(second, bootstrap), { reportGeneration: 1 }, "Lost activation reply remains idempotent for active document");
  const next = connection.prepare(); assert.notEqual(next, invitation);
  assert.throws(() => connection.authorize(second), rejection(410));
  for (let index = 0; index < MAX_CANDIDATES; index++) connection.candidate(next);
  assert.throws(() => connection.candidate(next), rejection(429));
  connection.close(); assert.throws(() => connection.prepare(), rejection(410));
});

test("all HTTP read and mutation paths reject a replaced renderer, including bodies already in flight", async t => {
  const room = fixture(t).room(), connection = createConnectionState(), preview = createPreviewStatus(); preview.open();
  const first = connection.candidate(connection.prepare()); connection.activate(first, () => ({}));
  const activeAuthority = { ...authority, connection, preview };
  const notices = [], handler = createApplicationRequestHandler({ workspace: room, authority: activeAuthority, onSubmitted: value => notices.push(value) });
  const before = fs.readFileSync(room.store.filename);
  const pending = [];
  for (const [url, body] of [["/comments", note(room)], ["/submit", { revision: 0 }], ["/view", { route: "/other", expectedCheckpoint: room.current().source.checkpoint }], ["/preview/status", {}], [`/comments/${"a".repeat(24)}/edit`, {}], [`/comments/${"a".repeat(24)}/delete`, {}]]) {
    const req = Object.assign(new PassThrough(), requestShape({ method: "POST", url, headers: { "x-designverksted-token": first } }));
    const res = { setHeader() {}, end(value) { this.value = JSON.parse(value); } };
    const done = handler(req, res); pending.push({ req, res, done, body });
  }
  const second = connection.candidate(connection.prepare()); connection.activate(second, () => ({}));
  for (const item of pending) { item.req.end(JSON.stringify(item.body)); await item.done; assert.equal(item.res.statusCode, 410); assert.equal(item.res.value.code, "renderer-stale"); }
  assert.equal((await request(handler, { headers: { "x-designverksted-token": first } })).status, 410);
  assert.equal((await request(handler, { headers: { "x-designverksted-token": second } })).status, 200);
  assert.deepEqual(fs.readFileSync(room.store.filename), before); assert.deepEqual(notices, []);
});

test("native candidate reload cannot take over or rotate the immutable proxy, and feedback receipts persist", { timeout: 15000 }, async t => {
  const upstream = http.createServer((_req, res) => { res.setHeader("Content-Type", "text/html"); res.end("<!doctype html><button>Neste</button>"); });
  await new Promise(resolve => upstream.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise(resolve => { upstream.close(resolve); upstream.closeAllConnections(); }));
  const owner = fixture(t), notices = [], server = owner.server({ create: true, application: { name: "Møtevalg", url: `http://127.0.0.1:${upstream.address().port}/start?view=kort` }, onSubmitted: value => notices.push(value) });
  const opened = await server.command("openView"), origin = new URL(opened.url).origin;
  const document = await (await fetch(opened.url)).text();
  assert(!document.includes("__designConnection"));
  const candidate = JSON.parse(/window\.__designApplication = (.*);/.exec(document)[1]);
  const call = (url, token, body, mutation) => fetch(origin + url, { method: body ? "POST" : "GET", headers: { Origin: origin, "Content-Type": "application/json", "X-Designverksted-Token": token, ...(mutation ? { "X-Feedback-Mutation": mutation } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) });
  assert.equal((await call("/state", candidate.token)).status, 410, "GET is inert");
  const activated = await call("/renderer/activate", candidate.token, {}); assert.equal(activated.status, 200);
  const bootstrap = await activated.json();
  assert.deepEqual(await (await call("/renderer/activate", candidate.token, {})).json(), bootstrap);
  const reloaded = JSON.parse(/window\.__designApplication = (.*);/.exec(await (await fetch(opened.url)).text())[1]);
  assert.notEqual(reloaded.token, candidate.token);
  assert.equal((await call("/renderer/activate", reloaded.token, {})).status, 410);
  for (const url of ["/connection/reopen", "/connection/status"]) {
    assert.equal((await call(url, candidate.token, {})).status, 404, "No controller can rotate this proxy");
  }
  const state = await (await call("/state", candidate.token)).json();
  const input = note({ current: () => ({ screen: state.screen, source: { route: state.application.route } }) });
  const created = await (await call("/comments", candidate.token, input, "a".repeat(32))).json();
  assert.equal(created.comments.length, 1);
  await assert.rejects(server.command("closeView", { extra: true }), rejection(400));
  assert.equal((await call("/state", candidate.token)).status, 200, "Rejected IPC parameters cannot revoke the view");
  const repeated = await (await call("/comments", candidate.token, input, "a".repeat(32))).json(); assert.equal(repeated.comments.length, 1);
  const submit = { revision: repeated.revision };
  assert.equal((await call("/submit", candidate.token, submit, "b".repeat(32))).status, 200);
  assert.equal((await call("/submit", candidate.token, submit, "b".repeat(32))).status, 200);
  assert.deepEqual(notices, [1]);
  assert.deepEqual(await server.command("openView"), opened);
  assert.deepEqual(await (await call("/renderer/activate", candidate.token, {})).json(), bootstrap);
  const firstRetry = await fetchPreview(bootstrap.previewUrl), secondRetry = await fetchPreview(bootstrap.previewUrl);
  assert.equal(firstRetry.status, 303); assert.equal(secondRetry.status, 303);
  assert.equal(firstRetry.headers.get("set-cookie"), secondRetry.headers.get("set-cookie"), "Iframe retry retains the same private connection");
  const publicState = JSON.stringify(await server.command("readState"));
  for (const secret of [candidate.token, reloaded.token, bootstrap.previewUrl, opened.url]) assert(!publicState.includes(secret));
  await server.command("closeView");
  await assert.rejects(server.command("openView"), rejection(410));
  assert.equal((await server.command("readState")).application.connection.state, "closed");
});

test("closing during shell or proxy listen waits for startup and leaves no owned listener", { timeout: 10000 }, async t => {
  for (const pauseAt of [1, 2]) {
    const owner = fixture(t), server = owner.server({ create: true });
    const original = http.Server.prototype.listen, handles = [];
    let release, signal;
    const waiting = new Promise(resolve => { signal = resolve; });
    http.Server.prototype.listen = function (...args) {
      handles.push(this);
      if (handles.length === pauseAt) { release = () => original.apply(this, args); signal(); return this; }
      return original.apply(this, args);
    };
    try {
      const opening = server.command("openView");
      // Attach the rejection handler before releasing the held listen operation.
      const rejected = assert.rejects(opening, rejection(410));
      await waiting;
      let finished = false; const closing = server.close().then(() => { finished = true; });
      await new Promise(resolve => setImmediate(resolve)); assert.equal(finished, false);
      release(); await rejected; await closing;
      assert(handles.every(handle => !handle.listening));
      await server.close();
    } finally { http.Server.prototype.listen = original; }
  }
});

test("closeView immediately rejects the old document while teardown waits behind a startup", { timeout: 10000 }, async t => {
  const owner = fixture(t), server = owner.server({ create: true });
  const original = http.Server.prototype.listen;
  let release, signal, handle;
  const waiting = new Promise(resolve => { signal = resolve; });
  http.Server.prototype.listen = function (...args) { handle = this; release = () => original.apply(this, args); signal(); return this; };
  try {
    const opening = server.command("openView"), rejected = assert.rejects(opening, rejection(410));
    await waiting; const closing = server.command("closeView");
    release(); await rejected; assert.deepEqual(await closing, { closed: true }); assert.equal(handle.listening, false);
    assert.equal((await server.command("readState")).application.connection.state, "closed");
  } finally { http.Server.prototype.listen = original; }
});


test("unexpected control or proxy listener loss retires the whole native view without replacing origins", { timeout: 10000 }, async t => {
  for (const lostIndex of [0, 1]) {
    const upstream = http.createServer((_req, res) => { res.setHeader("Content-Type", "text/html"); res.end("<!doctype html><button>Neste</button>"); });
    await new Promise(resolve => upstream.listen(0, "127.0.0.1", resolve));
    t.after(() => new Promise(resolve => { upstream.close(resolve); upstream.closeAllConnections(); }));
    const owner = fixture(t), handles = [], original = http.Server.prototype.listen;
    let lostCount = 0, signalLost;
    const lost = new Promise(resolve => { signalLost = resolve; });
    const server = owner.server({ create: true, application: { name: "Demo", url: `http://127.0.0.1:${upstream.address().port}/` }, onViewLost: () => { lostCount++; signalLost(); } });
    http.Server.prototype.listen = function (...args) { handles.push(this); return original.apply(this, args); };
    let opened;
    try { opened = await server.command("openView"); } finally { http.Server.prototype.listen = original; }
    assert.equal(handles.length, 2);
    const config = await externalView(opened.url);
    handles[lostIndex].close(); handles[lostIndex].closeAllConnections();
    await lost;
    assert.equal(lostCount, 1); assert(handles.every(handle => !handle.listening));
    await assert.rejects(server.command("openView"), rejection(410));
    await assert.rejects(server.command("readState"), rejection(410));
    await assert.rejects(fetch(opened.url)); await assert.rejects(fetchPreview(config.previewUrl));
    assert.equal((await fetch(`http://127.0.0.1:${upstream.address().port}/`)).status, 200);
  }
});
