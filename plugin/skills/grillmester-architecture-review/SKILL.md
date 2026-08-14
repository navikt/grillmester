---
name: grillmester-architecture-review
description: Review consequential architecture proposals using repository evidence, boundaries, quality attributes, operations, alternatives, migration, and reversibility. Use for new services, cross-team contracts, platform choices, migrations, or hard-to-reverse design choices, including when Nav or NAIS context may change the recommendation. Do not trigger merely because a repository uses Nav or NAIS, or for concrete implementation, configuration, security/privacy review, or incident diagnosis.
---

# Review architecture

Review the proposal; do not author the decision. This skill produces findings
and decision candidates. `/grillmester-domain-modeling` alone decides whether a
candidate qualifies for an ADR and drafts or records it after the user
explicitly chooses that route.

Use this skill for consequential choices across system boundaries. If
organization- or platform-specific facts could change the recommendation,
identify and verify them explicitly. When Nav or NAIS context may matter, load
[the conditional Nav context](references/nav-context.md) and apply only branches
that could change the recommendation. Concrete follow-up work belongs to the
matching implementation or review specialist.

Use `/grillmester-security-review` for a concrete code, configuration, privacy,
or threat review. An architecture review may identify the need for that deeper
review without pretending to replace it.

## Establish the review surface

Read the proposal, relevant code and contracts, repository instructions,
existing decisions, and only the domain documentation needed for the affected
seam. Derive the actual stack and constraints from evidence; do not assume a
language, framework, storage technology, deployment platform, or application
shape.

Identify:

- the proposed change, desired outcome, and decision owner;
- affected system boundaries, owners, producers, consumers, and operators;
- data, identities, dependencies, and failure modes crossing each boundary;
- quality attributes and constraints that can distinguish good options;
- rollout, compatibility, operational, cost, and organizational constraints.

Separate repository facts, current authoritative external constraints,
inference, and missing context. Report missing facts as open questions rather
than inventing them. Verify time-sensitive external behavior before relying on
it.

## Review the applicable concerns

Review every concern that could materially change the recommendation:

1. **Boundaries and ownership** — responsibility, contracts, coupling,
   dependency direction, change coordination, and decision ownership.
2. **Quality attributes and trade-offs** — security, privacy, reliability,
   performance, scalability, maintainability, operability, and cost, expressed
   as concrete scenarios or constraints rather than generic virtues.
3. **Evolution and operations** — compatibility, delivery, observability,
   failure handling, migration, rollback, reversibility, and decommissioning.

For a new service, cross-boundary integration, storage or event seam,
authentication or authorization change, platform migration, or difficult-to-
reverse choice, load [the conditional architecture review
checklist](references/review-checklist.md). Apply only relevant branches; it is
neither a form nor an ADR template.

## Compare real alternatives

Compare genuine alternatives against the evidenced decision criteria. Include
the current design only when keeping it is a credible option. Do not manufacture
a fixed number of alternatives, force a "do nothing" option, or declare a
winner when the evidence does not support one.

Identify the people or teams whose knowledge is needed, while keeping decision
ownership explicit. Do not claim consultation occurred without evidence. Do
not include personal data, secrets, or protected details in review or decision
material. Before contacting anyone or sharing material, show the recipient,
channel, and draft and get explicit approval. Ask before any other external or
durable change.

## Return a review, not an ADR

Return:

- **Scope and evidence** — facts, sources, assumptions, and decision criteria;
- **Findings** — ordered by consequence, each with evidence, impact, and a
  concrete recommendation;
- **Alternatives and trade-offs** — only where a real choice exists;
- **Open questions** — including who can answer them;
- **Overall recommendation** — with confidence and residual risk;
- **Decision candidates** — hard-to-reverse choices whose rationale a future
  reader may otherwise lose.

Do not decide ADR eligibility, draft an ADR, edit decision records, or imply
that the review made the team's decision. For each decision candidate, explain
why durable documentation may help and ask whether the user wants to route it
to `/grillmester-domain-modeling`. Make that handoff only after the user
explicitly chooses it.
