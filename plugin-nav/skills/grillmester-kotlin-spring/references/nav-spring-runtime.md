# NAV Spring runtime patterns

Load only the sections that match the repository's selected integrations.
Repository code, resolved dependencies, manifests, and current primary NAV,
Nais, Spring, and library documentation remain authoritative.

## NAV token validation

1. Identify the incoming caller and whether the request carries an employee,
   end-user, machine, or on-behalf-of identity.
2. Inspect resolved Gradle dependencies and existing security configuration to
   find the selected NAV token-support module and version.
3. Verify issuer, audience, discovery metadata, signature, lifetime, and client
   constraints for every accepted identity provider.
4. Follow the installed version's annotation or filter API. Do not infer an
   annotation, starter coordinate, property prefix, or claim accessor from an
   example written for another version.
5. Enforce role, client, organization, purpose, case, or resource ownership in
   application logic where the contract requires it.

Use the repository's established on-behalf-of client for downstream calls.
Never forward an incoming token to a service with a different audience, and do
not use call IDs or network policy as authorization evidence.

## Configuration and secrets

Map environment values into the application's existing typed configuration.
Discover NAV-generated names from the actual manifest and platform contract.
Keep credentials out of defaults, examples, exception messages, configuration
dump endpoints, and data-class `toString` output.

Validate required configuration during startup with useful non-secret error
messages. Test each configuration profile or binding shape that can reach a
deployed environment.

## Actuator and Nais

Actuator endpoint paths depend on the installed Spring Boot version and local
management configuration. Resolve the actual base path, exposure, port, health
groups, and security chain, then match the Nais liveness, readiness, startup,
and Prometheus paths to those observed endpoints.

- Liveness should represent whether the process must be restarted.
- Readiness should represent whether the workload should receive traffic.
- Avoid making liveness depend on a transient downstream outage.
- Expose only the management details required for platform operation; do not
  leak configuration, identities, health internals, or sensitive dependency
  state.
- Coordinate shutdown with the repository's Nais lifecycle so traffic drains
  before in-flight work and managed resources are terminated.

Verify endpoints locally or in an approved test environment. File inspection
alone does not prove path, status, access, or shutdown behavior.

## Database and pool

Follow `grillmester-postgresql-review` for migrations, transaction behavior, Cloud SQL,
and aggregate connection capacity. Derive datasource variables and pool
settings from repository and runtime evidence. Calculate connections across
maximum replicas and other workloads; never copy a fixed pool size or lifetime
from another service.

Test clean migration, upgrade from the deployed schema, transaction rollback,
pool exhaustion behavior where relevant, and datasource closure.

## Structured logging and correlation

Use the repository's selected logging facade, encoder, field names, and MDC or
context propagation. Emit structured, low-cardinality operational context to
stdout when that is the deployed pattern. Keep national identity numbers,
names, tokens, request bodies, and sensitive case facts out of ordinary logs,
metrics, and traces.

Propagate an existing correlation ID according to the actual API contract.
Generate one only at the owning boundary, and never trust it as identity.

## Spring-specific tests

- Use the repository's MVC or reactive test client according to the selected
  web stack.
- Use a Spring slice for framework behavior and a full context only when wiring
  or lifecycle is part of the claim.
- When NAV auth is involved, configure MockOAuth2Server or the repository's
  chosen equivalent through its current API and verify issuer, audience,
  claims, unauthenticated, and unauthorized cases separately.
- Use Testcontainers for real database or broker semantics when those semantics
  matter, with versions and lifecycle derived from the repository.
- Confirm that test-only authentication, permissive filters, and container
  configuration cannot enter a deployed profile.
