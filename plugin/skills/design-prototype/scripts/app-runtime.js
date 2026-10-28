#!/usr/bin/env node
"use strict";

// A short ordinary shell command owns this launcher. Consumer code inherits
// that shell's sandbox; the canvas extension never launches consumer commands.
const fs = require("node:fs"), path = require("node:path"), os = require("node:os");
const http = require("node:http"), crypto = require("node:crypto");
const { fork, spawn } = require("node:child_process");
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const fail = (condition, message) => { if (!condition) throw new Error(message); };
const hash = value => crypto.createHash("sha256").update(value).digest("hex");
const secret = () => crypto.randomBytes(32).toString("hex");
const uid = () => process.getuid();
const cleanEnvironment = () => Object.fromEntries(Object.entries(process.env).filter(([key]) =>
  ["PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TMPDIR", "SYSTEMROOT", "WINDIR"].includes(key)));
const forbiddenEnvironment = key => /TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH|COOKIE|PRIVATE|CERT|API_KEY/.test(key)
  || /^(?:HOME|NODE_OPTIONS|NODE_PATH|LD_.*|DYLD_.*)$/.test(key);

function privateDirectory(directory, create = false) {
  if (create) { try { fs.mkdirSync(directory, { mode: 0o700 }); } catch (error) { if (error.code !== "EEXIST") throw error; } }
  const stat = fs.lstatSync(directory);
  fail(stat.isDirectory() && !stat.isSymbolicLink() && stat.uid === uid() && (stat.mode & 0o077) === 0,
    "The runtime directory is not an owned private directory.");
  return stat;
}
function readPrivate(file) {
  const fd = fs.openSync(file, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
  try {
    const stat = fs.fstatSync(fd);
    fail(stat.isFile() && stat.nlink === 1 && stat.uid === uid() && (stat.mode & 0o077) === 0 && stat.size <= 16384,
      "The runtime record is not an owned private file.");
    return JSON.parse(fs.readFileSync(fd, "utf8"));
  } finally { fs.closeSync(fd); }
}
function writePrivate(directory, name, value) {
  privateDirectory(directory);
  const temporary = path.join(directory, ".record-" + secret());
  const fd = fs.openSync(temporary, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_NOFOLLOW, 0o600);
  try {
    try { fs.writeFileSync(fd, JSON.stringify(value) + "\n"); fs.fsyncSync(fd); }
    finally { fs.closeSync(fd); }
    fs.renameSync(temporary, path.join(directory, name));
  } finally { try { fs.unlinkSync(temporary); } catch (error) { if (error.code !== "ENOENT") throw error; } }
}
function location(projectDir, session, create = false) {
  fail(process.platform !== "win32", "This runtime helper currently supports macOS and Linux only.");
  const project = fs.realpathSync(projectDir);
  fail(fs.statSync(project).isDirectory(), "A project directory is required.");
  fail(typeof session === "string" && /^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(session), "Use a short local session key containing letters, numbers, underscores or hyphens.");
  const root = path.join(fs.realpathSync(os.tmpdir()), "gm-app-" + uid());
  const binding = hash(project + "\0" + session), directory = path.join(root, binding.slice(0, 24));
  if (!create && !fs.existsSync(root)) return { project, binding, directory, missing: true };
  privateDirectory(root, create);
  if (!create && !fs.existsSync(directory)) return { project, binding, directory, missing: true };
  privateDirectory(directory, create);
  fail(Buffer.byteLength(path.join(directory, "c")) <= 100, "The temporary directory path is too long for a private runtime socket.");
  return { project, binding, directory };
}
function recordFor(binding) {
  if (binding.missing) return null;
  let record;
  try { record = readPrivate(path.join(binding.directory, "state.json")); }
  catch (error) { if (error.code === "ENOENT") return null; throw error; }
  fail(record.version === 1 && record.binding === binding.binding && record.project === binding.project
    && /^[a-f0-9]{64}$/.test(record.token) && /^[a-f0-9]{64}$/.test(record.generation)
    && /^[a-f0-9]{64}$/.test(record.recipe) && record.socket === path.join(binding.directory, "c")
    && typeof record.logFile === "string" && /^output-[a-f0-9]{64}\.log$/.test(record.logFile)
    && ["running", "stopping", "stopped"].includes(record.state), "The runtime record does not match this project and session.");
  return record;
}
const publicState = record => record ? { state: record.state, owned: true, ...(record.reason ? { reason: record.reason } : {}),
  ...(record.exitCode !== undefined ? { exitCode: record.exitCode } : {}), expiresAt: record.expiresAt, logFile: path.join(path.dirname(record.socket), record.logFile),
  note: "Process state only; verify the demo URL separately. Closing a canvas keeps this demo available. Stop explicitly when finished." }
  : { state: "stopped", owned: false };
function request(record, method) {
  return new Promise((resolve, reject) => {
    const socketStat = fs.lstatSync(record.socket);
    fail(socketStat.isSocket() && socketStat.uid === uid() && (socketStat.mode & 0o077) === 0, "The runtime socket is not private.");
    const req = http.request({ socketPath: record.socket, path: "/" + method,
      method: method === "stop" ? "POST" : "GET", headers: { Host: "app-runtime.invalid", "X-App-Runtime-Key": record.token, "X-App-Runtime-Generation": record.generation }, timeout: 1500 }, res => {
      let text = "";
      res.on("data", chunk => { text += chunk; if (text.length > 16384) req.destroy(new Error("Runtime response exceeded its limit.")); });
      res.on("end", () => { try { fail(res.statusCode === 200, "Runtime control was not authorized."); resolve(JSON.parse(text)); } catch (error) { reject(error); } });
    });
    req.on("timeout", () => req.destroy(new Error("Runtime control did not respond.")));
    req.on("error", reject); req.end();
  });
}
async function status(binding) {
  const record = recordFor(binding);
  if (!record || record.state !== "running") return publicState(record);
  try { return await request(record, "status"); }
  catch { return { state: "unreachable", owned: true, note: "The owned controller could not be confirmed. No process was signalled or restarted." }; }
}
function clearAbandonedStart(binding) {
  if (binding.missing) return false;
  const lock = path.join(binding.directory, "starting");
  if (!fs.existsSync(lock)) return false;
  const identity = privateDirectory(lock); let lease;
  try { lease = readPrivate(path.join(lock, "lease.json")); }
  catch (error) { if (error.code !== "ENOENT" && !(error instanceof SyntaxError)) throw error; }
  const validLease = lease && Number.isFinite(lease.expiresAt) && /^[a-f0-9]{64}$/.test(lease.token);
  if (Date.now() <= (validLease ? lease.expiresAt : identity.mtimeMs + 10000)) return false;
  const files = fs.readdirSync(lock);
  fail(files.every(name => name === "lease.json" || /^\.record-[a-f0-9]{64}$/.test(name)), "The startup directory contains unexpected files; nothing was removed.");
  for (const name of files) {
    try { readPrivate(path.join(lock, name)); }
    catch (error) { if (!(error instanceof SyntaxError)) throw error; }
  }
  // A listening controller must be stopped through its authenticated record.
  // A delayed supervisor rechecks this lease after binding, before spawning.
  try { fs.lstatSync(path.join(binding.directory, "c")); return false; }
  catch (error) { if (error.code !== "ENOENT") throw error; }
  const current = fs.lstatSync(lock);
  fail(current.dev === identity.dev && current.ino === identity.ino, "The startup lease changed.");
  for (const name of files) fs.unlinkSync(path.join(lock, name));
  fs.rmdirSync(lock); return true;
}
async function stop(binding) {
  const record = recordFor(binding);
  if (!record || record.state === "stopped") return { ...publicState(record), clearedStarting: clearAbandonedStart(binding) };
  if (record.state === "running") await request(record, "stop");
  for (let attempt = 0; attempt < 40; attempt++) {
    const latest = recordFor(binding);
    fail(latest?.generation === record.generation, "The runtime changed while stopping; no other runtime was stopped.");
    if (latest.state === "stopped") return { ...publicState(latest), clearedStarting: clearAbandonedStart(binding) };
    await delay(50);
  }
  return { state: "stopping", owned: true, note: "Stop was accepted. Check status; no restart will be attempted." };
}
async function start(binding, command, environment, ttlSeconds) {
  const recipe = hash(JSON.stringify({ command, environment, ttlSeconds }));
  const lock = path.join(binding.directory, "starting");
  try { fs.mkdirSync(lock, { mode: 0o700 }); }
  catch (error) { if (error.code === "EEXIST") throw new Error("A start is already in progress. Read status; use stop after ten seconds to clear an abandoned start before retrying."); throw error; }
  const lockIdentity = privateDirectory(lock), lease = { token: secret(), expiresAt: Date.now() + 10000 };
  let child, handedOff = false;
  try {
  writePrivate(lock, "lease.json", lease);
  const previous = recordFor(binding);
  if (previous && previous.state !== "stopped") {
    fail(previous.recipe === recipe, "This session already owns another command. Stop it explicitly or use a new session key.");
    const current = await status(binding);
    fail(current.state !== "unreachable", current.note);
    return { ...current, reused: true };
  }
  child = fork(__filename, ["--supervise"], { cwd: binding.project, detached: true, execArgv: [],
    stdio: ["ignore", "ignore", "ignore", "ipc"], env: cleanEnvironment() });
    const result = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("The runtime did not confirm startup. No background tool should be left waiting.")), 8000);
      child.once("error", error => { clearTimeout(timer); reject(error); });
      child.once("exit", () => { clearTimeout(timer); reject(new Error("The runtime stopped before startup was confirmed.")); });
      child.on("message", value => {
        if (value?.event === "ready") { clearTimeout(timer); resolve(value.state); }
        else if (value?.event === "error") { clearTimeout(timer); reject(new Error(value.message)); }
      });
      child.send({ binding, command, environment, ttlSeconds, recipe, lease });
    });
    await new Promise((resolve, reject) => child.send({ event: "handoff" }, error => error ? reject(error) : resolve()));
    handedOff = true; child.disconnect(); child.unref();
    return result;
  } finally {
    if (child && !handedOff) {
      if (child.connected) child.disconnect();
      if (child.exitCode === null && child.signalCode === null) {
        try { process.kill(-child.pid, "SIGTERM"); } catch (error) { if (error.code !== "ESRCH") throw error; }
        await delay(600);
        if (child.exitCode === null && child.signalCode === null) {
          try { process.kill(-child.pid, "SIGKILL"); } catch (error) { if (error.code !== "ESRCH") throw error; }
        }
      }
      child.unref();
    }
    let current;
    try { current = fs.lstatSync(lock); } catch (error) { if (error.code !== "ENOENT") throw error; }
    if (current && current.dev === lockIdentity.dev && current.ino === lockIdentity.ino) {
      try { fs.unlinkSync(path.join(lock, "lease.json")); } catch (error) { if (error.code !== "ENOENT") throw error; }
      fs.rmdirSync(lock);
    }
  }
}
async function supervise(config) {
  const { binding, command, environment, ttlSeconds, recipe, lease } = config;
  privateDirectory(binding.directory);
  let handedOff = false, stopping = false, app, timer, grace;
  const logPath = path.join(binding.directory, "output-" + secret() + ".log");
  const log = fs.openSync(logPath, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_NOFOLLOW, 0o600);
  const record = { version: 1, binding: binding.binding, project: binding.project, recipe, token: secret(), generation: secret(),
    logFile: path.basename(logPath), state: "running", socket: path.join(binding.directory, "c"), expiresAt: new Date(Date.now() + ttlSeconds * 1000).toISOString() };
  const same = (a, b) => typeof a === "string" && /^[a-f0-9]{64}$/.test(a) && crypto.timingSafeEqual(Buffer.from(a), Buffer.from(b));
  const server = http.createServer((req, res) => {
    const authorized = req.headers.host === "app-runtime.invalid" && !req.headers.origin
      && !req.headers["transfer-encoding"] && (!req.headers["content-length"] || req.headers["content-length"] === "0")
      && same(req.headers["x-app-runtime-key"], record.token) && same(req.headers["x-app-runtime-generation"], record.generation);
    const valid = authorized && ((req.method === "GET" && req.url === "/status") || (req.method === "POST" && req.url === "/stop"));
    res.writeHead(valid ? 200 : 403, { "Content-Type": "application/json", "Cache-Control": "no-store", Connection: "close" });
    if (valid && req.url === "/stop") res.once("finish", () => shutdown("requested"));
    res.end(JSON.stringify(valid ? publicState(record) : { error: "Runtime request refused." }));
  });
  server.requestTimeout = 2000; server.headersTimeout = 2000; server.maxHeadersCount = 12;
  function shutdown(reason, exitCode) {
    if (stopping) return; stopping = true; clearTimeout(timer); clearTimeout(grace);
    record.state = "stopping"; record.reason = reason;
    if (Number.isInteger(exitCode)) record.exitCode = exitCode;
    try { writePrivate(binding.directory, "state.json", record); } catch { /* Cleanup must survive a failed journal write. */ }
    server.close(); server.closeAllConnections?.();
    // The supervisor is the leader of this private group. Never signal a PID
    // read from disk, another session, a port owner, or a caller-supplied PID.
    try { process.kill(-process.pid, "SIGTERM"); } catch (error) { if (error.code !== "ESRCH") throw error; }
    setTimeout(() => {
      record.state = "stopped";
      try { writePrivate(binding.directory, "state.json", record); } catch { /* Never prevent owned-group cleanup. */ }
      try { fs.closeSync(log); } catch { /* Already closed on failed startup. */ }
      // Reap descendants that ignore TERM even if their direct parent exited.
      try { process.kill(-process.pid, "SIGKILL"); } catch { process.exit(0); }
    }, 350);
  }
  process.on("SIGTERM", () => shutdown("signal")); process.on("SIGINT", () => shutdown("signal"));
  process.on("message", value => { if (value?.event === "handoff") { handedOff = true; clearTimeout(grace); } });
  process.once("disconnect", () => { if (!handedOff) shutdown("startup-abandoned"); });
  const confirmLease = () => {
    const current = readPrivate(path.join(binding.directory, "starting", "lease.json"));
    fail(current.token === lease.token && Date.now() <= current.expiresAt, "The startup lease is no longer active.");
  };
  try {
    confirmLease();
    try { fs.lstatSync(record.socket); throw new Error("A previous controller socket is still present. Use a new session key."); }
    catch (error) { if (error.code !== "ENOENT") throw error; }
    await new Promise((resolve, reject) => { server.once("error", reject); server.listen(record.socket, resolve); });
    fs.chmodSync(record.socket, 0o600);
    confirmLease();
    fail(!stopping, "Startup was cancelled.");
  app = spawn(command[0], command.slice(1), { cwd: binding.project, shell: false,
    env: { ...cleanEnvironment(), ...environment, NEXT_TELEMETRY_DISABLED: "1", ASTRO_TELEMETRY_DISABLED: "1", DO_NOT_TRACK: "1" },
    stdio: ["ignore", "pipe", "pipe"] });
  let logSize = 0;
  const output = chunk => {
    // A bounded private diagnostic file; nothing is streamed into the tool job.
    if (stopping) return;
    try {
      const bounded = chunk.subarray(Math.max(0, chunk.length - 1024 * 1024));
      if (logSize + bounded.length > 1024 * 1024) { fs.ftruncateSync(log, 0); logSize = 0; }
      fs.writeSync(log, bounded, 0, bounded.length, logSize); logSize += bounded.length;
    } catch { shutdown("output-unavailable"); }
  };
  app.stdout.on("data", output); app.stderr.on("data", output);
  app.once("exit", code => shutdown("command-exited", code));
  app.once("error", () => shutdown("spawn-failed"));
  await new Promise((resolve, reject) => { app.once("spawn", resolve); app.once("error", reject); });
  fail(!stopping, "Startup was cancelled.");
  writePrivate(binding.directory, "state.json", record);
  timer = setTimeout(() => shutdown("expired"), ttlSeconds * 1000);
  grace = setTimeout(() => { if (!handedOff) shutdown("startup-abandoned"); }, 5000);
  if (!process.connected) shutdown("startup-abandoned");
  else process.send({ event: "ready", state: publicState(record) }, error => { if (error) shutdown("startup-abandoned"); });
  } catch (error) { shutdown("startup-failed"); throw error; }
}
function parse(args) {
  const operation = args.shift(); fail(["start", "status", "stop", "cancel"].includes(operation), "Use start, status or stop with --project-dir and --session; start takes the command after --.");
  let projectDir = process.cwd(), session, ttlSeconds = 14400; const environment = {}; let command = [];
  while (args.length) {
    const flag = args.shift();
    if (flag === "--") { command = args; break; }
    const value = args.shift(); fail(value !== undefined, "A flag value is missing.");
    if (flag === "--project-dir") projectDir = value;
    else if (flag === "--session") session = value;
    else if (flag === "--ttl-seconds") { fail(/^\d+$/.test(value), "Invalid runtime lifetime."); ttlSeconds = Number(value); }
    else if (flag === "--env") {
      const match = /^([A-Z][A-Z0-9_]{0,63})=(.*)$/s.exec(value);
      fail(match && !forbiddenEnvironment(match[1]) && Buffer.byteLength(match[2]) <= 4096 && !match[2].includes("\0"), "Only bounded non-secret demo environment values are accepted.");
      environment[match[1]] = match[2];
    } else throw new Error("Unknown runtime option.");
  }
  fail(Number.isInteger(ttlSeconds) && ttlSeconds >= 1 && ttlSeconds <= 28800, "Runtime lifetime must be 1–28800 seconds.");
  fail(operation === "start" ? command.length > 0 && command.length <= 64 && command.every(arg => typeof arg === "string" && Buffer.byteLength(arg) <= 16384 && !arg.includes("\0")) : command.length === 0 && Object.keys(environment).length === 0, "Supply a bounded executable and argument list only for start.");
  if (operation === "start") {
    const missing = Object.keys(process.env).filter(key => /(?:^|_)(?:MOCK|DEMO|FIXTURE)(?:_|$)/.test(key) && !(key in environment));
    fail(missing.length === 0, "Demo/mock environment flags must be passed explicitly with --env NAME=value before --; ambient flags are not inherited.");
  }
  return { operation, projectDir, session, ttlSeconds, environment, command };
}
async function main(args) {
  const input = parse(args), binding = location(input.projectDir, input.session, input.operation === "start");
  if (input.operation === "start") return start(binding, input.command, input.environment, input.ttlSeconds);
  return input.operation === "status" ? status(binding) : stop(binding);
}
if (require.main === module) {
  if (process.argv[2] === "--supervise") {
    fail(!!process.send, "The supervisor can only be started by its launcher.");
    process.once("message", input => supervise(input).catch(error => { if (process.connected) process.send({ event: "error", message: "The owned runtime could not start." }, () => {}); process.exitCode = 1; }));
  } else main(process.argv.slice(2)).then(value => process.stdout.write(JSON.stringify(value) + "\n"), error => { process.stderr.write(error.message + "\n"); process.exitCode = 1; });
}
module.exports = { main, parse, location, recordFor, request, privateDirectory, readPrivate, cleanEnvironment };
