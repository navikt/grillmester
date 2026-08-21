---
name: grillmester-team-status
description: "Builds evidence-based team status, goal progress and prioritisation summaries from explicitly confirmed sources. Use for weekly status, planning-period reviews, cross-repository work overviews or prioritisation; GitHub Projects is supported but never assumed."
---
# Team status

> **OpenCode v1:** Backticked `grillmester-*` names below are skill IDs, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Build a traceable status report from the sources the team actually uses.
GitHub Projects is one possible source, not a prerequisite. The default mode is
read-only.

## 1. Clarify the status request

Find or ask for:

- team or product area
- report type, period, and audience
- the decision the report should support
- authoritative sources for goals, work, capacity, and field semantics
- which repositories, projects, and other systems are included

Read relevant consumer-owned instructions and documents first. A remote name,
project link, or project value in an issue template is only a clue until
confirmed by explicit team context or the user.

When working across repositories, the scope must be named or confirmed. Do not
perform organisation-wide searches and call the result "team status".

## 2. Establish the evidence base

Create a short internal source list with:

- source and scope
- when the data was retrieved
- which fields or documents were used
- access gaps and known weaknesses

If a necessary source, period, or semantic definition is missing, ask one
specific question. If the source cannot be read, ask the user to share a
relevant excerpt and note the limitation in the report.

For GitHub Projects:

1. Check whether an approved semantic GitHub or Projects integration is
   actually available at runtime. Never use `gh`, shell, raw HTTP, or other
   network commands as a fallback in this product workflow.
2. Obtain the owner and project number from a confirmed link or team source.
3. Retrieve fields, options, and items dynamically through the integration.
4. Find the team's explanation of columns and fields. Do not infer "active",
   "done", goals, period, size, or priority from the field name alone.
5. Use [projects-v2.md](./references/projects-v2.md) for technical read
   procedures when relevant.

If necessary Projects evidence cannot be read with the available approved
tools, ask for a dated export or pasted excerpt and stop with
`Status: NEEDS_INPUT`. Name the missing evidence; do not suggest a shell
command. A missing write tool cannot be bypassed either: keep the change draft
in the conversation and ask for the integration or manual execution in the
GitHub interface.

Issue templates may be used to suggest a project for the user to confirm, but
they do not automatically define the team's board or the full report scope.

## 3. Build the report

Select the appropriate template from
[rapportmaler.md](./references/rapportmaler.md):

| Report | Purpose |
|---|---|
| Weekly overview | Show work, blockers, and recent changes |
| Period status | Connect verified outcome signals and work to the team's goals |
| Prioritisation material | Compare clarified candidates against goals and criteria |

The report must distinguish:

1. **Evidence base** — what was read, with timestamp and scope.
2. **Verified observations** — what the sources actually show.
3. **Interpretation** — patterns and consequences you infer.
4. **Data gaps and assumptions** — what could not be verified.
5. **Next clarification** — what the team should investigate or decide.

A tracker documents work, not necessarily impact. Do not assess goal achievement
from issue status alone; use measurement data or mark impact status as unknown.

Before producing prioritisation material, clarify the occasion, goals, criteria,
capacity, and candidates. Do not fill missing candidates with an assumed
backlog.

## When a board or field guide is missing

Offer a short interview:

1. What does each relevant column or status mean?
2. Which fields are used for goals, period, priority, and size?
3. Which exceptions and transition rules exist?

First provide the guide as a draft in the conversation. Then clarify the correct
consumer-owned target location. Create an issue, file, or PR only after explicit
approval.

## External changes

Status work is read-only unless the user requests otherwise. Before changing an
issue, project value, guide, or report:

1. show the exact repository, project, item, and field or document
2. show the old and new value or the complete draft
3. ask for explicit approval

Do not change field definitions or options as a side effect of reporting.

## Boundaries

### Always

- Confirm the scope and sources.
- Retrieve project fields dynamically when GitHub Projects is used.
- Separate source data, interpretation, assumptions, and data gaps.
- State the timestamp for data that can change.

### Ask first

- Create or change issues, project items, field values, guides, or PRs.
- Extend the analysis to repositories or systems outside the confirmed scope.

### Never

- Guess the project, field semantics, team boundary, or goal period.
- Present tracker activity as documented user or societal impact.
- Change external state without showing a draft and receiving explicit
  approval.
