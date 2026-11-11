---
status: accepted
date: 2026-11-11
---

# Delte skills tas inn uendret

Supplerer ADR 0035 og ADR 0037.

Aksel har fått en MCP-server, og Aksel-teamet vedlikeholder selv skillen
`aksel-builder` i `navikt/copilot` og anbefaler den i
[Aksels dokumentasjon](https://aksel.nav.no/grunnleggende/kode/mcp-server.md).
Grillmester hadde `aksel-design` og `figma-workflow`, som begge kom fra en eldre
utgave via Hovmester. `figma-workflow` hadde en fargetabell med token-navn som
ikke finnes lenger, og begge manglet det `aksel-builder` har om ikoner, theming,
Tailwind og MCP-serveren. Et team som også bruker fellespakken fra `navikt/copilot`,
fikk to Aksel-skills med nesten like utløsere.

En skill som et annet team eier og vedlikeholder, tas derfor inn uendret i stedet
for å kopieres og tilpasses:

- `aksel-builder` erstatter `aksel-design` og `figma-workflow`. Alle filene i
  skillen er byte-identiske med `navikt/copilot` på en låst commit, unntatt
  katalogfilene `README.md` og `metadata.json`, som blir igjen hos kilden.
- ID-en er den samme som hos kilden, så oversikten får én Aksel-skill og ikke to
  nesten like. Har et team også installert kildens kopi i repoet eller hos
  brukeren, er det den som lastes, og `doctor` og konsument-preflighten melder
  skyggingen. Det er samme skill, men ikke nødvendigvis versjonen vi har låst og
  målt, så teamet bør velge én.
- Innholdslåsen fører skillen som `ported`, med kilde, commit og `contentSha256`.
  Valideringen feiler når en fil i en `ported` skill er endret lokalt. Ny versjon
  hentes med `scripts/port_skill.py` fra en checkout av kilden. Skriptet krever at
  commiten ligger på en gren hentet fra repoet låsen navngir, og det kan bevise at
  kopien er lik kilden. Det er ingen kobling ved kjøring: en ny versjon når
  brukerne først i en ny Grillmester-versjon.
- En `ported` skill er unntatt husreglene vi ikke kan følge uten å endre teksten:
  frontmatterfeltene `license` og `metadata` fra Agent Skills-spesifikasjonen er
  tillatt, og en lang referanse trenger ikke innholdsliste. Innholdssjekkene
  kjører fortsatt, men et funn kan ikke rettes hos oss. Det må derfor enten
  stoppe den nye versjonen eller føres som vurdert under `acceptedFindings` i
  innholdslåsen. Hver referanse har fortsatt et scenario i
  `scripts/measure_reference_reads.py`, og svakheter meldes til eieren.
- Pluginen leverer fortsatt ingen MCP-server. `aksel-builder` bruker Aksel MCP når
  økten har den, og ellers Aksels publiserte dokumentasjon. `doctor` sier fra når
  et repo som bruker Aksel, mangler verktøyene.
- Grillmester-prompten navngir `aksel-builder` i Build-fasen. `design-prototype`
  eier fortsatt forslag i kjørende apper og redigerbart Figma-design; Figma til
  kode er `aksel-builder` sin oppgave.

Den første målingen viser prisen for at vi ikke kan skjerpe pekerne selv: Haiku 5.5
lastet skillen i 30 av 30 økter, men leste referansen i omtrent halvparten. I de
sporede øktene gikk den rett til Aksels dokumentasjon, og flere brukte opp
verktøykallene på å bygge. Tallene står i
[baseline for referanser](../testing/reference-reads-baseline.md).

Konsekvensen er ellers at mønstrene i `aksel-design/references/patterns.md` forsvinner.
`aksel-builder` har egne layoutoppskrifter, og Aksel publiserer mønstre og maler
selv. Det som mangler der, foreslås hos eieren. Brief-modusen i `figma-workflow`
finnes ikke lenger: `aksel-builder` implementerer, og stopper når Figma-verktøy
mangler. OpenCode-projeksjonen tilpasser skillen som alle
andre, så byte-likheten gjelder kilden i `plugin/`. Agentpakken for nav-pilot
bærer samme kopi; nav-pilots `extends` ved kjøring brukes ikke, fordi
Copilot-pluginen ikke kan hente innhold fra et annet repo.

Dette reverserer valget fra 5. november om å beholde `figma-workflow` som egen
skill. Den hadde en smal utløser som små modeller traff, men innholdet var
utdatert, og `aksel-builder` nevner Figma til kode i beskrivelsen sin.
