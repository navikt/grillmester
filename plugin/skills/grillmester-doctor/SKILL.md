---
name: grillmester-doctor
description: "Audits whether the current repository is ready for effective Grillmester use across Copilot CLI, the Copilot app, cloud agent, and Copilot code review. Use only when the user explicitly asks to check, diagnose, or understand the repository's Grillmester setup; the audit is read-only."
license: MIT
disable-model-invocation: true
---

# Grillmester Doctor

Audit the repository boundary that the portable plugin cannot own. Distinguish
verified configuration from inferred coverage and recommend the smallest useful
consumer-owned improvement.

## Keep the audit read-only

This skill is read-only. Never create, edit, delete, rename, stage, commit,
push, install, enable, disable, or update anything while it is active. Do not
run a setup command that writes configuration. If the user also asks for a
fix, finish the audit first and return an exact proposed file set for a separate
authorized implementation step.

Invoking this skill proves that it is available in the current session. It does
not prove a global installation, marketplace freshness, cloud-agent activation,
or availability to another user or client.

## Discover the active repository contract

Establish the Git root, working directory, and target client surfaces. Inspect
only sources that exist and apply to the current scope:

- `AGENTS.md` files from the root through the working path;
- root `CLAUDE.md` or `GEMINI.md` when the team intentionally supports those
  clients;
- `.github/copilot-instructions.md`;
- `.github/instructions/**/*.instructions.md`, including each `applyTo` and
  `excludeAgent` value;
- `.github/copilot/settings.json`, for repository-scoped plugin and marketplace
  declarations;
- repo-local custom-agent and skill locations recognized by the target client,
  including `.github/agents`, `.github/skills`, and `.agents/skills`; compare
  filename-derived agent IDs and skill `name` values with the Grillmester
  components visible in the current runtime. If the runtime roster is not
  observable, report collision coverage as `UNVERIFIED` rather than guessing;
- build definitions, task scripts, continuous-integration workflows, source
  entry points, tests, deployment and authentication configuration;
- maintained domain, architecture, operations, language, tracker, and security
  documentation.

Do not require every supported instruction format. Multiple formats are merged
by some clients without a general precedence rule, so prefer one canonical
repository-wide owner and report duplicated or conflicting rules.

## Apply the ownership boundary

Treat these concerns as plugin-owned inside a selected Grillmester agent. Do
not recommend copying them into every consumer repository merely for those
sessions:

- the public agent roles, delegation protocol, review statuses, and universal
  approval boundaries;
- the shared language, sensitive-data, secret-handling, and untrusted-content
  floors embedded in the agents;
- portable task workflows and NAV expertise already provided by skills;
- generic technology guidance that can be derived from the repository and
  verified primary documentation.

An embedded agent floor is not an always-on repository floor. When the same
rule must govern the default Copilot agent, Copilot code review, or another AI
tool, give it one consumer-owned standing owner rather than assuming the custom
agent prompt applies there.

Treat these concerns as consumer-owned when they matter to the repository:

- service purpose, architecture, entry points, supported runtime, and the
  authoritative build, test, lint, and validation commands;
- local documentation ownership, glossary and ADR paths and formats, and which
  artifacts use Norwegian or English;
- product-specific data classification, risk signals, required review route,
  incident path, and controls that are not safely derivable from code;
- delivery authority for commits and shared GitHub or deployment actions;
- issue tracker, project, label, readiness, ownership, and team-specific
  metadata;
- environment, deployment-order, migration, compatibility, and operational
  invariants that must survive personnel or tooling changes.

Use path-specific instructions only for a concise rule that must activate
automatically for a matching path or file type. Typical candidates are workflow
permissions and deployment invariants, manifests and migrations, or
user-facing content policy. Their absence is not itself a defect when the rule
is enforced deterministically or a repository-wide contract is sufficient.

For a cross-tool standing contract, prefer `AGENTS.md`. Use
`.github/copilot-instructions.md` only for Copilot-specific repository behavior.
Never propose both with duplicated prose. Keep task procedures in skills, not
always-on instructions.

## Assess readiness from evidence

Check these dimensions separately:

1. **Current session** — the skill is visible; record the client only when it is
   observable.
2. **Cloud activation** — matching `enabledPlugins` and
   `extraKnownMarketplaces` declarations are configuration evidence only. Check
   that the plugin name, marketplace name, repository and ref agree. Report
   `CONFIGURED_UNVERIFIED` until the target runtime actually discovers the
   plugin; a declaration cannot prove marketplace reachability or enterprise
   policy. Their absence means `NOT_CONFIGURED_IN_REPO`, not disabled; report
   enterprise-managed activation as `UNVERIFIED` unless it is observable.
3. **Repository orientation** — a new agent can find the correct commands,
   entry points, and maintained context without expensive rediscovery.
4. **Safety and authority** — local risk, data, review, delivery, and incident
   boundaries are explicit where generic plugin floors are insufficient.
5. **Conditional routing** — path-specific rules have correct, non-overlapping
   scopes and no stale references.
6. **Portability** — consumer instructions do not duplicate the plugin's agent
   choreography or task-specific skill content.
7. **Default agent and code review** — any mandatory repository-wide or
   path-specific rule they need is consumer-owned and activates on those
   surfaces; do not count a Grillmester agent prompt as coverage.
8. **Shadowing** — no repo-local agent ID or skill name silently overrides a
   same-named Grillmester component on the requested client surface.

Classify each finding:

- `BLOCKER` — an observed conflict, unsafe ambiguity, or missing target-client
  activation prevents the requested use.
- `GAP` — material repository context is missing or too costly to rediscover.
- `DUPLICATION` — the same policy has competing owners or copies.
- `OPTIONAL` — an optimization with no present correctness or safety impact.

Do not mark a repository unready merely because it lacks path-specific files,
tracker configuration it does not use, or prose that duplicates deterministic
build and policy gates.

## Return one compact report

```text
GRILLMESTER_DOCTOR: READY | READY_WITH_GAPS | NOT_READY | UNVERIFIED

Surfaces:
- Current session: VERIFIED | UNVERIFIED
- CLI/app availability beyond this session: VERIFIED | UNVERIFIED
- Cloud activation: VERIFIED | CONFIGURED_UNVERIFIED | NOT_CONFIGURED_IN_REPO | UNVERIFIED
- Default agent/code review policy: VERIFIED | NOT_REQUESTED | UNVERIFIED

Active instruction sources:
- <path and effective scope, or none>

Coverage:
- <dimension>: OK | BLOCKER | GAP | DUPLICATION | OPTIONAL — <evidence>

Smallest next action:
- <one bounded consumer-owned change, or none>
```

Use `NOT_READY` only when at least one `BLOCKER` is evidenced. Use `UNVERIFIED`
when the target surface cannot be observed. State facts, inference, and unknowns
separately. Never claim that installing or updating the plugin will create or
repair consumer instruction files.
