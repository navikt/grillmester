# Saved design workspace: first human pilot

Prepared 2026-10-24. **Not run.** This protocol is for a moderated study with two designers and one developer. Its purpose is to find costly misunderstandings in the design-to-review-to-handoff flow before expanding the tool. Existing implementation evidence is in [the verification report](visual-companion-design-workspace.md).

This pilot does not establish that colleagues can browse and review designs independently through a shared web link. That capability is not implemented. Before claiming to replace the team's shared design workflow, add a separate test in which a colleague opens an exact chosen version on another device, without the authoring app or an active conversation, and can distinguish it from newer work. Durable comments and their return to the designer need their own check if offered.

## Prerequisite, scope and people

Confirm the native acceptance checks described in [the verification report](visual-companion-design-workspace.md#native-app-acceptance): full-plugin discovery, deliberate idle/busy delivery, exact instance routing, panel reopen and new-session recovery. Record the tested payload and any assistance or unresolved limits. These are technical acceptance checks; they cannot establish whether an unfamiliar person understands the tool. Do not spend participant time repairing installation, session ownership or transport. A blocked native gate postpones this pilot; a simulated host is not an equivalent substitute.

One facilitator runs a single **45-minute session**. Designer A does the content case; Designer B does the operational case. Each works independently, with the other designer out of view until their own tasks end. The developer joins only for the handoff portion, without seeing either designer's work. The facilitator observes; the developer is not also the moderator. This gives two first-use observations, not a comparison of which case or designer performs better.

Use a disposable local project and synthetic content. Prepare both cases in separate saved rooms through ordinary canvas actions. Use the tested full payload and installed Aksel version; record their versions. No production implementation, external publication, Figma transfer or new dependency is needed. Count live pilot work requests separately from technical acceptance checks, within the applicable authorized allowance. Record actual requests and stop before exceeding it.

## Before participants arrive

Prepare these fixtures and a private truth sheet. Use a fresh copy for each attempted pilot. Do not hand-edit workspace state or reuse an earlier participant's changes.

| Case | Initial material | Available controls and prepared history |
| --- | --- | --- |
| A: library collection notice | Room `designs/library-pickup`, title **Hentebeskjed**. Fictional Solvik library; fictional book **Etter regnet**; collection deadline **17. november kl. 16.00**; heading **Hent reservasjonen din**. | One initial version. The heading is a v2 source text field. Deadline paragraph is outside that field. Include one ordinary prototype input. No saved notes, rounds or manual values. |
| B: equipment review | Room `designs/equipment-check`, title **Utstyrskontroll**. Eight synthetic equipment items, two needing inspection. No real names or locations. | Three versions with identical facts: v1 **Utstyr til utlån**, v2 **Kontroller før utlån** with the two inspection items first, v3 **Status for utstyr** with an alphabetical list. All have editable heading and finite **Luft: Romslig/Kompakt**, initially Romslig. Include preview-only normal/empty/error states. One saved, unsent note: **Forklar hvorfor en kontroll mangler.** No manual values. |

Verify v2 visually contains the distinguishing order and that v3 is latest. For the first source save, ordinary draft typing and local state selection, no feedback round may be sent. Confirm the app's actual end-session/reopen procedure during acceptance, not by assuming panel close or archive releases ownership.

For A's requested review, keep the response narrow: improve only the deadline explanation, preserve the participant's saved heading, publish one revision and reply in the originating round. Do not issue that change until the participant requests it. This is a service response, not a hint about operating the interface. If they request an incompatible change, record their intent and the actual response rather than secretly correcting it.

Truth sheet fields: room path and ID; initial/current version; exact paired source for each version; manual field IDs and values; saved note IDs; submitted round count; any replies. Keep capability URLs and private session IDs out of participant materials and shared notes.

## Schedule and moderation

| Time | Activity |
| --- | --- |
| 00–03 | Explain the study, recording choice and think-aloud approach; no tool tour. |
| 03–15 | Designer A, four task cards below. Designer B and developer do not observe. |
| 15–27 | Designer B, four task cards below. Developer does not observe. |
| 27–35 | Developer receives each handoff independently, four minutes each. |
| 35–41 | Joint retrospective, after individual outcomes and predictions are recorded. |
| 41–45 | Buffer for app waits or one unfinished task. Stop at 45 minutes. |

Read only the relevant card. Introduce the work: **«Vi undersøker verktøyet, ikke deg. Løs oppgaven slik du ville gjort i arbeidshverdagen. Fortell gjerne hva du forventer skal skje. Jeg forklarer ikke grensesnittet underveis.»**

Allow roughly three minutes per task. At a stall, ask only **«Hva prøver du å få til nå?»** or **«Hva forventet du skulle skje?»**. Record any later directional help verbatim and score the task assisted; do not retrospectively call it independent success. If needed, advance to a prepared checkpoint so the next task can still be observed, marking that reset. Record app/model wait time separately from active interaction time; a response taking over two minutes is a blocked step, not evidence that the participant misunderstood.

The task cards deliberately omit control names and click paths. The observer key below is private. Accept a natural chat route as an observed alternative, but distinguish it from independently completing the intended canvas operation; do not conflate extra model assistance with interface discoverability.

## Participant task cards

### A — Hentebeskjed

1. **«Du har bestemt at overskriften skal være ‘Boken din er klar’. Gjør dette til en endring dere kan fortsette med senere. Du vil også huske spørsmålet ‘Kan hentefristen være tydeligere?’, men ingen skal arbeide med det ennå.»**
2. **«Nå vil du ha hjelp med hentefristen. Gi spørsmålet videre til designarbeidet, og vurder svaret når det kommer. Overskriften du valgte skal beholdes.»**
3. **«Du får en ny idé: ‘Forklar om en annen person kan hente boken.’ Ta vare på den til senere, uten å be om at den blir løst nå. Gjør arbeidet klart for en pause, og finn det igjen i en ny samtale.»**
4. **«Gi utvikleren det du mener trengs for å bygge den avtalte versjonen. Utvikleren får bare det du skriver eller peker til, og skal ikke behøve å se denne samtalen med deg.»**

After A1, before continuing, ask: **«Hva er tatt vare på nå, og hva tror du noen andre allerede har fått beskjed om å gjøre?»** After A3, ask: **«Hva kom tilbake, og hva forventet du skulle komme tilbake?»** Do not give the answer until the individual tasks are over.

### B — Utstyrskontroll

1. **«Dette er en tett arbeidsoversikt. Bruk overskriften ‘Utstyr må sjekkes’ og en kompakt liste som utgangspunkt for videre arbeid. Se også hvordan oversikten oppfører seg når det ikke finnes utstyr.»**
2. **«Tettheten skal ikke lenger være din føring: la den som videreutvikler skissen kunne endre den. Overskriften ‘Utstyr må sjekkes’ skal fortsatt beholdes. Det er ikke bestilt en ny utforming nå.»**
3. **«Teamet har ombestemt seg: dere skal fortsette fra det tidligere forslaget ‘Kontroller før utlån’, der de to kontrollsakene står først. Også den eldre overskriften skal brukes. Gjør det til arbeidsgrunnlaget, og ta vare på notatet om den manglende kontrollen.»**
4. **«Gi utvikleren én tydelig versjon å bygge videre på, hva som er bestemt, og hva som fremdeles må avklares. Utvikleren skal kunne skille dette fra det nyeste forkastede forslaget.»**

After B2, ask: **«Hvilke av valgene dine kan endres videre nå? Har det blitt bestilt arbeid?»** After B3, ask: **«Hvilken versjon er utgangspunktet nå, og hva skjedde med den gamle?»**

## Private observer key

| Task | Observable completion; record separately from the participant's explanation | Learning question |
| --- | --- | --- |
| A1 | Heading exists in a new saved source version; question is saved but unsent; round count remains zero. | Do they confuse source saving, note saving and asking for work? |
| A2 | One intentional review request; returned revision preserves the chosen heading and improves the deadline; participant locates the answer. Record canvas round vs direct-chat route. | Can they tell queued/admitted work from a completed answer, without a facilitator's interpretation? |
| A3 | Same room and latest paired-source version reopen after the prior owner ends; new note survives unsent; previous round is not replayed. Any still-unsaved typing is recorded before closing. | Can they predict the difference between saved material and typing, and find the correct work again? |
| A4 | An independent developer can locate the exact intended room/version and the outstanding collection question from the handoff. | Is the handoff an identifiable design decision, or just a screenshot/title? |
| B1 | New saved heading and compact setting both have manual ownership. Empty-state exploration remains local and sends nothing. | Do they distinguish an authored default from trying a state? |
| B2 | Only density ownership is released; stored density value remains unchanged until a later revision; heading ownership remains. No new source version or submitted round. | Does releasing a constraint mean “allow future change” to them, or “undo/change/send”? |
| B3 | Participant deliberately resolves the heading conflict and makes a new revision from old v2; old v2 remains intact; the unsent note remains. Record the actual new version, never assume it is v2 or the previous latest. | Do version selection and manual ownership work together intelligibly? |
| B4 | Developer identifies the new restored revision, its origin in v2, the intended normal/empty/error states and the unresolved control explanation. | Can someone outside the session distinguish chosen source, exploratory states and pending decisions? |

If a participant asks the conversation to do something only the UI is authorized to do, record the friction and whether they recover. Do not release manual values or change the state file for them behind the scenes. Selecting a complete HTML/descriptor pair is necessary: an exported HTML fragment alone may contain an older fallback heading.

## Developer's blind handoff and results

For each handoff, ask: **«Finn den versjonen du skal bygge. Vis hva du bruker som kilde, gjengi den avtalte overskriften og de viktige tilstandene, og si hva som fortsatt er et åpent spørsmål. Ikke implementer noe.»** Permit the same project access a normal handoff would have; the prior owner must have ended. No oral repair from the designer during the first four minutes. Record every clarification the developer would need.

Record one row per task. Capture outcome **independent / assisted / alternative-route / blocked / incomplete**, active seconds, wait seconds, first action, exact help, stated expectation, observed saved version/round/holds, unexpected writes or sends, and one short evidence note. Count affected people, not repeated clicks, and preserve contradictory observations.

Report five concrete measures, with raw denominators:

- Saved-versus-unsent predictions correct at A1 and A3: **0–2**; unintended submissions: exact count.
- Manual-ownership prediction and selective release correct at B2: **yes/no**; accidental release of the heading: **yes/no**.
- Reopen restores the same intended room and saved material without facilitator repair: **yes/no**, active time and operational assistance separately.
- Intended version and complete paired source found from each blind handoff: **0–2**; wrong-version confidence and clarification count.
- Independent designer tasks completed: **0–8**, with per-case counts and barriers. Do not infer a population completion rate from this pilot.

Before adding features, address any observed mistaken send, lost-needed-work assumption, unintentional ownership release or confident wrong-version handoff. If both handoffs are unambiguous, neither designer makes a critical state mistake, and each completes at least three of four tasks independently, proceed to a broader pilot. This is a local decision rule, not a usability certification. Otherwise fix the observed flow and repeat its affected task with someone unfamiliar with it; do not add a feature merely because one participant requests one.

For the retrospective ask only: **«Når ble du usikker på hva som var gjeldende?»**, **«Hva ville du normalt gjort annerledes?»**, and **«Hva manglet utvikleren for å fortsette?»** Keep the participants' wording and distinguish a requested solution from the underlying obstacle.

## Separate narrow-chart follow-up

The Lumi version 8 technical check preserved coordinates and removed marker
collisions, but a narrow panel cannot show both ends of the chart at once.
Keep this product question separate from the 45-minute workspace pilot and its
completion criteria. Use the unchanged paired source, chart direction B in
Normal at a 416 CSS-pixel viewport, with the chart initially scrolled fully
left. Record the actual width and starting position. Ask an unfamiliar
participant:

- **«Hvilke to oppgaver ville du undersøkt først, og hvorfor?»** Record whether they discover the rest of the chart without help and notice and consider task 1, which starts outside this viewport. Do not require a predetermined choice.
- **«Vis alle oppgavene i kartet.»** Record discovery of horizontal scrolling and whether zone orientation survives scrolling.
- **«Løs samme prioriteringsoppgave med listen og kartet. Hvilken gir deg tryggest grunnlag?»** Compare reasoning, misunderstandings and active time; vary the first view across participants.

Technical layout passes do not establish that the initial crop supports sound
prioritisation. This follow-up is prepared, not run, and selects no default view.
