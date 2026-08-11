# Nais Cloud SQL and HikariCP patterns

## Derive platform configuration from the repository

Inspect the actual Nais resource and the application's configuration mapping.
The following is a shape, not a version, database name, tier, prefix, or replica
recommendation:

```yaml
spec:
  replicas:
    min: <verified-min>
    max: <verified-max>
  gcp:
    sqlInstances:
      - type: <supported-postgres-type>
        tier: <approved-tier>
        databases:
          - name: <database-name>
            envVarPrefix: <repository-prefix>
```

Nais derives connection variables from `envVarPrefix`. Follow the repository's
existing mapping into typed application config. Do not hardcode the generated
variable names, JDBC URL, credentials, certificate paths, or database version
from this example.

## Configure HikariCP explicitly when it is the selected pool

```kotlin
fun dataSource(config: DatabaseConfig): HikariDataSource =
    HikariDataSource(
        HikariConfig().apply {
            jdbcUrl = config.jdbcUrl
            username = config.username
            password = config.password
            maximumPoolSize = config.maximumPoolSize
            minimumIdle = config.minimumIdle
            connectionTimeout = config.connectionTimeoutMillis
            idleTimeout = config.idleTimeoutMillis
            maxLifetime = config.maxLifetimeMillis
            transactionIsolation = config.transactionIsolation
        },
    )
```

Keep secrets out of `toString`, startup logs, exception messages, and metrics
labels. Ensure the data source closes through the application lifecycle.

## Calculate capacity across all workloads

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
small NAV service, not a guarantee. Size from concurrent database work, query
latency, transaction duration, and observed pending connections. Adding pool
connections can worsen a database already limited by slow queries or locks.

## Review lifecycle and timeouts

- `connectionTimeout`: fail within the caller's budget when the pool is
  exhausted.
- `maxLifetime`: recycle before any verified infrastructure lifetime while
  avoiding synchronized churn.
- `idleTimeout` and `minimumIdle`: balance burst readiness against needless
  connections.
- `transactionIsolation`: state it explicitly when semantics depend on it.
- validation and keepalive: add only when evidence shows stale connections.

Watch Hikari active, idle, pending, acquisition-timeout and usage-time metrics
alongside PostgreSQL sessions, locks, CPU, memory, I/O, and query latency. Pool
metrics alone cannot distinguish insufficient capacity from slow queries,
long transactions, or lock contention.
