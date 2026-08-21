# Auth diagnosis: 401 and 403

Use only the auth mechanisms verified in the consumer's code and deployment
configuration. TokenX, Entra ID, ID-porten, Maskinporten and Texas are possible
Nais patterns, not defaults.

## Establish the failing boundary

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

Do not paste or log a raw token. If claim inspection is necessary, use an
approved secure method and record only non-sensitive fields needed for the
diagnosis, such as issuer, audience, expiry and authorized party.

## 401 tree

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
clock issue. Do not assume a cache implementation or renewal skew; inspect it.

## 403 tree

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

## Texas or another sidecar

Only diagnose a sidecar when deployment evidence shows one is used. Compare:

1. sidecar health and injected endpoint variable names
2. application request shape and target
3. sidecar response status with sensitive content suppressed
4. application caching and error handling

Running a request inside a production pod can expose credentials or change
state. Show the exact redacted command and ask for approval first.

## Interpretation table

| Observation | Check next |
|---|---|
| wrong issuer | caller flow and recipient's documented provider |
| wrong audience | caller target and recipient identity |
| expired token | cache lifetime, clock and renewal behavior in actual code |
| discovery/JWKS unreachable | outbound policy, DNS and provider status |
| no HTTP response, timeout or reset | DNS, routing, ingress and service-to-service access policy |
| proxy- or sidecar-generated 401/403 | verified proxy/sidecar configuration and redacted diagnostics |
| app-level denial | verified roles, groups, scopes and route policy |

Any policy or code change is a proposal until the user approves the exact
target and diff. For pod/network symptoms, continue with
[pod-diagnose.md](./pod-diagnose.md).
