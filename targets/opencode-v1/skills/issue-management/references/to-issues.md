# To Issues

Break a plan, spec, or conversation into **GitHub issues** — tracer-bullet
vertical slices that remain understandable and useful on their own.

Use this workflow when the user asks to break the work into implementation
tickets or accepts that deliverable in ordinary language; naming the skill is
unnecessary. Do not automatically decompose every specification or create
multiple issues for one clear slice. Use `wayfinder` when the route still
depends on unresolved decisions.

Establish tracker context from consumer-owned instructions, issue templates,
contributor documentation, and read-only GitHub metadata before tracker use.
A dedicated adapter file is optional; its absence must not block drafting.
Stop before publishing only when the target repository, authorization boundary,
or a required operation or metadata value remains unresolved.

## Contents

- Process

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
- Size each slice around one independently verifiable outcome and a reviewable change
- Put enabling refactoring first only when the slice depends on it; otherwise keep it with the change it supports

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

### 4. Resolve material gaps

Present the proposed breakdown as a numbered list. For each issue, show:

- **Title**: plain-language outcome, understandable without opening the issue
- **Blocked by**: which other issues (if any) must complete first
- **In short**: who or what benefits, what changes, and why it matters
- **Implementation brief**: the decisive technical context, proof, and scope

Use the agreed plan to choose granularity and blocking edges. Ask only when a
material scope or dependency choice cannot be inferred. A settled breakdown
does not need another interview.

Draft each issue with the issue body and drafting rules in `SKILL.md`: a functional
title, the human-readable opening first, and the technical brief after it. Present tracker metadata alongside each draft: issue type,
labels, project and initial status, parent, blockers, and assignee when
applicable.

Distinguish drafting from publishing. A request to create tickets from the
agreed plan authorizes those issue writes and their necessary native
relationships; carry that authorization forward. Approval of a draft alone
does not authorize publication. If publication was not requested, finish the
drafts and proposed metadata before asking for that specific action. Ask again
only for writes outside the existing scope.

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
