# Local authentication test patterns

Inspect the repository's current test framework, HTTP engine, configuration
format, and auth integration before choosing a mock. Reuse existing helpers and
fixtures. Never weaken production validation or require real credentials for a
test.

## Outgoing sidecar calls

When the application calls Texas or another token sidecar over HTTP, test the
provider through the HTTP client's mock engine or a local stub. Configure the
provider with the stub URL through the same typed configuration boundary used
in production.

For a Ktor client, `MockEngine` can return a token response and capture the
request:

```kotlin
val engine = MockEngine { request ->
    respond(
        content = """{"access_token":"synthetic-token","expires_in":3600,"token_type":"Bearer"}""",
        status = HttpStatusCode.OK,
        headers = headersOf(HttpHeaders.ContentType, "application/json"),
    )
}

val client = HttpClient(engine)
```

Assert the provider, target, content type, failure mapping, and any cache
behavior. Advance a controllable clock to test expiry skew instead of waiting.
Do not assert or print a production-shaped secret value.

## Incoming JWT validation

When the repository uses NAV token-support, `no.nav.security:mock-oauth2-server`
can provide a local OIDC issuer. Add it only if the repository does not already
have a supported equivalent.

```kotlin
val server = MockOAuth2Server().apply { start() }
val token = server.issueToken(
    issuerId = "tokenx",
    subject = "test-subject",
    claims = mapOf("pid" to "<SYNTHETIC_ID>", "acr" to "Level4"),
).serialize()
```

Point the test-only discovery URL and accepted audience to the mock issuer, send
the token through the repository's normal test HTTP client, and stop the server
in the test framework's cleanup hook. Cover at least valid token, wrong issuer,
wrong audience, expired token, missing required claim, and insufficient
authorization.

## Local containers

Use a containerized mock OAuth server only when the repository's local or
end-to-end environment already uses containers or must exercise a sidecar.
Keep client IDs, issuer names, ports, and generated keys as local configuration,
not constants copied from production.

## Synthetic identities

Use explicit placeholders in documentation. When runnable code needs a valid
Norwegian identity-number format, use a value from an approved synthetic test
series and label it as synthetic. Never use a real person's identity number in
source, logs, snapshots, or examples.
