# Baseline for skillvalg

Målt 4. november 2026 på plugin 0.13.0 (`c85eba6`) med Copilot CLI 1.0.105 og
Haiku 5.5. Hvert scenario er kjørt fem ganger, til sammen 185 økter. Se
[scenarioene](../skill-routing-scenarios.md) for hvordan testen er bygd opp.

- I øktene der en skill var forventet, lastet modellen riktig skill i 25 av 175.
- Modellen lastet aldri feil skill.
- Den lastet ingen skill i de ti øktene der ingen skill trengs.

Haiku 5.5 kan gjengi fasene og skillene i prompten, men lar være å laste dem. Den
løser mange oppgaver uten skill. Tallene sier derfor mest om små modeller, og de
gjelder ikke for en sterkere modell.

Fem kjøringer viser bare store forskjeller. Sammenlign med samme modell og samme
scenarioer, og ikke les noe ut av ett eller to treff.

Målingen er gjort før åtte skills ble samlet i `nav-platform`. Scenarioene har
beholdt ID-ene i tabellen, men forventer nå `nav-platform`. Tabellen viser hva
som ble lastet da. `lumi-survey` er fjernet senere, så det scenarioet finnes ikke
lenger.

| Scenario | Agent | Treff | Uten skill | Lastet |
| --- | --- | --- | --- | --- |
| `grilling` | grillmester | 0/5 | 5 | – |
| `domain-modeling` | grillmester | 0/5 | 5 | – |
| `wayfinder` | grillmester | 1/5 | 4 | `wayfinder` 1 |
| `tdd` | grillmester | 0/5 | 5 | – |
| `diagnosing-bugs` | grillmester | 0/5 | 5 | – |
| `review` | grillmester | 0/5 | 5 | – |
| `security-review` | grillmester | 4/5 | 1 | `security-review` 4 |
| `pull-request` | grillmester | 0/5 | 5 | – |
| `to-spec` | grillmester | 0/5 | 5 | – |
| `to-issues` | grillmester | 1/5 | 4 | `to-issues` 1 |
| `triage` | grillmester | 3/5 | 2 | `triage` 3 |
| `issue-management` | grillmester | 0/5 | 5 | – |
| `api-design` | grillmester | 1/5 | 4 | `api-design` 1 |
| `auth-overview` | grillmester | 0/5 | 5 | – |
| `kafka-topic` | grillmester | 0/5 | 5 | – |
| `kotlin-ktor` | grillmester | 0/5 | 5 | – |
| `nais-manifest` | grillmester | 0/5 | 5 | – |
| `nav-troubleshoot` | grillmester | 3/5 | 2 | `nav-troubleshoot` 3 |
| `observability-setup` | grillmester | 0/5 | 5 | – |
| `postgresql-review` | grillmester | 0/5 | 5 | – |
| `architecture-review` | grillmester | 0/5 | 5 | – |
| `improve-codebase-architecture` | grillmester | 0/5 | 5 | – |
| `prototype` | grillmester | 0/5 | 5 | – |
| `readme-update` | grillmester | 0/5 | 5 | – |
| `klarsprak` | grillmester | 0/5 | 5 | – |
| `dulting` | grillmester | 2/5 | 3 | `dulting` 2 |
| `lumi-survey` | grillmester | 1/5 | 4 | `lumi-survey` 1 |
| `okr` | doctor-who | 1/5 | 4 | `okr` 1 |
| `team-status` | doctor-who | 0/5 | 5 | – |
| `workshop-design` | doctor-who | 4/5 | 1 | `workshop-design` 4 |
| `produktledelse` | doctor-who | 0/5 | 5 | – |
| `aksel-design` | designer | 4/5 | 1 | `aksel-design` 4 |
| `design-prototype` | designer | 0/5 | 5 | – |
| `figma-workflow` | designer | 0/5 | 5 | – |
| `accessibility-review` | designer | 0/5 | 5 | – |
| `no-skill-typo` | grillmester | 5/5 | 5 | – |
| `no-skill-question` | grillmester | 5/5 | 5 | – |

Etter at Grillmester-prompten navnga fasene, ga de åtte faseskillene samme
resultat som over: 5 av 40. Prompten alene endrer altså ikke hva Haiku 5.5 laster.
