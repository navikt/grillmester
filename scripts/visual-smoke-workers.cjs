"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { createApplicationServer } = require("../plugin/skills/design-prototype/scripts/application-server.js");

// A real app worker survives its listener. Force its port to be offered to a
// later control surface; the listener must reject that origin before use.
// Only booleans are captured: no control key or private address enters output.
async function checkWorkerOriginIsolation({ browser, root }) {
  const cleanups = [], observations = [];
  let originalListen;
  async function listen(handler) {
    const server = http.createServer(handler), sockets = new Set();
    server.on("connection", socket => { sockets.add(socket); socket.once("close", () => sockets.delete(socket)); });
    await new Promise((resolve, reject) => {
      server.once("error", reject); server.listen(0, "127.0.0.1", resolve);
    });
    cleanups.push(async () => { for (const socket of sockets) socket.destroy(); await new Promise(resolve => server.close(resolve)); });
    return `http://127.0.0.1:${server.address().port}`;
  }
  try {
    const sink = await listen((request, response) => {
      const chunks = []; let size = 0;
      request.on("data", chunk => { size += chunk.length; if (size <= 1024) chunks.push(chunk); else request.destroy(); });
      request.on("end", () => {
        try { observations.push(JSON.parse(Buffer.concat(chunks))); } catch { /* No credential output on malformed evidence. */ }
        response.end("ok");
      });
    });
    const worker = `self.addEventListener("install", e => e.waitUntil(self.skipWaiting()));
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => {
  const path = new URL(e.request.url).pathname;
  if (path === "/worker-proof") { e.respondWith(new Response("worker-active")); return; }
  if (path.startsWith("/browser/")) e.respondWith((async () => {
    const response = await fetch(e.request), html = await response.clone().text();
    const match = /window\\.__designApplication = (.*);/.exec(html);
    let controlTokenObserved = false;
    try { controlTokenObserved = typeof JSON.parse(match[1]).token === "string"; } catch {}
    await fetch(${JSON.stringify(sink)}, { method: "POST", mode: "no-cors", body: JSON.stringify({ controlTokenObserved }) });
    return response;
  })());
});`;
    const upstream = await listen((request, response) => {
      if (request.url.split("?")[0] === "/worker.js") {
        response.setHeader("Content-Type", "application/javascript"); response.end(worker); return;
      }
      response.setHeader("Content-Type", "text/html"); response.end("<!doctype html><h1>Worker fixture</h1>");
    });
    async function application(name) {
      const projectDir = path.join(root, "worker-isolation", name); fs.mkdirSync(projectDir, { recursive: true });
      const server = createApplicationServer({ projectDir, application: { name, url: upstream } });
      cleanups.push(() => server.close()); return server;
    }
    const first = await application("first"), opened = await first.command("openView");
    const context = await browser.newContext({ serviceWorkers: "allow" }); cleanups.push(() => context.close());
    const page = await context.newPage(); page.setDefaultTimeout(15000);
    await page.goto(opened.url);
    const frame = page.frameLocator("#app-preview");
    await frame.getByRole("heading", { name: "Worker fixture", exact: true }).waitFor();
    const oldOrigin = await frame.locator("body").evaluate(async () => {
      await Promise.race([
        (async () => {
          await navigator.serviceWorker.register("/worker.js", { scope: "/" });
          await navigator.serviceWorker.ready;
          if (!navigator.serviceWorker.controller) await new Promise(resolve => navigator.serviceWorker.addEventListener("controllerchange", resolve, { once: true }));
        })(),
        new Promise((_, reject) => setTimeout(() => reject(new Error("The fixture worker did not activate.")), 8000)),
      ]);
      if (await (await fetch("/worker-proof")).text() !== "worker-active") throw new Error("The fixture worker did not intercept its own app.");
      return location.origin;
    });
    const oldPort = Number(new URL(oldOrigin).port);
    assert(oldPort >= 20000 && oldPort <= 29999, "App workers must stay in the reserved preview port range");
    await first.close(); await page.close();
    const second = await application("second");
    originalListen = http.Server.prototype.listen;
    let offeredOldPort = false;
    http.Server.prototype.listen = function (...args) {
      if (!offeredOldPort && args[0] === 0 && args[1] === "127.0.0.1") {
        offeredOldPort = true; args[0] = oldPort;
      }
      return originalListen.apply(this, args);
    };
    let reopened;
    try { reopened = await second.command("openView"); }
    finally { http.Server.prototype.listen = originalListen; originalListen = null; }
    assert(offeredOldPort, "The operating-system port offer must exercise the reserved-port rejection");
    const controlPort = Number(new URL(reopened.url).port);
    assert(controlPort < 20000 || controlPort > 29999, "A control surface must never inherit an app worker origin");
    assert.notEqual(new URL(reopened.url).origin, oldOrigin);
    const next = await context.newPage(); next.setDefaultTimeout(15000); await next.goto(reopened.url);
    await next.frameLocator("#app-preview").getByRole("heading", { name: "Worker fixture", exact: true }).waitFor();
    assert.equal(await next.evaluate(() => navigator.serviceWorker.controller !== null), false, "The control document must not be owned by an app worker");
    assert.deepEqual(observations, [], "No previous app worker may read the control opening response");
  } finally {
    if (originalListen) http.Server.prototype.listen = originalListen;
    const failures = [];
    for (const cleanup of cleanups.reverse()) {
      try { await cleanup(); } catch (error) { failures.push(error); }
    }
    if (failures.length) throw new AggregateError(failures, "The worker-isolation fixture could not finish cleanup.");
  }
}

module.exports = { checkWorkerOriginIsolation };
