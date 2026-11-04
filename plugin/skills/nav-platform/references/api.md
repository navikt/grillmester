# APIs on Nais

This reference holds only the Nav-specific parts of an API change.

## Find the consumers

Discover service-to-service consumers represented by Nais
`accessPolicy.inbound`, ingress/external exposure and authentication
separately, and actual consumers from traffic, telemetry, code search, and
published usage. Use all applicable sources; they can differ.

## Apply Nav boundaries

- Keep Nais `accessPolicy.inbound` explicit for internal callers and match it
  with the callers' outbound policy. It governs service-discovery traffic and
  token grants; it does **not** restrict traffic arriving through an ingress.
  Analyze ingress exposure, edge authentication and application authorization
  separately. An empty inbound policy denies the covered internal callers; do
  not use wildcards without a deliberate security review.
- Validate the token mechanism selected by the repository; see
  [auth.md](auth.md). Derive user identity from the validated token, not from
  request input.
- Keep national identity numbers, names, tokens, and other personal data out
  of URLs, query parameters, logs, and error details.
- Register a discoverable API in Nav's API catalogue when it is intended for
  reuse beyond its immediate consumers.

## Boundaries

### Ask first

- Any breaking change consumed outside the repository.
- Removing a permitted consumer or changing production access policy.
- Exposing an API outside its current trust boundary.
