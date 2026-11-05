---
name: tdd
description: "Build or fix behavior test-first with few, well-placed tests. Use when writing or adding unit, integration, end-to-end (e2e) or regression tests, or building a feature or fixing a bug test-first; use `diagnosing-bugs` when the cause is unclear."
---

# Test-driven development

TDD is the red → green loop: a failing test, then the least code that makes it
pass. This skill keeps the loop tight and the kept tests few and well placed.
Use the repository's test framework, naming, fixtures and commands; find them
in neighboring tests, build files and CI.

## Read first

1. Find every row below that the task touches.
2. Read those references before you edit, answer or run a command.
3. Name the references you read when you report.

| The task touches | Read |
|---|---|
| **Seam:** choosing between the module interface, a real adapter and the running application | [test-boundaries.md](test-boundaries.md) |
| **Test double:** a test needs a fake, stub or mock | [mocking.md](mocking.md) |

## Plan the tests first

Before the first test, write a short test plan: the **seam** you test at and
the tests you intend to keep, one line each with what the test catches and what
it misses. Choose the highest seam that is still fast enough for the loop; the
ideal is one seam per feature.

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
change while the test stays. It makes one claim, reads like a specification in
the repository's language for tests, and mocks only at system boundaries.

Avoid:

- **Implementation-coupled tests:** mocking internal collaborators, testing
  private methods, asserting call counts or order with no contract reason, or
  checking a side channel, such as a storage table, instead of the interface,
  unless the schema itself is the contract.
- **Tautological tests:** an expected value computed the way the code computes
  it. Take expected values from an independent source: a literal, a worked
  example or the spec. Check that a plausible wrong result would fail.
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
- **Never refactor on red.** The loop ends at green; cleanup belongs to
  `review`.
- **Bug fixes start red.** Reproduce the bug in one test at the seam where it
  actually happens, then fix it.

Run the focused tests while you work and the repository's broader test gate
before reporting done. Report the commands, their results and exit codes; an
unrun check is unverified.
