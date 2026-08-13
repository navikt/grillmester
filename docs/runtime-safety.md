# Runtime safety for Grillmester

Grillmester's agent profiles decide which tools are visible to each agent, but
they do not grant permission, enforce a filesystem boundary, or replace the
client's sandbox. Public engineering agents intentionally need a broad runtime
surface. NAV-wide use therefore requires a sandboxed session **and** active
permission prompts; installing the plugin alone does not satisfy this gate.

This policy is based on GitHub's current Copilot CLI and Copilot app
documentation. Local and cloud sandboxes are in public preview, so the controls
must be reverified before every stable promotion.

## Required controls

For every session that can execute, edit, or call an external tool:

1. Run in a dedicated worktree, disposable fixture, or cloud sandbox. Only the
   task repository and required temporary paths may be writable.
2. Keep tool approvals active. Do not start or switch the session to
   `--allow-all`, `--allow-all-tools`, `/allow-all`, or `/yolo`.
3. Do not persist a broad approval for shell, writes, URLs, or an MCP server.
   Approve the smallest concrete action and target needed for the task.
4. Require an explicit human preview and approval before Git, GitHub, Figma,
   deployment, messaging, or other external writes. Sandbox isolation does not
   make those side effects harmless.
5. Never use production data, secrets, or personal data as pilot fixtures.
6. Record the effective sandbox policy, client version, granted approvals, and
   observed side effects as release evidence.

For managed NAV rollout, the device or account policy must also prevent users
and automations from enabling the allow-all/bypass mode. GitHub documents
`permissions.disableBypassPermissionsMode` for suppressing the allow-all flags.
Where local sandboxing is used, set `sandbox.allowBypass` to `false` so a tool
cannot ask to run one command outside the sandbox. Repository content cannot
enforce either setting; the managed-policy owner must verify the effective
configuration.

Enable `sandboxMcpServers` and `sandboxLspServers` when local stdio MCP/LSP
processes must inherit the OS sandbox. Remote HTTP/SSE MCP servers are never
inside that sandbox. For those calls—including remote Figma, Aksel or GitHub
servers—approval policy, OAuth scopes, data minimization and the server's own
authorization are the actual side-effect boundary.

## Copilot CLI

Command sandboxing is currently experimental. Prefer starting the session with
both switches so the gate is active before the agent is selected:

```bash
copilot --experimental --sandbox --agent=grillmester:grillmester
```

For an already running interactive session, enable experimental commands first,
then enable and inspect the OS-level sandbox:

```text
/settings experimental on
/sandbox enable
/sandbox
```

The status line must show that sandboxing is enabled. Run `/sandbox` without an
argument to open the policy view, and verify that its filesystem and network
boundary matches the intended profile.

The default local policy is not a NAV least-privilege profile: the working
directory and temporary folders are writable, outbound and local network
access can be available, and authenticated `git` and `gh` can keep working
because credentials can be injected by default. For read-only or fixture-only
scenarios, disable Git and `gh` credential injection in the `/sandbox` policy
UI. Declarative key names have changed between documented/installed preview
versions (`sandbox.gitAuth`/`sandbox.ghAuth` versus
`sandbox.auth.git`/`sandbox.auth.gh`), so use the keys shown by the exact tested
CLI and record the resolved policy rather than copying one shape blindly.
Enable credentials only for the separately approved external-write scenario. Do not rely on
per-host allow/block rules for security; GitHub documents cross-platform
limitations for those rules.

Sandboxing and tool permissions are complementary. Every MCP invocation still
requires explicit permission in Copilot CLI, including read-only calls to an
external service. Never persist an approval for an entire write-capable MCP
server during the pilot.

CLI permissions remain a separate layer. Deny rules take precedence over
saved approvals and allow-all. Use session-scoped `--deny-tool` or managed
policy for capabilities the scenario must never exercise, and run
`/reset-allowed-tools` before a new scenario if the session has accumulated
approvals.

## Copilot app

The app is built on Copilot CLI, but a Git worktree is not by itself an
OS-level sandbox. For the mandatory sandbox gate, select a **cloud sandbox**
when starting the app session and record that choice. GitHub documents cloud
sandbox as an explicit app session location; it does not document an ordinary
local-repository or worktree session as equivalent isolation.

Test Interactive/Plan approval behavior separately from Autopilot. A cloud
sandbox protects the local machine, but does not remove the need to preview and
approve GitHub, Figma, or other external writes.

## What this does not prove

- An agent prompt is a behavioral contract, not a permission boundary.
- An omitted `tools` field means all tools available in that runtime; it does
  not mean all actions run without approval.
- A sandbox does not prove that an MCP or remote API write is safe or intended.
- A repository setting does not prove that NAV's managed sandbox and permission
  policy is active on the user's device or account.
- A green CLI run does not prove the app or cloud-agent profile; capture each
  client independently.

## Primary sources

- [GitHub Copilot CLI command reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference)
- [Using local sandboxing](https://docs.github.com/en/copilot/how-tos/cloud-and-local-sandboxes/using-local-sandboxing)
- [Configuring local sandbox settings](https://docs.github.com/en/copilot/how-tos/cloud-and-local-sandboxes/configuring-local-sandbox-settings)
- [Allowing and denying tool use](https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/allowing-tools)
- [Working with agent sessions in the GitHub Copilot app](https://docs.github.com/en/copilot/how-tos/github-copilot-app/agent-sessions)
- [Custom-agent tools semantics](https://docs.github.com/en/copilot/reference/custom-agents-configuration)
