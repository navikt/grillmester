#!/usr/bin/env node
"use strict";

// Optional browser smoke. Uses an existing Playwright installation and browser;
// it never installs dependencies or touches a consumer repository.
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const args = process.argv.slice(2);
const options = new Map();
for (let index = 0; index < args.length; index += 1) {
  if (args[index] === "--headed") { options.set("--headed", true); continue; }
  if (!["--playwright-module", "--browser-channel", "--evidence-dir"].includes(args[index]) || !args[index + 1] || args[index + 1].startsWith("--")) {
    console.error("Usage: node scripts/smoke_visual_companion.cjs [--playwright-module ABSOLUTE_PATH] [--browser-channel chrome] [--headed] [--evidence-dir DIRECTORY]");
    process.exit(2);
  }
  options.set(args[index], args[++index]);
}
let chromium;
try { ({ chromium } = require(options.get("--playwright-module") || "playwright")); }
catch { console.error("Playwright is unavailable. Supply --playwright-module with an existing installation; no dependencies were installed."); process.exit(2); }
const browserChannel = options.get("--browser-channel");
const evidence = options.has("--evidence-dir") ? path.resolve(options.get("--evidence-dir")) : null;
if (evidence) fs.mkdirSync(evidence, { recursive: true });
const root = fs.mkdtempSync(path.join(os.tmpdir(), "grillmester-visual-smoke-"));
const project = path.join(root, "project");
fs.mkdirSync(project);
const repo = path.resolve(__dirname, "..");
const cli = path.join(repo, "plugin/skills/design-prototype/scripts/comments.js");
const styles = `<style>
:root{--ax-bg-sunken:#eef0f3;--ax-bg-default:#fff;--ax-text-default:#252b35;--ax-text-subtle:#555d69;--ax-border-subtle:#ccd2db;--ax-border-accent:#2467ac;--ax-bg-accent-soft:#eaf3ff;--ax-bg-accent-strong:#2467ac;--ax-text-accent:#1b5186;--ax-text-contrast:#fff;--ax-space-8:8px;--ax-space-12:12px;--ax-space-16:16px;--ax-space-24:24px;--ax-space-32:32px;--ax-space-40:40px}
.fixture{display:grid;gap:18px}.fixture h1{font-size:30px;line-height:1.2}.fixture label{display:grid;gap:7px;font-weight:600}.fixture input,.fixture textarea{width:100%;font:inherit;padding:12px;border:1px solid #788393;border-radius:7px}.fixture button{font:inherit;padding:12px 18px;background:#2467ac;color:white;border:0;border-radius:7px;justify-self:start}.fixture .option{padding:20px}.fixture td,.fixture th{text-align:left;padding:12px;border-bottom:1px solid #ccd2db}.workspace{display:grid;grid-template-columns:150px 1fr;gap:24px}@media(max-width:600px){.workspace{grid-template-columns:1fr}.vc-content{margin:20px auto;padding:20px}.fixture h1{font-size:26px}}
</style>`;
const concepts = {
 alternatives: styles + `<div class="fixture"><h1>Hvordan vil du se oppgavene dine?</h1><p>Tre retninger for samme arbeidsdag.</p><div class="options"><section class="option"><h3>En prioritert liste</h3><p>Neste oppgave øverst, med frist og årsak.</p></section><section class="option"><h3>Et oversiktsbrett</h3><p>Fordel oppgaver mellom nye, pågående og ferdige.</p></section></div></div>`,
 form: styles + `<div class="fixture"><h1>Avtal en veiledning</h1><p>Bruk bare oppdiktede opplysninger.</p><label>Hva vil du snakke om?<input id="private-field-id" name="private-field-name"></label><label>Hva passer best for deg?<textarea></textarea></label><button>Fortsett</button></div>`,
 workspace: styles + `<div class="fixture"><h1>Arbeidsoversikt</h1><p>Hva trenger du for å prioritere en oppgave?</p><div class="workspace"><nav><p>Mine oppgaver</p><p>Teamets oppgaver</p></nav><table><thead><tr><th>Oppgave</th><th>Frist</th></tr></thead><tbody><tr><td>Avklare møte</td><td>Om 1 dag</td></tr><tr><td>Gjennomgå utkast</td><td>Om 2 dager</td></tr></tbody></table></div><button>Åpne neste oppgave</button></div>`
};
async function screenshot(page, name) {
  if (!evidence) return;
  await page.locator("#vc-status").filter({ hasText: /^Tilkoblet$/ }).waitFor();
  await Promise.all(page.frames().map(frame => frame.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))));
  await page.screenshot({ animations: "disabled", path: path.join(evidence, path.basename(name)) });
}
function run(args) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [cli, ...args]);
    let stdout = "", stderr = "";
    child.stdout.on("data", value => { stdout += value; });
    child.stderr.on("data", value => { stderr += value; });
    child.on("error", reject);
    child.on("close", code => code ? reject(new Error(stderr)) : resolve(JSON.parse(stdout)));
  });
}
(async()=>{
 const child=spawn(process.execPath,[repo+'/plugin/skills/design-prototype/scripts/server.js','--project-dir',project],{stdio:['ignore','pipe','pipe']});
 let browser,page;
 try {
  const info=await new Promise((resolve,reject)=>{
    let buffer="", settled=false;
    const timer=setTimeout(()=>finish(new Error("Preview server startup timed out.")),5000);
    function finish(error,value){if(settled)return;settled=true;clearTimeout(timer);error?reject(error):resolve(value);}
    child.stdout.on("data",value=>{
      buffer+=value;
      if(!buffer.includes("\n")||settled)return;
      try{const info=JSON.parse(buffer.split("\n")[0]);if(info.type!=="server-started")throw new Error("Preview server did not start.");finish(null,info);}
      catch(error){finish(error);}
    });
    child.once("error",error=>finish(error));
    child.once("close",code=>finish(new Error("Preview server exited before startup: "+code)));
    child.stderr.on("data",value=>process.stderr.write(value));
  });
  let version=0;
  const write=(name,html)=>fs.writeFileSync(info.screen_dir+'/'+String(++version).padStart(2,'0')+'-'+name+'.html',html);
  const list=()=>run(['list','--state-dir',info.state_dir]);
  write('alternatives',concepts.alternatives);
  browser=await chromium.launch({headless:!options.has("--headed"),...(browserChannel ? {channel:browserChannel} : {})});
  const failures=[],completedRequests=[];
  let frame,ui;
  // Headless Chrome stops routing pointer input to the lower part of the sandboxed
  // preview after a live viewport change, even after a reload. Each viewport
  // therefore gets a fresh page.
  const openPage=async viewport=>{
    await page?.close();
    page=await browser.newPage({viewport});
    page.on('pageerror',error=>failures.push(error.message));
    page.on('requestfinished',r=>completedRequests.push(r.url()));
    await page.goto(info.url);
    frame=page.frameLocator('iframe');
    ui=frame.locator('[data-visual-feedback]');
    await ui.getByRole('button',{name:'Endre',exact:true}).waitFor();
  };
  await openPage({width:1440,height:1000});
  await frame.getByText('En prioritert liste',{exact:true}).click();
  assert.match(await frame.locator('#indicator-text').innerText(),/Valgt/);
  await ui.getByRole('button',{name:'Endre',exact:true}).click();
  await frame.getByText('En prioritert liste',{exact:true}).click();
  await ui.getByRole('button',{name:'Lagre innspill',exact:true}).click();
  await ui.getByText('Skriv et innspill før du lagrer.',{exact:true}).waitFor();
  assert(await ui.getByLabel('Hva vil du endre?').evaluate(node=>node.getRootNode().activeElement===node));
  await ui.getByLabel('Hva vil du endre?').fill('Vis hvorfor denne oppgaven er prioritert. Behold fristen synlig.');
  await page.route('**/comments?*',async route=>route.request().method()==='POST'?route.fulfill({status:503,contentType:'application/json',body:'{"error":"Unavailable"}'}):route.continue());
  await ui.getByRole('button',{name:'Lagre innspill',exact:true}).click();
  await ui.getByText('Lagringen ble ikke bekreftet. Behold utkastet og prøv samme innspill igjen.',{exact:true}).waitFor();
  assert.equal(await ui.getByLabel('Hva vil du endre?').inputValue(),'Vis hvorfor denne oppgaven er prioritert. Behold fristen synlig.');
  assert(await ui.getByLabel('Hva vil du endre?').isEnabled());
  await page.unroute('**/comments?*');
  let releaseCreate,started;
  const gate=new Promise(resolve=>{releaseCreate=resolve;});
  const creating=new Promise(resolve=>{started=resolve;});
  await page.route('**/comments?*',async route=>{if(route.request().method()==='POST'){started();await gate;}await route.continue();});
  await ui.getByRole('button',{name:'Lagre innspill',exact:true}).click();
  await creating;
  assert(await ui.getByLabel('Hva vil du endre?').isDisabled());
  assert(await ui.getByRole('button',{name:'Forkast',exact:true}).isDisabled());
  assert(await ui.getByRole('button',{name:'Legg utkast til side',exact:true}).isDisabled());
  await page.keyboard.press('Escape');
  assert(await ui.getByRole('dialog').isVisible());
  releaseCreate();

  await ui.getByRole('button',{name:'Send 1 innspill',exact:true}).waitFor();
  await page.unroute('**/comments?*');
  assert.equal((await list()).comments.length,1);
  await screenshot(page,'/visual-companion-comments.png');
  const waiting=run(['wait','--state-dir',info.state_dir,'--after','0','--timeout','10']);
  await ui.getByText('Følger med',{exact:true}).waitFor();
  await ui.getByRole('button',{name:'Send 1 innspill',exact:true}).click();
  const batch=await waiting;
  assert.equal(batch.type,'feedback-submission');assert.equal(batch.comments.length,1);
  write('alternatives-updated',concepts.alternatives.replace('Neste oppgave øverst, med frist og årsak.','Neste oppgave øverst fordi fristen er nær.'));
  await frame.getByText('Neste oppgave øverst fordi fristen er nær.',{exact:true}).waitFor();
  await run(['resolve','--state-dir',info.state_dir,'--id',batch.comments[0].id,'--reply','Prioriteringen har nå en forklaring.']);
  await ui.getByRole('button',{name:'Innspill',exact:false}).first().click();
  await ui.getByText('Prioriteringen har nå en forklaring.',{exact:false}).waitFor();
  await screenshot(page,'/visual-companion-reply.png');
  console.log('PASS: alternative selection, point comment, batch wait, full text, reply.');

  write('form',concepts.form);
  await frame.getByRole('heading',{name:'Avtal en veiledning'}).waitFor();
  await ui.getByRole('button',{name:'Innspill',exact:false}).first().click();
  await ui.getByText('Tidligere versjon',{exact:true}).waitFor();
  await ui.getByRole('button',{name:'Lukk innspill'}).click();
  await frame.getByLabel('Hva vil du snakke om?',{exact:true}).fill('SKJEMA_VERDI_SKAL_IKKE_LAGRES');
  await ui.getByRole('button',{name:'Endre',exact:true}).click();
  await frame.getByRole('heading',{name:'Avtal en veiledning'}).click();
  await ui.getByLabel('Hva vil du endre?').fill('Bruk en tydeligere overskrift.');
  await ui.getByRole('button',{name:'Foreslå ny tekst'}).click();
  await ui.getByLabel('Ny tekst',{exact:true}).fill('Velg tidspunkt for en samtale');
  await ui.getByRole('button',{name:'Forhåndsvis teksten'}).click();
  await frame.getByRole('heading',{name:'Velg tidspunkt for en samtale'}).waitFor();
  await screenshot(page,'/visual-companion-text-preview.png');
  await ui.getByRole('button',{name:'Tilbakestill',exact:true}).click();
  await frame.getByRole('heading',{name:'Avtal en veiledning'}).waitFor();
  await ui.getByRole('button',{name:'Lagre innspill'}).click();
  await ui.getByRole('button',{name:'Send 1 innspill'}).waitFor();
  await ui.getByRole('button',{name:'Lukk innspill'}).click();
  await ui.getByRole('button',{name:'Område',exact:true}).click();
  const field=await frame.getByLabel('Hva vil du snakke om?',{exact:true}).boundingBox();
  await page.mouse.move(field.x+5,field.y+5);await page.mouse.down();await page.mouse.move(field.x+300,field.y+110,{steps:8});await page.mouse.up();
  await ui.getByLabel('Hva vil du endre?').fill('Samle disse feltene og forklar hva som er valgfritt.');
  await ui.getByRole('button',{name:'Lagre innspill'}).click();
  await ui.getByRole('button',{name:'Send 2 innspill'}).waitFor();
  await screenshot(page,'/visual-companion-form.png');
  const saved=await list();assert.equal(saved.comments.filter(c=>c.kind==='area').length,1);assert.equal(saved.comments.filter(c=>c.kind==='edit').length,1);
  assert(!fs.readFileSync(info.state_dir+'/comments.json','utf8').includes('SKJEMA_VERDI_SKAL_IKKE_LAGRES'));
  console.log('PASS: old-version history, text proposal preview/undo, area drag, field-value privacy.');

  await ui.getByRole('button',{name:'Lukk innspill'}).click();
  await ui.getByRole('button',{name:'Punkt',exact:true}).click();
  await frame.getByRole('heading',{name:'Avtal en veiledning'}).focus();await page.keyboard.press('Enter');
  await ui.getByLabel('Hva vil du endre?').fill('Et tastaturinnspill som skal bevares mens neste versjon kommer.');
  write('workspace',concepts.workspace);
  await ui.getByRole('button',{name:'Vis ny versjon'}).waitFor();
  assert(await ui.getByRole('button',{name:'Vis ny versjon'}).isDisabled());
  assert.equal(await ui.getByLabel('Hva vil du endre?').inputValue(),'Et tastaturinnspill som skal bevares mens neste versjon kommer.');
  await page.keyboard.press('Escape');
  assert(await frame.getByRole('heading',{name:'Avtal en veiledning'}).evaluate(node=>document.activeElement===node));
  await ui.getByRole('button',{name:'Fortsett utkast'}).click();
  assert.equal(await ui.getByLabel('Hva vil du endre?').inputValue(),'Et tastaturinnspill som skal bevares mens neste versjon kommer.');
  await page.keyboard.press(process.platform==='darwin'?'Meta+Enter':'Control+Enter');
  await ui.getByRole('button',{name:'Send 3 innspill'}).click();
  await frame.getByRole('heading',{name:'Arbeidsoversikt'}).waitFor();
  console.log('PASS: keyboard comments, Escape draft recovery, refresh deferral until batch submit.');

  await openPage({width:390,height:844});
  await ui.getByRole('button',{name:'Endre',exact:true}).click();
  await ui.getByRole('button',{name:'Område',exact:true}).click();
  await frame.getByRole('heading',{name:'Arbeidsoversikt'}).focus();await page.keyboard.press('Enter');
  await ui.getByLabel('Hva vil du endre?').fill('På mobil bør oppgavene ligge i én kolonne.');
  const composer=await ui.getByRole('dialog').boundingBox();
  assert(composer.x>=0&&composer.y>=0&&composer.x+composer.width<=390&&composer.y+composer.height<=844);
  await screenshot(page,'/visual-companion-mobile.png');
  // The draft must survive a live resize. Keyboard activation still reaches the
  // resized preview, so it saves the draft; pointer input continues on a fresh page.
  await page.setViewportSize({width:320,height:800});
  await ui.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  assert.equal(await ui.getByLabel('Hva vil du endre?').inputValue(),'På mobil bør oppgavene ligge i én kolonne.');
  const resizedComposer=await ui.getByRole('dialog').boundingBox();
  assert(resizedComposer.x>=0&&resizedComposer.x+resizedComposer.width<=320);
  await ui.getByRole('button',{name:'Lagre innspill',exact:true}).focus();await page.keyboard.press('Enter');
  await ui.getByRole('button',{name:'Send 1 innspill'}).waitFor();
  const mobile=await list();assert.equal(mobile.comments.at(-1).kind,'area');
  await openPage({width:320,height:800});
  await ui.locator('[data-action="panel"]').click();
  await ui.getByRole('button',{name:'Slett',exact:true}).last().click();
  assert.equal((await list()).comments.length,4);
  assert(await ui.evaluate(host=>{const active=host.shadowRoot.activeElement;return Boolean(active?.closest('.comment')||active?.matches('[data-filter],[role="tab"]'));}),'Deleting a focused comment must preserve keyboard focus.');
  await screenshot(page,'/visual-companion-narrow.png');
  const panel=await ui.getByRole('region',{name:'Innspill til prototypen'}).boundingBox();
  assert(panel.x>=0&&panel.x+panel.width<=320);
  console.log('PASS: mobile/narrow layout, keyboard area anchor and deletion.');
  assert.equal(failures.length,0,failures.join('\n'));
  assert(completedRequests.every(url=>url.startsWith(new URL(info.url).origin)||/^(data|blob):/.test(url)),'Unexpected completed remote request');
  const result={scenarios:['alternatives','form','workspace'],browser:browserChannel||'chromium',viewports:['1440x1000','390x844','320x800'],checks:['selection','point','drag-area','keyboard-point','keyboard-area','text-preview','undo','batch-wait','reply','old-version','draft-retention','focus-restoration','validation','save-failure-retention','delayed-save-lock','draft-resize','refresh-deferral','delete','field-privacy','loopback-only'],errors:failures};
  if(evidence)fs.writeFileSync(path.join(evidence,'visual-companion-test-results.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result));
 } catch(error) {if(page)await screenshot(page,'/visual-companion-failure.png').catch(()=>{});throw error;}
 finally {
  try { await browser?.close(); }
  finally {
   if(child.exitCode===null&&child.signalCode===null){const stopped=new Promise(resolve=>child.once('close',resolve));child.kill('SIGTERM');const killTimer=setTimeout(()=>child.kill('SIGKILL'),5000);await stopped;clearTimeout(killTimer);}
   fs.rmSync(root,{recursive:true,force:true});
  }
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
