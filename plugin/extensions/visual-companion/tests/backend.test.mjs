import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import fs from 'node:fs';
import { EventEmitter } from 'node:events';
import { runInNewContext } from 'node:vm';
import { createServerBackend } from '../backend.mjs';
import { createCanvasAdapter } from '../adapter.mjs';
import feedbackApi from '../../../skills/design-prototype/scripts/feedback-store.js';
import workspaceApi from '../../../skills/design-prototype/scripts/workspace-store.js';
import workspaceStateApi from '../../../skills/design-prototype/scripts/workspace-state.js';

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
    await assert.rejects(createServerBackend(options), error => error.status === 409 && error.backendStopped === true && error.backendWasReady === false);
    assert.equal((await owner.readState({})).workspace.id, original.workspace.id);
    await owner.retire({}); owner = undefined;
    next = await createServerBackend(options);
    assert.equal((await next.readState({})).workspace.id, original.workspace.id);
  } finally { await owner?.retire({}); await next?.retire({}); await rm(projectDir, { recursive: true, force: true }); }
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
      feedbackSnapshot: () => feedback.snapshot(), lastActivity: 0, canvasMode: true,
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
    assert.equal((await backend.readRevision({ revisionId: 2, part: 'html' })).content, html, 'Saving fields never rewrites arbitrary HTML.');
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
