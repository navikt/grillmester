# Baseline for referanser

Målt 4. november 2026 med Copilot CLI 1.0.105 og Haiku 5.5, tre økter per
referanse i engangsrepoer. Meldingen ber om skillen, så tallene sier om agenten går
videre fra en lastet skill til riktig referanse. Om skillen lastes uten hint, står i
[baseline for skillvalg](skill-routing-baseline.md). Kjør målingen med
`scripts/measure_reference_reads.py`.

Etter endringen ble referansen lest i 148 av 156 økter, og hver gang før
første endring. Det gjelder alle referanser. Under to av tre:

- `aksel-design/references/components.md`: 1 av 3.
- `design-prototype/references/application-opening.md`: 0 av 3.
- `design-prototype/references/design-handoff.md`: 1 av 3.

| Skill | Lest |
| --- | --- |
| `aksel-design` | 13/15 |
| `app-sandbox-setup` | 12/12 |
| `architecture-review` | 6/6 |
| `create-a-skill` | 9/9 |
| `design-prototype` | 10/15 |
| `diagnosing-bugs` | 3/3 |
| `domain-modeling` | 6/6 |
| `dulting` | 6/6 |
| `improve-codebase-architecture` | 3/3 |
| `klarsprak` | 8/9 |
| `nav-platform` | 33/33 |
| `okr` | 3/3 |
| `produktledelse` | 6/6 |
| `security-review` | 6/6 |
| `tdd` | 6/6 |
| `team-status` | 6/6 |
| `triage` | 3/3 |
| `wayfinder` | 3/3 |
| `workshop-design` | 6/6 |

## Hva pekeren betyr

Før endringen ble 115 av 180 lest. De 29 referansene som fikk ny peker, gikk fra 37
til 82 av 87, med samme oppsett før og etter.

| Peker | Eksempel før endringen | Lest av Haiku |
| --- | --- | --- |
| Tabell øverst | `nav-platform`, `workshop-design` | 38 av 39 |
| Steg med tydelig utløser | `diagnosing-bugs`, `domain-modeling`, `wayfinder` | 12 av 12 |
| Betingelse midt i teksten | `architecture-review`, `security-review` | 3 av 12 |
| «Se» i teksten | `tdd`, `aksel-design` | 10 av 24 |
| Lenkeliste til slutt | `klarsprak` | 1 av 9 |

Referanser hver gren trenger, står nå i `SKILL.md`: `review` har smells selv, og det
`tdd` trengte fra `tests.md`, står i skillen. Haiku leste ikke `tests.md` når oppgaven
var å skrive kode, uansett hvordan pekeren var formulert.

## Ekte økter

I 138 ekte økter på én maskin, der en skill med referanser var lastet, ble minst én
referanse lest i 73. `security-review` fikk 17 av 17, `architecture-review` 5 av 5 og
`review` 4 av 4. `aksel-design` fikk 0 av 9, `klarsprak` 2 av 11 og `tdd` 3 av 11.
Øktene gikk mest på sterkere modeller og eldre versjoner av skillene. Ikke alle
oppgaver trenger en referanse, så tallene viser mønsteret, ikke en feilrate.

## En sterkere modell

Opus 5.5, målt utenfor Copilot CLI, leste alle 16 referanser Haiku bommet på, i
kjøringer som ikke så fasiten. Den leste ofte alle referansene i skillen. Svake
pekere rammer derfor mest de billige modellene, og Opus bruker mer kontekst enn den
trenger.

## Når målingen må tolkes

`--max-ai-credits` legger en beskjed om å være sparsom inn i hver tur. Det endrer
atferden, så målingene bruker ikke flagget. Tallene under «Hva pekeren betyr» ble
målt med flagget. De er sammenlignbare med hverandre, men ikke med hovedtallet.

Tre økter viser bare store forskjeller. En referanse er lest bare når teksten kom
tilbake til modellen, eller når `view` av filen lyktes.
