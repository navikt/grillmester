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

test('repeated concurrent open reuses one instance and close retires its identity', async t => {
  const f = await fixture(t);
  const duplicate = await Promise.all([f.probe.canvas.open(f.ctx), f.probe.canvas.open(f.ctx)]);
  assert(duplicate.every(result => result.url === f.url));
  await assert.rejects(f.probe.canvas.open({ ...f.ctx, extensionId: 'other-provider' }), /owner changed/);
  const openingContext = { ...f.ctx, instanceId: randomUUID() };
  const opening = f.probe.canvas.open(openingContext);
  const rejectedOpen = assert.rejects(opening, /closed/);
  await f.probe.canvas.onClose(openingContext);
  await rejectedOpen;
  await assert.rejects(f.probe.canvas.open(openingContext), /fresh canvas/);
  assert.equal((await fetch(f.url)).status, 200, 'Closing another instance must preserve its sibling');
  await f.probe.canvas.onClose(f.ctx);
  await f.probe.canvas.onClose(f.ctx);
  await assert.rejects(f.probe.canvas.open(f.ctx), /fresh canvas/);
  await assert.rejects(fetch(f.url));
});

test('at most four open canvases are admitted', async t => {
  const f = await fixture(t);
  for (let index = 0; index < 3; index++) await f.probe.canvas.open({ ...f.ctx, instanceId: randomUUID() });
  await assert.rejects(f.probe.canvas.open({ ...f.ctx, instanceId: randomUUID() }), /Close a canvas/);
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
  t.after(() => probe.close());
  const opening = assert.rejects(probe.canvas.open(f.ctx), /closed/);
  const closing = probe.canvas.onClose(f.ctx);
  await probe.close();
  await Promise.all([opening, closing]);
  assert.throws(() => probe.canvas.actions[0].handler({ ...f.ctx, input: {} }), /closed or unknown/);
});

test('finite expiry revokes the endpoint even without an onClose callback', async t => {
  const f = await fixture(t, { lifetimeMs: 100 });
  await pause(150);
  assert.throws(() => f.state(), /closed or unknown/);
  await assert.rejects(fetch(f.url, { signal: AbortSignal.timeout(500) }));
  await assert.rejects(f.probe.canvas.open(f.ctx), /fresh canvas/);
  assert.equal(f.sent.length, 0);
});

test('a late delivery receipt after closing cannot mutate a new canvas', async t => {
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
