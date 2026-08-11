# Kafka diagnosis

Detect the actual client and processing model first. Plain Kafka clients,
Streams, framework wrappers and Rapids & Rivers have different failure modes.
Discover topic, consumer group, partitions, offset policy, retry/dead-letter
behavior and metric names from consumer evidence.

## Read-only evidence

- deployed consumer health and restarts
- lag and throughput for the confirmed topic and group
- redacted errors in one time window
- rebalance frequency and processing duration
- current partition count and active consumers
- schema/version evidence and the repository's poison-message contract

Never print message payloads, keys or headers that may contain personal data or
secrets. Inspect raw records only with explicit approval and a safe,
data-minimizing method.

## Lag tree

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

## Failure interpretation

| Observation | Check |
|---|---|
| deserialization error | producer contract, schema/version and poison policy |
| no records, no errors | topic, group, offset position and filters |
| rebalance loop | processing time, poll/session settings and pod churn |
| TLS/connectivity error | injected config names, mounts, policy and broker status |
| downstream side effects missing | transaction/idempotency boundary and parked records |
| lag began after deploy | group ID, offset policy, subscription and code change |

## Rapids & Rivers, only when verified

Inspect validation rules, required/interested keys and event-name matching. A
filter can intentionally drop a packet without reaching the handler. Add
temporary diagnostics only after approval, with field allowlisting and no
payload/person data.

## Mutations

Scaling, partition changes, offset resets, message replay, dead-letter replay
and temporary logging are external mutations. Before any of them, show:

- exact environment, topic, group and scope
- expected records and side effects
- idempotency and data-safety evidence
- rollback or stop condition
- exact command or diff

Obtain explicit approval.

## Escalation

- Pod failure: [pod-diagnose.md](./pod-diagnose.md)
- Database failure: [database-diagnose.md](./database-diagnose.md)
- Auth on downstream calls: [auth-diagnose.md](./auth-diagnose.md)
- Consumer design: grillmester-kafka-topic
- Regression reproduction: grillmester-diagnosing-bugs
