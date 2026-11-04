---
name: nav-platform
description: "Design, change or diagnose a Nav backend on Nais: manifests, Texas, TokenX, Entra ID, ID-porten, Wonderwall, Aiven Kafka, Cloud SQL PostgreSQL, Nais observability, Ktor and APIs other teams call. Use for runtime problems on Nais too, such as crash loops, failed deploys, 401/403, consumer lag or database errors; use `diagnosing-bugs` once a code defect needs reproduction and a fix, and `security-review` for a broader security assessment."
---
# Nav platform

> **OpenCode:** Skill names below are exact IDs from the active catalog, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Nav and Nais facts and traps for building and running a backend on Nais. Each
area has one reference that holds both design and diagnosis.

## Route

Read the reference for every area the task touches before you act or answer,
and only those. When no row fits, this skill does not apply.

| Area | Use for | Reference |
|---|---|---|
| Runtime problem | A deployed workload fails, restarts or misbehaves, or a deploy fails | [diagnosis.md](references/diagnosis.md) first; it routes to the area |
| Identity | Texas, TokenX, Entra ID, ID-porten, Maskinporten, Wonderwall, token validation, claims, 401/403 | [auth.md](references/auth.md) |
| Auth in tests | Mock issuers, token-sidecar stubs, synthetic identities | [local-auth-mock.md](references/local-auth-mock.md) |
| Nais workload | `Application` manifests, probes, resources, scaling, `accessPolicy`, ingress, pod lifecycle, pod failures | [nais.md](references/nais.md) |
| Naisjob | Bounded scheduled or manually triggered work | [naisjob-example.md](references/naisjob-example.md) |
| Kafka | Aiven pools, Kafkarator `Topic` resources, ACLs, consumer lag | [kafka.md](references/kafka.md) |
| Plain Kafka client | Direct `kafka-clients` use, Nais SSL configuration, commits | [plain-kafka.md](references/plain-kafka.md) |
| Database | Cloud SQL, connection capacity, migrations, shared schemas, pool and connection errors | [database.md](references/database.md) |
| Observability | Metrics, logs, traces, dashboards, alerts, signals that disagree | [observability.md](references/observability.md) |
| API | An API other teams call: consumers, `accessPolicy`, the API catalogue | [api.md](references/api.md) |
| Ktor | Startup modes, plugin artifacts, shared clients, error handling | [ktor.md](references/ktor.md) |

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
