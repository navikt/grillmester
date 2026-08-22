---
name: grillmester-lumi-survey
description: "Integrate or review @navikt/lumi-survey in a Nav frontend and its backend-for-frontend. Use for survey selection and configuration, package setup, widget rendering, submission transport, TokenX or Azure/Entra token exchange, Nais accessPolicy, privacy-safe context, and end-to-end verification of Lumi feedback."
---
# Integrate Lumi Survey from current evidence

> **OpenCode v1:** Backticked `grillmester-*` names below are skill IDs, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Treat the installed package types, current Lumi owner contract, repository
patterns, and environment manifests as the source of truth. Package exports,
peer dependencies, CSS entry points, endpoints, audiences, auth support,
dashboard locations, and access procedures can change; never recover them from
an old example or another application.

## Map the consumer first

Inspect repository instructions, package manifest and lockfile, package-manager
and registry configuration, framework and rendering model, global styles,
existing survey or feedback code, BFF routes, authentication helpers, tests,
Nais manifests, and environment configuration. If the package is installed,
read its resolved version, exported types, package documentation, and peer
requirements. If it is not installed, verify the current authoritative Lumi
documentation and package metadata before proposing a dependency change.

Record:

- the feedback objective, user group, page or journey, and success measure;
- the selected package API and why it matches the resolved version;
- where the browser renders the widget and where same-origin submissions enter
  the server;
- the real identity flow, upstream contract owner, environment destinations,
  and required network access;
- the data fields, optional context, consent or storage behavior, retention,
  access, and deletion expectations.

Ask only for product or governance choices that cannot be derived from the
consumer or authoritative owner documentation.

## Design the smallest useful survey

Load [the survey-design reference](references/survey-design.md) when selecting
the survey shape, questions, branching, context, storage behavior, or events.
Use `grillmester-klarsprak`, `grillmester-aksel-design`, and
`grillmester-accessibility-review` where the change touches user text, layout,
focus, validation, or interaction. Derive components and tokens from the
consumer's installed Aksel version and current primary documentation. Mark
`NEEDS_CONTEXT` instead of guessing when the applicable Aksel or accessibility
contract cannot be verified.

Use the exact configuration types, component exports, presets, props, styles,
and import order supported by the resolved package. Do not assume names from
this skill. Keep the survey focused on one learning objective, minimize free
text and personal data, and provide a usable loading, success, closed, and
failure experience.

## Keep credentials and upstream access on the server

Submit from the browser to an established same-origin BFF boundary. Load
[the backend transport reference](references/backend-transport.md) before
implementing or reviewing token exchange and forwarding.

Derive the incoming token mechanism, on-behalf-of or machine flow, target
audience, upstream host and path, payload schema, response semantics, timeout,
and retry policy from current contracts. Never expose a client secret or
upstream bearer token to browser code, forward a token to the wrong audience,
or log feedback payloads and tokens.

Validate payload size and shape at the BFF boundary. Preserve useful status
semantics without returning upstream internals or sensitive error details to
the browser.

## Configure Nais from the owner contract

Load [the Nais integration reference](references/nais-integration.md) when the
consumer is deployed on Nais. Derive application, namespace, cluster, host,
audience, auth provider, environment mapping, and `accessPolicy` from the
current Lumi service contract and the consumer's manifests. Do not name a team,
application, proxy, URL, path, or environment value without evidence.

An upstream inbound-rule request, owner contact, issue, or configuration change
is an external write. Show the exact target, content, and consequence and get
explicit authorization before sending it.

## Verify each boundary

Run the consumer's focused typecheck, unit or component tests, and required
build gates. Verify:

- the package and peer dependencies resolve through the approved registry;
- the widget renders using the resolved API and remains keyboard and
  screen-reader usable;
- question visibility, dismissal, storage or consent, and success/error events
  match the chosen design;
- the browser calls only the intended same-origin endpoint;
- BFF tests cover authentication, authorization, payload validation, token
  exchange failure, upstream failure, timeout, and success;
- manifests and runtime configuration resolve the verified environment values
  and least-privilege network access;
- no personal data, feedback text, tokens, or high-cardinality identifiers
  enter ordinary logs, metrics, traces, or context tags.

Perform an end-to-end test submission only in an approved environment with
synthetic content and authorized upstream access. Verify receipt through the
current owner-supported method; do not infer success from a local 2xx alone.

## Boundaries

- Ask before adding or upgrading dependencies, changing registry config,
  enabling an identity provider, expanding network policy, or requesting
  upstream access.
- Never invent package APIs, compatibility minimums, feedback endpoints,
  audiences, owner teams, dashboards, CSS paths, or storage rules.
- Never send production feedback or personal data as test material.
- Never turn a product-survey request into broad analytics collection without a
  separately accepted purpose and data contract.
