---
name: grillmester-kotlin-spring
description: Implement or review Kotlin and Spring backend work in NAV. Use for Spring Boot controllers, services, configuration, dependency injection, authentication and authorization, Actuator probes, Nais runtime integration, structured logging, Testcontainers, MockOAuth2Server, or Spring-specific tests.
license: MIT
---

# Work with Kotlin and Spring in NAV

## Establish the repository contract

Inspect repository instructions, the complete Gradle build and version catalog,
Spring and Kotlin plugin versions, dependency locks, configuration profiles,
application entry points, controllers, security setup, data access, tests, Nais
manifests, and adjacent implementations. Search by symbols and configuration
keys instead of assuming package names or source and resource paths.

Identify the repository's Spring generation and programming model before using
an API. Verify changed or unfamiliar behavior against the dependency version's
primary documentation. Do not paste a starter template, introduce a framework
module, or upgrade Spring, Kotlin, Java, token support, logging, or test
libraries merely to complete a feature.

## Preserve the existing application shape

- Keep HTTP concerns at the controller boundary: parsing, validation, status,
  headers, and transport DTOs.
- Keep business decisions in the repository's existing service or domain seam.
- Keep database, messaging, and HTTP-client details behind the established
  adapter boundary and lifecycle.
- Use constructor injection and the repository's configuration-binding pattern.
- Make transactions, timeouts, retries, failure mapping, and coroutine or
  blocking boundaries explicit where correctness depends on them.

Use `grillmester-api-design`, `grillmester-auth-overview`, `grillmester-postgresql-review`, `grillmester-kafka-topic`, or
`grillmester-observability-setup` when the change crosses those specialist surfaces. A
specialist skill informs the Spring implementation; it does not silently widen
the accepted scope.

## Configure from evidence

Derive property names, environment mappings, profiles, secrets, health paths,
ports, and management exposure from the application and manifests. Keep
environment-dependent values outside source code and fail clearly when a
required value is missing. Never invent a NAV-generated variable, audience,
issuer, database prefix, probe path, pool size, or platform timeout.

Load [the NAV Spring runtime reference](references/nav-spring-runtime.md) when
the service uses NAV identity, Nais, Actuator, a database, structured logging,
or NAV-specific integration testing.

## Secure the boundary

Determine caller, identity provider, token type, issuer, audience, claims, and
resource-level authorization from the real contract. If the repository uses
NAV token-support, follow the installed module and version's configuration and
annotations; do not assume a starter coordinate or `@ProtectedWithClaims`
shape. Treat network access and a valid token as insufficient authorization.

Validate untrusted input at the boundary, avoid sensitive fields in URLs and
logs, and keep operational endpoints deliberately scoped. Use
`grillmester-security-review` for a changed identity model, sensitive-data flow, privileged
operation, or new trust boundary.

## Test through discovered seams

Use the repository's test engine, mocking library, HTTP test client, container
setup, fixtures, and auth-test pattern.

- Test domain behavior without booting Spring when no container behavior is
  under test.
- Use a controller or context slice only when Spring binding, validation,
  filters, security, serialization, or exception mapping is the subject.
- Use an application integration test for wiring, configuration, migrations,
  real adapters, or lifecycle behavior.
- Use Testcontainers and MockOAuth2Server only when the repository already
  selects them or the accepted change explicitly introduces them after version
  and lifecycle verification.

Cover success, invalid input, unauthenticated, unauthorized, dependency
failure, and relevant concurrency or transaction behavior. Prefer observable
responses and state over assertions on implementation details.

## Verify the assembled service

Run the repository's focused tests and required build gates. For runtime or
manifest changes, verify that configured Actuator endpoints and Nais probe or
metrics paths match, that shutdown closes resources and stops accepting new
work safely, and that secrets or personal data do not appear in startup output,
errors, logs, metrics, or traces. Report commands, results, exit codes, and any
environment behavior not exercised.

## Boundaries

- Ask before adding or upgrading a framework, auth module, database, message
  broker, management exposure, or production-facing endpoint.
- Never hardcode credentials, identities, environment-specific destinations,
  dependency versions, generated NAV values, or consumer paths.
- Never treat a passing application-context test as proof of authorization,
  probe behavior, database compatibility, or production readiness.
