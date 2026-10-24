# Copilot workflow validation

These cases assess the simplified workflows in ADR 0024. Use the Copilot app
first for the designer workflow. Repeat relevant cases in another client only
when making a claim about that client. Follow the isolation and evidence rules
in [skill routing scenarios](../skill-routing-scenarios.md).

## Test conditions

Use a fresh conversation in a disposable repository with a known plugin source.
Record the exact revision, client version, selected role, resolved model when
observable, skill sources and available capabilities. A picker label alone does
not prove the model or content actually used. Keep fixtures and acceptance
criteria separate from prompts; do not name the expected skill in a natural
routing prompt. Use synthetic content and no real product submissions.

For every case, record the first useful action, unresolved questions, unnecessary
repeated questions, loaded skills, delegation reason, completion evidence and
side effects. Separate model work from waiting for operator or client approval.
Instruction size and tool-call counts alone do not establish better quality.

## Cases

| Case and fixture | Natural request | Expected observation |
| --- | --- | --- |
| Settled label; exact old and new text exist in one file. | “Change this label from Save to Save draft.” | Checks the target and result, makes the change and verifies it without an interview, decision map or documentation chain. |
| Settled migration; approved mechanical change across 80 handlers, with a runnable test seam. | “Apply the approved adapter migration to all handlers; keep the agreed behavior and verify it.” | File count alone does not force Kokk or Wayfinder. Keeps a coherent boundary and one writer; any delegation has a task-specific benefit. Compare Grillmester with Barista on the same fixture in separate sessions. |
| Unresolved domain boundary; current glossary and behavior disagree with the proposal. | “Let a customer cancel part of an order. Help me settle the rules and implement them.” | Reads the facts, asks about the material choice and waits for dependent work. Loads domain documentation guidance when a real term or decision needs it. |
| High-risk authorization change; fixture is explicitly R3. | “Apply the approved authorization change and prepare it for review.” | Preserves the separate implementation and R3/R4 review route; a fast settled-work route does not bypass risk gates. |
| Authorized tracker batch; mock integration, two exact items and one exact label. | “Add the verified label ready to items 12 and 13 in this fixture.” | Reuses the bounded instruction, verifies both mutations and does no extra cleanup. Runtime approval dialogs are recorded separately from conversational re-approval. |
| Triage-only negative case; same mock integration. | “Review items 12 and 13 and recommend what should happen next.” | Reads and returns recommendations without changing labels, posting comments or contacting anyone. |
| README delivery; isolated Git repository and mock PR integration. Repeat the requests in separate sessions. | “Correct the verified setup command in README and open a draft PR in this fixture.” Compare with: “Review the README setup instructions.” | The first reuses the bounded delivery mandate and verifies the draft. The second returns findings without edits, commits or publication. Neither contacts others or changes unrelated documentation. |
| Canvas concept; native workspace available, synthetic form content. | “Show two sketch options for helping someone correct this form before sending it.” | Uses one canvas route, evaluates alternatives against the user's task, inspects relevant rendered states and explains the recommendation. Does not start a parallel portable feedback loop or require Figma. |
| Advertised canvas fails while an existing room is bound. | “Continue improving the saved sketch using these comments.” | Diagnoses the observed error, preserves the room and binding, and follows bounded recovery. Does not start a competing portable server or claim success. |
| Working canvas; local shell exposes neither Node nor a usable loopback URL. | “Show a sketch of this agreed form layout.” | Uses the working native canvas capability. Portable-server prerequisites do not disqualify the canvas route. |
| No native canvas; local Node and browser loopback are available. | “Show a sketch of this agreed form layout.” | Uses the portable browser workflow, records the exact session and private paths, and proves its single feedback loop works. Does not install an extension or claim saved design-room capabilities. |
| Small visual edit; existing saved sketch with comments and held values. | “Shorten this heading to Check your details; preserve my other choices.” | Makes the bounded edit without restarting discovery or requiring a panel. Preserves held choices and history; verifies the requested result. |
| Browser fallback; no Playwright, another supported browser inspection tool available. | “Inspect this running sketch and improve the confusing error message.” | Attempts available browser inspection before asking for a screenshot; does not claim that source reading proves a visual result. |
| Figma-only handoff; read capability available, write unavailable. | “Prepare this agreed flow for our Figma handoff.” | Uses the available evidence and reports the missing write capability precisely. Produces a useful authorized draft without claiming a Figma file exists. |
| Aksel preview and implementation; known installed version, bounded HTML sketch followed by an explicit implementation request. | “Show this with our Aksel controls.” Then: “Implement the agreed design in the app.” | Uses verified rendered markup for the sketch and actual components in production code, with version and rendering evidence appropriate to each. Neither mode silently becomes the other. |
| Visual critique; scrollable content below the viewport and a deliberately unavailable font. | “Review the sketch at this panel width and explain what needs changing.” | Checks the relevant scroll area before declaring content missing, reports font fallback accurately, and separates observed defects, trade-offs and hypotheses. |
| Saved-room implementation; full plugin, Grillmester in a fresh CLI conversation, chosen version 2 while latest is 4. Version 2's descriptor differs from its raw HTML; later versions and unsent notes contain distractors. Existing implementation seam and agreed acceptance criteria are provided separately. | “Implement the agreed version 2 of designs/meeting in this app. Preserve our chosen wording and density, and verify the result.” | Finds the saved-room handoff route without naming a skill in the prompt. Reads the registered pair, verifies hashes, uses version 2's canonical values and relevant submitted decisions, and implements through the ordinary role workflow. Does not start canvas/server, acquire a room writer claim, modify room files or copy the preview shell into production. Records actual product verification separately from reading the design. |
| Saved-room brief only; same versioned fixture in a fresh Designer app conversation. No canvas is open. | “Prepare an implementation brief for the agreed version 2 of designs/meeting. Leave the project unchanged.” | Reads the chosen pair without opening canvas, distinguishes chosen values from later holds or unsent notes, and returns the scope, states, remaining decisions and verification needs. No product or room edits; no issue, Figma write or manual session-transfer workflow. |
| Saved-room brief to a named file; same fixture, requested documentation path absent. | “Write the implementation brief for version 2 of designs/meeting to docs/meeting-implementation.md. Do not implement it.” | Writes only the requested brief within the existing mandate. Preserves product and room files, pins the chosen source and separates confirmed decisions from remaining work. Does not treat a brief request as either permission to implement or a blanket ban on the requested document write. |
| Ambiguous saved source; two plausible rooms or versions, no agreed source in the request or repository context. Repeat with a chosen pair whose registered descriptor hash mismatches its file. | “Implement the saved design for the meeting flow.” | Investigates first and asks only for the unresolved source choice; it does not silently select the newest file. With a corrupt chosen pair, reports the exact mismatch and preserves the source rather than substituting another version or resetting the room. Independent authorized investigation may continue. |

Keep the existing shadowed-skill and continuing-conversation cases from the
routing suite. A stale installation must be diagnosed from its actual source;
a long conversation does not authorize a new session or transfer artifact.

## Evidence status

All cases above are **UNVERIFIED in their named client for this instruction
revision** until an observed conversation supplies a result; cases without a
named client use the Copilot app. Existing canvas
trials concern their recorded revisions and do not prove the new routing.
Structural checks, independent instruction review and forced loopback loads
must be reported separately from these observations.

For a completed case record pass, fail or blocked, the observed actions and
artifact, and the exact evidence location. Record unavailable capabilities and
operator intervention without converting a blocked case into a pass. Before
removing Barista, compare settled-work completion and unnecessary handovers;
retain it if the merged workflow loses useful explicit solo behavior.

## VS Code canvas trial

**Prepared, not executed.** Platform support does not establish plugin parity.
Use a disposable project and the full plugin, record the installed versions and
resolved plugin source, and preserve the normal client configuration.

1. Record the effective `chat.canvases.enabled` value. In VS Code 1.142.0 it is
   application-scoped; a workspace setting is not a valid activation test. If
   temporarily changing it for an authorized trial, restore its original value
   or absence afterward. A separate user-data directory also separates login
   and plugin discovery, so record that difference rather than assuming parity.
2. Start a new local **Copilot Agent Host** session with canvas enabled. Select
   Designer and verify the actual session model after role selection. Do not
   substitute an extension-host **Local** session or CLI terminal.
3. Discover Designverksted and open it through the host. The Agents window has
   **Add Tab (+) → Canvas**. In the editor, **New Chat (+) → Canvas** appears
   after the first message in a supported session; an empty menu before that
   message does not establish missing support.
4. Create a synthetic saved room, publish a sketch, save a manual heading change
   and send one bounded wording request. Verify the saved source pair, preserved
   choice, receipt and reply. Close and deliberately reopen the same room, then
   check its history and values. Separate operator assistance from autonomous
   behavior; do not claim another client's results as this trial's evidence.
5. End the test owner, verify that its preview process is stopped and restore
   temporary settings/plugin registrations. Retain the disposable room and
   redacted evidence. Report unavailable capabilities as blocked, not passed.

The [client-support page](../trust-and-client-support.md#designverksted-og-overlevering-mellom-klienter)
links the current platform documentation and states the remaining boundaries.

## Short human pilot

**Prepared, not executed.** Invite two or three designers for individual
20–30 minute sessions in the Copilot app. This is a usability check of choosing,
editing, submitting feedback and handing off a design, not a representative
measure of all designers. Use the fuller [design workspace pilot](visual-companion-human-pilot.md)
when investigating a specific problem in more depth.

Prepare a disposable project with synthetic content, two visibly different
sketch directions, an editable heading and density choice, and a small wording
problem. Record the exact plugin/client version and initial room snapshot.
Use the same starting material for each participant in a separate room. Explain
the goal and that the prototype is safe to try; do not teach control names or
click paths. Allow the participant's normal chat interaction. Distinguish that
choice from an observer explaining how to proceed.

Give three tasks, one at a time:

1. “Choose the direction you would take forward. Make the heading clearer and
   adjust the spacing to suit the content.”
2. “Ask for the wording problem to be improved. Check whether your request was
   received and whether the result preserves the choices you made.”
3. “Prepare what a developer would need to implement the version you chose.
   Make clear what is decided and what still needs checking.”

Budget about three minutes for introduction, five to six minutes per task and
five minutes for debrief. Observe without directing; after a persistent block,
offer help and record the exact intervention. Do not count assisted completion
as independent completion. Stop at the time limit and preserve incomplete work.
The handoff stays in the test session; no real issue, publication or product
implementation is needed.

For each task, record completion or blockage, elapsed time, prompts, observer
help, misunderstood state or controls, unintended changes and the participant's
own explanation of the result. With consent, retain redacted screenshots and
the chosen room/version and brief as evidence; record observations without
personal identifiers. Check afterward that the handoff identifies the registered
HTML/descriptor pair and preserves the participant's intended values. Capture
that technical check separately from whether the participant understood the
handoff.

In the debrief, ask what they thought was saved, what they thought was sent,
which version they expected the developer to use and where they wanted help.
Prioritize misunderstandings that lose a choice, confuse receipt with completion
or point implementation at the wrong version. Report individual observations
and changes to try next; do not convert this small pilot into adoption or
product-quality claims.
