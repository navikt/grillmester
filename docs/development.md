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
```

Plugin-smoken skal bekrefte 7 agenter, 42 skills og byte-eksakt installasjon,
oppgradering, rollback og avinstallering. OpenCode-smoken bruker OpenCode
`1.18.19`, kopierer targetet til en skrivbar tempmappe og bekrefter native
discovery av 7 agenter, 42 skills, 42 commands, fravær av modellpin,
deklarerte permissionregler og at native `read` løser consumerens `AGENTS.md`
fra riktig repo uten å kontakte en modell. Den bekrefter også at en bruker-eid
hybridprofil kan pinne bare Kokk til en lokal modell. Den beviser derfor ikke
at `AGENTS.md` faktisk påvirker et modellsvar, modelldrevet skillbruk,
delegering, write-godkjenning eller kvalitet. Smoken hopper kontrollert over
når binæren mangler. En release-gate skal i stedet kreve den eksplisitt:

```bash
python3 scripts/smoke_opencode.py \
  --opencode /absolute/path/to/opencode \
  --require-binary
```

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
