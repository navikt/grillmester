---
name: grilling
description: Grill the user relentlessly about a plan, decision or idea, one round of numbered questions at a time. Use for unresolved intent, assumptions or design choices, or when the user asks to be grilled.
---

# Grilling

Interview the user relentlessly until you reach a shared understanding. Map
the work as a **design tree**: every material decision branches into the
decisions that hang off it. Routine, reversible implementation choices are
yours to make.

Work the tree in **rounds**. The **frontier** is every open material decision
whose prerequisites are already settled: the questions you can ask now without
guessing at answers you have not heard. Ask the whole frontier as one message
in the conversation, number the questions and give your recommendation for
each. Then wait for the user's answers before the next round.

Format a round like this:

```text
❓ **Q1 – <short title>:** <a question that "ja" or "yes" answers by accepting
your recommendation, with the real alternatives when they matter>

➡️ <your recommendation and its consequence>

---

❓ **Q2 – <short title>:** ...
```

The user may answer by number or accept every recommendation with "ja". If the
user asks for one question at a time, keep that pace.

Each answered round reshapes the tree. Recompute the frontier and ask the next
round.

Facts are your job; decisions are the user's. Look up anything the repository,
documentation or tools can answer instead of asking. When a fact needs longer
exploration and your role may delegate, hand it to a subagent with a fresh
context and keep asking the questions that do not depend on it. Never answer a
decision on the user's behalf or treat silence as agreement.

Keep it proportionate. Settled, bounded work needs only a brief check of the
facts and the agreed direction, not a round. Reopen a settled answer only when
new evidence changes it.

The session is done when the frontier is empty. Summarize the decisions in a
few lines. After a stress-test or a discussion, stop there; otherwise continue
the authorized work. Grilling writes no files. When a resolved term or
decision deserves to be recorded, recommend it in one line and leave the
writing to the full-context domain documentation workflow once the user agrees.
