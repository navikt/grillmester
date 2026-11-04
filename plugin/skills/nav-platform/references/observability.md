# Observability on Nais

## Contents

- Discover current state
- Metrics, logs and traces
- Health
- Alerts
- Observability diagnosis
- Boundaries

## Discover current state

Take the framework, package, paths, endpoints, metric names, labels, service
names, environments, backends, dashboard location and alert routing from
consumer evidence. Use the runtime and observability form already supported by
the repository and current Nais schema. Ensure logs go to stdout or stderr
without personal data, metrics match `prometheus.path`, and tracing does not
capture tokens or payloads.

## Metrics, logs and traces

- Never use personal identifiers, tokens, raw URLs, correlation IDs, message
  keys, payload values or IDs, or unbounded exception text as metric labels.
- Micrometer may translate dot-form meter names to Prometheus names, but
  dashboards and alerts must use the emitted names, not an inferred translation.
- Log event and outcome, not full request, token, payload or personal data.
  Reuse existing correlation fields and propagation.
- Do not duplicate personal or secret data in span names or attributes.
- Read the log format and parser stage, field casing, correlation key and
  platform labels from logger configuration, existing queries, documentation or
  an approved redacted sample. Never query by personal identifier, token or raw
  payload.

## Health

Take route names and ports from the application and its deployed probe
configuration. External dependency availability often belongs in metrics/alerts
rather than liveness, because restarting may not help. Discover actual workload
and dependency semantics; a queue consumer, job and HTTP service may need
different contracts. Keep probes fast and free of sensitive detail.

## Alerts

Discover the current Nais alert mechanism and resource kind, repository pattern,
notification routing and channel, owner, severity vocabulary and runbook
convention from authoritative docs and consumer evidence. No fixed threshold,
evaluation window or environment promotion sequence is portable. Ask when the
consumer has no documented choice. Do not alert on a convenient log phrase as a
permanent substitute without considering stability and data exposure.

Changing an alert rule, threshold, routing destination, dashboard annotation or
runbook is an external/persistent write. Show the exact target and diff,
expected notification behavior and rollback, then obtain explicit approval.
Do not send a test notification without approval.

## Observability diagnosis

Use when metrics, logs and traces disagree. Discover which backends, service
names, labels, metric names and correlation fields the consumer actually uses.
Mimir, Loki and Tempo may be available on Nais; check which of them hold the
workload's telemetry.

### Align scope first

- symptom and user-visible impact
- verified workload identity and environment
- exact time window and timezone
- deploy/config/traffic changes in that window
- available signals and known instrumentation gaps

### Diagnostic tree

```text
Signals disagree
├── Error-rate symptom?
│   ├── Start with an existing error/result metric
│   ├── inspect matching logs in the same window
│   └── follow a verified correlation field into traces when available
├── Latency symptom?
│   ├── start with an existing duration histogram or timer
│   ├── compare operations and pre/post-change windows
│   └── inspect slow traces for app, database or downstream time
├── Restart/resource symptom?
│   ├── correlate pod events, resource metrics and previous logs
│   └── verify requests/limits and exit reason before blaming code
└── Missing correlation?
    ├── verify service identity and environment
    ├── verify instrumentation is active
    └── record the missing signal as a gap, not proof of another cause
```

### Query discipline

- Start with labels and metric names found in dashboards, rules, code or live
  metadata. Do not invent app, namespace, route or status labels.
- Use the same target and time range across backends.
- Distinguish client errors, server errors and business-result failures from
  the consumer's actual semantics.
- Percentiles require an appropriate histogram. Confirm bucket series and
  labels before trusting a quantile query.
- A free-text search for «error» across all logs is not a scoped diagnostic.
- Verify that a trace belongs to the target service before interpreting spans.
- Use request counts or rates to judge how representative a failing or slow
  trace is. One trace establishes an instance, not the frequency of the problem.
- Check sampling, retention and query coverage before treating missing logs or
  spans as evidence that an event did not occur.

### Sensitive data

Use only correlation fields already approved and emitted by the service. Do not
introduce or query personal identifiers, raw message identifiers, tokens or
payload content. Temporary logging and broader data access require explicit
approval and a removal plan.

### Result format

Report:

1. aligned source, target and time window
2. verified observations per signal
3. leading hypothesis and falsifying evidence
4. instrumentation gaps
5. smallest next read-only check

Route restart/readiness issues to
[Pod diagnosis](nais.md#pod-diagnosis), database signals to
[Database diagnosis](database.md#database-diagnosis), auth failures to
[Auth diagnosis](auth.md#auth-diagnosis-401-and-403), and confirmed code
defects to `diagnosing-bugs`.

## Boundaries

### Ask first

- New high-cardinality dimensions or retained data.
- Dashboard, alert, routing or production-threshold changes.
- Every external write or sensitive runtime inspection.

### Never

- Invent service, metric, label, environment or routing names.
- Use observability as a reason to expose secrets or personal data.
