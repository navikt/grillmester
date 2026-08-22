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

## Verifikasjon

Releasekatalogen genereres fra pluginmanifestene. Det native OpenCode 1-
targetet genereres fra samme reviewede plugininnhold og den eksplisitte
policyen i `policy/opencode-v1.json`. Når canonical agent-, skill- eller
policyinnhold endres, regenerer det committede targetet først:

```bash
python3 scripts/generate_opencode.py
```

Ikke håndrediger `targets/opencode-v1/`. CI verifiserer blant annet
katalogpinning, innholdslås, agent-/skillroster, OpenCode-projeksjon,
progressive lenker og install–oppgradering–rollback–avinstallering.

OpenCode-sluttbrukere skal installere den deterministiske release-`tar.gz`-en
med detached SHA-256, ikke en source-checkout. Checkout-installasjon er bare
utviklingsinput. Bundlebygget verifiserer target, profiler og manager og binder
dem til eksakt source-SHA i `DISTRIBUTION-MANIFEST.json`:

```bash
python3 scripts/build_opencode_bundle.py \
  --source-root . \
  --source-sha "$(git rev-parse HEAD)" \
  --output /tmp/grillmester-opencode-v1.tar.gz
shasum -a 256 /tmp/grillmester-opencode-v1.tar.gz
```

Et releasebygg skal kjøres to ganger og gi byte-identiske arkiver før den
detached checksumfilen publiseres.

Kjør den lokale hovedgaten:

```bash
python3 scripts/generate_marketplace.py --mode development --check
python3 scripts/generate_opencode.py --check
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
node --check plugin/skills/grillmester-design-prototype/scripts/server.js
node --check plugin/skills/grillmester-design-prototype/scripts/helper.js
node --test plugin/skills/grillmester-design-prototype/tests/server.test.js
python3 scripts/smoke_plugin_install.py
python3 scripts/smoke_opencode.py
python3 scripts/smoke_opencode_runtime.py --cplt cplt
```

Plugin-smoken skal bekrefte 7 agenter, 42 skills og byte-eksakt installasjon,
oppgradering, rollback og avinstallering. OpenCode-smoken bruker OpenCode
`1.18.20`, kopierer targetet til en skrivbar tempmappe og bekrefter native
discovery av 7 agenter, 42 skills, 42 commands, fravær av modellpin,
deklarerte permissionregler og at native `read` løser consumerens `AGENTS.md`
fra riktig repo uten å kontakte en modell. Den bekrefter også at en bruker-eid
hybridprofil kan pinne bare Kokk til en lokal modell. Den beviser derfor ikke
at `AGENTS.md` faktisk påvirker et modellsvar, modelldrevet skillbruk,
delegering, write-godkjenning eller kvalitet. Den separate runtime-smoken bruker
en deterministisk loopback-provider gjennom ekte OpenCode og bekrefter native
delegering, blokkert `.env`, progressiv skill-reference, avvist write og en
eksplisitt auto-godkjent write uten å kontakte en modell. Begge smokene hopper
kontrollert over når binæren mangler. En release-gate skal kreve eksakt
OpenCode `1.18.20`, eksakt cplt `2026.08.17-062831-1008a92` for alle
cplt-baserte profiler og smokene eksplisitt:

```bash
python3 scripts/smoke_opencode.py \
  --opencode /absolute/path/to/opencode \
  --require-binary
python3 scripts/smoke_opencode_runtime.py \
  --opencode /absolute/path/to/opencode \
  --require-binary \
  --cplt cplt
```

Runtime-smoken bruker en deterministisk provider og beviser ikke kvaliteten til
en lokal eller ekstern modell. Manageren og bundle-en har ingen avhengighet til
`nav-pilot-agent` eller en installert Copilot-agent. `--direct` er bare et
eksplisitt opt-out fra cplt-sandbox og egresspolicy.

## Discovery-budsjett

Validatoren begrenser samlet UTF-8-størrelse for navn og beskrivelser til
13 KiB. Dette er en enkel vekstratchet, ikke en simulering av klientens
tokenisering. Kort ned discoverytekst før grensen eventuelt økes.

## Dokumentasjonskontrakt

Når du endrer agenter, skills eller pakkeinndeling:

- oppdater [agent- og skillkartet](agents-and-skills.md)
- hold [installasjonskommandoene](installation.md) copy/paste-klare
- oppdater klient-/releasegater dersom capability-grensen endres
- behold Team eSyfo som vedlikeholder **for Nav**, ikke som produktscope
- oppdater [PROVENANCE](../PROVENANCE.md) og tredjepartsmerknader ved
  kilde-/assetendringer

Se [release-runbooken](release-runbook.md) før publisering.
