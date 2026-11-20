---
name: security-review
description: "Examine whether a security control holds, investigate a single finding, or review a design or change for security and privacy risks. Use when work touches sensitive data, identity, authorization, trust boundaries or privileged operations; use `security-triage` to prioritize security work for a repository or team, and `nav-platform` to implement an authentication flow."
---
# Review security and privacy

> **OpenCode:** Skill names below are exact IDs from the active catalog, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

## Read first

1. Find every row below that the task touches, and look again when new facts
   appear.
2. Read those references before you edit, answer or run a command.
3. Name the references you read when you report.

| The task touches | Read |
|---|---|
| **Confirmed Nav context:** the task or repository identifies Nav/Nais, Nav data or identities, a fødselsnummer, or a Nav authentication, audit or network control | [nav-security-review.md](references/nav-security-review.md) for those controls. For a generic service, stay with the evidence supplied for that service. |
| **New attack surface:** it adds or materially alters an entry point, trust boundary, identity model, sensitive-data flow, privileged operation, external integration or deployed surface | [threat-model.md](references/threat-model.md), and perform its DFD-first STRIDE review |

## Establish facts and boundaries

Read the scoped design, complete diff, control implementation or evidence for
the reported finding, relevant repository policy, deployed configuration, and
tests. Identify protected assets, actors, data categories, trust boundaries,
entry points, privileged operations, external flows and plausible impact. Mark
missing facts as unknown. If an extract omits a control, ask for its design or
implementation before calling it absent. Reserve “undecided” for a choice
the team actually records as open.

Use `nav-platform` for authentication implementation and `architecture-review`
for broader design trade-offs. When `security-triage` requests a control
review, answer the specific question with the supporting evidence, limits
and remediation. Triage owns the combined ranking.

## Investigate a reported finding

Pin the claim to its source, advisory or rule, revision, package version or
artifact, and affected operation. For secret alerts use only metadata with
values excluded at the source. Trace the actual dependency path or code and
the controls that apply in the affected environment. Look for evidence
that would disprove the claim, such as an unaffected resolved version,
a build-only dependency, or an ownership check on every path to the resource.
Assess build and delivery privileges separately from production reachability.

For a single finding, review only surfaces that could change the verdict.
If the control already covers the claim, cite it and the test or evidence
that exercises it. Stop there unless a specific unresolved precondition
could change the result. For a supported finding, give the smallest fix
and its check. For a runtime finding, distinguish a source fix, deployment
of the intended digest, and a current scan or control check on that deployment.
For a code-scanning alert, verify that a successful analysis covered the
correct revision, rule and configuration before calling a fix verified.
When the evidence is inconclusive, say which observation would settle the
claim and who can supply it.

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

Discover the repository's security tools and required gates. When your role
forbids command execution or the runtime lacks explicit command-execution
capability, use repository evidence, approved web/MCP sources, and supplied CI
or test artifacts only. Never invoke or prescribe shell, `gh`, raw HTTP, or
another network command. When a material claim lacks evidence, ask for the
smallest pasted or exported artifact and return `Status: NEEDS_INPUT`, naming
the claim that remains unverified.

In a separate developer or security-reviewer workflow, an agent whose own
contract explicitly grants command execution may run only safe, authorized
checks relevant to the change and report the command, result, and exit code. A
non-product reviewer that expects fresh evidence but cannot execute may return
`MISSING_EVIDENCE` and hand the evidence request to an explicitly authorized
orchestrator. This paragraph grants no command execution to a role that
forbids it and must not be used to route commands through the user.

Never install tools, probe the reviewed service, rotate credentials, or mutate
deployed state merely to complete a review. Read other systems only through
approved, read-only sources. Return findings ordered by
potential impact and exploitability. For each, identify the evidence, affected
asset or boundary, credible failure mode, and smallest effective mitigation.
Separate verified findings, inference, and unresolved questions. Flag a
suspected active exposure to the user immediately and identify the
repository's incident route. Keep sensitive evidence in the approved system.
