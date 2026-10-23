import { createCanvas, joinSession } from '@github/copilot-sdk/extension';
import { createCanvasAdapter } from './adapter.mjs';

const adapter = createCanvasAdapter({ sessionId: process.env.SESSION_ID });
const session = await joinSession({ canvases: [createCanvas(adapter.canvas)] });
adapter.attachSession(session);
let stopping = false;
async function stop() {
  if (stopping) return;
  stopping = true;
  try { await adapter.close(); } finally { process.exit(0); }
}
for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, stop);
process.stdin.once('end', stop);
