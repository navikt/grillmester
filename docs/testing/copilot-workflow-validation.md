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

Keep the existing shadowed-skill and continuing-conversation cases from the
routing suite. A stale installation must be diagnosed from its actual source;
a long conversation does not authorize a new session or transfer artifact.

## Evidence status

All cases above are **UNVERIFIED in the Copilot app for this instruction
revision** until an observed conversation supplies a result. Existing canvas
trials concern their recorded revisions and do not prove the new routing.
Structural checks, independent instruction review and forced loopback loads
must be reported separately from these observations.

For a completed case record pass, fail or blocked, the observed actions and
artifact, and the exact evidence location. Record unavailable capabilities and
operator intervention without converting a blocked case into a pass. Before
removing Barista, compare settled-work completion and unnecessary handovers;
retain it if the merged workflow loses useful explicit solo behavior.
