---
name: grilling
description: "Clarify a request and challenge a plan's assumptions, requirements, and trade-offs through one question at a time. Use for unresolved intent or design choices, and as Grillmester's opening method; grill-with-docs adds durable domain documentation and Wayfinder organizes dependent decisions."
---
# Grilling

> **OpenCode v1:** Skill names below are exact IDs from the active catalog, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Build shared understanding before work depends on an unresolved decision.
Challenge assumptions with concrete scenarios, counterexamples, missing
acceptance criteria, and genuinely different alternatives. Follow dependencies
between decisions instead of treating the interview as a fixed questionnaire.

Read the relevant repository evidence and earlier answers first. Look up facts
the available environment can establish; do not ask the user to supply them.
Distinguish observed behavior from the behavior the user wants.

For each material user-owned decision, ask one question, explain the meaningful
alternatives, and recommend an answer with its consequence. Wait for the user's
answer before dependent work. Never answer on their behalf or treat silence as
agreement. Continue independent, authorized investigation while waiting.

Be proportionate: a settled, bounded request may need only an evidence check and
a concise statement of the agreed direction. Do not manufacture disagreement,
reopen settled choices without new evidence, or demand a separate confirmation
after the user has already resolved the relevant decisions. Routine reversible
implementation choices remain the agent's responsibility within the task.

At the boundary, summarize the locked decisions, remaining uncertainty, and the
next useful action. Continue the user's authorized workflow when the direction
is clear; a request for discussion or a stress-test ends with the findings.

This is the shared interview method. Use `grill-with-docs` when design work
should consult and maintain the domain model. Use `wayfinder` when multiple
dependent decisions require a persistent shared map, not merely because the
eventual implementation is large. Resolve these skills through the current
runtime's skill catalog and native loading mechanism.
