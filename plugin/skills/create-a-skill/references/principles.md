# Principles for Building Great Skills

A skill helps a capable model produce useful, reliable outcomes in a bounded
kind of task. **Predictability** means honoring intent, constraints and evidence,
not forcing the same process on different situations. Add guidance only when
it changes a decision or improves the result.

**Bold terms** use the definitions in the skill's glossary.

## Invocation

User reach and model reach are independent axes. Together they produce three
useful modes:

- **Manual-only** — user-reachable and not model-reachable. It avoids model
  discovery cost but spends **cognitive load** because the human must remember
  it.
- **Model-only** — model-reachable and hidden from the human picker. Its
  discovery description contributes permanent **context load**.
- **Both** — model-reachable and user-reachable. It pays the same model
  discovery cost while preserving direct human access.

Default to model and user reach for a new task skill; preserve an existing
policy unless the task changes its contract. Reserve manual-only for deliberate
explicit entry points. Requiring authorization for a write does not require
hiding the skill from relevance-based selection. Reuse authorization already
granted for that action instead of adding approval at every phase.

Hide a model-reachable skill from the human picker only when direct invocation
would add noise or expose an implementation detail. Add a **router skill** only
when it solves a demonstrated discovery problem; a router cannot make a
manual-only skill automatically callable.

Use GitHub Copilot's supported invocation fields rather than encoding policy
in prose.

## Writing the description

A model-facing **description** states what the skill does and when it applies.
Use concrete task language and a boundary against likely neighboring skills.
Include a synonym or example only when it materially improves discovery; avoid
catchalls, exhaustive trigger lists and process detail. Test with natural user
requests that do not name the expected skill.

A manual skill's description is a short human-facing picker summary, not a list
of automatic triggers the model cannot use.

## Information hierarchy

Keep the purpose, decision criteria and essential constraints in `SKILL.md`.
Use **steps** where order matters, and **reference** for facts or conditional
mechanics. Open-ended work needs room for judgment. Reserve fixed sequences,
deterministic scripts and exhaustive **completion criteria** for operations
whose correctness or safety depends on them.

**Progressive disclosure** moves reference down the hierarchy so the top stays
legible. **Branching** is the cleanest disclosure test: inline what every branch
needs and disclose what only some branches reach. A context pointer's wording,
not its target, decides when the agent follows it.

Use **co-location** within each file: keep a concept's definition, rules, and
caveats together.

## When to split

**Granularity** spends either context or cognitive load, so split only when the
cut earns it:

- **By task** — split when a coherent capability has a distinct trigger and
  useful result of its own.
- **By conditional detail** — prefer a reference when only one mode needs a
  long procedure, schema or example.

Avoid chains whose only purpose is enforcing a fixed process. Every delegated
skill should add task value and respect the caller's settled decisions.

## Pruning

Keep each meaning in a **single source of truth**. Check every line for
**relevance**, then test every sentence for **no-op** behavior: does it change
the model's behavior compared with the default? Delete failed sentences rather
than polishing them.

For volatile runtime facts, treat the environment, manifests and tool output as
source of truth and documentation or bundled snapshots as a cache: use them for
discovery, then verify against the current environment before acting.

## Leading words

A **leading word** is a compact concept already present in the model's
pretraining that recruits a useful behavioral prior. It anchors execution in
the body and invocation in the description. Hunt restatements that one strong
word can collapse.

## Failure modes

- **Premature completion** — ending a step before its completion criterion is
  met because later steps pull attention forward.
- **Duplication** — one meaning in multiple places.
- **Sediment** — stale layers retained because addition feels safer than
  removal.
- **Sprawl** — a skill too long even when each line is live and unique.
- **No-op** — an instruction that changes nothing versus model default.
- **Negation** — steering by naming forbidden behavior instead of positively
  specifying the target.
