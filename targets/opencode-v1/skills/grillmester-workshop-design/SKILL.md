---
name: grillmester-workshop-design
description: "Designs outcome-driven workshops, meetings, retrospectives, foundation sprints and team-health follow-up with facilitation plans and tool-neutral board structures. Use when a group needs exploration, alignment, a decision or concrete follow-up."
---
# Workshop design

> **OpenCode v1:** Backticked `grillmester-*` names below are skill IDs, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Design meetings and workshops with a clear outcome, genuine involvement and
follow-up. By default, deliver a facilitation plan and a tool-neutral
collaboration surface in text.

## Discover the context

Read relevant consumer-owned instructions and documents, and clarify one point
at a time:

1. **Background:** what has happened, and why now?
2. **Desired outcome:** what specifically should be different after the
   session?
3. **Participants and roles:** who participates, decides and facilitates, and
   which power or safety dynamics must be accommodated?
4. **Constraints:** time, physical/digital/hybrid format, accessibility,
   language and time zones.
5. **Tools and documentation:** what does the team use, who should have access,
   and what may be stored?

Do not assume the team, meeting tool, collaboration surface, decision model or
reporting requirements. Ask when facts are missing.

## The BØRA gate

Do not create a facilitation plan until the desired outcome is concrete enough
to evaluate. Every plan starts with:

- **Bakgrunn**
- **Ønsket resultat**
- **Agenda**

Label agenda items as information, discussion or decision. BØRA is a useful
format, not a consumer policy; use a documented local template if the team has
one.

## Design principles

- Let participants think individually before a plenary discussion.
- Use heatmapping or voting to reveal patterns, but clarify who actually owns
  the decision.
- Design for psychological safety and accessible participation, especially
  where there is asymmetric power or conflict.
- Anchor actions with an owner, deadline and expected signal of impact.
- Keep a visible parking lot and address it before closing.
- Vary the format and add breaks based on length, energy level and accessibility
  needs.

## Deliverable

### Facilitation plan

```markdown
# <Samling> — <dato>

**Bakgrunn:** <hva har skjedd>
**Ønsket resultat:** <observerbar endring eller beslutning>
**Deltakere og roller:** <deltakere, fasilitator, beslutningseier>
**Agenda:**

| Tid | Økt | Type | Fasilitatornotater |
|---|---|---|---|
| 09:00–09:15 | Innsjekk og spilleregler | informasjon | <notat> |
| 09:15–10:00 | <økt> | diskusjon/beslutning | <notat> |
```

For each session, include the purpose, timebox, working format, facilitator
script, materials, accessibility adaptations and likely pitfall.

### Collaboration surface as text

Describe areas, columns, instruction notes, voting rules, access and what should
be exported. Adapt to the tool the user has confirmed. If it is unknown,
deliver a tool-neutral structure and ask before using platform-specific
features.

## Format routing

| Need | Reference |
|---|---|
| New team or initiative that needs a shared hypothesis | [Foundation Sprint](./references/foundation-sprint.md) |
| Retrospective or team health | [Retro og teamhelse](./references/retro-og-teamhelse.md) |
| Goal workshop | Use this flow and load grillmester-okr for goal formulation |
| Group without a product mission | Consider a team contract rather than a Foundation Sprint |

The reference formats are starting points. Adapt them to the actual outcome,
participants, risks and constraints.

## Privacy and safety

- Clarify whether input is anonymous, confidential or shareable.
- Do not reproduce sensitive personal statements or health data in durable
  artifacts.
- Team health is a basis for conversation, not performance reporting.
- Ask the user to share only the necessary excerpt if an internal source cannot
  be read safely.

## Durable changes

Before creating or changing a meeting invitation, collaboration surface, issue,
document, message or other external resource:

1. show the target, recipients and access level
2. show the complete draft or planned structure
3. ask for explicit approval

## Boundaries

### Always

- Clarify the desired outcome before creating the facilitation plan.
- Adapt to the participants, decision format and accessibility needs.
- Close with an evaluation and concrete next steps.

### Ask first

- Create, share or change a meeting, document or collaboration surface.
- Contact participants or publish results and team-health data.

### Never

- Promise an integration or access that has not been verified.
- Use team health for individual assessment or upward reporting.
- Publish raw, sensitive workshop data without explicit approval.
