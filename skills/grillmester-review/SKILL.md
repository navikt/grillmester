---
name: grillmester-review
description: Self-review the complete task-scoped diff before independent review or delivery. Use after implementation, before a pull request, or when asked to inspect uncommitted work, a branch against a fixed point, or the changes since a named revision.
user-invocable: true
disable-model-invocation: false
---

# Review the complete task diff

## Establish the review boundary

Read the acceptance criteria, locked decisions, and repository instructions that govern the task. Resolve the stated base or fixed point, then account for staged, unstaged, committed, and untracked changes in scope. Read every new untracked file in full because ordinary diff output omits it.

Stop when the diff is empty, the base is ambiguous, or unrelated work cannot be separated safely. Do not review from the implementation summary or memory when primary evidence is available.

## Review six axes separately

1. **Correctness** — trace changed control and data flow; check errors, state transitions, cleanup, concurrency, and failure handling.
2. **Regression** — find affected callers, contracts, shared defaults, migrations, and behavior outside the immediate edit.
3. **Edge cases** — test relevant empty, missing, malformed, repeated, concurrent, timeout, retry, and partial-failure cases.
4. **Requirement coverage** — map every acceptance criterion and locked decision to concrete code or test evidence.
5. **Repository standards** — check the repository's established architecture, naming, language, test, documentation, and delivery rules.
6. **Scope** — require every hunk to serve the task and identify requested behavior that the diff does not implement.

When the change touches personal or confidential data, authentication or authorization, secrets, logging, network trust, external integrations, deployment permissions, or another security boundary, invoke and apply `grillmester-security-review`.

## Verify and report

Discover deterministic gates from repository instructions, build files, test configuration, and CI rather than assuming a toolchain. Run the smallest relevant checks and any required final gates after the last edit. Record commands, relevant results, and exit codes; distinguish fresh evidence from anything stale or unverified.

Report material findings first, ordered by consequence. For each finding, give the affected path and line when available, the concrete failure mode, and the smallest useful correction. End with acceptance-criterion coverage, gate evidence, and remaining uncertainty. A clean review must still state what was inspected and what the evidence does not prove.
