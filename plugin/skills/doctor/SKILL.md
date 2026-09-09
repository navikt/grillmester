---
name: doctor
description: "Audits whether the current repository is ready for effective Grillmester use across Copilot CLI, the Copilot app, cloud agent, and Copilot code review. Use only when the user explicitly asks to check, diagnose, or understand the repository's Grillmester setup; the audit is read-only."
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
fix, finish the audit and return the evidence and bounded file set to the
calling workflow. That workflow can immediately implement within the existing
authorization; completing this read-only phase does not require fresh approval.

Invoking this skill proves that it is available in the current session. It does
not prove a global installation, marketplace freshness, cloud-agent activation,
or availability to another user or client.

## Diagnose the actual skill resolution

For a missing skill, unexpected workflow, or stale agent, record the failed
invocation exactly. Use the current session's skill roster to find the offered
`name` and load that exact identity. Do not invent a prefix, use a heading as an
ID, or retry an obsolete `grillmester-` alias. A slash command is a user-facing
entry point; use the runtime's skill-loading tool for agent-initiated loading.

Trace the requested component through observable evidence:

- client and version, selected agent, requested skill ID, and offered skill ID;
- loaded file path or plugin source, plugin version/revision, and nav-pilot
  agent package when visible;
- full or focused projection and whether its manifest includes the skill;
- same-ID repository and user components, and older prefixed copies;
- legacy Hovmester workflows, copied components, and instruction references.

Compare file content or a content hash with the selected package when possible.
A plugin listing, a filesystem collision, or an agent's self-description does
not prove which file the runtime loaded. Report unobservable links as
`UNVERIFIED`. If a focused projection omits the skill, recommend the matching
full package or an appropriate included workflow. If the roster exposes the
skill but loading fails, report the exact call and error with the identity
chain; do not claim that the component is absent.

When the Grillmester source checkout is available, its
`scripts/audit_consumer_setup.py` provides a read-only filesystem inventory
without requiring a Hovmester manifest or sync caller. User roots must be
provided explicitly. Its exact-copy candidates require review of the complete
file set and current hashes before an authorized removal. Preserve
customized or unknown components and consumer domain rules while reconciling
their ownership; names and manifest membership alone never justify deletion.

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
- portable task workflows and Nav expertise already provided by skills;
- generic technology guidance that can be derived from the repository and
  verified primary documentation.

An embedded agent floor is not an always-on repository floor. When the same
rule must govern the default Copilot agent, Copilot code review, or another AI
tool, give it one consumer-owned standing owner rather than assuming the custom
agent prompt applies there.

These concerns can be consumer-owned when they materially affect the repository;
they are candidates for essential context, not an instruction-file checklist:

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

Keep one concise source for the shared standing contract. Both a common
`.github/copilot-instructions.md` with a tiny `AGENTS.md` pointer and the reverse
layout are valid when the intended clients demonstrably read the shared
content. Verify discovery instead of relocating useful instructions to satisfy
a preferred filename. Add client-specific rules only for an actual difference;
avoid duplicated prose.

Retain only essential repository facts and constraints that models cannot
reliably infer from maintained code and tooling. Prefer a pointer to existing
documentation over copied guidance. Do not recreate setup workflows, sync
checks, instruction trees or generic task procedures to fill this audit's
categories. Missing extra files are not missing context.

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

Skill resolution:
- Requested/offered ID: <exact IDs or UNVERIFIED>
- Loaded source and version: <path/plugin/revision or UNVERIFIED>
- Projection: full | focused | UNVERIFIED
- Repository/user conflicts: <exact paths and evidence or UNVERIFIED>

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
