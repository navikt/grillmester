---
description: Plain Apache Kafka patterns for a Ktor backend: lifecycle, consumer and producer behavior, Nais SSL configuration, event headers, commit strategy, and tests.
---

# Plain Apache Kafka in a Ktor backend

Use these patterns only after repository inspection confirms direct
`org.apache.kafka:kafka-clients` usage or the user approves it for a new flow.

## Lifecycle beside the HTTP server

`KafkaConsumer` is not thread-safe. Own it inside one runner and execute `poll`
on that runner's thread or coroutine. Register the runner with the DI and
startup mechanism the application already uses, and close it through the same
resource lifecycle. `wakeup()` is the normal way to interrupt a blocking poll
from another thread.

```kotlin
class EventConsumer(
    private val consumer: KafkaConsumer<String, String>,
    private val topic: String,
    private val handler: (ConsumerRecord<String, String>) -> Unit,
    private val park: (ConsumerRecord<String, String>, Throwable) -> Unit,
) : AutoCloseable {
    @Volatile private var running = true

    fun run() {
        try {
            consumer.subscribe(listOf(topic))
            while (running) {
                val records = consumer.poll(Duration.ofSeconds(1))
                records.forEach { record ->
                    try {
                        handler(record)
                    } catch (error: PermanentMessageError) {
                        park(record, error)
                    }
                }
                consumer.commitSync()
            }
        } catch (error: WakeupException) {
            if (running) throw error
        } finally {
            consumer.close()
        }
    }

    override fun close() {
        running = false
        consumer.wakeup()
    }
}
```

Let temporary failures escape the handler so the batch is not committed and is
redelivered. Park a permanent failure durably before continuing. If the
repository commits per record, pauses partitions, or uses transactions, retain
that established semantic instead of copying this batch example.

Keep `enable.auto.commit=false`. `commitSync()` after a processed batch is
simple and deterministic. Adopt asynchronous commits only with an explicit
throughput and failure design.

## Producer

```kotlin
producer.send(ProducerRecord(topic, key, value)) { metadata, error ->
    if (error != null) {
        logger.error(
            "Kafka publish failed",
            kv("topic", topic),
            error,
        )
    }
}
```

Use `enable.idempotence=true` with `acks=all` for an idempotent producer. Use
Kafka transactions only when the service deliberately coordinates consumed
offsets and produced records in the same transaction. A producer callback must
surface failure to metrics and the owning operation; logging alone may be
insufficient.

## Nais SSL configuration

Nais supplies Kafka connection material such as `KAFKA_BROKERS`, truststore and
keystore paths, and `KAFKA_CREDSTORE_PASSWORD`. Read those values through the
repository's existing configuration layer. Do not switch between typed config
and direct `System.getenv` access without reason.

```kotlin
fun consumerProperties(config: KafkaConfig) = Properties().apply {
    put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, config.brokers)
    put(CommonClientConfigs.SECURITY_PROTOCOL_CONFIG, "SSL")
    put(SslConfigs.SSL_TRUSTSTORE_TYPE_CONFIG, "PKCS12")
    put(SslConfigs.SSL_TRUSTSTORE_LOCATION_CONFIG, config.truststorePath)
    put(SslConfigs.SSL_TRUSTSTORE_PASSWORD_CONFIG, config.credentialPassword)
    put(SslConfigs.SSL_KEYSTORE_TYPE_CONFIG, "PKCS12")
    put(SslConfigs.SSL_KEYSTORE_LOCATION_CONFIG, config.keystorePath)
    put(SslConfigs.SSL_KEYSTORE_PASSWORD_CONFIG, config.credentialPassword)
    put(ConsumerConfig.GROUP_ID_CONFIG, config.groupId)
    put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, config.autoOffsetReset)
    put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false)
}
```

Derive group ID and `auto.offset.reset` from deployed configuration. Do not
invent defaults: either can change replay behavior.

## Event identity in a Kafka header

When the established plain-Kafka contract carries its event ID in a header,
keep it there and validate it before processing. A UUID header can be decoded
without exposing the payload:

```kotlin
fun ConsumerRecord<*, *>.eventId(headerName: String): UUID {
    val bytes = headers().lastHeader(headerName)?.value()
        ?: throw PermanentMessageError("missing event-id header")
    return runCatching { UUID.fromString(bytes.toString(Charsets.UTF_8)) }
        .getOrElse { throw PermanentMessageError("invalid event-id header") }
}
```

Persist that stable identity with a unique constraint or equivalent atomic
deduplication. Do not substitute message key, partition/offset, or a newly
generated ID. If the published contract uses a payload ID instead, follow it.

## Testing

- Unit-test parsing and processing separately from the Kafka client by building
  `ConsumerRecord` values, including missing and invalid event-ID cases.
- Prove that a redelivered event is a no-op through the real idempotency
  boundary.
- Prove that temporary failure prevents commit and permanent failure is durably
  parked before commit.
- Use the repository's existing Kafka integration harness. When none exists,
  Testcontainers Kafka is preferable to an in-process broker for realistic
  client behavior.
- Exercise startup and shutdown so a blocking poll exits within the pod's grace
  period.

Run the repository's own test and build gates; do not assume Gradle, Kotest, or
a specific test path.
