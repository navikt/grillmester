#!/usr/bin/env node
"use strict";

// Commit each first write, then lose only its response. This differs from a
// request rejected before persistence: retry must recover the existing intent.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");
// «Juster visning» belongs to Prøv; leave Endre first when its Vis bar is hidden.
async function openAdjust(ui) {
  const adjust = ui.getByRole("button", { name: "Juster visning", exact: true });
  if (!(await adjust.isVisible())) await ui.getByRole("button", { name: "Prøv", exact: true }).click();
  await adjust.click();
}
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
    const openPeer = async () => {
      const peer = await context.newPage(); peer.setDefaultTimeout(7000);
      peer.on("pageerror", error => errors.push(error.message));
      peer.on("requestfinished", request => { if (!request.url().startsWith(new URL(running.info.url).origin) && !/^(data|blob):/.test(request.url())) external.push(new URL(request.url()).origin); });
      await peer.goto(running.info.url);
      const peerFrame = peer.frameLocator("#vc-preview"), peerUi = peerFrame.locator("[data-visual-feedback]");
      await peerUi.getByRole("button", { name: "Endre", exact: true }).waitFor();
      return { page: peer, frame: peerFrame, ui: peerUi };
    };
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
    await page.route(/\/comments(?:\/|\?|$)/, async route => {
      const requestPath = new URL(route.request().url()).pathname;
      // Preserve the reviewed pre-submit list until the explicit retry. This
      // makes the lost-receipt case independent of the background poll timing.
      if (requestPath === "/comments" && route.request().method() === "GET" && frozenRead) {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(frozenRead) }); return;
      }
      const matchesPath = typeof lostResponsePath === "string" ? requestPath === lostResponsePath : lostResponsePath instanceof RegExp && lostResponsePath.test(requestPath);
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
    await ui.getByRole("button", { name: "Endre", exact: true }).waitFor();
    await frame.getByLabel("Prøvefelt", { exact: true }).fill("PRIVATE_PRACTICE_VALUE");
    const begin = async text => {
      await ui.getByRole("button", { name: "Endre", exact: true }).click();
      await frame.getByRole("heading", { name: "Forbered møtet", exact: true }).click();
      await ui.getByLabel("Hva vil du endre?", { exact: true }).fill(text);
    };
    const publish = heading => fs.writeFileSync(path.join(running.info.screen_dir, "test.html"), content.replace("Forbered møtet", heading));
    const details = await run({ page, frame, ui, snapshot, mutate, mutations, mutationPayloads, begin, openPeer, publish, releaseRead: () => { frozenRead = null; } });
    assert(mutations.every(id => /^[a-f0-9]{32}$/.test(id)), "Each actual browser mutation carries a bounded retry identifier.");
    assert.equal(JSON.stringify(await snapshot()).includes("PRIVATE_PRACTICE_VALUE"), false);
    assert.deepEqual(errors, []); assert.deepEqual(external, []);
    if (evidence) await page.screenshot({ path: path.join(evidence, `${name}.png`), animations: "disabled" });
    return { name, passed: true, writesAttempted: mutations.length, ...(details || {}) };
  } catch (error) {
    if (evidence && context?.pages()[0]) {
      try { await context.pages()[0].screenshot({ path: path.join(evidence, `${name}-failed.png`), animations: "disabled" }); } catch { /* Preserve the original assertion if the page has closed. */ }
    }
    throw error;
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
    await openAdjust(ui);
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
  { name: "keep-wish-after-lost-receipt", async run({ ui, snapshot, mutations, mutationPayloads }) {
    await openAdjust(ui);
    await ui.getByLabel("Tetthet", { exact: true }).selectOption("compact");
    await ui.locator("#workshop-remark").fill("Behold den tettere oversikten.");
    await ui.locator('[data-action="workshop-keep"]').click();
    await ui.locator(".workshop-error").waitFor({ state: "visible" });
    const committed = await snapshot();
    assert.equal(committed.comments.length, 1);
    assert.equal(committed.comments[0].text, "Behold denne delen.\nBehold den tettere oversikten.");
    assert.equal(await ui.locator("#workshop-remark").inputValue(), "Behold den tettere oversikten.");
    await ui.locator('[data-action="workshop-keep"]').click();
    await ui.getByRole("button", { name: "Send 1 innspill", exact: true }).waitFor();
    assert.equal(mutations.length, 2);
    assert.equal(mutations[0], mutations[1], "The keep wish retries the original committed intent.");
    assert.deepEqual(mutationPayloads[0], mutationPayloads[1]);
    const recovered = await snapshot();
    assert.equal(recovered.comments.length, 1, "A retried keep wish is saved once.");
    assert.deepEqual(recovered.comments[0].context, { variant: "", target: "summary", values: { density: "compact" } });
  } },
  { name: "full-comment-queue-keeps-draft", lostResponsePath: null, async run({ page, frame, ui, snapshot, mutate }) {
    const screen = (await snapshot()).screens[0].screen;
    const anchor = { path: "h1:nth-of-type(1)", role: "heading", rect: { x: 0, y: 0, width: 200, height: 40 }, viewport: { width: 1300, height: 1000 } };
    for (let index = 0; index < 200; index += 1) await mutate("/comments", "POST", { screen, kind: "point", text: `Tidligere innspill ${index + 1}.`, anchor });
    const before = await snapshot();
    assert.equal(before.comments.length, 200);
    const attempted = [];
    page.on("request", request => { if (request.method() === "POST" && new URL(request.url()).pathname === "/comments") attempted.push(request.postDataJSON()); });
    await ui.getByRole("button", { name: "Endre", exact: true }).click();
    await frame.getByRole("heading", { name: "Forbered møtet", exact: true }).focus();
    await page.keyboard.press("Enter");
    await ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Behold dette utkastet når køen er full.");
    await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click();
    await ui.locator(".compose-error").waitFor({ state: "visible" });
    assert.equal(await ui.getByLabel("Hva vil du endre?", { exact: true }).inputValue(), "Behold dette utkastet når køen er full.");
    assert.equal(await ui.getByRole("button", { name: "Lagre innspill", exact: true }).isEnabled(), true);
    const after = await snapshot();
    assert.equal(after.revision, before.revision);
    assert.deepEqual(after.comments, before.comments);
    assert.equal(attempted.length, 1, "A capacity refusal must not retry automatically.");
    const message = await ui.locator(".compose-error").textContent();
    assert.match(message, /full|grens|kapasitet/i, `Capacity must have actionable copy, received: ${message}`);
    assert.doesNotMatch(message, /prøv samme innspill igjen/i);
    return { writesAttempted: attempted.length, checks: ["actual comment capacity refused", "draft retained", "no retry loop", "capacity guidance shown"] };
  } },
  { name: "edited-draft-after-accepted-save-timeout", lostResponsePath: null, async run({ page, ui, snapshot, begin }) {
    let releaseReceipt, held = false, lateDelivered = false;
    const receipt = new Promise(resolve => { releaseReceipt = resolve; });
    const attempts = [];
    await page.route("**/comments?**", async route => {
      if (route.request().method() !== "POST") { await route.continue(); return; }
      attempts.push({ body: route.request().postDataJSON(), mutationId: route.request().headers()["x-feedback-mutation"] });
      if (held) { await route.continue(); return; }
      held = true;
      const response = await route.fetch();
      assert.equal(response.status(), 200);
      await receipt;
      await route.fulfill({ response });
      lateDelivered = true;
    });
    try {
      await begin("Det første innspillet er faktisk lagret.");
      const started = Date.now();
      await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click();
      await until(async () => (await snapshot()).comments.length === 1, "The first note was not committed before its receipt was delayed.");
      await ui.locator(".compose-error").waitFor({ state: "visible", timeout: 15000 });
      assert(Date.now() - started >= 11500, "The actual helper timeout must expire; an immediate transport rejection is a different case.");
      assert.equal(await ui.getByLabel("Hva vil du endre?", { exact: true }).inputValue(), "Det første innspillet er faktisk lagret.");
      await ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Et endret utkast etter tidsavbruddet.");
      releaseReceipt();
      await until(() => lateDelivered, "The late receipt was not delivered.");
      await page.waitForTimeout(150);
      assert.equal(await ui.getByLabel("Hva vil du endre?", { exact: true }).inputValue(), "Et endret utkast etter tidsavbruddet.", "A late success must not clear or close a newer local draft.");
      assert.equal(attempts.length, 1, "A timeout must never retry automatically.");
      await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click();
      await ui.getByRole("button", { name: "Send 2 innspill", exact: true }).waitFor();
      assert.equal(attempts.length, 2);
      assert.notEqual(attempts[0].mutationId, attempts[1].mutationId);
      assert.deepEqual((await snapshot()).comments.map(item => item.text), ["Det første innspillet er faktisk lagret.", "Et endret utkast etter tidsavbruddet."]);
      return { writesAttempted: attempts.length, checks: ["actual 12-second timeout", "accepted first note retained", "late receipt preserves edited draft", "explicit changed intent gets new key"] };
    } finally { releaseReceipt(); }
  } },
  { name: "parked-draft-versus-saved-preview", lostResponsePath: null, async run({ frame, ui, snapshot, begin }) {
    await begin("Lagret forslag B.");
    await ui.getByRole("button", { name: "Foreslå ny tekst", exact: true }).click();
    await ui.getByLabel("Ny tekst", { exact: true }).fill("Lagret overskrift B");
    await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click();
    await ui.getByRole("button", { name: "Send 1 innspill", exact: true }).waitFor();
    const saved = await snapshot();
    await ui.getByRole("button", { name: "Lukk innspill", exact: true }).click();
    await begin("Mitt nyere utkast A.");
    await ui.getByRole("button", { name: "Foreslå ny tekst", exact: true }).click();
    await ui.getByLabel("Ny tekst", { exact: true }).fill("Mitt nyere utkast A");
    await ui.getByRole("button", { name: "Legg utkast til side", exact: true }).click();
    await ui.locator('[data-action="panel"]').click();
    await ui.getByRole("button", { name: "Forhåndsvis tekst", exact: true }).click();
    assert.equal(await frame.locator("h1").textContent(), "Lagret overskrift B");
    await ui.getByRole("button", { name: "Fortsett utkast", exact: true }).click();
    assert.equal(await frame.locator("h1").textContent(), "Forbered møtet", "Resuming a draft must remove another saved proposal's preview even on the same element.");
    assert.equal(await ui.getByLabel("Ny tekst", { exact: true }).inputValue(), "Mitt nyere utkast A");
    assert.equal(await ui.getByRole("button", { name: "Se i skissen", exact: true }).isVisible(), false);
    await ui.getByRole("button", { name: "Forhåndsvis teksten", exact: true }).click();
    await ui.getByRole("button", { name: "Se i skissen", exact: true }).click();
    assert.equal(await frame.locator("h1").textContent(), "Mitt nyere utkast A", "Inspecting the resumed draft must show its own text.");
    assert.equal(await ui.locator(".composer").isVisible(), false);
    await ui.getByRole("button", { name: "Fortsett å redigere", exact: true }).click();
    assert.equal(await ui.getByLabel("Ny tekst", { exact: true }).inputValue(), "Mitt nyere utkast A");
    assert.equal(await ui.getByLabel("Ny tekst", { exact: true }).evaluate(element => element.getRootNode().activeElement === element), true);
    assert.deepEqual((await snapshot()).comments, saved.comments, "Preview and resume must never save or replace the parked draft automatically.");
    assert.equal((await snapshot()).revision, saved.revision);
    return { writesAttempted: 1, checks: ["saved preview remains separate from parked draft", "resume clears foreign preview", "own inspection shows draft text", "edit focus and unsaved state retained"] };
  } },
  { name: "late-receipt-after-version-change", lostResponsePath: null, async run({ page, frame, ui, snapshot, begin, publish }) {
    let releaseOld, releaseCurrent, oldDelivered = false, currentDelivered = false;
    const oldReceipt = new Promise(resolve => { releaseOld = resolve; });
    const currentFailure = new Promise(resolve => { releaseCurrent = resolve; });
    const attempts = [];
    await page.route("**/comments?**", async route => {
      if (route.request().method() !== "POST") { await route.continue(); return; }
      attempts.push({ body: route.request().postDataJSON(), mutationId: route.request().headers()["x-feedback-mutation"] });
      if (attempts.length === 1) {
        const response = await route.fetch();
        assert.equal(response.status(), 200);
        await oldReceipt;
        await route.fulfill({ response });
        oldDelivered = true;
      } else if (attempts.length === 2) {
        await currentFailure;
        await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: "Controlled current write failure." }) });
        currentDelivered = true;
      } else await route.continue();
    });
    try {
      await begin("Lagret før versjonsbytte.");
      const started = Date.now();
      await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click();
      await ui.locator(".compose-error").waitFor({ state: "visible", timeout: 15000 });
      assert(Date.now() - started >= 11500, "The original response must outlive the actual request timeout.");
      assert.deepEqual((await snapshot()).comments.map(item => item.text), ["Lagret før versjonsbytte."]);
      await ui.getByRole("button", { name: "Forkast", exact: true }).click();
      await ui.locator('[data-action="panel"]').click();
      await ui.getByRole("button", { name: "Send 1 innspill", exact: true }).click();
      await until(async () => (await snapshot()).submission === 1, "The accepted first comment was not submitted before changing versions.");
      publish("Neste versjon");
      // The refresh control stays visible but disabled while an automatic refresh runs.
      const nextHeading = frame.getByRole("heading", { name: "Neste versjon", exact: true }), refresh = ui.locator('[data-action="refresh"]');
      await until(async () => await nextHeading.count() > 0 || (await refresh.isVisible() && await refresh.isEnabled()), "The next sketch version was not announced.");
      if (await nextHeading.count() === 0) await refresh.click();
      await nextHeading.waitFor();
      await ui.getByRole("button", { name: "Endre", exact: true }).click();
      await frame.getByRole("heading", { name: "Neste versjon", exact: true }).click();
      await ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Nytt utkast som ikke er lagret.");
      await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click();
      await until(() => attempts.length === 2, "The next version's write was not intercepted.");
      assert.equal(await ui.locator(".composer").getAttribute("aria-busy"), "true");
      releaseOld();
      await until(() => oldDelivered, "The old version's receipt was not delivered.");
      await page.waitForTimeout(150);
      assert.equal(await ui.locator(".composer").isVisible(), true, "An earlier document's receipt must not close the current unsaved draft.");
      assert.equal(await ui.locator(".composer").getAttribute("aria-busy"), "true", "The current save must await its own result.");
      releaseCurrent();
      await ui.locator(".compose-error").waitFor({ state: "visible" });
      assert.equal(await ui.getByLabel("Hva vil du endre?", { exact: true }).inputValue(), "Nytt utkast som ikke er lagret.");
      assert.equal((await snapshot()).comments.length, 1);
      assert.equal(attempts.length, 2, "Neither an old receipt nor a current failure may trigger an automatic retry.");
      await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click();
      await ui.getByRole("button", { name: "Send 1 innspill", exact: true }).waitFor();
      assert.equal(attempts.length, 3);
      assert.equal(attempts[1].mutationId, attempts[2].mutationId, "An explicit unchanged retry still recovers the current document's intent.");
      assert.notEqual(attempts[0].body.screen, attempts[1].body.screen);
      assert.deepEqual((await snapshot()).comments.map(item => item.text), ["Lagret før versjonsbytte.", "Nytt utkast som ikke er lagret."]);
      return { writesAttempted: attempts.length, checks: ["actual timeout before version change", "old document receipt ignored", "current failure retains draft", "explicit retry saves current version"] };
    } finally {
      releaseOld(); releaseCurrent();
      if (attempts.length >= 1) await until(() => oldDelivered, "Old intercepted response was not released.");
      if (attempts.length >= 2) await until(() => currentDelivered, "Current intercepted response was not released.");
    }
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
  const report = { passed: results.every(result => result.passed), cases: results, limits: ["Controlled local request and response interruptions; no model or native app session is used."] };
  if (evidence) fs.writeFileSync(path.join(evidence, "retry-results.json"), JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report));
  if (!report.passed) process.exitCode = 1;
})().catch(error => { console.error(error.message); process.exitCode = 1; });
