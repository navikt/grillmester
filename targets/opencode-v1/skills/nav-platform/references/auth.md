# Authentication and authorization

## Contents

- Inspect the repository before choosing a mechanism
- Separate incoming and outgoing auth
- Authentication decision tree
- Keep platform and application configuration aligned
- Validate incoming tokens
- Obtain outgoing tokens
- Auth diagnosis: 401 and 403
- Deliver evidence
- Boundaries

## Inspect the repository before choosing a mechanism

Read the deployed Nais manifests, runtime configuration, build dependencies,
authentication and HTTP-client code, protected routes, tests, and local-run
setup. Determine from code which identity providers, validation libraries,
sidecars, claim names, endpoint variables, token caches, and access policies
already exist.

Do not infer the language, framework, package, config format, manifest path, or
auth library. Treat recognized consumer instructions as declared context and
rationale, then verify effective and volatile auth facts against code,
manifests, tests, runtime configuration and current primary documentation.
Stop and surface a conflict instead of silently choosing one source. If the repository has no auth implementation, establish the
caller, required identity context, downstream audience, and deployment
environment with the user before selecting one.

## Separate incoming and outgoing auth

Incoming authentication proves who called this service. Authorization then
decides what that identity may do. Outgoing authentication obtains a token for
a service this application calls. Do not treat an outbound token provider as
proof that inbound requests are protected.

Use the caller and identity-context
[decision tree](#authentication-decision-tree). The central rule is:

- preserve user context with TokenX on-behalf-of when downstream authorization
  needs that user;
- use Azure or Entra ID client credentials for pure Nav machine-to-machine
  calls without user context;
- use Maskinporten for the external organization flows for which it is
  intended;
- follow the repository's Wonderwall or direct-token pattern for browser login.

## Authentication decision tree

First identify who initiates the request, whether a user identity must survive
the call chain, and whether this service validates an incoming token or obtains
an outgoing one.

### Incoming caller

| Caller | Typical Nav mechanism | Platform signal to verify |
|---|---|---|
| Nav service carrying user context | TokenX | `tokenx.enabled` and explicit access policy |
| Nav service or batch without user context | Azure or Entra ID client credentials | `azure.application.enabled` |
| Case worker through a browser flow | Azure or Entra ID, often with Wonderwall | sidecar and application configuration |
| Citizen through a frontend or BFF | ID-porten at login, commonly TokenX from frontend to backend | actual frontend/backend exchange design |
| External organization or system | Maskinporten | configured consumed scopes |
| Altinn 3 system user | Maskinporten plus system-user flow | system-user configuration and authorization |

These are selection aids, not proof of the repository's current setup. Verify
the deployed manifest, code, and current platform documentation.

### Outgoing call

| Must user identity travel downstream? | Typical mechanism | Core property |
|---|---|---|
| Yes | TokenX exchange, on behalf of the user | user claims remain available for downstream authorization |
| No | Azure or Entra ID client credentials | the application acts as itself |

The common error is using client credentials where per-user authorization is
required. The downstream then knows only the application, not the user.

```text
Wrong for per-user authorization:
user -> frontend -> application M2M token -> backend

Typical OBO flow:
user -> frontend -> user token -> backend -> TokenX exchange -> downstream
```

Confirm who performs each exchange and which token the backend actually
receives. Do not enable ID-porten directly on a backend merely because a citizen
started the browser flow.

### Authorization questions after mechanism selection

- Which application, user, organization, role, or purpose may perform the
  operation?
- Which validated claim is authoritative?
- Does `accessPolicy` permit exactly the intended application path?
- Does the downstream audience match the configured target?
- Is a high login level required and checked through `acr`?

Authentication mechanism selection is incomplete until these questions have
answers and tests.

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
a Ktor service this may be Nav token-support integrated with Ktor
`Authentication`, or Texas introspection through its Nais-injected endpoint.
Do not hand-roll JWT validation or add a second auth stack without an explicit
decision.

Texas introspection answers HTTP 200 for a well-formed request, valid token or
not, so read `active` in the body, not the status. If Texas itself fails, answer
5xx, not 401, so an outage does not look like a rejected token.

Validate at least signature, issuer, audience, expiry and not-before. Then
validate the claims required by the operation:

- `pid` can carry a person's national identity number; treat it as sensitive
  and never log it;
- `NAVident` identifies a case worker in relevant Azure flows;
- `oid` identifies an Azure object;
- `azp` identifies the authorized party and must be checked against the
  intended callers for M2M access;
- `client_id` identifies the calling application in TokenX tokens as
  `<cluster>:<namespace>:<app>`; check it when authorizing per calling app;
- `acr` must meet the required login level when the operation needs one. Nais
  maps some values for compatibility, so check both forms, such as
  `idporten-loa-high` and `Level4`.

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
repository implementation. Preserve an existing token cache. Only the token
provider may cache or store a bearer token, and never stack a second cache on one
that already caches. A cache the provider owns keys by target, and by user for a
user-bound token, and refreshes before expiry. Texas caches tokens itself; if a
target denies a token after its access policy changed, retry once with
`skip_cache` set to `true`.

## Auth diagnosis: 401 and 403

Use only the auth mechanisms verified in the consumer's code and deployment
configuration. TokenX, Entra ID, ID-porten, Maskinporten and Texas are possible
Nais patterns, not defaults.

1. Reproduce without printing the token.
2. Identify the verified producer of the HTTP response from redacted evidence:
   ingress or auth proxy, sidecar, application, or downstream service.
3. Compare environment, issuer, audience, target, provider, expiry, `azp` or
   `client_id`, and required claims with the deployed manifest and code.
4. Diagnose ingress separately. Use `accessPolicy` for service-to-service
   connectivity and applicable token-grant context, and NetworkPolicy for
   network-connectivity evidence. Do not presume that either produced an
   observed HTTP status; a blocked network path commonly produces no HTTP
   response at all.
5. Verify that the caller's outbound policy and callee's inbound policy agree.
6. Add or update the smallest safe test that proves the failure mode.

### Establish the failing boundary

- caller and recipient workload
- route or operation
- environment, cluster and namespace on both sides
- expected identity provider, flow, audience and authorization rule
- the verified producer of the HTTP response: ingress or auth proxy, sidecar,
  application, or downstream service

Identify the response producer from redacted response metadata and tracing or
log evidence before interpreting the status. Nais `accessPolicy` contributes
service-to-service connectivity and, where applicable, token grants; generated
NetworkPolicy enforces network connectivity. Neither is generally the producer
of an HTTP 401 or 403. A blocked network path normally means that no HTTP
response arrives. Diagnose ingress separately, and do not infer the rejecting
layer from the status alone.

Keep raw tokens outside model context. If claim inspection is necessary, use
an approved method that returns only non-sensitive fields needed for diagnosis,
such as issuer, audience, expiry and authorized party where permitted. Select
those fields before output reaches the model, following the
[data-access boundary](diagnosis.md#data-access).

### 401 tree

```text
401 Unauthorized
├── Did the request include the expected credential?
│   ├── No → inspect caller configuration and propagation
│   └── Yes → continue
├── Does the recipient expect this auth mechanism?
│   ├── No → identify the documented flow; do not convert by guesswork
│   └── Yes → continue
├── Do issuer, audience and expiry match verified recipient configuration?
│   ├── No → compare caller target and recipient validation settings
│   └── Yes → continue
├── Can the recipient reach required discovery/JWKS endpoints?
│   ├── No → inspect declared outbound access and platform status
│   └── Yes → continue
└── Does the application reject the token?
    └── Trace the verified validation code and redacted error details
```

Check whether the failure began after deploy, key rotation, target change or
clock issue. Inspect the actual cache implementation and renewal skew.

### 403 tree

```text
403 Forbidden
├── Which verified component produced the HTTP response?
│   ├── ingress/auth proxy/sidecar → inspect that component's verified rules
│   ├── application → continue
│   └── downstream service → repeat the boundary analysis there
├── Does application authorization require roles, groups or scopes?
│   ├── Yes → compare redacted claims with verified rules
│   └── No → continue
└── Is there actually no HTTP response?
    └── diagnose DNS, routing, ingress and accessPolicy/NetworkPolicy separately
```

### Texas or another sidecar

Only diagnose a sidecar when deployment evidence shows one is used. Compare:

1. sidecar health and injected endpoint variable names
2. application request shape and target
3. sidecar response with sensitive content suppressed; Texas introspection
   answers 200 for a well-formed request, so read `active` and `error`, not the
   status
4. application caching and error handling

Running a request inside a production pod can expose credentials or change
state. Show the exact redacted command and ask for approval first.

### Interpretation table

| Observation | Check next |
|---|---|
| wrong issuer | caller flow and recipient's documented provider |
| wrong audience | caller target and recipient identity |
| expired token | cache lifetime, clock and renewal behavior in actual code |
| discovery/JWKS unreachable | outbound policy, DNS and provider status |
| no HTTP response, timeout or reset | DNS, routing, ingress and service-to-service access policy |
| proxy- or sidecar-generated 401/403 | verified proxy/sidecar configuration and redacted diagnostics |
| 401 while Texas itself fails | an outage shown as a rejected token; a Texas failure should give 5xx |
| target denies a cached token after an access-policy change | one retry with `skip_cache` set to `true` |
| login level rejected | both `acr` forms, such as `idporten-loa-high` and `Level4` |
| app-level denial | verified roles, groups, scopes and route policy |

Any policy or code change is a proposal until the user approves the exact
target and diff. For pod/network symptoms, continue with
[Pod diagnosis](nais.md#pod-diagnosis).

For local and automated test patterns, read
[local-auth-mock.md](local-auth-mock.md).

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
