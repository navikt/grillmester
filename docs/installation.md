# Installere og aktivere Grillmester

Denne guiden skiller mellom personlig installasjon, repoaktivering og
enterprise-policy. De tre nivåene løser ulike behov.

## Før du begynner

- Installer en versjon av GitHub Copilot CLI som støtter plugins.
- Bruk `marketplace`-branchen for POC, eller velg en reviewet tag fra
  [Grillmester Releases](https://github.com/navikt/grillmester/releases) når
  en kandidat er publisert.

En release-tag har formen `v<plugin-versjon>`. Taggen peker på en reviewet,
catalog-only commit; pakkeoppføringen i katalogen peker videre på eksakt
source-SHA og riktig undermappe. Bruk taggen, ikke `main`, når
installasjonen skal være reproduserbar.

## Innhold

`grillmester@grillmester` er hele produktet: fire offentlige agenter, tre
interne roller og 44 kuraterte skills for metode, design, produktarbeid,
levering og relevante Nav-teknologier. Det finnes ingen separat tilleggspakke.

## Personlig installasjon i Copilot CLI

Installer den nåværende POC-en:

```bash
copilot plugin marketplace add navikt/grillmester#marketplace
copilot plugin install grillmester@grillmester
copilot plugin list
```

`marketplace` er en flytende POC-kanal. For reproduserbar installasjon bruker
du samme kommando med en reviewet `v<versjon>`-tagg i stedet.

Start Copilot slik du vanligvis gjør i Nav, åpne `/agent`, og velg
`grillmester:grillmester`. Installasjonen ligger i brukerens Copilot-home og er
tilgjengelig i alle repoer på maskinen. Den skriver ikke agent- eller
skillfiler inn i repoene.

En personlig installasjon aktiverer ikke automatisk pluginen for andre
utviklere eller Copilot cloud agent. Bruk repoaktivering når teamet skal dele
samme versjon.

## Copilot app

1. [Legg til Grillmester-markedsplassen](https://github.com/copilot/app/launch?open=ghapp%3A%2F%2Fplugins%2Fmarketplace%2Fadd%3Fsource%3Dnavikt%252Fgrillmester)
2. [Installer Grillmester](https://github.com/copilot/app/launch?open=ghapp%3A%2F%2Fplugins%2Finstall%3Fsource%3Dgrillmester%2540grillmester)

GitHubs
[plugin-deep-links](https://docs.github.com/en/enterprise-cloud@latest/copilot/how-tos/github-copilot-app/open-with-deep-links#open-plugin-flows)
åpner **Settings → Plugins** med en ferdig utfylt verdi. De installerer eller
registrerer ingenting før brukeren bekrefter i appen.

App-lenken for marketplace tar `OWNER/REPO` eller Git-URL, ikke CLIs
`OWNER/REPO#ref`. Den følger derfor default branch og er en enkel onboarding,
ikke bevis for en immutable release. For RC-/stable-evidens må testen registrere
hvilken katalog og source-SHA appen faktisk resolver.

App-installasjonen gjelder brukerens app-oppsett og skriver ikke pluginfiler
eller aktivering inn i repoet. Den aktiverer heller ikke cloud agent for teamet;
bruk repoaktivering for det.

## Eksterne GitHub-capabilities

Plugininstallasjon installerer ikke en write-capable GitHub MCP og gir ingen
OAuth-scopes. Copilot CLIs innebygde GitHub MCP er read-only som standard, og
Projects er ikke del av standardverktøysettet. Arbeidsflyter som skal publisere
Issues, oppdatere Projects eller lage native parent-/dependency-relasjoner må
derfor først bekrefte at den aktuelle klienten eksponerer de konkrete read- og
write-verktøyene med riktig repo-/project-scope.

Hvis kapabiliteten mangler, skal Grillmester lage eller bevare et reviewbart
utkast og returnere `NEEDS_INPUT`/`NEEDS_CONTEXT`; den skal ikke bytte til
`gh`, rå API-kall eller late som en tekstlig «blocked by»-linje er en native
relasjon. Oppsett av en write-capable MCP er enterprise-/teameid og skal
reviewes separat fra plugininstallasjonen.

## Aktivering i ett teamrepo

Commit `.github/copilot/settings.json` når Copilot CLI og cloud agent i repoet
skal bruke samme reviewede versjon:

```json
{
  "extraKnownMarketplaces": {
    "grillmester": {
      "source": {
        "source": "github",
        "repo": "navikt/grillmester",
        "ref": "REVIEWED_RELEASE_TAG"
      }
    }
  },
  "enabledPlugins": {
    "grillmester@grillmester": true
  }
}
```

GitHubs
[konfigurasjonsreferanse](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference#repository-settings-githubcopilotsettingsjson)
dokumenterer at pluginfeltene leses av Copilot CLI og cloud agent. Repoet får
ikke dermed en global installasjon på brukerens maskin.

Behandle denne filen som kode:

- review tagendringer i en PR
- bruk kun reviewede, immutable tags
- dokumenter pluginidentitet og valgt agent i piloten
- behold rollback til forrige tag som en vanlig revert eller PR

Repoer som synkes fra Hovmester må også fjerne den aktive syncen og bare de
eksakte agentkollisjonene. Bruk den baseline- og rollback-bundne
[consumer-pilot-runbooken](consumer-pilot-runbook.md); ikke slett hele
`.github/agents` eller `.github/skills`.

## Personlig deklarativ aktivering

Copilot CLI støtter de samme `extraKnownMarketplaces`- og `enabledPlugins`-
feltene i `~/.copilot/settings.json`. Dette er et alternativ til de imperative
installasjonskommandoene for brukerens CLI-sesjoner. Ikke commit personlige
settings i et consumer-repo.

## Enterprise-policy

Enterprise-adminer kan bruke managed settings for å tillate, kreve eller
blokkere marketplace og plugins. De kan også sette `strictKnownMarketplaces`;
en tom liste betyr full marketplace-lockdown. Se
[enterprise managed settings](https://docs.github.com/en/copilot/reference/enterprise-administrators/enterprise-managed-settings).

En bruker- eller repoendring kan ikke omgå en enterprise-blokkering. Managed
settings er den autoritative grensen for hva brukere og repoer kan aktivere.

## Oppdatere og rulle tilbake

### Personlig installasjon

Bind marketplacen til den nye reviewede taggen og installer pluginen på nytt:

```bash
copilot plugin uninstall grillmester@grillmester
copilot plugin marketplace remove grillmester
copilot plugin marketplace add navikt/grillmester#NEW_REVIEWED_RELEASE_TAG
copilot plugin install grillmester@grillmester
copilot plugin list
```

Rollback er samme flyt med forrige reviewede tag. Start en ny Copilot-sesjon
etterpå; en pågående sesjon glemmer ikke nødvendigvis allerede lastet innhold.

Brukte du den tidligere `0.3.0-poc.1`-inndelingen, avinstallerer du den gamle
tilleggspakken én gang:

```bash
copilot plugin uninstall grillmester-nav@grillmester
```

Senere oppdateringer og rollback berører bare `grillmester@grillmester`.

### Teamrepo

Endre `ref` i `.github/copilot/settings.json` i en vanlig PR. Rollback er en PR
eller revert tilbake til forrige tag. Da er både endringen og gjenopprettingen
synlig i Git-historikken.

## Lokal POC og utvikling

Når ingen release er publisert, eller når du utvikler pluginen, kan du mounte
en lokal checkout i en disponibel testrepo:

```bash
git clone git@github.com:navikt/grillmester.git /tmp/grillmester-poc
cd /path/to/a/disposable-test-repo
```

Start Copilot slik du vanligvis gjør i Nav, last den lokale mappen
`/tmp/grillmester-poc/plugin` med klientens dokumenterte `--plugin-dir`-flyt,
og velg Grillmester med `/agent`.

Denne flyten er eksplisitt og midlertidig for prosessen du starter. Den er ikke
en global installasjon og er ikke immutable release-evidens. Bruk
`COPILOT_PLUGIN_DIR_ONLY=true` i en isolert smoke når andre personlige plugins
ikke skal påvirke resultatet.

## OpenCode

Copilot-agentene og marketplace-installasjonen er laget for GitHub Copilot.
Enkeltstående, reviewede skills kan prøves i OpenCode user-scope. `gh skill`
er public preview og krever GitHub CLI 2.90.0 eller nyere:

```bash
gh skill install navikt/grillmester grillmester-dulting \
  --agent opencode --scope user --pin REVIEWED_SOURCE_SHA
```

Bruk source-SHA-en som releasekatalogen peker på, ikke katalogtaggen. Dette er
skills-only interop: OpenCode får ikke agentteamet, kvalifisert delegering eller
agentenes felles kontrakt. Stående regler må fortsatt ligge i consumerens
`AGENTS.md`.

## Neste steg

- [Velg riktig agent og skillfamilie](agents-and-skills.md)
- [Forstå repoets ansvar for instructions og templates](repository-context.md)
- [Forstå tools, tillit og klientstøtte](trust-and-client-support.md)
- [Kjør en kontrollert consumer-pilot](consumer-pilot-runbook.md)
