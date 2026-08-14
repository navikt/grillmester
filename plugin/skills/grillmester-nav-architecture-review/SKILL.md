---
name: grillmester-nav-architecture-review
description: Review architecture choices that specifically depend on Nav or NAIS platform, integration, identity, deployment, security, privacy, operability, or team-governance constraints. Use for Nav services, cross-team contracts, NAIS resources and migrations, Nav authentication or accessPolicy changes, and Nav data flows; use grillmester-architecture-review for platform-independent review.
---

# Review Nav architecture

Perform a Nav-specific architecture review of a proposed change. This skill is
the specialisation for decisions where the Nav or NAIS context may change the
recommendation. Use `/grillmester-architecture-review` when the assessment is
platform-independent.

The review provides findings, advice, and decision candidates; it does not
author the decision. `/grillmester-domain-modeling` owns both ADR qualification
and any ADR draft or durable change, and is used only after the user explicitly
chooses that route.

## Bound the Nav surface

Discover the consumer repository's actual context before recommending anything:

1. Read relevant repository instructions, code, existing decisions, manifests,
   contracts, and architecture documentation.
2. Identify the desired outcome, decision owner, affected apps and teams,
   producers and consumers, data flow, data categories, caller identities, and
   operating environment.
3. Determine which Nav surfaces are actually affected: NAIS resources, network
   and deployment, identity and tokens, access policy, data or events,
   observability, platform services, or cross-team governance.
4. Distinguish verified repository facts, current authoritative guidance,
   interpretations, and missing context. Report missing facts as open questions.

For platform properties, identity mechanisms, security requirements, or other
time-sensitive guidance, use current authoritative documentation. The examples
in this skill are clues to what must be verified, not current policy in
themselves.

## When the specialisation is relevant

- A new or materially changed Nav service, system boundary, or cross-team
  contract.
- A NAIS resource, platform integration, data or event flow, or migration.
- Changed Nav authentication, token flow, authorisation, or `accessPolicy`.
- New or materially changed processing of personal data in a Nav context.
- A platform deviation or operational decision that affects Nav governance,
  other teams, or production readiness.

An internal refactoring choice or portable technology trade-off usually belongs
in `/grillmester-architecture-review`. Use this specialisation only for the Nav
part when a broader review contains both.

## Three Nav perspectives

Load the [perspective checklists](./references/perspektiv-sjekklister.md), and
use only the branches that fit the verified context:

1. **Architecture and governance** — team autonomy, contract ownership,
   platform capabilities, deviations, and the need for advice from affected
   teams.
2. **Security and privacy** — data categories, purpose and retention, caller
   identity, token flow, authorisation, `accessPolicy`, PII, audit, and the need
   for specialist assessment.
3. **NAIS platform and operations** — declared resources, network, capacity,
   observability, delivery, failure handling, migration, rollback, and
   decommissioning.

For each relevant perspective, report the fact and source, risk or concern,
recommendation, and remaining uncertainty. Use
`/grillmester-security-review` when a specific design, configuration, or trust
boundary requires a deeper security or privacy review.

## Alternatives and advice

Compare real alternatives against explicit decision criteria when a choice
exists. Include the current state only when retaining it is a credible
alternative. Do not construct a fixed number of alternatives or force in "do
nothing".

Identify who owns the decision, who owns or uses the contracts, and which advice
is needed. Architecture Advice informs the team's decision; it is not central
approval. Do not claim that someone was consulted without evidence. Do not
contact other teams or share material without the user's explicit approval;
show the recipient, channel, and draft first.

## Return a review, not an ADR

Return:

- **Scope and evidence** — including which Nav surfaces were verified;
- **Findings for each relevant Nav perspective** — prioritised by consequence,
  with evidence, impact, and recommendation;
- **Alternatives and trade-offs** — when a genuine choice exists;
- **Open questions** — naming who can answer or which authoritative source to
  consult;
- **Overall recommendation** — with uncertainty, residual risk, and necessary
  advice;
- **Decision candidates** — hard-to-reverse choices where the Nav context
  explains an otherwise surprising trade-off.

Do not decide ADR qualification, draft an ADR, edit decision documentation, or
change status. Explain why a candidate may deserve durable documentation, ask
the user whether it should be routed onward, and use
`/grillmester-domain-modeling` only after an explicit choice.

## Related skills

- `/grillmester-architecture-review` for platform-independent architecture
  questions
- `/grillmester-security-review` for a deeper security and privacy review

The review may also recommend `grillmester-nais-manifest` for concrete manifest
work, `grillmester-auth-overview` for identity mechanisms,
`grillmester-observability-setup` for telemetry and alerting, or
`grillmester-nav-troubleshoot` for operational diagnosis. They are deep dives,
not prerequisites; complete this review and report missing evidence if a
necessary runtime capability is unavailable.

## Boundaries

### Always

- Assess only the Nav perspectives that may change the recommendation.
- Show evidence, trade-offs, the decision owner, and remaining uncertainty.
- Verify time-sensitive guidance against authoritative sources.
- Note unresolved owners, data categories, and cross-team dependencies.

### Ask first

- Contact affected teams or share review or decision material.
- Make external or durable changes based on the recommendation.

### Never

- Make or document the decision on behalf of the team.
- Create, write, or change an ADR in this skill.
- Use the review as compliance, privacy, or security approval.
- Document personal data, secrets, or other protected details in review or
  decision material.
