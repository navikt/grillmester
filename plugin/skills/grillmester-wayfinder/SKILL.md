---
name: grillmester-wayfinder
description: Use only after the user explicitly selects Wayfinder to plan work too large for one agent session as a shared map of decision tickets, resolved one at a time until the route is clear.
license: MIT
---

# Wayfinder

A loose idea has arrived — too big for one agent session, and wrapped in fog: the way from here to the **destination** isn't visible yet. Wayfinding is about finding that way, not charging at the destination. This skill charts the way as a **shared map** on the repo's issue tracker, then works its **decision tickets** — questions whose resolution is a decision, not slices of a build to execute — one at a time until the route is clear.

Start only after the user has explicitly selected Wayfinder in the current
conversation. If it was merely relevant or recommended, return to the caller
without charting, claiming, or changing tracker state.

The destination varies per effort, and naming it is the first act of charting — it shapes every ticket. It might be a spec to hand off and iterate on, a decision to lock before planning starts, or a change made in place like a data-structure migration. The map is domain-agnostic — engineering work, course content, whatever fits the shape.

## Plan, don't do

Wayfinder is **planning**: each ticket resolves a decision, and the map is done when the way is clear — nothing left to decide before someone goes and does the thing. The pull to just do the work is usually the signal you've reached the edge of the map and it's time to hand off. Notes may constrain the planning effort, but never extend Wayfinder into implementation. Produce decisions, not deliverables.

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

Each ticket is a **child issue** of the map; the tracker's issue id is its identity. Its body is the question, sized to one 100K token agent session:

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

A claim has no automatic timeout. If a session cannot finish its ticket,
propose releasing the claim before ending and unassign only after explicit
authorization. Another session treats an assignment as active unless the
assignee or user confirms it is abandoned; it may then propose the same
authorized, verified release before selecting the ticket.

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
- **Prototype** (HITL): Raise the fidelity of the discussion by making a cheap, rough, concrete artifact to react to — an outline, a rough take, a stub, or UI/logic code via the /grillmester-prototype skill. Links the prototype as an asset. Use when "how should it look" or "how should it behave" is the key question.
- **Grilling** (HITL): Conversation. The default case. Use /grillmester-grilling. Use /grillmester-domain-modeling only when the repository's domain policy qualifies the result for durable documentation and the user selects that route.
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

Two modes. Either way, **never resolve more than one ticket per session** — with the exception of research tickets.

### Chart the map

User invokes with a loose idea.

1. **Name the destination.** Run a `/grillmester-grilling` session to pin down what this map is finding its way to — the spec, decision, or change. The destination fixes the scope, so it's settled first. Use `/grillmester-domain-modeling` only when durable documentation qualifies under repository policy and the user selects it.
2. **Map the frontier.** Grill again, **breadth-first** this time: fan out across the whole space rather than deep on any one thread, surfacing the open decisions and the first steps takeable now. **If this surfaces no fog** — the way to the destination is already clear, the whole journey small enough for one session — you don't need a map. Stop and ask the user how they'd like to proceed.
3. Present the proposed map, tickets, labels, blocking edges, project effects,
   and initial research-ticket claims. Obtain explicit authorization for that
   exact set of tracker writes, including project changes caused automatically
   by verified native sub-issue workflows.
4. **Create the map** (label `wayfinder:map`): Destination and Notes filled in, Decisions-so-far empty, the fog sketched into **Not yet specified**.
5. **Create the tickets you can specify now** as child issues of the map — then wire blocking edges in a **second pass** (issues need ids before they can reference each other). Wiring sorts them into the frontier and the blocked; everything you can't yet specify stays in the fog — the **Not yet specified** section.
6. **Fire the research subagents.** Assign each `research` ticket to the authenticated user and verify the claim before work; if that assignment was not in the authorized set from step 3, ask first. Then invoke one `grillmester:researcher` per claimed ticket through the agent task tool and investigate them in parallel. Each returns a sourced note ending in a result status. Branch on it: close a ticket only on `ANSWERED` evidence; on `PARTIAL` or `NOT_FOUND`, keep it open and propose an authorized claim release or follow-up; on `NEEDS_CONTEXT`, supply the named fact or source, or explicitly reroute the ticket to a surface with approved external retrieval, then re-fire that Researcher. For each answered ticket, present its exact resolution-comment, close, and map-index mutations; perform and verify those tracker writes only after explicit authorization.
7. Stop — charting is one session's work; it hand-resolves nothing.

### Work through the map

User invokes with a map (URL or number). A ticket is **optional** — without one, you pick the next decision, not the user.

1. Load the **map** — the low-res view, not every ticket body.
2. Choose the ticket. If the user named one, use it. Otherwise take the first frontier ticket in order. Obtain authorization to **claim it**, then follow the consumer's verified immediate pre-claim and post-claim checks before any work. Never work through a conflicting or ambiguous claim.
3. Resolve it — **zoom as needed**: fetch the full body of any related or closed ticket on demand; invoke the skills the `## Notes` block names. If in doubt, use `/grillmester-grilling`; use `/grillmester-domain-modeling` only through its durable-documentation gate.
4. Present the resolution and the exact tracker mutations required. After authorization, post the answer as a **resolution comment**, **close** the issue, and **append a context pointer** to the map's Decisions-so-far.
5. Propose newly-surfaced tickets and map changes before writing them. After authorization, create then wire new tickets; graduate any fog the answer has made specifiable, clearing each graduated patch from **Not yet specified** so it lives only as its new ticket. If the answer reveals a ticket — this one or another — sits beyond the destination, **rule it out of scope** rather than resolving it on the route. If the decision invalidates other tickets, preserve the audit trail: propose a resolution comment that names the superseding decision, then close them after authorization. Never delete a map ticket.

Consumer policy and verified tracker behavior own the concurrency boundary. Do
not assume that native assignment or issue-body writes provide an exclusive
session lock.

Before declaring the route clear, audit every child into exactly one category:
resolved and indexed; out of scope with a linked rationale; or invalidated with
a superseding-decision comment. Any other closed, failed, or partially recorded
ticket keeps the map incomplete. When no live ticket, unresolved child, or fog
remains, propose a final map summary and closure. Close the map only after
explicit authorization, then recommend the lightest useful handoff. A durable specification may use
`/grillmester-to-spec`; several independently deliverable slices may use `/grillmester-to-issues`.
Neither transition is automatic, and a single clear slice needs neither.
