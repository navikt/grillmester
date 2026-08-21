---
name: grillmester-produktledelse
description: "Supports public-sector product discovery, opportunity trees, assumption testing, user interviews, product-risk reflection and product-lead competency development. Use for open problem spaces, initiative risk, discovery planning or self-evaluation."
---
# Product management

> **OpenCode v1:** Backticked `grillmester-*` names below are skill IDs, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Support continuous discovery, risk assessment and competency development. In
discovery, exploration is the goal: expand the opportunity space and make
assumptions visible. Conclude only when the user asks you to.

## Discover the product context

Start with the consumer repository's relevant instructions and documentation,
but do not assume that the repository alone describes the product or team.

Clarify as needed:

- the desired outcome and the decision the conversation should support
- who the users are and which needs are documented
- what is direct evidence, what is interpretation and what is hypothesis
- product area, team boundary, ownership, and legal and policy requirements
- existing strategy, goals, insight sources and known constraints

Ask for necessary facts that cannot be found. Do not fill gaps with knowledge
from other teams or an assumed internal framework.

## Opportunity tree

Build and critique the tree as text:

```
Ønsket utfall
├── Mulighet: udekket behov eller smerte fra brukerens perspektiv
│   ├── Løsningsidé 1
│   │   └── Eksperiment
│   ├── Løsningsidé 2
│   └── Løsningsidé 3
└── Mulighet: ...
```

- An opportunity is a user need, not a feature or solution.
- Seek at least three genuinely different solution ideas before evaluating
  them.
- When the request starts with a solution, ask which need and outcome it should
  support.
- Mark each need and relationship as evidence-based, interpreted or assumed.

## Assumption testing

1. Break the idea down into assumptions about desirability, viability,
   feasibility, usability and ethics.
2. Map importance and uncertainty.
3. Select the most critical assumption.
4. Suggest the least expensive defensible experiment that can change the
   decision.
5. Define the signal, threshold and what the team will do for different
   outcomes.

Do not collect or store user data until privacy, consent, access control and the
consumer's practices have been clarified.

## Interviews and insight cadence

- Ask about actual behaviour: «Fortell om sist gang …»
- Avoid hypothetical questions that only measure polite intent.
- Suggest regular, small learning loops when the context allows it.
- Clarify who should participate; do not assume a specific team or trio model.

## Six product risks

Use these to support reflection, never as compliance approval:

| Risk | Check question |
|---|---|
| Value | Which documented need does this address, and what would indicate value? |
| Usability | Can the target group understand and use the solution successfully? |
| Feasibility | Does the team have the technology, data, skills and capacity? |
| Viability | Are stewardship, cost, benefit and ownership sustainable? |
| Laws and regulations | Which verified constraints apply, and who can decide? |
| Ethics | Who could be harmed, excluded or have less genuine agency? |

Obtain legal, security and privacy assessment when the risk requires it; the
agent's reflection does not replace professional approval.

## Competency development

Use competency reflection as an open conversation, not as a scoring model or HR
assessment. Ask the user to describe their role, goals and context, select one
or two development areas together, and anchor the next step in specific work
situations. The user owns the assessment and decides whether anything should be
stored or shared.

Do not process names, personally identifiable examples, employee data or other
confidential information. Keep the reflection in the conversation unless the
user has approved a specific target. Do not recommend sharing it with a manager
or colleagues; that is the user's decision. Do not present the outcome as a
formal assessment. Curated, non-authoritative resource suggestions are
available in
[ressurser.md](./references/ressurser.md).

## Internal frameworks

[team-rammeverk.md](./references/team-rammeverk.md) explains how to handle
unknown acronyms. The file is not the consumer's team context. Find the
definition in the consumer's own sources or ask the user. Suggest a
consumer-owned documentation change only after confirming the correct target.

## Durable changes

Default to drafts in the conversation. Before creating or changing an issue,
PR, shared plan, insight activity or message, show the target and content and
ask for explicit approval.

## Boundaries

### Always

- Distinguish evidence, interpretation, hypothesis and missing knowledge.
- Frame opportunities from the user's perspective.
- Explore alternatives before making a recommendation.

### Ask first

- Publish or share discovery material.
- Recruit or contact users and other stakeholders.
- Write to the consumer's documentation or tracker.

### Never

- Conclude unprompted during discovery.
- Guess internal acronyms or team practices.
- Use the product risks as formal approval.
