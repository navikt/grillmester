---
name: grillmester-issue-management
description: "Creates, updates, links, inspects or closes GitHub issues after the work has been shaped. Use for explicit tracker requests and native issue mechanics; do not use it to design, implement or decompose a plan."
---
# Issue Management

> **OpenCode v1:** Backticked `grillmester-*` names below are skill IDs, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Apply GitHub issue mechanics to work that is already understood. The caller owns
`grillmester-grilling`, planning, specifications, and ticket decomposition;
this skill owns the resulting tracker mutations.

## 1. Discover tracker context

Read consumer-owned instructions and tracker documentation before using tracker
tools. Do not assume a path or that an adapter exists. Establish the target
repository and account, authorization boundary, issue templates, language,
available labels and types, project mapping, and supported native
relationships from repository evidence or read-only tracker queries.

If any fact required for the requested mutation remains ambiguous, ask the
user. Never guess a repository, account, label, relationship, project or
status, and never create a parallel tracker.

## 2. Inspect before drafting

Resolve a referenced number or URL in the confirmed repository and read the
complete issue and comments. A bare number is ambiguous outside an established
repository context.
Search for an existing issue before proposing a new one. For an epic, inspect
its native children and dependency graph rather than inferring state from a
list of links in prose.

## 3. Draft the smallest useful change

Use the repository's issue template and documented language when they exist.
Otherwise ask when language affects the result, then keep the issue
self-contained and concise. Give it a functional title that says what changes,
not which file or mechanism will be touched. Make the opening useful to a
non-technical teammate:

```markdown
## In short

<one or two sentences: who or what benefits, what changes, and why it matters>

## Acceptance criteria

- [ ] <verifiable result>

## Implementation context and proof

<relevant current state, constraints, risks, test seams, and evidence>
```

Retain the context, non-goals, dependency rationale, rollback conditions, risk,
and evidence needed to make the issue independently actionable for a developer
or agent. Do not copy an umbrella specification, decision history, file
inventory, or implementation walkthrough into every child issue.
Use a user story only when a real actor and value are clearer in that form; it
is not a required wrapper for technical work.
Keep parent and dependency graph state in native relationships rather than
duplicating it in body sections.

Select only issue types, labels, assignees, parents, dependencies, and project
fields that consumer evidence or live metadata establishes. Present those proposed metadata values
with the draft; metadata is part of the task contract even when it is not body
prose.

Before proposing a pickable status, apply the consumer's documented readiness gate. A thin
intake issue may remain in backlog; do not compensate for missing evidence or
scope by inventing technical detail.

## 4. Confirm and write

Present the exact issues and mutations first. Obtain explicit human
authorization for that bounded set of external writes.

In `grillmester local run`, the original `local run` prompt may carry that
human authorization when it names the exact, bounded mutation and repository.
This means there is no second client tool dialog. It does not authorize
unstated writes or resolve an ambiguous repository, account, issue body or
metadata choice; return `Status: NEEDS_INPUT` when any such choice remains.

For Doctor Who, and for any runtime without explicit command-execution
capability, use only an available, approved semantic GitHub integration. Never
fall back to `gh`, shell, raw HTTP, or ask the user to run a command on the
agent's behalf. If read evidence is unavailable, request the smallest pasted or
exported issue/project excerpt and return `Status: NEEDS_INPUT`. If a write tool
is unavailable, keep the reviewed mutation as a draft and return
`Status: NEEDS_INPUT`, naming the required integration or the exact manual
GitHub UI action.

An implementation agent in a terminal session explicitly started through
Grillmester and cplt may use cplt-guarded `gh issue` commands as its approved
GitHub adapter. Use only the confirmed current repository and account, keep the
command inside cplt, and never bypass cplt's repository scope, GitHub guard or
command restrictions. Prefer semantic GitHub tools when they are available.
When `GH_TOKEN` is supplied, never inspect or print the token or enumerate the
full environment; invoke only the bounded `gh` command needed for the approved
mutation.
Outside that explicit cplt context, do not substitute `gh` or shell for a
missing semantic tracker capability. Never use raw HTTP for a
tracker mutation.

Verify every created or changed issue, project item, field value, and
relationship after writing.
Report partial failure without silently omitting project state or substituting
a text-only relationship.

## 5. Maintain lifecycle without taking over delivery

Use native sub-issues and dependencies as the graph. Recommend the first open,
unblocked child when the user asks for the frontier; selection does not start
implementation or mutate project state.

Link delivery through the repository's PR convention. Comment on or close an
issue only when explicitly requested or included in the authorized delivery.
When an epic has no open children, propose its summary and closure; never close
it automatically.
