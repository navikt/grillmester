# Outgoing Ktor HttpClient boundaries

## Inventory the client before changing it

Find where each `HttpClient` is constructed, configured, injected, and closed.
Record:

- engine and Ktor version;
- whether the client is shared or per downstream;
- `expectSuccess`, redirects, proxy, TLS, timeout, retry, logging, and content
  negotiation settings;
- serializer options and unknown-field behavior;
- token provider, target or scope configuration, and call-ID propagation;
- status and body mapping, metrics, tests, and resource cleanup.

Do not assume plugins are installed merely because downstream code uses the
client. Installing a plugin on a shared client changes every caller, including
token-sidecar calls when they share the instance.

## Keep transport details at the client boundary

Return a domain result or typed failure rather than exposing `HttpResponse` to
application logic:

```kotlin
sealed interface LookupResult {
    data class Found(val value: LookupValue) : LookupResult
    data object Missing : LookupResult
}

class LookupClient(
    private val httpClient: HttpClient,
    private val config: LookupConfig,
    private val tokenProvider: TokenProvider,
) {
    suspend fun lookup(id: String, callId: String): LookupResult {
        val response = httpClient.get("${config.baseUrl}/lookup/$id") {
            bearerAuth(tokenProvider.token(config.target))
            header(config.callIdHeader, callId)
        }

        return when (response.status) {
            HttpStatusCode.OK -> LookupResult.Found(parse(response.bodyAsText()))
            HttpStatusCode.NotFound -> LookupResult.Missing
            else -> error("Lookup service returned ${response.status.value}")
        }
    }
}
```

The URL shape and string ID are illustrative. Follow the repository's request
builder, DTOs, serializer, and identity policy. Do not put personal identifiers
in a URL if the contract can derive identity from the token.

Enumerate statuses when several downstream outcomes are meaningful. When only
2xx is valid, check that explicitly. GraphQL and similar protocols may carry
errors in a successful HTTP response, so inspect both transport and protocol
semantics. Include the downstream name and status in operational failures, but
not its raw body.

## Timeouts, retries, and circuit breaking

Set timeout budgets from the caller's deadline and the downstream SLO. Distinguish
connect, request, and socket timeouts. A default or absent timeout is a fact to
surface, not permission to choose an arbitrary number.

Retry only failures that are both transient and safe to repeat. GET is commonly
safe; a writing POST needs an idempotency key or a proven idempotent contract.
Use bounded attempts, backoff with jitter, and a total budget. Ensure Ktor's
retry behavior does not duplicate a retry already owned by a higher layer.

Ktor has no universal built-in circuit-breaker contract. Introduce a resilience
library only after a deliberate dependency and operational design. Avoid adding
a shared-client retry or breaker that also changes token acquisition.

## Correlation, authentication, and privacy

- Propagate the repository's existing call ID or event ID. Do not mint a new ID
  when a stable correlation value already exists.
- Obtain tokens through the established provider with a target or scope from
  configuration. Never cache or store a bearer token in client state unless the
  token provider explicitly owns that cache.
- Log downstream name, status, latency, attempt, and correlation ID. Never log
  authorization headers, national identity numbers, request or response bodies,
  or query strings that can contain personal data.
- Serialization exceptions may embed the input. When the body can contain
  personal data, throw a sanitized error without retaining an unsafe cause.

## Tests

Use the repository's existing client test approach, such as Ktor `MockEngine` or
a local stub. Cover request method and headers without exposing tokens, every
meaningful status mapping, malformed success bodies, timeout, retry boundaries,
idempotency behavior, correlation propagation, and client close. Test a shared
client change against all critical downstreams it affects.
