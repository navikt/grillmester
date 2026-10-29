#!/usr/bin/env node
"use strict";
const { openTools, enterBrowse, openAdjust, startComparison, collectFeedback } = require("./visual-smoke-controls.cjs");

// Synthetic role scenarios, exercised through actual browser input and the public reader.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { createRequire } = require("node:module");
const options = new Map();
for (let index = 2; index < process.argv.length; index += 1) {
  const flag = process.argv[index];
  if (!["--playwright-module", "--browser-channel", "--aksel-project", "--evidence-dir", "--case"].includes(flag) || !process.argv[index + 1] || process.argv[index + 1].startsWith("--")) {
    console.error("Usage: node scripts/smoke_visual_review_cycle.cjs --aksel-project DIRECTORY [--playwright-module PATH] [--browser-channel chrome] [--evidence-dir DIRECTORY] [--case NAME]"); process.exit(2);
  }
  options.set(flag, process.argv[++index]);
}
if (!options.has("--aksel-project")) { console.error("Supply an existing Aksel project. Nothing is installed."); process.exit(2); }
let chromium;
try { ({ chromium } = require(options.get("--playwright-module") || "playwright")); }
catch { console.error("Supply an existing Playwright module. Nothing is installed."); process.exit(2); }
const installedProject = path.resolve(options.get("--aksel-project"));
const installed = createRequire(path.join(installedProject, "package.json"));
const React = installed("react"), C = installed("@navikt/ds-react"), { renderToStaticMarkup } = installed("react-dom/server");
const packageRoot = path.join(installedProject, "node_modules/@navikt");
const akselVersion = JSON.parse(fs.readFileSync(path.join(packageRoot, "ds-react/package.json"))).version;
assert.equal(akselVersion, JSON.parse(fs.readFileSync(path.join(packageRoot, "ds-css/package.json"))).version);
assert.match(akselVersion, /^8\./);
const css = ["index.min.css", "index.css"].map(name => path.join(packageRoot, "ds-css/dist", name)).find(file => fs.existsSync(file));
assert(css);
const runtime = path.resolve(__dirname, "../plugin/skills/design-prototype/scripts");
const evidence = options.has("--evidence-dir") ? path.resolve(options.get("--evidence-dir")) : null;
if (evidence) fs.mkdirSync(evidence, { recursive: true });
const h = React.createElement;
let componentNumber = 0;
const render = element => renderToStaticMarkup(element, { identifierPrefix: `cycle-${++componentNumber}-` });
const heading = (text, level = "1") => render(h(C.Heading, { level, size: level === "1" ? "large" : "small" }, text));
const text = value => render(h(C.BodyShort, null, value));
const button = (label, state) => render(h(C.Button, { type: "button", variant: "secondary", "data-vc-control": "state", "data-vc-value": state }, label));
function sketch(title, detail = "short", state = "invitation") {
  const design = { version: 1, variants: [], targets: [{ key: "invitation", variant: "", label: "Møteinvitasjon", controls: [
    { id: "state", label: "Situasjon", type: "select", initial: state, options: [{ value: "invitation", label: "Tid og sted" }, { value: "change", label: "Endre møtet" }] },
    { id: "detail", label: "Mengde forklaring", type: "select", initial: detail, options: [{ value: "short", label: "Kort forklaring" }, { value: "full", label: "Utfyllende forklaring" }] },
  ] }] };
  return { design, html: `<style>.cycle-study,.cycle-part,.cycle-state{display:grid;gap:var(--ax-space-16)}.cycle-part{border:1px solid var(--ax-border-neutral-subtle);padding:var(--ax-space-24);border-radius:var(--ax-radius-8)}.cycle-part[data-vc-setting-state=invitation] .change,.cycle-part[data-vc-setting-state=change] .invitation{display:none}.cycle-full{display:none}.cycle-part[data-vc-setting-detail=full] .cycle-full{display:block}.cycle-actions{display:flex;flex-wrap:wrap;gap:var(--ax-space-12)}</style><div class="cycle-study">${heading(title)}${text("Samme oppdiktede møte i alle versjoner: Servicesenteret i Solvik, 18. november kl. 10.00. Utforsk og send innspill når du er klar.")}<section class="cycle-part" data-vc-key="invitation"><div class="cycle-state invitation">${heading("Passer tidspunktet?", "2")}${text("Du er invitert til en samtale på 30 minutter.")}<div class="cycle-actions">${button("Se muligheter for endring", "change")}</div></div><div class="cycle-state change">${heading("Du beholder timen mens du ser på andre tider", "2")}${text("Ingen avtale endres i denne skissen.")}<div class="cycle-actions">${button("Tilbake til invitasjonen", "invitation")}</div></div><div class="cycle-full">${text("Hvis tiden ikke passer, finner vi et annet tidspunkt sammen. Den nåværende timen gjelder frem til du har bekreftet en ny.")}</div></section></div>` };
}
async function until(check, label, timeout = 12000) {
  const end = Date.now() + timeout;
  do { const value = await check(); if (value) return value; await new Promise(resolve => setTimeout(resolve, 70)); } while (Date.now() < end);
  throw new Error(`Timed out: ${label}`);
}
async function stop(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const done = new Promise(resolve => child.once("close", resolve)); child.kill("SIGTERM");
  const timer = setTimeout(() => child.kill("SIGKILL"), 5000); await done; clearTimeout(timer);
}
function start(child) {
  return new Promise((resolve, reject) => {
    let data = "", settled = false;
    const timer = setTimeout(() => finish(new Error("Preview startup timed out.")), 6000);
    function finish(error, value) { if (settled) return; settled = true; clearTimeout(timer); error ? reject(error) : resolve(value); }
    child.stdout.on("data", chunk => { data += chunk; if (data.includes("\n")) { try { const info = JSON.parse(data.split("\n")[0]); assert.equal(info.type, "server-started"); finish(null, info); } catch (error) { finish(error); } } });
    child.once("error", error => finish(error)); child.once("close", () => finish(new Error("Preview ended before startup.")));
  });
}
function command(info, action, extra = []) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [path.join(runtime, "comments.js"), action, "--state-dir", info.state_dir, ...extra]);
    let out = "", err = ""; const timer = setTimeout(() => child.kill("SIGKILL"), 20000);
    child.stdout.on("data", data => { out += data; }); child.stderr.on("data", data => { err += data; });
    child.once("error", error => { clearTimeout(timer); reject(error); });
    child.once("close", code => { clearTimeout(timer); if (code) reject(new Error(err || `Reader failed (${code}).`)); else { try { resolve(JSON.parse(out)); } catch { reject(new Error("Reader returned invalid JSON.")); } } });
  });
}
function viewFor(page) {
  const frame = page.frameLocator("#vc-preview"), ui = frame.locator("[data-visual-feedback]"), workshop = ui.getByRole("region", { name: "Juster visningen", exact: true });
  const closeFeedback = async () => { const control = ui.getByRole("button", { name: "Lukk innspill", exact: true }); if (await control.isVisible()) await control.click(); };
  const closeWorkshop = async () => { const control = workshop.getByRole("button", { name: "Lukk justeringer", exact: true }); if (await control.isVisible()) await control.click(); };
  const openFeedback = async () => { await closeWorkshop(); if (!(await ui.getByRole("region", { name: "Innspill til prototypen", exact: true }).isVisible())) await ui.locator('[data-action="panel"]').click(); };
  const adjust = async () => { await closeFeedback(); if (!(await workshop.isVisible())) await openAdjust(ui); };
  return { page, frame, ui, workshop, closeFeedback, closeWorkshop, openFeedback, adjust,
    async browse() { await closeFeedback(); await closeWorkshop(); if (await ui.locator('[data-action="browse"]').getAttribute("aria-pressed") !== "true") await ui.locator('[data-action="browse"]').click(); },
    async note(value, selector = "h1") { await closeFeedback(); await closeWorkshop(); if (await ui.locator('[data-action="change-ask"]').getAttribute("aria-pressed") !== "true") await ui.getByRole("button", { name: "Gi innspill", exact: true }).click(); await frame.locator(selector).click(); await ui.getByLabel("Hva vil du endre?", { exact: true }).fill(value); },
    async save() { await collectFeedback(ui); await ui.getByRole("button", { name: "Legg til flere", exact: true }).waitFor({ state: "hidden" }); await ui.getByRole("region", { name: "Innspill til prototypen", exact: true }).waitFor(); },
    async keep(detail, value) { await adjust(); await workshop.getByLabel("Mengde forklaring", { exact: true }).selectOption(detail); await workshop.getByLabel("Merknad", { exact: true }).fill(value); await workshop.getByRole("button", { name: "Behold denne delen", exact: true }).click(); await ui.getByRole("region", { name: "Innspill til prototypen", exact: true }).waitFor(); await closeFeedback(); },
    async shown(title) { await frame.getByRole("heading", { name: title, exact: true }).waitFor(); },
  };
}
async function runCase(browser, testcase) {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "grillmester-review-cycle-"));
  const project = path.join(temporary, "project"), cssDirectory = path.join(project, "node_modules/@navikt/ds-css/dist");
  fs.mkdirSync(cssDirectory, { recursive: true }); fs.copyFileSync(css, path.join(cssDirectory, "index.min.css"));
  const child = spawn(process.execPath, [path.join(runtime, "server.js"), "--project-dir", project], { stdio: ["ignore", "pipe", "pipe"] });
  let context, current; const exceptions = [], externalResources = [];
  try {
    const info = await start(child); context = await browser.newContext({ viewport: testcase.viewport, reducedMotion: "reduce" });
    let sequence = 0;
    const write = (title, detail = "short", state = "invitation") => { const stem = `${String(++sequence).padStart(2, "0")}-invitation`, value = sketch(title, detail, state); fs.writeFileSync(path.join(info.screen_dir, `${stem}.design.json`), JSON.stringify(value.design)); fs.writeFileSync(path.join(info.screen_dir, `${stem}.html`), value.html); };
    const newTab = async (viewport = testcase.viewport) => { const page = await context.newPage(); await page.setViewportSize(viewport); page.setDefaultTimeout(12000); page.on("pageerror", error => exceptions.push(error.message)); page.on("requestfinished", request => { if (!request.url().startsWith(new URL(info.url).origin) && !/^(data|blob):/.test(request.url())) externalResources.push(new URL(request.url()).origin); }); await page.goto(info.url); const view = viewFor(page); await view.ui.getByRole("button", { name: "Gi innspill", exact: true }).waitFor(); return view; };
    const list = () => command(info, "list"), read = (after = 0) => command(info, "wait", ["--after", String(after), "--timeout", "0"]);
    const send = async (view, count) => { const before = (await list()).submission; await view.openFeedback(); await view.ui.getByRole("button", { name: `Send ${count} innspill`, exact: true }).click(); return until(async () => { const data = await list(); return data.submission > before && data; }, "explicit batch received"); };
    const screenshot = async (name, view = current) => { if (!evidence) return; await view.page.locator("#vc-status").filter({ hasText: /^Tilkoblet$/ }).waitFor(); await view.page.screenshot({ path: path.join(evidence, `${testcase.name}-${name}.png`), animations: "disabled" }); };
    write("Invitasjon · første gjennomgang"); current = await newTab(); await current.shown("Invitasjon · første gjennomgang");
    const result = await testcase.run({ ...current, info, write, newTab, list, read, send, screenshot });
    assert.deepEqual(exceptions, []); assert.deepEqual(externalResources, []);
    return { name: testcase.name, role: testcase.role, status: "completed", ...result, browserExceptions: exceptions, completedExternalResources: externalResources };
  } catch (error) {
    if (current && evidence) await current.page.screenshot({ path: path.join(evidence, `${testcase.name}-failure.png`), animations: "disabled" }).catch(() => {});
    return { name: testcase.name, role: testcase.role, status: "failed", error: error.message.replace(/http:\/\/127\.0\.0\.1:[^\s)]+/g, "[local preview]") };
  } finally { try { await context?.close(); } finally { await stop(child); fs.rmSync(temporary, { recursive: true, force: true }); } }
}
const cases = [
  { name: "mobile-sent-context-next-version", role: "Busy mobile participant following a completed review", viewport: { width: 390, height: 844 },
    async run(view) {
      await view.browse(); await view.frame.getByRole("button", { name: "Se muligheter for endring", exact: true }).click();
      await view.note("Vis tydelig at den gamle tiden gjelder mens jeg ser på andre tider.", ".change h2"); await view.save();
      const sent = await view.send(view, 1), comment = sent.comments[0]; const first = await view.read(0); assert(first.comments.some(item => item.id === comment.id));
      assert.deepEqual(comment.context, { variant: "", target: "invitation", values: { state: "change", detail: "short" } });
      await command(view.info, "resolve", ["--id", comment.id, "--reply", "Forklaringen i neste versjon sier når den opprinnelige timen slutter å gjelde."]);
      view.write("Invitasjon · forklaringen er presisert", "full", "change");
      const updated = view.frame.getByRole("heading", { name: "Invitasjon · forklaringen er presisert", exact: true });
      await until(async () => await updated.isVisible() || await view.ui.locator('[data-action="refresh"]').isVisible(), "new version offered");
      const blocked = !(await updated.isVisible()), findings = [];
      assert(blocked, "Local exploration must hold back automatic replacement until explicit reset-and-open.");
      if (blocked) {
        const refresh = view.ui.getByRole("button", { name: "Vis oppdatert forslag", exact: true }); assert(await refresh.isEnabled());
        await view.openFeedback(); await view.ui.locator(`article[data-id="${comment.id}"]`).getByText("Forklaringen i neste versjon sier når den opprinnelige timen slutter å gjelde.", { exact: false }).waitFor();
        await view.screenshot("explicit-reset-offered"); await view.closeFeedback();
        await view.adjust(); await view.workshop.getByLabel("Merknad", { exact: true }).fill("Dette må ikke forsvinne når ny versjon åpnes.");
        assert(await view.ui.locator('[data-action="refresh"]').isDisabled(), "A written workshop remark must still block reset-and-open.");
        assert.equal(await view.workshop.getByLabel("Merknad", { exact: true }).inputValue(), "Dette må ikke forsvinne når ny versjon åpnes.");
        await view.workshop.getByLabel("Merknad", { exact: true }).fill(""); await view.closeWorkshop();
        const geometry = await refresh.evaluate(node => { const b = node.getBoundingClientRect(), toolbar = node.closest(".toolbar").getBoundingClientRect(); return { x: b.x, y: b.y, width: b.width, height: b.height, viewportWidth: innerWidth, viewportHeight: innerHeight, toolbar: { x: toolbar.x, y: toolbar.y, width: toolbar.width, height: toolbar.height } }; });
        assert(geometry.x >= 0 && geometry.x + geometry.width <= geometry.viewportWidth + 1 && geometry.y + geometry.height <= geometry.viewportHeight, "The explicit reset action must remain visible in the mobile viewport.");
        await refresh.press("Enter");
        findings.push({ observation: "A sent situational comment can be followed by one explicit reset-and-open action. A newly written remark still disables that action.", recovery: "Vis oppdatert forslag", actionGeometry: geometry, savedUnsentFeedback: (await view.list()).comments.filter(item => item.submission === 0).length });
      }
      await view.shown("Invitasjon · forklaringen er presisert");
      const nextAction = view.frame.getByRole("button", { name: "Tilbake til invitasjonen", exact: true });
      let tabsToNewAction = 0;
      while (!(await nextAction.evaluate(node => node === document.activeElement)) && tabsToNewAction < 12) { await view.page.keyboard.press("Tab"); tabsToNewAction += 1; }
      assert(tabsToNewAction < 12, "Keyboard navigation must reach the revised sketch after its iframe is replaced.");
      await view.openFeedback();
      const card = view.ui.locator(`article[data-id="${comment.id}"]`); assert((await card.innerText()).includes("Tidligere versjon")); assert((await card.innerText()).includes("Forklaringen i neste versjon"));
      assert.equal(await card.getByRole("button", { name: "Vis situasjon", exact: true }).count(), 0, "An old pin must not be rebound to a new screen.");
      assert.equal((await view.list()).submission, 1); await view.screenshot("reply-on-new-version");
      return { findings, measurements: { viewport: view.page.viewportSize(), automaticVersionChangeBlockedByLocalView: blocked, explicitResetOpensNewVersion: true, unsavedRemarkProtected: true, tabsToNewAction, submittedBatches: 1, originalContextPreserved: true, oldReplyVisible: true } };
    } },
  { name: "stale-tab-same-part-wishes", role: "Service designer comparing an old tab with the revised tab", viewport: { width: 1440, height: 1000 },
    async run(view) {
      const old = await view.newTab();
      await old.shown("Invitasjon · første gjennomgang");
      await view.keep("full", "Behold forklaringen om hva som skjer med den gamle tiden."); const firstState = await view.send(view, 1);
      const first = firstState.comments[0]; assert.equal(first.context.values.detail, "full");
      await view.screenshot("old-tab-before-adjust", old); await old.adjust(); await view.screenshot("old-tab-adjust-open", old);
      await old.workshop.getByLabel("Merknad", { exact: true }).fill("Fra den gamle skissen: bruk kort forklaring.");
      view.write("Invitasjon · utfyllende forklaring", "full"); await view.shown("Invitasjon · utfyllende forklaring"); await old.shown("Invitasjon · første gjennomgang");
      await view.keep("full", "Den nye forklaringen skal beholdes som skrevet.");
      assert.equal(await old.workshop.getByLabel("Mengde forklaring", { exact: true }).inputValue(), "short");
      // Keeping the same part from an older tab is another wish; it replaces nothing.
      await old.workshop.getByRole("button", { name: "Behold denne delen", exact: true }).click(); await old.ui.getByRole("region", { name: "Innspill til prototypen", exact: true }).waitFor();
      const state = await view.list(), pending = state.comments.filter(item => item.submission === 0);
      assert.equal(pending.length, 2, "Two tabs keeping the same part save two wishes.");
      const fromOld = pending.find(item => item.text.includes("Fra den gamle skissen")), fromNew = pending.find(item => item.text.includes("Den nye forklaringen"));
      assert.equal(fromOld.screen, first.screen, "The older tab's wish keeps the screen it was made on.");
      assert.notEqual(fromNew.screen, first.screen);
      assert.equal(fromOld.context.values.detail, "short"); assert.equal(fromNew.context.values.detail, "full");
      assert.equal(state.submission, 1);
      await view.screenshot("both-wishes-kept", old);
      await view.send(old, 2); const second = await view.read(1);
      assert.deepEqual(second.comments.map(item => item.id).sort(), [fromOld.id, fromNew.id].sort());
      await view.openFeedback(); await view.screenshot("both-wishes-sent");
      return { findings: [{ observation: "Keeping the same part from an older tab saves a separate wish on its own screen. Neither tab's wish replaces the other, and both reach the next round.", oldTabScreenRetained: true }], measurements: { wishes: 2, submittedBatches: 2 } };
    } },
  { name: "reversal-and-delayed-reader", role: "Content designer revising a sent round while the reader resumes from an older cursor", viewport: { width: 390, height: 844 },
    async run(view) {
      await view.note("Den første overskriften bør være kortere."); await view.save();
      await view.note("Forklar hva jeg gjør hvis tiden ikke passer.", ".invitation h2"); await view.save();
      const sent = await view.send(view, 2), [removed, reopened] = sent.comments; const original = await view.read(0);
      assert.equal(original.submission, 1); assert.equal(original.comments.length, 2);
      await command(view.info, "resolve", ["--id", reopened.id, "--submission", "1", "--reply", "Den neste versjonen har en tydelig vei til å endre tidspunkt."]);
      view.write("Invitasjon · revidert etter første runde"); await view.shown("Invitasjon · revidert etter første runde"); await view.openFeedback();
      const removedCard = view.ui.locator(`article[data-id="${removed.id}"]`), reopenedCard = view.ui.locator(`article[data-id="${reopened.id}"]`);
      await removedCard.locator(".comment-details > summary").click();
      assert((await removedCard.innerText()).includes("Sendt i runde 1"));
      await removedCard.getByRole("button", { name: "Fjern fra listen", exact: true }).click(); await removedCard.waitFor({ state: "hidden" });
      const focusAfterRemoval = await view.ui.locator(".list").evaluate(list => { const active = list.getRootNode().activeElement; return { retained: list.contains(active), tag: active?.tagName || "", label: active?.textContent?.trim() || "" }; });
      assert(focusAfterRemoval.retained, "Removing an old item must retain keyboard focus in the feedback list.");
      await reopenedCard.getByRole("button", { name: "Åpne igjen", exact: true }).click();
      await until(async () => (await view.list()).comments.find(item => item.id === reopened.id)?.submission === 0, "reopened local round");
      await reopenedCard.locator(".comment-details > summary").click();
      const reopenedText = await reopenedCard.innerText(); assert(reopenedText.includes("Ny runde ikke sendt") && reopenedText.includes("Sendt i runde 1"));
      assert(await reopenedCard.getByRole("button", { name: "Fjern fra listen", exact: true }).isVisible()); await view.screenshot("reopened-after-sent");
      await view.note("Behold den konkrete forklaringen også når teksten kortes ned."); await view.save();
      const secondSent = await view.send(view, 2); assert.equal(secondSent.submission, 2);
      const currentBeforeStaleReply = secondSent.comments.find(item => item.id === reopened.id);
      await assert.rejects(command(view.info, "resolve", ["--id", reopened.id, "--submission", "1", "--reply", "Et sent svar på den gamle runden må ikke lukke den nye."]), /changed|submission|round|runde|newer|supersed|stale/i);
      const unchanged = (await view.list()).comments.find(item => item.id === reopened.id); assert.equal(unchanged.status, "open"); assert.equal(unchanged.reply, currentBeforeStaleReply.reply);
      const replayedFirst = await view.read(0); assert.equal(replayedFirst.submission, 1); assert.equal(replayedFirst.latestSubmission, 2); assert.equal(replayedFirst.hasMore, true);
      assert.deepEqual(replayedFirst.comments, original.comments, "Replaying a delivered round must preserve its exact submitted content after deletion, replies and reopening.");
      assert.deepEqual(replayedFirst.currentComments.find(item => item.id === removed.id), { id: removed.id, present: false });
      const current = replayedFirst.currentComments.find(item => item.id === reopened.id); assert.equal(current.present, true); assert.equal(current.status, "open"); assert.equal(current.submission, 2);
      const second = await view.read(1); assert.equal(second.submission, 2); assert.equal(second.hasMore, false); assert.equal(second.comments.length, 2);
      assert.equal(new Set(second.comments.map(item => item.screen)).size, 2, "A deliberate batch may include a reopened old-screen comment and a new-screen comment.");
      const newComment = second.comments.find(item => item.id !== reopened.id);
      await command(view.info, "resolve", ["--id", newComment.id, "--submission", "2", "--reply", "Forklaringen er beholdt i den korte versjonen."]);
      view.write("Invitasjon · kort tekst med konkret forklaring", "full"); await view.shown("Invitasjon · kort tekst med konkret forklaring"); await view.openFeedback();
      assert.equal(await view.ui.locator(`article[data-id="${removed.id}"]`).count(), 0); await view.ui.locator(`article[data-id="${newComment.id}"]`).getByText("Forklaringen er beholdt i den korte versjonen.", { exact: false }).waitFor();
      const drained = await view.read(2); assert.equal(drained.type, "feedback-timeout"); assert.equal(drained.comments.length, 0); await view.screenshot("second-reply-and-latest-version");
      return { findings: [{ observation: "The visible list can remove an old item while its sent receipt remains readable. Reopening shows both the earlier round and the new unsent status; a late reply with the old cursor is rejected.", reopenedLabels: ["Ny runde ikke sendt", "Sendt i runde 1", "Fjern fra listen"] }], measurements: { screenVersions: 3, submittedBatches: 2, roundOneComments: replayedFirst.comments.length, roundTwoComments: second.comments.length, secondRoundSourceScreens: new Set(second.comments.map(item => item.screen)).size, originalReceiptUnchanged: true, removedCurrentItemPresent: false, staleReplyRejected: true, focusAfterRemoval, drained: true } };
    } },
];
cases.push(
  { name: "first-save-after-filter", role: "Unfamiliar participant trying the filters before writing", viewport: { width: 390, height: 844 },
    async run(view) {
      await view.openFeedback();
      await view.ui.getByText("Hva kan bli bedre?", { exact: true }).waitFor();
      assert(await view.ui.getByRole("button", { name: "Send innspill", exact: true }).isDisabled());
      await view.ui.getByRole("tab", { name: /^Sendt/ }).click(); await view.ui.getByRole("button", { name: "Ordnet", exact: true }).click();
      await view.closeFeedback(); await view.openFeedback();
      assert.equal(await view.ui.getByRole("button", { name: "Ordnet", exact: true }).getAttribute("aria-pressed"), "true", "Merely reopening feedback must retain the chosen tab and filter.");
      await view.note("Forklar hvorfor jeg er invitert, før tidspunkt og sted."); await view.save();
      const state = await view.list(); assert.equal(state.comments.length, 1); assert.equal(state.submission, 0);
      await view.ui.getByRole("button", { name: "Send 1 innspill", exact: true }).waitFor();
      await view.screenshot("saved-with-filter");
      assert(await view.ui.locator(`article[data-id="${state.comments[0].id}"]`).isVisible(), "The newly saved note must be visible for review before sending, even after selecting Ordnet.");
      const card = view.ui.locator(`article[data-id="${state.comments[0].id}"]`);
      await until(() => view.ui.getByRole("region", { name: "Innspill til prototypen", exact: true }).evaluate(node => node.contains(node.getRootNode().activeElement)), "explicit opening retains focus in feedback");
      assert.equal(await view.ui.getByRole("tab", { name: /^Klar til sending/ }).getAttribute("aria-selected"), "true", "A new note is shown where it waits to be sent.");
      return { measurements: { emptyStateExplained: true, ordinaryOpeningRetainedFilter: true, savedCommentVisible: true, feedbackPanelFocused: true, submission: state.submission } };
    } },
  { name: "first-reopen-after-filter", role: "First-time designer reopening an unsent item", viewport: { width: 390, height: 844 },
    async run(view) {
      await view.note("Jeg trenger mer informasjon om hensikten med møtet."); await view.save();
      const first = await view.list(), id=first.comments[0].id;
      await view.ui.locator(`article[data-id="${id}"]`).getByRole("button", { name: "Marker ordnet", exact: true }).click();
      await until(async () => (await view.list()).comments[0].status === "fixed", "local item marked fixed");
      await view.ui.locator(`article[data-id="${id}"]`).getByRole("button", { name: "Åpne igjen", exact: true }).click();
      await until(async () => (await view.list()).comments[0].status === "open", "local item reopened");
      await view.ui.getByRole("button", { name: "Send 1 innspill", exact: true }).waitFor();
      await view.screenshot("reopened-with-filter");
      assert(await view.ui.locator(`article[data-id="${id}"]`).isVisible(), "A reopened item must remain visible for review instead of disappearing under Ordnet.");
      const card = view.ui.locator(`article[data-id="${id}"]`);
      await until(() => card.evaluate(node => node === node.getRootNode().activeElement), "focus reaches the reopened card");
      assert.equal(await view.ui.getByRole("tab", { name: /^Klar til sending/ }).getAttribute("aria-selected"), "true");
      assert.equal((await view.list()).comments.find(item => item.id === id).submission, 0);
      assert.equal(await card.getByText(/Sendt i runde/).count(), 0, "A never-sent item must not imply an earlier round.");
      return { measurements: { reopenedCommentVisible: true, reopenedCardFocused: true, neverSentStatusClear: true, submission: (await view.list()).submission } };
    } },
  { name: "first-kept-choice-after-filter", role: "Participant preserving useful wording after browsing open feedback", viewport: { width: 390, height: 844 },
    async run(view) {
      await view.openFeedback(); await view.ui.getByRole("tab", { name: /^Sendt/ }).click(); await view.ui.getByRole("button", { name: "Åpne", exact: true }).click();
      await view.adjust(); await view.workshop.getByLabel("Mengde forklaring", { exact: true }).selectOption("full");
      await view.workshop.getByLabel("Merknad", { exact: true }).fill("Behold forklaringen om at den nåværende timen fortsatt gjelder.");
      await view.workshop.getByRole("button", { name: "Behold denne delen", exact: true }).press("Enter");
      await view.ui.getByRole("region", { name: "Innspill til prototypen", exact: true }).waitFor(); const state = await view.list(); assert.equal(state.submission, 0);
      const wish = state.comments.find(item => item.submission === 0 && item.context); assert.equal(wish.text, "Behold denne delen.\nBehold forklaringen om at den nåværende timen fortsatt gjelder.");
      await view.ui.getByRole("button", { name: "Send 1 innspill", exact: true }).waitFor();
      await view.screenshot("kept-with-filter");
      assert(await view.ui.getByRole("region", { name: "Innspill til prototypen", exact: true }).locator(`article[data-id="${wish.id}"]`).isVisible(), "The new keep wish must be visible when feedback opens, even after selecting Åpne.");
      const card = view.ui.getByRole("region", { name: "Innspill til prototypen", exact: true }).locator(`article[data-id="${wish.id}"]`);
      await until(() => card.evaluate(node => node === node.getRootNode().activeElement), "focus reaches the kept choice");
      return { measurements: { keptChoiceVisible: true, keptCardFocused: true, submission: state.submission } };
    } }
);


cases.push({ name: "first-draft-preview-recovery", role: "Content designer trying an alternative before deciding", viewport: { width: 390, height: 844 },
  async run(view) {
    const original = "Passer tidspunktet?", proposed = "Velg en tid som passer deg";
    const note = "Jeg prøver en mer aktiv overskrift før jeg bestemmer meg.";
    await view.note(note, ".invitation h2");
    await view.ui.getByRole("button", { name: "Foreslå ny tekst", exact: true }).click();
    await view.ui.getByLabel("Ny tekst", { exact: true }).fill(proposed);
    await view.ui.getByRole("button", { name: "Forhåndsvis teksten", exact: true }).press("Enter");
    assert.equal(await view.frame.locator(".invitation h2").innerText(), proposed);
    await view.screenshot("preview-before-parking");
    await view.page.keyboard.press("Escape");
    await view.ui.getByRole("button", { name: "Fortsett utkast", exact: true }).waitFor();
    assert.equal(await view.frame.locator(".invitation h2").innerText(), original, "Parking must remove the visual preview.");
    let state=await view.list(); assert.equal(state.comments.length, 0); assert.equal(state.submission, 0);
    await view.ui.getByRole("button", { name: "Fortsett utkast", exact: true }).press("Enter");
    assert.equal(await view.ui.getByLabel("Hva vil du endre?", { exact: true }).inputValue(), note);
    assert.equal(await view.ui.getByLabel("Ny tekst", { exact: true }).inputValue(), proposed);
    const edited = "Finn et annet tidspunkt";
    await view.ui.getByLabel("Ny tekst", { exact: true }).fill(edited);
    await view.ui.getByRole("button", { name: "Forhåndsvis teksten", exact: true }).press("Space");
    assert.equal(await view.frame.locator(".invitation h2").innerText(), edited);
    await view.ui.getByRole("button", { name: "Forkast", exact: true }).press("Enter");
    await view.ui.getByRole("button", { name: "Legg til flere", exact: true }).waitFor({ state: "hidden" });
    assert.equal(await view.frame.locator(".invitation h2").innerText(), original, "Discard must restore the original text.");
    assert.equal(await view.ui.getByRole("button", { name: "Fortsett utkast", exact: true }).count(), 0);
    await view.openFeedback(); await view.ui.getByText("Hva kan bli bedre?", { exact: true }).waitFor();
    assert(await view.ui.getByRole("button", { name: "Send innspill", exact: true }).isDisabled());
    await view.screenshot("discarded-with-empty-queue");
    state=await view.list(); assert.equal(state.comments.length, 0); assert.equal(state.submission, 0);
    return { measurements: { viewport: view.page.viewportSize(), parkedDraftRetainedBothFields: true, localTextRestoredTwice: true, keyboardActions: ["Enter preview", "Escape park", "Enter resume", "Space preview", "Enter discard"], savedComments: 0, submittedBatches: 0 } };
  }
});


cases.push({ name: "first-adjustment-after-filter", role: "First-time designer recording a changed local setting", viewport: { width: 390, height: 844 },
  async run(view) {
    await view.openFeedback(); await view.ui.getByRole("tab", { name: /^Sendt/ }).click(); await view.ui.getByRole("button", { name: "Ordnet", exact: true }).click();
    await view.adjust(); await view.workshop.getByLabel("Mengde forklaring", { exact: true }).selectOption("full");
    await view.workshop.getByLabel("Merknad", { exact: true }).fill("Vis hva som skjer med den opprinnelige timen når jeg endrer den.");
    await view.workshop.getByRole("button", { name: "Legg til innspill", exact: true }).press("Enter");
    await view.ui.getByRole("region", { name: "Innspill til prototypen", exact: true }).waitFor();
    const state = await view.list(); assert.equal(state.comments.length, 1); assert.equal(state.comments[0].kind, "adjustment");
    assert.equal(state.comments[0].adjustment.values.detail, "full"); assert.equal(state.submission, 0);
    const card = view.ui.locator(`article[data-id="${state.comments[0].id}"]`);
    assert(await card.isVisible(), "The newly recorded adjustment must be visible despite the earlier Ordnet filter.");
    await until(() => card.evaluate(node => node === node.getRootNode().activeElement), "focus reaches the adjustment card");
    await card.getByText(/Utfyllende forklaring/).waitFor();
    assert(await view.ui.getByRole("button", { name: "Send 1 innspill", exact: true }).isEnabled());
    await view.screenshot("adjustment-visible-and-focused");
    return { measurements: { adjustmentVisible: true, adjustmentCardFocused: true, declaredValueRecorded: "full", submittedBatches: state.submission } };
  }
});


function previewInspectionCase(name, viewport, selector = ".invitation h2") {
  return { name, role: "Content designer inspecting a text proposal in the sketch", viewport,
    async run(view) {
      const original = await view.frame.locator(selector).innerText();
      const bodyChildren = await view.frame.locator("body").evaluate(node => node.children.length);
      const assertNoExtraSpace = async () => assert.equal(await view.frame.locator("body").evaluate(node => node.children.length), bodyChildren, "Leaving inspection must remove its temporary scroll space.");
      const note = "Prøv en tydelig handlingsorientert overskrift.", proposed = "Velg en tid som passer deg", edited = "Finn et annet tidspunkt";
      const noteField = view.ui.getByLabel("Hva vil du endre?", { exact: true }), proposalField = view.ui.getByLabel("Ny tekst", { exact: true });
      const inspect = async () => {
        await view.ui.getByRole("button", { name: "Se i skissen", exact: true }).press("Enter");
        await view.ui.getByRole("dialog", { name: "Nytt innspill", exact: true }).waitFor({ state: "hidden" });
        // Hiding the editor is synchronous; docking and reveal occur on the next frame.
        await view.frame.locator("body").evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
      };
      await view.note(note, selector); await view.ui.getByRole("button", { name: "Foreslå ny tekst", exact: true }).click(); await proposalField.fill(proposed);
      await view.ui.getByRole("button", { name: "Forhåndsvis teksten", exact: true }).press("Enter"); await inspect();
      const geometry = await view.frame.locator(selector).evaluate(node => {
        const r=node.getBoundingClientRect(), samples=[[.5,.25],[.5,.5],[.5,.75],[.1,.5],[.9,.5]].map(([dx,dy]) => { const x=r.left+r.width*dx,y=r.top+r.height*dy,hit=document.elementFromPoint(x,y);return {x,y,visible:node===hit||node.contains(hit),occludingTag:hit?.tagName||null,occludingClass:typeof hit?.className === "string" ? hit.className : ""}; });
        return { target: {x:r.x,y:r.y,width:r.width,height:r.height}, viewport:{width:innerWidth,height:innerHeight}, samples };
      });
      await view.screenshot("inspection-target-visible");
      if (evidence) fs.writeFileSync(path.join(evidence, `${name}-geometry.json`), `${JSON.stringify(geometry,null,2)}\n`);
      assert(geometry.samples.every(sample => sample.visible), "The inspected heading must be unobscured by the editor, preview bar and fixed header.");
      const editButton = view.ui.getByRole("button", { name: "Fortsett å redigere", exact: true });
      assert(await editButton.evaluate(node => node === node.getRootNode().activeElement), "Inspection must focus the return-to-edit action.");
      await editButton.press("Enter"); await assertNoExtraSpace(); assert.equal(await noteField.inputValue(),note); assert.equal(await proposalField.inputValue(),proposed);
      const resumedField = await proposalField.evaluate(node => { const field=node.getBoundingClientRect(),dialog=node.closest(".composer").getBoundingClientRect();return {focused:node===node.getRootNode().activeElement,field:{top:field.top,bottom:field.bottom},dialog:{top:dialog.top,bottom:dialog.bottom},scrollTop:node.closest(".composer").scrollTop}; });
      if (evidence) fs.writeFileSync(path.join(evidence, `${name}-resumed-field.json`), `${JSON.stringify(resumedField,null,2)}\n`);
      await view.screenshot("return-to-editor-focused-field");
      assert(resumedField.focused && resumedField.field.top >= resumedField.dialog.top && resumedField.field.bottom <= resumedField.dialog.bottom, "The focused proposal field must be visible inside the returned editor.");
      await proposalField.fill(edited); await inspect(); assert.equal(await view.frame.locator(selector).innerText(), edited);
      await view.ui.getByRole("button", { name: "Tilbakestill", exact: true }).press("Enter"); await assertNoExtraSpace(); assert.equal(await view.frame.locator(selector).innerText(),original);
      const resume = view.ui.getByRole("button", { name: "Fortsett utkast", exact: true });
      assert(await resume.evaluate(node => node === node.getRootNode().activeElement)); await resume.press("Enter");
      assert.equal(await noteField.inputValue(),note); assert.equal(await proposalField.inputValue(),edited);
      await view.ui.getByRole("button", { name: "Forhåndsvis teksten", exact: true }).press("Enter"); await inspect(); await view.page.keyboard.press("Escape"); await assertNoExtraSpace();
      assert.equal(await view.frame.locator(selector).innerText(),original); assert(await resume.evaluate(node => node === node.getRootNode().activeElement));
      await resume.press("Enter"); await view.ui.getByRole("button", { name: "Forhåndsvis teksten", exact: true }).press("Enter"); await inspect(); await editButton.press("Enter");
      await view.ui.getByRole("button", { name: "Forkast", exact: true }).press("Enter"); await assertNoExtraSpace(); assert.equal(await view.frame.locator(selector).innerText(),original);
      await view.note(note, selector); await view.ui.getByRole("button", { name: "Foreslå ny tekst", exact: true }).click(); await proposalField.fill(proposed);
      await view.ui.getByRole("button", { name: "Forhåndsvis teksten", exact: true }).press("Enter"); await inspect();
      view.write("Invitasjon · ny versjon mens tekst prøves"); const refresh=view.ui.locator('[data-action="refresh"]'); await refresh.waitFor();
      assert(await refresh.isDisabled(), "An inspected draft must still block a new version."); assert.equal(await view.frame.locator(selector).innerText(),proposed);
      await editButton.press("Enter"); assert.equal(await noteField.inputValue(),note); assert.equal(await proposalField.inputValue(),proposed);
      await view.screenshot("draft-preserved-during-new-version");
      await view.ui.getByRole("button", { name: "Forkast", exact: true }).press("Enter"); await view.shown("Invitasjon · ny versjon mens tekst prøves");
      const state=await view.list(); assert.equal(state.comments.length,0); assert.equal(state.submission,0);
      return { measurements: { geometry, resumedField, inspectionReturnFocused:true, bothFieldsPreserved:true, originalRestoredByUndoEscapeDiscard:true, temporarySpaceRemoved:true, newVersionBlockedUntilDiscard:true, savedComments:0, submittedBatches:0 } };
    }
  };
}
cases.push(
  previewInspectionCase("mobile-preview-inspection-390", {width:390,height:844}),
  previewInspectionCase("mobile-preview-inspection-320", {width:320,height:568}),
  previewInspectionCase("mobile-first-heading-preview-320", {width:320,height:568}, "h1")
);

async function main() {
  const allCases = [cases[0], { ...cases[0], name: "mobile-sent-context-next-version-320", viewport: { width: 320, height: 844 } }, ...cases.slice(1)];
  const selected = options.has("--case") ? allCases.filter(item => item.name === options.get("--case")) : allCases;
  if (!selected.length) { console.error(`Unknown case. Available: ${allCases.map(item => item.name).join(", ")}`); process.exitCode = 2; return; }
  const browser = await chromium.launch({ headless: true, ...(options.has("--browser-channel") ? { channel: options.get("--browser-channel") } : {}) });
  const results = [];
  try { for (const testcase of selected) { const result = await runCase(browser, testcase); results.push(result); console.log(`${result.status === "completed" ? "COMPLETE" : "FAIL"}: ${result.name}${result.error ? ` — ${result.error}` : ""}`); } }
  finally { await browser.close(); }
  const report = { kind: "simulated-role-review-cycle", realParticipants: 0, browser: options.get("--browser-channel") || "chromium", headless: true, aksel: akselVersion, results };
  if (evidence) fs.writeFileSync(path.join(evidence, options.has("--case") ? `review-cycle-${selected[0].name}.json` : "review-cycle-results.json"), `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify(report)); if (results.some(item => item.status === "failed")) process.exitCode = 1;
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
