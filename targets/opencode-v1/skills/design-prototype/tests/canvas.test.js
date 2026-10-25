"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { fork } = require("node:child_process");
const { test } = require("node:test");
const { FeedbackStore } = require("../scripts/feedback-store.js");
const { CanvasState, PAGE_BYTES } = require("../scripts/canvas-state.js");
const SERVER = path.resolve(__dirname, "../scripts/server.js");
const CHANNEL = "visual-companion-canvas";
const SCREEN = "a".repeat(32);
function note(screen = SCREEN, overrides = {}) {
  return { screen, kind: "point", text: "Gjør neste steg tydeligere.",
    anchor: { path: "h1:nth-of-type(1)", role: "heading", rect: { x: 0, y: 0, width: 120, height: 40 }, viewport: { width: 390, height: 844 } }, ...overrides };
}
function temporary(t) {
  const dir = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "grillmester-canvas-test-")));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return dir;
}
function state(t) {
  const store = new FeedbackStore(temporary(t), { canvas: true }); store.knowScreen(SCREEN, "initial.html");
  return { store, canvas: new CanvasState(store) };
}
async function running(t) {
  const project = temporary(t);
  const child = fork(SERVER, ["--project-dir", project], { execArgv: [], stdio: ["ignore", "pipe", "pipe", "ipc"] });
  child.stdout.resume(); child.stderr.resume();
  const ended = new Promise(resolve => {
    const finish = () => { child.stdout.destroy(); child.stderr.destroy(); resolve(); };
    child.once("exit", finish); child.once("close", finish);
  });
  t.after(async () => { if (child.exitCode === null && child.signalCode === null) child.kill("SIGTERM"); await ended; });
  let id = 0;
  const events = [], pending = new Map();
  const info = await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => { child.kill("SIGTERM"); reject(new Error("Canvas startup deadline exceeded.")); }, 6000);
    child.once("error", error => { clearTimeout(timeout); reject(error); });
    child.on("message", message => {
      if (message.channel !== CHANNEL || message.version !== 1) return;
      if (message.event === "ready") { clearTimeout(timeout); resolve(message.info); }
      else if (message.event) events.push(message);
      else if (pending.has(message.id)) { const request = pending.get(message.id); pending.delete(message.id); request(message); }
    });
  });
  const rpc = (method, params = {}) => new Promise((resolve, reject) => {
    const requestId = ++id;
    const timeout = setTimeout(() => { pending.delete(requestId); reject(new Error("Canvas request deadline exceeded.")); }, 6000);
    pending.set(requestId, message => { clearTimeout(timeout); message.ok ? resolve(message.result) : reject(Object.assign(new Error(message.error), { status: message.status })); });
    child.send({ channel: CHANNEL, version: 1, id: requestId, method, params });
  });
  return { child, ended, info, rpc, events };
}
async function http(url, pathname, method = "GET", body, mutation) {
  const target = new URL(url); target.pathname = pathname;
  return fetch(target, { method, headers: { Origin: target.origin, ...(body === undefined ? {} : { "Content-Type": "application/json" }), ...(mutation ? { "X-Feedback-Mutation": mutation } : {}) }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
}

test("delivery and immutable round commit together, and reviews do not rewrite history", t => {
  const { store, canvas } = state(t);
  store.create(note());
  const original = store.persist.bind(store);
  store.persist = () => { throw new Error("Controlled failed commit"); };
  assert.throws(() => store.submit({}), /failed commit/);
  assert.equal(store.state.submission, 0); assert.deepEqual(store.state.canvas.rounds, []);
  store.persist = original; store.submit({});
  const first = JSON.stringify(store.state.submissions);
  assert.deepEqual(store.snapshot().canvas.rounds, [{ submission: 1, delivery: "sending", review: "unread", reply: "" }]);
  store.create(note(SCREEN, { text: "Et annet innspill." }));
  assert.throws(() => store.submit({}), /previous delivery/);
  canvas.delivery({ submission: 1, status: "unknown" });
  assert.throws(() => store.submit({}), /previous delivery/);
  canvas.review({ submission: 1, status: "working", reply: "Ser på overskriften." });
  store.submit({});
  assert.equal(store.state.submission, 2);
  canvas.review({ submission: 1, status: "answered", reply: "Ny overskrift er publisert." });
  assert.throws(() => canvas.review({ submission: 1, status: "working", reply: "Igjen" }), /cannot return/);
  canvas.delivery({ submission: 1, status: "queued" });
  canvas.delivery({ submission: 1, status: "unknown" });
  assert.equal(store.state.canvas.rounds[0].delivery, "queued");
  assert.equal(JSON.stringify([store.state.submissions[0]]), first);
  assert.equal(canvas.summary().canvas.rounds[0].reply, undefined);
  assert.equal(canvas.read({ submission: 1 }).round.reply, "Ny overskrift er publisert.");
  const file = JSON.parse(fs.readFileSync(store.filename));
  assert.deepEqual(file.canvas, store.state.canvas);
});

test("canvas review rejects foreign, malformed and obsolete comment writes", t => {
  const { store, canvas } = state(t); store.create(note()); store.submit({});
  const id = store.state.comments[0].id;
  assert.throws(() => canvas.review({ submission: 2, status: "answered", reply: "Svar" }), /does not belong/);
  assert.throws(() => canvas.delivery({ submission: 1, status: "queued", prompt: "extra" }), /Invalid/);
  assert.throws(() => canvas.review({ submission: 1, status: "answered", reply: "ø".repeat(1001) }), /Invalid/);
  assert.throws(() => canvas.updateComment({ submission: 1, id: "b".repeat(24), reply: "Svar" }), /not part/);
  canvas.updateComment({ submission: 1, id, status: "fixed", reply: "Rettet" });
  assert.equal(store.state.canvas.rounds[0].review, "unread", "Comment state is not round processing state.");
  store.patch(id, { status: "open", resubmit: true });
  assert.throws(() => canvas.updateComment({ submission: 1, id, status: "fixed" }), /submission|round/i);
  assert.equal(store.state.comments[0].status, "open");
});

test("large rounds page completely within the canvas bound without disclosing drafts", t => {
  const { store, canvas } = state(t);
  store.create(note(SCREEN, { kind: "edit", text: "ø".repeat(1000), proposal: { property: "text", value: "å".repeat(1000) } }));
  const seed = store.state.comments[0];
  store.change(value => { value.comments = Array.from({ length: 199 }, (_, index) => ({ ...seed, id: index.toString(16).padStart(24, "0") })); });
  store.submit({}); store.create(note(SCREEN, { text: "THIS_UNSENT_DRAFT_MUST_NOT_REACH_THE_SESSION" }));
  const disk = fs.readFileSync(store.filename, "utf8");
  let offset = 0, pages = 0, comments = [];
  do {
    const page = canvas.read({ submission: 1, offset }); pages++;
    assert(Buffer.byteLength(JSON.stringify(page)) <= PAGE_BYTES);
    assert(!JSON.stringify(page).includes("THIS_UNSENT_DRAFT"));
    comments.push(...page.items.filter(item => item.type === "comment"));
    offset = page.nextOffset;
  } while (offset !== null);
  assert(pages > 10); assert.equal(comments.length, 199);
  assert(comments.every(item => item.value.proposal.value === "å".repeat(1000)));
  assert.equal(fs.readFileSync(store.filename, "utf8"), disk);
  assert.throws(() => canvas.read({ submission: 1, offset: 9999 }), /out of range/);
});

test("full server commits once, exposes only private IPC actions, and retains state across view close", async t => {
  const app = await running(t);
  const initial = await app.rpc("publishRevision", { expectedScreen: "", filename: "initial.html", html: "<h1>Velg tidspunkt</h1>" });
  assert.match(initial.screen, /^[a-f0-9]{32}$/);
  let response = await http(app.info.url, "/comments", "POST", note(initial.screen)); assert.equal(response.status, 200);
  const input = { revision: (await response.json()).revision };
  const mutation = "c".repeat(32);
  response = await http(app.info.url, "/comments/submit", "POST", input, mutation); assert.equal(response.status, 200);
  assert.equal((await response.json()).canvas.rounds[0].delivery, "sending");
  response = await http(app.info.url, "/comments/submit", "POST", input, mutation); assert.equal(response.status, 200);
  await app.rpc("readState"); assert.equal(app.events.filter(item => item.event === "submitted").length, 1);
  assert([404, 405].includes((await http(app.info.url, "/canvas", "POST", { method: "markDelivery" })).status));
  await assert.rejects(app.rpc("markDelivery", { submission: 1, status: "queued", extra: true }), /Invalid/);
  await assert.rejects(app.rpc("publishRevision", { expectedScreen: "", filename: "stale.html", html: "<h1>Stale</h1>" }), /changed/);
  await assert.rejects(app.rpc("publishRevision", { expectedScreen: initial.screen, filename: "../outside.html", html: "<h1>Outside</h1>" }), /Invalid/);
  await app.rpc("markDelivery", { submission: 1, status: "queued" });
  await app.rpc("reviewSubmission", { submission: 1, status: "working", reply: "Vurderer innspillet." });
  const next = await app.rpc("publishRevision", { expectedScreen: initial.screen, filename: "revised.html", html: "<h1>Finn en tid som passer</h1>" });
  assert.notEqual(next.screen, initial.screen);
  await app.rpc("reviewSubmission", { submission: 1, status: "answered", reply: "Overskriften er oppdatert." });
  const page = await app.rpc("readSubmission", { submission: 1 });
  assert.equal(page.items.find(item => item.type === "comment").value.screen, initial.screen);
  assert.equal(page.round.review, "answered");
  await app.rpc("closeView");
  await assert.rejects(fetch(app.info.url));
  assert(fs.existsSync(path.join(app.info.state_dir, "comments.json")));
  const reopened = await app.rpc("openView");
  assert.notEqual(reopened.url, app.info.url);
  const oldToken = new URL(reopened.url); oldToken.search = new URL(app.info.url).search;
  assert.equal((await fetch(oldToken)).status, 403);
  assert.equal((await (await http(reopened.url, "/comments")).json()).canvas.rounds[0].reply, "Overskriften er oppdatert.");
  assert.equal(app.events.filter(item => item.event === "submitted").length, 1);
  await app.rpc("retire"); await app.ended;
  assert.equal(fs.existsSync(app.info.state_dir), false);
});

test("losing the owning IPC parent stops its listener and removes its private state", async t => {
  const app = await running(t); app.child.disconnect(); await app.ended;
  assert.equal(fs.existsSync(app.info.state_dir), false);
  await assert.rejects(fetch(app.info.url));
});
