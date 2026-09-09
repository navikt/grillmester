# Configure a Nais consumer for Lumi

Use current Lumi owner documentation and the actual consumer manifests. Values
below are concepts to resolve, not names to paste.

## Resolve environment values

For every deployed environment, verify:

- Lumi application and namespace;
- cluster or supported cross-cluster route;
- service host and submission path;
- supported identity provider and target audience;
- whether a proxy or different application is part of that environment;
- which consumer identity the upstream permits;
- the owner process for inbound access and end-to-end verification.

Keep these values in the consumer's established configuration mechanism. Use
typed application configuration and validate required values without logging
them. Do not introduce arbitrary environment-variable names when the repository
already has a convention.

## Network and identity controls

Add the narrow outbound `accessPolicy` rule supported by the observed flow,
using the verified application, namespace, and cluster. Enable TokenX,
Azure/Entra, or another identity integration only when the chosen flow and
current platform contract require it.

Network policy permits connectivity; it does not validate the user, authorize
the consumer, or replace token audience and claim checks. Verify all layers.

The upstream may also require an inbound consumer rule or registration. Treat
that as an owner-controlled external change: prepare the exact consumer
application, namespace, environments, identity flow, purpose, and requested
access; show the destination and draft; obtain explicit authorization; then
verify the resulting access rather than assuming the request succeeded.

## Deployment verification

Before rollout, validate manifests with the repository's normal gates and
confirm that dev and production do not accidentally share destinations,
audiences, credentials, or data. In an approved non-production environment,
verify DNS or service routing, network access, token exchange, upstream
authorization, submission response, and receipt through the owner-supported
method. Use synthetic feedback and preserve privacy-safe evidence.
