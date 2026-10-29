#!/usr/bin/env node
// Test the installed SDK and full preview child against a deterministic host.
// An optional packaged executable runs only its extension bootstrap. No client
// session, account credentials, model call or dependency installation is used.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { constants } from 'node:fs';
import { mkdtemp, mkdir, open, readFile, realpath, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const options = {};
const usage = 'Use --sdk-dir PATH [--evidence-dir PATH] [--runtime-binary PATH --runtime-bootstrap PATH --runtime-dist-dir PATH].';
for (let index = 2; index < process.argv.length; index += 2) {
  const key = process.argv[index];
  assert(['--sdk-dir', '--evidence-dir', '--runtime-binary', '--runtime-bootstrap', '--runtime-dist-dir'].includes(key)
    && process.argv[index + 1] && !process.argv[index + 1].startsWith('--') && !Object.hasOwn(options, key.slice(2)), usage);
  options[key.slice(2)] = resolve(process.argv[index + 1]);
}
assert(options['sdk-dir'], 'An existing host SDK path is required.');
const runtimeOptions = ['runtime-binary', 'runtime-bootstrap', 'runtime-dist-dir'];
assert(runtimeOptions.every(key => options[key]) || runtimeOptions.every(key => !options[key]),
  'Packaged mode requires --runtime-binary, --runtime-bootstrap and --runtime-dist-dir together.');
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
async function binaryDigest(filename) {
  const handle = await open(filename, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const before = await handle.stat({ bigint: true });
    assert(before.isFile(), 'Supply an existing packaged executable.');
    const bytes = await handle.readFile();
    const after = await handle.stat({ bigint: true });
    assert(before.size === BigInt(bytes.length) && after.size === before.size
      && after.mtimeNs === before.mtimeNs && after.ctimeNs === before.ctimeNs,
    'Packaged executable changed while its evidence hash was being read.');
    return sha256(bytes);
  } finally { await handle.close(); }
}
const pause = milliseconds => new Promise(resolvePause => setTimeout(resolvePause, milliseconds));
async function until(read, accept, message, timeout = 8000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { const value = await read(); if (accept(value)) return value; await pause(25); }
  assert.fail(message);
}

class StdioHost {
  constructor(child, sessionId, workspacePath, protocolVersion) {
    this.child = child;
    this.sessionId = sessionId;
    this.workspacePath = workspacePath;
    this.protocolVersion = protocolVersion;
    this.buffer = Buffer.alloc(0);
    this.pending = new Map();
    this.requests = [];
    this.notifications = [];
    this.sends = [];
    this.sequence = 0;
    this.sendBehavior = 'accept';
    this.stderr = '';
    this.resume = undefined;
    this.failure = undefined;
    this.exit = new Promise(resolveExit => {
      const finish = (code, signal) => {
        if (this.exited) return;
        this.exited = true;
        for (const pending of this.pending.values()) {
          clearTimeout(pending.timer);
          pending.reject(new Error(`Extension exited: ${code ?? signal}`));
        }
        this.pending.clear();
        resolveExit({ code, signal });
      };
      child.once('exit', finish);
      child.once('close', finish); // A failed spawn closes without emitting exit.
    });
    child.on('error', error => { this.failure = error; });
    child.stdin.on('error', error => { if (!this.exited) this.failure = error; });
    child.stderr.on('data', chunk => { this.stderr = (this.stderr + chunk).slice(-16384); });
    child.stdout.on('data', chunk => {
      try { this.consume(chunk); } catch (error) { this.failure = error; }
    });
  }

  write(message) {
    const body = Buffer.from(JSON.stringify({ jsonrpc: '2.0', ...message }));
    this.child.stdin.write(Buffer.concat([Buffer.from(`Content-Length: ${body.length}\r\n\r\n`), body]));
  }

  consume(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    assert(this.buffer.length <= 8 * 1024 * 1024, 'Oversized SDK frame');
    while (true) {
      const boundary = this.buffer.indexOf('\r\n\r\n');
      if (boundary < 0) return;
      const match = /^Content-Length: (\d+)$/im.exec(this.buffer.subarray(0, boundary).toString('ascii'));
      assert(match, 'Extension stdout contains non-protocol output');
      const size = Number(match[1]);
      assert(size > 0 && size <= 8 * 1024 * 1024, 'Invalid SDK frame length');
      if (this.buffer.length < boundary + 4 + size) return;
      const message = JSON.parse(this.buffer.subarray(boundary + 4, boundary + 4 + size).toString('utf8'));
      this.buffer = this.buffer.subarray(boundary + 4 + size);
      this.handle(message);
    }
  }

  handle(message) {
    if (!message.method) {
      const pending = this.pending.get(message.id);
      assert(pending, `Unexpected response ID ${message.id}`);
      this.pending.delete(message.id);
      clearTimeout(pending.timer);
      if (message.error) pending.reject(Object.assign(new Error(message.error.message), { rpcError: message.error }));
      else pending.resolve(message.result);
      return;
    }
    if (message.id === undefined) {
      this.notifications.push(message);
      return;
    }
    this.requests.push(message);
    const reply = result => this.write({ id: message.id, result });
    switch (message.method) {
      case 'connect':
      case 'ping':
        reply({ protocolVersion: this.protocolVersion });
        break;
      case 'session.resume':
        assert.equal(message.params.sessionId, this.sessionId);
        this.resume = message.params;
        reply({ sessionId: this.sessionId, workspacePath: this.workspacePath, capabilities: { ui: {} }, openCanvases: [] });
        break;
      case 'session.send': {
        const record = { ...message.params, rpcId: message.id, messageId: `review-message-${this.sends.length + 1}` };
        this.sends.push(record);
        if (this.sendBehavior === 'accept') reply({ messageId: record.messageId });
        else if (this.sendBehavior === 'reject') this.write({ id: message.id, error: { code: -32000, message: 'Deterministic delivery failure' } });
        // A dropped response deliberately leaves admission unknown.
        break;
      }
      case 'session.log':
      case 'session.eventLog.registerInterest':
        reply({});
        break;
      default:
        this.failure = new Error(`Unexpected SDK request: ${message.method}`);
        this.write({ id: message.id, error: { code: -32601, message: 'Method not provided by this isolated test host' } });
    }
  }

  request(method, params, timeout = 5000) {
    const id = `test-${++this.sequence}`;
    return new Promise((resolveRequest, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`Timed out waiting for ${method}`));
      }, timeout);
      this.pending.set(id, { resolve: resolveRequest, reject, timer });
      this.write({ id, method, params });
    });
  }

  async stop() {
    if (this.exited) return this.exit;
    this.child.kill('SIGTERM');
    const exited = await Promise.race([this.exit.then(() => true), pause(2000).then(() => false)]);
    if (!exited) this.child.kill('SIGKILL');
    return this.exit;
  }
}


const sdkDir = await realpath(options['sdk-dir']);
const sdkEntry = await readFile(join(sdkDir, 'extension.js'));
const protocolDeclaration = await readFile(join(sdkDir, 'sdkProtocolVersion.d.ts'), 'utf8');
const protocolVersion = Number(/SDK_PROTOCOL_VERSION\s*=\s*(\d+)/.exec(protocolDeclaration)?.[1]);
assert(Number.isSafeInteger(protocolVersion));
let packagedRuntime;
if (options['runtime-binary']) {
  const binary = await realpath(options['runtime-binary']);
  const bootstrap = await realpath(options['runtime-bootstrap']);
  const distDir = await realpath(options['runtime-dist-dir']);
  const binarySha256 = await binaryDigest(binary);
  assert((await stat(distDir)).isDirectory(), 'Supply an existing extracted distribution.');
  // The reviewed SEA index dispatches by basename, then loads its own local
  // preload. Require that effective file rather than claiming an ignored path.
  assert.equal(basename(bootstrap), 'extension_bootstrap.mjs');
  assert.equal(bootstrap, await realpath(join(distDir, 'preloads', 'extension_bootstrap.mjs')),
    '--runtime-bootstrap must name the effective preload in --runtime-dist-dir.');
  const [bootstrapSource, resolverSource, indexSource, loaderSource] = await Promise.all([
    readFile(bootstrap, 'utf8'), readFile(join(dirname(bootstrap), 'extension_sdk_resolver.mjs'), 'utf8'),
    readFile(join(distDir, 'index.js'), 'utf8'), readFile(join(distDir, 'sea-loader.js'), 'utf8'),
  ]);
  for (const key of ['COPILOT_EXTENSION_PARENT_PID', 'EXTENSION_PATH', 'COPILOT_SDK_PATH'])
    assert(bootstrapSource.includes(`process.env.${key}`), `Packaged bootstrap does not expose the reviewed ${key} contract.`);
  assert(indexSource.includes('extension_bootstrap.mjs') && indexSource.includes('resolveBootstrapPath')
    && indexSource.includes('preloads'), 'Packaged index does not expose the reviewed bootstrap dispatch.');
  assert(loaderSource.includes('COPILOT_CLI_DIST_DIR') && loaderSource.includes('COPILOT_AUTO_UPDATE'),
    'Packaged loader does not expose explicit distribution and auto-update controls.');
  for (const filename of ['app.js', 'cli-main.js', `prebuilds/${process.platform}-${process.arch}/runtime.node`])
    assert((await stat(join(distDir, filename))).isFile(), `Packaged distribution is incomplete: ${filename}`);
  packagedRuntime = { binary, bootstrap, distDir, evidence: {
    mode: 'packaged', binarySha256, bootstrapSha256: sha256(bootstrapSource),
    resolverSha256: sha256(resolverSource), indexSha256: sha256(indexSource), loaderSha256: sha256(loaderSource),
  } };
}
const temporary = await mkdtemp(join(tmpdir(), 'visual-canvas-sdk-'));
const hosts = [], checks = [];
const check = async (name, run) => { await run(); checks.push(name); process.stdout.write(`ok ${checks.length} - ${name}\n`); };
const canvasId = 'design-workspace';
const methods = ['close_inspection', 'list_history', 'open_inspection', 'publish_proposal', 'publish_revision', 'read_preview', 'read_revision', 'read_state', 'read_submission', 'restore_revision', 'review_submission', 'save_proposal', 'update_comment'];
try {
  // Paths stay data; the loader source is constant, never interpolated JS.
  await writeFile(join(temporary, 'loader.mjs'), `export async function resolve(specifier, context, next) {
    if (specifier === '@github/copilot-sdk/extension') return {url: process.env.VISUAL_SDK_EXTENSION_URL, shortCircuit: true};
    if (specifier === '@github/copilot-sdk') return {url: process.env.VISUAL_SDK_INDEX_URL, shortCircuit: true};
    return next(specifier, context);
  }\n`);
  await writeFile(join(temporary, 'register.mjs'), "import {register} from 'node:module'; register(new URL('./loader.mjs', import.meta.url));\n");
  const workspace = join(temporary, 'workspace'); await mkdir(workspace);
  const styleProjectPath = 'apps/frontend';
  const stylePackage = join(workspace, styleProjectPath, 'node_modules/@navikt/ds-css');
  const selectedCss = '.navds-heading { --style-proof: selected-subproject; }\n';
  await mkdir(join(stylePackage, 'dist'), { recursive: true });
  await writeFile(join(stylePackage, 'dist/index.min.css'), selectedCss);
  await writeFile(join(stylePackage, 'package.json'), JSON.stringify({ name: '@navikt/ds-css', version: '8.9.0' }));
  async function launch() {
    const sessionId = `test-session-${randomUUID()}`;
    const home = join(temporary, `home-${hosts.length}`); await mkdir(home);
    const environment = { PATH: dirname(process.execPath), TMPDIR: temporary, SESSION_ID: sessionId,
      HOME: home, USERPROFILE: home, XDG_CONFIG_HOME: join(home, 'config'), XDG_CACHE_HOME: join(home, 'cache'),
      COPILOT_HOME: join(home, 'copilot'), NODE_DISABLE_COMPILE_CACHE: '1' };
    const executable = packagedRuntime?.binary ?? process.execPath;
    const args = packagedRuntime ? [packagedRuntime.bootstrap]
      : ['--import', join(temporary, 'register.mjs'), join(here, '../extension.mjs')];
    if (packagedRuntime) Object.assign(environment, {
      COPILOT_CLI_DIST_DIR: packagedRuntime.distDir, COPILOT_AUTO_UPDATE: 'false',
      COPILOT_PKG_CACHE_HOME: join(home, 'package-cache'), COPILOT_CACHE_HOME: join(home, 'cache'),
      COPILOT_EXTENSION_PARENT_PID: String(process.pid), EXTENSION_PATH: join(here, '../extension.mjs'), COPILOT_SDK_PATH: sdkDir,
    });
    else Object.assign(environment, {
      VISUAL_SDK_EXTENSION_URL: pathToFileURL(join(sdkDir, 'extension.js')).href,
      VISUAL_SDK_INDEX_URL: pathToFileURL(join(sdkDir, 'index.js')).href,
    });
    const child = spawn(executable, args, {
      cwd: workspace,
      env: environment,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const host = new StdioHost(child, sessionId, workspace, protocolVersion); hosts.push(host);
    await until(() => { if (host.failure) throw host.failure; if (host.exited) throw new Error('Extension exited during registration.'); return host.resume; }, Boolean, 'SDK did not register.');
    return host;
  }
  const one = await launch(), two = await launch();
  const context = host => ({ sessionId: host.sessionId, extensionId: 'project:visual-companion', canvasId, instanceId: 'same-logical-id', session: { workingDirectory: workspace } });
  const ctx = context(one), secondCtx = context(two), extraCtx = { ...ctx, instanceId: 'another-sketch' };
  const action = (host, target, actionName, input = {}) => host.request('canvas.action.invoke', { ...target, actionName, input });
  const open = (host, target) => host.request('canvas.open', target);
  const request = async (view, pathname, method = 'GET', body, mutationId) => {
    const url = new URL(view.url); url.pathname = pathname;
    const response = await fetch(url, { method, signal: AbortSignal.timeout(3000), headers: { Origin: url.origin, 'Content-Type': 'application/json', ...(mutationId ? { 'X-Feedback-Mutation': mutationId } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) });
    return { status: response.status, value: await response.json() };
  };
  const note = (screen, text) => ({ screen, kind: 'point', text, anchor: { path: 'h1:nth-of-type(1)', role: 'heading', rect: { x: 1, y: 1, width: 200, height: 30 }, viewport: { width: 1000, height: 800 } } });
  let view, extraView, otherView, styledView, bindingView, current, comment;
  await check('two real SDK joins register the bounded canvas open schema on their exact sessions', async () => {
    for (const host of hosts) {
      assert.equal(host.resume.sessionId, host.sessionId); assert.equal(host.resume.requestPermission, false);
      assert.equal(host.resume.gitHubToken, undefined); assert.equal(host.resume.requestedEnvironmentVariables, undefined);
      assert.equal(host.resume.canvases.length, 1); assert.equal(host.resume.canvases[0].id, canvasId);
      assert.deepEqual(host.resume.canvases[0].actions.map(item => item.name).sort(), methods);
      const inputSchema = host.resume.canvases[0].inputSchema;
      assert.equal(inputSchema.type, 'object'); assert.equal(inputSchema.additionalProperties, false);
      assert(Array.isArray(inputSchema.required)); assert(!inputSchema.required.includes('styleProjectPath'));
      const styleSelector = inputSchema.properties.styleProjectPath;
      assert.equal(styleSelector.type, 'string'); assert.equal(styleSelector.maxLength, 240);
      assert.equal(typeof styleSelector.description, 'string');
      assert(styleSelector.description.length > 0 && styleSelector.description.length <= 1000);
      assert.match(styleSelector.description, /project-relative subproject/);
      assert.match(styleSelector.description, /empty string for the session project root/);
      assert.match(styleSelector.description, /retain the selection on reopen/);
      assert.match(styleSelector.description, /Supply again in a new session/);
      assert.equal(host.sends.length, 0);
    }
  });
  await check('bound open accepts absent flags and rejects denial or foreign session', async () => {
    await assert.rejects(open(one, { ...ctx, host: { capabilities: { canvases: false } } }), /support/);
    await assert.rejects(open(one, { ...ctx, sessionId: two.sessionId }));
    view = await open(one, ctx); assert.equal(new URL(view.url).hostname, '127.0.0.1');
    assert(new URL(view.url).searchParams.get('token'));
  });
  await check('full HTML publication uses guarded revisions and the portable sandbox', async () => {
    current = await action(one, ctx, 'publish_revision', { expectedScreen: '', filename: 'meeting.html', html: '<main><h1>Forbered møtet</h1><p>Ta med to spørsmål.</p><input value="PRIVATE_FIELD_VALUE"></main>' });
    assert.match(current.screen, /^[a-f0-9]{32}$/);
    await assert.rejects(action(one, ctx, 'publish_revision', { expectedScreen: '', filename: 'wrong.html', html: '<h1>Stale</h1>' }));
    const shell = await fetch(view.url); assert.match(shell.headers.get('content-security-policy'), /frame-ancestors 'none'/);
    assert.match(await shell.text(), /sandbox="allow-scripts"/); assert.equal(one.sends.length, 0);
  });
  await check('an explicit style subproject crosses the SDK wire, renders exact CSS and remains bound on reopen', async () => {
    const styledCtx = { ...ctx, instanceId: 'styled-sketch' };
    styledView = await open(one, { ...styledCtx, input: { styleProjectPath } });
    const styled = await action(one, styledCtx, 'publish_revision', {
      expectedScreen: '', filename: 'styled.html', html: '<h1 class="navds-heading">Valgt stilgrunnlag</h1>',
    });
    assert.deepEqual(styled.styles, { styleProjectPath, status: 'loaded', version: '8.9.0',
      source: 'apps/frontend/node_modules/@navikt/ds-css/dist/index.min.css', sha256: sha256(selectedCss) });
    const previewUrl = new URL(styledView.url); previewUrl.pathname = '/preview';
    const html = await (await fetch(previewUrl, { signal: AbortSignal.timeout(3000) })).text();
    assert(html.includes(selectedCss)); assert.doesNotMatch(html, /Aksel CSS mangler/);
    assert.equal((await action(one, ctx, 'read_state')).styles.status, 'fallback');
    await one.request('canvas.close', styledCtx);
    await assert.rejects(fetch(styledView.url, { signal: AbortSignal.timeout(1000) }));
    styledView = await open(one, styledCtx);
    assert.deepEqual((await action(one, styledCtx, 'read_state')).styles, styled.styles);
    await assert.rejects(open(one, { ...styledCtx, input: { styleProjectPath: '' } }), /style project changed/);
    assert.equal(one.sends.length, 0);
  });
  await check('binding diagnostics cross the SDK safely and a corrected grouped description list creates only one revision', async () => {
    const bindingCtx = { ...ctx, instanceId: 'binding-recovery' };
    const bindingPath = 'designs/binding-recovery';
    bindingView = await open(one, { ...bindingCtx, input: { workspacePath: bindingPath, create: true, title: 'Oversikt' } });
    const descriptor = { version: 2, variants: [], targets: [], texts: [{ id: 'heading', label: 'Overskrift', value: 'Oversikt' }] };
    const html = '<dl><div><dt>Visning</dt><dd><span data-vc-text="heading">Oversikt</span></dd></div></dl>';
    const before = await action(one, bindingCtx, 'read_state');
    const workspaceFile = join(workspace, bindingPath, 'workspace.json');
    const beforeBytes = await readFile(workspaceFile);
    await assert.rejects(action(one, bindingCtx, 'publish_revision', {
      expectedScreen: '', filename: 'invalid-binding.html', design: descriptor,
      html: html.replace('Oversikt', '<b>PRIVATE_SOURCE_VALUE</b>'),
    }), error => {
      assert.match(error.message, /\[text-content\] texts\[0\],HTML offset \d+ \(zero-based UTF-16\)/);
      assert.doesNotMatch(JSON.stringify(error.rpcError), /PRIVATE_SOURCE_VALUE|heading|invalid-binding|designs\/binding-recovery/);
      assert(Buffer.byteLength(error.message) <= 512);
      return true;
    });
    assert.deepEqual(await action(one, bindingCtx, 'read_state'), before);
    assert.deepEqual(await readFile(workspaceFile), beforeBytes);
    await assert.rejects(readFile(join(workspace, bindingPath, 'revisions/invalid-binding.html')), { code: 'ENOENT' });
    const corrected = await action(one, bindingCtx, 'publish_revision', { expectedScreen: '', filename: 'grouped-list.html', html, design: descriptor });
    assert.equal(corrected.workspace.version, 1);
    assert.deepEqual((await action(one, bindingCtx, 'list_history')).items.map(item => item.revisionId), [1]);
    assert.equal((await action(one, bindingCtx, 'read_revision', { revisionId: 1, part: 'html' })).content, html);
    const editor = await request(bindingView, '/workspace/editor');
    assert.equal(editor.status, 200);
    assert.deepEqual(editor.value.fields.map(field => field.id), ['text:heading']);
    assert.equal(one.sends.length, 0);
  });
  await check('two instances and two sessions in one project have separate stores', async () => {
    extraView = await open(one, extraCtx); otherView = await open(two, secondCtx);
    assert.equal((await action(one, extraCtx, 'read_state')).screen, '');
    assert.equal((await action(two, secondCtx, 'read_state')).screen, '');
    assert.notEqual(extraView.url, view.url); assert.notEqual(otherView.url, view.url);
    await assert.rejects(action(one, { ...ctx, extensionId: 'other-provider' }, 'read_state'));
  });
  await check('only explicit committed Send enqueues one bounded reference through the exact SDK session', async () => {
    const created = await request(view, '/comments', 'POST', note(current.screen, 'VISUAL_REVIEW_TEXT')); assert.equal(created.status, 200);
    comment = created.value.comments[0]; assert.equal(one.sends.length, 0);
    const submitted = await request(view, '/comments/submit', 'POST', { revision: created.value.revision }, 'a'.repeat(32)); assert.equal(submitted.status, 200);
    await until(() => one.sends, value => value.length === 1, 'Explicit Send did not reach SDK.');
    const delivered = one.sends[0]; assert.equal(delivered.sessionId, one.sessionId); assert.equal(delivered.mode, 'enqueue'); assert.equal(delivered.source, 'user');
    assert(!delivered.prompt.includes('VISUAL_REVIEW_TEXT')); assert(!delivered.prompt.includes('PRIVATE_FIELD_VALUE')); assert(Buffer.byteLength(delivered.prompt) < 2000);
    assert.deepEqual(JSON.parse(delivered.prompt.split('\n').at(-1)), { extensionId: ctx.extensionId, canvasId, instanceId: ctx.instanceId, submission: 1 });
    await until(() => action(one, ctx, 'read_state'), state => state.canvas.rounds[0].delivery === 'queued', 'Queue acknowledgement did not reach UI state.');
    assert.equal(two.sends.length, 0);
    assert.equal((await request(view, '/comments/submit', 'POST', { revision: created.value.revision }, 'a'.repeat(32))).status, 200);
    await pause(80); assert.equal(one.sends.length, 1);
  });
  await check('immutable round survives live removal; trusted review and publication never send another prompt', async () => {
    assert.equal((await request(view, `/comments/${comment.id}`, 'DELETE', {})).status, 200);
    const page = await action(one, ctx, 'read_submission', { submission: 1, offset: 0 });
    const historical = page.items.find(item => item.type === 'comment');
    assert.equal(historical.value.text, 'VISUAL_REVIEW_TEXT'); assert.equal(historical.current.present, false);
    assert(Buffer.byteLength(JSON.stringify(page)) <= 65536);
    await action(one, ctx, 'review_submission', { submission: 1, status: 'working', reply: 'Jeg vurderer neste steg.' });
    const previous = current.screen;
    current = await action(one, ctx, 'publish_revision', { expectedScreen: previous, filename: 'meeting-revised.html', html: '<h1>Forbered to spørsmål</h1>' });
    assert.notEqual(current.screen, previous);
    await action(one, ctx, 'review_submission', { submission: 1, status: 'answered', reply: 'Neste steg er tydeliggjort.' });
    assert.equal(one.sends.length, 1);
    assert.equal((await action(one, ctx, 'read_submission', { submission: 1 })).items.find(item => item.type === 'comment').value.screen, previous);
  });
  await check('unknown delivery blocks another round and a late SDK acknowledgement reconciles without resend', async () => {
    one.sendBehavior = 'drop';
    const created = await request(view, '/comments', 'POST', note(current.screen, 'Usikker levering.'));
    assert.equal((await request(view, '/comments/submit', 'POST', { revision: created.value.revision })).status, 200);
    await until(() => action(one, ctx, 'read_state'), state => state.canvas.rounds.find(item => item.submission === 2)?.delivery === 'unknown', 'Send timeout did not become unknown.', 13000);
    assert.equal(one.sends.length, 2);
    const next = await request(view, '/comments', 'POST', note(current.screen, 'Et separat innspill.'));
    assert.equal((await request(view, '/comments/submit', 'POST', { revision: next.value.revision })).status, 409);
    const late = one.sends[1]; one.write({ id: late.rpcId, result: { messageId: late.messageId } });
    await until(() => action(one, ctx, 'read_state'), state => state.canvas.rounds.find(item => item.submission === 2).delivery === 'queued', 'Late acknowledgement was not reconciled.');
    assert.equal(one.sends.length, 2);
    one.sendBehavior = 'accept';
  });
  await check('explicit review, guarded live reply and later round stay separately identified', async () => {
    const page = await action(one, ctx, 'read_submission', { submission: 2 });
    const item = page.items.find(item => item.type === 'comment').value;
    await action(one, ctx, 'review_submission', { submission: 2, status: 'working', reply: 'Runden er mottatt.' });
    await action(one, ctx, 'update_comment', { id: item.id, submission: 2, status: 'fixed', reply: 'Vurdert.' });
    const live = await request(view, '/comments');
    assert.equal((await request(view, '/comments/submit', 'POST', { revision: live.value.revision })).status, 200);
    await until(() => one.sends.length, value => value === 3, 'Distinct third round was not delivered.');
    assert.equal(JSON.parse(one.sends[2].prompt.split('\n').at(-1)).submission, 3);
  });
  await check('close revokes a view; reopening preserves the same artifact without another send', async () => {
    await one.request('canvas.close', ctx); await assert.rejects(fetch(view.url, { signal: AbortSignal.timeout(1000) }));
    const reopened = await open(one, ctx); assert.notEqual(reopened.url, view.url); view = reopened;
    const retained = await action(one, ctx, 'read_state'); assert.equal(retained.screen, current.screen); assert.equal(retained.submission, 3); assert.equal(one.sends.length, 3);
    assert.equal((await action(two, secondCtx, 'read_state')).submission, 0);
  });
  await check('extension shutdown stops every owned backend transport', async () => {
    for (const host of hosts) { assert.equal(host.failure, undefined); const stopped = await host.stop(); assert.equal(stopped.code, 0); }
    for (const opened of [view, extraView, otherView, styledView, bindingView]) await assert.rejects(fetch(opened.url, { signal: AbortSignal.timeout(1000) }));
  });
  const owner = await launch(), successor = await launch();
  const ownerCtx = context(owner), successorCtx = context(successor);
  const workspacePath = 'designs/booking';
  let savedView, recoveredView, firstSaved, savedCurrent;
  await check('a durable workspace publishes revisions and one active owner excludes a second SDK session', async () => {
    savedView = await open(owner, { ...ownerCtx, input: { workspacePath, create: true, title: 'Timebestilling' } });
    firstSaved = await action(owner, ownerCtx, 'publish_revision', { expectedScreen: '', filename: 'booking-first.html', html: '<h1>Velg tidspunkt</h1>' });
    savedCurrent = await action(owner, ownerCtx, 'publish_revision', { expectedScreen: firstSaved.screen, filename: 'booking-second.html', html: '<h1>Bekreft tidspunktet</h1>' });
    assert.equal(savedCurrent.workspace.storage, 'project'); assert.equal(savedCurrent.workspace.version, 2);
    await assert.rejects(open(successor, { ...successorCtx, input: { workspacePath } }), /workspace|arbeidsrom/i);
    assert.equal(successor.sends.length, 0);
    owner.sendBehavior = 'drop';
    const created = await request(savedView, '/comments', 'POST', note(savedCurrent.screen, 'Bevar innspillet ved gjenåpning.'));
    assert.equal((await request(savedView, '/comments/submit', 'POST', { revision: created.value.revision })).status, 200);
    await until(() => owner.sends.length, value => value === 1, 'Durable explicit Send did not reach its SDK owner.');
    assert.equal((await action(owner, ownerCtx, 'read_state')).canvas.rounds[0].delivery, 'sending');
  });
  await check('a new session reopens after never-ready lock failure without replaying an interrupted delivery', async () => {
    assert.equal((await owner.stop()).code, 0);
    await assert.rejects(fetch(savedView.url, { signal: AbortSignal.timeout(1000) }));
    recoveredView = await open(successor, successorCtx);
    const recovered = await action(successor, successorCtx, 'read_state');
    assert.equal(recovered.workspace.id, firstSaved.workspace.id); assert.equal(recovered.workspace.recovered, true);
    assert.equal(recovered.screen, savedCurrent.screen); assert.equal(recovered.submission, 1);
    assert.equal(recovered.canvas.rounds[0].delivery, 'unknown'); assert.equal(recovered.canvas.rounds[0].previousSession, true);
    const read = await action(successor, successorCtx, 'read_submission', { submission: 1 });
    assert.equal(read.items.find(item => item.type === 'comment').value.text, 'Bevar innspillet ved gjenåpning.');
    assert.equal(successor.sends.length, 0);
    await assert.rejects(open(successor, { ...successorCtx, input: { workspacePath: 'designs/different' } }), /workspace changed/);
  });
  await check('history and guarded restore preserve submitted history and create no SDK prompt', async () => {
    const page = await action(successor, successorCtx, 'list_history', { limit: 1 });
    assert.deepEqual(page.items.map(item => item.revisionId), [2]); assert.equal(page.hasMore, true);
    const older = await action(successor, successorCtx, 'list_history', { after: page.nextAfter, limit: 1 });
    assert.deepEqual(older.items.map(item => item.revisionId), [1]);
    const content = await action(successor, successorCtx, 'read_revision', { revisionId: 1, part: 'html' });
    assert.equal(content.content, '<h1>Velg tidspunkt</h1>'); assert.equal(content.nextOffset, null);
    assert(Buffer.byteLength(JSON.stringify(content)) <= 65536);
    const before = await action(successor, successorCtx, 'read_state');
    await assert.rejects(action(successor, successorCtx, 'restore_revision', { revisionId: 1, expectedRevision: before.revision - 1 }), /changed/i);
    const restored = await action(successor, successorCtx, 'restore_revision', { revisionId: 1, expectedRevision: before.revision });
    assert.equal(restored.workspace.version, 3); assert.notEqual(restored.screen, firstSaved.screen);
    assert.equal(restored.submission, 1); assert.equal(restored.canvas.rounds[0].previousSession, true);
    assert.equal((await action(successor, successorCtx, 'read_submission', { submission: 1 })).items.find(item => item.type === 'comment').value.screen, savedCurrent.screen);
    assert.equal(successor.sends.length, 0); savedCurrent = restored;
  });
  await check('only a fresh explicit round reaches the new session, then shutdown preserves saved work and revokes its URL', async () => {
    const created = await request(recoveredView, '/comments', 'POST', note(savedCurrent.screen, 'Et nytt innspill i denne samtalen.'));
    assert.equal((await request(recoveredView, '/comments/submit', 'POST', { revision: created.value.revision })).status, 200);
    await until(() => successor.sends.length, value => value === 1, 'Fresh Send did not reach the new SDK session.');
    const delivered = successor.sends[0];
    assert.equal(delivered.sessionId, successor.sessionId);
    assert.equal(JSON.parse(delivered.prompt.split('\n').at(-1)).submission, 2);
    await until(() => action(successor, successorCtx, 'read_state'), state => state.canvas.rounds.find(round => round.submission === 2)?.delivery === 'queued', 'Fresh queue acknowledgement was not saved.');
    assert.equal((await action(successor, successorCtx, 'read_state')).canvas.rounds[0].previousSession, true);
    assert.equal(owner.sends.length, 1); assert.equal(owner.failure, undefined); assert.equal(successor.failure, undefined);
    assert.equal((await successor.stop()).code, 0);
    await assert.rejects(fetch(recoveredView.url, { signal: AbortSignal.timeout(1000) }));
    const reopened = await launch(), reopenedCtx = context(reopened);
    await open(reopened, { ...reopenedCtx, input: { workspacePath } });
    const saved = await action(reopened, reopenedCtx, 'read_state');
    assert.equal(saved.workspace.version, 3); assert.equal(saved.submission, 2); assert.equal(reopened.sends.length, 0);
    assert.equal((await reopened.stop()).code, 0);
  });
  const report = { passed: true, protocolVersion, sdkSha256: sha256(sdkEntry),
    runtime: packagedRuntime?.evidence ?? { mode: 'node', version: process.versions.node }, checks,
    limits: ['Installed SDK against a deterministic stdio host and actual local preview server.',
      packagedRuntime ? 'Packaged executable used only for its extension bootstrap; no native renderer, client session, model, account or credentials were used.'
        : 'No native renderer, client, model, account or credentials were used.',
      'Registered schemas are inspected; the test host does not perform native JSON Schema validation or cache refresh.',
      'Queue mode and session routing are wire assertions; actual idle/busy host behavior remains a native acceptance test.'] };
  if (options['evidence-dir']) { await mkdir(options['evidence-dir'], { recursive: true }); await writeFile(join(options['evidence-dir'], 'sdk-results.json'), JSON.stringify(report, null, 2) + '\n'); }
  process.stdout.write(JSON.stringify(report) + '\n');
} finally {
  for (const host of hosts) await host.stop();
  await rm(temporary, { recursive: true, force: true });
}
