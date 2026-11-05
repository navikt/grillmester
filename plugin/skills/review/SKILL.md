---
name: review
description: "Review a complete diff for correctness, fit to the requirements and the repository's standards. Use after implementing, when asked to review changes or a pull request, or as the method of an independent reviewer; use `security-review` for security-specific analysis."
---

# Review

Review the complete task diff in three passes, one per lens, and report the
findings per lens so one kind of finding does not hide another. The writer runs
it as a self-review before delivery and fixes in-scope findings, including
smells in its own code; an independent reviewer runs the same lenses read-only
and reports them.

When the user wants a walkthrough rather than a review, suggest
`guided-review`.

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
Then check the change against the smells below. Check the tests against the
keep rule in `tdd`: flag a missing test for a real risk, and flag test bloat.

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

## Smells

A fixed baseline of code smells, mostly from Martin Fowler's *Refactoring*, that
applies even when a repository documents nothing. A smell is a judgement call, such as
"possible feature envy", never a hard violation. A documented repository rule
always wins, and anything a linter or formatter already enforces is out of
scope.

Consider only smells the diff introduces or worsens, a few at most, and none
for text-only changes. As the writer, fix them in the code you added or changed,
and report what lies outside the task. As a read-only reviewer, report them.

- **Mysterious name:** a name that hides what the thing does or holds. Rename
  it; if no honest name comes, the design is unclear.
- **Long function:** a function that does several things, or whose parts need
  comments to tell them apart. Extract the parts that deserve their own name.
  Length alone is no reason: thin helpers that only shorten it make it worse.
- **Large class or module:** a class or file that has taken on several
  responsibilities. Split it along what changes together.
- **Long parameter list:** many parameters, or a flag that switches behavior.
  Give values that belong together a type, or split the function.
- **Shallow module:** an interface about as complex as what it hides. Merge or
  deepen it so a small interface hides more.
- **Duplicated code:** the same logic shape in more than one place in the
  change. Extract the shared shape and call it from both.
- **Feature envy:** a function that uses another module's data more than its
  own. Move it next to that data.
- **Data clumps:** the same few fields or parameters that keep travelling
  together. Give them one type.
- **Primitive obsession:** a primitive or string standing in for a domain
  concept. Give the concept its own small type.
- **Repeated switches:** the same branching on the same type in several
  places. Use one shared map or polymorphism.
- **Shotgun surgery:** one logical change that forces scattered edits. Gather
  what changes together.
- **Divergent change:** one module edited for several unrelated reasons. Split
  it so each part changes for one reason.
- **Speculative generality:** abstractions, parameters or hooks for needs
  nobody has. Remove them until a real need appears.
- **Message chains:** long `a.b().c().d()` navigation. Hide the walk behind one
  call on the first object.
- **Middle man:** a class or function that mostly delegates. Call the target
  directly.
- **Refused bequest:** a subtype that ignores most of what it inherits. Use
  composition instead.

## Refactor safely

Never refactor while a test is red. Reach green, run the focused tests, and
then refactor in small steps with fresh green evidence between them. Keep tests
on the public interface. Record friction the new behavior exposes, and widen the
refactor only when the task needs it.

Follow the repository's language, framework and module style, and read
neighboring production code before applying a pattern. Depending on what you
find, useful moves include:

- keeping transport or UI entry points focused on parsing, validation and
  response translation;
- collecting configuration and dependency composition behind one testable
  seam;
- replacing raw identifiers with the repository's established value-type
  pattern;
- moving protocol, persistence or framework details behind an adapter.

These are prompts, not universal layering rules. Preserve an established local
pattern when it already gives good locality and a stable public seam.
