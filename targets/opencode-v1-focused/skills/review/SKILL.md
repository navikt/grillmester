---
name: review
description: "Review a complete diff for correctness, fit to the requirements and the repository's standards. Use after implementing, when asked to review changes or a pull request, or as the method of an independent reviewer; use `security-review` for security-specific analysis."
---
# Review

> **OpenCode:** Skill names below are exact IDs from the active catalog, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Review the complete task diff in three passes, one per lens, and report the
findings per lens so one kind of finding does not hide another. The writer runs
it as a self-review before delivery and fixes in-scope findings; an
independent reviewer runs the same lenses read-only and reports them.

When the user wants a walkthrough rather than a review, suggest
the full-context guided human review workflow.

## Establish the boundary

Read the acceptance criteria, locked decisions and the repository's
instruction files. Resolve the base or fixed point, then account for staged,
unstaged, committed and untracked changes in scope, and read every new file in
full because an ordinary diff omits it. Stop when the diff is empty, the base
is ambiguous, or unrelated work cannot be separated. Review the actual diff and
files, not a summary or a memory of the intended change.

## Lens 1: Correctness

Trace the changed control and data flow: errors, state transitions, cleanup,
concurrency and failure handling. Find affected callers, contracts, shared
defaults and migrations outside the edit. Check that the code handles the
relevant empty, missing, malformed, repeated, concurrent, timeout, retry and
partial-failure cases.

## Lens 2: Requirements

Map every acceptance criterion and locked decision to concrete code or test
evidence. Report what is missing or partial and what looks implemented but
wrong. Check that every hunk serves the task, and report behavior nobody asked
for.

## Lens 3: Standards

Check the repository's documented rules: its instruction files, coding
standards or contributing guide, and conventions its linters do not enforce.
Then check the change against the [smell baseline](./references/smells.md); a
smell is a judgement call, never a hard violation, and a documented repository
rule overrides it. Check the tests against the keep rule in `tdd`: flag a
missing test for a real risk, and flag test bloat.

When the change touches personal or confidential data, authentication or
authorization, secrets, logging, network trust, external integrations,
deployment permissions or another security boundary, load `security-review`
as well.

## Correct, verify and report

As the writer, fix in-scope findings without silently widening scope, then run
the repository's required gates after the last edit, using commands from its
instructions, build files and CI, and record the commands, results and exit
codes. As a read-only reviewer, report the findings and judge the supplied
evidence; return `MISSING_EVIDENCE` when a material claim lacks fresh proof.

Report findings per lens, most consequential first. Give each finding the path
and line when available, the concrete failure mode and the smallest useful
correction. A finding is `material` when it breaks correctness, an acceptance
criterion, a locked decision, a security or data rule or a mandatory rule in
the repository's instructions, or leaves a claimed result unproven; otherwise
it is `minor`. End with acceptance-criterion and decision coverage, gate
evidence, and what the evidence does not prove. A clean review still states
what was inspected.
