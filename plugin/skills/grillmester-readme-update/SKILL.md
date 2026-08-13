---
name: grillmester-readme-update
description: "Creates or updates repository README documentation from verified implementation and operational evidence. Use when a README is missing, stale or needs accurate coverage of purpose, setup, interfaces, data flows, deployment, observability or ownership."
license: MIT
---

# README update

Describe current behavior, never a desired future presented as current state.

## Discover the documentation contract

1. Locate the relevant README and consumer-owned documentation instructions.
   Do not assume one root file or a fixed docs layout.
2. Discover the required language, audience, section conventions, ownership
   details and generated/manual boundaries.
3. Read the existing README and preserve accurate, intentional content.
4. If target, language, audience or publication scope remains ambiguous, ask.

## Build an evidence map

Inspect only sources that exist and are relevant:

- build and dependency definitions for stack and supported commands
- application code and schemas for interfaces and behavior
- deployment configuration for environments, auth, resources and integrations
- automation for actual CI/CD workflows
- migrations or data definitions for owned data
- observability configuration for verified dashboards, probes and alerts
- maintained documentation for domain purpose, operations and ownership

Find sources by role and content, not by a hardcoded path or stack. Record
support for consequential claims. Ask for product purpose, contact information
or private links that cannot be derived safely.

## Choose only useful sections

| Section | Include when |
|---|---|
| Purpose | Always; state what the software does and for whom |
| Status or support | The repository documents lifecycle or ownership |
| Development | Verified setup, run and test instructions exist |
| Interfaces | The repository exposes APIs, events, jobs or libraries |
| Data and dependencies | They materially explain behavior or operation |
| Deployment and configuration | Readers need it and evidence exists |
| Observability | Verified dashboards, signals or runbooks exist |
| Architecture visual | Three or more relationships are clearer visually |
| Further reading | A maintained document is directly relevant |

Do not add badges, contact channels, dashboards, environment links or
technology lists unless they are verified and useful.

## Update workflow

1. Compare current text with the evidence map.
2. Mark statements as keep, update, remove or unresolved.
3. Preserve manual operational knowledge until it is disproven or the user
   approves removal.
4. Write the smallest coherent update.
5. Validate commands and links where feasible, and review the diff for
   unsupported claims.

For a new README, start with purpose and the shortest verified path to use or
develop it. Add sections only when evidence and reader need justify them.

## Content rules

- Use the consumer's documented language and terminology.
- Prefer stable commands or pointers over copied output that will quickly age.
- Describe interfaces from code or generated contracts, not memory.
- Use service, topic, database, environment and auth names only after discovery.
- Use Mermaid only when it materially clarifies verified relationships.
- Do not duplicate an entire schema, runbook or ADR catalogue.
- Make uncertainty explicit instead of filling gaps with plausible defaults.

## Approval boundary

The requested local README edit is allowed. Before publishing, committing,
opening a PR, commenting, or editing other docs, show the diff and get approval.

## Grenser

### Alltid

- Cross-check consequential statements against current repository evidence.
- Preserve accurate manual content.
- Validate local links and commands proportionally to risk.

### Spør først

- Remove substantial manual sections.
- Choose between conflicting product descriptions or language rules.
- Add an unverified private link, owner or contact channel.
- Perform any external write.

### Aldri

- Invent endpoints, data stores, auth, environments, owners or dashboards.
- Assume a framework, package, manifest or documentation path.
- Replace a repository-specific README with a generic template.
