# Ktor StatusPages and error contracts

## Inspect the published error behavior first

Find installed `StatusPages`, exception types, response DTOs, serializers,
route-level handling, auth failures, tests, and API documentation. Record the
current status, content type, fields, code vocabulary, unknown-error behavior,
and logging rules. Do not introduce this pattern if the repository already has
a different public error contract.

## Keep internal failures separate from public errors

Use a small typed application failure and map it once at the HTTP boundary. Do
not return arbitrary exception messages or stack traces:

```kotlin
@Serializable
data class ApiError(
    val code: String,
    val message: String,
    val callId: String? = null,
)

sealed class ApiFailure(
    val status: HttpStatusCode,
    val code: String,
    val safeMessage: String,
) : RuntimeException(safeMessage) {
    class InvalidInput(message: String) :
        ApiFailure(HttpStatusCode.BadRequest, "invalid_input", message)

    class Missing :
        ApiFailure(HttpStatusCode.NotFound, "not_found", "Resource not found")
}
```

Only put user-safe, non-sensitive text in `safeMessage`. Domain IDs, national
identity numbers, tokens, raw input, SQL, and downstream bodies do not belong in
the public payload.

```kotlin
fun Application.installErrorHandling() {
    install(StatusPages) {
        exception<ApiFailure> { call, failure ->
            call.application.log.warn(
                "Request rejected: code={}, callId={}",
                failure.code,
                call.callId,
            )
            call.respond(
                failure.status,
                ApiError(failure.code, failure.safeMessage, call.callId),
            )
        }

        exception<Throwable> { call, failure ->
            call.application.log.error(
                "Unhandled request failure: type={}, callId={}",
                failure::class.qualifiedName,
                call.callId,
            )
            call.respond(
                HttpStatusCode.InternalServerError,
                ApiError("internal_error", "Internal server error", call.callId),
            )
        }
    }
}
```

Some parsing exceptions embed the input body in their message or cause chain,
so passing the original throwable may be unsafe. Attach a throwable only when
the repository's redaction policy makes it safe; otherwise preserve the useful
class and correlation metadata without retaining personal content.

## Respect framework-owned failures

Confirm how Ktor auth, content negotiation, request parsing, and unsupported
methods are handled. Do not convert every exception into 500 or override
authentication challenge headers accidentally. Map missing or malformed input
to the contract's client-error status and keep authorization failures distinct
from authentication failures.

## Verify the contract

Test every public error class, malformed and missing input, auth failures,
unexpected exceptions, content type, call-ID propagation, and redaction. Assert
that logs and response bodies contain neither the submitted personal data nor
token material. Update OpenAPI or other contract documentation in the same
change.
