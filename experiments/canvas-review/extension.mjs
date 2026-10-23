// Explicit experiment entry point. Not registered by the distributed plugin.
import { createCanvas, joinSession } from '@github/copilot-sdk/extension';
import { createReviewProbe } from './probe.mjs';

const probe = createReviewProbe({ sessionId: process.env.SESSION_ID });
const session = await joinSession({ canvases: [createCanvas(probe.canvas)] });
probe.attachSession(session);
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.once(signal, async () => { await probe.close(); process.exit(0); });
}
process.stdin.once('end', async () => { await probe.close(); process.exit(0); });
