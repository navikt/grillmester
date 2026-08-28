# Installere og starte Grillmester

Denne guiden skiller mellom den anbefalte native plugininstallasjonen,
Copilot app, OpenCode-piloten fra checkout, den foreløpig pausede
Homebrew-kanalen, repoaktivering og enterprise-policy.

## Før du begynner

- Installer Grillmester som native plugin i Copilot CLI eller Copilot app for
  den tilgjengelige brukerreisen nå.
- Homebrew-formelen for Grillmester er ferdig, men kanalen er ikke aktivert.
  OpenCode og lokale modeller kan foreløpig piloteres fra checkout; videre
  terminaldistribusjon samordnes med nav-pilot. Ikke annonser
  Homebrew-installasjonskommandoen ennå.
- For checkout-launcheren er OpenCode og GitHub Copilot CLI separate, valgfrie
  klienter. Installer minst én av dem; launcheren bruker den installerte
  binæren fra `PATH`.
- cplt er alltid påkrevd når du bruker Grillmesters terminal-launcher.
  Homebrew-formelen vil installere cplt gjennom den separate
  `navikt/tap/cplt`-avhengigheten, ikke som en privat Grillmester-binær. Native
  pluginbruk i Copilot CLI følger klientens egen runtime og krever ikke
  Grillmester-launcheren.
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
interne roller og 43 kuraterte skills for metode, design, produktarbeid,
levering og relevante Nav-teknologier. Det finnes ingen separat tilleggspakke.

## Installer i Copilot CLI

Installer Grillmester:

```bash
copilot plugin marketplace add navikt/grillmester#marketplace
copilot plugin install grillmester@grillmester
```

Start Copilot slik du vanligvis gjør i Nav, åpne `/agent`, og velg
`grillmester:grillmester`. Installasjonen ligger i brukerens Copilot-home og er
tilgjengelig i alle repoer på maskinen. Den skriver ikke agent- eller
skillfiler inn i repoene.

`marketplace` er en flytende oppdateringskanal. En maintainer avanserer den ved
å eksplisitt promotere en eksakt, validert source-SHA fra `main`; en vanlig
merge til `main` endrer ikke kanalen. Bruk en reviewet `v<versjon>`-tagg i
stedet når installasjonen skal være reproduserbar.

Denne imperative flyten slår ikke på automatisk oppdatering. Se den valgfrie
auto-update-flyten lenger ned, eller oppdater manuelt med:

```bash
copilot plugin marketplace update grillmester
copilot plugin update grillmester@grillmester
```

Kontroller installasjonen ved behov med `copilot plugin list`.

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

## Terminal-launcher og Homebrew på macOS — satt på vent

Homebrew-oppføringen er **ikke tilgjengelig**. Ikke annonser eller automatiser
kommandoen under. Copilot CLI kan bruke den native plugininstallasjonen over.
OpenCode kan valideres fra en checkout
eller releaseverifiseres gjennom den manuelle bundle-en i
[OpenCode-guiden](opencode.md#hent-og-verifiser-en-grillmester-bundle).

En checkout installerer ikke shellkommandoen `grillmester`. Med cplt og minst
én klient på `PATH` bruker du standardlauncheren fra repoet du vil arbeide i:

```bash
cd /path/to/consumer-repo
python3 /absolute/path/to/grillmester/scripts/grillmester.py
python3 /absolute/path/to/grillmester/scripts/grillmester.py doctor
```

Bytt ut `/absolute/path/to/grillmester` med checkoutens absolutte path. Disse
kommandoene bruker payloaden i checkouten og er utviklings-/pilotevidens, ikke
en installert eller immutable release.

Hvis kanalen aktiveres senere, er den planlagte installasjonen:

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
`1.0.79` og cplt fra den testede baselinen eller en nyere, datostemplet release.
Eksakte klientversjoner brukes bare som reproduserbart release-testinput.

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

Med en OpenAI-kompatibel server på loopback bruker dagens checkout-pilot den
absolutte launcherpathen:

```bash
cd /path/to/consumer-repo
python3 /absolute/path/to/grillmester/scripts/grillmester.py local setup
python3 /absolute/path/to/grillmester/scripts/grillmester.py local doctor
python3 /absolute/path/to/grillmester/scripts/grillmester.py local launch
python3 /absolute/path/to/grillmester/scripts/grillmester.py \
  local run "Fiks den avgrensede oppgaven og kjør testene"
```

I resten av guiden brukes `grillmester` som kortform. I checkout-piloten
erstattes den med
`python3 /absolute/path/to/grillmester/scripts/grillmester.py`.

`setup` oppdager installerte klienter uten å kjøre dem og kan hente modellene
fra `/v1/models`. Defaulten lagres separat i
`~/.config/grillmester/local.json`; den vanlige `preferences.json`-flyten
berøres ikke. Den lagrede kontekstkontrakten er som default et trygt
klientbudsjett på 57 344 tokens og 8 192 tokens maksimal output, for en
modellserver med 65 536 context. Bruk `grillmester local setup --context-window
57344 --max-output-tokens 8192` for å angi den eksplisitt. OpenCode bruker
kontrakten til native auto-compaction, og Grillmester injiserer ikke egne
context-hints.
Kjør `setup` på nytt hvis serverinnstillingen endres. Focused Barista er
default. Bruk `--client copilot`,
`--client opencode` eller `--full --agent grillmester` som engangsvalg.
OpenCode-local krever en nøkkelfri loopback-server fordi klientens tool-
subprosesser arver provider-miljøet. Copilot CLI kan bruke `--api-key-env` eller
`--api-key-file`; nøkkelen lagres ikke og markeres som secret for klientens
subprosesser. Nøkkelvariabelen må være dedikert og kan ikke være en bevart
terminalvariabel som `LANG` eller `TERM`. En nøkkelfil må være privat, uten
hardlinks og utenfor consumer-prosjektet; den kanoniske pathen deny-es også i
cplt.

Local-flyten bruker de samme kompatible systemklientene som standardlauncheren:
OpenCode `>=1.18.20,<2`, Copilot CLI `>=1.0.79,<2` og cplt fra testbaselinen
eller en nyere, gyldig datostemplet release. De eksakte CI-versjonene er
testinput, ikke runtimepinner; en vanlig 1.x-oppgradering krever derfor ikke en
ny Grillmester-release.

`local run` er den klientnøytrale formen for én non-interaktiv oppgave. Den
auto-godkjenner tools, prosjektwrites og nettverk innenfor cplt-policyen. Kjør
den i foreground i en egen terminal og i et rent, dedikert worktree; kontroller
sluttsvar, diff og tester etterpå. Se [local-modellguiden](local-models.md#avgrenset-kjøring)
for GitHub-opt-in, credentialgrensen og full sikkerhetskontrakt.

Repoer med private npm-pakker bruker en separat, eksplisitt capability:

```bash
NPM_AUTH_TOKEN="$NAV_PACKAGE_READ_TOKEN" \
  grillmester local run --npm-access \
  "Fiks oppgaven og kjør repoets deklarerte verifikasjon"
```

Launcheren bruker consumerens prosjekt-eide `.npmrc`, men erstatter hostens
npm user- og globalconfig med tomme, session-eide filer. `--npm-access` finner
nøyaktig én `_authToken`-placeholder med navnet `NPM_AUTH_TOKEN`,
`NODE_AUTH_TOKEN` eller `NPM_TOKEN`. Egendefinerte navn velges eksplisitt med
`--npm-token-env NAME`, må beskrive en package-token og ende på `_TOKEN`, og
aktiverer samtidig tilgangen. Tokenet lagres ikke;
prosjektets `.npmrc` kontrollerer registry-destinasjonen. Se
[local-modellguiden](local-models.md) for trustgrensen.

Bare modellrequests bindes til loopback. Launcheren åpner den eksakte
localhost-porten og krever cplts forced proxy, `gh`-guard og Git-guard; den
overstyrer ikke brukerens eller organisasjonens cplt-domeneconfig. Web,
dokumentasjon og GitHub virker når den effektive policyen og klientens
godkjenninger tillater det. Grillmester gir ikke en egen offline- eller
egressgaranti. Copilot-local deaktiverer den innebygde GitHub MCP-en; GitHub-
kommandoer forblir under cplts `gh`- og repo-guard.

Local-flyten skjermer ambient GitHub-tokenvariabler, rå `gh`-config og
caller-kontrollerte PATH-verktøy for begge klienter. OpenCode får hard isolasjon
fra den ambient GitHub-kontoen. Copilots cplt-profil tillater fortsatt macOS
Keychain, så Copilot-local gir ikke samme garanti; bruk OpenCode når dette er et
krav. Den støttede, eksplisitte GitHub-reisen bruker caller-eid `GH_TOKEN` og
`--github-access` med begge klienter, men flagget trekker ikke tilbake Copilots
Keychain-tilgang.
GitHub CLI må finnes på `PATH` (`brew install gh`). Launcheren verifiserer
binæren og validerer tokenet uten å starte `gh`, og skriver ikke tokenet til
local-config, sessionstate eller preview. Klienten og godkjente
tool-subprosesser kan likevel lese og eventuelt persistere det i skrivbar
sessionstate eller skrive det til terminaloutput og klientlogger. Dette kan
ikke cplt redigere bort i etterkant.

cplts `gh`-guard og Copilots ekstra `shell(gh:*)`-deny er myke,
best-effort-kommandogrenser; det eksplisitte tokenet kan brukes i direkte
API-kall. Bruk riktig GitHub-konto og minst mulig scope. I interaktiv launch
godkjenner brukeren sideeffektene i klienten; `local run` utfører den
opprinnelige, avgrensede prompten uten en ny tool-dialog. Offentlig web kan
fortsatt virke uten opt-in når cplt-policyen tillater det.

Git-guard blokkerer push som default. Dersom en dedikert agent-worktree skal
kunne levere en feature branch og opprette draft-PR, kan brukeren velge
`git_guard.protect_default_branch_only=true` i cplt. Denne globale
cplt-innstillingen er ment å beholde blokkering av default branch, force-push og
merge, men erstatter ikke repository rules eller branch protection. Se
[local-modellguiden](local-models.md#avgrenset-kjøring) for kommando,
best-effort-grense og konsekvenser. Grillmester slår aldri av Git-guard.

Hver launch lar cplt-parenten beholde hostens `HOME`, men gir child-klienten
isolert XDG-, provider- og
klientstate under `~/.local/state/grillmester/local/sessions/` (eller
`XDG_STATE_HOME`). På macOS kan `XDG_STATE_HOME` ikke ligge under systemets
midlertidige `/private/tmp`- eller `/private/var/folders`-røtter fordi cplt
nekter å kjøre trusted-bin derfra. De to nyeste avsluttede sessionmappene beholdes for
diagnostikk; `doctor` og `--print-command` oppretter ingen slik mappe. Ambient
klientkomponenter som kan skygge den distribuerte payloaden avvises. Dette er
payloadisolasjon; cplt eier runtime-sandboxen.
OpenCodes inerte `.opencode`-metadata og andre ikke-lastbare filer kan
sameksistere med local-flyten; prosjektconfig og lastbare komponentrøtter kan
ikke det. Stående prosjektinstrukser hører hjemme i repoets `AGENTS.md`.
For Copilot-local betyr fail-closed-gaten at enhver ikke-tom repo-lokal agent-
eller skillrot avvises, også nav-pilot-innhold uten navnekollisjon. Bruk
OpenCode-local eller en eksplisitt pilotbranch/fixture uten røttene; vanlig
pluginbruk kan fortsatt sameksistere med dem.
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

## Valgfritt: automatisk oppdatering i Copilot CLI

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

## Eksterne GitHub-capabilities

Plugininstallasjon installerer ikke en write-capable GitHub MCP og gir ingen
OAuth-scopes. Copilot CLIs innebygde GitHub MCP er read-only som standard, og
Projects er ikke del av standardverktøysettet.

En implementasjonsagent i en terminalsesjon som brukeren eksplisitt har startet
gjennom Grillmester og cplt, kan bruke cplt-guardede `gh issue`-kommandoer etter
bekreftelse av repo og konto. Interaktiv launch bruker klientgodkjenning. I
`local run` kan den opprinnelige prompten være den menneskelige autorisasjonen
for én eksakt, avgrenset endring, uten en ny tool-dialog. Det krever ikke en
egen write-MCP. Begge local-klientene krever eksplisitt `--github-access` med
caller-supplied `GH_TOKEN`; cplts repo-scope og `gh`-guard reduserer risiko, men
er myke grenser og kan omgås med direkte tokenbruk. Denne veien gjelder ikke
automatisk Copilot app, cloud agent eller en annen runtime uten cplt.

Hvis den aktuelle runtime-en mangler både en godkjent semantisk integrasjon og
den eksplisitte cplt-guardede `gh issue`-veien, skal Grillmester bevare et
reviewbart utkast og returnere `NEEDS_INPUT`/`NEEDS_CONTEXT`; den skal ikke
bytte til shell eller rå API-kall. Projects og native parent-/dependency-
relasjoner krever fortsatt en konkret capability med riktig project-scope.
Oppsett av en write-capable MCP er enterprise-/teameid og reviewes separat fra
plugininstallasjonen.

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
`1.18.20`. Det gir hele flaten med 7 agenter, 43 skills, 43 slash commands,
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

## Neste steg

- [Velg riktig agent og skillfamilie](agents-and-skills.md)
- [Forstå repoets ansvar for instructions og templates](repository-context.md)
- [Forstå tools, tillit og klientstøtte](trust-and-client-support.md)
- [Bruk hele Grillmester-teamet i OpenCode](opencode.md)
- [Velg og test en lokal modell](local-models.md)
- [Kjør en kontrollert consumer-pilot](consumer-pilot-runbook.md)
