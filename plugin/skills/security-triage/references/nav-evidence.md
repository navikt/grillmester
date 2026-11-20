# Nav and Nais evidence

## Contents

- [Establish scope](#establish-scope)
- [Verify a runtime finding](#verify-a-runtime-finding)
- [Select a manual check](#select-a-manual-check)

## Establish scope

For “my team”, use a team the user has already selected for this assessment.
Otherwise read their membership slugs. `get_nais_context` provides
memberships. If identity details must be excluded, use the read-only GraphQL
`me → User → teams → nodes → team → slug` selection and check pagination.
Use a sole membership automatically. With multiple memberships, use a matching
user-selected default if available, otherwise ask which team. With no
usable context, ask for the team slug. A repository's deploy team identifies
the workload owner. Teams visible in broader views do not extend the scope.
Skip membership discovery when the requested target is already clear.

For a runtime lookup with a Nais team slug, use Nais MCP or a dated extract.
For a whole team, page through `team(slug:) → workloads` across the requested
environments. Keep the environment, workload kind and name, including jobs.
Check against the team's inventory counts when available. For the security
overview, page through `team.vulnerabilitySummaries` with the same environment
scope and reconcile the results with the workload list. Report production
separately and retain workloads with missing scans or unknown source repos.

For a whole-team repository assessment, resolve the linked GitHub team
through `externalResources.gitHubTeam.slug` or use the supplied GitHub team.
Page through its GitHub repositories and the Nais team's `repositories`
connection. Join these with repositories seen on deployments by canonical
GitHub identity, retaining each relationship. A registration grants
[permission to deploy](https://docs.nais.io/tutorials/hello-nais/#authorize-the-repository-for-deployment).
An unused-looking grant is an ownership lead. Before prioritizing its removal,
check intended use, deployment history and evidence of unnecessary privilege.
A deployment identifies the repository that triggered it. Where builds and
deploys are separate, use build provenance to identify the source. A team
catalog, when available, can explain shared work or add missing repositories.

## Verify a runtime finding

Record the deployed image digest, installed package and version, advisory,
scan state, timestamp and any suppression. Use the SBOM to verify the
installed package version. Use a current vulnerability report for the same
digest to verify whether the advisory still matches. Looking for a CVE ID
in the component inventory cannot settle that question. A finding list
can omit installed packages with no matching advisory. A missing SBOM,
a pending scan or a summary from an older image leaves a gap. A library
without a workload needs repository or consumer evidence instead.

Check the active tool catalog. Where available,
`get_workload_vulnerability_report` groups findings by installed package.
After rollout, `get_workload_vulnerability_status` checks the expected
digest and scan readiness. A ready scan still needs a finding-specific
check. On servers with read-only GraphQL, a known app can be read through
`team(slug:) → environment(name:) → application(name:) → image`. For other
workloads, resolve the matching field in the active schema. Read `digest`,
`sbom.status` and `vulnerabilitySummary.lastUpdated`. For a package decision, page through
`image.vulnerabilities`. Match `identifier` to the advisory and use the
package URL for its installed version. Read `remediation.fixVersion` and
suppression state where relevant. Select only the fields the decision needs. Validate
the query against the active schema and inspect individual fields if it differs.
For an explicitly authorized Nais CLI workflow, inspect `nais vulnerability`
help for team summary, per-workload summaries, individual findings and ID
search. Apply the team and environment filters and check result limits.

Use the package totals from the report tool when available. For a complete
masked JSONL extract of GraphQL nodes from **one scan of one digest**, this read-only
calculation returns a row per package URL and severity. It counts distinct
advisories for that exact package version. Check pagination and digest
before using the totals. In a reader-only client, request this small
aggregate or quote only the workload totals already supplied.

```sh
jq -sc 'map(if ([.identifier, .package, .severity] | all(type == "string" and length > 0))
  then . else error("missing finding fields") end) |
  group_by([.identifier, .package]) |
  map(if (map(.severity) | unique | length) == 1 then first else error("conflicting severities") end) |
  group_by([.package, .severity]) |
  map({package: .[0].package, severity: .[0].severity, count: length})'
```

Trace a shared package to a runtime base layer, a bundled application
dependency or a build stage. Check what the final image actually contains.
A verified build-provenance attestation connects its subject digest to the
recorded source and builder. A signed SBOM describes components. To close a
finding, check rollout and the advisory in the fresh scan of that digest
for each affected workload. [Nais SBOM and attestations](https://docs.nais.io/services/vulnerabilities/how-to/sbom/) ·
[SLSA build provenance](https://slsa.dev/spec/v1.2/provenance).

Nav's Golden Path recommends a minimal, distroless runtime image and shows
Chainguard from Nav's pull-through registry. The playbook also documents
public Chainguard images for runtimes outside the subscription. For another
base, check maintenance, patch delivery and the team's requirements. The old
`navikt/baseimages` are retired. For a supported Chainguard tag, check a
recent rebuild that pulled the updated base and reached production. For a
pinned digest, verify how the pin gets updated. Nav documents Digestabot
for digest-only changes on a Chainguard tag in its registry. Check the
updater's support before recommending it. [Choice of base image](https://github.com/navikt/security-playbook/blob/main/docs/08-sikker-utvikling/baseimages.md) ·
[Chainguard images and updates](https://github.com/navikt/security-playbook/blob/main/docs/10-verktoy/chainguard-dockerimages.md).

## Select a manual check

Use [Nav's Golden Path](https://sikkerhet.nav.no/docs/goldenpath/) to choose
a check that could change a priority.

- For a privileged API, compare its actual callers with the effective
  `accessPolicy`, then check which identity can perform the operation on the
  requested resource. [Nais Zero Trust](https://docs.nais.io/workloads/explanations/zero-trust/).
- For sensitive logging, trace a field through the formatter and all sinks
  in configuration or a synthetic test. Team Logs is the private destination
  for necessary sensitive logging. Check for unintended copies in ordinary
  logs. [Nais logging](https://docs.nais.io/observability/logging/).
- For a workflow that publishes or deploys, check which jobs can use write
  permissions or credentials, how third-party actions are locked, and which
  workflow revision the latest relevant zizmor or CodeQL analysis covered.
  [Nav's GitHub guidance](https://github.com/navikt/security-playbook/blob/main/docs/08-sikker-utvikling/github.md).
- For a production credential, read the manifest's secret bindings and
  identify which workloads receive it. Use names and configuration metadata
  only. [Nais Secrets](https://docs.nais.io/services/secrets/).

For a seemingly obsolete service, establish whether it still runs, has
consumers or holds deploy access. The Security Champion helps the team
follow up. Assign the action to the control owner. For remaining risk,
record the decision owner, a safe decision reference and a review trigger.
[Security Champion guidance](https://github.com/navikt/security-playbook/blob/main/docs/security-champion-rolle.md) ·
[TryggNok](https://github.com/navikt/security-playbook/blob/main/docs/08-sikker-utvikling/tryggnok.md).

[Nais vulnerability management](https://docs.nais.io/services/vulnerabilities/) ·
[Nais MCP capabilities](https://github.com/nais/cli/blob/main/MCP.md)
