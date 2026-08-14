---
name: grillmester-create-a-skill
description: Create, revise, review, or diagnose a GitHub Copilot CLI skill with a predictable authoring and forward-testing workflow. Use when a user asks to create or improve a skill, investigate why one does not trigger, or validate skill behavior.
license: MIT
---

# Create a Skill

Create, revise, or diagnose one GitHub Copilot CLI skill. The target
repository's instructions and supported Copilot contract govern the artifact
this skill produces.

## Choose the mode

- **Create or revise** — run the complete workflow and edit the skill, callers,
  documentation, and provenance that the change actually affects.
- **Diagnose or review** — inspect, design, and validate read-only, then report
  evidence and concrete recommendations. Make no edits unless the user also
  asks for implementation.

When a creation request turns out to be owned by an existing skill or
reference, stop with a recommendation to extend that owner. Continue into an
edit only when the user requested implementation.

## 1. Inspect the target

Inspect the target repository, installed client contract, existing target
skill, neighboring skills, and known callers. Treat repository instructions
and skill policy as optional evidence when they exist, not as prerequisites.
Identify the repository's chosen skill root and available structural or
discovery validators from actual files and client behavior.

For a revision, inspect enough history and usage to distinguish intentional
behavior from sediment. For a new skill, search for an existing skill or
reference that already owns the job.

Complete this step when you can state:

- the skill's one job;
- its boundary against neighboring skills;
- the target repository's Copilot and language policies;
- the current callers or intended usage.

## 2. Design the invocation boundary

Decide whether the skill is manual-only, model-only, or reachable through both
surfaces before writing the body. For every model-reachable branch, write
representative positive prompts and nearby prompts that should not select it.
For every human-reachable branch, define the explicit slash invocation and any
argument shape.

Discover the roots supported by the installed client, then use the one already
selected by the target repository. If no root exists, verify the current client
contract and ask the user before introducing one. Do not add a parallel skill
tree. Place each skill at `<selected-root>/<kebab-case-name>/SKILL.md`, with
optional `references/`, `scripts/`, and `assets/` directories beside it. Keep
disclosed references one level below `SKILL.md` and point to each one directly
from `SKILL.md` with the condition for loading it.

Use the portable GitHub skill frontmatter supported by the target clients and
narrowed by the target repository's policy:

- `name` — required; match the directory and slash name.
- `description` — required; provide model discovery signals for a
  model-reachable skill and a concise picker summary for a manual-only skill.
- `license` — provenance metadata accepted by Grillmester's validator and
  verified client-loading flow. Grillmester requires `MIT`; another target
  repository follows its own verified client and license policy.
- `disable-model-invocation: true` — make the skill manual-only;
  `user-invocable` defaults to `true`.
- `user-invocable: false` — hide a model-reachable skill from the picker.
- Omit both invocation flags when the skill is reachable by both model and
  human.
- `argument-hint` — optional guidance when slash invocation accepts genuine
  user input.

Check the
[GitHub Copilot CLI skills reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference#skills-reference)
before introducing any other key. Repository policy may narrow these choices.

Complete this step when the invocation mode, its reachable surfaces, the
relevant prompts or explicit commands, and the human- or model-facing
description are explicit.

## 3. Design the information hierarchy

Apply [the authoring principles](references/principles.md) to decide what stays
in `SKILL.md`, what is disclosed behind a contextual pointer, and whether
deterministic repeated work belongs in `scripts/`. When a defined term needs
clarification or a failure mode needs diagnosis, find and read only its heading
in [the glossary](references/glossary.md).

Keep repository and stack constraints in repository instructions or a
repository-specific reference unless they are intrinsic to the skill's single
job. Reuse existing templates, scripts, and assets when they already express
the contract.

Complete this step when every proposed file has a purpose and every disclosed
file has a pointer whose wording says when to load it.

## 4. Implement and reconnect

For create or revise mode, write a concise `SKILL.md` with supported
frontmatter, ordered steps or co-located reference, and checkable completion
criteria. Add only the bundled resources justified in the previous step.

Update direct callers, routers, and bundled provenance when the skill's name,
invocation boundary, or imported material changes. Update consumer-owned
documentation only when the user included it in scope. Follow an explicit
artifact language policy when one exists; otherwise match neighboring skills.

Complete this step when there are no stale names, competing owners, dangling
links, or undocumented imported sources. In diagnose or review mode, skip the
edits and report these conditions as findings instead.

## 5. Validate and forward-test

Immediately before validation, read
[the Copilot CLI validation checklist](references/copilot-cli-validation.md),
then run its structural, link, discovery, and invocation checks that are safe
in the target repository. In create or revise mode, execute bundled scripts on
representative fixtures and inspect the final diff for scope, relevance,
no-ops, duplication, and stale repository assumptions. In diagnose or review
mode, run only non-mutating checks and include successes and failures as
evidence instead of requiring the target to pass.

In create or revise mode, revise against observed behavior. The edit is
complete when structure and links pass, invocation matches its mode, every
branch meets its completion criterion, and the final diff contains only
intentional changes.

In diagnose or review mode, the work is complete when an evidence-based report
covers the observed invocation behavior, structural or behavioral failures,
affected branches, and concrete recommendations. A failing target is a valid
diagnosis result.
