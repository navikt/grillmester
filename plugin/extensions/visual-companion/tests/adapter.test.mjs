import test from 'node:test';
import assert from 'node:assert/strict';
import { tmpdir } from 'node:os';
import { mkdtemp, mkdir, realpath, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { createCanvasAdapter, CANVAS_ID } from '../adapter.mjs';
import feedbackApi from '../../../skills/design-prototype/scripts/feedback-store.js';
import canvasApi from '../../../skills/design-prototype/scripts/canvas-state.js';

const tick = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve, reject; const promise = new Promise((done, fail) => { resolve = done; reject = fail; }); return { promise, resolve, reject }; };
function fixture({ sessionId = 'session-one', send = async () => 'message-one', sendTimeoutMs = 1000, factory } = {}) {
  const backends = [], sends = [];
  const backendFactory = factory || (async callbacks => {
    const calls = [], backend = { callbacks, calls, open: false, generation: 0 };
    for (const method of ['readState', 'readSubmission', 'publishRevision', 'publishProposal', 'saveProposal', 'reviewSubmission', 'updateComment', 'markDelivery', 'listHistory', 'readRevision', 'restoreRevision']) backend[method] = async input => { calls.push({ method, input }); return { method, input }; };
    backend.openView = async () => { backend.open = true; calls.push({ method: 'openView' }); return { url: `http://127.0.0.1:1234/?token=${++backend.generation}` }; };
    backend.closeView = async () => { backend.open = false; calls.push({ method: 'closeView' }); return { closed: true }; };
    backend.retire = async () => { backend.open = false; calls.push({ method: 'retire' }); callbacks.onExit(); };
    backends.push(backend); return backend;
  });
  const adapter = createCanvasAdapter({ sessionId, projectDir: tmpdir(), backendFactory, sendTimeoutMs });
  const session = { sessionId, capabilities: { ui: {} }, send: options => { sends.push(options); return send(options); } };
  const ctx = { sessionId, extensionId: 'project:visual-companion', canvasId: CANVAS_ID, instanceId: 'instance-one' };
  const action = (name, input = {}, overrides = {}) => adapter.canvas.actions.find(item => item.name === name).handler({ ...ctx, ...overrides, input });
  return { adapter, backends, sends, session, ctx, action };
}

test('registration is lazy and requires an exact joined session before opening', async () => {
  const f = fixture();
  assert.equal(f.backends.length, 0); assert.equal(f.sends.length, 0);
  await assert.rejects(f.adapter.canvas.open(f.ctx), /unavailable/);
  assert.throws(() => f.adapter.attachSession({ ...f.session, sessionId: 'another' }), /Invalid joined/);
  f.adapter.attachSession(f.session);
  assert.throws(() => f.adapter.attachSession(f.session), /Invalid joined/);
  await f.adapter.canvas.open(f.ctx);
  assert.equal(f.backends.length, 1); assert.equal(f.sends.length, 0);
  await f.adapter.close();
});

test('missing renderer flags permit bound open; explicit false and malformed flags veto it', async () => {
  const f = fixture(); f.adapter.attachSession(f.session);
  for (const value of [false, 'true', null]) await assert.rejects(f.adapter.canvas.open({ ...f.ctx, host: { capabilities: { canvases: value } } }), /support/);
  assert.equal(f.backends.length, 0);
  await f.adapter.canvas.open(f.ctx);
  f.session.capabilities.ui.canvases = false;
  await assert.rejects(f.adapter.canvas.open(f.ctx), /disabled/);
  await f.adapter.close();
});

test('session, provider and canvas ownership are checked on open, action and close', async () => {
  const f = fixture(); f.adapter.attachSession(f.session); await f.adapter.canvas.open(f.ctx);
  for (const override of [{ sessionId: 'other' }, { extensionId: 'other' }, { canvasId: 'other' }]) {
    await assert.rejects(f.adapter.canvas.open({ ...f.ctx, ...override }), /owner/i);
    await assert.rejects(f.action('read_state', {}, override), /owner/i);
    assert.throws(() => f.adapter.canvas.onClose({ ...f.ctx, ...override }), /owner/i);
  }
  await f.adapter.close();
  assert.throws(() => f.adapter.canvas.onClose({ ...f.ctx, extensionId: 'other' }), /owner/i);
  await f.adapter.canvas.onClose(f.ctx);
  await assert.rejects(f.action('read_state'), /closed|unknown/);
});

test('reopen retains one logical backend and four-instance capacity does not evict prior state', async () => {
  const f = fixture(); f.adapter.attachSession(f.session);
  const opened = await f.adapter.canvas.open(f.ctx);
  await f.adapter.canvas.onClose(f.ctx);
  const reopened = await f.adapter.canvas.open(f.ctx);
  assert.notEqual(opened.url, reopened.url); assert.equal(f.backends.length, 1);
  for (let index = 2; index <= 4; index++) await f.adapter.canvas.open({ ...f.ctx, instanceId: `instance-${index}` });
  await assert.rejects(f.adapter.canvas.open({ ...f.ctx, instanceId: 'instance-five' }), /capacity/);
  assert.equal(f.backends.length, 4);
  await f.adapter.close(); assert(f.backends.every(item => !item.open));
});

test('actions delegate to the same backend and cannot invoke delivery or change ownership', async () => {
  const f = fixture(); f.adapter.attachSession(f.session); await f.adapter.canvas.open(f.ctx);
  assert.deepEqual(f.adapter.canvas.actions.map(item => item.name), ['read_preview', 'read_state', 'read_submission', 'publish_proposal', 'save_proposal', 'publish_revision', 'review_submission', 'update_comment', 'list_history', 'read_revision', 'restore_revision']);
  await f.action('read_state');
  await f.action('read_submission', { submission: 1, offset: 32 });
  await f.action('publish_revision', { expectedScreen: '', filename: 'first.html', html: '<h1>First</h1>' });
  await f.action('review_submission', { submission: 1, status: 'working', reply: 'Reviewing.' });
  await f.action('update_comment', { id: 'a'.repeat(24), submission: 1, status: 'fixed', reply: 'Adjusted.' });
  await f.action('list_history', { after: 1, limit: 20 });
  await f.action('read_revision', { revisionId: 1, part: 'html', offset: 2048 });
  await f.action('restore_revision', { revisionId: 1, expectedRevision: 10 });
  await assert.rejects(f.action('read_state', { sessionId: 'another' }), /arguments/);
  assert.equal(f.sends.length, 0);
  assert.equal(f.backends[0].calls.filter(item => item.method === 'readSubmission')[0].input.offset, 32);
  assert.deepEqual(f.backends[0].calls.filter(item => item.method === 'restoreRevision')[0].input, { revisionId: 1, expectedRevision: 10 });
  for (const [name, input] of [['list_history', { workspacePath: 'other' }], ['read_revision', { revisionId: 1, part: 'html', sessionId: 'other' }], ['restore_revision', { revisionId: 1 }]]) await assert.rejects(f.action(name, input), /arguments/);
  await f.adapter.close();
});
test('saving a proposal requires its exact identity and guards without opening another canvas or sending', async () => {
  const f = fixture(); f.adapter.attachSession(f.session); await f.adapter.canvas.open(f.ctx);
  const input = { proposalId: 'a'.repeat(24), workspacePath: 'designs/proposal', expectedScreen: 'b'.repeat(32), expectedRevision: 4 };
  await f.action('save_proposal', input);
  assert.deepEqual(f.backends[0].calls.at(-1), { method: 'saveProposal', input });
  for (const key of Object.keys(input)) { const bad = { ...input }; delete bad[key]; await assert.rejects(f.action('save_proposal', bad), error => error.status === 400); }
  await assert.rejects(f.action('save_proposal', { ...input, url: 'http://localhost:4000' }), error => error.status === 400);
  assert.equal(f.backends.length, 1); assert.equal(f.sends.length, 0); await f.adapter.close();
});

test('workspace opening passes exact create intent once and cannot rebind a retained instance', async () => {
  const f = fixture(); f.adapter.attachSession(f.session);
  const input = { workspacePath: 'design/booking', create: true, title: 'Bestill time' };
  await f.adapter.canvas.open({ ...f.ctx, input });
  const backend = f.backends[0];
  assert.equal(backend.callbacks.workspacePath, input.workspacePath);
  assert.equal(backend.callbacks.create, true); assert.equal(backend.callbacks.title, input.title);
  await f.adapter.canvas.onClose(f.ctx);
  await f.adapter.canvas.open(f.ctx);
  await f.adapter.canvas.open({ ...f.ctx, input: { workspacePath: input.workspacePath } });
  assert.equal(f.backends.length, 1); assert.equal(f.sends.length, 0);
  for (const changed of [{ workspacePath: 'design/other' }, { ...input, title: 'Different title' }]) await assert.rejects(f.adapter.canvas.open({ ...f.ctx, input: changed }), /workspace.*changed/);
  await f.adapter.close();
});

test('the shared catalogue exposes feedback and HTML actions, never app source or reference authority', async () => {
  const f = fixture(); f.adapter.attachSession(f.session);
  await f.adapter.canvas.open({ ...f.ctx, input: { application: { name: 'Møtedemo', url: 'http://localhost:3000/demo' } } });
  const names = f.adapter.canvas.actions.map(item => item.name);
  for (const name of ['read_source', 'read_source_changes', 'prepare_source_change', 'apply_source_change', 'restore_source_change', 'abandon_source_change', 'register_reference', 'list_references']) assert(!names.includes(name));
  for (const name of ['publish_revision', 'list_history', 'read_revision', 'restore_revision']) {
    assert.match(f.adapter.canvas.actions.find(item => item.name === name).description, /HTML sketch only/);
  }
  await f.action('read_state'); await f.action('read_submission', { submission: 1 });
  await f.action('review_submission', { submission: 1, status: 'answered', reply: 'Vi har vurdert innspillet; kode er ikke endret.' });
  assert.equal(f.sends.length, 0); await f.adapter.close();
});

test('invalid workspace inputs fail before creating a preview or reading another location', async () => {
  const f = fixture(); f.adapter.attachSession(f.session);
  for (const input of [null, [], { create: true }, { title: 'Title' }, { workspacePath: '' },
    ...['/tmp/other', '../other', 'design/../other', './design/room', 'design//room', 'design/room/', 'C:/room', 'design\\room', 'design/\nroom', 'design/.hidden', 'design/node_modules', 'design/NODE_MODULES', 'design/AUX', 'a/'.repeat(8) + 'a', 'a'.repeat(65)].map(workspacePath => ({ workspacePath })),
    { workspacePath: 'design/room', create: 'true' }, { workspacePath: 'design/room', title: 'Unrequested rename' },
    { workspacePath: 'design/room', create: true, title: ' ' }, { workspacePath: 'design/room', create: true, title: 'a'.repeat(201) },
    { workspacePath: 'design/room', sessionId: 'other' }]) {
    await assert.rejects(f.adapter.canvas.open({ ...f.ctx, input }), error => error.status === 400);
  }
  assert.equal(f.backends.length, 0); assert.equal(f.sends.length, 0);
  await f.adapter.canvas.open(f.ctx);
  await assert.rejects(f.adapter.canvas.open({ ...f.ctx, input: { workspacePath: 'design/room', create: true } }), /workspace changed/);
  await f.adapter.close();
});

test('a saved running app retains its route and immutable binding while the same canvas stays open', async () => {
  const f = fixture(); f.adapter.attachSession(f.session);
  const input = { workspacePath: 'designs/meeting', create: true, title: 'Møteform', application: { name: 'Møtedemo', url: 'http://localhost:5173/dialogmote/demo?tema=mote%20form' } };
  await f.adapter.canvas.open({ ...f.ctx, input });
  assert.deepEqual(f.backends[0].callbacks.application, { name: 'Møtedemo', url: 'http://localhost:5173/dialogmote/demo?tema=mote+form' });
  await f.adapter.canvas.open(f.ctx);
  await f.adapter.canvas.open({ ...f.ctx, input });
  for (const application of [{ ...input.application, url: 'http://localhost:5174/dialogmote/demo' }, { ...input.application, name: 'Annen app' }])
    await assert.rejects(f.adapter.canvas.open({ ...f.ctx, input: { ...input, application } }), error => error.status === 409);
  await assert.rejects(f.adapter.canvas.open({ ...f.ctx, input: { styleProjectPath: '' } }), error => error.status === 409);
  assert.equal(f.backends.length, 1); assert.equal(f.sends.length, 0);
  await f.adapter.close();
});

test('app inputs cannot silently switch a sketch, escape loopback or mix style sources', async () => {
  const f = fixture(); f.adapter.attachSession(f.session);
  const application = { name: 'Demo', url: 'http://localhost:5173/demo' };
  for (const input of [{ application, create: true }, { application, title: 'No implicit save' }, { application, styleProjectPath: '' }, { workspacePath: 'designs/room', application, styleProjectPath: '' },
    ...['https://example.com/demo', 'http://localhost:5173/demo?token=private', 'http://name:secret@localhost:5173/demo'].map(url => ({ workspacePath: 'designs/room', application: { ...application, url } }))])
    await assert.rejects(f.adapter.canvas.open({ ...f.ctx, input }), error => error.status === 400);
  assert.equal(f.backends.length, 0);
  await f.adapter.canvas.open({ ...f.ctx, input: { workspacePath: 'designs/room' } });
  await assert.rejects(f.adapter.canvas.open({ ...f.ctx, input: { workspacePath: 'designs/room', application } }), error => error.status === 409);
  assert.equal(f.backends.length, 1);
  await f.adapter.close();
});

test('an explicit style subproject stays bound without changing the project or room location', async () => {
  const f = fixture(); f.adapter.attachSession(f.session);
  const input = { workspacePath: 'design/room', create: true, styleProjectPath: 'apps/frontend' };
  await f.adapter.canvas.open({ ...f.ctx, input });
  const original = f.backends[0].callbacks;
  assert.equal(original.workspacePath, 'design/room');
  assert.equal(original.styleProjectPath, 'apps/frontend');
  await f.adapter.canvas.onClose(f.ctx);
  await f.adapter.canvas.open(f.ctx);
  await f.adapter.canvas.open({ ...f.ctx, input: { styleProjectPath: 'apps/frontend' } });
  for (const styleProjectPath of ['', 'apps/other']) await assert.rejects(
    f.adapter.canvas.open({ ...f.ctx, input: { styleProjectPath } }), error => error.status === 409 && /style project changed/.test(error.message));
  assert.equal(f.backends.length, 1); assert.equal(f.sends.length, 0);
  await f.adapter.canvas.open({ ...f.ctx, instanceId: 'root-styles', input: { styleProjectPath: '' } });
  assert.equal(f.backends[1].callbacks.projectDir, original.projectDir);
  assert.equal(f.backends[1].callbacks.workspacePath, undefined);
  assert.equal(f.backends[1].callbacks.styleProjectPath, '');
  await f.adapter.canvas.open({ ...f.ctx, instanceId: 'root-styles' });
  await assert.rejects(f.adapter.canvas.open({ ...f.ctx, instanceId: 'root-styles', input: { styleProjectPath: 'apps/frontend' } }), /style project changed/);
  await f.adapter.close();
});

test('invalid style selectors fail before opening and an omitted selector retains legacy root styling', async () => {
  const f = fixture(); f.adapter.attachSession(f.session);
  for (const styleProjectPath of [null, true, 12, [], '/tmp/app', '../app', 'apps/../app', './app', '.',
    'apps//app', 'apps/app/', 'C:/app', 'apps\\app', '.hidden', 'node_modules', 'apps/AUX', 'a/'.repeat(8) + 'a', 'a'.repeat(65)]) {
    await assert.rejects(f.adapter.canvas.open({ ...f.ctx, input: { styleProjectPath } }), error => error.status === 400);
  }
  assert.equal(f.backends.length, 0);
  await f.adapter.canvas.open(f.ctx);
  await f.adapter.canvas.open({ ...f.ctx, input: { styleProjectPath: '' } });
  assert.equal(f.backends.length, 1); assert.equal(f.backends[0].callbacks.styleProjectPath, undefined);
  await f.adapter.close();
});

test('identical workspace paths in different host worktrees stay separately bound', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'visual-worktree-binding-'));
  const primary = join(directory, 'primary'), worktree = join(directory, 'worktree');
  await mkdir(primary); await mkdir(worktree);
  const f = fixture(); f.adapter.attachSession(f.session);
  try {
    const input = { workspacePath: 'design/room' };
    const one = { ...f.ctx, session: { workingDirectory: primary }, input };
    const two = { ...f.ctx, instanceId: 'instance-two', session: { workingDirectory: worktree }, input };
    await f.adapter.canvas.open(one); await f.adapter.canvas.open(two);
    assert.notEqual(f.backends[0].callbacks.projectDir, f.backends[1].callbacks.projectDir);
    assert.equal(f.backends[0].callbacks.workspacePath, f.backends[1].callbacks.workspacePath);
    await assert.rejects(f.adapter.canvas.open({ ...one, session: two.session }), /project changed/);
    await assert.rejects(f.action('restore_revision', { revisionId: 1, expectedRevision: 0 }, { session: two.session }), /project changed/);
    assert.equal(f.backends[0].calls.some(call => call.method === 'restoreRevision'), false);
  } finally { await f.adapter.close(); await rm(directory, { recursive: true, force: true }); }
});

test('a new session reopening the same workspace never synthesizes delivery from reads or restore', async () => {
  const one = fixture(), two = fixture({ sessionId: 'session-two' });
  const input = { workspacePath: 'design/room' };
  one.adapter.attachSession(one.session); two.adapter.attachSession(two.session);
  await one.adapter.canvas.open({ ...one.ctx, input });
  one.backends[0].callbacks.onSubmitted(1); await tick();
  await one.adapter.close();
  await two.adapter.canvas.open({ ...two.ctx, input });
  await two.action('read_state'); await two.action('list_history');
  await two.action('read_submission', { submission: 1 });
  await two.action('read_revision', { revisionId: 1, part: 'design' });
  await two.action('restore_revision', { revisionId: 1, expectedRevision: 10 });
  assert.equal(two.sends.length, 0);
  two.backends[0].callbacks.onSubmitted(2); await tick();
  assert.equal(two.sends.length, 1);
  assert.equal(JSON.parse(two.sends[0].prompt.split('\n').at(-1)).submission, 2);
  one.backends[0].callbacks.onSubmitted(3); await tick();
  assert.equal(one.sends.length, 1, 'Retired callbacks cannot deliver to the new session.');
  await two.adapter.close();
});

test('one committed round sends a bounded exact reference once, never content or automatic reviews', async () => {
  const ack = deferred(), f = fixture({ send: () => ack.promise });
  f.ctx.extensionId = '"'.repeat(200); f.ctx.instanceId = '\\'.repeat(200);
  f.adapter.attachSession(f.session); await f.adapter.canvas.open(f.ctx);
  const backend = f.backends[0];
  backend.callbacks.onSubmitted(200); backend.callbacks.onSubmitted(200);
  await tick(); assert.equal(f.sends.length, 1);
  assert.equal(f.sends[0].mode, 'enqueue'); assert.equal(f.sends[0].source, 'user');
  assert(Buffer.byteLength(f.sends[0].prompt.split('\n')[0]) < 2000);
  assert(Buffer.byteLength(f.sends[0].prompt) < 3000);
  assert.deepEqual(JSON.parse(f.sends[0].prompt.split('\n').at(-1)), { extensionId: f.ctx.extensionId, canvasId: CANVAS_ID, instanceId: f.ctx.instanceId, submission: 200 });
  assert.equal(backend.calls.some(item => item.method === 'markDelivery'), false);
  ack.resolve('accepted-message'); await tick();
  assert.deepEqual(backend.calls.filter(item => item.method === 'markDelivery').map(item => item.input), [{ submission: 200, status: 'queued' }]);
  assert.equal(backend.calls.some(item => item.method === 'reviewSubmission'), false);
  await f.adapter.close();
});

test('late queue receipts preserve early answers and expose live status without replaying work', async () => {
  const directory = await realpath(await mkdtemp(join(tmpdir(), 'visual-queued-rounds-')));
  const store = new feedbackApi.FeedbackStore(directory, { canvas: true });
  const canvas = new canvasApi.CanvasState(store), screen = 'a'.repeat(32);
  store.knowScreen(screen, 'meeting.html');
  const acknowledgements = [deferred(), deferred()];
  let callbacks, sent = 0;
  const f = fixture({ send: () => acknowledgements[sent++].promise, factory: async options => {
    callbacks = options;
    return {
      openView: async () => ({ url: 'http://127.0.0.1:1234/' }),
      readState: async () => canvas.summary(),
      readSubmission: async input => canvas.read(input),
      reviewSubmission: async input => canvas.review(input),
      updateComment: async input => canvas.updateComment(input),
      markDelivery: async input => canvas.delivery(input),
      retire: async () => options.onExit(),
    };
  } });
  try {
    f.adapter.attachSession(f.session); await f.adapter.canvas.open(f.ctx);
    const submit = text => {
      store.create({ screen, kind: 'point', text,
        anchor: { path: 'h1:nth-of-type(1)', role: 'heading', rect: { x: 0, y: 0, width: 120, height: 40 }, viewport: { width: 390, height: 844 } } });
      store.submit({}); callbacks.onSubmitted(store.state.submission);
    };
    submit('Behold overskriften.'); await tick();
    await f.action('review_submission', { submission: 1, status: 'working', reply: 'Vurderer bekreftelsen.' });
    await f.action('review_submission', { submission: 1, status: 'answered', reply: 'Overskriften beholdes.' });
    submit('Behold også den kompakte visningen.'); await tick();
    await f.action('review_submission', { submission: 2, status: 'working', reply: 'Vurderer visningen.' });
    await f.action('review_submission', { submission: 2, status: 'answered', reply: 'Kompakt visning beholdes.' });
    const immutable = JSON.stringify(store.state.submissions);
    const answers = store.state.canvas.rounds.map(({ review, reply }) => ({ review, reply }));

    // Host acknowledgements may arrive after another explicit instruction has
    // already caused the owning conversation to handle the exact rounds.
    acknowledgements[1].resolve('second-receipt'); await tick();
    acknowledgements[0].resolve('first-receipt'); await tick();
    assert.deepEqual(store.state.canvas.rounds.map(({ review, reply }) => ({ review, reply })), answers);
    assert.deepEqual(store.state.canvas.rounds.map(round => round.delivery), ['queued', 'queued']);
    callbacks.onSubmitted(2); callbacks.onSubmitted(1); await tick();
    assert.equal(f.sends.length, 2, 'Late receipts and duplicate callbacks cannot deliver either round again.');

    const revision = store.state.revision;
    // When the host later consumes either original notice, its exact reference
    // resolves to the live answer rather than to unread status at send time.
    for (const message of f.sends) {
      const { submission } = JSON.parse(message.prompt.split('\n').at(-1));
      const page = await f.action('read_submission', { submission });
      assert.equal(page.round.review, 'answered');
      assert.equal(page.round.reply, answers[submission - 1].reply);
      assert.equal(page.items.find(item => item.type === 'comment').current.status, 'open', 'An answered round does not imply a fixed comment.');
      await assert.rejects(f.action('review_submission', { submission, status: 'working', reply: 'Starter på nytt.' }), error => error.status === 409);
      await f.action('review_submission', { submission, status: 'answered', reply: page.round.reply });
    }
    assert.equal(store.state.revision, revision, 'Reads, rejected restarts and identical answers leave saved state unchanged.');

    // A stale notification is not permission to repeat the work, but the API
    // must still allow a later deliberate clarification of an existing reply.
    await f.action('review_submission', { submission: 2, status: 'answered', reply: 'Kompakt visning beholdes; mobilvisningen vurderes i neste runde.' });
    assert.equal(store.state.revision, revision + 1);
    assert.equal((await f.action('read_submission', { submission: 2 })).round.reply, 'Kompakt visning beholdes; mobilvisningen vurderes i neste runde.');
    assert.equal(JSON.stringify(store.state.submissions), immutable);
    assert.equal(f.sends.length, 2);
  } finally { await f.adapter.close(); await rm(directory, { recursive: true, force: true }); }
});

test('rejected or missing acknowledgements remain unknown and are never resent', async () => {
  for (const send of [async () => { throw new Error('Rejected'); }, async () => undefined]) {
    const f = fixture({ send }); f.adapter.attachSession(f.session); await f.adapter.canvas.open(f.ctx);
    f.backends[0].callbacks.onSubmitted(1); await tick();
    assert.deepEqual(f.backends[0].calls.filter(item => item.method === 'markDelivery').map(item => item.input), [{ submission: 1, status: 'unknown' }]);
    f.backends[0].callbacks.onSubmitted(1); await tick(); assert.equal(f.sends.length, 1);
    await f.adapter.close();
  }
});

test('a timeout becomes unknown and a late acknowledgement only reconciles that same round', async () => {
  const ack = deferred(), f = fixture({ send: () => ack.promise, sendTimeoutMs: 15 });
  f.adapter.attachSession(f.session); await f.adapter.canvas.open(f.ctx);
  f.backends[0].callbacks.onSubmitted(1);
  await new Promise(resolve => setTimeout(resolve, 40));
  assert.equal(f.backends[0].calls.at(-1).input.status, 'unknown');
  ack.resolve('late-ack'); await tick();
  assert.equal(f.backends[0].calls.at(-1).input.status, 'queued'); assert.equal(f.sends.length, 1);
  await f.adapter.close();
});

test('closing a view during delivery does not cancel the retained round or send again on reopen', async () => {
  const ack = deferred(), f = fixture({ send: () => ack.promise });
  f.adapter.attachSession(f.session); await f.adapter.canvas.open(f.ctx);
  f.backends[0].callbacks.onSubmitted(1); await tick();
  await f.adapter.canvas.onClose(f.ctx); ack.resolve('accepted-after-close'); await tick();
  assert.equal(f.backends[0].calls.at(-1).input.status, 'queued');
  await f.adapter.canvas.open(f.ctx); assert.equal(f.sends.length, 1);
  await f.adapter.close();
});

test('close-open-close cancels an opening view and leaves no transport open', async () => {
  const f = fixture(); f.adapter.attachSession(f.session); await f.adapter.canvas.open(f.ctx);
  await f.adapter.canvas.onClose(f.ctx);
  const gate = deferred(), backend = f.backends[0], original = backend.openView;
  backend.openView = async () => { await gate.promise; return original(); };
  const opening = f.adapter.canvas.open(f.ctx); await tick();
  const rejection = assert.rejects(opening, /closed after/);
  const closing = f.adapter.canvas.onClose(f.ctx);
  gate.resolve(); await rejection; await closing;
  assert.equal(backend.open, false);
  await f.adapter.close();
});

test('shutdown during lazy startup retires its child without opening it', async () => {
  const gate = deferred(); let retired = false, opens = 0;
  const f = fixture({ factory: () => gate.promise }); f.adapter.attachSession(f.session);
  const opening = f.adapter.canvas.open(f.ctx), rejected = assert.rejects(opening, /closed/);
  await tick(); const closing = f.adapter.close();
  gate.resolve({ openView: async () => { opens++; }, retire: async () => { retired = true; } });
  await rejected; await closing; assert.equal(opens, 0); assert.equal(retired, true);
});

test('backend exit and failed startup retire the identity instead of silently replacing its artifact', async () => {
  const f = fixture(); f.adapter.attachSession(f.session); await f.adapter.canvas.open(f.ctx);
  f.backends[0].callbacks.onExit();
  await assert.rejects(f.adapter.canvas.open(f.ctx), /expired/);
  await assert.rejects(f.action('read_state'), /closed|unknown/); await f.adapter.close();
  const failed = fixture({ factory: async () => { throw new Error('startup failed'); } }); failed.adapter.attachSession(failed.session);
  await assert.rejects(failed.adapter.canvas.open(failed.ctx), /startup failed/);
  await assert.rejects(failed.adapter.canvas.open(failed.ctx), /expired/); await failed.adapter.close();
});

test('an explicit open retries a fully stopped never-ready failure with the exact original binding', async () => {
  const starts = [], callbacks = [];
  let active = false;
  const f = fixture({ factory: async options => {
    starts.push(options); callbacks.push(options);
    if (starts.length === 1) {
      options.onExit();
      throw Object.assign(new Error('Workspace is already open.'), { status: 409, backendStopped: true, backendWasReady: false });
    }
    return {
      openView: async () => { active = true; return { url: 'http://127.0.0.1:1234/' }; },
      closeView: async () => { active = false; },
      readState: async () => ({ workspace: { path: options.workspacePath } }),
      retire: async () => { active = false; options.onExit(); },
    };
  } });
  f.adapter.attachSession(f.session);
  const input = { workspacePath: 'design/room', create: true, title: 'Arbeidsrom' };
  await assert.rejects(f.adapter.canvas.open({ ...f.ctx, input }), error => error.status === 409);
  await tick(); assert.equal(starts.length, 1, 'There is no automatic retry.');
  await assert.rejects(f.adapter.canvas.open({ ...f.ctx, input: { workspacePath: 'design/other' } }), /workspace changed/);
  await assert.rejects(f.adapter.canvas.open({ ...f.ctx, input: { workspacePath: input.workspacePath, create: false } }), /intent changed/);
  await f.adapter.canvas.onClose(f.ctx);
  await f.adapter.canvas.open(f.ctx);
  assert.equal(starts.length, 2); assert.equal(active, true);
  for (const property of ['projectDir', 'workspacePath', 'create', 'title']) assert.equal(starts[1][property], starts[0][property]);
  callbacks[0].onExit(); callbacks[0].onSubmitted(1); await tick();
  assert.equal(f.sends.length, 0, 'Retired startup callbacks cannot affect the successful retry.');
  assert.equal((await f.action('read_state')).workspace.path, input.workspacePath);
  await f.adapter.close(); assert.equal(active, false);
});

test('startup retry requires stopped proof and never-ready proof, and is forbidden after a submitted event', async () => {
  for (const flags of [{}, { backendStopped: true, backendWasReady: true }, { backendStopped: false, backendWasReady: false }, { backendStopped: true, backendWasReady: false, submitted: true }]) {
    let starts = 0;
    const f = fixture({ factory: async options => {
      starts++;
      if (flags.submitted) options.onSubmitted(1);
      options.onExit();
      throw Object.assign(new Error('Failed startup.'), flags);
    } });
    f.adapter.attachSession(f.session);
    await assert.rejects(f.adapter.canvas.open({ ...f.ctx, input: { workspacePath: 'design/room' } }), /Failed startup/);
    await assert.rejects(f.adapter.canvas.open(f.ctx), /expired/);
    assert.equal(starts, 1); assert.equal(f.sends.length, 0);
    await f.adapter.close();
  }
});

test('closing the adapter after a retryable startup failure needs no replacement process', async () => {
  let starts = 0;
  const f = fixture({ factory: async options => {
    starts++; options.onExit();
    throw Object.assign(new Error('Workspace is busy.'), { backendStopped: true, backendWasReady: false });
  } });
  f.adapter.attachSession(f.session);
  await assert.rejects(f.adapter.canvas.open({ ...f.ctx, input: { workspacePath: 'design/room' } }), /busy/);
  await f.adapter.close(); assert.equal(starts, 1);
  await assert.rejects(f.adapter.canvas.open(f.ctx), /unavailable/);
});

test('two sessions and two instances route each committed round only to their owner', async () => {
  const one = fixture(), two = fixture({ sessionId: 'session-two' });
  one.adapter.attachSession(one.session); two.adapter.attachSession(two.session);
  await one.adapter.canvas.open(one.ctx); await one.adapter.canvas.open({ ...one.ctx, instanceId: 'instance-two' });
  await two.adapter.canvas.open(two.ctx);
  one.backends[1].callbacks.onSubmitted(2); two.backends[0].callbacks.onSubmitted(1); await tick();
  assert.equal(one.sends.length, 1); assert.equal(two.sends.length, 1);
  assert.equal(JSON.parse(one.sends[0].prompt.split('\n').at(-1)).instanceId, 'instance-two');
  assert.equal(JSON.parse(two.sends[0].prompt.split('\n').at(-1)).instanceId, 'instance-one');
  await assert.rejects(one.action('read_state', {}, two.ctx), /ownership/);
  await one.adapter.close(); await two.adapter.close();
});

test('temporary app feedback retains its own binding without creating or silently saving a workspace', async () => {
  const f = fixture(); f.adapter.attachSession(f.session);
  const input = { application: { name: 'Møtedemo', url: 'http://localhost:3000/demo?mode=mock' } };
  await f.adapter.canvas.open({ ...f.ctx, input });
  assert.deepEqual(f.backends[0].callbacks.application, input.application);
  for (const key of ['workspacePath', 'create', 'title', 'styleProjectPath']) assert.equal(Object.hasOwn(f.backends[0].callbacks, key), false);
  await f.adapter.canvas.open(f.ctx);
  await f.adapter.canvas.open({ ...f.ctx, input });
  assert.equal(f.backends.length, 1);
  await assert.rejects(f.adapter.canvas.open({ ...f.ctx, input: { workspacePath: 'designs/app', create: true } }), /workspace changed/);
  await assert.rejects(f.adapter.canvas.open({ ...f.ctx, input: { application: { ...input.application, url: 'http://localhost:3001/demo' } } }), /application changed/);
  f.backends[0].callbacks.onSubmitted(1); await tick();
  assert.equal(f.sends.length, 1);
  assert.match(f.sends[0].prompt, /App feedback does not authorize code writes/);
  assert.match(f.sends[0].prompt, /separately agreed code work happens outside this canvas/);
  assert.match(f.sends[0].prompt, /publish_proposal in this same workshop preserves full-page context/);
  assert.match(f.sends[0].prompt, /Honor review-only\/no-HTML limits; questions or observations alone do not request a sketch/);
  assert.match(f.sends[0].prompt, /An explicit request to save the workshop\/design work includes its proposal in the agreed design area; reuse that choice/);
  assert.match(f.sends[0].prompt, /Feedback-only saving or an already saved app does not/);
  assert.match(f.sends[0].prompt, /Otherwise keep this follow-up temporary and say so/);
  assert.match(f.sends[0].prompt, /Answered is not implemented/);
  assert.match(f.sends[0].prompt, /Never invent an artifact or link/);
  assert.doesNotMatch(f.sends[0].prompt, /make only the agreed bounded source change/);
  assert(Buffer.byteLength(f.sends[0].prompt) < 2000);
  await f.adapter.close();
});

test('app and proposal rounds share one owning canvas but keep exact separate delivery identities', async () => {
  const f = fixture(); f.adapter.attachSession(f.session);
  await f.adapter.canvas.open({ ...f.ctx, input: { application: { name: 'Demo', url: 'http://localhost:3000/demo' } } });
  const proposalId = 'c'.repeat(24), backend = f.backends[0];
  backend.callbacks.onSubmitted(1); backend.callbacks.onSubmitted(1, proposalId);
  backend.callbacks.onSubmitted(1, proposalId); backend.callbacks.onSubmitted(1, 'bad');
  await tick(); assert.equal(f.sends.length, 2); assert.equal(f.backends.length, 1);
  const refs = f.sends.map(message => JSON.parse(message.prompt.split('\n').at(-1)));
  assert.equal(refs[0].proposalId, undefined); assert.equal(refs[1].proposalId, proposalId);
  assert.equal(refs[0].instanceId, refs[1].instanceId);
  assert.deepEqual(backend.calls.filter(call => call.method === 'markDelivery').map(call => call.input.proposalId), [undefined, proposalId]);
  await f.action('read_submission', { proposalId, submission: 1 });
  await f.action('review_submission', { proposalId, submission: 1, status: 'answered', reply: 'Forslaget er klart.' });
  assert.equal(backend.calls.at(-1).input.proposalId, proposalId);
  await assert.rejects(f.action('read_state', { proposalId: 'bad' }), error => error.status === 400);
  await f.adapter.close();
});

test('publishing a proposal is a bounded action on the app instance without another canvas', async () => {
  const f = fixture(); f.adapter.attachSession(f.session);
  await f.adapter.canvas.open({ ...f.ctx, input: { application: { name: 'Demo', url: 'http://localhost:3000/demo' } } });
  const input = { sourceSubmission: 1, commentIds: ['a'.repeat(24)], title: 'Tydelig neste steg', filename: 'next-step.html', html: '<h1>Neste steg</h1>' };
  await f.action('publish_proposal', input);
  assert.deepEqual(f.backends[0].calls.at(-1), { method: 'publishProposal', input });
  assert.equal(f.backends.length, 1); assert.equal(f.sends.length, 0);
  const chat = { source: 'conversation', title: 'Tydelig neste steg', filename: 'next-step.html', html: '<h1>Neste steg</h1>' };
  await f.action('publish_proposal', chat);
  assert.deepEqual(f.backends[0].calls.at(-1), { method: 'publishProposal', input: chat });
  await assert.rejects(f.action('publish_proposal', { ...input, url: 'http://localhost:4000' }), error => error.status === 400);
  await f.adapter.close();
});


test('native app focus reuses one renderer and close revokes actions before queued retirement', async () => {
  const f = fixture(); f.adapter.attachSession(f.session);
  const input = { application: { name: 'Demo', url: 'http://localhost:5173/demo' } };
  const opened = await f.adapter.canvas.open({ ...f.ctx, input });
  assert.deepEqual(await f.adapter.canvas.open(f.ctx), opened);
  assert.equal(f.backends[0].calls.filter(item => item.method === 'openView').length, 1);
  const gate = deferred(), backend = f.backends[0], original = backend.retire;
  backend.retire = async () => { await gate.promise; return original(); };
  const closing = f.adapter.canvas.onClose(f.ctx);
  await assert.rejects(f.action('read_state'), /closed|unknown/);
  await assert.rejects(f.adapter.canvas.open(f.ctx), /expired/);
  assert.throws(() => f.adapter.canvas.onClose({ ...f.ctx, extensionId: 'other' }), /owner/i);
  backend.callbacks.onSubmitted(1); await tick();
  assert.equal(f.sends.length, 0);
  assert.equal(backend.open, false, 'Renderer revocation does not wait for retirement');
  let shutdownDone = false; const shutdown = f.adapter.close().then(() => { shutdownDone = true; });
  await tick(); assert.equal(shutdownDone, false, 'Session shutdown waits for outstanding app retirement');
  gate.resolve(); await closing; await shutdown;
  assert.equal(backend.calls.filter(item => item.method === 'retire').length, 1);
});

test('native close during a pending open requests renderer revocation before waiting for open', async () => {
  const gate = deferred(), opened = deferred(), calls = [];
  const f = fixture({ factory: async callbacks => ({
    openView: async () => { calls.push('open'); opened.resolve(); await gate.promise; return { url: 'http://127.0.0.1:1234/browser/private' }; },
    closeView: async () => { calls.push('revoke'); },
    retire: async () => { calls.push('retire'); callbacks.onExit(); },
  }) });
  f.adapter.attachSession(f.session);
  const opening = f.adapter.canvas.open({ ...f.ctx, input: { application: { name: 'Demo', url: 'http://localhost:5173/' } } });
  const rejected = assert.rejects(opening, /closed after/); await opened.promise;
  const closing = f.adapter.canvas.onClose(f.ctx); await tick();
  assert.deepEqual(calls, ['open', 'revoke']);
  await assert.rejects(f.action('read_state'), /closed|unknown/);
  gate.resolve(); await rejected; await closing;
  assert.deepEqual(calls, ['open', 'revoke', 'retire']);
  await assert.rejects(f.adapter.canvas.open(f.ctx), /expired/);
  await f.adapter.close();
});

test('native close during backend startup retires the exact backend without opening a renderer', async () => {
  const gate = deferred(), calls = [];
  const f = fixture({ factory: () => gate.promise }); f.adapter.attachSession(f.session);
  const opening = f.adapter.canvas.open({ ...f.ctx, input: { application: { name: 'Demo', url: 'http://localhost:5173/' } } });
  const rejected = assert.rejects(opening, /closed after/); await tick();
  const closing = f.adapter.canvas.onClose(f.ctx);
  await assert.rejects(f.adapter.canvas.open(f.ctx), /expired/);
  gate.resolve({ openView: async () => { calls.push('open'); }, closeView: async () => { calls.push('revoke'); }, retire: async () => { calls.push('retire'); } });
  await rejected; await closing;
  assert.deepEqual(calls, ['revoke', 'retire']);
  await f.adapter.close();
});

test('native app backend loss and a never-ready app failure require a fresh instance', async () => {
  const f = fixture(); f.adapter.attachSession(f.session);
  const input = { application: { name: 'Demo', url: 'http://localhost:5173/demo' } };
  await f.adapter.canvas.open({ ...f.ctx, input });
  f.backends[0].callbacks.onExit();
  await assert.rejects(f.adapter.canvas.open(f.ctx), /expired/);
  await assert.rejects(f.action('read_state'), /closed|unknown/);
  await f.adapter.close();
  let starts = 0;
  const failed = fixture({ factory: async () => { starts++; throw Object.assign(new Error('Stopped before ready'), { backendStopped: true, backendWasReady: false }); } });
  failed.adapter.attachSession(failed.session);
  await assert.rejects(failed.adapter.canvas.open({ ...failed.ctx, input }), /Stopped before ready/);
  await assert.rejects(failed.adapter.canvas.open(failed.ctx), /expired/);
  assert.equal(starts, 1); await failed.adapter.close();
});

test('a fresh native identity opens the saved room binding without replaying old delivery', async () => {
  const ack = deferred(), f = fixture({ send: () => ack.promise }); f.adapter.attachSession(f.session);
  const application = { name: 'Demo', url: 'http://localhost:5173/demo' };
  await f.adapter.canvas.open({ ...f.ctx, input: { application, workspacePath: 'designs/meeting', create: true, title: 'Meeting' } });
  const old = f.backends[0]; old.callbacks.onSubmitted(1); await tick();
  await f.adapter.canvas.onClose(f.ctx);
  ack.resolve('old-ack'); await tick();
  assert.equal(old.calls.filter(item => item.method === 'markDelivery').length, 0, 'Late delivery acknowledgement cannot mutate a retired backend');
  await f.adapter.canvas.open({ ...f.ctx, instanceId: 'fresh-app', input: { application, workspacePath: 'designs/meeting' } });
  assert.equal(f.backends.length, 2);
  assert.equal(f.backends[1].callbacks.workspacePath, 'designs/meeting');
  assert.equal(f.backends[1].callbacks.create, undefined);
  old.callbacks.onSubmitted(1); old.callbacks.onSubmitted(2); await tick();
  assert.equal(f.sends.length, 1, 'Opening saved work does not resend prior rounds');
  await assert.rejects(f.adapter.canvas.open(f.ctx), /expired/);
  await f.adapter.close();
});
