---
status: accepted
date: 2026-08-23
---

# Bruk en fokusert kontekstprojeksjon for lokale modeller

## Kontekst

Den kanoniske pluginen og det fulle OpenCode 1-targetet gir hele Grillmester-
flaten: syv agenter og 42 skills, med 42 eksplisitte OpenCode-commands. Dette er
riktig default for GitHub Copilot, Copilot app og vanlig OpenCode-bruk, men
discovery-katalogen bruker en stor del av kontekstvinduet til mindre lokale
modeller før brukerens oppgave er behandlet.

En reell A/B-pilot med Qwen3.8-27B Q6 og samme korte oppgave målte 8 024 mot
13 667 inputtokens for focused/full OpenCode Barista og 15 841 mot 20 117 for
focused/full Copilot CLI. Det er henholdsvis 41,3 og 21,3 prosent mindre
inputkontekst. Alle fire kjedene gikk gjennom eksakt cplt til loopback, uten en
GitHub Copilot-cloudmodell eller premium request. Målingen er evidens for denne
oppgaven og modellkonfigurasjonen, ikke generell kvalitetsparitet.

Permission-filteret alene er ikke en ærlig distribusjonsflate. En OpenCode-
command som peker på en denied skill er fortsatt synlig, men kan ikke utføres.
En redusert opplevelse må derfor ha et redusert fysisk inventar og bare vise
innganger som faktisk virker.

## Beslutning

Den fulle kanoniske pluginen i `plugin/` og det fulle OpenCode-targetet i
`targets/opencode-v1/` forblir uendret og er fortsatt standard. Et separat,
deterministisk bygg genererer to private, fokuserte klienttargeter fra disse
fullrepresentasjonene:

- `targets/opencode-v1-focused/`
- `targets/copilot-cli-focused-v1/`

Begge targetene bruker samme reviewede roster:

- agentene `barista` og `grill-inspektor`
- skillsene `grillmester-diagnosing-bugs`,
  `grillmester-integration-tests`, `grillmester-pull-request`,
  `grillmester-review`, `grillmester-security-review` og `grillmester-tdd`
- nøyaktig seks OpenCode-commands, én for hver inkluderte skill

Security review inngår fordi Baristas kanoniske kontrakt krever den når
beskrivelsen matcher. Grill-inspektor inngår fordi Barista kan tilby uavhengig
review uten å laste resten av agentteamet.

`policy/focused-context-v1.json` eier roster, eksakte source-/outputpaths og
full-context-handoffen. `scripts/generate_context_projections.py` avleder begge
targetene og nekter å bygge fra et OpenCode-fulltarget som ikke matcher sitt
eget manifest. Genererte targets skal aldri håndredigeres.

OpenCode-projeksjonen kopierer reviewede OpenCode-adaptere, overlays,
permissions og command-wrappere fra fulltargetet. Den fjerner permissionlinjer
for Grillmester-skills som ikke finnes i den fokuserte projeksjonen. Copilot
CLI-projeksjonen kopierer den kanoniske pluginstrukturen, men fjerner `model:`
fra de to agentenes frontmatter slik at lokal BYOK-/sessionmodell arves. Den
private Copilot-projeksjonen publiseres ikke i marketplace eller Copilot app.

Begge adapterne bruker en liten, deterministisk focused-only tekstoverlay.
Instrukser som ellers ville lastet en utelatt agent eller skill erstattes med
runtimeuavhengig veiledning. Når Barista trenger agentteamet eller en
spesialistflate som bare finnes i fullversjonen, stopper den med:

```text
Status: NEEDS_FULL_CONTEXT
Resume with: grillmester local --full
```

Generatoren avviser alle gjenværende kvalifiserte agentreferanser og konkrete
`grillmester-*`-skillreferanser som ikke kan løses i den fokuserte rosteren.

Den fokuserte projeksjonen er default bare i en eksplisitt lokalmodell-flyt.
Vanlig `grillmester`, direkte marketplace-bruk og Copilot app bruker fortsatt
full plugin. Provider- eller modellnavn, localhost-flagg og ambient config skal
ikke brukes som heuristisk auto-deteksjon. Brukeren kan alltid velge full
kontekst eksplisitt.

## Grense og proveniens

En fokusert kontekstprojeksjon begrenser Grillmester-innholdet som distribueres
til klienten. Den er ikke en runtimeprofil og gir ingen garanti om lokal-only,
egress, sandbox, provider eller samlet kontekstbruk. Prosjekt- og brukereide
skills kan fortsatt øke klientens ambient kontekst etter klientens vanlige
precedence-regler når targetet brukes direkte. Den separate local-launcheren
lukker denne ambientflaten med privat HOME/klientstate og avviser kjente
prosjektkomponenter; dette er en runtimegaranti, ikke en egenskap ved
projeksjonen.

Begge manifestene binder policyen, source-manifestet eller pluginmanifestet,
alle genererte bytes og filmodi. Den fokuserte Copilot-projeksjonen kopierer
den kanoniske, releaseversjonerte `plugin.json` byte-eksakt. En RC-til-stable-
versjonsendring regenererer derfor også den private pluginen og dens manifest,
selv når agent- og skillinnholdet ellers er uendret. Releasekontrakten må
behandle dette som forventet avledet endring og aldri gjenbruke et eldre
focused-target under et nytt versjonsnummer.

Fulltargetenes 7/42-inventar og marketplace-pluginen er separate
regresjonskontrakter. En focused-endring kan ikke endre eller erstatte dem.

## Konsekvenser

- Lokale modeller får en vesentlig mindre Grillmester-katalog uten at standard
  GitHub Copilot- eller OpenCode-opplevelse degraderes.
- Commands og skills er konsistente: ingen utelatt skill annonseres gjennom en
  command som ikke kan virke.
- Samme roster og handoffsemantikk gjelder i begge terminalklienter, mens hver
  adapter beholder sitt native format.
- Det oppstår ingen installer-valgt kopilivssyklus eller synk inn i consumer-
  repoet. Begge targetene er immutable releaseinnhold.
- Spesialistoppgaver krever eksplisitt full kontekst. Dette er synlig adferd,
  ikke en stille kvalitetsreduksjon.
- Local-launcheren gir Copilot CLI et privat HOME og `COPILOT_HOME`, binder bare
  valgt `--plugin-dir` og setter kvalifiserte
  `subagents.agents.grillmester:<id>.model: inherit`-regler for alle syv
  agenter. Den deterministiske release-smoken tvinger normal delegering i både
  focused og full kontekst og krever at hovedagent, underagent og retur bruker
  den eksakte lokale modellen.
- Copilots `task`-tool har fortsatt et eksplisitt `model`-felt som modellen kan
  fylle inn per kall. Et slikt eksplisitt felt har høyere presedens enn
  `inherit`. Forced proxy og eksakt loopback-base-URL hindrer dette i å skape
  en cloudrute, men en lokal provider kan avvise eller aliasere det fremmede
  modellnavnet. Dette er en dokumentert delegerings-/tilgjengelighetsrest, ikke
  en egressfallback. Ikke lov universell modellbinding for modellgenererte,
  eksplisitte overrides før klienten tilbyr en policy som kan forby dem.

## Forkastede alternativer

- **Gjør focused til ny standard overalt:** ville redusere den reviewede
  GitHub Copilot-flaten og gjøre spesialistteamet usynlig for cloudmodeller som
  tåler full katalog.
- **Behold 42 filer og bruk bare permissions:** sparer for lite kontekst og
  etterlater commands som peker på denied skills.
- **Installer et brukerdefinert agentutvalg:** skaper mange artefaktvarianter,
  supportkombinasjoner og en ny mutable installasjonslivssyklus.
- **Slank den kanoniske Barista-teksten først:** gir mindre gevinst enn å fjerne
  irrelevant discovery og risikerer semantisk drift for alle klienter.
- **Auto-detekter lokal modell fra provider-ID:** provider-ID-er er ikke en
  stabil trustgrense og kan representere lokal, cloud eller hybrid kjøring.
- **Publiser focused som egen marketplace-plugin:** skaper identitets- og
  oppdateringskollisjoner i appen uten å løse terminalens kontekstbehov.
