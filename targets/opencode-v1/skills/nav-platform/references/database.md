# Cloud SQL PostgreSQL on Nais

## Contents

- Platform configuration
- Connection capacity
- Migrations
- Shared databases
- Database diagnosis
- Boundaries

## Platform configuration

```yaml
gcp:
  sqlInstances:
    - type: <supported-postgres-type>
      tier: <approved-tier>
      highAvailability: <approved-value>
      diskAutoresize: <approved-value>
      databases:
        - name: <database-name>
          envVarPrefix: <repository-prefix>
```

Verify the supported Postgres type, tier, HA, backup and disk choices against
current Nais documentation and repository needs.

Nais derives connection variables from `envVarPrefix`. Follow the repository's
existing mapping into typed application config, and do not copy a database
environment prefix from another service. Do not copy the generated variable
names, JDBC URL, credentials, certificate paths, or database version from another
service.

## Connection capacity

For capacity claims, obtain the actual production tier, replica range,
`max_connections`, pool settings, connection metrics, and other workloads using
the instance. If those facts are unavailable, report the calculation with
unknown inputs instead of presenting a safe pool size as fact.

```text
application max replicas × application pool
+ job concurrency × job pool
+ other applications sharing the instance
+ migration and operator connections
+ safety headroom
<= SHOW max_connections
```

Verify `SHOW max_connections` on the target environment; it varies with instance
configuration. A per-replica pool of 3–5 is a common initial hypothesis for a
small Nav service, not a guarantee. Size from concurrent database work, query
latency, transaction duration, and observed pending connections. Adding pool
connections can worsen a database already limited by slow queries or locks.
Never copy Hikari's default pool size into an autoscaled service without doing
the aggregate calculation.

A maximum lifetime below infrastructure-enforced connection lifetime can reduce
stale connections, but choose it from current platform behavior and metrics
rather than assuming a universal value.

## Migrations

- Determine whether migrations run at startup, in CI or as a separate job.
- Never edit a versioned migration already applied to a shared environment. Add
  a new forward migration and preserve a forward repair path.
- A repair, rollback or manual SQL command can change durable data. Show the
  exact command, target, backup/rollback and expected effect, then obtain
  approval.
- For conflicting migration versions, follow the tool and repository's
  documented ordering policy; do not invent a numbering convention.
- Ensure long startup migrations fit the repository's startup and probe design.
- Large table rewrites, constraint validation, and index builds need lock and
  duration analysis.
- Do not combine expand and contract into one deployment when old application
  replicas or external consumers may still use the old schema.

## Shared databases

Find every application and team with database access, not only code in the
current repository. Before `DROP`, rename, type change, constraint tightening,
or ownership change, confirm consumers can tolerate the expanded schema and
have migrated. A Nais permission or shared Cloud SQL instance is evidence of
possible coupling, not a complete consumer list.

Prefer an explicit API or event contract over adding new cross-team reads. Never
perform a destructive shared-schema change on an assumed notification window.

## Database diagnosis

First detect database engine, provisioning model, driver, pool, migration tool,
replica count and configuration names from consumer evidence. Cloud SQL,
PostgreSQL, HikariCP and Flyway are common Nais choices, not assumptions.

### Read-only evidence

- deployed workload and sidecar status
- redacted presence of expected configuration variables, never their values
- application startup and pool logs in the failing time window
- database/platform availability and connection-count signals
- deployed replica count, configured pool bounds and database connection limit
- migration history and the exact failed migration, if applicable

Use the verified namespace and workload selectors. Do not dump environment
variables or secrets.

### Diagnostic tree

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

### Pool interpretation

Calculate total potential connections from verified replica and pool settings,
then include other clients and reserved headroom. Read the instance class and
max-connections value from the instance or its deployed configuration.

Pool timeouts can indicate:

- leaked or unclosed connections
- slow queries or lock waits
- long transactions
- unavailable database or proxy
- a pool too small for measured concurrency
- a database limit reached across several workloads

Changing pool size or database capacity before distinguishing these causes can
make the incident worse.

### Escalation

- Startup crash or sidecar failure:
  [Pod diagnosis](nais.md#pod-diagnosis)
- Route code-level reproduction and regression testing to
  `diagnosing-bugs`.

## Boundaries

### Ask first

- Add a database type, shared schema, partitioning, advisory lock, or large
  production index.
- Raise a pool above measured capacity, change production tier, or perform a
  destructive or long-locking migration.

### Never

- Invent connection capacity, environment prefixes, paths, or consumers.
- Use a database as an undocumented integration contract between teams.
- Log credentials, national identity numbers, raw sensitive rows, or unsafe
  query parameters.
- Drop a shared table or column without confirmed consumer migration and a
  recovery plan.
