#!/usr/bin/env node
"use strict";

// Commit each first write, then lose only its response. This differs from a
// request rejected before persistence: retry must recover the existing intent.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");
const options = new Map();
for (let index = 2; index < process.argv.length; index += 1) {
  const flag = process.argv[index];
  if (flag === "--headed") { options.set(flag, true); continue; }
  if (!["--playwright-module", "--browser-channel", "--evidence-dir", "--case"].includes(flag) || !process.argv[index + 1] || process.argv[index + 1].startsWith("--")) {
    console.error("Usage: node scripts/smoke_visual_retry.cjs --playwright-module PATH [--browser-channel chrome] [--headed] [--evidence-dir DIRECTORY] [--case NAME]");
    process.exit(2);
  }
  options.set(flag, process.argv[++index]);
}
let chromium;
try { ({ chromium } = require(options.get("--playwright-module") || "playwright")); }
catch { console.error("Supply an existing Playwright installation. No dependencies were installed."); process.exit(2); }
const runtime = path.resolve(__dirname, "../plugin/skills/design-prototype/scripts");
const evidence = options.has("--evidence-dir") ? path.resolve(options.get("--evidence-dir")) : null;
if (evidence) fs.mkdirSync(evidence, { recursive: true });
const design = { version: 1, variants: [], targets: [{ key: "summary", variant: "", label: "Møteoversikt", controls: [{ id: "density", label: "Tetthet", type: "select", initial: "comfortable", options: [{ value: "comfortable", label: "Romslig" }, { value: "compact", label: "Kompakt" }] }] }] };
const content = '<style>[data-vc-key="summary"]{padding:32px;border:1px solid #ccc}[data-vc-setting-density="compact"]{padding:8px}</style><main><section data-vc-key="summary"><h1>Forbered møtet</h1><p>Ta med to spørsmål.</p></section><label>Prøvefelt<input id="practice"></label></main>';
async function until(check, message) {
  const deadline = Date.now() + 7000;
  while (Date.now() < deadline) { if (await check()) return; await new Promise(resolve => setTimeout(resolve, 50)); }
  throw new Error(message);
}
async function start(project) {
  const child = spawn(process.execPath, [path.join(runtime, "server.js"), "--project-dir", project], { stdio: ["ignore", "pipe", "pipe"] });
  try {
    const info = await new Promise((resolve, reject) => {
      let output = "";
      const timer = setTimeout(() => reject(new Error("Preview startup timed out.")), 5000);
      child.once("error", error => { clearTimeout(timer); reject(error); });
      child.once("close", code => { clearTimeout(timer); reject(new Error(`Preview stopped before startup (${code}).`)); });
      child.stdout.on("data", chunk => {
        output += chunk;
        if (!output.includes("\n")) return;
        clearTimeout(timer);
        try { const info = JSON.parse(output.split("\n")[0]); assert.equal(info.type, "server-started"); resolve(info); }
        catch { reject(new Error("Preview returned invalid startup information.")); }
      });
    });
    return { child, info };
  } catch (error) { await stop(child); throw error; }
}
async function stop(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const ended = new Promise(resolve => child.once("close", resolve));
  child.kill("SIGTERM"); const timer = setTimeout(() => child.kill("SIGKILL"), 5000);
  await ended; clearTimeout(timer);
}
async function session(browser, name, run, lostResponsePath = "/comments", lostResponseMethod = "POST") {
  const project = fs.mkdtempSync(path.join(os.tmpdir(), "grillmester-retry-"));
  let running, context;
  try {
    running = await start(project);
    fs.writeFileSync(path.join(running.info.screen_dir, "test.design.json"), JSON.stringify(design));
    fs.writeFileSync(path.join(running.info.screen_dir, "test.html"), content);
    context = await browser.newContext({ viewport: { width: 1300, height: 1000 } });
    const page = await context.newPage(); page.setDefaultTimeout(7000);
    const errors = [], external = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("requestfinished", request => { if (!request.url().startsWith(new URL(running.info.url).origin) && !/^(data|blob):/.test(request.url())) external.push(new URL(request.url()).origin); });
    const frame = page.frameLocator("#vc-preview"), ui = frame.locator("[data-visual-feedback]");
    const url = new URL(running.info.url); url.pathname = "/comments";
    const snapshot = async () => (await fetch(url)).json();
    const mutate = async (pathname, method, value) => {
      const target = new URL(running.info.url); target.pathname = pathname;
      const response = await fetch(target, { method, headers: { Origin: target.origin, "Content-Type": "application/json" }, body: JSON.stringify(value) });
      assert.equal(response.status, 200);
      return response.json();
    };
    const mutations = [];
    const mutationPayloads = [];
    let dropped = false;
    let frozenRead = null;
    await page.route(/\/(?:comments|decisions)(?:\/|\?|$)/, async route => {
      const requestPath = new URL(route.request().url()).pathname;
      // Preserve the reviewed pre-submit list until the explicit retry. This
      // makes the lost-receipt case independent of the background poll timing.
      if (requestPath === "/comments" && route.request().method() === "GET" && frozenRead) {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(frozenRead) }); return;
      }
      const matchesPath = typeof lostResponsePath === "string" ? requestPath === lostResponsePath : lostResponsePath.test(requestPath);
      if (!matchesPath || route.request().method() !== lostResponseMethod) { await route.continue(); return; }
      mutations.push(route.request().headers()["x-feedback-mutation"]);
      mutationPayloads.push(route.request().postDataJSON());
      if (dropped) { await route.continue(); return; }
      dropped = true;
      if (lostResponsePath === "/comments/submit" || lostResponseMethod === "PATCH") frozenRead = await snapshot();
      const response = await route.fetch();
      assert.equal(response.status(), 200, "The first mutation must reach durable storage before its response is lost.");
      await route.abort("failed");
    });
    await page.goto(running.info.url);
    await ui.getByRole("button", { name: "Kommenter", exact: true }).waitFor();
    await frame.getByLabel("Prøvefelt", { exact: true }).fill("PRIVATE_PRACTICE_VALUE");
    const begin = async text => {
      await ui.getByRole("button", { name: "Kommenter", exact: true }).click();
      await frame.getByRole("heading", { name: "Forbered møtet", exact: true }).click();
      await ui.getByLabel("Hva vil du endre?", { exact: true }).fill(text);
    };
    await run({ page, frame, ui, snapshot, mutate, mutations, mutationPayloads, begin, releaseRead: () => { frozenRead = null; } });
    assert(mutations.every(id => /^[a-f0-9]{32}$/.test(id)), "Each actual browser mutation carries a bounded retry identifier.");
    assert.equal(JSON.stringify(await snapshot()).includes("PRIVATE_PRACTICE_VALUE"), false);
    assert.deepEqual(errors, []); assert.deepEqual(external, []);
    if (evidence) await page.screenshot({ path: path.join(evidence, `${name}.png`), animations: "disabled" });
    return { name, passed: true, writesAttempted: mutations.length };
  } finally {
    if (context) await context.close();
    if (running) await stop(running.child);
    fs.rmSync(project, { recursive: true, force: true });
  }
}
const cases = [
  { name: "submit-after-lost-receipt", lostResponsePath: "/comments/submit", async run({ ui, snapshot, mutations, begin, releaseRead }) {
    await begin("Vis neste steg tydeligere.");
    await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click();
    const send = ui.getByRole("button", { name: "Send 1 innspill", exact: true });
    await send.waitFor();
    const before = await snapshot();
    await send.click();
    await ui.locator(".panel-error").waitFor({ state: "visible" });
    const committed = await snapshot();
    assert.equal(committed.submission, before.submission + 1, "The first submission is actually committed before its receipt is lost.");
    assert.equal(committed.comments[0].submission, committed.submission);
    await send.click();
    await until(() => mutations.length === 2, "The explicit submission retry did not reach the server.");
    assert.equal(mutations[0], mutations[1], "Retrying the unchanged reviewed submission must reuse its mutation identifier.");
    await until(async () => (await ui.locator(".pending").textContent()) === "1 innspill sendt", "The retry did not recover the accepted submission receipt.");
    const recovered = await snapshot();
    assert.equal(recovered.submission, committed.submission);
    assert.equal(recovered.revision, committed.revision, "Recovering a receipt must not commit another revision.");
    assert.deepEqual(recovered.comments, committed.comments);
    assert.equal(await ui.locator(".send").isDisabled(), true);
    assert.equal(await ui.locator(".panel-error").isVisible(), false);
    releaseRead();
  } },
  { name: "same-note-after-lost-receipt", async run({ ui, snapshot, mutations, begin }) {
    const text = "Vis hvor lang tid møtet tar.";
    await begin(text);
    await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click();
    await ui.locator(".compose-error").waitFor({ state: "visible" });
    assert.equal((await snapshot()).comments.length, 1);
    assert.equal(await ui.getByLabel("Hva vil du endre?", { exact: true }).inputValue(), text);
    await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click();
    await ui.getByRole("button", { name: "Send 1 innspill", exact: true }).waitFor();
    assert.equal(mutations[0], mutations[1]);
    assert.equal((await snapshot()).comments.length, 1);
    await ui.getByRole("button", { name: "Send 1 innspill", exact: true }).click();
    await until(async () => (await snapshot()).submission === 1, "Recovered note was not submitted.");
    assert.equal((await snapshot()).comments[0].submission, 1);
  } },
  { name: "edited-note-after-lost-receipt", async run({ ui, snapshot, mutations, begin }) {
    await begin("Vis hvor lang tid møtet tar.");
    await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click();
    await ui.locator(".compose-error").waitFor({ state: "visible" });
    await ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Forklar hvordan jeg kan flytte møtet.");
    await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click();
    await ui.getByRole("button", { name: "Send 2 innspill", exact: true }).waitFor();
    assert.notEqual(mutations[0], mutations[1], "Changing the draft creates a distinct intent, not an invalid retry.");
    assert.deepEqual((await snapshot()).comments.map(item => item.text), ["Vis hvor lang tid møtet tar.", "Forklar hvordan jeg kan flytte møtet."]);
  } },
  { name: "adjustment-after-lost-receipt", async run({ ui, snapshot, mutations }) {
    await ui.getByRole("button", { name: "Juster", exact: true }).click();
    await ui.getByLabel("Tetthet", { exact: true }).selectOption("compact");
    await ui.locator("#workshop-remark").fill("Samle oversikten tettere.");
    await ui.locator('[data-action="workshop-add"]').click();
    await ui.locator(".workshop-error").waitFor({ state: "visible" });
    assert.equal((await snapshot()).comments.length, 1);
    await ui.locator('[data-action="workshop-add"]').click();
    await ui.getByRole("button", { name: "Send 1 innspill", exact: true }).waitFor();
    assert.equal(mutations[0], mutations[1]);
    const result = await snapshot();
    assert.equal(result.comments.length, 1);
    assert.deepEqual(result.comments[0].adjustment.values, { density: "compact" });
    assert.equal(result.comments[0].text, "Samle oversikten tettere.");
  } },
  { name: "keep-after-lost-receipt", lostResponsePath: "/decisions", async run({ ui, snapshot, mutate, mutations, mutationPayloads }) {
    await ui.getByRole("button", { name: "Juster", exact: true }).click();
    await ui.getByLabel("Tetthet", { exact: true }).selectOption("compact");
    await ui.locator("#workshop-remark").fill("Behold den tettere oversikten.");
    await ui.locator('[data-action="workshop-keep"]').click();
    await ui.locator(".workshop-error").waitFor({ state: "visible" });
    const committed = await snapshot();
    assert.equal(committed.decisions.length, 1);
    assert.equal(committed.decisions[0].text, "Behold den tettere oversikten.");
    assert.equal(await ui.locator("#workshop-remark").inputValue(), "Behold den tettere oversikten.");
    const first = committed.decisions[0];
    const newer = await mutate("/decisions", "POST", { screen: first.screen, variant: first.variant, target: first.target, values: { density: "comfortable" }, text: "Et nyere valg fra en annen fane.", expectedRevision: first.revision });
    await until(async () => (await ui.locator(".workshop-keep-list").textContent()).includes("Et nyere valg fra en annen fane."), "Polling did not expose the newer choice before retry.");
    await ui.locator('[data-action="workshop-keep"]').click();
    await ui.getByRole("button", { name: "Send 1 innspill", exact: true }).waitFor();
    assert.equal(mutations.length, 2);
    assert.equal(mutations[0], mutations[1], "The kept choice retries the original committed intent.");
    assert.deepEqual(mutationPayloads[0], mutationPayloads[1], "Polling must not rebase the guard while a saved receipt is still unknown.");
    assert.equal(mutationPayloads[0].expectedRevision, 0);
    const recovered = await snapshot();
    assert.equal(recovered.revision, newer.revision);
    assert.deepEqual(recovered.decisions, newer.decisions, "Recovering an older receipt must not overwrite the newer choice.");
  } },
  { name: "release-after-lost-receipt", lostResponsePath: /^\/decisions\/[a-f0-9]{24}$/, lostResponseMethod: "PATCH", async run({ ui, snapshot, mutate, mutations, mutationPayloads, releaseRead }) {
    await ui.getByRole("button", { name: "Juster", exact: true }).click();
    await ui.locator('[data-action="workshop-keep"]').click();
    await ui.getByRole("button", { name: "Send 1 innspill", exact: true }).waitFor();
    const original = (await snapshot()).decisions[0];
    await ui.getByRole("button", { name: "Juster", exact: true }).click();
    await ui.locator(".workshop-keep-list").getByRole("button", { name: "Frigi", exact: true }).click();
    await ui.locator(".workshop-error").waitFor({ state: "visible" });
    const released = (await snapshot()).decisions[0];
    assert.equal(released.state, "released");
    const restored = await mutate("/decisions", "POST", { screen: released.screen, variant: released.variant, target: released.target, values: { density: "compact" }, text: "En annen fane beholdt delen igjen.", expectedRevision: released.revision });
    await ui.locator(".workshop-keep-list").getByRole("button", { name: "Frigi", exact: true }).click();
    await ui.getByRole("button", { name: "Send 1 innspill", exact: true }).waitFor();
    assert.equal(mutations.length, 2);
    assert.equal(mutations[0], mutations[1]);
    assert.deepEqual(mutationPayloads[0], mutationPayloads[1], "Release retries retain the guard of the original card.");
    assert.equal(mutationPayloads[0].expectedRevision, original.revision);
    const recovered = await snapshot();
    assert.equal(recovered.revision, restored.revision);
    assert.deepEqual(recovered.decisions, restored.decisions, "A release receipt must not release a later re-kept decision.");
    releaseRead();
  } },
];
(async () => {
  const chosen = options.has("--case") ? cases.filter(item => item.name === options.get("--case")) : cases;
  if (!chosen.length) throw new Error("Unknown retry case.");
  const browser = await chromium.launch({ channel: options.get("--browser-channel") || "chrome", headless: !options.get("--headed") });
  const results = [];
  try {
    for (const testcase of chosen) {
      try { results.push(await session(browser, testcase.name, testcase.run, testcase.lostResponsePath, testcase.lostResponseMethod)); }
      catch (error) { results.push({ name: testcase.name, passed: false, error: String(error.message).replace(/https?:\/\/[^\s]+/g, "[local URL]") }); }
    }
  } finally { await browser.close(); }
  const report = { passed: results.every(result => result.passed), cases: results, limits: ["Simulated response loss after an actual local commit; no model or native app session is used."] };
  if (evidence) fs.writeFileSync(path.join(evidence, "retry-results.json"), JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report));
  if (!report.passed) process.exitCode = 1;
})().catch(error => { console.error(error.message); process.exitCode = 1; });
