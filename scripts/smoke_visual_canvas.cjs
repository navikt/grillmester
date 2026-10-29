#!/usr/bin/env node
"use strict";

// Actual browser/server exercise with a simulated host. Never contacts a model.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { createRequire } = require("node:module");
async function openTools(ui) {
  const menu = ui.locator(".more-tools");
  if (!(await menu.evaluate(node => node.open))) await menu.locator(":scope > summary").click();
}
async function openAdjust(ui) {
  await openTools(ui);
  await ui.getByRole("button", { name: "Juster visning", exact: true }).click();
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
  const workshop = ui.getByRole("region", { name: "Juster visningen", exact: true });
  const closeWorkshop = async () => { const close = workshop.getByRole("button", { name: "Lukk justeringer", exact: true }); if (await close.isVisible()) await close.click(); };
  return { page, frame, ui, workshop, closeFeedback, closeWorkshop,
    async openFeedback() { await closeWorkshop(); if (!(await ui.locator(".panel").isVisible())) await ui.locator('[data-action="panel"]').click(); },
    async note(value) { await closeFeedback(); await closeWorkshop(); if (await ui.locator('[data-action="change-ask"]').getAttribute("aria-pressed") !== "true") await ui.locator('[data-action="comment"]').click(); await frame.locator("h1").click(); await ui.getByLabel("Hva vil du endre?", { exact: true }).fill(value); },
    async save() { await ui.getByRole("button", { name: "Legg til flere", exact: true }).click(); await ui.locator(".composer").waitFor({ state: "hidden" }); await ui.locator('[data-action="panel"]').click(); await ui.locator(".panel").waitFor(); },
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
      const item = { ...view, ctx, action, publish, snapshot, send, reopen, host: bound, close: () => bound.adapter.canvas.onClose(ctx), url: () => opened.url, title: () => opened.title, retired: false };
      item.retire = async () => { item.retired = true; await context.close(); await bound.adapter.close(); };
      views.push(item); return item;
    };
    const screenshot = async (view, suffix) => { if (evidence) { await view.page.locator("#vc-status").filter({ hasText: /^Tilkoblet$/ }).waitFor(); await view.page.screenshot({ path: path.join(evidence, `${testcase.name}-${suffix}.png`), animations: "disabled" }); } };
    const openInspectionPage = async (url, viewport) => {
      const origin = new URL(url).origin;
      allowedOrigins.add(origin);
      const context = await browser.newContext({ viewport, reducedMotion: "reduce" }); contexts.push(context);
      const page = await context.newPage(); page.setDefaultTimeout(12000);
      page.on("pageerror", error => errors.push(error.message));
      page.on("requestfinished", request => { if (!/^(data|blob):/.test(request.url()) && new URL(request.url()).origin !== origin) external.push(new URL(request.url()).origin); });
      await page.goto(url);
      return page;
    };
    const measured = await testcase.run({ host, instance, screenshot, openInspectionPage });
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
  const edit = view.ui.getByRole("button", { name: "Rediger", exact: true });
  await until(async () => {
    await openTools(view.ui);
    return await edit.isVisible() && await edit.isEnabled();
  }, "Rediger is available in Verktøy");
  await edit.click();
  const editor = view.ui.getByRole("region", { name: "Rediger skissen", exact: true });
  await editor.getByLabel("Overskrift", { exact: true }).waitFor();
  await until(async () => await editor.getByLabel("Overskrift", { exact: true }).isEnabled(), "source editor ready");
  return editor;
}
const cases = [
  { name: "compact-tools-keyboard", viewport: { width: 320, height: 568 }, async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "compact-tools", "Din avtale", { fixture: editableSketch, openInput: { workspacePath: "design/compact-tools", create: true, title: "Kompakte verktøy" } });
    const summary = view.ui.locator(".more-tools > summary"), menu = view.ui.locator(".more-tools");
    assert.deepEqual(await view.ui.locator(".toolbar button").evaluateAll(buttons => buttons.filter(button => button.getClientRects().length).map(button => button.dataset.action)), ["comment", "panel"]);
    await summary.focus(); await view.page.keyboard.press("Enter");
    const bounds = await view.ui.locator(".more-items").evaluate(node => { const rect = node.getBoundingClientRect(); return { left: rect.left, right: rect.right, bottom: rect.bottom, width: innerWidth, height: innerHeight }; });
    assert(bounds.left >= 0 && bounds.right <= bounds.width && bounds.bottom <= bounds.height, JSON.stringify(bounds));
    await screenshot(view, "mobile-tools");
    await view.page.keyboard.press("Tab"); await view.page.keyboard.press("Tab"); await view.page.keyboard.press("Enter");
    await view.ui.getByRole("region", { name: "Rediger skissen", exact: true }).waitFor();
    await view.page.keyboard.press("Escape");
    assert(await summary.evaluate(node => node.getRootNode().activeElement === node));
    await view.page.keyboard.press("Enter"); await view.page.keyboard.press("Tab"); await view.page.keyboard.press("Enter");
    await view.ui.getByRole("region", { name: "Versjoner og lagring", exact: true }).waitFor();
    await view.page.keyboard.press("Escape");
    assert(await summary.evaluate(node => node.getRootNode().activeElement === node));
    await view.page.keyboard.press("Enter"); await view.page.keyboard.press("Tab"); await view.page.keyboard.press("Tab"); await view.page.keyboard.press("Tab"); await view.page.keyboard.press("Enter");
    await view.workshop.waitFor(); await view.page.keyboard.press("Escape");
    assert(await summary.evaluate(node => node.getRootNode().activeElement === node));
    await view.page.keyboard.press("Enter"); await view.page.keyboard.press("Escape");
    assert.equal(await menu.getAttribute("open"), null); assert(await summary.evaluate(node => node.getRootNode().activeElement === node));
    await view.page.setViewportSize({ width: 1280, height: 900 }); await screenshot(view, "desktop-default");
    assert.equal(bound.calls.length, 0); assert.equal((await view.snapshot()).submission, 0);
    return { defaultPrimaryButtons: 2, secondaryToolsInOneMenu: 3, keyboardOpenAndFocusReturn: true, menuBounds: bounds, automaticSubmissions: 0 };
  } },
  { name: "visible-variant-tabs", viewport: { width: 390, height: 844 }, async run({ host, instance, screenshot }) {
    const variants = [{ key: "short", label: "Kort" }, { key: "steps", label: "Trinnvis" }, { key: "all", label: "Samlet" }, { key: "detail", label: "Detaljert" }];
    const fixture = title => ({ html: `<style>[data-vc-variants]{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}</style><main><h1>${title}</h1><div data-vc-variants>${variants.map(variant => `<section data-vc-variant="${variant.key}"><article data-vc-key="card"><h2>${variant.label} variant</h2><label>Notat ${variant.label}<input aria-label="Notat ${variant.label}"></label></article></section>`).join("")}</div><label>Prøvefelt<input id="practice" aria-label="Prøvefelt"></label></main>`,
      design: { version: 1, variants, targets: variants.map(variant => ({ key: "card", variant: variant.key, label: `Kort ${variant.label}`, controls: [] })) } });
    const bound = host(), view = await instance(bound, "variant-tabs", "Fire forslag", { fixture });
    const tabs = view.frame.getByRole("tablist", { name: "Velg skissevariant", exact: true });
    await tabs.waitFor(); assert.equal(await tabs.getByRole("tab").count(), 4);
    const container = await view.frame.locator("[data-vc-variants]").boundingBox(), single = await view.frame.getByRole("tabpanel", { name: "Kort", exact: true }).boundingBox();
    assert(Math.abs(container.width - single.width) <= 1, "A single variant must use the full authored comparison container.");
    await view.frame.getByLabel("Notat Kort", { exact: true }).fill("LOCAL_VARIANT_VALUE");
    const first = tabs.getByRole("tab", { name: "Kort", exact: true });
    await first.focus(); await view.page.keyboard.press("ArrowRight");
    assert.equal(await tabs.getByRole("tab", { name: "Trinnvis", exact: true }).getAttribute("aria-selected"), "true");
    assert(await view.frame.getByRole("tabpanel", { name: "Trinnvis", exact: true }).isVisible());
    assert(await view.frame.getByRole("heading", { name: "Kort variant", exact: true }).isHidden());
    await view.page.keyboard.press("End"); assert(await view.frame.getByRole("tabpanel", { name: "Detaljert", exact: true }).isVisible());
    await view.page.keyboard.press("Home"); assert.equal(await view.frame.getByLabel("Notat Kort", { exact: true }).inputValue(), "LOCAL_VARIANT_VALUE");
    assert.equal((await view.snapshot()).comments.length, 0); assert.equal(bound.calls.length, 0);
    await screenshot(view, "four-named-tabs");
    await view.ui.getByRole("button", { name: "Gi innspill", exact: true }).click();
    await view.frame.getByRole("heading", { name: "Kort variant", exact: true }).click();
    await view.ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Behold den korte forklaringen.");
    assert(await first.isDisabled(), "An unfinished target cannot silently move to another variant.");
    await view.ui.getByRole("button", { name: "Legg utkast til side", exact: true }).click();
    await tabs.getByRole("tab", { name: "Detaljert", exact: true }).click();
    await view.ui.getByRole("button", { name: "Fortsett utkast", exact: true }).click();
    assert.equal(await first.getAttribute("aria-selected"), "true", "Resuming a parked draft must show its original variant.");
    assert(await first.isDisabled(), "A resumed draft must immediately expose its protected variant state.");
    assert.equal(await view.ui.getByLabel("Hva vil du endre?", { exact: true }).inputValue(), "Behold den korte forklaringen.");
    await view.save(); await view.closeFeedback();
    await tabs.getByRole("tab", { name: "Trinnvis", exact: true }).click();
    const saved = (await view.snapshot()).comments[0];
    assert.equal(await view.frame.locator(saved.anchor.path).evaluate(node => node.closest("[data-vc-variant]").dataset.vcVariant), "short");
    await view.page.setViewportSize({ width: 1280, height: 900 });
    await view.frame.getByRole("button", { name: "Sammenlign", exact: true }).click();
    assert(await view.frame.getByRole("heading", { name: "Kort variant", exact: true }).isVisible());
    assert(await view.frame.getByRole("heading", { name: "Trinnvis variant", exact: true }).isVisible());
    await screenshot(view, "comparison-kept");
    await view.frame.getByRole("button", { name: "Vis én variant", exact: true }).click();
    assert(await tabs.isVisible()); assert(await view.frame.getByRole("tabpanel", { name: "Trinnvis", exact: true }).isVisible());
    assert.equal(bound.calls.length, 0); assert.equal((await view.snapshot()).submission, 0);
    assert(!JSON.stringify(await view.snapshot()).includes("LOCAL_VARIANT_VALUE"));
    return { namedTabs: 4, keyboardNavigation: true, fullWidthSingleVariant: true, parkedDraftRestoresVariant: true, variantFormPreserved: true, savedTargetRetained: true, comparisonRetained: true, automaticSubmissions: 0 };
  } },
  { name: "read-only-inspection-render-and-revocation", viewport: { width: 800, height: 700 }, async run({ host, instance, screenshot, openInspectionPage }) {
    const fixture = title => {
      const value = sketch(title);
      value.html = value.html.replace(/(<[^>]*data-vc-key="meeting"[^>]*>)/,
        '$1<button type="button" data-vc-control="detail" data-vc-value="full">Vis mer</button><button type="button" data-vc-control="detail" data-vc-value="short">Vis mindre</button>');
      return value;
    };
    const bound = host(), view = await instance(bound, "inspection", "Forbered avtalen", {
      fixture, openInput: { workspacePath: "design/inspection", create: true, title: "Visuell kontroll" },
    });
    const before = await view.action("read_state"), feedbackBefore = await view.snapshot();
    const sourceBefore = await view.action("read_revision", { revisionId: 1, part: "html" });
    await view.frame.getByRole("button", { name: "Vis mer", exact: true }).click();
    await view.frame.locator(".canvas-extra").waitFor({ state: "visible" });
    const viewport = await view.frame.locator("html").evaluate(() => ({ width: innerWidth, height: innerHeight }));
    const geometry = async root => root.locator(".canvas-meeting").evaluate(node => {
      const bounds = node.getBoundingClientRect(), style = getComputedStyle(node);
      const heading = node.querySelector("h2"), headingStyle = getComputedStyle(heading);
      return { width: bounds.width, padding: style.padding, border: style.borderTopWidth,
        headingFont: headingStyle.fontFamily, headingSize: headingStyle.fontSize };
    });
    const normalGeometry = await geometry(view.frame);
    const inspection = await view.action("open_inspection", { expectedScreen: before.screen });
    assert.equal(inspection.screen, before.screen);
    assert.equal(typeof inspection.inspectionId, "string");
    assert.notEqual(new URL(inspection.url).origin, new URL(view.url()).origin, "Inspection must have its own read-only origin.");
    const preview = await openInspectionPage(inspection.url, viewport);
    await preview.getByRole("heading", { name: "Forbered avtalen", exact: true }).waitFor();
    assert.equal(await preview.locator("[data-visual-feedback]").count(), 0, "Inspection does not mount the feedback toolbar.");
    assert.equal(await preview.getByRole("button", { name: "Gi innspill", exact: true }).count(), 0);
    assert(await preview.locator(".canvas-extra").isHidden(), "Inspection starts from declared initial state, not the designer's local view.");
    assert.equal(await preview.getByLabel("Prøvefelt", { exact: true }).inputValue(), "", "Live form values must not be copied into inspection.");
    const inspectedGeometry = await geometry(preview);
    const initialImage = await preview.screenshot({ animations: "disabled", ...(evidence ? { path: path.join(evidence, "read-only-inspection-initial.png") } : {}) });
    assert.deepEqual(inspectedGeometry, normalGeometry, "The same Aksel CSS and content width must render in the inspection view.");
    assert.equal(initialImage.subarray(0, 8).toString("hex"), "89504e470d0a1a0a");
    await preview.getByRole("button", { name: "Vis mer", exact: true }).click();
    await preview.locator(".canvas-extra").waitFor({ state: "visible" });
    const changedImage = await preview.screenshot({ animations: "disabled", ...(evidence ? { path: path.join(evidence, "read-only-inspection-expanded.png") } : {}) });
    assert(!initialImage.equals(changedImage), "A declared interaction visibly changes the rendered PNG.");
    await preview.getByRole("button", { name: "Vis mindre", exact: true }).focus();
    await preview.keyboard.press("Enter");
    await preview.locator(".canvas-extra").waitFor({ state: "hidden" });
    assert(await view.frame.locator(".canvas-extra").isVisible(), "Inspection does not change the open workshop's local state.");
    assert.equal(await view.frame.getByLabel("Prøvefelt", { exact: true }).inputValue(), "PRIVATE_PRACTICE_VALUE");
    const rejectedWrite = await fetch(inspection.url, { method: "POST", body: "{}", signal: AbortSignal.timeout(3000) });
    assert([404, 405].includes(rejectedWrite.status), "The inspection capability must reject writes.");
    assert.deepEqual(await view.snapshot(), feedbackBefore, "Inspection and interactions do not write feedback or versions.");
    assert.deepEqual(await view.action("read_revision", { revisionId: 1, part: "html" }), sourceBefore);
    assert.equal(bound.calls.length, 0, "Inspection never queues a message.");
    const assertRevoked = async url => {
      let response;
      try { response = await fetch(url, { signal: AbortSignal.timeout(3000) }); }
      catch (error) { assert(error instanceof TypeError, "A revoked listener may refuse the connection."); return; }
      assert([403, 404, 410].includes(response.status), `Revoked inspection returned ${response.status}.`);
    };
    await view.action("close_inspection", { inspectionId: inspection.inspectionId });
    await assertRevoked(inspection.url);
    const stale = await view.action("open_inspection", { expectedScreen: before.screen });
    assert.equal((await fetch(stale.url, { signal: AbortSignal.timeout(3000) })).status, 200);
    await view.publish("Forbered neste avtale");
    await assertRevoked(stale.url);
    await view.ui.getByRole("button", { name: "Vis oppdatert forslag", exact: true }).click();
    await view.frame.getByRole("heading", { name: "Forbered neste avtale", exact: true }).waitFor();
    await screenshot(view, "workshop-retained");
    assert.equal((await view.snapshot()).comments.length, 0); assert.equal(bound.calls.length, 0);
    assert.deepEqual(await view.action("read_revision", { revisionId: 1, part: "html" }), sourceBefore);
    await preview.close();
    return { readOnlyInspection: true, declaredInitialState: true, nativeFormValuesExcluded: true,
      sameContentGeometry: true, pointerAndKeyboardInteraction: true, actualPngChanged: true,
      feedbackUnchanged: true, originalSourceUnchanged: true, closeRevokesUrl: true, publicationRevokesUrl: true,
      inspectionImageBytes: changedImage.length, automaticSubmissions: 0 };
  } },
  { name: "direct-send-keyboard-and-collection", viewport: { width: 390, height: 844 }, async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "direct-send", "Avtale · direkte innspill");
    await view.note("Gjør tidspunktet tydeligere.");
    assert.equal(await view.ui.locator('[data-action="comment"]').getAttribute("aria-pressed"), "false", "Choosing one target leaves pointer interception.");
    assert(await view.ui.getByRole("button", { name: "Send innspill", exact: true }).isVisible());
    await screenshot(view, "single-composer");
    await view.page.keyboard.press("Control+Enter");
    await until(async () => (await view.snapshot()).submission === 1, "keyboard sends one draft directly");
    await view.round(1, "queued");
    assert.equal(bound.calls.length, 1);
    assert.equal((await view.snapshot()).comments.length, 1);
    await view.closeFeedback();
    assert.equal(await view.frame.getByLabel("Prøvefelt", { exact: true }).inputValue(), "PRIVATE_PRACTICE_VALUE");
    await view.frame.getByLabel("Prøvefelt", { exact: true }).focus();
    await view.page.keyboard.press("End"); await view.page.keyboard.type("!");
    assert.equal(await view.frame.getByLabel("Prøvefelt", { exact: true }).inputValue(), "PRIVATE_PRACTICE_VALUE!");
    await view.note("Behold kontaktinformasjonen."); await view.save();
    assert.equal(bound.calls.length, 1, "Collecting must never enqueue work.");
    await view.note("Gi knappen en tydeligere tekst.");
    const sendAll = view.ui.getByRole("button", { name: "Send alle 2 innspill", exact: true });
    await view.ui.locator(".compose-batch summary").click();
    assert(await view.ui.locator(".compose-batch li").isVisible());
    assert.equal(await view.ui.locator(".compose-batch-text").textContent(), "Behold kontaktinformasjonen.");
    await screenshot(view, "explicit-collection");
    await sendAll.click();
    await until(async () => (await view.snapshot()).submission === 2, "exact collection sent directly");
    const result = await view.snapshot();
    assert.deepEqual(result.comments.filter(item => item.submission === 2).map(item => item.text), ["Behold kontaktinformasjonen.", "Gi knappen en tydeligere tekst."]);
    assert.equal(result.comments.filter(item => item.submission === 1).length, 1);
    await view.round(2, "queued");
    return { directKeyboardSend: true, collectedCount: 2, ordinaryFormPreserved: true };
  } },
  { name: "direct-send-variant-labels", viewport: { width: 320, height: 568 }, async run({ host, instance, screenshot }) {
    const variants = [{ key: "list", label: "Prioritert liste" }, { key: "board", label: "Arbeidsbrett" }];
    const fixture = title => ({ html: `<main><h1>${title}</h1><div data-vc-variants>${variants.map(variant => `<section data-vc-variant="${variant.key}"><article data-vc-key="summary"><h2>Oppsummering</h2><p>Oppgaver og neste steg.</p></article></section>`).join("")}</div><label>Prøvefelt<input aria-label="Prøvefelt"></label></main>`,
      design: { version: 1, variants, targets: variants.map(variant => ({ key: "summary", variant: variant.key, label: "Oppsummering", controls: [] })) } });
    const bound = host(), view = await instance(bound, "batch-labels", "To retninger", { fixture });
    const text = "Gjør neste steg tydeligere.";
    for (const variant of variants) {
      await view.frame.getByRole("tab", { name: variant.label, exact: true }).click();
      await view.ui.getByRole("button", { name: "Gi innspill", exact: true }).click();
      await view.frame.getByRole("heading", { name: "Oppsummering", exact: true }).click();
      await view.ui.getByLabel("Hva vil du endre?", { exact: true }).fill(text);
      await view.save(); await view.closeFeedback();
    }
    const before = await view.snapshot();
    assert.equal(before.comments.length, 2); assert.equal(bound.calls.length, 0);
    assert(before.comments.every(item => !item.context), "The label must also work for declared parts without adjustable controls.");
    await view.note("Vurder begge retningene samlet.");
    const batch = view.ui.locator(".compose-batch");
    assert.equal(await batch.evaluate(node => node.open), false, "A fresh composer keeps the collected notes collapsed.");
    const primaryGeometry = await view.ui.locator('[data-action="save"]').evaluate(node => {
      const button = node.getBoundingClientRect(), clip = node.closest(".composer").getBoundingClientRect();
      return { top: button.top, bottom: button.bottom, clipTop: clip.top, clipBottom: clip.bottom, visible: button.top >= clip.top && button.bottom <= clip.bottom };
    });
    assert(primaryGeometry.visible, JSON.stringify(primaryGeometry));
    await screenshot(view, "collapsed-primary-visible-320");
    await batch.locator("summary").click();
    await view.page.waitForResponse(response => /\/comments\?/.test(response.url()) && response.request().method() === "GET");
    assert.equal(await batch.evaluate(node => node.open), true, "Polling must preserve the participant's expanded collection.");
    const labels = view.ui.locator(".compose-batch-target");
    assert.deepEqual(await labels.allTextContents(), ["Oppsummering · Prioritert liste", "Oppsummering · Arbeidsbrett"]);
    assert.deepEqual(await view.ui.locator(".compose-batch-text").allTextContents(), [text, text]);
    await batch.scrollIntoViewIfNeeded();
    await batch.locator("li").last().evaluate(node => node.scrollIntoView({ block: "nearest" }));
    const geometry = await batch.evaluate(node => {
      const composer = node.closest(".composer"), clip = composer.getBoundingClientRect();
      const actions = composer.querySelector(".compose-actions").getBoundingClientRect();
      const rows = [...node.querySelectorAll("li")].map(row => { const rect = row.getBoundingClientRect(); return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom }; });
      return { viewport: innerWidth, clip: { left: clip.left, right: clip.right, top: clip.top, bottom: Math.min(clip.bottom, actions.top) }, rows, horizontalOverflow: composer.scrollWidth > composer.clientWidth + 1 };
    });
    assert(!geometry.horizontalOverflow);
    assert(geometry.rows.every(row => row.left >= geometry.clip.left && row.right <= geometry.clip.right && row.top >= geometry.clip.top && row.bottom <= geometry.clip.bottom), JSON.stringify(geometry));
    await screenshot(view, "same-notes-distinct-targets-320");
    await view.ui.getByRole("button", { name: "Send alle 3 innspill", exact: true }).click();
    await view.round(1, "queued");
    const sent = await view.snapshot();
    assert.equal(sent.comments.length, 3); assert.equal(bound.calls.length, 1);
    assert.deepEqual(sent.comments.slice(0, 2).map(item => item.id), before.comments.map(item => item.id));
    assert(sent.comments.every(item => item.submission === 1));
    return { identicalNotes: 2, defaultDetailsCollapsed: true, primaryGeometry, distinctHumanLabels: true, exactCommentCount: 3, geometry };
  } },
  { name: "direct-send-lost-response", async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "direct-retry", "Avtale · samme sending");
    await view.note("Et lagret innspill."); await view.save();
    await view.note("Dette innspillet sendes med det første.");
    const requests = [];
    await view.page.route(/\/comments\/submit-draft(?:\?|$)/, async route => {
      requests.push({ body: route.request().postData(), mutation: route.request().headers()["x-feedback-mutation"] });
      const response = await route.fetch();
      if (requests.length === 1) await route.abort("failed"); else await route.fulfill({ response });
    });
    await view.ui.getByRole("button", { name: "Send alle 2 innspill", exact: true }).click();
    const retry = view.ui.getByRole("button", { name: "Prøv samme sending igjen", exact: true });
    await retry.waitFor();
    assert.equal(await view.ui.getByLabel("Hva vil du endre?", { exact: true }).getAttribute("readonly"), "");
    assert(await view.ui.getByRole("button", { name: "Legg til flere", exact: true }).isDisabled());
    assert(await view.ui.getByRole("button", { name: "Forkast", exact: true }).isDisabled());
    await screenshot(view, "preserved-intent");
    await retry.click();
    await view.ui.locator(".composer").waitFor({ state: "hidden" });
    await view.round(1, "queued");
    assert.equal(requests.length, 2); assert.deepEqual(requests[1], requests[0]);
    const result = await view.snapshot();
    assert.equal(result.submission, 1); assert.equal(result.comments.length, 2); assert.equal(bound.calls.length, 1);
    return { lostResponseRetried: true, identicalRequestAndReceipt: true, exactCommentCount: 2 };
  } },
  { name: "direct-send-changed-collection", async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "direct-stale", "Avtale · endret samling");
    await view.note("Dette er min uferdige tekst.");
    const requests = [];
    await view.page.route(/\/comments\/submit-draft(?:\?|$)/, async route => {
      requests.push({ body: route.request().postDataJSON(), mutation: route.request().headers()["x-feedback-mutation"] });
      if (requests.length === 1) {
        const target = new URL(route.request().url()); target.pathname = "/comments";
        const response = await fetch(target, { method: "POST", headers: { Origin: target.origin, "Content-Type": "application/json" }, body: JSON.stringify({ ...requests[0].body.comment, text: "Et nyere lagret innspill." }) });
        assert.equal(response.status, 200);
      }
      await route.continue();
    });
    await view.ui.getByRole("button", { name: "Send innspill", exact: true }).click();
    await view.ui.locator(".compose-error").waitFor();
    const text = view.ui.getByLabel("Hva vil du endre?", { exact: true });
    assert.equal(await text.inputValue(), "Dette er min uferdige tekst.");
    assert.equal(await text.getAttribute("readonly"), null);
    assert(await view.ui.getByRole("button", { name: "Send alle 2 innspill", exact: true }).isEnabled());
    await view.ui.locator(".compose-batch summary").click();
    assert.equal(await view.ui.locator(".compose-batch-text").textContent(), "Et nyere lagret innspill.");
    assert(await view.ui.locator(".compose-batch li").isVisible());
    assert.equal((await view.snapshot()).submission, 0); assert.equal(bound.calls.length, 0); assert.equal(requests.length, 1);
    await screenshot(view, "collection-needs-review");
    await view.ui.getByRole("button", { name: "Send alle 2 innspill", exact: true }).click();
    await view.round(1, "queued");
    assert.equal(requests.length, 2); assert.notEqual(requests[0].mutation, requests[1].mutation);
    assert.equal((await view.snapshot()).comments.length, 2);
    return { staleCollectionRejected: true, composerTextRetained: true, updatedScopeVisible: true, explicitNewIntentRequired: true };
  } },
  { name: "editor-keyboard-error-and-proposal-ownership", viewport: { width: 320, height: 568 }, async run({ host, instance, screenshot }) {
    const fixture = title => {
      const value = editableSketch(title), lead = "Oppdiktet møte: Servicesenteret i Solvik, 18. november kl. 10.00.";
      value.design.texts.push({ id: "lead", label: "Forklaring", value: lead });
      value.html = value.html.replace(renderToStaticMarkup(h(C.BodyShort, null, lead)), renderToStaticMarkup(h(C.BodyShort, null, h("span", { "data-vc-text": "lead" }, "Opprinnelig forklaring"))));
      return value;
    };
    const bound = host(), view = await instance(bound, "keyboard-source", "Din avtale", { fixture, openInput: { workspacePath: "design/keyboard", create: true, title: "Tekst og innspill" } });
    await view.ui.getByRole("button", { name: "Gi innspill", exact: true }).click(); await view.frame.locator("[data-vc-text=heading]").click();
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
  { name: "editor-manual-holds-and-releases", viewport: { width: 1280, height: 900 }, async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "constraints", "Avtalens overskrift", { fixture: editableSketch, openInput: { workspacePath: "design/constraints", create: true, title: "Bevarte valg" } });
    let editor = await openEditor(view); await editor.getByLabel("Overskrift", { exact: true }).fill("Min beholdte overskrift");
    await editor.getByLabel("Mengde forklaring · Møteavtale", { exact: true }).selectOption("full");
    await editor.getByRole("button", { name: "Lagre som ny versjon", exact: true }).click();
    await view.frame.getByRole("heading", { name: "Min beholdte overskrift", exact: true }).waitFor();
    await until(async () => (await view.snapshot()).workspace.version === 2, "manual fields saved");
    await assert.rejects(view.publish("Forsøk på å endre overskriften"), error => error.status === 409);
    const saved = await view.snapshot(); await assert.rejects(view.action("restore_revision", { revisionId: 1, expectedRevision: saved.revision }), error => error.status === 409);
    // The designer can change a saved field again; that is a new saved value, not a release.
    editor = await openEditor(view); await editor.getByLabel("Mengde forklaring · Møteavtale", { exact: true }).selectOption("short");
    await editor.getByRole("button", { name: "Lagre som ny versjon", exact: true }).click();
    await until(async () => (await view.snapshot()).workspace.version === 3, "changed finite source saved");
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
    return { manualPublishAndRestoreConflicts: 2, savedFieldChangedAgain: true, manualReleases: 2, releaseCreatesNoRevision: true, publicationAfterRelease: true, automaticSubmissions: 0 };
  } },
  { name: "endre-parts-and-whole-sketch", viewport: { width: 390, height: 844 }, async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "parts", "Timeavtale · deler", { fixture: editableSketch, openInput: { workspacePath: "design/deler", create: true, title: "Deler" } });
    await view.ui.getByRole("button", { name: "Gi innspill", exact: true }).click();
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
    if (await view.ui.locator('[data-action="change-ask"]').getAttribute("aria-pressed") !== "true") await view.ui.getByRole("button", { name: "Gi innspill", exact: true }).click();
    await parts.selectOption({ label: "Møteavtale" });
    await view.ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Vis hva som skjer med den opprinnelige timen.");
    await view.save();
    const part = await pointed();
    assert.equal(part.element.key, "meeting", "A declared part points at its own element.");
    assert.equal(part.item.kind, "point"); assert.equal((await view.snapshot()).submission, 0); assert.equal(bound.calls.length, 0);
    await view.closeFeedback();
    // A point on the heading widens to its box and back, one visible step at a time.
    if (await view.ui.locator('[data-action="change-ask"]').getAttribute("aria-pressed") !== "true") await view.ui.getByRole("button", { name: "Gi innspill", exact: true }).click();
    await view.frame.getByRole("heading", { name: "Passer tidspunktet?", exact: true }).click();
    const label = view.ui.locator(".anchor-label"), larger = view.ui.getByRole("button", { name: "Større del", exact: true }), smaller = view.ui.getByRole("button", { name: "Mindre del", exact: true });
    assert.equal(await label.textContent(), "Valgt overskrift «Passer tidspunktet?»");
    assert(await smaller.isDisabled(), "Nothing smaller than the clicked element.");
    await larger.click();
    assert.equal(await label.textContent(), "Valgt del «Passer tidspunktet?»");
    await screenshot(view, "larger-part");
    await smaller.click();
    assert.equal(await label.textContent(), "Valgt overskrift «Passer tidspunktet?»");
    assert(await larger.evaluate(node => node.getRootNode().activeElement === node), "Focus stays on the remaining step.");
    await larger.click();
    await view.ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Hele boksen bør bli kortere.");
    await view.save();
    const box = await pointed();
    assert.equal(box.element.key, "meeting", "The widened point anchors the whole box.");
    assert.equal(box.item.context?.target, "meeting", "The widened point keeps the declared part as context.");
    await view.closeFeedback();
    assert(await view.ui.getByRole("group", { name: "Endre skissen", exact: true }).isHidden(), "Completed annotation returns directly to ordinary interaction.");
    return { wholeSketchAnchor: true, declaredPartAnchor: "meeting", widenedPointAnchor: "meeting", automaticSubmissions: 0 };
  } },
  // Boxes come from headings: a box without its own layout is skipped, every
  // heading bounds a box, and a text preview never changes a measured part.
  { name: "parts-from-headings-and-preview", viewport: { width: 1280, height: 900 }, async run({ host, instance, screenshot }) {
    const steps = Array.from({ length: 59 }, (_, index) => `<h3>Punkt ${index + 1}</h3>`).join("");
    const headed = title => ({ html: `<main>${renderToStaticMarkup(h(C.Heading, { level: "1", size: "large" }, title))}<div class="pair"><div style="display:contents"><section class="box-a"><h2>Første boks</h2>${steps}</section></div><section class="box-b"><h2>Andre boks</h2><p>Kort tekst.</p></section></div>${renderToStaticMarkup(h(C.TextField, { label: "Prøvefelt", id: "practice" }))}</main>` });
    const bound = host(), view = await instance(bound, "headed", "Timeavtale · bokser", { fixture: headed });
    const pointed = async () => {
      const item = (await view.snapshot()).comments.at(-1);
      return { item, element: await view.frame.locator("body").evaluate((_, path) => {
        const node = document.querySelector(path), rect = node?.getBoundingClientRect();
        return node && { className: node.className, height: Math.round(rect.height) };
      }, item.anchor.path) };
    };
    await view.ui.getByRole("button", { name: "Gi innspill", exact: true }).click();
    await view.ui.getByLabel("Velg en del", { exact: true }).selectOption({ label: "Første boks" });
    assert.equal(await view.ui.locator(".anchor-label").textContent(), "Valgt del «Første boks»");
    await view.ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Del opp punktene.");
    await view.save();
    assert.equal((await pointed()).element.className, "box-a", "The visible box, not its display: contents wrapper or the pair around both boxes.");
    await view.closeFeedback();
    if (await view.ui.locator('[data-action="change-ask"]').getAttribute("aria-pressed") !== "true") await view.ui.getByRole("button", { name: "Gi innspill", exact: true }).click();
    const heading = view.frame.getByRole("heading", { name: "Andre boks", exact: true });
    await heading.click();
    await view.ui.getByRole("button", { name: "Foreslå ny tekst", exact: true }).click();
    await view.ui.getByLabel("Ny tekst", { exact: true }).fill("En mye lengre overskrift som brytes over flere linjer og gjør boksen høyere enn den er i skissen");
    await view.ui.getByRole("button", { name: "Forhåndsvis teksten", exact: true }).click();
    await view.ui.getByRole("button", { name: "Se i skissen", exact: true }).click();
    await view.ui.getByRole("button", { name: "Fortsett å redigere", exact: true }).click();
    assert.equal(await view.ui.locator(".anchor-label").textContent(), "Valgt overskrift «Andre boks»", "The label names the part, not the previewed text.");
    await view.ui.getByRole("button", { name: "Større del", exact: true }).click();
    await heading.waitFor();
    assert.equal(await view.ui.locator(".anchor-label").textContent(), "Valgt del «Andre boks»");
    assert(await view.ui.getByRole("button", { name: "Foreslå ny tekst", exact: true }).isHidden(), "A box is not a single piece of text.");
    await view.ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Kortere tekst i boksen.");
    await view.save();
    const box = await pointed();
    assert.equal(box.element.className, "box-b");
    assert.equal(box.item.anchor.rect.height, box.element.height, "The anchor is measured without the text preview.");
    assert.equal(box.item.kind, "point");
    return { displayContentsSkipped: true, headingsBeyondSixtyBound: true, previewFreeAnchor: true };
  } },
  // Header badges give way on narrow screens; the feedback panel still says it.
  { name: "temporary-sketch-and-standalone-page", viewport: { width: 1280, height: 900 }, async run({ host, instance, screenshot }) {
    // No declared parts and no headed boxes besides the page heading.
    const plain = title => ({ html: `<main>${renderToStaticMarkup(h(C.Heading, { level: "1", size: "large" }, title))}${renderToStaticMarkup(h(C.BodyShort, null, "Oppdiktet tekst uten egne deler."))}${renderToStaticMarkup(h(C.TextField, { label: "Prøvefelt", id: "practice" }))}</main>` });
    const bound = host(), view = await instance(bound, "temporary", "Timeavtale · midlertidig", { fixture: plain });
    assert.equal(view.title(), "Midlertidig skisse", "A temporary sketch is titled as one.");
    const badge = view.frame.locator(".vc-header .vc-badge", { hasText: "Midlertidig" });
    await until(async () => await badge.isVisible(), "temporary badge shown");
    await view.openFeedback();
    assert.equal(await view.ui.locator(".panel-intro").textContent(), "Midlertidig skisse: forsvinner når samtalen avsluttes eller etter fire timer uten bruk.");
    await screenshot(view, "temporary-intro");
    await view.closeFeedback();
    // With nothing else to choose, a single button replaces the list.
    await view.ui.getByRole("button", { name: "Gi innspill", exact: true }).click();
    assert(await view.ui.getByLabel("Velg en del", { exact: true }).isHidden(), "A list with one choice is not offered.");
    await view.ui.getByRole("button", { name: "Hele skissen", exact: true }).click();
    assert.equal(await view.ui.locator(".anchor-label").textContent(), "Valgt hele skissen");
    assert(await view.ui.locator(".anchor-scope").isHidden(), "The whole sketch has no larger or smaller step.");
    await screenshot(view, "whole-sketch-button");
    await view.ui.getByRole("button", { name: "Forkast", exact: true }).click();
    // Opened on its own, the sketch page offers no feedback tools.
    const src = await view.page.locator("#vc-preview").getAttribute("src");
    const alone = await view.page.context().newPage();
    const aloneErrors = []; alone.on("pageerror", error => aloneErrors.push(error.message));
    await alone.goto(new URL(src, view.url()).href);
    await alone.getByRole("heading", { name: "Timeavtale · midlertidig", exact: true }).waitFor();
    const notice = alone.locator("[data-visual-feedback-notice]").getByRole("status");
    assert.equal(await notice.textContent(), "Bare visning. Innspill lagres ikke her. Gi innspill i Designverksted.");
    assert.equal(await alone.locator("[data-visual-feedback]").evaluate(node => getComputedStyle(node).display), "none", "No feedback tools without Designverksted.");
    await alone.getByRole("heading", { name: "Timeavtale · midlertidig", exact: true }).click();
    assert.equal(await alone.locator("[data-visual-feedback]").evaluate(node => node.shadowRoot.querySelector(".composer").hidden), true, "A click starts no wish.");
    if (evidence) await alone.screenshot({ path: path.join(evidence, "temporary-sketch-and-standalone-page-alone.png"), animations: "disabled" });
    await alone.close();
    assert.deepEqual(aloneErrors, []);
    assert.equal((await view.snapshot()).comments.length, 0);
    return { temporaryTitle: true, temporaryBadge: true, standaloneNotice: true, standaloneFeedbackTools: 0 };
  } },
  { name: "workspace-view-stored-version-read-only", viewport: { width: 390, height: 844 }, async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "view-stored", "Timeavtale · første", { openInput: { workspacePath: "design/visning", create: true, title: "Visning" } });
    await view.publish("Timeavtale · andre"); await view.frame.getByRole("heading", { name: "Timeavtale · andre", exact: true }).waitFor();
    const before = await view.snapshot(); let restoreRequests = 0;
    view.page.on("request", request => { if (new URL(request.url()).pathname === "/workspace/restore") restoreRequests += 1; });
    const banner = view.ui.getByText("Viser lagret versjon 1. Ingen ny versjon er laget.", { exact: true });
    await openTools(view.ui); await view.ui.getByRole("button", { name: "Versjoner", exact: true }).click();
    await view.ui.locator('.workspace-revision[data-revision-id="1"]').getByRole("button", { name: "Vis versjon 1", exact: true }).click();
    await view.frame.getByRole("heading", { name: "Timeavtale · første", exact: true }).waitFor(); await banner.waitFor();
    assert.equal(await view.frame.locator('[data-vc-key="meeting"]').getAttribute("data-vc-setting-detail"), "short", "A stored version starts from its declared values.");
    for (const name of ["Gi innspill", "Juster visning", "Innspill"]) assert.equal(await view.ui.getByRole("button", { name, exact: true }).count(), 0, `${name} is not offered on a stored version.`);
    assert.deepEqual(await view.snapshot(), before, "Viewing changes nothing in the room."); assert.equal(restoreRequests, 0);
    await screenshot(view, "stored-version-read-only");
    await view.publish("Timeavtale · tredje"); await new Promise(resolve => setTimeout(resolve, 4500));
    assert(await view.frame.getByRole("heading", { name: "Timeavtale · første", exact: true }).isVisible(), "A newer version does not replace the stored version on screen.");
    await view.ui.getByRole("button", { name: "Tilbake til gjeldende versjon", exact: true }).click();
    await view.frame.getByRole("heading", { name: "Timeavtale · tredje", exact: true }).waitFor();
    await view.ui.locator('[data-action="comment"]').waitFor(); assert.equal(await banner.count(), 0);
    await openTools(view.ui); await view.ui.getByRole("button", { name: "Versjoner", exact: true }).click();
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
  { name: "view-restore-preserved-field-and-leave-editor", viewport: { width: 1280, height: 900 }, async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "view-hold", "Avtale · første", { fixture: editableSketch, openInput: { workspacePath: "design/visning-hold", create: true, title: "Visning og bevarte felt" } });
    let editor = await openEditor(view);
    await editor.getByLabel("Overskrift", { exact: true }).fill("Min lagrede overskrift");
    await editor.getByRole("button", { name: "Lagre som ny versjon", exact: true }).click();
    await view.frame.getByRole("heading", { name: "Min lagrede overskrift", exact: true }).waitFor();
    // Closing Rediger returns directly to normal sketch interaction.
    editor = await openEditor(view);
    await editor.getByRole("button", { name: "Lukk redigering", exact: true }).click();
    assert.equal(await view.ui.locator('[data-action="comment"]').getAttribute("aria-pressed"), "false", "Prøv leaves Endre.");
    assert(await editor.isHidden(), "Prøv closes Rediger.");
    // Using a stored version can release the preserved field it changes.
    await openTools(view.ui); await view.ui.getByRole("button", { name: "Versjoner", exact: true }).click();
    await view.ui.locator('.workspace-revision[data-revision-id="1"]').getByRole("button", { name: "Vis versjon 1", exact: true }).click();
    await view.ui.getByText("Viser lagret versjon 1. Ingen ny versjon er laget.", { exact: true }).waitFor();
    await view.ui.getByRole("button", { name: "Bruk som ny versjon", exact: true }).first().click();
    await view.ui.locator('[data-action="workspace-restore"]').click();
    const release = view.ui.getByRole("button", { name: "Tillat endring og bruk versjon 1", exact: true });
    await release.waitFor(); await release.click();
    await until(async () => (await view.snapshot()).workspace.version === 3, "stored version used after releasing its preserved field");
    await view.ui.locator('[data-action="comment"]').waitFor();
    await view.frame.getByRole("heading", { name: "Avtale · første", exact: true }).waitFor();
    // «Vises nå» follows the version on screen while a newer one waits.
    await openTools(view.ui); await view.ui.getByRole("button", { name: "Versjoner", exact: true }).click();
    await view.ui.locator('.workspace-revision[data-revision-id="3"]').waitFor();
    await view.publish("Avtale · fjerde");
    await view.ui.locator('[data-action="workspace-reload"]').click();
    const latest = view.ui.locator('.workspace-revision[data-revision-id="4"]'), shown = view.ui.locator('.workspace-revision[data-revision-id="3"]');
    await latest.waitFor();
    assert.equal(await latest.getByRole("button", { name: "Vis versjon 4", exact: true }).textContent(), "Vis");
    assert.equal(await shown.getByRole("button", { name: "Vis versjon 3", exact: true }).textContent(), "Vises nå");
    await screenshot(view, "displayed-version-marked");
    assert.equal(bound.calls.length, 0);
    return { leftEditorWithProv: true, restoredThroughPreservedField: 3, displayedVersionMarked: 3, automaticSubmissions: 0 };
  } },
  { name: "wish-while-editing-names-saved-version", viewport: { width: 1280, height: 900 }, async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "wish-edit", "Avtale · lagret", { fixture: editableSketch, openInput: { workspacePath: "design/onske-under-redigering", create: true, title: "Ønske under redigering" } });
    let editor = await openEditor(view);
    await editor.getByLabel("Overskrift", { exact: true }).fill("Ulagret overskrift");
    await view.frame.getByRole("heading", { name: "Ulagret overskrift", exact: true }).waitFor();
    // A wish names the saved sketch; the unsaved field stays in Rediger.
    await view.ui.locator('[data-action="comment"]').click();
    assert(await editor.isHidden(), "Be om endring leaves Rediger.");
    const heading = view.frame.getByRole("heading", { name: "Avtale · lagret", exact: true });
    await heading.waitFor(); await heading.click();
    await view.ui.getByText("Gjelder den lagrede versjonen. Ulagrede endringer i «Rediger» er ikke med.", { exact: true }).waitFor();
    await view.ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Overskriften kan være kortere.");
    await screenshot(view, "wish-names-saved-version");
    // Rediger shows the unfinished wish instead of opening over it.
    await view.ui.getByRole("button", { name: "Legg utkast til side", exact: true }).click();
    await openTools(view.ui); await view.ui.getByRole("button", { name: "Rediger", exact: true }).click();
    await view.ui.locator(".composer").waitFor();
    assert(await editor.isHidden(), "Rediger stays closed while a wish draft is unfinished.");
    assert.equal(await view.ui.getByLabel("Hva vil du endre?", { exact: true }).inputValue(), "Overskriften kan være kortere.");
    await view.save();
    editor = await openEditor(view);
    assert.equal(await editor.getByLabel("Overskrift", { exact: true }).inputValue(), "Ulagret overskrift", "The unsaved field survives the wish.");
    assert(await view.ui.locator(".compose-scope").isHidden());
    const saved = await view.snapshot();
    assert.equal(saved.comments.length, 1); assert.equal(saved.workspace.version, 1); assert.equal(bound.calls.length, 0);
    return { wishNamesSavedVersion: true, editorWaitsForDraft: true, unsavedFieldKept: true, automaticSubmissions: 0 };
  } },
  { name: "prov-past-hidden-editor-draft", viewport: { width: 1280, height: 900 }, async run({ host, instance, screenshot }) {
    // Declared actions in the sketch switch the meeting part between short and full.
    const fixture = title => { const value = editableSketch(title); value.html = value.html.replace(/(<[^>]*data-vc-key="meeting"[^>]*>)/, '$1<button type="button" data-vc-control="detail" data-vc-value="full">Vis mer</button><button type="button" data-vc-control="detail" data-vc-value="short">Vis mindre</button>'); return value; };
    const bound = host(), view = await instance(bound, "prov-draft", "Avtale · prøv", { fixture, openInput: { workspacePath: "design/prov-utkast", create: true, title: "Prøv med utkast" } });
    const meeting = view.frame.locator('[data-vc-key="meeting"]'), detail = () => meeting.getAttribute("data-vc-setting-detail");
    await view.frame.getByRole("button", { name: "Vis mer", exact: true }).click(); assert.equal(await detail(), "full");
    await view.frame.getByRole("button", { name: "Vis mindre", exact: true }).click(); assert.equal(await detail(), "short");
    let editor = await openEditor(view);
    const rediger = view.ui.locator('[data-action="editor-open"]');
    assert.equal(await rediger.getAttribute("aria-expanded"), "true", "Rediger tells that it is open.");
    await editor.getByLabel("Overskrift", { exact: true }).fill("Ulagret overskrift");
    // With Rediger open, the prototype waits and says why.
    await view.frame.getByRole("button", { name: "Vis mer", exact: true }).click();
    assert.equal(await detail(), "short");
    assert.equal(await view.ui.locator(".hint").textContent(), "Lukk «Rediger» for å prøve knappene i skissen. Utkastet ditt beholdes.");
    await editor.getByRole("button", { name: "Lukk redigering", exact: true }).click();
    assert.equal(await rediger.getAttribute("aria-expanded"), "false");
    // A closed Rediger keeps its draft, and ordinary interaction works immediately.
    await view.frame.getByRole("button", { name: "Vis mer", exact: true }).click();
    assert.equal(await detail(), "full", "A hidden editor draft must not stop the prototype in Prøv.");
    editor = await openEditor(view);
    assert.equal(await editor.getByLabel("Overskrift", { exact: true }).inputValue(), "Ulagret overskrift", "The editor draft survives trying the sketch.");
    await screenshot(view, "editor-draft-kept-after-prov");
    assert.equal((await view.snapshot()).workspace.version, 1); assert.equal(bound.calls.length, 0);
    return { prototypeWorksWithHiddenDraft: true, openEditorExplains: true, editorExpandedState: true, automaticSubmissions: 0 };
  } },
  { name: "workspace-limit-preserves-history", async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "capacity", "Timeavtale · første", { openInput: { workspacePath: "design/capacity", create: true, title: "Bevart historikk" } });
    await view.publish("Timeavtale · andre"); await view.frame.getByRole("heading", { name: "Timeavtale · andre", exact: true }).waitFor();
    const before = await view.snapshot(); let attempts = 0;
    // The backend capacity limit has its own tests; exercise the browser's permanent-error guidance without creating 100 revisions here.
    await view.page.route(/\/workspace\/restore(?:\?|$)/, async route => { attempts += 1; await route.fulfill({ status: 429, contentType: "application/json", body: JSON.stringify({ error: "Workspace capacity reached." }) }); });
    await openTools(view.ui); await view.ui.getByRole("button", { name: "Versjoner", exact: true }).click(); await view.ui.locator('.workspace-revision[data-revision-id="1"]').getByRole("button", { name: "Bruk som ny versjon", exact: true }).click(); await view.ui.locator('[data-action="workspace-restore"]').click();
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
    await original.workshop.getByRole("button", { name: "Behold denne delen", exact: true }).click(); await original.ui.locator(".panel").waitFor();
    await original.note("Første innspill, sendt i den tidligere samtalen."); await original.save(); await original.send(2); await original.round(1, "unknown");
    await original.note("Nytt innspill som er lagret, men ikke sendt."); await original.save();
    await original.publish("Timeavtale · neste dag");
    const saved = await original.snapshot(); assert.equal(saved.workspace.storage, "project"); assert.equal(saved.workspace.version, 2);
    await original.retire();
    const next = host(), reopened = await instance(next, "second-opening", "Timeavtale · neste dag", { openInput: { workspacePath: "design/timeavtale" }, publishInitial: false });
    const recovered = await reopened.snapshot();
    assert.equal(recovered.workspace.id, saved.workspace.id); assert.equal(recovered.workspace.version, saved.workspace.version); assert.equal(recovered.workspace.recovered, true);
    assert.deepEqual(recovered.comments, saved.comments); assert.equal(Object.hasOwn(recovered, "decisions"), false);
    assert(recovered.comments.some(item => item.text.startsWith("Behold denne delen.") && item.context?.target === "meeting"), "The keep wish is recovered as an ordinary wish.");
    assert.equal(next.calls.length, 0, "Opening a project must not deliver historical rounds.");
    await reopened.openFeedback(); const old = await reopened.round(1, "previous");
    assert.equal(await old.locator(".badge").textContent(), "Fra tidligere økt");
    assert.match(await old.locator(".workspace-previous").textContent(), /uavklart/);
    assert(await reopened.ui.getByRole("button", { name: "Send 1 innspill", exact: true }).isEnabled(), "A previous session's uncertainty must not permanently block new feedback.");
    await screenshot(reopened, "previous-round-and-new-feedback");
    await reopened.closeFeedback(); await openTools(reopened.ui); await reopened.ui.getByRole("button", { name: "Versjoner", exact: true }).click();
    await reopened.ui.locator(".workspace-history-list article").first().waitFor();
    assert.equal(await reopened.ui.locator(".workspace-title").textContent(), "Timeavtale");
    assert.match(await reopened.ui.locator(".workspace-path").textContent(), /design\/timeavtale/);
    assert(await reopened.ui.locator(".workspace-recovered").isVisible());
    await screenshot(reopened, "project-workspace-reopened");
    await reopened.ui.getByRole("button", { name: "Lukk versjoner", exact: true }).click();
    await reopened.send(1); await reopened.round(2, "queued");
    assert.equal(next.calls.length, 1); assert.equal(next.calls[0].identity.submission, 2);
    assert.equal(first.calls.length, 1);
    return { actualBackendRestart: true, projectIdentityPreserved: true, savedUnsentFeedbackPreserved: true, keepWishPreserved: true, historicalUnknownDistinguished: true, openingEnqueuesNothing: true, onlyNewRoundSent: true };
  } },
  { name: "workspace-restore-protects-draft", viewport: { width: 1280, height: 900 }, async run({ host, instance, screenshot }) {
    const bound = host(), view = await instance(bound, "restoring", "Timeavtale · opprinnelig", { openInput: { workspacePath: "design/restore", create: true, title: "Timeavtale med historikk" } });
    await view.publish("Timeavtale · bearbeidet"); await view.frame.getByRole("heading", { name: "Timeavtale · bearbeidet", exact: true }).waitFor();
    await view.note("Lagret innspill til den bearbeidede versjonen."); await view.save();
    const saved = await view.snapshot();
    await view.note("Ulagret begrunnelse som må beholdes."); await view.ui.getByRole("button", { name: "Foreslå ny tekst", exact: true }).click(); await view.ui.getByLabel("Ny tekst", { exact: true }).fill("Din neste avtale");
    let restoreRequests = 0;
    view.page.on("request", request => { if (new URL(request.url()).pathname === "/workspace/restore") restoreRequests += 1; });
    await openTools(view.ui); await view.ui.getByRole("button", { name: "Versjoner", exact: true }).click();
    await view.ui.locator('.workspace-revision[data-revision-id="1"]').getByRole("button", { name: "Bruk som ny versjon", exact: true }).click();
    assert(await view.ui.locator('[data-action="workspace-restore"]').isDisabled()); assert.equal(restoreRequests, 0);
    assert.match(await view.ui.locator(".workspace-restore-warning").textContent(), /Utkastet ditt er beholdt/);
    await screenshot(view, "draft-blocks-restore");
    await view.ui.getByRole("button", { name: "Lukk versjoner", exact: true }).click(); await view.ui.getByRole("button", { name: "Fortsett utkast", exact: true }).click();
    assert.equal(await view.ui.getByLabel("Hva vil du endre?", { exact: true }).inputValue(), "Ulagret begrunnelse som må beholdes."); assert.equal(await view.ui.getByLabel("Ny tekst", { exact: true }).inputValue(), "Din neste avtale");
    await view.ui.getByRole("button", { name: "Forkast", exact: true }).click();
    await openTools(view.ui); await view.ui.getByRole("button", { name: "Versjoner", exact: true }).click();
    await view.ui.locator('.workspace-revision[data-revision-id="1"]').getByRole("button", { name: "Bruk som ny versjon", exact: true }).click();
    await view.ui.locator('[data-action="workspace-restore"]').click();
    await view.frame.getByRole("heading", { name: "Timeavtale · opprinnelig", exact: true }).waitFor();
    const restored = await view.snapshot();
    assert.equal(restored.workspace.version, 3); assert.deepEqual(restored.comments, saved.comments); assert.equal(restored.submission, 0); assert.equal(bound.calls.length, 0); assert.equal(restoreRequests, 1);
    await openTools(view.ui); await view.ui.getByRole("button", { name: "Versjoner", exact: true }).click();
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
    await openTools(view.ui); await view.ui.getByRole("button", { name: "Versjoner", exact: true }).click();
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
    await openTools(view.ui); await view.ui.getByRole("button", { name: "Versjoner", exact: true }).click(); await view.ui.locator('.workspace-revision[data-revision-id="23"]').waitFor();
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
    await view.workshop.getByLabel("Mengde forklaring", { exact: true }).selectOption("full");
    await view.workshop.getByLabel("Merknad", { exact: true }).fill("Behold forklaringen om gjeldende avtale.");
    assert.equal(bound.calls.length, 0);
    await view.workshop.getByRole("button", { name: "Behold denne delen", exact: true }).click();
    await view.ui.locator(".panel").waitFor();
    await view.note("Gjør tidspunktet lettere å finne."); await view.save();
    assert.equal(bound.calls.length, 0, "Saving and keeping are local until explicit Send.");
    await view.send(2); await until(() => bound.calls.length === 1, "one host notification");
    await view.round(1, "sending");
    const batch = await view.action("read_submission", { submission: 1 });
    assert(batch.items.some(item => item.type === "comment" && item.value.text === "Behold denne delen.\nBehold forklaringen om gjeldende avtale." && item.value.context?.target === "meeting"), "The keep wish travels as a wish.");
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
