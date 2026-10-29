"use strict";
const test = require("node:test"), assert = require("node:assert/strict");
const fs = require("node:fs"), os = require("node:os"), path = require("node:path"), http = require("node:http"), net = require("node:net"), crypto = require("node:crypto");
const { execFile, spawn, fork } = require("node:child_process"), { promisify } = require("node:util");
const run = promisify(execFile), helper = path.resolve(__dirname, "../scripts/app-runtime.js");
const runtime = require(helper), delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const supported = process.platform !== "win32";
async function until(check, timeout = 3500) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await check()) return; await delay(30); }
  assert.fail("The owned fixture did not reach its expected state in time.");
}
function alive(pid) { try { process.kill(pid, 0); return true; } catch (e) { if (e.code === "ESRCH") return false; throw e; } }
async function fixture(t, mode = "serve", ttl = 20) {
  const base = fs.mkdtempSync(path.join(process.platform === "darwin" ? "/tmp" : os.tmpdir(), "gm-run-"));
  const project = path.join(base, "project"); fs.mkdirSync(project);
  const temp = path.join(base, "tmp"); fs.mkdirSync(temp);
  const script = path.join(project, "demo.cjs"), ready = path.join(project, "ready.json");
  fs.writeFileSync(script, `const fs=require('node:fs'),http=require('node:http'),{spawn}=require('node:child_process');
const mode=process.argv[2];let descendant;
if(mode==='descendants'||mode==='exit-parent')descendant=spawn(process.execPath,['-e',"process.on('SIGTERM',()=>{});setInterval(()=>{},1000)"],{stdio:'ignore'});
const server=http.createServer((q,s)=>s.end('synthetic demo')).listen(0,'127.0.0.1',()=>{
 fs.writeFileSync(${JSON.stringify(ready + ".tmp")},JSON.stringify({pid:process.pid,parent:process.ppid,descendant:descendant?.pid,port:server.address().port,env:{demo:process.env.IS_DEMO_MODE,secret:process.env.EXAMPLE_SECRET,track:process.env.DO_NOT_TRACK}}));
 fs.renameSync(${JSON.stringify(ready + ".tmp")},${JSON.stringify(ready)});
 if(mode==='exit-parent')setTimeout(()=>process.exit(0),300);
 if(mode==='verbose')process.stdout.write('x'.repeat(3*1024*1024));
});`);
  const env = { PATH: process.env.PATH, TMPDIR: temp, EXAMPLE_SECRET: "synthetic-not-inherited" };
  const session = "test", args = ["--project-dir", project, "--session", session];
  const cli = async (op, extra = [], customEnv = {}) => {
    const result = await run(process.execPath, [helper, op, ...args, ...extra], { env: { ...env, ...customEnv }, timeout: 12000, maxBuffer: 32768 });
    return JSON.parse(result.stdout);
  };
  const startArgs = ["--ttl-seconds", String(ttl), "--env", "IS_DEMO_MODE=true", "--", process.execPath, script, mode];
  const hash = crypto.createHash("sha256").update(fs.realpathSync(project) + "\0" + session).digest("hex");
  const directory = path.join(fs.realpathSync(temp), "gm-app-" + process.getuid(), hash.slice(0,24));
  const record = () => JSON.parse(fs.readFileSync(path.join(directory, "state.json")));
  const info = () => JSON.parse(fs.readFileSync(ready));
  t.after(async () => {
    if (fs.existsSync(directory)) fs.chmodSync(directory, 0o700);
    try { await cli("stop"); } catch { /* A deliberately damaged record may be unqueryable. */ }
    // Every fixture has a short TTL; do not use arbitrary discovered PID kills.
    if (fs.existsSync(ready)) await until(() => !alive(info().pid), (ttl + 2) * 1000);
    fs.rmSync(base, { recursive: true, force: true });
  });
  return { cli, startArgs, base, project, env, args, ready, directory, record, info };
}
async function request(record, options = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request({ socketPath: record.socket, method: options.method || "GET", path: options.path || "/status",
      headers: { Host: "app-runtime.invalid", "X-App-Runtime-Key": record.token, "X-App-Runtime-Generation": record.generation, ...options.headers } }, res => {
      let text = ""; res.on("data", c => text += c); res.on("end", () => resolve({ status: res.statusCode, body: JSON.parse(text) }));
    }); req.on("error", reject); req.end(options.body);
  });
}

function privateReadRace(t, replace) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "gm-read-race-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const file = path.join(directory, "state.json"), opened = [], readLinks = [];
  fs.writeFileSync(file, JSON.stringify({ state: "stopping" }), { mode: 0o600 });
  const originalOpen = fs.openSync, originalRead = fs.readFileSync;
  t.mock.method(fs, "openSync", function (name, ...args) {
    if (name !== file) return Reflect.apply(originalOpen, this, [name, ...args]);
    if (opened.length) assert.throws(() => fs.fstatSync(opened.at(-1)), { code: "EBADF" }, "Close the old descriptor before reopening.");
    const fd = Reflect.apply(originalOpen, this, [name, ...args]);
    opened.push(fd);
    replace({ file, directory, attempt: opened.length });
    return fd;
  });
  t.mock.method(fs, "readFileSync", function (name, ...args) {
    if (typeof name === "number" && opened.includes(name)) readLinks.push(fs.fstatSync(name).nlink);
    return Reflect.apply(originalRead, this, [name, ...args]);
  });
  return { file, opened, readLinks, assertClosed() { for (const fd of opened) assert.throws(() => fs.fstatSync(fd), { code: "EBADF" }); } };
}

test("private record reads reopen after an atomic replacement without reading the detached inode", { skip: !supported }, t => {
  const f = privateReadRace(t, ({ file, attempt }) => {
    if (attempt !== 1) return;
    fs.writeFileSync(file + ".next", JSON.stringify({ state: "stopped" }), { mode: 0o600 });
    fs.renameSync(file + ".next", file);
  });
  assert.deepEqual(runtime.readPrivate(f.file), { state: "stopped" });
  assert.equal(f.opened.length, 2); assert.deepEqual(f.readLinks, [1]); f.assertClosed();
});

test("replacement records still reject symlinks, broad modes and hardlinks", { skip: !supported }, async t => {
  for (const kind of ["symlink", "mode", "hardlink"]) await t.test(kind, t => {
    const f = privateReadRace(t, ({ file, directory, attempt }) => {
      if (attempt !== 1) return;
      const target = path.join(directory, "replacement"), next = file + ".next";
      fs.writeFileSync(target, JSON.stringify({ state: "stopped" }), { mode: 0o600 });
      if (kind === "symlink") fs.symlinkSync(target, next);
      else if (kind === "hardlink") fs.linkSync(target, next);
      else { fs.chmodSync(target, 0o644); fs.renameSync(target, next); }
      fs.renameSync(next, file);
    });
    assert.throws(() => runtime.readPrivate(f.file), kind === "symlink" ? { code: "ELOOP" } : /owned private file/);
    assert.equal(f.opened.length, kind === "symlink" ? 1 : 2);
    assert.deepEqual(f.readLinks, []); f.assertClosed();
  });
});

test("an unsafe detached record fails before retrying its otherwise safe replacement", { skip: !supported }, t => {
  const f = privateReadRace(t, ({ file }) => {
    fs.writeFileSync(file + ".next", JSON.stringify({ state: "stopped" }), { mode: 0o600 });
    fs.renameSync(file + ".next", file);
  });
  fs.chmodSync(f.file, 0o644);
  assert.throws(() => runtime.readPrivate(f.file), /owned private file/);
  assert.equal(f.opened.length, 1); assert.deepEqual(f.readLinks, []); f.assertClosed();
});

test("continuous private record replacement stops after three closed descriptors", { skip: !supported }, t => {
  const f = privateReadRace(t, ({ file, attempt }) => {
    fs.writeFileSync(file + ".next", JSON.stringify({ revision: attempt }), { mode: 0o600 });
    fs.renameSync(file + ".next", file);
  });
  assert.throws(() => runtime.readPrivate(f.file), /record changed repeatedly.*Try the command again/);
  assert.equal(f.opened.length, 3); assert.deepEqual(f.readLinks, []); f.assertClosed();
});

test("short launcher exits, demo survives and repeated start reuses the owned runtime", { skip: !supported }, async t => {
  const f = await fixture(t); const started = Date.now();
  const state = await f.cli("start", f.startArgs);
  assert.equal(state.state, "running"); assert.ok(Date.now() - started < 5000);
  assert.equal("token" in state, false); assert.equal("socket" in state, false);
  await until(() => fs.existsSync(f.ready)); const info = f.info();
  assert.equal(info.env.demo, "true"); assert.equal(info.env.secret, undefined); assert.equal(info.env.track, "1");
  const again = await f.cli("start", f.startArgs); assert.equal(again.reused, true);
  assert.equal(f.info().pid, info.pid); assert.equal((await f.cli("status")).state, "running");
  await assert.rejects(f.cli("start", ["--", process.execPath, "-e", "setInterval(()=>{},1000)"]), /already owns another command/);
  assert.equal((await f.cli("stop")).state, "stopped"); await until(() => !alive(info.pid));
  assert.equal((await f.cli("status")).reason, "requested");
  // An explicit new start works, but stopping never restarts it by itself.
  await delay(150); assert.equal(alive(info.pid), false);
  fs.unlinkSync(f.ready); assert.equal((await f.cli("start", f.startArgs)).state, "running");
  await until(() => fs.existsSync(f.ready)); assert.notEqual(f.info().pid, info.pid);
});

test("private control rejects browser, malformed capability, generation and command requests without crashing", { skip: !supported }, async t => {
  const f = await fixture(t); await f.cli("start", f.startArgs); const r = f.record();
  assert.equal(fs.statSync(r.socket).mode & 0o777, 0o600);
  for (const options of [
    { headers: { Origin: "http://localhost" } }, { headers: { Host: "localhost" } },
    { headers: { "X-App-Runtime-Key": "é".repeat(64) } }, { headers: { "X-App-Runtime-Key": "0".repeat(64) } },
    { headers: { "X-App-Runtime-Generation": "0".repeat(64) } },
    { method: "POST", path: "/exec" }, { method: "POST", path: "/stop", headers: { "Content-Length": "2" }, body: "{}" }
  ]) assert.equal((await request(r, options)).status, 403);
  assert.equal((await f.cli("status")).state, "running");
  const other = await run(process.execPath, [helper, "stop", "--project-dir", f.project, "--session", "other"], {env:f.env});
  assert.equal(JSON.parse(other.stdout).owned, false); assert.equal((await f.cli("status")).state, "running");
});

test("stop reaps ordinary descendants, including children ignoring TERM", { skip: !supported }, async t => {
  const f = await fixture(t, "descendants"); await f.cli("start", f.startArgs); await until(() => fs.existsSync(f.ready));
  const info = f.info(); assert.ok(alive(info.descendant));
  await f.cli("stop"); await until(() => !alive(info.pid) && !alive(info.descendant));
});

test("natural command exit cleans its descendants and never restarts", { skip: !supported }, async t => {
  const f = await fixture(t, "exit-parent"); await f.cli("start", f.startArgs); await until(() => fs.existsSync(f.ready));
  const info = f.info(); await until(() => !alive(info.pid) && !alive(info.descendant));
  const state = await f.cli("status"); assert.equal(state.state, "stopped"); assert.equal(state.reason, "command-exited");
});

test("TTL stops an owned demo and logs remain private and bounded", { skip: !supported }, async t => {
  const f = await fixture(t, "verbose", 2); const state = await f.cli("start", f.startArgs);
  await until(() => fs.existsSync(f.ready)); await delay(200);
  const stat = fs.statSync(state.logFile); assert.ok(stat.size > 0 && stat.size <= 1024 * 1024); assert.equal(stat.mode & 0o777, 0o600);
  await until(async () => !alive(f.info().pid) && (await f.cli("status")).state === "stopped", 4000); assert.equal((await f.cli("status")).reason, "expired");
});

test("journal failures do not prevent owned-group shutdown", { skip: !supported }, async t => {
  const f = await fixture(t, "descendants", 5); await f.cli("start", f.startArgs); await until(() => fs.existsSync(f.ready));
  const r = f.record(), info = f.info(); fs.chmodSync(f.directory, 0o500);
  assert.equal((await request(r, { method: "POST", path: "/stop" })).status, 200);
  await until(() => !alive(info.pid) && !alive(info.descendant)); fs.chmodSync(f.directory, 0o700);
});

test("private state rejects symlinks, hardlinks and broad modes; forged PID never controls another process", { skip: !supported }, async t => {
  const f = await fixture(t); await f.cli("start", f.startArgs); await until(() => fs.existsSync(f.ready));
  const recordPath = path.join(f.directory, "state.json"), contents = fs.readFileSync(recordPath);
  fs.chmodSync(f.directory, 0o755); await assert.rejects(f.cli("status"), /private directory/); fs.chmodSync(f.directory, 0o700);
  fs.chmodSync(recordPath, 0o644); await assert.rejects(f.cli("status"), /private file/); fs.chmodSync(recordPath, 0o600);
  const hardlink = path.join(f.base, "linked"); fs.linkSync(recordPath, hardlink); await assert.rejects(f.cli("status"), /private file/); fs.unlinkSync(hardlink);
  const target = path.join(f.base, "elsewhere"); fs.renameSync(recordPath, target); fs.symlinkSync(target, recordPath);
  await assert.rejects(f.cli("stop")); fs.unlinkSync(recordPath); fs.renameSync(target, recordPath);
  const canary = spawn(process.execPath, ["-e", "setInterval(()=>{},1000)"], { stdio:"ignore" });
  t.after(() => canary.kill()); await new Promise(resolve => canary.once("spawn", resolve));
  const forged = JSON.parse(contents); forged.pid = canary.pid; fs.writeFileSync(recordPath, JSON.stringify(forged));
  await f.cli("stop"); assert.ok(alive(canary.pid));
});

test("an expired interrupted startup lease can be cleared without signalling any process", { skip: !supported }, async t => {
  const f = await fixture(t); await f.cli("start", f.startArgs); await f.cli("stop");
  const lock = path.join(f.directory,"starting"); fs.mkdirSync(lock,{mode:0o700});
  fs.writeFileSync(path.join(lock,"lease.json"), JSON.stringify({token:"a".repeat(64),expiresAt:Date.now()-1}), {mode:0o600});
  await assert.rejects(f.cli("start", f.startArgs), /start is already in progress/);
  assert.equal((await f.cli("stop")).clearedStarting,true); assert.equal(fs.existsSync(lock),false);
});

test("spawn failure returns promptly and leaves no controller or waiting tool", { skip: !supported }, async t => {
  const f = await fixture(t); await assert.rejects(f.cli("start", ["--", path.join(f.project,"absent-command")]), /could not start/);
  assert.equal(fs.existsSync(path.join(f.directory,"c")),false);
  assert.equal((await f.cli("status")).state,"stopped");
});

test("demo flags require explicit forwarding and secret/preload overrides are refused", () => {
  const previous = process.env.IS_DEMO_MODE; process.env.IS_DEMO_MODE="true";
  try {
    assert.throws(() => runtime.parse(["start","--session","test","--","node","demo.cjs"]), /explicitly/);
    assert.equal(runtime.parse(["start","--session","test","--env","IS_DEMO_MODE=true","--","node","demo.cjs"]).environment.IS_DEMO_MODE,"true");
  } finally { if(previous===undefined)delete process.env.IS_DEMO_MODE;else process.env.IS_DEMO_MODE=previous; }
  for (const key of ["API_TOKEN","PASSWORD","NODE_OPTIONS","HOME","LD_PRELOAD"]) {
    assert.throws(() => runtime.parse(["start","--session","test","--env",key+"=example","--","node"]), /non-secret/);
  }
});


test("a launcher disappearing before handoff leaves no app or ordinary descendants", { skip: !supported }, async t => {
  const f = await fixture(t,"descendants",5);
  // Prepare only this fixture's private directory and a valid startup lease.
  fs.mkdirSync(path.dirname(f.directory),{mode:0o700}); fs.mkdirSync(f.directory,{mode:0o700});
  const lock=path.join(f.directory,"starting"); fs.mkdirSync(lock,{mode:0o700});
  const lease={token:"b".repeat(64),expiresAt:Date.now()+10000};
  fs.writeFileSync(path.join(lock,"lease.json"),JSON.stringify(lease),{mode:0o600});
  const binding={project:fs.realpathSync(f.project),directory:f.directory,binding:crypto.createHash("sha256").update(fs.realpathSync(f.project)+"\0test").digest("hex")};
  const supervisor=fork(helper,["--supervise"],{detached:true,stdio:["ignore","ignore","ignore","ipc"],env:f.env,execArgv:[]});
  supervisor.send({binding,command:[process.execPath,path.join(f.project,"demo.cjs"),"descendants"],environment:{IS_DEMO_MODE:"true"},ttlSeconds:5,recipe:"c".repeat(64),lease});
  await new Promise((resolve,reject)=>{supervisor.once("message",resolve);supervisor.once("error",reject);});
  await until(()=>fs.existsSync(f.ready)); const info=f.info();
  supervisor.disconnect(); supervisor.unref();
  await until(()=>!alive(info.pid)&&!alive(info.descendant));
  await until(async()=>(await f.cli("status")).state==="stopped");
  assert.equal((await f.cli("status")).reason,"startup-abandoned");
});

test("a symlink runtime root is rejected without touching its target", { skip: !supported }, async t => {
  const f=await fixture(t), target=path.join(f.base,"target"); fs.mkdirSync(target,{mode:0o700});
  fs.symlinkSync(target,path.dirname(f.directory));
  await assert.rejects(f.cli("start",f.startArgs),/private directory/);
  assert.deepEqual(fs.readdirSync(target),[]);
});


test("explicit stop clears an expired empty or partial startup lease, retaining unknown files", { skip: !supported }, async t => {
  const f=await fixture(t); await f.cli("start",f.startArgs); await f.cli("stop");
  const lock=path.join(f.directory,"starting"), old=new Date(Date.now()-20000);
  for (const partial of [false,true]) {
    fs.mkdirSync(lock,{mode:0o700});
    if(partial)fs.writeFileSync(path.join(lock,".record-"+"d".repeat(64)),"{",{mode:0o600});
    fs.utimesSync(lock,old,old);
    assert.equal((await f.cli("stop")).clearedStarting,true);
    assert.equal(fs.existsSync(lock),false);
  }
  fs.mkdirSync(lock,{mode:0o700}); fs.writeFileSync(path.join(lock,"unknown"),"keep",{mode:0o600}); fs.utimesSync(lock,old,old);
  await assert.rejects(f.cli("stop"),/unexpected files/); assert.equal(fs.readFileSync(path.join(lock,"unknown"),"utf8"),"keep");
});


test("reading a FIFO runtime record refuses promptly without creating or consuming data", { skip: !supported }, async t => {
  const f = await fixture(t);
  fs.mkdirSync(path.dirname(f.directory), { mode: 0o700 }); fs.mkdirSync(f.directory, { mode: 0o700 });
  const recordPath = path.join(f.directory, "state.json");
  await run("mkfifo", ["-m", "600", recordPath]);
  const result = await run(process.execPath, [helper, "status", ...f.args], { env: f.env, timeout: 1500 })
    .then(value => ({ value }), error => ({ error }));
  const retained = fs.lstatSync(recordPath).isFIFO(); fs.unlinkSync(recordPath);
  assert.equal(result.error?.killed, false, "Reading an unsafe record must fail before the caller timeout.");
  assert.match(result.error.stderr, /owned private file/);
  assert.ok(retained);
});

test("runtime capabilities travel only over the pinned private Unix socket", { skip: !supported }, async t => {
  const f = await fixture(t); await f.cli("start", f.startArgs); const record = f.record();
  let networkConnections = 0;
  const listener = net.createServer(socket => { networkConnections++; socket.destroy(); });
  await new Promise(resolve => listener.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise(resolve => listener.close(resolve)));
  const poisoned = { ...record, hostname: "127.0.0.1", host: "127.0.0.1", port: listener.address().port,
    protocol: "http:", href: `http://127.0.0.1:${listener.address().port}/capture` };
  assert.equal((await runtime.request(poisoned, "status")).state, "running");
  assert.equal(networkConnections, 0, "Record data cannot select a network destination.");
  const recordPath = path.join(f.directory, "state.json");
  fs.writeFileSync(recordPath, JSON.stringify({ ...record, socket: path.join(f.base, "other-socket") }));
  await assert.rejects(f.cli("status"), /does not match this project and session/);
  fs.writeFileSync(recordPath, JSON.stringify(record));
});

test("a crashed controller gives bounded recovery guidance and never reuses stopping state", { skip: !supported }, async t => {
  const f = await fixture(t, "serve", 5);
  fs.mkdirSync(path.dirname(f.directory), { mode: 0o700 }); fs.mkdirSync(f.directory, { mode: 0o700 });
  const lock = path.join(f.directory, "starting"); fs.mkdirSync(lock, { mode: 0o700 });
  const lease = { token: "e".repeat(64), expiresAt: Date.now() + 10000 };
  fs.writeFileSync(path.join(lock, "lease.json"), JSON.stringify(lease), { mode: 0o600 });
  const binding = { project: fs.realpathSync(f.project), directory: f.directory,
    binding: crypto.createHash("sha256").update(fs.realpathSync(f.project) + "\0test").digest("hex") };
  const command = [process.execPath, path.join(f.project, "demo.cjs"), "serve"], environment = { IS_DEMO_MODE: "true" }, ttlSeconds = 5;
  const recipe = crypto.createHash("sha256").update(JSON.stringify({ command, environment, ttlSeconds })).digest("hex");
  const supervisor = fork(helper, ["--supervise"], { detached: true, stdio: ["ignore", "ignore", "ignore", "ipc"], env: f.env, execArgv: [] });
  try {
    supervisor.send({ binding, command, environment, ttlSeconds, recipe, lease });
    await new Promise((resolve, reject) => { supervisor.once("message", resolve); supervisor.once("error", reject); });
    await until(() => fs.existsSync(f.ready));
    await new Promise((resolve, reject) => supervisor.send({ event: "handoff" }, error => error ? reject(error) : resolve()));
    fs.rmSync(lock, { recursive: true });
    const exited = new Promise(resolve => supervisor.once("exit", resolve));
    // This handle owns the newly forked group; no PID from a runtime file is trusted.
    process.kill(-supervisor.pid, "SIGKILL"); await exited;
    await until(() => !alive(f.info().pid));
    const status = await f.cli("status"); assert.equal(status.state, "unreachable");
    assert.match(status.note, /new --session key/);
    const stopped = await f.cli("stop"); assert.equal(stopped.state, "unreachable");
    assert.match(stopped.note, /no unrelated process was signalled/); assert.equal(JSON.stringify(stopped).includes(f.base), false);
    await assert.rejects(f.cli("start", f.startArgs), /new --session key/);
    const recordPath = path.join(f.directory, "state.json"), stale = f.record();
    fs.writeFileSync(recordPath, JSON.stringify({ ...stale, state: "stopping" }));
    await assert.rejects(f.cli("start", f.startArgs), /still stopping/);
    assert.equal((await f.cli("stop")).state, "unreachable");
  } finally {
    if (supervisor.exitCode === null && supervisor.signalCode === null) process.kill(-supervisor.pid, "SIGKILL");
    supervisor.unref();
  }
});
