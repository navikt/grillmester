# Installere og aktivere Grillmester

Denne guiden skiller mellom personlig installasjon, repoaktivering og
enterprise-policy. De tre nivåene løser ulike behov.

## Før du begynner

- Installer en versjon av GitHub Copilot CLI som støtter plugins.
- Bruk `marketplace`-branchen for løpende oppdateringer, eller velg en reviewet tag fra
  [Grillmester Releases](https://github.com/navikt/grillmester/releases) når
  en kandidat er publisert.

En release-tag har formen `v<plugin-versjon>`. Taggen peker på en reviewet,
catalog-only commit; pakkeoppføringen i katalogen peker videre på eksakt
source-SHA og riktig undermappe. Bruk taggen, ikke `main`, når
installasjonen skal være reproduserbar.

## Innhold

`grillmester@grillmester` er hele produktet: fire offentlige agenter, tre
interne roller og 42 kuraterte skills for metode, design, produktarbeid,
levering og relevante Nav-teknologier. Det finnes ingen separat tilleggspakke.

## Anbefalt personlig oppsett med automatisk oppdatering

For en personlig CLI-installasjon er det anbefalte oppsettet en flytende
marketplace-kanal med automatisk oppdatering ved sesjonsstart. Merge dette i
din egen `~/.copilot/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "grillmester": {
      "source": {
        "source": "github",
        "repo": "navikt/grillmester",
        "ref": "marketplace"
      },
      "autoUpdate": true
    }
  },
  "enabledPlugins": {
    "grillmester@grillmester": true
  }
}
```

`enabledPlugins` installerer og aktiverer pluginen deklarativt.
`extraKnownMarketplaces.grillmester.autoUpdate` gjør at Copilot CLI sjekker den
egendefinerte marketplacen ved starten av en ny trusted CLI-sesjon. Denne
opt-in-en virker bare fra brukerens egen settingsfil; samme felt i repo- eller
managed settings ignoreres. Oppdateringen hoppes over i CI og når sesjonen startes med
`COPILOT_AUTO_UPDATE=false` eller `--no-auto-update`. Se GitHubs
[pluginreferanse](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference#copilot-plugins-update-options)
og
[settingsreferanse](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference#user-settings-copilotsettingsjson).

Fra en Grillmester-checkout kan du bruke det idempotente bootstrap-scriptet i
stedet for å merge JSON manuelt:

```bash
python3 scripts/configure_autoupdate.py
python3 scripts/configure_autoupdate.py --apply
```

Første kjøring er bare preview. `--apply` bevarer ukjente innstillinger,
oppretter en privat backup av en eksisterende fil og skriver atomisk. Scriptet
avviser JSONC, symlinker, en eksisterende pin og eksplisitt global
`autoUpdate: false` fremfor å overskrive dem stille. Se `--help` for de
eksplisitte override-flaggene. `--enable-global-auto-update` endrer en bredere
brukerpreferanse: den aktiverer automatisk oppdatering av både selve Copilot
CLI og alle plugins. Bruk den bare etter å ha lest previewen.

Start deretter Copilot slik du vanligvis gjør i Nav. Copilot CLI sjekker etter
pluginoppdateringer når en ny sesjon starter. Andre klienter har egne
oppdateringsmekanismer.

## Manuell personlig installasjon i Copilot CLI

Installer Grillmester:

```bash
copilot plugin marketplace add navikt/grillmester#marketplace
copilot plugin install grillmester@grillmester
copilot plugin list
```

`marketplace` er en flytende oppdateringskanal. For reproduserbar installasjon bruker
du samme kommando med en reviewet `v<versjon>`-tagg i stedet.

En maintainer avanserer `marketplace` ved å eksplisitt promotere en eksakt,
validert source-SHA fra `main`. En vanlig merge til `main` endrer ikke den
flytende kanalen. For brukere med `autoUpdate: true` blir versjonen tilgjengelig
etter denne promoteringen. Bruk en immutable release-tag når oppdateringen må
vente på en separat godkjenning.

Denne imperative flyten slår ikke på automatisk oppdatering for en
egendefinert marketplace. Bruk brukeroppsettet over, eller oppdater manuelt
med:

```bash
copilot plugin marketplace update grillmester
copilot plugin update grillmester@grillmester
```

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

GitHub dokumenterer foreløpig ikke om Copilot app automatisk oppdaterer en
personlig installasjon fra en egendefinert marketplace. Dette må observeres med
to faktiske Grillmester-versjoner før det loves som App-adferd.

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

## Enterprise-policy

Enterprise-adminer kan bruke managed settings for å tillate, kreve eller
blokkere marketplace og plugins. De kan også sette `strictKnownMarketplaces`;
en tom liste betyr full marketplace-lockdown. Se
[enterprise managed settings](https://docs.github.com/en/copilot/reference/enterprise-administrators/enterprise-managed-settings).

En bruker- eller repoendring kan ikke omgå en enterprise-blokkering. Managed
settings er den autoritative grensen for hva brukere og repoer kan aktivere.

Enterprise kan registrere marketplacen og deklarativt aktivere pluginen på
støttede klientflater. GitHub tillater derimot ikke managed settings å slå på
CLIs session-start auto-update for en egendefinert marketplace. For en
Nav-dekkende utrulling må Team Copilot derfor avklare om en reviewet ref rulles
sentralt, eller om den bruker-eide opt-in-en distribueres gjennom en godkjent
bootstrap.

## Oppdatere og rulle tilbake

### Personlig installasjon

Flytende `marketplace` + bruker-eid `autoUpdate: true` oppdaterer ved starten
av en ny trusted CLI-sesjon. CI, `COPILOT_AUTO_UPDATE=false` og
`--no-auto-update` hopper over hentingen. Hver katalog peker fortsatt på en
immutable source-SHA. En feil utrulling på den flytende kanalen fikses fremover
med en ny, høyere pluginversjon. Ikke flytt eller skriv om en publisert tag
eller kataloghistorie.

For en umiddelbar manuell oppdatering:

```bash
copilot plugin marketplace update grillmester
copilot plugin update grillmester@grillmester
```

For å pinne eller rulle tilbake, bind marketplacen til en reviewet tag og
installer på nytt:

```bash
copilot plugin uninstall grillmester@grillmester
copilot plugin marketplace remove grillmester
copilot plugin marketplace add navikt/grillmester#NEW_REVIEWED_RELEASE_TAG
copilot plugin install grillmester@grillmester
copilot plugin list
```

Rollback er samme flyt med forrige reviewede tag. Start en ny Copilot-sesjon
etterpå; en pågående sesjon glemmer ikke nødvendigvis allerede lastet innhold.

En pinned tag er bevisst ikke en auto-update-kanal. Hvis du senere vil tilbake
til den flytende kanalen, bruk bootstrap-scriptet med det eksplisitte
`--replace-existing-marketplace`-flagget etter preview.

### Teamrepo

Endre `ref` i `.github/copilot/settings.json` i en vanlig PR. Rollback er en PR
eller revert tilbake til forrige tag. Da er både endringen og gjenopprettingen
synlig i Git-historikken.

## Lokal utvikling

Når ingen release er publisert, eller når du utvikler pluginen, kan du mounte
en lokal checkout i en disponibel testrepo:

```bash
git clone git@github.com:navikt/grillmester.git /tmp/grillmester-dev
cd /path/to/a/disposable-test-repo
```

Start Copilot slik du vanligvis gjør i Nav, last den lokale mappen
`/tmp/grillmester-dev/plugin` med klientens dokumenterte `--plugin-dir`-flyt,
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
