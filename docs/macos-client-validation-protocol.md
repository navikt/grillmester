# macOS client validation protocol v1.0

This protocol is the narrow runtime and client entry point for a `0.3.0`
release. It is for **macOS only** and covers **Copilot CLI**, **Copilot App**,
and **VS Code**. It does not run model scenarios in CI.

Use [the consumer-pilot runbook](consumer-pilot-runbook.md) as the authority
for the identity chain (section 4), role scenarios (section 5), controlled and
rejected writes (section 6), rollback (section 7), and the exit gate (section
8). This protocol records the client-specific evidence without duplicating that
runbook.

## 1. Scope and exclusions

Run one exact immutable RC against:

- one disposable synthetic fixture;
- one frontend repository; and
- one backend repository.

When a real repository is needed, use a clean, isolated worktree. Never run a
write scenario in an active developer worktree. The same RC tag, catalog SHA,
and source SHA must be recorded for every client. A client that cannot resolve
that identity is `UNVERIFIED` or `FAIL`, never `PASS`.

This protocol excludes execution of the full client matrix, all 42 individual
skills, Windows, Linux, cloud agent, and OpenCode.

## 2. Prepare the run

1. Select the exact immutable RC and record its tag, catalog SHA, and source
   SHA in the evidence file.
2. Create the disposable fixture and clean isolated worktrees for the frontend
   and backend repositories as applicable.
3. Start a fresh client session for each client and use the identity chain in
   consumer-pilot runbook section 4. Record the client version, RC tag, catalog
   SHA, source SHA, and model resolved by that client; do not trust an agent's
   self-report alone.
4. Start from the previous reviewed version when an update or rollback scenario
   requires it. Follow the client-specific update and rollback instructions in
   the [installation guide](installation.md) and
   [release runbook](release-runbook.md). Restart the client after rollback
   before recording its result.

## 3. Per-client validation

Perform every item below separately in Copilot CLI, Copilot App, and VS Code.
Do not infer one client's result from another.

| Scenario | Required observation |
| --- | --- |
| Installation and discovery | The exact plugin identity and each public agent are discoverable. |
| Update | The client reaches the selected RC and its resolved identity is recorded. |
| Rollback | The client returns to the previous reviewed version without moving an immutable tag. |
| Restart after rollback | A newly started session resolves the rolled-back version. |
| Grillmester | Complete the bounded role scenario from consumer-pilot runbook section 5. |
| Barista | Complete the bounded role scenario from consumer-pilot runbook section 5. |
| Designer | Complete the frontend design scenario from consumer-pilot runbook section 5. |
| Doctor Who | Complete the read-only product scenario from consumer-pilot runbook section 5. |

Copilot CLI is the update reference, but its result does not prove App or VS
Code behavior. Copilot App's marketplace deep link cannot itself prove an
immutable RC; record the resolved catalog and source identity or classify it as
`UNVERIFIED` or `FAIL`.

## 4. Harness-parity core

For each client, run and record one harness-parity scenario that explicitly
covers all of the following:

1. `/grillmester-grilling`;
2. automatic skill routing;
3. Wayfinder discovery and delegation;
4. the handoff `Grillmester → Kokk → Grill-inspektør`;
5. Visual Companion;
6. one approved, harmless write in the disposable fixture; and
7. one rejected write with no file, Git ref, or external-resource side effect.

Use the role and write constraints in consumer-pilot runbook sections 5 and 6.
Record the observed tools, approval decisions, and side effects rather than
prompts or transcripts.

## 5. Evidence and disposition

Copy `docs/release-evidence-template.json`, fill one `clientResults` entry for
each client, and aggregate them into one `releaseVersion: "0.3.0"` evidence
file. `protocolVersion: "1.0"` and `schemaVersion: 1` are part of the contract.
Each client entry records its version and resolved release identity. Each
scenario records its result, observed tools and approvals, side effects, and
deviations. See
`docs/release-evidence-0.3.0-dry-run.json` for synthetic, non-sensitive
example data only.

Never store prompts, transcripts, secrets, personal data, or sensitive
diagnostics in release evidence. Use terse synthetic scenario labels and
non-sensitive observations.

Stop and classify the release evidence as blocked for any of these hard
blockers:

- an unexpected write;
- an approval or stop-boundary violation;
- sensitive data in the evidence;
- a wrong plugin or agent identity; or
- a failed rollback.

The maintainer decides the disposition of every other deviation. Existing CI
structure and installation gates remain separate from this protocol; they
validate documentation and package contracts, not client model behavior.
