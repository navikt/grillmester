# Ktor pitfalls

A few pitfalls in Ktor services. Follow the repository's own patterns for the
rest. If the repository is not Ktor, stop applying this reference and follow its
actual framework.

- **Startup modes differ.** Trace production, local and test startup separately.
  A component added only to a production configuration file may be absent from
  `testApplication` or a custom test bootstrap, and a direct module call may
  bypass a configured module list. Add plugins, routes, migrations, consumers,
  workers and resource owners through the shared bootstrap seam that every
  required startup mode reaches.
- **Plugins are separate artifacts.** Ktor `Authentication`,
  `ContentNegotiation`, client serialization, timeouts, retry, metrics and DI are
  separate dependencies. Confirm that a plugin's artifact is present before
  calling it.
- **A shared `HttpClient` reaches every downstream.** A plugin added to a shared
  client changes every downstream, possibly including token acquisition. Avoid
  adding a shared-client retry or breaker that also changes token acquisition,
  and ensure Ktor's retry behavior does not duplicate a retry already owned by a
  higher layer.
- **Parsing exceptions can carry the body.** Serialization and parsing
  exceptions can include the offending body. Sanitize or replace exception causes
  before logging or returning an error when the body may contain personal data.
- **`StatusPages` can hide framework failures.** Confirm how Ktor auth, content
  negotiation, request parsing and unsupported methods are handled. Do not
  convert every exception into 500 or override authentication challenge headers
  accidentally.
- **Blocking work stays out of handlers.** Run Kafka polling outside request
  handlers. Shutdown follows [the pod lifecycle](nais.md#pod-lifecycle).

## Ask first

- Adding an engine, DI framework, public error contract, shared-client retry
  policy or new startup path.
- Changing authentication, database migration timing, Kafka delivery semantics or
  graceful-shutdown guarantees.
