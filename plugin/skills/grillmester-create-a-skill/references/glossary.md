# Glossary — Building Great Skills

The domain model for what makes a skill great. A skill exists to wrangle
determinism out of a stochastic system; the root virtue is **Predictability**,
and every term below is a lever on it.

The terms are grouped by axis: **Invocation** (how a skill is reached),
**Information Hierarchy** (how its content is arranged), **Steering** (how the
agent's runtime behavior is shaped), and **Pruning** (how it is kept lean).
Each **failure mode** lives beside the lever that cures it, tagged
*failure mode*.

**Bold terms** in any definition are themselves defined in this glossary.

## Predictability

The degree to which a skill makes the agent behave the same *way* on every run
— the same process, not the same output. A brainstorming skill should
predictably diverge: its tokens vary, its behavior does not. The root virtue
every other term serves; cost and maintainability are symptoms of it, not
rivals.

_Avoid_: consistency, reliability, robustness, output-determinism

## Invocation

How a skill is reached and the two loads paid for the choice.

### Model-Invoked

A skill the agent can discover and fire autonomously. Model reach is
independent of human reach: the skill can be model-only or reachable by both.
It pays permanent **Context Load** in exchange for discoverability and reach
from other skills. A model-invoked skill whose content is all **Reference** can
be a shared reference home.

_Avoid_: ability, tool, capability

### User-Invoked

A skill exposed for deliberate human invocation. User reach is independent of
model reach: the skill can be manual-only or reachable by both. A manual-only
skill trades agent discoverability for zero **Context Load** and spends
**Cognitive Load** because the human must remember it.

_Avoid_: procedure, workflow, command

### Description

The skill's machine-readable discovery pointer. For a **Model-Invoked** skill,
its presence in model context is the source of **Context Load**. Runtime
behavior is configured through GitHub Copilot's supported fields, which define
exactly how model and user reach are configured.

_Avoid_: frontmatter, summary

### Context Pointer

A reference held in the agent's context that names out-of-context material and
encodes the condition for reaching it. A model-facing **Description** is the
top-level pointer; links to disclosed files are the same object one level down.
Its wording, not its target, decides when and how reliably the agent follows it.
A must-have target behind a weak pointer is a variance bug: sharpen the wording
first and inline only if sharpening fails.

_Avoid_: link, import

### Context Load

The cost a **Model-Invoked** skill imposes on the agent's context window through
its always-visible discovery information. This is the brake on splitting into
more model-invoked skills.

_Avoid_: token cost, context bloat

### Cognitive Load

The cost a human-facing skill surface imposes on the user: which skills exist
and when to reach for each. It is the price of human agency, not a cost to
minimize unconditionally. Spend it where human judgment matters.

_Avoid_: human index, burden, overhead

### Router Skill

A **User-Invoked** skill whose job is to name other manual skills and when to
reach for each, so the human remembers one entry rather than many. It points;
it does not make an undiscoverable manual skill model-reachable.

_Avoid_: dispatcher, menu, registry, index, router procedure

### Granularity

How finely skills are divided. Finer division spends one of two loads: more
**Model-Invoked** skills spend **Context Load** and more human-facing skills
spend **Cognitive Load**. Split by invocation where a distinct **Leading Word**
should trigger independently. Split by sequence where a step's
**Post-Completion Steps** need hiding behind a real context boundary.

_Avoid_: chunking, modularity

## Information Hierarchy

How a skill's content is arranged and how far down the ladder each piece sits.

### Information Hierarchy

A skill's content ranked by how immediately the agent needs it:

- **Steps** — in-file, primary
- **Reference**, in-file — secondary
- **Reference**, disclosed — behind a **Context Pointer**

A skill with no steps can use only the bottom two rungs, often as a legitimately
flat peer set. The hierarchy is independent of invocation. Keep the top
legible; push down whatever a branch does not always need.

_Avoid_: structure, organization, layout

### Steps

The ordered actions the agent performs. When a skill has them, they are the
primary tier of `SKILL.md`. Every step ends on a **Completion Criterion**. Not
every skill needs steps; a skill can be all steps, all **Reference**, or both.

_Avoid_: workflow, instructions, choreography

### Reference

Material the agent consults on demand: definitions, facts, parameters,
examples, or conditional instructions. It can be in-skill, disclosed, or fully
external. It is reached through **Context Pointers** and is the prime candidate
for **Progressive Disclosure**.

_Avoid_: supporting material, docs, background

### External Reference

**Reference** that lives outside the skill system: a plain artifact with no
invocation surface or steps that multiple skills can point to. It is the shared
home for material that need not fire independently.

_Avoid_: doc, resource, knowledge base

### Progressive Disclosure

Moving **Reference** down the hierarchy, out of `SKILL.md` and behind a
**Context Pointer**, so the top stays legible. **Branching** licenses the move:
disclose what only some branches need and inline what every branch needs. If a
pointer fires unreliably on must-have material, sharpen it before pulling the
material back inline.

_Avoid_: lazy loading, chunking

### Co-Location

Keeping material needed at once together: a concept's definition, rules, and
caveats under one heading rather than scattered. The hierarchy decides how far
down material sits; co-location decides what sits beside it. This differs from
**Duplication**, which repeats meaning rather than fragmenting it.

_Avoid_: grouping, clustering, cohesion

### Sprawl

*Failure mode.* A skill that is too long even when every line is live and
unique. It thins attention, costs maintenance, and wastes tokens. Cure it by
moving **Reference** behind **Context Pointers** or splitting by **Branch** or
sequence. This differs from **Sediment** and **Duplication**.

_Avoid_: bloat, length, size, verbosity

## Steering

The levers that shape runtime behavior toward **Predictability**.

### Branch

A distinct way a skill is invoked or used, so different runs take different
paths. A linear skill has no branches.

_Avoid_: path, case, fork

### Leading Word

A compact concept, also called a *Leitwort*, already living in the model's
pretraining and carrying a useful behavioral prior. It encodes a principle in
few tokens. Repeated as a token rather than a restated sentence, it accumulates
a distributed definition.

A leading word anchors execution in the body and invocation in the
**Description**. When the same word lives in prompts, documentation, and code,
the agent links that language to the skill more reliably. Prefer an existing
word before coining one that needs a long definition.

_Avoid_: keyword, term, motif

### Completion Criterion

The condition that tells the agent a unit of work is done. Its clarity resists
**Premature Completion**; its demand controls **Legwork**. The strongest
criteria are both checkable and exhaustive. Clarity needs **Steps** to prevent
between-step rushing, while demand also binds flat **Reference**.

_Avoid_: done condition, exit condition, stopping rule

### Legwork

The work an agent does inside a step: reading files, exploring code, running
checks, and digging up facts rather than offloading them to the user. A
demanding **Completion Criterion** or strong **Leading Word** increases it.
It can be thin even when no between-step rush occurs.

_Avoid_: scope, effort, diligence, coverage

### Post-Completion Steps

The **Steps** following the current step. When visible, they can pull attention
forward into **Premature Completion**. A real context boundary can hide them
when sharpening the current criterion is not enough.

_Avoid_: horizon, fog of war, lookahead

### Premature Completion

*Failure mode.* Ending a step before it is genuinely done because attention
slips toward being finished. It is a tug-of-war between visible
**Post-Completion Steps** and the current **Completion Criterion**. Sharpen the
criterion first. Only when it remains irreducibly fuzzy and rushing is observed
should later steps be hidden behind a real context boundary.

_Avoid_: premature closure, the rush, rushing, shortcutting

### Negation

*Failure mode.* Steering by prohibition, which names forbidden behavior into
context and can make it more available. Cure it by positively specifying the
target behavior. Keep a prohibition only as a hard guardrail that cannot be
phrased positively, and pair it with what to do instead.

_Avoid_: ironic rebound, don't-prompting, the pink elephant

## Pruning

Keeping a skill lean, with each remedy paired to the failure it cures.

### Single Source of Truth

The desired state where each meaning lives in one authoritative place, so a
behavior change is a one-place edit. **Duplication** violates it.

_Avoid_: home, canonical location

### Duplication

*Failure mode.* The same meaning in more than one place. It costs maintenance
and tokens and inflates the meaning's prominence. It is the accidental inverse
of a **Leading Word**, which repeats a token while keeping one definition.

_Avoid_: repetition, redundancy

### Relevance

Whether a line still bears on what the skill does. A line loses relevance when
it never affects the task or when it becomes stale. This differs from
**No-Op**, which asks whether the line changes behavior.

_Avoid_: load-bearing, staleness, freshness

### Sediment

*Failure mode.* Stale layers retained because adding feels safe and removal
feels risky. It is the slow erosion of **Relevance**, distinct from repeated
meaning.

_Avoid_: accretion, bloat, cruft, rot

### No-Op

*Failure mode.* An instruction that changes nothing because the model already
does it by default. The test is model-relative: does the line change behavior
versus default? A weak **Leading Word** can itself be a no-op; replace it with a
stronger prior rather than more restatement.

_Avoid_: redundant instruction, restating the obvious, belaboring
