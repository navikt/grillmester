---
name: grillmester-triage
description: "Assesses incoming issues and pull requests, verifies claims, identifies missing context and produces work-ready briefs. Use for inbox review, bug-report assessment, prioritisation, readiness decisions or a specific issue/PR that needs triage."
---

# Triage

Classify, verify, clarify, recommend and prepare;
grillmester-issue-management owns approved mutations.

## Discover the contract

Establish from consumer instructions and read-only tracker metadata:

- target repository and account
- issue types, labels, project fields and their semantics
- readiness criteria and closure policy
- templates, language and required attribution
- which authors or PR states count as intake work

Do not assume paths or familiar labels. Ask when a mapping is missing.

## Semantic outcomes

Map these concepts only to verified consumer labels or fields:

| Outcome | Meaning |
|---|---|
| Unassessed | Not evaluated |
| Needs context | A concrete question blocks verification or shaping |
| Ready for agent | Bounded, independently verifiable and delegable |
| Ready for human | Shaped, but needs human judgment or access |
| Declined | Duplicate, implemented, invalid or intentionally not pursued |

Discover categories; do not force bug/enhancement. Keep category, readiness
and priority separate.

## Show what needs attention

With a confirmed repository, query read-only for unassessed items, items
explicitly awaiting triage, and items awaiting context with new reporter
activity. Use consumer mappings and sort oldest first unless asked otherwise.
Include PRs only according to intake policy. Show counts, type and one-line
summary, then let the user choose.

## Triage one item

### 1. Gather

Read body, discussion, metadata and native relationships. For a PR, include
diff and review state. Reuse settled facts. Search for:

- an existing implementation or duplicate
- prior closed work with a relevant rationale
- task-relevant policy and domain documentation

Report where you looked. Absence of evidence is not evidence of absence.

### 2. Recommend

Present proposed category, semantic outcome, rationale and any verified local
label/type/project mapping without mutating it.

### 3. Verify

For a bug, use the repository's deterministic reproduction or diagnostic
workflow. For a PR, run the actual checks against its claims. Route operational
symptoms through deployed-environment diagnostics. Report confirmed,
contradicted or insufficient evidence with fresh evidence.

### 4. Clarify

Ask one question at a time and preserve settled context. Route lasting
decisions or domain terms through the consumer's documented policy.

### 5. Prepare

Use [AGENT-BRIEF.md](./AGENT-BRIEF.md) for ready items. For needs-context,
draft concrete unanswered questions. For declined items, draft a
self-contained rationale with verified duplicate or implementation evidence.
Follow consumer language and attribution; add no AI marker unless required.

## Approval boundary

Reading and drafting are read-only. Before posting, editing, closing, or
changing any label, type, assignee, relationship or project field:

1. show repository, item, every mutation and full comment
2. obtain explicit approval
3. apply only the approved set and verify it

The requested outcome is not permission for additional cleanup mutations.

## Grenser

- Always verify before declaring work ready or invalid.
- Ask before every external tracker write or scope expansion.
- Never guess tracker metadata or closure rationale.
- Never treat delivered closed work as evidence that an idea was rejected.
- Never mark work agent-ready without verifiable acceptance criteria.
