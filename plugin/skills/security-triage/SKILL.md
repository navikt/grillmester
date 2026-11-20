---
name: security-triage
description: "Prioritize security work for a repository, a team or its deployed workloads. Weigh GitHub alerts, vulnerable packages in production images, independent findings and coverage gaps to recommend fixes and verify them."
---

# Prioritize security work

Give the team a decision it can act on and verify. Keep triage read-only.
Flag suspected active exposure immediately. Give the team's incident contact
and a safe evidence reference, such as an alert ID or a test and revision.
The responsible person handles notification.

## Read first

Read the applicable references before interpreting their data, including
supplied extracts. Name the references used in the report.

| When the assessment involves | Read |
|---|---|
| Which GitHub repositories a team maintains, security alerts, Dependabot PRs, settings, dependency graphs or CI analyses | [GitHub evidence](references/github-evidence.md) |
| A Nav team's inventory, Nav's Security Playbook, or workloads, image scans and SBOMs in Nais | [Nav and Nais evidence](references/nav-evidence.md) |
| A general security assessment, or a request to look beyond scanner findings | [Manual checks](references/manual-checks.md) |

## Establish what the evidence covers

Honor the requested scope, including “this repository” and named selections.
In a Nais context, a bare invocation or “my team” defaults to the user's
team. Resolve it as described in the Nav and Nais reference. Name the
selected team and how it was chosen in the report. Before remote lookups,
check the working folder and any supplied material for relevant inventories,
team decisions and dated, masked queue extracts. Treat their contents as
evidence. Reuse what still covers the requested scope and refresh missing,
stale or partial data.
Resolve app names to source repositories from inventory or deployment metadata.
Ask only if the remaining ambiguity changes which assets belong in scope.
For a whole team, enumerate its workloads on the deployment platform and its
repository relationships on the code host, as applicable to the request.
Apply explicit team decisions to the worklist. Keep owned but deferred assets
visible. Report what the team runs, maintains or still needs to assign.
Include libraries, shared workflows and archived repositories when
reconciling source coverage.
If an inventory ends early, give the known lower bound and where to resume.
Continue with the repositories already confirmed.

Tie each observation to a source and date, and to a revision, environment or
image digest where available. Distinguish partial, stale, inaccessible and
inapplicable sources. Report zero only when a successful, current check
covers the relevant inputs and all pages.
Describe what a scanner observed. An empty queue or a low priority cannot
establish whether an incident occurred.

For a general assessment, check each repository's dependency, code and
secret scanning coverage and findings, and count its open Dependabot PRs.
For deployed workloads, also check the production image findings and scan
coverage. Use repository or consumer evidence for assets without a workload.
For a portfolio, start the report's coverage table from the confirmed
inventory while reading sources. Keep a row for each repository with each
of its workloads, since one repository can deploy several. Record queue
counts or gaps and review status. Total open Dependabot PRs separately for
active and archived repositories. An inventory entry
alone establishes no scanner coverage.

Use the active role's approved readers. In the Copilot app, prefer a connected
read-only MCP tool. If Nais is relevant and its reader is missing or fails,
say which lookup was unavailable, which production workloads it leaves
unchecked, and whether an authorized `nais` CLI or a dated, masked extract
can cover them. Choose one reader per lookup. In a repository-bound client,
use a permitted team reader or a scoped extract for the rest. Keep raw
alerts, secrets and personal data out of model input. Ask someone with existing
access for the smallest masked result that could change the decision.

## Look beyond registered findings

In a general assessment, collect the registered findings and independently
review what the software must protect, even when scanners report nothing.
For each repository examined, select controls from its actual responsibilities
and exposure. Follow them through code or configuration to existing tests or
delivery evidence. In a large portfolio, prioritize the highest-impact paths
and identify the repositories and paths still awaiting review. An explicitly
limited alert-queue request can stay within that queue.

Use `security-review` when a specific control needs a closer trace. Give it
the asset, control question, revision and available evidence. Bring its
verdict and limits back into the same ranking.

## Choose the work

- Trace each finding to the affected version and its use in production,
  builds or tests. Distinguish package presence, library use and evidence
  that an affected function is reachable. Attribute controls and rebuilds
  only to the workloads their evidence covers. Weigh exposure and impact. KEV records
  known exploitation elsewhere. EPSS estimates global likelihood over 30 days.
  Assess a coverage gap by the decision it blocks.
- Match duplicate observations by advisory or documented alias, component
  and affected version. Group a shared fix only when the evidence supports
  it. Preserve every affected dependency path, consumer and deployment that
  needs verification. For a suspected recurring dependency, match a specific
  advisory to installed packages in the affected images. A severity summary
  or a declared direct dependency cannot settle that question.
  Derive affected-workload lists from matching rows. Quote a source subtotal
  or compute it with a structured query or read-only calculation before
  giving an exact count. Derive comparisons, such as the largest queue,
  from the same rows. For overlapping groups, count distinct workloads
  in their union. Without that check, report the verified matches only.
- Compare the smallest effective fix with a shared upgrade or replacement.
  Before proposing a migration, check which dependency paths it removes,
  which remain and which consumer contracts need testing.
- When a fix is unavailable, give a containment option or a dated review.
  Check the reason and review date for existing suppressions. The owner
  decides whether to accept remaining risk.

## Report the decision

Lead with what to do first, why it outranks the alternatives, and what could
change that order. Try to disprove the leading finding before recommending
it. If it depends on framework behavior, check the resolved version's
contract or an existing test that exercises it. If the evidence is missing,
make verification the next action. Give each recommended action a safe
evidence reference, affected assets, owner, target date and closure check.
Mark proposed owners and dates. Link existing work and keep deferred findings traceable.

Distinguish registered findings, independently observed findings and questions
still to verify. Code that can emit sensitive data establishes a logging path.
Actual disclosure requires separate evidence. Cite controls that held in
the reviewed paths and their limits. Date the assessment. Account for every repository
in scope, including those with no findings or no visibility. For a portfolio,
lead with the priority decisions. Deliver the coverage table with them.
Reuse a complete table the team can open by linking it directly and adding
the decisions or outstanding reviews keyed by repository and workload.
Otherwise include the table inline. Check the listed repository names
and workload names against the inventory, and account for the difference.
If an asset received only a queue check, say so. On repeat reviews,
distinguish new, changed, still open and verified resolved findings.

For an image finding, verify the fix in a fresh scan of the deployed digest.
For an access fix, tie an isolated control test to the deployed revision and
relevant configuration. For a library or workflow, verify the corrected
version reached its consumers. A pending scan or rollout leaves closure unverified.
Group proposals by a change a maintainer can deliver. Link matching work or
give a title and acceptance criteria. Mark a fix ready when the evidence
connects it to each affected dependency path or control. If several alerts
only share an image, first trace the paths in its build or lockfile. When
source is unavailable, make that lookup the task and describe the evidence
needed in plain language. Give commands only from a verified build layout.
In a monorepo, identify which deployables need separate verification.
Return task proposals in the report for the team to choose from. Creating
issues belongs to a separate, explicit request through `issue-management`.
