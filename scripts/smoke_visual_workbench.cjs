#!/usr/bin/env node
"use strict";
const assert = require("node:assert/strict"), fs = require("node:fs"), os = require("node:os"), path = require("node:path"), http = require("node:http");
const { pathToFileURL } = require("node:url");
const { checkWorkerOriginIsolation } = require("./visual-smoke-workers.cjs");
const options = new Map();
for (let i = 2; i < process.argv.length; i += 2) {
  if (!["--playwright-module", "--browser-engine", "--browser-channel", "--evidence-dir", "--aksel-project"].includes(process.argv[i]) || !process.argv[i + 1]) throw new Error("Supply the existing Playwright module and optional browser, evidence and Aksel paths.");
  options.set(process.argv[i], process.argv[i + 1]);
}
const browserEngine = options.get("--browser-engine") || "chromium";
if (!["chromium", "webkit"].includes(browserEngine) || browserEngine !== "chromium" && options.has("--browser-channel")) throw new Error("Choose chromium or webkit; browser-channel is supported only with chromium.");
const browserType = require(options.get("--playwright-module") || "playwright")[browserEngine];
const evidence = options.get("--evidence-dir") && path.resolve(options.get("--evidence-dir"));
if (evidence) fs.mkdirSync(evidence, { recursive: true });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms)), results = [], viewportMeasurements = [];
async function until(read, label) { const end = Date.now() + 15000; while (Date.now() < end) { if (await read()) return; await pause(40); } throw new Error("Timed out: " + label); }
async function check(name, fn) { await fn(); results.push({ name, passed: true }); console.log("PASS " + name); }
function sketch(title) {
  return { html: `<style>main{padding:24px;max-width:46rem;margin:auto;font:18px/1.6 system-ui}button{font:inherit;padding:12px}.details{display:none}[data-vc-setting-detail=full] .details{display:block}</style><main><h1 class="aksel-heading aksel-heading--large">${title}</h1><p class="aksel-body-short">Forslag med oppdiktede data.</p><section data-vc-key="meeting"><button class="aksel-button" data-variant="primary" data-color="accent" type="button" data-vc-control="detail" data-vc-value="full">Se forberedelsene</button><div class="details"><h2>Før møtet</h2><p>Lag en plan sammen og noter hva dere trenger hjelp til.</p><button type="button" data-vc-control="detail" data-vc-value="short">Tilbake</button></div></section></main>`,
    design: { version: 1, variants: [], targets: [{ key: "meeting", variant: "", label: "Forberedelser", controls: [{ id: "detail", label: "Forklaring", type: "select", initial: "short", options: [{ value: "short", label: "Kort" }, { value: "full", label: "Utfyllende" }] }] }] } };
}
async function main() {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "design-workbench-smoke-"))), project = path.join(root, "project"); fs.mkdirSync(project);
  if (options.has("--aksel-project")) {
    const from = path.join(path.resolve(options.get("--aksel-project")), "node_modules/@navikt/ds-css"), to = path.join(project, "node_modules/@navikt/ds-css");
    fs.mkdirSync(path.dirname(to), { recursive: true }); fs.cpSync(fs.realpathSync(from), to, { recursive: true, dereference: true });
  }
  const appSource = '<!doctype html><html lang="nb"><meta charset="utf-8"><title>Møtedemo</title><style>body{font:18px/1.6 system-ui;padding:30px}input,button{font:inherit;padding:12px}</style><main><h1>Dialogmøter</h1><label for="choice">Prøvefelt</label><input id="choice"><button type="button">Be om møte</button><p>Oppdiktede data.</p></main></html>';
  fs.writeFileSync(path.join(project, "demo.html"), appSource);
  const app = http.createServer((req, res) => { res.setHeader("Content-Type", "text/html; charset=utf-8"); res.end(appSource); });
  let proposalApp, adapter, browser, context, page, releaseInitialState = () => {}, generation = 0;
  const errors = [], external = [], messages = [];
  try {
    await new Promise(resolve => app.listen(0, "127.0.0.1", resolve));
    const { createCanvasAdapter, CANVAS_ID } = await import(pathToFileURL(path.resolve(__dirname, "../plugin/extensions/visual-companion/adapter.mjs")).href);
    let identity = { sessionId: "workbench-smoke", extensionId: "project:visual-companion", canvasId: CANVAS_ID, instanceId: "meeting" };
    const attach = directory => { adapter = createCanvasAdapter({ sessionId: identity.sessionId, projectDir: directory }); adapter.attachSession({ sessionId: identity.sessionId, capabilities: { ui: { canvases: true } }, send: async value => { messages.push(value); await pause(200); return "accepted"; } }); };
    attach(project);
    const action = (name, input = {}) => adapter.canvas.actions.find(item => item.name === name).handler({ ...identity, input });
    const application = { name: "Møtedemo", url: `http://127.0.0.1:${app.address().port}/demo` };
    browser = await browserType.launch({ headless: true, ...(options.has("--browser-channel") ? { channel: options.get("--browser-channel") } : {}) });
    context = await browser.newContext({ viewport: { width: 1280, height: 800 }, reducedMotion: "reduce" });
    const allowedOrigins = new Set([new URL(application.url).origin]);
    await context.route("**/*", route => { const url = new URL(route.request().url()); if (["data:", "blob:"].includes(url.protocol) || url.protocol === "http:" && allowedOrigins.has(url.origin)) return route.continue(); external.push(url.origin); return route.abort(); });
    for (const endpoint of ["renderer", "proposal"]) await context.route(`**/${endpoint}/activate`, async route => {
      assert(allowedOrigins.has(new URL(route.request().url()).origin));
      const response = await route.fetch();
      if (response.ok()) {
        const value = await response.json(), origin = new URL(endpoint === "renderer" ? value.previewOrigin : value.origin);
        assert.equal(origin.protocol, "http:"); assert.equal(origin.hostname, "127.0.0.1");
        allowedOrigins.add(origin.origin);
      }
      await route.fulfill({ response });
    });
    await context.routeWebSocket("**/*", socket => socket.close());
    context.on("page", opened => opened.on("pageerror", error => errors.push(error.message)));
    const open = async input => {
      identity = { ...identity, instanceId: `meeting-${++generation}` };
      const view = await adapter.canvas.open({ ...identity, input });
      assert.equal(new URL(view.url).hostname, "127.0.0.1"); assert.match(new URL(view.url).pathname, /^\/browser\/[a-f0-9]{64}$/);
      allowedOrigins.add(new URL(view.url).origin); page = await context.newPage(); page.setDefaultTimeout(15000); await page.goto(view.url);
      await until(async () => await page.locator("#proposal-tab").getAttribute("aria-selected") === "true" || await page.frameLocator("#app-preview").getByRole("heading", { name: "Dialogmøter", exact: true }).count() > 0, "selected workshop surface"); return view;
    };
    const frames = () => { const frame = page.frameLocator("#proposal-preview").frameLocator("#sketch").frameLocator("#vc-preview"); return { frame, ui: frame.locator("[data-visual-feedback]") }; };
    const settleProposalPaint = async () => {
      // Each visible frame has its own resize/paint cycle. A heading present
      // in the DOM does not prove that the nested preview has been painted.
      const bridge = page.frameLocator("#proposal-preview"), sketch = bridge.frameLocator("#sketch");
      for (const surface of [page, bridge, sketch, frames().frame]) {
        await surface.locator("body").evaluate(async () => {
          await document.fonts.ready;
          await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        });
      }
    };
    const measureAppViewport = async (shell, preview, ancestors, viewport, title) => {
      // Paint every boundary after resize/focus changes; DOM visibility alone
      // misses clipped nested iframes and stale compositor screenshots.
      for (let pass = 0; pass < 2; pass += 1) for (const surface of [page, ...ancestors.map(item => item.frame), shell, preview]) {
        await surface.locator("body").evaluate(async () => {
          await document.fonts.ready;
          await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        });
      }
      const boxes = [{ x: 0, y: 0, ...viewport }, ...await Promise.all(ancestors.map(item => item.element.boundingBox())), await shell.locator("#app-preview").boundingBox()];
      assert(boxes.every(Boolean), "Every app iframe boundary must be visible");
      const left = Math.max(...boxes.map(box => box.x)), top = Math.max(...boxes.map(box => box.y));
      const right = Math.min(...boxes.map(box => box.x + box.width)), bottom = Math.min(...boxes.map(box => box.y + box.height));
      const appBox = boxes.at(-1), visibleHeight = bottom - top;
      assert(visibleHeight >= Math.min(250, viewport.height / 2), `App content needs usable height, got ${visibleHeight}px at ${viewport.width}×${viewport.height}`);
      assert(visibleHeight >= appBox.height - 2, "Outer chrome must not crop the app iframe");
      assert(right - left >= appBox.width - 2, "The app iframe must fit all outer boundaries");
      for (const surface of [page, shell]) {
        const layout = await surface.locator("body").evaluate(body => ({ width: body.scrollWidth, height: document.documentElement.scrollHeight, viewportWidth: innerWidth, viewportHeight: innerHeight, scrollY }));
        assert(layout.width <= layout.viewportWidth + 1 && layout.height <= layout.viewportHeight + 1 && layout.scrollY === 0, "Workshop chrome must fit without moving its parent document");
      }
      const heading = await preview.getByRole("heading", { name: title, exact: true }).boundingBox();
      assert(heading && heading.y >= top - 1 && heading.y + heading.height <= bottom + 1, "The full app heading must be visible after returning to browse");
      viewportMeasurements.push({ embedded: ancestors.length > 0, ...viewport, visibleHeight, iframeHeight: appBox.height, headingHeight: heading.height });
    };
    await open({ application, workspacePath: "designs/meeting-app", create: true, title: "Forbered et møte" });
    await check("app feedback shows immediate progress and returns to Try", async () => {
      assert.equal(await page.locator("#app-title").textContent(), "Forbered et møte");
      assert.equal(await page.locator("#app-preview").getAttribute("title"), "Møtedemo");
      await page.frameLocator("#app-preview").getByLabel("Prøvefelt").fill("Valg beholdes");
      await page.locator("#mode-change").click(); await page.locator("#whole-page").click(); await page.locator("#comment-text").fill("Vis forberedelsene tydeligere og lag et klikkbart forslag.");
      await page.route("**/submit-draft", async route => { await pause(700); await route.continue(); });
      await page.locator("#send-comment").click(); assert.match(await page.locator("#review-progress-title").textContent(), /Sender/);
      await until(async () => (await action("read_state")).submission === 1, "round committed");
      await until(async () => await page.locator("#mode-browse").getAttribute("aria-pressed") === "true", "Try after send");
      await page.unroute("**/submit-draft"); await until(() => messages.length === 1, "one automatic message");
    });
    const round = await action("read_submission", { submission: 1 }); const commentIds = round.items.filter(item => item.type === "comment").map(item => item.value.id);
    let proposal;
    const initial = { source: "app-feedback", sourceSubmission: 1, commentIds, title: "Tydeligere forberedelser", workspacePath: "designs/meeting-sketch", create: true, filename: "meeting-v1.html", ...sketch("Forbered møtet") };
    await check("proposal tab reflects queued and working feedback before a sketch exists", async () => {
      await page.locator("#proposal-tab").click();
      await until(async () => await page.locator("#proposal-message-title").textContent() === "Innspillene er sendt", "queued proposal status");
      assert.equal(await page.locator("#proposal-back").isVisible(), true);
      await action("review_submission", { submission: 1, status: "working", reply: "Lager et forslag med tydeligere forberedelser." });
      await until(async () => /Arbeider med innspillene/.test(await page.locator("#proposal-message-title").textContent()), "working proposal status");
      assert.equal(await page.evaluate(() => document.activeElement.id), "proposal-tab", "status changes must not move keyboard focus");
      const repeatedAnnouncements = await page.evaluate(() => new Promise(resolve => {
        let changes = 0;
        const observer = new MutationObserver(records => { changes += records.length; });
        observer.observe(document.getElementById("proposal-message"), { childList: true, subtree: true, characterData: true, attributes: true });
        setTimeout(() => { observer.disconnect(); resolve(changes); }, 5500);
      }));
      assert.equal(repeatedAnnouncements, 0, "unchanged polling must not rewrite the live status text");
      if (evidence) await page.screenshot({ path: path.join(evidence, "proposal-working.png") });
      await page.locator("#proposal-back").click();
      assert.equal(await page.locator("#app-tab").getAttribute("aria-selected"), "true");
    });
    await check("one verified proposal appears in the same workshop without stealing focus", async () => {
      await action("review_submission", { submission: 1, status: "working", reply: "Lager et forslag med tydeligere forberedelser." });
      await page.locator("#app-tab").focus(); proposal = await action("publish_proposal", initial);
      if (options.has("--aksel-project")) assert.equal((await action("read_state", { proposalId: proposal.id })).styles.status, "loaded");
      const repeated = await action("publish_proposal", initial); assert.equal(repeated.id, proposal.id); assert.equal(repeated.revisionId, 1);
      await action("review_submission", { submission: 1, status: "answered", reply: "Forslaget gjør forberedelsene lettere å finne. Prøv knappen og fortell hva du vil justere." });
      await until(async () => await page.locator("#proposal-new").isVisible(), "new proposal badge");
      assert.equal(await page.locator("#app-tab").getAttribute("aria-selected"), "true"); assert.equal(await page.evaluate(() => document.activeElement.id), "app-tab");
      assert.equal(context.pages().length, 1, "one direct workshop; no connection panel, popup or proposal window");
      // Publishing can briefly appear in a poll before its child screen is
      // available. A deliberate tab choice must resume when that state changes.
      let publishing = true;
      const duringPublication = async route => {
        const response = await route.fetch(), value = await response.json();
        if (publishing) value.proposals = value.proposals.map(item => ({ ...item, available: false, screen: "" }));
        await route.fulfill({ response, json: value });
      };
      await page.route("**/state", duringPublication);
      await until(async () => await page.locator("#proposal-new").isHidden(), "publication-in-progress poll");
      await page.locator("#proposal-tab").click();
      assert.equal(await page.locator("#proposal-message-title").textContent(), "Forslaget er ikke tilgjengelig");
      publishing = false;
      await frames().frame.getByRole("heading", { name: "Forbered møtet", exact: true }).waitFor();
      await page.unroute("**/state", duringPublication);
      assert.equal(await page.locator("#app-title").textContent(), "Forbered et møte", "The task title must stay the same on the proposal tab");
      await page.frameLocator("#proposal-preview").frameLocator("#sketch").locator('#vc-status[data-connected="true"]').waitFor({ state: "attached" });
      assert.equal(await page.locator("#proposal-message").isVisible(), false);
      await settleProposalPaint();
      if (evidence) await page.screenshot({ path: path.join(evidence, "proposal-desktop.png") });
    });
    await check("real declarative interaction and draft survive switching between app and proposal", async () => {
      const { frame, ui } = frames(); await frame.getByRole("button", { name: "Se forberedelsene", exact: true }).click();
      await frame.getByRole("heading", { name: "Før møtet", exact: true }).waitFor();
      await ui.getByRole("button", { name: "Gi innspill", exact: true }).click(); await frame.getByRole("heading", { name: "Forbered møtet", exact: true }).click();
      await ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Gi overskriften en tydeligere handling.");
      await page.locator("#app-tab").click(); assert.equal(await page.frameLocator("#app-preview").getByLabel("Prøvefelt").inputValue(), "Valg beholdes");
      await page.locator("#proposal-tab").click(); assert.equal(await ui.getByLabel("Hva vil du endre?", { exact: true }).inputValue(), "Gi overskriften en tydeligere handling.");
      await ui.getByRole("button", { name: "Send innspill", exact: true }).click();
      await until(() => messages.length === 2, "proposal feedback delivered once");
      assert.equal(await ui.getByRole("button", { name: "Gi innspill", exact: true }).getAttribute("aria-pressed"), "false");
      const ref = JSON.parse(messages[1].prompt.split("\n").at(-1)); assert.equal(ref.instanceId, identity.instanceId); assert.equal(ref.proposalId, proposal.id); assert.equal(ref.submission, 1);
      assert.equal((await action("read_submission", { proposalId: proposal.id, submission: 1 })).items.filter(item => item.type === "comment").length, 1);
      assert.equal((await action("read_submission", { submission: 1 })).round.review, "answered");
    });
    await check("second sketch version updates the existing view and retains exact feedback routing", async () => {
      const before = await action("read_state", { proposalId: proposal.id });
      await action("publish_revision", { proposalId: proposal.id, expectedScreen: before.screen, filename: "meeting-v2.html", ...sketch("Gjør dere klare til møtet") });
      await action("review_submission", { proposalId: proposal.id, submission: 1, status: "answered", reply: "Overskriften sier nå tydeligere hva dere kan gjøre. Prøv forberedelsene igjen." });
      const update = frames().ui.getByRole("button", { name: "Vis oppdatert forslag", exact: true });
      await update.waitFor(); assert.equal(await update.isEnabled(), true);
      assert.match(await update.getAttribute("aria-description"), /Valg i skissen starter på nytt/);
      await update.click();
      await frames().frame.getByRole("heading", { name: "Gjør dere klare til møtet", exact: true }).waitFor();
      assert.equal((await action("read_state", { proposalId: proposal.id })).workspace.version, 2); assert.equal(messages.length, 2);

    });
    await check("close and fresh reopen keep both rounds and the latest proposal without replay", async () => {
      const previous = page, oldProposal = frames();
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.bringToFront();
      assert.equal(await oldProposal.ui.getByRole("button", { name: "Gi innspill", exact: true }).getAttribute("aria-pressed"), "false");
      await until(async () => await page.locator("#proposal-new").isHidden(), "updated sketch confirmed");
      await oldProposal.ui.getByRole("button", { name: "Gi innspill", exact: true }).click();
      assert.equal(await oldProposal.ui.getByRole("button", { name: "Gi innspill", exact: true }).getAttribute("aria-pressed"), "true");
      await oldProposal.frame.getByRole("heading", { name: "Gjør dere klare til møtet", exact: true }).focus();
      await page.keyboard.press("Enter");
      await oldProposal.ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Uferdig skisseinnspill som kan kopieres fra gammel visning.");
      const closedIdentity = identity;
      await adapter.canvas.onClose(closedIdentity);
      await assert.rejects(adapter.canvas.open(closedIdentity), /expired|closed/i);
      await open({ application, workspacePath: "designs/meeting-app" });
      await page.locator("#proposal-tab").click();
      await frames().frame.getByRole("heading", { name: "Gjør dere klare til møtet", exact: true }).waitFor();
      await page.locator("#app-tab").click();
      await page.frameLocator("#app-preview").getByRole("heading", { name: "Dialogmøter", exact: true }).waitFor();
      await page.locator("#proposal-tab").click();
      await previous.bringToFront();
      await until(async () => /Forbindelsen må sjekkes|Denne visningen er ikke aktiv/.test(await previous.locator("#app-status").textContent()), "old workshop reports lost connection");
      assert.equal(await previous.locator("#proposal-tab").getAttribute("aria-selected"), "true");
      assert.equal(await oldProposal.ui.getByLabel("Hva vil du endre?", { exact: true }).inputValue(), "Uferdig skisseinnspill som kan kopieres fra gammel visning.");
      assert.equal(await oldProposal.ui.getByLabel("Hva vil du endre?", { exact: true }).isVisible(), true);
      if (evidence) await previous.screenshot({ path: path.join(evidence, "disconnected-proposal-draft.png") });
      assert.equal((await action("read_state")).submission, 1); assert.equal((await action("read_state", { proposalId: proposal.id })).submission, 1); assert.equal(messages.length, 2);
      await previous.close();
    });
    await check("saved app and sketch reopen together in a copied project", async () => {
      await adapter.close(); await page.close();
      const copied = path.join(root, "copied-project"); fs.cpSync(project, copied, { recursive: true }); attach(copied);
      const firstState = new Promise(resolve => { releaseInitialState = resolve; });
      const delayState = async route => { await firstState; await route.continue(); };
      await context.route("**/state", delayState);
      await open({ application, workspacePath: "designs/meeting-app" }); await page.locator("#proposal-tab").click();
      assert.equal(await page.locator("#proposal-message-title").textContent(), "Ingen forslag ennå");
      assert.equal(await page.locator("#proposal-tab").getAttribute("aria-selected"), "true");
      releaseInitialState();
      await frames().frame.getByRole("heading", { name: "Gjør dere klare til møtet", exact: true }).waitFor();
      assert.equal((await action("read_state", { proposalId: proposal.id })).workspace.version, 2); assert.equal(messages.length, 2);
      await context.unroute("**/state", delayState);
      assert.equal(fs.readFileSync(path.join(project, "demo.html"), "utf8"), appSource);
    });
    await check("narrow viewports retain the same proposal and keyboard tab access", async () => {
      await until(async () => await page.locator("#proposal-new").isHidden(), "proposal preview authenticated before viewport checks");
      for (const viewport of [{ width: 320, height: 568 }, { width: 640, height: 400 }, { width: 375, height: 812 }]) {
        await page.setViewportSize(viewport); assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await page.locator("#app-tab").focus(); await page.keyboard.press("ArrowRight"); await page.keyboard.press("Enter");
        assert.equal(await page.locator("#proposal-tab").getAttribute("aria-selected"), "true");
        await page.frameLocator("#proposal-preview").frameLocator("#sketch").locator('#vc-status[data-connected="true"]').waitFor({ state: "attached" });
        await frames().frame.getByRole("heading", { name: "Gjør dere klare til møtet", exact: true }).waitFor();
        await settleProposalPaint();
        if (evidence) await page.screenshot({ path: path.join(evidence, `proposal-${viewport.width}x${viewport.height}.png`) });
      }
    });
    await check("running proposal retains real interactions, exact feedback routing and saved reopen", async () => {
      await adapter.close(); await page.close(); attach(project);
      let proposalSource = appSource.replace("Dialogmøter", "Forbered møtet").replace('<p>Oppdiktede data.</p>', '<details><summary>Forberedelser er valgfrie</summary><p>Noter det du ønsker å ta opp.</p></details>');
      proposalApp = http.createServer((_req, res) => { res.setHeader("Content-Type", "text/html; charset=utf-8"); res.end(proposalSource); });
      await new Promise(resolve => proposalApp.listen(0, "127.0.0.1", resolve));
      allowedOrigins.add(`http://127.0.0.1:${proposalApp.address().port}`);
      await context.route("**/embedded/activate", async route => {
        assert(allowedOrigins.has(new URL(route.request().url()).origin));
        const response = await route.fetch();
        const policy = response.headers()["content-security-policy"] || "";
        for (const origin of policy.match(/http:\/\/(?:localhost|127\.0\.0\.1):[0-9]+/g) || []) allowedOrigins.add(origin);
        await route.fulfill({ response });
      });
      await open({ application, workspacePath: "designs/application-workbench", create: true, title: "Forberedelser" });
      const initialApp = { source: "conversation", title: "Forbered møtet", application: { name: "Møteforslag", url: `http://127.0.0.1:${proposalApp.address().port}/demo` }, workspacePath: "designs/application-proposal", create: true };
      const live = await action("publish_proposal", initialApp);
      assert.equal(live.kind, "application"); assert.equal((await action("publish_proposal", initialApp)).id, live.id);
      await page.setViewportSize({ width: 1280, height: 800 }); await page.locator("#proposal-tab").click();
      const shell = page.frameLocator("#proposal-preview").frameLocator("#sketch"), preview = shell.frameLocator("#app-preview");
      await preview.getByRole("heading", { name: "Forbered møtet", exact: true }).waitFor();
      assert.equal(await page.locator(".app-location").isVisible(), false, "Reference status must not describe the proposal");
      assert.equal(await shell.locator(".app-location").isVisible(), true);
      await preview.getByLabel("Prøvefelt").fill("PRIVATE FIELD VALUE");
      await preview.locator("summary").click(); await preview.getByText("Noter det du ønsker å ta opp.").waitFor();
      const observed = await action("read_preview", { proposalId: live.id });
      assert.equal(observed.health.state, "no-errors-observed"); assert(!JSON.stringify(observed).includes("PRIVATE FIELD VALUE"));
      assert(observed.elements.some(item => item.text === "Noter det du ønsker å ta opp."));
      await shell.locator("#mode-change").click(); await shell.locator("#whole-page").click();
      await shell.locator("#comment-text").fill("Gi overskriften en tydeligere handling."); await shell.locator("#save-comment").click(); await shell.locator("#submit-feedback").click();
      await until(async () => (await action("read_state", { proposalId: live.id })).submission === 1, "app proposal round");
      assert.equal((await action("read_state")).submission, 0);
      await until(() => messages.length === 3, "app proposal delivery");
      assert.equal(JSON.parse(messages.at(-1).prompt.split("\n").at(-1)).proposalId, live.id);
      await shell.locator("#close-panel").click();
      proposalSource = proposalSource.replace("Forbered møtet", "Velg hva du vil forberede");
      // A normal document reload exercises the same immutable app proxy.
      await preview.locator("body").evaluate(() => location.reload());
      await preview.getByRole("heading", { name: "Velg hva du vil forberede", exact: true }).waitFor();
      if (evidence) await page.screenshot({ path: path.join(evidence, "running-proposal.png") });
      for (const viewport of [{ width: 320, height: 568 }, { width: 640, height: 400 }]) {
        await page.setViewportSize(viewport);
        const width = await shell.locator("body").evaluate(body => ({ actual: body.scrollWidth, available: innerWidth }));
        assert(width.actual <= width.available + 1, "The running proposal must fit the workshop");
        await shell.locator("#mode-change").focus(); await page.keyboard.press("Enter");
        await shell.locator("#whole-page").waitFor({ state: "visible" });
        await page.keyboard.press("Escape");
        await until(async () => await shell.locator("#mode-browse").isHidden() && await shell.locator("#mode-change").getAttribute("aria-pressed") === "false" && await shell.locator("#side-panel").isHidden(), "Escape finished selection and closed the panel");
        assert.equal(await shell.locator("#mode-change").evaluate(button => button === document.activeElement), true);
        assert.equal(await shell.locator(".app-identity").isVisible(), false, "Embedded app must not duplicate the parent title");
        assert.equal(await shell.locator(".surface-tabs").isVisible(), false, "Embedded app must not duplicate parent tabs");
        await preview.locator("body").evaluate(() => scrollTo(0, 0));
        await measureAppViewport(shell, preview, [
          { element: page.locator("#proposal-preview"), frame: page.frameLocator("#proposal-preview") },
          { element: page.frameLocator("#proposal-preview").locator("#sketch"), frame: shell },
        ], viewport, "Velg hva du vil forberede");
        if (evidence) await page.screenshot({ path: path.join(evidence, `running-proposal-${viewport.width}x${viewport.height}.png`) });
      }
      await adapter.close(); await page.close(); attach(project);
      await open({ application, workspacePath: "designs/application-workbench" });
      const saved = (await action("read_state")).proposals[0]; assert.equal(saved.needsReconnect, true);
      assert.equal((await action("publish_proposal", initialApp)).id, live.id);
      await page.locator("#proposal-tab").click(); await page.frameLocator("#proposal-preview").frameLocator("#sketch").frameLocator("#app-preview").getByRole("heading", { name: "Velg hva du vil forberede", exact: true }).waitFor();
      assert.equal((await action("read_submission", { proposalId: live.id, submission: 1 })).round.previousSession, true);
      assert.equal(messages.length, 3); assert.equal(context.pages().length, 1);
      await context.unroute("**/embedded/activate");
    });
    await check("main app keeps a usable viewport and keyboard width tools on narrow screens", async () => {
      await page.locator("#app-tab").click();
      if (await page.locator("#side-panel").isVisible()) await page.locator("#close-panel").click();
      for (const viewport of [{ width: 320, height: 568 }, { width: 640, height: 400 }]) {
        await page.setViewportSize(viewport);
        await page.locator("#view-tools summary").focus(); await page.keyboard.press("Enter");
        await page.locator("#width-mobile").click();
        assert.equal(await page.locator("#view-tools").evaluate(node => node.open), false);
        assert.equal(await page.locator("#view-tools summary").evaluate(node => node === document.activeElement), true);
        await page.keyboard.press("Enter"); await page.locator("#width-fit").click();
        await measureAppViewport(page, page.frameLocator("#app-preview"), [], viewport, "Dialogmøter");
        if (evidence) await page.screenshot({ path: path.join(evidence, `main-app-${viewport.width}x${viewport.height}.png`) });
      }
      await page.setViewportSize({ width: 1280, height: 800 });
    });
    await check("retired app workers cannot inherit a control surface when a port is reused", () => checkWorkerOriginIsolation({ browser, root }));
    assert.deepEqual(errors, []); assert.deepEqual(external, []);
  } catch (error) {
    if (evidence && page && !page.isClosed()) {
      await page.screenshot({ path: path.join(evidence, "failure.png") }).catch(() => {});
      const frameEvidence = await Promise.all(page.frames().map(async frame => ({ name: frame.name(), body: (await frame.locator("body").innerText({timeout: 1000}).catch(() => "unavailable")).slice(0,1000) })));
      fs.writeFileSync(path.join(evidence, "failure-frames.json"), JSON.stringify(frameEvidence));
      const visible = await page.locator("body").innerText().catch(() => "");
      fs.writeFileSync(path.join(evidence, "failure-visible.txt"), visible.replace(/https?:\/\/[^\s]+/g, "[local view]"));
    }
    throw error;
  } finally {
    releaseInitialState();
    await adapter?.close(); await context?.close(); await browser?.close();
    proposalApp?.closeAllConnections?.(); if (proposalApp?.listening) await new Promise(resolve => proposalApp.close(resolve));
    app.closeAllConnections?.(); if (app.listening) await new Promise(resolve => app.close(resolve));
    fs.rmSync(root, { recursive: true, force: true });
    if (evidence) fs.writeFileSync(path.join(evidence, "results.json"), JSON.stringify({ results, viewportMeasurements, errors, external, messages: messages.length, simulatedConversationHost: true, nativeAppTested: false }, null, 2) + "\n");
  }
}
main().catch(error => { console.error(String(error.stack).replace(/https?:\/\/[^\s)]+/g, "[local view]")); process.exitCode = 1; });
