# Interactive concept exploration

This study extends the existing review-round protocol with three new design
questions, six authored directions and actual browser interaction. It is a
simulated role review followed by scripted browser checks, not research with
human participants. All application, task and appointment data is synthetic.

## Questions and panel lenses

The service-design, content-design, keyboard-use and implementation perspectives
were applied before writing the sketches. Each pair uses the same question and
facts; a different arrangement must not win by receiving better sample data.

| Study | Two directions | Task and concern |
| --- | --- | --- |
| Mobile correction | Step-by-step / correct from the overview | Find a missing fare, enter 340, review, go back, confirm and return. The content perspective asks whether the missing item is explicit. The keyboard perspective checks a real error-summary link and recovery when the initiating button disappears. |
| Operational overview | Prioritized table / grouped work stages | Recover from an error, inspect loading and an empty filter, then return to the same three tasks. The service perspective distinguishes “no matching tasks” from “we could not fetch tasks”. The implementation perspective requires every declared density setting to visibly change the target. |
| Appointment reversal | Current appointment first / change action first | Explore another time, return without changing the appointment, cancel, choose the safe return and try undo. The content perspective checks the specific consequence before confirmation. The implementation perspective treats undo as a product hypothesis that needs a real service contract. |

These are meaningful alternatives in information order and scanning cost, not
three cosmetic treatments of the same card. The operational table and grouped
stages expose identical task IDs, descriptions, deadlines and status words.
Both appointment directions offer the same two alternative times.

## Reproduce

Run the source script with existing Playwright and matched Aksel v8 packages:

```sh
node scripts/smoke_visual_exploration.cjs \
  --playwright-module /path/to/existing/node_modules/playwright \
  --browser-channel chrome \
  --aksel-project /path/to/existing/project \
  --evidence-dir /tmp/grillmester-exploration-rounds
```

Use `--case mobile-correction`, `--case operations-recovery` or
`--case appointment-reversal` to repeat an affected case. The script never
installs packages. It creates an isolated temporary consumer, copies only the
installed CSS into it, launches a private local preview and closes its browser
context and server on completion or failure. It does not publish, contact a
model or use an existing consumer as a write target. Screenshots omit the
address bar; reports omit capability URLs and session credentials.

The recorded run uses real Chrome in headless mode and installed
`@navikt/ds-react` / `@navikt/ds-css` **8.19.2**. Components are rendered through
React SSR, including Button, TextField, ErrorSummary, RadioGroup, LocalAlert,
Loader, Tag and Table. Each SSR render gets a unique identifier prefix; browser
checks reject duplicate IDs. No component classes or semantic tokens are
overridden. The current primary [ErrorSummary](https://aksel.nav.no/komponenter/core/errorsummary.md),
[TextField](https://aksel.nav.no/komponenter/core/textfield.md),
[Radio](https://aksel.nav.no/komponenter/core/radio.md) and
[LocalAlert](https://aksel.nav.no/komponenter/core/localalert.md) references
were read, with installed component types and actual output authoritative for
the 8.19.2 fixtures.

## Acceptance protocol

1. Set the viewport before opening the sketch: mobile 390 × 844, operations
   1440 × 1000, appointment 1280 × 960. Inspect actual rendered screenshots.
2. Follow authored states through native buttons, including Enter and Space.
   A disappearing button must leave focus on its visible declared target.
   Workshop controls must report the state selected in the sketch.
3. Type into the actual mobile field and select an actual appointment radio.
   Returning to that state must preserve the local DOM value. Neither value
   may be copied into the feedback protocol.
4. Verify that all this exploration leaves zero saved feedback and submission 0. Loading remains an authored state until deliberately
   changed; the sketch does not simulate successful network work on a timer.
5. Comment on the relevant state, including on a button in comment mode. The
   button must not perform its ordinary action. Save the comment, change the
   sketch's state and restore it with **Vis situasjon**. Both state and density
   must restore where declared.
6. Keep a part from another direction with **Behold denne delen**. The
   operations case combines two wishes to keep parts from different directions
   with a separate reservation. Send one explicit batch per study; verify the
   exact comments and original context delivered by the public feedback reader.
7. Check equal comparison widths, horizontal overflow, duplicate IDs, browser
   exceptions and completed external resource requests. Record measurements,
   not a claim of broad accessibility compliance.

## Findings and refinement

The first browser round found a real mismatch between component appearance and
available interaction: the mobile ErrorSummary looked like a link, while the
preview stripped even a same-document fragment target. After a narrowly scoped
runtime fix, actual pointer activation and Shift+Tab followed by Enter both
focused the matching field. The outer URL and iframe hash stayed unchanged.
This was verified with the real Aksel component, not a substitute link.

The first mobile screenshot after a state change also exposed the need to
reveal the new state when its initiating button disappears. After the runtime
scroll/focus fix, the review heading and first fact are visible below the
fixed header, with focus still on the declared target. The focused follow-up
records the geometry in iframe coordinates.

The design review also found an inert density setting in the first table
fixture. The refined fixture uses the installed Table's medium/small sizes,
while grouped stages use authored spacing changes. The first table also
omitted the explicit status words available in the grouped direction. Those
words were added before comparison. This is a fixture correction, not a
runtime bug. `operations-recovery-round-one.png` preserves the initial design.

The completed interaction run measured 326 px of content in the
390 px viewport, with no horizontal document overflow. Both desktop
comparisons allocated exactly 436 px to each direction. Aksel buttons retained
20 px inline padding and 18 px type. Repeated separate SSR calls produced no
duplicate IDs. There were no browser exceptions or completed external resource
requests.

Each full run of the three studies delivered three deliberate batches: three
comments and four kept-part decisions in total. Since
[ADR 0025](../adr/0025-behold-som-innspill-og-juster-visning-i-prov.md), the
four kept parts are wishes in the same batches. The same native field value and radio selection
survived returning within the open sketch, without entering comment context.
Comments preserved the declared situation, and **Vis situasjon** restored it
after later local changes. Commenting on the retry or safe-return button did
not trigger that button.

| Observed measurement | Result |
| --- | --- |
| Mobile viewport / content / document width | 390 / 326 / 390 px |
| Mobile review heading / fixed header bottom | 120 / 57 px |
| Mobile review first fact bottom / viewport height | 222 / 844 px |
| Tab from fare to forward action | 1 |
| Tab from cancelled-state target to undo | 1 |
| Desktop comparison directions | 436 / 436 px in both studies |
| Table target, comfortable → compact | 371 → 307 px high |
| Grouped stages, comfortable → compact | 590 → 526 px high |
| Duplicate IDs / browser exceptions / completed external resources | 0 / 0 / 0 |

Final-run measurements and screenshots are stored in
`/tmp/grillmester-exploration-rounds/exploration-results.json` alongside the
named PNGs. The additional focused mobile verification is
`exploration-mobile-correction-results.json`; a single-case rerun does not
overwrite the full-run report. The reports record the browser mode, resolved Aksel version, exact
viewports, comparison widths, density heights, observed Tab counts, submitted
item counts and absence of external resources.

## Design conclusions

- Keep the task, error, consequence and safe return visible in the authored
  state. A comment becomes much more useful when it carries that state rather
  than only a location on the page.
- Explicit local exploration followed by one batch worked for all three tasks.
  Native field input and a clicked state button should not imply agreement or
  permission to change source code.
- Mixed directions are valuable: the review can keep one direction's structure
  and another direction's explanation while preserving a separate reservation.
  A single “winner” would lose this distinction.
- In these comparisons the fixed content area gives each desktop direction
  436 px. The operational groups therefore stack vertically. The table exposes
  more task rows at once; this measured space cost should inform discussion,
  not be mistaken for a participant preference or a full-width dashboard test.
- The mobile field can be edited, but the following review is an authored sample
  with 340 kroner. It does not calculate or validate typed values. A true
  arbitrary-input application prototype belongs in the executable-prototype
  workflow. The appointment undo similarly demonstrates an interaction idea,
  not a supported transaction or reservation guarantee.

No screen-reader session, native app host, browser zoom, business backend,
durable storage, cross-session resume or real participant completion rate is
claimed by these checks. Headless viewport checks are not device testing.
