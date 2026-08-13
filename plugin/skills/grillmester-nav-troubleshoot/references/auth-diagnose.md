# Auth diagnosis: 401 and 403

Use only the auth mechanisms verified in the consumer's code and deployment
configuration. TokenX, Entra ID, ID-porten, Maskinporten and Texas are possible
Nais patterns, not defaults.

## Establish the failing boundary

- caller and recipient workload
- route or operation
- environment, cluster and namespace on both sides
- expected identity provider, flow, audience and authorization rule
- whether 401/403 comes from ingress/network policy, token validation or
  application authorization

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
├── Is the request rejected before application code?
│   ├── Yes → inspect actual Nais access policy and generated network policy
│   └── No → continue
├── Is the confirmed caller allowed by the deployed inbound policy?
│   ├── No → propose the narrowest required rule
│   └── Yes → continue
├── Does application authorization require roles, groups or scopes?
│   ├── Yes → compare redacted claims with verified rules
│   └── No → continue
└── Is a downstream service returning 403?
    └── Repeat the boundary analysis for that caller-recipient pair
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
| network-policy denial | deployed inbound rule for the confirmed caller |
| app-level denial | verified roles, groups, scopes and route policy |

Any policy or code change is a proposal until the user approves the exact
target and diff. For pod/network symptoms, continue with
[pod-diagnose.md](./pod-diagnose.md).
