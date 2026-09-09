---
name: to-spec
description: "Turn resolved requirements and design choices into a concise engineering specification. Use when the user asks to capture an agreed plan for implementation; use `grill-with-docs` for unresolved decisions and `to-issues` for several independently deliverable slices."
---
# To Spec

> **OpenCode v1:** Skill names below are exact IDs from the active catalog, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Synthesize what is already resolved into one durable engineering specification.
Reuse the agreed decisions and existing artifacts; create a separate spec only
when requested or when the user accepts it as the deliverable.

Use this workflow when the user asks for a specification or accepts that
deliverable in ordinary language; naming the skill is unnecessary. Do not
create a specification merely because the planning conversation is resolved,
or automatically chain it after another skill.

Follow the user's requested destination, such as `docs/payment-design.md`.
Otherwise use the repository's established spec location or return the draft
in the conversation. A local document needs no tracker setup or issue metadata.

## 1. Establish the source

Use the current conversation, the active issue or plan, relevant maintained
domain documentation, and only the decisions that constrain this work. Explore
the repository when needed to verify the current state and existing test seams.

Resolve a material gap in the problem, outcome or scope before committing to
that part of the specification. Ask only for choices the existing brief cannot
answer; continue drafting the settled parts without inventing decisions.

## 2. Draft the specification

Prefer the highest existing test seam and the fewest seams that can prove the
outcome. Give the specification a functional, plain-language title. Start with
the change and its value so a product lead or designer can understand the work
without reading technical detail. Write only what implementation and review
need, omitting sections that add no useful context:

```markdown
## In short

<one or two sentences: who or what benefits, what changes, and why it matters>

## Acceptance criteria

- [ ] <externally verifiable behavior>

## Locked decisions

- <decision and the constraint it creates>

## Implementation context

- <relevant current state, technical boundary, risk, or integration seam>

## Proof

- <test seam and required evidence>

## Non-goals

- <explicit boundary>

## Dependencies

- <team, system, or ticket dependency, or none>
```

Include user stories only when they clarify genuinely different actors or
behaviors; never force technical work into “As a …” prose. Put implementation
context after the human-readable opening, but retain the evidence, constraints,
risks, integration seams, and proof an implementer or agent needs. Avoid file
inventories, repeated decision rationale, speculative future work, and
exhaustive implementation prose. Inline a small schema, type, or state-machine
fragment only when it carries a decision more precisely than prose.

## 3. Deliver to the requested destination

Write the local document when that is the requested deliverable, then read it
back for accuracy. Reuse existing authorization; an agreed plan and a request
to write it do not need another confirmation. If the user requested only a
draft, return the draft.

Only when delivering to a tracker, discover its contract from consumer-owned
instructions, templates and read-only metadata. Use `issue-management` for
tracker mechanics. Apply only established labels and native relationships and
read the published issue back. Stop before a tracker write if the target,
required metadata or authorization remains unresolved; prepare the complete
draft first. A request to publish this specification is authorization for that
bounded write, without an additional approval round.

A specification does not imply issue decomposition. Recommend `to-issues`
only when several independently deliverable slices need durable tracking.
