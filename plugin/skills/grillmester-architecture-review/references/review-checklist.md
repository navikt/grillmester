# Conditional Architecture Review Checklist

Use this reference only for branches that match the change. Treat every item as
a question to answer from repository evidence or current authoritative
guidance, not as an assumed requirement.

## Decision and evidence

- What outcome is sought, what is in scope, and who owns the decision?
- Which facts are verified, which are inferred, and which remain unknown?
- Which quality scenarios, constraints, and success measures distinguish the
  alternatives?
- Which existing decisions, contracts, or operational evidence constrain the
  choice?

## Boundaries and ownership

- Is each responsibility narrow and cohesive enough to have a clear owner?
- Which components, teams, producers, consumers, and operators cross the seam?
- Are contracts and dependency direction explicit, or does knowledge leak
  through shared state, coordinated deployment, or incidental coupling?
- Does the proposal put failure handling and consistency at the boundary that
  owns the relevant business invariant?
- What advice is needed, and who still owns the decision after receiving it?

## Data, identity, and trust

- Which data categories and caller identities cross each trust boundary?
- Are authentication, authorization, purpose, retention, and deletion
  responsibilities explicit?
- Could sensitive data, identifiers, payloads, or secrets reach logs, traces,
  metrics, errors, fixtures, or decision material?
- Are privileged actions auditable without recording the protected data?
- Does the change need a focused privacy, security, or threat review?

## Contracts and quality attributes

- Are API, event, file, schema, and storage contracts explicit, versionable,
  testable, and owned?
- Can relevant consumers tolerate retry, duplication, replay, reordering,
  partial failure, and schema evolution?
- Are latency, throughput, availability, recovery, consistency, and capacity
  expectations expressed as concrete scenarios?
- Does the design hide implementation complexity behind stable boundaries, or
  spread coordination and policy across callers?
- Which trade-offs remain if one quality attribute is optimized?

## Operations and delivery

- Which business and technical signals prove the change works in production?
- Are failure modes observable, alerts actionable, and recovery procedures
  owned?
- Are resource demand, quotas, data growth, external dependencies, and material
  cost drivers understood?
- Can old and new application, schema, and contract versions operate safely
  during delivery?
- Do build, dependency, infrastructure, and delivery changes preserve the
  required security and supply-chain controls?

## Migration and reversibility

- Is rollout backward compatible, gradual, parallel, or deliberately a
  cutover?
- What observable condition pauses rollout or triggers rollback?
- Can rollback avoid data loss, duplicate effects, or split-brain state?
- Are reconciliation, backfill, feature controls, or dual-read/write behavior
  needed, and how will they end?
- What exit criteria prove migration is complete?
- How and when will the old path, contract, data, and infrastructure be
  decommissioned?

## Review completion

The review is complete when every applicable branch is evidenced, reported as
an open question, or explicitly marked not applicable. The checklist produces
findings and decision candidates. It never decides ADR eligibility or changes
the repository's decision records.
