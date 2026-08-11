---
name: grillmester-to-spec
description: Use only after the user explicitly selects To Spec to turn an already resolved conversation or design into a concise engineering specification; do not interview or reopen decisions.
license: MIT
---

# To Spec

Synthesize what is already resolved into one durable engineering specification.
Do not run a new interview, invent missing choices, or create a spec when a
single actionable issue already carries the work.

Start only after the user has explicitly selected `/grillmester-to-spec` in the current
conversation. Relevance or a prior recommendation is not selection.

Read the repository's issue-tracker adapter before tracker use. Follow its
language, terminology, label, and write-authorization rules.

## 1. Establish the source

Use the current conversation, the active issue or plan, relevant maintained
domain documentation, and only the decisions that constrain this work. Explore
the repository when needed to verify the current state and existing test seams.

Stop and return to the planning conversation when the problem, outcome, scope,
or a material user-owned choice is unresolved.

## 2. Draft the specification

Prefer the highest existing test seam and the fewest seams that can prove the
outcome. Give the issue a functional, plain-language title. Start with the
change and its value so a product lead or designer can understand the work
without reading technical detail. Write only what implementation and review
need:

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

## 3. Confirm and publish

Present the complete draft and proposed tracker metadata. Publish only after
explicit human authorization. Apply only labels and relationships defined by
the tracker adapter, then read the published issue back and verify it.

A specification does not imply issue decomposition. Recommend `/grillmester-to-issues`
only when several independently deliverable slices need durable tracking.
