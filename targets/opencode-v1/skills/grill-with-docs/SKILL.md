---
name: grill-with-docs
description: "Clarify one coherent problem or design decision against the repository's domain model, recording resolved terms and qualifying architectural decisions as part of authorized design work. Use without an explicit grill phrase; Wayfinder adds a persistent map when several dependent decisions span sessions."
---
# Grill with Docs

> **OpenCode v1:** Skill names below are exact IDs from the active catalog, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Load `grilling` and `domain-modeling` through the active skill catalog and the
runtime's native loading mechanism. Combine the shared interview method with
the repository's vocabulary and decision history. Start automatically when a
request needs coherent design clarification; the user need not name this skill
or separately select a documentation mode.

Inspect the relevant domain documents and implementation before asking. Test
the proposal against established terms, boundaries, invariants, and concrete
edge cases. Ask one material question at a time, recommend an answer with its
consequence, and wait for the user's choice before dependent work.

As terms and decisions are resolved, apply `domain-modeling` within the user's
authorized scope and the repository's language, paths, and formats. Write only
what qualifies: a conversation can complete without creating a glossary entry
or an ADR. Never turn an unchosen recommendation into a documented decision.
Honor explicit discussion-only or read-only requests.

If the work exposes several dependent decisions that need a durable shared map
across sessions, use `wayfinder` to organize them and continue this method for
the active decision. Implementation size alone does not justify a map. When
the direction is settled, summarize it and continue the authorized delivery
workflow without an extra skill-selection or confirmation step.
