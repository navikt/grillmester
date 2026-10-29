# Utvikle Grillmester

Bruk en lokal checkout og et disponibelt testrepo. Ikke mount utviklingspluginen
i et repo med pågående arbeid som du ikke vil risikere å endre.

## Lokal kjøring

```bash
git clone git@github.com:navikt/grillmester.git
cd /path/to/a/disposable-test-repo
```

Start Copilot slik du vanligvis gjør i Nav, last
`/path/to/grillmester/plugin` med klientens dokumenterte `--plugin-dir`-flyt,
og velg agent med `/agent`. En lokal mount gjelder bare prosessen du starter.
Den endrer ikke den vanlige personlige installasjonen.

For å inspisere terminalbindingen uten å starte en klient kan du bruke
launcheren fra checkouten eller en installert distribusjon med eksplisitt klient
og agent:

```bash
python3 /absolute/path/to/grillmester/scripts/grillmester.py \
  --client opencode --agent grillmester --print-command
```

Kommandoen skriver den eksakte cplt-invokasjonen og endrer ingen OpenCode-
runtimefiler.

## Verifikasjon

Linux-jobbene i PR-validering og release bruker `ubuntu-24.04`, slik at
testing, bygging og publisering deler samme OS-generasjon. Dette er et
kontrollert testmiljø, ikke et krav til brukerens operativsystem. Verten
oppdaterer fortsatt runner-imaget innenfor denne OS-generasjonen.
Etter at `ubuntu-latest` skiftet til Ubuntu 26.04, observerte vi gjentatt
agent-discovery-feil gjennom cplt med uendrede klientbinærer, mens direkte
OpenCode-discovery bestod. Årsaken og støtte for denne kombinasjonen er fortsatt
uavklart; ikke flytt runtimeportene før den nye verten er verifisert med de
samme kontrollkravene.

På macOS har focused OpenCode-smoken sporadisk manglet resultater fra
shellverktøyet. Årsaken er fortsatt uavklart; en vellykket omkjøring forklarer
ikke feilen eller erstatter resultatet fra den opprinnelige kjøringen.

Releasekatalogen genereres fra pluginmanifestene. Det native OpenCode 1-
targetet genereres fra samme reviewede plugininnhold og den eksplisitte
policyen i `policy/opencode-v1.json`. De fokuserte lokalmodelltargetene avledes
deretter fra den kanoniske pluginen og det fulle OpenCode-targetet gjennom
`policy/focused-context-v1.json`. Når canonical agent-, skill- eller
policyinnhold endres, regenerer targetene i denne rekkefølgen:

```bash
python3 scripts/generate_copilot_manifest.py
python3 scripts/generate_opencode.py
python3 scripts/generate_context_projections.py
python3 scripts/generate_agentpakke_manifest.py
```

Ikke håndrediger `plugin/manifest.json`, `targets/opencode-v1/`,
`targets/opencode-v1-focused/` eller
`targets/copilot-cli-focused-v1/`. Ikke håndrediger
`.nav-pilot/agentpakke.json`; den peker deterministisk på disse fire
payloadene og avledes sist. CI verifiserer blant annet katalogpinning,
innholdslås, full og fokusert agent-/skillroster, OpenCode-projeksjon,
progressive lenker og install–oppgradering–rollback–avinstallering.

Terminalbrukere skal installere den deterministiske release-`tar.gz`-en ved å
verifisere checksummen og pakke ut arkivet, ikke fra en source-checkout.
Checkout-installasjon
er bare utviklingsinput. Bundlebygget verifiserer Copilot-pluginen, launcheren,
OpenCode-targetet og focused-targetene og binder dem til eksakt source-SHA i
`DISTRIBUTION-MANIFEST.json`. Det ytre distribusjonsnavnet er
`grillmester-terminal-v1`; `opencode-v1` er fortsatt identiteten til det indre
OpenCode-targetet. Eksakte klientversjoner ligger kun under manifestets
`releaseTest`-metadata:

```bash
python3 scripts/build_opencode_bundle.py \
  --source-root . \
  --source-sha "$(git rev-parse HEAD)" \
  --output /tmp/grillmester-terminal-v1.tar.gz
shasum -a 256 /tmp/grillmester-terminal-v1.tar.gz
```

Et releasebygg skal kjøres to ganger og gi byte-identiske arkiver før den
detached checksumfilen publiseres. Release-workflowen publiserer bundle og
checksum som to immutable assets.

Kjør den lokale hovedgaten:

```bash
python3 scripts/generate_marketplace.py --mode development --check
python3 -m py_compile scripts/grillmester.py scripts/grillmester_local.py scripts/smoke_grillmester_local.py scripts/generate_copilot_manifest.py scripts/generate_context_projections.py scripts/generate_agentpakke_manifest.py
python3 scripts/generate_copilot_manifest.py --check
python3 scripts/generate_opencode.py --check
python3 scripts/generate_context_projections.py --check
python3 scripts/generate_agentpakke_manifest.py --check
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
node --check plugin/skills/design-prototype/scripts/server.js
node --check plugin/skills/design-prototype/scripts/helper.js
node --check plugin/skills/design-prototype/scripts/workshop.js
node --check plugin/skills/design-prototype/scripts/design-contract.js
node --check plugin/skills/design-prototype/scripts/comments.js
node --check plugin/skills/design-prototype/scripts/feedback-store.js
node --check plugin/skills/design-prototype/scripts/canvas-state.js
node --check plugin/skills/design-prototype/scripts/workspace-store.js
node --check plugin/skills/design-prototype/scripts/workspace-promotion.js
node --check plugin/skills/design-prototype/scripts/workspace-state.js
node --check plugin/skills/design-prototype/scripts/editor-contract.js
node --check plugin/skills/design-prototype/scripts/editor-bindings.js
node --check plugin/skills/design-prototype/scripts/editor.js
node --check plugin/skills/design-prototype/scripts/app-runtime.js
node --check plugin/skills/design-prototype/scripts/application-connection-state.js
node --check plugin/skills/design-prototype/scripts/application-connection-view.js
node --check plugin/skills/design-prototype/scripts/application-contract.js
node --check plugin/skills/design-prototype/scripts/application-error.js
node --check plugin/skills/design-prototype/scripts/application-inspector.js
node --check plugin/skills/design-prototype/scripts/application-proxy.js
node --check plugin/skills/design-prototype/scripts/application-server.js
node --check plugin/skills/design-prototype/scripts/application-shell.js
node --check plugin/skills/design-prototype/scripts/application-workspace.js
node --check plugin/skills/design-prototype/scripts/application-proposals.js
node --check plugin/skills/design-prototype/scripts/application-proposal-view.js
node --check plugin/skills/design-prototype/scripts/html-embedding.js
node --check plugin/skills/design-prototype/scripts/html-inspection.js
node --test plugin/skills/design-prototype/tests/*.test.js
node --check plugin/extensions/visual-companion/extension.mjs
node --check plugin/extensions/visual-companion/adapter.mjs
node --check plugin/extensions/visual-companion/backend.mjs
node --check plugin/extensions/visual-companion/runtime.mjs
node --check plugin/extensions/visual-companion/tests/sdk-smoke.mjs
node --check scripts/smoke_visual_canvas.cjs
node --check scripts/smoke_visual_application.cjs
node --check scripts/smoke_visual_workbench.cjs
node --check scripts/visual-smoke-controls.cjs
node --test plugin/extensions/visual-companion/tests/*.test.mjs
python3 scripts/smoke_plugin_install.py
python3 scripts/smoke_opencode.py
python3 scripts/smoke_opencode_runtime.py --cplt cplt
python3 scripts/smoke_grillmester_local.py \
  --cplt cplt --opencode opencode --copilot copilot
```

Visual Companion kan også testes direkte i nettleser uten en modellklient.
Den valgfrie smoken bruker en allerede installert Playwright og nettleser,
oppretter et disponibelt prosjekt og rydder sin egen sesjon etterpå:

```bash
node scripts/smoke_visual_companion.cjs \
  --playwright-module /absolute/path/to/playwright/index.js \
  --browser-channel chrome \
  --headed \
  --evidence-dir /tmp/visual-companion-evidence
```

Utelat `--playwright-module` hvis pakken allerede kan resolves lokalt, og
`--browser-channel` for Playwrights eksisterende Chromium-installasjon.
Bruk `--headed` for resize-kontrollen med Chrome på macOS. Den lokale Chrome-
versjonen kan miste treffområder for faste elementer i en sandboxet iframe når
en hodeløs test endrer viewport etter versjonsbytter. Feilen er også reprodusert
på uendret baseline; samme sekvens fungerer i en synlig nettleser. Smoken
kontrollerer resize uten å laste siden på nytt, slik at utkastet må bevares.
Smoken installerer ingenting. Den prøver konseptvalg, skjema og arbeidsoversikt
på desktop og smale vinduer: kommentarer med mus og tastatur, tekstforslag og
angre, innsending, svar, versjonsbytte, fokus og bevaring av utkast. HTML-fixturene
bruker bevisst fallback-stiler; en separat visuell gjennomgang med consumerens
verifiserte Aksel-versjon er fortsatt nødvendig. Skjermleserbruk og klientens
videreføring av `comments.js wait` må verifiseres separat.

`scripts/smoke_visual_workshop.cjs` bruker samme flagg og tester deklarerte
justeringer, sammenligning, ønsker om å beholde deler og ugyldige deklarasjoner. Kjør den
ved endringer i denne kontrakten, i tillegg til kommentarsmoken. Bruk separate
evidensmapper for de to kjøringene. Ingen av dem installerer avhengigheter eller
starter en modellklient.

`scripts/smoke_visual_scenarios.cjs` supplerer disse med åtte sammenhengende
oppgaver for ulike simulerte roller, blant annet fire varianter, flere utkast,
lange norske tekster, skjema i kort og feil under innsending. Se
[scenarioer og akseptansekriterier](testing/visual-companion-scenarios.md).
Flagget `--aksel-project` kan bruke en eksisterende, samversjonert Aksel-
installasjon til faktisk komponentrendering uten å endre kildeprosjektet.

`scripts/smoke_visual_review_rounds.cjs` følger fem nye oppgaver over flere
gjennomganger: to faner, endret retning, gjenåpnet forbehold, faktisk 200 %
nettleserzoom og frakobling med et utkast. Zoomcaset velger 200 % i Chromes
innstillinger og måler CSS-viewport og enhetsskala. En emulert mindre viewport
med høyere enhetsskala er ikke nettleserzoom. Se
[flere runder med innspill](testing/visual-companion-review-rounds.md).
Klientforutsetninger og egne akseptprøver for Copilot app, CLI og andre flater
står i [klientmatrisen](testing/visual-companion-client-capabilities.md).

`scripts/smoke_visual_application.cjs` prøver direkte verkstedvisning uten popup
og en syntetisk kjørende app gjennom
den faktiske adapteren og en simulert canvasvert. Bruk samme Playwright-,
nettleser- og evidensflagg som over. Prøven skal dekke navigasjon, valg av del eller
hele siden, innspill, bevisst innsending, svar, gjenåpning og avviste skissehandlinger;
den gjør ingen kildeendringer eller modellkall. Dette er ikke en native appprøve,
og en liten CSS-viewport beviser ikke 200 % nettleserzoom.
`scripts/smoke_visual_workbench.cjs` dekker app → innspill → forslag → videre
innspill, køstatus og gjenåpning i samme verksted. Begge kjøres i CI med Chromium.
`app-runtime.test.js` starter bare eide syntetiske prosesser og prøver kort retur,
privat kontroll, gjenbruk, avbrudd, utløp og opprydding av vanlige barn. Se
[beslutningen om demolivsløp](adr/0028-eid-livslop-for-lokale-demoer.md).

En isolert prøve av appens canvas-API ligger i `experiments/canvas-review/`.
Den bruker et medfølgende SDK mot en simulert vert og et separat nettleseroppsett;
den starter ingen modellklient og inngår ikke i pluginpayloaden. Se
[canvas-protokollen](testing/visual-companion-canvas.md) og
[kjøreinstruksjonene](../experiments/canvas-review/README.md).

Plugin-smoken skal bekrefte 8 agenter, 44 skills og byte-eksakt installasjon,
oppgradering, rollback og avinstallering. I compatibility-jobben krever den at
minimumsklienten Copilot CLI `1.0.79` annonserer hele flaggrosteren som local-run
eier i `--help`, uten modell- eller nettverkskall. Den eksakte local-smoken
kjører flaggene med release-testklienten. OpenCode-smoken bruker
OpenCode `1.18.20`, kopierer targetet til en skrivbar tempmappe og bekrefter native
discovery av 8 agenter, 44 skills, 44 commands, fravær av modellpin,
deklarerte permissionregler og at native `read` løser consumerens `AGENTS.md`
fra riktig repo uten å kontakte en modell. Den beviser derfor ikke
at `AGENTS.md` faktisk påvirker et modellsvar, modelldrevet skillbruk,
delegering, write-godkjenning eller kvalitet. Den separate runtime-smoken bruker
en deterministisk loopback-provider gjennom ekte OpenCode og bekrefter native
delegering, blokkert `.env`, progressiv skill-reference, avvist write og en
eksplisitt auto-godkjent write uten å kontakte en modell. Begge smokene hopper
kontrollert over når binæren mangler. Den eksakte release-testbaselinen er
OpenCode `1.18.20`, Copilot CLI `1.0.80` og cplt
`2026.08.17-062831-1008a92`. De er testinput, ikke runtimepinner;
standardlauncheren støtter kompatible 1.x-klienter og nyere datostemplede
cplt-releaser. Releasegaten skal kjøre de eksakte smokene:

```bash
python3 scripts/smoke_opencode.py \
  --opencode /absolute/path/to/opencode \
  --require-binary
python3 scripts/smoke_opencode_runtime.py \
  --opencode /absolute/path/to/opencode \
  --require-binary \
  --cplt cplt
python3 scripts/smoke_grillmester_local.py \
  --cplt /absolute/path/to/cplt \
  --opencode /absolute/path/to/opencode \
  --copilot /absolute/path/to/copilot \
  --require-binaries
```

Runtime-smoken bruker en deterministisk provider og beviser ikke kvaliteten til
en lokal eller ekstern modell. Local-smoken kjører focused/full i begge
klienter gjennom den offentlige `local run`-flaten, krever eksakt lokal modell
i hvert request, tester syntetiske ambient credentials og caller-PATH-verktøy,
og tvinger normal Copilot-delegering til Grill-inspektøren. En separat fake-`gh`
beviser current-repo issue-opprettelse med eksplisitt token og cplt-blokkering av
cross-repo, destruktive og tokenuttrekkende kommandoer. Ingen GitHub-request eller
cloudmodell brukes. Smoken erstatter ikke en separat kvalitetspilot med den
konkrete lokale modellen. Agentpakkemanifestet er en kildekontrakt for
`nav-pilot` og inngår ikke i terminalbundle-en; launcherne har ingen runtime-
avhengighet til `nav-pilot` eller en installert Copilot-agent.

Launcher- og formeltestene skal i tillegg bevise systemklientkontrakten: en
manglende OpenCode-installasjon gir `brew install opencode`, installert Copilot
CLI virker uten OpenCode, `doctor` skiller `skip` fra eksplisitt feil, ingen
klienter gir en samlet feil, og formelen oppretter aldri `libexec/clients` eller
legger en privat klientkatalog først på `PATH`.

## Discovery-budsjett

Validatoren begrenser samlet UTF-8-størrelse for navn og beskrivelser til
13 KiB. Dette er en enkel vekstratchet, ikke en simulering av klientens
tokenisering. Kort ned discoverytekst før grensen eventuelt økes.

## Dokumentasjonskontrakt

Bruk [CONTEXT.md](../CONTEXT.md) som kanonisk ordliste for prosjektspesifikke
begreper. Arkitekturbeslutninger som er vanskelige å reversere, overraskende
uten kontekst **og** resultat av en reell trade-off, hører hjemme som
sekvensielt nummererte ADR-er i [`docs/adr/`](adr/). Hold hver ADR fokusert på
beslutningen og hvorfor den ble tatt, men ta med kontekst, alternativer og
konsekvenser når de trengs. Operasjonelle prosedyrer og detaljerte kontrakter
kan ligge i egne guider og runbooks.

Når du endrer agenter, skills eller pakkeinndeling:

- oppdater [agent- og skillkartet](agents-and-skills.md)
- hold [installasjonskommandoene](installation.md) copy/paste-klare
- oppdater klient-/releasegater dersom capability-grensen endres
- behold Team eSyfo som vedlikeholder **for Nav**, ikke som produktscope
- oppdater [PROVENANCE](../PROVENANCE.md) og tredjepartsmerknader ved
  kilde-/assetendringer

For å rulle ut kjører du `python3 scripts/bump_version.py patch` i PR-en som
skal ut, og merger den. `Release`-workflowen publiserer katalogen og den
immutable releasen automatisk. Se [release-runbooken](release-runbook.md) for
detaljer og for hva du gjør når et løp stopper.
