---
name: grillmester-kafka-topic
description: Design, implement, or review Kafka in a Nav backend. Use for a new or changed topic, Kafkarator resource, event contract, producer, consumer, key strategy, idempotency, consumer group, event evolution, poison-message handling, DLQ, plain Apache Kafka, or Rapids and Rivers.
license: MIT
---

# Design a Kafka topic and flow

## Inspect the repository first

Before proposing code or a topic resource, inspect build dependencies,
producers, consumers, application startup and shutdown, configuration loading,
Nais manifests, Kafkarator resources, deployment workflows, contract
documentation, persistence, health checks, metrics, and tests.

Determine where topics are provisioned and how they are deployed from repository
evidence. They may live beside the application or in another owned repository.
Do not assume a build tool, package, source path, environment variable mapping,
consumer group, event-ID location, topic directory, or dead-letter strategy. If
the flow has no established owner or provisioning repository, ask the user
before creating either.

## Detect and preserve the Kafka stack

| Evidence | Stack |
|---|---|
| direct `KafkaConsumer` or `KafkaProducer`, `org.apache.kafka:kafka-clients` | Plain Apache Kafka |
| `RapidApplication`, `River.PacketListener`, `no.nav.helse:rapids-rivers` | Rapids and Rivers |
| `@KafkaListener`, `KafkaTemplate`, Spring Kafka dependency | Spring Kafka |

Follow the dominant pattern already used by the service. Do not migrate or mix
plain Kafka, Rapids, and Spring Kafka without an explicit design decision. In a
Ktor process, prefer the repository's existing plain-Kafka or Rapids lifecycle;
do not introduce Spring idioms merely because a generic Nav example uses them.

If the repository has no Kafka stack, compare the operational and contract
needs with the user. Plain Kafka is a small direct dependency; Rapids is useful
when the surrounding domain already coordinates through a shared rapid.

## Decide whether Kafka fits

Use synchronous HTTP when the caller needs an immediate success or failure and
an asynchronous event when producers should not wait for downstream work.
Periodic bounded work belongs in a Naisjob; a continuous consumer belongs in a
long-running application. Reuse an established rapid for choreography rather
than adding a parallel event mechanism without agreement.

## Specify the event contract

Define and document:

- topic owner, producer, consumers, retention, cleanup policy, partition count,
  replication, and ACLs;
- event name, required and optional fields, serialization, timestamps, and
  compatibility rules;
- stable key and the ordering scope it creates;
- stable event identity and where it lives;
- delivery semantics, commit boundary, idempotency store, retry behavior,
  poison-message handling, replay, observability, and personal-data handling.

Use past-tense fact names rather than commands. A stable entity key preserves
ordering only within that entity's partition. A random key improves spread but
removes entity ordering.

Do not impose Rapids metadata on plain Kafka. Rapids commonly uses `@id` and
`@event_name` in the packet. A plain contract may instead carry event identity
in a Kafka header or a documented payload field. Preserve the repository's
published contract and deduplicate on that event identity, never on offset.

## Provision the topic declaratively

Use a Kafkarator `Topic` resource in the repository and workflow that owns topic
provisioning. Treat this as an illustrative shape and replace every placeholder
from repository evidence:

```yaml
apiVersion: kafka.nais.io/v1
kind: Topic
metadata:
  name: <team>.<domain>.v<version>
  namespace: <team-namespace>
  labels:
    team: <team-label>
spec:
  pool: <kafka-pool>
  config:
    retentionHours: <verified-retention-hours>
    cleanupPolicy: <delete-or-compact>
    partitions: <verified-partitions>
    replication: <verified-replication>
  acl:
    - team: <producer-team>
      application: <producer-app>
      access: write
    - team: <consumer-team>
      application: <consumer-app>
      access: read
```

Use compaction only for a latest-state-per-key contract with a stable key.
Partition count, retention, and cleanup policy are durable operational choices;
justify them from traffic, replay needs, and consumer parallelism. Keep ACLs
explicit per application.

## Wire a consumer into Ktor safely

A blocking `poll` loop runs alongside the HTTP server, never inside a route.
Use the service's existing DI, coroutine, thread, or lifecycle mechanism. Close
the consumer through the same owned-resource cleanup path and allow the pod's
termination grace period to drain work.

Measure loop progress without calling the broker from a health probe. Follow the
repository's existing liveness/readiness policy; an application-maintained poll
heartbeat is safer than turning a transient broker issue into probe traffic or
load-balancer churn.

## Handle delivery and permanent failures

Assume at-least-once delivery unless the implementation proves stronger
semantics. Commit only after the batch's successful or deliberately parked
records are durable. Temporary dependency failures should prevent the commit so
Kafka can redeliver. Permanently invalid records must not block a partition
forever.

Reuse the existing poison-message strategy:

- some services park the original record and reason in Postgres and replay it
  through an explicit operator flow;
- services without suitable persistence may publish to an owned DLQ topic;
- Rapids services may have an established validation or parking pattern.

Do not replace one strategy with another silently. Preserve enough metadata to
replay safely, alert on the rate, restrict access to sensitive payloads, and
never log the raw payload or personal key.

## Evolve events compatibly

- Add optional fields with tolerant readers.
- For a breaking format or semantic change, create a new contract version,
  dual-publish when feasible, migrate consumers one at a time, and stop the old
  version last.
- Remove a field only after all consumers confirm they no longer require it and
  observed traffic supports that claim.
- Changing a consumer group can replay data according to `auto.offset.reset`;
  treat it as an operational change requiring approval.

Record durable contract and replay decisions through the repository's ADR
process after user agreement.

## Load only the relevant implementation reference

- Plain Apache Kafka in Ktor, including SSL configuration, commit strategy,
  producer settings, and tests:
  [references/plain-kafka.md](references/plain-kafka.md).
- Rapids and Rivers validation, publishing, idempotency, and TestRapid:
  [references/rapids-and-rivers.md](references/rapids-and-rivers.md).

## Deliver evidence

Return the detected stack, topic owner and resource, contract, key and event-ID
strategy, group and commit semantics, retry/parking path, compatibility plan,
tests, and deployment checks. Mark unverified consumers and capacity assumptions
as unknown.

## Boundaries

### Ask first

- Change stack, consumer group, partitions, cleanup policy, retention, or a
  contract consumed by another team.
- Introduce a new topic owner, replay path, or personal-data field.

### Never

- Create topics ad hoc from application code or manual cluster commands.
- Use Kafka offset as an idempotency key.
- Run a poll loop in an HTTP handler.
- Log tokens, national identity numbers, personal keys, or raw payloads.
- Commit past an unhandled record or let a permanent record halt the stream
  without an observable recovery path.
