---
name: grillmester-nais-manifest
description: Create, change, or review a Nais Application or Naisjob manifest. Use for ingress, resources, probes, accessPolicy, Azure or TokenX, Kafka, GCP Postgres, observability, scaling, CPU throttling, OOM behavior, graceful shutdown, or scheduled batch jobs.
license: MIT
---

# Create or change a Nais manifest

## Inspect deployed intent first

Find existing Nais resources, environment overlays, templating, deployment
workflows, app configuration, server startup, health and metrics routes, runtime
type, external calls, auth, Kafka, database configuration, and production
telemetry. Search the repository rather than assuming `.nais/`, `nais/`, file
names, or one manifest per environment.

Derive application name, namespace, team label, image placeholder, port, probes,
ingress, resource values, environment variables, pools, database type, and
access policy from repository evidence. Treat recognized
`AGENTS.md`/instruction sources as declared context and rationale, then verify
names, topology and effective values against manifests, code, workflows,
telemetry or current authoritative platform documentation. If the sources
conflict, stop and ask rather than silently preferring either one.

If no manifest exists, ask the user for owning team, app name, target
environments, runtime port, required dependencies, exposure, and operational
expectations. Confirm the current Nais schema and supported resource versions
before creating a new resource.

## Choose the resource kind

- Use `Application` for a continuously running HTTP service, worker, or Kafka
  consumer.
- Use `Naisjob` for bounded scheduled or manually triggered work that exits.
- Do not turn a frequent or continuous queue consumer into a cron job.

Reuse the repository's environment and templating strategy. Do not introduce
separate dev/prod files, variables, or a new renderer when the repository uses a
different established pattern.

## Start from an evidence-filled Application shape

```yaml
apiVersion: nais.io/v1alpha1
kind: Application
metadata:
  name: <application-name>
  namespace: <team-namespace>
  labels:
    team: <team-label>
spec:
  image: {{ image }}
  port: <verified-listen-port>

  prometheus:
    enabled: true
    path: <verified-metrics-path>
  liveness:
    path: <verified-liveness-path>
    initialDelay: <verified-delay>
  readiness:
    path: <verified-readiness-path>
    initialDelay: <verified-delay>

  resources:
    requests:
      cpu: <measured-or-approved-request>
      memory: <measured-or-approved-request>
    limits:
      memory: <measured-or-approved-limit>
```

Every endpoint in the manifest must exist on the configured port in every
deployed startup mode. Do not copy conventional health paths into a repository
that exposes different ones.

## Resource rules

Normally omit `resources.limits.cpu` for a Nais workload, in line with current
Nais cost and good-practice guidance. CPU quota throttling can amplify JVM
startup, GC, and latency problems. Verify current platform guidance and retain
an evidenced exception when the workload deliberately needs CPU-constrained
testing or another owner-approved bound. Set a CPU request for scheduling and
retain a measured memory limit so the pod cannot consume unbounded node memory.

Treat example sizes as hypotheses, not defaults. Compare current telemetry,
heap and off-heap use, workload concurrency, replicas, autoscaling, startup,
and peak behavior. Keep memory headroom above JVM heap for metaspace, threads,
native libraries, and direct buffers. Production resource or replica changes
require user approval and fresh evidence.

## Keep access policy explicit and minimal

List the applications and external hosts the workload actually communicates
with. Include namespace and cluster when required by the real topology:

```yaml
accessPolicy:
  inbound:
    rules:
      - application: <calling-application>
        namespace: <calling-namespace>
  outbound:
    rules:
      - application: <downstream-application>
        namespace: <downstream-namespace>
    external:
      - host: <approved-external-host>
```

An empty or absent inbound rule set does not grant callers through the
service-discovery/accessPolicy path. It does not block traffic through an
ingress. Review ingress exposure, edge authentication and application-level
authorization as separate controls; never present `accessPolicy.inbound` as a
complete caller inventory or ingress firewall. Do not add a fake inbound
caller merely to make the block non-empty. Keep policy aligned with application
token validation and authorization. Require security review for changes to
callers, destinations, auth flags, ingress or scopes.

## Add platform capabilities only when code uses them

### PostgreSQL

```yaml
gcp:
  sqlInstances:
    - type: <supported-postgres-type>
      tier: <approved-tier>
      highAvailability: <approved-value>
      diskAutoresize: <approved-value>
      databases:
        - name: <database-name>
          envVarPrefix: <repository-prefix>
```

Verify the supported Postgres type, tier, HA, backup and disk choices against
current Nais documentation and repository needs. Follow the prefix already
mapped by application config; do not copy a database environment prefix from
another service. Size connection pools against replicas and actual
`max_connections`. Ensure long startup migrations fit the repository's startup
and probe design.

### Kafka

```yaml
kafka:
  pool: <environment-kafka-pool>
```

Match the pool to the environment and owned topic resources. A Kafka block does
not provision a topic; use the owning Kafkarator workflow and explicit ACLs.

### Authentication

```yaml
azure:
  application:
    enabled: true

tokenx:
  enabled: true
```

Enable only mechanisms required by verified incoming and outgoing flows. Keep
their access policy and application validation aligned. Do not copy tenants,
scopes, audiences, or sidecar annotations from another app.

### Ingress

Choose a public, internal, or external Nav domain from the actual audience and
current platform policy. A service called only by other Nais applications may
need no ingress. Adding or widening ingress changes the trust boundary and
requires approval.

### Observability

Use the runtime and observability form already supported by the repository and
current Nais schema. Ensure logs go to stdout or stderr without personal data,
metrics match `prometheus.path`, and tracing does not capture tokens or payloads.

## Preserve pod lifecycle

Use the application's framework shutdown and owned-resource cleanup. Do not
invent manual readiness toggles or duplicate shutdown hooks. Load
[references/pod-lifecycle.md](references/pod-lifecycle.md) when changing grace
periods, pre-stop behavior, workers, consumers, or long-running requests.

## Create Naisjob deliberately

A Naisjob needs an explicit schedule or manual invocation model, overlap policy,
deadline, retry limit, cleanup policy, resources, and only the platform
capabilities it actually uses. Load the portable example in
[references/naisjob-example.md](references/naisjob-example.md).

## Deliver evidence

Validate the rendered manifest with the repository's existing tooling and
current Nais schema. Return the source and rendered resource, values derived
from code, environment differences, security and cost changes, probe evidence,
and validation command with exit code. Mark unverified capacity or platform
assumptions explicitly.

Record hard-to-reverse platform decisions through the repository's ADR process
after the user accepts them.

## Boundaries

### Ask first

- Change production resources, replicas, autoscaling, ingress, access policy,
  database tier or HA, Kafka pool, or paid GCP resources.
- Add a new resource kind or deployment strategy.

### Never

- Add `resources.limits.cpu` without current Nais guidance and an evidenced,
  owner-approved exception, or remove the memory limit without equivalent
  measured protection.
- Store secrets in Git or copy another application's identity values.
- Invent paths, namespaces, ports, probes, environment prefixes, or callers.
- Lower the termination grace period without measured shutdown evidence.
