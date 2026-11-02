"use strict";

const test = require("node:test"), assert = require("node:assert/strict"), http = require("node:http");
const { EventEmitter } = require("node:events");
const { spawnSync } = require("node:child_process");
const path = require("node:path"), os = require("node:os"), fs = require("node:fs");
const { listenLocal, isApplicationPort, MAX_BIND_ATTEMPTS } = require("../scripts/local-ports.js");

const stop = server => new Promise(resolve => { server.close(resolve); server.closeAllConnections?.(); });
class Listener extends EventEmitter {
  constructor(ports) { super(); this.ports = ports; this.calls = []; this.closes = 0; this.listening = false; }
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
  close(callback) { this.listening = false; this.closes += 1; queueMicrotask(() => { this.emit("close"); callback?.(); }); }
  closeAllConnections() {}
}

test("preview and control listeners occupy disjoint port ranges on real loopback", async t => {
  const preview = http.createServer(), control = http.createServer();
  t.after(() => Promise.all([stop(preview), stop(control)]));
  await listenLocal(preview, { role: "application" }); await listenLocal(control, { role: "control" });
  assert.equal(preview.address().address, "127.0.0.1"); assert.equal(control.address().address, "127.0.0.1");
  assert.equal(isApplicationPort(preview.address().port), true);
  assert.equal(isApplicationPort(control.address().port), false);
});

test("an actual former preview port is closed and rejected for a later control listener", async t => {
  const preview = http.createServer(), control = http.createServer();
  t.after(() => Promise.all([stop(preview), stop(control)]));
  await listenLocal(preview, { role: "application" });
  const previousPort = preview.address().port; await stop(preview);
  const originalListen = control.listen; let attempts = 0;
  control.listen = function (port, host) { return originalListen.call(this, attempts++ === 0 ? previousPort : port, host); };
  await listenLocal(control, { role: "control" });
  assert.ok(attempts >= 2); assert.equal(isApplicationPort(control.address().port), false);
  await listenLocal(preview, { role: "application", port: previousPort });
  assert.equal(preview.address().port, previousPort, "The excluded attempt leaves no listener on the former app origin.");
});

test("control checks the actual ephemeral port and closes excluded binds before returning", async () => {
  const server = new Listener([20000, 29999, 42000]);
  await listenLocal(server, { role: "control" });
  assert.equal(server.address().port, 42000); assert.equal(server.closes, 2);
  assert.deepEqual(server.calls, Array.from({ length: 3 }, () => ({ port: 0, host: "127.0.0.1" })));
  for (const event of ["error", "listening", "close"]) assert.equal(server.listenerCount(event), 0);
});

test("excluded control binds and occupied preview ports have bounded retries", async () => {
  const control = new Listener([25000]), preview = new Listener(["EADDRINUSE"]);
  for (const [server, role] of [[control, "control"], [preview, "application"]]) {
    await assert.rejects(listenLocal(server, { role }), { code: "ERR_LOCAL_PORT_EXHAUSTED" });
    assert.equal(server.calls.length, MAX_BIND_ATTEMPTS); assert.equal(server.listening, false);
    for (const event of ["error", "listening", "close"]) assert.equal(server.listenerCount(event), 0);
  }
  assert.equal(control.closes, MAX_BIND_ATTEMPTS);
  assert.equal(new Set(preview.calls.map(call => call.port)).size, MAX_BIND_ATTEMPTS);
  assert.ok(preview.calls.every(call => isApplicationPort(call.port)));
});

test("only occupied dynamic preview ports retry; close and permission failures remain failures", async () => {
  const preview = new Listener(["EADDRINUSE", 0]); await listenLocal(preview, { role: "application" });
  assert.equal(preview.calls.length, 2); assert.equal(isApplicationPort(preview.address().port), true);
  for (const [next, code] of [["EACCES", "EACCES"], [null, "ERR_LOCAL_LISTENER_CLOSED"]]) {
    const server = new Listener([next]);
    await assert.rejects(listenLocal(server, { role: "application" }), { code });
    assert.equal(server.calls.length, 1); assert.equal(server.listening, false);
    for (const event of ["error", "listening", "close"]) assert.equal(server.listenerCount(event), 0);
  }
  const explicit = new Listener(["EADDRINUSE"]);
  await assert.rejects(listenLocal(explicit, { role: "application", port: 25000 }), { code: "EADDRINUSE" });
  assert.equal(explicit.calls.length, 1);
});

test("explicit ports are validated before bind and are not silently moved", async () => {
  for (const port of [20000, 25000, 29999]) {
    const server = new Listener([]);
    await assert.rejects(listenLocal(server, { role: "control", port }), { code: "ERR_LOCAL_PORT_ROLE" });
    assert.equal(server.calls.length, 0);
  }
  for (const port of [19999, 30000]) {
    const server = new Listener([port]); await listenLocal(server, { role: "control", port });
    assert.deepEqual(server.calls, [{ port, host: "127.0.0.1" }]);
  }
  const wrong = new Listener([25000]);
  await assert.rejects(listenLocal(wrong, { role: "control", port: 42000 }), { code: "ERR_LOCAL_PORT_ROLE" });
  assert.equal(wrong.closes, 1); assert.equal(wrong.listening, false);
});

test("standalone sketches reject reserved explicit ports without creating session state", () => {
  const project = fs.mkdtempSync(path.join(os.tmpdir(), "local-port-test-"));
  try {
    const result = spawnSync(process.execPath, [path.resolve(__dirname, "../scripts/server.js"), "--project-dir", project, "--port", "25000"], { encoding: "utf8", timeout: 5000 });
    assert.equal(result.status, 2); assert.match(result.stderr, /reserved for application previews/);
    assert.deepEqual(fs.readdirSync(project), []);
  } finally { fs.rmSync(project, { recursive: true, force: true }); }
});
