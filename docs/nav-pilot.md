# nav-pilot og terminalpiloter — pågående arbeid

Grillmester distribueres i dag som en native Copilot-plugin. Bruk
[plugininstallasjonen i README](../README.md#kom-i-gang) for vanlig bruk.
Integrasjonen med nav-pilot og pilotene for OpenCode og lokale modeller
videreutvikles ved siden av pluginen.

## nav-pilot-agentpakka

Grillmester publiserer en Tier 2-agentpakke for
[nav-pilot](https://github.com/navikt/copilot), med ferdige pakker for Copilot
CLI og OpenCode. Installasjon for utprøving:

```bash
nav-pilot install --source navikt/grillmester
```

nav-pilot lagrer en revisjonspinnet pakke, verifiserer innholdet og starter
klienten med valgt agent. Dette er en egen installasjons- og oppdateringsvei;
Copilot-pluginens automatiske oppdatering flytter ikke nav-pilot-pinnen.
Se [agentpakke-installasjon](installation.md#agentpakke-for-nav-pilot).

Per nav-pilot `2026.09.15-175926-f3614e6` krever oppstart av Tier 2-pakker
cplt. Denne flyten har ikke et konfigurasjonsvalg for å bruke Copilots egen
sandbox i stedet. Native pluginbruk følger Copilot-klientens runtime.

## Utvalgte fellesskills

Målet er å gjenbruke et eksplisitt utvalg fellesskills, for eksempel Aksel,
Nais og security, uendret i Grillmester. Det betyr ikke å installere hele
nav-pilots innhold hos brukerne.

`aksel-builder` er den første: den er tatt inn uendret fra `navikt/copilot` på en
låst commit, slik [ADR 0038](adr/0038-delte-skills-tas-inn-uendret.md) beskriver.
`scripts/port_skill.py` henter en ny versjon fra en checkout av kilden og beviser
at kopien er lik. En endring i en fellesskill må fortsatt bygges, valideres og
publiseres som en ny Grillmester-versjon før den når brukerne. Nais og security
er ikke tatt inn på denne måten ennå.

[Avklaringen om gjenbruk](https://github.com/navikt/copilot/issues/840)
beskriver hvordan nav-pilot kan sette sammen pakker ved kjøring. Copilot-pluginen
kan ikke hente innhold fra et annet repo, så Grillmester bærer en kopi i både
pluginen og agentpakken. Det gjenstår å automatisere oppdateringen.

## OpenCode og lokale modeller — pilot fra checkout

OpenCode laster ikke Copilot-plugins. OpenCode og lokale modeller kan
foreløpig piloteres fra en checkout på macOS.
Videre terminaldistribusjon samordnes med nav-pilot. Installer ønsket klient, og
cplt hvis du vil ha sandbox rundt den. Lokale modeller krever cplt.

```bash
brew install opencode navikt/tap/cplt
# eller for Copilot CLI: brew install --cask copilot-cli
```

Du trenger en lokal checkout av `navikt/grillmester`. Den er pilotinput, ikke en
installert eller immutable release. Fra repoet du vil arbeide i:

```bash
cd /path/to/consumer-repo
python3 /absolute/path/to/grillmester/scripts/grillmester.py doctor
python3 /absolute/path/to/grillmester/scripts/grillmester.py --client opencode --agent grillmester
```

For en lokal modell starter du først en OpenAI-kompatibel modellserver på
loopback og kjører:

```bash
python3 /absolute/path/to/grillmester/scripts/grillmester.py local setup --client opencode
python3 /absolute/path/to/grillmester/scripts/grillmester.py local doctor
python3 /absolute/path/to/grillmester/scripts/grillmester.py local launch
```

For lokale modeller lager launcheren isolert OpenCode-config og kjører
terminalsesjonen gjennom cplt. Den støtter OpenCode 2.x fra `2.2.5`, Copilot CLI
1.x fra `1.0.100` og cplt fra testbaselinen. Hver modell må kvalitetsvalideres
separat.
Se [OpenCode-guiden](opencode.md), [guiden for lokale modeller](local-models.md)
og [klientstatus og releasegater](trust-and-client-support.md).
