---
description: "Use when building PromQL, LogQL or dashboards from metric and log names verified in the consumer."
---

# PromQL, LogQL and dashboards

Inventory the service's emitted metrics, log format, labels and existing
queries first. Dashboard JSON, alert rules, instrumentation code and live
metadata are useful evidence. Do not infer names from another service or from a
library default without verifying emission.

## PromQL patterns

Substitute verified metric and label names:

```promql
sum(rate(<counter_total>[5m]))
sum by (<bounded_label>)(rate(<counter_total>[5m]))
sum(rate(<failure_counter_total>[5m]))
  /
sum(rate(<attempt_counter_total>[5m]))
histogram_quantile(
  0.95,
  sum by (le, <operation_label>)(rate(<duration_seconds_bucket>[5m]))
)
```

Check:

- whether the counter suffix and unit are actually emitted
- whether the selected window matches traffic volume and response needs
- whether histogram buckets exist
- whether aggregation preserves the dimensions needed for diagnosis
- whether missing series means zero, no traffic or broken instrumentation

## LogQL patterns

Start with verified platform labels and a bounded time window, then parse the
service's actual log format. Replace all placeholders:

```logql
{<service_label>="<service_value>"} | json | <level_field>="ERROR"
sum(rate({<service_label>="<service_value>"} | json
  | <level_field>="ERROR" [5m]))
{<service_label>="<service_value>"} | json
  | <correlation_field>="<approved-id>"
```

Do not assume JSON, field casing, a correlation key or platform label. Never
query by personal identifier, token or raw payload.

## Dashboard workflow

1. State the operational question for each panel.
2. Reuse verified service and environment variables.
3. Build from emitted metrics and existing log fields.
4. Test no-data, low-traffic and failure cases.
5. Link actionable panels to a verified runbook or owner when available.
6. Remove panels that do not change a decision.

Use the same dimension vocabulary across metrics, logs and alerts when the
consumer already supports it. Do not add cardinality merely to make panels
symmetrical.
