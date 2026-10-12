# Risks to explain before confirmation

Explain these in plain words. The sandbox is guardrails, **not containment**.

## Credential masking

- Masking covers **only app-injected** GH_TOKEN/git helper, not credentials in
  `.npmrc`, `gradle.properties`, `hosts.yml`, etc. Those files stay readable
  either way; suggest a separate token with only `read:packages` for package
  registries instead of a broad personal token.
- OFF allows exfiltration by builds/dependencies with outbound allowed.
  ADR 0014 assumes sandboxed processes then see the real app-injected
  GH_TOKEN/git credentials; GitHub's documentation only says turning
  credentials off can block pushes. In a sandboxed session, verify's
  `GH_TOKEN format` and proxy lines show which case applies.
- ON forces loopback deny even with Local network enabled, breaking Gradle
  daemon, Testcontainers, dev servers and Playwright.
- New policies default to masking OFF; reruns preserve both toggles unless a
  masking flag is selected.

## Docker

- The Docker socket is **effectively unsandboxed host access**: it can mount
  HOME, read `~/.ssh` and write LaunchAgents.
- `--no-docker` omits Docker grants/hardening and removes exact matching rw
  grants; Docker/Testcontainers stop working. Broader user grants remain.

## Paths and persistence

- Narrower readonly/deny wins over broader rw **once paths exist**. Missing
  readonly paths are not pre-created and their creation cannot be blocked.
- Writable code, git hooks and tool installs can persist later execution.
  mise `installs/` stays writable; agent-edited repo `.mise.toml` may affect
  tools outside the sandbox through shims (trust prompts; not verified).
- Denies qualify by type or missing directories under writable parents.
  Only empty placeholders outside writable parents are removed. The backup
  directory is always denied; WAL/SHM are app-owned, never deleted.
- Rerun after adding projects/tools, app updates and creating credential folders.
- A sandboxed Gradle client may reuse an **unsandboxed daemon**. Passing builds
  alone do not prove enforcement. Enterprise settings can also alter results.

## Deliberately blocked

- SSH/signing (`.ssh`/`.gnupg`), nais/kubectl/gcloud, private Docker pulls via
  keychain and Chromium/Playwright macOS IPC are deliberately blocked.
  Use explicit **Run once** outside for those operations; no blanket grants.
- `gh auth status` may fail cosmetically while app-injected GH_TOKEN works.
- Global `~/Library/pnpm` installs/links may fail despite rw; project installs work.
- “Permission could not be granted automatically” is app **path approval**,
  not a sandbox probe.

## Deferred

The #83 tightenings (config allowlist, strict roots, credential scanning)
remain deferred.
