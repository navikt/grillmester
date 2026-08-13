# Forward Lumi submissions through a BFF

Use this reference only after resolving the current Lumi submission contract
and the consumer's auth and server framework.

## Resolve the contract

Record evidence for:

| Fact | Evidence source |
|---|---|
| Browser request schema and size limit | resolved package types and consumer route |
| Incoming user or workload identity | consumer auth configuration |
| Exchange flow and target audience | current NAV auth and Lumi owner contract |
| Upstream host, path, method, and payload | current Lumi owner documentation |
| Success and error responses | upstream contract or verified test |
| Timeout, retry, and idempotency semantics | upstream contract and consumer policy |

Leave a fact unknown rather than copying a value from another application.

## Browser-to-BFF boundary

Post to an established same-origin route and rely on the consumer's existing
browser authentication and CSRF model. Validate content type, schema, question
IDs, text lengths, option values, total size, and any accepted context. Reject
unexpected fields when the local contract supports doing so.

Do not trust browser-supplied identity, upstream destination, audience, auth
provider, or survey ownership. Keep those server-controlled.

## Token exchange and forwarding

Use the consumer's current auth library or sidecar integration. Extract and
validate the incoming identity according to its existing boundary, exchange it
for the verified upstream audience when an on-behalf-of flow is required, and
send only the accepted payload over the verified destination.

For Node, Kotlin/Ktor, or Kotlin/Spring, follow the framework and auth patterns
already present in the repository. Do not invent a local sidecar URL, identity
provider value, environment variable name, request helper, or annotation.

Set an explicit timeout inside the browser request budget. Retry only when the
upstream contract says a repeated submission is safe or provides an
idempotency mechanism. Avoid turning one user action into duplicate feedback.

## Failure and observability

- Map missing or invalid identity to the consumer's normal unauthenticated or
  unauthorized response.
- Treat token-exchange and upstream failures separately so operations can
  diagnose them without exposing internals to the browser.
- Log a correlation identifier, stage, status class, latency, and safe survey
  identifier only when permitted. Never log bearer tokens, raw payloads,
  feedback text, personal data, or unbounded exception bodies.
- Bound upstream error reads and return a stable consumer-owned error shape.

## Verify

Test payload rejection, missing identity, wrong or rejected claims, token
exchange failure, timeout, upstream 4xx and 5xx, malformed upstream response,
and success. Use an approved test double or environment; never call production
merely to prove wiring.
