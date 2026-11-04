---
name: diagnosing-bugs
description: "Diagnose hard bugs, flakes and performance regressions with a tight feedback loop that goes red before any fix. Use when something is broken, failing or slow and the cause is unclear; use `tdd` for an established fix and `nav-platform` when the evidence is in a deployed Nais environment."
---

# Diagnosing Bugs

A discipline for bugs whose cause is unclear: build a loop that goes red on
this bug, shrink it, test ranked hypotheses, then fix it with a regression
test. Skip a phase only with a stated reason, and keep observations,
hypotheses and unverified work apart.

Use the repository's runtime, test runner and commands; find them in build
files, scripts, neighboring tests, CI and local run documentation. Read only
the domain documentation and decisions that touch the symptom.

**Redact first.** Every command, output and artifact you show uses
`<REDACTED>` for secrets, tokens, cookies and personal data, and credentials
stay in approved environment variables. Filter operational output through an
approved path before it reaches the model; never fetch raw data to redact it
afterwards. Before reading logs, traces, HAR files, events or other
operational output, follow [the data-access rules](references/data-access.md).

If the symptom is a runtime/platform problem in production, use the platform's
approved diagnostic tooling to establish the failing boundary, then return here
for the reproduction and fix discipline. When the app runs on NAIS,
`nav-platform` can supply Nav-specific diagnostic trees.

## Phase 1 — Build a feedback loop

**This is the skill.** With a tight loop that goes red on this bug, the cause
will be found; without one, every conclusion from reading code stays
inference. Spend disproportionate effort here.

### Ways to construct one, roughly in this order

1. **Failing test** at the seam that reaches the bug, asserting the exact
   symptom.
2. **HTTP, CLI or protocol script** against the local boot path, diffing the
   response against known-good behavior.
3. **Replay of a captured event:** a sanitized message, payload or event played
   through the code path in isolation.
4. **Throwaway harness:** the smallest subset of the system that reaches the
   failing path, reusing the repository's fakes and fixtures.
5. **Property or fuzz loop** for output that is sometimes wrong.
6. **Bisection harness** between two known states, so `git bisect run` can
   drive it.
7. **Differential loop:** the same input through the old and new version, or
   two configurations, with the outputs diffed.
8. **Human-in-the-loop script** as a last resort: drive the person with
   `scripts/hitl-loop.template.sh` and feed back only sanitized signal.

### Tighten the loop

Make it faster (focused selectors, cached setup), sharper (assert the specific
symptom, not "did not crash") and more deterministic (pinned time, seeded
randomness, isolated state). A slower integration test can still be the right
boundary; speed is an optimization, not an entry gate.

For a flaky bug, raise the reproduction rate with bounded repetition,
parallelism or narrowed timing in an isolated test environment until it is
debuggable. Record the number of runs and failures; a few passing runs do not
prove a flake fixed.

### Done when the loop is red

Phase 1 is done when you can name one command you have already run, shown
redacted, that:

- drives the real failing path and asserts the user's exact symptom;
- gives the same verdict every run, or a pinned, high failure rate;
- is as fast as the failing boundary allows, ideally seconds;
- runs unattended, or through the human-in-the-loop script.

If you cannot build such a loop, say so, list what you tried, and ask for the
smallest thing that would help: access to an environment that reproduces it, a
redacted captured artifact, or permission for temporary production
instrumentation. Meanwhile continue bounded code, configuration and permitted
log analysis, labelled as inference; static analysis does not prove a runtime
cause or fix. Local investigation and reversible local instrumentation within
the task are already authorized; production changes need explicit authority.
Missing runtime access does not block an evidence-backed local patch.

## Phase 2 — Reproduce and minimize

Run the loop and confirm that it shows the failure the user described, not a
nearby one, and capture the exact symptom. Then shrink the scenario one element
at a time, keeping only what is load-bearing: removing it turns the loop
green. A minimal reproduction narrows the hypotheses and becomes the
regression test. Stop once the remaining elements separate the plausible
causes; do not delay a decisive experiment for the smallest possible
reproduction. Without a loop, narrow the relevant code and evidence instead.

## Phase 3 — Hypothesize

Rank 3–5 falsifiable hypotheses before testing any of them; a single
hypothesis anchors on the first plausible idea. Give fewer when the loop
already isolates the cause, and never invent one to fill the count. State the
prediction for each: "If X is the cause, then changing Y makes the bug
disappear." Show the ranked list, since the user may rule some out, and
continue without waiting for an answer.

## Phase 4 — Instrument

Map each probe to one prediction and change one variable at a time. Prefer a
debugger or REPL, then targeted logs at the boundaries that separate the
hypotheses; never log everything and grep. Tag every temporary log with a
unique prefix, such as `[DEBUG-a4f2]`, so cleanup is one search.

**PII boundary (Nav):** never log national identity numbers, tokens, names or
special categories of personal data, not even in temporary debug logs. Log IDs
and correlation fields such as `Nav-Call-Id` instead.

For a performance regression, measure a baseline with the stack's profiler,
metrics, benchmark or query plan, then bisect; measure before you fix.

## Phase 5 — Fix + regression test

Write the regression test before the fix, at a **correct seam**: one where the
test exercises the real failure pattern as it occurs at the call site. A seam
too shallow to reproduce the chain gives false confidence. When none exists,
you may still apply an evidence-backed fix; report the missing regression
proof and why (architecture, fixtures, access or an unknown trigger) as a
finding.

1. Turn the minimized reproduction into a failing test at that seam.
2. Watch it fail. If you forced the red by changing code or a fixture, diff
   against a pristine copy to prove the change landed before you trust it.
3. Apply the fix.
4. Watch it pass.
5. Rerun the Phase 1 loop against the original, unminimized scenario.

The regression test stays; the rest of the loop is throwaway unless it is that
test. Run the focused tests and the repository's broader gate, and report the
commands, results and exit codes.

## Phase 6 — Cleanup

Before delivery:

- the original reproduction no longer reproduces;
- the regression test passes, or the missing seam is documented;
- all `[DEBUG-...]` instrumentation and throwaway harnesses are removed, unless
  the user asked to keep a diagnostic artifact;
- the established cause, or the leading explanation when it is not proven, is
  stated in the commit, pull request or report, so the next person debugging
  learns from it.

State plainly which scenarios could not be verified, and do not call an
unverified runtime outcome fixed.

**Then ask: what would have prevented this bug?** Answer in one or two lines.
When the answer is an architectural gap (no good test seam, entangled callers,
hidden coupling), recommend `/improve-codebase-architecture` or
`/architecture-review`; when the fix changes a domain term or an ADR-worthy
decision, recommend recording it through `domain-modeling`. Leave each as a
recommendation until the user chooses it; not every fix needs an architecture
exercise.

## Runtime/platform symptoms

For a production-only failure, identify the layer before changing code:
deployment/startup, identity or authorization, messaging, database, or
observability. Use only repository-approved platform tools, keep the pass
read-only until the boundary is known, and then return to phases 5–6 here.
Always propose the least invasive fix first. Production configuration changes,
workload restarts and managed-resource changes require explicit authorization;
reuse it when the user already approved the same concrete action.

`nav-platform` gives deeper NAIS trees for pod startup, Nav
identity, Kafka, Cloud SQL and observability. If required live platform evidence
is unavailable, name the missing capability or owner documentation instead of
inventing Nav behavior.

## Related skills

- `/grilling` — stress-test the design when the bug exposes a design gap;
  propose records through `domain-modeling` when needed
- `nav-platform` — runtime problems on NAIS, and Azure AD / TokenX /
  ID-porten / Maskinporten / Texas when those mechanisms are involved
- `/architecture-review` — review architectural changes that would
  have prevented the bug
