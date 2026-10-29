# Developer handoff from a design room

Use this reference when the agreed deliverable is a saved design room and a
developer will continue from repository files. A room path and chosen sketch
version or submitted app round identify the source; the handoff also needs the selected direction, relevant
decisions, state coverage and remaining acceptance criteria. This can be part
of an existing task or an authorized issue. Saving a room does not publish its
files or authorize a new issue, Git action or product-code change.

Check the workspace shape before selecting the procedure. App rooms have
`workspace.source.kind: "application"` and contain feedback about an observed
app. Existing HTML rooms have `workspace.version` and `workspace.revisions`,
with no `workspace.source`; they contain a registered sketch pair. A local preview URL is not a shared artifact.

## Read saved app feedback without opening canvas

Read `<room>/workspace.json` once as ordinary JSON. Do not start a server, open
canvas, construct a writer store or save the file from an editor. A supported
app room has `workspace.mode: "feedback"` and
`workspace.source.kind: "application"`. Its source records the descriptive
`name`, `startPath` and optional `resourceQueryKeys`; `workspace.checkpoint`
is an opaque feedback identifier, not a code snapshot or Git revision.
Unreleased rooms with source journals or source-change proposals need their matching tooling;
do not reinterpret them as feedback-only rooms or migrate them during handoff.

1. Identify the exact room and agreed submitted rounds in `submissions` by
   `submission`. Read their immutable `comments`; match each `comment.screen`
   to `screens[].screen`. The screen's `source.route` and the comment's
   `applicationContext` preserve the observed page, target and viewport.
   Never replace them with the app's current route or imply code identity.
2. Read each round's current `review` and `reply` from `canvas.rounds`, and
   distinguish submitted observations from unsent `comments`. Preserve unresolved
   questions and do not treat `answered` as proof of a working implementation.
3. Include the actual app/repository reference and synthetic scenario only when
   independently known, along with observed runtime evidence and remaining checks.
   This room contains no source files, code versions, reference images or undo
   records. Restarting the app and verifying its current state are separate work.

A concrete design-change request may already have produced an interactive
HTML proposal under Forslag in the same workshop. Name the actual sketch and its chosen version, then use the
verified sketch-pair procedure below. Do not create a proposal as part of a
read-only handoff. An answered round alone proves neither that a proposal exists
nor that the app was changed. Verify any registered link as below; do not infer
one from reply text or claim that synthetic interactions establish live app behavior.

A feedback handoff authorizes neither product edits nor publication. Separately
agreed implementation follows the active role's ordinary workflow outside
canvas, using the explicitly owned copy and verified server/source relationship.
A Git worktree alone does not establish that unrelated work can be overwritten.

## Connect app feedback to a sketch proposal

A saved app room can contain `workspace.sketch` when both feedback and the
proposal were saved by request. An explicit request to save the workshop includes
both within the agreed design area; saving only feedback does not. This is a portable relationship, not a source
snapshot. Read its `id`, `title`, `workspacePath`, `workspaceId` and `source`.
An `app-feedback` source also records exact `sourceSubmission` and `commentIds`;
a `conversation` source has no submitted round. Do not invent one. `requestHash`
identifies the initial publication request; it is not the current HTML hash.

`workspace.pendingSketchSave` is an unfinished save intent, not a confirmed
proposal link. Do not complete it by editing JSON, initialize its target, or
claim the whole workshop is saved. The owning canvas must confirm the same
pending save before a durable handoff. A proposal saved later keeps its original
identity, source and full feedback history; its verified saved versions follow
the same procedure below.

Before following the link, validate its bounded project-relative path, reject
symlinks or escapes, read the target `workspace.json` as ordinary data, and match
its exact `workspace.id` to `workspaceId`. It must be an HTML workspace with
`version`/`revisions`, not an application source. Missing or replaced files make
the link unavailable; never initialize a writer store or create a replacement.
The relationship does not pick a historical version for implementation. Resolve
the agreed revision and verify its registered pair using the procedure below.

For an agreed durable handoff, record the app's name and safe route, relative
feedback workspace, applicable round/comment references, and the proposal
workspace plus chosen `revisionId` in the existing handoff file. Example:

> Møtedemo, `/demo?mode=mock`; app feedback in `designs/meeting`, round 2,
> comment `<id>` → proposal in `designs/meeting-proposal`, revision 3.
> The confirmation and error states are simulated; live validation is untested.

These exact identifiers belong in technical handoff or tool calls, not in the
normal designer-facing reply. The workshop's **Vis forslag** action opens the
registered proposal. Temporary proposals have no saved link or revision history;
use their current state in the owning conversation and do not claim later
recovery. Do not create a project note unless that deliverable was requested.
Never write relation fields or revision files directly; only the owning canvas
may update its managed state. A portable link does not authorize product edits.

## Choose the HTML sketch pair

Resolve the room and chosen version from the request or existing agreed brief.
If that choice remains materially ambiguous, ask only for the missing choice
before dependent work. When the user explicitly selects the latest version,
resolve it to a registered `revisionId` and record that exact value. Do not
silently replace an agreed older version with the current room state.

An explicit revision choice fixes that pair's canonical values as the handoff
baseline. Do not make those values conditional or ask the user to choose them
again because current holds, later revisions or unsent notes differ. Read-only
handoff does not require releasing or changing current holds. Treat conflicting
submitted feedback or another explicit requirement in the request or agreed brief
as remaining work, distinct from the chosen source. A current room hold is not
such a requirement; a hold that differs from the chosen pair is later room state,
never a condition on the chosen values.

## Read the chosen sketch pair without opening canvas

Read the chosen pair read-only as ordinary text/JSON, for example with a viewer
or `cat`; extract room metadata with a JSON tool as described below. This needs
no canvas session or writer claim. Never save the files from an editor:
format-on-save, an added final newline or whitespace cleanup can change the
registered content. Opening the room through the canvas or constructing
`WorkspaceStore` acquires its writer claim.

1. Locate the room in the intended repository/worktree. If the files are already
   shared through version control, include the existing repository reference in
   the handoff. The same project-relative path in another worktree can contain
   different work.
2. Parse `<room>/workspace.json` once as a snapshot with a JSON tool. It can be
   a few MiB; do not read the whole file into context. Extract only the entry in
   `workspace.revisions` whose `revisionId` equals the chosen version, current
   holds and the needed submissions with their referenced screen entries. Use
   the chosen entry's `filename` and `screen`. `workspace.version` points to the
   latest version; the top-level `revision` is the feedback/state revision used
   for concurrency checks. Neither replaces the chosen `revisionId`.
3. Read `<room>/revisions/<filename>`. If the entry's `designHash` is not `null`,
   also read the adjacent file obtained by replacing `.html` with `.design.json`.
   These two files form the chosen source. If `designHash` is `null`, that version
   has no descriptor. Do not select files by modification time or infer a version
   from its filename: an unregistered file can remain after an interrupted save.
4. Before any product, test, brief or documentation write that depends on the
   chosen source, verify each referenced file from its actual bytes. `hash` is the
   SHA-256 of the exact HTML bytes and `bytes` is their count; compare both.
   `designHash` is the SHA-256 of the descriptor as the room writes it:
   `JSON.stringify(value)` followed by one newline. A repository formatter may
   have re-indented the file; it still matches when its parsed value in that
   canonical form has the recorded hash. Reading the recorded hashes or checking
   file size alone is not verification. If a referenced file is missing or fails
   this check, name the missing or mismatching file and stop dependent work.
   Retain the chosen reference; do not repair the files, rewrite their hashes
   or substitute another version. The canvas verifies only the current pair
   when opening a room, and older pairs when they are read or restored.

For a version 2 descriptor, `texts[].value` is the canonical text for the matching
`data-vc-text` binding. For a control with `editable: true`, `controls[].initial`
is the saved choice, identified by `variant`, target `key` and control `id`.
For a preview-only control, `initial` is only the starting state of the flow,
not a saved implementation choice. The descriptor's `version` is its schema
version, not the workspace revision number.

Always read the saved HTML together with its descriptor. Descriptor text values
and editable control choices override HTML text and setting attributes at their
declared bindings, whether or not the HTML already contains the saved edits.
Older editor-saved pairs can contain stale HTML. Raw HTML alone is never the
complete source for a pair with a descriptor. A local preview choice or a
feedback text proposal does not become canonical source merely because it was
visible in the preview.

## Separate values, feedback and evidence

- The chosen descriptor preserves that version's values. `workspace.holds`
  records currently preserved manual fields, with `id`, `label`, `value` and
  `signature`; it is not a historical hold snapshot for each version. A release
  can change holds without creating a sketch version. State which values the
  request or agreed brief requires for implementation. Holds that differ from
  the chosen pair are later room state, never conditions on its chosen values;
  do not copy them over the baseline or ask for their release to use it.
- Unsent comments (`submission: 0`) are never part of the handoff unless the
  user explicitly includes them. For an agreed submission cutoff, read
  `submissions` through that number in order; without one, read all rounds in
  order. Use each comment's `screen`, and its `context` when present, with the
  original entry in `screens` to recover what it was written about. The revision
  register does not record a submission cutoff; include the cutoff or the rounds
  read in the handoff instead of guessing from timestamps. Ask only when a
  conflict would change the implementation.
- A keep wish is a submitted comment whose text starts with «Behold denne
  delen.» and whose `context` names the part and values. Treat its part as kept
  unless a later submitted wish asks otherwise, and compare it with the chosen
  pair like any other submitted comment.
- A submitted comment is not proof that the chosen source incorporates it.
  Compare it with the chosen descriptor and HTML, and name any
  disagreement or unfinished work. Record the selected direction and rationale
  in plain language. A round marked `answered` is not design approval or proof
  that all its comments are fixed. Current comments/replies may differ from the
  immutable copies in submitted rounds.
- Descriptor variants and control options describe available choices, not tested
  state coverage. For relevant normal, loading, error, empty and confirmation
  states, identify the version/variant/setting that shows each one and distinguish
  what was inspected from what remains unshown or unverified. Include responsive
  or accessibility findings only with their actual evidence and limitations.

When appearance matters, link the inspected visual evidence and record the Aksel
or other style version used. The saved pair does not freeze external styles.
Preview evidence does not establish production interaction, accessibility or
backend correctness; name the checks the implementer still needs for this task.

Return to the active role's normal implementation or brief workflow with this
source and its acceptance criteria. Reimplement the selected design with the
application's components and patterns; do not promote the preview shell or
simulated actions into production. A brief request does not authorize product-code
or room changes; write or publish the brief only within the requested scope.

## Compact handoff example

The following is illustrative. Replace placeholders with observed source and
agreed decisions; leave unknowns explicit. These descriptor fields supply the
sample canonical values:

```json
{
  "version": 2,
  "variants": [],
  "texts": [{ "id": "heading", "label": "Overskrift", "value": "Velg tidspunkt" }],
  "targets": [{
    "key": "summary", "variant": "", "label": "Oppsummering",
    "controls": [{
      "id": "density", "label": "Luft", "type": "select",
      "initial": "roomy", "editable": true,
      "options": [
        { "value": "roomy", "label": "Romslig" },
        { "value": "compact", "label": "Kompakt" }
      ]
    }]
  }]
}
```

```text
Design question: <the question this design resolves>
Source: designs/meeting; chosen revisionId: <number>; repository reference: <if available>
Pair: revisions/<registered filename>.html + matching .design.json
Canonical values: text:heading = "Velg tidspunkt"; control:/summary/density = "roomy"
Preserve for implementation: <values the request or agreed brief requires, or none>
Direction and rationale: <chosen direction, why, and any borrowed parts>
Feedback evidence: submission cutoff <number, or all rounds>; keep wishes and other comment IDs <ids>; <matched / conflicting>
State coverage: <state → revision/variant/setting → inspected / unverified / not shown>
Visual evidence: <reference or not captured>; style version: <observed version or unknown>
Accessibility findings: <observed findings and limits, or not assessed>
Remaining acceptance: <open choices and implementation checks>
```

Figma is optional. If another artifact is also used, state which source and
version govern the implementation and resolve differences explicitly.
