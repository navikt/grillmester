# Toolchains, verify probes and optional add-ons

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
An unreadable toolchain file gets its own warning and leaves that project's
instructions untouched, since its pins are unknown; an unreadable Java source
also replaces the missing-pin warning.

Verify uses the current session, never a login shell. Managed Java/Gradle
commands gate; their bare Java probe is informational. Without managed Java,
bare Java gates; a missing matching JDK also gates. Node gates only with a
node pin, `.nvmrc`/`.node-version`, or `engines.node`; otherwise it is information.
pnpm is probed only for a pnpm pin, `packageManager: pnpm@…`, or `pnpm-lock.yaml`.
Results distinguish `ok`, `environment`, `seatbelt` and `not-installed`.
Mise auto-install, Corepack network/download prompts, pnpm version management
and Gradle JDK auto-download are disabled for probes. **Verify runs
`./gradlew --version`, which may download the wrapper distribution** if absent.
`--no-toolchain` skips these project probes and keeps the behavioral probes.
Behavioral probes use cleaned-up temporary files; DB open reads no content.
Proxy/GH_TOKEN output is yes/no plus a shape class (`GitHub token shape`,
`other (placeholder?)`, `absent`), never values or session-state policy files.
The follow-up lines are heuristics from live observation, not documented app
behavior: a GitHub-shaped token without a loopback proxy (127.0.0.1,
`localhost`, `::1`) likely means a real token is readable; a placeholder could
share that shape, and a local corporate proxy (for example Zscaler or Cntlm)
looks like the app's proxy. Unsandboxed sessions get none of these hints. Masking hints appear when loopback is denied behind a loopback
proxy without `--mask-credentials`, or works although the flag was given.

`next dev` rewrites `AGENTS.md` on start; revert that incidental change after
dev-server checks.

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
