---
name: grillmester-architecture-review
description: Review a proposed architecture change against NAV platform, security, privacy, operability, and team-boundary constraints. Use for new services, cross-team integrations, storage or event seams, authentication or accessPolicy changes, personal-data processing, platform migrations, or deviations from established NAV patterns.
license: MIT
---

# Review NAV Architecture

Review the proposal; do not author the decision. `/grillmester-domain-modeling` owns the ADR
gate and any resulting ADR. This skill contributes NAV-specific evidence,
risks, questions, and advice.

Use `/grillmester-security-review` for a concrete code, configuration, or threat review.
Use this skill when the review must connect architecture, security/privacy,
platform operations, and team boundaries around a proposed design.

## Establish the review surface

Read the proposal, relevant code and contracts, repository instructions, and
only the domain documents needed for the affected seam. Derive the actual
stack and constraints from the target repository; do not assume a language,
framework, storage technology, or application shape.

Identify:

- the decision or change being reviewed;
- the owning team and affected producers, consumers, and platform surfaces;
- data categories and caller identities crossing the seam;
- rollout, compatibility, and operational constraints.

If a fact is missing from the repository, report it as an open question rather
than inventing it.

## Review through three lenses

Cover every applicable lens:

1. **Architecture** — boundaries and ownership, contracts, coupling, viable
   alternatives, affected teams, and use of established platform capabilities.
2. **Security and privacy** — data classification, purpose and retention,
   authentication, authorization, `accessPolicy`, PII handling, auditability,
   and whether specialist privacy or security assessment is needed.
3. **Platform and operations** — NAIS dependencies, capacity, observability,
   delivery, rollback, migration, failure handling, and decommissioning.

For a new service, new data or auth path, cross-team contract, storage/event
seam, or migration, load
[the conditional NAV review checklist](references/review-checklist.md). Apply
only the relevant branches; it is not an ADR template or a form to fill in.

When current platform or regulatory behavior affects the recommendation,
verify it against the repository's pinned guidance or current authoritative
NAV documentation.

## Seek advice without transferring ownership

Identify teams that own or consume the affected contract and the advice needed
from them. NAV architecture advice informs the owning team's decision; it is
not an approval substitute. Do not claim consultation occurred unless evidence
shows it did.

Compare genuine alternatives when a choice exists. Do not manufacture a fixed
number of options or force "do nothing" into every review.

## Return a review, not an ADR

Return:

- **Scope and evidence**
- **Findings**, ordered by consequence, each with evidence, impact, and a
  concrete recommendation
- **Open questions**
- **Overall recommendation**
- **Decision evidence**, including reversibility, context a future reader would
  otherwise miss, and genuine alternatives or trade-offs

Do not decide ADR eligibility or create or edit an ADR in this skill. If the
user wants a durable decision considered, hand the evidence to
`/grillmester-domain-modeling`, which owns the gate and applies the repository's one
operative ADR format.
