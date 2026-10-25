// Optional, disposable file-URL experiment; not registered by the plugin.
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { randomBytes, randomUUID } from 'node:crypto';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const template = readFileSync(new URL('./file-preview.html', import.meta.url), 'utf8');
const labels = { booking: 'Timevalg · lokal skisse', priorities: 'Prioritering · lokal skisse' };
const validId = value => typeof value === 'string' && value.length > 0 && Buffer.byteLength(value) <= 200;
function requireValue(condition, message) { if (!condition) throw new Error(message); }

export function createFilePreview({ sessionId, directory = tmpdir(), lifetimeMs = 20 * 60 * 1000 } = {}) {
  requireValue(validId(sessionId), 'An exact session is required.');
  requireValue(Number.isInteger(lifetimeMs) && lifetimeMs > 0 && lifetimeMs <= 20 * 60 * 1000, 'Invalid file preview lifetime.');
  const root = mkdtempSync(join(directory, 'canvas-file-preview-'));
  chmodSync(root, 0o700);
  const instances = new Map();
  let session, closed = false;
  const expiry = setTimeout(close, lifetimeMs);
  expiry.unref();

  function owned(ctx) {
    requireValue(ctx?.sessionId === sessionId && ctx.canvasId === 'design-file-preview' && validId(ctx.instanceId) && validId(ctx.extensionId), 'Canvas ownership does not match.');
    const instance = instances.get(ctx.instanceId);
    requireValue(!instance || instance.extensionId === ctx.extensionId, 'Canvas owner changed.');
    return instance;
  }
  function close() {
    if (closed) return;
    closed = true;
    clearTimeout(expiry);
    // This path is created by mkdtemp, never taken from canvas input.
    rmSync(root, { recursive: true, force: true });
  }
  const canvas = {
    id: 'design-file-preview', displayName: 'Lokal skisseprøve',
    description: 'Open a disposable local wireframe with time selection and a priority board. Local choices are never submitted to the conversation.',
    inputSchema: { type: 'object', properties: { concept: { type: 'string', enum: Object.keys(labels) } }, additionalProperties: false },
    actions: [],
    open(ctx) {
      requireValue(!closed, 'File preview has ended.');
      requireValue(session, 'The exact session must be attached before opening.');
      let instance = owned(ctx);
      const flags = [ctx?.host?.capabilities?.canvases, session.capabilities?.ui?.canvases];
      requireValue(flags.every(value => value === undefined || typeof value === 'boolean') && !flags.includes(false), 'Canvas support was denied or malformed.');
      const input = ctx.input ?? {};
      requireValue(typeof input === 'object' && !Array.isArray(input) && Object.keys(input).every(key => key === 'concept') && (!Object.hasOwn(input, 'concept') || Object.hasOwn(labels, input.concept) && typeof input.concept === 'string'), 'Unknown file preview input.');
      requireValue(!instance || !Object.hasOwn(input, 'concept') || input.concept === instance.concept, 'Use another instance for a different initial concept.');
      if (!instance) {
        requireValue(instances.size < 4, 'This bounded file preview holds at most four instances.');
        instance = { extensionId: ctx.extensionId, concept: input.concept ?? 'booking' };
        instances.set(ctx.instanceId, instance);
      }
      if (!instance.path) {
        const path = join(root, `${randomUUID()}.html`);
        const nonce = randomBytes(18).toString('base64url');
        writeFileSync(path, template.replaceAll('{{NONCE}}', nonce), { encoding: 'utf8', mode: 0o600, flag: 'wx' });
        instance.path = path;
      }
      const url = pathToFileURL(instance.path);
      url.hash = `concept=${instance.concept}`;
      return { url: url.href, title: labels[instance.concept], status: 'Kun lokalt utkast. Ingenting sendes. Lukk eller last inn på nytt for å nullstille.' };
    },
    onClose(ctx) {
      const instance = owned(ctx);
      if (!closed && instance?.path) {
        rmSync(instance.path, { force: true });
        instance.path = undefined;
      }
    },
  };
  return {
    canvas, close,
    attachSession(value) {
      requireValue(!closed && !session && value?.sessionId === sessionId, 'Invalid joined session.');
      session = value;
    },
  };
}

// Importing the factory in tests never loads the SDK or starts a session.
if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  const { createCanvas, joinSession } = await import('@github/copilot-sdk/extension');
  const preview = createFilePreview({ sessionId: process.env.SESSION_ID });
  const stop = () => { preview.close(); process.exit(0); };
  for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, stop);
  process.stdin.once('end', stop);
  try { preview.attachSession(await joinSession({ canvases: [createCanvas(preview.canvas)] })); }
  catch (error) { preview.close(); throw error; }
}
