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

If the target runs in Nav or NAIS, handles Nav data or identities, or uses Nav
authentication, audit, or network controls, load [the Nav security review
reference](references/nav-security-review.md). Apply it only where repository
and current authoritative evidence show that it fits.

When the change adds or materially alters an entry point, trust boundary,
identity model, sensitive-data flow, privileged operation, external
integration, or deployed surface, load [the threat-modeling
reference](references/threat-model.md) and perform its DFD-first STRIDE review.

## Review the applicable surfaces

- Minimize sensitive data and keep it out of ordinary logs, URLs, errors,
  telemetry, fixtures, and agent output.
- Trace values through validation and diagnostic wrappers before approving log
  or error output. A field named `validatedValue`, a validation report, or an
  interpolated exception can still contain the original sensitive input.
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
agent is Doctor Who, or otherwise lacks explicit command-execution capability,
use repository evidence, approved web/MCP sources, and supplied CI or test
artifacts only. Never invoke or prescribe shell, `gh`, raw HTTP, or another
network command. When a material claim lacks evidence, ask for the smallest
pasted or exported artifact and return `Status: NEEDS_INPUT`, naming the claim
that remains unverified.

In a separate developer or security-reviewer workflow, an agent whose own
contract explicitly grants command execution may run only safe, authorized
checks relevant to the change and report the command, result, and exit code. A
non-product reviewer that expects fresh evidence but cannot execute may return
`MISSING_EVIDENCE` and hand the evidence request to an explicitly authorized
orchestrator. This paragraph does not grant Doctor Who shell access and must
not be used to route commands through the user.

Never install tools, contact external systems, rotate credentials, or mutate
deployed state merely to complete a review. Return findings ordered by
potential impact and exploitability. For each, identify the evidence, affected
asset or boundary, credible failure mode, and smallest effective mitigation.
Separate verified findings, inference, and unresolved questions. Escalate a
suspected active exposure or incident through the repository's incident
process without exposing sensitive evidence in the report.
