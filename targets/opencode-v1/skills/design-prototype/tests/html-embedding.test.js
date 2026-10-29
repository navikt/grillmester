'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { createHtmlEmbedding, renderEmbeddingBootstrap } = require('../scripts/html-embedding.js');
const options = { parentOrigin: 'http://127.0.0.1:4000', leaseId: 'a'.repeat(32) };
test('embedding accepts only exact loopback parent and bounded closed lease', () => {
  for (const bad of [null, {}, { ...options, extra: true }, { ...options, parentOrigin: 'http://localhost:4000' }, { ...options, parentOrigin: 'http://127.0.0.1:99999' }, { ...options, parentOrigin: 'http://127.0.0.1:0' }, { ...options, parentOrigin: 'http://127.0.0.1:4000/' }, { ...options, leaseId: 'b'.repeat(33) }]) assert.throws(() => createHtmlEmbedding(bad), error => error.status === 400);
});
test('candidate GET carries no active authority and only one candidate can activate', () => {
  const state = createHtmlEmbedding(options);
  assert.throws(() => state.candidate('x'), error => error.status === 410);
  const one = state.candidate(state.invitation), two = state.candidate(state.invitation);
  assert.equal(state.active, false);
  for (const bad of [{ candidate: one.candidate, activationKey: 'ø'.repeat(64) }, { candidate: one.candidate, activationKey: state.activationKey, extra: true }, { candidate: 'a'.repeat(64), activationKey: state.activationKey }]) assert.throws(() => state.activate(bad), error => error.status === 403);
  const input = { candidate: one.candidate, activationKey: state.activationKey };
  assert.equal(state.activate(input).nonce, one.nonce); assert.equal(state.active, true);
  assert.equal(state.activate(input).nonce, one.nonce, 'Lost activation response can be retried by same candidate.');
  assert.throws(() => state.activate({ candidate: two.candidate, activationKey: state.activationKey }), error => error.status === 409);
  assert.throws(() => state.candidate(state.invitation), error => error.status === 409);
  state.revoke(); assert.equal(state.active, false);
  assert.throws(() => state.activate(input), error => error.status === 410);
});
test('bootstrap is inert outside exact parent and does not contain activation authority', () => {
  const state = createHtmlEmbedding(options), candidate = state.candidate(state.invitation);
  const html = renderEmbeddingBootstrap({ ...options, ...candidate });
  assert.ok(!html.includes(state.activationKey)); assert.ok(!html.includes('token='));
  assert.match(html, /event\.source!==window\.parent/); assert.match(html, /event\.origin!==config\.parentOrigin/);
  assert.match(html, /window\.parent===window/);
});
test('unactivated candidate capacity is bounded', () => {
  const state = createHtmlEmbedding(options);
  for (let index = 0; index < 8; index++) state.candidate(state.invitation);
  assert.throws(() => state.candidate(state.invitation), error => error.status === 409);
});

test('bootstrap retry keeps one candidate/key, bounds attempts and does not accept a replacement parent key', async () => {
  const { runInNewContext } = require('node:vm');
  const state = createHtmlEmbedding(options), candidate = state.candidate(state.invitation), calls = [], listeners = {};
  const status = { textContent: '' }, attributes = new Map(), retry = { hidden: true, disabled: false,
    setAttribute: (name, value) => attributes.set(name, value), removeAttribute: name => attributes.delete(name),
    addEventListener: (name, listener) => { listeners[`button:${name}`] = listener; } };
  const parent = { postMessage() {} }, window = { parent, addEventListener: (name, listener) => { listeners[name] = listener; } };
  const html = renderEmbeddingBootstrap({ ...options, ...candidate });
  const script = /<script nonce="[^"]+">([\s\S]*?)<\/script>/.exec(html)[1];
  runInNewContext(script, { window, document: { querySelector: selector => selector === 'button' ? retry : status },
    AbortController, setTimeout, clearTimeout, fetch: async (path, input) => { calls.push({ path, body: input.body }); throw new Error('response lost'); } });
  const event = { source: parent, origin: options.parentOrigin, data: { channel: 'design-workshop-embed', version: 1, command: 'activate', leaseId: options.leaseId, activationKey: state.activationKey } };
  listeners.message({ ...event, source: {} }); assert.equal(calls.length, 0);
  listeners.message(event); assert.equal(retry.disabled, true); assert.equal(attributes.get('aria-busy'), 'true');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(retry.hidden, false); assert.equal(retry.disabled, false); assert.equal(attributes.has('aria-busy'), false);
  listeners.message({ ...event, data: { ...event.data, activationKey: 'b'.repeat(64) } }); assert.equal(calls.length, 1);
  for (let index = 0; index < 3; index++) { listeners['button:click'](); await new Promise(resolve => setImmediate(resolve)); }
  assert.equal(calls.length, 3); assert.equal(new Set(calls.map(call => call.body)).size, 1);
  assert.ok(calls.every(call => call.path === '/embedded/activate')); assert.equal(retry.hidden, true);
  assert.match(status.textContent, /Åpne verkstedet på nytt/);
});
