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

Start a fresh session for each case with a minimal synthetic repository that
contains the facts the task needs, not hints about which method to choose.
Use the natural-language requests unchanged; do not put expected skill names
in the prompt or force tool calls. Explicit command cases below test manual
invocation separately. Exercise the full payload and repeat applicable settled
work in the focused payload; record `NOT_APPLICABLE` for an omitted role or
skill rather than treating focused fallback as a routing failure. Record the
resolved model as well as the client. A client or model without an observed
conversation remains `UNVERIFIED`.

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
| Existing design: "Her er Figma-lenken til dagens skjema; utforsk tre bedre varianter." | Use `design-prototype` for design exploration, even though a Figma artifact already exists. Missing Figma capabilities lead to a useful supported design artifact; they do not turn the task into code implementation. |
| Local specification: "Retningen er avklart: behold én ordre med flere ordrelinjer. Skriv planen i docs/order-design.md. Ingen issues skal opprettes." | Write the specified local document from the settled brief without tracker setup, publication, or another approval request. |
| Settled bug: "Feilen er bekreftet: en tom ordre skal gi 0. Legg til regresjonstest og rett feilen." A supplied failing test exposes an exception for an empty order. | Reuse the confirmed behavior, exercise the failure, then fix and verify it without another planning interview. |
| Incident without local reproduction: "Vi har bare denne redigerte feilloggen fra hendelsen. Finn den mest sannsynlige årsaken og foreslå hvordan vi kan bekrefte den." | Use bounded code/log analysis and label hypotheses and unrun checks. Do not fabricate a reproduction or stop all diagnosis because a deterministic local loop is unavailable. |
| Bounded research: "Undersøk i de vedlagte leverandørdokumentene om delvis refusjon støttes, og oppgi kilde og forbehold." No decision map exists. | Researcher can accept the factual brief, distinguish verified facts from inference, and return its answer without requiring a Wayfinder ticket. |
| Continuing work: "Samtalen begynner å bli lang. Fortsett med den avtalte testen her." | Continue the authorized work. Do not load `handoff`, write a transfer file, or require a new session because of conversation length or context pressure. Leave ordinary compaction to the client. |
| Requested transfer: "/handoff Lag et kort overleveringsnotat til en kollega som skal fortsette arbeidet." | Load the manual skill, write a portable brief with current evidence and unresolved work, and return the verified path. Do not transfer the session or send the note to anyone automatically. |
| Requested walkthrough: "/guided-review Forklar endringen og de viktigste avveiningene." | Start the requested walkthrough without another confirmation; an ordinary code review must not silently invoke this manual skill. |
| Shadowed skill: the active catalog's `grill-with-docs` resolves to a stale repository copy instead of this plugin. | Identify the actual source conflict and report the needed cleanup. Do not claim the plugin skill was loaded or invent an alternate qualified identity to bypass precedence. |

An automated loopback smoke can verify catalog identities, packaged content,
native loading, delegation, and emitted evidence without a real model. Mark
natural-language routing as unverified until an actual client conversation has
observed it; a payload assertion alone is not behavioral evidence.
