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
node --check plugin/skills/grillmester-design-prototype/scripts/server.js
node --check plugin/skills/grillmester-design-prototype/scripts/helper.js
node --test plugin/skills/grillmester-design-prototype/tests/server.test.js
python3 scripts/smoke_plugin_install.py
python3 scripts/smoke_opencode.py
python3 scripts/smoke_opencode_runtime.py --cplt cplt
python3 scripts/smoke_grillmester_local.py \
  --cplt cplt --opencode opencode --copilot copilot
```

Plugin-smoken skal bekrefte 7 agenter, 43 skills og byte-eksakt installasjon,
oppgradering, rollback og avinstallering. I compatibility-jobben krever den at
minimumsklienten Copilot CLI `1.0.79` annonserer hele flaggrosteren som local-run
eier i `--help`, uten modell- eller nettverkskall. Den eksakte local-smoken
kjører flaggene med release-testklienten. OpenCode-smoken bruker
OpenCode `1.18.20`, kopierer targetet til en skrivbar tempmappe og bekrefter native
discovery av 7 agenter, 43 skills, 43 commands, fravær av modellpin,
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

Se [release-runbooken](release-runbook.md) før publisering.
