---
description: "Use for Micrometer instrumentation and health contracts in a verified Kotlin/Ktor service."
---

# Micrometer and health in Ktor

Use only after confirming that the consumer uses Ktor and Micrometer. Discover
the exact Ktor/Micrometer versions, registry type, dependency injection,
metrics route and deployment scrape/probe configuration.

## Registry and plugin

Find the existing registry provider and Ktor metrics installation. A service
should normally reuse one application registry rather than create a registry
per component. Confirm the actual API against the installed library version.

An illustrative shape is:

```kotlin
install(MicrometerMetrics) {
    registry = existingRegistry
}
```

Do not paste it before locating the consumer's established wiring and test
pattern.

## Metric choice

- Counter: cumulative event count.
- Timer: count and duration of operations.
- Gauge: current value with a trustworthy lifecycle.
- Distribution summary: distribution of non-time values.

Discover local naming conventions. Micrometer may translate dot-form meter
names to Prometheus names, but dashboards and alerts must use the emitted
names, not an inferred translation.

For percentiles in PromQL, verify that the timer publishes histogram buckets.
Without emitted bucket series, histogram quantile queries cannot produce a
meaningful result.

## Labels

Use bounded domain dimensions that answer a planned query. Discover allowed
names and values from the consumer. Never label with message keys, payload IDs,
personal identifiers, tokens, correlation IDs or unbounded exception text.

## Health routes

Compare application behavior with deployed probes:

- Liveness: would restarting this process help?
- Readiness: should this instance receive its intended work now?
- Startup: does the platform need a distinct allowance for initialization?

Do not assume route names, ports or which dependencies belong in a probe.
External dependency availability often belongs in metrics/alerts rather than
liveness, because restarting may not help. Decide from workload semantics.

Keep checks fast, bounded and free of sensitive response detail. Validate
failure and recovery behavior, not only the green path.
