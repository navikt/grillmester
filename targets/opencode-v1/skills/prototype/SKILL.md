---
name: prototype
description: "Build a bounded, runnable throwaway experiment to resolve uncertain behavior or an interface contract. Use for data models, state machines, event flows, retries or failure semantics; use `design-prototype` for visual layouts and user-flow sketches."
---
# Prototype one uncertain decision

> **OpenCode v1:** Skill names below are exact IDs from the active catalog, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Use a prototype to answer a named question, not to start implementation early.
If the decision is already settled, return to the calling workflow and build
the real vertical slice instead.

Use `design-prototype` when the question is visual layout, hierarchy or a
user-flow sketch. This skill exercises behavior and contracts; a visual
preview alone does not prove a state machine or failure-handling rule.

## Frame the experiment

1. State the question, competing hypotheses, and the observation that would
   distinguish them. If the choice is user-owned, use `grilling` first.
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
scope decision. Use `architecture-review` for architecture
boundaries, including when the decision depends on Nav or NAIS. Use
`domain-modeling` for qualifying durable decisions within the active task's
documented-work boundary; preserve its eligibility and authorization gate.

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
