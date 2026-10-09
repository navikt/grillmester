---
name: app-sandbox-setup
description: "Configure the GitHub Copilot desktop app's local sandbox on macOS with a reviewed plan, confirmed settings update, or manual click guide."
---
# App sandbox setup

> **OpenCode v1:** Skill names below are exact IDs from the active catalog, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Use explicitly for the **GitHub Copilot desktop app on macOS**, not CLI sandbox
configuration. Policies live **per project** in `~/.copilot/data.db`.
Use the bundled [script](scripts/app_sandbox_setup.py), never ad hoc DB updates.
The [settings documentation](https://docs.github.com/copilot/how-tos/cloud-and-local-sandboxes/configuring-local-sandbox-settings)
and [session documentation](https://docs.github.com/copilot/how-tos/cloud-and-local-sandboxes/using-local-sandboxing)
describe app controls (verified 2026-10-08); enterprise settings may override
them. Use an installed Python 3.9+: stock Python/git may require Xcode tools.
`--home PATH` and `--db PATH` support isolated fixtures.

## Plan → confirm → apply → verify

1. Run `python3 <script> plan` first. If exit 2 reports access **denied**, ask
   for **Run outside the sandbox? → Run once** for that single command.
   Never silently bypass denial or select **Disable sandbox and run**.
   The user may instead choose `/sandbox off` or a normal terminal.
2. Present the changed-project diff, **all warnings**, and `Plan digest`.
   Explain masking and Docker below. New policies default to masking **OFF**;
   reruns preserve both toggles unless `--mask-credentials` or
   `--no-mask-credentials` is selected. Offer `--no-docker`. Recompute after
   option changes. Report skipped corrupt policies as partial, not complete.
3. Obtain explicit **conversational confirmation**, then run
   `python3 <script> apply --confirm <digest>` with identical options.
   Request **Run once** separately if this apply is denied. Apply checks schema
   and a fresh digest under `BEGIN IMMEDIATE`, backs up, merges policies and
   enables sandbox for valid projects. Failed DB writes roll back.
   After commit, only planned, still-empty, non-symlink placeholders are removed;
   cleanup failures warn without undoing policy.
4. Policy changes apply to **NEW sessions or after `/restart-session`**.
   `/sandbox off`/`on` affects the current session immediately and persists
   through restart, overriding project defaults. After `/sandbox off`, use
   `/sandbox on` **plus** `/restart-session`, or a new session.
5. In a **NEW sandboxed session**, from the project directory, run
   `python3 <script> verify` (add `--mask-credentials` for masking ON).
   Offer to create that session if supported; put the actual Python command in
   its kickoff prompt, not a slash-command string. Never run verify outside
   the sandbox. Exit 0 requires matching behavioral probes and all project
   gates; exit 7 includes unavailable/mismatched gates. HOME write succeeding
   means this session is not sandboxed. Do not declare setup verified otherwise.

Exit codes: **1** usage/setup/no projects; **2** DB missing/denied/unreadable;
**3** schema mismatch (use `python3 <script> guide`, never guess the schema);
**4** digest mismatch (replan/reconfirm); **5** busy/locked after up to 30 s
(retry later, never delete WAL/SHM). Guide also maps paths to Settings labels.

## Discovery, instructions and probes

**Plan runs one login shell** (`zsh`/`bash`/`fish`) with a stripped environment,
**10 s timeout**, and caches its session PATH and ZDOTDIR for all projects.
This executes login configuration, not project tools. Unknown/failed shells
mean unknown PATH, no node/pnpm guidance. ZDOTDIR learned from `.zshenv` is
respected; relative/invalid values refuse profile writes.
Repository toolchain/config files must be regular, non-symlink files ≤64 KiB.
Installed JDKs are validated without executing Java.

The app captures its shell environment at **app startup**. A Java pin alone
does not activate mise; `/usr/bin/java` cannot discover JDKs via Spotlight in
the sandbox. Plan manages only a marked **per-project** instructions block,
recommending `mise exec -- …` or command-local `JAVA_HOME`. This guides agents,
not enforcement of every command. Working node/pnpm are left alone.
Malformed instruction markers leave instructions untouched but do **not**
skip sandbox policy updates. Global `settings.instructions` is never changed.

`--no-instructions` leaves instructions untouched, including rollback.
Top-level `instructions` in `.github/github-app.yml` may overlay DB text
(precedence unverified): the script leaves DB instructions alone, reports
trusted-config state and prints a block to add manually; it never edits that file.
Unpinned Gradle projects get a warning, not default Java or an instructions block.

Verify uses the current session, never a login shell. Managed Java/Gradle
commands gate; their bare Java probe is informational. Without managed Java,
bare Java gates; a missing matching JDK also gates. Node gates only with a
node pin, `.nvmrc`/`.node-version`, or `engines.node`; otherwise it is information.
pnpm is probed only for a pnpm pin, `packageManager: pnpm@…`, or `pnpm-lock.yaml`.
Results distinguish `ok`, `environment`, `seatbelt` and `not-installed`.
Mise auto-install, Corepack network/download prompts, pnpm version management
and Gradle JDK auto-download are disabled for probes. **Verify runs
`./gradlew --version`, which may download the wrapper distribution** if absent.
Behavioral probes use cleaned-up temporary files; DB open reads no content.
Proxy/GH_TOKEN output is yes/no only, never values or session-state policy files.

## Optional: shell profile

For bare commands, separately review `profile plan`, then confirm
`profile apply --confirm <digest>` with identical options. Never part of default
apply. `--tool java|node|pnpm` limits selection to failing tools. The block uses
guarded static mise shims, not prompt hooks. Without mise, Java needs explicit
`--java-home PATH` or `auto` (validated JDK; conflicting project majors refused).
**Never overwrites existing `JAVA_HOME`** or picks generic default Java.

`$SHELL` (`--shell` overrides) selects captured `$ZDOTDIR/.zprofile`/`~/.zprofile`,
bash's first existing `.bash_profile`/`.bash_login`/`.profile` (else creates
`.bash_profile`), or fish's `~/.config/fish/conf.d/app-sandbox-setup.fish`.
Never writes `.zshenv`; other shells get instructions only. Malformed markers
and symlinks refuse writes. Existing files get 0600 backups and atomic,
mode-preserving replacement. Before the block, one confirmed apply commits
readonly shims, login file and mise's binary directory under HOME in all policies;
**it changes no sandbox toggles or other policy fields**. File failure leaves
DB hardening committed; inspect the reported phase and a fresh plan.
Install tools and run `mise reshim` **outside the sandbox**.
`profile remove` previews; `remove --confirm <digest>` removes only our block.
Normal plans check **all supported profile candidates**, retaining readonly while
any block is active; rerun plan/apply in the same toolchain environment after removal.
**Quit and restart the app completely, not just `/restart-session`.**

## Optional: Gradle toolchain paths

Review `gradle-toolchains plan`; separately confirm `apply --confirm <digest>`.
Matching instructions launcher/toolchain majors need **no repair**: Gradle
detects its current JVM/`JAVA_HOME`, including mise-launched Java. No Java
decision means no proven missing discovery, no repair. Only differing majors
can require a validated matching JDK outside asdf/SDKMAN! and existing paths.
Prefer mise, user Library, system Library, then highest version within each root.
Location alone does not prove a missing toolchain. Plan explains every project.

Merges JDK **homes** into `$GRADLE_USER_HOME/gradle.properties` (default
`~/.gradle/gradle.properties`), preserving other lines/comments, with backup
and atomic replacement. `remove` previews; `remove --confirm <digest>` removes
only tracked paths and an empty key only if the script created it.
**This does NOT give the wrapper a java to start with**; instructions handle that.

## Risks to explain before confirmation

- Masking covers **only app-injected** GH_TOKEN/git helper, not credentials in
  `.npmrc`, `gradle.properties`, `hosts.yml`, etc. OFF allows exfiltration by
  builds/dependencies. ON forces loopback deny even with Local network enabled,
  breaking Gradle daemon, Testcontainers, dev servers and Playwright.
- Docker socket is **effectively unsandboxed host access**. `--no-docker`
  omits Docker grants/hardening and removes exact matching rw grants;
  Docker/Testcontainers stop working. Broader user grants remain.
- Narrower readonly/deny wins over broader rw **once paths exist**. Missing
  readonly paths are not pre-created and their creation cannot be blocked.
  Writable code, git hooks and tool installs can persist later execution.
  mise `installs/` stays writable; agent-edited repo `.mise.toml` may affect
  tools outside the sandbox through shims (trust prompts; not verified).
  These are guardrails, **not containment**.
- Denies qualify by type or missing directories under writable parents.
  Only empty placeholders outside writable parents are removed. The backup
  directory is always denied; WAL/SHM are app-owned, never deleted.
  Rerun after adding projects/tools, app updates and creating credential folders.
- A sandboxed Gradle client may reuse an **unsandboxed daemon**. Passing builds
  alone do not prove enforcement. Enterprise settings can also alter results.
- SSH/signing (`.ssh`/`.gnupg`), nais/kubectl/gcloud, private Docker pulls via
  keychain and Chromium/Playwright macOS IPC are deliberately blocked.
  Use explicit **Run once** outside for those operations; no blanket grants.
  `gh auth status` may fail cosmetically while app-injected GH_TOKEN works.
  Global `~/Library/pnpm` installs/links may fail despite rw; project installs work.
- “Permission could not be granted automatically” is app **path approval**,
  not a sandbox probe. #83 tightenings (config allowlist, strict roots,
  credential scanning) remain deferred.

## Change later

- Rerun plan/apply to change masking or use Settings → Projects → Sandbox.
  Default apply re-enables valid projects; profile apply preserves their toggle.
- `rollback --from <backup>` previews; confirm with the same command plus
  `--confirm <digest>`. It restores shared project policies/toggles and **only
  our instructions block**, preserving current user text. Malformed current/
  backup markers skip that rollback project with a warning. Never replace DB.
  A fresh backup makes rollback reversible; repeat the new-session verify gate.
- Apply/rollback retain ten matching DB backups in the denied 0700
  `~/.copilot/app-sandbox-setup-backups` directory (files 0600).
  `--move-backups` confirms loose-copy moves into it after commit; no symlink
  moves, overwrite or deletion. Failures warn without undoing DB changes.

`next dev` rewrites `AGENTS.md` on start; revert that incidental change after dev-server checks.
