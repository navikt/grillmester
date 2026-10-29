"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const crypto = require("node:crypto");
const http = require("node:http");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { PassThrough } = require("node:stream");
const { createConnectionState, INVITATION_MS, MAX_CANDIDATES } = require("../scripts/application-connection-state.js");
const { renderActivationScript } = require("../scripts/application-connection-view.js");
const { createApplicationServer, createApplicationRequestHandler, createPreviewStatus, renderShell } = require("../scripts/application-server.js");
const rejected = status => error => error.status === status;
const origin = "http://127.0.0.1:34567";
const bootstrap = reportGeneration => ({ previewUrl: "http://localhost:34568/preview/" + "a".repeat(64), previewOrigin: "http://localhost:34568", epoch: "b".repeat(32), reportGeneration });
function fixture() {
  let now = 0, bootstraps = 0;
  const connection = createConnectionState({ now: () => now });
  const invitation = connection.prepare();
  return { connection, invitation, expire() { now += INVITATION_MS; }, bootstrap() { return bootstrap((++bootstraps).toString(16).padStart(32, "0")); }, get bootstraps() { return bootstraps; } };
}
function storage(initial = new Map()) {
  return { values: initial, getItem(key) { return initial.get(key) ?? null; }, setItem(key, value) { initial.set(key, value); }, removeItem(key) { initial.delete(key); } };
}
async function documentFor(owner, { store = storage(), type = "navigate", opener = null, loseReply = false, response } = {}) {
  const candidate = owner.connection.bootstrapCandidate(owner.invitation);
  const config = { title: "Synthetic", token: candidate, activationRequired: true, connectionId: owner.connection.generation };
  const calls = [], nodes = new Map();
  const node = id => { if (!nodes.has(id)) nodes.set(id, { hidden: false, disabled: false, addEventListener(name, callback) { this[name] = callback; }, removeEventListener(name) { delete this[name]; } }); return nodes.get(id); };
  const context = { window: { __designApplication: config, opener }, location: { origin },
    performance: { getEntriesByType: () => [{ type }] }, sessionStorage: store,
    document: { getElementById: node, querySelectorAll: () => [] },
    crypto: crypto.webcrypto, Uint8Array, AbortController, URL, setTimeout, clearTimeout,
    fetch: async (url, options) => {
      calls.push({ url, options });
      if (response) return response;
      let value;
      try { value = owner.connection.activate(options.headers["X-Designverksted-Token"], () => owner.bootstrap(), Object.keys(JSON.parse(options.body)).length ? JSON.parse(options.body) : undefined); }
      catch (error) { return { ok: false, status: error.status }; }
      if (loseReply) throw new Error("synthetic lost reply");
      return { ok: true, json: async () => value };
    } };
  await vm.runInNewContext(renderActivationScript("window.started = window.__designApplication;"), context);
  return { ...context, calls, candidate, nodes };
}

test("repeated same-tab reload uses only validated authority after invitation expiry and candidate exhaustion", async () => {
  const owner = fixture(), store = storage();
  for (let i = 1; i < MAX_CANDIDATES; i++) owner.connection.candidate(owner.invitation);
  const initial = await documentFor(owner, { store });
  assert(initial.window.started); const token = initial.window.started.token;
  owner.expire();
  for (let i = 0; i < MAX_CANDIDATES + 2; i++) {
    const reloaded = await documentFor(owner, { store, type: "reload" });
    assert.equal(reloaded.candidate, null, "Recovery must not consume another candidate");
    assert.equal(reloaded.window.started.token, token);
    assert.equal(reloaded.window.started.previewUrl, initial.window.started.previewUrl);
    assert.notEqual(reloaded.window.started.reportGeneration, initial.window.started.reportGeneration);
    owner.connection.authorize(token);
  }
  assert.equal(owner.bootstraps, MAX_CANDIDATES + 3);
});

test("public invitation, new tabs and opener-cloned storage cannot take over an existing writer", async () => {
  const owner = fixture(), store = storage(), initial = await documentFor(owner, { store });
  const token = initial.window.started.token, reportGeneration = initial.window.started.reportGeneration;
  for (const options of [{}, { type: "reload" }, { type: "navigate", store: storage(new Map(store.values)) }, { type: "reload", opener: {}, store: storage(new Map(store.values)) }]) {
    const cloneStore = options.store || storage();
    const other = await documentFor(owner, { ...options, store: cloneStore });
    assert.equal(other.window.started, undefined); assert.equal(other.calls.length, 0);
    assert.equal(cloneStore.values.size, 0);
    const retry = await documentFor(owner, { store: cloneStore, type: "reload" });
    assert.equal(retry.window.started, undefined);
    owner.connection.authorize(token);
  }
  assert.equal(owner.bootstraps, 1);
  assert.equal(owner.connection.activate(token, () => assert.fail("Must retain bootstrap")).reportGeneration, reportGeneration);
});

test("inert recovery document cannot enlarge candidate capacity or reopen an expired invitation", async () => {
  const owner = fixture();
  for (let i = 0; i < MAX_CANDIDATES; i++) owner.connection.candidate(owner.invitation);
  assert.equal(owner.connection.bootstrapCandidate(owner.invitation), null);
  assert.throws(() => owner.connection.candidate(owner.invitation), rejected(429));
  assert.equal((await documentFor(owner)).window.started, undefined);
  owner.expire(); assert.equal(owner.connection.bootstrapCandidate(owner.invitation), null);
  assert.equal((await documentFor(owner, { type: "reload" })).calls.length, 0);
  assert.throws(() => owner.connection.bootstrapCandidate(owner.invitation + "?extra=1"), rejected(410));
});

test("new generation and closed views reject old authority even if storage is copied to the new key", async () => {
  const owner = fixture(), store = storage(), first = await documentFor(owner, { store });
  const oldToken = first.window.started.token, oldGeneration = owner.connection.generation;
  owner.invitation = owner.connection.prepare();
  assert.notEqual(owner.connection.generation, oldGeneration);
  store.setItem("designverksted.renderer.v1:" + owner.connection.generation, [...store.values.values()][0]);
  const stale = await documentFor(owner, { store, type: "reload" });
  assert.equal(stale.window.started, undefined); assert.equal(stale.calls.length, 1);
  assert.throws(() => owner.connection.authorize(oldToken), rejected(410));
  const fresh = await documentFor(owner); assert(fresh.window.started);
  owner.connection.close();
  assert.throws(() => owner.connection.activate(fresh.window.started.token, () => owner.bootstrap()), rejected(410));
  assert.throws(() => owner.connection.bootstrapCandidate(owner.invitation), rejected(410));
});

test("ambiguous resume reply is retried once with the same generation and request", async () => {
  const owner = fixture(), store = storage();
  await documentFor(owner, { store });
  const lost = await documentFor(owner, { store, type: "reload", loseReply: true });
  assert.equal(lost.window.started, undefined); assert.equal(owner.bootstraps, 2);
  const retry = await documentFor(owner, { store, type: "reload" });
  assert(retry.window.started); assert.equal(owner.bootstraps, 2);
  assert.equal(retry.calls[0].options.body, lost.calls[0].options.body);
  const oldResume = JSON.parse(lost.calls[0].options.body);
  const next = await documentFor(owner, { store, type: "reload" });
  assert.equal(owner.bootstraps, 3);
  assert.throws(() => owner.connection.activate(next.window.started.token, () => owner.bootstrap(), oldResume), rejected(410));
  assert.equal(owner.bootstraps, 3);
});

test("only a validated successful response is retained; disabled storage never creates replacement authority", async () => {
  const owner = fixture(), store = storage();
  const invalid = await documentFor(owner, { store, response: { ok: true, json: async () => ({ ...bootstrap("c".repeat(32)), previewOrigin: origin }) } });
  assert.equal(invalid.window.started, undefined); assert.equal(store.values.size, 0);
  const disabled = { getItem() { throw new Error("disabled"); }, setItem() { throw new Error("disabled"); }, removeItem() { throw new Error("disabled"); } };
  const first = await documentFor(owner, { store: disabled }); assert(first.window.started);
  const reload = await documentFor(owner, { store: disabled, type: "reload" });
  assert.equal(reload.window.started, undefined); assert.equal(reload.calls.length, 0);
  owner.connection.authorize(first.window.started.token);
});

test("HTTP recovery keeps one writer, rotates only its diagnostics and rejects stale invitations and reports", async t => {
  const owner = fixture(), preview = createPreviewStatus(); preview.open();
  let activations = 0;
  const authority = { connection: owner.connection, preview, readState: async () => ({ safe: true }),
    renderShell: token => renderShell({ title: "Synthetic", token, previewOrigin: "http://localhost:34568", activationRequired: true, connectionId: owner.connection.generation }),
    activationBootstrap: () => { activations++; return bootstrap(preview.bootstrap()); } };
  const handler = createApplicationRequestHandler({ workspace: { assertOpen() {} }, authority });
  const server = http.createServer(handler);
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  authority.origin = `http://127.0.0.1:${server.address().port}`;
  const call = (route, token, body) => fetch(authority.origin + route, { method: body ? "POST" : "GET", headers: { Origin: authority.origin, "Content-Type": "application/json", "X-Designverksted-Token": token || "" }, ...(body ? { body: JSON.stringify(body) } : {}) });
  const document = async route => {
    const response = await fetch(authority.origin + route), html = await response.text();
    const match = /window\.__designApplication = (.*);/.exec(html);
    return { response, html, config: match ? JSON.parse(match[1]) : null };
  };
  const first = await document(owner.invitation), competing = await document(owner.invitation);
  assert.equal((await call("/state", first.config.token)).status, 410);
  const opened = await call("/renderer/activate", first.config.token, {});
  assert.equal(opened.status, 200); const original = await opened.json();
  const reloaded = await document(owner.invitation);
  assert.equal(reloaded.config.token, null); assert(!reloaded.html.includes(first.config.token));
  for (const token of [competing.config.token, "f".repeat(64)]) {
    assert.equal((await call("/renderer/activate", token, {})).status, 410);
    assert.equal((await call("/state", token)).status, 410);
    assert.equal((await call("/submit-draft", token, {})).status, 410);
  }
  const resume = { resumeId: "d".repeat(32), expectedReportGeneration: original.reportGeneration };
  assert.equal((await call("/renderer/activate", competing.config.token, resume)).status, 410);
  const resumed = await call("/renderer/activate", first.config.token, resume);
  assert.equal(resumed.status, 200); const next = await resumed.json();
  assert.equal(next.previewUrl, original.previewUrl); assert.equal(next.epoch, original.epoch);
  assert.notEqual(next.reportGeneration, original.reportGeneration); assert.equal(activations, 2);
  for (const body of [{ ...resume, extra: true }, { ...resume, resumeId: "invalid" }]) assert.equal((await call("/renderer/activate", first.config.token, body)).status, 400);
  assert.equal((await call("/renderer/activate?extra=1", first.config.token, {})).status, 400);
  assert.equal((await call("/preview/status", first.config.token, { generation: original.reportGeneration, sequence: 1, state: "ready", reason: "inspector-ready" })).status, 409);
  assert.equal((await call("/preview/status", first.config.token, { generation: next.reportGeneration, sequence: 1, state: "ready", reason: "inspector-ready" })).status, 200);
  owner.expire(); assert.equal((await document(owner.invitation)).config.token, null);
  assert.deepEqual(await (await call("/renderer/activate", first.config.token, resume)).json(), next);
  assert.equal(activations, 2); assert.deepEqual(await (await call("/state", first.config.token)).json(), { safe: true });
  const oldInvitation = owner.invitation; owner.invitation = owner.connection.prepare();
  const stale = await document(oldInvitation); assert.equal(stale.config, null); assert(!stale.html.includes(first.config.token));
  assert.equal((await call("/renderer/activate", first.config.token, resume)).status, 410);
  owner.connection.close(); assert.equal((await call("/state", first.config.token)).status, 410);
});

test("proposal opening retains its original parent lease across a slow body and asynchronous child startup", async () => {
  const owner = fixture(), token = owner.connection.candidate(owner.invitation);
  owner.connection.activate(token, () => owner.bootstrap());
  let opened = 0, release, starting;
  const authority = { origin, connection: owner.connection, proposalLeaseId: "a".repeat(32),
    openProposal: async () => { opened++; return { safe: true }; } };
  const handler = createApplicationRequestHandler({ workspace: { assertOpen() {} }, authority });
  const pending = () => {
    const headers = { host: new URL(origin).host, origin, "content-type": "application/json", "x-designverksted-token": token };
    const request = Object.assign(new PassThrough(), { method: "POST", url: "/proposal/open", headers, rawHeaders: Object.entries(headers).flat(), socket: { remoteAddress: "127.0.0.1" } });
    const response = { setHeader() {}, end(value) { this.value = JSON.parse(value); } };
    return { request, response, done: handler(request, response) };
  };
  const slow = pending(); authority.proposalLeaseId = "b".repeat(32);
  slow.request.end(JSON.stringify({ proposalId: "c".repeat(24) })); await slow.done;
  assert.equal(slow.response.statusCode, 410); assert.equal(opened, 0);
  const started = new Promise(resolve => { starting = resolve; });
  authority.openProposal = async () => { opened++; starting(); await new Promise(resolve => { release = resolve; }); return { safe: true }; };
  const delayed = pending(); delayed.request.end(JSON.stringify({ proposalId: "c".repeat(24) }));
  await started; authority.proposalLeaseId = "d".repeat(32); release(); await delayed.done;
  assert.equal(delayed.response.statusCode, 410); assert.equal(delayed.response.value.safe, undefined);
  authority.openProposal = async () => ({ safe: true });
  const fresh = pending(); fresh.request.end(JSON.stringify({ proposalId: "c".repeat(24) })); await fresh.done;
  assert.equal(fresh.response.statusCode, 200); assert.deepEqual(fresh.response.value, { safe: true });
});

test("running child rebind keeps source and proxy, rejects former controls, and requires the exact same parent", async t => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "application-rebind-")));
  const upstream = http.createServer((_request, response) => { response.setHeader("Content-Type", "text/html"); response.end("<!doctype html><h1>Synthetic proposal</h1>"); });
  await new Promise(resolve => upstream.listen(0, "127.0.0.1", resolve));
  const app = createApplicationServer({ projectDir: root, application: { name: "Synthetic", url: `http://127.0.0.1:${upstream.address().port}/start` } });
  t.after(async () => { await app.close(); await new Promise(resolve => { upstream.close(resolve); upstream.closeAllConnections(); }); fs.rmSync(root, { recursive: true, force: true }); });
  const parentOrigin = "http://127.0.0.1:34569", embedding = { parentOrigin, leaseId: "a".repeat(32) };
  const view = await app.command("openView", { embedding });
  const load = async value => {
    const html = await (await fetch(value.url)).text();
    const candidate = JSON.parse(/const config=(\{.*?\});/.exec(html)[1]).candidate;
    return { candidate, activationKey: value.activationKey };
  };
  const call = (route, token, body) => fetch(view.origin + route, { method: body ? "POST" : "GET", headers: { Origin: view.origin, "Content-Type": "application/json", ...(token ? { "X-Designverksted-Token": token } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) });
  const oldCandidate = await load(view), activated = await call("/embedded/activate", null, oldCandidate);
  assert.equal(activated.status, 200);
  const old = JSON.parse(/window\.__designApplication = (.*);/.exec(await activated.text())[1]);
  const before = await app.command("readState");
  for (const invalid of [{ ...embedding, parentOrigin: "http://127.0.0.1:34570" }, { ...embedding, extra: true }]) await assert.rejects(app.command("openView", { embedding: invalid }));
  assert.equal((await call("/state", old.token)).status, 200, "Rejected rebind cannot revoke the current writer");
  const nextEmbedding = { parentOrigin, leaseId: "b".repeat(32) }, nextView = await app.command("openView", { embedding: nextEmbedding });
  assert.equal(nextView.origin, view.origin); assert.notEqual(nextView.url, view.url);
  assert.deepEqual(await app.command("openView", { embedding: nextEmbedding }), nextView);
  assert.equal((await call("/state", old.token)).status, 410);
  assert.equal((await call("/submit-draft", old.token, {})).status, 410);
  assert.equal((await call("/embedded/activate", null, oldCandidate)).status, 403);
  assert.equal((await fetch(view.url)).status, 410);
  const nextCandidate = await load(nextView), nextResponse = await call("/embedded/activate", null, nextCandidate);
  assert.equal(nextResponse.status, 200);
  const next = JSON.parse(/window\.__designApplication = (.*);/.exec(await nextResponse.text())[1]);
  assert.notEqual(next.token, old.token); assert.notEqual(next.reportGeneration, old.reportGeneration);
  assert.equal(next.previewUrl, old.previewUrl); assert.equal(next.epoch, old.epoch);
  const after = await app.command("readState");
  assert.equal(after.screen, before.screen); assert.equal(after.application.checkpoint, before.application.checkpoint);
  assert.equal(after.submission, before.submission); assert.equal((await call("/state", next.token)).status, 200);
});
