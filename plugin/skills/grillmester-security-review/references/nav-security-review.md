# NAV security and privacy review

Use this reference only when the target repository or task establishes a NAV
or NAIS context. Treat repository documentation and current authoritative NAV
and NAIS guidance as the source of truth. Platform controls and organizational
terminology change; verify consequential claims instead of applying this
document as a universal policy.

## Data and privacy

- Identify the processing purpose, data subjects, fields, derived facts,
  recipients, retention, and deletion path. Classification depends on context
  as well as field type.
- Treat national identity numbers as personal data whose use, exposure, and
  propagation must be minimized and protected. Protected-address information,
  health information, and facts that reveal health or benefit circumstances
  can require stronger safeguards. Confirm the applicable classification with
  maintained product and privacy documentation instead of inferring it from
  the field name alone.
- Use only clearly synthetic identities in source code, examples, tests, and
  review output. Verify the approved test-data source when executable
  identifiers must pass format validation.
- Check whether combining otherwise ordinary fields reveals a sensitive fact.
  Minimize collection and propagation at every boundary, including events,
  caches, analytics, exports, backups, and test fixtures.
- Record an unresolved legal basis, retention rule, or data classification as
  a blocker for the responsible product or privacy role; do not invent it
  during technical review.

## Logs, telemetry, audit, and secrets

- Keep personal data, tokens, credentials, and sensitive case facts out of
  ordinary application logs, URLs, exception messages, metrics labels, traces,
  dashboards, and agent transcripts.
- Prefer correlation identifiers and non-sensitive structured fields. Confirm
  that correlation values cannot themselves identify a person or grant access.
- Determine audit-logging requirements from the user journey, data category,
  applicable NAV guidance, and maintained consumer policy. Audit access to or
  changes of protected data when required; do not assume that every background
  lookup belongs in an audit log.
- Keep audit events separate from ordinary logs when the approved platform
  pattern requires it. Log only necessary actor, subject reference, action,
  decision, time, and resource context; protect access and retention according
  to current policy.
- Source secrets through the approved platform mechanism. Review manifests,
  configuration, workflows, examples, generated files, and history-facing
  changes for accidental disclosure. Redact values from evidence while
  preserving the location and type of finding.

## Authentication and authorization

- Derive the identity mechanism from the caller and audience. Verify current
  issuer, audience, signature, lifetime, and client constraints against the
  repository's chosen NAV authentication pattern.
- Treat possession of a valid token as authentication, not sufficient
  authorization. Check role, organization, case or resource ownership, purpose,
  protected-address handling, and employee restrictions where applicable.
- Verify machine-to-machine and on-behalf-of flows independently. Do not
  silently forward a user token to a service with a different audience.
- Keep internal probes and operational endpoints deliberately scoped. Confirm
  whether they require platform-only reachability, application authentication,
  or both.
- Do not use call or consumer correlation headers as authorization evidence.

## Conditional NAV API and browser signals

Apply these checks only when the actual API, gateway, client, or browser
architecture uses the named mechanism. Verify the current contract and which
component owns each control before reporting a gap.

- When `Nav-Call-Id` is part of the contract, trace it from ingress through
  downstream calls, responses, and approved structured logging. Preserve the
  existing value across hops unless the boundary contract says otherwise. Use
  it for correlation and troubleshooting, never for authentication or
  authorization.
- When `Nav-Consumer-Id` is emitted by an established gateway or client
  contract, verify how it is set and trusted before using it for per-consumer
  rate limiting or audit context. Define safe behavior when it is absent or
  spoofable. Never treat it as proof that a caller may access a resource.
- For responses containing sensitive personal data, assess whether
  `Cache-Control: no-store` or another stricter cache policy is required across
  the real client, proxy, and gateway path. Verify behavior instead of adding a
  header without understanding downstream caching.
- When Wonderwall or another browser-facing identity layer is present, map
  ownership of login, session cookies, CSRF protection, security headers, and
  application-level authorization. Avoid both duplicated authentication and a
  gap where each layer assumes the other enforces a control.

## NAIS network and workload controls

- Read the actual manifests and deployed architecture before evaluating
  `accessPolicy`. Verify current NAIS semantics for omitted and empty rules
  rather than relying on memory.
- Make inbound callers and outbound applications or hosts explicit and no
  broader than the observed flow requires. Check application, namespace,
  cluster, environment, and external hostname values.
- Treat network policy and application authorization as complementary controls.
  A permitted network caller may still need identity and resource-level
  authorization.
- Scrutinize new external egress, broad wildcard access, cross-namespace or
  cross-cluster traffic, public ingress, privileged workload settings, writable
  filesystems, and expanded service-account permissions.
- Confirm that development and production configuration do not accidentally
  share identities, destinations, secrets, or data.

## External integrations and data movement

- Name the owning and consuming teams, purpose, data categories, contract,
  authentication, failure behavior, and deletion or retention responsibility.
- Check whether the integration changes processing purpose, crosses an
  organizational or trust boundary, or sends data outside NAV-controlled
  infrastructure. Route unanswered governance or agreement questions to the
  responsible roles.
- Require bounded timeouts and retries, idempotency where side effects can
  repeat, safe error handling, and observability that does not reveal payloads.
- Review exports and support tooling as data disclosures, including temporary
  files, manual downloads, analytics sinks, and debugging access.

## DPIA, audit, and escalation

- Reassess privacy impact when processing purpose, sensitive data, scale,
  systematic monitoring, automated decision support, data combination,
  external recipients, or technology changes materially. The responsible data
  controller decides the process with privacy-office advice; the agent should
  surface evidence and uncertainty, not declare legal sufficiency.
- Confirm current audit requirements with maintained NAV guidance and relevant
  audit-logging owners when protected data is displayed, changed, exported,
  deleted, or access is permitted or denied.
- Escalate suspected credential exposure, unauthorized access, or
  personal-data breach immediately through the repository's incident procedure.
  Preserve necessary evidence without copying sensitive content into chat,
  issues, or ordinary logs.
- Seek product-security, privacy, legal, platform, or audit-log advice when the
  change introduces a new data category, identity model, external boundary,
  privileged access path, or unresolved policy interpretation.

## Evidence checklist

- Map every material claim to code, manifest, configuration, test,
  authoritative documentation, or an explicitly named unknown.
- Use repository-provided scanners and policy checks when available. Secret
  scanning, dependency review, container scanning, infrastructure validation,
  and workflow analysis support the review but do not replace design and
  authorization checks.
- Record exact commands, relevant output, exit codes, tool versions when
  material, and the analyzed revision or diff boundary.
- Distinguish absence of a detected problem from proof of safety. State which
  paths, environments, and runtime behavior were not examined.

Authoritative starting points include [NAV security
guidance](https://sikkerhet.nav.no/) and [NAIS
documentation](https://docs.nais.io/). Follow the repository's pinned or
maintained references when they are more specific.
