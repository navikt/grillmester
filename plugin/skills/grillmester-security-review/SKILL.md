---
name: grillmester-security-review
description: Review a design or change for security and privacy risks involving sensitive data, authentication, authorization, secrets, logging, trust boundaries, external integrations, infrastructure permissions, or incident exposure. Use before delivery of security-relevant work or when the user requests a security review.
license: MIT
---

# Review security and privacy

## Establish facts and boundaries

Read the scoped design or complete diff, relevant repository policy, deployed
configuration, and tests. Identify protected assets, actors, data categories,
trust boundaries, entry points, privileged operations, external flows, and
plausible failure impact. Mark missing facts as unknown instead of filling them
from a generic checklist.

If the target runs in NAV or NAIS, handles NAV data or identities, or uses NAV
authentication, audit, or network controls, load [the NAV security review
reference](references/nav-security-review.md). Apply it only where repository
and current authoritative evidence show that it fits.

When the change adds or materially alters an entry point, trust boundary,
identity model, sensitive-data flow, privileged operation, external
integration, or deployed surface, load [the threat-modeling
reference](references/threat-model.md) and perform its DFD-first STRIDE review.

## Review the applicable surfaces

- Minimize sensitive data and keep it out of ordinary logs, URLs, errors,
  telemetry, fixtures, and agent output.
- Verify secret sourcing, storage, rotation, redaction, and failure behavior
  without printing secret values.
- Separate authentication from authorization; validate identity and token
  constraints, then enforce role, ownership, purpose, or resource access at the
  operation.
- Trace untrusted input to interpreters, queries, templates, files, redirects,
  deserializers, and outbound requests.
- Check trust-boundary and infrastructure changes for least privilege,
  explicit callers and destinations, environment separation, and safe defaults.
- Review external integrations for necessary data transfer, authenticated
  transport, failure containment, retention, ownership, and incident handling.
- Check dependencies, build and delivery changes, generated artifacts, and
  automation for supply-chain or privilege expansion.
- Confirm that security-relevant events are observable without exposing the
  protected data itself.

## Produce evidence

Discover the repository's security tools and required gates. When the active
agent can execute commands, run only safe, authorized checks relevant to the
change and report the command, result, and exit code. A read-only reviewer
validates supplied evidence instead; when a material claim lacks fresh
evidence, return `MISSING_EVIDENCE` and name the smallest relevant command for
the orchestrator to run.

Never install tools, contact external systems, rotate credentials, or mutate
deployed state merely to complete a review. Return findings ordered by
potential impact and exploitability. For each, identify the evidence, affected
asset or boundary, credible failure mode, and smallest effective mitigation.
Separate verified findings, inference, and unresolved questions. Escalate a
suspected active exposure or incident through the repository's incident
process without exposing sensitive evidence in the report.
