# Grillmester 🔥

Grillmester er en kostnadsbevisst arbeidsflyt for GitHub Copilot. Den avklarer
først det som faktisk er uklart, delegerer én avgrenset implementasjon og
krever fersk evidens. Uavhengig review brukes for ikke-trivielle endringer og
når risiko eller repository-policy krever det.

## Status

Dette er en eksperimentell POC med de endelige komponentnavnene. Den tester en
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
`.github/copilot/settings.json` auto-installerer og aktiverer pluginen.

Full commit-SHA i samme `ref` virker **ikke** i denne klientversjonen. CLI-en
forsøker `git clone --branch <SHA>` og feiler fordi commit-SHA-en ikke er en
remote branch eller tag. Stabil distribusjon er blokkert til klienten håndterer
SHA korrekt, eller en immutabel tag/release-bane er bevist. Delegasjon mellom
agentene, rollback, VS Code og Copilot cloud gjenstår også før stabil release.

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
