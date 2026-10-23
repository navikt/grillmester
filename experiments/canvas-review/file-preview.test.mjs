import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { closeSync, constants, existsSync, fstatSync, mkdirSync, mkdtempSync, openSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import http from 'node:http';
import https from 'node:https';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createFilePreview } from './file-preview.mjs';

const pause = ms => new Promise(resolvePause => setTimeout(resolvePause, ms));
function fixture(t, options = {}) {
  const directory = mkdtempSync(join(tmpdir(), 'file-preview-test-'));
  const sessionId = randomUUID();
  const preview = createFilePreview({ sessionId, directory, ...options });
  t.after(() => { preview.close(); rmSync(directory, { recursive: true, force: true }); });
  preview.attachSession({ sessionId, capabilities: { ui: {} } });
  const ctx = { sessionId, extensionId: 'file-preview-test', canvasId: preview.canvas.id, instanceId: randomUUID() };
  return { preview, ctx, directory };
}

test('file URLs reference only private generated HTML, including Unicode and spaces in the parent path', t => {
  const parent = mkdtempSync(join(tmpdir(), 'file-preview-path-'));
  const directory = join(parent, 'lokal prøve med mellomrom'); mkdirSync(directory);
  t.after(() => rmSync(parent, { recursive: true, force: true }));
  const f = fixture(t, { directory });
  t.mock.method(http, 'createServer', () => assert.fail('File previews must not create HTTP servers'));
  t.mock.method(https, 'createServer', () => assert.fail('File previews must not create HTTPS servers'));
  const opened = f.preview.canvas.open({ ...f.ctx, instanceId: '../../outside', input: { concept: 'priorities' } });
  const url = new URL(opened.url), path = fileURLToPath(url);
  assert.equal(url.protocol, 'file:');
  assert.equal(url.hostname, '');
  assert.equal(url.search, '');
  assert.equal(url.hash, '#concept=priorities');
  assert.equal(dirname(dirname(path)), directory);
  assert.equal(statSync(dirname(path)).mode & 0o777, 0o700);
  assert.equal(opened.title, 'Prioritering · lokal skisse');
  const fd = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  let html;
  try {
    const stat = fstatSync(fd);
    assert(stat.isFile());
    assert.equal(stat.mode & 0o777, 0o600);
    html = readFileSync(fd, 'utf8');
  } finally { closeSync(fd); }
  assert.match(html, /connect-src 'none'/);
  assert.match(html, /Bare et lokalt utkast/);
  assert.match(html, /id="booking"/); assert.match(html, /id="priorities"/);
  assert(!html.includes('{{NONCE}}'));
  assert.deepEqual(f.preview.canvas.actions, []);
  assert(!html.includes(f.ctx.sessionId));
});

test('session, provider, input and rendering denials fail before a file is published', t => {
  const f = fixture(t);
  for (const change of [
    { sessionId: randomUUID() }, { canvasId: 'different-canvas' },
    { input: { path: '/unrelated/file.html' } }, { input: { concept: ['booking'] } },
    { host: { capabilities: { canvases: false } } }, { host: { capabilities: { canvases: 'true' } } },
  ]) assert.throws(() => f.preview.canvas.open({ ...f.ctx, ...change }));
  const root = join(f.directory, readdirSync(f.directory)[0]);
  assert.deepEqual(readdirSync(root), []);
  const opened = f.preview.canvas.open(f.ctx);
  assert.throws(() => f.preview.canvas.open({ ...f.ctx, extensionId: 'other-provider' }), /owner changed/);
  assert.throws(() => f.preview.canvas.open({ ...f.ctx, input: { concept: 'priorities' } }), /another instance/);
  assert.throws(() => f.preview.canvas.onClose({ ...f.ctx, extensionId: 'other-provider' }), /owner changed/);
  assert(existsSync(fileURLToPath(opened.url)));
});

test('repeated open shares a file, panel close removes it, and final cleanup only removes its own directory', t => {
  const f = fixture(t);
  const sibling = join(f.directory, 'keep.txt'); writeFileSync(sibling, 'keep');
  const first = f.preview.canvas.open(f.ctx);
  assert.equal(f.preview.canvas.open(f.ctx).url, first.url);
  f.preview.canvas.onClose(f.ctx); f.preview.canvas.onClose(f.ctx);
  assert(!existsSync(fileURLToPath(first.url)));
  const reopened = f.preview.canvas.open(f.ctx);
  assert.notEqual(reopened.url, first.url);
  assert(existsSync(fileURLToPath(reopened.url)));
  f.preview.close(); f.preview.close(); f.preview.canvas.onClose(f.ctx);
  assert(!existsSync(dirname(fileURLToPath(reopened.url))));
  assert.equal(readFileSync(sibling, 'utf8'), 'keep');
  assert.throws(() => f.preview.canvas.open(f.ctx), /ended/);
  assert.throws(() => f.preview.canvas.onClose({ ...f.ctx, extensionId: 'other-provider' }), /owner changed/);
});

test('the file experiment bounds retained identities and expires without a panel callback', async t => {
  const f = fixture(t, { lifetimeMs: 50 });
  const first = f.preview.canvas.open(f.ctx);
  f.preview.canvas.onClose(f.ctx);
  for (let index = 0; index < 3; index++) f.preview.canvas.open({ ...f.ctx, instanceId: randomUUID() });
  assert.throws(() => f.preview.canvas.open({ ...f.ctx, instanceId: randomUUID() }), /four instances/);
  assert(existsSync(dirname(fileURLToPath(first.url))));
  await pause(80);
  assert(!existsSync(dirname(fileURLToPath(first.url))));
  assert.throws(() => f.preview.canvas.open(f.ctx), /ended/);
});

test('file HTML supports both concepts, keyboard, narrow viewports and local-only drafts in headless Chrome', { skip: !process.env.FILE_PREVIEW_PLAYWRIGHT_MODULE }, async t => {
  const require = createRequire(import.meta.url);
  const { chromium } = require(resolve(process.env.FILE_PREVIEW_PLAYWRIGHT_MODULE));
  const browser = await chromium.launch({ headless: true, channel: process.env.FILE_PREVIEW_BROWSER_CHANNEL || 'chrome' });
  t.after(() => browser.close());
  const f = fixture(t);
  const opened = f.preview.canvas.open(f.ctx);
  const context = await browser.newContext({ viewport: { width: 1000, height: 900 }, reducedMotion: 'no-preference' });
  t.after(() => context.close());
  const page = await context.newPage();
  const errors = [], requests = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => requests.push(request.url()));
  await page.goto(opened.url);
  await page.keyboard.press('Tab');
  assert.equal(await page.locator(':focus').textContent(), 'Hopp til konseptene');
  const luminance = color => {
    const channels = color.match(/[\d.]+/g).slice(0, 3).map(value => Number(value) / 255);
    const linear = channels.map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
    return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
  };
  const contrastSamples = [];
  for (const motion of ['no-preference', 'reduce']) {
    await page.emulateMedia({ reducedMotion: motion });
    for (const targetId of ['tab-priorities', 'tab-booking']) {
      await page.evaluate(id => {
        const read = () => [...document.querySelectorAll('[role=tab]')].map(tab => {
          const style = getComputedStyle(tab);
          return { id: tab.id, color: style.color, background: style.backgroundColor };
        });
        read(); // Flush the previous state before the actual pointer activation.
        window.tabContrastSample = new Promise(resolveSample => document.getElementById(id).addEventListener('click', () => {
          const immediate = read();
          requestAnimationFrame(() => resolveSample({ immediate, firstFrame: read() }));
        }, { once: true }));
      }, targetId);
      await page.locator(`#${targetId}`).click();
      const sample = { motion, targetId, ...(await page.evaluate(() => window.tabContrastSample)) };
      for (const phase of ['immediate', 'firstFrame']) for (const tab of sample[phase]) {
        const foreground = luminance(tab.color), background = luminance(tab.background);
        tab.contrast = (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05);
        assert(tab.contrast >= 4.5, `${motion} ${phase} ${tab.id} must remain readable immediately after switching`);
      }
      contrastSamples.push(sample);
    }
  }
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  if (process.env.FILE_PREVIEW_EVIDENCE_DIR) {
    mkdirSync(process.env.FILE_PREVIEW_EVIDENCE_DIR, { recursive: true });
    writeFileSync(join(process.env.FILE_PREVIEW_EVIDENCE_DIR, 'tab-contrast.json'), JSON.stringify(contrastSamples, null, 2));
  }
  await page.getByRole('button', { name: 'Se lokal oppsummering', exact: true }).click();
  assert.equal(await page.locator(':focus').getAttribute('id'), 'slot-first');
  assert.equal(await page.locator('#time-error').isVisible(), true);
  await page.keyboard.press('Space');
  await page.keyboard.press('ArrowDown');
  assert.equal(await page.locator('[name="slot"]:checked').inputValue(), 'Mandag kl. 13.30');
  await page.getByLabel('Hva vil du forberede? (valgfritt)').fill('Avklar <b>neste steg</b>. Ærlig og kort.');
  await page.getByRole('button', { name: 'Se lokal oppsummering', exact: true }).click();
  assert.equal(await page.locator(':focus').getAttribute('id'), 'booking-summary');
  assert.match(await page.locator('#booking-choice').textContent(), /Mandag kl. 13.30/);
  assert.match(await page.locator('#booking-note').textContent(), /<b>neste steg<\/b>/);
  assert.equal(await page.locator('#booking-note b').count(), 0);
  await page.getByRole('tab', { name: '1. Finn en time', exact: true }).focus();
  await page.keyboard.press('ArrowRight');
  assert.equal(await page.locator(':focus').getAttribute('id'), 'tab-priorities');
  assert.equal(await page.locator('#priorities').isVisible(), true);
  await page.locator('#task-plan').focus();
  // Headless macOS does not expose the native select popup to key events.
  // Exercise its change handler and verify focus, without claiming that popup
  // keyboard behavior has been checked in the native app.
  await page.locator('#task-plan').selectOption('later');
  assert.equal(await page.locator('#later #task-plan').count(), 1);
  assert.equal(await page.locator(':focus').getAttribute('id'), 'task-plan');
  assert.equal(await page.locator('#later-count').textContent(), '(2)');
  await page.keyboard.press('Tab');
  assert.equal(await page.locator(':focus').getAttribute('id'), 'reset-board');
  await page.locator('#task-read').selectOption('parked');
  assert.equal(await page.locator('#today').locator('..').getByText('Ingen oppgaver her.', { exact: true }).isVisible(), true);
  await page.getByRole('button', { name: 'Nullstill prioriteringen', exact: true }).click();
  assert.equal(await page.locator('#today-count').textContent(), '(2)');
  for (const width of [1000, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    for (const tab of ['tab-booking', 'tab-priorities']) {
      await page.locator(`#${tab}`).click();
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `No horizontal overflow at ${width}px in ${tab}`);
      if (process.env.FILE_PREVIEW_EVIDENCE_DIR) {
        mkdirSync(process.env.FILE_PREVIEW_EVIDENCE_DIR, { recursive: true });
        await page.screenshot({ path: join(process.env.FILE_PREVIEW_EVIDENCE_DIR, `file-${tab}-${width}.png`), fullPage: true });
      }
    }
  }
  await page.getByRole('tab', { name: '1. Finn en time', exact: true }).click();
  assert.match(await page.locator('#preparation').inputValue(), /neste steg/);
  await page.reload();
  assert.equal(await page.locator('#preparation').inputValue(), '');
  assert.equal(await page.locator('[name="slot"]:checked').count(), 0);
  assert.deepEqual(errors, []);
  assert(requests.every(url => new URL(url).protocol === 'file:'), 'No network requests');
});

test('the actual installed SDK returns a local file and cleans it without HTTP or model requests', { skip: !process.env.FILE_PREVIEW_SDK_DIR }, async t => {
  const sdk = resolve(process.env.FILE_PREVIEW_SDK_DIR);
  const scratch = mkdtempSync(join(tmpdir(), 'file-preview-sdk-'));
  t.after(() => rmSync(scratch, { recursive: true, force: true }));
  const loader = join(scratch, 'loader.mjs'), register = join(scratch, 'register.mjs');
  writeFileSync(loader, "export async function resolve(specifier, context, next) { if (specifier === '@github/copilot-sdk/extension') return { url: process.env.FILE_PREVIEW_SDK_ENTRY_URL, shortCircuit: true }; return next(specifier, context); }");
  writeFileSync(register, "import { register } from 'node:module'; register(new URL('./loader.mjs', import.meta.url));");
  const protocolVersion = Number(/SDK_PROTOCOL_VERSION\s*=\s*(\d+)/.exec(readFileSync(join(sdk, 'sdkProtocolVersion.d.ts'), 'utf8'))?.[1]);
  assert(Number.isSafeInteger(protocolVersion));
  const sessionId = randomUUID(), methods = [], pending = new Map();
  let buffer = Buffer.alloc(0), sequence = 0, resume, failure, stderr = '';
  let resolveResume;
  const resumed = new Promise(resolvePromise => { resolveResume = resolvePromise; });
  const child = spawn(process.execPath, ['--import', register, fileURLToPath(new URL('./file-preview.mjs', import.meta.url))], {
    cwd: scratch, env: { PATH: dirname(process.execPath), TMPDIR: scratch, SESSION_ID: sessionId, COPILOT_HOME: join(scratch, 'isolated-home'), FILE_PREVIEW_SDK_ENTRY_URL: pathToFileURL(join(sdk, 'extension.js')).href }, stdio: ['pipe', 'pipe', 'pipe'],
  });
  let exited = false;
  const exit = new Promise(resolveExit => child.once('exit', code => { exited = true; resolveExit(code); }));
  t.after(async () => { if (!exited) child.kill('SIGTERM'); await Promise.race([exit, pause(1000)]); if (!exited) child.kill('SIGKILL'); await exit; });
  child.stderr.on('data', chunk => { stderr = (stderr + chunk).slice(-8000); });
  const write = message => { const body = Buffer.from(JSON.stringify({ jsonrpc: '2.0', ...message })); child.stdin.write(Buffer.concat([Buffer.from(`Content-Length: ${body.length}\r\n\r\n`), body])); };
  child.stdout.on('data', chunk => {
    try {
      buffer = Buffer.concat([buffer, chunk]);
      assert(buffer.length <= 1024 * 1024);
      while (true) {
        const boundary = buffer.indexOf('\r\n\r\n'); if (boundary < 0) break;
        const size = Number(/^Content-Length: (\d+)$/im.exec(buffer.subarray(0, boundary).toString())?.[1]);
        assert(Number.isInteger(size) && size > 0 && size <= 1024 * 1024);
        if (buffer.length < boundary + 4 + size) break;
        const message = JSON.parse(buffer.subarray(boundary + 4, boundary + 4 + size).toString()); buffer = buffer.subarray(boundary + 4 + size);
        if (!message.method) {
          const waiting = pending.get(message.id); assert(waiting); pending.delete(message.id); clearTimeout(waiting.timer);
          if (message.error) waiting.reject(new Error(message.error.message)); else waiting.resolve(message.result);
        } else if (message.id !== undefined) {
          methods.push(message.method);
          let result;
          if (['connect', 'ping'].includes(message.method)) result = { protocolVersion };
          else if (message.method === 'session.resume') { resume = message.params; result = { sessionId, workspacePath: scratch, capabilities: { ui: {} }, openCanvases: [] }; }
          else if (['session.log', 'session.eventLog.registerInterest'].includes(message.method)) result = {};
          else throw new Error(`Unexpected SDK call: ${message.method}`);
          write({ id: message.id, result });
          if (message.method === 'session.resume') resolveResume();
        }
      }
    } catch (error) { failure = error; }
  });
  const request = (method, params) => new Promise((resolveRequest, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`No SDK response to ${method}: ${stderr}`)); }, 5000);
    pending.set(id, { resolve: resolveRequest, reject, timer }); write({ id, method, params });
  });
  await Promise.race([resumed, pause(5000).then(() => { if (!resume) throw failure || new Error(`No SDK registration: ${stderr}`); })]);
  assert.equal(resume.sessionId, sessionId); assert.equal(resume.requestPermission, false);
  assert.equal(resume.canvases.length, 1); assert.equal(resume.canvases[0].id, 'design-file-preview');
  assert.deepEqual(resume.canvases[0].actions ?? [], []);
  const ctx = { sessionId, extensionId: 'project:file-preview', canvasId: 'design-file-preview', instanceId: randomUUID() };
  const opened = await request('canvas.open', { ...ctx, input: { concept: 'priorities' } });
  assert.equal(new URL(opened.url).protocol, 'file:');
  const path = fileURLToPath(opened.url); assert(existsSync(path));
  await assert.rejects(request('canvas.open', { ...ctx, sessionId: randomUUID() }));
  await request('canvas.close', ctx); assert(!existsSync(path));
  const reopened = await request('canvas.open', ctx); assert.notEqual(reopened.url, opened.url);
  child.kill('SIGTERM'); assert.equal(await exit, 0);
  assert(!existsSync(dirname(fileURLToPath(reopened.url))));
  assert(!methods.includes('session.send')); assert.equal(failure, undefined);
});
