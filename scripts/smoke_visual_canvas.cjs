#!/usr/bin/env node
"use strict";

// Actual browser/server exercise with a simulated host. Never contacts a model.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { createRequire } = require("node:module");
// Juster is one of the Endre tools; open Endre first when its bar is hidden.
async function openAdjust(ui) {
  const adjust = ui.getByRole("button", { name: "Juster", exact: true });
  if (!(await adjust.isVisible())) await ui.getByRole("button", { name: "Endre", exact: true }).click();
  await adjust.click();
}
const options = new Map();
for (let index = 2; index < process.argv.length; index += 1) {
  const flag = process.argv[index];
  if (!["--playwright-module", "--browser-channel", "--aksel-project", "--evidence-dir", "--case"].includes(flag) || !process.argv[index + 1] || process.argv[index + 1].startsWith("--")) {
    console.error("Usage: node scripts/smoke_visual_canvas.cjs --aksel-project DIRECTORY [--playwright-module PATH] [--browser-channel chrome] [--evidence-dir DIRECTORY] [--case NAME]"); process.exit(2);
  }
  options.set(flag, process.argv[++index]);
}
if (!options.has("--aksel-project")) { console.error("Supply an existing Aksel project. No dependencies are installed."); process.exit(2); }
let chromium;
try { ({ chromium } = require(options.get("--playwright-module") || "playwright")); }
catch { console.error("Supply an existing Playwright installation. No dependencies are installed."); process.exit(2); }
const installedProject = path.resolve(options.get("--aksel-project")), installed = createRequire(path.join(installedProject, "package.json"));
const React = installed("react"), C = installed("@navikt/ds-react"), { renderToStaticMarkup } = installed("react-dom/server");
const packageRoot = path.join(installedProject, "node_modules/@navikt");
const akselVersion = JSON.parse(fs.readFileSync(path.join(packageRoot, "ds-react/package.json"))).version;
assert.equal(akselVersion, JSON.parse(fs.readFileSync(path.join(packageRoot, "ds-css/package.json"))).version);
assert.match(akselVersion, /^8\./);
const css = ["index.min.css", "index.css"].map(name => path.join(packageRoot, "ds-css/dist", name)).find(file => fs.existsSync(file));
assert(css);
const evidence = options.has("--evidence-dir") ? path.resolve(options.get("--evidence-dir")) : null;
if (evidence) fs.mkdirSync(evidence, { recursive: true });
const h = React.createElement;
function sketch(title) {
  const render = element => renderToStaticMarkup(element);
  return {
    design: { version: 1, variants: [], targets: [{ key: "meeting", variant: "", label: "Møteavtale", controls: [{ id: "detail", label: "Mengde forklaring", type: "select", initial: "short", options: [{ value: "short", label: "Kort" }, { value: "full", label: "Utfyllende" }] }] }] },
    html: `<style>.canvas-study{display:grid;gap:var(--ax-space-24)}.canvas-meeting{display:grid;gap:var(--ax-space-16);padding:var(--ax-space-24);border:1px solid var(--ax-border-neutral-subtle);border-radius:var(--ax-radius-8)}.canvas-extra{display:none}[data-vc-setting-detail=full] .canvas-extra{display:block}</style><main class="canvas-study">${render(h(C.Heading, { level: "1", size: "large" }, title))}${render(h(C.BodyShort, null, "Oppdiktet møte: Servicesenteret i Solvik, 18. november kl. 10.00."))}<section class="canvas-meeting" data-vc-key="meeting">${render(h(C.Heading, { level: "2", size: "medium" }, "Passer tidspunktet?"))}${render(h(C.BodyShort, null, "Den opprinnelige avtalen gjelder mens du ser på andre tider."))}<div class="canvas-extra">${render(h(C.BodyShort, null, "Du kan sammenligne flere tider før du bestemmer deg. Ingen avtale endres i denne skissen."))}</div></section>${render(h(C.TextField, { label: "Prøvefelt", id: "practice" }))}</main>`,
  };
}
function editableSketch(title) {
  const value = sketch(title);
  value.design.version = 2;
  value.design.texts = [{ id: "heading", label: "Overskrift", value: title }];
  value.design.targets[0].controls[0].editable = true;
  value.html = value.html.replace(renderToStaticMarkup(h(C.Heading, { level: "1", size: "large" }, title)), renderToStaticMarkup(h(C.Heading, { level: "1", size: "large" }, h("span", { "data-vc-text": "heading" }, "Tekst fra HTML før kildeverdien brukes"))));
  return value;
}
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(check, label, timeout = 12000) {
  const end = Date.now() + timeout;
  do { const value = await check(); if (value) return value; await pause(60); } while (Date.now() < end);
  throw new Error(`Timed out: ${label}`);
}
function viewFor(page) {
  const frame = page.frameLocator("#vc-preview"), ui = frame.locator("[data-visual-feedback]");
  const closeFeedback = async () => { const close = ui.getByRole("button", { name: "Lukk innspill", exact: true }); if (await close.isVisible()) await close.click(); };
  const workshop = ui.getByRole("region", { name: "Juster skissen", exact: true });
  const closeWorkshop = async () => { const close = workshop.getByRole("button", { name: "Lukk justeringer", exact: true }); if (await close.isVisible()) await close.click(); };
  return { page, frame, ui, workshop, closeFeedback, closeWorkshop,
    async openFeedback() { await closeWorkshop(); if (!(await ui.locator(".panel").isVisible())) await ui.locator('[data-action="panel"]').click(); },
    async note(value) { await closeFeedback(); await closeWorkshop(); if (await ui.locator('[data-action="change-ask"]').getAttribute("aria-pressed") !== "true") await ui.locator('[data-action="comment"]').click(); await frame.locator("h1").click(); await ui.getByLabel("Hva vil du endre?", { exact: true }).fill(value); },
    async save() { await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click(); await ui.locator(".composer").waitFor({ state: "hidden" }); await ui.locator(".panel").waitFor(); },
    async round(number, status) { const card = ui.locator(`[data-canvas-submission="${number}"]`); await until(async () => await card.getAttribute("data-status") === status, `round ${number} is ${status}`); return card; },
  };
}
async function runCase(browser, createCanvasAdapter, testcase) {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "grillmester-canvas-browser-"));
  const project = path.join(temporary, "project"), cssDirectory = path.join(project, "node_modules/@navikt/ds-css/dist");
  fs.mkdirSync(cssDirectory, { recursive: true }); fs.copyFileSync(css, path.join(cssDirectory, "index.min.css"));
  const adapters = [], contexts = [], views = [], errors = [], external = [], allMessages = [];
  const allowedOrigins = new Set();
  let adapterSequence = 0, publicationSequence = 0;
  try {
    const host = (send = async () => "accepted-message", sendTimeoutMs = 10000) => {
      const sessionId = `test-session-${++adapterSequence}`, calls = [];
      const adapter = createCanvasAdapter({ sessionId, projectDir: project, sendTimeoutMs }); adapters.push(adapter);
      adapter.attachSession({ sessionId, capabilities: { ui: { canvases: true } }, send: async request => {
        assert.equal(request.mode, "enqueue"); assert.equal(request.source, "user");
        const identity = JSON.parse(request.prompt.split("\n").at(-1));
        const message = { ...request, identity }; calls.push(message); allMessages.push(message);
        return send(request, calls.length);
      } });
      return { adapter, sessionId, calls };
    };
    const instance = async (bound, instanceId, title, { openInput = {}, publishInitial = true, fixture = sketch } = {}) => {
      const ctx = { sessionId: bound.sessionId, extensionId: "project:visual-companion", canvasId: "design-workspace", instanceId, session: { workingDirectory: project } };
      const action = (name, input = {}, override = {}) => bound.adapter.canvas.actions.find(item => item.name === name).handler({ ...ctx, ...override, input });
      let opened = await bound.adapter.canvas.open({ ...ctx, input: openInput });
      const publish = async nextTitle => { const current = await action("read_state"); const value = fixture(nextTitle); return action("publish_revision", { expectedScreen: current.screen, filename: `${String(++publicationSequence).padStart(2, "0")}-meeting.html`, ...value }); };
      if (publishInitial) await publish(title);
      const context = await browser.newContext({ viewport: testcase.viewport || { width: 390, height: 844 }, reducedMotion: "reduce" }); contexts.push(context);
      const page = await context.newPage(); page.setDefaultTimeout(12000);
      page.on("pageerror", error => errors.push(error.message));
      page.on("requestfinished", request => { if (!/^(data|blob):/.test(request.url()) && !allowedOrigins.has(new URL(request.url()).origin)) external.push(new URL(request.url()).origin); });
      const navigate = async url => { allowedOrigins.add(new URL(url).origin); await page.goto(url); await page.frameLocator("#vc-preview").locator('[data-visual-feedback] [data-action="comment"]').waitFor(); };
      await navigate(opened.url);
      const view = viewFor(page);
      await view.frame.getByRole("heading", { name: title, exact: true }).waitFor();
      await view.frame.getByLabel("Prøvefelt", { exact: true }).fill("PRIVATE_PRACTICE_VALUE");
      const snapshot = async () => { const url = new URL(opened.url); url.pathname = "/comments"; const response = await fetch(url); assert.equal(response.status, 200); return response.json(); };
      const send = async count => {
        const previous = (await snapshot()).submission;
        await view.openFeedback(); await view.ui.getByRole("button", { name: `Send ${count} innspill`, exact: true }).click();
        return until(async () => { const current = await snapshot(); return current.submission > previous && current; }, "explicit submission committed");
      };
      const reopen = async () => { const previous = opened; opened = await bound.adapter.canvas.open(ctx); assert.notEqual(opened.url, previous.url, "Reopening rotates the transport capability."); await navigate(opened.url); return { previous, current: opened }; };
      const item = { ...view, ctx, action, publish, snapshot, send, reopen, host: bound, close: () => bound.adapter.canvas.onClose(ctx), url: () => opened.url, retired: false };
      item.retire = async () => { item.retired = true; await context.close(); await bound.adapter.close(); };
      views.push(item); return item;
    };
    const screenshot = async (view, suffix) => { if (evidence) { await view.page.locator("#vc-status").filter({ hasText: /^Tilkoblet$/ }).waitFor(); await view.page.screenshot({ path: path.join(evidence, `${testcase.name}-${suffix}.png`), animations: "disabled" }); } };
    const measured = await testcase.run({ host, instance, screenshot });
    for (const view of views.filter(item => !item.retired)) assert.equal(JSON.stringify(await view.snapshot()).includes("PRIVATE_PRACTICE_VALUE"), false, "Ordinary form contents must not enter feedback snapshots.");
    assert(allMessages.every(item => !item.prompt.includes("PRIVATE_PRACTICE_VALUE")), "The notification must not contain ordinary form values.");
    assert.deepEqual(errors, []); assert.deepEqual(external, []);
    return { name: testcase.name, passed: true, simulatedHost: true, modelCalls: 0, enqueuedMessages: allMessages.length, ...measured, browserExceptions: errors, completedExternalResources: external };
  } catch (error) {
    if (evidence) for (const [index, view] of views.entries()) await screenshotFailure(view, `${testcase.name}-failed-${index}`);
    return { name: testcase.name, passed: false, error: error.message.replace(/http:\/\/127\.0\.0\.1:[^\s)]+/g, "[local preview]") };
  } finally {
    await Promise.all(contexts.map(context => context.close()));
    await Promise.all(adapters.map(adapter => adapter.close()));
    fs.rmSync(temporary, { recursive: true, force: true });
  }
}
async function screenshotFailure(view, name) { try { await view.page.screenshot({ path: path.join(evidence, `${name}.png`), animations: "disabled" }); } catch { /* Preserve the assertion if the page closed. */ } }
async function openEditor(view) {
  await view.closeFeedback();
  // Rediger is one of the Endre tools, next to Be om endring and Juster. After a
  // save the preview reloads, so wait until the current document offers it.
  const edit = view.ui.getByRole("button", { name: "Rediger", exact: true });
  await until(async () => {
    if (await edit.isVisible() && await edit.isEnabled()) return true;
    const endre = view.ui.getByRole("button", { name: "Endre", exact: true });
    if (!(await edit.isVisible()) && await endre.isVisible() && await endre.isEnabled()) await endre.click().catch(() => {});
    return false;
  }, "Rediger is available in the Endre bar");
  await edit.click();
  const editor = view.ui.getByRole("region", { name: "Rediger skissen", exact: true });
  await editor.getByLabel("Overskrift", { exact: true }).waitFor();
  await until(async () => await editor.getByLabel("Overskrift", { exact: true }).isEnabled(), "source editor ready");
  return editor;
}
const cases = [
  { name: "editor-keyboard-error-and-proposal-ownership", viewport: { width: 320, height: 568 }, async run({ host, instance, screenshot }) {
    const fixture = title => {
      const value = editableSketch(title), lead = "Oppdiktet møte: Servicesenteret i Solvik, 18. november kl. 10.00.";
      value.design.texts.push({ id: "lead", label: "Forklaring", value: lead });
      value.html = value.html.replace(renderToStaticMarkup(h(C.BodyShort, null, lead)), renderToStaticMarkup(h(C.BodyShort, null, h("span", { "data-vc-text": "lead" }, "Opprinnelig forklaring"))));
      return value;
    };
    const bound = host(), view = await instance(bound, "keyboard-source", "Din avtale", { fixture, openInput: { workspacePath: "design/keyboard", create: true, title: "Tekst og innspill" } });
    await view.ui.getByRole("button", { name: "Endre", exact: true }).click(); await view.frame.locator("[data-vc-text=heading]").click();
    await view.ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Foreslår en annen tittel til vurdering.");
    await view.ui.getByRole("button", { name: "Foreslå ny tekst", exact: true }).click(); await view.ui.getByLabel("Ny tekst", { exact: true }).fill("Forslag som fortsatt er et innspill"); await view.save();
    const originalComment = (await view.snapshot()).comments[0];
    const editor = await openEditor(view);
    await view.page.keyboard.press("Tab"); const heading = editor.getByLabel("Overskrift", { exact: true });
    assert(await heading.evaluate(node => node.getRootNode().activeElement === node));
    await heading.fill("Lokal redigering av overskriften"); await view.page.keyboard.press("Tab");
    const explanation = editor.getByLabel("Forklaring", { exact: true }); assert(await explanation.evaluate(node => node.getRootNode().activeElement === node));
    await explanation.fill("ø".repeat(1001));
    await view.page.keyboard.press("Tab"); await view.page.keyboard.press("Tab"); await view.page.keyboard.press("Enter");
    await editor.locator(".source-editor-error").waitFor();
    assert(await explanation.evaluate(node => node.getRootNode().activeElement === node));
    assert.equal(await explanation.getAttribute("aria-invalid"), "true");
    const geometry = await explanation.evaluate(node => { const clip=node.closest(".source-editor-body").getBoundingClientRect(), r=node.getBoundingClientRect(), e=node.getRootNode().querySelector(".source-editor-error").getBoundingClientRect(); return { input:{top:r.top,bottom:r.bottom},error:{top:e.top,bottom:e.bottom},clip:{top:clip.top,bottom:clip.bottom},inputVisible:r.top>=clip.top && r.bottom<=clip.bottom,errorVisible:e.top>=clip.top && e.bottom<=clip.bottom }; });
    await screenshot(view, "keyboard-validation-at-last-text-field");
    assert(geometry.inputVisible && geometry.errorVisible, JSON.stringify(geometry));
    assert.equal((await view.snapshot()).workspace.version, 1); assert.deepEqual((await view.snapshot()).comments[0], originalComment); assert.equal(bound.calls.length, 0);
    await view.page.keyboard.press("Escape"); assert.equal(await view.frame.locator("[data-vc-text=heading]").textContent(), "Din avtale");
    await openEditor(view); assert.equal(await heading.inputValue(), "Lokal redigering av overskriften"); assert.equal(await explanation.inputValue(), "ø".repeat(1001));
    await editor.getByRole("button", { name: "Forkast endringer", exact: true }).click(); await editor.getByRole("button", { name: "Lukk redigering", exact: true }).click();
    await view.openFeedback(); assert.deepEqual((await view.snapshot()).comments[0], originalComment);
    return { keyboardTabEnterEscape: true, fieldLinkedUnicodeError: true, sourceWrites: 0, feedbackProposalUnchanged: true, paneCloseRetainsDraft: true, geometry, automaticSubmissions: 0 };
  } },
  { name: "editor-save-retry-and-reopen", viewport: { width: 320, height: 568 }, async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "source", "Avtalen din", { fixture: editableSketch, openInput: { workspacePath: "design/source", create: true, title: "Redigert avtale" } });
    const before = await view.snapshot();
    let readCount = 0;
    view.page.on("request", request => { if (new URL(request.url()).pathname === "/workspace/editor" && request.method() === "GET") { assert.equal(request.headers()["x-feedback-mutation"], undefined); readCount += 1; } });
    let editor = await openEditor(view), field = editor.getByLabel("Overskrift", { exact: true });
    assert.equal(await field.inputValue(), "Avtalen din", "Canonical sidecar text must render before authoring begins.");
    const attempts = [];
    await view.page.route(/\/workspace\/editor\/save(?:\?|$)/, async route => {
      attempts.push({ key: route.request().headers()["x-feedback-mutation"], payload: route.request().postDataJSON() });
      if (attempts.length !== 1) { await route.continue(); return; }
      const response = await route.fetch(); assert.equal(response.status(), 200); await route.abort("failed");
    });
    await field.fill("ø".repeat(1001)); await editor.getByRole("button", { name: "Lagre som ny versjon", exact: true }).click();
    assert.equal(attempts.length, 0); assert.equal(await field.getAttribute("aria-invalid"), "true");
    assert(await field.evaluate(node => node.getRootNode().activeElement === node));
    assert.match(await editor.locator(".source-editor-error").textContent(), /Kort den ned/);
    const literal = 'Din <img src=x onerror=alert(1)> avtale';
    await field.fill(literal); await editor.getByLabel("Mengde forklaring · Møteavtale", { exact: true }).selectOption("full");
    assert.equal(await view.frame.locator("[data-vc-text=heading]").textContent(), literal);
    assert.equal(await view.frame.locator("[data-vc-text=heading] img").count(), 0);
    assert.equal(await view.frame.locator("[data-vc-key=meeting]").getAttribute("data-vc-setting-detail"), "full");
    assert.equal((await view.snapshot()).workspace.version, 1); assert.equal(bound.calls.length, 0);
    const geometry = await editor.evaluate(node => { const r=node.getBoundingClientRect(), body=node.querySelector(".source-editor-body"); return { left:r.left,right:r.right,width:innerWidth,bodyHeight:body.clientHeight,overflow:body.scrollWidth>body.clientWidth+1 }; });
    assert(geometry.left >= 0 && geometry.right <= geometry.width && geometry.bodyHeight >= 100, JSON.stringify(geometry)); assert.equal(geometry.overflow, false);
    await screenshot(view, "local-fields-at-320");
    await editor.getByRole("button", { name: "Lukk redigering", exact: true }).click();
    assert.equal(await view.frame.locator("[data-vc-text=heading]").textContent(), "Avtalen din");
    editor = await openEditor(view); assert.equal(await editor.getByLabel("Overskrift", { exact: true }).inputValue(), literal);
    let releaseVersion;
    const versionGate = new Promise(resolve => { releaseVersion = resolve; });
    await view.page.route(/\/version(?:\?|$)/, async route => { await versionGate; await route.continue(); });
    const oldFrame = await view.page.locator("#vc-preview").getAttribute("src");
    await editor.getByRole("button", { name: "Lagre som ny versjon", exact: true }).click(); await editor.locator(".source-editor-error").waitFor();
    assert.equal((await view.snapshot()).workspace.version, 2);
    await editor.getByRole("button", { name: "Prøv samme lagring igjen", exact: true }).click();
    await until(async () => /Den nye versjonen er lagret/.test(await editor.locator(".source-editor-status").textContent()), "save receipt before delayed version poll");
    assert.equal(await view.page.locator("#vc-preview").getAttribute("src"), oldFrame);
    assert.equal(await view.frame.locator("[data-vc-text=heading]").textContent(), "Avtalen din", "Before replacement, the old frame must show its own source rather than saved text from a newer revision.");
    const receiptLock = await view.ui.evaluate(node => ({ enabled: [...node.shadowRoot.querySelectorAll("button,input,textarea,select")].filter(item => !item.disabled).length }));
    assert.equal(receiptLock.enabled, 0, "Accepted source edits lock input even before the next version poll can return.");
    releaseVersion();
    await until(async () => await view.page.frameLocator("#vc-preview").locator("[data-visual-feedback]").evaluate(node => node.shadowRoot.querySelector(".source-editor")?.hidden === true), "saved version replaced the editor frame");
    await view.frame.getByRole("heading", { name: literal, exact: true }).waitFor();
    assert.equal(attempts.length, 2); assert.match(attempts[0].key, /^[a-f0-9]{32}$/); assert.deepEqual(attempts[0], attempts[1]);
    const saved = await view.snapshot(); assert.equal(saved.workspace.version, 2); assert.equal(saved.submission, before.submission); assert.equal(bound.calls.length, 0);
    assert.equal(saved.workspace.preservedFields.length, 2);
    assert.equal(readCount, 1, "Closing and reopening the pane retains its draft without silently rebasing.");
    await view.retire();
    const successor = host(), reopened = await instance(successor, "source-reopened", literal, { fixture: editableSketch, publishInitial: false, openInput: { workspacePath: "design/source" } });
    assert.equal(await reopened.frame.locator("[data-vc-key=meeting]").getAttribute("data-vc-setting-detail"), "full");
    editor = await openEditor(reopened);
    assert.equal(await editor.getByLabel("Overskrift", { exact: true }).inputValue(), literal);
    assert.equal(await editor.getByRole("button", { name: /^Tillat senere endring for/ }).count(), 2);
    await screenshot(reopened, "saved-fields-after-backend-restart");
    return { unicodeBytesRejected: 2002, validationWrites: 0, literalMarkupIsText: true, localPreviewAndPaneDraftPreserved: true, readWithoutMutation: readCount, saveAttempts: attempts.length, identicalRetryIntent: true, acceptedBeforePollLock: receiptLock, newVersions: 1, reopenedCanonicalFields: 2, geometry, automaticSubmissions: 0 };
  } },
  { name: "editor-draft-publish-and-refresh-lock", async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "editing", "Første utkast", { fixture: editableSketch, openInput: { workspacePath: "design/draft", create: true, title: "Utkast og ny kilde" } });
    let editor = await openEditor(view); await editor.getByLabel("Overskrift", { exact: true }).fill("Min påbegynte overskrift");
    await view.publish("Ny overskrift fra designarbeidet");
    const refresh = view.ui.locator('[data-action="refresh"]'); await refresh.waitFor(); assert(await refresh.isDisabled());
    assert.equal(await editor.getByLabel("Overskrift", { exact: true }).inputValue(), "Min påbegynte overskrift");
    assert.equal(await view.frame.locator("[data-vc-text=heading]").textContent(), "Min påbegynte overskrift");
    await until(async () => await editor.getByRole("button", { name: "Lagre som ny versjon", exact: true }).isDisabled(), "stale draft cannot save old source");
    await screenshot(view, "draft-retained-across-publish");
    await editor.getByRole("button", { name: "Forkast endringer", exact: true }).click();
    assert.equal(await view.frame.locator("[data-vc-text=heading]").textContent(), "Første utkast");
    // Capture the actual old frame's controls in the same dispatch turn, before the shell's 400 ms replacement.
    const lock = await refresh.evaluate(button => { const root=button.getRootNode(); button.click(); return { refresh:button.disabled, enabledInputs:[...root.querySelectorAll("textarea,input,select")].filter(node=>!node.disabled).length, enabledButtons:[...root.querySelectorAll("button")].filter(node=>!node.disabled).length }; });
    assert.deepEqual(lock, { refresh: true, enabledInputs: 0, enabledButtons: 0 });
    await view.frame.getByRole("heading", { name: "Ny overskrift fra designarbeidet", exact: true }).waitFor();
    editor = await openEditor(view); assert.equal(await editor.getByLabel("Overskrift", { exact: true }).inputValue(), "Ny overskrift fra designarbeidet");
    assert.equal((await view.snapshot()).workspace.version, 2); assert.equal(bound.calls.length, 0);
    return { draftRetained: true, staleSaveDisabled: true, discardRestoresVisibleSource: true, synchronousRefreshLock: lock, latestSourceRead: true, automaticSubmissions: 0 };
  } },
  { name: "editor-manual-hold-and-keep-conflict", viewport: { width: 1280, height: 900 }, async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "constraints", "Avtalens overskrift", { fixture: editableSketch, openInput: { workspacePath: "design/constraints", create: true, title: "Bevarte valg" } });
    await openAdjust(view.ui);
    await view.workshop.getByLabel("Mengde forklaring", { exact: true }).selectOption("full");
    await view.workshop.getByRole("button", { name: "Behold dette", exact: true }).click(); await view.ui.locator(".panel").waitFor();
    let editor = await openEditor(view); await editor.getByLabel("Overskrift", { exact: true }).fill("Min beholdte overskrift");
    // The source is short, while the explicitly kept workshop choice is full.
    await editor.getByLabel("Mengde forklaring · Møteavtale", { exact: true }).selectOption("full");
    await editor.getByLabel("Mengde forklaring · Møteavtale", { exact: true }).selectOption("short");
    // A changed finite value is required to test the keep guard: save full first, then try short against that saved source below.
    await editor.getByLabel("Mengde forklaring · Møteavtale", { exact: true }).selectOption("full");
    await editor.getByRole("button", { name: "Lagre som ny versjon", exact: true }).click();
    await view.frame.getByRole("heading", { name: "Min beholdte overskrift", exact: true }).waitFor();
    await until(async () => (await view.snapshot()).workspace.version === 2, "manual fields saved");
    await assert.rejects(view.publish("Forsøk på å endre overskriften"), error => error.status === 409);
    const saved = await view.snapshot(); await assert.rejects(view.action("restore_revision", { revisionId: 1, expectedRevision: saved.revision }), error => error.status === 409);
    editor = await openEditor(view); await editor.getByLabel("Mengde forklaring · Møteavtale", { exact: true }).selectOption("short");
    await editor.getByRole("button", { name: "Lagre som ny versjon", exact: true }).click(); await editor.locator(".source-editor-error").waitFor();
    assert.match(await editor.locator(".source-editor-error").textContent(), /Behold dette/); assert.equal((await view.snapshot()).workspace.version, 2);
    await editor.getByRole("button", { name: "Lukk redigering", exact: true }).click();
    await view.openFeedback(); await view.ui.getByRole("button", { name: "Slutt å beholde", exact: true }).click();
    editor = await openEditor(view); assert.equal(await editor.getByLabel("Mengde forklaring · Møteavtale", { exact: true }).inputValue(), "short");
    await editor.getByRole("button", { name: "Oppdater grunnlaget", exact: true }).click();
    await until(async () => await editor.getByRole("button", { name: "Lagre som ny versjon", exact: true }).isEnabled(), "explicit same-source rebase after keep release");
    assert(await editor.getByRole("button", { name: "Lagre som ny versjon", exact: true }).evaluate(node => node.getRootNode().activeElement === node));
    assert.equal(await editor.getByLabel("Mengde forklaring · Møteavtale", { exact: true }).inputValue(), "short");
    await editor.getByRole("button", { name: "Lagre som ny versjon", exact: true }).click();
    await until(async () => (await view.snapshot()).workspace.version === 3, "changed finite source saved after release");
    await until(async () => await view.ui.locator(".source-editor").isHidden(), "third version opened");
    editor = await openEditor(view);
    await editor.getByRole("button", { name: "Tillat senere endring for Overskrift", exact: true }).click();
    await until(async () => await editor.getByRole("button", { name: "Tillat senere endring for Overskrift", exact: true }).count() === 0, "manual heading hold released");
    assert(await editor.getByLabel("Overskrift", { exact: true }).evaluate(node => node.getRootNode().activeElement === node));
    await editor.getByRole("button", { name: "Tillat senere endring for Mengde forklaring · Møteavtale", exact: true }).click();
    await until(async () => await editor.getByRole("button", { name: /^Tillat senere endring for/ }).count() === 0, "manual finite hold released");
    assert(await editor.getByLabel("Mengde forklaring · Møteavtale", { exact: true }).evaluate(node => node.getRootNode().activeElement === node));
    assert.equal(await editor.getByLabel("Overskrift", { exact: true }).inputValue(), "Min beholdte overskrift");
    assert.equal((await view.snapshot()).workspace.version, 3, "Releasing constraints must not create a source revision.");
    await screenshot(view, "explicit-releases-preserve-current-values");
    await editor.getByRole("button", { name: "Lukk redigering", exact: true }).click(); await view.publish("Neste avtaleforslag");
    const final = await view.snapshot(); assert.equal(final.workspace.version, 4); assert.equal(final.submission, 0); assert.equal(bound.calls.length, 0);
    return { manualPublishAndRestoreConflicts: 2, keepConflictRetainsDraft: true, explicitSameSourceRebase: true, manualReleases: 2, releaseCreatesNoRevision: true, publicationAfterRelease: true, automaticSubmissions: 0 };
  } },
  { name: "endre-parts-and-whole-sketch", viewport: { width: 390, height: 844 }, async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "parts", "Timeavtale · deler", { fixture: editableSketch, openInput: { workspacePath: "design/deler", create: true, title: "Deler" } });
    await view.ui.getByRole("button", { name: "Endre", exact: true }).click();
    await view.ui.getByRole("group", { name: "Endre skissen", exact: true }).waitFor();
    assert.equal(await view.ui.locator('[data-action="change-ask"]').getAttribute("aria-pressed"), "true", "Endre starts with Be om endring.");
    const parts = view.ui.getByLabel("Velg en del", { exact: true });
    assert.deepEqual(await parts.locator("option").allTextContents(), ["Eller velg en del …", "Hele skissen", "Møteavtale", "Overskrift"]);
    await screenshot(view, "endre-bar");
    const pointed = async () => {
      const item = (await view.snapshot()).comments.at(-1);
      return { item, element: await view.frame.locator("body").evaluate((_, path) => {
        const node = document.querySelector(path);
        return node && { tag: node.localName, key: node.getAttribute("data-vc-key"), text: node.getAttribute("data-vc-text"), content: node.classList.contains("vc-content") };
      }, item.anchor.path) };
    };
    await parts.selectOption("whole");
    await view.ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Hele flyten bør bli kortere.");
    await view.save();
    const whole = await pointed();
    assert.equal(whole.element.content, true, "Hele skissen points at the sketch content.");
    await view.closeFeedback();
    if (await view.ui.locator('[data-action="change-ask"]').getAttribute("aria-pressed") !== "true") await view.ui.getByRole("button", { name: "Endre", exact: true }).click();
    await parts.selectOption({ label: "Møteavtale" });
    await view.ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Vis hva som skjer med den opprinnelige timen.");
    await view.save();
    const part = await pointed();
    assert.equal(part.element.key, "meeting", "A declared part points at its own element.");
    assert.equal(part.item.kind, "point"); assert.equal((await view.snapshot()).submission, 0); assert.equal(bound.calls.length, 0);
    await view.closeFeedback();
    await view.ui.getByRole("button", { name: "Prøv", exact: true }).click();
    assert(await view.ui.getByRole("group", { name: "Endre skissen", exact: true }).isHidden(), "Prøv leaves Endre.");
    return { wholeSketchAnchor: true, declaredPartAnchor: "meeting", automaticSubmissions: 0 };
  } },
  { name: "workspace-view-stored-version-read-only", viewport: { width: 390, height: 844 }, async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "view-stored", "Timeavtale · første", { openInput: { workspacePath: "design/visning", create: true, title: "Visning" } });
    await view.publish("Timeavtale · andre"); await view.frame.getByRole("heading", { name: "Timeavtale · andre", exact: true }).waitFor();
    const before = await view.snapshot(); let restoreRequests = 0;
    view.page.on("request", request => { if (new URL(request.url()).pathname === "/workspace/restore") restoreRequests += 1; });
    const banner = view.ui.getByText("Viser lagret versjon 1. Ingen ny versjon er laget.", { exact: true });
    await view.ui.getByRole("button", { name: "Versjoner", exact: true }).click();
    await view.ui.locator('.workspace-revision[data-revision-id="1"]').getByRole("button", { name: "Vis versjon 1", exact: true }).click();
    await view.frame.getByRole("heading", { name: "Timeavtale · første", exact: true }).waitFor(); await banner.waitFor();
    for (const name of ["Kommenter", "Juster", "Innspill"]) assert.equal(await view.ui.getByRole("button", { name, exact: true }).count(), 0, `${name} is not offered on a stored version.`);
    assert.deepEqual(await view.snapshot(), before, "Viewing changes nothing in the room."); assert.equal(restoreRequests, 0);
    await screenshot(view, "stored-version-read-only");
    await view.publish("Timeavtale · tredje"); await new Promise(resolve => setTimeout(resolve, 4500));
    assert(await view.frame.getByRole("heading", { name: "Timeavtale · første", exact: true }).isVisible(), "A newer version does not replace the stored version on screen.");
    await view.ui.getByRole("button", { name: "Tilbake til gjeldende versjon", exact: true }).click();
    await view.frame.getByRole("heading", { name: "Timeavtale · tredje", exact: true }).waitFor();
    await view.ui.locator('[data-action="comment"]').waitFor(); assert.equal(await banner.count(), 0);
    await view.ui.getByRole("button", { name: "Versjoner", exact: true }).click();
    await view.ui.locator('.workspace-revision[data-revision-id="1"]').getByRole("button", { name: "Vis versjon 1", exact: true }).click(); await banner.waitFor();
    await view.ui.getByRole("button", { name: "Bruk som ny versjon", exact: true }).first().click();
    await view.ui.locator('[data-action="workspace-restore"]').click();
    await until(async () => (await view.snapshot()).workspace.version === 4, "stored version used as a new version");
    await view.ui.locator('[data-action="comment"]').waitFor(); assert.equal(await banner.count(), 0);
    await view.frame.getByRole("heading", { name: "Timeavtale · første", exact: true }).waitFor();
    assert.equal(restoreRequests, 1); assert.equal(bound.calls.length, 0);
    await screenshot(view, "stored-version-used-as-new");
    return { viewedRevision: 1, viewingWritesNothing: true, newerVersionWaited: true, returnedToCurrent: true, restoredFromView: 4, automaticSubmissions: 0 };
  } },
  { name: "workspace-limit-preserves-history", async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "capacity", "Timeavtale · første", { openInput: { workspacePath: "design/capacity", create: true, title: "Bevart historikk" } });
    await view.publish("Timeavtale · andre"); await view.frame.getByRole("heading", { name: "Timeavtale · andre", exact: true }).waitFor();
    const before = await view.snapshot(); let attempts = 0;
    // The backend capacity limit has its own tests; exercise the browser's permanent-error guidance without creating 100 revisions here.
    await view.page.route(/\/workspace\/restore(?:\?|$)/, async route => { attempts += 1; await route.fulfill({ status: 429, contentType: "application/json", body: JSON.stringify({ error: "Workspace capacity reached." }) }); });
    await view.ui.getByRole("button", { name: "Versjoner", exact: true }).click(); await view.ui.locator('.workspace-revision[data-revision-id="1"]').getByRole("button", { name: "Bruk som ny versjon", exact: true }).click(); await view.ui.locator('[data-action="workspace-restore"]').click();
    await view.ui.locator(".workspace-error").waitFor(); assert.match(await view.ui.locator(".workspace-error").textContent(), /lagringsgrense/);
    assert(await view.ui.getByRole("button", { name: "Lagringsgrensen er nådd", exact: true }).isDisabled());
    assert.equal(await view.ui.getByRole("button", { name: "Prøv samme gjenoppretting igjen", exact: true }).count(), 0);
    assert.deepEqual(await view.snapshot(), before); assert.equal(attempts, 1); assert.equal(bound.calls.length, 0);
    await screenshot(view, "clear-permanent-error");
    return { injectedResponse: 429, unchangedWorkspace: true, noMisleadingRetry: true, automaticSubmissions: 0 };
  } },
  { name: "workspace-recover-in-new-session", async run({ host, instance, screenshot }) {
    const first = host(async () => { throw new Error("No receipt"); });
    const original = await instance(first, "first-opening", "Timeavtale · første versjon", { openInput: { workspacePath: "design/timeavtale", create: true, title: "Timeavtale" } });
    await openAdjust(original.ui);
    await original.workshop.getByLabel("Mengde forklaring", { exact: true }).selectOption("full");
    await original.workshop.getByLabel("Merknad", { exact: true }).fill("Behold forklaringen om den opprinnelige avtalen.");
    await original.workshop.getByRole("button", { name: "Behold dette", exact: true }).click(); await original.ui.locator(".panel").waitFor();
    await original.note("Første innspill, sendt i den tidligere samtalen."); await original.save(); await original.send(2); await original.round(1, "unknown");
    await original.note("Nytt innspill som er lagret, men ikke sendt."); await original.save();
    await original.publish("Timeavtale · neste dag");
    const saved = await original.snapshot(); assert.equal(saved.workspace.storage, "project"); assert.equal(saved.workspace.version, 2);
    await original.retire();
    const next = host(), reopened = await instance(next, "second-opening", "Timeavtale · neste dag", { openInput: { workspacePath: "design/timeavtale" }, publishInitial: false });
    const recovered = await reopened.snapshot();
    assert.equal(recovered.workspace.id, saved.workspace.id); assert.equal(recovered.workspace.version, saved.workspace.version); assert.equal(recovered.workspace.recovered, true);
    assert.deepEqual(recovered.comments, saved.comments); assert.deepEqual(recovered.decisions, saved.decisions);
    assert.equal(next.calls.length, 0, "Opening a project must not deliver historical rounds.");
    await reopened.openFeedback(); const old = await reopened.round(1, "previous");
    assert.equal(await old.locator(".badge").textContent(), "Fra tidligere samtale");
    assert.match(await old.locator(".workspace-previous").textContent(), /uavklart/);
    assert(await reopened.ui.getByRole("button", { name: "Send 1 innspill", exact: true }).isEnabled(), "A previous session's uncertainty must not permanently block new feedback.");
    await screenshot(reopened, "previous-round-and-new-feedback");
    await reopened.closeFeedback(); await reopened.ui.getByRole("button", { name: "Versjoner", exact: true }).click();
    await reopened.ui.locator(".workspace-history-list article").first().waitFor();
    assert.equal(await reopened.ui.locator(".workspace-title").textContent(), "Timeavtale");
    assert.match(await reopened.ui.locator(".workspace-path").textContent(), /design\/timeavtale/);
    assert(await reopened.ui.locator(".workspace-recovered").isVisible());
    await screenshot(reopened, "project-workspace-reopened");
    await reopened.ui.getByRole("button", { name: "Lukk versjoner", exact: true }).click();
    await reopened.send(1); await reopened.round(2, "queued");
    assert.equal(next.calls.length, 1); assert.equal(next.calls[0].identity.submission, 2);
    assert.equal(first.calls.length, 1);
    return { actualBackendRestart: true, projectIdentityPreserved: true, savedUnsentFeedbackPreserved: true, retainedDecisionsPreserved: true, historicalUnknownDistinguished: true, openingEnqueuesNothing: true, onlyNewRoundSent: true };
  } },
  { name: "workspace-restore-protects-draft", viewport: { width: 1280, height: 900 }, async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "restoring", "Timeavtale · opprinnelig", { openInput: { workspacePath: "design/restore", create: true, title: "Timeavtale med historikk" } });
    await view.publish("Timeavtale · bearbeidet"); await view.frame.getByRole("heading", { name: "Timeavtale · bearbeidet", exact: true }).waitFor();
    await view.note("Lagret innspill til den bearbeidede versjonen."); await view.save();
    const saved = await view.snapshot();
    await view.note("Ulagret begrunnelse som må beholdes."); await view.ui.getByRole("button", { name: "Foreslå ny tekst", exact: true }).click(); await view.ui.getByLabel("Ny tekst", { exact: true }).fill("Din neste avtale");
    let restoreRequests = 0;
    view.page.on("request", request => { if (new URL(request.url()).pathname === "/workspace/restore") restoreRequests += 1; });
    await view.ui.getByRole("button", { name: "Versjoner", exact: true }).click();
    await view.ui.locator('.workspace-revision[data-revision-id="1"]').getByRole("button", { name: "Bruk som ny versjon", exact: true }).click();
    assert(await view.ui.locator('[data-action="workspace-restore"]').isDisabled()); assert.equal(restoreRequests, 0);
    assert.match(await view.ui.locator(".workspace-restore-warning").textContent(), /Utkastet ditt er beholdt/);
    await screenshot(view, "draft-blocks-restore");
    await view.ui.getByRole("button", { name: "Lukk versjoner", exact: true }).click(); await view.ui.getByRole("button", { name: "Fortsett utkast", exact: true }).click();
    assert.equal(await view.ui.getByLabel("Hva vil du endre?", { exact: true }).inputValue(), "Ulagret begrunnelse som må beholdes."); assert.equal(await view.ui.getByLabel("Ny tekst", { exact: true }).inputValue(), "Din neste avtale");
    await view.ui.getByRole("button", { name: "Forkast", exact: true }).click();
    await view.ui.getByRole("button", { name: "Versjoner", exact: true }).click();
    await view.ui.locator('.workspace-revision[data-revision-id="1"]').getByRole("button", { name: "Bruk som ny versjon", exact: true }).click();
    await view.ui.locator('[data-action="workspace-restore"]').click();
    await view.frame.getByRole("heading", { name: "Timeavtale · opprinnelig", exact: true }).waitFor();
    const restored = await view.snapshot();
    assert.equal(restored.workspace.version, 3); assert.deepEqual(restored.comments, saved.comments); assert.equal(restored.submission, 0); assert.equal(bound.calls.length, 0); assert.equal(restoreRequests, 1);
    await view.ui.getByRole("button", { name: "Versjoner", exact: true }).click();
    const revision = view.ui.locator('.workspace-revision[data-revision-id="3"]'); await revision.waitFor();
    assert.match(await revision.textContent(), /Fra versjon 1/); assert(await revision.getByRole("button", { name: "Gjeldende versjon", exact: true }).isDisabled());
    await screenshot(view, "restored-as-new-version");
    return { localDraftBothFieldsPreserved: true, restoreBlockedWhileDraftExists: true, newRevisionCreated: 3, savedFeedbackPreserved: true, restoredVersionOpenedWithUnsentFeedback: true, automaticSubmissions: 0 };
  } },
  { name: "workspace-history-and-lost-restore-receipt", viewport: { width: 320, height: 568 }, async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "many-revisions", "Timeavtale · versjon 1", { openInput: { workspacePath: "design/history", create: true, title: "Timeavtale: historikk" } });
    for (let version = 2; version <= 22; version += 1) await view.publish(`Timeavtale · versjon ${version}`);
    await view.frame.getByRole("heading", { name: "Timeavtale · versjon 22", exact: true }).waitFor();
    await view.note("Lagret innspill skal overleve gjenoppretting."); await view.save(); const saved = await view.snapshot();
    await view.ui.getByRole("button", { name: "Versjoner", exact: true }).click();
    await until(async () => await view.ui.locator(".workspace-revision").count() === 20, "first bounded history page");
    const initialOrder = await view.ui.locator(".workspace-revision").evaluateAll(nodes => nodes.map(node => Number(node.dataset.revisionId)));
    assert.deepEqual(initialOrder, Array.from({ length: 20 }, (_, index) => 22 - index));
    await view.ui.getByRole("button", { name: "Vis flere versjoner", exact: true }).click();
    await until(async () => await view.ui.locator(".workspace-revision").count() === 22, "remaining history page");
    assert.equal(await view.ui.getByRole("button", { name: "Vis flere versjoner", exact: true }).isVisible(), false);
    const attempts = [];
    await view.page.route(/\/workspace\/restore(?:\?|$)/, async route => {
      attempts.push({ key: route.request().headers()["x-feedback-mutation"], payload: route.request().postDataJSON() });
      if (attempts.length !== 1) { await route.continue(); return; }
      const response = await route.fetch(); assert.equal(response.status(), 200); await route.abort("failed");
    });
    await view.ui.locator('.workspace-revision[data-revision-id="1"]').getByRole("button", { name: "Bruk som ny versjon", exact: true }).click(); await view.ui.locator('[data-action="workspace-restore"]').click();
    await view.ui.locator(".workspace-error").waitFor();
    const committed = await view.snapshot(); assert.equal(committed.workspace.version, 23);
    assert.equal(await view.frame.getByRole("heading", { name: "Timeavtale · versjon 22", exact: true }).isVisible(), true, "The uncertain receipt must not silently replace the visible sketch.");
    await screenshot(view, "lost-receipt-keeps-reviewed-action");
    await view.ui.getByRole("button", { name: "Prøv samme gjenoppretting igjen", exact: true }).click();
    await view.frame.getByRole("heading", { name: "Timeavtale · versjon 1", exact: true }).waitFor();
    const recovered = await view.snapshot(); assert.equal(recovered.workspace.version, 23); assert.deepEqual(recovered.comments, saved.comments);
    assert.equal(attempts.length, 2); assert.match(attempts[0].key, /^[a-f0-9]{32}$/); assert.equal(attempts[0].key, attempts[1].key); assert.deepEqual(attempts[0].payload, attempts[1].payload); assert.equal(bound.calls.length, 0);
    await view.ui.getByRole("button", { name: "Versjoner", exact: true }).click(); await view.ui.locator('.workspace-revision[data-revision-id="23"]').waitFor();
    const bounds = await view.ui.locator(".workspace-panel").evaluate(node => { const rect = node.getBoundingClientRect(), body = node.querySelector(".workspace-body"); return { left: rect.left, right: rect.right, viewport: innerWidth, readingHeight: body.clientHeight, horizontalOverflow: body.scrollWidth > body.clientWidth + 1 }; });
    assert(bounds.left >= 0 && bounds.right <= bounds.viewport + 1); assert(bounds.readingHeight >= 150); assert.equal(bounds.horizontalOverflow, false);
    const firstVersionVisible = await view.ui.locator('.workspace-revision[data-revision-id="23"] h3').evaluate(node => { const rect = node.getBoundingClientRect(), clip = node.closest(".workspace-body").getBoundingClientRect(); return rect.top >= clip.top && rect.bottom <= clip.bottom; });
    assert(firstVersionVisible, "The first version heading should be readable before scrolling the narrow workspace panel.");
    await screenshot(view, "restored-history-at-320");
    return { pagination: [20, 2], restoreAttempts: attempts.length, committedRevisionsAfterRetry: 23, identicalRetryIntent: true, savedFeedbackPreserved: true, automaticSubmissions: 0, firstVersionVisible, bounds };
  } },
  { name: "queued-working-answer-draft", async run({ host, instance, screenshot }) {
    let acknowledge;
    const bound = host(() => new Promise(resolve => { acknowledge = resolve; }));
    const view = await instance(bound, "meeting", "Møteavtale · første versjon");
    await openAdjust(view.ui);
    assert(await view.workshop.locator(".source-editor-entry").isHidden(), "Legacy sketches must not gain an empty source-editor entry.");
    await view.workshop.getByLabel("Mengde forklaring", { exact: true }).selectOption("full");
    await view.workshop.getByLabel("Merknad", { exact: true }).fill("Behold forklaringen om gjeldende avtale.");
    assert.equal(bound.calls.length, 0);
    await view.workshop.getByRole("button", { name: "Behold dette", exact: true }).click();
    await view.ui.locator(".panel").waitFor();
    await view.note("Gjør tidspunktet lettere å finne."); await view.save();
    assert.equal(bound.calls.length, 0, "Saving and keeping are local until explicit Send.");
    await view.send(2); await until(() => bound.calls.length === 1, "one host notification");
    await view.round(1, "sending");
    const batch = await view.action("read_submission", { submission: 1 });
    assert(batch.items.some(item => item.type === "comment")); assert(batch.items.some(item => item.type === "decision"));
    assert.equal(bound.calls[0].identity.instanceId, "meeting"); assert.equal(bound.calls[0].identity.submission, 1);
    assert.equal(bound.calls[0].prompt.includes("Gjør tidspunktet lettere"), false, "The message carries a bounded reference; the action reads actual feedback.");
    acknowledge("accepted-round-1"); await view.round(1, "queued");
    assert.equal((await view.snapshot()).canvas.rounds[0].review, "unread", "Queue acknowledgement must not claim processing.");
    await view.action("review_submission", { submission: 1, status: "working", reply: "" }); await view.round(1, "working");
    await view.note("Usendt innspill om overskriften.");
    await view.ui.getByRole("button", { name: "Foreslå ny tekst", exact: true }).click();
    await view.ui.getByLabel("Ny tekst", { exact: true }).fill("Din neste samtale");
    await view.publish("Møteavtale · tydeligere tidspunkt");
    await view.ui.locator('[data-action="refresh"]').waitFor();
    assert(await view.ui.locator('[data-action="refresh"]').isDisabled());
    assert.equal(await view.ui.getByLabel("Hva vil du endre?", { exact: true }).inputValue(), "Usendt innspill om overskriften.");
    assert.equal(await view.ui.getByLabel("Ny tekst", { exact: true }).inputValue(), "Din neste samtale");
    assert(await view.frame.getByRole("heading", { name: "Møteavtale · første versjon", exact: true }).isVisible());
    await view.action("review_submission", { submission: 1, status: "answered", reply: "Tidspunktet er fremhevet i den nye versjonen. Det beholdte innholdet er videreført." });
    await view.ui.getByRole("button", { name: "Legg utkast til side", exact: true }).click(); await view.openFeedback();
    const answered = await view.round(1, "answered"); await answered.locator("summary").click();
    await answered.getByText("Tidspunktet er fremhevet i den nye versjonen. Det beholdte innholdet er videreført.", { exact: true }).waitFor();
    assert.equal((await view.snapshot()).comments[0].status, "open", "An answered round must not silently resolve its comments.");
    await screenshot(view, "answer-with-protected-draft");
    await view.closeFeedback(); await view.ui.getByRole("button", { name: "Fortsett utkast", exact: true }).click();
    assert.equal(await view.ui.getByLabel("Ny tekst", { exact: true }).inputValue(), "Din neste samtale");
    const explicitRefresh = await view.ui.getByRole("button", { name: "Forkast", exact: true }).evaluate(button => {
      const root = button.getRootNode(); button.click();
      const refresh = root.querySelector('[data-action="refresh"]');
      if (!refresh.hidden && !refresh.disabled) { refresh.click(); return true; }
      // Once all local drafts are explicitly discarded, an automatic refresh is
      // also permitted. Do not race its replacement with a hidden old button.
      return false;
    });
    await view.frame.getByRole("heading", { name: "Møteavtale · tydeligere tidspunkt", exact: true }).waitFor();
    assert.equal(bound.calls.length, 1); await view.openFeedback(); await view.round(1, "answered");
    await screenshot(view, "revised-sketch");
    return { localSaveBeforeSend: true, queueDistinctFromWork: true, draftBothFieldsPreserved: true, answerDoesNotResolveComments: true, revisedScreenOpenedAfterDraftDiscard: true, explicitRefresh };
  } },
  { name: "unknown-blocks-new-send", async run({ host, instance, screenshot }) {
    let lateAcknowledge;
    const bound = host((_request, count) => count === 1 ? new Promise(resolve => { lateAcknowledge = resolve; }) : Promise.reject(new Error("No receipt")), 160);
    const view = await instance(bound, "meeting", "Møteavtale · leveringsprøve");
    await view.note("Forklar om jeg kan endre tiden."); await view.save(); await view.send(1); await view.round(1, "unknown");
    await view.note("Behold formuleringen om gjeldende avtale."); await view.save();
    assert.equal((await view.snapshot()).comments.filter(item => item.submission === 0).length, 1, "A delivery uncertainty must still allow local saving.");
    assert(await view.ui.getByRole("button", { name: "Send 1 innspill", exact: true }).isDisabled());
    assert.equal(await view.ui.getByRole("button", { name: /prøv.*sending|send.*nytt|send på nytt/i }).count(), 0, "There is no resend shortcut for an uncertain model message.");
    await screenshot(view, "uncertain-with-saved-note");
    await pause(650); assert.equal(bound.calls.length, 1, "Timeouts do not automatically retry.");
    lateAcknowledge("late-accepted-round-1"); await view.round(1, "queued");
    await until(() => view.ui.locator(".send").isEnabled(), "trusted receipt releases the next explicit send");
    assert.equal(bound.calls.length, 1); await view.send(1); await view.round(2, "unknown");
    await view.action("review_submission", { submission: 2, status: "working", reply: "" }); await view.round(2, "working");
    assert.equal((await view.snapshot()).canvas.rounds[1].delivery, "unknown", "Working is an explicit review state, not a fabricated SDK receipt.");
    await view.action("review_submission", { submission: 2, status: "answered", reply: "Jeg har lest den andre runden og beholdt formuleringen." }); await view.round(2, "answered");
    await screenshot(view, "explicit-answer");
    return { unknownBlocksOnlySending: true, unknownAutomaticRetries: 0, lateReceiptRecovers: true, trustedReviewTakesDisplayPriority: true };
  } },
  { name: "bound-sessions-instances-and-reopen", async run({ host, instance, screenshot }) {
    const first = host(), second = host();
    const a = await instance(first, "same-instance", "Samtale A · møte"), sibling = await instance(first, "another-instance", "Samtale A · alternativ");
    const b = await instance(second, "same-instance", "Samtale B · møte");
    await a.note("Presiser stedet i samtale A."); await a.save(); await a.send(1); await a.round(1, "queued");
    assert.equal(first.calls.length, 1); assert.equal(second.calls.length, 0); assert.equal((await sibling.snapshot()).submission, 0);
    await b.note("Presiser tiden i samtale B."); await b.save(); await b.send(1); await b.round(1, "queued");
    await sibling.note("Behold det andre konseptet."); await sibling.save(); await sibling.send(1); await sibling.round(1, "queued");
    assert.deepEqual(first.calls.map(item => item.identity.instanceId), ["same-instance", "another-instance"]);
    assert.deepEqual(second.calls.map(item => item.identity.instanceId), ["same-instance"]);
    await assert.rejects(a.action("read_state", {}, { sessionId: second.sessionId }), error => error.status === 403);
    await a.action("review_submission", { submission: 1, status: "working", reply: "" }); await a.round(1, "working");
    await a.note("Ulagret utkast som skal forsvinne ved lukking.");
    const previousURL = a.url(); await a.close();
    let oldTransportRejected = false;
    try { oldTransportRejected = !(await fetch(previousURL, { signal: AbortSignal.timeout(1500) })).ok; } catch { oldTransportRejected = true; }
    assert(oldTransportRejected, "Panel close revokes the old transport.");
    const reopened = await a.reopen(), stale = new URL(reopened.current.url); stale.search = new URL(reopened.previous.url).search;
    assert.equal((await fetch(stale)).status, 403, "The old capability must not authorize the fresh listener.");
    assert.equal((await a.snapshot()).submission, 1); assert.equal((await a.snapshot()).comments.length, 1);
    assert.equal(await a.ui.getByRole("button", { name: "Fortsett utkast", exact: true }).isVisible(), false, "An unsaved editor is not falsely promised to survive closing.");
    await a.openFeedback(); await a.round(1, "working");
    await a.action("review_submission", { submission: 1, status: "answered", reply: "Stedet er avklart i samtale A." }); await a.round(1, "answered");
    assert.equal((await b.snapshot()).canvas.rounds[0].review, "unread"); assert.equal((await sibling.snapshot()).canvas.rounds[0].review, "unread");
    assert.equal(first.calls.length + second.calls.length, 3, "Reopen and reply do not enqueue another request.");
    await screenshot(a, "reopened-working-round"); await screenshot(b, "separate-conversation");
    return { conversations: 2, instances: 3, exactRouting: true, closeWhileWorkingRetainsRound: true, reopenedCapabilityRotated: true, oldCapabilityRejected: true, editorDraftLostAsDescribed: true, reopenEnqueuesNothing: true };
  } },
  { name: "round-history-keyboard-320", viewport: { width: 320, height: 568 }, async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "meeting", "Møteavtale · flere runder");
    for (let number = 1; number <= 4; number += 1) { await view.note(`Runde ${number}: Gjør forklaringen tydeligere.`); await view.save(); await view.send(1); await view.round(number, "queued"); }
    assert.equal(await view.ui.locator(".canvas-recent > article").count(), 3); assert.equal(await view.ui.locator(".canvas-older > article").count(), 1);
    const history = view.ui.locator(".canvas-history"), summary = history.locator(":scope > summary");
    assert.equal(await history.getAttribute("open"), null); await summary.focus(); await view.page.keyboard.press("Enter");
    assert.notEqual(await history.getAttribute("open"), null);
    const longReply = "<strong>Avklart</strong>\n" + "Tidspunkt, sted og forklaring er gjennomgått. ".repeat(28);
    await view.action("review_submission", { submission: 1, status: "answered", reply: longReply });
    const old = await view.round(1, "answered"), answerSummary = old.locator("summary"); await answerSummary.focus(); await view.page.keyboard.press("Enter");
    assert.equal(await old.locator(".canvas-answer p").textContent(), longReply); assert.equal(await old.locator(".canvas-answer strong").count(), 0, "Reply text must not become markup.");
    await view.ui.locator('.sr[role="status"]').evaluate(node => { window.statusWrites = 0; new MutationObserver(() => { window.statusWrites += 1; }).observe(node, { childList: true, characterData: true, subtree: true }); });
    await pause(180); // Allow the announcement associated with opening the reply to settle.
    await view.ui.locator('.sr[role="status"]').evaluate(() => { window.statusWrites = 0; });
    await pause(2200);
    assert.equal(await view.ui.locator('.sr[role="status"]').evaluate(() => window.statusWrites), 0, "Unchanged polls must not repeatedly announce round status.");
    assert(await answerSummary.evaluate(node => node.getRootNode().activeElement === node));
    await view.action("review_submission", { submission: 4, status: "working", reply: "" }); await view.round(4, "working");
    assert(await answerSummary.evaluate(node => node.getRootNode().activeElement === node), "A different round's update must preserve keyboard focus.");
    assert.notEqual(await old.locator("details").getAttribute("open"), null);
    const geometry = await view.ui.locator(".panel").evaluate(node => {
      const bounds = node.getBoundingClientRect(), list = node.querySelector(".list");
      return { width: bounds.width, left: bounds.left, right: bounds.right, viewport: innerWidth, listHeight: list.clientHeight, listOverflow: list.scrollWidth > list.clientWidth + 1 };
    });
    assert(geometry.left >= 0 && geometry.right <= geometry.viewport + 1); assert(geometry.listHeight >= 80, `The reply list needs reading space: ${JSON.stringify(geometry)}`); assert.equal(geometry.listOverflow, false);
    await screenshot(view, "older-reply");
    return { visibleRecentRounds: 3, collapsedOlderRounds: 1, keyboardReplyReachable: true, statusOnlyChangePreservesFocus: true, unchangedStatusAnnouncements: 0, geometry };
  } },
  { name: "invalid-frame-cannot-submit", async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "meeting", "Møteavtale · avgrenset innspill");
    await view.note("Et legitimt lokalt innspill."); await view.save();
    const before = await view.snapshot(), current = await view.action("read_state");
    const forged = { channel: "grillmester-visual-companion", version: 1, action: "comments-submit", requestId: 700, payload: { revision: before.revision, screen: current.screen } };
    await view.page.evaluate(data => {
      window.postMessage(data, "*");
      const unrelated = document.createElement("iframe"); unrelated.id = "unrelated-frame"; unrelated.srcdoc = "<p>Uavhengig ramme</p>"; document.body.appendChild(unrelated);
    }, forged);
    await view.page.frameLocator("#unrelated-frame").locator("p").evaluate((_node, data) => parent.postMessage(data, "*"), forged);
    await pause(1300);
    assert.equal((await view.snapshot()).submission, 0); assert.equal(bound.calls.length, 0);
    await view.page.locator("#unrelated-frame").evaluate(node => node.remove());
    await view.send(1); await view.round(1, "queued"); assert.equal(bound.calls.length, 1);
    await screenshot(view, "explicit-send-only");
    return { invalidTopLevelMessageRejected: true, unrelatedFrameMessageRejected: true, explicitSendStillWorks: true };
  } },
];
(async () => {
  const { createCanvasAdapter } = await import(pathToFileURL(path.resolve(__dirname, "../plugin/extensions/visual-companion/adapter.mjs")).href);
  const selected = options.has("--case") ? cases.filter(item => item.name === options.get("--case")) : cases;
  if (!selected.length) throw new Error(`Unknown case. Available: ${cases.map(item => item.name).join(", ")}`);
  const browser = await chromium.launch({ channel: options.get("--browser-channel") || "chrome", headless: true });
  const results = [];
  try { for (const testcase of selected) { const result = await runCase(browser, createCanvasAdapter, testcase); results.push(result); console.log(JSON.stringify(result)); } }
  finally { await browser.close(); }
  const report = { scope: "Actual headless Chrome, Aksel SSR and full canvas adapter/server; simulated host, no model or native application calls", akselVersion, passed: results.filter(item => item.passed).length, total: results.length, results };
  if (evidence) fs.writeFileSync(path.join(evidence, "canvas-results.json"), JSON.stringify(report, null, 2));
  if (report.passed !== report.total) process.exitCode = 1;
})().catch(error => { console.error(error.message.replace(/http:\/\/127\.0\.0\.1:[^\s)]+/g, "[local preview]")); process.exitCode = 1; });
