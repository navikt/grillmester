"use strict";

const test = require("node:test"), assert = require("node:assert/strict"), http = require("node:http");
const { EventEmitter, once } = require("node:events");
const { spawn } = require("node:child_process");
const { createInterface } = require("node:readline");
const path = require("node:path"), os = require("node:os"), fs = require("node:fs");
const { listenLocal } = require("../scripts/local-ports.js");

const stop = server => new Promise(resolve => { server.close(resolve); server.closeAllConnections?.(); });
class Listener extends EventEmitter {
  constructor(ports) { super(); this.ports = ports; this.calls = []; this.listening = false; }
  listen(port, host) {
    this.calls.push({ port, host });
    const next = this.ports[this.calls.length - 1] ?? this.ports.at(-1);
    queueMicrotask(() => {
      if (typeof next === "string") this.emit("error", Object.assign(new Error("Bind failed"), { code: next }));
      else if (next === null) this.emit("close");
      else { this.port = next || port; this.listening = true; this.emit("listening"); }
    });
  }
  address() { return this.listening ? { port: this.port } : null; }
}
const unobserved = server => { for (const event of ["error", "listening", "close"]) assert.equal(server.listenerCount(event), 0); };

test("a listener binds an ephemeral port on real loopback by default", async t => {
  const server = http.createServer();
  t.after(() => stop(server));
  await listenLocal(server);
  assert.equal(server.address().address, "127.0.0.1");
  assert.ok(server.address().port > 0);
});

test("the host and an explicit port are used as given, in any valid range", async () => {
  for (const port of [19999, 20000, 25000, 29999, 30000]) {
    const server = new Listener([port]); await listenLocal(server, { port, host: "::1" });
    assert.deepEqual(server.calls, [{ port, host: "::1" }]); unobserved(server);
  }
});

test("bind failures are final and leave no observers behind", async () => {
  for (const [next, code] of [["EADDRINUSE", "EADDRINUSE"], ["EACCES", "EACCES"], [null, "ERR_LOCAL_LISTENER_CLOSED"]]) {
    const server = new Listener([next]);
    await assert.rejects(listenLocal(server), { code });
    assert.equal(server.calls.length, 1); assert.equal(server.listening, false); unobserved(server);
  }
});

test("invalid ports and a server that already listens are rejected before binding", async () => {
  for (const port of [-1, 65536, 1.5, "8080", null]) {
    const server = new Listener([0]);
    await assert.rejects(listenLocal(server, { port }), { code: "ERR_LOCAL_PORT_OPTIONS" });
    assert.equal(server.calls.length, 0);
  }
  const busy = new Listener([0]); busy.listening = true;
  await assert.rejects(listenLocal(busy), { code: "ERR_SERVER_ALREADY_LISTEN" });
  assert.equal(busy.calls.length, 0);
});

test("a sketch server accepts an explicit port in the formerly reserved range", { timeout: 10000 }, async t => {
  const project = fs.mkdtempSync(path.join(os.tmpdir(), "local-port-test-"));
  t.after(() => fs.rmSync(project, { recursive: true, force: true }));
  const probe = http.createServer();
  let port = 0;
  for (let candidate = 25000; candidate < 25100 && !port; candidate += 1) {
    try { await listenLocal(probe, { port: candidate }); port = candidate; } catch { /* Try the next port. */ }
  }
  assert.ok(port, "No free port in the probe range.");
  await stop(probe);
  const child = spawn(process.execPath, [path.resolve(__dirname, "../scripts/server.js"), "--project-dir", project, "--port", String(port)], { stdio: ["ignore", "pipe", "pipe"] });
  t.after(() => { if (child.exitCode === null) child.kill("SIGTERM"); });
  const [line] = await once(createInterface({ input: child.stdout }), "line");
  const started = JSON.parse(line);
  assert.equal(started.type, "server-started"); assert.equal(started.port, port);
  child.kill("SIGTERM"); await once(child, "close");
  assert.deepEqual(fs.readdirSync(project), []);
});
