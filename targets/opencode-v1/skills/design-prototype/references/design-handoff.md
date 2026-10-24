# Developer handoff from a design room

Use this reference when the agreed deliverable is a saved design room and a
developer will continue from repository files. A room path and chosen version
identify the source; the handoff also needs the selected direction, relevant
decisions, state coverage and remaining acceptance criteria. This can be part
of an existing task or an authorized issue. Saving a room does not publish its
files or authorize a new issue, Git action or product-code change.

Resolve the room and chosen version from the request or existing agreed brief.
If that choice remains materially ambiguous, ask only for the missing choice
before dependent work. When the user explicitly selects the latest version,
resolve it to a registered `revisionId` and record that exact value. Do not
silently replace an agreed older version with the current room state.

An explicit revision choice also selects that pair's canonical values as the
handoff baseline. Do not ask the user to choose those values again solely because
current holds, later revisions or unsent notes differ. Read-only handoff does not
require releasing or changing current holds. Treat conflicting feedback from the
rounds the user included, or another explicit requirement, as remaining work;
distinguish that conflict from the already chosen source.

## Read the chosen source without opening canvas

Read the files as ordinary text/JSON in an editor. This needs no canvas session
or writer claim. Keep the files unchanged during inspection; opening the room
through the canvas or constructing `WorkspaceStore` acquires its writer claim.

1. Locate the room in the intended repository/worktree. If the files are already
   shared through version control, include the existing repository reference in
   the handoff. The same project-relative path in another worktree can contain
   different work.
2. Read `<room>/workspace.json` once as a snapshot. Find the entry in
   `workspace.revisions` whose `revisionId` equals the chosen version. Use that
   entry's `filename` and `screen`. `workspace.version` points to the latest
   version; the top-level `revision` is the feedback/state revision used for
   concurrency checks. Neither replaces the chosen `revisionId`.
3. Read `<room>/revisions/<filename>`. If the entry's `designHash` is not `null`,
   also read the adjacent file obtained by replacing `.html` with `.design.json`.
   These two files form the chosen source. If `designHash` is `null`, that version
   has no descriptor. Do not select files by modification time or infer a version
   from its filename: an unregistered file can remain after an interrupted save.
4. Before using the chosen source for implementation or a brief, calculate
   SHA-256 from the actual bytes of each referenced file. Compare the HTML hash
   with the entry's `hash` and, when present, the descriptor hash with
   `designHash`; also compare the HTML byte count with `bytes`. Include the
   descriptor's trailing newline. Reading the recorded hashes or checking file
   size alone is not verification. If a referenced file is missing or a value
   differs, report the mismatch and stop dependent work. Retain the chosen
   reference; do not repair the files, rewrite their hashes or substitute another
   version.

For a version 2 descriptor, `texts[].value` is the canonical text for the matching
`data-vc-text` binding. A target's `controls[].initial` supplies its declared
starting choice, identified by `variant`, target `key` and control `id`. The
descriptor's `version` is its schema version, not the workspace revision number.

The editor saves a new descriptor alongside a copy of the immutable HTML. Raw
HTML can therefore contain older fallback text or setting attributes. Read the
pair together: the trusted preview applies descriptor values to their declared
bindings. Opening the raw HTML alone is not an equivalent rendering or a complete
export of source edits. A local preview choice or a feedback text proposal does
not become canonical source merely because it was visible in the preview.

## Separate values, decisions and evidence

- The chosen descriptor preserves that version's values. `workspace.holds`
  records currently preserved manual fields, with `id`, `label`, `value` and
  `signature`; it is not a historical hold snapshot for each version. A release
  can change holds without creating a sketch version. State explicitly which
  manual values the handoff should preserve, and compare them with the chosen
  pair rather than copying newer room values over it.
- `decisions` includes local unsent changes and releases. `submittedDecisions`
  contains the latest submitted state, which may be newer than the chosen sketch.
  For a recorded submission cutoff, read `submissions` through that number in
  order and retain the last decision for each `id`: `active` retains the choice,
  `released` releases it. Use each decision's `screen`, `variant`, `target` and
  `values` with its original entry in `screens` to recover its context. The
  revision register does not record a submission cutoff; include the relevant
  cutoff or exact rounds in the handoff instead of guessing from timestamps.
- A submitted choice is not proof that the chosen source incorporates it.
  Compare the decision with the chosen descriptor and HTML, and name any
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
agreed decisions; leave unknowns explicit. The field names and sample values
follow the descriptor example in the [workspace reference](design-workspace.md).

```text
Design question: <the question this design resolves>
Source: designs/meeting; chosen revisionId: <number>; repository reference: <if available>
Pair: revisions/<registered filename>.html + matching .design.json
Canonical values: text:heading = "Velg tidspunkt"; control:/summary/density = "roomy"
Preserve for implementation: <agreed manual values, or none recorded>
Direction and rationale: <chosen direction, why, and any borrowed parts>
Decision evidence: submission cutoff <number>; decision IDs <ids>; <incorporated / remaining>
State coverage: <state → revision/variant/setting → inspected / unverified / not shown>
Visual evidence: <reference or not captured>; style version: <observed version or unknown>
Accessibility findings: <observed findings and limits, or not assessed>
Remaining acceptance: <open choices and implementation checks>
```

Figma is optional. If another artifact is also used, state which source and
version govern the implementation and resolve differences explicitly.
