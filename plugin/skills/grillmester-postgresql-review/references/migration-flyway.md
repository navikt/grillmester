# Flyway and PostgreSQL migration patterns

## Inspect migration policy first

Find the Flyway version, configured locations, naming convention, schemas,
baseline, placeholders, repeatable migrations, transaction settings, startup
timing, and tests. Do not assume `db/migration`, a version number sequence, or a
per-script transaction directive. If another migration tool is in use, apply
its actual semantics instead of these Flyway patterns.

Never edit a versioned migration already applied to a shared environment. Add a
new forward migration and preserve a forward repair path.

## Concurrent indexes

PostgreSQL `CREATE INDEX CONCURRENTLY` cannot run inside a transaction. Put it in
a migration whose transaction behavior is explicitly disabled through the
mechanism supported by the repository's Flyway version and configuration.

```sql
CREATE INDEX CONCURRENTLY idx_entity_owner_status
    ON entity (owner_id, status);
```

Do not assume `IF NOT EXISTS` makes this safely repeatable. An interrupted
concurrent build can leave an invalid index with the same name. Before retrying,
inspect the catalog, remove the invalid index through an approved operational
step, and rerun the migration. Test how the repository handles non-transactional
migrations before production.

## Type, constraint, and index checks

- Use `TIMESTAMPTZ` for real instants and `DATE` for calendar dates.
- Add indexes for foreign keys and frequent query paths when workload evidence
  supports them.
- Add `NOT NULL`, `CHECK`, and `UNIQUE` constraints in a way existing rows and
  old application versions can tolerate.
- Match primary-key strategy and extensions already approved by the schema;
  do not impose UUIDs or sequences universally.
- Use repeatable migrations for views or functions only when that is the
  repository's established Flyway policy.

Large table rewrites, constraint validation, and index builds need lock and
duration analysis. Separate a non-transactional concurrent index from unrelated
DDL so its failure and recovery are clear.

## Expand–migrate–contract for shared or rolling deployments

1. **Expand:** add a nullable or backward-compatible field, table, index, or
   behavior that old and new application versions can both use.
2. **Migrate:** backfill in bounded, observable batches; deploy dual reads or
   writes where needed; move consumers one at a time.
3. **Contract:** after all consumers and production evidence confirm migration,
   remove the old field or behavior in a later release.

Do not combine expand and contract into one deployment when old application
replicas or external consumers may still use the old schema.

## Verification

- Apply all migrations to an empty supported PostgreSQL instance.
- Upgrade a database at the currently deployed schema to the new version.
- Exercise rollback of application code against the expanded schema, even when
  database migrations are forward-only.
- Verify constraints and indexes with catalog queries, not file inspection
  alone.
- Test representative queries and lock behavior with safe data volume.
- Document operator recovery for partial backfills and failed concurrent
  indexes.
