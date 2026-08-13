---
description: Nais pod termination and portable graceful-shutdown checks for backend applications, workers, and Kafka consumers.
---

# Pod lifecycle and graceful shutdown

Inspect the current Nais behavior and repository lifecycle before changing it.
When termination begins, Kubernetes starts the grace period and removes the pod
from service endpoints. A `preStopHook` runs only when one is configured; some
repositories or deployment templates use a delay or application callback there.
Confirm current platform and manifest behavior rather than assuming such a hook
exists or copying a delay value from another service.

The application should:

1. let the framework stop accepting new requests;
2. wake blocking poll loops and stop scheduling new work;
3. finish, cancel, or durably hand off in-flight work according to its delivery
   contract;
4. close Kafka clients, HTTP clients, data sources, executors, and coroutine
   scopes exactly once;
5. exit within `terminationGracePeriodSeconds`.

Readiness is not a substitute for termination handling. Do not add a manual
`readiness=false` toggle unless repository and current platform evidence prove
that it participates in routing soon enough to solve the measured problem.

Before lowering a grace period, measure worst-case request, batch, commit, and
cleanup time under load. A shorter value can abort calls, lose uncommitted work,
or leave external side effects in an ambiguous state. Test termination with a
production-like startup and show that every owned resource closes within the
configured period.
