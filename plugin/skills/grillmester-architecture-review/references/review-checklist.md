# Conditional NAV Architecture Review Checklist

Use this reference only for branches that match the change. Treat every item as
a question to verify from repository evidence or current authoritative
guidance, not as an assumed answer.

## Architecture and team boundaries

- Is the service or module responsibility narrow enough to have a clear owner?
- Which teams produce or consume the affected API, event, data, or policy?
- Does the change preserve team autonomy and explicit contracts rather than
  shared databases or coordinated deployment?
- Can an established NAV platform capability replace custom infrastructure?
- Are synchronous and asynchronous boundaries chosen for domain and failure
  semantics rather than convenience?
- Are deviations from established repository or NAV patterns explicit and
  justified?
- What advice is needed from affected teams, and who still owns the decision?

## Security and privacy

- Which data categories cross the seam, and what classification applies?
- What is the processing purpose, legal basis, retention period, and deletion
  behavior?
- Who initiates each call: an end user, employee, internal workload, batch, or
  external organization?
- Which current identity mechanism, token exchange, claims, scopes, and
  authorization checks are required for that caller?
- Do inbound and outbound `accessPolicy` rules grant only the required access?
- Could personal data, identifiers, payloads, or secrets reach logs, traces,
  metrics, error messages, or ADR text?
- Is sensitive access auditable without recording raw personal data?
- Does changed processing require privacy, DPIA, or security specialist review?
- Are secrets held by supported platform facilities and rotated appropriately?

## Data, APIs, and events

- Are API and event contracts explicit, versionable, and owned?
- Are consumers identified before a schema, topic, or semantic change?
- Can consumers tolerate replay, duplication, reordering, partial failure, and
  schema evolution where those conditions apply?
- Is idempotency defined at the correct business boundary?
- Are storage ownership, retention, indexing, backup, and recovery understood?
- Can old and new application versions operate safely during schema or contract
  rollout?

## NAIS platform and operability

- Are required applications, external hosts, topics, databases, buckets,
  secrets, and policies declared through supported NAIS mechanisms?
- Are replicas, memory, CPU requests, probes, and shutdown behavior appropriate
  for the actual runtime and workload?
- Which business and technical signals prove the change works in production?
- Are logs structured and free of personal data and secrets?
- Are alerts actionable, owned, and linked to recovery guidance?
- Does delivery include dependency and supply-chain controls appropriate to the
  repository?
- Are quotas, data egress, storage growth, and other material cost drivers
  understood?

## Migration and rollback

- Is rollout backward compatible, gradual, parallel, or deliberately a cutover?
- What is the rollback path, and can it avoid data loss or split-brain state?
- Are feature toggles, reconciliation, or dual-read/write behavior needed?
- What observable condition triggers rollback?
- What exit criteria prove migration is complete?
- How and when will the old path, contract, data, and infrastructure be
  decommissioned?

## Review completion

The review is complete when every applicable branch above is evidenced,
reported as an open question, or explicitly marked not applicable. The
checklist produces findings and ADR candidacy; it never changes the ADR shape.
