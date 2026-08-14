---
description: Rapids and Rivers patterns: lifecycle choice, packet validation, publishing, idempotency, error handling, and TestRapid.
---

# Rapids and Rivers

Use this reference only when repository evidence shows Rapids and Rivers, for
example the current
`com.github.navikt:rapids-and-rivers` facade coordinate, an older
established coordinate, or imports from its API packages. Otherwise require the
user to approve adopting it. Do not add a second Kafka stack to a plain- or
Spring-Kafka service by accident. Resolve the version and coordinate from the
consumer's build before editing; do not copy a version from this reference.

`RapidApplication` owns a process lifecycle and an HTTP server. If the service
also has Ktor startup, inspect how the repository composes them before changing
either. Avoid starting two engines without a deliberate port, health, and
shutdown design.

## Packet validation

```kotlin
class DomainEventRiver(
    rapidsConnection: RapidsConnection,
    private val handler: DomainEventHandler,
) : River.PacketListener {
    init {
        River(rapidsConnection).apply {
            precondition { it.requireValue("@event_name", "case_created") }
            validate { it.requireKey("@id", "@created_at", "case_id") }
            validate { it.interestedIn("optional_field") }
        }.register(this)
    }

    override fun onPacket(
        packet: JsonMessage,
        context: MessageContext,
        metadata: MessageMetadata,
        meterRegistry: MeterRegistry,
    ) {
        handler.handle(
            eventId = packet["@id"].asString(),
            caseId = packet["case_id"].asString(),
        )
    }

    override fun onError(
        problems: MessageProblems,
        context: MessageContext,
        metadata: MessageMetadata,
    ) {
        logger.error("packet_validation_failed river=DomainEventRiver")
    }
}
```

| Predicate | Purpose |
|---|---|
| `precondition { requireValue(key, value) }` | select the intended event type |
| `precondition { forbid(key) }` / `precondition { forbidValue(key, value) }` | exclude packets outside this river |
| `requireKey(...)` | require fields or report validation failure |
| `require(key, parser)` | require and parse a field |
| `requireAny(...)` | require at least one alternative |
| `interestedIn(...)` | read optional fields without rejecting old messages |

Use `precondition` with `requireValue` and `forbid*` for routing. Use
`validate` only after the packet has been selected. Requiring an optional
field breaks backward compatibility; use `interestedIn` for additive
evolution.

## Publishing

```kotlin
context.publish(
    JsonMessage.newMessage(
        mapOf(
            "@event_name" to "case_created",
            "@id" to UUID.randomUUID().toString(),
            "@created_at" to Instant.now(),
            "@produced_by" to applicationName,
            "case_id" to caseId,
        ),
    ).toJson(),
)
```

Use the repository's existing clock, serialization, naming, and correlation
conventions. Keep personal data out of logs and avoid copying sensitive values
onto a shared rapid unless the contract and access assessment require them.

## Idempotency and errors

Rapids is at-least-once. Deduplicate atomically on `@id` or the repository's
documented event identity before applying side effects.

- Temporary dependency failure: throw so the record can be redelivered.
- Permanent semantic failure: use the repository's established parking or DLQ
  path, then continue only after the record is durably accounted for.
- Packet validation failure: report through `onError` with a sanitized,
  structural summary such as the river or contract name. Never interpolate the
  packet, `MessageProblems`, `toExtendedReport()` or sensitive validation
  values.

Do not invent a DLQ topic when the service already parks records in a database,
and do not silently discard a packet that cannot be replayed or investigated.

## Testing with TestRapid

```kotlin
val rapid = TestRapid()
DomainEventRiver(rapid, fakeHandler)

rapid.sendTestMessage(
    """
    {
      "@event_name": "case_created",
      "@id": "550e8400-e29b-41d4-a716-446655440000",
      "@created_at": "2026-01-01T08:00:00Z",
      "case_id": "case-1"
    }
    """.trimIndent(),
)
```

Follow the repository's actual test framework and assertion style. Cover event
filtering, required versus optional fields, duplicate IDs, temporary failure,
permanent parking, and any published follow-up event. Changing the consumer
group or rapid topic can replay data; require operational approval.
