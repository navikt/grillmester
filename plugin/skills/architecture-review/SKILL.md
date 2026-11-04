---
name: architecture-review
description: "Evaluate a consequential architecture proposal. Use for new services, cross-team boundaries, platform choices or costly migrations; use `improve-codebase-architecture` to discover refactoring candidates in existing code and `security-review` for security analysis."
---

# Review architecture

Review the proposal; do not author the decision. This skill produces findings
and decision candidates. `/domain-modeling` alone decides whether a
candidate qualifies for an ADR and proposes it. Use `/improve-codebase-architecture` when the work
starts with finding refactoring opportunities rather than evaluating a named
proposal.

Use this skill for consequential choices across system boundaries. If
organization- or platform-specific facts could change the recommendation,
identify and verify them explicitly. Concrete follow-up work belongs to the
matching implementation or review specialist.

Use `/security-review` for a concrete code, configuration, privacy,
or threat review. An architecture review may identify the need for that deeper
review without pretending to replace it.

## Read first

1. Find every row below that the task touches.
2. Read those references before you edit, answer or run a command.
3. Name the references you read when you report.

| The proposal touches | Read |
|---|---|
| **Nav context:** Nais, Nav teams, Nav identity or Nav data | [nav-context.md](references/nav-context.md), applying only branches that could change the recommendation |
| **Consequential seam:** a new service, cross-boundary integration, storage or event seam, authentication or authorization change, platform migration or hard-to-reverse choice | [review-checklist.md](references/review-checklist.md), applying only relevant branches; it is neither a form nor an ADR template |

## Establish the review surface

Read the proposal, relevant code and contracts, repository instructions,
existing decisions, and only the domain documentation needed for the affected
seam. Derive the actual language, framework, storage technology, deployment
platform, application shape and constraints from evidence.

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

## Compare real alternatives

Compare genuine alternatives against the evidenced decision criteria. Include
the current design only when keeping it is a credible option. Do not manufacture
a fixed number of alternatives, force a "do nothing" option, or declare a
winner when the evidence does not support one.

Identify the people or teams whose knowledge is needed, while keeping decision
ownership explicit. Do not claim consultation occurred without evidence. Do
not include personal data, secrets, or protected details in review or decision
material. Before contacting anyone or sharing material, show the recipient,
channel, and draft if that communication has not already been authorized.
Reuse explicit authority for the same recipient, channel and bounded content;
otherwise ask for the missing authority. A review request alone does not
authorize contacting others, publishing or other external or durable changes.
Carry out separately requested changes within their authorized scope without
adding a second approval gate.

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
in one line why recording it may help; `/domain-modeling` decides eligibility
and proposes the ADR.
