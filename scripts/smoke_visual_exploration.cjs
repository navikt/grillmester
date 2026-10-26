#!/usr/bin/env node
"use strict";

// Synthetic concept studies exercised through the portable preview's public UI.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createRequire } = require("node:module");
const { spawn } = require("node:child_process");
// Comparing variants belongs to Prøv; leave Endre first when needed.
async function startComparison(ui) {
  const compare = ui.getByRole("button", { name: "Sammenlign varianter", exact: true });
  if (!(await compare.isVisible())) await ui.getByRole("button", { name: "Prøv", exact: true }).click();
  await compare.click();
}
// «Juster visning» belongs to Prøv; leave Endre first when its Vis bar is hidden.
async function openAdjust(ui) {
  const adjust = ui.getByRole("button", { name: "Juster visning", exact: true });
  if (!(await adjust.isVisible())) await ui.getByRole("button", { name: "Prøv", exact: true }).click();
  await adjust.click();
}
// «Behold denne delen» saves an ordinary wish that names the part.
const keepWishes = batch => batch.comments.filter(item => item.text.startsWith("Behold denne delen.") && item.context);
const options = new Map();
for (let index = 2; index < process.argv.length; index += 1) {
  const flag = process.argv[index];
  if (!["--playwright-module", "--browser-channel", "--evidence-dir", "--aksel-project", "--case"].includes(flag) || !process.argv[index + 1] || process.argv[index + 1].startsWith("--")) {
    console.error("Usage: node scripts/smoke_visual_exploration.cjs --aksel-project DIRECTORY [--playwright-module PATH] [--browser-channel chrome] [--evidence-dir DIRECTORY] [--case NAME]"); process.exit(2);
  }
  options.set(flag, process.argv[++index]);
}
if (!options.has("--aksel-project")) { console.error("Supply a project with existing, matching Aksel React and CSS packages. Nothing is installed."); process.exit(2); }
let chromium;
try { ({ chromium } = require(options.get("--playwright-module") || "playwright")); }
catch { console.error("Supply an existing Playwright installation. Nothing is installed."); process.exit(2); }
const project = path.resolve(options.get("--aksel-project"));
const installed = createRequire(path.join(project, "package.json"));
const React = installed("react"), C = installed("@navikt/ds-react");
const { renderToStaticMarkup } = installed("react-dom/server");
const packageRoot = path.join(project, "node_modules/@navikt");
const version = JSON.parse(fs.readFileSync(path.join(packageRoot, "ds-react/package.json"))).version;
assert.equal(version, JSON.parse(fs.readFileSync(path.join(packageRoot, "ds-css/package.json"))).version);
assert.match(version, /^8\./, "These fixtures use the Aksel v8 component contract.");
const css = ["index.min.css", "index.css"].map(name => path.join(packageRoot, "ds-css/dist", name)).find(file => fs.existsSync(file));
assert(css, "The supplied project must contain installed Aksel CSS.");
const runtime = path.resolve(__dirname, "../plugin/skills/design-prototype/scripts");
const evidence = options.has("--evidence-dir") ? path.resolve(options.get("--evidence-dir")) : null;
if (evidence) fs.mkdirSync(evidence, { recursive: true });
let componentNumber = 0;
const h = React.createElement;
const render = element => renderToStaticMarkup(element, { identifierPrefix: `study-${++componentNumber}-` });
const escape = value => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll('"', "&quot;");
const heading = (text, level = "1") => render(h(C.Heading, { level, size: level === "1" ? "large" : level === "2" ? "medium" : "small" }, text));
const body = text => render(h(C.BodyShort, null, text));
const button = (text, value, id, variant = "secondary", danger = false) => render(h(C.Button, { type: "button", variant, id, "data-vc-control": "state", "data-vc-value": value, ...(danger ? { "data-color": "danger" } : {}) }, text));
const alert = (status, title, text) => render(h(C.LocalAlert, { status }, h(C.LocalAlert.Header, null, h(C.LocalAlert.Title, null, title)), h(C.LocalAlert.Content, null, text)));
const tag = (text, color = "info") => render(h(C.Tag, { size: "small", variant: "moderate", "data-color": color }, text));
const state = (value, content) => `<div class="x-state x-stack" data-state="${value}">${content}</div>`;
const actions = content => `<div class="x-actions">${content}</div>`;
const summary = entries => `<dl class="x-summary">${entries.map(([label, value]) => `<div><dt>${escape(label)}</dt><dd>${escape(value)}</dd></div>`).join("")}</dl>`;
const control = (id, label, initial, entries) => ({ id, label, initial, type: "select", options: entries.map(([value, label]) => ({ value, label })) });
const stateControl = (initial, entries) => control("state", "Situasjon", initial, entries);
const target = (variant, key, label, controls, content) => ({ descriptor: { variant, key, label, controls }, html: `<section class="x-target x-stack" data-vc-key="${key}" ${controls.map(item => `data-vc-setting-${item.id}="${item.initial}"`).join(" ")}>${content}</section>` });
const sharedCss = `<style>
.x-study{display:grid;gap:var(--ax-space-24)}.x-intro{max-width:70ch}.x-variants{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--ax-space-24);align-items:start}.x-card{min-width:0;container-type:inline-size;display:grid;gap:var(--ax-space-24);padding:var(--ax-space-24);border:1px solid var(--ax-border-neutral-subtle);border-radius:var(--ax-radius-12);background:var(--ax-bg-default)}.x-stack{display:grid;gap:var(--ax-space-16);min-width:0}.x-target{padding:var(--ax-space-16);border:1px solid var(--ax-border-neutral-subtle);border-radius:var(--ax-radius-8)}.x-target>.x-state{display:none}.x-target[data-vc-setting-state=error]>.x-state[data-state=error],.x-target[data-vc-setting-state=review]>.x-state[data-state=review],.x-target[data-vc-setting-state=complete]>.x-state[data-state=complete],.x-target[data-vc-setting-state=loaded]>.x-state[data-state=loaded],.x-target[data-vc-setting-state=loading]>.x-state[data-state=loading],.x-target[data-vc-setting-state=empty]>.x-state[data-state=empty],.x-target[data-vc-setting-state=booked]>.x-state[data-state=booked],.x-target[data-vc-setting-state=change]>.x-state[data-state=change],.x-target[data-vc-setting-state=cancel-confirm]>.x-state[data-state=cancel-confirm],.x-target[data-vc-setting-state=cancelled]>.x-state[data-state=cancelled]{display:grid}.x-actions{display:flex;flex-wrap:wrap;gap:var(--ax-space-12)}.x-summary{display:grid;gap:var(--ax-space-12);margin:0}.x-summary>div{display:grid;gap:var(--ax-space-4)}.x-summary dt{font-weight:600}.x-summary dd{margin:0}.x-fact{padding:var(--ax-space-12);background:var(--ax-bg-neutral-soft);border-radius:var(--ax-radius-4)}.x-detail{display:none}.x-target[data-vc-setting-detail=full] .x-detail{display:block}.x-lanes{display:grid;gap:var(--ax-space-16)}.x-lane{display:grid;gap:var(--ax-space-12);align-content:start}.x-task{display:grid;gap:var(--ax-space-8);padding:var(--ax-space-16);background:var(--ax-bg-neutral-soft);border-radius:var(--ax-radius-8)}.x-target[data-vc-setting-density=compact] .x-task{padding:var(--ax-space-8)}.x-target[data-vc-setting-density=compact] .x-lanes{gap:var(--ax-space-8)}.x-loading{display:flex;align-items:center;gap:var(--ax-space-16);padding-block:var(--ax-space-24)}.x-time-friday{display:none}.x-change:has(input[value=friday]:checked) .x-time-thursday{display:none}.x-change:has(input[value=friday]:checked) .x-time-friday{display:block}.x-card-title{display:grid;gap:var(--ax-space-8)}
.x-table-task{display:grid;justify-items:start;gap:var(--ax-space-8)}.x-table-compact{display:none}.x-target[data-vc-setting-density=compact] .x-table-comfortable{display:none}.x-target[data-vc-setting-density=compact] .x-table-compact{display:block}
@container(min-width:640px){.x-lanes{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:900px){.x-variants{grid-template-columns:1fr}.x-card{padding:var(--ax-space-16)}.x-target{padding:var(--ax-space-12)}}
</style>`;
function compose(title, brief, variants, makeTargets) {
  const targets = [];
  const cards = variants.map(({ key, label }) => {
    const sections = makeTargets(key); targets.push(...sections.map(item => item.descriptor));
    return `<article class="x-card" data-vc-variant="${key}"><header class="x-card-title">${heading(label, "2")}</header>${sections.map(item => item.html).join("")}</article>`;
  });
  return { title, html: `${sharedCss}<div class="x-study">${heading(title)}<div class="x-intro x-stack">${body(brief)}${body("Eksempeldata. Bare «Send innspill» sender tilbakemelding.")}</div><div class="x-variants" data-vc-variants>${cards.join("")}</div></div>`, design: { version: 1, variants, targets } };
}
function mobileSketch() {
  const variants = [{ key: "steps", label: "Ett steg om gangen" }, { key: "overview", label: "Rett fra oversikten" }];
  const facts = [["Reise", "Solvik – servicesenteret"], ["Møte", "12. november kl. 10.00"], ["Transport", "Buss"]];
  return compose("Hvordan retter du én manglende opplysning?", "Samme reise i begge forslag: Én billettpris mangler. Prøv å rette, se over og gå tilbake før du bekrefter.", variants, key => {
    const costId = `${key}-fare`;
    const error = render(h(C.ErrorSummary, { heading: "Du må rette én opplysning", headingTag: "h3" }, h(C.ErrorSummary.Item, { href: `#${costId}` }, "Oppgi billettprisen")));
    const field = render(h(C.TextField, { id: costId, label: "Billettpris i kroner", description: "Eksempel: 340 kroner tur-retur.", inputMode: "numeric", autoComplete: "off", error: "Oppgi billettprisen", defaultValue: "" }));
    const intro = key === "steps" ? `${tag("Steg 2 av 3")}${heading("Reiseutgiften", "3")}` : `${heading("Se over reisen", "3")}${summary(facts)}`;
    const flow = target(key, "application", "Søknadsflyt", [stateControl("error", [["error", "Manglende opplysning"], ["review", "Kontroller opplysningene"], ["complete", "Bekreftet eksempel"]])],
      state("error", `${intro}${error}${field}${key === "steps" ? summary(facts) : ""}${actions(button("Fortsett til oversikt", "review", `${key}-next`, "primary"))}`) +
      state("review", `${tag("Steg 3 av 3")}${heading("Er opplysningene riktige?", "3")}${summary([...facts, ["Billettpris", "340 kroner tur-retur"]])}${actions(button("Endre opplysninger", "error", `${key}-back`) + button("Bekreft eksemplet", "complete", `${key}-confirm`, "primary"))}`) +
      state("complete", `${alert("success", "Eksemplet er bekreftet", "Dette er en skisse. Ingen søknad er sendt.")}${actions(button("Se gjennom igjen", "review", `${key}-again`))}`));
    const help = target(key, "help", "Hjelp før bekreftelse", [control("detail", "Mengde forklaring", "short", [["short", "Kort hjelp"], ["full", "Utfyllende hjelp"]])], `${heading("Usikker på prisen?", "3")}${body("Du kan gå tilbake før du bekrefter.")}<div class="x-detail">${body("Finn beløpet på billetten. Eksemplet bruker 340 kroner tur-retur. Du kan endre opplysningen fra oversikten.")}</div>`);
    return [flow, help];
  });
}
const tasks = [{ id: "RF-104", title: "Mangler vedlegg", due: "I dag", status: "Følg opp", color: "warning" }, { id: "RF-105", title: "Venter på svar", due: "I morgen", status: "Venter", color: "info" }, { id: "RF-106", title: "Avklart", due: "Fredag", status: "Ferdig", color: "success" }];
function operationsSketch() {
  const variants = [{ key: "list", label: "Prioritert liste" }, { key: "board", label: "Arbeidssteg" }];
  return compose("Hva trenger oppfølging nå?", "Begge forslag viser de samme tre oppgavene. Prøv feil, venting og et tomt utvalg før du går tilbake til oppgavene.", variants, key => {
    const table = size => render(h(C.Table, { size }, h(C.Table.Header, null, h(C.Table.Row, null, h(C.Table.HeaderCell, { scope: "col" }, "Oppgave"), h(C.Table.HeaderCell, { scope: "col" }, "Frist"))), h(C.Table.Body, null, tasks.map(item => h(C.Table.Row, { key: item.id }, h(C.Table.HeaderCell, { scope: "row" }, h("div", { className: "x-table-task" }, h("span", null, `${item.id} · ${item.title}`), h(C.Tag, { size: "small", variant: "moderate", "data-color": item.color }, item.status))), h(C.Table.DataCell, null, item.due))))));
    const lanes = `<div class="x-lanes">${tasks.map(item => `<section class="x-lane">${tag(item.status, item.color)}<article class="x-task">${heading(item.id, "3")}${body(item.title)}${body(`Frist: ${item.due}`)}</article></section>`).join("")}</div>`;
    const states = [stateControl("loaded", [["loaded", "Oppgaver lastet"], ["error", "Kunne ikke laste"], ["loading", "Henter oppgaver"], ["empty", "Tomt utvalg"]]), control("density", "Luft mellom oppgaver", "comfortable", [["comfortable", "Romslig"], ["compact", "Kompakt"]])];
    const flow = target(key, "overview", "Oppgaveoversikt", states,
      state("loaded", `${heading("Tre oppgaver · én haster", "3")}${key === "list" ? `<div class="x-table-comfortable">${table("medium")}</div><div class="x-table-compact">${table("small")}</div>` : lanes}`) +
      state("error", `${alert("error", "Vi fikk ikke hentet oppgavene", "Vi kan ikke vise om oversikten er oppdatert. Prøv å hente den på nytt.")}${actions(button("Prøv igjen", "loading", `${key}-retry`, "primary"))}`) +
      state("loading", `<div class="x-loading">${render(h(C.Loader, { size: "large", title: "Henter oppgavene" }))}${body("Henter oppgavene …")}</div>`) +
      state("empty", `${alert("announcement", "Ingen oppgaver i dette utvalget", "Du har fortsatt tre oppgaver totalt. Vis alle for å fjerne utvalget.")}${actions(button("Vis alle oppgaver", "loaded", `${key}-all`, "primary"))}`));
    const legend = target(key, "meaning", "Forklaring av prioritet", [control("detail", "Mengde forklaring", "short", [["short", "Kort forklaring"], ["full", "Med eksempel"]])], `${heading("Hva betyr «én haster»?", "3")}${body("Én oppgave har frist i dag.")}<div class="x-detail">${body("RF-104 mangler vedlegg. Frist vises sammen med oppgaven, slik at farge alene ikke avgjør hva du gjør først.")}</div>`);
    return [flow, legend];
  });
}
function appointmentSketch() {
  const variants = [{ key: "current", label: "Avtalen først" }, { key: "options", label: "Valgene først" }];
  const facts = [["Når", "Onsdag 18. november kl. 10.00"], ["Hvor", "Servicesenteret i Solvik"], ["Varighet", "30 minutter"]];
  return compose("Hvordan endrer du avtalen trygt?", "Begge forslag gjelder samme avtale og de samme to ledige tidene. Prøv å endre tidspunkt, beholde timen og angre en avbestilling.", variants, key => {
    const choices = render(h(C.RadioGroup, { legend: "Velg et nytt tidspunkt", name: `${key}-appointment`, defaultValue: "thursday" }, h(C.Radio, { value: "thursday" }, "Torsdag 19. november kl. 09.30"), h(C.Radio, { value: "friday" }, "Fredag 20. november kl. 13.00")));
    const change = button("Endre tidspunkt", "change", `${key}-change`, "primary"), cancel = button("Avbestill timen", "cancel-confirm", `${key}-cancel`, "tertiary", true);
    const flow = target(key, "appointment", "Avtale og endring", [stateControl("booked", [["booked", "Avtalen er beholdt"], ["change", "Velg ny tid"], ["cancel-confirm", "Bekreft avbestilling"], ["cancelled", "Avbestilt eksempel"]])],
      state("booked", `${heading("Din avtale", "3")}${key === "options" ? actions(change) : ""}${summary(facts)}${actions((key === "current" ? change : "") + cancel)}`) +
      state("change", `<div class="x-change x-stack">${choices}<div class="x-fact x-time-thursday">${body("Du ser på torsdag 19. november kl. 09.30.")}</div><div class="x-fact x-time-friday">${body("Du ser på fredag 20. november kl. 13.00.")}</div>${body("Avtalen er ikke endret. Denne skissen utforsker valg og avbestilling.")}${actions(button("Behold nåværende time", "booked", `${key}-keep-current`))}</div>`) +
      state("cancel-confirm", `${alert("warning", "Vil du avbestille denne timen?", "Du mister timen onsdag 18. november kl. 10.00. Det bestilles ingen ny time.")}${actions(button("Behold timen", "booked", `${key}-keep`, "primary") + button("Ja, avbestill", "cancelled", `${key}-confirm-cancel`, "secondary", true))}`) +
      state("cancelled", `${alert("success", "Timen er avbestilt i eksemplet", "Vi prøver her om en angremulighet er forståelig. Ingen virkelig time er avbestilt.")}${actions(button("Angre avbestilling", "booked", `${key}-undo`, "primary"))}`));
    const help = target(key, "consequence", "Forklaring av konsekvens", [control("detail", "Mengde forklaring", "short", [["short", "Kort forklaring"], ["full", "Med neste steg"]])], `${heading("Vil du fortsatt ha en time?", "3")}${body("Velg «Endre tidspunkt» for å se andre tider.")}<div class="x-detail">${body("Ved avbestilling bestilles ingen ny time. Du beholder den nåværende avtalen mens du ser på andre tidspunkt.")}</div>`);
    return [flow, help];
  });
}

async function until(check, label, timeout = 12000) {
  const deadline = Date.now() + timeout;
  do { const value = await check(); if (value) return value; await new Promise(resolve => setTimeout(resolve, 80)); } while (Date.now() < deadline);
  throw new Error(`Timed out: ${label}`);
}
async function stop(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const closed = new Promise(resolve => child.once("close", resolve)); child.kill("SIGTERM");
  const timer = setTimeout(() => child.kill("SIGKILL"), 5000); await closed; clearTimeout(timer);
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
    let out = "", err = ""; const timer = setTimeout(() => child.kill("SIGKILL"), 20000);
    child.stdout.on("data", data => { out += data; }); child.stderr.on("data", data => { err += data; });
    child.once("error", error => { clearTimeout(timer); reject(error); });
    child.once("close", code => { clearTimeout(timer); if (code) reject(new Error(err || `Feedback command failed (${code}).`)); else { try { resolve(JSON.parse(out)); } catch { reject(new Error("Feedback command returned invalid JSON.")); } } });
  });
}
function controls(page) {
  const frame = page.frameLocator("#vc-preview"), ui = frame.locator("[data-visual-feedback]");
  const workshop = ui.getByRole("region", { name: "Juster visningen", exact: true });
  const closeFeedback = async () => { const close = ui.getByRole("button", { name: "Lukk innspill", exact: true }); if (await close.isVisible()) await close.click(); };
  const closeWorkshop = async () => { const close = workshop.getByRole("button", { name: "Lukk justeringer", exact: true }); if (await close.isVisible()) await close.click(); };
  const adjust = async (key) => { await closeFeedback(); if (!(await workshop.isVisible())) await openAdjust(ui); if (key) await workshop.getByLabel("Velg del", { exact: true }).selectOption(key); };
  const browse = async () => { await closeFeedback(); await closeWorkshop(); const button = ui.getByRole("button", { name: "Prøv", exact: true }); if (await button.getAttribute("aria-pressed") !== "true") await button.click(); };
  return { page, frame, ui, workshop, closeFeedback, closeWorkshop, adjust, browse,
    target: (variant, key) => frame.locator(`[data-vc-variant="${variant}"] [data-vc-key="${key}"]`),
    async set(key, label, value) { await adjust(key); await workshop.getByLabel(label, { exact: true }).selectOption(value); await browse(); },
    async keep(key, note) { await adjust(key); await workshop.getByLabel("Merknad", { exact: true }).fill(note); await workshop.getByRole("button", { name: "Behold denne delen", exact: true }).click(); await ui.getByRole("region", { name: "Innspill til prototypen", exact: true }).waitFor(); await closeFeedback(); },
    async note(selector, text) { await closeWorkshop(); await closeFeedback(); const mode = ui.getByRole("button", { name: "Endre", exact: true }); if (await ui.locator('[data-action="change-ask"]').getAttribute("aria-pressed") !== "true") await mode.click(); await frame.locator(selector).click(); await ui.getByLabel("Hva vil du endre?", { exact: true }).fill(text); await ui.getByRole("button", { name: "Lagre innspill", exact: true }).click(); await ui.getByRole("button", { name: "Lagre innspill", exact: true }).waitFor({ state: "hidden" }); },
    async openFeedback() { if (!(await ui.getByRole("region", { name: "Innspill til prototypen", exact: true }).isVisible())) await ui.locator('[data-action="panel"]').click(); },
  };
}
async function tabTo(view, locator) {
  for (let count = 0; count < 100; count += 1) {
    if (await locator.evaluate(node => node === document.activeElement)) return count;
    await view.page.keyboard.press("Tab");
  }
  throw new Error("Keyboard did not reach the expected prototype action.");
}
async function assertState(view, variant, targetKey, expected) {
  const part = view.target(variant, targetKey);
  assert.equal(await part.getAttribute("data-vc-setting-state"), expected);
  assert(await part.locator(`:scope > [data-state="${expected}"]`).isVisible());
}
async function workshopMatches(view, key, value) {
  await view.adjust(key); assert.equal(await view.workshop.getByLabel("Situasjon", { exact: true }).inputValue(), value); await view.browse();
}
async function cleanLocal(view) {
  const data = await view.list(); assert.equal(data.submission, 0); assert.equal(data.comments.length, 0);
}
async function replay(view, comment, variant, key, expected) {
  await view.openFeedback();
  const card = view.ui.locator(`article[data-id="${comment.id}"]`);
  await card.getByRole("button", { name: "Vis situasjon", exact: true }).click();
  await assertState(view, variant, key, expected); await view.closeFeedback();
}
async function layoutMetrics(view) {
  return view.frame.locator(".x-study").evaluate(node => {
    const ids = [...document.querySelectorAll("[id]")].map(item => item.id), duplicates = [...new Set(ids.filter((id, i) => ids.indexOf(id) !== i))];
    const button = node.querySelector("button"), style = getComputedStyle(button);
    return { viewport: { width: innerWidth, height: innerHeight }, contentWidth: node.getBoundingClientRect().width, documentWidth: document.documentElement.scrollWidth, duplicateIds: duplicates, button: { className: button.className, paddingInline: style.paddingInline, fontSize: style.fontSize, background: style.backgroundColor } };
  });
}
async function comparison(view) {
  await startComparison(view.ui);
  const boxes = await view.frame.locator("[data-vc-variant]").evaluateAll(nodes => nodes.map(node => ({ width: node.getBoundingClientRect().width, visible: Boolean(node.getClientRects().length) && getComputedStyle(node).display !== "none" })));
  await view.screenshot("comparison");
  if (view.viewport.width > 900) assert(Math.abs(boxes[0].width - boxes[1].width) < 1, "Compared concepts must get equal space.");
  await view.ui.getByRole("button", { name: "Avslutt sammenligning", exact: true }).click(); await view.browse(); return boxes;
}
const cases = [
  { name: "mobile-correction", viewport: { width: 390, height: 844 }, make: mobileSketch,
    async run(view) {
      await view.browse();
      const target = view.target("steps", "application");
      const summaryItem = target.getByRole("link", { name: "Oppgi billettprisen", exact: true });
      assert.equal(await summaryItem.getAttribute("href"), "#steps-fare");
      const beforeUrl = view.page.url(), beforeHash = await view.frame.locator("html").evaluate(() => location.hash);
      await summaryItem.click(); const fare = view.frame.locator("#steps-fare");
      assert(await fare.evaluate(node => document.activeElement === node), "The real ErrorSummary link must focus its field.");
      await view.page.keyboard.press("Shift+Tab"); assert(await summaryItem.evaluate(node => document.activeElement === node));
      await view.page.keyboard.press("Enter"); assert(await fare.evaluate(node => document.activeElement === node), "Keyboard activation must reach the same field.");
      assert.equal(view.page.url(), beforeUrl); assert.equal(await view.frame.locator("html").evaluate(() => location.hash), beforeHash, "Local links must not navigate the iframe.");
      await view.page.keyboard.type("340");
      const tabs = await tabTo(view, view.frame.locator("#steps-next")); await view.page.keyboard.press("Enter");
      await assertState(view, "steps", "application", "review"); assert(await target.evaluate(node => document.activeElement === node), "A hidden forward button must move focus to its still-visible target.");
      const reviewVisibility = await target.evaluate(node => {
        const heading = node.querySelector('[data-state="review"] h3').getBoundingClientRect(), firstFact = node.querySelector('[data-state="review"] dd').getBoundingClientRect();
        return { headingTop: heading.top, headingBottom: heading.bottom, firstFactBottom: firstFact.bottom, headerBottom: document.querySelector("body > .vc-header").getBoundingClientRect().bottom, viewportHeight: innerHeight };
      });
      assert(reviewVisibility.headingTop >= reviewVisibility.headerBottom + 1 && reviewVisibility.firstFactBottom < reviewVisibility.viewportHeight, "Changing the mobile step must reveal the new heading and first fact below the fixed header.");
      await view.screenshot("review"); await workshopMatches(view, "steps/application", "review");
      await view.frame.locator("#steps-back").click(); assert.equal(await fare.inputValue(), "340", "Going back preserves the typed sample value.");
      await view.frame.locator("#steps-next").click(); await view.frame.locator("#steps-confirm").press("Space"); await assertState(view, "steps", "application", "complete");
      await view.frame.locator("#steps-again").click(); await assertState(view, "steps", "application", "review"); await cleanLocal(view);
      await view.note('[data-vc-variant="steps"] [data-state="review"] h3', "Behold muligheten til å rette direkte fra oversikten.");
      const comment = (await view.list()).comments[0]; assert.deepEqual(comment.context, { variant: "steps", target: "application", values: { state: "review" } });
      await view.set("steps/application", "Situasjon", "error"); await replay(view, comment, "steps", "application", "review");
      await view.keep("overview/help", "Ta med hjelpen fra oversiktsforslaget i den trinnvise flyten.");
      const batch = await view.send(2); assert.equal(batch.comments.length, 2); assert.deepEqual(keepWishes(batch).map(item => item.context.variant), ["overview"]);
      assert(!JSON.stringify(batch).includes('"340"'), "A native field value must not be collected as comment context.");
      await view.screenshot("combined-feedback"); await view.browse();
      const metrics = await layoutMetrics(view); assert.equal(metrics.duplicateIds.length, 0); assert(metrics.documentWidth <= metrics.viewport.width + 1);
      return { ...metrics, errorSummaryFocusedField: true, errorSummaryKeyboardFocusedField: true, fragmentKeptUrlUnchanged: true, tabsFromFareToNext: tabs, reviewVisibility, statesVisited: ["error", "review", "error", "review", "complete", "review"], batch: { comments: batch.comments.length, keepWishes: keepWishes(batch).length }, contextRestored: true, typedValuePreserved: true };
    } },
  { name: "operations-recovery", viewport: { width: 1440, height: 1000 }, make: operationsSketch,
    async run(view) {
      await view.browse();
      const densityHeights = {};
      for (const variant of ["list", "board"]) {
        const overview = view.target(variant, "overview");
        for (const task of tasks) for (const fact of [task.id, task.title, task.due, task.status]) assert((await overview.innerText()).includes(fact), "Both directions must expose the same task facts.");
        const comfortable = (await overview.boundingBox()).height;
        await view.set(`${variant}/overview`, "Luft mellom oppgaver", "compact"); const compact = (await overview.boundingBox()).height;
        assert(compact < comfortable, "Every declared density control must actually change its target."); densityHeights[variant] = { comfortable, compact };
        await view.set(`${variant}/overview`, "Luft mellom oppgaver", "comfortable");
      }
      const compared = await comparison(view);
      await view.set("board/overview", "Situasjon", "error"); await view.screenshot("load-error");
      const tabs = await tabTo(view, view.frame.locator("#board-retry")); await view.page.keyboard.press("Enter"); await assertState(view, "board", "overview", "loading");
      assert(await view.target("board", "overview").evaluate(node => node === document.activeElement));
      await workshopMatches(view, "board/overview", "loading"); await view.screenshot("loading");
      await view.set("board/overview", "Situasjon", "empty"); await view.frame.locator("#board-all").press("Space"); await assertState(view, "board", "overview", "loaded"); await cleanLocal(view);
      await view.set("board/overview", "Situasjon", "error"); await view.set("board/overview", "Luft mellom oppgaver", "compact");
      await view.note('[data-vc-variant="board"] [data-state="error"] button', "Feilen må si om det er trygt å vente, og hva jeg kan gjøre nå.");
      await assertState(view, "board", "overview", "error");
      const comment = (await view.list()).comments[0]; assert.deepEqual(comment.context, { variant: "board", target: "overview", values: { state: "error", density: "compact" } });
      await view.set("board/overview", "Situasjon", "loaded"); await view.set("board/overview", "Luft mellom oppgaver", "comfortable");
      await replay(view, comment, "board", "overview", "error"); assert.equal(await view.target("board", "overview").getAttribute("data-vc-setting-density"), "compact");
      await view.set("list/overview", "Luft mellom oppgaver", "compact"); await view.keep("list/overview", "Behold den kompakte listen for rask gjennomgang av frister.");
      await view.keep("board/meaning", "Behold forklaringen som ikke er avhengig av farge.");
      const batch = await view.send(3); assert.equal(batch.comments.length, 3); assert.deepEqual(keepWishes(batch).map(item => item.context.variant).sort(), ["board", "list"]);
      await view.screenshot("mixed-keep-wishes"); await view.browse(); const metrics = await layoutMetrics(view); assert(metrics.documentWidth <= metrics.viewport.width + 1);
      return { ...metrics, comparison: compared, densityHeights, keyboardTabsToRetry: tabs, sharedTasks: tasks.length, statesVisited: ["loaded", "error", "loading", "empty", "loaded"], batch: { comments: batch.comments.length, keepWishes: keepWishes(batch).length }, contextRestored: true, commentButtonDidNotAct: true };
    } },
  { name: "appointment-reversal", viewport: { width: 1280, height: 960 }, make: appointmentSketch,
    async run(view) {
      await view.browse(); const compared = await comparison(view);
      await view.frame.locator("#current-change").click(); const friday = view.target("current", "appointment").getByRole("radio", { name: "Fredag 20. november kl. 13.00", exact: true }); await friday.check();
      assert(await view.target("current", "appointment").locator(".x-time-friday").isVisible());
      await view.frame.locator("#current-keep-current").click(); await view.frame.locator("#current-change").click(); assert(await friday.isChecked(), "A local choice remains when returning to the same authored situation.");
      await view.frame.locator("#current-keep-current").click(); const tabs = await tabTo(view, view.frame.locator("#current-cancel")); await view.page.keyboard.press("Enter"); await assertState(view, "current", "appointment", "cancel-confirm");
      assert(await view.target("current", "appointment").evaluate(node => node === document.activeElement)); await view.screenshot("confirm-cancellation");
      const safeTabs = await tabTo(view, view.frame.locator("#current-keep")); await view.page.keyboard.press("Space"); await assertState(view, "current", "appointment", "booked");
      await view.frame.locator("#current-cancel").click(); await view.frame.locator("#current-confirm-cancel").click(); await assertState(view, "current", "appointment", "cancelled");
      const undoTabs = await tabTo(view, view.frame.locator("#current-undo")); await view.page.keyboard.press("Space"); await assertState(view, "current", "appointment", "booked"); await cleanLocal(view);
      await view.frame.locator("#current-cancel").click(); await view.note('[data-vc-variant="current"] [data-state="cancel-confirm"] button[data-vc-value="booked"]', "Behold en tydelig vei tilbake. Avklar om angre faktisk kan tilbys før utvikling.");
      await assertState(view, "current", "appointment", "cancel-confirm"); const comment = (await view.list()).comments[0]; assert.deepEqual(comment.context, { variant: "current", target: "appointment", values: { state: "cancel-confirm" } });
      await view.set("current/appointment", "Situasjon", "booked"); await replay(view, comment, "current", "appointment", "cancel-confirm");
      await view.keep("options/consequence", "Ta med konsekvensforklaringen sammen med avtalen først.");
      const batch = await view.send(2); assert.equal(batch.comments.length, 2); assert.equal(keepWishes(batch).length, 1); assert(!JSON.stringify(batch).includes("friday"), "Native radio values must not be copied into the feedback protocol.");
      await view.screenshot("consequence-feedback"); await view.browse(); const metrics = await layoutMetrics(view); assert.equal(metrics.duplicateIds.length, 0); assert(metrics.documentWidth <= metrics.viewport.width + 1);
      return { ...metrics, comparison: compared, keyboardTabs: { cancel: tabs, safeReturn: safeTabs, undo: undoTabs }, statesVisited: ["booked", "change", "booked", "cancel-confirm", "booked", "cancel-confirm", "cancelled", "booked"], batch: { comments: batch.comments.length, keepWishes: keepWishes(batch).length }, contextRestored: true, localRadioPreserved: true };
    } },
];
async function runCase(browser, testcase) {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "grillmester-exploration-"));
  const consumer = path.join(temporary, "project"), cssDirectory = path.join(consumer, "node_modules/@navikt/ds-css/dist"); fs.mkdirSync(cssDirectory, { recursive: true }); fs.copyFileSync(css, path.join(cssDirectory, "index.min.css"));
  const child = spawn(process.execPath, [path.join(runtime, "server.js"), "--project-dir", consumer], { stdio: ["ignore", "pipe", "pipe"] });
  let context, page; const errors = [], remoteResources = [];
  try {
    context = await browser.newContext({ viewport: testcase.viewport, reducedMotion: "reduce" });
    const info = await start(child), sketch = testcase.make();
    fs.writeFileSync(path.join(info.screen_dir, `01-${testcase.name}.design.json`), JSON.stringify(sketch.design)); fs.writeFileSync(path.join(info.screen_dir, `01-${testcase.name}.html`), sketch.html);
    page = await context.newPage(); page.setDefaultTimeout(10000); page.on("pageerror", error => errors.push(error.message));
    page.on("requestfinished", request => { if (!request.url().startsWith(new URL(info.url).origin) && !/^(data|blob):/.test(request.url())) remoteResources.push(new URL(request.url()).origin); });
    await page.goto(info.url); const view = controls(page); await view.ui.getByRole("button", { name: "Endre", exact: true }).waitFor(); await view.frame.getByRole("heading", { name: sketch.title, exact: true }).waitFor();
    view.viewport = testcase.viewport; view.list = () => command(info, "list");
    view.screenshot = async name => { if (evidence) { await page.locator("#vc-status").filter({ hasText: /^Tilkoblet$/ }).waitFor(); await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))); await page.screenshot({ path: path.join(evidence, `${testcase.name}-${name}.png`), animations: "disabled" }); } };
    view.send = async count => { const before = await view.list(); assert.equal(before.submission, 0, "These studies send exactly one explicit batch each."); await view.openFeedback(); await view.ui.getByRole("button", { name: `Send ${count} innspill`, exact: true }).click(); const batch = await command(info, "wait", ["--after", String(before.submission), "--timeout", "10"]); assert.equal(batch.type, "feedback-submission"); assert.equal(batch.submission, 1); return batch; };
    await view.screenshot("initial"); const metrics = await testcase.run(view);
    assert.deepEqual(errors, [], "No browser exception is expected."); assert.deepEqual(remoteResources, [], "No external resource may finish loading.");
    return { name: testcase.name, question: sketch.title, variants: sketch.design.variants, status: "passed", metrics, browserErrors: errors, externalResources: remoteResources };
  } catch (error) {
    if (page && evidence) await page.screenshot({ path: path.join(evidence, `${testcase.name}-failure.png`), animations: "disabled" }).catch(() => {});
    return { name: testcase.name, status: "failed", error: error.message.replace(/http:\/\/127\.0\.0\.1:[^\s)]+/g, "[local preview]") };
  } finally {
    try { await context?.close(); }
    finally { await stop(child); fs.rmSync(temporary, { recursive: true, force: true }); }
  }
}
async function main() {
  const selected = options.has("--case") ? cases.filter(item => item.name === options.get("--case")) : cases;
  if (!selected.length) { console.error(`Unknown case. Available: ${cases.map(item => item.name).join(", ")}`); process.exitCode = 2; return; }
  const browser = await chromium.launch({ headless: true, ...(options.has("--browser-channel") ? { channel: options.get("--browser-channel") } : {}) });
  const results = [];
  try { for (const testcase of selected) { const result = await runCase(browser, testcase); results.push(result); console.log(`${result.status === "passed" ? "PASS" : "FAIL"}: ${result.name}${result.error ? ` — ${result.error}` : ""}`); } }
  finally { await browser.close(); }
  const report = { kind: "simulated-role-concept-exploration", browser: options.get("--browser-channel") || "chromium", headless: true, aksel: version, realParticipants: 0, results };
  if (evidence) fs.writeFileSync(path.join(evidence, options.has("--case") ? `exploration-${selected[0].name}-results.json` : "exploration-results.json"), `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify(report)); if (results.some(item => item.status !== "passed")) process.exitCode = 1;
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
