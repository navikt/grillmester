---
name: grillmester-tdd
description: "Runs vertical red-green-refactor cycles through a repository's discovered public interfaces and test tooling. Use when test-first or red-green-refactor is explicitly requested, or when a bug fix needs a reproduction test before implementation; use grillmester-integration-tests or grillmester-e2e-tests for ordinary test creation without a TDD request."
license: MIT
---

# Test-driven development

See [tests.md](tests.md) for examples and [mocking.md](mocking.md) for when and how to mock system boundaries.

## Anti-pattern: horizontal slices

**DO NOT write all the tests first and then all the implementation.** That is "horizontal slicing" — treating RED as "write all the tests" and GREEN as "write all the code".

It produces bad tests:

- Tests written in bulk test *imagined* behavior, not *actual* behavior.
- You end up testing the *shape* of things (data structures, function signatures) instead of user-facing behavior.
- The tests become insensitive to real changes — they pass when behavior breaks and fail when everything is fine.
- You lock yourself into a test structure before you understand the implementation.

```
WRONG (horizontal):
  RED:   test1, test2, test3, test4, test5
  GREEN: impl1, impl2, impl3, impl4, impl5

RIGHT (vertical):
  RED→GREEN: test1→impl1
  RED→GREEN: test2→impl2
  RED→GREEN: test3→impl3
```

**The right approach**: vertical slices via tracer bullets. One test → one implementation → repeat. Each test answers what you just learned from the previous cycle.

## Workflow

### 1. Plan

If you are following a plan or task brief from the calling workflow, stick to
the behaviors there. Use domain vocabulary or binding decisions when the
repository exposes them, but do not depend on a particular documentation path.

Discover the test contract before writing: inspect neighboring tests, build
manifests, runner configuration, scripts and CI. Record the framework, test
style, public seam, focused command, broader gate and fixture conventions. Do
not assume Gradle, Kotest, Ktor, Jest, Vitest, pytest, containers or any other
stack choice until repository evidence establishes it.

Before you write code:

- [ ] Clarify with the user which interface changes are needed (new route, new service function, new contract)
- [ ] Clarify which behaviors are to be tested, and prioritize
- [ ] Look for deep modules — small interface, deep implementation — so the service is easy to test from the outside
- [ ] List the behaviors to be tested (not implementation steps)
- [ ] Get the user's approval

Ask: "Which public interface should we expose? Which behaviors matter most to test?"

**You cannot test everything.** Clarify exactly which behaviors matter most. Spend testing effort on critical paths and complex logic — authorization, validation rules, state transitions — not every conceivable edge case.

### 2. Tracer bullet

Write ONE test that confirms ONE thing end-to-end through the public interface:

```
RED:   Write a test for the first behavior → fails
GREEN: Minimal code to make it pass → passes
```

For a new entry point, choose the thinnest production-shaped test supported by
the detected stack. It should prove that the entry point, composition and
observable response or outcome hang together without locking the test to
internal collaborators.

### 3. Incremental loop

For each remaining behavior:

```
RED:   Next test → fails
GREEN: Minimal code → passes
```

Rules:

- One test at a time
- Only enough code to pass the current test
- Do not anticipate future tests
- Keep the tests on observable behavior

Run the discovered focused command while you work:

```bash
<focused-test-command>
echo "exit: $?"
```

A GREEN claim requires fresh evidence in the same message — command + output + exit code. Without it: UNVERIFIED.

### 4. Refactor

When all tests pass, look for [refactoring candidates](refactoring.md):

- [ ] Extract duplication
- [ ] Deepen modules — move complexity behind simple interfaces
- [ ] Apply SOLID where it falls naturally
- [ ] Consider what the new code reveals about existing code
- [ ] Run the tests after each refactoring step

**Never refactor while RED.** Get to GREEN first.

When the implementation is done and green, return the command that was run and
the result to the calling workflow so it can close the verification phase.

## Checklist per cycle

```
[ ] Test describes behavior, not implementation
[ ] Test uses only the public interface
[ ] Test would have survived internal refactoring
[ ] Code is minimal for this test
[ ] No speculative features added
[ ] GREEN proven with fresh command + output + exit code in the same message (otherwise UNVERIFIED)
```

## Bug fixing is TDD

A bug fix starts with a **reproduction test**: write a test that fails because the bug exists (RED), then fix until it turns green (GREEN). That way you have both proven the bug and prevented regression. Never write the fix first.

For a bug that is hard to reproduce (flaky, timing- or environment-dependent): start with `/grillmester-diagnosing-bugs` to build a tight, red-capable repro loop first — the reproduction test here is then the minimized loop.
