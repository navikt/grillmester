---
name: app-sandbox-setup
description: "Configure the GitHub Copilot desktop app's local sandbox on macOS with a reviewed plan, confirmed settings update, or manual click guide."
disable-model-invocation: true
---

# App sandbox setup

Use `/app-sandbox-setup` explicitly for the **GitHub Copilot desktop app on
macOS**, not CLI sandbox configuration. The app stores a policy **per project**
in `~/.copilot/data.db`; there is no repository-owned sandbox config file.
Use the bundled [script](scripts/app_sandbox_setup.py), not ad hoc DB updates.
The [settings documentation](https://docs.github.com/copilot/how-tos/cloud-and-local-sandboxes/configuring-local-sandbox-settings)
and [session documentation](https://docs.github.com/copilot/how-tos/cloud-and-local-sandboxes/using-local-sandboxing)
describe app controls (verified 2026-10-08); enterprise managed settings may
override them. Stock `/usr/bin/python3` may prompt to install Xcode Command
Line Tools; use an already installed Python 3.9+ if available. Stock git
discovery is skipped when those tools are absent.

## Plan → confirm → apply → verify

1. **Run plan first:** resolve the script beside this skill and run
   `python3 <script> plan`. Do not require Settings changes or a restart first.
   If exit 2 reports access **denied**, ask the user to approve **that single
   command** outside the sandbox when the runtime offers
   **Run outside the sandbox? → Run once**. Do not silently bypass a denial or
   choose **Disable sandbox and run** for them. Fallback: the user can use
   `/sandbox off` in this session, or run the command in a normal terminal.
   Missing DB means the app was never started or `--db` is wrong.
2. Present the per-project diff, **all warnings**, and `Plan digest`. Explain
   the risk choices below. New policies default to masking **OFF**; reruns
   preserve both existing credential toggles unless `--mask-credentials` or
   `--no-mask-credentials` is selected. Offer `--no-docker` to omit Docker
   grants and remove exact matching existing rw grants. Recompute plan after
   changing options. Corrupt policies are skipped individually; report them,
   never call a partial update complete.
   Plan displays only changed projects and counts unchanged projects. Apply
   reports a summary instead of repeating the diff.
3. Obtain explicit confirmation **in the conversation** for the displayed
   plan, credential and Docker choices. Run
   `python3 <script> apply --confirm <digest>` with the same options.
   If denied, request **Run once** again for this apply command only, after
   confirmation. Apply validates the schema and fresh digest under
   `BEGIN IMMEDIATE`, merges policies, enables sandbox for all valid projects
   and takes a protected SQLite backup before writing. Failed writes roll
   back and delete the fresh backup. After commit, apply removes only the
   plan's still-empty, non-symlink placeholder directories with `rmdir`;
   failures warn without undoing the policy.
   - Exit 1: usage/setup problem, or no projects (add one in the app first).
   - Exit 2: DB missing/denied/unreadable; follow the specific diagnostic.
   - Exit 3: schema mismatch; show `python3 <script> guide` with the same
     options rather than guessing the schema. Also offer guide on request.
   - Exit 4: digest mismatch; present a fresh plan and reconfirm.
   - Exit 5: DB busy/locked after up to 30 seconds; retry after the competing
     operation ends, never delete WAL/SHM files.
4. Policy changes apply to **NEW sessions or after `/restart-session`**.
   Restart or close sessions that were already open: they keep the old policy
   and can recreate empty placeholder directories that apply just removed.
   `/sandbox off` and `/sandbox on` toggle the **current session immediately**;
   the choice persists for that session **including after restart**, taking
   precedence over the project default. If the user used `/sandbox off`, they
   need `/sandbox on` **plus** `/restart-session`, or a new session.
5. **Closing gate, in a NEW sandboxed session:** run
   `python3 <script> verify` directly **from the project directory**, or
   `verify --mask-credentials` for masking ON.
   After apply, offer to create that session if the client supports it and
   have it run the script and report back. Put the actual Python command in
   its kickoff prompt: a slash command there is plain text, not an invocation.
   Select the actual credential expectation; mixed project toggles may
   require checking both controls. Do not run verify outside the sandbox.
   Verify checks HOME/DB denials, loopback, cache writes and readonly
   hardening using temporary files cleaned up afterwards; it opens the DB
   without reading any content, and never reads session-state policy files.
   Proxy/GH_TOKEN reporting is yes/no only. Exit 0 means all behavioral probes
   match and all gating project probes are `ok`; exit 7 means mismatch
   (including unavailable gating probes). If HOME write
   succeeds, this session is not sandboxed: use a new session or `/sandbox on`.
   Explain that enterprise managed settings can cause differences. Do not
   declare verified setup until this gate matches.

## Toolchain guidance and backup moves

The app captures the login shell environment at app startup. A Java pin
alone does not activate mise; the macOS `/usr/bin/java` stub cannot discover a
JDK inside the sandbox. Plan reads pins and validates installed JDKs without
executing tools. It manages a marked English block in **per-project**
`projects.instructions`, preserving all text outside its markers. Never touch
global `settings.instructions`. Malformed/duplicate markers skip the project.
The block recommends `mise exec -- …` or a matching command-local `JAVA_HOME`;
it steers agents, but **does not enforce the right version in every command**.
Existing node/pnpm on the captured session PATH are left alone; failed shell
discovery means unknown, no guidance. Install missing tools outside the sandbox.

`--no-instructions` leaves instructions untouched (including rollback).
When `.github/github-app.yml` has top-level `instructions`, DB instructions
are left untouched: precedence is unverified. Plan reports the trusted-config
state and prints a block to add to that file manually; it never edits the file.
`--move-backups` includes loose DB-copy moves in the confirmed digest, then
moves them after commit into the denied 0700 backup directory. It refuses
symlinks/non-regular files and existing destinations, suffixes name collisions,
and never deletes those copies. Move failures warn without undoing the DB commit.

Project verify probes report expected/actual versions and `ok`, `environment`
(missing tool, Java stub, wrong version or timeout), `seatbelt` (EPERM),
or `not-installed` (mise/missing JDK). Results show `gate` or `info`; managed
Java and Gradle commands gate when recommended, as do managed node/pnpm for
mise decisions, while their bare probes are informational.
Bare `java` failing is expected when the block instructs `mise exec`/`JAVA_HOME`.
Without a managed command, bare probes still gate, and a missing JDK gates as
`not-installed`; informational results never affect the exit code.
Probes disable mise auto-install and Gradle JDK auto-download.
“Permission could not be granted automatically” is the app's own **path
approval**, not the sandbox; the script cannot observe it.
The #83 tightenings (~/.config allowlist, strict code roots and credential
scanning) are deferred, not part of this change.

## Optional: shell profile

For bare commands, separately review `python3 <script> profile plan` and confirm
`profile apply --confirm <digest>` with the same options. This is **never**
part of default plan/apply. `--tool java`, `--tool node` and `--tool pnpm` limit
selection: only failing tools are added; working nvm node/pnpm are not moved.
The marked block uses static, guarded mise shims, not prompt hooks. Without
mise, Java requires explicit `--java-home <absolute JDK home>` or
`--java-home auto`; auto needs compatible project pins and a validated JDK.
It never overwrites an existing `JAVA_HOME` or chooses a generic default Java.

Uses `$SHELL` (`--shell` overrides it), zsh's `$ZDOTDIR/.zprofile` or
`~/.zprofile`, bash's first existing `.bash_profile`/`.bash_login`/`.profile`
(creates `.bash_profile` if none), or fish's
`~/.config/fish/conf.d/app-sandbox-setup.fish`. Never writes `.zshenv`.
Other shells get instructions only. Malformed markers and symlinks are refused;
existing files get protected backups and atomic, mode-preserving updates.
One digest binds policy and profile changes: **first commit readonly shims,
the login file and the mise binary directory under HOME in every project's
sandbox policy, then
write the profile**. A file failure leaves the DB hardening committed; inspect
the reported partial result and a fresh plan. Install tools and run
`mise reshim` **outside the sandbox**. `profile remove` previews removal;
`profile remove --confirm <digest>` removes only our block. Rerun normal
plan/apply in the same shell/toolchain environment to drop its conditional rule.

**Quit and restart the GitHub Copilot app completely (not just
`/restart-session`): the app captures the shell environment at startup.**

## Optional: Gradle toolchain paths

Use `gradle-toolchains plan`, then separately confirm
`gradle-toolchains apply --confirm <digest>` when a Gradle toolchain pin has
a validated matching JDK that Gradle cannot discover in the sandbox. Reuse the
per-project instructions decision: `mise exec` launches the project's pinned
Java; a command-local `JAVA_HOME` launches that validated JDK. If its major
matches the requested toolchain, Gradle detects the launching JVM and needs
**no repair**, including mise installs. Without a Java instruction decision,
missing discovery is not proven, so no automatic repair is offered.
Only differing majors can need a path: the requested JDK must exist outside
asdf/SDKMAN! and not already be configured. Prefer mise installs, then user
Library, then system Library, with the highest version in that major within
each root. Plan explains each project's result. Gradle 9.8.0 has no mise
supplier, and sandboxed macOS `java_home` cannot discover standard locations;
those location facts alone do **not** prove a repair is needed.
The command merges JDK **homes**, not parent installation directories, into
`~/.gradle/gradle.properties`, preserves other properties/comments, and tracks
only paths it adds. It backs up and writes atomically; `gradle-toolchains remove`
previews and `remove --confirm <digest>` removes only tracked paths.
**This does NOT give the wrapper a java to start with**; per-project instructions
handle that. A Gradle project without a Java pin gets a warning, never an
automatic `JAVA_HOME` or instructions block.

When checking frontend dev servers, note that `next dev` rewrites `AGENTS.md`
on start (Next.js agent rules); revert that incidental change after the check.

## Choices and limits to explain before confirmation

- Masking covers **only app-injected** GH_TOKEN / git credential helper, not
  credentials on disk in `.npmrc`, `gradle.properties`, `hosts.yml`, etc.
  With masking OFF, build scripts/dependencies can see real injected
  credentials and exfiltrate them through allowed outbound. Masking ON uses
  a proxy that forces loopback deny even with Local network enabled, breaking
  Gradle daemon, Testcontainers, dev servers and Playwright.
- Docker socket access is **effectively unsandboxed host access**: a process
  can mount HOME, read `.ssh` or write LaunchAgents despite the deny list.
  `--no-docker` omits Docker grants, including readonly `.docker/cli-plugins`
  and `.docker/config.json`, and removes our exact existing Docker rw grants.
  Docker/Testcontainers will not work; unrelated broader user grants remain.
- Readonly hardening covers app-owned cache directories, git/shell/tool
  configuration and Gradle init files. Narrower readonly/deny wins over a
  broader rw grant **once the path exists**. Missing hardening paths remain
  listed as readonly without pre-creation, but the app cannot block their
  creation. This is accepted residual risk alongside git hooks in writable
  code, writable tool installs and the Docker socket. Code and tool installs
  can persist changes that execute outside the sandbox later.
  These are guardrails, **not containment**.
- Deny paths are listed only with their expected existing type, or for
  missing directories under writable folders: the app creates empty
  placeholder directories for missing deny paths. Plan lists empty
  placeholders at file paths (e.g. `~/.netrc`) and directly under HOME or
  `~/.copilot` for removal; placeholders under writable parents stay denied.
  The backup directory is always denied and never removed. `data.db-wal`
  and `data.db-shm` are no longer denied: `~/.copilot` is already unreadable,
  and deny placeholders could break the app's SQLite WAL.
  Policies are merged: user entries kept, except entries identical to our deny
  paths that no longer qualify.
- A sandboxed Gradle client can reuse an **unsandboxed daemon** started by
  IntelliJ/a terminal, running the build outside the sandbox. Successful
  builds alone do not prove sandbox enforcement.
- Deliberately blocked: nais/kubectl/gcloud (including `nav-troubleshoot`'s
  kubectl steps), SSH remotes and commit signing (`.ssh`/`.gnupg` denied),
  and private `docker pull` via osxkeychain (pull outside the sandbox).
  `gh auth status` may exit 1 because keychain access is blocked; this is
  cosmetic when GH_TOKEN works. GitHub MCP, gh and HTTPS git use the app's
  credential flow, not a blanket grant to credential stores.
- Inside the sandbox, `/usr/bin/java` / `java_home` cannot discover JDKs
  (Spotlight lookup unavailable). Use the project's managed command guidance;
  do not change shell profiles or install tools inside the sandbox.
- The app protects `~/Library/pnpm` (`PNPM_HOME`) despite its rw grant:
  global pnpm installs/links fail in the sandbox; project installs work.
- Playwright/Chromium cannot run inside the app sandbox: it denies required macOS IPC (Mach bootstrap/crashpad handshake
  and sandbox extensions); no path grant helps. Run browser tests/Playwright MCP outside the sandbox:
  approve **Run outside the sandbox → Run once** for that command, or use a session with `/sandbox off`.
- Processes from earlier shell calls cannot be inspected or signalled in the
  sandbox; stop background servers in the same call or by port.

Tool discovery supports different JDK/tool installations without requiring
mise. Missing tool grants are skipped. Missing code paths are skipped except
under `/Volumes` (possibly unmounted). New projects start with sandbox off.
Rerun after adding projects, installing tools **and app updates**, which create
new version-named cache directories, and after first creating or logging in to
credential folders such as ~/.aws, ~/.ssh, ~/.gnupg, ~/.kube, ~/.azure, ~/.netrc
or MCP OAuth; until then they are not denied, but they are only readable if you
added a broader grant. Reruns are idempotent and remove the old
`~/.copilot/session-state` rw grant; the app supplies its own session access.
`--home PATH` and `--db PATH` support isolated fixtures.

## Change later

- Turn masking ON by rerunning plan/apply with `--mask-credentials`, or use
  **Settings → Projects → <project> → Sandbox → Git credentials / GitHub CLI
  credentials**. `--no-mask-credentials` turns both OFF explicitly.
- Turn one project off manually with **Sandbox new sessions**. Rerunning
  this skill enables it again. Other labels are **Additional read/write**
  (Add folder), **Additional read-only**, **Denied**, **Outbound internet**
  and **Local network**; `guide` maps diagnostic fields to these labels.
- Roll back: `python3 <script> rollback --from <backup>` previews the
  current→backup diff and digest. Get conversational confirmation, then run
  the same command with `--confirm <digest>` (request Run once if denied).
  It restores sandbox_enabled, differing policy rows and project instructions for projects
  present in both DBs, leaving other projects and app state untouched.
  Preview omits unchanged projects and counts them; rollback never recreates
  removed placeholder directories.
  A fresh backup makes rollback itself reversible; never replace data.db.
  Successful apply/rollback keeps the newest **10** matching backups in
  `~/.copilot/app-sandbox-setup-backups` with 0700/0600 permissions.
  Repeat the new-session verify gate after any change.
