# Shared tracker protocol

Read this when inspecting or publishing a live Wayfinder map. The consumer's
repository instructions, issue templates, contributor documentation, and
read-only tracker metadata identify the tracker and its policy. Verify its
actual operations; do not assume a particular API or invent missing labels.

## Map and ticket schema

The map is one issue labelled `wayfinder:map`. Each decision ticket is a native
child issue with one label from `wayfinder:research`, `wayfinder:prototype`,
`wayfinder:grilling`, or `wayfinder:task`. Its tracker issue id is its identity.
Use linked titles in narration and the map so the human can recognize them.

The map is an index: each decision's detailed answer lives only in its ticket.
Open tickets are queried as children, not duplicated in the map body.

```markdown
## Destination

<what this effort is finding its way to; one or two lines>

## Notes

<domain, relevant skills, and standing preferences for this effort>

## Decisions so far

- <resolved ticket title> — <canonical ticket URL> — <one-line gist>

## Not yet specified

<in-scope questions that cannot yet be phrased precisely>

## Out of scope

<work ruled beyond the destination; include rationale and links to any closed tickets>
```

A ticket body holds one bounded question or investigation:

```markdown
## Question

<the decision or investigation this ticket resolves>
```

Link assets from the ticket. Record its answer as a resolution comment when
resolved rather than rewriting the question or copying the answer into the map.

## Native graph and publication

Blocking uses the tracker's native dependency relationship. A ticket is
**unblocked** when every blocker is closed; the **frontier** consists of open,
unblocked, unclaimed children. Query these relationships rather than inferring
them from prose or checklists. Assignment and issue-body updates do not by
themselves provide an exclusive session lock.

Before writes, prepare the map, ticket questions, exact labels, blocking edges,
initial research claims, and project effects, including effects caused by
native sub-issue workflows. Reuse the user's existing authorization; ask only
for missing scope. Verify child/dependency read and write capabilities, label
availability, and the consumer's claim checks before publishing a live graph.

If a required capability, label, or authority is missing, retain the proposal
as a draft and name what is needed for publication. Independent authorized
investigation may continue, but it must not pretend to hold a live ticket claim
or replace the shared graph with a second tracker.

Create the map and children first; wire dependencies in a second pass once
their ids exist. Verify the resulting graph. A partial write remains partial:
record the actual tracker state and reconcile it before claiming that the
proposed map is live or choosing work from its frontier.

## Claim and work a ticket

Choose the user's named ticket after checking blockers and ownership, or take
the next frontier ticket in the established order. Claim it by assigning it to
the developer driving the map before ticket work. Follow consumer policy and
verified immediate pre-claim and post-claim checks. Never work through a
conflicting or ambiguous claim; narrow concurrency when the tracker cannot
provide the necessary ownership guarantee.

An assignment has no automatic timeout. Treat another session's assignment as
active unless its assignee or the user confirms abandonment. Never unassign an
active claim to make work available. If a session cannot finish its own ticket,
record a checkpoint and release its claim only within the authorized workflow
and consumer policy; otherwise leave the proposed release explicit.

For research, claim and verify each ticket before delegating its bounded
question to `researcher`. Independent claimed questions may run in
parallel. External research requires an approved retrieval tool; unavailable
sources are missing evidence, not permission for shell fetches or invented
facts. Interpret the returned status:

- `ANSWERED`: inspect the sourced evidence, then record and verify resolution.
- `PARTIAL` or `NOT_FOUND`: keep the ticket open; follow up or release the claim
  within the authorized workflow.
- `NEEDS_CONTEXT`: supply the named fact or source, or route to an approved
  retrieval surface. Continue independent work where possible.

For a human-owned design decision, a live answer or an already settled answer
from the current task is required. A prototype or researched fact informs that
answer; neither lets an agent supply it on the human's behalf.

## Resolve and advance

Within authorized scope, post the actual answer as a resolution comment, close
the ticket, and append a linked one-line pointer to **Decisions so far**.
Verify the mutations; a write response alone does not establish a complete
resolution when its target or resulting content is uncertain.

Revisit the frontier after each resolution:

- Create newly precise questions as children, then wire dependencies. Remove
  their former **Not yet specified** entries so each question lives once.
- Close a ticket beyond the destination with a rationale; link it under
  **Out of scope**, not **Decisions so far**. Excluded work returns only through
  an explicit scope change and a fresh effort.
- For an invalidated ticket, comment with the superseding decision and close
  it. Preserve every ticket and its audit trail; never delete map tickets.

Explain material map changes and ask only for effects outside the authorized
scope. A blocked frontier does not imply that research or clarification outside
those claims is blocked too.

Before completing the map, account for every child as resolved and indexed,
out of scope with a linked rationale, or invalidated with a superseding-decision
comment. Other closed, failed, or partially recorded children keep the map
incomplete. When no live ticket, unresolved child, or fog remains, write the
final map summary and close it if the user's scope includes closure. Otherwise
present that concrete remaining action for authorization.
