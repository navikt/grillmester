---
name: domain-modeling
description: Challenge and maintain canonical domain terminology and qualifying architectural decisions during authorized design work. Use when concepts, boundaries, or durable trade-offs change; reading existing vocabulary alone does not need this skill.
---

# Domain Modeling

Actively build and sharpen the project's domain model as you design. This is
the *active* discipline — challenging terms, inventing edge-case scenarios, and
writing the glossary and decisions down the moment they crystallise. (Merely
*reading* `CONTEXT.md` for vocabulary is not this skill — that's a one-line
habit any skill can do. This skill is for when you're changing the model, not
just consuming it.)

## Repository conventions

Before using the default paths below, follow any domain-documentation policy
linked by the repository's instructions. That policy owns local paths, artifact
language, and established formats. If no policy exists, use the defaults here.

## Durable write boundary

Maintaining resolved terms and qualifying decisions is part of authorized
design or implementation work when it preserves the meaning or rationale of
the agreed change. Follow the repository's documentation policy and conventions.
A direct user request to document, including user invocation of
`domain-modeling` or `grill-with-docs`, also supplies that scope. The user need
not select a skill or approve the same documentation route again.

Skill selection does not expand the task: an exploratory question, review, or
explicit discussion-only request may identify candidates without authorizing
edits. In that case, complete the investigation and show the proposed target
and concrete change before asking for the smallest missing authority. Never
record an unresolved user-owned choice as settled. Once the work is authorized
and the decision resolved, capture it inline under the repository's policy.

## ADR ownership

This skill is the single owner of the ADR eligibility gate and ADR drafting.
Architecture-review skills return findings and **decision candidates**; they do
not decide that an ADR is warranted and they do not draft one. A candidate or
handoff from another skill does not expand the user's authorized scope.

Discover the repository's established ADR language, location, numbering, status
model, and format. Then apply the eligibility gate below. If the candidate does
not meet all three criteria, explain why and keep the result in the conversation
or the more appropriate existing document. If it qualifies, draft one decision using
the repository's format, or [ADR-FORMAT.md](./ADR-FORMAT.md) only when no local
format exists. Show the target and draft before any write outside the already
authorized workflow; do not repeat an approval request within that scope.

## File structure

Most repos have a single context:

```text
/
├── CONTEXT.md
├── docs/
│   └── adr/
│       ├── 0001-event-sourced-orders.md
│       └── 0002-postgres-for-write-model.md
└── src/
```

If a `CONTEXT-MAP.md` exists at the root, the repo has multiple contexts. The
map points to where each one lives:

```text
/
├── CONTEXT-MAP.md
├── docs/
│   └── adr/                          ← system-wide decisions
├── src/
│   ├── ordering/
│   │   ├── CONTEXT.md
│   │   └── docs/adr/                 ← context-specific decisions
│   └── billing/
│       ├── CONTEXT.md
│       └── docs/adr/
```

Create files lazily — only when you have something to write. If no
`CONTEXT.md` exists, create one when the first term is resolved. If no
`docs/adr/` exists, create it when the first ADR is needed.

## During the session

### Challenge against the glossary

When the user uses a term that conflicts with the existing language in
`CONTEXT.md`, call it out immediately. "Your glossary defines 'cancellation' as
X, but you seem to mean Y — which is it?"

### Sharpen fuzzy language

When the user uses vague or overloaded terms, propose a precise canonical term.
"You're saying 'account' — do you mean the Customer or the User? Those are
different things."

### Discuss concrete scenarios

When domain relationships are being discussed, stress-test them with specific
scenarios. Invent scenarios that probe edge cases and force the user to be
precise about the boundaries between concepts.

### Cross-reference with code

When the user states how something works, check whether the code agrees. If you
find a contradiction, surface it: "Your code cancels entire Orders, but you just
said partial cancellation is possible — which is right?"

### Update the glossary inline

When a term is resolved, update the repository's glossary right there. Don't
batch these up — capture them as they happen. Use the local format when one is
defined; otherwise use [CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md).

The glossary should be totally devoid of implementation details. Do not treat
it as a spec, a scratch pad, or a repository for implementation decisions. It
is a glossary and nothing else.

### Record ADRs sparingly

Create an ADR only when all three are true:

1. **Hard to reverse** — the cost of changing your mind later is meaningful.
2. **Surprising without context** — a future reader will wonder "why did they
   do it this way?"
3. **The result of a real trade-off** — there were genuine alternatives and
   you picked one for specific reasons.

If any of the three is missing, skip the ADR. Use the format in
[ADR-FORMAT.md](./ADR-FORMAT.md).

For a decision candidate returned by `/architecture-review`, first
explain why it does or does not pass this gate. Record it only when the decision
is resolved and durable documentation is within the authorized task. Review
output alone never settles the decision or expands that authority.
