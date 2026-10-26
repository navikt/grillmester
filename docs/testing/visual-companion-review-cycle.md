# Complete review cycles

This round tests what happens after feedback is sent: a new screen arrives,
another tab changes the same choice, or the reader resumes after comments were
removed or reopened. Service-design, content-design and busy mobile-user
perspectives are simulated. The browser interactions and measurements below
were actually executed; there were no human study participants.

## Reproduce

Use existing Playwright, Chrome and matching Aksel v8 packages:

```sh
node scripts/smoke_visual_review_cycle.cjs \
  --playwright-module /path/to/existing/node_modules/playwright \
  --browser-channel chrome \
  --aksel-project /path/to/existing/project \
  --evidence-dir /tmp/grillmester-review-cycle
```

The script installs nothing. Each case creates an isolated temporary consumer,
uses synthetic appointment data and real Aksel components rendered through
React SSR, then closes its browser context and local server. Reports contain
no capability URLs. Use `--case` with a name from the table for an affected
rerun. The recorded run used Aksel 8.19.2 and headless Chrome.

| Case | Acceptance criteria |
| --- | --- |
| `mobile-sent-context-next-version` | After exploring a state, sending a comment and receiving a reply, automatic replacement stays blocked by the local view. The explicit reset action opens the new screen. A written remark still blocks replacement. Original context and reply survive; one Tab reaches the new screen's first action. |
| `mobile-sent-context-next-version-320` | Repeat the same interaction at 320 px; the reset action and toolbar remain within the viewport. |
| `stale-tab-same-part-wishes` | An older tab and the revised tab both keep the same part. Each saves its own wish on the screen it was made on, with that screen's values; neither replaces the other, no kept choice is created and both reach the next explicit round. |
| `reversal-and-delayed-reader` | Remove one sent comment and reopen another, then submit again across two source screens. A reader starting at zero receives the unchanged first round, then the second. Current status is separate. An old-round reply is rejected, removal retains focus and a third screen preserves the latest reply. |

## Findings and refinements

The initial mobile run had no unsent feedback but could not show the answered
version because its explored state remained locally changed. **Nullstill og
vis ny versjon** now makes that reset explicit. A written remark, unfinished
comment, pending save or unsent saved feedback still protects the old screen.
The case asserts the blocked state before trying the explicit action, so it
cannot pass by skipping the recovery path.

The first two-tab run let an old draft silently replace a newer unsent choice
and its remark. Per-decision revision checks now preserve both intentions and
show the newer saved values. **Bruk mitt valg i stedet** uses the revision
displayed in that conflict; another change produces another conflict.
**Forkast mitt utkast** changes only local state. The three-tab follow-up
observed three conflicts, one shared decision ID and an unchanged accepted
direction until the next deliberate submission. [ADR 0025](../adr/0025-behold-som-innspill-og-juster-visning-i-prov.md)
later made **Behold denne delen** an ordinary wish, so this conflict flow no
longer exists; the replacement case checks that two tabs save two wishes. Kept
choices were removed, as they were never released.

The original mutable list could lose or change a submitted round before the
reader fetched it. The journal in ADR 0021 preserves that round and gives its
current comment statuses separately. The follow-up delivered two exact rounds
despite removal, reopening and resubmission. **Ny runde ikke sendt** distinguishes
the reopened draft from its earlier **Sendt i runde 1** badge.

| Measurement | Result |
| --- | --- |
| Completed logical scenarios / viewport runs | 3 / 4 |
| Mobile viewports | 390 × 844 and 320 × 844 px |
| Reset action | 162.22 × 36 px in both viewports |
| Toolbar at 390 / 320 px | 374 × 86 / 304 × 86 px, x = 8 px |
| Tab from conflict explanation to replacement | 1, in all three conflicts |
| Tab to first action after explicit version reset | 1, in both mobile runs |
| Delayed reader: comments in round one / two | 2 / 2 |
| Browser exceptions / completed external resource requests | 0 / 0 |

Named screenshots and per-case JSON reports are written to the requested
evidence directory. The reviewed follow-up reports are also collected in
`/tmp/grillmester-review-cycle/review-cycle-verified-results.json`; original
failure evidence remains separate. Images were visually inspected for the
conflict state, reopened comment and narrow reset toolbar.

## Related regression coverage and limits

`scripts/smoke_visual_retry.cjs` has browser cases that deliberately lose a
successful HTTP response. A keep wish retries as one comment, and a retry reuses
the original operation instead of saving a second copy. The cases passed without
browser exceptions or completed external resource requests.

The server suite covers immutable rounds, cursor validation, current status,
old-round reply rejection, decision revisions, receipt replay and atomic
failure at the 200-round and 2 MiB limits. Capacity errors retain the drafts;
the server does not evict old rounds.

Mixed 1440/390 px tabs in one headless context reproduced an emulation
hit-testing problem. The three-tab protocol case therefore uses equal-width
tabs; mobile cases use fresh separate contexts. This was not classified as a
product defect. These checks do not establish screen-reader compatibility,
real-device usability, native-host behavior, restart recovery or durable
cross-session delivery. No additional native-app model calls were made.
