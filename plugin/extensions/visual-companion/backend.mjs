import { fork } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { previewEnvironment, resolveNodeRuntime } from './runtime.mjs';
import applicationContract from '../../skills/design-prototype/scripts/application-contract.js';

const serverPath = fileURLToPath(new URL('../../skills/design-prototype/scripts/server.js', import.meta.url));
const applicationServerPath = fileURLToPath(new URL('../../skills/design-prototype/scripts/application-server.js', import.meta.url));
const channel = 'visual-companion-canvas';
const methods = ['openView', 'closeView', 'readState', 'readPreview', 'readSubmission', 'publishRevision', 'publishProposal', 'saveProposal', 'saveWorkspace', 'reviewSubmission', 'updateComment', 'markDelivery', 'listHistory', 'readRevision', 'restoreRevision', 'retire'];
const closedKeys = (value, required, optional = []) => value && typeof value === 'object' && !Array.isArray(value)
  && required.every(key => Object.hasOwn(value, key)) && Object.keys(value).every(key => required.includes(key) || optional.includes(key));
const failure = message => Object.assign(new Error(message), { status: 503 });

export function workspaceOptions(value = {}) {
  const invalid = () => Object.assign(new Error('Invalid project workspace options.'), { status: 400 });
  if (!closedKeys(value, [], ['workspacePath', 'create', 'title', 'styleProjectPath', 'application'])) throw invalid();
  const relativeDirectory = path => typeof path === 'string' && path.length > 0 && Buffer.byteLength(path) <= 240
    && path.split('/').length <= 8 && path.split('/').every(part => /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(part)
      && !/^(?:node_modules|__pycache__|con|prn|aux|nul|com[1-9]|lpt[1-9])$/i.test(part));
  const styles = {};
  const source = {};
  if (Object.hasOwn(value, 'application')) {
    if (Object.hasOwn(value, 'styleProjectPath')) throw invalid();
    const parsed = applicationContract.parseApplication(value.application);
    source.application = { name: parsed.name, url: parsed.url, ...(parsed.resourceQueryKeys ? { resourceQueryKeys: parsed.resourceQueryKeys } : {}) };
  }
  if (Object.hasOwn(value, 'styleProjectPath')) {
    if (value.styleProjectPath !== '' && !relativeDirectory(value.styleProjectPath)) throw invalid();
    styles.styleProjectPath = value.styleProjectPath;
  }
  if (!Object.hasOwn(value, 'workspacePath')) {
    if (Object.hasOwn(value, 'create') || Object.hasOwn(value, 'title')) throw Object.assign(new Error('For a temporary workshop, omit create and title. Use application.name to name a running app. Supply workspacePath only when saving was requested.'), { status: 400 });
    return { ...styles, ...source };
  }
  const { workspacePath, create, title } = value;
  if (!relativeDirectory(workspacePath)
      || (Object.hasOwn(value, 'create') && typeof create !== 'boolean')
      || (Object.hasOwn(value, 'title') && (create !== true || typeof title !== 'string' || !title.trim()
        || Buffer.byteLength(title) > 200 || /[\u0000-\u001f\u007f]/.test(title)))) throw invalid();
  return { workspacePath, ...(Object.hasOwn(value, 'create') ? { create } : {}), ...(Object.hasOwn(value, 'title') ? { title } : {}), ...styles, ...source };
}

// One child owns the existing HTTP server and FeedbackStore. This client never
// reads or rewrites its files and never infers a session from a latest marker.
export async function createServerBackend({ projectDir, workspacePath, create, title, styleProjectPath, application, onSubmitted, onExit, requestTimeoutMs = 10000 } = {}) {
  if (typeof projectDir !== 'string' || !projectDir || !Number.isInteger(requestTimeoutMs) || requestTimeoutMs < 1 || requestTimeoutMs > 30000) throw failure('Invalid preview backend configuration.');
  const workspace = workspaceOptions({ ...(workspacePath !== undefined ? { workspacePath } : {}), ...(create !== undefined ? { create } : {}), ...(title !== undefined ? { title } : {}), ...(styleProjectPath !== undefined ? { styleProjectPath } : {}), ...(application !== undefined ? { application } : {}) });
  const args = ['--project-dir', projectDir];
  if (workspace.workspacePath !== undefined) args.push('--workspace-dir', workspace.workspacePath);
  if (workspace.create === true) args.push('--workspace-create', 'true');
  if (workspace.title !== undefined) args.push('--workspace-title', workspace.title);
  if (workspace.styleProjectPath) args.push('--style-project-path', workspace.styleProjectPath);
  if (workspace.application) args.push('--application', JSON.stringify(workspace.application));
  let executable;
  try { executable = await resolveNodeRuntime({ projectDir }); }
  catch (error) { throw Object.assign(error, { backendStopped: true, backendWasReady: false }); }
  const child = fork(workspace.application ? applicationServerPath : serverPath, args, {
    cwd: projectDir, execPath: executable, execArgv: [],
    env: previewEnvironment(executable),
    stdio: ['ignore', 'pipe', 'pipe', 'ipc'],
  });
  child.stdout.resume(); child.stderr.resume();
  const pending = new Map();
  let sequence = 0, exited = false, closing = false, readyReceived = false, closePromise, readyResolve, readyReject;
  const ready = new Promise((resolve, reject) => { readyResolve = resolve; readyReject = reject; });
  const ended = new Promise(resolve => {
    const finish = (code, signal) => {
      if (exited) return;
      exited = true;
      const error = failure('The preview process is closed.');
      readyReject(error);
      for (const item of pending.values()) { clearTimeout(item.timer); item.reject(error); }
      pending.clear();
      try { onExit?.({ code, signal }); } catch { /* An observer cannot prevent cleanup. */ }
      child.stdout.destroy(); child.stderr.destroy();
      if (child.connected) { try { child.disconnect(); } catch { /* Already disconnected. */ } }
      resolve();
    };
    child.once('exit', finish);
    child.once('close', finish); // Spawn failures may emit close without exit.
  });
  child.on('error', () => readyReject(failure('The preview process could not start.')));
  child.on('message', message => {
    if (!message || message.channel !== channel || message.version !== 1) return;
    if (closedKeys(message, ['channel', 'version', 'event', 'info']) && message.event === 'ready' && message.info?.type === 'server-started') {
      readyReceived = true; readyResolve(); return;
    }
    if (!readyReceived && closedKeys(message, ['channel', 'version', 'event', 'status', 'error']) && message.event === 'startup-error'
        && Number.isInteger(message.status) && message.status >= 400 && message.status <= 599
        && typeof message.error === 'string' && message.error.length > 0 && Buffer.byteLength(message.error) <= 2000) {
      readyReject(Object.assign(new Error(message.error), { status: message.status })); return;
    }
    if (closedKeys(message, ['channel', 'version', 'event', 'submission'], ['proposalId']) && message.event === 'submitted'
        && Number.isSafeInteger(message.submission) && message.submission > 0 && message.submission <= 200
        && (message.proposalId === undefined || (typeof message.proposalId === 'string' && /^[a-f0-9]{24}$/.test(message.proposalId)))) {
      if (!closing) { try { onSubmitted?.(message.submission, message.proposalId); } catch { /* Delivery ownership stays with the adapter. */ } }
      return;
    }
    if (!closedKeys(message, ['channel', 'version', 'id', 'ok'], ['result', 'error', 'status']) || !Number.isSafeInteger(message.id) || typeof message.ok !== 'boolean') return;
    const item = pending.get(message.id);
    if (!item) return;
    pending.delete(message.id); clearTimeout(item.timer);
    if (message.ok) item.resolve(message.result);
    else item.reject(Object.assign(new Error(typeof message.error === 'string' && message.error.length <= 2000 ? message.error : 'The preview action failed.'), { status: Number.isInteger(message.status) && message.status >= 400 && message.status <= 599 ? message.status : 503 }));
  });
  function rpc(method, params = {}) {
    if (exited || !child.connected || (closing && method !== 'retire')) return Promise.reject(failure('The preview process is closed.'));
    if (pending.size >= 64 || sequence >= Number.MAX_SAFE_INTEGER) return Promise.reject(failure('Too many pending preview actions.'));
    if (Buffer.byteLength(JSON.stringify(params), 'utf8') > 2 * 1024 * 1024 + 65536) return Promise.reject(Object.assign(new Error('The preview action is too large.'), { status: 413 }));
    const id = ++sequence;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { pending.delete(id); reject(failure('The preview action was not confirmed.')); }, requestTimeoutMs);
      pending.set(id, { resolve, reject, timer });
      child.send({ channel, version: 1, id, method, params }, error => {
        if (!error) return;
        const item = pending.get(id);
        if (item) { pending.delete(id); clearTimeout(item.timer); item.reject(failure('The preview connection is closed.')); }
      });
    });
  }
  async function stop() {
    if (closePromise) return closePromise;
    closing = true;
    closePromise = (async () => {
      if (exited) return;
      // Disconnect also triggers the server's own normal cleanup.
      if (child.connected) child.disconnect();
      const kill = setTimeout(() => child.kill('SIGTERM'), 1500);
      const force = setTimeout(() => child.kill('SIGKILL'), 4000);
      try { await ended; } finally { clearTimeout(kill); clearTimeout(force); }
    })();
    return closePromise;
  }
  const startup = setTimeout(() => readyReject(failure('The preview process did not become ready.')), requestTimeoutMs);
  try { await ready; }
  catch (error) { await stop(); throw Object.assign(error, { backendStopped: true, backendWasReady: readyReceived }); }
  finally { clearTimeout(startup); }
  const backend = Object.fromEntries(methods.filter(method => method !== 'retire').map(method => [method, params => rpc(method, params)]));
  backend.retire = async () => {
    if (closing) return stop();
    closing = true;
    try { if (!exited) await rpc('retire'); } catch { /* Shutdown may close IPC before the acknowledgement. */ }
    await stop();
  };
  return backend;
}
