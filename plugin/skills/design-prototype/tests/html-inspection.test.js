"use strict";
const test = require("node:test"), assert = require("node:assert/strict"), http = require("node:http");
const { createHtmlInspection, MAX_SNAPSHOT_BYTES } = require("../scripts/html-inspection.js");
const snapshot = { html: "<h1>Immutable</h1>", csp: "default-src 'none'; frame-ancestors 'self'", screen: "a".repeat(32) };
const request = (url, options = {}) => new Promise((resolve, reject) => {
  const req = http.request(url, options, res => { let text = ""; res.on("data", chunk => { text += chunk; }); res.on("end", () => resolve({ status: res.statusCode, headers: res.headers, text })); });
  req.on("error", reject); req.end();
});
test("inspection is a separate exact GET capability with no control or filesystem routes", async t => {
  const owner = createHtmlInspection(); t.after(() => owner.revokeAll());
  const opened = await owner.open(snapshot), url = new URL(opened.url);
  assert.match(opened.inspectionId, /^[a-f0-9]{32}$/); assert.equal(url.hostname, "127.0.0.1");
  const response = await request(url);
  assert.equal(response.status, 200); assert.equal(response.text, snapshot.html);
  assert.equal(response.headers["cache-control"], "no-store"); assert.equal(response.headers["referrer-policy"], "no-referrer");
  assert.match(response.headers["content-security-policy"], /frame-ancestors 'none'; sandbox allow-scripts/);
  assert.equal(response.headers["access-control-allow-origin"], undefined); assert.equal(response.headers["set-cookie"], undefined);
  for (const method of ["POST", "PUT", "DELETE", "OPTIONS", "HEAD"]) assert.equal((await request(url, { method })).status, 404);
  for (const pathname of ["/", "/comments", "/workspace/editor/save", "/preview", "/snapshot/wrong", url.pathname + "?token=anything", "/../server.js"]) {
    const altered = new URL(url); altered.pathname = pathname; assert.equal((await request(altered)).status, 404);
  }
  for (const host of ["localhost:" + url.port, "outside.invalid", url.host + "."]) assert.equal((await request(url, { headers: { Host: host } })).status, 404);
  assert.equal((await request(url, { headers: ["Host", url.host, "Host", url.host] })).status, 404);
  assert.equal((await request(url, { headers: { "Content-Length": "1" } })).status, 404);
  await assert.rejects(owner.close("b".repeat(32)), error => error.status === 404);
  assert.equal((await request(url)).status, 200, "An unrelated inspection ID cannot revoke the owner.");
});
test("replacement, expiry and explicit close revoke only owned immutable snapshots", async t => {
  const a = createHtmlInspection(), b = createHtmlInspection(); t.after(() => Promise.all([a.revokeAll(), b.revokeAll()]));
  const first = await a.open(snapshot), other = await b.open(snapshot), next = await a.open({ ...snapshot, html: "<h1>Second</h1>" });
  await assert.rejects(request(first.url)); assert.equal((await request(next.url)).text, "<h1>Second</h1>");
  await assert.rejects(a.close(other.inspectionId), error => error.status === 404);
  assert.equal((await request(other.url)).status, 200);
  await a.close(next.inspectionId); await assert.rejects(request(next.url));
  const short = createHtmlInspection({ ttlMs: 30 }); t.after(() => short.revokeAll());
  const expiring = await short.open(snapshot); await new Promise(resolve => setTimeout(resolve, 60));
  await assert.rejects(request(expiring.url));
});
test("close wins a pending mint, oversized HTML never starts an inspection", async t => {
  const owner = createHtmlInspection(); t.after(() => owner.revokeAll());
  const pending = owner.open(snapshot); await owner.revokeAll();
  await assert.rejects(pending, error => error.status === 410);
  await assert.rejects(owner.open({ ...snapshot, html: "x".repeat(MAX_SNAPSHOT_BYTES + 1) }), error => error.status === 413);
  const good = await owner.open(snapshot); assert.equal((await request(good.url)).status, 200);
});
