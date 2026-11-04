---
name: tdd
description: "Build or fix behavior test-first with few, well-placed tests. Use when writing or adding unit, integration, end-to-end (e2e) or regression tests, or building a feature or fixing a bug test-first; use `diagnosing-bugs` when the cause is unclear."
---
# Test-driven development

> **OpenCode:** Skill names below are exact IDs from the active catalog, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

TDD is the red → green loop: a failing test, then the least code that makes it
pass. This skill keeps the loop tight and the kept tests few and well placed.
Use the repository's test framework, naming, fixtures and commands; find them
in neighboring tests, build files and CI.

## Plan the tests first

Before the first test, write a short test plan: the **seam** you test at and
the tests you intend to keep, one line each with what the test catches and what
it misses. Choose the highest seam that is still fast enough for the loop; the
ideal is one seam per feature. [test-boundaries.md](test-boundaries.md) helps
choose between the module interface, a real adapter and the running
application.

State the plan and continue; starting a TDD cycle needs no approval. Ask only
when the seam or the tests to keep are an unsettled material choice, such as a
new test harness, an end-to-end test, or a listed risk you propose to leave
untested, and then inside an open grilling round if there is one.

## Keep only tests worth keeping

The loop and the kept tests are different things. Use typechecks, focused runs
and throwaway checks freely while you work, and keep a test only when it
protects one of these:

- an acceptance criterion;
- a real risk: access control, personal data, money or benefits, an external
  contract, input validation, or data loss or duplication (migrations,
  idempotency, concurrency);
- a non-obvious rule or state transition;
- a fixed bug, whose regression test always stays.

Extend an existing test or add a row to a table-driven test before creating a
new test file. Checklists in other skills list cases to verify, not tests to
keep: handle them in the code, and keep a test only when it meets the list
above. Delete throwaway checks before delivery, and leave existing tests in
place unless the user asks to change them.

Use synthetic data in tests; never real personal data, such as a fødselsnummer,
or secrets.

## What a good test is

A good test verifies behavior through a public interface, so the code can
change while the test stays. See [tests.md](tests.md) for patterns and
[mocking.md](mocking.md) for mocking only at system boundaries.

Avoid:

- **Implementation-coupled tests:** mocking internal collaborators, testing
  private methods, or checking a side channel instead of the interface.
- **Tautological tests:** an expected value computed the way the code computes
  it. Take expected values from an independent source: a literal, a worked
  example or the spec.
- **Horizontal slicing:** writing all tests first and then all code. Work one
  vertical slice at a time.
- **Test bloat:** near-duplicate tests, one test per trivial edge case, tests
  of trivial code, and snapshots nobody reads.

## Rules of the loop

- **Red before green.** Watch the new test fail for the right reason, then
  write only enough code to pass it. For behavior that already exists, show
  that each new test can fail, for example by briefly breaking the code, before
  trusting it.
- **One slice at a time.** One behavior, one test, one minimal change.
- **Refactor only when green**, using [refactoring.md](refactoring.md), and
  rerun the focused tests after each step.
- **Bug fixes start red.** Reproduce the bug in one test at the seam where it
  actually happens, then fix it.

Run the focused tests while you work and the repository's broader test gate
before reporting done. Report the commands, their results and exit codes; an
unrun check is unverified.
