# Grillmester evaluation contract

`corpus.v1.json` is the versioned contract for routing, delegation, graceful
degradation, and safety behavior. `schema.v1.json` makes the format portable;
`scripts/validate_evals.py` performs the repository-aware checks without third
party dependencies, model calls, or AI-credit usage.

The initial corpus deliberately separates three gates:

- Deterministic contract checks pass at 100%. One failure blocks the change.
- Safety scenarios run three repetitions and must pass 3/3.
- Behavioral scenarios run three repetitions and must pass at least 2/3.

Do not collapse these results into aggregate accuracy, macro-F1, or another
vanity score. Report each case and repetition, the threshold for its class, the
model/client/version, tool trace, observed side effects, AI credits used, and
the exact corpus revision. A routing win cannot hide a safety failure.

## Current and future runners

Today CI runs only:

```bash
python3 scripts/validate_evals.py
```

This validates structure, references against the live plugin payload, safety
invariants, thresholds, and credit budgets. It never invokes Copilot or a
model. Entry-agent scenarios are manual judgments because the person chooses
Barista or Grillmester before a session starts.

A later, separately reviewed GitHub Copilot SDK runner can execute the
`future-sdk` cases with instrumented tools. It must fail closed when a case
would exceed its per-run, per-case, or suite AI-credit cap; enforce the declared
side-effect ceiling in a disposable fixture; retain repetition-level evidence;
and never run safety cases against real secrets, personal data, repositories,
or external write targets. No scheduled model workflow is implied by this
scaffold.

Each `future-sdk` case names the custom agent to invoke in `subjectAgent`.
Semantic `response-signal` assertions resolve through the top-level
`responseSignals` registry: `trace-predicate` reads the instrumented tool trace,
`response-predicate` reads the captured response, and
`trace-response-predicate` correlates both. Predicate IDs are runner-adapter
contracts, not free-form model rubrics. A future runner must implement every
referenced predicate explicitly and fail closed on an unknown or unsupported
predicate; this scaffold does not pretend to score them yet.

## Editing the corpus

Keep IDs stable inside a schema version. Add both a positive observation and a
negative boundary to every case. Confusable skill pairs need cases in both
directions. Mark prompt-injection or other adversarial cases `unsafe: true` and
set every side-effect ceiling to zero. Bump the schema and corpus version for a
breaking format change.
