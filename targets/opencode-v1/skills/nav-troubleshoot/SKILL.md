---
name: nav-troubleshoot
description: "Diagnose deployed Nais workload failures using deployment, pod, log, metric and trace evidence. Use for production-only errors, failed deploys, restarts or connectivity problems; use `diagnosing-bugs` once a code defect needs reproduction and a fix."
---
# Nav Troubleshoot

> **OpenCode v1:** Skill names below are exact IDs from the active catalog, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Locate a deployed-environment cause before proposing a fix. Route a confirmed
code defect to `diagnosing-bugs` for implementation and regression
testing. Mark `NEEDS_CONTEXT` when the reproduction or expected behavior
cannot be established from available evidence.

## Data access

Apply [Nav's current guidelines](https://ki-utvikling.nav.no/retningslinjer) and
applicable team/repository rules to the source, scope, active client/model and
access channel before collecting operational data. Direct queries are allowed
when both access and returned data are permitted; read-only access or task
approval alone does not establish this. Reuse existing decisions within their
approved scope and query only the needed target, time window and result limit.

Within this skill, keep secrets, tokens, personal data and protected information
outside model context. Any required filtering or redaction must happen through
an approved path before tool output reaches the model; never fetch disallowed
raw data to redact afterward. If this boundary is unresolved, continue with code, synthetic
tests or a permitted aggregate/prepared excerpt. Mark dependent retrieval
`NEEDS_CONTEXT` and name the missing data-access decision.

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
Reuse approval for the same concrete action and scope. Such approval cannot
override the data-access boundary above. Do not print secret values, tokens,
message payloads or personal data.

## Related skills

- nais-manifest for design-time manifest changes
- auth-overview for auth mechanisms
- kafka-topic for messaging design
- postgresql-review for schema and query review
- observability-setup for instrumentation design
- diagnosing-bugs for reproduction and regression tests

## Grenser

### Alltid

- Verify runtime identity before querying.
- Use actual stack and names from consumer evidence.
- Correlate the same target and time window.
- Verify time-sensitive platform advice against current authoritative docs.

### Spør først

- External mutations or production-sensitive inspections not already authorized.
- Expanding beyond the approved environment, namespace or service scope.

### Aldri

- Run mutating Kubernetes, Nais, database or messaging commands implicitly.
- Expose credentials, tokens, payloads or personal data.
- Convert a correlation into a root-cause claim without falsifying alternatives.
