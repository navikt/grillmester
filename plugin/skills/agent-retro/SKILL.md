---
name: agent-retro
description: "Review an agent session and propose improvements to the repository's agent environment: instructions, checks, skills and tool access."
disable-model-invocation: true
---

# Agent Retro

Review an agent session and propose changes to the agent's **environment**, so
future runs go better: the instructions, checks, skills and tools around the
work, not the work itself.

1. Review the session the user names, from a transcript or export they share;
   without one, use the current conversation. Keep secrets and personal data
   out of the findings.
2. Look for candidates in these categories:
   - **Navigation:** the agent spent long finding a file or fact, or missed a
     hidden dependency. Candidate: a **navigation pointer** in an instruction
     file or document the agent already reads.
   - **Automated checks:** the agent made a mistake that a linter, type check,
     test or CI job could catch. Read the repository's own check commands and
     CI workflows first: an existing check that is unwired or silently broken
     is the finding. A repository with no check in CI or a pre-commit hook is a
     finding in itself.
   - **Standards:** the reviewer missed a mistake. A mechanical rule, such as a
     fixed pattern, a banned API, an import shape or a file location, gets a
     deterministic check in the repository's linter or CI. Keep documented
     standards for judgement calls that no check can make, and put them where
     every enforcing reviewer reads them: review receives a diff and has room
     for standards, while implementation carries the most context pressure.
   - **Instruction files:** `AGENTS.md` reaches every session, and path-scoped
     instructions reach the sessions that touch their paths. Move rules that
     only review needs to the standards above, and replace long content with
     pointers, or with a skill when it describes a repeated procedure.
   - **Tool economy:** expensive or repeated tool calls that a narrower
     command, script or query would make cheaper.
   - **No-ops:** instructions that do not change the agent's behavior.
   - **Information access:** a crucial fact the agent could not reach, such as
     local dev-server logs or read-only access to a development or test
     environment.
3. Present the candidates most severe first, each with the evidence from the
   session and the smallest change. Draft agent-facing text with the writing
   principles in `create-a-skill`, and make a change only when the user accepts
   it. When the fix belongs in a Grillmester agent or skill, propose it as
   feedback to Grillmester instead of a repository copy, which would shadow the
   plugin's version.
