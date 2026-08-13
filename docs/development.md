# Utvikle Grillmester

Bruk en lokal checkout og et disponibelt testrepo. Ikke mount utviklingspluginen
i et repo med pågående arbeid som du ikke vil risikere å endre.

## Lokal kjøring

```bash
git clone git@github.com:navikt/grillmester.git
cd /path/to/a/disposable-test-repo
copilot --experimental --sandbox --plugin-dir /path/to/grillmester/plugin \
  --agent=grillmester:grillmester
```

En lokal mount gjelder bare prosessen du starter. Den endrer ikke den vanlige
personlige installasjonen.

## Verifikasjon

Releasekatalogen genereres fra pluginmanifestene. CI verifiserer blant annet
katalogpinning, innholdslås, agent-/skillroster, progressive lenker,
evalkontrakt og install–oppgradering–rollback–avinstallering.

Kjør den lokale hovedgaten:

```bash
python3 scripts/generate_marketplace.py --mode development --check
python3 scripts/validate.py
python3 scripts/validate_evals.py
python3 -m unittest discover -s tests -v
node --check plugin/skills/grillmester-design-prototype/scripts/server.js
node --check plugin/skills/grillmester-design-prototype/scripts/helper.js
node --test plugin/skills/grillmester-design-prototype/tests/server.test.js
python3 scripts/smoke_plugin_install.py
```

NAV-tillegget har en egen pluginmappe. Verifiser også denne eksplisitt gjennom
generator, validator og install-smoke. En grønn standardpakke beviser ikke at
tillegget er fritt for døde referanser.

Begge kan lastes i samme lokale sesjon fordi `--plugin-dir` kan gjentas:

```bash
copilot --experimental --sandbox --plugin-dir /path/to/grillmester/plugin \
  --plugin-dir /path/to/grillmester/plugin-nav \
  --agent=grillmester:grillmester
```

## Dokumentasjonskontrakt

Når du endrer agenter, skills eller pakkeinndeling:

- oppdater [agent- og skillkartet](agents-and-skills.md)
- hold [installasjonskommandoene](installation.md) copy/paste-klare
- oppdater klient-/releasegater dersom capability-grensen endres
- behold Team eSyfo som vedlikeholder **for NAV**, ikke som produktscope
- oppdater [PROVENANCE](../PROVENANCE.md) og tredjepartsmerknader ved
  kilde-/assetendringer

Se [release-runbooken](release-runbook.md) før publisering.
