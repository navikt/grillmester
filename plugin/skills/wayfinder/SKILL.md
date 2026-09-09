---
name: wayfinder
description: Organize several unresolved, dependent decisions as a persistent shared issue map when a conversation checkpoint cannot keep the route navigable across sessions. Select automatically from that need or continue an existing map; use grill-with-docs for each design decision, and ordinary planning when the direction is already settled.
---

# Wayfinder

Chart a shared map of **decision tickets**: questions whose resolution clears
the route to a destination, not implementation slices. Use an existing relevant
map. Size or implementation duration alone does not justify one: use
`grill-with-docs` for one coherent conversation and ordinary planning when the
direction is settled. Explain the route choice briefly and continue.

The destination may be a specification, a decision, or an eventual change.
Wayfinder resolves what must be decided before doing that work. Its completion
is a phase boundary: the caller continues into implementation when the user
already authorized it.

## Decision method

- Load `grill-with-docs` through the active skill catalog for each unresolved
  design decision. Let its shared grilling/domain method own terminology and
  documentation eligibility; no separate documentation-mode choice is needed.
- Resolve material user-owned choices with the user, one at a time. Reuse an
  already settled answer; never impersonate the human side of a decision.
- Investigate independent facts while waiting. Keep conclusions proportional
  to the evidence and record only decisions actually reached.
- Refer to maps and tickets by their linked titles, not bare issue numbers.

Choose the method that answers the current question:

- **Grilling** is the default for a design decision: use `grill-with-docs`.
- **Research** establishes a fact a decision depends on. Delegate a bounded,
  sourced question to `grillmester:researcher` through the agent task tool.
  Independent investigations may run in parallel. The caller owns tracker
  state and decisions; the researcher supplies evidence.
- **Prototype** makes uncertainty concrete. Use `design-prototype` for visual
  layouts and user-flow sketches, and `prototype` for runnable experiments in
  behavior, data models, state machines, or interface contracts. A simple
  outline or rough text example may need neither skill. Bring the result back
  to the human for the decision.
- **Task** performs a bounded prerequisite that unblocks a decision, such as
  obtaining access or preparing sample data. It is not a destination delivery
  slice. Use the existing authorization and record the resulting facts without
  exposing credentials or sensitive data.

## Chart or continue the map

1. **Establish the destination and frontier.** Reuse an agreed destination, or
   use documented grilling to clarify it. Explore unresolved dependencies
   breadth-first before going deep. If the route fits one conversation or is
   already settled, return to the lighter method instead of creating a map.
2. **Keep the map selective.** A precise question is a ticket even when it is
   blocked. A question not yet sharp enough belongs in **Not yet specified**;
   do not prematurely split it into tickets. Work outside the destination
   belongs in **Out of scope**, never in the future frontier.
3. **Prepare or maintain the shared graph.** When drafting tracker artifacts,
   reading a live map, or publishing changes, read [the tracker protocol](references/tracker.md)
   for its schema, native relationships, claims, and verified updates.
   Establish consumer policy from repository instructions and tracker evidence;
   a dedicated adapter file is optional.
4. **Resolve the next available decision.** Load only the map's overview and
   the ticket detail needed now. On a live map, check blockers and claims before
   working a ticket. Use the method above, record the actual resolution, and
   update the frontier: newly precise questions become tickets; invalidated or
   out-of-scope tickets retain their rationale and audit trail.
5. **Continue while useful authorized work remains.** Pause for a real missing
   decision, authority, capability needed by that action, or the user's pause;
   there is no fixed one-ticket limit. Leave a compact checkpoint at an actual
   session boundary. Ordinary context compression is the client's concern.

## Authority and missing capabilities

Selecting Wayfinder grants no tracker-write authority. Reuse the user's
existing scope for map creation or maintenance, including its authorized
claims, dependencies, resolution comments, closure, and project effects. When
authority is missing, finish the concrete proposal and ask once for the
remaining actions and their effects. Do not ask again for each bookkeeping
update, and do not confuse permission to read with permission to write.

The shared map requires native child and blocking relationships and reliable
claim checks. If the integration lacks them, keep the proposed graph as a
reviewable draft and report the specific missing capability. Do not emulate a
live graph with checklists, labels, or a parallel local tracker, or claim a
ticket was assigned or resolved without verification. This blocks the affected
tracker operation, not independent authorized analysis, research, or
clarification. Preserve those results for later reconciliation; never work
through another session's conflicting or ambiguous claim.

## Finish the route

The route is clear only when no live decision or fog remains and every child is
accounted for: resolved and indexed, out of scope with a rationale, or
invalidated by a recorded superseding decision. Close the map within the
authorized workflow, then return the decisions to the caller's next phase.
A durable specification may use `to-spec`; independently deliverable slices
may use `to-issues`. Neither transition is automatic, and a single clear slice
needs neither.
