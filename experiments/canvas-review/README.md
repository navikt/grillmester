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

All state is **in process memory** and is lost on extension shutdown or process
crash. The probe does not reuse the production atomic feedback store and does not prove durable or
exactly-once delivery across restarts. Each canvas expires after 20 minutes,
permits at most 50 batches and 50 sketch revisions, and has its own token and
port. At most four sketch artifacts are retained, including those with closed
panels. Closing a panel revokes its URL; reopening the same ID restores the
same sketch and submitted batches through a fresh token. It never changes the
original expiry or concept, and unsent browser drafts are not retained. Expired
IDs cannot be reused within the same extension lifetime. Restart this bounded
experiment after 20 expired instances. The three concept labels use the same
small text-and-direction surface; this is not a replacement for the full design editor.

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
existing session and render canvases. No command here stages it in a project
or personal extension directory. Rendering capabilities in the open callback
and joined session are optional: an exact, bound host request may attempt
opening when both flags are absent. Explicit `false` and malformed flags are
rejected. An attached session with the exact session ID is always required;
missing flags never replace ownership checks or prove rendering works.

Disposable native app tests on 2026-10-23 (version 1.1.31) verified discovery,
panel rendering with the existing CSP, idle-session delivery, an observed queued
message while busy, and separate replies in two canvas instances. A new unsent
draft retained its original sketch while a revision waited. Long Norwegian input
was rejected locally with focus returned to the field; the reply shortcut focused
the answered round. Concept-specific tab titles distinguish the sketches.

With the final lifecycle code, closing during accepted work revoked the listener.
The host rejected actions on the closed panel, so the session reopened the same
instance and completed its retained batch. Manual reopening after completion also
restored the sketch and reply through a fresh URL, without another message.
Closing a panel therefore does not cancel accepted work and may be followed by
an automatic reopen. A production adapter must make that distinction explicit.
Repository trust was revoked, the session archived, and all test listeners and
extension processes were stopped. Concurrent sessions, crashes, screen readers,
actual zoom and storage of the token-bearing URL remain unverified in the app.
Do not relax `frame-ancestors` or other network boundaries to make embedding work.

The SDK close callback has no view generation. A delayed callback may close a
newly reopened panel, but cannot reset its retained artifact; opening it again
restores the same data. Final expiry or extension shutdown discards the artifact
and rejects further actions. This is bounded in-memory recovery, not persistence.

See [ADR 0019](../../docs/adr/0019-app-canvas-prove.md) and the
[architecture and acceptance protocol](../../docs/testing/visual-companion-canvas.md)
for the optional adapter direction and production gates. The portable Node
server remains the supported path until those gates pass.

## Local HTML without an HTTP server

The separate `file-preview.mjs` experiment returns a `file://` URL from a private
temporary directory. Its two deliberately plain wireframes exercise time
selection, validation and a local summary, plus a priority board whose cards can
move between groups. The page has no network access, canvas actions or connection
to the conversation. All edits remain in the open page and disappear on reload.
The Node extension still registers the provider and manages temporary files;
this proves a server-free page, not a runtime-free extension.

```bash
FILE_PREVIEW_PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright \
FILE_PREVIEW_BROWSER_CHANNEL=chrome \
FILE_PREVIEW_SDK_DIR=/absolute/path/to/existing/copilot-sdk \
FILE_PREVIEW_EVIDENCE_DIR=/tmp/canvas-file-evidence \
node --test experiments/canvas-review/file-preview.test.mjs
```

With both explicit dependency paths, six checks exercise file ownership and
cleanup, the installed SDK against a test host, and headless Chrome. Both
concepts fit 1000, 390 and 320 CSS pixels without horizontal overflow. The
browser checks include tab and radio keyboard operation, invalid-choice focus,
literal text rendering, moving cards, preserved drafts between concept tabs and
reset on reload. Native select-popup keyboard behavior and the actual app's
`file://` rendering remain unverified. No model or real session is used.

For a later disposable native test, stage `file-preview.mjs` and
`file-preview.html` together in a separate project extension, with the former as
its package entry. The canvas ID is `design-file-preview`; its optional `concept`
is `booking` or `priorities`. Do not replace the existing feedback experiment or
activate this through the distributed plugin. Files expire after 20 minutes,
panel close removes its file, and final shutdown removes the private directory.
Closing does not retroactively erase pixels or drafts already loaded by a host.
