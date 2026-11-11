# Baseline for referanser

Målt 4. november 2026 med Copilot CLI 1.0.105 og Haiku 5.5, tre økter per
referanse i engangsrepoer. Meldingen ber om skillen, så tallene sier om agenten går
videre fra en lastet skill til riktig referanse. Om skillen lastes uten hint, står i
[baseline for skillvalg](skill-routing-baseline.md). Kjør målingen med
`scripts/measure_reference_reads.py`.

Etter endringen ble referansen lest i 153 av 162 økter. Det gjelder alle
referanser. Under to av tre:

- `design-prototype/references/application-opening.md`: 0 av 3.
- `design-prototype/references/design-handoff.md`: 1 av 3.

| Skill | Lest |
| --- | --- |
| `aksel-design` (erstattet 11. november, se under) | 3/3 |
| `app-sandbox-setup` | 12/12 |
| `architecture-review` | 6/6 |
| `create-a-skill` | 9/9 |
| `design-prototype` | 10/15 |
| `diagnosing-bugs` | 3/3 |
| `domain-modeling` | 6/6 |
| `dulting` | 6/6 |
| `improve-codebase-architecture` | 3/3 |
| `issue-management` | 8/9 |
| `klarsprak` | 8/9 |
| `nav-platform` | 33/33 |
| `produktledelse` | 31/33 |
| `security-review` | 6/6 |
| `tdd` | 6/6 |
| `wayfinder` | 3/3 |

`aksel-design` hadde da bare `patterns.md`. Fire referanser som kopierte Aksels egne
dokumenter, var fjernet. I seks kjøringer med spørsmål om komponenter, tokens og
migrering hentet agenten dokumentasjonen fra aksel.nav.no i alle seks.

## Måling av aksel-builder

11. november ble Aksel-teamets `aksel-builder` fra `navikt/copilot` målt som
erstatning for `aksel-design` og `figma-workflow`
([ADR 0038](../adr/0038-en-liten-aksel-skill-malt-frem.md)). Med samme oppsett,
Copilot CLI 1.0.105 og Haiku 5.5, ble skillen lastet i 30 av 30 økter, og referansen
ble lest i 15 av 30.

| Referanse | Lest |
| --- | --- |
| `figma-to-code.md` | 3/3 |
| `mcp-workflow.md` | 3/3 |
| `setup-and-imports.md` | 3/3 |
| `migrations.md` | 2/3 |
| `theming.md` | 2/3 |
| `primitives-layout.md` | 1/3 |
| `tokens-styling.md` | 1/3 |
| `accessibility.md` | 0/3 |
| `components.md` | 0/3 |
| `icons.md` | 0/3 |

Tre sporede økter viser hva agenten gjorde i stedet. For ikoner og komponenter gikk
den rett til Aksels dokumentasjon, slik reservetabellen i `SKILL.md` beskriver, og
svarte derfra uten å åpne referansen. Én økt hentet en sti som ikke står i Aksels
indeks. I ni økter, fordelt på komponenter, layout og tokens, nådde agenten grensen
på tolv verktøykall mens den bygde.

Måleoppsettet har ikke Aksel MCP, så tallene gjelder skillens reserveløp, og de
gjelder Haiku 5.5. Sterkere modeller er ikke målt. Tre scenarioer ble rettet etter
første kjøring og målt på nytt, og tabellen viser de rettede: `accessibility.md`
viste til en fil som ikke finnes i engangsrepoet, `mcp-workflow.md` sa ikke at
brukeren hadde MCP-en, og `migrations.md` ba om en oppgradering repoet alt hadde
gjort. Summen ble 15 av 30 begge ganger.

`aksel-builder` ble ikke tatt inn. `aksel`, som erstattet den, har to referanser
bak en Les først-tabell, `figma-to-code.md` og `migration.md`. Begge ble lest i
3 av 3 økter med samme oppsett.

## Ny måling av design-prototype

5. november ga `design-prototype` 14/15 med samme oppsett, mot 10/15 over.
`application-opening.md` fikk 3 av 3 og `design-handoff.md` 2 av 3. To ting endret
seg: pekerne fikk en Les først-blokk foran stegene, og verktøyet teller nå første
prosalinje i hver seksjon. Før så det bare etter filens lengste linjer, så et oppslag
på én seksjon kunne stå som ulest. Noe av hoppet skyldes altså tellingen.

En lenke til i samme setning ga 1 av 3 for `application-opening.md`, så hold
Les først til én peker per ønske. De andre skillene er ikke målt på nytt.

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

Tre økter viser bare store forskjeller. En referanse teller som lest når teksten
kom tilbake til modellen, eller når `view` av filen lyktes. Et delvis oppslag teller
også, så tallene sier ikke at hele referansen ble lest.
