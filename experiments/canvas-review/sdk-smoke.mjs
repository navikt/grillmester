#!/usr/bin/env node
// Exercise the real installed SDK against an isolated, deterministic stdio host.
// This does not start a client, use account credentials, or make model requests.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { mkdtemp, mkdir, readFile, realpath, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const options = { extension: join(here, 'extension.mjs') };
for (let index = 2; index < process.argv.length; index += 2) {
  const key = process.argv[index];
  assert(['--sdk-dir', '--extension', '--evidence-dir'].includes(key), `Unknown option: ${key}`);
  assert(process.argv[index + 1], `Missing value for ${key}`);
  options[key.slice(2)] = resolve(process.argv[index + 1]);
}
assert(options['sdk-dir'], 'Pass --sdk-dir pointing to an existing SDK directory. No SDK is installed automatically.');

const pause = milliseconds => new Promise(resolvePause => setTimeout(resolvePause, milliseconds));
async function until(read, accept, message, timeout = 8000) {
  const end = Date.now() + timeout;
  let last;
  while (Date.now() < end) {
    last = await read();
    if (accept(last)) return last;
    await pause(25);
  }
  assert.fail(`${message}; last value: ${JSON.stringify(last)}`);
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
    this.exit = new Promise(resolveExit => child.once('exit', (code, signal) => {
      this.exited = true;
      for (const pending of this.pending.values()) {
        clearTimeout(pending.timer);
        pending.reject(new Error(`Extension exited: ${code ?? signal}`));
      }
      this.pending.clear();
      resolveExit({ code, signal });
    }));
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
        reply({ sessionId: this.sessionId, workspacePath: this.workspacePath, capabilities: { ui: { canvases: true } }, openCanvases: [] });
        break;
      case 'session.send': {
        const record = { ...message.params, messageId: `review-message-${this.sends.length + 1}` };
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
assert(Number.isSafeInteger(protocolVersion), 'Could not identify the installed SDK protocol version');
const temporary = await mkdtemp(join(tmpdir(), 'canvas-sdk-smoke-'));
const checks = [];
let host;
const check = async (name, run) => { await run(); checks.push(name); process.stdout.write(`ok ${checks.length} - ${name}\n`); };
try {
  const loader = `export async function resolve(specifier, context, next) {
    if (specifier === '@github/copilot-sdk/extension') return { url: ${JSON.stringify(pathToFileURL(join(sdkDir, 'extension.js')).href)}, shortCircuit: true };
    if (specifier === '@github/copilot-sdk') return { url: ${JSON.stringify(pathToFileURL(join(sdkDir, 'index.js')).href)}, shortCircuit: true };
    return next(specifier, context);
  }\n`;
  await writeFile(join(temporary, 'loader.mjs'), loader);
  await writeFile(join(temporary, 'register.mjs'), `import { register } from 'node:module'; register(new URL('./loader.mjs', import.meta.url));\n`);
  const workspace = join(temporary, 'workspace');
  await mkdir(workspace);
  const sessionId = `review-session-${randomUUID()}`;
  const child = spawn(process.execPath, ['--import', join(temporary, 'register.mjs'), options.extension], {
    cwd: temporary,
    env: {
      PATH: dirname(process.execPath),
      TMPDIR: temporary,
      SESSION_ID: sessionId,
      COPILOT_HOME: join(temporary, 'isolated-home'),
    },
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  host = new StdioHost(child, sessionId, workspace, protocolVersion);
  await until(() => {
    if (host.failure) throw host.failure;
    if (host.exited) throw new Error(`Extension exited during startup: ${host.stderr}`);
    return host.resume;
  }, Boolean, 'SDK never registered the extension');

  await check('installed SDK declares the canvas on the exact existing session', async () => {
    assert.equal(host.resume.sessionId, sessionId);
    assert.equal(host.resume.requestPermission, false);
    assert.equal(host.resume.gitHubToken, undefined);
    assert.equal(host.resume.requestedEnvironmentVariables, undefined);
    assert.equal(host.resume.canvases.length, 1);
    assert.equal(host.resume.canvases[0].id, 'design-review-probe');
    assert.deepEqual(host.resume.canvases[0].actions.map(action => action.name).sort(), ['apply_revision', 'read_state', 'review_batch']);
  });

  const context = { sessionId, extensionId: 'project:design-review-probe', canvasId: 'design-review-probe', instanceId: randomUUID(), host: { capabilities: { canvases: true } }, session: { workingDirectory: workspace } };
  await pause(30);
  const opened = await host.request('canvas.open', { ...context, input: { concept: 'content' } });
  let canvasUrl = new URL(opened.url);
  assert.equal(canvasUrl.hostname, '127.0.0.1');
  assert(canvasUrl.searchParams.get('token'), 'Canvas URL lacks a capability token');
  const endpoint = path => {
    const url = new URL(path, canvasUrl);
    url.searchParams.set('token', canvasUrl.searchParams.get('token'));
    return url;
  };
  const state = async () => {
    const response = await fetch(endpoint('/api/state'), { signal: AbortSignal.timeout(3000) });
    assert.equal(response.status, 200);
    return response.json();
  };
  const post = async body => {
    const response = await fetch(endpoint('/api/submit'), {
      method: 'POST', headers: { 'Content-Type': 'application/json', Origin: canvasUrl.origin }, body: JSON.stringify(body),
      signal: AbortSignal.timeout(3000),
    });
    return { status: response.status, value: await response.json() };
  };
  const action = (actionName, input = {}, overrides = {}) => host.request('canvas.action.invoke', { ...context, ...overrides, actionName, input });
  await check('canvas open serves the local view and SDK action reads the shared state', async () => {
    const response = await fetch(canvasUrl, { signal: AbortSignal.timeout(3000) });
    assert.equal(response.status, 200);
    assert.match(response.headers.get('content-type'), /text\/html/);
    const read = await action('read_state');
    assert.deepEqual(read, await state());
  });

  let firstBody;
  let firstBatch;
  await check('explicit UI batch sends exactly once with user provenance and queued delivery', async () => {
    const before = await state();
    firstBody = { expectedRevision: before.revision, screen: before.screen, requestId: randomUUID(), choice: 'clear', note: 'Behold overskriften. Gjør forklaringen kortere.' };
    const response = await post(firstBody);
    assert.equal(response.status, 202);
    firstBatch = response.value.batch;
    assert(firstBatch.id);
    const after = await until(state, value => value.batches.some(batch => batch.id === firstBatch.id && batch.messageId), 'Message was not marked admitted');
    assert.equal(host.sends.length, 1);
    const sent = host.sends[0];
    assert.equal(sent.sessionId, sessionId);
    assert.equal(sent.source, 'user');
    assert.equal(sent.mode, 'enqueue');
    assert(sent.prompt.includes(firstBody.note));
    assert(sent.prompt.includes(firstBatch.id));
    const batch = after.batches.find(item => item.id === firstBatch.id);
    assert.equal(batch.screen, firstBody.screen);
    assert.equal(batch.delivery, 'queued');
    assert.equal(batch.messageId, sent.messageId);
  });

  await check('HTTP retry of an admitted batch does not duplicate the SDK message', async () => {
    const response = await post(firstBody);
    assert.equal(response.status, 202);
    assert.equal(response.value.batch.id, firstBatch.id);
    await pause(50);
    assert.equal(host.sends.length, 1);
  });

  await check('stale and caller-selected provenance are rejected before session.send', async () => {
    assert.equal((await post({ ...firstBody, requestId: randomUUID() })).status, 409);
    const current = await state();
    assert.equal((await post({ expectedRevision: current.revision, screen: current.screen, requestId: randomUUID(), choice: 'clear', note: 'test', source: 'system' })).status, 400);
    assert.equal(host.sends.length, 1);
  });

  await check('agent acknowledgement and revision update change shared state without another send', async () => {
    await action('review_batch', { batchId: firstBatch.id, status: 'working', reply: 'Vurderer innspillet.' });
    const current = await state();
    await action('apply_revision', { expectedRevision: current.revision, title: 'En tydeligere overskrift', description: 'Kort og konkret forklaring.' });
    await action('review_batch', { batchId: firstBatch.id, status: 'resolved', reply: 'Forklaringen er kortet ned.' });
    const after = await state();
    assert.equal(after.document.title, 'En tydeligere overskrift');
    assert.equal(after.batches.find(item => item.id === firstBatch.id).review, 'resolved');
    assert.equal(host.sends.length, 1);
  });

  await check('cross-session, wrong provider, wrong instance and undeclared actions fail closed', async () => {
    await assert.rejects(action('read_state', {}, { sessionId: randomUUID() }));
    await assert.rejects(action('read_state', {}, { extensionId: 'project:unrelated' }));
    await assert.rejects(action('read_state', {}, { instanceId: randomUUID() }));
    await assert.rejects(action('submit_batch', { note: 'An action must not impersonate a user click.' }));
    assert.equal(host.sends.length, 1);
  });

  await check('a preserved draft is bound to its viewed screen after a newer revision arrives', async () => {
    const current = await state();
    assert(current.screen > firstBody.screen);
    const body = { expectedRevision: current.revision, screen: firstBody.screen, requestId: randomUUID(), choice: 'clear', note: 'Dette gjelder fortsatt den opprinnelige skissen.' };
    const response = await post(body);
    assert.equal(response.status, 202);
    assert.equal(response.value.batch.screen, firstBody.screen);
    await until(state, value => value.batches.some(batch => batch.id === body.requestId && batch.delivery === 'queued'), 'Preserved draft was not admitted');
    assert.equal(host.sends.length, 2);
    const payload = JSON.parse(host.sends[1].prompt.slice(host.sends[1].prompt.indexOf('\n') + 1));
    assert.equal(payload.batch.screen, firstBody.screen);
    assert.equal(payload.batch.id, body.requestId);
    assert.equal((await post({ ...body, screen: current.screen })).status, 409);
    assert.equal(host.sends.length, 2);
  });

  let unknownBody;
  await check('delivery rejection remains unknown and retry does not emit another prompt', async () => {
    host.sendBehavior = 'reject';
    const current = await state();
    const body = { expectedRevision: current.revision, screen: current.screen, requestId: randomUUID(), choice: 'compact', note: 'En ny vurdering.' };
    unknownBody = body;
    const response = await post(body);
    assert.equal(response.status, 202);
    const batchId = response.value.batch.id;
    await until(state, value => value.batches.some(batch => batch.id === batchId && batch.delivery === 'unknown'), 'Rejected delivery did not retain an unknown state');
    assert.equal(host.sends.length, 3);
    assert.equal((await post(body)).value.batch.id, batchId);
    await pause(50);
    assert.equal(host.sends.length, 3);
  });

  await check('trusted review receipt permits a new batch without resending unknown delivery', async () => {
    const blocked = await state();
    assert.equal((await post({ expectedRevision: blocked.revision, screen: blocked.screen, requestId: randomUUID(), choice: 'guided', note: 'En separat oppfølging.' })).status, 409);
    assert.equal(host.sends.length, 3);
    await action('review_batch', { batchId: unknownBody.requestId, status: 'working', reply: 'Innspillet er mottatt og vurderes.' });
    const acknowledged = await state();
    const previous = acknowledged.batches.find(batch => batch.id === unknownBody.requestId);
    assert.equal(previous.delivery, 'unknown');
    assert.equal(previous.review, 'working');
    host.sendBehavior = 'accept';
    const body = { expectedRevision: acknowledged.revision, screen: acknowledged.screen, requestId: randomUUID(), choice: 'guided', note: 'En separat oppfølging etter mottaksbekreftelsen.' };
    assert.equal((await post(body)).status, 202);
    await until(state, value => value.batches.some(batch => batch.id === body.requestId && batch.delivery === 'queued'), 'New batch remained blocked after trusted receipt');
    assert.equal(host.sends.length, 4);
    assert.equal((await post(unknownBody)).value.batch.id, unknownBody.requestId);
    await pause(50);
    assert.equal(host.sends.length, 4);
  });

  const firstContext = { ...context };
  const firstUrl = new URL(canvasUrl);
  await check('a second canvas instance keeps its artifact and review batches isolated', async () => {
    context.instanceId = randomUUID();
    const second = await host.request('canvas.open', { ...context, input: { concept: 'booking' } });
    canvasUrl = new URL(second.url);
    assert.notEqual(canvasUrl.origin, firstUrl.origin);
    assert.notEqual(canvasUrl.searchParams.get('token'), firstUrl.searchParams.get('token'));
    const secondState = await state();
    assert.equal(secondState.concept, 'booking');
    assert.deepEqual(secondState.batches, []);
    const firstStateUrl = new URL('/api/state', firstUrl);
    firstStateUrl.search = firstUrl.search;
    const firstState = await (await fetch(firstStateUrl, { signal: AbortSignal.timeout(3000) })).json();
    assert.equal(firstState.batches.length, 4);
    assert.equal(firstState.document.title, 'En tydeligere overskrift');
  });

  await check('unacknowledged send times out honestly without an automatic retry', async () => {
    host.sendBehavior = 'drop';
    const current = await state();
    const body = { expectedRevision: current.revision, screen: current.screen, requestId: randomUUID(), choice: 'guided', note: 'Kontroller levering etter forbindelsesbrudd.' };
    const response = await post(body);
    assert.equal(response.status, 202);
    const batchId = response.value.batch.id;
    await until(state, value => value.batches.some(batch => batch.id === batchId && batch.delivery === 'unknown'), 'Unacknowledged delivery did not time out', 15000);
    assert.equal(host.sends.length, 5);
    assert.equal((await post(body)).value.batch.id, batchId);
    await pause(300);
    assert.equal(host.sends.length, 5);
  });

  await check('closing the canvas revokes its state and HTTP endpoint', async () => {
    await host.request('canvas.close', context);
    await assert.rejects(action('read_state'));
    await assert.rejects(fetch(canvasUrl, { signal: AbortSignal.timeout(2000) }));
    await host.request('canvas.close', firstContext);
    await assert.rejects(fetch(firstUrl, { signal: AbortSignal.timeout(2000) }));
  });
  assert.equal(host.failure, undefined, host.failure?.message);
  const report = {
    result: 'passed', checks,
    sdk: { protocolVersion, extensionSha256: createHash('sha256').update(sdkEntry).digest('hex') },
    host: 'deterministic stdio substitute',
    actualSdk: true, actualApp: false, actualRuntime: false, modelRequests: 0,
    outgoingMethods: [...new Set(host.requests.map(request => request.method))],
    sends: host.sends.map(({ sessionId: ignoredSession, ...send }) => send),
    limitations: ['Does not verify runtime scheduling, app rendering, plugin discovery, permissions, or restart persistence.'],
  };
  if (options['evidence-dir']) {
    await mkdir(options['evidence-dir'], { recursive: true });
    await writeFile(join(options['evidence-dir'], 'sdk-smoke.json'), `${JSON.stringify(report, null, 2)}\n`);
  }
  process.stdout.write(`${checks.length} SDK integration checks passed; no client or model was started.\n`);
} catch (error) {
  if (host?.stderr) process.stderr.write(`${host.stderr}\n`);
  throw error;
} finally {
  if (host) await host.stop();
  await rm(temporary, { recursive: true, force: true });
}
