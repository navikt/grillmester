#!/usr/bin/env node
"use strict";

// Optional, isolated browser smoke. Reuses an installed browser and Playwright.
// All example screens and state belong to the temporary preview session.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");

const options = new Map();
const args = process.argv.slice(2);
for (let index = 0; index < args.length; index += 1) {
  if (args[index] === "--headed") { options.set("--headed", true); continue; }
  if (!["--playwright-module", "--browser-channel", "--evidence-dir"].includes(args[index]) || !args[index + 1] || args[index + 1].startsWith("--")) {
    console.error("Usage: node scripts/smoke_visual_workshop.cjs [--playwright-module ABSOLUTE_PATH] [--browser-channel chrome] [--headed] [--evidence-dir DIRECTORY]");
    process.exit(2);
  }
  options.set(args[index], args[++index]);
}

let chromium;
try { ({ chromium } = require(options.get("--playwright-module") || "playwright")); }
catch {
  console.error("Playwright is unavailable. Supply --playwright-module with an existing installation; no dependencies were installed.");
  process.exit(2);
}
const repo = path.resolve(__dirname, "..");
const runtime = path.join(repo, "plugin/skills/design-prototype/scripts");
const browserChannel = options.get("--browser-channel");
const evidence = options.has("--evidence-dir") ? path.resolve(options.get("--evidence-dir")) : null;
if (evidence) fs.mkdirSync(evidence, { recursive: true });
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "grillmester-workshop-smoke-"));
const project = path.join(temporary, "project");
fs.mkdirSync(project);

function cli(command, info, extra = []) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [path.join(runtime, "comments.js"), command, "--state-dir", info.state_dir, ...extra]);
    let stdout = "", stderr = "";
    const timer = setTimeout(() => child.kill("SIGKILL"), 20000);
    child.stdout.on("data", value => { stdout += value; });
    child.stderr.on("data", value => { stderr += value; });
    child.once("error", error => { clearTimeout(timer); reject(error); });
    child.once("close", code => {
      clearTimeout(timer);
      if (code) { reject(new Error(stderr || `Feedback command failed (${code}).`)); return; }
      try { resolve(JSON.parse(stdout)); } catch { reject(new Error("Feedback command returned invalid JSON.")); }
    });
  });
}

function startServer(child) {
  return new Promise((resolve, reject) => {
    let buffer = "", settled = false;
    const timer = setTimeout(() => finish(new Error("Preview server startup timed out.")), 5000);
    function finish(error, value) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      error ? reject(error) : resolve(value);
    }
    child.stdout.on("data", value => {
      buffer += value;
      if (!buffer.includes("\n") || settled) return;
      try {
        const info = JSON.parse(buffer.split("\n")[0]);
        if (info.type !== "server-started") throw new Error("Preview server did not start.");
        finish(null, info);
      } catch (error) { finish(error); }
    });
    child.stderr.on("data", value => process.stderr.write(value));
    child.once("error", error => finish(error));
    child.once("close", code => finish(new Error(`Preview server exited before startup (${code}).`)));
  });
}

const styles = `<style>
:root{--ax-bg-sunken:#eef0f3;--ax-bg-default:#fff;--ax-text-default:#252b35;--ax-text-subtle:#555d69;--ax-border-subtle:#ccd2db;--ax-border-accent:#2467ac;--ax-bg-accent-soft:#eaf3ff;--ax-bg-accent-strong:#2467ac;--ax-text-accent:#1b5186;--ax-text-contrast:#fff;--ax-space-8:8px;--ax-space-12:12px;--ax-space-16:16px;--ax-space-24:24px;--ax-space-32:32px;--ax-space-40:40px}
.workshop-fixture{font-family:system-ui,sans-serif;color:#252b35}.workshop-fixture h1{font-size:30px}.fixture-variants{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}.fixture-variant{min-width:0;padding:24px;border:1px solid #ccd2db;border-radius:12px;background:#fff}.fixture-summary{padding:16px;border:2px solid #ccd2db;border-radius:8px}.fixture-items{display:grid;gap:16px;padding-left:22px}.fixture-summary[data-vc-setting-density="compact"] .fixture-items{gap:4px}.fixture-summary[data-vc-setting-spacing="tight"]{padding:8px}.fixture-summary[data-vc-setting-spacing="balanced"]{padding:12px}.fixture-summary[data-vc-setting-spacing="spacious"]{padding:16px}.fixture-summary[data-vc-setting-emphasis="highlighted"]{border-color:#2467ac;background:#eaf3ff}.fixture-form{display:grid;gap:8px;margin-top:20px}.fixture-form input{padding:10px;font:inherit;border:1px solid #788393;border-radius:6px}@media(max-width:700px){.fixture-variants{grid-template-columns:1fr}.vc-content{margin:16px auto;padding:16px}.fixture-variant{padding:16px}}
</style>`;

function fixture(title = "Velg arbeidsoversikt", missingTarget = false) {
  return styles + `<main class="workshop-fixture"><h1>${title}</h1><p>Sammenlign prioritering og arbeidsflyt med samme oppgaver.</p><div data-vc-variants class="fixture-variants"><section data-vc-variant="list" class="fixture-variant"><h2>Prioritert liste</h2><section ${missingTarget ? "" : 'data-vc-key="summary-list"'} class="fixture-summary"><h3>Oppgaver som haster</h3><ul class="fixture-items"><li>Avklare møte · om 1 dag</li><li>Gjennomgå utkast · om 2 dager</li></ul></section></section><section data-vc-variant="board" class="fixture-variant"><h2>Arbeidsbrett</h2><section data-vc-key="summary-board" class="fixture-summary"><h3>Oppgaver i arbeid</h3><ul class="fixture-items"><li>Avklare møte · pågår</li><li>Gjennomgå utkast · ny</li></ul></section></section></div><label class="fixture-form">Privat prøveverdi<input id="not-for-feedback" name="not-for-feedback"></label><p class="unsupported-target">Denne teksten har ingen erklærte justeringer.</p></main>`;
}

function manifest(initial = "comfortable") {
  const controls = () => [
    { id: "density", label: "Tetthet", type: "select", initial, options: [{ value: "compact", label: "Tett" }, { value: "comfortable", label: "Romslig" }] },
    { id: "spacing", label: "Luft", type: "range", initial: "spacious", options: [{ value: "spacious", label: "Mye luft" }, { value: "balanced", label: "Balansert" }, { value: "tight", label: "Lite luft" }] },
    { id: "emphasis", label: "Fremhev", type: "toggle", initial: "ordinary", options: [{ value: "ordinary", label: "Vanlig" }, { value: "highlighted", label: "Fremhevet" }] },
  ];
  return {
    version: 1,
    variants: [{ key: "list", label: "Prioritert liste" }, { key: "board", label: "Arbeidsbrett" }],
    targets: [
      { key: "summary-list", variant: "list", label: "Prioriterte oppgaver", controls: controls() },
      { key: "summary-board", variant: "board", label: "Oppgaver på brettet", controls: controls() },
    ],
  };
}

async function screenshot(page, name) {
  if (!evidence) return;
  await page.locator("#vc-status").filter({ hasText: /^Tilkoblet$/ }).waitFor();
  await Promise.all(page.frames().map(frame => frame.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))));
  await page.screenshot({ path: path.join(evidence, path.basename(name)), animations: "disabled" });
}

async function stopServer(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const stopped = new Promise(resolve => child.once("close", resolve));
  child.kill("SIGTERM");
  const timer = setTimeout(() => child.kill("SIGKILL"), 5000);
  await stopped;
  clearTimeout(timer);
}

async function waitFor(check, description) {
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    const result = await check();
    if (result) return result;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out: ${description}`);
}

function selectionEvents(info) {
  const filename = path.join(info.state_dir, "events.jsonl");
  return fs.existsSync(filename) ? fs.readFileSync(filename, "utf8").trim() : "";
}

async function main() {
  const child = spawn(process.execPath, [path.join(runtime, "server.js"), "--project-dir", project], { stdio: ["ignore", "pipe", "pipe"] });
  let browser, page;
  try {
    const info = await startServer(child);
    let sequence = 0;
    function writeScreen(name, html, design) {
      const stem = `${String(++sequence).padStart(2, "0")}-${name}`;
      if (design !== undefined) fs.writeFileSync(path.join(info.screen_dir, `${stem}.design.json`), typeof design === "string" ? design : JSON.stringify(design));
      fs.writeFileSync(path.join(info.screen_dir, `${stem}.html`), html);
      return stem;
    }
    writeScreen("workshop", fixture(), manifest());
    browser = await chromium.launch({ headless: !options.has("--headed"), ...(browserChannel ? { channel: browserChannel } : {}) });
    page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.setDefaultTimeout(10000);
    const errors = [], completedRequests = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("requestfinished", request => completedRequests.push(request.url()));
    await page.goto(info.url);
    const frame = page.frameLocator("#vc-preview");
    const ui = frame.locator("[data-visual-feedback]");
    const list = () => cli("list", info);

    await runWorkshop({ page, frame, ui, info, list, writeScreen });

    assert.deepEqual(errors, [], errors.join("\n"));
    assert(completedRequests.every(url => url.startsWith(new URL(info.url).origin) || /^(data|blob):/.test(url)), "Unexpected completed remote request.");
    const result = {
      browser: browserChannel || "chromium",
      headed: options.has("--headed"),
      viewports: ["1440x1000", "390x844"],
      checks: ["declared-controls", "source-css", "local-reset", "structured-batch", "variant-comparison", "narrow-comparison", "narrow-heading-clearance", "narrow-overlay-close", "hidden-variant-pin", "no-spurious-selection", "keep", "fresh-release-enabled", "release-failure-retention", "accepted-decision-batch", "release", "version-mismatch", "historical-labels", "duplicate-target", "invalid-manifest", "keyboard", "area-comparison-boundary", "draft-retention", "field-privacy", "loopback-only"],
      errors,
    };
    if (evidence) fs.writeFileSync(path.join(evidence, "visual-workshop-test-results.json"), `${JSON.stringify(result, null, 2)}\n`);
    console.log(JSON.stringify(result));
  } catch (error) {
    if (page) await screenshot(page, "visual-workshop-failure.png").catch(() => {});
    throw error;
  } finally {
    try { await browser?.close(); }
    finally { await stopServer(child); fs.rmSync(temporary, { recursive: true, force: true }); }
  }
}

async function runWorkshop(context) {
  const { page, frame, ui, info, list, writeScreen } = context;
  await frame.getByRole("heading", { name: "Velg arbeidsoversikt" }).waitFor();
  await frame.getByLabel("Privat prøveverdi", { exact: true }).fill("PRIVAT_VERDI_SKAL_IKKE_BLI_INNSPILL");
  const summary = frame.locator('[data-vc-key="summary-list"]');
  const adjustment = ui.getByRole("region", { name: "Juster skissen", exact: true });
  const control = name => adjustment.getByLabel(name, { exact: true });
  const settings = () => summary.evaluate(node => ({
    density: node.getAttribute("data-vc-setting-density"),
    spacing: node.getAttribute("data-vc-setting-spacing"),
    emphasis: node.getAttribute("data-vc-setting-emphasis"),
    padding: getComputedStyle(node).paddingTop,
  }));
  const openWorkshop = async () => {
    if (!(await adjustment.isVisible())) await ui.getByRole("button", { name: "Juster", exact: true }).click();
    await adjustment.waitFor();
  };
  const closeWorkshop = async () => {
    if (await adjustment.isVisible()) await ui.getByRole("button", { name: "Lukk justeringer", exact: true }).click();
  };
  const send = async count => {
    const before = await list();
    const waiting = cli("wait", info, ["--after", String(before.submission), "--timeout", "10"]);
    await ui.getByRole("button", { name: `Send ${count} innspill`, exact: true }).click();
    const result = await waiting;
    assert.equal(result.type, "feedback-submission");
    return result;
  };
  const closeFeedback = async () => {
    const close = ui.getByRole("button", { name: "Lukk innspill", exact: true });
    if (await close.isVisible()) await close.click();
  };

  await ui.getByRole("button", { name: "Juster", exact: true }).focus();
  await page.keyboard.press("Enter");
  await adjustment.waitFor();
  await control("Velg del").selectOption("list/summary-list");
  await control("Tetthet").selectOption("compact");
  await control("Luft").focus();
  await page.keyboard.press("ArrowRight");
  await control("Fremhev").focus();
  await page.keyboard.press("Space");
  assert.deepEqual(await settings(), { density: "compact", spacing: "balanced", emphasis: "highlighted", padding: "12px" });
  assert.equal((await list()).comments.length, 0, "Control previews must not create submitted or saved comments.");
  assert.equal(selectionEvents(info), "", "Workshop controls must not generate legacy selection events.");
  await screenshot(page, "visual-workshop-controls.png");
  await adjustment.getByRole("button", { name: "Tilbakestill visning", exact: true }).click();
  const reset = await settings();
  assert([null, "comfortable"].includes(reset.density));
  assert([null, "spacious"].includes(reset.spacing));
  assert([null, "ordinary"].includes(reset.emphasis));
  assert.equal(reset.padding, "16px");
  await control("Tetthet").selectOption("compact");
  await control("Merknad").fill("Behold fristene synlige når oppgavene ligger tettere.");
  await adjustment.getByRole("button", { name: "Legg til innspill", exact: true }).click();
  const saved = await waitFor(async () => {
    const value = await list();
    return value.comments.some(item => item.kind === "adjustment") && value;
  }, "structured adjustment saved");
  const proposed = saved.comments.find(item => item.kind === "adjustment");
  assert.equal(proposed.submission, 0);
  assert.equal(proposed.adjustment.target, "summary-list");
  assert.equal(proposed.adjustment.variant, "list");
  assert.equal(proposed.adjustment.values.density, "compact");
  assert.equal(proposed.text, "Behold fristene synlige når oppgavene ligger tettere.");
  await closeFeedback();
  await openWorkshop();
  await control("Velg del").selectOption("list/summary-list");
  await adjustment.getByRole("button", { name: "Behold dette", exact: true }).click();
  const kept = await waitFor(async () => {
    const value = await list();
    return value.decisions?.find(item => item.state === "active" && item.target === "summary-list");
  }, "kept decision saved");
  assert.equal(kept.values.density, "compact");
  assert.equal(kept.submission, 0);
  const queuedRelease = ui.getByRole("region", { name: "Innspill til prototypen", exact: true }).getByRole("button", { name: "Frigi", exact: true });
  await waitFor(() => queuedRelease.isEnabled(), "newly saved keep can be released without another snapshot revision");
  const beforeKeepSubmission = await list();
  const unsentKeep = await cli("wait", info, ["--after", String(beforeKeepSubmission.submission), "--timeout", "0"]);
  assert(!unsentKeep.decisions.some(item => item.id === kept.id), "Unsent keeps must not become active decisions in the consumer wait result.");
  const firstBatch = await send(2);
  assert(firstBatch.comments.some(item => item.id === proposed.id));
  assert(firstBatch.decisions.some(item => item.id === kept.id && item.submission === firstBatch.submission));
  assert(!fs.readFileSync(path.join(info.state_dir, "comments.json"), "utf8").includes("PRIVAT_VERDI_SKAL_IKKE_BLI_INNSPILL"));
  console.log("PASS: keyboard controls, rendered preview/reset, structured feedback, keep and batch through the CLI.");

  await closeFeedback();
  await openWorkshop();
  const beforeCompare = await list();
  await adjustment.getByRole("button", { name: "Sammenlign varianter", exact: true }).click();
  const panes = frame.locator("[data-vc-variant]");
  const left = await panes.nth(0).boundingBox(), right = await panes.nth(1).boundingBox();
  assert(left && right && Math.abs(left.width - right.width) <= 1, "Comparison panes must have equal widths.");
  assert(right.x >= left.x + left.width - 1, "Desktop comparison must place the two variants beside each other.");
  assert.equal((await list()).comments.length, beforeCompare.comments.length, "Opening comparison must not send a preference.");
  assert.equal(selectionEvents(info), "");
  await screenshot(page, "visual-workshop-comparison.png");
  await page.setViewportSize({ width: 390, height: 844 });
  await ui.getByRole("button", { name: "Arbeidsbrett", exact: true }).focus();
  await page.keyboard.press("Space");
  assert(await frame.locator('[data-vc-variant="board"]').isVisible());
  assert(!(await frame.locator('[data-vc-variant="list"]').isVisible()), "Narrow comparison must show one chosen variant at a time.");
  const narrow = await ui.locator(".compare-bar").boundingBox();
  assert(narrow && narrow.x >= 0 && narrow.x + narrow.width <= 390, "Comparison controls must fit the narrow viewport.");
  const narrowHeading = await frame.getByRole("heading", { name: "Velg arbeidsoversikt", exact: true }).boundingBox();
  assert(narrowHeading && narrowHeading.y >= narrow.y + narrow.height - 1, "The mobile comparison toolbar must leave the page heading visible below it.");
  const narrowContent = await frame.locator("body > .vc-content").boundingBox();
  assert(narrowContent && narrowContent.y >= narrow.y + narrow.height - 1, "Comparison must reserve space for the first content, including a fallback notice.");
  assert(await ui.getByRole("button", { name: "Arbeidsbrett", exact: true }).evaluate(node => node.getRootNode().activeElement === node), "Switching comparison tabs must retain keyboard focus.");
  await waitFor(async () => !(await ui.locator(`.pin[data-id="${proposed.id}"]`).isVisible()), "hidden-variant comment pin disappears");
  await screenshot(page, "visual-workshop-narrow.png");
  await openWorkshop();
  const narrowPanel = await adjustment.boundingBox();
  assert(narrowPanel && narrowPanel.x >= 0 && narrowPanel.x + narrowPanel.width <= 390, "Workshop panel must fit the narrow viewport.");
  await screenshot(page, "visual-workshop-narrow-controls.png");
  await ui.getByRole("button", { name: "Lukk justeringer", exact: true }).click();
  assert(!(await adjustment.isVisible()), "A comparison toolbar must not intercept the narrow adjustment panel's close button.");
  await ui.getByRole("button", { name: "Foretrekk denne varianten", exact: true }).click();
  const preference = await waitFor(async () => (await list()).comments.find(item => item.kind === "variant"), "explicit variant preference");
  assert.equal(preference.variant, "board");
  assert.equal(preference.submission, 0);
  assert.equal(selectionEvents(info), "");
  await send(1);
  await page.setViewportSize({ width: 1440, height: 1000 });
  console.log("PASS: equal desktop panes, narrow variant switch and explicit preference without selection events.");

  await closeFeedback();
  await ui.getByRole("button", { name: "Kommenter", exact: true }).click();
  await ui.getByRole("button", { name: "Område", exact: true }).click();
  await frame.getByRole("heading", { name: "Velg arbeidsoversikt", exact: true }).focus();
  await page.keyboard.press("Enter");
  assert(!(await ui.getByRole("dialog").isVisible()), "New area comments must not capture comparison geometry.");
  assert.match(await ui.locator(".hint").innerText(), /Avslutt sammenligning for å markere et område/);
  const stopComparison = ui.getByRole("button", { name: "Avslutt sammenligning", exact: true });
  if (await stopComparison.isVisible()) await stopComparison.click();
  await frame.getByRole("heading", { name: "Velg arbeidsoversikt", exact: true }).focus();
  await page.keyboard.press("Enter");
  await ui.getByLabel("Hva vil du endre?").fill("Områdeutkastet skal ha samme forankring etter sammenligning.");
  await openWorkshop();
  await adjustment.getByRole("button", { name: "Sammenlign varianter", exact: true }).click();
  await ui.locator(".compare-bar").waitFor({ state: "visible" });
  await ui.getByRole("button", { name: "Fortsett utkast", exact: true }).click();
  assert(!(await ui.locator(".compare-bar").isVisible()), "Resuming an area draft must restore its original layout first.");
  assert.equal(await ui.getByLabel("Hva vil du endre?").inputValue(), "Områdeutkastet skal ha samme forankring etter sammenligning.");
  await ui.getByRole("button", { name: "Forkast", exact: true }).click();
  await closeWorkshop();
  await ui.getByRole("button", { name: "Kommenter", exact: true }).click();
  await ui.getByRole("button", { name: "Punkt", exact: true }).click();
  await frame.getByRole("heading", { name: "Velg arbeidsoversikt", exact: true }).focus();
  await page.keyboard.press("Enter");
  await ui.getByLabel("Hva vil du endre?").fill("Dette utkastet skal bevares mens neste versjon kommer.");
  writeScreen("changed", fixture("Arbeidsoversikt etter gjennomgang"), manifest());
  await ui.getByRole("button", { name: "Vis ny versjon", exact: true }).waitFor();
  assert(await ui.getByRole("button", { name: "Vis ny versjon", exact: true }).isDisabled());
  assert.equal(await ui.getByLabel("Hva vil du endre?").inputValue(), "Dette utkastet skal bevares mens neste versjon kommer.");
  await page.keyboard.press("Escape");
  assert(await frame.getByRole("heading", { name: "Velg arbeidsoversikt", exact: true }).evaluate(node => document.activeElement === node));
  await ui.getByRole("button", { name: "Fortsett utkast", exact: true }).click();
  await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click();
  await send(1);
  await frame.getByRole("heading", { name: "Arbeidsoversikt etter gjennomgang", exact: true }).waitFor();
  await openWorkshop();
  await adjustment.getByText("Må følges opp", { exact: true }).waitFor();
  const carried = (await list()).decisions.find(item => item.id === kept.id);
  assert.equal(carried.screen, kept.screen, "Kept decisions must retain the original screen identity.");
  assert.equal(carried.values.density, "compact");
  assert.equal(carried.state, "active");
  await adjustment.getByText("Må følges opp", { exact: true }).scrollIntoViewIfNeeded();
  await screenshot(page, "visual-workshop-decision-mismatch.png");
  await closeWorkshop();
  const missingDesign = manifest();
  missingDesign.targets = missingDesign.targets.filter(target => target.key !== "summary-list");
  writeScreen("missing-target", fixture("En del mangler i denne versjonen", true), missingDesign);
  await frame.getByRole("heading", { name: "En del mangler i denne versjonen", exact: true }).waitFor();
  await openWorkshop();
  await adjustment.getByText("Må følges opp", { exact: true }).waitFor();
  const missingDecision = adjustment.locator(`[data-decision="${kept.id}"]`);
  await missingDecision.getByRole("heading", { name: "Prioriterte oppgaver · Prioritert liste", exact: true }).waitFor();
  await missingDecision.getByText("Tetthet: Tett", { exact: true }).waitFor();
  assert.equal(await frame.locator('[data-vc-key="summary-list"]').count(), 0);
  await closeWorkshop();
  writeScreen("kept-version", fixture("Arbeidsoversikt med beholdt tetthet"), manifest("compact"));
  await frame.getByRole("heading", { name: "Arbeidsoversikt med beholdt tetthet", exact: true }).waitFor();
  await openWorkshop();
  assert.equal(await adjustment.getByText("Må følges opp", { exact: true }).count(), 0, "Matching declared values must not be reported as a mismatch.");
  await closeWorkshop();
  await ui.locator('[data-action="panel"]').click();
  await page.route("**/decisions/**", async route => route.request().method() === "PATCH"
    ? route.fulfill({ status: 503, contentType: "application/json", body: '{"error":"Unavailable"}' })
    : route.continue());
  await queuedRelease.click();
  await ui.locator(".panel-error").waitFor({ state: "visible" });
  assert((await ui.locator(".panel-error").innerText()).trim(), "A failed queue release must show an error in the visible feedback panel.");
  assert.equal((await list()).decisions.find(item => item.id === kept.id).state, "active", "A failed release must preserve the kept decision.");
  await page.unroute("**/decisions/**");
  await waitFor(() => queuedRelease.isEnabled(), "failed release restores its control");
  await closeFeedback();
  await openWorkshop();
  const decisions = ui.getByRole("region", { name: "Beholdes videre", exact: true });
  const beforeReleaseSubmission = await list();
  await decisions.getByRole("button", { name: "Frigi", exact: true }).click();
  await waitFor(async () => (await list()).decisions.some(item => item.id === kept.id && item.state === "released" && item.submission === 0), "released decision pending submission");
  const unsentRelease = await cli("wait", info, ["--after", String(beforeReleaseSubmission.submission), "--timeout", "0"]);
  assert(unsentRelease.decisions.some(item => item.id === kept.id && item.state === "active" && item.values.density === "compact"), "An unsent release must preserve the last submitted active constraint for the consumer.");
  const releasedBatch = await send(1);
  assert(releasedBatch.decisions.some(item => item.id === kept.id && item.state === "released"));
  await closeFeedback();
  await closeWorkshop();
  console.log("PASS: draft/focus preservation, retained decision identity, mismatch/missing target, matching new version and release.");

  const duplicateHtml = fixture("En tvetydig del skal ikke kunne justeres").replace(
    "<h3>Oppgaver som haster</h3>",
    '<h3>Oppgaver som haster</h3><div data-vc-key="summary-list">En annen del med samme nøkkel</div>',
  );
  writeScreen("duplicate-target", duplicateHtml, manifest());
  await frame.getByRole("heading", { name: "En tvetydig del skal ikke kunne justeres", exact: true }).waitFor();
  await openWorkshop();
  await control("Velg del").selectOption("list/summary-list");
  assert(await adjustment.getByRole("button", { name: "Legg til innspill", exact: true }).isDisabled(), "An ambiguous target must not allow adjustments.");
  assert(await adjustment.getByRole("button", { name: "Behold dette", exact: true }).isDisabled(), "An ambiguous target must not allow a keep decision.");
  assert(await control("Tetthet").isDisabled(), "An ambiguous target must not expose an active setting control.");
  assert.equal(await frame.locator('[data-vc-key="summary-list"][data-vc-setting-density]').count(), 0, "Ambiguous targets must not receive declared settings.");
  await closeWorkshop();

  await checkInvalidManifest(context);
}

async function checkInvalidManifest({ page, frame, ui, info, list, writeScreen }) {
  const invalid = manifest();
  invalid.targets[0].controls[0].options[0].value = "url(https://invalid.example/style)";
  writeScreen("invalid-manifest", fixture("Oppsettet må rettes"), invalid);
  await frame.getByRole("heading", { name: "Oppsettet må rettes" }).waitFor();
  await frame.getByText("Justeringspanelet er utilgjengelig. Skisseoppsettet må rettes.", { exact: true }).waitFor();
  assert.equal(await frame.locator("body").evaluate(() => window.__grillmesterVisualCompanionDesign), null);
  assert.equal(await frame.locator("[data-vc-setting-density]").count(), 0, "Invalid metadata must never activate a declared setting.");
  const before = await list();
  await ui.getByRole("button", { name: "Kommenter", exact: true }).click();
  await frame.getByRole("heading", { name: "Oppsettet må rettes" }).click();
  await ui.getByLabel("Hva vil du endre?").fill("Vanlige innspill skal fortsatt fungere når justeringsoppsettet er ugyldig.");
  await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click();
  await ui.getByRole("button", { name: "Send 1 innspill", exact: true }).waitFor();
  const waiting = cli("wait", info, ["--after", String(before.submission), "--timeout", "10"]);
  await ui.getByRole("button", { name: "Send 1 innspill", exact: true }).click();
  const result = await waiting;
  assert.equal(result.type, "feedback-submission");
  assert.equal(result.comments.length, 1);
  assert.equal(result.comments[0].kind, "point");
  await screenshot(page, "visual-workshop-invalid-manifest.png");
  console.log("PASS: malformed manifest fails closed while ordinary comments remain available.");
}

main().catch(error => { console.error(error); process.exitCode = 1; });
