---
description: "Use when designing actionable alerts from verified service signals, ownership and routing."
---

# Alert design

Discover the current Nais alert mechanism, repository pattern, notification
routing, owner, severities and runbook convention from authoritative docs and
consumer evidence. Do not assume a resource kind, namespace-based routing,
channel or severity vocabulary.

## Choose symptoms, not components

Start with a failure that needs human action:

- user-visible failure or unacceptable latency
- sustained processing backlog
- repeated domain-operation failures
- exhausted capacity
- workload unavailable or repeatedly restarting
- absence of an expected success signal

Select the exact metric and labels from live/repository evidence. If no safe,
stable signal exists, add and validate instrumentation before writing an alert.
Do not alert on a convenient log phrase as a permanent substitute without
considering stability and data exposure.

## Threshold workflow

1. Identify owner, response action and urgency.
2. Establish baseline, normal variance and traffic sensitivity.
3. Define condition, duration and no-data behavior.
4. Test against historical or representative data.
5. Draft summary, impact, first check and runbook link.
6. Confirm routing and deduplication with the owning team.
7. Review after introduction and tune from observed signal quality.

No fixed threshold, evaluation window or environment promotion sequence is
portable. Ask when the consumer has no documented choice.

## Quality gate

An alert is not ready unless:

- someone owns it
- it represents actionable impact
- responders can identify the target
- annotations explain the first useful action
- sensitive data is absent
- expected false-positive/no-data behavior is understood
- routing and severity are verified

## Approval boundary

Changing an alert rule, threshold, routing destination, dashboard annotation or
runbook is an external/persistent write. Show the exact target and diff,
expected notification behavior and rollback, then obtain explicit approval.
Do not send a test notification without approval.
