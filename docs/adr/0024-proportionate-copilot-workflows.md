---
status: accepted
date: 2026-10-24
---

# Proportionate workflows in Copilot

## Context

Choosing between Grillmester and Barista asks users to classify an assignment
before the work has been inspected. Grillmester already scales clarification
to uncertainty, but its implementation route also depends on file count and
test duration. A large, settled change can therefore trigger an unnecessary
handover. Barista remains useful as an explicitly solo workflow, including in
saved launcher settings and the focused Copilot payload.

Designer now supports a saved canvas workspace. Its instructions still mix
that route with portable server mechanics, Figma-specific delivery language,
and inconsistent browser and Aksel fallbacks. Several skills also ask for
approval again after the user has already authorized the exact action.

## Decision

- Recommend Grillmester for general repository delivery. After a proportionate
  facts, outcome and failure-case check, settled work proceeds directly to
  implementation and verification. Open choices still use the clarification
  methods from ADR 0010; documentation methods load when their purpose applies.
- For R0–R2 work, choose implementation ownership from uncertainty, a coherent
  scope, and the benefit of a separate implementer. File count and test duration
  alone do not force delegation. Preserve one active writer, explicit boundaries
  and stable material for review. Preserve the R3/R4 separation and review gates.
- Keep Barista, all existing agent IDs, model settings, invocation policies,
  saved defaults and focused payload membership. Removing Barista is a separate
  migration decision after comparative Copilot app trials.
- Keep Designer's mandate from ADR 0013. Use one delivery route at a time:
  native Designverksted when available, the portable browser workflow when
  needed, or Figma when requested. Load route mechanics conditionally.
- Distinguish production Aksel components from verified component markup in a
  bounded HTML sketch. Inspect the actual rendered state before making visual
  claims, and distinguish observed defects, trade-offs and research hypotheses.
- Reuse authorization for the specified target, action and scope. Ask for a
  missing material choice or authority; a review request never implies
  publication or contact with others. Client approval controls remain unchanged.
- Validate in the client whose behavior is claimed. Copilot app discovery and
  natural routing require an observed app session; CLI and deterministic
  protocol checks provide different evidence. Preserve the existing release
  gates rather than presenting app-first authoring as a new support guarantee.

## Consequences

No installation, runtime, storage, model or public-ID migration is required.
The existing generators continue to project the canonical prompt content.
The first improvement is less contradictory guidance and more conditional
loading, not a claimed speed or quality increase.

The [Copilot workflow validation cases](../testing/copilot-workflow-validation.md)
define the observations needed before considering role removal. Actual routing,
question counts and design quality remain unverified until those sessions run.
These trials supplement structural checks and do not replace human usability
testing of the design workspace.
