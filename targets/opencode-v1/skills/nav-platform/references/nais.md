# Nais workloads

## Contents

- Derive values from the repository
- Choose the resource kind
- Start from an evidence-filled Application shape
- Resource rules
- Keep access policy explicit and minimal
- Add platform capabilities only when code uses them
- Pod lifecycle
- Validate the rendered manifest
- Pod diagnosis
- Boundaries

## Derive values from the repository

Derive application name, namespace, team label, image placeholder, port, probes,
ingress, resource values, environment variables, pools, database type, and
access policy from repository evidence. Search the repository for the manifest
locations, file names and number of manifests per environment.

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

A Naisjob needs an explicit schedule or manual invocation model, overlap policy,
deadline, retry limit, cleanup policy, resources, and only the platform
capabilities it actually uses. Load the portable example in
[naisjob-example.md](naisjob-example.md).

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

Treat example sizes as hypotheses, not defaults. Production resource or replica
changes require user approval and fresh evidence.

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

| Capability | Manifest key | Details |
|---|---|---|
| PostgreSQL | `gcp.sqlInstances` | [database.md](database.md) |
| Kafka | `kafka.pool` | [kafka.md](kafka.md) |
| Authentication | `azure.application.enabled`, `tokenx.enabled` | [auth.md](auth.md) |
| Metrics, logs and traces | `prometheus`, `observability` | [observability.md](observability.md) |

Do not copy tenants, scopes, audiences, or sidecar annotations from another app.

### Ingress

Choose a public, internal, or external Nav domain from the actual audience and
current platform policy. A service called only by other Nais applications may
need no ingress. Adding or widening ingress changes the trust boundary and
requires approval.

## Pod lifecycle

Inspect the current Nais behavior and repository lifecycle before changing it.
When termination begins, Kubernetes starts the grace period and removes the pod
from service endpoints. Unless the manifest sets its own hook, Nais adds a
default `preStop` hook that waits five seconds before the application receives
SIGTERM, and the wait counts toward the grace period. Some repositories use
their own delay or application callback instead. Confirm current platform and
manifest behavior rather than copying a delay value from another service.

Use the application's framework shutdown and owned-resource cleanup. On
termination, stop new work, wake blocking poll loops, finish, cancel or durably
hand off in-flight work according to its delivery contract, close owned resources
exactly once, and exit within `terminationGracePeriodSeconds`.

Readiness is not a substitute for termination handling. Do not add a manual
`readiness=false` toggle unless repository and current platform evidence prove
that it participates in routing soon enough to solve the measured problem.
Do not duplicate shutdown hooks.

Before lowering a grace period, measure worst-case request, batch, commit, and
cleanup time under load. A shorter value can abort calls, lose uncommitted work,
or leave external side effects in an ambiguous state. Test termination with a
production-like startup and show that every owned resource closes within the
configured period.

## Validate the rendered manifest

Validate the rendered manifest with the repository's existing tooling and
current Nais schema. Mark unverified capacity or platform assumptions explicitly.

## Pod diagnosis

Confirm cluster, namespace, workload, pod, container and selector from
consumer/deployment evidence. Labels and container names vary.

### Inspection command templates

Read-only is not a safety classification. Live logs, events and `describe`
output can contain secrets, personal data and sensitive operational metadata.
Apply the [data-access boundary](diagnosis.md#data-access) before any command.
Confirm the exact cluster/context, namespace, object and container, and choose
a narrow time window or result limit. For production-sensitive inspection,
show the exact command and scope and obtain explicit approval unless already
granted for that action and scope.

These templates return raw output. Run them directly only when that output is
permitted in model context. Otherwise, use an approved path that filters or
redacts before the model receives output; do not fetch disallowed data to
decide what to redact. Substitute only verified values:

```bash
kubectl get pods --namespace <namespace> --selector '<verified-selector>' -o wide
kubectl describe pod --namespace <namespace> <pod>
kubectl logs --namespace <namespace> <pod> --container <container> --since=<verified-window> --tail=<verified-limit>
kubectl logs --namespace <namespace> <pod> --container <container> --previous --tail=<verified-limit>
kubectl get events --namespace <namespace> --field-selector 'involvedObject.name=<pod>' --sort-by='.lastTimestamp'
kubectl top pod --namespace <namespace> <pod>
```

If context is not already locked to the verified cluster, include the explicit
context argument supported by the local setup. Do not rely on the current
kubectl context by accident.

Keep only the permitted diagnostic signal. Following logs, exec, port-forwarding
and broad namespace queries require an explanation of scope and explicit
approval if not already covered by the authorized action.

### Diagnostic tree

```text
Pod fails
├── Pending?
│   └── inspect scheduling events, quota, selectors, affinity and volumes
├── ImagePullBackOff or ErrImagePull?
│   └── inspect resolved image, build/push result and registry authorization
├── CrashLoopBackOff?
│   ├── get termination reason and previous-container logs
│   ├── OOMKilled → inspect memory trend, workload and verified resource config
│   ├── missing config → compare app requirements and deployed declarations
│   ├── dependency startup failure → route to auth/database/messaging tree
│   └── config/runtime error → reproduce through the repository bug workflow
└── Running but probe fails?
    ├── compare deployed probe path, port and protocol with application behavior
    ├── inspect startup duration and dependency checks
    └── verify whether the probe contract itself is appropriate
```

### Interpret evidence, do not prescribe from one line

| Observation | Required follow-up |
|---|---|
| exit 137 / OOMKilled | memory usage, heap/native split, workload and limit |
| missing variable | actual variable name, enabling feature and secret source |
| connection refused | target, sidecar/dependency status, DNS and policy |
| address in use | declared port versus application listener |
| failed scheduling | exact event reason, quota and placement constraints |
| image pull failure | resolved digest/tag and upstream build/push evidence |

Discover whichever of these apply from the workload: the JVM heap fraction,
manifest keys, database proxy, auth flags, Kafka pool and readiness path.

### Mutation boundary

Restart, delete, scale, rollout, patch, config change or probe/resource change
requires the exact target, command/diff, expected impact, rollback and explicit
approval. A restart can erase transient evidence; preserve the permitted
diagnostic signal first, within the data-access boundary above.

For database startup failures, continue with
[Database diagnosis](database.md#database-diagnosis). For auth failures, use
[Auth diagnosis](auth.md#auth-diagnosis-401-and-403). Confirmed
application defects may continue through `diagnosing-bugs`.

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
