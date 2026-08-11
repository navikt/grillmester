# Grillmester 🔥

Grillmester er en Copilot-plugin for å forme, gjennomføre og kontrollere
programvare- og produktarbeid. Den pakker det agentoppsettet Team eSyfo har
pilotert i `syfo-budstikka`, sammen med de portable design- og
produktarbeidsflytene fra Hovmester.

Dette er en full-port POC: pluginmekanismen er bevist, mens innholdet nå
paritetskontrolleres og klienttestes før første stabile release.

## Velg riktig inngang

| Agent | Bruk den når |
| --- | --- |
| `grillmester` | Oppgaven er viktig eller uklar og trenger avklaring, speccing, domenemodellering, arkitekturvalg eller ADR før en avgrenset implementasjon og evidensbasert review. |
| `barista` | Oppgaven allerede er godt nok spesifisert eller er enkel nok for en lett, direkte solo-flyt med implementasjon og verifikasjon. |
| `designer` | Designarbeidet trenger utforsking, Aksel, Figma eller en designprototype. |
| `doctor-who` | Produktarbeidet gjelder mål, status, prioritering, discovery, workshops, teamhelse eller Nav-arkitektur. |

De interne agentene er `kokk` (implementasjon), `grill-inspektor`
(uavhengig review), `researcher` (kildestøttet research) og `konditor`
(frontendprototype for Designer). De er ikke egne brukerinnganger.

Agentene pinner reviewede modeller. Før utrulling må organisasjonspolicyen
tillate disse modellene; en manglende modell er en eksplisitt preflight-feil,
ikke en grunn til å la klienten velge en tilfeldig erstatning.

Navnene fra det piloterte oppsettet er beholdt i denne porten. Eventuelle
navneendringer vurderes etter at atferdspariteten er bevist, slik at navne- og
funksjonsendringer ikke blandes sammen.

## Én plugin, progressivt innhold

Hele pakken installeres samlet. Det finnes ingen frontend-/backend-collections;
Copilot ser korte skillbeskrivelser og laster selve arbeidsflyten og tilhørende
referanser først når de trengs.

| Område | Skills |
| --- | --- |
| Avklaring og plan | `grilling`, `grill-me`, `grill-with-docs`, `domain-modeling`, `wayfinder`, `to-spec`, `to-issues`, `handoff` |
| Implementasjon og kvalitet | `review`, `pull-request`, `security-review`, `architecture-review`, `prototype`, `diagnosing-bugs`, `tdd`, `integration-tests`, `e2e-tests`, `improve-codebase-architecture`, `create-a-skill` |
| NAV/backend | `api-design`, `auth-overview`, `kafka-topic`, `kotlin-ktor`, `kotlin-spring`, `lumi-survey`, `nais-manifest`, `nav-troubleshoot`, `observability-setup`, `postgresql-review` |
| Design | `accessibility-review`, `aksel-design`, `figma-workflow`, `design-prototype` |
| Produkt | `dulting`, `nav-architecture-review`, `okr`, `produktledelse`, `team-status`, `workshop-design` |
| Samarbeid og tekst | `issue-management`, `triage`, `readme-update`, `klarsprak` |

Tabellen bruker de kjente kortnavnene. De 43 kanoniske runtime-ID-ene har
prefikset `grillmester-`, for eksempel `grillmester-security-review`. Det
hindrer at en personlig eller repo-lokal skill med samme kortnavn stille
skygger den reviewede pluginvarianten.

Den maskinlesbare innholdslåsen i
[`policy/content-lock.json`](policy/content-lock.json) er pakkens reviewede BOM:
eksakt agent- og skillroster, operative agentkontrakter og pinnede
kilderevisjoner. Den distribueres ikke til consumer-repoer og er ikke en
synkmekanisme.

## Utvikling og lokal test

Den native Copilot-pluginen ligger i `plugin/`. Monter en checkout direkte:

```bash
copilot --plugin-dir /absolute/path/to/grillmester/plugin \
  --agent=grillmester:grillmester
```

Klienten kan vise plugin-komponenter med kvalifiserte navn som
`grillmester:grillmester`. Den lokale mounten er den tryggeste testen mens
branchen er under utvikling; den krever ingen installasjon og skal kjøres i et
tomt, disponibelt testrepo.

Repoet er også sin egen marketplace. Etter at en publisert revisjon finnes:

```bash
copilot plugin marketplace add navikt/grillmester#<reviewed-release-tag>
copilot plugin install grillmester@grillmester
```

Utviklingskatalogen bruker `source: "plugin"`. En releasekatalog skal i stedet
peke til det fryste plugininnholdet med `plugins[].source.sha` og `path:
"plugin"`. Det er denne katalogpinnen — ikke en commit-SHA brukt som Git-ref —
som gir eksakt og reproduserbar installasjon.

Etter en validert endring på `main` genererer publiseringsflyten en katalog-only
commit på `marketplace`-branchen. Katalogen peker tilbake på eksakt validert
innholds-SHA; den kopierer eller transformerer ikke pluginpayloaden. Branchen er
en kandidatkanal. En stabil release-tag opprettes på den valgte katalogcommiten,
og consumer-repoer pinner denne taggen i stedet for den flytende branchen.

## Repoaktivert installasjon

Et consumer-repo kan anbefale og aktivere den interne marketplacen med
`.github/copilot/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "grillmester": {
      "source": {
        "source": "github",
        "repo": "navikt/grillmester",
        "ref": "<reviewed-release-tag>"
      }
    }
  },
  "enabledPlugins": {
    "grillmester@grillmester": true
  }
}
```

Release-taggen identifiserer den reviewede marketplace-katalogen; katalogen
pinner igjen eksakt plugin-SHA. Oppgradering skjer som en vanlig, reviewet
dependency-endring av `ref`, ikke ved at Grillmester kopierer filer inn i
consumer-repoet.

Copilot CLI og Copilot cloud agent leser repo-innstillingen og bruker pluginen i
det aktuelle repoet. Den lokale CLI-installasjonen ligger utenfor worktreeet;
cloud-agenten løser pluginen i sitt isolerte miljø. Copilot app støtter plugins
og custom agents, men testes som en egen primærflate i denne POC-en i stedet for
at vi antar samme aktiveringsflyt. VS Code behandler repo-innstillingen som en
workspace-anbefaling og kan kreve et eksplisitt trust-/installsteg. Bruk en ren
VS Code-profil ved testing, slik at en tidligere CLI-installasjon ikke gir falsk
positiv.

Som diagnostisk lokal kontroll i VS Code:

```json
{
  "chat.plugins.enabled": true,
  "chat.pluginLocations": {
    "/absolute/path/to/grillmester/plugin": true
  }
}
```

Hvis lokal plugin virker, men recommendation-flyten ikke gjør det, ligger
feilen i marketplace-, settings- eller enterprise-policy-laget, ikke i
pluginformatet.

## Hvorfor native Copilot-format

Pakken bruker `plugin/plugin.json` uten Agent Plugins 1.0-`$schema`. Agent
Plugins 1.0 er en åpen, leverandørnøytral standard, men det portable 1.0-gulvet
dekker skills og MCP — ikke custom agents. Grillmester er agent-first, så den
native Copilot-manifestsemantikken er nødvendig i denne versjonen. Skillene er
likevel strukturert for progressiv lasting med `SKILL.md` og lokale
`references/`, `scripts/` og assets.

## Eksperimentell OpenCode-støtte

OpenCode leser ikke Copilot-marketplacen, `plugin.json` eller custom agents.
GitHub CLI kan derimot installere de samme standardiserte skillmappene direkte
til OpenCodes user-scope uten kopier i consumer-repoet:

```bash
gh skill install navikt/grillmester grillmester-dulting \
  --agent opencode --scope user --pin <reviewed-release-tag>
```

Dette tar med hele skill-treet, inkludert progressive referanser, scripts og
assets. Det gir ikke Grillmester-, Barista-, Designer- eller Doctor Who-agenten.
Project-scope anbefales ikke på maskiner som også bruker Copilot-pluginen,
fordi `.agents/skills` da kan skygge pluginens skill med samme ID.

`gh skill --all` er foreløpig kun en smoke-test. OpenCode ignorerer Copilot-
feltene som gjør `grill-me`, `grill-with-docs` og `handoff` manuelt styrte, og
alle skills må portabilitetsauditeres for klientspesifikke agent- og
verktøyantakelser før hele pakken kan kalles OpenCode-kompatibel.

## Repo-spesifikke regler

Pluginen distribuerer agenter og skills, ikke `copilot-instructions.md`,
`AGENTS.md` eller path-scoped instructions. Consumer-repoet eier lokale fakta
som bygg- og testkommandoer, domeneord, artefaktspråk, datakategorier,
autentisering og path-spesifikke invariants.

Portable språk-, sikkerhets- og reviewmetoder ligger i agentene og skillene.
Lokale instructions skal bare uttrykke consumerens faktiske delta. En senere
Setup-skill kan hjelpe med å oppdage og foreslå et tynt adapterlag, og Doctor
kan validere det, men plugininstallasjon og -oppgradering skal aldri
synkronisere eller overskrive consumer-filer.

## Verifisering

```bash
python3 scripts/generate_marketplace.py --mode development --check
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
node --check plugin/skills/grillmester-design-prototype/scripts/server.js
node --check plugin/skills/grillmester-design-prototype/scripts/helper.js
node --test plugin/skills/grillmester-design-prototype/tests/server.test.js
python3 scripts/smoke_plugin_install.py
```

Generator-sjekken håndhever én metadatafasit for plugin og marketplace.
Python-validatoren og enhetstestene kontrollerer manifestformat, eksakt roster
og agentkontrakt, frontmatter, progressive lenker, alternative manifestbaner,
symlinks, proveniens og sensitive eksempeldata. Node-testene håndhever
sikkerhetsgrensen rundt Visual Companion. Smoke-testen installerer den lokale
marketplacen i et disponibelt, isolert Copilot-hjem og verifiserer at alle åtte
agenter og 43 skills faktisk blir pakket. Før release skal pakken også bestå:

1. agent- og skilldiscovery med en lokal `--plugin-dir`-mount,
2. installasjon fra en katalog som pinner eksakt plugin-SHA,
3. repo-deklarativ installasjon og reell oppgave i Copilot cloud agent,
4. plugin- og custom-agentdiscovery i Copilot app, inkludert kvalifisert
   delegering til `grillmester:kokk`, `grillmester:grill-inspektor`,
   `grillmester:researcher` og `grillmester:konditor`,
5. installasjon og en ufarlig ende-til-endeoppgave i én pilotapp,
6. OpenCode user-scope skill-smoke og separat portabilitetsrapport,
7. ren VS Code-profil som en sekundær kompatibilitetskontroll.

## Eierskap

Grillmester utvikles av Team eSyfo i Nav og er tilgjengelig under
[MIT-lisensen](LICENSE). Kildegrunnlag og tredjepartsmerknader er dokumentert i
[PROVENANCE.md](PROVENANCE.md) og
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
