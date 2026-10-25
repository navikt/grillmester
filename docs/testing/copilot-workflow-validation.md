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

Except for the bounded observations below, cases above are **UNVERIFIED in their
named client for this instruction revision**; cases without a named client use
the Copilot app. Existing canvas
trials concern their recorded revisions and do not prove the new routing.
Structural checks, independent instruction review and forced loopback loads
must be reported separately from these observations.

For a completed case record pass, fail or blocked, the observed actions and
artifact, and the exact evidence location. Record unavailable capabilities and
operator intervention without converting a blocked case into a pass. Before
removing Barista, compare settled-work completion and unnecessary handovers;
retain it if the merged workflow loses useful explicit solo behavior.

### Saved room to CLI implementation, 24 October 2026

The full plugin at `42164e2` was loaded into a fresh Grillmester conversation in
Copilot CLI `1.0.102-0.unstable` (build commit `0401dd9`), through cplt
`2026.09.15-143904-77f4321`. The disposable frontend used React 19.2.4, Vite 7.3.5
and Aksel React/CSS 8.9.0. Its room was a byte-for-byte copy of an earlier
app-created synthetic room. The natural request selected version 2 while the
latest was 4; it did not name a skill or explain the source-resolution procedure.

- **Observed:** naturally loaded `design-prototype`, its handoff reference and
  `aksel-design`; read the registered version-2 HTML/descriptor pair; used the
  descriptor heading and compact setting with the older version's body text.
  The implementation uses actual Aksel components. It did not open canvas or
  a preview server to read the room. All nine room files remained unchanged.
- **Verification order failed:** measured the HTML byte count and eventually
  computed matching SHA-256 hashes, but only after product writes. This exposed
  an instruction gap: the handoff reference now explicitly requires calculation
  and comparison before using the pair. This original trial does not establish
  compliance with the strengthened instruction.
- **Client build blocked:** the wrapper denied execution of the Vite
  shim and then loading Rollup's native module from the disposable dependency
  directory. No sandbox policy was changed. A separate operator build of a
  fixed implementation snapshot succeeded. All five final frontend source files
  match that snapshot by SHA-256; this is not autonomous CLI build evidence.
- **Client rendering:** a Chromium comparison at 416 px passed after correcting
  an extra heading gap. It compared static server-rendered component markup with
  the selected HTML after applying its descriptor values. It did not exercise
  the Vite build or hydrated application, and the client explicitly reported
  that it had not visually inspected its screenshot.
- **Independent rendering:** 20 checks passed at 320, 375, 768 and 1280 px,
  including chosen copy, 8 px compact spacing, no horizontal overflow, labelled
  editable input, visible keyboard focus, literal/Unicode/long/empty input and
  room-byte preservation. Screenshots were inspected separately. External font
  requests were blocked, so the observed typography is fallback; the trial does
  not prove font or pixel parity with the original canvas environment.

This fixture is one heading, paragraph and text field. It does not test a full
meeting-booking journey, persistence, backend behavior, screen readers, actual
browser zoom or human usability. The room had submitted comments but no unsent
comment, so this trial does not prove separation of unsent feedback. Ordinary
one-time client permission approvals were supplied by an operator.

### Designer brief and altered source, 24 October 2026

Two fresh Designer CLI conversations used the same client/wrapper versions as
above, the same selected model settings and the identical natural request. Each
received a fresh copy of the same 24-file fixture. The request named an output
brief, selected version 2 and submitted round 1, prohibited product/room edits,
and asked whether version 2 of a second room was usable. The first room included
a newer unchosen heading and an unsent comment. The second room's chosen
descriptor had one appended space: valid JSON with unchanged values, but bytes
that did not match the registered SHA-256.

The first payload already contained the explicit hash-check instruction. The
retest payload matches `df08dd8`; its only differences were Designer's explicit
saved-room entry and that agent's generated manifest digest. Prompts did not
name a skill or disclose the deliberate mismatch. The private evidence retains
both frozen payload manifests, prompts, source baselines, tool traces and
resulting briefs; only one-time client permissions were supplied by an operator.

- **Initial failure:** wrote the brief without loading the handoff reference or
  calculating file hashes. Treated the canonical descriptor values versus older
  raw HTML as unresolved design choices, missed the byte mismatch and suggested
  a newer version as a possible source. This exposed a routing gap: making the
  reference stricter was insufficient when Designer did not load it.
- **Retest, partial result:** naturally loaded `design-prototype` and the handoff
  reference, calculated the chosen files' hashes and HTML byte counts before
  writing the brief, and detected the appended space. The brief named the exact
  mismatch, retained the files, used the selected version's canonical values and
  kept the unsent comment outside submitted round 1. However, its own review
  still made the already chosen heading conditional on reconfirmation and
  release of the newer hold. Correct source discovery and integrity checks did
  not establish a fully usable brief.
- **Follow-up clarification:** the reference now explicitly treats the chosen
  pair's canonical values as settled source, without requiring release of
  current holds. Actual conflicts with included feedback remain open work.
  This final wording has independent source review and package validation, but
  is **UNVERIFIED in a fresh live client**; the recorded retry used `df08dd8`.

These are individual bounded observations, not a quality or speed comparison
across models or clients. The brief request itself prohibited product and room
edits, so detecting the altered pair here does not prove that an implementation
request would stop before writing product code. The fixtures have no submitted
decision journal entries; they test comment-round selection, not replay of
active/released decisions. Neither brief trial supplies visual or human evidence.

## VS Code canvas trial

**Setup attempted; blocked before model execution on 25 October 2026.**
Platform support does not establish plugin parity.
Use a disposable project and the full plugin, record the installed versions and
resolved plugin source, and preserve the normal client configuration.

1. Record the effective `chat.canvases.enabled` value. In VS Code 1.142.0 it is
   application-scoped; a workspace setting is not a valid activation test. If
   temporarily changing it for an authorized trial, restore its original value
   or absence afterward. A separate user-data directory also separates login
   and plugin discovery, so record that difference rather than assuming parity.
   Local source registration uses `chat.pluginLocations` in this client version.
   Record plugin inclusion in the actual host profile: the Agents window has
   its own profile, so changing inclusion in the editor profile is insufficient.
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

### Setup observation, 25 October 2026

VS Code 1.142.0 with bundled Copilot Chat 0.70.0 was opened on an empty synthetic
repository. The full plugin was frozen from `a320c07`; an independent audit
matched all 171 files against the commit and package manifests. Canvas was
temporarily enabled at application scope and the frozen plugin registered as a
local source.

The editor and Agents window discovered both the published installation and
the test source. In the Agents profile, the published installation was then
excluded: Customizations showed it as disabled and the test source as enabled.
Nevertheless, the mode picker still displayed two indistinguishable Designer
entries. This persisted after closing and reopening the Agents window. A blank
new chat did not establish a fresh or unambiguous role catalog. The exact cause
of the disagreement between the picker and plugin inclusion was not established.

Captured editor screenshots and accessibility snapshots disagreed, and
reloading the Agents window left it blank until it was closed and reopened.
These observations limit the trial; they do not identify a Designverksted defect.
No model request was sent, no Designer source was selected, and no canvas was
opened. Rendering, editing, feedback delivery and reopening therefore remain
**UNVERIFIED in VS Code**. Do not choose between duplicate names by list order
or infer runtime source from the Customizations count alone.

The published plugin was re-enabled in the Agents profile, the temporary source
removed, the application settings restored byte-for-byte and the exact test
folder's trust withdrawn. Both test windows were closed. A new attempt needs
an unambiguous role source before the interaction cases above can begin.

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
