---
name: grillmester-prototype
description: Build a bounded, runnable throwaway prototype to resolve an uncertain behavior or interface before committing to a production design. Use for data models, state machines, API or error contracts, event flows, retries, and other questions that benefit from something concrete to exercise.
---

# Prototype one uncertain decision

Use a prototype to answer a named question, not to start implementation early.
If the decision is already settled, return to the calling workflow and build
the real vertical slice instead.

## Frame the experiment

1. State the question, competing hypotheses, and the observation that would
   distinguish them. If the choice is user-owned, use `/grillmester-grilling` first.
2. Inspect the repository for the current language, framework, test seams, and
   existing spike conventions. Do not assume a stack or invent a parallel
   project layout.
3. Define a strict time, file, and side-effect boundary. Use synthetic data and
   do not contact production systems or external services merely to increase
   fidelity.

Useful shapes include:

- a small interactive runner for a data model or state machine;
- minimal request, response, and error types for an interface contract;
- a pure function over an ordered event sequence for retry, replay,
  idempotency, or partial-failure behavior;
- two or three deliberately different implementations behind the same tiny
  interface when the trade-off is the question.

## Build for learning

- Keep the experimental shell separate from the behavior under test.
- Make the relevant state, output, and failures visible after each action.
- Provide one documented command that reproduces the experiment.
- Prefer the repository's existing test/runtime tooling; do not add a durable
  dependency for a disposable experiment without explicit approval.
- Label every artifact as a prototype and keep it away from production entry
  points, deployment inputs, and real data.

Pause when the prototype exposes a new product, architecture, security, or
scope decision. Use `/grillmester-architecture-review` for architecture
boundaries, including when the decision depends on Nav or NAIS. Use
`/grillmester-domain-modeling` only when the repository's durable-documentation
gate qualifies the decision and the user selects that route.

## Close the experiment

Demonstrate the exact command and observations, then record:

- the question answered;
- what the evidence supports and does not support;
- the decision or remaining alternatives;
- which part, if any, is suitable to reimplement in production.

Delete the prototype after the result is captured, unless the user explicitly
chooses to retain it as a clearly marked task artifact. Never promote the
throwaway shell directly to production. Return the conclusion to the calling
workflow so production implementation and verification start from a clean
contract.
