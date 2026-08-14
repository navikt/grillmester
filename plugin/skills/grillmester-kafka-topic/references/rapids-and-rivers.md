---
description: Version and compatibility gate for an existing Rapids and Rivers service.
---

# Rapids and Rivers compatibility gate

Use this reference only when the repository already uses Rapids and Rivers, or
after the user explicitly chooses to adopt it. Do not infer its API from model
memory, this file, or the latest upstream branch.

Before editing:

1. Resolve the exact dependency coordinates and version from the build and
   lockfiles.
2. Inspect the imported packages, application lifecycle, and a representative
   local River and TestRapid test.
3. Derive event matching, validation, callback signatures, metadata,
   publishing, error handling, and idempotency from that local evidence.
4. If local evidence is incomplete, consult the matching release or commit in
   [navikt/rapids-and-rivers](https://github.com/navikt/rapids-and-rivers), not
   an unrelated newer version. Return `NEEDS_CONTEXT` if no matching source is
   available.
5. Compile and run the repository's focused tests after the change.

The repository's existing contract owns fields such as event identity and
event name. Preserve its lifecycle, replay, parking, and failure semantics.
Log only a stable structural summary; never log raw packets, validation values,
keys, headers, or diagnostic reports that may contain personal data.

Do not introduce or migrate to Rapids merely because it is used elsewhere in
Nav. Changing a rapid, consumer group, event contract, or replay behavior
requires an explicit design and operational decision.
