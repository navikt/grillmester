---
name: grillmester-okr
description: "Helps formulate and review outcome-oriented goals for public-sector product work. Use for OKRs, objectives and key results, planning cycles, goal reviews, baselines, measurement plans or converting delivery lists into measurable outcomes."
---
# OKRs and goal-setting in the public sector

> **OpenCode v1:** Backticked `grillmester-*` names below are skill IDs, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Help the team formulate, review and follow up on goals. Move drafts from activities
to observable outcomes, but do not invent baselines, target values or
measurement data. Examples are available in
[eksempler.md](./references/eksempler.md).

## Discover the goal context

Do not assume a four-month (tertial) cadence, OKR format, goal document, tracker
or project fields.

1. Read the request and relevant consumer-owned instructions and documents.
2. Find the team's documented goal period, terminology, adopted goals, owners,
   data sources and follow-up cadence.
3. If an issue template, link or remote name only suggests a repository,
   document or project, treat it as a candidate and have it confirmed.
4. Ask one missing factual question at a time. The minimum context is the
   desired outcome, target group, period, decision owner and available
   measurement basis.

Distinguish adopted goals, working drafts and your own suggestions.

## Formulation guide

- Measure outcomes, not outputs. A deliverable is one possible means.
- Default to user and societal value rather than revenue in the public sector.
- Keep the number of goals low. One to three objectives with two to three key
  results each is a useful rule of thumb, not a policy.
- An objective is qualitative; a key result describes a measurable outcome.
- Ask for a baseline and target value. If either is missing, mark it as
  unresolved.
- Clarify how and how often the result can be measured with adequate data
  quality.
- Distinguish routine operations from improvement objectives. A measurable
  improvement in service quality can be a genuine outcome.
- Adapt Norwegian or English terminology to the consumer's language rules.

Example:

- Good starting point: «Andelen brukere som fullfører uten å kontakte oss øker
  fra 62 prosent til 75 prosent.»
- Activity: «Lansere ny søknadsdialog.» Ask what observable change the
  deliverable should contribute to.

## Lint every draft

Present findings for each relevant rule and suggest a specific rewrite:

| Check | Clarification |
|---|---|
| Activity in disguise | What changes for the user or society? |
| Missing baseline or target | What are the current level, desired level and source? |
| Missing measurement plan | How, where and how often is the result measured? |
| Too many goals | What can be deprioritised to create focus? |
| Operations mixed in | Is this an ongoing obligation or an improvement? |
| Missing value link | What user or societal value does this support? |
| Proxy measure | Does the number actually measure the value, and what side effects might it have? |

Do not "improve" a goal by inventing a plausible number. Use clear placeholders
and questions.

## Follow-up cadence

Follow the team's documented cadence. If none exists, offer this generic cadence
as a suggestion:

| Timing | Activity |
|---|---|
| Start of period | Formulate goals, baseline, measurement plan and ownership |
| Regularly | Review signals and learning, not only delivery status |
| Mid-period | Assess the forecast and adjust effort or assumptions |
| End of period | Summarise results, data quality and learning |

A tracker can connect work to goals, but tracker activity does not itself
document goal attainment. Discover the project and fields dynamically if the
team actually uses them. Do not assume that goals should become field options
or that field names can be changed automatically.

## Durable changes

Before changing a goal document, issue, PR or project metadata:

1. show the exact repository, document or project
2. show the complete draft and planned field changes
3. ask for explicit approval

If the correct target is unknown, ask. Do not create a new goal document by
default.

## Boundaries

### Always

- Lint your own suggestions too.
- Distinguish outcomes, deliverables and routine operations.
- Mark missing data, baselines and decisions.

### Ask first

- Write or publish goals.
- Create issues or pull requests.
- Change tracker or project metadata.

### Never

- Rate goal attainment without data.
- Invent a baseline, target value, owner or measurement plan.
- Treat the number of completed tasks as evidence of impact.
