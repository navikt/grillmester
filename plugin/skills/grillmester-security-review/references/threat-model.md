# DFD-first threat modeling

Use this reference when a change adds or materially alters an entry point,
trust boundary, identity model, sensitive-data flow, privileged operation,
external integration, or deployed surface. Model the scoped current or
proposed flow only; do not invent adjacent architecture.

## Draw the data flow first

Pin the reviewed revision, design, or diff. Build a compact data-flow diagram
from repository and architecture evidence that names:

- actors and workload identities;
- protected assets and data categories;
- entry points, processes, stores, queues, and external recipients;
- credentials or identity context carried across each flow;
- every trust boundary crossed and the control observed at that boundary.

Keep unknown boundaries or controls visibly unknown. A diagram inferred from
names alone is not evidence.

## Walk STRIDE across each boundary

Evaluate each applicable category against every entry point, flow, store, and
privileged operation:

- **Spoofing** — caller, user, workload, producer, or external-service identity.
- **Tampering** — requests, events, state, configuration, build artifacts, or
  data in transit and at rest.
- **Repudiation** — whether a security-relevant action or decision can be
  reconstructed with trustworthy, privacy-safe evidence.
- **Information disclosure** — responses, caches, logs, errors, telemetry,
  exports, backups, and unintended egress.
- **Denial of service** — unbounded work, payloads, retries, fan-out, resource
  exhaustion, hot keys, queue pressure, and unavailable dependencies.
- **Elevation of privilege** — missing role, ownership, purpose, tenant, or
  resource checks; overbroad network, workload, or automation permissions.

Mark a category not applicable only with a flow-specific reason. Record an
unknown when evidence is absent rather than declaring the threat mitigated.

## Connect evidence to mitigation

For each credible threat, report:

1. the affected asset and trust boundary;
2. the evidence and exact precondition or attack path;
3. the impact and existing controls;
4. the control gap or unresolved fact;
5. the smallest effective mitigation; and
6. a deterministic way to verify that mitigation.

Order findings by impact and exploitability. Do not produce checklist noise
for threats unsupported by the data flow, and do not treat the presence of a
control as proof that it is configured or enforced correctly.
