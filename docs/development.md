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

Releasekatalogen genereres fra pluginmanifestene. CI verifiserer blant annet
katalogpinning, innholdslås, agent-/skillroster, progressive lenker og
install–oppgradering–rollback–avinstallering.

Kjør den lokale hovedgaten:

```bash
python3 scripts/generate_marketplace.py --mode development --check
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
node --check plugin/skills/grillmester-design-prototype/scripts/server.js
node --check plugin/skills/grillmester-design-prototype/scripts/helper.js
node --test plugin/skills/grillmester-design-prototype/tests/server.test.js
python3 scripts/smoke_plugin_install.py
```

Smoken skal bekrefte hele pluginen: 7 agenter, 43 skills og byte-eksakt
installasjon, oppgradering, rollback og avinstallering.

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
