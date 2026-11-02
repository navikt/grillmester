---
name: handoff
description: "Prepare a portable handoff when the user requests transferring work to another session, client, or colleague. Ordinary context compression and same-session delegation belong to the client."
disable-model-invocation: true
---

# Handoff

Write a handoff only when the user asks for a transfer. A long conversation,
high context usage or a phase change is not a reason; the client handles
ordinary compaction, and work inside the session uses its native delegation.
When the user says what the next session is for, tailor the document to that.

Save the document in a new private directory under the OS temporary directory,
for example from `mktemp -d`, never in the repository or at a predictable
shared path. Include:

- the goal, current state, decisions with their reasons, remaining steps,
  blockers and the authorization already given;
- the repository's identity as owner/name or a safe canonical URL, plus the
  local path for a transfer on the same machine; never print or record a remote
  with credentials;
- fresh output of `git rev-parse HEAD` and
  `git status --short --branch --untracked-files=all`, which also shows the
  branch or a detached `HEAD`; outside a Git worktree or before the first
  commit, the working directory and relevant artifact paths instead;
- links or paths to existing specs, plans, ADRs, issues, commits, diffs and
  pull requests instead of copies of their content;
- separate `Verified now` and `Unverified or pending` sections: each verified
  claim with the command, path or link that supports it, and assumptions, stale
  reports and unfinished checks in the second;
- suggested skills for the next session when they help, for the recipient to
  resolve against its own skill catalog.

Redact secrets and personal or sensitive data, including tokens, passwords,
names, national identity numbers and health information.

In the document, tell the recipient to rerun those Git commands and compare
before continuing, and to reread the complete diff, including staged and
untracked files, and rerun the relevant checks before relying on earlier
results: the status shows the shape of the working tree, not its uncommitted
content. The recipient asks the user only when the intended workspace or the
remaining authority cannot be inferred. A local path from another machine is
not an instruction to recreate it.

Read the document back to confirm it is complete, then return its absolute
path. For a colleague or another machine, also give the redacted text to copy
and name the files or uncommitted changes that must travel with it. Do not
imply that a private temporary file is shared or durable. Sending, publishing
or starting a new session is outside this skill.
