---
name: grillmester-observability-setup
description: "Designs or improves metrics, structured logging, tracing, health checks, dashboards and alerts for deployed services. Use for instrumentation, correlation, PromQL/LogQL, operational dashboards, SLO signals or Nais observability setup."
license: MIT
---

# Observability setup

Build from actual runtime: metrics show change, logs give event context, and
traces show where time and failures occur.

## Discover current state

Do not assume framework, package, paths, endpoints, metric names, labels,
service names, environments, backends, dashboard location or alert routing.

Inspect consumer evidence for:

- runtime, instrumentation, registry/exporter and scrape configuration
- logger format, approved fields, language and correlation
- trace instrumentation, service identity and propagation
- probe contracts, metrics, dashboards, alerts, runbooks and SLOs
- deployment labels, owners, routing and prohibited data

If a required name or policy is not discoverable, ask. Verify time-sensitive
Nais and library guidance against current authoritative documentation.

## Design workflow

1. Name the user-visible or operational question.
2. Inventory existing signals and their exact names/labels.
3. Reuse an established pattern before adding a parallel registry or field.
4. Add the smallest signal that changes diagnosis or response.
5. Define how it will be queried, visualized or alerted on.
6. Validate output, ownership, runbook and removal criteria.

### Metrics

- Use names and units consistent with the consumer's registry and conventions.
- Keep labels low-cardinality and bounded.
- Never use personal identifiers, tokens, raw URLs, correlation IDs or payload
  values as metric labels.
- Confirm histogram buckets exist before relying on percentile queries.
- Prefer outcome and saturation signals over implementation counters with no
  operational use.

### Logs

- Follow the consumer's format, language and approved field set.
- Log event and outcome, not full request, token, payload or personal data.
- Reuse existing correlation fields and propagation.
- Temporary debug logging requires approval and an explicit removal plan.

### Traces

- Confirm instrumentation and service identity before adding manual spans.
- Propagate the consumer's verified context standard across supported
  boundaries.
- Do not duplicate personal or secret data in span names or attributes.

### Health

- Liveness answers whether restarting this process can help.
- Readiness answers whether this instance should receive its intended work.
- Discover actual workload and dependency semantics; a queue consumer, job and
  HTTP service may need different contracts.
- Keep probes fast and free of sensitive detail.

## Progressive references

- [Micrometer and Ktor](./references/micrometer.md)
- [PromQL, LogQL and dashboards](./references/promql-logql.md)
- [Alert design](./references/alerting.md)

## Approval boundary

Drafts and read-only inspection come first. Before editing code/config,
dashboards, alerts, thresholds or routing, publishing, deploying, or running
sensitive live queries, show the target and plan and get explicit approval.

## Grenser

### Alltid

- Derive names and labels from consumer evidence.
- Tie every new signal to an operational question.
- Protect personal data, credentials and payloads.
- Validate that the signal is actually emitted and queryable.

### Spør først

- New high-cardinality dimensions or retained data.
- Dashboard, alert, routing or production-threshold changes.
- Every external write or sensitive runtime inspection.

### Aldri

- Invent service, metric, label, environment or routing names.
- Add instrumentation with no intended consumer.
- Use observability as a reason to expose secrets or personal data.
