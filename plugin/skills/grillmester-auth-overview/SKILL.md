---
name: grillmester-auth-overview
description: Set up, change, or troubleshoot authentication and authorization in a NAV backend. Use for incoming JWT validation, TokenX OBO, Azure or Entra ID M2M, Texas, Maskinporten, Wonderwall, accessPolicy, protected endpoints, 401 or 403 errors, and issuer or audience mismatches.
license: MIT
---

# Establish an authentication design

## Inspect the repository before choosing a mechanism

Read the deployed Nais manifests, runtime configuration, build dependencies,
authentication and HTTP-client code, protected routes, tests, and local-run
setup. Determine from code which identity providers, validation libraries,
sidecars, claim names, endpoint variables, token caches, and access policies
already exist.

Do not infer the language, framework, package, config format, manifest path, or
auth library. Do not use a consumer repository's agent instructions as a source
of runtime facts. If the repository has no auth implementation, establish the
caller, required identity context, downstream audience, and deployment
environment with the user before selecting one.

## Separate incoming and outgoing auth

Incoming authentication proves who called this service. Authorization then
decides what that identity may do. Outgoing authentication obtains a token for
a service this application calls. Do not treat an outbound token provider as
proof that inbound requests are protected.

Use the caller and identity-context decision tree in
[references/decision-tree.md](references/decision-tree.md). The central rule is:

- preserve user context with TokenX on-behalf-of when downstream authorization
  needs that user;
- use Azure or Entra ID client credentials for pure NAV machine-to-machine
  calls without user context;
- use Maskinporten for the external organization flows for which it is
  intended;
- follow the repository's Wonderwall or direct-token pattern for browser login.

## Keep platform and application configuration aligned

Enable only the mechanism the design requires and keep the matching Nais
`accessPolicy` rules explicit. These snippets are shapes, not repository facts:

```yaml
azure:
  application:
    enabled: true

tokenx:
  enabled: true

accessPolicy:
  inbound:
    rules:
      - application: <calling-application>
        namespace: <calling-namespace>
  outbound:
    rules:
      - application: <downstream-application>
        namespace: <downstream-namespace>
```

Validate that code and manifest agree on identity provider, issuer, audience,
claims, caller allow-list, and downstream target. A platform permission is not
application authorization, and application token validation does not replace
network policy.

## Validate incoming tokens

Use the authentication integration already established in the repository. In
a Ktor service this may be NAV token-support integrated with Ktor
`Authentication`, or Texas introspection through its Nais-injected endpoint.
Do not hand-roll JWT validation or add a second auth stack without an explicit
decision.

Validate at least signature, issuer, audience, expiry and not-before. Then
validate the claims required by the operation:

- `pid` can carry a person's national identity number; treat it as sensitive
  and never log it;
- `NAVident` identifies a case worker in relevant Azure flows;
- `oid` identifies an Azure object;
- `azp` identifies the authorized party and must be checked against the
  intended callers for M2M access;
- `acr` must meet the required login level when the operation needs one.

Derive the acting identity from validated claims, not from request fields.
Keep health and metrics routes outside user authentication only when the
repository and platform probe design require that boundary.

## Obtain outgoing tokens

Use the endpoint and target configuration injected by Nais and read through
the repository's existing configuration layer. Never hardcode a sidecar host,
port, issuer, client ID, secret, audience, or cluster target.

Typical Texas request shapes are:

```text
POST $NAIS_TOKEN_EXCHANGE_ENDPOINT
{ "identity_provider": "tokenx", "target": "<cluster>:<namespace>:<app>", "user_token": "<incoming-token>" }

POST $NAIS_TOKEN_ENDPOINT
{ "identity_provider": "<configured-m2m-provider>", "target": "api://<cluster>.<namespace>.<app>/.default" }
```

Confirm the exact endpoint variable, content type, provider name, target format,
and response shape from current authoritative Nais documentation and the
repository implementation. Preserve an existing token cache. If a client-side
cache is necessary, key it by target and refresh before expiry; never stack a
second cache on top of a provider that already owns caching.

## Diagnose 401 and 403 systematically

1. Reproduce without printing the token.
2. Confirm which layer rejected the request: ingress or access policy, token
   validation, claim validation, or resource authorization.
3. Compare environment, issuer, audience, target, provider, expiry, `azp`, and
   required claims with the deployed manifest and code.
4. Verify that the caller's outbound policy and callee's inbound policy agree.
5. Add or update the smallest safe test that proves the failure mode.

For local and automated test patterns, read
[references/local-auth-mock.md](references/local-auth-mock.md).

## Deliver evidence

Return the caller flow, selected mechanism, manifest/code alignment, protected
route or outgoing target, security assumptions, tests run, and unresolved
authorization questions. Run the bundled security review workflow for changes
to validation, claims, scopes, or access policy.

## Boundaries

### Always

- Validate incoming tokens and authorize the resulting identity.
- Keep access policy and auth code aligned.
- Source endpoints and credentials through deployed configuration.
- Use HTTPS outside the pod boundary.

### Ask first

- Change production access policy, audience, claims, or OAuth scopes.
- Switch auth libraries or sidecar strategy.
- Change which identity is authoritative for an operation.

### Never

- Hardcode or log tokens, secrets, national identity numbers, or case-worker
  identifiers.
- Disable validation for tests or local development.
- Implement OAuth or JWT verification from scratch when a supported integration
  exists.
- Assume authentication also grants authorization.
