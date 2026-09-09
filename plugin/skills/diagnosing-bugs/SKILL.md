---
name: diagnosing-bugs
description: "Diagnose failures, hangs, flakes or performance regressions from reproduction, code and runtime evidence. Use when the cause is unclear; use `tdd` for an established fix and `nav-troubleshoot` when the missing evidence is in a deployed Nais environment."
---

# Diagnosing Bugs

Establish the failing boundary, test the most plausible causes and verify the
fix. Use the sequence below as a preferred loop, adapting it to the evidence
and access available. Distinguish observations, hypotheses and unverified work.

Use the active task or calling brief as scope. If the repository advertises
domain documentation or binding decisions, read only what touches the symptom;
the workflow does not depend on any particular documentation path.

Before choosing a command or test shape, discover the repository's runtime and
test contract from manifests, scripts, neighboring tests, CI configuration and
local run documentation. Record the detected language, framework, test runner,
focused command, application boot command and available fixtures. Do not assume
Gradle, Kotest, Ktor, Node, pytest, containers, Kafka or a database until
repository evidence establishes them.

Before showing or saving command output, a HAR, log, trace or event, replace
secrets, auth headers, cookies, tokens and personal or sensitive data with
`<REDACTED>`; retain only signal lines. Keep required credentials in approved
environment variables, never in commands, scripts or fixtures. If redacted
evidence cannot establish the boundary, return `Status: NEEDS_CONTEXT` and name
the approved evidence or access needed instead of asking for raw data.

If the symptom is a runtime/platform problem in production, use the platform's
approved diagnostic tooling to establish the failing boundary, then return here
for the reproduction and fix discipline. When the app runs on NAIS,
`nav-troubleshoot` can supply Nav-specific diagnostic trees.

## Phase 1 — Build a feedback loop

A repeatable signal for the exact symptom makes experiments and regression
tests stronger. Read relevant code, logs and configuration to find that signal;
prefer a runnable reproduction when it is feasible.

### Ways to construct one — try them roughly in this order

1. **Failing test** at the seam that reaches the bug — unit, integration, or
   application test in the framework already used by the repository. Run the
   discovered focused command and assert the exact symptom.
2. **HTTP, CLI, or protocol script** against the repository's discovered local
   boot path, diffing status, output, or response against known-good behavior.
3. **Replay of a captured event.** Save a sanitized representative message,
   HTTP payload or event artifact and play it through the code path in isolation.
4. **Throwaway harness.** Spin up the smallest subset that reaches the failing
   path, reusing the repository's existing fakes, fixtures, embedded services,
   or container strategy where evidence supports them.
5. **Property / fuzz loop.** If the bug is "sometimes wrong output", run 1000 random inputs and look for the failure mode.
6. **Bisection harness.** If the bug appeared between two known states (commit, dataset, version), automate "boot at X, check, repeat" so you can `git bisect run` it.
7. **Differential loop.** Run the same input through the old vs. the new version (or two configurations) and diff the output.
8. **HITL bash script.** Last resort. If a human has to click/act, drive _them_ with `scripts/hitl-loop.template.sh` so the loop stays structured. Only sanitized signal output is fed back to you.

### Tighten the loop

Treat the loop as a product. Once you have _a_ loop, **tighten** it:

- Can I make it faster? (Cache setup, skip unrelated initialization, use the
  test runner's focused selector, reuse an existing fixture.)
- Can I make the signal sharper? (Assert on the specific symptom, not "did not crash".)
- Can I make it more deterministic? (Pin time, seed randomness, isolate mutable
  state, and replace uncontrolled network access at an established seam.)

Use the fastest reliable loop the repository supports. A slower integration
test can be the right boundary; speed is an optimization, not an entry gate.

### Non-deterministic bugs

Measure the failure rate and seek a controlled trigger using bounded repeated
runs, concurrency or timing controls in an isolated test environment. Record
the number of runs and failures; a few passing runs do not prove a flake fixed.

### When you genuinely cannot build a loop

State what could not be reproduced and what you tried. Continue bounded code,
configuration and sanitized log analysis to test specific explanations or
design targeted instrumentation. Label inference and missing evidence; static
analysis does not prove a runtime reproduction or a successful runtime fix.

Ask only for evidence or access needed for the next dependent step, such as a
sanitized trace or an approved environment. Reuse existing authorization for
local investigation and reversible instrumentation within scope. Production
changes still require explicit authority. Lack of runtime access does not
block independent analysis or an evidence-supported local patch.

### Evidence for a reproduction claim

Name the command or human-assisted steps actually run and record sanitized
signal output. The check must exercise the real failing path and detect the
user's exact symptom. Report determinism or measured failure rate and any
environment limits. An unrun command is a proposed check, not reproduction
evidence. `scripts/hitl-loop.template.sh` can structure manual steps when useful.

## Phase 2 — Reproduce + minimize

When a runnable loop is available, run it and confirm the observed failure.

Confirm:

- [ ] The loop produces the failure mode **the user** described — not some other bug that happens to be nearby. Wrong bug = wrong fix.
- [ ] The bug is reproducible across several runs (or, for non-deterministic bugs, reproducible at a high enough rate to debug against).
- [ ] You have captured the exact symptom (error message, wrong output, slow timing) so later phases can verify that the fix actually hits it.

### Minimize

Once it is red, shrink the repro to the **smallest scenario that still goes red**. Cut inputs, callers, config, data and steps **one at a time**, rerunning the loop after each cut — keep only what is load-bearing for the bug.

Why bother: a minimal repro shrinks the hypothesis space in phase 3 (fewer moving parts left to suspect) and becomes the clean regression test in phase 5.

Minimize enough to separate plausible causes and support a meaningful test.
Do not delay a decisive experiment solely to obtain the smallest possible
reproduction. Without a runnable loop, narrow the relevant code and evidence
instead, preserving uncertainty about the runtime trigger.

## Phase 3 — Hypothesize

Rank the explanations supported by the evidence. Consider alternatives when
the cause remains ambiguous; do not invent extra hypotheses to fill a quota.

Each hypothesis must be **falsifiable**: state the prediction it makes.

> Format: "If <X> is the cause, then <changing Y> will make the bug disappear / <changing Z> will make it worse."

If you cannot state the prediction, the hypothesis is a gut feeling — discard it or sharpen it.

Share the leading explanation and next discriminating check when useful.
Continue authorized experiments; this progress update is not an approval gate.

## Phase 4 — Instrument

Each probe must map to a specific prediction from phase 3. **Change one variable at a time.**

Tool preference:

1. **Debugger / REPL inspection** if the environment supports it. One breakpoint beats ten log lines.
2. **Targeted logging** at the boundaries that separate the hypotheses, using
   the repository's established logging framework.
3. Never "log everything and grep".

**Tag every debug log** with a unique prefix, e.g. `log.info("[DEBUG-a4f2] ...")`. Cleanup at the end becomes a single grep. Untagged logs survive; tagged logs die.

**PII boundary (Nav):** never log national identity numbers, tokens, names or special categories of personal data — not even in temporary debug logs. Log IDs/correlation (`Nav-Call-Id`, `callId`), not personal data.

**Perf branch.** For performance regressions, logs are usually the wrong tool.
Establish a baseline with the profiler, metrics, benchmark or query-plan tooling
already supported by the stack, then bisect. Measure first, fix afterwards. On
a managed platform, use its approved observability tooling to establish the
boundary before changing application code.

## Phase 5 — Fix + regression test

Write the regression test **before the fix** — but only if a **correct seam** exists for it.

A correct seam is one where the test hits the **real failure pattern** as it occurs at the call site. If the only available seam is too shallow (a single-caller test when the bug requires several callers, a unit test that cannot replicate the chain that triggered the bug), a regression test there gives false confidence.

If no suitable seam is available, report whether the limitation is architecture,
fixtures, access or an unknown trigger. Avoid a test that cannot catch the bug.
An evidence-supported patch can still be prepared with the available checks;
report the missing regression proof and the next useful verification.

If a correct seam exists:

1. Turn the minimized repro into a failing test at that seam.
2. Watch it fail.
3. Apply the fix.
4. Watch it pass.
5. Run the phase 1 loop against the original (un-minimized) scenario.

Use the repository's focused test command and proportionate broader gates.
Report commands actually run, relevant results and exit codes. Separate passing
checks from any original runtime scenario that remains unverified.

## Phase 6 — Cleanup + post-mortem

Before delivery:

- Rerun the original reproduction and regression test when available; state
  explicitly which scenarios could not be verified.
- Remove temporary instrumentation and harnesses introduced by this task,
  unless the user requested a diagnostic artifact for the next investigation.
- Report the established cause or leading explanation, the patch if any,
  checks run and remaining uncertainty. Do not call an unverified runtime
  outcome fixed or the investigation complete when dependent work remains.

**Then ask: what would have prevented this bug?** If the answer involves an
architectural change (no good test seam, entangled callers, hidden coupling),
carry the finding forward via `/grilling`. Use
`/architecture-review` for consequential architecture questions.
When the agreed fix changes lasting concepts or qualifying decisions, use
`/grill-with-docs` and `/domain-modeling` within the authorized task and the
repository's documentation policy. Do not require the user to select the same
route again. Keep additional architectural proposals as candidates until the
user chooses them. Base those recommendations on the boundary established by
the investigation, without turning every fix into an architecture exercise.

## Runtime/platform symptoms

For a production-only failure, identify the layer before changing code:
deployment/startup, identity or authorization, messaging, database, or
observability. Use only repository-approved platform tools, keep the pass
read-only until the boundary is known, and then return to phases 5–6 here.
Always propose the least invasive fix first. Production configuration changes,
workload restarts and managed-resource changes require explicit authorization;
reuse it when the user already approved the same concrete action.

`nav-troubleshoot` gives deeper NAIS trees for pod startup, Nav
identity, Kafka, Cloud SQL and observability. If required live platform evidence
is unavailable, name the missing capability or owner documentation instead of
inventing Nav behavior.

## Related skills

- `/grilling` — stress-test the design when the bug exposes a design gap;
  recommend the documented route when needed
- `auth-overview` — Azure AD / TokenX /
  ID-porten / Maskinporten / Texas when those mechanisms are involved
- `/architecture-review` — review architectural changes that would
  have prevented the bug
