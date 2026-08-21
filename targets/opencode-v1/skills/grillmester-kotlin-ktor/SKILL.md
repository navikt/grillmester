---
name: grillmester-kotlin-ktor
description: "Implement or review Kotlin and Ktor backend work in Nav. Use for routes, plugins, startup, modules, dependency injection, configuration, structured logging and MDC, outgoing HttpClient, graceful shutdown, or Ktor integration with authentication, Kafka, and Postgres."
---
# Work in a Kotlin and Ktor backend

> **OpenCode v1:** Backticked `grillmester-*` names below are skill IDs, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

## Build a repository map first

Before proposing code, inspect the build files and version catalogs, runtime and
Java versions, Ktor engine and startup entry point, application configuration,
module registration, package layout, dependency injection, installed plugins,
routes, resource cleanup, logging configuration, tests, and quality gates.

Search by symbols and dependencies rather than assuming paths. Establish
whether startup uses `EngineMain`, `embeddedServer`, test-only modules, or a
custom bootstrap; whether configuration is HOCON, YAML, environment-backed, or
typed code; and which DI approach is already used. Treat recognized consumer
instructions as declared context and rationale, then verify effective or
volatile runtime facts against code, build files, manifests, tests and current
primary documentation. Stop and surface conflicts. If the repository is not Ktor,
stop applying Ktor patterns and follow its actual framework.

## Preserve startup reachability

Trace production, local, and test startup separately. A component added only to
a production configuration file may be absent from `testApplication` or a
custom test bootstrap. A direct module call may bypass a configured module list.

Add plugins, routes, migrations, consumers, workers, and resource owners through
the shared bootstrap seam that every required startup mode reaches. Keep one
clear composition root unless the repository deliberately supports several.
Do not add a second engine, module entry, or `main` path without proving why it
is needed and how ports and shutdown interact.

## Follow dependency and version conventions

Confirm that a plugin's artifact is present before calling it. Ktor
`Authentication`, `ContentNegotiation`, client serialization, timeouts, retry,
metrics, and DI are separate dependencies. Add a dependency through the
repository's established catalog or build convention and keep Ktor artifacts
on the version already selected by the build.

Do not infer a Ktor or Java version from this skill, add a second version source,
or introduce Spring annotations and response types into a Ktor application.

## Extend the existing module and DI design

Read registrations and ownership before adding a collaborator. Reuse Ktor DI,
Koin, manual constructors, or the framework already present. Do not introduce a
new container merely for one dependency.

Any registration that owns a data source, HTTP client, Kafka client, executor,
or coroutine scope must close it through the existing lifecycle. Ensure tests
can replace external ports through the current override mechanism and that
production still detects accidental duplicate bindings.

## Install plugins deliberately

Plugin installation order and scope can affect behavior. Match existing
patterns for:

- call IDs, structured request logging, and MDC propagation;
- content negotiation and serializer settings;
- status-to-error mapping and exception redaction;
- authentication and authorization around route groups;
- metrics, tracing, and health routes.

Do not invent a generic error response if the API already publishes one. Error
status, body, headers, validation rules, and unknown-field behavior are contract
surface. Keep internal probes outside user auth only when the deployed probe and
access design requires it.

For a new or changed Ktor error boundary, load
[references/error-handling.md](references/error-handling.md). For list routes,
query parsing, and request validation, load
[references/pagination-validation.md](references/pagination-validation.md).

## Keep identity and logs safe

Use the repository's call-ID header and MDC keys. Propagate an existing
correlation or event ID instead of minting unrelated IDs at every boundary.
Structured fields should carry operational identifiers, not national identity
numbers, tokens, raw payloads, or special categories of personal data.

Serialization and parsing exceptions can include the offending body. Sanitize
or replace exception causes before logging or returning an error when the body
may contain personal data. Never expose a token or downstream response body in
an exception message.

Authentication mechanism, claims, and token exchange must follow the bundled
`grillmester-auth-overview` workflow and the repository's existing integration. Ktor wiring
does not by itself decide who may call an operation.

## Treat outgoing HTTP as a boundary

Inspect the shared or per-downstream `HttpClient`, engine, installed plugins,
serializer, token provider, timeout and retry policy, `expectSuccess` behavior,
status mapping, and cleanup before changing it. A plugin added to a shared
client changes every downstream, possibly including token acquisition.

Keep `HttpResponse` inside the infrastructure client. Map downstream statuses
and bodies to domain results or typed failures at that boundary. Load the
detailed patterns in [references/http-client.md](references/http-client.md)
when changing an outgoing client.

## Integrate persistence and Kafka through owned lifecycles

- Run migrations through the startup path and transaction policy already used
  by the service. Do not edit an applied migration.
- Read database connection material through the repository's configuration
  layer and keep credentials out of logs and object string representations.
- Run Kafka polling outside request handlers. Preserve the repository's commit,
  idempotency, parking, health, and close semantics.
- Keep storage and event-contract decisions separate from Ktor wiring and
  record hard-to-reverse decisions through the repository's ADR process after
  user approval.

## Shut down through the framework lifecycle

Use the engine and DI cleanup hooks already present. On termination, stop new
work, wake blocking consumers, drain or cancel owned work within the platform
grace period, and close resources exactly once. Do not add manual readiness
toggles or duplicate JVM shutdown hooks without repository evidence that the
current lifecycle is insufficient.

## Verify every startup mode touched

Discover and run the repository's own formatter, static checks, unit tests,
Ktor `testApplication` tests, integration tests, and build gates in proportion
to the change. For bootstrap changes, test production-like startup and cleanup,
not only an isolated function. Report exact commands, exit codes, and any gate
that could not run.

## Boundaries

### Ask first

- Add an engine, DI framework, public error contract, shared-client retry policy,
  or new startup path.
- Change authentication, database migration timing, Kafka delivery semantics,
  or graceful-shutdown guarantees.

### Never

- Assume package names, source paths, versions, config formats, or dependencies.
- Add framework APIs whose artifacts are absent.
- Leak personal data, tokens, or raw bodies through logs or exception causes.
- Start blocking work in an HTTP handler or leave owned resources unclosed.
