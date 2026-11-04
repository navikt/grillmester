---
name: domain-modeling
description: "Sharpen a project's domain language and durable decisions. Use when a domain term is fuzzy, overloaded or disputed, when deciding whether a choice deserves an ADR, or when editing a glossary or an ADR."
---
# Domain Modeling

> **OpenCode:** Skill names below are exact IDs from the active catalog, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Actively sharpen the project's domain model while you design: challenge terms,
probe boundaries with concrete scenarios and check the code. Reading the
glossary for vocabulary is not this skill; any task can do that.

## Find the glossary

Follow the repository's documented location and format when one exists.
Otherwise use `GLOSSARY.md` at the root, or `GLOSSARY-MAP.md` when the
repository has several contexts. Older repositories may still use
`CONTEXT.md` and `CONTEXT-MAP.md`; read and update those in place instead of
creating a second glossary. The format is in
[GLOSSARY-FORMAT.md](./GLOSSARY-FORMAT.md).

## During the conversation

- **Challenge against the glossary.** "The glossary defines cancellation as X,
  but you seem to mean Y. Which is it?"
- **Sharpen fuzzy language.** "By account, do you mean the Customer or the
  User? Those are different things."
- **Stress-test with scenarios.** Invent concrete edge cases that force a
  precise boundary between concepts.
- **Cross-check the code.** "The code cancels whole orders, but you said
  partial cancellation is possible. Which is right?"

## Propose before writing

Write documentation when the user has asked for it, for example through
`grill-with-docs` or "skriv en ADR", when the user has accepted your proposal,
or when repository policy requires it alongside the change. Otherwise end with
one short proposal, each term and each ADR candidate on one line, and ask once.
Never record an unresolved choice as settled.

Keep what you write small. A glossary entry is one or two sentences with no
implementation detail. Add to the existing glossary and ADR folder rather than
creating topic documents, summaries or evidence files.

## ADRs

Offer an ADR only when all three hold:

1. **Hard to reverse:** changing your mind later is costly.
2. **Surprising without context:** a future reader would wonder why.
3. **A real trade-off:** there were genuine alternatives.

Write it in the short format in [ADR-FORMAT.md](./ADR-FORMAT.md), even when
older ADRs in the repository are long. Architecture reviews return decision
candidates; this skill decides whether they qualify.
