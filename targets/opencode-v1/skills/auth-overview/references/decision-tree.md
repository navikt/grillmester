# Authentication decision tree

First identify who initiates the request, whether a user identity must survive
the call chain, and whether this service validates an incoming token or obtains
an outgoing one.

## Incoming caller

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

## Outgoing call

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

## Authorization questions after mechanism selection

- Which application, user, organization, role, or purpose may perform the
  operation?
- Which validated claim is authoritative?
- Does `accessPolicy` permit exactly the intended application path?
- Does the downstream audience match the configured target?
- Is a high login level required and checked through `acr`?

Authentication mechanism selection is incomplete until these questions have
answers and tests.
