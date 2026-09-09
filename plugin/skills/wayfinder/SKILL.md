---
name: wayfinder
description: Organize several unresolved, dependent decisions as a persistent shared issue map when a conversation checkpoint cannot keep the route navigable across sessions. Select automatically from that need or continue an existing map; use grill-with-docs for each design decision, and ordinary planning when the direction is already settled.
---

# Wayfinder

A loose idea has arrived, and several decisions depend on answers that are
still unknown. This skill charts a **shared map** on the repo's issue tracker,
then works its **decision tickets** — questions whose resolution is a decision,
not implementation slices — one at a time until the route is clear.

Select Wayfinder when those dependencies need to remain navigable across
sessions and ordinary grilling plus a concise checkpoint cannot hold the route.
No explicit skill name is required. Continue an existing relevant map rather
than creating another. Size or implementation duration alone is insufficient:
use `grill-with-docs` for one coherent conversation and ordinary planning for a
large implementation whose direction is already settled.

Explain the route choice briefly and continue. Load `grill-with-docs` and its
shared grilling/domain method for each design decision through the active skill
catalog and native loading mechanism. Skill names identify catalog entries;
slash entrypoints are user UI, not shell commands.

The destination varies per effort, and naming it is the first act of charting — it shapes every ticket. It might be a spec to hand off and iterate on, a decision to lock before planning starts, or a change made in place like a data-structure migration. The map is domain-agnostic — engineering work, course content, whatever fits the shape.

## Plan, don't do

Wayfinder is **planning**: each ticket resolves a decision, and the map is done when the way is clear — nothing left to decide before someone goes and does the thing. The pull to just do the work is usually the signal you've reached the edge of the map and it's time to hand off. Notes may constrain the planning effort, but never extend Wayfinder into implementation. Produce decisions, not deliverables.

The calling workflow may continue into implementation when the user already
authorized it. Ending the map is a phase boundary, not a forced end of the
conversation.

## Authorization and decisions

Choosing this skill authorizes no additional external action. Read repository
and tracker context, resolve the destination, and prepare a concrete map within
the task. Before tracker writes, check whether the user has already authorized
creating or maintaining this map, including claims, dependencies, resolution
comments, closure, and any project effects. Reuse that authorization within its
scope; do not ask again for each ticket or bookkeeping update.

If authority is missing, finish the reviewable proposal, name the exact missing
actions and their effects, and ask once for the smallest remaining authority.
Do not turn a routing choice into a permission question or treat permission to
read a tracker as permission to write it. New scope or materially different
external effects require their own authority.

Resolve material user-owned choices with the user, one at a time. A live answer
or an already settled decision in the current task supplies the human side;
the agent never impersonates that answer. Continue independent authorized
investigation while waiting, and record only decisions actually reached.

## Refer by name

Every map and ticket is an issue, so it has a **name** — its title. In everything the human reads — narration, the map's Decisions-so-far — refer to it by that name, never by a bare id, number, or slug. A wall of `#42, #43, #44` is illegible; names read at a glance. The id and URL don't vanish — a name wraps its link — but they ride _inside_ the name, never stand in for it.

## The Map

The map is a single issue on this repo's issue tracker, labelled `wayfinder:map` — the canonical artifact. Its tickets are child issues of the map.

The map is an **index**, not a store. It lists the decisions made and points at the tickets that hold their detail; a decision lives in exactly one place — its ticket — so the map never restates it, only gists it and links.

**Where the map, its child tickets, blocking, and frontier queries physically
live is tracker-specific.** Establish that context from consumer-owned
instructions, issue templates, contributor documentation, and read-only
tracker metadata. A dedicated adapter file is optional. If the live tracker
does not expose a required operation or an exact label or authorization
boundary remains unresolved, keep the map as a reviewed draft and ask for the
smallest decision needed before writing. Never invent a parallel local tracker
or approximate missing labels.

### The map body

The whole map at low resolution, loaded once per session. Open tickets are **not** listed — they are open child issues, found by query.

```markdown
## Destination

<what reaching the end of this map looks like — the spec, decision, or change this effort is finding its way to. One or two lines; every session orients to it before choosing a ticket.>

## Notes

<domain; skills every session should consult; standing preferences for this effort>

## Decisions so far

<!-- the index — one line per resolved, in-scope ticket: enough to judge relevance, then zoom the link for the detail the ticket holds -->

- <closed ticket title> — <canonical ticket URL> — <one-line gist of the answer>

## Not yet specified

<!-- see "Fog of war": in-scope fog you can't ticket yet; graduates as the frontier advances -->

## Out of scope

<!-- see "Out of scope": work ruled beyond the destination; closed, never graduates -->
```

### Tickets

Each ticket is a **child issue** of the map; the tracker's issue id is its identity. Its body is one bounded decision or investigation that can be resolved independently once its blockers are closed:

```markdown
## Question

<the decision or investigation this ticket resolves>
```

Each ticket carries a `wayfinder:<type>` label — one of `research`, `prototype`,
`grilling`, `task` (see [Ticket Types](#ticket-types)).

A session **claims** a ticket by assigning it to the dev driving the map,
**first**, before any work, so collaborators and recovery sessions can see
that it is active. That assignee _is_ the claim: an open, unassigned ticket is
unclaimed. Consumer policy or verified tracker behavior may narrow concurrency
where assignment cannot provide an exclusive session lock.

A claim has no automatic timeout. If a session cannot finish its ticket, record
the checkpoint and release its own claim only when the authorized map workflow
and consumer policy permit it; otherwise propose the release before ending.
Another session treats an assignment as active unless the assignee or user
confirms it is abandoned. Never unassign someone else's active claim to make a
ticket available.

Blocking uses the tracker's **native** dependency relationship — essential
because it renders the frontier _visually_ in the tracker's own UI, so the
human sees what's takeable without opening the map. Do not emulate a missing
native relationship with body text, checklists or labels: those are not an
atomic, queryable dependency graph. If the current tracker integration cannot
read and write child/dependency relationships, keep the complete map as a
reviewed draft and return `NEEDS_CONTEXT` with the missing capability. A ticket
is **unblocked** when every ticket blocking it is closed; the **frontier** is
the open, unblocked, unclaimed children — the edge of the known.

The answer isn't part of the body — it's recorded on resolution (see [Work through the map](#work-through-the-map)). Assets created while resolving a ticket are linked from the issue, not pasted in.

## Ticket Types

Every ticket is either **HITL** — human in the loop, worked _with_ a human who speaks for themselves — or **AFK**, driven by the agent alone. A HITL ticket only resolves through that live exchange; the agent never stands in for the human's side of it (a grilling agent that answers its own questions has broken this).

- **Research** (AFK): Reading documentation, third-party APIs, or local
  resources like knowledge bases to surface a fact a decision waits on.
  Resolved by `grillmester:researcher` through the agent task tool. External
  retrieval is runtime-dependent; when no approved web or MCP tool exists, the
  ticket remains open with `NEEDS_CONTEXT` instead of falling back to shell
  fetches or unsourced inference.
- **Prototype** (HITL): Raise the fidelity of the discussion by making a cheap, rough, concrete artifact to react to — an outline, a rough take, a stub, or UI/logic code via the `prototype` skill. Links the prototype as an asset. Use when "how should it look" or "how should it behave" is the key question.
- **Grilling** (HITL): Conversation. The default case. Use `grill-with-docs` to resolve the decision against the domain model, recording only resolved terms and qualifying decisions under repository policy and the authorized task. No separate documentation-mode choice is needed.
- **Task** (HITL or AFK): Manual work that must happen before a _decision_ can be made — nothing to decide, prototype, or research, but the discussion is blocked until it's done. Signing up for a service so its API can be judged, provisioning access, moving data so its shape can be seen. This is the one type that _does_ rather than decides — and it earns its place by unblocking a decision, not by delivering the destination. The agent drives it alone where it can (AFK); otherwise it hands the human a precise checklist (HITL). Resolved when the work is done; the answer records what was done and any resulting facts (credentials location, new URLs, row counts) later tickets depend on.

## Fog of war

The map is _deliberately_ incomplete: don't chart what you can't yet see. Beyond the live tickets lies the **fog of war** — the dim view of decisions and investigations you can tell are coming but can't yet pin down, because they hang on questions still open. Resolving a ticket clears the fog ahead of it, graduating whatever's now specifiable into fresh tickets — one at a time, until the way to the destination is clear and no tickets remain.

The map's **Not yet specified** section is where that dim view is written down: the suspected question, the area to revisit later. It's the undiscovered frontier _toward_ the destination — everything here is in scope, just not sharp enough to ticket. Write as loosely or as fully as the view allows; it doubles as a signpost for collaborators reading where the effort is headed.

**Fog or ticket?** The test is whether you can state the question precisely now — _not_ whether you can answer it now.

- **Ticket when** the question is already sharp — even if it's blocked and you can't act on it yet.
- **Not yet specified when** you can't yet phrase it that sharply. Don't pre-slice the fog into ticket-sized pieces: it's coarser than a ticket, and one patch may graduate into several tickets, or none, once the frontier reaches it.

**Not yet specified** excludes what's already decided (Decisions so far), what's already a live ticket, and what's out of scope (the next section).

## Out of scope

Fog only ever gathers _toward_ the destination. The destination fixes the scope, so work beyond it is **out of scope** — it isn't fog, and it doesn't belong in **Not yet specified**. It gets its own **Out of scope** section on the map: work you've consciously ruled out of _this_ effort. Scope, not sharpness, lands it here.

Out-of-scope work never graduates — the frontier stops at the destination — so it returns only if the destination is redrawn, and then as a fresh effort, not a resumption.

Ruling something out of scope is a scoping act, not a step on the route. When a ticket that already exists turns out to sit past the destination — mis-scoped in while charting, or exposed by a resolution — **close it** (a closed ticket is unambiguously off the frontier) and leave one line in the **Out of scope** section: the gist plus why it's out of scope, linking the closed ticket. It stays out of **Decisions so far**, which records the route actually walked — a scope boundary isn't a step on it.

## Invocation

Two modes. Work on one human decision at a time, but continue to the next
available ticket while the user's scope and the session allow it. Charting and
working through the map may happen in the same conversation. Pause for a real
missing decision, authority, capability, or session boundary, not a fixed
one-ticket limit.

### Chart the map

A request or the calling workflow supplies a loose idea.

1. **Name the destination.** Use `grill-with-docs` to pin down what this map is finding its way to — the spec, decision, or change. Reuse an already settled destination. It fixes the scope and must be clear before charting.
2. **Map the frontier.** Grill again, **breadth-first** this time: fan out across the whole space rather than deep on any one thread, surfacing open decisions and the first steps available now. If the decisions fit one coherent conversation or the route is already clear, explain that a map adds no value and return to documented grilling or the caller's authorized planning workflow. Do not create a map solely because implementation will take several sessions.
3. Present the proposed map, tickets, labels, blocking edges, project effects,
   and initial research-ticket claims. Apply the authorization boundary above,
   including project changes caused automatically by verified native sub-issue
   workflows. Ask only for authority the current task has not already supplied.
4. **Create the map** (label `wayfinder:map`): Destination and Notes filled in, Decisions-so-far empty, the fog sketched into **Not yet specified**.
5. **Create the tickets you can specify now** as child issues of the map — then wire blocking edges in a **second pass** (issues need ids before they can reference each other). Wiring sorts them into the frontier and the blocked; everything you can't yet specify stays in the fog — the **Not yet specified** section.
6. **Fire the research subagents.** Claim each `research` ticket under the authorized workflow, verify the claim, then invoke one `grillmester:researcher` per claimed ticket through the agent task tool. Independent investigations may run in parallel. Each returns a sourced note ending in a result status. Close a ticket only on `ANSWERED` evidence; on `PARTIAL` or `NOT_FOUND`, keep it open and choose an authorized claim release or follow-up. On `NEEDS_CONTEXT`, supply the named fact or source, or reroute to a surface with approved external retrieval. Record and verify each answered ticket's resolution, closure, and map-index update within the authorized scope.
7. Continue with the next available decision through the procedure below. If the frontier is blocked, preserve the map and report the actual blocker.

### Work through the map

A request names a map, or the calling workflow finds the existing relevant map. A ticket is **optional** — without one, choose the next available decision.

1. Load the **map** — the low-res view, not every ticket body.
2. Choose the ticket. If the user named one, check its blockers and claim before proceeding. Otherwise take the first frontier ticket in the established order. Claim it within the authorized workflow and follow the consumer's verified immediate pre-claim and post-claim checks. Never work through a conflicting or ambiguous claim.
3. Resolve it — **zoom as needed**: fetch the full body of related or closed tickets on demand and load the relevant skills from `## Notes`. For a design decision, use `grill-with-docs`; let `domain-modeling` own documentation eligibility. Wait for each unresolved material user choice.
4. Summarize the resolution. Within the authorized scope, post the answer as a **resolution comment**, **close** the issue, and **append a context pointer** to the map's Decisions-so-far. Verify the mutations; an unverified write is not a completed resolution.
5. Update the frontier within that scope: create then wire newly specified tickets, clearing each graduated patch from **Not yet specified** so it lives only as its new ticket. If a ticket sits beyond the destination, **rule it out of scope** rather than resolving it on the route. If a decision invalidates other tickets, preserve the audit trail with a resolution comment naming the superseding decision, then close them. Never delete a map ticket. Explain material map changes and ask before effects outside the authorized scope.
6. Continue to the next available decision while useful work remains and the user has not paused or changed direction. Leave a compact checkpoint at a real session boundary.

Consumer policy and verified tracker behavior own the concurrency boundary. Do
not assume that native assignment or issue-body writes provide an exclusive
session lock.

Before declaring the route clear, audit every child into exactly one category:
resolved and indexed; out of scope with a linked rationale; or invalidated with
a superseding-decision comment. Any other closed, failed, or partially recorded
ticket keeps the map incomplete. When no live ticket, unresolved child, or fog
remains, write the final map summary and close it when the authorized workflow
includes closure; otherwise present that final action for authorization. Return
to the caller's next authorized phase or recommend the lightest useful handoff.
A durable specification may use `to-spec`; several independently deliverable
slices may use `to-issues`.
Neither transition is automatic, and a single clear slice needs neither.
