---
name: grillmester-nav-troubleshoot
description: "Diagnoses failures in deployed Nais workloads using runtime evidence from Kubernetes, deployment status, metrics, logs and traces. Use for pod startup failures, deploy failures, 401/403 responses, message-consumer lag, database connectivity, latency, restarts or conflicting production signals."
license: MIT
---

# Nav Troubleshoot

Locate a deployed-environment cause before proposing a fix. When the standard
`grillmester` package is also installed, optionally route a confirmed code
defect to `grillmester-diagnosing-bugs` for implementation and regression
testing. Without that package, keep this diagnostic skill read-only: report a
minimal reproduction, the confirmed evidence, a proposed regression-test
boundary and the smallest reversible fix, then hand implementation back to the
user or repository workflow. Mark `NEEDS_CONTEXT` when the reproduction or
expected behavior cannot be established from available evidence.

## Establish runtime identity

Do not assume environment names, namespace, app, cluster, container, repository
or observability labels.

1. Read consumer-owned deployment and operational documentation.
2. Confirm target environment, cluster, namespace, workload/app, container and
   time window with repository evidence or the user.
3. Detect the actual stack in the failing path: runtime, auth mechanism,
   messaging client, database, migration tool and observability backends.
4. Record the last known good state and relevant deploy/config changes.
5. Ask for any fact needed to make a command target unambiguous.

Never use a placeholder, inferred label or value copied from another service in
a live command.

## Evidence loop

1. State the observed symptom without a cause claim.
2. Start with the least invasive read-only evidence.
3. Follow one hypothesis at a time and record what would falsify it.
4. Correlate signals in the same target and time window.
5. State confirmed facts, leading interpretation and missing evidence
   separately.
6. Propose the smallest reversible fix and verification, but do not apply it
   without authorization.

## Route by symptom

| Symptom | Reference |
|---|---|
| Pending, image pull, crash loop, OOM or failed probes | [Pod diagnosis](./references/pod-diagnose.md) |
| 401 or 403 | [Auth diagnosis](./references/auth-diagnose.md) |
| Consumer lag or unprocessed messages | [Kafka diagnosis](./references/kafka-diagnose.md) |
| Connection pool, migration or database errors | [Database diagnosis](./references/database-diagnose.md) |
| Error, latency or restart signals disagree | [Observability diagnosis](./references/observability-diagnose.md) |

For a deploy failure, first separate automation/build failure, Nais resource
rejection and a successful deploy followed by runtime failure. Read the actual
workflow and deployment status; do not assume registry, identity or manifest
layout.

For performance, locate the bottleneck with the service's actual metrics and
traces, then distinguish application, database, downstream dependency and
resource saturation. Verify current Nais resource guidance before recommending
limits or requests.

## Safety and authorization

Read-only inspection is the default. Before restart, rollout, scale, config or
secret change, database command, message replay, deploy, repository edit or
other external mutation:

1. show exact target and environment
2. show command or diff, expected effect and rollback
3. obtain explicit approval

Treat exec into a production pod, port-forwarding, raw record inspection and
temporary debug logging as sensitive actions; explain the need and ask first.
Do not print secret values, tokens, message payloads or personal data.

## Related skills

- grillmester-nais-manifest for design-time manifest changes
- grillmester-auth-overview for auth mechanisms
- grillmester-kafka-topic for messaging design
- grillmester-postgresql-review for schema and query review
- grillmester-observability-setup for instrumentation design
- When the standard `grillmester` package is installed,
  `grillmester-diagnosing-bugs` is an optional route for reproduction and
  regression tests. Without it, use the self-contained handoff above.

## Grenser

### Alltid

- Verify runtime identity before querying.
- Use actual stack and names from consumer evidence.
- Correlate the same target and time window.
- Verify time-sensitive platform advice against current authoritative docs.

### Spør først

- Every external mutation or production-sensitive inspection.
- Expanding scope to another environment, namespace or service.

### Aldri

- Run mutating Kubernetes, Nais, database or messaging commands implicitly.
- Expose credentials, tokens, payloads or personal data.
- Convert a correlation into a root-cause claim without falsifying alternatives.
