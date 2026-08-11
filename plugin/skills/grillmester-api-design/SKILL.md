---
name: grillmester-api-design
description: Design or change a backend API contract in NAV. Use for new endpoints, versioning, breaking changes, deprecation, consumer discovery, accessPolicy implications, compatibility gates, or API catalogue publication.
license: MIT
---

# Design an API contract

## Establish repository evidence first

Before proposing a contract, inspect the repository's routes or generated API,
build and framework configuration, published schemas, compatibility checks,
deployment manifests, tests, and contract documentation. Search for every
contract surface: HTTP, generated clients, published libraries, Kafka events,
and files such as OpenAPI or AsyncAPI definitions.

Identify the current framework, versioning mechanism, error shape,
serialization rules, authentication, consumers, and release gates from that
evidence. Do not assume Ktor, Spring, path versioning, a source layout, or that
HTTP is the repository's public contract. If the evidence is missing, ask for
the contract owner and intended consumers before designing the change.

## Define the contract and its owners

Describe:

- the consumer-visible operation, request, response, errors, and invariants;
- authentication and authorization expectations;
- idempotency, pagination, ordering, and retry semantics where relevant;
- the source of truth for the contract and how compatibility is verified;
- the producer, known consumers, and migration owner.

Treat error bodies, headers, status codes, validation rules, generated types,
and library signatures as contract surface when consumers can branch on them.
Follow the repository's existing documentation format rather than imposing a
new one.

## Classify compatibility

Usually breaking:

- removing or renaming an operation, field, enum value, header, or public type;
- changing a field's meaning or type;
- making optional input required or tightening accepted input;
- changing an error shape or status that consumers may handle;
- changing authentication, audience, authorization, or identity semantics.

Usually additive:

- adding an optional input or response field;
- adding an operation without changing shared behavior;
- adding an error code only when consumers already parse unknown values
  defensively.

Repository compatibility tests and published baselines outrank intent. If a
gate rejects a change, handle it as a breaking change or deliberately update
the baseline through the repository's approved process.

## Coordinate a breaking change

1. Discover permitted consumers from Nais `accessPolicy.inbound` and actual
   consumers from traffic, telemetry, code search, and published usage. Use
   both; they can differ.
2. Notify each owning team directly and agree on a transition window.
3. Use the versioning mechanism already established by the repository. For a
   new HTTP version, keep both contracts available during migration when
   practical. For a published library, follow its semantic-version and release
   rules.
4. Mark an HTTP version as deprecated before removal. Use `Deprecation` and
   `Sunset` headers when they fit the existing API and gateway behavior.
5. Remove the old contract only after the agreed window and after observed use
   has stopped.

Record hard-to-reverse contract and migration decisions through the
repository's ADR process after the user accepts the recommendation.

## Apply NAV boundaries

- Keep Nais `accessPolicy.inbound` explicit for internal callers and match it
  with the callers' outbound policy. An empty inbound policy denies callers;
  do not use wildcards without a deliberate security review.
- Validate the token mechanism selected by the repository. For APIs carrying
  user context, validate issuer, audience, signature, expiry, and the relevant
  identity claims. Check `acr` when the operation requires a high login level.
- Derive user identity from the validated token, not from request input.
- Keep national identity numbers, names, tokens, and other personal data out
  of URLs, query parameters, logs, and error details.
- Register a discoverable API in NAV's API catalogue when it is intended for
  reuse beyond its immediate consumers.

## Deliver evidence

Return the changed contract, compatibility classification, consumer list,
migration plan, authorization impact, documentation update, and fresh results
from the repository's contract and test gates. Separate verified consumers
from inferred or unknown consumers.

## Boundaries

### Ask first

- Any breaking change consumed outside the repository.
- Removing a permitted consumer or changing production access policy.
- Exposing an API outside its current trust boundary.

### Never

- Ship an uncoordinated breaking change.
- Invent consumers, versions, routes, packages, or release rules.
- Trust request-provided identity when a validated identity claim exists.
- Put personal data or credentials in URLs, logs, examples, or errors.
