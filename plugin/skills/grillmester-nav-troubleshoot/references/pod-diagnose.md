# Pod diagnosis

Confirm cluster, namespace, workload, pod, container and selector from
consumer/deployment evidence. Labels and container names vary.

## Read-only command templates

Substitute only verified values:

```bash
kubectl get pods --namespace <namespace> --selector '<verified-selector>' -o wide
kubectl describe pod --namespace <namespace> <pod>
kubectl logs --namespace <namespace> <pod> --container <container> --tail=100
kubectl logs --namespace <namespace> <pod> --container <container> --previous --tail=100
kubectl get events --namespace <namespace> --sort-by='.lastTimestamp'
kubectl top pod --namespace <namespace> <pod>
```

If context is not already locked to the verified cluster, include the explicit
context argument supported by the local setup. Do not rely on the current
kubectl context by accident.

Following logs, exec, port-forwarding and broad namespace queries can expose
sensitive data or consume a long-running session. Explain scope and ask first.

## Diagnostic tree

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

## Interpret evidence, do not prescribe from one line

| Observation | Required follow-up |
|---|---|
| exit 137 / OOMKilled | memory usage, heap/native split, workload and limit |
| missing variable | actual variable name, enabling feature and secret source |
| connection refused | target, sidecar/dependency status, DNS and policy |
| address in use | declared port versus application listener |
| failed scheduling | exact event reason, quota and placement constraints |
| image pull failure | resolved digest/tag and upstream build/push evidence |

Do not assume a JVM heap fraction, manifest key, database proxy, auth flag,
Kafka pool or readiness path. Discover them.

## Mutation boundary

Restart, delete, scale, rollout, patch, config change or probe/resource change
requires the exact target, command/diff, expected impact, rollback and explicit
approval. A restart can erase the best transient evidence, so collect it first.

For database startup failures, continue with
[database-diagnose.md](./database-diagnose.md). For auth failures, use
[auth-diagnose.md](./auth-diagnose.md). Confirmed application defects may
continue through `grillmester-diagnosing-bugs`.
