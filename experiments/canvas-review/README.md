# Session-bound design review experiment

This is an isolated protocol and interaction experiment, not an installed
Grillmester feature. It does not change the plugin manifest, generated targets,
client settings or the existing Visual Companion runtime. The extension entry
uses the host-provided `@github/copilot-sdk/extension`; no SDK implementation or
third-party example code is bundled here.

The experiment keeps a small authenticated Node.js HTTP server per canvas.
`createCanvas().open` supplies its URL to the host. An explicit **Send innspill**
stores one immutable batch before calling the joined session's `send` with
`source: "user"` and `mode: "enqueue"`. Trying a radio option, writing a draft,
opening the panel, polling or publishing a revised sketch never sends a prompt.

An acknowledgement means queued, not processed. `review_batch` records a
separate working/resolved state. An uncertain delivery is never automatically
resent. A repeated HTTP request uses the same immutable ID; a trusted review
of that exact batch can reconcile receipt without replaying it. Browser drafts
retain the viewed screen while a newer revision waits. Each submitted batch
keeps the original authored title and description for later review; no DOM text
or prototype field values are harvested.

All state is **in process memory** and is lost on stop or crash. The probe does
not reuse the production atomic feedback store and does not prove durable or
exactly-once delivery across restarts. Each canvas expires after 20 minutes,
permits at most 50 batches and 50 sketch revisions, and has its own token and
port. At most four canvases may be open; closed IDs cannot be reused within the
same extension lifetime. Restart this bounded experiment after 20 closed
instances. The three concept labels use the same small text-and-direction
surface; this is not a replacement for the full design editor.

## Verify without a client or model

Use existing Node.js, an existing SDK and, for browser checks, an existing
Playwright/browser installation. Nothing is installed by these commands.

```bash
node --test experiments/canvas-review/probe.test.mjs
node experiments/canvas-review/sdk-smoke.mjs \
  --sdk-dir /absolute/path/to/existing/copilot-sdk \
  --evidence-dir /tmp/canvas-sdk-evidence
node experiments/canvas-review/browser-smoke.mjs \
  --playwright-module /absolute/path/to/node_modules/playwright \
  --browser-channel chrome --headed \
  --evidence-dir /tmp/canvas-browser-evidence
```

The SDK test uses the actual SDK against a deterministic stdio substitute for
the host. It does not start a client, runtime or model, nor inherit credentials.
Its report records the SDK protocol and entry-file hash. The browser test uses
the actual HTTP/UI code with a simulated `session.send`; screenshots are from
that browser, not the app's native panel. It supports `--case` for focused
rechecks and explicitly labels reduced viewports as distinct from browser zoom.

The native entry point is `extension.mjs`. Merely executing it with Node is not
a real app test: the host must discover it, supply SDK resolution, bind an
existing session and support canvases. No command here stages it in a project
or personal extension directory. The native panel, current CSP, actual idle
and busy scheduling, cross-window lifecycle and storage of the token-bearing
URL must still be verified in a disposable app session. Do not relax
`frame-ancestors` or other network boundaries merely to make embedding work.

See [ADR 0019](../../docs/adr/0019-app-canvas-prove.md) and the
[architecture and acceptance protocol](../../docs/testing/visual-companion-canvas.md)
for the optional adapter direction and production gates. The portable Node
server remains the supported path until those gates pass.
