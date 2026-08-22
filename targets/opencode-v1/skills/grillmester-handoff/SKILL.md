---
name: grillmester-handoff
description: "Create a compact temporary handoff so a fresh OpenCode session can continue the current work."
---
# Handoff

> **OpenCode v1:** Backticked `grillmester-*` names below are skill IDs, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Create a handoff only at a real session seam or context-pressure boundary.
Use a short, bounded task brief for same-flow agent delegation instead.

1. Create a private directory under the user's OS temporary directory, for
   example with `mktemp -d` on Unix-like systems. Do not write the handoff to
   the repository or directly to a predictable shared temporary path.
2. Record the goal, current state, next actions, blockers, and suggested
   skills. If the user supplied arguments, use them to focus the next session.
3. Reference existing specs, plans, ADRs, context documents, issues, commits,
   diffs, and pull requests by canonical path or URL. Do not duplicate their
   contents; durable team state belongs in those artifacts.
4. Use separate `Verified now` and `Unverified or pending` sections. Include
   the command, path, or link that supports each important verified claim;
   put assumptions, stale reports, and unfinished checks in the latter.
5. Redact secrets and personally identifiable or sensitive information,
   including tokens, passwords, names, national identity numbers, and health
   information.

When inside a Git worktree with an existing `HEAD`, capture fresh output for
the canonical repository path, branch or detached state, full commit ID, and
complete status including untracked paths:

```bash
set -euo pipefail
repository_root=$(git rev-parse --show-toplevel)
(cd "$repository_root" && pwd -P)
git -C "$repository_root" symbolic-ref --quiet --short HEAD || printf '%s\n' DETACHED
git -C "$repository_root" rev-parse HEAD
git -C "$repository_root" status --short --branch --untracked-files=all
```

Tell the receiving session to use that repository path, rerun the commands,
and compare the branch, commit, and status before continuing. Stop and resolve
the discrepancy with the user when the state has drifted. If no Git worktree
or `HEAD` exists, record the canonical working directory and relevant artifact
paths instead.

This preflight verifies repository identity and the shape of the working tree,
not byte-for-byte equality of uncommitted content. Treat claims about modified
or untracked content and previous test results as unverified after the handoff:
reread the complete current diff and rerun the relevant checks before relying
on them.

After writing the document, reopen it from its canonical path and confirm that
it is readable and non-empty. Then print that absolute path so the user can
give it to the receiving session.
