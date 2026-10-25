#!/usr/bin/env node
"use strict";

// Optional, isolated browser smoke. Reuses an installed browser and Playwright.
// All example screens and state belong to the temporary preview session.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");
// Comparing variants belongs to Prøv; leave Endre first when needed.
async function startComparison(ui) {
  const compare = ui.getByRole("button", { name: "Sammenlign varianter", exact: true });
  if (!(await compare.isVisible())) await ui.getByRole("button", { name: "Prøv", exact: true }).click();
  await compare.click();
}
// Juster is one of the Endre tools; open Endre first when its bar is hidden.
async function openAdjust(ui) {
  const adjust = ui.getByRole("button", { name: "Juster", exact: true });
  if (!(await adjust.isVisible())) await ui.getByRole("button", { name: "Endre", exact: true }).click();
  await adjust.click();
}

const options = new Map();
const args = process.argv.slice(2);
for (let index = 0; index < args.length; index += 1) {
  if (args[index] === "--headed") { options.set("--headed", true); continue; }
  if (!["--playwright-module", "--browser-channel", "--evidence-dir", "--case"].includes(args[index]) || !args[index + 1] || args[index + 1].startsWith("--")) {
    console.error("Usage: node scripts/smoke_visual_workshop.cjs [--playwright-module ABSOLUTE_PATH] [--browser-channel chrome] [--headed] [--evidence-dir DIRECTORY] [--case declared-actions|keyboard-errors]");
    process.exit(2);
  }
  options.set(args[index], args[++index]);
}
if (options.has("--case") && !["declared-actions", "keyboard-errors"].includes(options.get("--case"))) { console.error("Unknown workshop case."); process.exit(2); }

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
    const errors = [], completedRequests = [];
    // Headless Chrome stops routing pointer input to the lower part of the
    // sandboxed preview after a live viewport change, even after a reload.
    // Each viewport therefore gets its own page instead of a resize.
    const openPage = async viewport => {
      const opened = await browser.newPage({ viewport });
      opened.setDefaultTimeout(10000);
      opened.on("pageerror", error => { errors.push(error.message); console.error(`Browser error: ${error.message}`); });
      opened.on("requestfinished", request => completedRequests.push(request.url()));
      await opened.goto(info.url);
      return opened;
    };
    page = await openPage({ width: 1440, height: 1000 });
    const frame = page.frameLocator("#vc-preview");
    const ui = frame.locator("[data-visual-feedback]");
    const list = () => cli("list", info);

    if (!options.has("--case")) await runWorkshop({ page, frame, ui, info, list, writeScreen, openPage });
    if (!options.has("--case") || options.get("--case") === "declared-actions") await runDeclaredActions({ page, frame, ui, info, list, writeScreen });
    const keyboardErrors = !options.has("--case") || options.get("--case") === "keyboard-errors"
      ? await runKeyboardErrors({ page, frame, ui, info, list, writeScreen, openPage }) : null;

    assert.deepEqual(errors, [], errors.join("\n"));
    assert(completedRequests.every(url => url.startsWith(new URL(info.url).origin) || /^(data|blob):/.test(url)), "Unexpected completed remote request.");
    const result = {
      browser: browserChannel || "chromium",
      headed: options.has("--headed"),
      viewports: options.get("--case") === "keyboard-errors" ? ["320x568", "568x320"]
        : options.has("--case") ? ["1440x1000"] : ["1440x1000", "390x844", "320x568", "568x320"],
      checks: options.has("--case") ? [] : ["declared-controls", "source-css", "local-reset", "structured-batch", "variant-comparison", "narrow-comparison", "narrow-heading-clearance", "narrow-overlay-close", "hidden-variant-pin", "no-spurious-selection", "keep", "fresh-release-enabled", "release-failure-retention", "accepted-decision-batch", "release", "version-mismatch", "historical-labels", "duplicate-target", "invalid-manifest", "keyboard", "area-comparison-boundary", "draft-retention", "field-privacy", "loopback-only"],
      declaredActions: options.get("--case") === "keyboard-errors" ? [] : ["native-keyboard", "hidden-button-focus", "variant-isolation", "invalid-choice", "disabled-choice", "nested-unbound-target", "comment-mode", "state-context", "restore-context", "parked-context", "preview-context", "explicit-batch", "field-privacy"],
      ...(keyboardErrors ? { keyboardErrors } : {}),
      errors,
    };
    if (evidence) fs.writeFileSync(path.join(evidence, "visual-workshop-test-results.json"), `${JSON.stringify(result, null, 2)}\n`);
    console.log(JSON.stringify(result));
  } catch (error) {
    const latest = browser?.contexts().flatMap(item => item.pages()).filter(item => !item.isClosed()).at(-1) || page;
    if (latest) await screenshot(latest, "visual-workshop-failure.png").catch(() => {});
    throw error;
  } finally {
    try { await browser?.close(); }
    finally { await stopServer(child); fs.rmSync(temporary, { recursive: true, force: true }); }
  }
}

async function runWorkshop(context) {
  const { info, list, writeScreen, openPage } = context;
  let { page, frame, ui } = context;
  await frame.getByRole("heading", { name: "Velg arbeidsoversikt" }).waitFor();
  await frame.getByLabel("Privat prøveverdi", { exact: true }).fill("PRIVAT_VERDI_SKAL_IKKE_BLI_INNSPILL");
  const summary = frame.locator('[data-vc-key="summary-list"]');
  let adjustment = ui.getByRole("region", { name: "Juster skissen", exact: true });
  // The helpers below follow whichever page is shown.
  const show = target => {
    page = target; frame = page.frameLocator("#vc-preview"); ui = frame.locator("[data-visual-feedback]");
    adjustment = ui.getByRole("region", { name: "Juster skissen", exact: true });
  };
  const control = name => adjustment.getByLabel(name, { exact: true });
  const settings = () => summary.evaluate(node => ({
    density: node.getAttribute("data-vc-setting-density"),
    spacing: node.getAttribute("data-vc-setting-spacing"),
    emphasis: node.getAttribute("data-vc-setting-emphasis"),
    padding: getComputedStyle(node).paddingTop,
  }));
  const openWorkshop = async () => {
    if (!(await adjustment.isVisible())) await openAdjust(ui);
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

  // Keyboard: Endre opens its bar, then Juster opens the adjustment panel.
  await ui.getByRole("button", { name: "Endre", exact: true }).focus();
  await page.keyboard.press("Enter");
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
  const queuedRelease = ui.getByRole("region", { name: "Innspill til prototypen", exact: true }).getByRole("button", { name: "Slutt å beholde", exact: true });
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
  await startComparison(ui);
  const panes = frame.locator("[data-vc-variant]");
  const left = await panes.nth(0).boundingBox(), right = await panes.nth(1).boundingBox();
  assert(left && right && Math.abs(left.width - right.width) <= 1, "Comparison panes must have equal widths.");
  assert(right.x >= left.x + left.width - 1, "Desktop comparison must place the two variants beside each other.");
  assert.equal((await list()).comments.length, beforeCompare.comments.length, "Opening comparison must not send a preference.");
  assert.equal(selectionEvents(info), "");
  await screenshot(page, "visual-workshop-comparison.png");
  // A narrow page compares on its own; the desktop page keeps its comparison.
  const desktop = page;
  show(await openPage({ width: 390, height: 844 }));
  await ui.getByRole("button", { name: "Endre", exact: true }).waitFor();
  await openWorkshop();
  await startComparison(ui);
  await ui.locator(`.pin[data-id="${proposed.id}"]`).waitFor(); // Shown until the variant switch hides it.
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
  await page.close();
  show(desktop);
  await page.bringToFront();
  console.log("PASS: equal desktop panes, narrow variant switch and explicit preference without selection events.");

  await closeFeedback();
  await ui.getByRole("button", { name: "Endre", exact: true }).click();
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
  await startComparison(ui);
  await ui.locator(".compare-bar").waitFor({ state: "visible" });
  await ui.getByRole("button", { name: "Fortsett utkast", exact: true }).click();
  assert(!(await ui.locator(".compare-bar").isVisible()), "Resuming an area draft must restore its original layout first.");
  assert.equal(await ui.getByLabel("Hva vil du endre?").inputValue(), "Områdeutkastet skal ha samme forankring etter sammenligning.");
  await ui.getByRole("button", { name: "Forkast", exact: true }).click();
  await closeWorkshop();
  await ui.getByRole("button", { name: "Endre", exact: true }).click();
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
  await decisions.getByRole("button", { name: "Slutt å beholde", exact: true }).click();
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
  await ui.getByRole("button", { name: "Endre", exact: true }).click();
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

async function runDeclaredActions({ page, frame, ui, info, list, writeScreen }) {
  const close = ui.getByRole("button", { name: "Lukk innspill", exact: true });
  if (await close.isVisible()) await close.click();
  const stateControl = { id: "stage", label: "Steg", type: "select", initial: "start", options: [{ value: "start", label: "Start" }, { value: "review", label: "Gjennomgang" }] };
  const design = { version: 1, variants: [{ key: "left", label: "Samlet" }, { key: "right", label: "Trinnvis" }], targets: ["left", "right"].map(variant => ({ key: "flow", variant, label: "Avtale", controls: [stateControl] })) };
  const part = variant => `<section data-vc-variant="${variant}"><h2>${variant === "left" ? "Samlet" : "Trinnvis"}</h2><section data-vc-key="flow"><h3>Avtale</h3><div class="start"><button type="button" data-vc-control="stage" data-vc-value="review">Se gjennom</button></div><div class="review"><p>Bekreft tidspunktet før du går videre.</p><button type="button" data-vc-control="stage" data-vc-value="start">Tilbake</button></div><button type="button" data-vc-control="stage" data-vc-value="unknown">Ukjent valg</button><button type="button" data-vc-control="stage" data-vc-value="review" aria-disabled="true">Ikke tilgjengelig</button><button type="submit" data-vc-control="stage" data-vc-value="review">Ingen skjemainnsending</button><div data-vc-key="undeclared"><button type="button" data-vc-control="stage" data-vc-value="review">Ukjent del</button></div><label>Prøvefelt<input></label></section></section>`;
  writeScreen("declared-actions", `<style>[data-vc-variants]{display:grid;grid-template-columns:1fr 1fr;gap:24px}[data-vc-key]{padding:16px}[data-vc-setting-stage=start] .review,[data-vc-setting-stage=review] .start{display:none}button{margin:8px;max-width:100%}</style><h1>Prøv en deklarert flyt</h1><p>Teknisk wireframe med oppdiktet innhold.</p><div data-vc-variants>${part("left")}${part("right")}</div>`, design);
  await frame.getByRole("heading", { name: "Prøv en deklarert flyt", exact: true }).waitFor();
  const left = frame.locator('[data-vc-variant="left"]'), right = frame.locator('[data-vc-variant="right"]');
  const target = left.locator('[data-vc-key="flow"]');
  const state = () => target.getAttribute("data-vc-setting-stage");
  const baseline = await list();
  await left.getByLabel("Prøvefelt").fill("SYNTETISK_FELT_SOM_IKKE_SKAL_SAMLES");
  await left.getByRole("button", { name: "Se gjennom", exact: true }).focus();
  await page.keyboard.press("Enter");
  assert.equal(await state(), "review");
  assert(await target.evaluate(node => document.activeElement === node), "When the activated button hides, focus must move to its visible part.");
  assert.equal(await right.locator('[data-vc-key="flow"]').getAttribute("data-vc-setting-stage"), "start");
  await left.getByRole("button", { name: "Tilbake", exact: true }).focus();
  await page.keyboard.press("Space");
  assert.equal(await state(), "start");
  for (const name of ["Ukjent valg", "Ingen skjemainnsending", "Ukjent del"]) {
    await left.getByRole("button", { name, exact: true }).click();
    assert.equal(await state(), "start", `${name} must not select a valid setting on another part.`);
  }
  // A native keyboard activation reaches aria-disabled controls; runtime must ignore it.
  await left.getByRole("button", { name: "Ikke tilgjengelig", exact: true }).focus();
  await page.keyboard.press("Enter");
  assert.equal(await state(), "start");
  await ui.getByRole("button", { name: "Endre", exact: true }).click();
  await left.getByRole("button", { name: "Se gjennom", exact: true }).click();
  assert.equal(await state(), "start", "Comment mode must annotate a control without activating it.");
  await ui.getByRole("button", { name: "Forkast", exact: true }).click();
  await ui.locator('[data-action="browse"]').click();
  await left.getByRole("button", { name: "Se gjennom", exact: true }).click();
  await ui.getByRole("button", { name: "Endre", exact: true }).click();
  await left.getByText("Bekreft tidspunktet før du går videre.", { exact: true }).click();
  await ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Forklar hva bekreftelsen betyr.");
  await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click();
  await ui.getByRole("button", { name: "Send 1 innspill", exact: true }).waitFor();
  const saved = (await list()).comments.find(item => item.text === "Forklar hva bekreftelsen betyr.");
  assert.deepEqual(saved.context, { variant: "left", target: "flow", values: { stage: "review" } });
  assert.equal(saved.submission, 0);
  await close.click(); await ui.locator('[data-action="browse"]').click();
  await left.getByRole("button", { name: "Tilbake", exact: true }).click();
  await ui.locator('[data-action="panel"]').click();
  const card = ui.locator(`article[data-id="${saved.id}"]`);
  assert.match(await card.innerText(), /Steg: Gjennomgang/);
  await card.getByRole("button", { name: "Vis situasjon", exact: true }).click();
  assert.equal(await state(), "review");
  assert(await left.getByText("Bekreft tidspunktet før du går videre.", { exact: true }).evaluate(node => document.activeElement === node));
  assert.equal((await list()).comments.length, baseline.comments.length + 1, "Trying a flow must never create feedback automatically.");
  await ui.locator('[data-action="panel"]').click();
  await ui.getByRole("button", { name: "Send 1 innspill", exact: true }).click();
  const batch = await cli("wait", info, ["--after", String(baseline.submission), "--timeout", "10"]);
  assert.equal(batch.comments.length, 1);
  assert.deepEqual(batch.comments[0].context, saved.context);
  assert(!JSON.stringify(batch).includes("SYNTETISK_FELT_SOM_IKKE_SKAL_SAMLES"));
  await close.click(); await ui.locator('[data-action="browse"]').click();
  await left.getByRole("button", { name: "Tilbake", exact: true }).click();
  await ui.getByRole("button", { name: "Endre", exact: true }).click();
  await left.getByRole("button", { name: "Se gjennom", exact: true }).click();
  await ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Behold utkastet på startsteget.");
  await ui.getByRole("button", { name: "Legg utkast til side", exact: true }).click();
  await ui.locator('[data-action="panel"]').click();
  await card.getByRole("button", { name: "Vis situasjon", exact: true }).click();
  assert.equal(await state(), "review");
  await ui.getByRole("button", { name: "Fortsett utkast", exact: true }).click();
  assert.equal(await state(), "start", "Resuming a parked draft must restore its own declared situation.");
  assert(await left.getByRole("button", { name: "Se gjennom", exact: true }).isVisible());
  assert.equal(await ui.getByLabel("Hva vil du endre?", { exact: true }).inputValue(), "Behold utkastet på startsteget.");
  await ui.getByRole("button", { name: "Legg utkast til side", exact: true }).click();
  await openAdjust(ui);
  await ui.getByRole("region", { name: "Juster skissen", exact: true }).getByLabel("Steg", { exact: true }).selectOption("review");
  await ui.getByRole("button", { name: "Lukk justeringer", exact: true }).click();
  await ui.getByRole("button", { name: "Fortsett utkast", exact: true }).click();
  assert.equal(await state(), "start");
  await ui.getByRole("button", { name: "Forkast", exact: true }).click();
  assert.equal((await list()).comments.length, baseline.comments.length + 1);
  await ui.getByRole("button", { name: "Endre", exact: true }).click();
  await left.getByRole("button", { name: "Se gjennom", exact: true }).click();
  await ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Prøv en kortere knappetekst.");
  await ui.getByRole("button", { name: "Foreslå ny tekst", exact: true }).click();
  await ui.getByLabel("Ny tekst", { exact: true }).fill("Se over");
  await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click();
  const edit = await waitFor(async () => (await list()).comments.find(item => item.text === "Prøv en kortere knappetekst."), "saved proposal with context");
  await ui.locator(`article[data-id="${edit.id}"]`).getByRole("button", { name: "Forhåndsvis tekst", exact: true }).click();
  assert(await ui.locator(".preview-bar").isVisible());
  await ui.locator('[data-action="panel"]').click();
  // Waiting feedback opens «Klar til sending»; the earlier round is under «Sendt».
  await ui.getByRole("tab", { name: /^Sendt/ }).click();
  await card.getByRole("button", { name: "Vis situasjon", exact: true }).click();
  assert.equal(await state(), "review");
  assert(!(await ui.locator(".preview-bar").isVisible()), "Showing another situation must first restore the previous text preview.");
  assert.equal(await left.locator('.start button').textContent(), "Se gjennom");
  assert.equal(selectionEvents(info), "");
  await screenshot(page, "visual-workshop-declared-actions.png");
  console.log("PASS: declared click-through, keyboard focus, safe choices, exact state context and explicit private batch.");
}

async function runKeyboardErrors({ page, frame, ui, list, writeScreen, openPage }) {
  // This wireframe tests the review controls, not a domain component design.
  const title = "Vurder lange tekster med tastatur";
  const baseline = await list();
  writeScreen("keyboard-errors", fixture(title), manifest());
  // Each viewport gets its own page; the helpers below follow the shown page.
  const show = async viewport => {
    page = await openPage(viewport); frame = page.frameLocator("#vc-preview"); ui = frame.locator("[data-visual-feedback]");
    await frame.getByRole("heading", { name: title, exact: true }).waitFor();
  };
  await show({ width: 320, height: 568 });
  const isFocused = locator => locator.evaluate(node => node === node.getRootNode().activeElement);
  async function tabTo(locator) {
    await locator.waitFor();
    for (let count = 0; count <= 80; count += 1) {
      if (await isFocused(locator)) return;
      await page.keyboard.press("Tab");
    }
    throw new Error("Keyboard could not reach the required review control.");
  }
  async function activate(locator) { await tabTo(locator); await page.keyboard.press("Enter"); }
  async function type(locator, text) {
    await tabTo(locator);
    await page.keyboard.press("ControlOrMeta+A");
    await page.keyboard.insertText(text);
  }
  async function visibleBounds(locator, description) {
    const bounds = await locator.evaluate(node => {
      const rect = node.getBoundingClientRect();
      const clip = { left: 0, top: 0, right: innerWidth, bottom: innerHeight };
      for (let parent = node.parentElement; parent; parent = parent.parentElement) {
        const style = getComputedStyle(parent), box = parent.getBoundingClientRect();
        if (/hidden|clip|auto|scroll/.test(style.overflowY)) { clip.top = Math.max(clip.top, box.top); clip.bottom = Math.min(clip.bottom, box.bottom); }
        if (/hidden|clip|auto|scroll/.test(style.overflowX)) { clip.left = Math.max(clip.left, box.left); clip.right = Math.min(clip.right, box.right); }
      }
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height, clip,
        fullyVisible: rect.width > 0 && rect.height > 0 && rect.left >= clip.left - 1 && rect.top >= clip.top - 1 && rect.right <= clip.right + 1 && rect.bottom <= clip.bottom + 1 };
    });
    assert(bounds.fullyVisible, `${description} is clipped: ${JSON.stringify(bounds)}`);
    return bounds;
  }
  async function checkError(field, error, message, text) {
    await error.filter({ hasText: message }).waitFor();
    await waitFor(() => isFocused(field), "validation field focus");
    assert.equal(await field.inputValue(), text, "Rejected text must remain editable.");
    return { field: await visibleBounds(field, "Focused field"), error: await visibleBounds(error, "Error message") };
  }
  const measurements = {};
  await activate(ui.getByRole("button", { name: "Endre", exact: true }));
  await activate(frame.getByRole("heading", { name: title, exact: true }));
  const note = ui.getByLabel("Hva vil du endre?", { exact: true });
  const composeError = ui.locator(".compose-error");
  const oversizedNote = "ø".repeat(1001);
  await type(note, oversizedNote);
  await page.keyboard.press("ControlOrMeta+Enter");
  measurements.note = await checkError(note, composeError, "Innspillet er for langt.", oversizedNote);
  assert.equal((await list()).comments.length, baseline.comments.length);
  await screenshot(page, "visual-workshop-note-error-320.png");

  const draftText = "Gjør avtalen tydeligere, med ærlige forbehold og neste steg.";
  await type(note, draftText);
  await activate(ui.getByRole("button", { name: "Foreslå ny tekst", exact: true }));
  const proposal = ui.getByLabel("Ny tekst", { exact: true });
  const oversizedProposal = "😀".repeat(501);
  await type(proposal, oversizedProposal);
  await page.keyboard.press("ControlOrMeta+Enter");
  measurements.proposal = await checkError(proposal, composeError, "Tekstforslaget er for langt.", oversizedProposal);
  assert.equal((await list()).comments.length, baseline.comments.length);
  await screenshot(page, "visual-workshop-proposal-error-320.png");
  await activate(ui.getByRole("button", { name: "Forkast", exact: true }));

  await activate(frame.getByRole("heading", { name: title, exact: true }));
  await type(note, draftText);
  let failed = false;
  const failFirstSave = route => {
    if (route.request().method() === "POST" && !failed) {
      failed = true;
      return route.fulfill({ status: 503, contentType: "application/json", body: '{"error":"Temporary local failure"}' });
    }
    return route.continue();
  };
  await page.route("**/comments?*", failFirstSave);
  try {
    await page.keyboard.press("ControlOrMeta+Enter");
    measurements.retry = await checkError(note, composeError, "Lagringen ble ikke bekreftet.", draftText);
    assert.equal((await list()).comments.length, baseline.comments.length);
    await screenshot(page, "visual-workshop-retry-error-320.png");
  } finally { await page.unroute("**/comments?*", failFirstSave); }
  await page.keyboard.press("ControlOrMeta+Enter");
  const saved = await waitFor(async () => {
    const snapshot = await list();
    return snapshot.comments.length === baseline.comments.length + 1 && snapshot;
  }, "keyboard retry saves once");
  assert.equal(saved.comments.at(-1).text, draftText);
  assert.equal(saved.submission, baseline.submission, "Saving must not submit a round.");
  await page.keyboard.press("Escape");
  assert(await isFocused(ui.locator('[data-action="panel"]')), "Closing feedback must restore toolbar focus.");

  await page.close();
  await show({ width: 568, height: 320 });
  await activate(ui.getByRole("button", { name: "Endre", exact: true }));
  await activate(ui.getByRole("button", { name: "Juster", exact: true }));
  const workshop = ui.getByRole("region", { name: "Juster skissen", exact: true });
  const remark = workshop.getByLabel("Merknad", { exact: true });
  await type(remark, oversizedNote);
  await activate(workshop.getByRole("button", { name: "Behold dette", exact: true }));
  measurements.remark = await checkError(remark, workshop.locator(".workshop-error"), "Merknaden er for lang.", oversizedNote);
  assert.equal((await list()).decisions.length, baseline.decisions.length);
  await screenshot(page, "visual-workshop-remark-error-landscape.png");
  await page.keyboard.press("Escape");
  assert(await isFocused(ui.getByRole("button", { name: "Juster", exact: true })), "Closing adjustments must restore focus to the Juster entry in the Endre bar.");
  await activate(ui.getByRole("button", { name: "Juster", exact: true }));
  assert.equal(await remark.inputValue(), oversizedNote, "Closing and reopening must preserve the rejected draft.");
  const keepText = "Behold forklaringen om hvem som tar kontakt etter møtet.";
  await type(remark, keepText);
  let keepFailed = false;
  const failFirstKeep = route => {
    if (route.request().method() === "POST" && !keepFailed) {
      keepFailed = true;
      return route.fulfill({ status: 503, contentType: "application/json", body: '{"error":"Temporary local failure"}' });
    }
    return route.continue();
  };
  await page.route("**/decisions?*", failFirstKeep);
  try {
    await activate(workshop.getByRole("button", { name: "Behold dette", exact: true }));
    measurements.keepRetry = await checkError(remark, workshop.locator(".workshop-error"), "Lagringen ble ikke bekreftet.", keepText);
    assert.equal((await list()).decisions.length, baseline.decisions.length);
    await screenshot(page, "visual-workshop-keep-retry-landscape.png");
  } finally { await page.unroute("**/decisions?*", failFirstKeep); }
  await activate(workshop.getByRole("button", { name: "Behold dette", exact: true }));
  const kept = await waitFor(async () => {
    const snapshot = await list();
    return snapshot.decisions.some(item => item.text === keepText) && snapshot;
  }, "keyboard keep retry saves once");
  assert.equal(kept.decisions.filter(item => item.text === keepText).length, 1);
  assert.equal(kept.submission, baseline.submission);
  await page.keyboard.press("Escape");
  console.log("PASS: keyboard-only byte-limit recovery, visible field errors, retry and pane focus at narrow and short viewports.");
  return { realParticipants: 0, screenReader: false, keyboardOnly: true, rejectedNoteBytes: Buffer.byteLength(oversizedNote), rejectedProposalBytes: Buffer.byteLength(oversizedProposal), measurements };
}

main().catch(error => { console.error(error); process.exitCode = 1; });
