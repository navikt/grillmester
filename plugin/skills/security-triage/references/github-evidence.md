# GitHub evidence

Use the tools advertised by the active GitHub connection. Repository search
and pull request access alone do not establish access to security alerts.
When an authorized CLI is the selected source, `gh api` can read the same
repository endpoints. Read every page in scope or label the result partial.

## Which repositories does the team maintain?

Use a team-provided scope or maintainer confirmation, dated to this review.
Record ownership separately from an instruction to defer work, future
retirement or a request to omit a repo from team documentation.
If the organization uses a
[GitHub custom property](https://docs.github.com/en/rest/orgs/custom-properties)
for the responsible team, check the schema and query its values across the
requested scope. Verify that missing or default values have a documented
meaning. An enforced, current register that covers the requested repository
types can settle a source-only question directly.

In the absence of a complete register, start from the team's paginated
access list at `GET /orgs/{org}/teams/{slug}/repos`. Reconcile it with
deployment evidence where applicable and any existing team catalog.
Search organization CODEOWNERS files for the exact team handle to find
candidates beyond that list. Read the effective file on the default branch.
Reconcile by repository ID or canonical name. Resolve discrepancies using
a current maintainer statement, catalog entry or repo-wide ownership rule.
If they disagree, check the latest decision about source maintenance.
Leave ownership open if it only settles who runs the workload.
Check [CODEOWNERS errors](https://docs.github.com/en/rest/repos/repos#list-codeowners-errors)
when a rule conflicts with permissions.
Admin access and topics are leads. A path rule only covers that path.
A README example can name a consumer. For an archive, check whether a
later transfer or retirement decision supersedes an old owner declaration.

Record the evidence for maintained, shared, externally maintained and
unresolved repositories. Keep access-only candidates visible. Surface an
independently verified urgent exposure even while its maintainer is being
resolved. Count source alerts only for the stated ownership scope. Preserve
archives and search, permission or pagination gaps. When using a team
catalog, show which entries agree, which depend on the catalog alone,
and which supported additions or conflicts the team could use to update it.

## Security evidence

Check status, filters, default branch and last successful analysis. On a
403, check the error message and rate-limit headers. Report a confirmed
permission failure as “access denied”. A [rate limit](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api#exceeding-the-rate-limit)
leaves coverage incomplete until collection resumes. Keep the last completed
page and respect the retry window. An ambiguous 403 or 404 leaves the cause
unknown. Call scanning disabled only when
the effective settings confirm it. Access denied alone is no evidence of a
live credential. Use the affected asset and known exposures to set urgency.

| Evidence | What to establish |
|---|---|
| Dependabot alerts (`dependabot/alerts`) | Match advisory ID, ecosystem, manifest, dependency path, installed version, affected range and fix if available. Check that the dependency graph includes resolved versions. Separate a security alert from a version-update PR. An alert can have no PR. |
| Open Dependabot PRs | Count open PRs authored by the Dependabot app in each scoped repo. List their numbers and updates, including grouped updates. Link a PR to an alert only when its changes cover the affected manifest, package and fixed version. Check outstanding tests or rollout before marking an alert resolved. |
| Code scanning (`code-scanning/alerts`) | Record the rule, tool, revision, affected location and most recent applicable analysis. Check effective default or advanced setup and language coverage. SARIF may contain image scanner findings already visible elsewhere. |
| Secret scanning (`secret-scanning/alerts`) | Require server-side masking such as `hide_secret=true` on the first and every subsequent list or detail read. If the tool cannot exclude values before retrieval, use a prefiltered extract or leave the source unread. Retain the alert ID, type, state and the minimum evidence needed for incident handling. |

For a possibly live credential, identify the owner who can assess exposure
and revoke or rotate it under the incident procedure. An alert ID, type or
validity alone cannot locate the value in Git history. Any history cleanup needs separate
evidence, a decision by the repository owner and its own scope.

Check controls where they affect a decision. For an empty dependency graph,
inspect the repository's dependency submission and last successful run.
For a shared delivery workflow, check the actual caller revision, job token
permissions and required checks. For an Actions lockfile, check which actions
it covers and whether the lock matches the workflow. External reusable
workflow calls and container images need their own immutable references.

Use observed repository or organization settings as evidence of inherited
controls. A missing workflow file by itself does not prove that code
scanning, secret scanning or a branch ruleset is absent.

Current sources: [Dependabot alerts](https://docs.github.com/en/rest/dependabot/alerts),
[team repositories](https://docs.github.com/en/rest/teams/teams#list-team-repositories),
[code scanning](https://docs.github.com/en/rest/code-scanning/code-scanning),
[secret scanning](https://docs.github.com/en/rest/secret-scanning/secret-scanning)
and [GitHub MCP toolsets](https://github.com/github/github-mcp-server).
