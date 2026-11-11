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
4. november. `aksel` har erstattet dem, og målingene står under [Aksel](#aksel).

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

## Aksel

`aksel-design` og `figma-workflow` er erstattet av `aksel`
([ADR 0038](../adr/0038-en-liten-aksel-skill-malt-frem.md)). Radene over viser de
to gamle skillene slik de var 4. november.

Underveis ble Aksel-teamets `aksel-builder` målt med scenarioene over, 11. november:

| Scenario | Agent | Treff | Lastet |
| --- | --- | --- | --- |
| `aksel-design` | designer | 3/3 | `aksel-builder` 3 |
| `figma-workflow` | designer | 2/3 | `aksel-builder` 2, `design-prototype` 2 |

Disse scenarioene nevner Aksel eller designsystemet. I vanlige bestillinger til
Grillmester som ikke gjør det, ble `aksel-builder` lastet i 7 av 22 økter og
`aksel` i 19 av 22 på de samme oppgavene. De tallene står i
[baseline for Aksel](aksel-outcomes-baseline.md). Scenarioene over er ikke kjørt
på nytt for `aksel`.

### Designer i en ekte app

Designer ble prøvd gjennom Copilot CLI 1.0.105, uten nettleserfane, i en kopi av
en ekte Nav-app som ikke bruker avviklede komponenter.

Opus 5.5, to økter med `aksel-builder` i pluginen. Bestillingen var en melding om
at et møte er flyttet, og en knapp med kalenderikon. Den ene økten hadde Aksel
MCP:

- Ingen av øktene lastet `aksel-builder`. Designer fulgte `design-prototype`, som
  er forhåndslastet, og appens egne mønstre.
- Med MCP gjorde den to oppslag. Uten MCP slo den ikke opp noe hos Aksel.
- Begge ga `LocalAlert` med `status="announcement"` og `CalendarIcon`, som er
  riktig for versjonen appen har installert. Prosjektet sto urørt i begge.
- Øktene kostet 77 og 118 credits.

Haiku 5.5, ti økter. Bestillingen var en advarsel om at hele tjenesten er nede:

| Plugin | Økter | Komponent i forslaget |
| --- | --- | --- |
| Main, med `aksel-design` | 3 | avviklet `Alert` i 3 |
| Grenen, `aksel` ikke forhåndslastet | 4 | `Alert` i 1, `LocalAlert` i 1, 2 uten forslag |
| Grenen, `aksel` forhåndslastet i Designer | 3 | `GlobalAlert` i 3 |

Designer forhåndslaster derfor `aksel` sammen med `design-prototype`. En peker
til skillen i steget der forslaget lages, ga ingen lasting i to økter.

Opus 5.5 med `aksel` forhåndslastet, én økt med samme bestilling: forslaget brukte
`GlobalAlert` med tittel og innhold, prosjektet sto urørt, og økten kostet 47
credits.

Designer-øktene med `aksel` gikk før skillen ble kortet ned til tre regler.
Regelen om avviklede komponenter er den samme i den endelige teksten, men
Designer er ikke kjørt på nytt med den.

I fire av de ti Haiku-øktene endret Designer selve prosjektet i stedet for den
eide kopien, også med pluginen fra main. Det er ikke målt på Opus utover de to
øktene over, der prosjektet sto urørt.
