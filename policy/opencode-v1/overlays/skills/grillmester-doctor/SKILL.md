---
name: grillmester-doctor
description: "Audit whether the current repository and session are ready for effective Grillmester use in OpenCode v1. Use only when the user explicitly asks to check, diagnose, or understand the OpenCode setup; the audit is read-only."
---

# Grillmester Doctor for OpenCode v1

Audit the consumer-owned boundary around the portable Grillmester target.
Distinguish observed runtime behavior from configuration that merely appears
correct, and recommend the smallest useful improvement.

## Keep the audit read-only

Never create, edit, delete, rename, install, authenticate, enable, disable, or
update anything while this skill is active. Do not print provider credentials,
tokens, request headers, or complete configuration values that may contain
secrets. If the user also asks for a fix, complete the audit and propose the
exact change as a separate authorized step.

Invoking this skill proves only that the skill is visible in this session. It
does not prove that every Grillmester agent or command is discovered, that a
different OpenCode installation uses the same config directory, or that the
selected model can complete the workflow reliably.

## Discover the effective OpenCode boundary

Establish the Git root, working directory, OpenCode version, selected agent,
and the effective config directory when they are observable without mutation.
Inspect only applicable sources:

- `AGENTS.md` files from the repository root through the working directory;
- `opencode.json` or `opencode.jsonc` at project and user scope, without
  exposing provider options or environment-derived secrets;
- `OPENCODE_CONFIG` and `OPENCODE_CONFIG_DIR` as path evidence only;
- project-local `.opencode/agents`, `.opencode/commands`, and
  `.opencode/skills`, plus portable `.agents/skills` roots;
- the configured Grillmester target's `manifest.json`, `agents/`, `commands/`,
  and `skills/` trees;
- repository build definitions, entry points, tests, and maintained domain,
  architecture, security, and operations documentation.

OpenCode merges several configuration scopes. A file's existence does not
prove it wins. When effective config or the runtime roster cannot be observed,
mark precedence and collision coverage `UNVERIFIED` rather than guessing.

## Check the native target contract

Verify these dimensions separately:

1. **Target integrity** — generated file counts and hashes agree with
   `manifest.json`; no runtime dependency artifact is treated as Grillmester
   source.
2. **Agent discovery** — four primary agents and three hidden subagents are
   present under `agents/`; agent frontmatter has `mode`, `hidden`, and native
   permissions, and omits `model` so the session/provider choice is inherited.
3. **Delegation** — Grillmester can use `task` only for `kokk`,
   `grill-inspektor`, and `researcher`; other roles preserve their narrower
   task boundary.
4. **Skills and commands** — all manifest skills exist under `skills/`, each
   command wrapper resolves the same skill ID, and manual-only source skills
   require approval through ordered `permission.skill` rules.
5. **Instructions** — consumer facts remain in applicable `AGENTS.md` or other
   consumer-owned sources; Grillmester does not distribute a competing
   repository instruction file.
6. **Provider and model** — the selected provider/model is observable and
   supports the tool calls and context needed by the chosen workflow. Record
   identity and capability, never credentials. A configured provider is not a
   successful model smoke test.
7. **Permissions** — effective project or user configuration does not silently
   widen a role's denied task, shell, edit, web, or skill boundaries.
8. **Shadowing** — no higher-precedence agent, command, or skill with the same
   ID silently replaces a Grillmester component.

Treat the OpenCode target as generated output. Recommend changing its canonical
plugin source, adapter policy, or overlay and regenerating it; never recommend
hand-editing a generated file.

## Return one compact report

```text
GRILLMESTER_OPENCODE_DOCTOR: READY | READY_WITH_GAPS | NOT_READY | UNVERIFIED

Runtime:
- OpenCode version: <observed version or UNVERIFIED>
- Effective config directory: <path evidence or UNVERIFIED>
- Provider/model: <non-secret identity or UNVERIFIED>

Coverage:
- Target integrity: OK | BLOCKER | GAP | UNVERIFIED — <evidence>
- Agents/delegation: OK | BLOCKER | GAP | UNVERIFIED — <evidence>
- Skills/commands: OK | BLOCKER | GAP | UNVERIFIED — <evidence>
- Instructions: OK | GAP | DUPLICATION | UNVERIFIED — <evidence>
- Permissions: OK | BLOCKER | GAP | UNVERIFIED — <evidence>
- Shadowing: OK | BLOCKER | UNVERIFIED — <evidence>

Smallest next action:
- <one bounded consumer- or source-owned change, or none>
```

Use `NOT_READY` only for an evidenced blocker. Keep facts, inference, and
unknowns separate.
