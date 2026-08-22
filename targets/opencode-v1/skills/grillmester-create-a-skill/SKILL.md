---
name: grillmester-create-a-skill
description: "Create, revise, review, or diagnose a portable Agent Skill for OpenCode v1, including native discovery, permissions, and an optional slash-command adapter. Use when a user asks to create or improve a skill, investigate why one does not load, or validate skill behavior."
---
# Create an OpenCode-compatible Agent Skill

> **OpenCode v1:** Backticked `grillmester-*` names below are skill IDs, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Create, revise, or diagnose one portable Agent Skill. Repository instructions,
the installed OpenCode v1 contract, and the target repository's chosen skill
root govern the artifact.

## Choose the mode

- **Create or revise** — inspect, design, edit, reconnect callers, and validate.
- **Diagnose or review** — inspect and validate read-only, then report evidence
  and recommendations. Edit only if the user also requested implementation.

Stop and recommend extending an existing owner when the requested behavior is
already owned by a skill or reference.

## 1. Inspect the target

Inspect applicable `AGENTS.md`, OpenCode config, existing skills, neighboring
commands, and repository validation. Determine which supported root the
repository already uses:

- `.agents/skills/<name>/SKILL.md` for a portable project skill;
- `.opencode/skills/<name>/SKILL.md` for an OpenCode-specific project skill;
- the corresponding supported user-level root only when the user requested a
  personal skill.

Do not introduce a parallel skill tree without a material reason and user
agreement. State the skill's one job, its boundary, current callers, and
whether it needs a separate slash command.

## 2. Design discovery and invocation

Use portable skill frontmatter:

- `name` — required, kebab-case, and equal to the directory name;
- `description` — required, concise, and specific enough for model discovery;
- `license`, `compatibility`, and `metadata` — optional only when they convey a
  real portable contract.

Do not copy client-specific invocation keys into an OpenCode skill. OpenCode
loads skills through the `skill` tool. Control model access with ordered
`permission.skill` patterns in agent or project configuration. When a direct
slash entry point matters, add a native command with the same stable ID under
the selected OpenCode `commands/` root; the wrapper must load the skill and
pass `$ARGUMENTS` as user input.

For access rules, put `"*"` before narrower patterns because the last matching
rule wins. Use `ask` for a source skill that was intended to require deliberate
human invocation; this is an approval approximation, not provenance-aware
manual-only behavior.

## 3. Design the information hierarchy

Apply [the authoring principles](references/principles.md). Keep instructions
needed every time in `SKILL.md`; put conditional reference, scripts, and assets
beside it and link them with an explicit loading condition. Consult only the
needed heading in [the glossary](references/glossary.md).

## 4. Implement and reconnect

Write the smallest complete skill and only justified bundled resources. Update
direct callers, command wrappers, adapter policy, and provenance affected by a
name or invocation change. If a repository generates its OpenCode target,
change the canonical source or target overlay and regenerate; never hand-edit
the generated output.

Complete the edit when names are stable, links resolve, target roots do not
compete, permissions preserve the intended boundary, and the diff contains no
unrelated client assumptions.

## 5. Validate and forward-test

Immediately before validation, read
[the OpenCode validation checklist](references/opencode-validation.md). Run its
safe structural and runtime checks using a disposable target/config copy when
the client may create dependency artifacts. Test explicit command invocation,
positive skill discovery, a close negative prompt, and every distinct branch
that can be exercised without unauthorized external writes.

In diagnose mode, a failing target is valid evidence. In create/revise mode,
iterate until structure, discovery, permission behavior, and the final diff
match the intended contract.
