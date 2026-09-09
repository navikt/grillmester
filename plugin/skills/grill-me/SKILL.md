---
name: grill-me
description: Run an explicitly requested standalone stress-test of a plan, proposal, or idea. Use when the user asks to be grilled; expose weak assumptions and resolve choices in conversation without automatically creating documentation or a decision map.
disable-model-invocation: true
---

# Grill Me

Load `grilling` through the active skill catalog and use its interview method
to stress-test the user's proposal. Begin with the assumption or trade-off most
likely to change the plan. Ask one question at a time and wait for the answer.

Return the sharpened plan, decisions, and unresolved concerns in the
conversation. This standalone session does not itself authorize implementation,
documentation, or tracker writes. Honor any broader authorization the user has
already given; if documented design work is part of that scope, use
`grill-with-docs` for it.
