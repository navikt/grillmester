# Open a running application

Use this path when the active client offers the **Designverksted** canvas
(`design-workspace`) and the task needs the actual app. For «show/run the demo»,
read this opening path; load the full workspace reference only for a requested
next action or a concrete problem. Ideas and alternative directions can start
with a sketch instead of an app.

Use the client's actual canvas tool and schemas, in the owning conversation
and project. Do not invent aliases or install an extension. The first native
app flow is inside Copilot on macOS: one visible workshop, no extra browser or
canvas. Never expose or open its private renderer address in an external browser.

Opening message: «Jeg åpner demoen, så du kan prøve dagens løsning.»

## Start the demo

Start the actual app using its repository instructions and established
mock/demo setup with synthetic data. Open the owning workshop early.

Treat the demo as a service, not an indefinitely running tool task that keeps
the conversation's answer open. Start it from the ordinary client shell through
the skill's owned-service helper, using the repo's actual program and arguments:

```text
node <skill-dir>/scripts/app-runtime.js start --project-dir <owned-app-copy> --session <stable-local-key> -- <program> <args...>
node <skill-dir>/scripts/app-runtime.js status --project-dir <owned-app-copy> --session <stable-local-key>
node <skill-dir>/scripts/app-runtime.js stop --project-dir <owned-app-copy> --session <stable-local-key>
```

Pass required non-secret mock/demo flags explicitly as `--env NAME=value`
before `--`, using the repo's exact names and values. An environment prefix on
the helper command is not forwarded to the app; the helper filters inherited
environment. Never pass authentication values or weaken the demo's network guard.
Use the ordinary foreground demo command; do not add daemonization, `setsid` or
another background launcher. Its children must stay in the owned process group.

Use an explicitly owned copy for demo startup; frameworks and package managers
may write generated metadata even when no product edit was requested. Reuse one
local service key for this app and conversation; keep it out of normal replies.
The start command returns a bounded status, not a tool task to poll forever.
If status is `unreachable`, first inspect the existing demo and its ownership;
the helper cannot safely stop or reclaim an unconfirmed controller. Only then
use a new local service key if a separate start is appropriate. A `stopping`
runtime is not a reusable running service. Never delete its state or signal a
stored process ID to force a restart.
Check the observed demo URL separately. A permitted local redirect may normalize
the path or public parameters; follow the observed destination rather than wait
for the original address to return 200. Do not follow a redirect into login or
another unapproved service.

Closing a canvas keeps its demo available within the service lifetime. After
expiry, start it explicitly and reopen saved work in a fresh canvas instance.
An explicit end, stop or cancellation of the demo work calls the helper's
`stop`; it is not a failure to repair or an instruction to restart. Do not invent detached launch
workarounds, use sudo or change sandbox settings. Explain a real startup blocker
briefly and continue independent design work.

## Open the workshop

Open with the exact observed local URL, including its path and public query:

```json
{
  "application": { "name": "Møtedemo", "url": "http://localhost:3000/demo?mode=mock" }
}
```

This starts temporary feedback. To save the feedback when the designer has
requested it, also supply `workspacePath`, `create: true` and `title`, for
example `"workspacePath": "designs/meeting"`. This saves comments and replies,
not app code, versions or browser state. An existing saved room opens with its
exact `workspacePath` and `application`, without `create`. The application name
is descriptive; the saved starting path and declared query policy must match.
The local port can change between sessions. Never reset a room after an opening
error. Older unreleased app rooms with source history are not migrated: preserve
them and report the incompatibility.

The app owns its styles; do not pass `styleProjectPath`. Never include
credentials, private query parameters or production content. Unsupported routes
and connections remain explicit limitations. For a verified synthetic demo
whose public resource IDs use UUID query values, declare only the exact names
in `application.resourceQueryKeys`, for example `["itemId"]`. The bounded policy
permits UUIDs for those names only; authentication/personal-data keys and other
opaque credentials remain forbidden. App content cannot grant an exception.

## Finish a view-only request

For a view-only request, use `read_state` without `proposalId` and finish when
`application.previewStatus.state` is
`ready` and `application.route` matches the requested page, including any
observed permitted redirect. Say the demo is open, not visually verified or
interaction-tested. Do not continue with browser-tool discovery, screenshot
attempts or source reconstruction after this opening check. A successful HTTP
request alone is not the workshop opening check. Diagnose an unavailable view
or wrong route; missing setup or an error page is a concrete blocker, not a
reason to reconstruct the app as static HTML or silently remove its route.

Final reply after that check: «Demoen er åpnet i Appen nå. Du kan prøve den der.»

## Read the next recipe only when needed

- For an actual design review, change or interaction test, follow
  [rendered inspection](design-workspace.md#inspect-the-rendered-sketch).
  Check the relevant rendering and interaction before reporting them verified.
- For an app innspill or proposal request, use
  [app feedback and proposals](design-workspace.md#running-application).
- Before closing, reopening or diagnosing a blocked native view, read
  [native lifecycle](design-workspace.md#initial-native-support). Preserve the
  room on failure; never reset it or start a competing writer as a shortcut.
