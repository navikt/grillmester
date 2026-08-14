---
name: grillmester-to-issues
description: Use only after the user explicitly selects To Issues to break an approved plan or specification into independently useful GitHub issues with native blocking edges.
---

# To Issues

Break a plan, spec, or conversation into **GitHub issues** — tracer-bullet
vertical slices that remain understandable and useful on their own.

Start only after the user has explicitly selected `/grillmester-to-issues` in the current
conversation. Relevance or a prior recommendation is not selection.

Establish tracker context from consumer-owned instructions, issue templates,
contributor documentation, and read-only GitHub metadata before tracker use.
A dedicated adapter file is optional; its absence must not block drafting.
Stop before publishing only when the target repository, authorization boundary,
or a required operation or metadata value remains unresolved.

## Process

### 1. Gather context

Work from whatever is already in the conversation context. If the user passes a reference (a spec path, an issue number or URL) as an argument, fetch it and read its full body and comments.

### 2. Explore the codebase (optional)

If you have not already explored the codebase, do so to understand the current
state of the code. Issue titles and descriptions should use the project's
domain glossary vocabulary and respect ADRs in the area you're touching.

Look for opportunities to prefactor the code to make the implementation easier. "Make the change easy, then make the easy change."

### 3. Draft vertical slices

Break the work into **tracer bullet** issues.

<vertical-slice-rules>

- Each slice cuts a narrow but COMPLETE path through every layer (schema, API, UI, tests) — vertical, NOT a horizontal slice of one layer
- A completed slice is demoable or verifiable on its own
- Each slice is sized to fit in a single fresh context window
- Any prefactoring should be done first

</vertical-slice-rules>

Give each issue its **blocking edges** — the other issues that must complete
before it can start. An issue with no blockers can start immediately.

**Wide refactors are the exception to vertical slicing.** A **wide refactor** is
one mechanical change — rename a column, retype a shared symbol — whose **blast
radius** fans across the whole codebase, so a single edit breaks thousands of
call sites at once and no vertical slice can land green. Don't force it into a
tracer bullet; sequence it as **expand–contract**. First expand: add the new
form beside the old so nothing breaks. Then migrate the call sites over in
batches sized by blast radius (per package, per directory), each batch its own
issue blocked by the expand, keeping CI green batch to batch because the old
form still exists. Finally contract: delete the old form once no caller
remains, in an issue blocked by every migrate batch. When even the batches
can't stay green alone, keep the sequence but let them share an integration
branch that all block a final integrate-and-verify issue — green is promised
only there.

### 4. Quiz the user

Present the proposed breakdown as a numbered list. For each issue, show:

- **Title**: plain-language outcome, understandable without opening the issue
- **Blocked by**: which other issues (if any) must complete first
- **In short**: who or what benefits, what changes, and why it matters
- **Implementation brief**: the decisive technical context, proof, and scope

Ask the user:

- Does the granularity feel right? (too coarse / too fine)
- Are the blocking edges correct — does each issue only depend on issues that genuinely gate it?
- Should any issues be merged or split further?

Iterate until the user approves the breakdown. Approval of its shape is not
authorization to mutate the tracker: present the exact issues, metadata, and
relationships and obtain explicit authorization for those writes.

### 5. Publish the issues to GitHub

After authorization, publish one issue per slice in dependency order
(blockers first) so later relationships can reference real identifiers. Use the
tracker's native parent and blocking relationships. Apply only labels and issue
types established by consumer evidence or live metadata; never approximate a
missing relationship or label in prose.

Read the created issues, project state, and native relationships back after
writing. Report a
partial failure instead of silently continuing with a malformed graph.

Work the **frontier**: any issue whose blockers are all done. For a purely
linear chain that means top to bottom.

Do NOT close or otherwise modify a parent issue unless that mutation was
included in the authorized set.

Use a functional title that names the observable change rather than the
implementation mechanism. Start the body for humans who do not know the code:

<issue-template>
## In short

<one or two sentences: who or what benefits, what changes, and why it matters>

## What to build

<the end-to-end behaviour this issue makes work, not a layer-by-layer walkthrough>

## Acceptance criteria

- [ ] Criterion 1
- [ ] Criterion 2

## Implementation context and proof

<relevant current state, constraints, risks, test seams, and evidence>

## Out of scope

<the nearest tempting work that this issue deliberately does not include>

</issue-template>

Use a user story only when a real actor and value become clearer in that form.
Do not force technical work into “As a …” prose. Put the technical brief after
the human-readable opening. Preserve the evidence, constraints, test seams,
and non-goals an implementer or agent needs; remove only detail that would go
stale or prescribe an unchosen implementation.

Present tracker metadata alongside the draft: issue type, labels, project and
initial status, parent, blockers, and assignee when applicable. Store parent,
blocking, and project state in native metadata rather than body prose.

Keep parent and blocking state in native tracker relationships, not duplicated
body sections. Add dependency prose only when a non-obvious rationale will
help the implementer; it never carries graph state.

Avoid speculative paths, exhaustive file inventories, and snippets that merely
prescribe an implementation. Retain verified current anchors such as a symbol,
path, failing test, query, or command when they are evidence or the clearest
test seam. If a prototype produced a snippet that encodes a decision more
precisely than prose can (state machine, reducer, schema, type shape), inline
only its decision-rich parts and identify it as prototype output.
