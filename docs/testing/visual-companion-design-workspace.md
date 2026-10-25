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
The browser and SDK hosts were simulated. The separate native app trial below
uses the real application and is reported independently.

The expanded Lumi and Dialogmøte frontend trial has completed its assisted
functional rounds. It has
verified saved-field preservation, deliberate owner recovery, a question-only
round and historical source restoration with rendered readback. All six rounds
have saved replies. Closure comparison, original-source audit and cleanup are
verified. The later follow-up below resolves the measured narrow-layout overlap
and verifies 48 responsive combinations. Concept selection and a human pilot
remain incomplete; exact-revision CI results are recorded in the pull request.
The local results below do not identify an exact source commit unless explicitly
stated. They are local evidence, separate from the revision-bound CI results.

## Verified behavior

| Layer | Result | Scope |
| --- | --- | --- |
| Earlier Node regression baseline after restoration-message correction | 149/149 passed | Server, feedback, canvas, workspace files/state, editor bindings, adapter, runtime selection, styles and child backend, including distinct preserved-field versus stale-history guidance. This baseline predates the additional 162-test run below. |
| Earlier full Python baseline | 823/823 passed | Complete rerun after the helper and reference follow-ups, with all 243 captured source/test/manifest hashes unchanged. The later storage and queued-notice changes are reported separately below. |
| Retained workspace file baseline | 17/17 passed | Reopen, immutable files, corruption rejection, exact capacity boundary, post-rename failure, eight concurrent processes, killed writer, distinct temporary environments and macOS case aliases. |
| Targeted adapter checks after conditional-publication correction | 20/20 passed | Stubbed session binding, lifecycle, action routing and explicit delivery. These checks do not establish how a model handles a confirmation-only round. |
| Installed SDK with deterministic stdio host after schema-registration follow-up | 16/16 passed | Ordinary Node 24.18.0; actual protocol and local child backend, including bounded registered style-subproject schema, exact CSS binding, safe diagnostics, delivery, isolation and recovery. Excludes native schema validation and provider reload lifecycle. |
| Retained packaged app runtime baseline with deterministic stdio host | 14/14 passed | The earlier protocol checks through the app's existing packaged executable and effective extension bootstrap, with isolated configuration and no model calls. This run predates the conditional-publication and monorepo styling changes. |
| Earlier native app 1.1.31 trial with synthetic sketches | Interaction, recovery and corrected confirmation round passed | Full-plugin discovery, two saved rooms, manual source editing, idle and busy delivery, replies in the correct rooms, explicit same-instance reopen and recovery after ending the owning session. An initial no-change round failed and was corrected and retested below. |
| Expanded native frontend trial | Assisted functional rounds completed | Real-source Lumi and Dialogmøte copies, twelve verified source pairs and six answered rounds, with artifact comparisons and rendered checks. The later layout and native follow-up is reported below; this is not a completed design acceptance or human pilot. |
| Integrated Chrome cases | 13/13 verified across retained reports | Feedback, history, recovery, bounded editing, keyboard/mobile operation, conflicts, lost receipts and refresh locks. |
| Isolated Chrome description-list DOM checks | 2/2 passed | Synthetic `dl > div > dt` and `dl > div > dd` bindings preserve the intended target, literal text and compact setting. These are separate from native acceptance. |
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

The SDK runs used protocol 3 and SDK entry SHA-256
`a8faeb5d4c8379ce6d8473c86e001fc4e2cd5d260e064d4c622f72c35102871d`.
It proves wire behavior against installed SDK files, not native rendering,
idle/busy scheduling or discovery through the app's plugin catalog.

## Native app acceptance

The real app trial used version 1.1.31 and a temporary local marketplace with
the complete plugin. The active Designer discovered `design-workspace` from
`plugin:grillmester:visual-companion`, including all eight actions. The first
open failed before creating a room: the backend treated the host's packaged
Node executable as an ordinary Node script runner. That executable dispatches
its own application entry point, so the preview child exited before readiness.

The adapter now resolves and probes an existing ordinary Node 18+ runtime,
without installing one or forwarding host credentials and startup options.
Project-local and relative PATH candidates are excluded. A missing runtime
produces an actionable opening error before writing a room. The regression
suite includes seven runtime-selection cases, and the additional SDK run uses
the actual packaged executable and its effective bootstrap. Its 14 passing
checks establish this startup path independently of a native model session.

The corrected native trial used Node 24.18.0 and the Designer role. Two
distinct saved rooms opened through the complete plugin in one disposable
local project. Both rendered their first sketch. In Møteplan, the source editor
saved the heading **Min møteplan** and the **Kompakt** density as version 2.
Reopening the small editor showed both values and their preserved-field labels.
Saving these edits started no conversation work.

Sending the first Møteplan round while the conversation was idle started work
automatically. Sending the Pakkeliste round while the native conversation
visibly showed **Working** produced one queued message. Both rounds subsequently
received replies in their respective canvases without a separate chat prompt.
Møteplan reached version 3 with its requested paragraph, edited heading and
compact density; Pakkeliste reached version 2 with its own requested paragraph.
All five registered HTML/descriptor pairs matched their saved source, with
exactly one submitted round and one answered review in each room.

Closing Møteplan revoked its old preview transport. The host menu
**Add tab → Canvas → Designverksted** opened a new temporary blank sketch,
rather than the existing instance. The original tool card still contained the
revoked link. A subsequent explicit chat request to reopen the same instance
succeeded with a fresh transport and retained version 3, its answered feedback
and both preserved fields. Reopening the existing instance without a model
request therefore remains unverified through the tested host menu; this result
does not establish an adapter reopen failure.

After `/clear`, the owning extension and both room backends were confirmed
stopped. A new Designer session in the same exact project opened the existing
Møteplan room without creating it again. The recovered canvas rendered version
3 with **Min møteplan** and the requested paragraph. State readback retained
both preserved fields, and the old answered round was visibly marked as an
answer from a previous conversation.

The next explicit round reached the new owner, but exposed an instruction
conflict. Its note requested only confirmation and explicitly said that no new
sketch version was needed. The delivery prompt and canonical reference still
directed publication for every round. The Designer response cited that conflict
and published version 4 anyway. The completed round and a file
comparison confirmed that both its HTML and descriptor were byte-for-byte
identical to version 3. This failed the no-new-version criterion despite
successful delivery to the recovered conversation.

The delivery prompt and reference now require a new revision only when the
requested source actually changes. After the targeted adapter and SDK checks
passed, the corrected payload was loaded, the owning session was ended and
the existing room was recovered again. The same confirmation-only note was
submitted as round 3. Its delivered message visibly contained the conditional
publication instruction. The canvas showed the round as answered with a saved
comment reply, while the source stayed at version 4. The comment correctly
remained open: this was a confirmation, not a claim that a source issue was
fixed.

The final snapshot contained all 14 room files and six source pairs.
Møteplan's four source pairs, screen identity and both preserved fields were
unchanged from before the corrected round. Earlier submitted snapshots,
comments and replies were unchanged; older rounds acquired only the expected
previous-session attribution. The new round, its comment and reply, and the
associated state counters were added. The entire Pakkeliste room remained
byte-for-byte identical to both earlier baselines. The failed round and its
extra identical version remain in the evidence.

Cleanup was verified at 2026-10-24 06:20 UTC. The temporary live plugin was
disabled and its marketplace registration removed, while the normal
Grillmester 0.7.1 installation was re-enabled. The CLI inventory confirmed the
normal installation and marketplaces, with the existing disabled built-in
unchanged; the native plugin detail also showed the normal installation enabled.
After `/clear`, the session was idle and the test-owned extension, preview
backend and listener were gone. No repository trust was granted; access used
individual approvals. Saved test artifacts were retained as evidence.

The native marketplace-management and canvas lists retained stale trial
entries. Attempting the scoped removal there reported that the marketplace
was not registered, consistent with the authoritative CLI inventory. The whole
app was not restarted and unrelated sessions were left intact. These cached
entries remain a host UI limitation rather than evidence of an active trial
registration.

## Expanded frontend trial — bounded technical results

Disposable copies of Lumi and Dialogmøte were rendered with their existing mock
data before design work. The native app remained at 1.1.31, using the Designer
role and Node 24.18.0. Original repositories were not write targets. The final
audit found all 1,057 copied Lumi files and 267 copied Dialogmøte files unchanged
in their original locations. This covers the manifest-listed regular files,
not added, omitted, untracked or dependency paths.

| Case | Observed result and remaining boundary |
| --- | --- |
| Lumi concepts and fidelity | Both concepts retain all ten normal task rows, counts, rates and 95% intervals. V3 corrected the phrase, six-marker description and theme-overlap wording; ambiguous theme percentages and the unthemed count were omitted rather than recomputed. V6 corrected cross-concept wording and moved a zone label without moving markers, but contained an unintended “30–100”→“30–30” method change. V7 corrects only that number. The final reply and native narrow-panel inspection disclose a separate marker 5/zone-label overlap and close label placement; marker 6 is fixed. Choosing one concept was deliberately not exercised. |
| Saved edits and question-only reply | The edited heading and compact density survived v2→v3 with both preservation records intact. A question-only round was answered at v2 without changing either source pair; its comment correctly remained open. |
| Owner recovery and styles | After deliberate `/clear`, the same Lumi room recovered with all five files byte-identical, including its unsent note and preserved values; recovery did not send the note. An explicit subproject style context loaded the exact CSS file. Opening succeeded after the completed fixture update and a subsequent owner clear; no cache defect was established. |
| Lumi finite states | Both concepts' Normal, Få svar and Ingen treff states and both resets worked in Chrome against the actual published preview. Preview reading and capture succeeded, but iframe clicks required manual interaction. |
| Preservation conflicts and history | Restore was rejected while preservation records remained, including after releasing only the heading. After both explicit releases, v1 restored as v4 and polished v3 as v5. Each new HTML/descriptor pair exactly matches its chosen source; all older pairs, comments, submitted snapshots and replies are unchanged. The actual iframe accessibility tree showed the old v4 appearance and the polished v5 heading/compact setting. Intermediate release states have UI evidence only. Conflict messages misleadingly referred to stale history; the correction passed local tests but is not loaded in this fixture. |
| Dialogmøte editing and iteration | A stale v2 editor rejected Save after another tab saved compact density as v3, retained the typed draft, and required explicit discard. Published v4 preserves the heading and density. Its 15 buttons have declared bindings, three readonly examples have matching counters, and four links have local targets. Twelve of thirteen original letter values remain; the requested dead mock video URL was removed. |
| Dialogmøte queues and response states | Round 1 remained bound to v2 and queued round 2 to v3 after v4 publication; both received separate saved replies. Confirmation round 2 added no version. The proposed fixed-status write was declined; keeping the comment open required explicit guidance. Round 3 published v5 to correct receipt/error precedence, combined-state labels and the disabled error-link target. All 28 combinations passed static analysis and manual UI checks. The error link focuses its legend; the embedded receipt→send-error flow retains the reason and hides the receipt. The saved final reply distinguishes automated checks from manual interaction. Descriptor values, letter content, holds and previous rounds are unchanged. |

Final file snapshots contain seven Lumi pairs and five Dialogmøte pairs, with
three answered rounds in each room. Answering the last rounds changed only
their comment/review records and state counters; all source pairs, preservation
records, submitted snapshots and earlier replies stayed unchanged. Afterward,
a queued Dialogmøte notification prompted a proposed rewrite of an already
answered round. That redundant write was declined before the owning session
ended. No extra version was created; autonomous duplicate handling is not
established. After both owners were cleared, all 26 room files were byte-for-byte
identical to these answered snapshots: no redundant reply rewrite persisted.

Expanded-trial cleanup was verified separately. Both native sessions reached
Idle, owned preview tabs and six trial Chrome tabs were closed, and the frontend
servers and all four trial listeners were gone. The temporary plugin was
disabled and its marketplace removed; the authoritative inventory showed the
normal Grillmester 0.7.1 enabled and the existing browser component disabled.
The native installed-plugin view agreed.
The canvas list may retain a cached entry; it was not activated or treated as
an active registration. No persistent repository trust was granted, and saved
evidence was retained.

Both initial designs encountered binding rejections before corrected publication;
these failed attempts remain in the evidence. The Dialogmøte iteration later
needed explicit guidance to stop private preview CSS debugging
and publish through the actual canvas. Lumi also needed guidance when its first
owner misread deliberate manual edits and when native click verification could
not proceed. These are assisted workflow results, not autonomous completion.
The later manual v3 edit prompted a fresh state read before publication in
Dialogmøte.

New reference guidance describes finite response/receipt combinations, error
precedence and combined-state labels. That guidance is locally validated but
has not been loaded into this running native fixture. It does not retroactively
turn the observed prototype failures into passes. No product source changes,
real response submission or human usability validation are established by these
finite demonstrations.

## Reading an implementation handoff

A separate technical exercise created four source versions through the actual
workspace APIs. The brief selected version 2, while version 4 had a different
heading, different body text and an unsent note. Version 2's heading, density
choice and body text were recovered from only the brief and saved project files,
without opening the canvas. The registered HTML and descriptor hashes
matched; all nine project files remained byte-for-byte unchanged after reading.

The exercise also exposed the limits of a version-only handoff. Raw HTML held
older fallback text and spacing settings; the descriptor contained the saved
edits. Current preserved fields and feedback status did not establish historical
approval or verified state coverage for the chosen version. The
[handoff guidance](../../plugin/skills/design-prototype/references/design-handoff.md)
therefore records the exact pair, agreed decisions, relevant submitted rounds,
values to preserve and observed coverage. It does not add a new file format.
This was a technical cold-read with synthetic content, not human usability
research or a check of rendered appearance.

## Installation and release gates

An isolated registration probe used the installed Copilot CLI
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
A later isolated rerun first stopped for a missing `--source-sha` argument;
with an explicit valid SHA, it reached installation and stopped on the same
missing copied-manifest expectation. The version-gated checks below also
stopped before running scenarios on that payload.

| Required gate | Result and boundary |
| --- | --- |
| `smoke_opencode.py --require-binary` | Exit 1 before scenarios: installed 1.18.30; requires 1.18.20. |
| `smoke_opencode_runtime.py --require-binary --cplt cplt` | Exit 1 at the same OpenCode version gate. |
| `smoke_grillmester_local.py --require-binaries --cplt cplt --opencode opencode --copilot copilot` | Exit 1 before all four scenarios: also requires Copilot 1.0.80 and cplt 2026.08.17-062831-1008a92; observed 1.0.91 and 2026.09.15-143904-77f4321. |

No client installation, version change, account change or baseline relaxation
was used. Earlier retained full-suite results were 135/135 Node and 823/823
Python; those logs do not identify an exact source commit. An earlier Python
attempt reported seven failures and two errors caused by a late source change
leaving generated files and content digests stale. Regeneration resolved that
mismatch. A subsequent wording change clarifying that Figma delivery is
optional passed the four affected role, package and content-digest checks.

The conditional-publication correction first passed 20/20 targeted adapter
tests, 14/14 installed-SDK checks under ordinary Node, two checks of current
content hashes and the existing rights-approval decision reference, all four
generated-target checks and package validation. Its confirmation-only behavior
was established separately by the native round described above.

The later working-tree payload containing monorepo styling and
conditional-publication changes passed the full 145-test Node suite and
823-test Python suite, plus 13 deterministic validation commands. Those commands
covered marketplace and generated-target checks, Python compilation, package
validation, JavaScript syntax and diff whitespace. The installed-SDK run passed
15 checks, adding explicit style-subproject resolution, exact CSS delivery and
reopen binding.

A subsequent prompt-only follow-up passed five focused Python tests: three
Designer content contracts covering degraded delivery, tool coverage and the
implementation boundary, plus the two existing rights-journal checks. Its
seven deterministic commands checked the marketplace, four generated targets,
package validation and diff whitespace. That report records the full runtime
baseline and unchanged hashes for its listed implementation, reference and test
files. These are distinct validation stages; the full suites were not rerun for
the prompt-only follow-up.

The binding-diagnostics and description-list grouping change then passed the
full 148-test Node suite, 16 installed-SDK checks, two focused rights-journal
checks and ten deterministic validation commands. Two isolated Chrome cases
checked DOM behavior for editable text inside `dl > div > dt` and
`dl > div > dd`. The SDK addition verifies safe diagnostics across the wire and
that a rejected binding followed by a corrected grouped description list creates
only one revision. These checks do not establish native rendering or model
behavior.

The subsequent browser-capability and manual-edit guidance changes each passed
five focused Python tests and seven deterministic checks. A later SDK run kept
16 checks and strengthened inspection of the actual registered optional
`styleProjectPath` schema. Eight deterministic checks passed. This harness does
not reproduce native schema validation or provider reload behavior.

The full Python suite was then rerun: 823 tests passed, with all nine captured
source and manifest hashes unchanged through the run. Subsequent reference-only
follow-ups for finite response flows and error precedence each passed five
focused Python tests and seven deterministic checks; eleven listed runtime and
test hashes remained unchanged. Their retained baselines are 148 Node tests,
16 SDK checks and the latest full 823-test Python run. Those full suites were
not rerun for the reference-only changes, and their new wording is not validated
by the running native fixture.

The subsequent helper correction distinguishes a preserved-field restore
conflict from stale history without changing rejection guards, persistence or
SDK behavior. It passed the full 149-test Node suite, five focused Python tests
and eight deterministic checks. The new helper behavior test covers both
messages, unknown errors, unchanged versions, no false success or duplicate
retry, and no raw server-detail disclosure. At that stage, full Python and SDK
results were preceding baselines; neither was rerun for that correction. It is not
loaded in the native fixture. Rights checks preserve existing decision records
and do not constitute a new legal or licensing review.

A final reference-only follow-up permits inspection of the already-observed
preview in an existing browser canvas while retaining feedback and revision
actions in the owner. It passed five focused Python tests and seven
deterministic checks with twelve runtime/test hashes unchanged from the
149-test Node baseline. This wording is also not loaded in the native fixture.

The final source payload then passed the full 823-test Python suite with all
243 captured source, test and manifest hashes unchanged. A sandboxed attempt
had local access failures; the same suite passed outside the sandbox without
code changes. Required compilation, server/helper syntax and whitespace checks
also passed. The 149-test Node and 16-check SDK runs remain their distinct
preceding evidence; they were not repeated for this final Python run.

## Reproduce and evidence

Supply existing dependencies; do not install them as part of the probe:

```sh
node --test plugin/skills/design-prototype/tests/*.test.js \
  plugin/extensions/visual-companion/tests/*.test.mjs
node plugin/extensions/visual-companion/tests/sdk-smoke.mjs \
  --sdk-dir /path/to/existing/copilot-sdk --evidence-dir /tmp/design-workspace-sdk
node plugin/extensions/visual-companion/tests/sdk-smoke.mjs \
  --sdk-dir /path/to/existing/copilot-sdk \
  --runtime-binary /path/to/existing/packaged-executable \
  --runtime-bootstrap /path/to/existing/dist/preloads/extension_bootstrap.mjs \
  --runtime-dist-dir /path/to/existing/dist \
  --evidence-dir /tmp/design-workspace-sdk-packaged
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
The later release-gate rerun is recorded in
`/tmp/design-workspace-final-release-smokes/results.json`.
The packaged-runtime report is
`/tmp/grillmester-durable-adapter/sdk-packaged/sdk-results.json`; it records
executable, effective bootstrap, loader and SDK hashes without private paths.
The retained full-suite logs are `/tmp/grillmester-native-runtime-node.log`
and `/tmp/grillmester-native-runtime-python.log`. The installed-SDK report for
the conditional-publication correction is
`/tmp/design-workspace-sdk-conditional-revision/sdk-results.json`.
The later full-suite and 13-command validation report is
`/tmp/design-workspace-monorepo-validation/validation.json`. The subsequent
five-test and seven-command prompt follow-up is
`/tmp/design-workspace-prompt-followup-validation/validation.json`; its payload
fingerprint differs from the full-run baseline. The 15-check installed-SDK
report is `/tmp/design-workspace-sdk-monorepo-css/sdk-results.json`.
The later 148-test Node, two-test Python and ten-command binding validation is
`/tmp/design-workspace-binding-validation/validation.json`, with the 16-check
SDK report in `/tmp/design-workspace-sdk-binding-diagnostics/sdk-results.json`
and the two synthetic DOM checks in
`/tmp/grillmester-binding-diagnostics/dom-parity.json`.
The five-test and seven-command browser-wording follow-up is
`/tmp/design-workspace-browser-wording-validation/validation.json`; it records
the separate runtime and full-Python baselines rather than claiming new full
suite or native passes.
The registered-schema SDK follow-up is
`/tmp/design-workspace-schema-registration-validation/validation.json`, with
results in `/tmp/design-workspace-sdk-registered-schema/sdk-results.json`.
The later full Python run is
`/tmp/design-workspace-final-python-validation/validation.json`.
Reference-only follow-ups are recorded in
`/tmp/design-workspace-flow-reference-validation/validation.json` and
`/tmp/design-workspace-cross-state-reference-validation/validation.json`.
The later helper correction and 149-test Node run are recorded in
`/tmp/design-workspace-restore-message-validation/validation.json`.
The subsequent preview-inspection guidance is recorded in
`/tmp/design-workspace-preview-inspection-validation/validation.json`.
The final full Python result and unchanged-source comparison are in
`/tmp/design-workspace-final-payload-validation-unsandboxed/validation.json`;
that report retains the preceding sandbox attempt and its access limitations.
Expanded-trial source snapshots, static fidelity/state audits, screenshots,
post-shutdown comparisons and the original-file audit are retained with the
private acceptance ledger. It records ten bounded cases passed and one partial
case for concept selection and narrow-panel visual polish.
The redacted native artifact comparison is
`/tmp/grillmester-durable-adapter/native-acceptance/final-artifact-audit.json`.
Original, failed-round and final file snapshots are retained privately; shared
evidence omits session identifiers and transport capabilities.

## Additional adversarial and responsive checks, 24 October

The follow-up found four contradictory persisted-choice shapes: a missing
current copy of an accepted choice, duplicate active targets, an accepted
choice changed without becoming pending, and duplicate accepted choices hidden
by an unsent release. Hydration now rejects these without rewriting the room.
Pending edits, releases, scoped re-keeps and a new choice after a submitted
release remain valid through repeated reopening.

Five real process-kill cases cover partial HTML, partial descriptor and partial
journal bytes, complete revision files before the journal rename, and immediately
after rename. Prior source pairs, submitted and unsent
feedback, and manually preserved values survive at one complete publication
boundary. Missing or changed older source files also reject reopening without
silently repairing or replacing data. These are process-interruption tests on
a running filesystem, not simulations of power loss.

The full Node suite passed **162/162**, with no skips. The Python run passed
821 of 823 checks; both remaining checks passed after correcting the single
stale design-prototype digest in the existing rights journal. Its decisions,
dates and review references were unchanged. Generator checks and validation
passed. Installed-client release preflights still require the pinned CI inputs.
An existing eight-writer
test exposed a timing-sensitive retry budget under parallel load; its 30 rapid
attempts allowed only about 585 ms of waiting. The test now uses an eight-second
monotonic deadline with bounded, staggered retries. The same eight processes,
exclusive critical-section check, exact final revision and overall timeout
remain. Earlier failed runs are retained in the private evidence.

CodeQL flagged a check-before-read pattern in the new corruption test. Both
occurrences now read directly and treat only `ENOENT` as absence, preserving
the missing-file and damaged-file assertions. The seven affected recovery
cases passed after this test-only correction; runtime files were unchanged.

Delayed queued notices now explicitly require checking the round's live review
and reply before doing work. Already answered notices retain their answer and
version unless a newer explicit request requires follow-up. An unread round
may become working; an explicit correction to an answered round retains answered.
The adapter unit regression covers late reversed acknowledgements, duplicate
callbacks, immutable original inputs, rejected restart, identical-answer no-op
and permitted deliberate answer correction. The separate installed-SDK harness
passed **16 checks**; it does not exercise that queued-notice scenario.
These checks establish adapter behavior and SDK protocol behavior within their
respective scopes, not model obedience or withdrawal of a message already
queued in the native client.

A separate static layout fixture rendered the exact Lumi fragment, descriptor,
frame template and existing Aksel CSS at 320, 375, 768 and 1280 CSS pixels.
All **48 combinations** of width, direction, situation and density matched the
requested width, selected direction and expected marker count. None had
horizontal document overflow or overlapping numbered markers. The baseline
reproduced the old 6/7 marker collision. Captions now sit outside the data plane;
a named, keyboard-focusable horizontal chart region preserves the coordinates.
ArrowRight moved the chart by 40 px without moving the page horizontally.
Narrow ranking and interval rows were inspected visually. Numeric data,
all 16 marker declarations and the descriptor were preserved. This fixture
excludes the feedback helper and native app; it is a layout check only.

The reviewed candidate was then published as Lumi version 8 through the guarded
workspace action. All 14 files belonging to its seven older source pairs and
all comments, decisions, submitted snapshots and review answers were unchanged.
A separate room exercised the current full browser wrapper: save a manual
heading as version 2, receive the specific held-field restore conflict, release
the hold without changing the text, refresh history and restore version 1 as
version 3. The restored source pair was byte-identical; no feedback was sent.

Evidence is retained under `/tmp/design-workspace-recovery-validation/`,
`/tmp/design-workspace-queued-notice-sdk/`,
`/tmp/design-workspace-extended-python-final/` and
`/tmp/design-workspace-responsive-probe-3ys3jdko/`.

## Latest native read-only follow-up, 24 October

After the desktop became available, the complete current payload was loaded
from a freshly verified temporary marketplace in a cleared conversation.
Designer reopened Lumi version 8 with the explicit frontend style subproject
and identified the three earlier rounds as answered. The installed Playwright
browser was unavailable. The sandboxed iframe boundary was identified through
the built-in Browser canvas, and its observed preview URL was opened directly
without additional installation or navigation guidance. Screenshots were
inspected; measurements showed a 416 px viewport, a 352 px content area, the
inline Aksel stylesheet and its spacing token. Source Sans 3 was not loaded;
this run used a system-font fallback and does not establish font fidelity.
One screenshot request returned the wrong region; retargeting corrected it.
Individual tool approvals were still required.

The 560 px chart can be read by horizontal scrolling, but its extremes are not
visible together in this panel. Tasks 1 and 4 start outside the viewport, while
other tasks disappear at the opposite scroll position. This is a product
tradeoff to assess in the prepared human follow-up, not evidence that scrolling
is the best default. The priority list was inspected in the same narrow view.

Two separate question/confirmation rounds were submitted from the sketch while
Designer was busy. Before ending its initial request it read the
fresh state, found both rounds, read each immutable submission, saved comment
replies and marked both answered. Neither requested a new sketch. All 16
existing source files, the revision history, the first three comments and round
answers, prior submissions, decisions and manual-ownership state were unchanged;
the current source stayed at version 8.

Both delayed host notifications then ran as separate conversation turns.
Designer re-read each already answered round and current state, retained both
answers and finished without another write or submission. The complete room
state and every room file were byte-identical before and after both queued
notices. This verifies this observed native sequence, not universal model
obedience or cancellation of already queued messages. Questions remained open
comments with replies while their review rounds were answered.

The conversation was then cleared and idle, both owned panels and the evidence
browser tab were closed, the temporary marketplace was removed, and the ordinary
0.7.1 package was re-enabled. No trial backend remained. All room files also
matched after shutdown. A separate audit
confirmed the 1,057 Lumi and 267 Dialogmøte original files listed in the copy
manifests remained unchanged; unlisted files were outside that comparison.
Private evidence is retained under the latest native-trial directory, including
the before/after file audit, queued-notice equality check and rendered replies.

## Remaining acceptance

The real-frontend technical trial and latest native queued-notice check are
complete with the assistance described above. The follow-up resolves
the measured narrow-layout overlap in Lumi version 8, but no final concept was
selected and complete visual/design acceptance is not established. The latest
helper diagnostic was exercised in the full browser wrapper; the complete
current payload was subsequently loaded and exercised in the native client.
Trial registrations are cleaned up. Exact-revision CI results, including the
pinned release-tool gates and the test-only CodeQL correction, are recorded
separately in the pull request.

Existing-instance reopening through the host menu without a model request was
not established, and stale trial entries remained in the host's cached lists
after verified registration cleanup. The tested recovery followed a
deliberate session clear; native app crashes and interrupted delivery with an
unknown outcome remain separate cases. A
[human pilot](visual-companion-human-pilot.md) with designers and an
implementation partner also remains. Simulated panels
and automated interaction do not establish usability or adoption.

This work does not provide shared concurrent editing, free layout manipulation,
automatic production-code changes, a lossless Figma round trip or recovery of
unsaved typing after closing the sketch. HTML and its descriptor remain the
paired source. The native panel still uses Node and private loopback transport;
project storage currently requires the reviewed Unix locking contract.
There is no hosted, persistent review link for colleagues: a local preview URL
is not a shared design library. Reading saved files without the app is possible,
but independently opening an equivalent interactive preview and collecting
cross-device comments remain separate product requirements.
