# Baseline for skillvalg

Målt 4. november 2026 med Copilot CLI 1.0.105 og Haiku 5.5, etter at åtte skills ble
samlet i `nav-platform`. Hvert scenario er kjørt tre ganger, til sammen 105 økter. Se
[scenarioene](../skill-routing-scenarios.md) for hvordan testen er bygd opp.

- I øktene der en skill var forventet, lastet modellen riktig skill i 40 av 99.
- Én økt lastet en skill i tillegg til den riktige. Ingen økt lastet bare feil skill.
- Den lastet ingen skill i de seks øktene der ingen skill trengs.

Skills med en klar utløser i beskrivelsen lastes ofte, som `architecture-review`,
`dulting` og skillene til Designer. Flytskillene Grillmester-prompten nevner, som
`tdd`, `review` og `grilling`, lastes nesten aldri av Haiku 5.5. Modellen løser mange
slike oppgaver uten skill. Tallene sier mest om små modeller, og de gjelder ikke for
en sterkere modell.

Den første målingen, på plugin 0.13.0, ga 25 av 175, men den brukte
`--max-ai-credits`. Flagget legger en beskjed om å være sparsom inn i hver tur, og
det undertrykker lasting. `nav-platform` gikk fra 0 av 40 med flagget til 6 av 24
uten det. Bruk aldri flagget i en måling, og sammenlign ikke med den første målingen.

Tre kjøringer viser bare store forskjeller. Sammenlign med samme modell og samme
scenarioer, og ikke les noe ut av ett eller to treff.

Scenarioene har beholdt ID-ene fra før sammenslåingene, men forventer nå
`nav-platform`, `produktledelse` eller `issue-management`.

Radene for `okr`, `team-status`, `workshop-design` og `produktledelse` er målt etter
at de tre første ble slått sammen med `produktledelse`. Haiku 5.5 lastet da ikke
skillen for mål og status, selv om `okr` alene ga 3 av 3. Et smalt navn er en sterk
utløser. Opus 5.5, målt utenfor Copilot CLI, fant skillen og leste riktige referanser
for begge forespørslene. Doctor Who bruker Opus som standard.

Radene for `to-issues`, `triage` og `issue-management` er målt etter at de to første
ble slått sammen med `issue-management`. Oppdeling og issue-forespørsler gikk opp, mens
vurdering av en feilrapport gikk fra 2 av 3 til 0 av 3. Opus 5.5, målt utenfor Copilot
CLI, fant skillen og leste `triage.md` og `AGENT-BRIEF.md` for den samme forespørselen.

Radene for `aksel-design` og `figma-workflow` viser de to skillene slik de var
4. november. `aksel-builder` har erstattet dem, og den nye målingen står under
[Etter aksel-builder](#etter-aksel-builder).

| Scenario | Agent | Treff | Uten skill | Lastet |
| --- | --- | --- | --- | --- |
| `grilling` | grillmester | 0/3 | 3 | – |
| `domain-modeling` | grillmester | 0/3 | 3 | – |
| `wayfinder` | grillmester | 1/3 | 2 | `wayfinder` 1 |
| `tdd` | grillmester | 0/3 | 3 | – |
| `diagnosing-bugs` | grillmester | 0/3 | 3 | – |
| `review` | grillmester | 0/3 | 3 | – |
| `security-review` | grillmester | 2/3 | 1 | `security-review` 2 |
| `pull-request` | grillmester | 0/3 | 3 | – |
| `to-spec` | grillmester | 0/3 | 3 | – |
| `to-issues` | grillmester | 3/3 | 0 | `issue-management` 3 |
| `triage` | grillmester | 0/3 | 3 | – |
| `issue-management` | grillmester | 2/3 | 1 | `issue-management` 2 |
| `api-design` | grillmester | 0/3 | 3 | – |
| `auth-overview` | grillmester | 0/3 | 3 | – |
| `kafka-topic` | grillmester | 3/3 | 0 | `nav-platform` 3 |
| `kotlin-ktor` | grillmester | 0/3 | 3 | – |
| `nais-manifest` | grillmester | 0/3 | 3 | – |
| `nav-troubleshoot` | grillmester | 3/3 | 0 | `nav-platform` 3 |
| `observability-setup` | grillmester | 0/3 | 3 | – |
| `postgresql-review` | grillmester | 0/3 | 3 | – |
| `architecture-review` | grillmester | 3/3 | 0 | `architecture-review` 3 |
| `improve-codebase-architecture` | grillmester | 3/3 | 0 | `improve-codebase-architecture` 3 |
| `prototype` | grillmester | 2/3 | 1 | `prototype` 2 |
| `klarsprak` | grillmester | 0/3 | 3 | – |
| `dulting` | grillmester | 3/3 | 0 | `dulting` 3 |
| `okr` | doctor-who | 0/3 | 3 | – |
| `team-status` | doctor-who | 0/3 | 3 | – |
| `workshop-design` | doctor-who | 2/3 | 1 | `produktledelse` 2 |
| `produktledelse` | doctor-who | 1/3 | 2 | `produktledelse` 1 |
| `aksel-design` | designer | 3/3 | 0 | `aksel-design` 3 |
| `design-prototype` | designer | 3/3 | 0 | `design-prototype` 3 |
| `figma-workflow` | designer | 3/3 | 0 | `figma-workflow` 3, `design-prototype` 1 |
| `accessibility-review` | designer | 3/3 | 0 | `accessibility-review` 3 |
| `no-skill-typo` | grillmester | 3/3 | 3 | – |
| `no-skill-question` | grillmester | 3/3 | 3 | – |

## Etter aksel-builder

Målt 11. november 2026 med samme oppsett, etter at `aksel-builder` erstattet
`aksel-design` og `figma-workflow`
([ADR 0038](../adr/0038-delte-skills-tas-inn-uendret.md)). De to første scenarioene
har beholdt ID-ene og forventer nå `aksel-builder`. Det tredje er nytt: en utvikler
ber Grillmester bygge et skjema og sier at teamet bruker Navs designsystem, uten å
nevne Aksel eller pakkenavnet. Grillmester-prompten navngir `aksel-builder` i
Build-fasen.

| Scenario | Agent | Treff | Uten skill | Lastet |
| --- | --- | --- | --- | --- |
| `aksel-design` | designer | 3/3 | 0 | `aksel-builder` 3 |
| `figma-workflow` | designer | 2/3 | 0 | `aksel-builder` 2, `design-prototype` 2 |
| `aksel-builder` | grillmester | 3/3 | 0 | `aksel-builder` 3, `tdd` 1 |

Figma til kode gikk fra 3 til 2 av 3: én økt lastet bare `design-prototype`. Det er
innenfor det tre kjøringer kan skille, men `figma-workflow` hadde en smalere
utløser.
