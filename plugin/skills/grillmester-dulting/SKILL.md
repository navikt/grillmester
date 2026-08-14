---
name: grillmester-dulting
description: "Explores, designs and evaluates ethically responsible behavioural interventions in public services. Use for nudging, behavioural design, reminders, defaults, friction or sludge, action-triggering copy, and experiments intended to influence user behaviour."
---

# Design responsible nudges

Treat a nudge as a hypothesis about a specific user behaviour, not as decoration
or a shortcut around a service problem. Base it on actual user insight, product
data, regulations and the consumer's documented constraints. Distinguish
verified facts, assumptions and decisions throughout the work.

## Scope the problem

1. Read the relevant user journey, research, target state, existing
   measurements, user-facing copy and consumer instructions.
2. Define the behaviour precisely: «Når `<situasjon>` oppstår, skal `<aktør>`
   kunne gjøre `<handling>`». Name the desired user outcome, not only the
   system's goal.
3. Establish the baseline, affected groups, voluntariness, the consequences of
   acting or not acting, and whether the action affects rights, health,
   finances or the sharing of personal data.
4. Mark missing insight as an open question. Do not invent effect data, user
   needs, deadlines, social norms or legal consequences.

## Find the right type of intervention

First diagnose whether the barrier is information, ability or friction,
motivation, prompt or timing, trust, or a structural constraint.

- Correct errors, unclear information and unnecessary friction before applying
  stronger influence.
- Use `grillmester-klarsprak` when comprehension or wording is the problem.
- Treat necessary legal or security-related friction as a constraint, not as
  sludge that should automatically be removed.
- Do not use nudging to conceal insufficient capacity, unresolved regulations
  or a service that does not let the user complete the task.

Load the [behavioural patterns](references/behavioral-patterns.md) when mapping
the journey, applying Fogg/EAST or comparing specific techniques.

## Compare interventions

Create two or three genuinely different hypotheses, including a simpler option
such as information, friction removal or no nudge where relevant. For each
hypothesis, show:

- the barrier it is intended to affect;
- its placement and timing in the user journey;
- the expected mechanism and what evidence is missing;
- autonomy, privacy, accessibility and distributional risks;
- the primary measure, guardrails and an explicit stopping rule.

Use `grillmester-aksel-design`, `grillmester-design-prototype` or
`grillmester-prototype` when a scoped visualisation or experiment is needed.
Never use the prototype as evidence that the intervention works in production.

## Run the ethics gate

Load the [ethics and evaluation reference](references/ethics-and-evaluation.md)
for the FORGOOD assessment, experiment design and measurement plan. Stop before
designing or experimenting when the responsible product, subject-matter, legal,
privacy or accessibility role must make a decision that cannot be derived from
the sources.

Require specific clarification for:

- time pressure or loss framing in rights-critical or vulnerable situations;
- defaults that may share or process personal data;
- personalisation based on sensitive or unexpected data;
- automated influence that could be mistaken for a formal decision or
  professional advice;
- different effects on groups that already face substantial friction.

## Deliver a testable brief

Summarise the user journey, baseline, desired behaviour, documented barrier,
selected and rejected hypotheses, evidence, FORGOOD findings, data needs,
measures, guardrails, stopping rule, responsible roles and the next smallest
learning step. Clearly distinguish a design hypothesis from an approved
production change.

## Boundaries

- Never use false deadlines, fabricated social-proof figures, hidden opt-outs,
  guilt or fear as mechanisms.
- Never optimise solely for completion when errors, pressure, complaints, bias
  or quality may worsen.
- Do not publish externally, recruit users, change production or start an
  experiment without explicit, scoped approval.
