# Installere og starte Grillmester

Denne guiden starter med den anbefalte terminalflyten og skiller deretter
mellom Copilot app, native plugininstallasjon, repoaktivering og
enterprise-policy.

## Før du begynner

- Den felles Homebrew-terminalflyten støttes bare på macOS i denne releasen.
  Formelen er ferdig, men installasjonskommandoen aktiveres først etter første
  stabile release og bootstrap av `navikt/homebrew-tap`.
- OpenCode og GitHub Copilot CLI er separate, valgfrie klienter. Installer minst
  én av dem; Grillmester bruker den installerte binæren fra `PATH`.
- cplt er alltid påkrevd for terminalflyten. Homebrew-formelen installerer cplt
  gjennom den separate `navikt/tap/cplt`-avhengigheten, ikke som en privat
  Grillmester-binær.
- Copilot app bruker sin egen Plugins-UI og startes ikke gjennom cplt.

Bruk `marketplace`-branchen for løpende native Copilot-oppdateringer, eller velg
en reviewet tag fra
[Grillmester Releases](https://github.com/navikt/grillmester/releases) når en
kandidat er publisert.

En release-tag har formen `v<plugin-versjon>`. Taggen peker på en reviewet,
catalog-only commit; pakkeoppføringen i katalogen peker videre på eksakt
source-SHA og riktig undermappe. Bruk taggen, ikke `main`, når
installasjonen skal være reproduserbar.

## Innhold

`grillmester@grillmester` er hele produktet: fire offentlige agenter, tre
interne roller og 42 kuraterte skills for metode, design, produktarbeid,
levering og relevante Nav-teknologier. Det finnes ingen separat tilleggspakke.

## Felles terminaloppsett på macOS

Homebrew-oppføringen er foreløpig **ikke tilgjengelig**. Ikke annonser eller
automatiser kommandoen under før release-runbookens tap-bootstrap og clean
install er fullført. Frem til da kan Copilot CLI bruke den native
plugininstallasjonen i neste seksjon. OpenCode kan valideres fra en checkout;
når en kandidat-release er publisert, kan den også releaseverifiseres gjennom
den manuelle bundle-en i [OpenCode-guiden](opencode.md#hent-og-verifiser-en-grillmester-bundle).

Etter aktivering installerer du Grillmester og cplt fra Navs Homebrew-tap:

```bash
brew install navikt/tap/cplt navikt/tap/grillmester
```

Begge formlene navngis fullt kvalifisert slik at Homebrew gir item-level trust
til akkurat Grillmester og cplt, ikke til alle nåværende og fremtidige elementer
i `navikt/tap`. Grillmester-formelen installerer den checksummede
Grillmester-distribusjonen og Python-runtimen launcheren bruker, og deklarerer
cplt som en ekstern Homebrew-avhengighet. Den
bundle-inkluderte Copilot-pluginen og det genererte OpenCode-targetet oppdateres
atomisk med `brew upgrade grillmester`. OpenCode og Copilot CLI er derimot
brukereide systemklienter: formelen installerer, erstatter eller skygger dem
aldri.

Terminalkanalen oppdaterer ikke automatisk. Hent tap-oppdateringer og installer
nytt Grillmester-innhold og launcher med:

```bash
grillmester update
```

Kommandoen kjører eksplisitt `brew update` og deretter
`brew upgrade grillmester`; `grillmester upgrade` er et alias. Ingen
pakkeoperasjon eller oppdateringsforespørsel skjer under vanlig launch. Nye
versjoner annonseres som [Grillmester
Releases](https://github.com/navikt/grillmester/releases). OpenCode og Copilot
CLI oppdateres gjennom sine egne pakkekanaler; cplt følger den separate
Homebrew-formelen. En klientoppgradering endrer ikke Grillmester-payloaden, men
nye kompatibilitetsgrenser må fortsatt gjennom de dokumenterte releasegatene.

Releasegaten krever samme formeltest på Apple Silicon og GitHubs hostede
Intel-miljø. Installering og oppgradering krever nettverk for å hente de
checksummede releaseassetene og eventuelle eksterne klientpakker. Etter
installasjon kan selve runtime-en være offline når valgt klient, modell og
cplt-policy støtter det.

Installer minst én terminalklient. Du kan ha begge samtidig og oppdatere dem
uavhengig av Grillmester:

```bash
brew install opencode
brew install --cask copilot-cli
```

`opencode` her er terminalklienten. Den forventes ikke å vises som en egen app
i macOS Launchpad eller `/Applications`.

Standardlauncheren støtter OpenCode 1.x fra `1.18.20`, Copilot CLI 1.x fra
`1.0.79` og cplt fra den testede baselinen eller en nyere, datostemplet release. Den
valgfrie high-assurance-manageren lenger ned har med vilje eksakte pinner i
stedet.

Start den interaktive velgeren:

```bash
grillmester
```

Første gang finner launcheren installerte klienter på `PATH` uten å kjøre dem og
viser bare de tilgjengelige valgene. Du velger klient og offentlig agent; bare
den valgte klienten versjonssjekkes gjennom cplt mot en tom 0700-mappe før
valget lagres i
`~/.config/grillmester/preferences.json` eller under `XDG_CONFIG_HOME`, og
neste kjøring tilbyr samme kombinasjon som default. Filen inneholder bare
skjemaversjon, `client` og `agent`. Bruk `grillmester choose` for å endre og
lagre defaulten uten å starte en klientsesjon.

For scripts eller en enkelt avvikende sesjon kan valget oppgis eksplisitt:

```bash
grillmester --client copilot --agent designer
grillmester --client opencode --agent doctor-who
```

Begge kommandoene starter den valgte terminalklienten gjennom cplt. Manglende
cplt er en hard feil; launcheren faller aldri tilbake til direkte kjøring.
Kontroller installasjonen uten å starte en agentsesjon:

```bash
grillmester doctor
grillmester doctor --client opencode
```

Uten `--client` sjekker `doctor` cplt én gang og begge klienttypene; en valgfri
klient som ikke er installert rapporteres som `skip`. Et eksplisitt klientvalg
gjør fravær eller inkompatibel versjon til en feil med en handlingsrettet
installasjonskommando. Hvis ingen støttet klient finnes, feiler den samlede
sjekken. Klientens `--version` kjøres alltid inne i cplt med avgrenset output,
timeout og en disposable prosjektmappe; `doctor` gir aldri klienten
skriverettigheter i consumer-repoet.

OpenCode 1.18.20-testbaselinen forsøker å opprette `.gitignore` i både targetet
og brukerens OpenCode-config ved første TUI-start, mens cplt med vilje holder
configen read-only. Distribusjonen inneholder derfor den eksakte støttefilen,
som er den eksakte targetfilen fra testbaselinen, og launcheren oppretter
`~/.config/opencode/.gitignore` (eller tilsvarende under
`XDG_CONFIG_HOME`) bare når filen mangler. En eksisterende regulær fil blir
aldri endret, og ingen generell write-tilgang gis til OpenCode-configen.

### Lokal modell i OpenCode eller Copilot CLI

Distribusjonen inneholder også to deterministiske focused-targets og den
lokale launcheren. Modellserveren og terminalklientene er fortsatt brukereide;
Grillmester laster ikke ned, starter, stopper eller oppgraderer dem.

Med en OpenAI-kompatibel server på loopback:

```bash
grillmester local setup
grillmester local
```

`setup` oppdager installerte klienter uten å kjøre dem og kan hente modellene
fra `/v1/models`. Defaulten lagres separat i
`~/.config/grillmester/local.json`; den vanlige `preferences.json`-flyten
berøres ikke. Focused Barista er default. Bruk `--client copilot`,
`--client opencode` eller `--full --agent grillmester` som engangsvalg.
OpenCode-local krever en nøkkelfri loopback-server fordi klientens tool-
subprosesser arver provider-miljøet. Copilot CLI kan bruke `--api-key-env` eller
`--api-key-file`; nøkkelen lagres ikke og markeres som secret for klientens
subprosesser. Nøkkelvariabelen må være dedikert og kan ikke være en bevart
terminalvariabel som `LANG` eller `TERM`. En nøkkelfil må være privat, uten
hardlinks og utenfor consumer-prosjektet; den kanoniske pathen deny-es også i
cplt.

Vanlig terminalmodus godtar testbaselinen eller en nyere kompatibel cplt.
Local-only krever derimot eksakt reviewet cplt-release, OpenCode `1.18.20` eller
Copilot CLI `1.0.80`, og feiler uten fallback. Local-gaten er eksakt fordi
argumentallowlist, discovery, modelldelegasjon og secret-isolasjon er
versjonssemantikk; vanlig terminalmodus beholder bredere kompatibilitetsranger.
En cplt-release som publiseres før tilsvarende Grillmester-gate kan derfor gjøre
local midlertidig utilgjengelig. Kjør
`brew update && brew upgrade grillmester navikt/tap/cplt` for å hente et
reviewet par; hvis et slikt par ikke er publisert ennå, skal pinnen ikke omgås.
Hver launch får en privat mappe under
`~/.local/state/grillmester/local/sessions/` (eller `XDG_STATE_HOME`) for
isolert HOME/XDG/policy. De to nyeste avsluttede sessionmappene beholdes for
diagnostikk ved sekvensiell bruk; parallelle aktive sessioner kan midlertidig
etterlate flere til neste launch. Eldre inaktive mapper ryddes automatisk,
mens levende og ukjente mapper aldri slettes. Owner-identiteten inkluderer
prosess-starttid og tåler PID-gjenbruk. Hver mappe inneholder en privat kopi av
cplt og valgt klient; med dagens klientstørrelser kan to retained mapper bruke
omtrent 300–330 MB. `doctor` og `--print-command` oppretter ingen slik mappe.
Mappene kan inneholde klientstate, men aldri nøkkelen som launcheren leste fra
valgt env-variabel eller privat fil. Copilot-local bruker også privat
`COPILOT_HOME`, slik at personlige agents, skills og approvals ikke merges inn.
Se [hele
local-modellflyten](local-models.md#anbefalt-flyt-ett-lokalt-oppsett-begge-terminalklienter).

`brew uninstall grillmester` fjerner Grillmester-formelen, men ikke den separat
installerte OpenCode- eller Copilot CLI-klienten. Homebrew avgjør på vanlig måte
om en ekstern dependency fortsatt er i bruk. Avinstallasjonen bevarer det
brukereide `preferences.json`, `local.json`, privat local-sessionstate (eller
tilsvarende XDG-stier som ennå ikke er automatisk prunet) og en eventuell
OpenCode-`.gitignore` som allerede kan være i bruk. Slett disse eksplisitt hvis
du også vil nullstille brukerstate.

Flagg før `--` videresendes til cplt, mens flagg etter `--` videresendes til
klienten. `--client`, `--agent`, `--project-dir` og klientens agent-/pluginbinding
eies av launcheren og kan ikke overstyres gjennom passthrough. `--role` er et
kompatibelt alias for `--agent`. Bruk `--print-command` for å se den eksakte
cplt-kommandoen uten å starte cplt eller klienten, versjonssjekke dem eller
endre runtime-støttefiler. Hvis en interaktiv `--print-command` trenger et
midlertidig klient-/agentvalg, brukes det bare i utskriften og lagres ikke.

## Alternativ: native Copilot CLI-installasjon med automatisk oppdatering

Hvis du ikke vil bruke Homebrew-launcheren, kan Copilot CLI installere pluginen
direkte fra en flytende marketplace-kanal og oppdatere ved sesjonsstart. Merge
dette i din egen `~/.copilot/settings.json`:

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

For å oppdatere en installert plugin må du foreløpig velge **Update** under
**Settings → Plugins** i Copilot app. Dette er en kjent klientbegrensning.
GitHub dokumenterer foreløpig ikke automatisk oppdatering av en personlig
installasjon fra en egendefinert marketplace. Dette må observeres med to
faktiske Grillmester-versjoner før det loves som App-adferd.

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

Grillmester har et deterministisk generert, native target for OpenCode 1.x fra
`1.18.20`. Det gir hele flaten med 7 agenter, 42 skills, 42 slash commands,
native delegering og native permissions. `1.18.20` er den eksakte
release-testbaselinen; standardlauncheren godtar nyere 1.x-versjoner, mens
OpenCode 2 er en separat, ikke-verifisert flate. Installer og oppdater OpenCode
selv med `brew install opencode`. Homebrew-formelen for Grillmester verken
installerer eller skygger klienten. Start den lagrede defaulten eller oppgi
OpenCode eksplisitt:

```bash
grillmester
grillmester --client opencode --agent grillmester
```

Launcheren setter targetpath og cplt-binding automatisk. For en lokal provider
på port `1234`:

```bash
grillmester --client opencode --allow-localhost 1234 \
  -- --model lmstudio/replace-with-id-from-v1-models
```

Se [OpenCode-guiden](opencode.md#kom-i-gang) for lokal provider,
cloud-provider, GitHub Copilot via OpenCodes `/connect` og manuell binding for
utvikling.

### Valgfri high-assurance manager

Resten av denne seksjonen gjelder den valgfrie manageren. Den bruker en
immutable, manifestverifisert bundle i brukerdata og skriver ikke config-,
agent- eller skillfiler i consumer-repoet. Manageren er uavhengig av
`nav-pilot-agent`, Copilot-pluginen og Copilot-agentene, men støtter bare
eksplisitte OpenAI-compatible providers – ikke OpenCodes innebygde GitHub
Copilot-provider.

For managerens strengere assurance-kontrakt installerer du eksakt klient og den
reviewede
[cplt-releasen](https://github.com/navikt/cplt/releases/tag/2026.08.17-062831-1008a92).
Ved normal npm-installasjon kjører pakkens installkode: `postinstall` kjører
`verifyBinary` før manageren kan hashe OpenCode-binæren. Den separate, globale
Homebrew-formelen for cplt er en bekvemmelighetsinstallasjon og må faktisk
resolve den eksakte managerpinnen. Grillmesters normale formel bruker den
eksterne cplt-avhengigheten og gir ikke managerens byte- eller versjonsgaranti.

Lifecycle-manageren krever Python `3.11` eller nyere i tillegg til de pinnede
klientene:

```bash
python3 -c 'import sys; assert sys.version_info >= (3, 11)'
npm install --global opencode-ai@1.18.20
test "$(opencode --version)" = "1.18.20"

brew install navikt/tap/cplt
test "$(cplt --version)" = "cplt 2026.08.17-062831-1008a92"
```

For høy assurance skal du i stedet hente den eksakte npm-plattformpakken for
OpenCode `1.18.20` og den eksakte cplt-releaseasseten. Verifiser
upstream-arkivchecksummen, forventet inventar og den reviewede binærdigesten før
første kjøring, og legg deretter binærene på `PATH`. Managerens senere kontroll
kan ikke retroaktivt sikre bootstrapen eller installkode som allerede har kjørt.

Ved en cplt-basert managerlaunch checksum-autentiseres også den resolverte
OpenCode-binæren mot de offisielle plattformbinærene i npm-distribusjonen av
`opencode-ai@1.18.20`. Manageren kopierer OpenCode og cplt byte-identisk til en
privat, forseglet `trusted-bin` og starter bare disse kopiene. Den opprinnelige
OpenCode-binæren leses, men kjøres ikke i cplt-modus.

Last ned den deterministiske OpenCode-`tar.gz`-asseten og dens detached
`.sha256` fra samme
[Grillmester-release](https://github.com/navikt/grillmester/releases). Bruk de
eksakte navnene fra releasen, ikke GitHubs automatisk genererte source-arkiv,
og verifiser før utpakking:

```bash
cd /path/to/downloads
tag=vREPLACE_WITH_VERSION
asset="grillmester-opencode-${tag}.tar.gz"
shasum -a 256 -c "${asset}.sha256"
tar -xzf "${asset}" -C /path/to/user-owned/extraction
```

Pakk ut til en vanlig, brukereid arbeidskatalog. cplt tillater med vilje ikke
prosesskjøring fra macOS-katalogene `/private/tmp` eller
`/private/var/folders`, så de er ikke egnede som launchplassering.

Kontroller deretter at `DISTRIBUTION-MANIFEST.json` oppgir forventet source-SHA,
OpenCode `1.18.20` og cplt `2026.08.17-062831-1008a92`, og installer:

```bash
cd /path/to/extracted/grillmester-opencode-v1
python3 -I -S scripts/manage_opencode.py install
```

Bruk en eksplisitt betrodd Python 3.11+ og behold `-I -S` for alle managed
manager-kall. Scriptet er stdlib-only; isolert/no-site-modus hindrer
`PYTHONPATH`, user-site og `sitecustomize` i å kjøre før managerens validering.
Python-binæren selv er fortsatt en bootstrap-tillitsrot. Native cplt krever
ikke lifecycle-manageren.

Behold den checksumverifiserte, utpakkede bundle-en på en bruker-eid plassering;
manageren kjøres derfra ved senere launch, oppdatering og rollback.

Start deretter fra consumer-repoet med en eksplisitt runtimeprofil. For LM
Studio på port `1234`:

```bash
cd /path/to/consumer-repo
python3 -I -S /path/to/grillmester-opencode-v1/scripts/manage_opencode.py launch \
  --profile local \
  --provider-id lmstudio \
  --provider-base-url lmstudio=http://127.0.0.1:1234/v1 \
  --provider-model lmstudio/replace-with-id-from-v1-models \
  --local-port 1234
```

Manageren verifiserer og kopierer aktiv release til en unik read-only config-
stage ved hver launch. Den sender `OPENCODE_CONFIG_DIR` eksplisitt gjennom cplt
og gir bare `--allow-read` til stage; targetet er aldri en skrivbar policyflate.
cplt og OpenCode velges fra den private `trusted-bin`, ikke fra installasjonens
skrivbare package-managerområde.
cplt strict tillater OpenCodes innebygde infrastruktur ved siden av den
eksplisitte localhost-porten. `local` er derfor lokal-kapabel, men stenger ikke
OpenCodes egen cloud-infrastruktur. Manageren slipper bare provider-ID-er,
base-URL-er og modell-ID-er som er valgt med `--provider-id`,
`--provider-base-url` og `--provider-model` inn i sessionen og binder dem til
profilens host/port. Den attesterer ikke modellvekter, lisens, kvalitet eller
hva endpointet faktisk serverer bak ID-en. Profilene
`cloud-open-weight` og `hybrid` krever navngitte `--provider-domain`-hostnavn;
cplt matcher hvert navn som samme hostname eller et subdomene, så bruk den
smaleste faktiske verdien. `cloud-open-weight` uttrykker tiltenkt bruk, ikke en
attestasjon av modellvekter eller lisens. Managed mode bruker HTTPS-port `443`;
en ekstra providerport ville blitt cplt `--allow-port`, som åpner direkte
egress til alle hoster på porten, og avvises derfor. Bruk native unmanaged cplt
når den tradeoff-en faktisk er ønsket. `cloud-open-weight` godtar bare offentlige
hostnavn og avviser localhost, IP-litteraler og `--private-provider-domain`.
Bruk `hybrid` for et eksplisitt privat/internt hostname; samme eksakte navn må
da også oppgis med `--provider-domain`. Manageren gjør ingen DNS-preflight.
cplt håndhever public/private- og loopbackgrensen når forbindelsen opprettes og
unngår dermed en DNS-TOCTOU mellom preflight og tilkobling. `local-only` forbyr
cloud-domener og håndhever bare navngitte host-lokale porter med full forced-
proxy-grense på macOS. Manageren binder fortsatt providerens base-URL eksakt
til loopback. Seatbelts `localhost`-selector omfatter alle adresser som tilhører
samme Mac, så en annen lokal tjeneste på den valgte porten er en dokumentert
restflate; eksterne hoster på samme port forblir blokkert. Alle fire
cplt-baserte profiler krever eksakt cplt
`2026.08.17-062831-1008a92`; pinnen gjelder ikke bare `local-only`.

`local-only` avgrenser harnesset. Den lokale providerprosessen kjører utenfor
cplt og må være betrodd og egressbegrenset separat hvis hele kjeden skal være
offline. På Linux er Landlock-nettverket portbasert selv med kernel `6.7` eller
nyere, og den pinnede cplt-releasen dokumenterer en smal restkanal på proxyens
ephemeral-port; eldre kernels har bare filesystem-enforcement. Launcheren skal
derfor feile lukket for `local-only` på Linux med denne pinnen.

Bundle-en inneholder ingen provider, modell eller credential. I managerens
cplt-profiler peker `OPENCODE_MODELS_PATH` på en read-only tom modellkatalog;
bare eksplisitt valgte provider-/modelloppføringer med nøyaktig
`npm: "@ai-sdk/openai-compatible"`, eksakt launcherbundet base-URL og positive
`limit.context`/`limit.output` godtas. Dette er en Grillmester-tradeoff som
reduserer eksekverbar providerkode, ikke et cplt-krav. Det komplette lokale
configeksempelet ligger i
[guiden for lokale modeller](local-models.md#avansert-manuell-opencode-binding),
mens et generisk cloud-`baseURL`-eksempel ligger i
[OpenCode-guiden](opencode.md#åpen-modell-i-cloud).

Credentials videresendes bare etter eksplisitt `--pass-env NAME`. Profilens
`OPENCODE_CONFIG_CONTENT` er en baseline, ikke garantert siste configlag;
managed/MDM-config kan merge senere. Manageren validerer derfor OpenCodes
effektivt resolved config før launch, og `OPENCODE_DISABLE_SHARE=true` blokkerer
sharing uavhengig av merge-rekkefølgen. OpenCode 1.18.20s core V2-loader
ignorerer project-config-flagget; manageren aksepterer derfor bare
restriction-only prosjektconfig og avviser øvrige `.opencode`-komponenter før
klientstart. Probene bruker et disposable preflight-project og en forseglet
`OPENCODE_TEST_HOME`.

Dette er ikke en same-UID-isolasjonsgrense. cplt mangler sealed repo-config og
leser `HEAD:.cplt.toml` på nytt etter managerens siste snapshotkontroll; en
samtidig prosess med samme bruker kan også opprette en prosjektplugin etter
siste scan. Full lukking krever upstream-støtte i både cplt og OpenCode.

`--direct` bruker samme verifiserte config-stage, men starter den opprinnelige
caller-resolverte OpenCode-binæren. Det omgår offisiell OpenCode-checksum,
private `trusted-bin`, cplt-sandbox og egresspolicy, er et eksplisitt trusted-
code-opt-out og virker ikke med `local-only`. Native surface- og runtime-smoke
beviser ikke at en
vilkårlig lokal eller ekstern modell har samme kvalitet som en annen klient;
hver konkret modellprofil må valideres separat.

De tre normale cplt-profilene beholder kompatibilitetssikre innstillinger som
corporate upstream-proxy, men avviser skjulte globale/repo-relaxations.
`--direct` arver eksisterende absolutte XDG-røtter etter overlap-validering.
Managed profiler fryser auth fra valgt data-rot og bruker deretter private
per-process XDG data/state/cache; bare den validerte config-roten beholdes.
Launcheren eksponerer ikke ekstra filesystem-/socket-grants. Bruk
ordinær `cplt --agent opencode` for en bevisst custom cplt-policy, men ikke
rapporter den flyten med managerens staging- eller `local-only`-garanti.
Manageren er valgfri hardening, ikke en forutsetning for cplts native OpenCode-
støtte; den komplette guiden viser en minimal unmanaged kommando med
`OPENCODE_CONFIG_DIR`, `--allow-read`, `--pass-env` og `-- --agent grillmester`.

Oppdater ved å installere en ny verifisert asset. Rollback er atomisk:

```bash
python3 -I -S /path/to/grillmester-opencode-v1/scripts/manage_opencode.py rollback
```

Se [den komplette OpenCode-guiden](opencode.md) for discovery, smoke,
alle fire profiler, deklarative miljøvariabler, oppdatering, rollback,
kollisjoner og grensen mot OpenCode 2-beta. Se [lokale modeller](local-models.md)
for LM Studio, `llama.cpp`, Qwen3.8-27B og Copilot CLI BYOK som et alternativ
uten harnessbytte.

## Neste steg

- [Velg riktig agent og skillfamilie](agents-and-skills.md)
- [Forstå repoets ansvar for instructions og templates](repository-context.md)
- [Forstå tools, tillit og klientstøtte](trust-and-client-support.md)
- [Bruk hele Grillmester-teamet i OpenCode](opencode.md)
- [Velg og test en lokal modell](local-models.md)
- [Kjør en kontrollert consumer-pilot](consumer-pilot-runbook.md)
