# Skill routing scenarios

Use these scenarios in a disposable repository with the current plugin and the
client's active skill catalog. They assess selection separately from loading:
a scripted tool call proves that a skill can load, but does not prove that a
model chooses it from an ordinary request.

For every scenario, record the client and plugin versions, the request, the
catalog identity and source actually loaded, the first useful question or
action, and any files or tracker state changed. Use a disposable tracker fixture
or read-only draft for tracker scenarios. Never use a consumer repository as a
write target for a smoke test.

| Scenario and request | Expected behavior |
|---|---|
| Coherent design: "Customers should be able to cancel part of an order. Help me settle the rules and implement them." The glossary currently defines cancellation for the whole order. | Grillmester loads `grill-with-docs`, inspects the glossary and implementation, and asks one consequential question with a recommendation. It does not ask the user to select a skill. Resolved terminology is maintained within the authorized design work; an ADR appears only if the eligibility gate passes. |
| Dependent decisions: "We need a replacement settlement flow. Provider capabilities determine the data model, which determines migration and rollout. Keep the decisions navigable across several sessions." | Select `wayfinder` from the decision dependencies. Prepare a destination, initial decision tickets, and blocking relationships. Load `grill-with-docs` for the first design decision. Ask for missing tracker-write authority only after the concrete map is ready. |
| Existing map: "Continue the settlement decision map." The user has already authorized maintaining its issues and claims; one unclaimed child has no open blockers. | Read the map, verify the frontier and claim, then work the next decision. Reuse the existing map and authorization. After a resolved decision, update and verify its records and continue when another decision is available. |
| Large settled build: "Apply the approved adapter migration to all 80 handlers; the acceptance criteria and rollout decision are in this task." | Perform a brief grilling check against repository facts and the approved direction, then plan implementation slices. The file count and expected duration do not trigger Wayfinder. |
| Small settled fix: "Change this misspelled label to the exact text below." | Perform a proportionate check of the target and requested result, then continue without manufactured questions, a decision map, or an ADR. |
| Standalone stress-test: "/grill-me Here is my proposal; challenge it, but keep this discussion in chat." | Load `grill-me` and `grilling`, ask one question at a time, and return the sharpened proposal. Do not write documentation or tracker records. |
| Resolved design, ordinary documentation: "Use the agreed distinction between Customer and User and finish the change." Repository policy requires updating its glossary alongside domain changes. | Reuse the resolved choice, update the glossary under the existing task authority, and continue implementation. Do not ask for a separate documentation mode or repeat the decision. |
| Unresolved choice: "Could we use either one shared account or a separate account for each tenant?" | Investigate existing facts and ask about the material tenancy choice before dependent changes. Recommendations are not recorded as user decisions; silence supplies no answer. |
| Candidate that needs no ADR: a reversible naming correction with no meaningful architectural alternative. | Apply the relevant glossary or ordinary documentation change when authorized. Do not create an ADR merely because `grill-with-docs` was selected. |
| Missing native tracker dependency support. | Complete the proposed map as a reviewable draft, identify the missing capability, and preserve it for a supported integration. Do not approximate dependencies with body text or create a second local tracker. |
| Designer request: "Explore three different layouts for this checkout flow." | Resolve the appropriate design skill from the active catalog by its exact short ID and source. Native loading succeeds without an invented `grillmester-` prefix and without executing a slash entrypoint in the shell. |
| Shadowed skill: the active catalog's `grill-with-docs` resolves to a stale repository copy instead of this plugin. | Identify the actual source conflict and report the needed cleanup. Do not claim the plugin skill was loaded or invent an alternate qualified identity to bypass precedence. |

An automated loopback smoke can verify catalog identities, packaged content,
native loading, delegation, and emitted evidence without a real model. Mark
natural-language routing as unverified until an actual client conversation has
observed it; a payload assertion alone is not behavioral evidence.
