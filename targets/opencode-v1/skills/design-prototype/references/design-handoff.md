# Design handoff

Use this reference when the designer wants to keep a result, or when a developer
continues from one. The handoff needs the selected direction, relevant decisions,
state coverage and remaining acceptance criteria. This can be part of an existing
task or an authorized issue. Saving a result does not publish it or authorize a new
issue, Git action or product-code change. A local preview URL is not a shared
artifact.

## Hand off a running proposal

A running proposal lives in an explicitly owned copy of the app. The Browser tab,
its local URL and the picks in the conversation are not deliverables. When the
designer wants to keep the result, do this before the demo and copy go away:

1. Remove what only served the comparison: other alternatives, the query parameter
   and page titles. Then read the diff from the copy's private baseline, and check
   that it holds only the agreed proposal, with no generated files, lockfile churn,
   secrets or demo data.
2. With agreed storage, save it as a patch with a short brief in the agreed design
   area of the conversation's project. Without agreed storage, keep the copy and
   say that the result is temporary.
3. Write the brief below. Leave unknowns explicit.

```text
Design question: <the question this design resolves>
Source: <patch path>; app: <name>, route <safe route>; original revision: <sha or unknown>
Direction and rationale: <chosen direction, why, and any borrowed parts>
Changed: <what changed, in design language>
Aksel: <components used, and anything custom>
State coverage: <state: tried or not tried>
Visual evidence: <reference or not captured>
Accessibility findings: <observed findings and limits, or not assessed>
Remaining acceptance: <open choices and implementation checks>
```

Applying the patch to the original is implementation. It needs an explicit order
and follows the role's ordinary workflow in a location the user chose, with its own
verification. Prototype source is not automatically production-ready.

For Figma, use the selected full page and agreed relevant states as the visual
reference, with the active Aksel library, and verify the resulting editable frames
against that page. Do not substitute a small reconstruction or claim lossless
code-to-Figma conversion. Name the source that governs if another artifact is used.

## Read a room from an earlier release

Earlier releases could save sketches and app feedback in a folder such as
`designs/<name>`. Nothing opens these rooms any more, but they are ordinary files.
Treat them as read-only.

`workspace.json` lists `workspace.revisions`, with `filename`, `hash` and
`designHash` for each HTML version in `revisions/`, and submitted feedback in
`submissions`. Before relying on a version, compare its bytes with the SHA-256
`hash`, and stop if the file is missing or differs. When `designHash` is set, read
the adjacent `.design.json` too: its `texts[].value` and the `initial` value of
editable controls override the HTML. Unsent comments have `submission: 0` and are
not part of a handoff unless the user says so. A room with
`workspace.source.kind: "application"` holds feedback about an observed app, not
source. Saved rounds are evidence of what was asked, not proof that it was done.
