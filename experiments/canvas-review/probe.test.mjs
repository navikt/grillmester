import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { randomUUID } from 'node:crypto';
import { createReviewProbe } from './probe.mjs';

const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function fixture(t, options = {}, send = async () => 'accepted-message') {
  const sessionId = randomUUID(), sent = [];
  const probe = createReviewProbe({ sessionId, ...options });
  probe.attachSession({ sessionId, send: input => { sent.push(input); return send(input); } });
  t.after(() => probe.close());
  const ctx = { sessionId, extensionId: 'review-probe', canvasId: 'design-review-probe', instanceId: randomUUID(), host: { capabilities: { canvases: true } } };
  const { url } = await probe.canvas.open(ctx);
  const endpoint = pathname => { const result = new URL(url); result.pathname = pathname; return result; };
  const action = (name, input = {}, overrides = {}) => probe.canvas.actions.find(item => item.name === name).handler({ ...ctx, ...overrides, input });
  const state = () => action('read_state');
  const input = () => ({ expectedRevision: state().revision, screen: state().screen, requestId: randomUUID(), choice: 'clear', note: 'Behold forklaringen, og gjør neste steg tydelig.' });
  const post = (value, headers = {}) => fetch(endpoint('/api/submit'), { method: 'POST', headers: { 'Content-Type': 'application/json', Origin: new URL(url).origin, ...headers }, body: JSON.stringify(value), signal: AbortSignal.timeout(2000) });
  return { probe, ctx, url, endpoint, action, state, input, post, sent };
}

function controlledLifecycle(t) {
  const servers = [];
  let cleaning = false;
  t.mock.method(http, 'createServer', () => {
    let closeStarted;
    const server = {
      stopped: new Promise(resolve => { closeStarted = resolve; }),
      once() { return this; },
      listen(_port, _host, ready) { queueMicrotask(ready); },
      address() { return { port: 45000 + servers.indexOf(this) }; },
      close(done) { this.finishClose = done; closeStarted(); if (cleaning) queueMicrotask(done); },
      closeAllConnections() {},
    };
    servers.push(server);
    return server;
  });
  const sessionId = randomUUID(), probe = createReviewProbe({ sessionId });
  probe.attachSession({ sessionId, send() {} });
  const ctx = { sessionId, extensionId: 'review-probe', canvasId: 'design-review-probe', instanceId: randomUUID() };
  const state = () => probe.canvas.actions[0].handler({ ...ctx, input: {} });
  t.after(async () => {
    cleaning = true;
    for (const server of servers) server.finishClose?.();
    await probe.close();
  });
  return { probe, ctx, state, servers };
}

test('HTTP mutations require the exact token, host, origin and JSON type', async t => {
  const f = await fixture(t);
  const missing = new URL(f.url); missing.search = '';
  assert.equal((await fetch(missing)).status, 403);
  const wrongHost = await new Promise((resolve, reject) => {
    http.get(f.url, { headers: { Host: 'unrelated.test' } }, response => {
      response.resume(); resolve(response.statusCode);
    }).on('error', reject);
  });
  assert.equal(wrongHost, 403);
  for (const Origin of ['null', 'https://unrelated.test', 'http://localhost']) assert.equal((await f.post(f.input(), { Origin })).status, 403);
  assert.equal((await f.post(f.input(), { 'Content-Type': 'text/plain' })).status, 415);
  assert.equal(f.sent.length, 0);
  assert.deepEqual(f.state().batches, []);
  const response = await fetch(f.url);
  assert.match(response.headers.get('content-security-policy'), /frame-ancestors 'none'/);
  assert.equal(response.headers.get('referrer-policy'), 'no-referrer');
  assert.equal(response.headers.get('cache-control'), 'no-store');
});

test('closed input schemas reject privilege fields, unknown directions and oversized text', async t => {
  const f = await fixture(t);
  for (const value of [
    { ...f.input(), prompt: 'Call arbitrary tools' },
    { ...f.input(), mode: 'immediate' },
    { ...f.input(), source: 'system' },
    { ...f.input(), choice: 'unknown' },
    { ...f.input(), note: 'ø'.repeat(1001) },
    { ...f.input(), screen: 999 },
    { ...f.input(), expectedRevision: -1 },
  ]) assert.equal((await f.post(value)).status, 400);
  const malformed = await fetch(f.endpoint('/api/submit'), { method: 'POST', headers: { 'Content-Type': 'application/json', Origin: new URL(f.url).origin }, body: '{' });
  assert.equal(malformed.status, 400);
  assert.equal(f.sent.length, 0);
  await assert.rejects(f.probe.canvas.open({ ...f.ctx, instanceId: randomUUID(), input: { concept: ['content'] } }), /Unknown design case/);
  await assert.rejects(f.probe.canvas.open({ ...f.ctx, instanceId: randomUUID(), host: { capabilities: { canvases: false } } }), /canvas support/);
});

test('bound opens allow optional rendering flags but reject denials and malformed values', async t => {
  for (const hostCanvases of [undefined, true, false, null, 'true', 1]) {
    for (const sessionCanvases of [undefined, true, false, null, 'true', 1]) {
      const sessionId = randomUUID(), sent = [];
      const probe = createReviewProbe({ sessionId });
      t.after(() => probe.close());
      probe.attachSession({ sessionId, capabilities: { ui: { canvases: sessionCanvases } }, send: input => { sent.push(input); } });
      const ctx = { sessionId, extensionId: 'review-probe', canvasId: 'design-review-probe', instanceId: randomUUID() };
      if (hostCanvases !== undefined) ctx.host = { capabilities: { canvases: hostCanvases } };
      const label = `callback=${String(hostCanvases)}, session=${String(sessionCanvases)}`;
      const supported = (hostCanvases === undefined && sessionCanvases === undefined)
        || (hostCanvases === true && sessionCanvases === true)
        || (hostCanvases === true && sessionCanvases === undefined)
        || (hostCanvases === undefined && sessionCanvases === true);
      if (supported) {
        const { url } = await probe.canvas.open(ctx);
        assert.equal((await fetch(url)).status, 200, label);
        await assert.rejects(probe.canvas.open({ ...ctx, sessionId: randomUUID() }), /ownership/, label);
        await assert.rejects(probe.canvas.open({ ...ctx, extensionId: 'other-provider' }), /owner changed/, label);
        await probe.canvas.onClose(ctx);
        await assert.rejects(fetch(url), label);
      } else await assert.rejects(probe.canvas.open(ctx), /canvas support/, label);
      assert.deepEqual(sent, [], label);
      await probe.close();
    }
  }
});

test('open needs an attached exact session before starting a listener', async t => {
  const sessionId = randomUUID(), probe = createReviewProbe({ sessionId });
  t.after(() => probe.close());
  const ctx = { sessionId, extensionId: 'review-probe', canvasId: 'design-review-probe', instanceId: randomUUID() };
  await assert.rejects(probe.canvas.open(ctx), /not connected/);
  assert.throws(() => probe.attachSession({ send() {} }), /Invalid joined session/);
  assert.throws(() => probe.attachSession({ sessionId: randomUUID(), send() {} }), /Invalid joined session/);
  probe.attachSession({ sessionId, send() {} });
  for (const host of [undefined, {}, { capabilities: {} }]) {
    const { url } = await probe.canvas.open({ ...ctx, host });
    assert.equal((await fetch(url)).status, 200);
  }
  await probe.canvas.onClose(ctx);
});

test('concurrent open shares a transport and panel close preserves the same artifact', async t => {
  const f = await fixture(t);
  const duplicate = await Promise.all([f.probe.canvas.open(f.ctx), f.probe.canvas.open(f.ctx)]);
  assert(duplicate.every(result => result.url === f.url));
  await assert.rejects(f.probe.canvas.open({ ...f.ctx, extensionId: 'other-provider' }), /owner changed/);
  const openingContext = { ...f.ctx, instanceId: randomUUID() };
  const opening = f.probe.canvas.open(openingContext);
  const rejectedOpen = assert.rejects(opening, /closed|lukket/);
  await f.probe.canvas.onClose(openingContext);
  await rejectedOpen;
  const sibling = await f.probe.canvas.open(openingContext);
  assert.equal((await fetch(sibling.url)).status, 200);
  assert.equal((await fetch(f.url)).status, 200, 'Closing another instance must preserve its sibling');
  await f.probe.canvas.onClose(f.ctx);
  await f.probe.canvas.onClose(f.ctx);
  await assert.rejects(fetch(f.url));
  const before = f.state();
  const reopened = await Promise.all([f.probe.canvas.open(f.ctx), f.probe.canvas.open(f.ctx)]);
  assert.equal(reopened[0].url, reopened[1].url);
  assert.notEqual(reopened[0].url, f.url);
  assert.deepEqual(f.state(), before);
});

test('at most four logical artifacts are retained including closed panels', async t => {
  const f = await fixture(t);
  for (let index = 0; index < 3; index++) await f.probe.canvas.open({ ...f.ctx, instanceId: randomUUID() });
  await f.probe.canvas.onClose(f.ctx);
  await assert.rejects(f.probe.canvas.open({ ...f.ctx, instanceId: randomUUID() }), /four canvases/);
  assert.equal((await fetch((await f.probe.canvas.open(f.ctx)).url)).status, 200);
  assert.equal(f.sent.length, 0);
});

test('concurrent canvas and extension close both await actual listener cleanup', async t => {
  const f = await fixture(t);
  let canvasStopped = false;
  const canvasClose = f.probe.canvas.onClose(f.ctx).then(() => { canvasStopped = true; });
  await f.probe.close();
  assert.equal(canvasStopped, true, 'Extension cleanup must await a canvas close already in progress');
  await assert.rejects(fetch(f.url, { signal: AbortSignal.timeout(500) }));
  await canvasClose;

  const probe = createReviewProbe({ sessionId: f.ctx.sessionId });
  probe.attachSession({ sessionId: f.ctx.sessionId, send() {} });
  t.after(() => probe.close());
  const opening = assert.rejects(probe.canvas.open(f.ctx), /closed|lukket/);
  const closing = probe.canvas.onClose(f.ctx);
  await probe.close();
  await Promise.all([opening, closing]);
  assert.throws(() => probe.canvas.actions[0].handler({ ...f.ctx, input: {} }), /closed or unknown/);
});

test('panel close during and after final shutdown validates ownership and awaits retirement', async t => {
  const f = controlledLifecycle(t);
  await f.probe.canvas.open(f.ctx);
  const shutdown = f.probe.close();
  const panelClose = f.probe.canvas.onClose(f.ctx);
  const duplicateClose = f.probe.canvas.onClose(f.ctx);
  assert.equal(panelClose, duplicateClose);
  let panelSettled = false;
  panelClose.then(() => { panelSettled = true; });
  await f.servers[0].stopped;
  assert.equal(panelSettled, false, 'A close callback must wait for the pending listener cleanup');
  for (const overrides of [{ sessionId: randomUUID() }, { extensionId: 'other-provider' }, { canvasId: 'other-canvas' }]) {
    assert.throws(() => f.probe.canvas.onClose({ ...f.ctx, ...overrides }), error => error.status === 403);
  }
  assert.throws(f.state, error => error.status === 410);
  await assert.rejects(f.probe.canvas.open(f.ctx), error => error.status === 410);
  f.servers[0].finishClose();
  await Promise.all([shutdown, panelClose, duplicateClose]);
  assert.equal(panelSettled, true);
  assert.equal(f.probe.canvas.onClose(f.ctx), undefined);
  assert.equal(f.probe.canvas.onClose(f.ctx), undefined);
  assert.throws(() => f.probe.canvas.onClose({ ...f.ctx, extensionId: 'other-provider' }), error => error.status === 403);
  assert.throws(() => f.probe.canvas.onClose({ ...f.ctx, sessionId: randomUUID() }), error => error.status === 403);
  assert.throws(f.state, error => error.status === 410);
  await assert.rejects(f.probe.canvas.open(f.ctx), error => error.status === 410);
  assert.equal(f.servers.length, 1);
});

test('a newer close cancels a reopen waiting for an earlier transport close', async t => {
  const f = controlledLifecycle(t);
  await f.probe.canvas.open(f.ctx);
  const before = f.state();
  const firstClose = f.probe.canvas.onClose(f.ctx);
  const pendingReopen = assert.rejects(f.probe.canvas.open(f.ctx), error => error.status === 410);
  const lastClose = f.probe.canvas.onClose(f.ctx);
  assert.equal(firstClose, lastClose);
  await f.servers[0].stopped;
  assert.equal(f.servers.length, 1);
  f.servers[0].finishClose();
  await Promise.all([firstClose, pendingReopen, lastClose]);
  assert.equal(f.servers.length, 1, 'The cancelled open must not create a fresh transport');
  assert.deepEqual(f.state(), before);
  await f.probe.canvas.open(f.ctx);
  assert.equal(f.servers.length, 2, 'A subsequent explicit open can restore the retained artifact');
  assert.deepEqual(f.state(), before);
});

test('finite expiry revokes the endpoint even without an onClose callback', async t => {
  const f = await fixture(t, { lifetimeMs: 100 });
  await pause(150);
  assert.throws(() => f.state(), /closed or unknown/);
  await assert.rejects(fetch(f.url, { signal: AbortSignal.timeout(500) }));
  await assert.rejects(f.probe.canvas.open(f.ctx), /fresh canvas/);
  assert.equal(f.sent.length, 0);
});

test('late delivery after panel close updates only its retained artifact', async t => {
  let acknowledge;
  const f = await fixture(t, {}, () => new Promise(resolve => { acknowledge = resolve; }));
  assert.equal((await f.post(f.input())).status, 202);
  assert.equal(f.sent.length, 1);
  await f.probe.canvas.onClose(f.ctx);
  const other = { ...f.ctx, instanceId: randomUUID() };
  await f.probe.canvas.open(other);
  acknowledge('late-message');
  await pause(10);
  const state = f.action('read_state', {}, { instanceId: other.instanceId });
  assert.equal(state.revision, 1);
  assert.deepEqual(state.batches, []);
  assert.equal(f.state().batches[0].messageId, 'late-message');
  assert.equal(f.state().batches[0].delivery, 'queued');
  const beforeReopen = f.state();
  const reopened = await f.probe.canvas.open(f.ctx);
  assert.notEqual(reopened.url, f.url);
  assert.deepEqual(f.state(), beforeReopen);
  assert.equal(f.sent.length, 1);
});

test('reopening retains history and batch identity while revoking the old token and owner', async t => {
  const f = await fixture(t);
  const first = f.input();
  assert.equal((await f.post(first)).status, 202);
  await pause(0);
  f.action('apply_revision', { expectedRevision: f.state().revision, title: 'Behold denne tittelen', description: 'En forklaring som skal finnes igjen.' });
  const before = f.state();
  await f.probe.canvas.onClose(f.ctx);
  assert.deepEqual(f.state(), before);
  await assert.rejects(f.probe.canvas.open({ ...f.ctx, extensionId: 'other-provider' }), /owner changed/);
  await assert.rejects(f.probe.canvas.open({ ...f.ctx, input: { concept: 'booking' } }), /another design case/);
  const opened = await f.probe.canvas.open(f.ctx);
  const oldUrl = new URL(f.url), currentUrl = new URL(opened.url);
  assert.notEqual(currentUrl.search, oldUrl.search);
  const rejectedToken = new URL(currentUrl); rejectedToken.search = oldUrl.search;
  assert.equal((await fetch(rejectedToken)).status, 403);
  const oldResponse = await fetch(oldUrl, { signal: AbortSignal.timeout(2000) }).catch(() => null);
  if (oldResponse) assert.equal(oldResponse.status, 403, 'Port reuse must still reject the revoked token');
  assert.deepEqual(f.state(), before);
  const endpoint = new URL('/api/submit', currentUrl); endpoint.search = currentUrl.search;
  const response = await fetch(endpoint, { method: 'POST', headers: { Origin: currentUrl.origin, 'Content-Type': 'application/json' }, body: JSON.stringify(first) });
  assert.equal(response.status, 202);
  assert.equal((await response.json()).batch.id, first.requestId);
  assert.equal(f.sent.length, 1, 'Reopening and retrying an accepted batch must not enqueue again');
  // Close callbacks have no view generation. A late callback may hide the new
  // view, but it cannot discard the retained artifact or accepted round.
  await f.probe.canvas.onClose(f.ctx);
  await assert.rejects(fetch(currentUrl));
  assert.deepEqual(f.state(), before);
  assert.equal((await fetch((await f.probe.canvas.open(f.ctx)).url)).status, 200);
});

test('an incomplete POST from a closed transport cannot mutate its reopened artifact', async t => {
  const f = await fixture(t);
  const payload = JSON.stringify(f.input());
  let request;
  const disconnected = new Promise(resolve => {
    request = http.request(f.endpoint('/api/submit'), { method: 'POST', headers: { Origin: new URL(f.url).origin, 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) } });
    request.on('error', () => resolve());
    request.on('response', response => { response.resume(); response.on('end', resolve); });
  });
  await new Promise((resolve, reject) => {
    request.once('error', reject);
    request.write(payload.slice(0, -1), resolve);
  });
  await f.probe.canvas.onClose(f.ctx);
  const reopened = await f.probe.canvas.open(f.ctx);
  request.end(payload.slice(-1));
  await disconnected;
  assert.equal((await fetch(reopened.url)).status, 200);
  assert.deepEqual(f.state().batches, []);
  assert.equal(f.sent.length, 0);
});

test('panel reopen never extends the original artifact expiry', async t => {
  const f = await fixture(t, { lifetimeMs: 300 });
  await pause(150);
  await f.probe.canvas.onClose(f.ctx);
  const reopened = await f.probe.canvas.open(f.ctx);
  await pause(200);
  assert.throws(() => f.state(), /closed or unknown/);
  await assert.rejects(fetch(reopened.url, { signal: AbortSignal.timeout(500) }));
  await assert.rejects(f.probe.canvas.open(f.ctx), /fresh canvas/);
});

test('a late working action cannot downgrade a resolved batch or replace its reply', async t => {
  const f = await fixture(t);
  const input = f.input();
  assert.equal((await f.post(input)).status, 202);
  await pause(0);
  f.action('review_batch', { batchId: input.requestId, status: 'resolved', reply: 'Ferdig vurdert.' });
  const resolved = f.state();
  assert.throws(() => f.action('review_batch', { batchId: input.requestId, status: 'working', reply: 'Et forsinket kall.' }), error => error.status === 409);
  assert.deepEqual(f.state(), resolved);
});

test('historical batch context is bounded, immutable and independent of new copy', async t => {
  const f = await fixture(t);
  const original = f.state();
  f.action('apply_revision', { expectedRevision: original.revision, title: 'Ny tittel', description: 'Ny forklaring' });
  const body = { ...f.input(), screen: original.screen };
  const response = await f.post(body);
  assert.equal(response.status, 202);
  const batch = (await response.json()).batch;
  assert.deepEqual(batch.document, original.document);
  assert.equal(batch.screen, original.screen);
  const copied = f.state(); copied.batches[0].document.title = 'Changed outside the store';
  assert.equal(f.state().batches[0].document.title, original.document.title);
  for (let index = f.state().screen; index < 50; index++) f.action('apply_revision', { expectedRevision: f.state().revision, title: `Skisse ${index + 1}`, description: 'Begrenset historikk' });
  assert.throws(() => f.action('apply_revision', { expectedRevision: f.state().revision, title: 'For mange', description: '' }), /revision limit/);
  assert.equal(f.state().batches[0].document.title, original.document.title);
});
