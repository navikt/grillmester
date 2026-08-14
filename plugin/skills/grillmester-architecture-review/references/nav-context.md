# Nav context

Load this reference only when Nav- or NAIS-specific facts could change the
architecture recommendation. It is contextual guidance, not Nav policy or a
reason to run a special review merely because the repository is in Nav.

## Establish current context

- Start with consumer code, manifests, contracts, decisions, and explicit
  policy.
- Verify volatile platform, identity, security, and operating facts against
  current authoritative documentation from the responsible owner. For Nais
  claims, start with [the current Nais documentation](https://docs.nais.io/).
  Cite the concrete page and date checked; internal policy may be stricter.
- Never infer a universal "Nav standard" from prevalence in other repositories.
  Compare alternatives against the verified identity, data-flow, failure,
  operating, migration, and exit needs.
- Check whether a supported platform capability covers the need, but verify its
  identity, data-flow, failure, operating, migration, and exit behavior before
  recommending it.

## Ownership and advice

- Name the decision owner, affected teams, producers, consumers, contract
  owners, and operators.
- Architecture Advice informs the owning team's decision; it is not central
  approval. Identify advice needed across team or platform boundaries without
  claiming it was obtained.
- Make platform deviations, cross-team coordination, and exit costs explicit.

## Route depth

Keep this skill responsible for cross-cutting architecture trade-offs. Use
`/grillmester-security-review` for a focused security/privacy or threat review,
`/grillmester-auth-overview` for concrete identity mechanisms,
`/grillmester-nais-manifest` for manifest work,
`/grillmester-api-design` or `/grillmester-kafka-topic` for concrete contracts,
`/grillmester-observability-setup` for telemetry and alerts, and
`/grillmester-nav-troubleshoot` for incident diagnosis. These deep dives are
not prerequisites; finish the architecture review and report missing evidence
when one is unavailable.

When the open choice is whether to replace REST with Kafka, keep the transport
trade-off here. After that direction is chosen, route the concrete event flow
and contract to `/grillmester-kafka-topic`.
