#!/usr/bin/env node
"use strict";

// Isolated transport and interaction smoke with an actual browser and adapter.
// The synthetic fixture is not evidence of compatibility with a real Nav app.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const http = require("node:http");
const { pathToFileURL } = require("node:url");
const options = new Map();
for (let i = 2; i < process.argv.length; i += 1) {
  const flag = process.argv[i];
  if (flag === "--headed") { options.set(flag, true); continue; }
  if (!["--playwright-module", "--browser-channel", "--evidence-dir"].includes(flag) || !process.argv[i + 1] || process.argv[i + 1].startsWith("--")) {
    console.error("Usage: node scripts/smoke_visual_application.cjs --playwright-module PATH [--browser-channel chrome] [--evidence-dir DIRECTORY] [--headed]"); process.exit(2);
  }
  options.set(flag, process.argv[++i]);
}
let chromium;
try { ({ chromium } = require(options.get("--playwright-module") || "playwright")); }
catch { console.error("Supply an existing Playwright installation. No packages were installed."); process.exit(2); }
const evidence = options.get("--evidence-dir") && path.resolve(options.get("--evidence-dir"));
if (evidence) fs.mkdirSync(evidence, { recursive: true });
const results = [], external = [], errors = [], expectedErrors = [], failures = [];
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(read, description, timeout = 12000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await read()) return; await delay(50); }
  throw new Error(`Timed out: ${description}`);
}
async function check(name, action) {
  const start = Date.now();
  try { await action(); results.push({ name, status: "passed", durationMs: Date.now() - start }); console.log(`PASS ${name}`); }
  catch (error) { failures.push({ name, error: error.message.replace(/https?:\/\/[^\s)]+/g, "[local preview address]") }); throw error; }
}
const document = `<!doctype html><html lang="nb"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Møtedemo</title>
<style>body{font:18px/1.5 system-ui;margin:0;background:#f7f7fa;color:#1b1b24}main{max-width:700px;padding:28px;margin:auto}h1{line-height:1.2}label{display:block;font-weight:600}button,select,input{font:inherit;padding:12px;margin:8px 0;max-width:100%}section{padding:16px;margin-top:20px;background:white;border:1px solid #b7b7c1;border-radius:8px}button{background:#0645ad;color:white;border:2px solid #0645ad;border-radius:6px}a{color:#0645ad}button:focus-visible,a:focus-visible,select:focus-visible{outline:3px solid #b05e00;outline-offset:3px}</style></head>
<body><main><p>Oppdiktede data · Servicesenter Solvik</p><h1>Avtal et møte</h1><form id="meeting-form"><label for="meeting-type">Hvordan vil du møtes?</label><select id="meeting-type" name="meetingType" required><option value="">Velg møteform</option><option value="video">Videomøte</option><option value="office">På kontoret</option><option value="phone">Telefon</option></select><p id="meeting-help">Velg det som passer deg. Valget kan endres.</p><button type="submit">Fortsett</button><p id="form-result" role="status"></p></form><a id="next-page" href="/demo/neste?visning=ny">Se neste side</a><section aria-label="Første avtale"><h2>Første avtale</h2><button type="button" data-action="first">Velg tidspunkt</button></section><section aria-label="Andre avtale"><h2>Andre avtale</h2><button type="button" data-action="second">Velg tidspunkt</button></section><a id="outside-link" href="https://outside.invalid/fixture">Les utenfor demoen</a><button id="load-options" type="button">Hent ledige tider</button><p id="api-result" role="status"></p></main>
<script>document.getElementById('meeting-form').addEventListener('submit',event=>{event.preventDefault();document.getElementById('form-result').textContent='Valgt møteform: '+document.getElementById('meeting-type').value});document.getElementById('next-page').addEventListener('click',event=>{event.preventDefault();history.pushState({},'',event.currentTarget.href);document.querySelector('h1').textContent='Velg tidspunkt'});document.getElementById('load-options').addEventListener('click',async()=>{const data=await(await fetch('/demo/api')).json();document.getElementById('api-result').textContent=data.message});document.querySelectorAll('[data-action]').forEach(button=>button.addEventListener('click',()=>button.dataset.activated='true'));</script></body></html>`;

async function main() {
  const temporary = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "design-application-smoke-")));
  const project = path.join(temporary, "project"); fs.mkdirSync(project);
  const sourceFile = path.join(project, "meeting.html"); fs.writeFileSync(sourceFile, document);
  const sockets = new Set(), messages = [];
  const app = http.createServer((request, response) => {
    if (request.url === "/demo/api") { response.writeHead(200, { "Content-Type": "application/json" }); response.end(JSON.stringify({ message: "Tre ledige, oppdiktede tider" })); return; }
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" }); response.end(fs.readFileSync(sourceFile, "utf8"));
  });
  app.on("connection", socket => { sockets.add(socket); socket.once("close", () => sockets.delete(socket)); });
  let browser, context, htmlContext, adapter, page;
  try {
    await new Promise((resolve, reject) => { app.once("error", reject); app.listen(0, "127.0.0.1", resolve); });
    const { createCanvasAdapter, CANVAS_ID } = await import(pathToFileURL(path.resolve(__dirname, "../plugin/extensions/visual-companion/adapter.mjs")).href);
    let identity = { sessionId: "application-smoke", extensionId: "project:visual-companion", canvasId: CANVAS_ID, instanceId: "application" };
    adapter = createCanvasAdapter({ sessionId: identity.sessionId, projectDir: project });
    adapter.attachSession({ sessionId: identity.sessionId, capabilities: { ui: { canvases: true } }, send: async value => { messages.push(value); return "accepted-review-round"; } });
    const action = (name, input = {}) => adapter.canvas.actions.find(item => item.name === name).handler({ ...identity, input });
    const application = { name: "Møtedemo", url: `http://127.0.0.1:${app.address().port}/demo/mote?visning=ny` };
    const temporaryIdentity = { ...identity, instanceId: "temporary-application" };
    const temporaryView = await adapter.canvas.open({ ...temporaryIdentity, input: { application } });
    const allowedOrigins = new Set([new URL(application.url).origin]);
    async function allowView(view) { allowedOrigins.add(new URL(view.url).origin); }
    browser = await chromium.launch({ headless: !options.has("--headed"), ...(options.has("--browser-channel") ? { channel: options.get("--browser-channel") } : {}) });
    context = await browser.newContext({ viewport: { width: 1280, height: 800 }, reducedMotion: "reduce", serviceWorkers: "block" });
    const localRequest = route => {
      const url = new URL(route.request().url());
      const previewHost = url.protocol === "http:" && /^dv-[a-f0-9]{24}\.localhost$/.test(url.hostname);
      if ((url.protocol === "http:" && (["127.0.0.1", "localhost", "[::1]"].includes(url.hostname) || previewHost) && allowedOrigins.has(url.origin)) || ["data:", "blob:"].includes(url.protocol)) return route.continue();
      external.push(url.origin); return route.abort();
    };
    await context.route("**/*", localRequest);
    await context.routeWebSocket("**/*", socket => socket.close());
    await context.addInitScript(() => {
      window.__viewEvidence = [];
      window.addEventListener("message", event => {
        const preview = document.getElementById("app-preview");
        if (!preview || event.source !== preview.contentWindow || event.origin !== new URL(preview.src, location.href).origin) return;
        if (["design-view-ready", "design-route"].includes(event.data?.type)) window.__viewEvidence.push(event.data);
      });
    });
    context.on("page", opened => { opened.on("pageerror", error => errors.push(error.message)); opened.setDefaultTimeout(10000); });
    await context.route("**/renderer/activate", async route => {
      assert(allowedOrigins.has(new URL(route.request().url()).origin));
      const response = await route.fetch();
      if (response.ok()) {
        const value = await response.json(), previewOrigin = new URL(value.previewOrigin);
        assert.equal(previewOrigin.protocol, "http:"); assert.equal(previewOrigin.hostname, "localhost");
        allowedOrigins.add(previewOrigin.origin);
      }
      await route.fulfill({ response });
    });
    async function openWorkshop(view) {
      await allowView(view);
      assert.equal(new URL(view.url).hostname, "127.0.0.1");
      assert.match(new URL(view.url).pathname, /^\/browser\/[a-f0-9]{64}$/);
      page = await context.newPage(); await page.goto(view.url);
      assert.equal(await page.locator("#open-workshop").count(), 0, "native workshop opens directly");
      assert.equal(await page.evaluate(() => window.opener), null);
    }
    async function browse() {
      if (await page.locator("#side-panel").isVisible()) await page.locator("#close-panel").click();
      if (await page.locator("#mode-browse").isVisible()) await page.locator("#mode-browse").click();
    }
    await openWorkshop(temporaryView);
    let preview = page.frameLocator("#app-preview");
    await check("running applications default to a temporary feedback session", async () => {
      await preview.getByRole("heading", { name: "Avtal et møte", exact: true }).waitFor();
      const temporaryState = await adapter.canvas.actions.find(item => item.name === "read_state").handler({ ...temporaryIdentity, input: {} });
      assert.equal(temporaryState.workspace.storage, "temporary");
      assert.deepEqual(fs.readdirSync(project), ["meeting.html"], "default opening creates no project workspace");
      assert.equal(await page.locator("#open-history,#history-pane,#comparison-bar,#reference-view").count(), 0);
      assert.equal(temporaryState.workspace.version, undefined);
    });
    await adapter.canvas.onClose(temporaryIdentity);
    await page.close();
    const view = await adapter.canvas.open({ ...identity, input: { workspacePath: "designs/meeting", create: true, title: "Møtedemo", application } });
    await allowView(view);
    const workspaceFile = path.join(project, "designs/meeting/workspace.json");
    const initialWorkspace = fs.readFileSync(workspaceFile, "utf8");
    const savedState = () => JSON.parse(fs.readFileSync(workspaceFile, "utf8"));
    await openWorkshop(view); preview = page.frameLocator("#app-preview");
    await check("direct workshop has keyboard access without a connection panel or popup", async () => {
      await preview.getByRole("heading", { name: "Avtal et møte", exact: true }).waitFor();
      for (const viewport of [{ width: 320, height: 568 }, { width: 640, height: 400 }]) {
        await page.setViewportSize(viewport);
        assert.equal(await page.locator("#app-preview").count(), 1);
        assert.equal(context.pages().length, 1);
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await page.locator("#mode-change").focus();
        assert.equal(await page.evaluate(() => document.activeElement.id), "mode-change");
        if (evidence) await page.screenshot({ path: path.join(evidence, `native-${viewport.width}x${viewport.height}.png`) });
      }
      await page.setViewportSize({ width: 1280, height: 800 });
      assert.equal(messages.length, 0);
    });
    await check("a duplicate browser address cannot acquire or replace the active document", async () => {
      const duplicate = await context.newPage(); await duplicate.goto(page.url());
      await until(async () => await duplicate.locator("#app-status").textContent() === "Visningen er ikke aktiv", "duplicate renderer denied");
      assert.equal(await duplicate.locator("iframe[src]").count(), 0);
      assert.equal(await duplicate.locator("#stage-title").textContent(), "Åpne Designverksted igjen fra samtalen");
      assert.equal((await action("read_state")).application.connection.state, "connected");
      assert.equal(messages.length, 0); await duplicate.close();
    });
    await check("exact app route and actual form are visible", async () => {
      await preview.getByRole("heading", { name: "Avtal et møte", exact: true }).waitFor();
      await until(async () => (await action("read_state")).application?.route === "/demo/mote?visning=ny", "start route retained");
      assert.equal(await preview.locator("#meeting-type").inputValue(), "");
    });
    await check("diagnostic messages require the current iframe, origin, epoch and view", async () => {
      await until(async () => (await action("read_state")).application.previewStatus.state === "ready", "current view ready");
      const previewOrigin = await preview.locator("body").evaluate(() => location.origin);
      await page.evaluate(origin => {
        const ready = [...window.__viewEvidence].reverse().find(item => item.type === "design-view-ready");
        const frame = document.getElementById("app-preview").contentWindow;
        const data = { type: "design-view-error", epoch: ready.epoch, view: ready.view, reason: "preview-cookie-unavailable", httpStatus: 403 };
        const dispatch = (body, source = frame, eventOrigin = origin) => window.dispatchEvent(new MessageEvent("message", { source, origin: eventOrigin, data: body }));
        dispatch(data, window); dispatch(data, frame, location.origin);
        dispatch({ ...data, epoch: "0".repeat(32) }); dispatch({ ...data, view: "0".repeat(32) });
        dispatch({ ...data, httpStatus: 200 }); dispatch({ ...data, reason: "unknown" });
        dispatch({ ...data, health: { script: 0, module: 0, rejection: 0 } });
      }, previewOrigin);
      await delay(100);
      assert.equal(await page.locator("#stage-message").isVisible(), false);
      assert.equal((await action("read_state")).application.previewStatus.state, "ready");
    });
    await check("selection and route storms are volatile until deliberate saving", async () => {
      assert.equal(savedState().screens.length, 0); assert.equal(savedState().comments.length, 0);
      const frame = preview.locator("body");
      await frame.evaluate(() => { for (let i = 0; i < 35; i++) history.pushState({}, "", "/demo/mote?visning=side-" + i); history.pushState({}, "", "/demo/mote?visning=siste"); });
      await until(async () => (await action("read_state")).application.route === "/demo/mote?visning=siste", "last observed route");
      await page.locator("#mode-change").click(); await preview.locator('[data-action="first"]').click();
      await page.locator("#comment-text").fill("Et utkast som ikke skal lagres av observasjon.");
      assert.equal(fs.readFileSync(workspaceFile, "utf8"), initialWorkspace);
      await page.locator("#clear-draft").click(); await browse();
      await frame.evaluate(() => history.pushState({}, "", "/demo/mote?visning=ny"));
      await until(async () => (await action("read_state")).application.route === "/demo/mote?visning=ny", "original observed route");
      assert.equal(fs.readFileSync(workspaceFile, "utf8"), initialWorkspace);
    });
    await check("application surface exposes no source, reference or version capabilities", async () => {
      const names = adapter.canvas.actions.map(item => item.name);
      for (const name of ["read_source", "read_source_changes", "prepare_source_change", "apply_source_change", "restore_source_change", "abandon_source_change", "register_reference", "list_references"]) assert(!names.includes(name), name);
      for (const [name, input] of [["list_history", {}], ["read_revision", { revisionId: 1, part: "html" }], ["restore_revision", { revisionId: 1, expectedRevision: 0 }], ["publish_revision", { expectedScreen: (await action("read_state")).screen, filename: "replacement.html", html: "<!doctype html><h1>Not a running app</h1>" }]]) await assert.rejects(action(name, input), error => error.status === 409);
      assert.equal(savedState().workspace.mode, "feedback");
      assert.equal(savedState().workspace.history, undefined); assert.equal(savedState().workspace.version, undefined);
      for (const directory of ["revisions", "changes", "references"]) assert(!fs.existsSync(path.join(project, "designs/meeting", directory)));
      assert.equal(fs.readFileSync(sourceFile, "utf8"), document);
    });
    await check("Prøv retains validation, field state and API calls", async () => {
      await preview.getByRole("button", { name: "Fortsett", exact: true }).click();
      assert.equal(await preview.locator("#form-result").textContent(), "");
      await preview.locator("#meeting-type").selectOption("video");
      await preview.getByRole("button", { name: "Fortsett", exact: true }).click();
      await until(async () => (await preview.locator("#form-result").textContent()).includes("video"), "form behaviour");
      await preview.getByRole("button", { name: "Hent ledige tider" }).click();
      await until(async () => (await preview.locator("#api-result").textContent()).includes("Tre ledige"), "actual API response");
    });
    await check("selection prevents the underlying action and saves a precise target", async () => {
      await page.locator("#mode-change").click();
      await preview.locator('[data-action="second"]').click();
      await page.locator("#comment-text").waitFor();
      assert.equal(await preview.locator('[data-action="second"]').getAttribute("data-activated"), null);
      assert.equal(await page.locator("#mode-browse").getAttribute("aria-pressed"), "true", "selection is a one-shot action");
      await page.locator("#comment-text").fill("Gjør tidspunktet tydeligere i den andre avtalen.");
      await page.locator("#save-comment").click();
      await until(async () => await page.locator("#feedback-count").textContent() === "1", "one pending comment");
      assert.equal(messages.length, 0);
      assert.equal(savedState().screens.length, 1); assert.equal(savedState().comments.length, 1); assert.equal(savedState().revision, 1);
      assert.equal(await page.evaluate(() => document.activeElement.id), "panel-title");
    });
    await check("lost save response retries the same intent once", async () => {
      await page.locator("#mode-change").click();
      await preview.locator("#meeting-type").click();
      await page.locator("#comment-text").fill("Prøv radioknapper med de samme tre verdiene.");
      let lost = false;
      await page.route("**/comments", async route => {
        if (route.request().method() !== "POST" || lost) { await route.continue(); return; }
        lost = true; await route.fetch(); await route.abort("failed");
      });
      await page.locator("#save-comment").click();
      await until(async () => await page.locator("#save-comment").textContent() === "Prøv samme lagring igjen", "explicit retry");
      assert.equal(await page.evaluate(() => document.activeElement.id), "save-comment");
      await page.locator("#save-comment").click();
      await until(async () => await page.locator("#feedback-count").textContent() === "2", "two distinct comments");
      await page.unroute("**/comments"); assert.equal(messages.length, 0);
    });
    const placeCard = () => page.locator(".feedback-card").first();
    const placeButton = () => placeCard().locator(".show-location");
    const placeNote = () => placeCard().locator(".location-notice");
    const placeTarget = preview.locator('[data-action="second"]');
    const layoutSettled = () => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await check("Vis stedet scrolls without app actions, field changes, feedback writes or lost draft", async () => {
      await page.locator("#mode-change").click(); await page.locator("#whole-page").click();
      await page.locator("#comment-text").fill("Uferdig innspill som skal beholdes under gjenfinning.");
      await page.locator("#open-feedback").click();
      await preview.locator("body").evaluate(() => {
        window.__locationEffects = { click: 0, focus: 0, input: 0, change: 0, submit: 0 };
        for (const type of Object.keys(window.__locationEffects)) document.addEventListener(type, () => window.__locationEffects[type]++, true);
        window.scrollTo(0, 0);
      });
      const before = fs.readFileSync(workspaceFile, "utf8");
      await placeButton().focus(); await page.keyboard.press("Enter");
      await until(async () => (await placeNote().textContent()).startsWith("Stedet er markert"), "saved place located");
      assert.equal(await preview.locator(".location-outline").isVisible(), true);
      await placeTarget.hover();
      assert.equal(await preview.locator(".outline:visible").count(), 1, "only the requested place is outlined");
      assert.equal(await page.locator("#mode-change").getAttribute("aria-pressed"), "false");
      assert.deepEqual(await preview.locator("body").evaluate(() => window.__locationEffects), { click: 0, focus: 0, input: 0, change: 0, submit: 0 });
      assert.equal(await preview.locator("#meeting-type").inputValue(), "video");
      assert.equal(await placeTarget.getAttribute("data-activated"), null);
      assert.equal(await page.evaluate(() => document.activeElement.dataset.focusKey), "location");
      assert.equal(await page.locator("#comment-text").inputValue(), "Uferdig innspill som skal beholdes under gjenfinning.");
      assert.equal(fs.readFileSync(workspaceFile, "utf8"), before);
    });
    await check("narrow Vis stedet reveals the target and returns to feedback with one action", async () => {
      for (const viewport of [{ width: 375, height: 812 }, { width: 320, height: 568 }, { width: 640, height: 400 }, { width: 568, height: 320 }]) {
        await page.setViewportSize(viewport); await layoutSettled();
        if (await page.locator("#location-return").isVisible()) await page.locator("#location-return").click();
        await placeButton().focus(); await page.keyboard.press("Enter");
        await page.locator("#location-return").waitFor();
        assert.equal(await page.locator("#side-panel").isVisible(), false);
        assert.equal(await page.locator("#open-feedback").getAttribute("aria-expanded"), "false");
        assert.equal(await page.evaluate(() => document.activeElement.id), "location-return");
        await until(async () => {
          const target = await placeTarget.boundingBox(), frame = await page.locator("#app-preview").boundingBox();
          return target && frame && target.y >= frame.y && target.y + target.height <= frame.y + frame.height;
        }, "located target fits the resized app frame");
        const target = await placeTarget.boundingBox(), controls = await page.locator("#workspace-tools").boundingBox();
        assert(target.y + target.height <= controls.y, "the location controls must not cover the target");
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "no horizontal overflow");
        if (evidence) await page.screenshot({ path: path.join(evidence, `location-${viewport.width}x${viewport.height}.png`) });
        await page.keyboard.press("Escape");
        assert.equal(await page.locator("#side-panel").isVisible(), true);
        assert.equal(await page.evaluate(() => document.activeElement.dataset.focusKey), "location");
        await placeButton().click(); await page.locator("#location-return").waitFor();
        await page.locator("#open-feedback").click();
        assert.equal(await page.locator("#side-panel").isVisible(), true, "Innspill opens on its first click");
        assert.equal(await page.locator("#open-feedback").getAttribute("aria-expanded"), "true");
        assert.equal(await page.locator("#comment-text").inputValue(), "Uferdig innspill som skal beholdes under gjenfinning.");
        assert.equal(await preview.locator("#meeting-type").inputValue(), "video");
      }
    });
    await check("Ctrl+Enter and Cmd+Enter cannot save an editor hidden by Vis stedet", async () => {
      await page.setViewportSize({ width: 375, height: 812 }); await layoutSettled();
      await placeCard().locator(".edit-comment").click();
      await placeCard().locator(".edit-text").fill("Bare et uferdig redigeringsutkast.");
      const before = fs.readFileSync(workspaceFile, "utf8");
      await placeButton().click(); await page.locator("#location-return").waitFor();
      await page.keyboard.press("Control+Enter"); await page.keyboard.press("Meta+Enter"); await delay(150);
      assert.equal(fs.readFileSync(workspaceFile, "utf8"), before, "hidden editing never mutates feedback");
      await page.locator("#location-return").click();
      assert.equal(await placeCard().locator(".edit-text").inputValue(), "Bare et uferdig redigeringsutkast.");
      await placeCard().getByRole("button", { name: "Avbryt redigering", exact: true }).click();
      await page.setViewportSize({ width: 1280, height: 800 }); await layoutSettled();
      await page.locator("#resume-draft").click(); await page.locator("#clear-draft").click();
      await browse();
    });
    await check("queued feedback editing and removal keep meaningful focus", async () => {
      await page.locator("#mode-change").click(); await page.locator("#whole-page").click();
      await page.locator("#comment-text").fill("Et tredje innspill for å prøve redigering.");
      assert.equal(savedState().comments.length, 2);
      await page.locator("#save-comment").click();
      await until(async () => await page.locator("#feedback-count").textContent() === "3", "third queued comment");
      assert.equal(await page.evaluate(() => document.activeElement.id), "panel-title");
      const card = page.locator(".feedback-card").last();
      await card.locator(".edit-comment").click(); await card.locator(".edit-text").fill("Oppdatert tredje innspill.");
      await card.locator(".edit-text").press("Control+Enter");
      await until(async () => await card.locator(".feedback-text").textContent() === "Oppdatert tredje innspill.", "saved edit");
      assert.equal(await page.evaluate(() => document.activeElement.dataset.focusKey), "edit");
      await card.locator(".edit-comment").click(); await card.getByRole("button", { name: "Avbryt redigering", exact: true }).click();
      assert.equal(await page.evaluate(() => document.activeElement.dataset.focusKey), "edit");
      await card.locator(".remove-comment").click();
      await until(async () => await page.locator("#feedback-count").textContent() === "2", "removed only extra feedback");
      assert(await page.evaluate(() => { const el = document.activeElement; return el !== document.body && document.getElementById("feedback-pane").contains(el) && !el.disabled && el.getClientRects().length > 0; }));
      assert.equal(await page.locator("#submit-feedback").textContent(), "Send alle 2 innspill");
      assert.equal(messages.length, 0);
    });
    await check("one deliberate submission reaches the exact round and receives a reply", async () => {
      // WebKit does not necessarily focus buttons on pointer activation.
      // Exercise that path in every browser, including the Chromium CI run.
      await page.locator("#submit-feedback").evaluate(button => {
        document.activeElement.blur();
        button.addEventListener("mousedown", event => event.preventDefault(), { once: true });
      });
      await page.locator("#submit-feedback").click();
      await until(() => messages.length === 1, "single queued round");
      await until(async () => await page.locator("#sent-tab").getAttribute("aria-selected") === "true", "confirmed sent tab");
      assert.equal(await page.evaluate(() => document.activeElement.id), "sent-tab");
      const round = await action("read_submission", { submission: 1 });
      const comments = round.items.filter(item => item.type === "comment");
      assert.equal(comments.length, 2);
      assert.equal(comments[0].value.applicationContext.route, "/demo/mote?visning=ny");
      assert.match(comments[0].value.applicationContext.target.path, /section:nth-of-type\(2\)/);
      assert.equal(comments[1].value.applicationContext.target.text, "");
      await action("review_submission", { submission: 1, status: "answered", reply: "Begge ønskene er vurdert. Ingen kildeendring er gjort i denne prøven." });
      await page.getByText("Begge ønskene er vurdert.", { exact: false }).waitFor();
      await placeButton().click();
      await until(async () => (await placeNote().textContent()).startsWith("Stedet er markert"), "sent feedback retains Vis stedet");
      assert.equal(await preview.locator(".location-outline").isVisible(), true);
    });
    await check("draft survives mode changes and closing the panel", async () => {
      await page.locator("#mode-change").click(); await page.locator("#whole-page").click();
      await page.locator("#comment-text").fill("Halvskrevet ønske som skal beholdes.");
      await browse();
      await page.locator("#resume-draft").click();
      assert.equal(await page.locator("#comment-text").inputValue(), "Halvskrevet ønske som skal beholdes.");
      await page.locator("#comment-text").press("Escape");
      assert.equal(await page.locator("#side-panel").isVisible(), false);
      await page.locator("#resume-draft").click();
      assert.equal(await page.locator("#comment-text").inputValue(), "Halvskrevet ønske som skal beholdes.");
      await page.locator("#clear-draft").click();
    });
    await check("navigation remains live and preserves the selected form state", async () => {
      await browse();
      await preview.getByRole("link", { name: "Se neste side" }).click();
      await until(async () => (await action("read_state")).application?.route === "/demo/neste?visning=ny", "navigation route");
      assert.equal(await preview.locator("#meeting-type").inputValue(), "video");
    });
    await check("external link is explained without leaving the local app", async () => {
      await preview.locator("#outside-link").click();
      await page.locator("#navigation-message").waitFor();
      assert.equal(await page.evaluate(() => document.activeElement.id), "return-to-app");
      await page.getByRole("button", { name: "Tilbake til appen", exact: true }).click();
      assert.equal(await page.evaluate(() => document.activeElement.id), "app-preview");
      assert.equal(await preview.locator("#meeting-type").inputValue(), "video");
      assert.equal(external.length, 0);
    });
    for (const viewport of [{ width: 1280, height: 800 }, { width: 375, height: 812 }, { width: 320, height: 568 }, { width: 640, height: 400 }]) {
      await check(`controls and feedback panel fit ${viewport.width}x${viewport.height}`, async () => {
        await page.setViewportSize(viewport); await page.locator("#open-feedback").click();
        if (!(await page.locator("#feedback-pane").isVisible())) await page.locator("#open-feedback").click();
        await delay(100);
        const layout = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth,
          controls: ["mode-browse", "mode-change", "open-feedback", "close-panel"].filter(id => document.getElementById(id).getClientRects().length).map(id => { const r = document.getElementById(id).getBoundingClientRect(); return { id, x: r.x, y: r.y, right: r.right, bottom: r.bottom, width: r.width, height: r.height }; }) }));
        assert(layout.scroll <= layout.width + 1, "control surface must not scroll sideways");
        for (const control of layout.controls) assert(control.x >= -1 && control.y >= -1 && control.right <= viewport.width + 1 && control.bottom <= viewport.height + 1 && control.width >= 24 && control.height >= 24, `visible control: ${control.id}`);
        if (viewport.width <= 760) {
          assert.equal(await page.locator("#side-panel").getAttribute("aria-modal"), "true");
          assert.equal(await page.locator("#workspace-tools").evaluate(el => el.inert), true);
          for (let index = 0; index < 12; index++) { await page.keyboard.press("Tab"); assert(await page.evaluate(() => document.getElementById("side-panel").contains(document.activeElement))); }
          await page.keyboard.press("Shift+Tab"); assert(await page.evaluate(() => document.getElementById("side-panel").contains(document.activeElement)));
        }
        if (evidence) await page.screenshot({ path: path.join(evidence, `feedback-${viewport.width}x${viewport.height}.png`) });
        await page.keyboard.press("Escape");
        assert.equal(await page.evaluate(() => document.activeElement.id), "open-feedback");
      });
    }
    await check("forced-colors retains visible focus and selected controls", async () => {
      await page.setViewportSize({ width: 640, height: 400 }); await page.emulateMedia({ forcedColors: "active" });
      await page.locator("#open-feedback").click(); await page.locator("#close-panel").focus();
      await page.keyboard.press("Tab"); await page.keyboard.press("Shift+Tab");
      assert.equal(await page.evaluate(() => document.activeElement.id), "close-panel");
      assert(await page.evaluate(() => matchMedia("(forced-colors: active)").matches));
      const focus = await page.locator("#close-panel").evaluate(el => ({ width: getComputedStyle(el).outlineWidth, style: getComputedStyle(el).outlineStyle }));
      assert.notEqual(focus.width, "0px"); assert.notEqual(focus.style, "none");
      if (evidence) await page.screenshot({ path: path.join(evidence, "forced-colors-640x400.png") });
      await page.keyboard.press("Escape"); await page.emulateMedia({ forcedColors: "none" });
    });
    await check("reopen preserves submitted feedback and does not resend", async () => {
      await adapter.canvas.onClose(identity);
      await assert.rejects(adapter.canvas.open(identity), /expired|closed/i);
      identity = { ...identity, instanceId: "application-reopened" };
      const reopened = await adapter.canvas.open({ ...identity, input: { application, workspacePath: "designs/meeting" } });
      await page.close();
      await openWorkshop(reopened); preview = page.frameLocator("#app-preview");
      await preview.getByRole("heading", { name: "Avtal et møte", exact: true }).waitFor();
      assert.equal((await action("read_state")).submission, 1); assert.equal(messages.length, 1);
      assert.equal((await action("read_state")).workspace.storage, "project");
      await page.locator("#open-feedback").click(); await page.locator("#sent-tab").click(); await page.locator(".feedback-card").first().waitFor();
      assert.equal(await page.locator(".feedback-card").count(), 2);
      assert.equal(fs.readFileSync(sourceFile, "utf8"), document);
    });
    await check("lost preview access rejects stale evidence and retry preserves the saved round and draft", async () => {
      await page.setViewportSize({ width: 1280, height: 800 });
      if (await page.locator("#side-panel").isVisible()) await page.locator("#close-panel").click();
      await page.locator("#mode-change").click(); await page.locator("#whole-page").click();
      await page.locator("#comment-text").fill("Uferdig innspill skal beholdes ved gjenåpning.");
      await page.keyboard.press("Escape");
      const originalState = fs.readFileSync(workspaceFile, "utf8");
      const oldMessages = await page.evaluate(() => window.__viewEvidence.slice(-2));
      const previewOrigin = await preview.locator("body").evaluate(() => location.origin);
      await context.clearCookies({ domain: new URL(previewOrigin).hostname });
      await preview.locator("body").evaluate(() => location.reload());
      await page.locator("#retry-preview").waitFor({ state: "visible" });
      await until(async () => (await action("read_state")).application.previewStatus.reason === "preview-cookie-unavailable", "validated cookie failure reaches diagnostics");
      const failed = (await action("read_state")).application;
      assert.equal(failed.transportStatus.state, "unavailable"); assert.equal(failed.transportStatus.httpStatus, 403);
      assert.equal(failed.previewStatus.httpStatus, 403); assert.equal(failed.applicationHealth, undefined);
      assert.equal(await page.locator("#stage-title").textContent(), "Appvisningen mangler tilgang");
      assert.equal(await page.locator("#whole-page").isDisabled(), true);
      await page.evaluate(({ oldMessages, previewOrigin }) => {
        for (const data of oldMessages) window.dispatchEvent(new MessageEvent("message", { source: document.getElementById("app-preview").contentWindow, origin: previewOrigin, data }));
      }, { oldMessages, previewOrigin });
      assert.equal(await page.locator("#stage-message").isVisible(), true);
      assert.equal(await page.locator("#whole-page").isDisabled(), true);
      assert.equal(await page.locator("#comment-text").inputValue(), "Uferdig innspill skal beholdes ved gjenåpning.");
      if (evidence) await page.screenshot({ path: path.join(evidence, "lost-preview-access.png") });
      await page.evaluate(() => { window.__oldFrame = document.getElementById("app-preview"); });
      await page.locator("#retry-preview").click();
      await page.locator("#stage-message").waitFor({ state: "hidden" });
      await until(() => page.locator("#whole-page").isEnabled(), "fresh validated route");
      await page.evaluate(() => window.__oldFrame.dispatchEvent(new Event("load")));
      assert.equal(await page.locator("#stage-message").isVisible(), false, "retired iframe load cannot reset readiness");
      assert.equal(fs.readFileSync(workspaceFile, "utf8"), originalState);
      assert.equal(messages.length, 1);
      await page.locator("#resume-draft").click();
      assert.equal(await page.locator("#comment-text").inputValue(), "Uferdig innspill skal beholdes ved gjenåpning.");
      assert.equal(await page.locator("#save-comment").isEnabled(), true);
      await page.locator("#clear-draft").click(); await browse();
    });
    await check("a delayed old route cannot label or block feedback on the next document", async () => {
      let release, captured;
      const hold = new Promise(resolve => { release = resolve; });
      const arrived = new Promise(resolve => { captured = resolve; });
      const handler = async route => {
        if (route.request().postDataJSON()?.route !== "/demo/slow") return route.fallback();
        const response = await route.fetch(); captured(); await hold; await route.fulfill({ response });
      };
      await context.route("**/view", handler);
      try {
        await preview.locator("body").evaluate(() => history.pushState({}, "", "/demo/slow"));
        await arrived;
        assert.equal(await page.locator("#whole-page").isDisabled(), true);
        assert.equal(await page.locator("#pick-part").isDisabled(), true);
        assert.notEqual(await page.locator("#app-route").textContent(), "/demo/slow");
        await preview.locator("body").evaluate(() => { location.href = "/demo/fresh"; });
        await until(async () => (await page.evaluate(() => window.__viewEvidence.filter(item => item.type === "design-route").at(-1)?.route)) === "/demo/fresh", "new document route evidence");
        release();
        await until(async () => (await page.locator("#app-route").textContent()) === "/demo/fresh" && await page.locator("#whole-page").isEnabled(), "only the new route becomes selectable");
        assert.equal(await page.locator("#global-message").isVisible(), false, "old response causes no stale error banner");
        assert.equal(messages.length, 1);
      } finally { release(); await context.unroute("**/view", handler); }
    });
    await check("late inspector startup recovers after the deadline without reloading or losing feedback", async () => {
      const originalState = fs.readFileSync(workspaceFile, "utf8");
      const handler = async route => {
        const response = await route.fetch();
        await route.fulfill({ response, body: `setTimeout(() => {${await response.text()}\n}, 7000);` });
      };
      await context.route("**/inspect.js", handler);
      try {
        await preview.locator("body").evaluate(() => location.reload());
        await page.locator("#retry-preview").waitFor({ state: "visible" });
        assert.equal(await page.locator("#whole-page").isDisabled(), true);
        await page.locator("#stage-message").waitFor({ state: "hidden" });
        await until(() => page.locator("#whole-page").isEnabled(), "late inspector validates its current route");
        assert.equal(fs.readFileSync(workspaceFile, "utf8"), originalState);
        assert.equal(messages.length, 1);
      } finally { await context.unroute("**/inspect.js", handler); }
    });
    await check("blocked navigation retains a usable app or offers recovery", async () => {
      for (const method of ["script", "form"]) {
        await preview.locator("body").evaluate((_, method) => {
          window.__navigationProbe = method;
          if (method === "script") location.href = "https://outside.invalid/script";
          else { const form = document.createElement("form"); form.action = "https://outside.invalid/form"; document.body.append(form); form.submit(); }
        }, method);
        let needsRecovery = true;
        try { await page.locator("#retry-preview").waitFor({ state: "visible", timeout: 8000 }); }
        catch (error) { if (error.name !== "TimeoutError") throw error; needsRecovery = false; }
        if (needsRecovery) {
          assert.equal(await page.locator("#whole-page").isDisabled(), true);
          await page.locator("#retry-preview").click();
          await page.locator("#stage-message").waitFor({ state: "hidden" });
          await until(() => page.locator("#whole-page").isEnabled(), "recovered route");
        } else {
          // Some engines reject the navigation before replacing the document.
          // Prove it is the same usable app, not an undetected blank/error page.
          assert.equal(await preview.locator("body").evaluate(() => window.__navigationProbe), method);
          await preview.getByRole("heading", { name: "Avtal et møte", exact: true }).waitFor();
          await preview.getByLabel("Hvordan vil du møtes?", { exact: true }).selectOption("phone");
          await preview.getByRole("button", { name: "Fortsett", exact: true }).click();
          assert.equal(await preview.locator("#form-result").textContent(), "Valgt møteform: phone");
          assert.equal(await page.locator("#whole-page").isEnabled(), true);
          assert.equal(await page.locator("#stage-message").isVisible(), false);
        }
      }
      await preview.locator("body").evaluate(() => {
        const host = document.createElement("div"); document.body.append(host);
        host.attachShadow({ mode: "open" }).innerHTML = '<a href="https://outside.invalid/shadow">Ekstern skyggelenke</a>';
      });
      await preview.getByRole("link", { name: "Ekstern skyggelenke" }).click();
      await page.locator("#navigation-message").waitFor();
      await page.locator("#return-to-app").click();
      assert.equal(await page.locator("#stage-message").isVisible(), false);
      assert.equal(await page.locator("#whole-page").isEnabled(), true);
      assert.equal(messages.length, 1);
    });
    await check("explicit close and fresh reopen reject the old writer and retain unsaved text", async () => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.locator("#mode-change").click(); await page.locator("#whole-page").click();
      const draft = "Ulagret ønske før ny åpning skal kunne kopieres.";
      await page.locator("#comment-text").fill(draft);
      const oldPage = page, closedIdentity = identity, before = fs.readFileSync(workspaceFile, "utf8");
      await adapter.canvas.onClose(closedIdentity);
      await assert.rejects(adapter.canvas.actions.find(item => item.name === "read_state").handler({ ...closedIdentity, input: {} }), /closed|unknown/i);
      await until(async () => /Forbindelsen må sjekkes|Denne visningen er ikke aktiv/.test(await oldPage.locator("#app-status").textContent()), "closed workshop reports lost connection");
      assert.equal(await oldPage.locator("#comment-text").inputValue(), draft);
      identity = { ...identity, instanceId: "application-reconnected" };
      await openWorkshop(await adapter.canvas.open({ ...identity, input: { application, workspacePath: "designs/meeting" } }));
      preview = page.frameLocator("#app-preview");
      await preview.getByRole("heading", { name: "Avtal et møte", exact: true }).waitFor();
      assert.equal(fs.readFileSync(workspaceFile, "utf8"), before); assert.equal(messages.length, 1);
      oldPage.on("dialog", dialog => dialog.accept()); await oldPage.close();
      assert.equal(context.pages().length, 1);
    });
    // Compatibility for independently opened sketches. The recommended app-to-
    // proposal workflow stays in one workshop and is covered by smoke_visual_workbench.
    await check("an independently opened HTML sketch keeps its own review and lifecycle", async () => {
      const proposalIdentity = { ...identity, instanceId: "meeting-proposal" };
      const proposalAction = (name, input = {}) => adapter.canvas.actions.find(item => item.name === name).handler({ ...proposalIdentity, input });
      let proposal = await adapter.canvas.open({ ...proposalIdentity, input: { workspacePath: "designs/meeting-proposal", create: true, title: "Møtevalg – forslag" } });
      const proposalHtml = title => `<style>main{max-width:620px;margin:24px auto;padding:20px;font:18px/1.5 system-ui}label{display:block;padding:10px}button{padding:12px;font:inherit}</style><main><p>Forslag med oppdiktede data. Appens validering er ikke simulert.</p><h1>${title}</h1><fieldset><legend>Hvordan vil du møtes?</legend><label><input type="radio" name="meeting" value="video"> Videomøte</label><label><input type="radio" name="meeting" value="office"> På kontoret</label><label><input type="radio" name="meeting" value="phone"> Telefon</label></fieldset><button type="button">Se ledige tidspunkt</button></main>`;
      const publish = async (number, title) => proposalAction("publish_revision", { expectedScreen: (await proposalAction("read_state")).screen, filename: `meeting-${number}.html`, html: proposalHtml(title) });
      await publish(1, "Velg møteform"); allowedOrigins.add(new URL(proposal.url).origin);
      // The proposal models the separate embedded renderer. Playwright's
      // serviceWorkers:"block" initialization itself throws in an opaque HTML
      // sandbox, even for an empty document; keep the normal HTML-smoke context.
      htmlContext = await browser.newContext({ viewport: { width: 1280, height: 800 }, reducedMotion: "reduce" });
      await htmlContext.route("**/*", localRequest);
      await htmlContext.routeWebSocket("**/*", socket => socket.close());
      htmlContext.on("page", opened => { opened.on("pageerror", error => errors.push(error.message)); opened.setDefaultTimeout(10000); });
      const sketchPage = await htmlContext.newPage(); await sketchPage.goto(proposal.url);
      let sketch = sketchPage.frameLocator("#vc-preview"), ui = sketch.locator("[data-visual-feedback]");
      await sketch.getByRole("heading", { name: "Velg møteform", exact: true }).waitFor();
      await sketch.getByRole("radio", { name: "Videomøte", exact: true }).check();
      assert.equal(await sketch.getByRole("radio", { name: "Videomøte", exact: true }).isChecked(), true);
      await action("review_submission", { submission: 1, status: "answered", reply: "Se Møtevalg – forslag, versjon 1 i samtalen. Forslaget følger opp runde 1 på /demo/mote?visning=ny med radioknapper. Prøv valgene og gi innspill i skissen. Appen er uendret." });
      await page.locator("#open-feedback").click(); await page.locator("#sent-tab").click();
      await page.getByText("Se Møtevalg – forslag, versjon 1", { exact: false }).waitFor();
      assert.equal((await action("read_state")).application.connection.state, "connected");
      await ui.locator('[data-action="comment"]').click(); await sketch.getByRole("heading", { name: "Velg møteform", exact: true }).click();
      await ui.getByLabel("Hva vil du endre?", { exact: true }).fill("Bruk overskriften Hvordan vil du møtes?");
      await ui.locator('.composer [data-action="save"]').click();
      await until(() => messages.length === 2, "one distinct proposal round");
      assert.equal(JSON.parse(messages[1].prompt.split("\n").at(-1)).instanceId, proposalIdentity.instanceId);
      const round = await proposalAction("read_submission", { submission: 1 });
      assert(round.items.some(item => item.type === "comment" && item.value.text.includes("Hvordan vil du møtes?")));
      await publish(2, "Hvordan vil du møtes?");
      await proposalAction("review_submission", { submission: 1, status: "answered", reply: "Overskriften er oppdatert i versjon 2. Appen er fortsatt uendret." });
      const refresh = ui.locator('[data-action="refresh"]');
      const revisedHeading = sketch.getByRole("heading", { name: "Hvordan vil du møtes?", exact: true });
      await until(async () => await revisedHeading.isVisible() || await refresh.isVisible() && await refresh.isEnabled(), "new sketch available");
      if (!(await revisedHeading.isVisible())) await refresh.click();
      await revisedHeading.waitFor();
      if (evidence) await sketchPage.screenshot({ path: path.join(evidence, "html-proposal-iteration.png") });
      await adapter.canvas.onClose(proposalIdentity); await sketchPage.close();
      assert.equal((await action("read_state")).application.connection.state, "connected", "closing proposal leaves app connection alone");
      proposal = await adapter.canvas.open(proposalIdentity); allowedOrigins.add(new URL(proposal.url).origin);
      const reopenedSketch = await htmlContext.newPage(); await reopenedSketch.goto(proposal.url);
      await reopenedSketch.frameLocator("#vc-preview").getByRole("heading", { name: "Hvordan vil du møtes?", exact: true }).waitFor();
      assert.equal((await proposalAction("read_state")).submission, 1); assert.equal(messages.length, 2);
      assert.equal(fs.readFileSync(sourceFile, "utf8"), document, "proposal never changes original fixture code");
      await adapter.canvas.onClose(proposalIdentity); await reopenedSketch.close();
    });
    await check("a delayed submission respects moved focus and a closed panel", async () => {
      const previous = page;
      for (const closePanel of [false, true]) {
        const focusIdentity = { ...identity, instanceId: `submission-focus-${closePanel}` };
        let release = () => {};
        try {
          await openWorkshop(await adapter.canvas.open({ ...focusIdentity, input: { application } }));
          await page.frameLocator("#app-preview").getByRole("heading", { name: "Avtal et møte", exact: true }).waitFor();
          await page.locator("#mode-change").click(); await page.locator("#whole-page").click();
          await page.locator("#comment-text").fill("Et eget innspill for forsinket sending.");
          await page.locator("#save-comment").click();
          await page.locator("#submit-feedback").waitFor({ state: "visible" });
          let received = false;
          const held = new Promise(resolve => { release = resolve; });
          await page.route("**/submit", async route => { received = true; await held; await route.continue(); });
          const before = messages.length;
          await page.locator("#submit-feedback").focus(); await page.keyboard.press("Enter");
          await until(() => received, "submission request starts");
          if (closePanel) await page.keyboard.press("Escape");
          const destination = closePanel ? "open-feedback" : "close-panel";
          await page.locator(`#${destination}`).focus();
          release();
          await until(async () => await page.locator("#sent-tab").getAttribute("aria-selected") === "true", "delayed send completes");
          assert.equal(await page.evaluate(() => document.activeElement.id), destination);
          assert.equal(await page.locator("#side-panel").isVisible(), !closePanel);
          await until(() => messages.length === before + 1, "one delayed round");
        } finally {
          release(); await page.unrouteAll({ behavior: "wait" });
          await adapter.canvas.onClose(focusIdentity); await page.close(); page = previous;
        }
      }
    });
    await check("draft recovery ignores cloned tabs and malformed cached data", async () => {
      const previous = page, recoveryIdentity = { ...identity, instanceId: "draft-recovery-boundary" };
      const before = messages.length;
      let clone;
      try {
        await openWorkshop(await adapter.canvas.open({ ...recoveryIdentity, input: { application } }));
        await page.frameLocator("#app-preview").getByRole("heading", { name: "Avtal et møte", exact: true }).waitFor();
        await page.locator("#mode-change").click(); await page.locator("#whole-page").click();
        await page.locator("#comment-text").fill("Et privat utkast i denne fanen.");
        [clone] = await Promise.all([context.waitForEvent("page"), page.evaluate(() => { window.open(location.href, "_blank"); })]);
        await until(async () => await clone.locator("#app-status").textContent() === "Visningen er ikke aktiv", "cloned tab denied");
        assert.equal(await clone.evaluate(() => Object.keys(sessionStorage).some(key => key.startsWith("designverksted.application-draft.v1:"))), true, "the clone carries storage but cannot recover authority");
        assert.equal(await clone.locator("#comment-text").inputValue(), "");
        assert.equal(await clone.locator("#app-preview[src]").count(), 0);
        await clone.close(); clone = null;
        await page.evaluate(() => {
          const key = Object.keys(sessionStorage).find(key => key.startsWith("designverksted.application-draft.v1:"));
          const value = JSON.parse(sessionStorage.getItem(key));
          sessionStorage.setItem(key, JSON.stringify({ ...value, unexpected: "Not part of the recovery contract" }));
        });
        page.once("dialog", dialog => void dialog.accept()); await page.reload();
        await page.locator("#stage-message").waitFor({ state: "hidden" });
        assert.equal(await page.locator("#comment-text").inputValue(), "");
        assert.equal(await page.locator("#draft-restored").isVisible(), false);
        assert.equal(await page.evaluate(() => Object.keys(sessionStorage).some(key => key.startsWith("designverksted.application-draft.v1:"))), false);
        assert.equal(messages.length, before, "reload and cloned tabs never send feedback");
      } finally { await clone?.close(); await adapter.canvas.onClose(recoveryIdentity); await page.close(); page = previous; }
    });
    await check("draft recovery waits for the first successful state after a startup failure", async () => {
      const previous = page, recoveryIdentity = { ...identity, instanceId: "draft-recovery-retry" };
      const before = messages.length;
      const call = (name, input = {}) => adapter.canvas.actions.find(item => item.name === name).handler({ ...recoveryIdentity, input });
      try {
        await openWorkshop(await adapter.canvas.open({ ...recoveryIdentity, input: { application } }));
        await page.frameLocator("#app-preview").getByRole("heading", { name: "Avtal et møte", exact: true }).waitFor();
        await page.locator("#mode-change").click(); await page.locator("#whole-page").click();
        let text = "Behold utkastet selv om første tilstandshenting feiler.";
        await page.locator("#comment-text").fill(text);
        for (const recovery of ["poll", "retry"]) {
          let requests = 0, stateAvailable = false;
          await page.route("**/state", route => {
            requests++;
            return stateAvailable ? route.continue() : route.fulfill({ status: 503, contentType: "application/json", body: "{}" });
          });
          page.once("dialog", dialog => void dialog.accept()); await page.reload();
          await page.locator("#global-message").waitFor();
          assert.equal(await page.locator("#comment-text").inputValue(), "", "recovery waits for validated state");
          stateAvailable = true;
          if (recovery === "retry") await page.locator("#retry-state").click();
          await page.locator("#draft-restored").waitFor();
          assert(requests >= 2, "a later state request recovers the connection");
          assert.equal(await page.locator("#comment-text").inputValue(), text);
          assert.equal(await page.locator("#target-label").textContent(), "Hele siden");
          assert.equal(await page.locator("#global-message").isVisible(), false);
          await page.unroute("**/state");
          text += " Fortsatt redigerbart.";
          await page.locator("#comment-text").fill(text);
          page.once("dialog", dialog => void dialog.accept()); await page.reload();
          await page.locator("#draft-restored").waitFor();
          assert.equal(await page.locator("#comment-text").inputValue(), text, "new edits persist after recovery");
        }
        assert.equal((await call("read_state")).submission, 0);
        assert.equal(messages.length, before, "recovery never sends feedback");
      } finally {
        await page.unrouteAll({ behavior: "wait" });
        await adapter.canvas.onClose(recoveryIdentity); await page.close(); page = previous;
      }
    });
    await check("direct keyboard send preserves an uncertain draft and retries one immutable submission", async () => {
      const previous = page, directIdentity = { ...identity, instanceId: "direct-feedback" };
      const call = (name, input = {}) => adapter.canvas.actions.find(item => item.name === name).handler({ ...directIdentity, input });
      let release = () => {};
      try {
        await openWorkshop(await adapter.canvas.open({ ...directIdentity, input: { application } }));
        await page.frameLocator("#app-preview").getByRole("heading", { name: "Avtal et møte", exact: true }).waitFor();
        await page.locator("#mode-change").click(); await page.locator("#whole-page").click();
        const text = "Gjør møtetidspunktet lettere å finne.";
        await page.locator("#comment-text").fill(text);
        assert.equal(await page.locator("#send-comment").textContent(), "Send innspill");
        assert.equal(await page.locator("#save-comment").textContent(), "Legg til flere");
        assert.equal((await call("read_state")).revision, 0, "typing does not save or send");
        assert(await page.evaluate(() => {
          const area = document.getElementById("compose-pane").getBoundingClientRect();
          return ["send-comment", "save-comment", "clear-draft"].every(id => {
            const rect = document.getElementById(id).getBoundingClientRect();
            return rect.top >= area.top && rect.bottom <= area.bottom && rect.width >= 44 && rect.height >= 44;
          });
        }), "all composer actions fit the desktop panel without scrolling");
        if (evidence) await page.screenshot({ path: path.join(evidence, "direct-feedback-desktop.png") });
        page.once("dialog", dialog => void dialog.accept()); await page.reload();
        await page.locator("#draft-restored").waitFor();
        assert.equal(await page.locator("#comment-text").inputValue(), text);
        assert.equal(await page.locator("#target-label").textContent(), "Hele siden");
        assert.equal((await call("read_state")).submission, 0, "plain draft reload does not send");
        if (evidence) await page.screenshot({ path: path.join(evidence, "restored-application-draft.png") });
        let rejectedKey;
        await page.route("**/submit-draft", async route => {
          rejectedKey = route.request().headers()["x-feedback-mutation"];
          await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ rejected: true }) });
        });
        await page.locator("#send-comment").click();
        await until(async () => await page.locator("#comment-error").isVisible() && await page.locator("#send-comment").textContent() === "Send innspill", "definite rejection leaves the draft editable");
        assert.equal(await page.locator("#comment-text").inputValue(), text);
        assert.equal(await page.locator("#comment-text").getAttribute("readonly"), null);
        assert.equal((await call("read_state")).submission, 0);
        await page.unroute("**/submit-draft");
        const requests = []; let reached = false;
        const hold = new Promise(resolve => { release = resolve; });
        await page.route("**/submit-draft", async route => {
          requests.push({ key: route.request().headers()["x-feedback-mutation"], body: route.request().postDataJSON() });
          if (requests.length === 1) {
            reached = true; await hold; await route.fetch();
            // A conflicting response without an explicit rejection can also be
            // post-commit uncertainty; it must retain the original request.
            await route.fulfill({ status: 409, contentType: "application/json", body: "{}" });
          } else await route.continue();
        });
        const before = messages.length;
        await page.locator("#comment-text").press("Control+Enter");
        await until(() => reached, "direct request starts");
        assert.equal(await page.locator("#submission-status").textContent(), "Sender innspill …");
        assert.equal(await page.locator("#comment-text").inputValue(), text);
        release();
        await until(async () => await page.locator("#send-comment").textContent() === "Prøv samme sending igjen", "same direct send retry");
        assert.equal(await page.locator("#comment-text").inputValue(), text);
        assert.equal(await page.locator("#comment-text").getAttribute("readonly"), "");
        assert.equal(await page.locator("#clear-draft").isDisabled(), true);
        page.once("dialog", dialog => void dialog.accept()); await page.reload();
        await page.locator("#draft-restored").waitFor();
        assert.equal(await page.locator("#comment-text").inputValue(), text);
        assert.equal(await page.locator("#send-comment").textContent(), "Prøv samme sending igjen");
        assert.equal(requests.length, 1, "restoration never retries automatically");
        await page.locator("#send-comment").click();
        await until(async () => await page.locator("#comment-text").inputValue() === "", "confirmed draft clears");
        assert.equal(requests.length, 2); assert.deepEqual(requests[1], requests[0]); assert.notEqual(requests[0].key, rejectedKey);
        assert.equal(await page.locator("#sent-count").textContent(), "1");
        assert.equal(await page.evaluate(() => Object.keys(sessionStorage).some(key => key.startsWith("designverksted.application-draft.v1:"))), false, "confirmed send clears its cached intent");
        assert.equal((await call("read_submission", { submission: 1 })).items.filter(item => item.type === "comment").length, 1);
        await until(() => messages.length === before + 1, "only one direct round");
        assert.equal(await page.locator("#mode-browse").getAttribute("aria-pressed"), "true");
        await page.unroute("**/submit-draft");
        await call("review_submission", { submission: 1, status: "answered", reply: "Tidspunktet kan fremheves." });
        await page.locator("#mode-change").click(); await page.locator("#whole-page").click();
        await page.locator("#comment-text").fill("Første innspill i neste runde."); await page.locator("#save-comment").click();
        await until(async () => await page.locator("#feedback-count").textContent() === "1", "queued next comment");
        await page.locator("#mode-change").click(); await page.locator("#whole-page").click();
        await page.locator("#comment-text").fill("Andre innspill i neste runde.");
        assert.equal(await page.locator("#send-comment").textContent(), "Send alle 2 innspill");
        await page.setViewportSize({ width: 390, height: 844 });
        if (evidence) await page.screenshot({ path: path.join(evidence, "direct-feedback-mobile.png") });
        await page.locator("#send-comment").click();
        await until(async () => (await call("read_state")).submission === 2, "combined direct send");
        await until(async () => await page.locator("#side-panel").isHidden(), "mobile returns to app");
        const batch = await call("read_submission", { submission: 2 });
        assert.deepEqual(batch.items.filter(item => item.type === "comment").map(item => item.value.text), ["Første innspill i neste runde.", "Andre innspill i neste runde."]);
        assert.equal(await page.locator("#mode-browse").getAttribute("aria-pressed"), "true");
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      } finally {
        release(); await page.unrouteAll({ behavior: "wait" });
        await adapter.canvas.onClose(directIdentity); await page.close(); page = previous;
      }
    });
    await check("an early runtime error stays visible despite HTTP 200 and a connected inspector", async () => {
      const healthIdentity = { ...identity, instanceId: "runtime-health" };
      const call = (name, input = {}) => adapter.canvas.actions.find(item => item.name === name).handler({ ...healthIdentity, input });
      const before = messages.length, previous = page;
      const signature = "module factory is not available: synthetic failure";
      fs.writeFileSync(sourceFile, document.replace("<head>", `<head><script>throw new Error(${JSON.stringify(signature)})</script>`));
      expectedErrors.push(signature);
      try {
        await openWorkshop(await adapter.canvas.open({ ...healthIdentity, input: { application } }));
        const appFrame = page.frameLocator("#app-preview");
        await appFrame.getByRole("heading", { name: "Avtal et møte", exact: true }).waitFor();
        await page.locator("#health-message").waitFor({ state: "visible" });
        let connected;
        await until(async () => {
          connected = await call("read_state");
          return connected.application.applicationHealth?.module === 1 && connected.application.previewStatus.state === "ready";
        }, "early error and completed connection reach state");
        assert.equal(connected.application.previewStatus.state, "ready");
        assert.equal(connected.application.applicationHealth.state, "errors-observed");
        await appFrame.getByLabel("Hvordan vil du møtes?").selectOption("video");
        const observation = await call("read_preview");
        assert.equal(observation.health.module, 1); assert.equal(observation.evidence, "untrusted-page-content");
        assert(!JSON.stringify(observation).includes("synthetic failure"), "exception text never enters diagnostics");
        assert(observation.elements.some(item => item.name === "Avtal et møte"));
        assert.equal(messages.length, before, "inspection cannot submit feedback or send messages");
        fs.writeFileSync(sourceFile, document);
        await appFrame.locator("body").evaluate(() => location.reload());
        await until(async () => (await call("read_state")).application.applicationHealth?.state === "no-errors-observed", "new document clears prior health");
        assert.equal(await page.locator("#health-message").isVisible(), false);
      } finally {
        fs.writeFileSync(sourceFile, document); await adapter.canvas.onClose(healthIdentity); await page.close(); page = previous;
      }
    });
    assert.deepEqual(external, [], "the fixture must not attempt external traffic");
    assert.deepEqual(errors, expectedErrors, "only the deliberate runtime-health fixture may throw");
  } catch (error) {
    if (evidence && page) await page.screenshot({ path: path.join(evidence, "failure.png") }).catch(() => {});
    throw error;
  } finally {
    await htmlContext?.close(); await context?.close(); await browser?.close(); await adapter?.close();
    for (const socket of sockets) socket.destroy();
    if (app.listening) await new Promise(resolve => app.close(resolve));
    fs.rmSync(temporary, { recursive: true, force: true });
    if (evidence) fs.writeFileSync(path.join(evidence, "results.json"), JSON.stringify({ fixture: "synthetic application", scope: "Actual Chrome and adapter/backend; simulated host replies, no native application or model calls.", results, failures, externalOrigins: [...new Set(external)], unhandledScriptErrors: errors, zoomNote: "640x400 is a small CSS viewport, not a claim of actual 200% browser zoom." }, null, 2) + "\n");
  }
}
main().catch(error => { console.error(error.message.replace(/https?:\/\/[^\s)]+/g, "[local preview address]")); process.exitCode = 1; });
