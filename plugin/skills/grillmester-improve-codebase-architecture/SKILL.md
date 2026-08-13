---
name: grillmester-improve-codebase-architecture
description: "Finds deepening opportunities that improve module depth, locality, leverage, test seams, and navigability. Use when the user asks to improve architecture, consolidate tightly coupled or shallow modules, find refactoring candidates, or explain why code is difficult to test or navigate."
license: MIT
---

# improve-codebase-architecture

Uncover architectural friction in this repository and propose **deepening opportunities** — refactorings that make shallow modules deep. The goal is testability, and that both humans and AI can navigate the code easily.

**Role:** this _finds_ candidates (discovery). Design the interface for a chosen
candidate inline with two genuinely different alternatives and interrogate the
choice with `/grillmester-grilling`. When lasting concepts or decisions ought to be
documented, recommend the documented route and wait for the user's choice. Use
`/grillmester-architecture-review` for architecture review and
`/grillmester-domain-modeling` after the
documented route has been chosen.

The skill is **informed by** domain language and settled decisions when the
repository exposes them, but it does not require a glossary, ADR directory, or
agent-documentation layout. Discover those artifacts from repository evidence
and load only what touches the area. This is the calling workflow's discovery
stage: findings feed into `/grillmester-grilling`, the active plan and verification.

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

Write a self-contained HTML file to the OS temp directory so that nothing ends up in the repository. Resolve the temp directory from `$TMPDIR` with `/tmp` as fallback, and write to `<tmpdir>/architecture-candidates-<timestamp>.html`. Open it for the user (`open <path>` on macOS, `xdg-open <path>` on Linux) and state the absolute path.

Each candidate gets a card with: **Files**, **Problem** (one sentence), **Solution** (one sentence), **Benefits** (bullet list in the vocabulary — locality/leverage/test surface), **Before/after diagram**, and **Recommendation strength** (`Strong`, `Worth exploring`, `Speculative`). Close with a **Top recommendation**: which one you would take first and why.

Use the repository's discovered domain vocabulary when one exists, and the
architecture vocabulary above for structure. Prefer the domain concept over a
class name or generic "service" label.

**ADR conflict:** if a candidate contradicts an existing ADR, raise it only when the friction is real enough to justify reopening the decision. Mark it clearly on the card (yellow callout: _"contradicts ADR-0007 — but worth reopening because…"_). Do not list every theoretical refactoring an ADR forbids.

See [HTML-REPORT.md](HTML-REPORT.md) for the full HTML scaffold, diagram patterns and style guide.

**Do not** propose concrete interfaces yet. Once the file is written, ask the user: "Which of these do you want to explore?"

### 3. Grilling loop

Once the user has chosen a candidate, run `/grillmester-grilling` to walk down the decision
tree together with them — constraints, dependencies, the shape of the deepened
module, what sits behind the seam, which tests survive. This is the calling
workflow's design stage.

When clarified concepts or qualifying, lasting decisions ought to be written,
recommend `/grillmester-grill-with-docs`, explain why and wait for the user's choice. Before
a documented route is chosen, keep results in the conversation and active task.

After a documented route has been chosen, documentation happens **continuously**
as decisions fall into place:

- **Naming a deepened module after a missing domain concept?** Use
  `/grillmester-domain-modeling` to update the repository's chosen vocabulary artifact when
  the documented route has been approved.
- **Sharpening a vague term along the way?** Update that same artifact when it
  exists and the write is in scope.
- **Does the user reject the candidate for a load-bearing reason?** Consider an
  ADR only when the decision is hard to reverse, surprising without context and
  the result of a real trade-off. Skip transient ("not worth it right now") and
  self-evident reasons. Use `/grillmester-architecture-review` for consequential
  architecture questions; use the bundled `/grillmester-nav-architecture-review`
  when NAV-specific consequences need assessing. Use
  `/grillmester-domain-modeling` for the ADR itself.
- **Want to explore alternative interfaces for the deepened module?** Design two genuinely different alternatives sequentially, inline, before comparing them. Use subagents only for compact, read-only divergent exploration, never for parallel writing.

### 4. Connect to the phase loop

Once the chosen deepening has been thoroughly grilled:

- Write the task scope to the issue/plan. After a documented route has been
  chosen, `/grillmester-domain-modeling` writes new concepts and qualifying decisions;
  maintained detail goes to the relevant topic document.
- Break the deepening down into a safe, incremental refactoring plan in the
  active task (optionally on to `/grillmester-to-issues` for grabbable slices).
- Define what proves the deepening succeeded (tests through a single
  interface, the seam confirmed by two adapters), and return that to the calling
  workflow.
