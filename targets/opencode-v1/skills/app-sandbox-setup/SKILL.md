---
name: app-sandbox-setup
description: "Configure the GitHub Copilot desktop app's local sandbox on macOS with a reviewed plan, confirmed settings update, or manual click guide."
---
# App sandbox setup

> **OpenCode v1:** Skill names below are exact IDs from the active catalog, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Use `app-sandbox-setup` explicitly for the **GitHub Copilot desktop app on
macOS**, not CLI sandbox configuration. Settings live in `~/.copilot/data.db`;
there is no per-repository sandbox configuration. See the
[official local sandbox documentation](https://docs.github.com/copilot/how-tos/cloud-and-local-sandboxes/configuring-local-sandbox-settings).

1. The running session must have **sandbox OFF**: Settings → Projects →
   <this project> → Sandbox off, then `/restart-session`. Alternatively run
   the bundled [script](scripts/app_sandbox_setup.py) in a normal terminal.
   If the DB is unreadable (exit 2), explain this precondition; do not bypass
   the sandbox's denial.
2. Resolve the script beside this skill and run
   `python3 <script> plan`. Present the per-project diff, warnings, and
   `Plan digest`. Paths are discovered across all projects and worktrees.
   **Credential masking is off by default:** sandboxed processes see the real
   GH_TOKEN / git credentials; with outbound allowed, any build script or
   dependency could exfiltrate them. Offer `--mask-credentials` instead:
   its credential proxy forces loopback deny even with allowLocalNetwork=true,
   breaking Gradle daemon, Testcontainers, dev servers and Playwright.
   Recompute the plan with that option if chosen.
3. Get explicit confirmation **in the conversation** for the presented plan
   and credential choice. Then run
   `python3 <script> apply --confirm <digest>` with the same options.
   Apply checks the schema and digest inside a write transaction, merges
   rather than overwrites, and saves a protected SQLite backup first.
   Exit 4 means settings changed: present a fresh plan and obtain confirmation
   again. Exit 3 means schema/policy mismatch: show
   `python3 <script> guide` with the chosen masking option instead. Also offer
   the guide whenever the user prefers manual settings.
4. Tell the user to start new sessions or `/restart-session`. **The current
   session stays unsandboxed until restarted.** In a new sandboxed session,
   optional verification with masking off: the newest
   `~/.copilot/session-state/<sid>/policies/*.json` has
   `network.ingress.hostLoopback` = `allow` and no
   `runtimeConfig.networkProxy`. Inspect only those fields, not credentials.

New projects start with sandbox off; rerun after adding projects or installing
tools. Reruns are idempotent. `--home PATH` and `--db PATH` support isolated
fixtures; defaults use the current user's home, never a fixed checkout root.
The sandbox is guardrails, not containment: writable code/config/tool
directories can hold changes that later execute outside the sandbox.

Tip: repository-level instructions, not this plugin, can tell agents to use
`mise exec -- ./gradlew` when there is no system JDK.
