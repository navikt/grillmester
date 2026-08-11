# Principles for Building Great Skills

A skill exists to wrangle determinism out of a stochastic system.
**Predictability** — the agent taking the same *process* every run, not
producing the same output — is the root virtue; every lever below serves it.

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

Enable model reach only when the agent must discover the skill on its own or
another skill must reach it. When manual skills multiply past what a human can
remember, use a **router skill**. Hide a model-reachable skill from the human
picker only when direct invocation would add noise or expose an implementation
detail.

Use GitHub Copilot's supported invocation fields rather than encoding policy
in prose.

## Writing the description

A model-facing **description** identifies the skill and the distinct
**branches** that should trigger it. Every word increases **context load**:

- Front-load the skill's **leading word**.
- Keep one trigger per branch; synonyms for one branch are **duplication**.
- Remove identity already carried by the body.

A manual skill's description is a short human-facing picker summary, not a list
of automatic triggers the model cannot use.

## Information hierarchy

A skill is built from **steps** and **reference**:

1. **In-skill step** — an ordered action in `SKILL.md`. Each step ends on a
   checkable and, where needed, exhaustive **completion criterion**.
2. **In-skill reference** — a definition, rule, or fact consulted on demand.
3. **Disclosed or external reference** — material behind a **context pointer**,
   loaded only when the pointer fires.

A demanding completion criterion drives thorough **legwork**. Push too little
down and the top bloats; push too much and required material becomes hard to
reach.

**Progressive disclosure** moves reference down the hierarchy so the top stays
legible. **Branching** is the cleanest disclosure test: inline what every branch
needs and disclose what only some branches reach. A context pointer's wording,
not its target, decides when the agent follows it.

Use **co-location** within each file: keep a concept's definition, rules, and
caveats together.

## When to split

**Granularity** spends either context or cognitive load, so split only when the
cut earns it:

- **By invocation** — split when a distinct leading word should trigger
  independently or another skill must reach the behavior.
- **By sequence** — split when visible **post-completion steps** cause
  **premature completion** and a real context boundary can hide them.

Sharpen a completion criterion before splitting a sequence. A purely inline
call does not hide later steps.

## Pruning

Keep each meaning in a **single source of truth**. Check every line for
**relevance**, then test every sentence for **no-op** behavior: does it change
the model's behavior compared with the default? Delete failed sentences rather
than polishing them.

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
