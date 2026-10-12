---
name: app-sandbox-setup
description: "Configure the GitHub Copilot desktop app's local sandbox on macOS with a reviewed plan, confirmed settings update, or manual click guide."
disable-model-invocation: true
---

# App sandbox setup

Use explicitly for the **GitHub Copilot desktop app on macOS**, not CLI sandbox
configuration; the CLI keeps its own settings and the two never sync. The app
stores one policy **per project** in `~/.copilot/data.db`; one run plans every
project the app knows. Use the bundled [script](scripts/app_sandbox_setup.py),
never ad hoc DB updates.
The [settings documentation](https://docs.github.com/copilot/how-tos/cloud-and-local-sandboxes/configuring-local-sandbox-settings)
and [session documentation](https://docs.github.com/copilot/how-tos/cloud-and-local-sandboxes/using-local-sandboxing)
describe app controls (verified 2026-10-08); enterprise settings may override
them. `--home PATH` and `--db PATH` support isolated fixtures.

Many users are not developers. Answer in the user's language with plain words;
you handle digests, flags and exit codes. Do not paste raw script output
unless asked.

## Before you start

- Use an installed Python 3.9+. Stock `/usr/bin/python3` and git may open an
  install dialog for Xcode Command Line Tools: tell the user to accept it and
  wait, or use Python from Homebrew or mise. Without Python nothing runs,
  including `guide`.
- Ask once whether the user builds, tests or runs dev servers locally, for
  example Gradle, Testcontainers or `pnpm dev`.
  - **No:** recommend `--mask-credentials`, which matches the app's own
    default: the token the app injects stays behind its proxy, and the blocked
    loopback does not matter. Tokens in files such as `~/.npmrc` stay readable
    either way. Recommend `--no-docker` unless they use Docker.
  - **Yes:** new policies default to masking **OFF** so loopback works; explain
    the token risk. Offer `--no-docker` when Docker and Testcontainers are not
    needed.
  - Offer the optional toolchain add-ons only to developers.

## Plan → confirm → apply → verify

1. Run `python3 <script> plan` first. If exit 2 reports access **denied**, ask
   for **Run outside the sandbox? → Run once** for that single command.
   Never silently bypass denial or select **Disable sandbox and run**.
   The user may instead choose `/sandbox off` or a normal terminal.
2. Present the plan as described below. Reruns preserve both credential
   toggles unless `--mask-credentials` or `--no-mask-credentials` is selected.
   Recompute after option changes. Report skipped corrupt policies as partial,
   not complete; verify in such a project has no known masking state.
3. Obtain explicit **conversational confirmation**, then run
   `python3 <script> apply --confirm <digest>` with identical options.
   Request **Run once** separately if this apply is denied. Apply rechecks
   schema and digest in one transaction, backs up the DB, merges policies and
   enables sandbox for valid projects. Failed DB writes roll back.
4. Policy changes apply to **NEW sessions or after `/restart-session`**.
   `/sandbox off`/`on` affects the current session immediately and persists
   through restart, overriding project defaults. After `/sandbox off`, use
   `/sandbox on` **plus** `/restart-session`, or a new session.
5. In a **NEW sandboxed session**, from the project directory, run
   `python3 <script> verify`. Add `--mask-credentials` when that project's
   masking is ON after apply, as the plan's `Credential masking after apply`
   line shows; reruns without a flag keep earlier choices, so do not copy the
   last run's flags. For a `mixed` project, ask the user to choose masking ON or
   OFF, then rerun plan and apply with that explicit flag before verify. Add `--no-toolchain` for users who do not build locally:
   otherwise verify gates on Java, node and pnpm and runs `./gradlew --version`,
   which may download the wrapper distribution.
   Offer to create that session if supported; put the exact Python command,
   flags included, in its kickoff prompt, not a slash-command string. The new
   session does not know earlier choices. Never run verify outside the sandbox.
   Exit 0 requires matching behavioral probes and all project gates; exit 7
   includes unavailable/mismatched gates and prints a hint when the masking
   flag looks wrong. HOME write succeeding means this session is not
   sandboxed. Do not declare setup verified otherwise.

Exit codes: **1** usage/setup/no projects; **2** DB missing/denied/unreadable;
**3** schema mismatch (use `python3 <script> guide`, never guess the schema);
**4** digest mismatch (replan/reconfirm); **5** busy/locked after up to 30 s
(retry later, never delete WAL/SHM). Guide also maps paths to Settings labels.

## Presenting the plan

- Lead with a short summary: how many projects change, what they gain (code
  folders, build and package caches, Docker if kept) and what stays blocked
  (SSH keys, cloud and cluster credentials, the app's own files).
- Explain every `Warning:` line in plain words; each needs a decision or an
  action. For non-developers, group toolchain and git warnings (Java pins,
  missing JDKs, unreadable toolchain files, manual `github-app.yml` blocks, SSH
  remotes, commit signing) as items for a developer on the team: they need no
  decision now. `Info:` lines are background: mention one only when it explains
  something the user asks about or is about to hit. JSON output separates
  `warnings` from `info` and lists `masking_after` per project.
- Settle the two real decisions, masking and Docker, using
  [the risks](references/risks.md).
- Apply also writes a marked toolchain block into a project's instructions when
  a pinned tool needs `mise exec` or `JAVA_HOME`; `--no-instructions` opts out.
- Offer the full per-project diff. Show it unprompted when it removes user
  entries, keeps a broad grant or removes a placeholder directory.
- Keep the digest to yourself unless asked.

## When to rerun

Rerun plan and apply after adding a project in the app (new projects start
without a sandbox policy), installing tools, app updates or creating credential
folders such as `~/.aws`. Default apply re-enables valid projects.

## References

- [Risks to explain before confirmation](references/risks.md)
- [Toolchains, verify probes and the optional shell profile and Gradle paths](references/toolchain.md),
  for developers whose Java, node or pnpm fails in the sandbox
- [Change later, rollback and backups](references/maintenance.md)
