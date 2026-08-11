# Grillmester 🔥

Grillmester er en kostnadsbevisst arbeidsflyt for GitHub Copilot. Den avklarer
først det som faktisk er uklart, delegerer én avgrenset implementasjon og
krever fersk evidens. Uavhengig review brukes for ikke-trivielle endringer og
når risiko eller repository-policy krever det.

## Status

Dette er en eksperimentell POC med foreløpige arbeidsnavn. Den tester en
liten, men reell verdikjede:

1. `grillmester` avklarer, planlegger og orkestrerer.
2. `grillmester-implementer` implementerer én komplett vertikal slice.
3. `grillmester-reviewer` vurderer diff, krav og evidens uavhengig.
4. Skills for grilling, self-review og sikkerhetsreview lastes progressivt.

Setup/Doctor, solo-utvikler, design, produktarbeid og flere teknologipakker er
bevisst utsatt til denne flyten er verifisert i målklientene.

POC-en er verifisert med GitHub Copilot CLI 1.0.79-9: native pluginformat,
marketplace med `source: "."`, discovery av alle tre agenter,
plugin-kvalifisert Grillmester-kjøring, installasjon av tre skills og progressiv
lasting av review-skillen. En remote branch-ref i consumerens
`.github/copilot/settings.json` auto-installerer og aktiverer pluginen. Dette er
også verifisert manuelt fra et separat, isolert consumer-repo.

Eksakt commit-pinning er verifisert separat med marketplace-katalogens
`plugins[].source.sha`: klienten installerte innhold fra den angitte
40-tegns-SHA-en selv om marketplace-branchen hadde nyere innhold. En tidligere
kontroll brukte commit-SHA som marketplace-repoets `ref`; denne klienten
forsøkte da å klone SHA-en som en navngitt Git-ref. Det testet et annet lag og
sa ingenting om katalogens dokumenterte `source.sha`-mekanisme. POC-katalogen
beholder `source: "."` mens branchen er i utvikling. Før release skal katalogen
peke eksplisitt på det fryste plugininnholdet.

Delegasjon mellom agentene, rollback, VS Code og Copilot cloud gjenstår før
stabil release.

## Installer POC-en

Copilot CLI kan legge til repoet som en egen marketplace og installere
pluginen derfra:

```bash
copilot plugin marketplace add navikt/grillmester
copilot plugin install grillmester@grillmester
```

Start deretter Copilot og velg `grillmester` som agent. Komponentene kan vises
med kvalifiserte navn som `grillmester:grillmester` dersom en klient må skille
mellom flere plugins.

Under utvikling kan en lokal checkout monteres uten installasjon:

```bash
copilot --plugin-dir . --agent=grillmester:grillmester
```

### Test i VS Code

Bruk en separat Git-workspace og en ren VS Code-profil, slik at en tidligere
CLI-installasjon ikke gir falsk positiv. Legg denne POC-konfigurasjonen i
`.github/copilot/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "grillmester": {
      "source": {
        "source": "github",
        "repo": "navikt/grillmester",
        "ref": "agent/plugin-poc"
      }
    }
  },
  "enabledPlugins": {
    "grillmester@grillmester": true
  }
}
```

Bekreft at `chat.plugins.enabled` er aktivert, åpne Chat og send den første
meldingen. VS Code skal anbefale pluginen. Finn den eventuelt i Extensions med
filteret `@agentPlugins @recommended`, godkjenn marketplace-trust og aktiver
pluginen. Bekreft deretter at den offentlige `grillmester`-agenten kan velges,
at de tre `grillmester-*`-skillene finnes, og at en ufarlig samtale ikke endrer
workspaceet. Noter VS Code- og Copilot-extension-versjon, nødvendige trust-steg
og om pluginen fortsatt er tilgjengelig etter restart.

Hvis recommendation-flyten feiler, bruk en lokal checkout som diagnostisk
kontroll i workspace-innstillingene:

```json
{
  "chat.plugins.enabled": true,
  "chat.pluginLocations": {
    "/absolute/path/to/grillmester": true
  }
}
```

Hvis den lokale pluginen virker, men recommendation ikke gjør det, ligger
problemet i marketplace-, settings- eller policy-laget, ikke i pluginformatet.

POC-en bruker det native Copilot-formatet i `plugin.json`. Den bruker med vilje
ikke Agent Plugins 1.0-manifestet, fordi den åpne 1.0-standarden foreløpig bare
har et portabelt gulv for skills og MCP, ikke custom agents.

## Repo-spesifikke regler

Pluginen distribuerer agenter og skills, ikke
`copilot-instructions.md`, `AGENTS.md` eller path-scoped instructions. Slike
filer eies av consumer-repoet og skal inneholde lokale fakta: bygg- og
testkommandoer, domeneord, artefaktspråk, datakategorier, autentisering og
andre regler som ikke er portable.

En senere Setup-skill kan hjelpe et repo å skrive et lite lokalt adapterlag,
men installasjon eller oppgradering av pluginen skal aldri synkronisere eller
overskrive consumer-filer.

## Verifiser

```bash
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
```

Før merge av en endring i agent- eller skillkontrakten skal pakken i tillegg
monteres med `copilot --plugin-dir .` i en isolert `COPILOT_HOME`. Testen skal
bekrefte plugin-kvalifisert agent-discovery og relevant skill-loading uten å
skrive til et consumer-repo.

## Eierskap

Grillmester utvikles av Team eSyfo i Nav og er tilgjengelig under
[MIT-lisensen](LICENSE). Kildegrunnlag og tredjepartsmerknader er dokumentert i
[PROVENANCE.md](PROVENANCE.md) og [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
