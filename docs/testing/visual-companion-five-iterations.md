# Five focused polishing iterations

These rounds use simulated first-time participant, content designer, mobile
participant, keyboard user and implementation-review perspectives. The Chrome
interactions, HTTP interruptions and geometry measurements were actually run.
There were no human study participants, native canvas sessions or model calls.
Data and consumer projects were disposable. Nothing was installed.

## 1. First use, filters and draft recovery

Three reproductions showed a misleading empty list after saving a comment,
reopening an item under **Ordnet**, or keeping a choice under **Åpne**. The
footer offered **Send 1 innspill** while the affected item was hidden.
Successful creation, reopening and workshop actions now reveal their card
under **Alle** and focus it. Ordinary panel opening retains the selected filter.

Five browser cases passed: the three reproductions, a declared adjustment and
a text-draft recovery control. The latter used Enter, Escape and Space to
preview, park, resume, edit and discard. Both fields survived parking, original
text was restored, and nothing was saved or submitted automatically. A
never-sent reopened item retained **Ikke sendt**, without implying an old round.

## 2. Inspectable text and visible errors on small screens

The original text preview changed the heading behind its editor. **Se i
skissen** now hides the editor while preserving the local preview and draft;
**Fortsett å redigere** returns to the proposal field. Initial inspection still
covered the first heading with its control bar. The bar now sits above the
bottom toolbar, with temporary scroll space that is removed on return or reset.

Three permanent cases cover 390×844 and 320×568, including the first heading.
All five sampled points hit the actual heading. After the final spacing polish,
the 320 px heading occupied y129–201 and the smaller heading y169–225; the
focused proposal field occupied y196–284 inside the editor's y67–460 clip.
Undo, Escape and discard restored original text; a new screen stayed blocked
until discard. Separate landscape and actual 200% browser zoom checks also
passed. The retained `keyboard/panel.cjs` script selected 200% in Chrome's
settings: CSS viewport 1440×913/DPR1 became 720×456/DPR2. This result used
browser zoom; setting a smaller viewport and higher device scale alone would
only emulate those dimensions.

A second defect placed error text outside the scrollable editor or workshop
while the field itself stayed visible. Errors now appear beside their field
and reveal both field and explanation. Five permanent keyboard flows passed:
2002-byte notes/remarks, a 2004-byte emoji proposal, and failed comment/keep
saves followed by explicit retry. Fields and errors were visible together;
validation wrote nothing and each retry saved once. The complete workshop also
passed its existing 24 checks and 13 declared-action checks in headed Chrome;
the focused error and independent preview checks ran headless.

## 3. Concurrent release and an older poll

Two tabs held back a release request and an older polling response. Another
tab saved a newer choice before either was delivered. The stale release was
rejected, its written remark survived, and the older poll could not roll back
the newer snapshot. Only a second explicit release used the reviewed revision
and a new operation key. This new browser case passed without a runtime change.

## 4. Capacity and a delayed successful response

A public-API setup filled a disposable queue with 200 synthetic comments. Saving
comment 201 correctly failed but originally recommended retrying the same
request. HTTP 429 now maps to a closed capacity error explaining the limit and
how to preserve text before starting a new session. The browser retained its
draft, and queue/revision stayed unchanged after one explicit attempt.

A separate browser case held a successful save response beyond the actual
12-second timeout. Editing the draft before that response arrived remained safe;
only a new explicit attempt saved the changed text. No automatic retry occurred.
A server regression returned a complete UTF-8 round exceeding 800 KiB within
the CLI read bound, with current status separate, no whole-journal export and an exhausted cursor
response below 1 KiB. Capacity handling accepts no arbitrary server text as UI.

## 5. Preview ownership and screen-generation receipts

Two targeted reproductions found that a saved preview could be confused with a
parked draft on the same element, and that a late successful response from the
old screen could acknowledge an unrelated request in the replacement screen.
Preview state now has an explicit draft owner; HTTP results are checked against
the initiating screen generation before they can affect the current draft.
Both permanent reproductions passed. The final repeat passed all 60 server tests
and all 11 retry browser cases. The generation test covers delayed HTTP success,
failure, JSON parsing and conflict reads; it does not establish general isolation
of every queued WindowProxy message.

## Reproduce the permanent cases

Supply existing installations; the review-cycle fixture uses matching Aksel
React/CSS 8.x packages (recorded runs: 8.19.2) through React SSR. Retry/workshop
fixtures are explicit control wireframes, not Aksel design-quality evidence.

```sh
VC_PLAYWRIGHT_MODULE=/path/to/existing/node_modules/playwright
VC_AKSEL_PROJECT=/path/to/existing/project
for vc_case in first-save-after-filter first-reopen-after-filter \
  first-kept-choice-after-filter first-adjustment-after-filter \
  first-draft-preview-recovery mobile-preview-inspection-390 \
  mobile-preview-inspection-320 mobile-first-heading-preview-320; do
  node scripts/smoke_visual_review_cycle.cjs --case "$vc_case" \
    --playwright-module "$VC_PLAYWRIGHT_MODULE" --browser-channel chrome \
    --aksel-project "$VC_AKSEL_PROJECT" \
    --evidence-dir "/tmp/grillmester-five-rounds/reproduce/$vc_case"
done
for vc_case in release-conflict-with-late-snapshot \
  full-comment-queue-keeps-draft edited-draft-after-accepted-save-timeout \
  parked-draft-versus-saved-preview late-receipt-after-version-change; do
  node scripts/smoke_visual_retry.cjs --case "$vc_case" \
    --playwright-module "$VC_PLAYWRIGHT_MODULE" --browser-channel chrome \
    --evidence-dir "/tmp/grillmester-five-rounds/reproduce/$vc_case"
done
node scripts/smoke_visual_workshop.cjs --case keyboard-errors \
  --playwright-module "$VC_PLAYWRIGHT_MODULE" --browser-channel chrome \
  --evidence-dir /tmp/grillmester-five-rounds/reproduce/keyboard-errors
node --test plugin/skills/design-prototype/tests/server.test.js
```

## Evidence and limits

The final complete review-cycle run passed 12/12 cases, with no browser
exceptions or completed external requests. Geometry waits two animation frames:
an earlier full run sampled synchronous editor hiding before the scheduled
control-bar docking. That failing report and its already-settled screenshot
remain in `final-review-cycle/`; the corrected final run is in
`final-review-cycle-settled/`. No runtime change was needed for this test timing.

Local reports and named screenshots are under `/tmp/grillmester-five-rounds`:
`iteration-1-verified.json`, `iteration-2-verified.json`, the later
`iteration-2-polished/` measurements, `iteration-3/`, `iteration-4-capacity/`,
`iteration-4-timeout/`, `iteration-5/retry-final/`, and
`keyboard/verified-results.json` with its four source reports. Original failures
remain separate. The browser-zoom script is `keyboard/panel.cjs`, with its
preview result in `keyboard/preview-final/preview-zoom-200-results.json`. The tests
close their own browser contexts and servers and omit capability URLs.

These results establish the tested local flows, not real-device usability,
screen-reader compatibility, native-host behavior, crash/restart recovery,
durable storage or cross-session delivery. The temporary scroll-space and
hit-point checks are accompanied by screenshot inspection; they are not an
exhaustive pixel-occlusion proof for every possible prototype.
