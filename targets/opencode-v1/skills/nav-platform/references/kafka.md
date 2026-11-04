# Kafka on Nais

This reference holds Kafkarator, pools, ACLs and diagnosis. Event contracts and
team conventions belong in the owning repository. For direct `kafka-clients`
use, load [plain-kafka.md](plain-kafka.md).

## Find the topic owner

Determine where topics are provisioned and how they are deployed from repository
evidence. They may live beside the application or in another owned repository.
If the flow has no established owner or provisioning repository, ask the user
before creating either.

## Connect the workload to a pool

```yaml
kafka:
  pool: <environment-kafka-pool>
```

Match the pool to the environment and owned topic resources. A Kafka block does
not provision a topic; use the owning Kafkarator workflow and explicit ACLs.

## Provision the topic declaratively

Use a Kafkarator `Topic` resource in the repository and workflow that owns topic
provisioning. Treat this as an illustrative shape and replace every placeholder
from repository evidence:

```yaml
apiVersion: kafka.nais.io/v1
kind: Topic
metadata:
  name: <topic-name>
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

## Traps

- Preserve the Kafka stack the service already uses. Do not migrate or mix plain
  Kafka and Spring Kafka without an explicit design decision.
- Measure a plain client's loop progress without calling the broker from a
  health probe; an application-maintained poll heartbeat is safer than turning a
  transient broker issue into probe traffic or load-balancer churn.
- Changing a consumer group can replay data according to `auto.offset.reset`;
  treat it as an operational change requiring approval.
- The published contract owns its event identity. Deduplicate on that identity,
  never on offset.
- Reuse the existing poison-message strategy. Do not replace one strategy with
  another silently.

## Kafka diagnosis

Detect the actual client and processing model first. Plain Kafka clients,
Streams and framework wrappers have different failure modes.
Discover topic, consumer group, partitions, offset policy, retry/dead-letter
behavior and metric names from consumer evidence.

### Read-only evidence

- deployed consumer health and restarts
- lag and throughput for the confirmed topic and group
- redacted errors in one time window
- rebalance frequency and processing duration
- current partition count and active consumers
- schema/version evidence and the repository's poison-message contract

Keep payloads, keys and headers containing personal data or secrets outside
model context. Raw-record inspection requires explicit authority for the scope
and the [data-access boundary](diagnosis.md#data-access): use an approved method
that returns only permitted diagnostic fields, filtering before output reaches
the model. Task approval alone does not authorize the data.

### Lag tree

```text
Consumer lag grows
├── Is the consumer running and subscribed to the confirmed topic?
│   ├── No → inspect pod state, config and subscription
│   └── Yes → continue
├── Is growth sustained relative to arrival rate?
│   ├── No → quantify the transient and recovery time
│   └── Yes → continue
├── Is processing slow or blocked?
│   ├── One record repeatedly fails → follow the verified poison policy
│   ├── Downstream/database latency → diagnose that dependency
│   ├── Processing exceeds poll interval → inspect batch and poll settings
│   └── No progress/no error → verify group, offsets and filtering
├── Are rebalances frequent?
│   └── correlate deploys, membership, poll duration and session settings
└── Is capacity below measured load?
    └── compare consumers, partitions and per-record processing cost
```

Do not label sporadic lag «normal» without a documented SLO or observed
recovery. Do not recommend scaling past useful partition parallelism.

### Failure interpretation

| Observation | Check |
|---|---|
| deserialization error | producer contract, schema/version and poison policy |
| no records, no errors | topic, group, offset position and filters |
| rebalance loop | processing time, poll/session settings and pod churn |
| TLS/connectivity error | injected config names, mounts, policy and broker status |
| downstream side effects missing | transaction/idempotency boundary and parked records |
| lag began after deploy | group ID, offset policy, subscription and code change |

### Mutations

Scaling, partition changes, offset resets, message replay, dead-letter replay
and temporary logging are external mutations. Before any of them, show:

- exact environment, topic, group and scope
- expected records and side effects
- idempotency and data-safety evidence
- rollback or stop condition
- exact command or diff

Obtain explicit approval.

### Escalation

- Pod failure: [Pod diagnosis](nais.md#pod-diagnosis)
- Database failure: [Database diagnosis](database.md#database-diagnosis)
- Auth on downstream calls: [Auth diagnosis](auth.md#auth-diagnosis-401-and-403)
- Route regression reproduction to `diagnosing-bugs`.

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
