"use strict";
const test = require("node:test"), assert = require("node:assert/strict");
const { createProposalViews } = require("../scripts/application-proposal-view.js");
const parentOrigin = "http://127.0.0.1:34441", child = { url: "http://127.0.0.1:34442/embedded/" + "a".repeat(64), origin: "http://127.0.0.1:34442", activationKey: "b".repeat(64), leaseId: "c".repeat(32), title: "Møteforslag" };
function candidate(html) { return JSON.parse(/const config=(\{.*?\}),frame=/.exec(html)[1]).candidate; }
test("proposal bridge keeps exact navigation boundaries and carries no child authority before activation", () => {
  const views = createProposalViews(parentOrigin), view = views.open("d".repeat(24), child), rendered = views.render(new URL(view.url).pathname);
  assert(rendered.csp.includes("frame-src " + child.origin)); assert(!rendered.csp.includes("127.0.0.1:*")); assert(rendered.csp.includes("frame-ancestors " + parentOrigin));
  assert(!rendered.html.includes(child.activationKey)); assert(!rendered.html.includes(child.url)); assert(!rendered.html.includes(view.activationKey));
  assert(rendered.html.includes("event.source!==window.parent")); assert(rendered.html.includes("event.source===frame.contentWindow"));
  assert.throws(() => views.activate({ candidate: candidate(rendered.html), activationKey: "f".repeat(64) }), error => error.status === 410);
  assert.deepEqual(views.activate({ candidate: candidate(rendered.html), activationKey: view.activationKey }), child);
  assert.deepEqual(views.activate({ candidate: candidate(rendered.html), activationKey: view.activationKey }), child, "one intent can retry without a new writer");
});
test("another fetched bridge cannot acquire the active proposal, and revoke invalidates every old capability", () => {
  const views = createProposalViews(parentOrigin), view = views.open("d".repeat(24), child), first = candidate(views.render(new URL(view.url).pathname).html), second = candidate(views.render(new URL(view.url).pathname).html);
  views.activate({ candidate: first, activationKey: view.activationKey });
  assert.throws(() => views.activate({ candidate: second, activationKey: view.activationKey }), error => error.status === 410);
  assert.throws(() => views.render(new URL(view.url).pathname), error => error.status === 410);
  views.revoke(); assert.throws(() => views.activate({ candidate: first, activationKey: view.activationKey }), error => error.status === 410);
  assert.throws(() => views.render(new URL(view.url).pathname), error => error.status === 410);
});
test("one proposal and a bounded number of inactive bridge candidates avoid unbounded capabilities", () => {
  const views = createProposalViews(parentOrigin), view = views.open("d".repeat(24), child);
  assert.deepEqual(views.open("d".repeat(24), child), view);
  assert.throws(() => views.open("e".repeat(24), child), error => error.status === 409);
  for (let i = 0; i < 8; i++) views.render(new URL(view.url).pathname);
  assert.throws(() => views.render(new URL(view.url).pathname), error => error.status === 429);
});

function bootstrap(fetch) {
  const views = createProposalViews(parentOrigin), view = views.open("d".repeat(24), child), html = views.render(new URL(view.url).pathname).html;
  const listeners = {}, attributes = new Map(), status = { textContent: "" }, frame = { hidden: true }, retry = { hidden: true,
    setAttribute: (name, value) => attributes.set(name, value), removeAttribute: name => attributes.delete(name),
    addEventListener: (name, fn) => { listeners[`button:${name}`] = fn; } };
  const parent = { postMessage() {} }, window = { parent, addEventListener: (name, fn) => { listeners[name] = fn; } };
  require("node:vm").runInNewContext(/<script nonce="[^"]+">([\s\S]*?)<\/script>/.exec(html)[1], {
    window, document: { getElementById: id => ({ sketch: frame, status, retry })[id] }, fetch, URL, AbortController,
    setTimeout: fn => setTimeout(fn, 10), clearTimeout,
  });
  const event = { source: parent, origin: parentOrigin, data: { channel: "design-workshop-embed", version: 1, command: "activate", leaseId: child.leaseId, activationKey: view.activationKey } };
  return { listeners, event, attributes, status, frame, retry };
}
const tick = () => new Promise(resolve => setImmediate(resolve));
test("bridge timeout releases retry, retains its first capability and bounds uncertain attempts", async () => {
  const calls = [], ui = bootstrap(async (path, input) => {
    calls.push({ path, body: input.body });
    return new Promise((resolve, reject) => input.signal.addEventListener("abort", () => reject(new Error("timeout")), { once: true }));
  });
  ui.listeners.message({ ...ui.event, source: {} }); assert.equal(calls.length, 0);
  ui.listeners.message(ui.event); assert.equal(ui.attributes.get("aria-busy"), "true");
  await new Promise(resolve => setTimeout(resolve, 25));
  assert.equal(ui.retry.hidden, false); assert.equal(ui.attributes.has("aria-busy"), false);
  ui.listeners.message({ ...ui.event, data: { ...ui.event.data, activationKey: "f".repeat(64) } }); assert.equal(calls.length, 1);
  for (let i = 0; i < 3; i++) { ui.listeners["button:click"](); await new Promise(resolve => setTimeout(resolve, 25)); }
  assert.equal(calls.length, 3); assert.equal(new Set(calls.map(call => call.body)).size, 1);
  assert.equal(ui.retry.hidden, true); assert.match(ui.status.textContent, /Åpne verkstedet på nytt/);
});
test("bridge recovers a lost reply without a new GET and stops on a revoked capability", async () => {
  const calls = [], ui = bootstrap(async (path, input) => {
    calls.push({ path, body: input.body }); if (calls.length === 1) throw new Error("response lost");
    return { ok: true, json: async () => child };
  });
  ui.listeners.message(ui.event); await tick(); assert.equal(ui.retry.hidden, false);
  ui.listeners["button:click"](); await tick();
  assert.equal(ui.frame.src, child.url); assert.equal(ui.frame.hidden, false);
  assert.equal(new Set(calls.map(call => call.body)).size, 1); assert(calls.every(call => call.path === "/proposal/activate"));
  let revokedCalls = 0;
  const revoked = bootstrap(async () => { revokedCalls++; return { ok: false, status: 410 }; });
  revoked.listeners.message(revoked.event); await tick(); revoked.listeners["button:click"](); await tick();
  assert.equal(revokedCalls, 1); assert.equal(revoked.retry.hidden, true); assert.match(revoked.status.textContent, /avsluttet/);
});
