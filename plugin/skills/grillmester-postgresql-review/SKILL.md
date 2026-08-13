---
name: grillmester-postgresql-review
description: Review or design PostgreSQL use in a Nav backend. Use for a DataSource, HikariCP pool, Cloud SQL capacity, connection errors, schema or query review, Flyway migration, indexes, N+1 behavior, shared databases, destructive changes, or database technology choice.
license: MIT
---

# Review PostgreSQL safely

## Establish repository and runtime evidence first

Inspect database dependencies, configuration loading, data-source construction,
Nais manifests and replicas, Cloud SQL resources, migration tool and locations,
schema history, query or ORM style, transaction boundaries, tests, metrics, and
known consumers. Search by symbols and configuration keys rather than assuming
source paths, package names, environment prefixes, HikariCP, Flyway, or one
database per service.

For capacity claims, obtain the actual production tier, replica range,
`max_connections`, pool settings, connection metrics, and other workloads using
the instance. Consumer instructions can declare ownership and intended
invariants, but verify effective capacity values against manifests,
configuration and telemetry; never borrow them from another repository. If those facts are unavailable, report the calculation with
unknown inputs instead of presenting a safe pool size as fact.

## Confirm PostgreSQL is the right state boundary

| Need | Likely choice | Check |
|---|---|---|
| transactional operational state | PostgreSQL | ownership, backup, recovery, migrations |
| reproducible cache or ephemeral state | no database or an approved cache | invalidation and rebuild path |
| analytics and large reporting workloads | approved data platform | freshness, governance, cost |
| communication between independently owned services | API or Kafka | contract and ownership; do not couple through tables |

Introducing a new database technology, shared instance, or cross-team table
contract is an architectural and operational decision. Ask before implementing
it and record the accepted decision through the repository's ADR process.

## Review the connection pool from measured capacity

When the repository uses HikariCP, configure it explicitly through the existing
typed configuration boundary. Treat 3–5 connections per small service replica
as a starting hypothesis only, then verify it against workload concurrency and
database capacity. Never copy Hikari's default pool size into an autoscaled
service without doing the aggregate calculation.

```text
sum(max replicas for each workload × pool size per replica)
  + migration, admin, and operational headroom
  <= verified max_connections
```

Review connection and validation timeouts, idle policy, maximum lifetime,
minimum idle, transaction isolation, leak detection, and shutdown. A maximum
lifetime below infrastructure-enforced connection lifetime can reduce stale
connections, but choose it from current platform behavior and metrics rather
than assuming a universal value. Explicit `READ_COMMITTED` can document the
PostgreSQL default when it matches repository semantics.

Load [references/sql-patterns.md](references/sql-patterns.md) for a portable Nais
Cloud SQL and HikariCP configuration pattern.

## Review schema and queries

- Enforce stable domain invariants with appropriate `NOT NULL`, `CHECK`,
  `UNIQUE`, and foreign-key constraints.
- Index foreign keys and frequent filter, join, ordering, and lookup paths when
  query evidence supports it. Check write and storage cost for every index.
- Select only needed columns in production paths and bound result sets that can
  grow.
- Detect N+1 behavior at the repository or ORM boundary and batch or join where
  appropriate.
- Verify `ON CONFLICT` targets a real unique constraint and that its update is
  safe under concurrency.
- Use `TIMESTAMPTZ` for real instants; use domain-appropriate types such as
  `DATE` for calendar dates.
- Use `EXPLAIN (ANALYZE, BUFFERS)` only in a safe environment with representative
  data and awareness that `ANALYZE` executes the statement.

Partitioning, advisory locks, JSONB-heavy models, and new production indexes on
large tables need evidence and explicit review. `CREATE INDEX CONCURRENTLY`
reduces blocking but has transaction and recovery constraints.

## Review migrations as production code

Read the repository's applied migration history and configuration before
creating a file. Never modify an applied versioned migration. Prefer a new
forward migration and a forward repair path over relying on an undo file.

For shared schemas, use expand–migrate–contract:

1. add a backward-compatible column or table;
2. deploy dual-read or dual-write behavior and migrate consumers and data;
3. remove the old shape in a later change only after consumers and observed
   production use confirm migration.

Load [references/migration-flyway.md](references/migration-flyway.md) for
concurrent indexes, invalid-index recovery, repeatable objects, and shared-schema
coordination.

## Coordinate shared databases

Find every application and team with database access, not only code in the
current repository. Before `DROP`, rename, type change, constraint tightening,
or ownership change, confirm consumers can tolerate the expanded schema and
have migrated. A Nais permission or shared Cloud SQL instance is evidence of
possible coupling, not a complete consumer list.

Prefer an explicit API or event contract over adding new cross-team reads. Never
perform a destructive shared-schema change on an assumed notification window.

## Verify with relevant evidence

Run the repository's migration and database tests, preferably against the
supported PostgreSQL version rather than an in-memory substitute. Verify clean
bootstrap and upgrade from the currently deployed schema. For pool changes,
show the capacity calculation and monitor pending, active, idle, timeout, server
connection, and saturation metrics.

Return findings ordered by production risk with file or query evidence, the
failure mode, and the smallest corrective action. Separate verified facts,
inferences, and unknown operational inputs.

## Review checklist

- [ ] Database ownership and consumers identified.
- [ ] Actual Postgres version, replicas, pool, and `max_connections` verified.
- [ ] Aggregate connection budget leaves operational headroom.
- [ ] Transactions and isolation match concurrency requirements.
- [ ] Queries avoid unbounded reads, N+1, and unsupported index assumptions.
- [ ] Constraints and indexes match domain and query evidence.
- [ ] Migration is forward-safe and tested from the deployed schema.
- [ ] Shared-schema change is coordinated through expand–migrate–contract.
- [ ] Personal data, credentials, and query parameters stay out of logs.

## Boundaries

### Ask first

- Add a database type, shared schema, partitioning, advisory lock, or large
  production index.
- Raise a pool above measured capacity, change production tier, or perform a
  destructive or long-locking migration.

### Never

- Invent connection capacity, environment prefixes, paths, or consumers.
- Modify an applied migration.
- Use a database as an undocumented integration contract between teams.
- Log credentials, national identity numbers, raw sensitive rows, or unsafe
  query parameters.
- Drop a shared table or column without confirmed consumer migration and a
  recovery plan.
