---
name: handoff
description: "Prepare a portable handoff when the user requests transferring work to another session, client, or colleague. Ordinary context compression and same-session delegation belong to the client."
---
# Handoff

> **OpenCode v1:** Skill names below are exact IDs from the active catalog, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Create a handoff only for a user-requested transfer. Let the client manage
ordinary compaction; a long conversation, high context usage, or phase change
does not trigger a handoff or require a fresh OpenCode session. Use the client's native
delegation with a bounded task brief for work within the same session.

1. Create a private directory under the user's OS temporary directory, for
   example with `mktemp -d` on Unix-like systems. Do not write the handoff to
   the repository or directly to a predictable shared temporary path.
2. Record the goal, current state, decisions and their rationale, remaining
   actions, blockers, and existing authorization. Focus the brief on the
   receiving task. If a skill recommendation helps, have the recipient resolve
   it against its active catalog rather than assume the same installation.
   Identify the repository by its known project identity or a safe canonical
   URL as well as the sender's local path; never print credential-bearing remotes.
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

On the same machine, the recipient can reuse the repository path. Elsewhere,
locate the corresponding checkout by repository identity; sender-local paths
are not instructions to create a matching directory. Rerun the commands and
compare the branch, commit, and status before continuing. Reassess changed
state before relying on old conclusions; ask the user only when the intended
workspace or remaining authority cannot be inferred. If no Git worktree or
`HEAD` exists, record the canonical working directory and relevant artifact
paths instead.

This preflight verifies repository identity and the shape of the working tree,
not byte-for-byte equality of uncommitted content. Treat claims about modified
or untracked content and previous test results as unverified after the handoff:
reread the complete current diff and rerun the relevant checks before relying
on them.

After writing the document, reopen it and confirm it is readable and non-empty.
Return the absolute path for a same-machine transfer. For a colleague or another
machine, also provide the redacted brief as copyable content and identify any
referenced files or uncommitted changes that must travel with it. Do not imply
that private temporary files are remotely accessible or durable. Sending,
publishing, or starting a new session is outside this skill's task.
