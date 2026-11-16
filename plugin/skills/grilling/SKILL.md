---
name: grilling
description: Grill the user relentlessly about a plan, decision or idea, one question at a time. Use for unresolved intent, assumptions or design choices, or when the user asks to be grilled.
---

# Grilling

Interview the user relentlessly until you reach a shared understanding. Map
the work as a **design tree**: every material decision branches into the
decisions that hang off it. Routine, reversible implementation choices are
yours to make.

Ask one question at a time, because a team often answers together and needs to
discuss each decision. The **frontier** is every open material decision whose
prerequisites are already settled: the questions you can ask now without
guessing at answers you have not heard. Ask the frontier question that
unblocks the most, wait for the answer, then recompute the frontier and ask
the next.

Make each question answerable on its own. Say in plain sentences what you
found and what is at stake, give each real alternative its consequence, and
put the one you recommend first. Word it as a choice between the alternatives.

If the user asks for all the open questions at once, ask the whole frontier as
one numbered message with your recommendation for each, and let them answer by
number.

Facts are your job; the decisions in the tree are the user's. Look up anything
the repository, documentation or tools can answer instead of asking. When a
fact needs longer exploration and your role may delegate, hand it to a subagent
with a fresh context and keep asking the questions that do not depend on it.
Never answer one of those decisions on the user's behalf or treat silence as
agreement.

Keep it proportionate. Settled, bounded work needs only a brief check of the
facts and the agreed direction, not an interview. Reopen a settled answer only
when new evidence changes it.

The session is done when the frontier is empty. Summarize the decisions in a
few lines. After a stress-test or a discussion, stop there; otherwise continue
the authorized work. Grilling writes no files. When a resolved term or
decision deserves to be recorded, recommend it in one line and leave the
writing to `domain-modeling` once the user agrees.
