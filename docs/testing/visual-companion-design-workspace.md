# Project design workspace verification

Checked 2026-10-24 for the integrated canvas, project-owned storage and bounded
source editor described in [ADR 0022](../adr/0022-app-canvas-adapter.md) and
[ADR 0023](../adr/0023-prosjektlagret-designrom.md). This report concerns the
full plugin implementation. The earlier native app experiment in
[the canvas report](visual-companion-canvas.md) does not validate this later
implementation.

Design, accessibility and implementation perspectives were simulated reviews,
not research with human participants. Browser tests used synthetic content,
disposable projects, existing Chrome and Aksel React/CSS 8.19.2 through SSR.
The host was simulated; no model requests or real app sessions were used.

## Verified behavior

| Layer | Result | Scope |
| --- | --- | --- |
| Node regression suites | 128/128 passed | Server, feedback, canvas, workspace files/state, editor bindings, adapter and child backend. |
| Workspace file tests, included above | 17/17 passed | Reopen, immutable files, corruption rejection, exact capacity boundary, post-rename failure, eight concurrent processes, killed writer, distinct temporary environments and macOS case aliases. |
| Installed SDK with deterministic stdio host | 14/14 passed | Actual protocol and local child backend: session binding, explicit Send, unknown receipt, isolation, URL revocation, single writer, restart without replay and guarded history restore. |
| Integrated Chrome cases | 13/13 verified across retained reports | Feedback, history, recovery, bounded editing, keyboard/mobile operation, conflicts, lost receipts and refresh locks. |
| Independent disconnect case | 1/1 passed | After acknowledged source saving and a connection loss, the old frame restores its old source before accepting further feedback. |

The Chrome result is a combined result, not one uninterrupted 13/13 run. The
first full run passed 12/13. Its remaining driver case assumed a refresh button
would remain visible after the last draft was discarded; an idle frame may
already have advanced. The corrected case verifies the new source whether
refresh is still needed. That case and affected v1/v2 editor-entry cases passed
again after the final UI change. Original reports remain available.

The editor tests verify that typing and saving do not submit feedback, literal
markup remains text, saved fields survive restart, and manual values prevent
conflicting publication or restore until explicitly released. A lost save
receipt uses the same operation identity and creates one new version. A stale
draft survives and requires deliberate review of its baseline. Text proposals
and source edits keep separate ownership.

At 320×568, the editor stays within the viewport. Keyboard validation of a
2002-byte value leaves the field and its error visible together and writes
nothing. The tested feedback history retains keyboard focus and distinguishes
queued, working, answered and previous-session rounds. These are focused
checks; there was no new screen-reader or actual 200% zoom test in this phase.

The SDK run used protocol 3 and SDK entry SHA-256
`a8faeb5d4c8379ce6d8473c86e001fc4e2cd5d260e064d4c622f72c35102871d`.
It proves wire behavior against installed SDK files, not native rendering,
idle/busy scheduling or discovery through the app's plugin catalog.

## Installation and release gates

An independent isolated registration probe used the installed Copilot CLI
1.0.91 and a disposable copy of the generated full payload. Marketplace add,
install, list and uninstall all returned exit 0. The actual list schema
reported `source: "live"`, `enabled: true` and an `installedFrom` directory;
the client explicitly reported that nothing was copied.

`skill list --json` discovered all 44 enabled plugin skills, plus two separate
client built-ins. The registered payload contained all eight manifest-addressed
agent files and `extensions/visual-companion/extension.mjs`. These commands did
not expose an agent or canvas registry, so file presence is not proof of runtime
agent or extension discovery. Uninstall retained the live registration with
`enabled: false`, left source files intact and removed all plugin skills from
the available skill list.

The required `smoke_plugin_install.py` returned exit 1: its copied
`installed-plugins/.../plugin.json` expectation was absent with this client's
live-directory behavior. The separate registration probe does not turn that
release gate green. Its contract and tested baseline were not changed.

| Required gate | Result and boundary |
| --- | --- |
| `smoke_opencode.py --require-binary` | Exit 1 before scenarios: installed 1.18.30; requires 1.18.20. |
| `smoke_opencode_runtime.py --require-binary --cplt cplt` | Exit 1 at the same OpenCode version gate. |
| `smoke_grillmester_local.py --require-binaries --cplt cplt --opencode opencode --copilot copilot` | Exit 1 before all four scenarios: also requires Copilot 1.0.80 and cplt 2026.08.17-062831-1008a92; observed 1.0.91 and 2026.09.15-143904-77f4321. |

No client installation, version change, account change or baseline relaxation
was used. All 823 Python regression tests passed after regenerating the final
payload. The earlier attempt reported seven failures and two errors caused by
a late source change leaving its generated files and content digests stale.
After the final wording clarified that Figma delivery is optional, all four
affected role, package and content-digest checks passed again, as did every
generated-target check and package validation. Runtime files were unchanged.

## Reproduce and evidence

Supply existing dependencies; do not install them as part of the probe:

```sh
node --test plugin/skills/design-prototype/tests/*.test.js \
  plugin/extensions/visual-companion/tests/*.test.mjs
node plugin/extensions/visual-companion/tests/sdk-smoke.mjs \
  --sdk-dir /path/to/existing/copilot-sdk --evidence-dir /tmp/design-workspace-sdk
node scripts/smoke_visual_canvas.cjs \
  --playwright-module /path/to/existing/node_modules/playwright \
  --browser-channel chrome --aksel-project /path/to/existing/aksel-project \
  --evidence-dir /tmp/design-workspace-browser
```

Local evidence: `/tmp/grillmester-source-editor/verified-results.json` links
the original browser reports and source hashes;
`/tmp/grillmester-durable-adapter/sdk-final/sdk-results.json` records the SDK
checks; `/tmp/grillmester-durable-adapter/editor-disconnect-after/` records the
independent disconnect case. File tests are in
`/tmp/grillmester-durable-workspace/workspace-store-tests.log`. Exact release
commands, exits and observed registration JSON are under
`/tmp/grillmester-design-room-release-smokes/`.

## Remaining acceptance

The complete saved-room workflow still needs a real app run: plugin discovery,
opening, deliberate Send from idle and busy conversations, reviewed revision,
panel close/reopen and continuation after ending the session. A human pilot
with designers and an implementation partner also remains. Simulated panels
and automated interaction do not establish usability or adoption.

This work does not provide shared concurrent editing, free layout manipulation,
automatic production-code changes, a lossless Figma round trip or recovery of
unsaved typing after closing the sketch. HTML and its descriptor remain the
paired source. The native panel still uses Node and private loopback transport;
project storage currently requires the reviewed Unix locking contract.
