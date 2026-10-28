import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import http from 'node:http';
import { createServerBackend } from '../backend.mjs';
async function fixture(run) {
  const projectDir = await mkdtemp(join(tmpdir(), 'workshop-embedding-')); let backend;
  try { backend = await createServerBackend({ projectDir }); await run(backend); }
  finally { await backend?.retire({}); await rm(projectDir, { recursive: true, force: true }); }
}
async function candidate(view) {
  const response = await fetch(view.url); assert.equal(response.status, 200);
  const html = await response.text(); assert.ok(!html.includes(view.activationKey)); assert.ok(!html.includes('token='));
  const config = JSON.parse(/const config=(\{.*?\});let pending/.exec(html)[1]);
  return { ...config, csp: response.headers.get('content-security-policy') };
}
async function activate(view, doc, origin = view.origin) {
  return fetch(`${view.origin}/embedded/activate`, { method: 'POST', headers: { Origin: origin, 'Content-Type': 'application/json' }, body: JSON.stringify({ candidate: doc.candidate, activationKey: view.activationKey }) });
}
const embedded = { parentOrigin: 'http://127.0.0.1:45678', leaseId: 'a'.repeat(32) };

test('embedded HTML has one authenticated document, exact ancestors and inert copied entry', () => fixture(async backend => {
  const state = await backend.publishRevision({ expectedScreen: '', filename: 'first.html', html: '<h1>Forslag</h1>' });
  const view = await backend.openView({ embedding: embedded });
  assert.equal(view.leaseId, embedded.leaseId); assert.match(view.activationKey, /^[a-f0-9]{64}$/);
  const one = await candidate(view), two = await candidate(view);
  assert.ok(one.csp.includes(`frame-ancestors ${embedded.parentOrigin}`));
  assert.equal((await activate(view, one, 'http://127.0.0.1:45679')).status, 403);
  const response = await activate(view, one); assert.equal(response.status, 200);
  const html = await response.text(), token = /\/preview\?token=([^"&]+)/.exec(html)[1];
  assert.match(html, /#vc-status\[data-connected=/);
  assert.match(html, /event:"activated"/); assert.ok(html.includes(state.screen));
  assert.equal((await activate(view, one)).status, 200);
  assert.equal((await activate(view, two)).status, 409);
  assert.equal((await fetch(view.url)).status, 409);
  assert.equal((await fetch(`${view.origin}/?token=${token}`)).status, 410);
  const preview = await fetch(`${view.origin}/preview?token=${token}`);
  assert.equal(preview.status, 200); const previewHtml = await preview.text(); assert.match(previewHtml, /body > main\.vc-content \{ margin: 0 auto; padding: 16px/); assert.match(previewHtml, /window\.__grillmesterVisualCompanionEmbedded=true/); assert.ok(preview.headers.get('content-security-policy').includes(`frame-ancestors 'self' ${embedded.parentOrigin}`));
  assert.equal((await fetch(`${view.origin}/comments?token=${token}`)).status, 200);
  await backend.closeView({});
  const next = await backend.openView({ embedding: { ...embedded, leaseId: 'b'.repeat(32) } });
  assert.notEqual(next.url, view.url); assert.notEqual(next.activationKey, view.activationKey);
  const current = await backend.readState({}); assert.equal(current.screen, state.screen);
  await assert.rejects(fetch(view.url, { signal: AbortSignal.timeout(1000) }));
}));

test('closing an embedded document while a feedback body is pending does not mutate it', () => fixture(async backend => {
  const state = await backend.publishRevision({ expectedScreen: '', filename: 'first.html', html: '<h1>Forslag</h1>' });
  const view = await backend.openView({ embedding: embedded }), doc = await candidate(view);
  const response = await activate(view, doc), html = await response.text(), token = /\/preview\?token=([^"&]+)/.exec(html)[1];
  const before = await backend.readState({});
  const body = JSON.stringify({ screen: state.screen, kind: 'point', text: 'Et forslag.', anchor: { path: 'body:nth-of-type(1)', role: '', rect: { x: 0, y: 0, width: 10, height: 10 }, viewport: { width: 800, height: 600 } } });
  let settled;
  const ended = new Promise(resolve => { settled = resolve; });
  const req = http.request(`${view.origin}/comments?token=${token}`, { method: 'POST', headers: { Origin: view.origin, 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) } }, res => { res.resume(); res.once('end', () => settled(res.statusCode)); });
  req.on('error', () => settled('closed')); req.write(body.slice(0, -1));
  await new Promise(resolve => setTimeout(resolve, 25));
  await backend.closeView({}); req.end(body.slice(-1)); await ended;
  const after = await backend.readState({}); assert.equal(after.revision, before.revision); assert.equal(after.submission, 0);
}));


test('standalone HTML keeps its existing header, outer spacing and connected status', () => fixture(async backend => {
  await backend.publishRevision({ expectedScreen: '', filename: 'standalone.html', html: '<h1>Selvstendig skisse</h1>' });
  const view = await backend.openView({}), shell = await (await fetch(view.url)).text();
  assert.doesNotMatch(shell, /#vc-status\[data-connected=/);
  const preview = new URL(view.url); preview.pathname = '/preview';
  const html = await (await fetch(preview)).text();
  assert.match(html, /class="vc-header"/);
  assert.match(html, /window\.__grillmesterVisualCompanionEmbedded=false/);
  assert.doesNotMatch(html, /body > main\.vc-content \{ margin: 0 auto; padding: 16px/);
}));
