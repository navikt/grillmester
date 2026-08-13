# Database diagnosis

First detect database engine, provisioning model, driver, pool, migration tool,
replica count and configuration names from consumer evidence. Cloud SQL,
PostgreSQL, HikariCP and Flyway are common Nais choices, not assumptions.

## Read-only evidence

- deployed workload and sidecar status
- redacted presence of expected configuration variables, never their values
- application startup and pool logs in the failing time window
- database/platform availability and connection-count signals
- deployed replica count, configured pool bounds and database connection limit
- migration history and the exact failed migration, if applicable

Use the verified namespace and workload selectors. Do not dump environment
variables or secrets.

## Diagnostic tree

```text
Database failure
├── Is the database and any proxy/sidecar healthy?
│   ├── No → inspect platform status and pod events
│   └── Yes → continue
├── Does the workload have the expected config names?
│   ├── No → compare deployment declaration with application config
│   └── Yes → continue without printing values
├── Did startup or migration fail?
│   ├── Yes → identify tool, migration and immutable-history rules
│   └── No → continue
├── Is the connection pool exhausted?
│   ├── Yes → distinguish leak, slow query, long transaction and undersizing
│   └── No → continue
├── Is the database connection limit exhausted?
│   ├── Yes → compare all clients, replicas and pool maxima with headroom
│   └── No → continue
└── Is connectivity or authorization failing?
    └── inspect proxy, DNS, policy, credentials rotation and database grants
```

## Migration discipline

- Determine whether migrations run at startup, in CI or as a separate job.
- Never edit a migration already applied in a shared environment unless the
  consumer's migration policy explicitly permits it.
- A repair, rollback or manual SQL command can change durable data. Show the
  exact command, target, backup/rollback and expected effect, then obtain
  approval.
- For conflicting migration versions, follow the tool and repository's
  documented ordering policy; do not invent a numbering convention.

## Pool interpretation

Calculate total potential connections from verified replica and pool settings,
then include other clients and reserved headroom. Do not assume a default pool
size, instance class or max-connections value.

Pool timeouts can indicate:

- leaked or unclosed connections
- slow queries or lock waits
- long transactions
- unavailable database or proxy
- a pool too small for measured concurrency
- a database limit reached across several workloads

Changing pool size or database capacity before distinguishing these causes can
make the incident worse.

## Escalation

- Startup crash or sidecar failure:
  [pod-diagnose.md](./pod-diagnose.md)
- Query, index or schema design: grillmester-postgresql-review
- When the standard `grillmester` package is installed, optionally route
  code-level reproduction and regression testing to
  `grillmester-diagnosing-bugs`. Without it, report the smallest reproducible
  query or transaction, observable failure and proposed regression boundary;
  use `NEEDS_CONTEXT` if any cannot be verified safely.
