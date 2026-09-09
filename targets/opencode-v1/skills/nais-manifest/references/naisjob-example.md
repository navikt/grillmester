---
description: Portable Naisjob shape and decision guidance for bounded scheduled or manually triggered backend work.
---

# Naisjob example

Use only the blocks the job actually needs. Resolve every placeholder from the
repository, owning team, target environment, and current Nais schema.

```yaml
apiVersion: nais.io/v1
kind: Naisjob
metadata:
  name: <job-name>
  namespace: <team-namespace>
  labels:
    team: <team-label>
spec:
  image: {{ image }}

  # Omit schedule for a manually triggered one-off job.
  schedule: "<approved-cron-expression>"
  concurrencyPolicy: Forbid
  activeDeadlineSeconds: <approved-deadline>
  backoffLimit: <approved-retry-limit>
  ttlSecondsAfterFinished: <approved-retention-seconds>

  resources:
    requests:
      cpu: <measured-or-approved-request>
      memory: <measured-or-approved-request>
    limits:
      memory: <measured-or-approved-limit>

  # Include only if this job needs an Azure application identity.
  azure:
    application:
      enabled: true

  # Jobs normally declare outbound dependencies, not inbound HTTP callers.
  accessPolicy:
    outbound:
      rules:
        - application: <downstream-application>
          namespace: <downstream-namespace>
      external:
        - host: <approved-external-host>

  # Include only if the job produces to or consumes a bounded set from Kafka.
  kafka:
    pool: <environment-kafka-pool>

  # Include only if the job owns or deliberately shares this database.
  gcp:
    sqlInstances:
      - type: <supported-postgres-type>
        tier: <approved-tier>
        highAvailability: <approved-value>
        diskAutoresize: <approved-value>
        databases:
          - name: <database-name>
            envVarPrefix: <repository-prefix>

  env:
    - name: <repository-defined-variable>
      value: <non-secret-value>
```

## Decision checks

- The work has a defined end and exits with a meaningful status.
- The schedule and timezone behavior are understood and tested.
- `concurrencyPolicy` matches whether overlapping runs are safe.
- Deadline and retry limits cannot create an endless failure loop.
- Re-running after partial completion is idempotent or has a documented recovery
  path.
- Secrets come from a supported secret source, never `env.value` in Git.
- A continuous Kafka consumer uses `Application`, not `Naisjob`.
- Metrics and HTTP probes are included only if the job runtime actually exposes
  them and the platform supports the intended collection window.

Validate the cron expression and a fully rendered manifest through the
repository's normal gates before delivery.
