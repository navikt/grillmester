import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import fs from 'node:fs';
import http from 'node:http';
import { EventEmitter } from 'node:events';
import { runInNewContext } from 'node:vm';
import { createServerBackend } from '../backend.mjs';
import { createCanvasAdapter } from '../adapter.mjs';
import feedbackApi from '../../../skills/design-prototype/scripts/feedback-store.js';
import workspaceApi from '../../../skills/design-prototype/scripts/workspace-store.js';
import workspaceStateApi from '../../../skills/design-prototype/scripts/workspace-state.js';
import applicationWorkspaceApi from '../../../skills/design-prototype/scripts/application-workspace.js';
import applicationProposalsApi from '../../../skills/design-prototype/scripts/application-proposals.js';

const waitFor = async read => { for (let index = 0; index < 100; index++) { if (await read()) return; await new Promise(resolve => setTimeout(resolve, 20)); } assert.fail('Timed out waiting for the owned backend.'); };
async function fixture(run) {
  const projectDir = await mkdtemp(join(tmpdir(), 'visual-canvas-backend-'));
  const submitted = []; let exits = 0, backend;
  try {
    backend = await createServerBackend({ projectDir, onSubmitted: round => submitted.push(round), onExit: () => { exits++; } });
    await run({ backend, submitted, exits: () => exits });
  } finally { await backend?.retire({}); await rm(projectDir, { recursive: true, force: true }); }
}
const request = async (view, pathname, method = 'GET', value, mutationId) => {
  const url = new URL(view.url); url.pathname = pathname;
  const response = await fetch(url, { method, signal: AbortSignal.timeout(3000), headers: { Origin: url.origin, 'Content-Type': 'application/json', ...(mutationId ? { 'X-Feedback-Mutation': mutationId } : {}) }, ...(value ? { body: JSON.stringify(value) } : {}) });
  return { status: response.status, value: await response.json() };
};
const note = screen => ({ screen, kind: 'point', text: 'Gjør neste steg tydeligere.', anchor: { path: 'body:nth-of-type(1) > div:nth-of-type(2) > h1:nth-of-type(1)', role: 'heading', rect: { x: 0, y: 0, width: 150, height: 35 }, viewport: { width: 1000, height: 800 } } });

test('the child reuses full preview, immutable submission, guarded reply and revoked/reopened transport', () => fixture(async ({ backend, submitted, exits }) => {
  const first = await backend.openView({});
  assert.equal(new URL(first.url).hostname, '127.0.0.1');
  const empty = await backend.readState({}); assert.equal(empty.submission, 0);
  const published = await backend.publishRevision({ expectedScreen: empty.screen, filename: 'meeting.html', html: '<h1>Forbered møtet</h1><p>Ta med to spørsmål.</p>' });
  assert.match(published.screen, /^[a-f0-9]{32}$/);
  await assert.rejects(backend.publishRevision({ expectedScreen: '', filename: 'stale.html', html: '<p>Stale</p>' }), error => error.status === 409);
  const created = await request(first, '/comments', 'POST', note(published.screen)); assert.equal(created.status, 200);
  const batch = await request(first, '/comments/submit', 'POST', { revision: created.value.revision }, 'a'.repeat(32)); assert.equal(batch.status, 200);
  await waitFor(() => submitted.length === 1); assert.deepEqual(submitted, [1]);
  const retry = await request(first, '/comments/submit', 'POST', { revision: created.value.revision }, 'a'.repeat(32)); assert.equal(retry.status, 200);
  assert.deepEqual(submitted, [1], 'Recovering a persisted HTTP receipt must not emit another delivery.');
  const delivery = await backend.markDelivery({ submission: 1, status: 'queued' });
  assert.equal(delivery.canvas.rounds[0].delivery, 'queued'); assert.equal(delivery.canvas.rounds[0].review, 'unread');
  await backend.reviewSubmission({ submission: 1, status: 'working', reply: 'Jeg ser på neste steg.' });
  const page = await backend.readSubmission({ submission: 1 });
  const comment = page.items.find(item => item.type === 'comment').value;
  assert.equal(comment.text, note(published.screen).text); assert.equal(page.nextOffset, null);
  await assert.rejects(backend.updateComment({ id: comment.id, submission: 2, status: 'fixed' }), error => error.status === 404);
  await backend.updateComment({ id: comment.id, submission: 1, status: 'fixed', reply: 'Neste steg er tydeligere.' });
  await backend.reviewSubmission({ submission: 1, status: 'answered', reply: 'Forslaget er fulgt opp i skissen.' });
  const immutable = await backend.readSubmission({ submission: 1 });
  assert.equal(immutable.items.find(item => item.type === 'comment').value.status, 'open');
  assert.equal(immutable.items.find(item => item.type === 'comment').current.status, 'fixed');
  await backend.closeView({});
  await assert.rejects(fetch(first.url, { signal: AbortSignal.timeout(1000) }));
  const reopened = await backend.openView({}); assert.notEqual(first.url, reopened.url);
  const retained = await backend.readState({}); assert.equal(retained.screen, published.screen); assert.equal(retained.canvas.rounds[0].review, 'answered');
  assert.equal(submitted.length, 1);
  await backend.retire({}); await waitFor(() => exits() === 1);
  await assert.rejects(fetch(reopened.url, { signal: AbortSignal.timeout(1000) }));
}));

test('an uncertain round blocks another submission until exact trusted review acknowledges it', () => fixture(async ({ backend, submitted }) => {
  const view = await backend.openView({});
  const published = await backend.publishRevision({ expectedScreen: '', filename: 'booking.html', html: '<h1>Velg tidspunkt</h1>' });
  let response = await request(view, '/comments', 'POST', note(published.screen)); assert.equal(response.status, 200);
  response = await request(view, '/comments/submit', 'POST', { revision: response.value.revision }); assert.equal(response.status, 200);
  await waitFor(() => submitted.length === 1);
  await backend.markDelivery({ submission: 1, status: 'unknown' });
  response = await request(view, '/comments', 'POST', { ...note(published.screen), text: 'Et separat nytt innspill.' });
  const blocked = await request(view, '/comments/submit', 'POST', { revision: response.value.revision }); assert.equal(blocked.status, 409);
  assert.equal((await backend.readState({})).submission, 1); assert.deepEqual(submitted, [1]);
  await backend.reviewSubmission({ submission: 1, status: 'working', reply: 'Runden er mottatt og vurderes.' });
  const current = await request(view, '/comments');
  const accepted = await request(view, '/comments/submit', 'POST', { revision: current.value.revision }); assert.equal(accepted.status, 200);
  await waitFor(() => submitted.length === 2); assert.deepEqual(submitted, [1, 2]);
}));

test('a project workspace survives child restart with bounded history, guarded restore and no replay', async () => {
  const projectDir = await mkdtemp(join(tmpdir(), 'visual-canvas-recovery-'));
  const submitted = [], options = { projectDir, workspacePath: 'designs/booking', onSubmitted: value => submitted.push(value) };
  let backend;
  try {
    backend = await createServerBackend({ ...options, create: true, title: 'Timebestilling' });
    const view = await backend.openView({});
    const html = `<h1>Første skisse 🧭</h1><!--${'🧭ø'.repeat(23000)}-->`;
    const design = { version: 1, variants: [], targets: [] };
    const first = await backend.publishRevision({ expectedScreen: '', filename: 'booking-first.html', html, design });
    assert.equal(first.workspace.title, 'Timebestilling'); assert.equal(first.workspace.storage, 'project');
    assert.equal(first.workspace.version, 1); assert.equal(first.workspace.recovered, false);
    const created = await request(view, '/comments', 'POST', note(first.screen)); assert.equal(created.status, 200);
    assert.equal((await request(view, '/comments/submit', 'POST', { revision: created.value.revision })).status, 200);
    await waitFor(() => submitted.length === 1);
    await backend.markDelivery({ submission: 1, status: 'queued' });
    await backend.reviewSubmission({ submission: 1, status: 'working', reply: 'Jeg vurderer første skisse.' });
    const second = await backend.publishRevision({ expectedScreen: first.screen, filename: 'booking-second.html', html: '<h1>Andre skisse</h1>' });
    await backend.retire({}); backend = undefined;
    await assert.rejects(fetch(view.url, { signal: AbortSignal.timeout(1000) }));

    backend = await createServerBackend(options);
    const recovered = await backend.readState({});
    assert.equal(recovered.workspace.id, first.workspace.id); assert.equal(recovered.workspace.path, options.workspacePath);
    assert.equal(recovered.workspace.recovered, true); assert.equal(recovered.workspace.version, 2);
    assert.equal(recovered.screen, second.screen); assert.equal(recovered.submission, 1);
    assert.equal(recovered.canvas.rounds[0].delivery, 'queued'); assert.equal(recovered.canvas.rounds[0].review, 'working');
    assert.equal(recovered.canvas.rounds[0].previousSession, true);
    assert.deepEqual(submitted, [1], 'Hydration must never emit the persisted submission again.');
    await assert.rejects(backend.markDelivery({ submission: 1, status: 'queued' }), error => error.status === 409);
    const history = await backend.listHistory({ limit: 1 });
    assert.deepEqual(history.items.map(item => item.revisionId), [2]); assert.equal(history.hasMore, true);
    const older = await backend.listHistory({ after: history.nextAfter, limit: 1 });
    assert.deepEqual(older.items.map(item => item.revisionId), [1]); assert.equal(older.nextAfter, null);
    let offset = 0, source = '', pages = 0;
    do {
      const page = await backend.readRevision({ revisionId: 1, part: 'html', offset });
      assert(Buffer.byteLength(JSON.stringify(page)) <= 65536); assert(!/[\uD800-\uDBFF]$/.test(page.content));
      source += page.content; pages++; offset = page.nextOffset;
    } while (offset !== null);
    assert.equal(source, html); assert(pages > 1);
    assert.deepEqual(JSON.parse((await backend.readRevision({ revisionId: 1, part: 'design' })).content), design);
    await assert.rejects(backend.restoreRevision({ revisionId: 1, expectedRevision: recovered.revision - 1 }), error => error.status === 409);
    const restored = await backend.restoreRevision({ revisionId: 1, expectedRevision: recovered.revision });
    assert.equal(restored.workspace.version, 3); assert.notEqual(restored.screen, first.screen); assert.notEqual(restored.screen, second.screen);
    assert.equal(restored.submission, 1);
    const batch = await backend.readSubmission({ submission: 1 });
    assert.equal(batch.items.find(item => item.type === 'comment').value.screen, first.screen);
    assert.equal(batch.items.find(item => item.type === 'comment').value.text, note(first.screen).text);
    assert.deepEqual(submitted, [1], 'History reads and restore must not send old feedback.');
    await backend.reviewSubmission({ submission: 1, status: 'working', reply: 'Jeg fortsetter vurderingen her.' });
    assert.notEqual((await backend.readState({})).canvas.rounds[0].previousSession, true);
    const newView = await backend.openView({});
    const draft = await request(newView, '/comments', 'POST', { ...note(restored.screen), text: 'Et nytt innspill etter gjenåpning.' });
    assert.equal((await request(newView, '/comments/submit', 'POST', { revision: draft.value.revision })).status, 200);
    await waitFor(() => submitted.length === 2); assert.deepEqual(submitted, [1, 2]);
  } finally { await backend?.retire({}); await rm(projectDir, { recursive: true, force: true }); }
});

test('another process cannot write an owned workspace, and a stopped startup can reopen after release', async () => {
  const projectDir = await mkdtemp(join(tmpdir(), 'visual-canvas-lock-'));
  const options = { projectDir, workspacePath: 'designs/room' };
  let owner, next;
  try {
    owner = await createServerBackend({ ...options, create: true, title: 'Arbeidsrom' });
    const original = await owner.readState({});
    await assert.rejects(createServerBackend(options), error => error.status === 409 && error.backendStopped === true && error.backendWasReady === false
      && /åpent i en annen økt/.test(error.message));
    assert.equal((await owner.readState({})).workspace.id, original.workspace.id);
    await owner.retire({}); owner = undefined;
    next = await createServerBackend(options);
    assert.equal((await next.readState({})).workspace.id, original.workspace.id);
  } finally { await owner?.retire({}); await next?.retire({}); await rm(projectDir, { recursive: true, force: true }); }
});

test('later save preserves all temporary versions, immutable rounds and unsent feedback without restarting the view', async () => {
  const projectDir = await mkdtemp(join(tmpdir(), 'visual-canvas-later-save-')), deliveries = [];
  let backend;
  try {
    backend = await createServerBackend({ projectDir, onSubmitted: value => deliveries.push(value) });
    const view = await backend.openView({});
    const first = await backend.publishRevision({ expectedScreen: '', filename: 'first.html', html: '<h1>Første valg</h1>', design: { version: 1, targets: [], variants: [] } });
    const created = await request(view, '/comments', 'POST', note(first.screen)); assert.equal(created.status, 200);
    assert.equal((await request(view, '/comments/submit', 'POST', { revision: created.value.revision })).status, 200);
    await waitFor(() => deliveries.length === 1);
    await backend.markDelivery({ submission: 1, status: 'queued' });
    await backend.reviewSubmission({ submission: 1, status: 'answered', reply: 'Et tydeligere valg vises i forslaget.' });
    const second = await backend.publishRevision({ expectedScreen: first.screen, filename: 'second.html', html: '<h1>Andre valg</h1>' });
    const unsent = await request(view, '/comments', 'POST', { ...note(second.screen), text: 'Dette er ikke sendt ennå.' }); assert.equal(unsent.status, 200);
    const before = await backend.readState({}), immutable = await backend.readSubmission({ submission: 1 });
    const input = { workspacePath: 'designs/proposal', workspaceId: 'c'.repeat(24), title: 'Valg', expectedScreen: before.screen, expectedRevision: before.revision };
    await assert.rejects(backend.saveWorkspace({ ...input, expectedRevision: before.revision - 1 }), error => error.status === 409);
    assert.equal(fs.existsSync(join(projectDir, input.workspacePath)), false);
    const saved = await backend.saveWorkspace(input);
    assert.equal(saved.screen, second.screen); assert.equal(saved.workspace.version, 2); assert.equal(saved.workspace.id, input.workspaceId);
    assert.equal(saved.revision, before.revision + 1); assert.equal(saved.submission, 1);
    assert.deepEqual(await backend.readSubmission({ submission: 1 }), immutable);
    assert.equal((await request(view, '/comments')).value.comments.some(comment => comment.text === 'Dette er ikke sendt ennå.' && !comment.submitted), true);
    assert.deepEqual(deliveries, [1]);
    assert.deepEqual(await backend.saveWorkspace(input), saved, 'Exact retry must neither increment state nor replace the renderer.');
    const disk = JSON.parse(fs.readFileSync(join(projectDir, input.workspacePath, 'workspace.json')));
    assert.equal(disk.submissions.length, 1); assert.equal(disk.screens.length, 2); assert.equal(disk.canvas.rounds[0].review, 'answered');
    assert.equal((await backend.listHistory({})).items.length, 2);
    assert.equal((await backend.readRevision({ revisionId: 1, part: 'html' })).content, '<h1>Første valg</h1>');
    const third = await backend.publishRevision({ expectedScreen: saved.screen, filename: 'third.html', html: '<h1>Tredje valg</h1>' });
    assert.equal(third.workspace.version, 3); assert.equal((await request(view, '/comments')).status, 200);
    await backend.retire({}); backend = undefined;
    backend = await createServerBackend({ projectDir, workspacePath: input.workspacePath, onSubmitted: value => deliveries.push(value) });
    const reopened = await backend.readState({});
    assert.equal(reopened.screen, third.screen); assert.equal(reopened.workspace.id, input.workspaceId); assert.equal(reopened.workspace.version, 3);
    assert.equal(reopened.canvas.rounds[0].review, 'answered'); assert.deepEqual(deliveries, [1]);
    assert.equal((await backend.readSubmission({ submission: 1 })).items.find(item => item.type === 'comment').value.screen, first.screen);
  } finally { await backend?.retire({}); await rm(projectDir, { recursive: true, force: true }); }
});

test('later save through the app backend retains one proposal and reopens its exact saved identity', async () => {
  const projectDir = await mkdtemp(join(tmpdir(), 'visual-app-later-save-')), deliveries = [];
  const options = { projectDir, workspacePath: 'designs/app', application: { name: 'Møtedemo', url: 'http://localhost:32100/demo' }, onSubmitted: (...value) => deliveries.push(value) };
  let backend;
  try {
    backend = await createServerBackend({ ...options, create: true });
    const first = await backend.publishProposal({ source: 'conversation', title: 'Forslag', filename: 'one.html', html: '<h1>Første</h1>' });
    const second = await backend.publishRevision({ proposalId: first.id, expectedScreen: first.screen, filename: 'two.html', html: '<h1>Andre</h1>' });
    const input = { proposalId: first.id, workspacePath: 'designs/proposal', expectedScreen: second.screen, expectedRevision: second.revision };
    const saved = await backend.saveProposal(input); assert.equal(saved.id, first.id); assert.equal(saved.storage, 'project'); assert.equal(saved.revisionId, 2);
    assert.deepEqual(await backend.saveProposal(input), saved);
    const binding = JSON.parse(fs.readFileSync(join(projectDir, 'designs/app/workspace.json'))).workspace.sketch;
    assert.equal(binding.id, first.id); assert.equal(binding.source, 'conversation');
    assert.equal((await backend.listHistory({ proposalId: first.id })).items.length, 2);
    await backend.retire({}); backend = undefined;
    const before = fs.readFileSync(join(projectDir, 'designs/app/workspace.json'));
    backend = await createServerBackend(options);
    const state = await backend.readState({}); assert.equal(state.proposals[0].id, first.id); assert.equal(state.proposals[0].storage, 'project');
    assert.deepEqual(fs.readFileSync(join(projectDir, 'designs/app/workspace.json')), before, 'Opening the saved link does not rewrite its parent.');
    const proposal = await backend.readState({ proposalId: first.id }); assert.equal(proposal.workspace.id, binding.workspaceId); assert.equal(proposal.screen, second.screen);
    assert.equal((await backend.readRevision({ proposalId: first.id, revisionId: 1, part: 'html' })).content, '<h1>Første</h1>');
    assert.deepEqual(deliveries, []);
  } finally { await backend?.retire({}); await rm(projectDir, { recursive: true, force: true }); }
});

test('later save recovers an actual child commit after parent binding failed, without recreating or silently adopting it', async () => {
  const projectDir = fs.realpathSync(await mkdtemp(join(tmpdir(), 'visual-save-recovery-'))), deliveries = [];
  const { ApplicationWorkspace } = applicationWorkspaceApi, { ApplicationProposals } = applicationProposalsApi;
  const options = { projectDir, workspacePath: 'designs/app', application: { name: 'Møtedemo', url: 'http://localhost:32100/demo' } };
  let workspace, proposals;
  const open = create => {
    const stateDir = fs.mkdtempSync(join(projectDir, 'runtime-')); fs.chmodSync(stateDir, 0o700);
    workspace = new ApplicationWorkspace({ ...options, stateDir, ...(create ? { create: true } : {}) });
    proposals = new ApplicationProposals({ workspace, projectDir, backendFactory: createServerBackend, onSubmitted: (...value) => deliveries.push(value) });
  };
  try {
    open(true);
    const first = await proposals.publish({ source: 'conversation', title: 'Forslag', filename: 'first.html', html: '<h1>Første forslag</h1>' });
    const current = await proposals.action('readState', { proposalId: first.id });
    const input = { proposalId: first.id, workspacePath: 'designs/proposal', expectedScreen: current.screen, expectedRevision: current.revision };
    workspace.finishSketchSave = () => { throw new Error('Controlled binding failure'); };
    await assert.rejects(proposals.action('saveProposal', input), error => error.status === 503);
    const pending = structuredClone(workspace.feedback.state.workspace.pendingSketchSave);
    const target = join(projectDir, input.workspacePath, 'workspace.json'), child = fs.readFileSync(target);
    assert.equal(JSON.parse(child).workspace.id, pending.binding.workspaceId);
    await proposals.close(); workspace.close(); open(false);
    const parentBefore = fs.readFileSync(workspace.store.filename);
    const summary = await proposals.summary(); assert.equal(summary[0].id, first.id); assert.equal(summary[0].storage, 'temporary'); assert(summary[0].pendingSave);
    assert.deepEqual(fs.readFileSync(workspace.store.filename), parentBefore, 'A read never completes the pending binding.');
    assert.deepEqual(fs.readFileSync(target), child, 'Opening does not rewrite or recreate the saved child.');
    const saved = await proposals.action('saveProposal', input);
    assert.equal(saved.id, first.id); assert.equal(saved.storage, 'project'); assert.equal(saved.screen, first.screen);
    assert.equal(workspace.feedback.state.workspace.sketch.workspaceId, pending.binding.workspaceId);
    assert.equal(workspace.feedback.state.workspace.pendingSketchSave, undefined);
    assert.deepEqual(fs.readdirSync(join(projectDir, 'designs')), ['app', 'proposal']); assert.deepEqual(deliveries, []);
  } finally { await proposals?.close(); workspace?.close(); await rm(projectDir, { recursive: true, force: true }); }
});

test('a room survives repository formatting and Finder files, and one damaged older file stays local to its version', async () => {
  const projectDir = await mkdtemp(join(tmpdir(), 'visual-canvas-format-'));
  const options = { projectDir, workspacePath: 'designs/format' };
  const room = join(projectDir, 'designs/format'), revisions = join(room, 'revisions');
  const design = { version: 2, variants: [], targets: [], texts: [{ id: 'heading', label: 'Overskrift', value: 'Velg tidspunkt' }] };
  const html = '<h1><span data-vc-text="heading">Velg tidspunkt</span></h1>';
  let backend;
  try {
    backend = await createServerBackend({ ...options, create: true, title: 'Formatering' });
    const first = await backend.publishRevision({ expectedScreen: '', filename: 'first.html', html, design });
    await backend.publishRevision({ expectedScreen: first.screen, filename: 'second.html', html,
      design: { ...design, texts: [{ ...design.texts[0], value: 'Finn en tid' }] } });
    await backend.retire({}); backend = undefined;
    // What a staged-file formatter, an editor saving an old version and Finder leave behind.
    for (const filename of [join(room, 'workspace.json'), join(revisions, 'first.design.json'), join(revisions, 'second.design.json')]) {
      fs.writeFileSync(filename, `${JSON.stringify(JSON.parse(fs.readFileSync(filename, 'utf8')), null, 2)}\n`);
    }
    fs.appendFileSync(join(revisions, 'first.html'), '\n');
    for (const name of ['.DS_Store', '._first.html', 'first.html~']) fs.writeFileSync(join(revisions, name), 'x');
    backend = await createServerBackend(options);
    const state = await backend.readState({});
    assert.equal(state.workspace.version, 2);
    assert.equal(JSON.parse((await backend.readRevision({ revisionId: 2, part: 'design' })).content).texts[0].value, 'Finn en tid');
    const named = error => error.status === 409 && /first\.html no longer matches its saved hash/.test(error.message);
    await assert.rejects(backend.readRevision({ revisionId: 1, part: 'html' }), named);
    await assert.rejects(backend.restoreRevision({ revisionId: 1, expectedRevision: state.revision }), named);
    const view = await backend.openView({});
    const restore = await request(view, '/workspace/restore', 'POST', { revisionId: 1, expectedRevision: state.revision });
    assert.equal(restore.status, 409); assert.match(restore.value.error, /first\.html no longer matches its saved hash/);
    const third = await backend.publishRevision({ expectedScreen: state.screen, filename: 'third.html', html, design });
    assert.equal(third.workspace.version, 3);
  } finally { await backend?.retire({}); await rm(projectDir, { recursive: true, force: true }); }
});

test('startup names a damaged current file and a used directory without blaming another session', async () => {
  const projectDir = await mkdtemp(join(tmpdir(), 'visual-canvas-startup-'));
  const options = { projectDir, workspacePath: 'designs/startup' };
  let backend;
  try {
    backend = await createServerBackend({ ...options, create: true, title: 'Oppstart' });
    await backend.publishRevision({ expectedScreen: '', filename: 'current.html', html: '<h1>Gjeldende</h1>' });
    await backend.retire({}); backend = undefined;
    const current = join(projectDir, 'designs/startup/revisions/current.html');
    fs.appendFileSync(current, '\n');
    await assert.rejects(createServerBackend(options), error => error.status === 409 && /lagrede filen current\.html ikke stemmer med registeret/.test(error.message)
      && !/annen økt/.test(error.message));
    await assert.rejects(createServerBackend({ ...options, create: true, title: 'Ny' }), error => error.status === 409 && /ikke tom/.test(error.message)
      && !/annen økt/.test(error.message));
    fs.mkdirSync(join(projectDir, 'designs/empty'));
    await assert.rejects(createServerBackend({ projectDir, workspacePath: 'designs/empty' }), error => error.status === 404 && /finnes ikke/.test(error.message));
    fs.mkdirSync(join(projectDir, 'designs/unregistered/revisions'), { recursive: true });
    fs.writeFileSync(join(projectDir, 'designs/unregistered/revisions/first.html'), '<h1>Uten register</h1>');
    for (const create of [false, true]) {
      await assert.rejects(createServerBackend({ projectDir, workspacePath: 'designs/unregistered', ...(create ? { create, title: 'Uten register' } : {}) }),
        error => error.status === 409 && /mangler workspace\.json\. Ingen filer er endret\. Hent workspace\.json tilbake/.test(error.message));
    }
    assert.equal(fs.readFileSync(current, 'utf8'), '<h1>Gjeldende</h1>\n', 'A failed startup changes no project file.');
  } finally { await backend?.retire({}); await rm(projectDir, { recursive: true, force: true }); }
});

test('a post-commit directory sync failure still emits one round, and receipt retry cannot emit it twice', async t => {
  const projectDir = fs.realpathSync(await mkdtemp(join(tmpdir(), 'visual-canvas-committed-')));
  const { FeedbackStore, FeedbackMutationReceipts, FeedbackError } = feedbackApi;
  const { WorkspaceStore } = workspaceApi;
  const { WorkspaceState, validWorkspaceState } = workspaceStateApi;
  let workspace;
  try {
    workspace = new WorkspaceStore({ projectDir, workspacePath: 'designs/room', create: true, validateState: validWorkspaceState });
    const stateDir = join(projectDir, 'state'); fs.mkdirSync(stateDir, { mode: 0o700 });
    const feedback = new FeedbackStore(stateDir, { canvas: true, persistence: workspace,
      initialWorkspace: { id: 'a'.repeat(24), title: 'Arbeidsrom', version: 0, revisions: [] } });
    const state = new WorkspaceState(feedback, workspace, { path: 'designs/room' });
    state.publish({ expectedScreen: '', filename: 'first.html', html: '<h1>Første skisse</h1>' });
    feedback.create(note(state.current().screen));
    const events = [], responses = [], receipts = new FeedbackMutationReceipts();
    const source = fs.readFileSync(new URL('../../../skills/design-prototype/scripts/server.js', import.meta.url), 'utf8');
    const start = source.indexOf('function readFeedbackBody('), end = source.indexOf('\nconst server = http.createServer', start);
    assert(start >= 0 && end > start);
    const receive = runInNewContext(`${source.slice(start, end)}; readFeedbackBody`, {
      Buffer, Date, MAX_BODY_BYTES: 16 * 1024, FeedbackError, feedback, mutationReceipts: receipts,
      feedbackSnapshot: () => feedback.snapshot(), currentRequest: () => true, lastActivity: 0, canvasMode: true,
      canvasEvent: value => events.push(JSON.parse(JSON.stringify(value))),
      requestErrorStatus: error => error.status || 500,
      sendJson: (res, status, value) => { responses.push({ status, value }); res.writableEnded = true; },
    });
    const submit = (revision, mutationId) => {
      const req = new EventEmitter(); req.method = 'POST'; req.headers = { 'x-feedback-mutation': mutationId };
      const res = { writableEnded: false };
      receive(req, res, value => feedback.submit(value), '/comments/submit');
      req.emit('data', Buffer.from(JSON.stringify({ revision }))); req.emit('end');
      return responses.at(-1);
    };
    const fsync = fs.fsyncSync;
    let failDirectorySync = true;
    t.mock.method(fs, 'fsyncSync', function (fd) {
      if (failDirectorySync && fs.fstatSync(fd).isDirectory()) { failDirectorySync = false; throw new Error('Controlled post-rename sync failure.'); }
      return fsync(fd);
    });
    const revision = feedback.state.revision, mutationId = 'b'.repeat(32);
    assert.equal(submit(revision, mutationId).status, 500);
    assert.equal(feedback.state.submission, 1);
    assert.equal(JSON.parse(fs.readFileSync(workspace.filename, 'utf8')).submission, 1);
    assert.deepEqual(events, [{ event: 'submitted', submission: 1 }]);
    assert.equal(submit(revision, mutationId).status, 200);
    assert.deepEqual(events, [{ event: 'submitted', submission: 1 }]);
    assert.equal(feedback.state.submissions.length, 1);
    assert.equal(state.current().content, '<h1>Første skisse</h1>');
  } finally { workspace?.close(); await rm(projectDir, { recursive: true, force: true }); }
});

test('the HTTP editor preserves explicit fields, one save receipt and user-only constraint release', async () => {
  const projectDir = await mkdtemp(join(tmpdir(), 'visual-canvas-editor-'));
  const submitted = [];
  let backend;
  try {
    backend = await createServerBackend({ projectDir, workspacePath: 'designs/editor', create: true, onSubmitted: round => submitted.push(round) });
    const view = await backend.openView({});
    const design = { version: 2, texts: [{ id: 'heading', label: 'Heading', value: 'Første overskrift' }], variants: [], targets: [
      { key: 'card', variant: '', label: 'Card', controls: [
        { id: 'density', label: 'Density', type: 'select', initial: 'clear', editable: true,
          options: [{ value: 'clear', label: 'Clear' }, { value: 'compact', label: 'Compact' }] },
        { id: 'tone', label: 'Tone', type: 'select', initial: 'calm',
          options: [{ value: 'calm', label: 'Calm' }, { value: 'bright', label: 'Bright' }] },
      ] },
    ] };
    const html = '<h1><span data-vc-text="heading">Source heading</span></h1><section data-vc-key="card">Content</section>';
    const beforeRejected = await backend.readState({});
    const workspaceFile = join(projectDir, 'designs/editor/workspace.json');
    const beforeBytes = fs.readFileSync(workspaceFile);
    await assert.rejects(backend.publishRevision({ expectedScreen: '', filename: 'invalid-editor.html',
      html: html.replace('Source heading', '<b>PRIVATE_INVALID_SOURCE</b>'), design }),
    error => {
      assert.equal(error.status, 400);
      assert.match(error.message, /\[text-content\] texts\[0\],HTML offset 33 \(zero-based UTF-16\)/);
      assert.match(error.message, /text only, without nested tags or comments/);
      assert.doesNotMatch(error.message, /PRIVATE_INVALID_SOURCE|heading|invalid-editor|designs\/editor/);
      assert(Buffer.byteLength(error.message) <= 512);
      return true;
    });
    assert.deepEqual(await backend.readState({}), beforeRejected);
    assert.deepEqual(fs.readFileSync(workspaceFile), beforeBytes);
    assert.equal(fs.existsSync(join(projectDir, 'designs/editor/revisions/invalid-editor.html')), false);
    assert.deepEqual(submitted, []);
    const first = await backend.publishRevision({ expectedScreen: '', filename: 'editor-first.html', html, design });
    assert.equal(first.workspace.version, 1, 'The corrected first sketch creates only one revision.');
    const editor = await request(view, '/workspace/editor');
    assert.equal(editor.status, 200);
    assert.deepEqual(editor.value.fields.map(field => field.id), ['text:heading', 'control:/card/density']);
    assert.equal(editor.value.fields[0].value, 'Første overskrift');
    const changes = [{ id: 'text:heading', value: 'Min lagrede overskrift' }, { id: 'control:/card/density', value: 'compact' }];
    const saving = { screen: first.screen, expectedRevision: editor.value.revision, changes };
    for (const invalid of [{ ...saving, html: '<p>Replacement</p>' }, { ...saving, changes: [{ id: 'text:heading', value: {} }] },
      { ...saving, changes: [{ id: 'control:/card/density', value: 'outside-options' }] },
      { ...saving, changes: [{ id: 'control:/card/tone', value: 'bright' }] },
      { ...saving, changes: [changes[0], { id: 'missing', value: 'Not a declared field' }] }]) {
      assert.equal((await request(view, '/workspace/editor/save', 'POST', invalid)).status, 400);
    }
    const foreignUrl = new URL(view.url); foreignUrl.pathname = '/workspace/editor/save';
    const foreign = await fetch(foreignUrl, { method: 'POST', signal: AbortSignal.timeout(3000),
      headers: { Origin: 'https://unrelated.invalid', 'Content-Type': 'application/json' }, body: JSON.stringify(saving) });
    assert.equal(foreign.status, 403); await foreign.text();
    assert.equal((await backend.readState({})).workspace.version, 1, 'Rejected or partial edits cannot create a revision.');
    const mutationId = 'e'.repeat(32);
    const saved = await request(view, '/workspace/editor/save', 'POST', saving, mutationId);
    assert.equal(saved.status, 200); assert.equal(saved.value.workspace.version, 2);
    const replay = await request(view, '/workspace/editor/save', 'POST', saving, mutationId);
    assert.equal(replay.status, 200); assert.equal(replay.value.workspace.version, 2);
    assert.equal(replay.value.revision, saved.value.revision);
    assert.equal((await request(view, '/workspace/editor/save', 'POST', { ...saving, changes: [{ id: 'text:heading', value: 'Different intent' }] }, mutationId)).status, 409);
    assert.equal((await request(view, '/workspace/editor/save', 'POST', saving)).status, 409, 'An old request without its receipt must fail CAS.');
    const edited = await backend.readState({});
    const currentEditor = await request(view, '/workspace/editor');
    assert.equal(currentEditor.value.fields.every(field => field.locked), true);
    assert.equal(currentEditor.value.fields[0].value, changes[0].value);
    assert.equal(currentEditor.value.fields[1].value, 'compact');
    assert.equal((await backend.readRevision({ revisionId: 2, part: 'html' })).content,
      '<h1><span data-vc-text="heading">Min lagrede overskrift</span></h1><section data-vc-key="card" data-vc-setting-density="compact">Content</section>',
      'Saving writes only the declared text and editable setting into the HTML.');
    assert.deepEqual(JSON.parse((await backend.readRevision({ revisionId: 2, part: 'design' })).content).texts[0].value, changes[0].value);
    await assert.rejects(backend.publishRevision({ expectedScreen: edited.screen, filename: 'overwrite.html', html, design }),
      error => error.status === 409 && /manually saved field/.test(error.message));
    await assert.rejects(backend.restoreRevision({ revisionId: 1, expectedRevision: edited.revision }),
      error => error.status === 409 && /manually saved field/.test(error.message));
    const heldRestore = await request(view, '/workspace/restore', 'POST', { revisionId: 1, expectedRevision: edited.revision });
    assert.equal(heldRestore.status, 409); assert.equal(heldRestore.value.errorCode, 'editor-conflict');
    const release = { screen: edited.screen, expectedRevision: edited.revision, ids: changes.map(change => change.id) };
    assert.equal((await request(view, '/workspace/editor/release', 'POST', { ...release, expectedRevision: first.revision })).status, 409);
    assert.equal((await request(view, '/workspace/editor/release', 'POST', { ...release, force: true })).status, 400);
    const released = await request(view, '/workspace/editor/release', 'POST', release, 'f'.repeat(32));
    assert.equal(released.status, 200); assert.equal(released.value.workspace.version, 2);
    assert.deepEqual(released.value.workspace.preservedFields, []);
    assert.equal((await request(view, '/workspace/editor/save', 'POST', { screen: edited.screen, expectedRevision: edited.revision,
      changes: [{ id: 'text:heading', value: 'Late edit' }] })).status, 409);
    const restored = await backend.restoreRevision({ revisionId: 1, expectedRevision: released.value.revision });
    assert.equal(restored.workspace.version, 3); assert.notEqual(restored.screen, edited.screen);
    const restoredEditor = await request(view, '/workspace/editor');
    assert.equal(restoredEditor.value.fields[0].value, design.texts[0].value);
    assert.equal(restoredEditor.value.fields.every(field => !field.locked), true);
    assert.equal((await request(view, '/workspace/editor/release', 'POST', release)).status, 409, 'A late release cannot apply to the new screen.');
    assert.equal(backend.editorSave, undefined); assert.equal(backend.editorRelease, undefined);
    const adapter = createCanvasAdapter({ sessionId: 'editor-contract-owner', projectDir });
    assert.equal(adapter.canvas.actions.some(action => /editor/i.test(action.name)), false, 'The SDK has no editor mutation or release action.');
    await adapter.close();
    assert.equal(restored.submission, 0); assert.deepEqual(submitted, [], 'Save, retry, release and restore never submit feedback.');
  } finally { await backend?.retire({}); await rm(projectDir, { recursive: true, force: true }); }
});

test('a stored version is shown read-only through the token-protected preview, and viewing writes nothing', async () => {
  const projectDir = await mkdtemp(join(tmpdir(), 'visual-canvas-view-'));
  const options = { projectDir, workspacePath: 'designs/view' };
  const design = { version: 2, variants: [], targets: [], texts: [{ id: 'heading', label: 'Overskrift', value: 'Velg tidspunkt' }] };
  const html = '<h1><span data-vc-text="heading">Velg tidspunkt</span></h1><img src="x.png" onerror="alert(1)">';
  let backend;
  try {
    backend = await createServerBackend({ ...options, create: true, title: 'Visning' });
    const first = await backend.publishRevision({ expectedScreen: '', filename: 'first.html', html, design });
    await backend.publishRevision({ expectedScreen: first.screen, filename: 'second.html',
      html: '<h1><span data-vc-text="heading">Finn en tid</span></h1>', design: { ...design, texts: [{ ...design.texts[0], value: 'Finn en tid' }] } });
    const statePath = join(projectDir, 'designs/view/workspace.json'), before = fs.readFileSync(statePath);
    const view = await backend.openView({});
    const page = async (search, token = true) => {
      const url = new URL(view.url); url.pathname = '/preview';
      if (!token) url.searchParams.delete('token');
      for (const [key, value] of search) url.searchParams.append(key, value);
      const response = await fetch(url, { signal: AbortSignal.timeout(3000) });
      return { status: response.status, text: await response.text(), csp: response.headers.get('content-security-policy') || '' };
    };
    const old = await page([['revision', '1']]);
    assert.equal(old.status, 200);
    assert.match(old.text, /Velg tidspunkt/);
    assert.doesNotMatch(old.text, /Finn en tid/);
    assert.match(old.text, /window\.__grillmesterVisualCompanionView=\{"revisionId":1\};/);
    assert.ok(old.text.includes(`window.__grillmesterVisualCompanionScreen="${first.screen}";`));
    assert.doesNotMatch(old.text, /onerror/, 'The stored version is sanitized like the current sketch.');
    assert.match(old.csp, /script-src 'nonce-/);
    const current = await page([]);
    assert.match(current.text, /Finn en tid/);
    assert.match(current.text, /window\.__grillmesterVisualCompanionView=null;/);
    for (const search of [[['revision', '0']], [['revision', 'abc']], [['revision', '1'], ['revision', '2']]]) {
      const invalid = await page(search);
      assert.equal(invalid.status, 400, JSON.stringify(search));
      assert.match(invalid.text, /"unavailable":true/);
    }
    assert.equal((await page([['revision', '9']])).status, 404);
    assert.equal((await page([['revision', '1']], false)).status, 403, 'Viewing needs the session token.');
    fs.appendFileSync(join(projectDir, 'designs/view/revisions/first.html'), '\n');
    const damaged = await page([['revision', '1']]);
    assert.equal(damaged.status, 409);
    assert.match(damaged.text, /En lagret fil for denne versjonen er endret eller mangler/);
    assert.deepEqual(fs.readFileSync(statePath), before, 'Viewing never writes the room.');
  } finally { await backend?.retire({}); await rm(projectDir, { recursive: true, force: true }); }
});

const removedAppMethods = ['readSource', 'readSourceChanges', 'prepareSourceChange', 'applySourceChange', 'restoreSourceChange', 'abandonSourceChange', 'registerReference', 'listReferences'];
async function appControl(backend) {
  const opened = await backend.openView({}), html = await (await fetch(opened.url)).text();
  const config = JSON.parse(html.match(/window\.__designApplication\s*=\s*(\{.*?\});/s)[1]);
  const origin = new URL(opened.url).origin;
  const activation = await fetch(origin + '/renderer/activate', { method: 'POST', headers: { Origin: origin, 'Content-Type': 'application/json', 'X-Designverksted-Token': config.token }, body: '{}' });
  assert.equal(activation.status, 200);
  return { opened, async request(pathname, method = 'GET', value, mutationId) {
    const response = await fetch(origin + pathname, { method, signal: AbortSignal.timeout(3000),
      headers: { Origin: origin, 'Content-Type': 'application/json', 'X-Designverksted-Token': config.token,
        ...(mutationId ? { 'X-Feedback-Mutation': mutationId } : {}) }, ...(value ? { body: JSON.stringify(value) } : {}) });
    return { status: response.status, value: await response.json() };
  } };
}
function appNote(state) {
  return { screen: state.screen, kind: 'point', text: 'Er neste steg tydelig nok?',
    anchor: { path: 'button:nth-of-type(1)', role: 'button', rect: { x: 12, y: 40, width: 100, height: 40 }, viewport: { width: 375, height: 812 } },
    applicationContext: { route: state.application.route, target: { tag: 'button', role: 'button', name: 'Neste', text: 'Neste', path: 'button:nth-of-type(1)' },
      viewport: { width: 375, height: 812, scrollX: 0, scrollY: 0 } } };
}
async function withApp(run) {
  const upstream = http.createServer((_req, res) => { res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><title>Møtedemo</title><button>Neste</button>'); });
  await new Promise(resolve => upstream.listen(0, '127.0.0.1', resolve));
  try { await run({ name: 'Møtedemo', url: `http://127.0.0.1:${upstream.address().port}/demo?mode=mock` }); }
  finally { await new Promise(resolve => { upstream.close(resolve); upstream.closeAllConnections(); }); }
}

test('real temporary app feedback uses no project files and retains one round only within its native view lifetime', () => withApp(async application => {
  const projectDir = await mkdtemp(join(tmpdir(), 'visual-app-feedback-')); let backend;
  const submitted = [], original = 'export const heading = "Uendret";\n';
  try {
    fs.writeFileSync(join(projectDir, 'view.js'), original);
    backend = await createServerBackend({ projectDir, application, onSubmitted: round => submitted.push(round) });
    const initial = await backend.readState({});
    assert.equal(initial.workspace.storage, 'temporary'); assert.equal(initial.workspace.mode, 'feedback');
    assert.equal(initial.workspace.path, undefined); assert.equal(initial.workspace.version, undefined);
    for (const method of removedAppMethods) assert.equal(backend[method], undefined);
    for (const method of ['publishRevision', 'listHistory', 'readRevision', 'restoreRevision']) {
      await assert.rejects(backend[method]({}), error => error.status === 409 && /HTML/.test(error.message));
    }
    const control = await appControl(backend);
    const moved = await control.request('/view', 'POST', { route: '/demo/details?mode=mock', expectedCheckpoint: initial.application.checkpoint });
    assert.equal(moved.status, 200); assert.equal(moved.value.screens.length, 0);
    const created = await control.request('/comments', 'POST', appNote(moved.value), 'a'.repeat(32));
    assert.equal(created.status, 200); assert.equal(created.value.comments.length, 1); assert.equal(created.value.screens.length, 1);
    const repeated = await control.request('/comments', 'POST', appNote(moved.value), 'a'.repeat(32));
    assert.equal(repeated.status, 200); assert.equal(repeated.value.comments.length, 1);
    const sending = { revision: created.value.revision };
    assert.equal((await control.request('/submit', 'POST', sending, 'b'.repeat(32))).status, 200);
    assert.equal((await control.request('/submit', 'POST', sending, 'b'.repeat(32))).status, 200);
    await waitFor(() => submitted.length === 1); assert.deepEqual(submitted, [1]);
    await backend.reviewSubmission({ submission: 1, status: 'answered', reply: 'Innspillet er vurdert. Ingen kode er endret.' });
    const round = await backend.readSubmission({ submission: 1 });
    assert.equal(round.round.review, 'answered');
    assert.equal(round.items.find(item => item.type === 'comment').value.applicationContext.route, '/demo/details?mode=mock');
    assert.deepEqual(await backend.openView({}), control.opened, 'Focusing retains the same native view');
    await backend.closeView({});
    await assert.rejects(backend.openView({}), error => error.status === 410);
    await assert.rejects(control.request('/state'));
    assert.equal((await backend.readState({})).submission, 1);
    assert.deepEqual(fs.readdirSync(projectDir), ['view.js']); assert.equal(fs.readFileSync(join(projectDir, 'view.js'), 'utf8'), original);
    await backend.retire({}); backend = null;
    assert.deepEqual(fs.readdirSync(projectDir), ['view.js']);
  } finally { await backend?.retire({}); await rm(projectDir, { recursive: true, force: true }); }
}));

test('saved app feedback reopens from a copied checkout with a new descriptive name and no app history', () => withApp(async application => {
  const projectDir = await mkdtemp(join(tmpdir(), 'visual-saved-feedback-'));
  const nextProject = await mkdtemp(join(tmpdir(), 'visual-copied-feedback-')); let backend;
  try {
    const workspacePath = 'designs/meeting';
    backend = await createServerBackend({ projectDir, workspacePath, create: true, title: 'Møtevalg', application });
    const initial = await backend.readState({}), control = await appControl(backend);
    assert.equal(initial.workspace.storage, 'project');
    const created = await control.request('/comments', 'POST', appNote(initial), 'c'.repeat(32)); assert.equal(created.status, 200);
    assert.equal((await control.request('/submit', 'POST', { revision: created.value.revision }, 'd'.repeat(32))).status, 200);
    await backend.reviewSubmission({ submission: 1, status: 'answered', reply: 'Spørsmålet er avklart; ingen filendring.' });
    const originalRound = await backend.readSubmission({ submission: 1 });
    const room = join(projectDir, workspacePath), savedPath = join(room, 'workspace.json');
    const saved = fs.readFileSync(savedPath), parsed = JSON.parse(saved);
    assert.equal(parsed.workspace.mode, 'feedback');
    assert.deepEqual(Object.keys(parsed.workspace).sort(), ['checkpoint', 'id', 'mode', 'source', 'title']);
    assert.equal(parsed.workspace.source.projectIdentity, undefined);
    for (const name of ['revisions', 'changes', 'references']) assert.equal(fs.existsSync(join(room, name)), false);
    await backend.retire({}); backend = null;
    fs.cpSync(join(projectDir, 'designs'), join(nextProject, 'designs'), { recursive: true });
    const replayed = [];
    backend = await createServerBackend({ projectDir: nextProject, workspacePath, application: { ...application, name: 'Ny beskrivelse' }, onSubmitted: round => replayed.push(round) });
    const reopened = await backend.readState({});
    assert.equal(reopened.workspace.id, initial.workspace.id); assert.equal(reopened.workspace.recovered, true);
    assert.equal(reopened.application.name, 'Ny beskrivelse');
    const round = await backend.readSubmission({ submission: 1 });
    assert.equal(round.round.previousSession, true); assert.equal(round.round.reply, originalRound.round.reply);
    assert.deepEqual(round.items, originalRound.items); assert.deepEqual(replayed, []);
    assert.deepEqual(fs.readFileSync(join(nextProject, workspacePath, 'workspace.json')), saved, 'Opening and reading do not rewrite saved feedback.');
    await backend.retire({}); backend = null;
    await assert.rejects(createServerBackend({ projectDir: nextProject, workspacePath, application: { ...application, url: application.url.replace('/demo?', '/other?') } }), error => error.status === 409);
    assert.deepEqual(fs.readFileSync(join(nextProject, workspacePath, 'workspace.json')), saved);
  } finally { await backend?.retire({}); await rm(projectDir, { recursive: true, force: true }); await rm(nextProject, { recursive: true, force: true }); }
}));
