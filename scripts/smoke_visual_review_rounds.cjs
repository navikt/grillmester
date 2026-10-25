#!/usr/bin/env node
"use strict";

// Longer review rounds with synthetic roles, isolated sessions and real UI input.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createRequire } = require("node:module");
const { spawn } = require("node:child_process");
// Juster is one of the Endre tools; open Endre first when its bar is hidden.
async function openAdjust(ui) {
  const adjust = ui.getByRole("button", { name: "Juster", exact: true });
  if (!(await adjust.isVisible())) await ui.getByRole("button", { name: "Endre", exact: true }).click();
  await adjust.click();
}
const options = new Map();
for (let index = 2; index < process.argv.length; index += 1) {
  const flag = process.argv[index];
  if (flag === "--headed") { options.set(flag, true); continue; }
  if (!["--playwright-module", "--browser-channel", "--evidence-dir", "--aksel-project", "--case"].includes(flag) || !process.argv[index + 1] || process.argv[index + 1].startsWith("--")) {
    console.error("Usage: node scripts/smoke_visual_review_rounds.cjs [--playwright-module PATH] [--browser-channel chrome] [--headed] [--evidence-dir DIRECTORY] [--aksel-project DIRECTORY] [--case NAME]"); process.exit(2);
  }
  options.set(flag, process.argv[++index]);
}
let chromium;
try { ({ chromium } = require(options.get("--playwright-module") || "playwright")); }
catch { console.error("Supply an existing Playwright installation. Nothing was installed."); process.exit(2); }
const runtime = path.resolve(__dirname, "../plugin/skills/design-prototype/scripts");
const evidence = options.has("--evidence-dir") ? path.resolve(options.get("--evidence-dir")) : null;
if (evidence) fs.mkdirSync(evidence, { recursive: true });
let aksel;
if (options.has("--aksel-project")) {
  const project = path.resolve(options.get("--aksel-project")), installed = createRequire(path.join(project, "package.json"));
  const react = installed("react"), components = installed("@navikt/ds-react"), { renderToStaticMarkup } = installed("react-dom/server");
  const packageRoot = path.join(project, "node_modules/@navikt");
  const version = JSON.parse(fs.readFileSync(path.join(packageRoot, "ds-react/package.json"))).version;
  assert.equal(version, JSON.parse(fs.readFileSync(path.join(packageRoot, "ds-css/package.json"))).version);
  const css = ["index.min.css", "index.css"].map(name => path.join(packageRoot, "ds-css/dist", name)).find(file => fs.existsSync(file));
  assert(css, "The supplied project must contain installed Aksel CSS.");
  aksel = { version, css, render: (name, props, child) => renderToStaticMarkup(react.createElement(components[name], props, child)) };
}
const escape = text => text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll('"', "&quot;");
const heading = (text, level = "1") => aksel ? aksel.render("Heading", { size: level === "1" ? "large" : "medium", level }, text) : `<h${level}>${escape(text)}</h${level}>`;
const button = text => aksel ? aksel.render("Button", { type: "button", variant: "secondary" }, text) : `<button type="button">${escape(text)}</button>`;
const variants = [{ key: "guided", label: "Ett steg om gangen" }, { key: "summary", label: "Samlet avklaring" }, { key: "conversation", label: "Samtalen først" }];
function descriptor(initial = "clear") {
  return { version: 1, variants, targets: variants.map(({ key }) => ({ key: "next-step", variant: key, label: "Neste steg", controls: [{ id: "detail", label: "Mengde forklaring", type: "select", initial, options: [{ value: "clear", label: "Kort forklaring" }, { value: "full", label: "Utfyllende forklaring" }] }] })) };
}
function sketch(title = "Hvordan avklarer vi neste steg sammen?", initial = "clear") {
  return `<style>.review-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--ax-space-24,24px)}.review-card{min-width:0;padding:var(--ax-space-24,24px);border:1px solid var(--ax-border-neutral-subtle,#b9c2cb);border-radius:var(--ax-radius-12,12px)}.review-card h2{overflow-wrap:anywhere}.review-step{padding:var(--ax-space-16,16px);margin-block:var(--ax-space-16,16px);background:var(--ax-bg-neutral-soft,#f1f2f4)}.review-step .detail{display:none}.review-step[data-vc-setting-detail=full] .detail{display:block}.review-card button{max-width:100%}.review-card p{line-height:1.5}@media(max-width:900px){.review-grid{grid-template-columns:1fr}}</style><main>${heading(title)}<p>Samme situasjon i tre retninger: Det er ti dager til neste møte, én opplysning mangler, og du kan be om hjelp.</p><div data-vc-variants class="review-grid">${variants.map(({ key, label }, index) => `<section data-vc-variant="${key}" class="review-card">${heading(label, "2")}${index === 0 ? "<ol><li>Se hva som mangler</li><li>Velg hvem som følger opp</li><li>Bekreft neste steg</li></ol>" : index === 1 ? "<dl><dt>Tid igjen</dt><dd>Ti dager</dd><dt>Til avklaring</dt><dd>Én opplysning</dd><dt>Hjelp</dt><dd>Avtal en samtale</dd></dl>" : "<p>Hva vil du få avklart før møtet?</p><blockquote>Jeg vil vite hva jeg må gjøre selv, og hva jeg kan få hjelp til.</blockquote>"}<section data-vc-key="next-step" data-vc-setting-detail="${initial}" class="review-step"><h3>Neste steg</h3><p>Velg hvem som følger opp opplysningen.</p><p class="detail">Du kan be om hjelp hvis du er usikker. Vi blir enige om én tydelig oppgave før neste møte.</p></section>${button(index === 0 ? "Gå videre" : index === 1 ? "Bekreft planen" : "Avtal samtale")}</section>`).join("")}</div></main>`;
}
async function until(check, label, timeout = 12000) {
  const deadline = Date.now() + timeout;
  do { const value = await check(); if (value) return value; await new Promise(resolve => setTimeout(resolve, 80)); } while (Date.now() < deadline);
  throw new Error(`Timed out: ${label}`);
}
async function stop(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const closed = new Promise(resolve => child.once("close", resolve));
  child.kill("SIGTERM"); const timer = setTimeout(() => child.kill("SIGKILL"), 5000);
  await closed; clearTimeout(timer);
}
function start(child) {
  return new Promise((resolve, reject) => {
    let buffer = "", done = false;
    const timer = setTimeout(() => finish(new Error("Preview startup timed out.")), 5000);
    function finish(error, value) { if (done) return; done = true; clearTimeout(timer); error ? reject(error) : resolve(value); }
    child.stdout.on("data", data => { buffer += data; if (buffer.includes("\n") && !done) { try { const info = JSON.parse(buffer.split("\n")[0]); assert.equal(info.type, "server-started"); finish(null, info); } catch (error) { finish(error); } } });
    child.once("error", error => finish(error)); child.once("close", () => finish(new Error("Preview closed before startup.")));
  });
}
function command(info, action, extra = []) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [path.join(runtime, "comments.js"), action, "--state-dir", info.state_dir, ...extra]);
    let out = "", err = "";
    const timer = setTimeout(() => child.kill("SIGKILL"), 20000);
    child.stdout.on("data", data => { out += data; }); child.stderr.on("data", data => { err += data; });
    child.once("error", error => { clearTimeout(timer); reject(error); });
    child.once("close", code => { clearTimeout(timer); if (code) reject(new Error(err || `Feedback command failed (${code}).`)); else { try { resolve(JSON.parse(out)); } catch { reject(new Error("Feedback command returned invalid JSON.")); } } });
  });
}
function controls(page) {
  const frame = page.frameLocator("#vc-preview"), ui = frame.locator("[data-visual-feedback]");
  const workshop = ui.getByRole("region", { name: "Juster skissen", exact: true });
  return {
    page, frame, ui, workshop,
    closeFeedback: async () => { const close = ui.getByRole("button", { name: "Lukk innspill", exact: true }); if (await close.isVisible()) await close.click(); },
    openFeedback: async () => { if (!(await ui.getByRole("region", { name: "Innspill til prototypen", exact: true }).isVisible())) await ui.locator('[data-action="panel"]').click(); },
    adjust: async () => { if (!(await workshop.isVisible())) await openAdjust(ui); },
    note: async (text, selector = "h1") => {
      const close = ui.getByRole("button", { name: "Lukk innspill", exact: true }); if (await close.isVisible()) await close.click();
      const comment = ui.getByRole("button", { name: "Endre", exact: true }); if (await ui.locator('[data-action="change-ask"]').getAttribute("aria-pressed") !== "true") await comment.click();
      await frame.locator(selector).first().click(); await ui.getByLabel("Hva vil du endre?", { exact: true }).fill(text);
    },
    save: async () => { await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click(); await ui.getByRole("button", { name: "Lagre innspill", exact: true }).waitFor({ state: "hidden" }); },
  };
}
async function runCase(context, testcase) {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "grillmester-review-rounds-"));
  const project = path.join(temporary, "project"); fs.mkdirSync(project);
  if (aksel) { const css = path.join(project, "node_modules/@navikt/ds-css/dist"); fs.mkdirSync(css, { recursive: true }); fs.copyFileSync(aksel.css, path.join(css, "index.min.css")); }
  const child = spawn(process.execPath, [path.join(runtime, "server.js"), "--project-dir", project], { stdio: ["ignore", "pipe", "pipe"] });
  const pages = [], browserErrors = [], remoteResources = [];
  let current;
  try {
    const info = await start(child);
    const newTab = async () => {
      const page = await context.newPage(); pages.push(page); page.setDefaultTimeout(7000);
      if (!testcase.zoom) await page.setViewportSize({ width: 1440, height: 1000 });
      page.on("pageerror", error => browserErrors.push(error.message));
      page.on("requestfinished", request => { if (!request.url().startsWith(new URL(info.url).origin) && !/^(data|blob):/.test(request.url())) remoteResources.push(new URL(request.url()).origin); });
      await page.goto(info.url); const item = controls(page); await item.ui.getByRole("button", { name: "Endre", exact: true }).waitFor(); return item;
    };
    let sequence = 0;
    const write = (title, initial = "clear") => { const stem = `${String(++sequence).padStart(2, "0")}-review`; fs.writeFileSync(path.join(info.screen_dir, `${stem}.design.json`), JSON.stringify(descriptor(initial))); fs.writeFileSync(path.join(info.screen_dir, `${stem}.html`), sketch(title, initial)); };
    write(); current = await newTab();
    const list = () => command(info, "list");
    const send = async (view, count) => {
      const before = await list(); await view.openFeedback(); await view.ui.getByRole("button", { name: `Send ${count} innspill`, exact: true }).click();
      const result = await command(info, "wait", ["--after", String(before.submission), "--timeout", "10"]); assert.equal(result.type, "feedback-submission"); return result;
    };
    const screenshot = async (name, view = current) => { if (evidence) { if (testcase.name !== "disconnected-draft") await view.page.locator("#vc-status").filter({ hasText: /^Tilkoblet$/ }).waitFor(); await view.page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))); if (testcase.zoom) { const client = await context.newCDPSession(view.page); try { const capture = await client.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false }); fs.writeFileSync(path.join(evidence, `${testcase.name}-${name}.png`), Buffer.from(capture.data, "base64")); } finally { await client.detach(); } } else await view.page.screenshot({ path: path.join(evidence, `${testcase.name}-${name}.png`), animations: "disabled" }); } };
    const metrics = await testcase.run({ ...current, newTab, write, list, send, screenshot, info, context, stop: () => stop(child) });
    assert.deepEqual(browserErrors, [], "Review rounds must not cause browser exceptions."); assert.deepEqual(remoteResources, [], "No external resource may finish loading.");
    return { name: testcase.name, role: testcase.role, status: "passed", outcomes: testcase.outcomes, ...(metrics ? { metrics } : {}) };
  } catch (error) {
    if (current && evidence) await current.page.screenshot({ path: path.join(evidence, `${testcase.name}-failure.png`), animations: "disabled" }).catch(() => {});
    return { name: testcase.name, role: testcase.role, status: "failed", error: error.message.replace(/http:\/\/127\.0\.0\.1:[^\s)]+/g, "[local preview]") };
  } finally { for (const page of pages) await page.close(); await stop(child); fs.rmSync(temporary, { recursive: true, force: true }); }
}
const cases = [
  {
    name: "shared-review", role: "Facilitator with two open review tabs",
    outcomes: ["An outdated tab cannot send unseen additions from the other tab", "Saved items become visible in both tabs", "One deliberate batch reaches the recipient without duplicate items"],
    async run(view) {
      const { page, ui, newTab, note, save, list, screenshot, send } = view;
      await note("Vis ansvaret for neste steg tydelig."); await save();
      const frozen = await list(), second = await newTab(); await second.openFeedback();
      await until(async () => await second.ui.locator(".comment").count() === 1, "first note in second tab");
      await page.route("**/comments?*", async route => route.request().method() === "GET" ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(frozen) }) : route.continue());
      await second.note("Ta også med hvordan jeg kan be om hjelp.", '[data-vc-variant="conversation"] h2'); await second.save();
      assert.equal(await ui.locator(".comment").count(), 1, "The test must reproduce an outdated visible queue.");
      await screenshot("outdated-tab");
      const submitted = page.waitForResponse(response => response.url().includes("/comments/submit?") && response.request().method() === "POST");
      await ui.getByRole("button", { name: "Send 1 innspill", exact: true }).click(); await submitted;
      const after = await list(); const unseen = after.comments.find(item => item.text.includes("be om hjelp"));
      assert.equal(unseen.submission, 0, "Sending a reviewed item must not silently submit an unseen note from another tab.");
      await page.unroute("**/comments?*"); await until(async () => await ui.locator(".comment").count() === 2, "updated shared queue");
      const count = after.comments.filter(item => item.submission === 0).length;
      const batch = await send(view, count); assert.equal(batch.comments.length, count);
      await until(async () => (await second.ui.getByRole("button", { name: "Send innspill", exact: true }).isDisabled()), "second tab sees completed submission");
      assert.equal((await list()).comments.length, 2); await screenshot("shared-submission"); await second.page.close();
    },
  },
  {
    name: "change-direction", role: "Service designer changing direction after two reviews",
    outcomes: ["A newly written sketch waits while a local comment is unfinished", "The old comment keeps its original screen after the new layout opens", "A release and replacement decision are delivered as an explicit new round"],
    async run(view) {
      const { ui, frame, workshop, adjust, list, send, closeFeedback, write, note, save, screenshot } = view;
      await adjust(); await workshop.getByLabel("Velg del", { exact: true }).selectOption("guided/next-step"); await workshop.getByRole("button", { name: "Behold dette", exact: true }).click();
      const first = await send(view, 1); const kept = first.decisions[0]; await closeFeedback();
      write("Andre runde: Behold tydelig ansvar"); await frame.getByRole("heading", { name: "Andre runde: Behold tydelig ansvar", exact: true }).waitFor();
      await note("Etter ny gjennomgang trenger vi samtalen før oppgaven.");
      const screenBefore = (await list()).screens.at(-1).screen;
      write("Tredje runde: Samtalen kommer først", "full");
      await ui.getByRole("button", { name: "Vis ny versjon", exact: true }).waitFor(); assert(await ui.getByRole("button", { name: "Vis ny versjon", exact: true }).isDisabled());
      assert.equal(await ui.getByLabel("Hva vil du endre?", { exact: true }).inputValue(), "Etter ny gjennomgang trenger vi samtalen før oppgaven.");
      await screenshot("new-layout-waits"); await save(); const second = await send(view, 1); assert.equal(second.comments[0].screen, screenBefore);
      await frame.getByRole("heading", { name: "Tredje runde: Samtalen kommer først", exact: true }).waitFor(); await adjust();
      const previous = workshop.locator(`article[data-decision="${kept.id}"]`); assert((await previous.innerText()).includes("Må følges opp"));
      await previous.getByRole("button", { name: "Slutt å beholde", exact: true }).click(); await ui.getByRole("region", { name: "Innspill til prototypen", exact: true }).waitFor(); await closeFeedback(); await adjust();
      await workshop.getByLabel("Velg del", { exact: true }).selectOption("conversation/next-step"); await workshop.getByLabel("Merknad", { exact: true }).fill("Samtalen skal avklare ansvaret sammen med brukeren."); await workshop.getByRole("button", { name: "Behold dette", exact: true }).click();
      const third = await send(view, 2); assert.equal(third.decisions.find(item => item.id === kept.id).state, "released");
      assert.equal(third.decisions.find(item => item.state === "active").variant, "conversation");
      const oldCard = ui.locator(`article[data-id="${second.comments[0].id}"]`); assert((await oldCard.innerText()).includes("Tidligere versjon")); await screenshot("explicit-new-direction");
    },
  },
  {
    name: "qualified-approval", role: "Domain reviewer accepting a part while keeping a reservation open",
    outcomes: ["An accepted part and a separate reservation remain distinct", "A reply on an earlier screen remains readable after further work", "Reopening the reservation can be submitted as another round without releasing the accepted part"],
    async run(view) {
      const { workshop, adjust, note, save, send, closeFeedback, frame, ui, write, info, screenshot } = view;
      await adjust(); await workshop.getByLabel("Velg del", { exact: true }).selectOption("summary/next-step"); await workshop.getByLabel("Merknad", { exact: true }).fill("Behold den felles oppsummeringen av ansvar."); await workshop.getByRole("button", { name: "Behold dette", exact: true }).click(); await closeFeedback();
      await note("Jeg støtter retningen, men hjelpen må beskrives før vi går videre."); await save(); const first = await send(view, 2); const reservation = first.comments[0], decision = first.decisions[0];
      write("Ny gjennomgang med tydeligere hjelp"); await frame.getByRole("heading", { name: "Ny gjennomgang med tydeligere hjelp", exact: true }).waitFor();
      await command(info, "resolve", ["--id", reservation.id, "--reply", "Vi har lagt til veien til hjelp før neste steg."]); await view.openFeedback();
      const card = ui.locator(`article[data-id="${reservation.id}"]`); await card.getByText("Vi har lagt til veien til hjelp før neste steg.", { exact: false }).waitFor();
      await card.getByRole("button", { name: "Åpne igjen", exact: true }).click(); await ui.getByRole("button", { name: "Send 1 innspill", exact: true }).waitFor();
      await screenshot("reservation-reopened"); const second = await send(view, 1);
      assert.equal(second.comments.length, 1); assert.equal(second.comments[0].id, reservation.id); assert.equal(second.comments[0].status, "open");
      assert.equal(second.decisions.find(item => item.id === decision.id).state, "active"); assert.equal(second.comments[0].reply, "Vi har lagt til veien til hjelp før neste steg.");
    },
  },
  {
    name: "zoomed-review", role: "Participant using 200 percent browser zoom and reduced motion", zoom: true,
    outcomes: ["The browser reports real 200 percent zoom, with a smaller CSS viewport", "A complete adjustment can be written and sent without clipped actions", "Comparison and close controls remain reachable at the measured zoom"],
    async run(view) {
      const { page, context, ui, frame, workshop, adjust, send, closeFeedback, screenshot } = view;
      const initial = await page.evaluate(() => ({ width: innerWidth, height: innerHeight, dpr: devicePixelRatio }));
      const settings = await context.newPage();
      try {
        await settings.goto("chrome://settings/appearance"); await settings.locator("#zoomLevel").selectOption("2"); await page.bringToFront();
        await until(async () => (await page.evaluate(() => devicePixelRatio)) >= initial.dpr * 1.9, "actual browser zoom");
        const zoomed = await page.evaluate(() => ({ width: innerWidth, height: innerHeight, dpr: devicePixelRatio }));
        assert(Math.abs(zoomed.width * 2 - initial.width) <= 2, "Browser zoom must reduce the CSS viewport, not just magnify an image.");
        await page.emulateMedia({ reducedMotion: "reduce" }); await adjust();
        const panelBounds = await workshop.boundingBox(); assert(panelBounds && panelBounds.x >= 0 && panelBounds.y >= 0 && panelBounds.x + panelBounds.width <= zoomed.width + 1 && panelBounds.y + panelBounds.height <= zoomed.height + 1, "The adjustment panel must fit the actual zoomed viewport.");
        const close = workshop.getByRole("button", { name: "Lukk justeringer", exact: true }); await close.click(); await adjust();
        await workshop.getByLabel("Velg del", { exact: true }).selectOption("conversation/next-step"); await workshop.getByLabel("Mengde forklaring", { exact: true }).selectOption("full"); await workshop.getByLabel("Merknad", { exact: true }).fill("Jeg trenger hele forklaringen når jeg leser med forstørrelse.");
        await workshop.getByLabel("Merknad", { exact: true }).scrollIntoViewIfNeeded(); await screenshot("note-at-200-percent");
        await workshop.getByRole("button", { name: "Legg til innspill", exact: true }).click(); const batch = await send(view, 1); assert.equal(batch.comments[0].adjustment.values.detail, "full"); await closeFeedback();
        await adjust(); await workshop.getByRole("button", { name: "Sammenlign varianter", exact: true }).click(); await ui.getByLabel("Høyre variant", { exact: true }).selectOption("conversation");
        const comparisonBounds = await ui.locator(".compare-bar").boundingBox(); assert(comparisonBounds && comparisonBounds.x >= 0 && comparisonBounds.x + comparisonBounds.width <= zoomed.width + 1, "The comparison controls must fit without horizontal scrolling at 200 percent.");
        assert(!(await frame.locator("html").evaluate(node => node.scrollWidth > node.clientWidth + 1)), "The zoomed sketch must not require horizontal scrolling.");
        await screenshot("comparison-at-200-percent"); await ui.getByRole("button", { name: "Avslutt sammenligning", exact: true }).click();
        return { initial, zoomed, zoom: 2, reducedMotion: true };
      } finally { await settings.locator("#zoomLevel").selectOption("1").catch(() => {}); await settings.close(); }
    },
  },
  {
    name: "disconnected-draft", role: "Meeting participant whose local preview stops while writing",
    outcomes: ["A temporary outage preserves the draft and reports a failed save", "Reconnecting restores ordinary saving and submission without reloading", "Stopping the session cannot be mistaken for a successfully saved note", "The written draft stays accessible for copying after connection loss", "The interface explains that a new session is needed"],
    async run(view) {
      const { page, ui, note, save, list, send, stop, screenshot } = view;
      const recoveryNote = "Et kort nettbrudd skal ikke miste forbeholdet mitt.";
      await note(recoveryNote);
      await page.locator("#vc-status").filter({ hasText: /^Tilkoblet$/ }).waitFor();
      // Only the browser's feedback reads fail; the local session remains alive.
      // This also verifies that a healthy version endpoint alone cannot report recovery.
      await page.route("**/comments?*", route => route.request().method() === "GET"
        ? route.fulfill({ status: 503, contentType: "application/json", body: '{"error":"Temporarily unavailable"}' })
        : route.continue());
      try {
        await page.locator("#vc-paused").waitFor({ state: "visible", timeout: 22000 });
        await page.getByRole("button", { name: "Se skissen og kopier utkast", exact: true }).click();
        await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click();
        await ui.locator(".compose-error").waitFor({ state: "visible" });
        assert.equal(await ui.getByLabel("Hva vil du endre?", { exact: true }).inputValue(), recoveryNote);
        assert.equal((await list()).comments.length, 0, "A failed offline save must not be reported as saved.");
        await screenshot("temporary-outage");
      } finally { await page.unroute("**/comments?*"); }
      await page.locator("#vc-status").filter({ hasText: /^Tilkoblet$/ }).waitFor();
      await save();
      const recovered = await send(view, 1);
      assert.equal(recovered.comments.length, 1); assert.equal(recovered.comments[0].text, recoveryNote);
      assert.equal((await list()).comments.length, 1, "Recovery must not duplicate a formerly failed save.");
      await screenshot("reconnected-and-sent");
      await note("Ta vare på dette forbeholdet: Vi må avtale hvem som følger opp."); await stop();
      await page.locator("#vc-paused").waitFor({ state: "visible", timeout: 22000 }); await screenshot("connection-lost");
      await page.getByRole("button", { name: "Se skissen og kopier utkast", exact: true }).click();
      const draft = ui.getByLabel("Hva vil du endre?", { exact: true }); assert.equal(await draft.inputValue(), "Ta vare på dette forbeholdet: Vi må avtale hvem som følger opp.");
      await draft.click(); await page.keyboard.press(process.platform === "darwin" ? "Meta+A" : "Control+A");
      const selected = await draft.evaluate(node => node.selectionEnd - node.selectionStart); assert.equal(selected, (await draft.inputValue()).length, "A participant must be able to select the existing draft to copy it after disconnection.");
      await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click(); await ui.locator(".compose-error").waitFor({ state: "visible" });
      assert.equal(await draft.inputValue(), "Ta vare på dette forbeholdet: Vi må avtale hvem som følger opp."); await screenshot("draft-preserved");
    },
  },
];
async function main() {
  const selected = options.has("--case") ? cases.filter(item => item.name === options.get("--case")) : cases;
  if (!selected.length) { console.error(`Unknown case. Available: ${cases.map(item => item.name).join(", ")}`); process.exitCode = 2; return; }
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "grillmester-review-browser-"));
  let context;
  const results = [];
  try {
    context = await chromium.launchPersistentContext(profile, { headless: !options.has("--headed"), viewport: null, args: ["--window-size=1440,1000"], ...(options.has("--browser-channel") ? { channel: options.get("--browser-channel") } : {}) });
    for (const testcase of selected) { const result = await runCase(context, testcase); results.push(result); console.log(`${result.status === "passed" ? "PASS" : "FAIL"}: ${result.name}${result.error ? ` — ${result.error}` : ""}`); }
  } finally { await context?.close(); fs.rmSync(profile, { recursive: true, force: true }); }
  const report = { kind: "synthetic-review-rounds", browser: options.get("--browser-channel") || "chromium", headed: options.has("--headed"), aksel: aksel?.version || null, results };
  if (evidence) fs.writeFileSync(path.join(evidence, "review-rounds-results.json"), `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify(report)); if (results.some(item => item.status !== "passed")) process.exitCode = 1;
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
