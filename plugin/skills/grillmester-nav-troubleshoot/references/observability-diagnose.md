# Observability diagnosis

Use when metrics, logs and traces disagree. Discover which backends, service
names, labels, metric names and correlation fields the consumer actually uses.
Mimir, Loki and Tempo may be available on Nais, but do not assume all three are
configured for the workload.

## Align scope first

- symptom and user-visible impact
- verified workload identity and environment
- exact time window and timezone
- deploy/config/traffic changes in that window
- available signals and known instrumentation gaps

## Diagnostic tree

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

## Query discipline

- Start with labels and metric names found in dashboards, rules, code or live
  metadata. Do not invent app, namespace, route or status labels.
- Use the same target and time range across backends.
- Distinguish client errors, server errors and business-result failures from
  the consumer's actual semantics.
- Percentiles require an appropriate histogram. Confirm bucket series and
  labels before trusting a quantile query.
- A free-text search for «error» across all logs is not a scoped diagnostic.
- Verify that a trace belongs to the target service before interpreting spans.

## Sensitive data

Use only correlation fields already approved and emitted by the service. Do not
introduce or query personal identifiers, raw message identifiers, tokens or
payload content. Temporary logging and broader data access require explicit
approval and a removal plan.

## Result format

Report:

1. aligned source, target and time window
2. verified observations per signal
3. leading hypothesis and falsifying evidence
4. instrumentation gaps
5. smallest next read-only check

Route restart/readiness issues to [pod-diagnose.md](./pod-diagnose.md),
database signals to [database-diagnose.md](./database-diagnose.md), auth
failures to [auth-diagnose.md](./auth-diagnose.md), and confirmed code defects
to grillmester-diagnosing-bugs.
