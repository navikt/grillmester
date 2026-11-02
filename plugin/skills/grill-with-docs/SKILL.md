---
name: grill-with-docs
description: Grill a plan and write agreed glossary terms and qualifying short ADRs as you go.
disable-model-invocation: true
---

# Grill with Docs

Load the `grilling` skill and the `domain-modeling` skill. When the user typed
`/grill-with-docs` or asked to document as you go, add each resolved term to
the glossary and record each decision that passes the ADR gate as soon as it is
settled, in the short formats from `domain-modeling`, without asking again.
Otherwise follow the propose-before-writing rule in `domain-modeling`.
