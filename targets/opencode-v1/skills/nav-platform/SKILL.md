---
name: nav-platform
description: "Design, change or diagnose a Nav backend on Nais: manifests, Texas, TokenX, Entra ID, ID-porten, Maskinporten, Wonderwall, Aiven Kafka, Cloud SQL PostgreSQL, Nais observability, Ktor and APIs other teams call. Use for runtime problems on Nais too, such as crash loops, failed deploys, 401/403, consumer lag or database errors; use `diagnosing-bugs` once a code defect needs reproduction and a fix, `security-review` for a broader security assessment, and `architecture-review` to evaluate a consequential proposal."
---
# Nav platform

> **OpenCode:** Skill names below are exact IDs from the active catalog, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Nais and Nav facts and traps a model cannot infer. This file routes; the
references hold the rules.

## Read first

1. Find every row below that the task touches. A live failure touches Runtime
   failure as well as the row for its symptom. A call between services touches
   Identity and Nais workload, a new topic or database also touches Nais
   workload, and plain Kafka client work also touches Kafka.
2. Read each of those references before you edit, answer or run a command
   against an environment.
3. Name the references you read when you report.

When no row fits, this skill does not apply.

| The task touches | Read |
|---|---|
| **Runtime failure:** a deployed workload fails, restarts or misbehaves, or a deploy fails | [diagnosis.md](references/diagnosis.md), then the row for the symptom |
| **Identity:** Texas, TokenX, Entra ID, ID-porten, Maskinporten, Wonderwall, token validation, claims, 401/403 | [auth.md](references/auth.md) |
| **Auth in tests:** mock issuers, token-sidecar stubs, synthetic identities | [local-auth-mock.md](references/local-auth-mock.md) |
| **Nais workload:** `Application` manifests, resources, scaling, `accessPolicy`, ingress, probes, pod lifecycle, crash loops, OOM, image pulls, Pending pods | [nais.md](references/nais.md) |
| **Naisjob:** bounded scheduled or manually triggered work | [naisjob-example.md](references/naisjob-example.md) |
| **Kafka:** Aiven pools, Kafkarator `Topic` resources, ACLs, consumer lag, unprocessed messages | [kafka.md](references/kafka.md) |
| **Plain Kafka client:** direct `kafka-clients` use, Nais SSL configuration, commits | [plain-kafka.md](references/plain-kafka.md) |
| **Database:** Cloud SQL, connection capacity, migrations, shared schemas, pool and connection errors | [database.md](references/database.md) |
| **Observability:** health endpoints, metrics, logs, traces, dashboards, alerts, signals that disagree | [observability.md](references/observability.md) |
| **API:** an API other teams call: consumers, `accessPolicy`, the API catalogue | [api.md](references/api.md) |
| **Ktor:** routes, startup modes, plugin artifacts, shared clients, error handling | [ktor.md](references/ktor.md) |

## Work from evidence

The snippets in the references are shapes, not repository facts. Take names,
namespaces, ports, paths, prefixes, callers, labels and library choices from the
repository's manifests, configuration, code, tests and workflows, and never copy
them from another service.

Treat recognized consumer instructions as declared context and rationale, then
verify effective and volatile facts against code, manifests, tests, runtime
configuration and current primary documentation. Stop and surface a conflict
instead of silently choosing one source. If a needed fact is not discoverable,
ask.
