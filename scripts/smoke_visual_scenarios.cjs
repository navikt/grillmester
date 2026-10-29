#!/usr/bin/env node
"use strict";

// Task-oriented browser scenarios. Every case owns an isolated temporary session;
// failures are collected so that an early problem does not hide later cases.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createRequire } = require("node:module");
const { spawn } = require("node:child_process");
const { openTools, enterBrowse, startComparison, openAdjust, collectFeedback } = require("./visual-smoke-controls.cjs");

const options = new Map();
const args = process.argv.slice(2);
for (let index = 0; index < args.length; index += 1) {
  if (args[index] === "--headed") { options.set(args[index], true); continue; }
  if (!["--playwright-module", "--browser-channel", "--evidence-dir", "--aksel-project", "--case"].includes(args[index]) || !args[index + 1] || args[index + 1].startsWith("--")) {
    console.error("Usage: node scripts/smoke_visual_scenarios.cjs [--playwright-module ABSOLUTE_PATH] [--browser-channel chrome] [--headed] [--evidence-dir DIRECTORY] [--aksel-project DIRECTORY] [--case NAME]");
    process.exit(2);
  }
  options.set(args[index], args[++index]);
}
let chromium;
try { ({ chromium } = require(options.get("--playwright-module") || "playwright")); }
catch { console.error("Supply an existing Playwright installation with --playwright-module. Nothing was installed."); process.exit(2); }
const runtime = path.resolve(__dirname, "../plugin/skills/design-prototype/scripts");
const evidence = options.has("--evidence-dir") ? path.resolve(options.get("--evidence-dir")) : null;
if (evidence) fs.mkdirSync(evidence, { recursive: true });
const escaped = text => text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll('"', "&quot;");
let aksel = null;
if (options.has("--aksel-project")) {
  const project = path.resolve(options.get("--aksel-project"));
  const requireInstalled = createRequire(path.join(project, "package.json"));
  const components = requireInstalled("@navikt/ds-react");
  const react = requireInstalled("react");
  const { renderToStaticMarkup } = requireInstalled("react-dom/server");
  const installed = path.join(project, "node_modules/@navikt");
  const reactVersion = JSON.parse(fs.readFileSync(path.join(installed, "ds-react/package.json"))).version;
  const cssVersion = JSON.parse(fs.readFileSync(path.join(installed, "ds-css/package.json"))).version;
  assert.equal(reactVersion, cssVersion, "Aksel components and CSS must use the same installed version.");
  const css = ["index.min.css", "index.css"].map(name => path.join(installed, "ds-css/dist", name)).find(file => fs.existsSync(file));
  assert(css, "The supplied Aksel project must contain installed CSS.");
  aksel = { version: cssVersion, css, render: (name, props, text) => renderToStaticMarkup(react.createElement(components[name], props, text)) };
}
const heading = (text, level = "1") => aksel ? aksel.render("Heading", { level, size: level === "1" ? "large" : "medium" }, text) : `<h${level}>${escaped(text)}</h${level}>`;
const button = text => aksel ? aksel.render("Button", { variant: "primary", type: "button" }, text) : `<button type="button">${escaped(text)}</button>`;
const textField = () => aksel ? aksel.render("TextField", { id: "practice-note", label: "Eget prøvenotat", description: "Denne prøveverdien skal aldri bli en del av innspillene." }) : '<label>Eget prøvenotat<input id="practice-note"></label>';
const styles = `<style>
.scenario{display:grid;gap:var(--ax-space-24,24px)}.scenario h1,.scenario h2,.scenario h3{overflow-wrap:anywhere}.scenario p{max-width:65ch}.scenario-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--ax-space-24,24px)}.scenario-variant{min-width:0;border:1px solid var(--ax-border-neutral-subtle,#bcc5cd);padding:var(--ax-space-24,24px);border-radius:var(--ax-radius-12,12px)}.scenario-summary{padding:var(--ax-space-16,16px);border:1px solid var(--ax-border-neutral-subtle,#bcc5cd);border-radius:var(--ax-radius-8,8px)}.scenario-summary[data-vc-setting-density="compact"]{padding:var(--ax-space-8,8px)}.scenario-summary[data-vc-setting-density="compact"] li{padding-block:var(--ax-space-4,4px)}.scenario-summary li{padding-block:var(--ax-space-12,12px)}.scenario-variant ul{padding-left:var(--ax-space-24,24px)}.scenario-variant[data-vc-variant="board"] ul{display:grid;grid-template-columns:1fr 1fr;gap:var(--ax-space-12,12px);list-style:none;padding:0}.scenario-variant[data-vc-variant="timeline"] li{border-left:3px solid var(--ax-border-accent,#005b82);padding-left:var(--ax-space-12,12px)}.scenario-variant[data-vc-variant="calendar"] ul{display:grid;grid-template-columns:1fr 1fr;gap:var(--ax-space-8,8px);list-style:none;padding:0}.scenario-variant[data-vc-variant="calendar"] li{border:1px solid var(--ax-border-neutral-subtle,#bcc5cd);padding:var(--ax-space-8,8px)}.scenario-form{display:grid;gap:var(--ax-space-24,24px);max-width:640px}.scenario-form button{justify-self:start}@media(max-width:700px){.scenario-grid{grid-template-columns:1fr}.scenario-variant{padding:var(--ax-space-16,16px)}.vc-content{padding:var(--ax-space-16,16px);margin:var(--ax-space-16,16px) auto}}
</style>`;
const variants = [{ key: "list", label: "Prioritert liste" }, { key: "board", label: "Arbeidsbrett" }, { key: "timeline", label: "Tidslinje" }, { key: "calendar", label: "Ukeoversikt" }];
const design = () => ({ version: 1, variants: variants.map(variant => ({ ...variant })), targets: variants.map(variant => ({ key: "summary", variant: variant.key, label: "Oppsummering", controls: [{ id: "density", label: "Tetthet", type: "select", initial: "comfortable", options: [{ value: "comfortable", label: "Romslig" }, { value: "compact", label: "Tett" }] }] })) });
const overview = (title = "Hva hjelper deg å prioritere arbeidsdagen?") => styles + `<main class="scenario">${heading(title)}<p>Sammenlign fire retninger med de samme to oppgavene. Velg én retning, og behold gjerne gode deler fra en annen.</p><div class="scenario-grid" data-vc-variants>${variants.map(variant => `<section class="scenario-variant" data-vc-variant="${variant.key}">${heading(variant.label, "2")}<section class="scenario-summary" data-vc-key="summary"><h3>Dette trenger oppfølging</h3><ul><li>Avklare møte<br>Frist: torsdag</li><li>Gjennomgå utkast<br>Frist: fredag</li></ul></section></section>`).join("")}</div></main>`;
const form = (title = "Gjør avtalen enklere å forstå") => styles + `<main class="scenario scenario-form">${heading(title)}<p id="editable-copy">Velg tidspunkt for en samtale om veien videre.</p>${textField()}${button("Se ledige tidspunkt")}</main>`;

function overlap(left, right) {
  return left && right && left.x < right.x + right.width - 1 && right.x < left.x + left.width - 1 && left.y < right.y + right.height - 1 && right.y < left.y + left.height - 1;
}
async function settle(page) {
  await Promise.all(page.frames().map(childFrame => childFrame.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))));
}
async function waitFor(check, description, timeout = 10000) {
  const end = Date.now() + timeout;
  do { const value = await check(); if (value) return value; await new Promise(resolve => setTimeout(resolve, 80)); } while (Date.now() < end);
  throw new Error(`Timed out: ${description}`);
}
async function stop(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const ended = new Promise(resolve => child.once("close", resolve));
  child.kill("SIGTERM"); const timer = setTimeout(() => child.kill("SIGKILL"), 5000);
  await ended; clearTimeout(timer);
}
function cli(info, command, extra = []) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [path.join(runtime, "comments.js"), command, "--state-dir", info.state_dir, ...extra]);
    let out = "", err = "";
    const timer = setTimeout(() => child.kill("SIGKILL"), 20000);
    child.stdout.on("data", data => { out += data; }); child.stderr.on("data", data => { err += data; });
    child.once("error", error => { clearTimeout(timer); reject(error); });
    child.once("close", code => { clearTimeout(timer); if (code) reject(new Error(err || `Feedback command failed (${code}).`)); else { try { resolve(JSON.parse(out)); } catch { reject(new Error("Feedback command returned invalid JSON.")); } } });
  });
}
function started(child) {
  return new Promise((resolve, reject) => {
    let buffer = "", settled = false;
    const timer = setTimeout(() => finish(new Error("Preview startup timed out.")), 5000);
    function finish(error, value) { if (settled) return; settled = true; clearTimeout(timer); error ? reject(error) : resolve(value); }
    child.stdout.on("data", data => { buffer += data; if (buffer.includes("\n") && !settled) { try { const value = JSON.parse(buffer.split("\n")[0]); assert.equal(value.type, "server-started"); finish(null, value); } catch (error) { finish(error); } } });
    child.once("error", error => finish(error)); child.once("close", code => finish(new Error(`Preview exited before startup (${code}).`)));
  });
}
async function session(browser, testcase) {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "grillmester-scenarios-"));
  const project = path.join(temporary, "project"); fs.mkdirSync(project);
  if (aksel) { const target = path.join(project, "node_modules/@navikt/ds-css/dist"); fs.mkdirSync(target, { recursive: true }); fs.copyFileSync(aksel.css, path.join(target, "index.min.css")); }
  const child = spawn(process.execPath, [path.join(runtime, "server.js"), "--project-dir", project], { stdio: ["ignore", "pipe", "pipe"] });
  let page, frame, ui, workshop;
  try {
    const info = await started(child);
    const errors = [], remoteRequests = [];
    // Headless Chrome stops routing pointer input to the lower part of the
    // sandboxed preview after a live viewport change, even after a reload, so a
    // new viewport gets a fresh page. The helpers below follow the shown page.
    const show = async viewport => {
      await page?.close();
      page = await browser.newPage({ viewport }); page.setDefaultTimeout(7000);
      page.on("pageerror", error => errors.push(error.message));
      page.on("requestfinished", request => { if (!request.url().startsWith(new URL(info.url).origin) && !/^(data|blob):/.test(request.url())) remoteRequests.push(new URL(request.url()).origin); });
      frame = page.frameLocator("#vc-preview"); ui = frame.locator("[data-visual-feedback]");
      workshop = ui.getByRole("region", { name: "Juster visningen", exact: true });
    };
    await show(testcase.viewport || { width: 1440, height: 1000 });
    let sequence = 0;
    const write = (name, html, descriptor) => { const stem = `${String(++sequence).padStart(2, "0")}-${name}`; if (descriptor) fs.writeFileSync(path.join(info.screen_dir, `${stem}.design.json`), JSON.stringify(descriptor)); fs.writeFileSync(path.join(info.screen_dir, `${stem}.html`), html); };
    const reopen = async viewport => { await show(viewport); await page.goto(info.url); await ui.getByRole("button", { name: "Gi innspill", exact: true }).waitFor(); return { page, frame, ui, workshop }; };
    const screenshot = async name => { if (evidence) { await page.locator("#vc-status").filter({ hasText: /^Tilkoblet$/ }).waitFor(); await settle(page); await page.screenshot({ path: path.join(evidence, `${testcase.name}-${name}.png`), animations: "disabled" }); } };
    const open = async (html, descriptor) => { write(testcase.name, html, descriptor); await page.goto(info.url); await ui.getByRole("button", { name: "Gi innspill", exact: true }).waitFor(); };
    const list = () => cli(info, "list");
    const send = async count => { const previous = await list(); const waiting = cli(info, "wait", ["--after", String(previous.submission), "--timeout", "10"]); await ui.getByRole("button", { name: `Send ${count} innspill`, exact: true }).click(); const result = await waiting; assert.equal(result.type, "feedback-submission"); return result; };
    const closePanel = async () => { const close = ui.getByRole("button", { name: "Lukk innspill", exact: true }); if (await close.isVisible()) await close.click(); };
    const adjust = async () => { if (!(await workshop.isVisible())) await openAdjust(ui); await workshop.waitFor(); };
    await testcase.run({ page, frame, ui, open, write, list, send, closePanel, workshop, adjust, screenshot, info, reopen });
    assert.deepEqual(errors, [], "No browser exceptions are allowed."); assert.deepEqual(remoteRequests, [], "No remote resource may finish loading.");
    return { name: testcase.name, role: testcase.role, status: "passed", outcomes: testcase.outcomes };
  } catch (error) {
    if (page && evidence) await page.screenshot({ path: path.join(evidence, `${testcase.name}-failure.png`), animations: "disabled" }).catch(() => {});
    return { name: testcase.name, role: testcase.role, status: "failed", error: error.message.replace(/http:\/\/127\.0\.0\.1:[^\s)]+/g, "[local preview]") };
  } finally { await page?.close(); await stop(child); fs.rmSync(temporary, { recursive: true, force: true }); }
}

const cases = [
  {
    name: "four-directions", role: "Designer comparing and combining concepts",
    outcomes: ["Four variants can be compared in changing pairs", "A preferred variant belongs to the visible pair", "Wishes to keep parts remain distinguishable across variants", "The full mixed brief reaches the CLI in one batch", "Earlier wishes retain their original labels"],
    async run({ frame, ui, open, write, list, send, closePanel, workshop, adjust, screenshot }) {
      await open(overview(), design());
      await startComparison(ui);
      await ui.getByLabel("Venstre variant", { exact: true }).selectOption("timeline");
      await ui.getByLabel("Høyre variant", { exact: true }).selectOption("calendar");
      assert(["timeline", "calendar"].includes(await ui.getByLabel("Foretrukket variant", { exact: true }).inputValue()), "Changing both compared variants must not leave an invisible preferred variant selected.");
      assert.equal(await frame.locator("[data-vc-variant]:visible").count(), 2);
      const left = await frame.locator('[data-vc-variant="timeline"]').boundingBox(), right = await frame.locator('[data-vc-variant="calendar"]').boundingBox();
      assert(left && right && Math.abs(left.width - right.width) <= 1, "Both compared directions must have the same usable width.");
      await ui.getByLabel("Foretrukket variant", { exact: true }).selectOption("calendar");
      await ui.getByRole("button", { name: "Foretrekk denne varianten", exact: true }).click();
      await waitFor(async () => (await list()).comments.length === 1, "variant preference saved"); await closePanel();
      for (const key of ["list", "board"]) {
        await adjust(); await workshop.getByLabel("Velg del", { exact: true }).selectOption(`${key}/summary`);
        await workshop.getByLabel("Tetthet", { exact: true }).selectOption(key === "list" ? "compact" : "comfortable");
        await workshop.getByLabel("Merknad", { exact: true }).fill(key === "list" ? "Ta med prioriteringen fra listen." : "Ta med grupperingen fra brettet.");
        await workshop.getByRole("button", { name: "Behold denne delen", exact: true }).click();
        await waitFor(async () => (await list()).comments.some(item => item.context?.variant === key), `keep wish for ${key}`); await closePanel();
      }
      await ui.locator('[data-action="panel"]').click();
      const saved = await list();
      const keeps = saved.comments.filter(item => item.context);
      assert.equal(keeps.length, 2);
      for (const wish of keeps) {
        const card = ui.locator(`article[data-id="${wish.id}"]`);
        assert((await card.innerText()).includes(variants.find(variant => variant.key === wish.context.variant).label), "A kept part needs its variant name when target labels repeat.");
      }
      await screenshot("mixed-brief");
      const batch = await send(3);
      assert.equal(batch.comments.length, 3); assert.equal(batch.comments.find(item => item.variant)?.variant, "calendar");
      assert.deepEqual(batch.comments.filter(item => item.context).map(item => `${item.context.variant}/${item.context.target}`).sort(), ["board/summary", "list/summary"]);
      await closePanel();
      const renamed = design(); renamed.variants.forEach(variant => { variant.label = `Ny ${variant.label.toLowerCase()}`; }); renamed.targets.forEach(target => { target.label = "Ny oppsummering"; target.controls[0].label = "Ny tetthet"; target.controls[0].options.forEach(option => { option.label = `Ny ${option.label.toLowerCase()}`; }); });
      write("renamed-directions", overview("Neste skisse med nye navn"), renamed);
      await frame.getByRole("heading", { name: "Neste skisse med nye navn", exact: true }).waitFor();
      await ui.locator('[data-action="panel"]').click(); await ui.getByRole("tab", { name: /^Sendt/ }).click();
      for (const wish of batch.comments.filter(item => item.context)) {
        const card = ui.locator(`article[data-id="${wish.id}"]`);
        const text = await card.innerText();
        assert(text.includes(`Oppsummering · ${variants.find(variant => variant.key === wish.context.variant).label}`), "An earlier wish must retain the names used when it was made.");
        assert(!text.includes("Ny oppsummering"), "A new target label must not rewrite the earlier wish.");
        assert(text.includes(wish.context.variant === "list" ? "Tetthet: Tett" : "Tetthet: Romslig"), "An earlier wish must retain its original control and option labels.");
      }
      await screenshot("historical-brief");
    },
  },
  {
    name: "target-drafts", role: "Designer switching between several unfinished adjustments",
    outcomes: ["Each part keeps its own note and preview", "Resetting one part does not erase another part's work", "Both notes reach the correct target in the submitted brief"],
    async run({ ui, open, list, send, closePanel, workshop, adjust, screenshot }) {
      await open(overview(), design()); await adjust();
      const choose = key => workshop.getByLabel("Velg del", { exact: true }).selectOption(`${key}/summary`);
      await choose("list"); await workshop.getByLabel("Tetthet", { exact: true }).selectOption("compact");
      await workshop.getByLabel("Merknad", { exact: true }).fill("Listen skal vise fristene tydelig.");
      await choose("board"); assert.equal(await workshop.getByLabel("Merknad", { exact: true }).inputValue(), "", "A note about the list must not move to the board.");
      await workshop.getByLabel("Tetthet", { exact: true }).selectOption("compact");
      await workshop.getByLabel("Merknad", { exact: true }).fill("Brettet skal gruppere oppgavene etter status.");
      await choose("list"); assert.equal(await workshop.getByLabel("Merknad", { exact: true }).inputValue(), "Listen skal vise fristene tydelig.");
      assert.equal(await workshop.getByLabel("Tetthet", { exact: true }).inputValue(), "compact");
      await workshop.getByRole("button", { name: "Tilbakestill visning", exact: true }).click();
      assert.equal(await workshop.getByLabel("Merknad", { exact: true }).inputValue(), "Listen skal vise fristene tydelig.", "Resetting the preview must not silently discard the written note.");
      await choose("board"); assert.equal(await workshop.getByLabel("Merknad", { exact: true }).inputValue(), "Brettet skal gruppere oppgavene etter status.");
      assert.equal(await workshop.getByLabel("Tetthet", { exact: true }).inputValue(), "compact");
      await screenshot("two-drafts");
      for (const key of ["board", "list"]) {
        await adjust(); await choose(key); await workshop.getByRole("button", { name: "Legg til innspill", exact: true }).click();
        await waitFor(async () => (await list()).comments.some(item => item.adjustment?.variant === key), `adjustment from ${key}`);
        if (key === "board") await closePanel();
      }
      const batch = await send(2);
      assert.equal(batch.comments.find(item => item.adjustment.variant === "list").text, "Listen skal vise fristene tydelig.");
      assert.equal(batch.comments.find(item => item.adjustment.variant === "board").text, "Brettet skal gruppere oppgavene etter status.");
    },
  },
  {
    name: "slow-adjustment", role: "Participant navigating while an adjustment is still saving",
    outcomes: ["A delayed save cannot open overlapping feedback panels", "The selected target and note remain intact", "The adjustment is saved and submitted exactly once"],
    async run({ page, ui, open, list, send, workshop, adjust, screenshot }) {
      await open(overview(), design()); await adjust();
      await workshop.getByLabel("Tetthet", { exact: true }).selectOption("compact");
      await workshop.getByLabel("Merknad", { exact: true }).fill("La fristen stå ved siden av oppgaven.");
      let release, began;
      const gate = new Promise(resolve => { release = resolve; });
      const started = new Promise(resolve => { began = resolve; });
      await page.route("**/comments?*", async route => { if (route.request().method() === "POST") { began(); await gate; } await route.continue(); });
      try {
        await workshop.getByRole("button", { name: "Legg til innspill", exact: true }).click(); await started;
        const panelButton = ui.locator('[data-action="panel"]');
        if (await panelButton.isEnabled()) await panelButton.click();
        assert(!(await workshop.isVisible()) || !(await ui.getByRole("region", { name: "Innspill til prototypen", exact: true }).isVisible()), "A slow adjustment save must not leave both panels visible.");
        assert.equal(await workshop.getByLabel("Merknad", { exact: true }).inputValue(), "La fristen stå ved siden av oppgaven.");
        await screenshot("saving");
      } finally { release(); }
      await waitFor(async () => (await list()).comments.length === 1, "delayed adjustment saved"); await page.unroute("**/comments?*");
      const batch = await send(1); assert.equal(batch.comments.length, 1); assert.equal(batch.comments[0].text, "La fristen stå ved siden av oppgaven.");
    },
  },
  {
    name: "norwegian-copy", role: "Content designer writing long Norwegian copy",
    outcomes: ["Norwegian text and literal markup preview safely", "Undo restores the source copy", "UTF-8 size errors preserve the draft", "A shortened complete proposal reaches the CLI"],
    async run({ page, frame, ui, open, list, send, screenshot }) {
      await open(form());
      const original = await frame.locator("#editable-copy").innerText();
      await ui.getByRole("button", { name: "Gi innspill", exact: true }).click(); await frame.locator("#editable-copy").click();
      await ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Forklar valget med roligere språk, og bruk æ, ø og å riktig.");
      await ui.getByRole("button", { name: "Foreslå ny tekst", exact: true }).click();
      const proposal = "Velg et tidspunkt som passer for deg. Vi snakker om ønskene dine, spørsmål du har og veien videre. Du trenger ikke å ha alle svarene klare. <strong>Dette er vanlig tekst.</strong>";
      await ui.getByLabel("Ny tekst", { exact: true }).fill(proposal); await ui.getByRole("button", { name: "Forhåndsvis teksten", exact: true }).click();
      assert.equal(await frame.locator("#editable-copy").innerText(), proposal); assert.equal(await frame.locator("#editable-copy strong").count(), 0);
      await screenshot("preview"); await ui.getByRole("button", { name: "Tilbakestill", exact: true }).click(); assert.equal(await frame.locator("#editable-copy").innerText(), original);
      const tooLong = "Blåbær, spørsmål og ønsker. ".repeat(65);
      assert(Buffer.byteLength(tooLong) > 2000 && tooLong.length < 2000);
      await ui.getByLabel("Ny tekst", { exact: true }).fill(tooLong); await collectFeedback(ui);
      await ui.getByText("Tekstforslaget er for langt. Kort det ned før du fortsetter.", { exact: true }).waitFor();
      assert.equal(await ui.getByLabel("Ny tekst", { exact: true }).inputValue(), tooLong); assert.equal((await list()).comments.length, 0);
      await ui.getByLabel("Ny tekst", { exact: true }).fill(proposal); await collectFeedback(ui);
      const batch = await send(1); assert.equal(batch.comments[0].proposal.value, proposal); assert.equal(batch.comments[0].kind, "edit");
    },
  },
  {
    name: "recover-send", role: "First-time participant recovering from a failed send",
    outcomes: ["The participant can recover an abandoned draft", "A failed batch leaves every saved item intact", "Retry sends exactly the saved items", "Reload preserves feedback and reply filters", "Typed prototype fields are never collected"],
    async run({ page, frame, ui, open, list, send, closePanel, screenshot, info }) {
      await open(form("Finn et tidspunkt som passer")); await frame.getByLabel("Eget prøvenotat", { exact: true }).fill("PRIVAT_PROEVE_SKAL_IKKE_LAGRES");
      await ui.getByRole("button", { name: "Gi innspill", exact: true }).click(); await frame.getByRole("heading", { name: "Finn et tidspunkt som passer", exact: true }).click();
      await ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Fortell hvor lenge samtalen varer."); await ui.getByRole("button", { name: "Legg utkast til side", exact: true }).click();
      await ui.getByRole("button", { name: "Fortsett utkast", exact: true }).click(); assert.equal(await ui.getByLabel("Hva vil du endre?", { exact: true }).inputValue(), "Fortell hvor lenge samtalen varer.");
      await collectFeedback(ui); await ui.getByRole("button", { name: "Send 1 innspill", exact: true }).waitFor(); await closePanel();
      await ui.getByRole("button", { name: "Gi innspill", exact: true }).click(); await frame.locator("#editable-copy").click(); await ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Vis om jeg kan endre tidspunkt senere."); await collectFeedback(ui);
      await page.route("**/comments/submit?*", route => route.fulfill({ status: 503, contentType: "application/json", body: '{"error":"Unavailable"}' }));
      await ui.getByRole("button", { name: "Send 2 innspill", exact: true }).click(); await ui.locator(".panel-error").waitFor({ state: "visible" });
      const saved = await list(); assert.equal(saved.comments.length, 2); assert(saved.comments.every(item => item.submission === 0)); await screenshot("retry");
      await page.unroute("**/comments/submit?*"); const batch = await send(2); assert.equal(batch.comments.length, 2);
      await page.reload(); await ui.getByRole("button", { name: "Gi innspill", exact: true }).waitFor(); await ui.locator('[data-action="panel"]').click();
      assert.equal(await ui.locator(".comment").count(), 2);
      await cli(info, "resolve", ["--id", batch.comments[0].id, "--reply", "Samtalen varer i 30 minutter."]);
      await ui.getByText("Samtalen varer i 30 minutter.", { exact: false }).waitFor(); await ui.getByRole("button", { name: "Ordnet", exact: true }).click();
      assert.equal(await ui.locator(".comment").count(), 1); await ui.getByRole("button", { name: "Åpne", exact: true }).click(); assert.equal(await ui.locator(".comment").count(), 1);
      assert(!fs.readFileSync(path.join(info.state_dir, "comments.json"), "utf8").includes("PRIVAT_PROEVE_SKAL_IKKE_LAGRES"));
    },
  },
  {
    name: "interactive-card", role: "Participant trying a form inside a concept card",
    outcomes: ["Text input preserves spaces and textarea preserves newlines", "Checkboxes and buttons retain their native interactions", "Form interaction does not select a concept", "A separate explicit concept choice still works", "Selection and connection status remain separate at desktop and 320 pixels"],
    async run({ page, frame, ui, open, screenshot, info, reopen }) {
      const textarea = aksel ? aksel.render("Textarea", { id: "practice-details", label: "Hva vil du ta opp?", minRows: 2 }) : '<label>Hva vil du ta opp?<textarea id="practice-details"></textarea></label>';
      const checkbox = aksel ? aksel.render("Checkbox", { id: "practice-reminder", value: "reminder" }, "Send en påminnelse") : '<label><input type="checkbox" id="practice-reminder">Send en påminnelse</label>';
      const choice = aksel ? aksel.render("Button", { variant: "secondary", type: "button", className: "option" }, "Velg samlet avtale") : '<button class="option" type="button">Velg samlet avtale</button>';
      await open(styles + `<main class="scenario">${heading("Prøv avtaleskjemaet")}<section class="card scenario-form"><h2>En samlet avtale</h2>${textField()}${textarea}${checkbox}${button("Se ledige tidspunkt")}</section>${choice}</main>`);
      const events = () => { const file = path.join(info.state_dir, "events.jsonl"); return fs.existsSync(file) ? fs.readFileSync(file, "utf8").trim() : ""; };
      await frame.getByLabel("Eget prøvenotat", { exact: true }).click(); await page.keyboard.type("Et møte med veileder");
      assert.equal(await frame.getByLabel("Eget prøvenotat", { exact: true }).inputValue(), "Et møte med veileder");
      await frame.getByLabel("Hva vil du ta opp?", { exact: true }).click(); await page.keyboard.type("Første spørsmål"); await page.keyboard.press("Enter"); await page.keyboard.type("Neste spørsmål");
      assert.equal(await frame.getByLabel("Hva vil du ta opp?", { exact: true }).inputValue(), "Første spørsmål\nNeste spørsmål");
      await frame.getByLabel("Send en påminnelse", { exact: true }).check(); assert(await frame.getByLabel("Send en påminnelse", { exact: true }).isChecked());
      await page.keyboard.press("Space"); assert(!(await frame.getByLabel("Send en påminnelse", { exact: true }).isChecked()));
      await frame.getByRole("button", { name: "Se ledige tidspunkt", exact: true }).click(); assert.equal(events(), "", "Typing or activating native form controls must not select their surrounding card.");
      await frame.getByRole("heading", { name: "En samlet avtale", exact: true }).click(); assert.equal(events(), "", "A card containing a form is layout, not an implicit concept choice.");
      await frame.getByRole("button", { name: "Velg samlet avtale", exact: true }).click();
      await waitFor(() => events(), "explicit card choice saved"); const choices = events().split("\n").map(line => JSON.parse(line)); assert.equal(choices.length, 1); assert.equal(choices[0].choice, "choice-1");
      for (const width of [1440, 320]) {
        if (width === 320) {
          // The selection is page state, so the fresh narrow page chooses the card again.
          ({ page, frame, ui } = await reopen({ width, height: 800 }));
          await frame.getByRole("button", { name: "Velg samlet avtale", exact: true }).click(); await frame.locator("#indicator").waitFor({ state: "visible" });
        }
        await page.locator("#vc-status").filter({ hasText: /^Tilkoblet$/ }).waitFor(); await settle(page);
        const indicator = await frame.locator("#indicator").boundingBox(), status = await page.locator("#vc-status").boundingBox();
        assert(indicator && status && !overlap(indicator, status), "The connection badge must not obscure the selected concept.");
        assert(indicator.x >= 0 && indicator.x + indicator.width <= width + 1, "The selected concept must fit the viewport.");
        const horizontalOverflow = await frame.locator("html").evaluate(node => node.scrollWidth > node.clientWidth + 1);
        assert(!horizontalOverflow, "The header and selected concept must not create horizontal scrolling.");
        await screenshot(width === 320 ? "narrow-selection" : "form-interactions");
      }
      assert.equal(await ui.getByRole("button", { name: "Gi innspill", exact: true }).getAttribute("aria-pressed"), "false");
    },
  },
  {
    name: "keyboard-review", role: "Reviewer using only keyboard navigation",
    outcomes: ["Toolbar, target, draft and submission are reachable without pointer input", "Escape restores the selected target", "Saved feedback reaches the CLI using keyboard activation"],
    async run({ page, frame, ui, open, list, screenshot }) {
      await open(form("Tastaturgjennomgang av avtalen"));
      const active = locator => locator.evaluate(node => node.getRootNode().activeElement === node);
      const tabTo = async locator => { for (let count = 0; count < 100; count += 1) { if (await active(locator)) return; await page.keyboard.press("Tab"); } throw new Error("The requested control was not reachable by Tab."); };
      const comment = ui.getByRole("button", { name: "Gi innspill", exact: true }); await tabTo(comment); await page.keyboard.press("Enter");
      const title = frame.getByRole("heading", { name: "Tastaturgjennomgang av avtalen", exact: true }); await tabTo(title); await page.keyboard.press("Enter");
      assert(await active(ui.getByLabel("Hva vil du endre?", { exact: true }))); await page.keyboard.type("Vis tydelig hva neste steg er."); await page.keyboard.press("Escape"); assert(await active(title));
      await tabTo(ui.getByRole("button", { name: "Fortsett utkast", exact: true })); await page.keyboard.press("Enter");
      await tabTo(ui.getByRole("button", { name: "Send innspill", exact: true })); await screenshot("ready");
      await page.keyboard.press(process.platform === "darwin" ? "Meta+Enter" : "Control+Enter");
      const saved = await waitFor(async () => { const value = await list(); return value.submission > 0 && value; }, "keyboard submission"); assert.equal(saved.comments[0].text, "Vis tydelig hva neste steg er.");
    },
  },
  {
    name: "compact-landscape", role: "Designer reviewing on a compact landscape screen", viewport: { width: 667, height: 375 },
    outcomes: ["Adjustment actions remain reachable at 667 by 375", "Panels can be scrolled and closed without losing work", "Portrait rotation preserves the draft", "Comparison can show the third and fourth variants together on mobile", "Connection status does not cover the close control in landscape"],
    async run({ page, frame, ui, open, workshop, adjust, list, send, closePanel, screenshot, reopen }) {
      await open(overview("Velg en retning på liten skjerm"), design()); await adjust();
      await page.locator("#vc-status").filter({ hasText: /^Tilkoblet$/ }).waitFor(); await settle(page);
      const bounds = await workshop.boundingBox(); assert(bounds && bounds.y >= 0 && bounds.y + bounds.height <= 375, "The adjustment panel must fit the landscape viewport.");
      const closeButton = workshop.getByRole("button", { name: "Lukk justeringer", exact: true });
      assert(!overlap(await closeButton.boundingBox(), await page.locator("#vc-status").boundingBox()), "Connection status must not cover the adjustment close control in landscape.");
      await closeButton.click(); assert(!(await workshop.isVisible()), "The landscape close control must be clickable."); await adjust();
      await workshop.getByLabel("Velg del", { exact: true }).selectOption("calendar/summary"); await workshop.getByLabel("Tetthet", { exact: true }).selectOption("compact");
      await workshop.getByLabel("Merknad", { exact: true }).fill("Jeg vil se alle ukens oppgaver uten mye rulling.");
      await workshop.getByLabel("Merknad", { exact: true }).scrollIntoViewIfNeeded();
      const noteBounds = await workshop.getByLabel("Merknad", { exact: true }).boundingBox();
      const panelBounds = await workshop.boundingBox();
      assert(noteBounds.y >= panelBounds.y && noteBounds.y + noteBounds.height <= panelBounds.y + panelBounds.height, "The entire note field must fit in the visible part of the short panel.");
      await screenshot("controls");
      await workshop.getByRole("button", { name: "Legg til innspill", exact: true }).click(); await waitFor(async () => (await list()).comments.length === 1, "landscape adjustment saved"); await send(1); await closePanel();
      await adjust(); await workshop.getByRole("button", { name: "Behold denne delen", exact: true }).scrollIntoViewIfNeeded();
      await page.keyboard.press("Escape"); await adjust();
      const pickerBounds = await workshop.getByLabel("Velg del", { exact: true }).boundingBox();
      const reopened = await workshop.boundingBox();
      assert(pickerBounds.y >= reopened.y && pickerBounds.y + pickerBounds.height <= reopened.y + reopened.height, "The focused part picker must be visible when reopening a scrolled panel.");
      await page.keyboard.press("Escape");
      await ui.getByRole("button", { name: "Gi innspill", exact: true }).click(); const title = frame.getByRole("heading", { name: "Velg en retning på liten skjerm", exact: true }); await title.scrollIntoViewIfNeeded(); await title.click();
      await ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Sammenligningen må fungere når jeg roterer skjermen."); await page.setViewportSize({ width: 375, height: 667 });
      assert.equal(await ui.getByLabel("Hva vil du endre?", { exact: true }).inputValue(), "Sammenligningen må fungere når jeg roterer skjermen.");
      // Keyboard activation still reaches the rotated preview, so it saves the draft; pointer input continues on a fresh page.
      await ui.getByRole("button", { name: "Legg til flere", exact: true }).focus(); await page.keyboard.press("Enter");
      await waitFor(async () => (await list()).comments.length === 2, "rotated draft saved");
      ({ page, frame, ui, workshop } = await reopen({ width: 375, height: 667 }));
      await ui.locator('[data-action="panel"]').click(); await send(1); await closePanel();
      await startComparison(ui); await ui.getByRole("button", { name: "Arbeidsbrett", exact: true }).click();
      assert(await frame.locator('[data-vc-variant="board"]').isVisible()); assert(!(await frame.locator('[data-vc-variant="list"]').isVisible())); await ui.getByLabel("Venstre variant", { exact: true }).selectOption("timeline");
      await ui.getByLabel("Høyre variant", { exact: true }).selectOption("calendar");
      assert.equal(await ui.getByLabel("Venstre variant", { exact: true }).inputValue(), "timeline");
      assert.equal(await ui.getByLabel("Høyre variant", { exact: true }).inputValue(), "calendar");
      await ui.getByLabel("Foretrukket variant", { exact: true }).selectOption("calendar");
      assert(await frame.locator('[data-vc-variant="calendar"]').isVisible(), "Choosing a third or fourth variant on mobile must show it for inspection before preference is sent.");
      assert.equal((await list()).comments.filter(item => item.kind === "variant").length, 0, "Viewing another variant must not submit a preference.");
      await screenshot("portrait-comparison");
      await ui.getByRole("button", { name: "Avslutt sammenligning", exact: true }).click();
    },
  },
];

async function main() {
  const selected = options.has("--case") ? cases.filter(testcase => testcase.name === options.get("--case")) : cases;
  if (!selected.length) { console.error(`Unknown case. Available: ${cases.map(testcase => testcase.name).join(", ")}`); process.exitCode = 2; return; }
  const browser = await chromium.launch({ headless: !options.has("--headed"), ...(options.has("--browser-channel") ? { channel: options.get("--browser-channel") } : {}) });
  const results = [];
  try { for (const testcase of selected) { const result = await session(browser, testcase); results.push(result); console.log(`${result.status === "passed" ? "PASS" : "FAIL"}: ${result.name}${result.error ? ` — ${result.error}` : ""}`); } }
  finally { await browser.close(); }
  const report = { kind: "synthetic-role-scenarios", browser: options.get("--browser-channel") || "chromium", headed: options.has("--headed"), aksel: aksel?.version || null, results };
  if (evidence) fs.writeFileSync(path.join(evidence, "scenario-results.json"), `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify(report)); if (results.some(result => result.status !== "passed")) process.exitCode = 1;
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
