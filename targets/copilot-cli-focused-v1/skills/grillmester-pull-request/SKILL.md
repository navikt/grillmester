---
name: grillmester-pull-request
description: Create or update a pull request for a verified task-scoped change. Use when the user explicitly asks to open or update a PR after implementation, self-review, and required deterministic gates are complete.
---

# Prepare and publish a reviewable pull request

Do not create or modify a pull request until the user has explicitly authorized
that external action. A request to implement, verify, or review a change is not
itself authorization to publish it.

## Establish the delivery boundary

1. Resolve the repository, current branch, base branch, remote, and existing PR
   from current Git state. Never hardcode an owner, repository, or branch.
2. Read the complete task-scoped diff, including staged, unstaged, committed,
   and untracked content. Stop if unrelated work cannot be separated safely.
3. Read the repository's pull-request template and contribution instructions
   when present. Follow existing title, issue-linking, language, reviewer, and
   merge conventions rather than inventing replacements.
4. Confirm that acceptance criteria are covered and that required gates were
   run after the final diff change. Record exact commands, relevant output, and
   exit codes. Label missing or environment-only proof honestly.

## Draft before publishing

Prepare a concise title and body containing:

- the observable outcome and why it matters;
- the material changes and deliberate non-goals;
- issue or task links using the repository's established closing semantics;
- fresh verification evidence;
- risk, rollout or rollback notes, and focused reviewer guidance;
- any accepted concern, waived review, or unverified behavior required by
  repository policy.

Avoid implementation diaries, generated filler, copied secrets or personal
data, and claims that exceed the supplied evidence. Present the complete draft
and target base/head to the user when authorization is not already explicit.

## Create or update

Use the available GitHub integration or authenticated CLI for the resolved
repository. Update an existing pull request for the branch rather than opening
a duplicate. Perform only the authorized operations; do not merge, alter
project state, request reviewers, or change labels unless those actions were
also authorized.

Read the resulting pull request back and verify its URL, title, base/head,
body, and current check state. Report the link and any remaining gate or review
work without claiming merge readiness beyond repository policy.
