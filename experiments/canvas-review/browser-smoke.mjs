import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { parseArgs } from 'node:util';
import { createReviewProbe } from './probe.mjs';

const { values } = parseArgs({ options: {
  'playwright-module': { type: 'string' },
  'evidence-dir': { type: 'string', default: '/tmp/canvas-review-browser' },
  'browser-channel': { type: 'string' },
  headed: { type: 'boolean', default: false },
  case: { type: 'string' },
} });
if (!values['playwright-module']) throw new Error('Supply an existing Playwright module using --playwright-module.');
const require = createRequire(import.meta.url);
const { chromium } = require(path.resolve(values['playwright-module']));
const evidence = path.resolve(values['evidence-dir']);
await mkdir(evidence, { recursive: true });
const browser = await chromium.launch({ headless: !values.headed, ...(values['browser-channel'] ? { channel: values['browser-channel'] } : {}) });
const results = [];
const cleanError = error => String(error?.stack || error).replace(/token=[^\s"'&)>]+/g, 'token=[redacted]');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(fn, message, timeout = 7000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) { if (await fn()) return; await delay(30); }
  throw new Error(message);
}
async function run(name, concept, exercise, options = {}) {
  if (values.case && values.case !== name) return;
  const sessionId = `test-${randomUUID()}`;
  const calls = [];
  const probe = createReviewProbe({ sessionId, sendTimeoutMs: options.sendTimeoutMs || 1500 });
  probe.attachSession({ sessionId, send: async input => { calls.push(structuredClone(input)); return options.send ? options.send(input) : `receipt-${calls.length}`; } });
  const ctx = { sessionId, canvasId: probe.canvas.id, instanceId: `instance-${randomUUID()}`, extensionId: 'review-test', host: { capabilities: { canvases: true } }, input: { concept } };
  const opening = await probe.canvas.open(ctx);
  const context = await browser.newContext({ viewport: options.viewport || { width: 1280, height: 900 }, reducedMotion: 'reduce' });
  const page = await context.newPage();
  const errors = [], external = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (new URL(request.url()).origin !== new URL(opening.url).origin) external.push(request.url()); });
  const action = (name, input = {}) => probe.canvas.actions.find(action => action.name === name).handler({ ...ctx, input });
  const state = () => action('read_state');
  const refresh = async () => {
    await Promise.all([page.waitForResponse(response => new URL(response.url()).pathname === '/api/state'), page.getByRole('button', { name: 'Oppdater status', exact: true }).click()]);
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await until(async () => (await page.locator('#connection').textContent()) === 'Tilkoblet', 'Connection did not refresh.');
  };
  try {
    await page.goto(opening.url);
    await page.waitForFunction(() => document.querySelector('#connection').textContent === 'Tilkoblet');
    await exercise({ page, calls, action, state, refresh });
    assert.deepEqual(errors, [], 'No browser exceptions');
    assert.deepEqual(external, [], 'No external resource requests');
    await page.screenshot({ path: path.join(evidence, `${name}.png`), fullPage: true });
    results.push({ name, status: 'passed', concept, host: 'simulated', viewport: page.viewportSize(), assertions: 'Native client and model behavior were not exercised.' });
    process.stdout.write(`PASS ${name}\n`);
  } catch (error) {
    await page.screenshot({ path: path.join(evidence, `${name}-failed.png`), fullPage: true }).catch(() => {});
    results.push({ name, status: 'failed', concept, host: 'simulated', error: cleanError(error) });
    process.stdout.write(`FAIL ${name}: ${cleanError(error).split('\n')[0]}\n`);
  } finally { await context.close(); await probe.close(); }
}

try {
  await run('content-keyboard-round', 'content', async ({ page, calls, action, state, refresh }) => {
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => document.activeElement?.value), 'clear');
    await page.keyboard.press('ArrowDown');
    assert.equal(await page.locator('.surface').getAttribute('data-choice'), 'compact');
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'note');
    const note = 'Behold datoen, men forklar hva jeg skal gjøre før møtet. Ærlig språk: <strong>ikke kode</strong>.';
    await page.keyboard.insertText(note);
    assert.equal(calls.length, 0, 'Local choices and typing must not send');
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'submit');
    await page.keyboard.press('Enter');
    await until(() => state().batches[0]?.delivery === 'queued', 'Explicit submission was not queued');
    assert.equal(calls.length, 1);
    assert.equal(calls[0].mode, 'enqueue');
    const batch = state().batches[0];
    assert.equal(batch.note, note);
    assert.equal(batch.choice, 'compact');
    assert.equal(batch.review, 'unread');
    await page.waitForFunction(() => document.querySelector('#batches').textContent.includes('Lagt i samtalens kø'));
    assert.equal(await page.locator('#batches strong').count(), 0, 'Literal submitted markup must remain text');
    action('review_batch', { batchId: batch.id, status: 'working', reply: 'Jeg vurderer neste steg i denne runden.' });
    await refresh();
    await page.waitForFunction(() => document.querySelector('#batches').textContent.includes('Under behandling'));
    action('apply_revision', { expectedRevision: state().revision, title: 'Forbered deg til møtet', description: 'Les gjennom avtalen. Ta med spørsmålene du ønsker å snakke om.' });
    action('review_batch', { batchId: batch.id, status: 'resolved', reply: 'Neste handling er presisert i skisseversjon 2.' });
    await refresh();
    await page.waitForFunction(() => document.querySelector('#batches').textContent.includes('Besvart'));
    assert.equal(await page.locator('#title').textContent(), 'Forbered deg til møtet');
    assert.equal(calls.length, 1, 'Review and revision actions must not enqueue more prompts');
    await page.locator('.batch p').filter({ hasText: note }).first().click({ clickCount: 3 });
    const selection = await page.evaluate(() => getSelection().toString());
    assert.ok(selection.includes('Behold datoen'), 'Submitted text can be selected for copying');
    await page.waitForResponse(response => new URL(response.url()).pathname === '/api/state');
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.equal(await page.evaluate(() => getSelection().toString()), selection, 'Unchanged polling preserves selected reply text');
  });

  await run('dashboard-draft-revision', 'dashboard', async ({ page, calls, action, state, refresh }) => {
    const before = await page.locator('#sample-title').textContent();
    await page.getByRole('radio', { name: /Kompakt oversikt/ }).check();
    const draft = 'Behold oppfølging først. Skill tydeligere mellom ventende og ferdige saker.';
    await page.locator('#note').fill(draft);
    action('apply_revision', { expectedRevision: state().revision, title: 'Prioriter oppfølgingen', description: 'Se forfalte oppgaver før ventende avklaringer.' });
    await refresh();
    assert.equal(await page.locator('#note').inputValue(), draft, 'Typing survives a new revision');
    assert.equal(await page.locator('#sample-title').textContent(), before, 'A new sketch must not replace the draft target silently');
    await page.screenshot({ path: path.join(evidence, 'dashboard-draft-preserved.png'), fullPage: true });
    assert.equal(calls.length, 0);
    await page.getByRole('button', { name: 'Send innspill', exact: true }).click();
    await until(() => state().batches.length === 1, 'Draft was not submitted');
    assert.equal(state().batches[0].screen, 1, 'The draft remains bound to the sketch it described');
    assert.equal(state().batches[0].document.title, before, 'The receiver can read the actual older sketch context');
    assert.equal(state().batches[0].note, draft);
    assert.equal(calls.length, 1);
  });

  await run('booking-narrow-view', 'booking', async ({ page, calls, state }) => {
    assert.match(await page.locator('#title').textContent(), /tidspunkt/);
    await page.getByRole('radio', { name: /Ett steg om gangen/ }).check();
    await page.locator('#note').fill('Vis hjelp når ingen tidspunkt passer, og behold bekreftelsen før innsending.');
    assert.equal(calls.length, 0);
    await page.getByRole('button', { name: 'Send innspill', exact: true }).click();
    await until(() => state().batches[0]?.delivery === 'queued', 'Narrow-screen submission failed');
    assert.equal(state().batches[0].choice, 'guided');
    assert.equal(calls.length, 1);
    await page.waitForFunction(() => document.querySelector('#batches').textContent.includes('Lagt i samtalens kø'));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'No horizontal page overflow at 390px');
    await page.screenshot({ path: path.join(evidence, 'booking-390.png'), fullPage: true });
    await page.locator('#note').fill('Et nytt lokalt utkast mens første runde venter.');
    await page.setViewportSize({ width: 720, height: 456 });
    assert.equal(await page.locator('#note').inputValue(), 'Et nytt lokalt utkast mens første runde venter.');
    await page.locator('#submit').scrollIntoViewIfNeeded();
    assert.equal(await page.locator('#submit').isVisible(), true);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'No horizontal page overflow at reduced viewport');
    assert.equal(calls.length, 1, 'Resizing must not submit');
  }, { viewport: { width: 390, height: 844 } });

  await run('lost-http-receipt', 'content', async ({ page, calls, state }) => {
    let release, intercepted;
    const interception = new Promise(resolve => { intercepted = resolve; });
    const pause = new Promise(resolve => { release = resolve; });
    let first = true;
    await page.route('**/api/submit?*', async route => {
      if (!first) return route.continue();
      first = false;
      await route.fetch();
      intercepted();
      await pause;
      await route.abort('failed');
    });
    const oldNote = 'Første innspill skal bare sendes én gang.';
    const newNote = 'Nytt utkast skrevet mens kvitteringen var på vei.';
    await page.locator('#note').fill(oldNote);
    await page.getByRole('button', { name: 'Send innspill', exact: true }).click();
    await interception;
    await page.locator('#note').fill(newNote);
    release();
    await until(() => state().batches[0]?.delivery === 'queued', 'Server did not accept the first batch');
    await page.waitForFunction(() => document.querySelector('#batches').textContent.includes('Første innspill'));
    await page.waitForFunction(() => !document.querySelector('#submit').disabled);
    assert.equal(await page.locator('#note').inputValue(), newNote, 'Recovery preserves text typed after dispatch');
    assert.equal(calls.length, 1, 'A lost HTTP receipt does not automatically resend');
    assert.equal(await page.locator('#error').isVisible(), false, 'Reconciled delivery must clear the obsolete lost-receipt error');
    await page.getByRole('button', { name: 'Send innspill', exact: true }).click();
    await until(() => state().batches.length === 2, 'Newly typed draft did not become a distinct round');
    assert.equal(state().batches[0].note, oldNote);
    assert.equal(state().batches[1].note, newNote);
    assert.equal(calls.length, 2);
  });

  await run('unknown-delivery', 'dashboard', async ({ page, calls, action, state, refresh }) => {
    await page.locator('#note').fill('Denne runden har en uavklart leveringskvittering.');
    await page.getByRole('button', { name: 'Send innspill', exact: true }).click();
    await until(() => state().batches[0]?.delivery === 'unknown', 'Ambiguous delivery did not time out');
    await refresh();
    await page.waitForFunction(() => document.querySelector('#batches').textContent.includes('Levering uavklart'));
    await page.locator('#note').fill('Et senere utkast skal fortsatt finnes.');
    assert.equal(await page.locator('#submit').isDisabled(), true, 'Unknown delivery blocks additional submission');
    await delay(1700);
    assert.equal(calls.length, 1, 'Polling must not retry an unknown delivery');
    assert.equal(await page.locator('#note').inputValue(), 'Et senere utkast skal fortsatt finnes.');
    const batch = state().batches[0];
    action('review_batch', { batchId: batch.id, status: 'working', reply: 'Denne eksakte runden er mottatt og vurderes.' });
    await refresh();
    await page.waitForFunction(() => document.querySelector('#batches').textContent.includes('Under behandling'));
    assert.equal(calls.length, 1, 'Explicit processing action does not create an automatic prompt loop');
    action('review_batch', { batchId: batch.id, status: 'resolved', reply: 'Runden er vurdert, med det åpne spørsmålet beholdt.' });
    await refresh();
    await page.waitForFunction(() => document.querySelector('#batches').textContent.includes('Besvart'));
    assert.equal(await page.locator('#note').inputValue(), 'Et senere utkast skal fortsatt finnes.');
    assert.equal(calls.length, 1);
  }, { sendTimeoutMs: 120, send: () => new Promise(() => {}) });
} finally { await browser.close(); }

const report = {
  method: 'Real browser against the actual local probe with a simulated session.send host. No Copilot client or model was started.',
  limitations: ['Three concept labels use the same small protocol-probe surface; these are not full design-product prototypes.', '720x456 is a reduced viewport, not actual browser zoom.', 'Keyboard checks cover this page, not app focus traversal or a screen reader.', 'Native canvas registration, app lifecycle and real turn execution are outside this test.'],
  results,
};
await writeFile(path.join(evidence, 'browser-results.json'), `${JSON.stringify(report, null, 2)}\n`);
if (!results.length) throw new Error('No matching case.');
if (results.some(result => result.status !== 'passed')) process.exitCode = 1;
