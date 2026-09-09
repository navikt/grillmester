---
name: improve-codebase-architecture
description: "Find refactoring opportunities that simplify module boundaries and improve testability and navigation. Use when existing code is tightly coupled, shallow or hard to change; use `architecture-review` to evaluate a concrete architecture proposal."
---
# improve-codebase-architecture

> **OpenCode v1:** Skill names below are exact IDs from the active catalog, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Uncover architectural friction in this repository and propose **deepening opportunities** — refactorings that make shallow modules deep. The goal is testability, and that both humans and AI can navigate the code easily.

**Role:** this _finds_ candidates (discovery). Design the interface for a chosen
candidate inline with two genuinely different alternatives and interrogate the
choice with `grilling`. When lasting concepts or decisions ought to be
documented, use `grill-with-docs` within the active task's documented-work
boundary. Use `architecture-review` to evaluate a concrete consequential
proposal; `domain-modeling` owns qualifying durable documentation.

The skill is **informed by** domain language and settled decisions when the
repository exposes them, but it does not require a glossary, ADR directory, or
agent-documentation layout. Discover those artifacts from repository evidence
and load only what touches the area. This is the calling workflow's discovery
stage: findings feed into `grilling`, the active plan and verification.

## Vocabulary

Use the deep-module vocabulary precisely: a **module** hides an **implementation** behind a small **interface**; **depth** is the amount of complexity the interface hides. A **seam** is the place where the module can be separated from an **adapter**. **Locality** keeps related knowledge together, and **leverage** is how much complexity a single interface carries. Do not drift into "component", "service", "layer" or "API" when these more precise words fit.

**The deletion test** (the operational tool for discovery): would deleting the module *concentrate* complexity (good — it was shallow) or merely move it (then it was real)? A "yes, it concentrates" is the signal you are hunting for.

## Process

### 1. Explore

Discover the repository's domain vocabulary, decision records and architecture
guidance when they exist. Read only the artifacts that touch the area, then walk
the codebase organically. Do not follow rigid heuristics. Note where you
experience friction. Common deepening opportunities include:

- **Thin modules in a call chain:** entry point → coordinator → adapter where
  each link does little more than forward. Consolidate responsibility behind
  one deep interface.
- **Mappers extracted purely for testability:** pure conversion functions whose
  real bugs sit in how callers compose them, leaving no locality.
- **Shallow client wrappers:** a transport call wrapped in a class that hides
  nothing — authentication, retry and error contracts still leak to callers.
- **Scattered event logic:** ingestion, deserialization, idempotency or replay,
  and domain behavior spread across modules without one seam.
- **Leaking persistence:** query, connection, migration or transaction details
  seeping out of the persistence adapter.
- **Hard to test through the interface:** modules that require booting most of
  the application to exercise one behavior — a sign the seam is misplaced.

Apply the deletion test to anything you suspect is shallow.

### 2. Present the candidates as an HTML report

Write an offline, self-contained, script-free HTML file in a fresh private OS
temporary directory. Treat every value derived from the repository as
untrusted data and follow the safe-write, escaping, static-markup, and Content
Security Policy contract in
[HTML-REPORT.md](HTML-REPORT.md). Do not run `open` or `xdg-open`. State the
absolute path and offer to open the report only if the user explicitly asks
after it has been written.

Each candidate gets a card with: **Files**, **Problem** (one sentence), **Solution** (one sentence), **Benefits** (bullet list in the vocabulary — locality/leverage/test surface), **Before/after diagram**, and **Recommendation strength** (`Strong`, `Worth exploring`, `Speculative`). Close with a **Top recommendation**: which one you would take first and why.

Use the repository's discovered domain vocabulary when one exists, and the
architecture vocabulary above for structure. Prefer the domain concept over a
class name or generic "service" label.

**ADR conflict:** if a candidate contradicts an existing ADR, raise it only when the friction is real enough to justify reopening the decision. Mark it clearly on the card (yellow callout: _"contradicts ADR-0007 — but worth reopening because…"_). Do not list every theoretical refactoring an ADR forbids.

See [HTML-REPORT.md](HTML-REPORT.md) for the full HTML scaffold, diagram patterns and style guide.

**Do not** propose concrete interfaces yet. Once the file is written, ask the user: "Which of these do you want to explore?"

### 3. Grilling loop

Once the user has chosen a candidate, run `grilling` to walk down the decision
tree together with them — constraints, dependencies, the shape of the deepened
module, what sits behind the seam, which tests survive. This is the calling
workflow's design stage.

When clarified concepts or qualifying, lasting decisions ought to be written,
use `grill-with-docs` and follow `domain-modeling` for documentation scope
and write authorization. Do not ask for the same documented-work choice again
when the active task already provides it.

Within authorized documented work, documentation happens **continuously**
as decisions fall into place:

- **Naming a deepened module after a missing domain concept?** Use
  `domain-modeling` to update the repository's chosen vocabulary artifact when
  the resolved term is in scope.
- **Sharpening a vague term along the way?** Update that same artifact when it
  exists and the write is in scope.
- **Does the user reject the candidate for a load-bearing reason?** Consider an
  ADR only when the decision is hard to reverse, surprising without context and
  the result of a real trade-off. Skip transient ("not worth it right now") and
  self-evident reasons. Use `architecture-review` for consequential
  architecture questions, including when Nav or NAIS context changes the
  recommendation. Use `domain-modeling` for the ADR itself.
- **Want to explore alternative interfaces for the deepened module?** Design two genuinely different alternatives sequentially, inline, before comparing them. Use subagents only for compact, read-only divergent exploration, never for parallel writing.

### 4. Connect to the phase loop

Once the chosen deepening has been thoroughly grilled:

- Record the task scope in the active plan. Within authorized documented
  work, `domain-modeling` writes new concepts and qualifying decisions;
  maintained detail goes to the relevant topic document.
- Break the deepening down into a safe, incremental refactoring plan in the
  active task (optionally on to `to-issues` for grabbable slices).
- Define what proves the deepening succeeded (tests through a single
  interface, the seam confirmed by two adapters), and return that to the calling
  workflow.
