---
status: accepted
date: 2026-08-23
---

# Bind lokal inference, og la cplt eie runtimegrensen

## Kontekst

Grillmester skal kunne bruke samme agentteam i OpenCode og Copilot CLI med en
bruker-eid, OpenAI-kompatibel modell på loopback. En vanlig utviklingsagent må
samtidig kunne lese dokumentasjon, bruke GitHub og løse komplette oppgaver.
«Modellen er lokal» skal derfor ikke blandes sammen med «hele klienten er
offline».

Den første local-launcheren forsøkte også å eie en egen local-only-grense:
eksakte klientpinner, private kopier av klientbinærer, egen proxyallowlist,
syntetisk HOME og dobbel validering av cplt-policy. Det dupliserte ansvar som
cplt allerede eier, gjorde vanlige klientoppgraderinger til Grillmester-
vedlikehold og fjernet nyttige verktøy fra normalreisen. ADR 0007 fjerner denne
parallelle manager- og `local-only`-flaten; cplt er eneste runtimeeier.

## Beslutning

### Lokal inference, tilkoblede verktøy

`grillmester local` binder providerens base-URL til `localhost` eller en
literal loopbackadresse og velger én eksplisitt modell. Kommandoen har ingen
cloudmodell-fallback. Den starter den valgte systemklienten gjennom cplt med
forced proxy, `gh`-guard, Git-guard og den eksakte loopback-porten. Brukerens
eller organisasjonens effektive cplt-config beholdes. Den pinnede cplt-
releasens parent-side Git-audit kan kjøre repo-eide Git-helpers utenfor
sandboxen; launcheren bruker derfor `--no-audit` til upstreamgrensen er lukket
og regresjonstestet.

Dette betyr med vilje:

- modellrequests går til den valgte lokale provideren
- web, dokumentasjon og GitHub kan nås når klienten og cplt-policyen tillater det
- cplt eier filesystem-, miljø-, proxy-, `gh`- og Git-grensene
- Grillmester åpner ikke alle domener og utsteder ingen egen egressattest

Launcheren lager fortsatt en privat provider- og klientkonfigurasjon, binder
den distribuerte focused- eller full-payloaden og avviser ambient
klientkomponenter som kan skygge agentteamet. Dette beskytter hvilken metode og
modell som lastes; det er ikke en parallell sandboximplementasjon. Focused
Barista er default, mens `--full` bruker den kanoniske fullpayloaden.

### Systemklienter og kompatible versjonsranger

OpenCode, Copilot CLI og cplt installeres og oppdateres av brukeren. Local-
flyten bruker de samme kompatibilitetsgrensene som standardlauncheren:
OpenCode `>=1.18.20,<2`, Copilot CLI `>=1.0.79,<2` og cplt fra testbaselinen
eller en nyere, gyldig datostemplet release.

De eksakte versjonene i releasegaten er testinput, ikke runtimepinner.
Grillmester skal derfor ikke ha en upstream-watch eller kreve ny release for
hver OpenCode- eller Copilot CLI-versjon innenfor støttet major. En ny major
krever eksplisitt kompatibilitetsarbeid.

Vanlig TUI- og promptbruk skal virke på kompatible nye 1.x-versjoner uten en
ny Grillmester-release. Rå klientflagg er derimot en eksplisitt reviewet flate:
nye flagg kan endre provider, modell, plugin, MCP, remote-mode eller
godkjenningssemantikk på måter cplt ikke kan tolke. Ukjente passthrough-flagg
feiler derfor lukket til de eventuelt støttes som en launcher-eid,
klientnøytral funksjon. Det er ikke en pin av klientens normalreise.

### GitHub i OpenCode og Copilot CLI

cplt medierer foreløpig ikke Keychain-backed GitHub-auth generisk for begge
child-klientene med isolert klientstate. Ingen local-klient får derfor GitHub-
credential som default. Copilot CLIs innebygde GitHub MCP er deaktivert; GitHub-
operasjoner skal gå gjennom guarded `gh`. Bare når brukeren både
setter `GH_TOKEN` i caller-miljøet og velger `--github-access`, validerer
launcheren verdien uten å kjøre `gh` og sender den til valgt child-miljø.
Launcheren skriver ikke tokenet til config, sessionstate eller preview. Klienten
og godkjente tool-subprosesser kan likevel persistere det i skrivbar
sessionstate. Uten opt-in starter OpenCode fortsatt med offentlig webtilgang,
og `doctor` forklarer at autentiserte GitHub-operasjoner mangler.

Alle eksisterende host-paths som GitHub CLI kan bruke som rå credentialstore
deny-es for begge child-klientene. Valgt klient ser bare opt-in-tokenet.

Dette er en myk secret-grense: modellen og vilkårlige tool-subprosesser i
klienten kan lese `GH_TOKEN` og kan i prinsippet bruke det utenom `gh`-guarden.
Brukeren skal derfor bare starte en local-session i repo og med GitHub-konto som
er innenfor ønsket scope, og godkjenne sideeffekter som vanlig. Langsiktig mål
er generisk cplt-mediering som lar child-klientene bruke GitHub uten at tokenet blir
synlig i child-miljøet.

### Ingen egen offlineprofil

Denne beslutningen etablerer ingen offlinegaranti. Grillmester tilbyr ikke en
egen `local-only`-profil eller lifecycle-manager. Et strengere egresskrav må
eies av cplt eller organisasjonens runtimepolicy, ikke av en parallell launcher.

## Konsekvenser

- En lokal modell kan løse normale utviklingsoppgaver med dokumentasjon og
  GitHub uten egne domeneallowlister eller release per klientoppdatering.
- cplt er én runtimeeier for både vanlig og lokal terminalbruk; Grillmester
  eier payload-, provider- og modellbindingen.
- Local-flyten er ikke offline. Et krav om fravær av ekstern egress må løses i
  cplt eller organisasjonens runtimepolicy.
- Den eksplisitte opt-in-tokenbroen er brukbar nå, men svakere enn ekte
  credentialmediering og må omtales ærlig i trustdokumentasjonen.
- Modellserverens binær, vekter, logging og egen egress forblir en separat
  tillitsgrense.
- Nye klientversjoner krever ikke løpende arbeid; bare nye majorversjoner eller
  nye rå passthrough-flagg utvider den reviewede kompatibilitetsflaten.

## Forkastede alternativer

- **Behold eksakte pinner i normal local-flyt:** ville gjort hver vanlig
  klientoppgradering til et Grillmester-releasearbeid uten å styrke cplt.
- **Gjør normal local-flyt offline:** ville fjernet dokumentasjon og GitHub fra
  den vanligste utviklingsreisen og flyttet runtimeansvar tilbake til
  Grillmester.
- **Start klienten uten cplt:** ville fjernet Navs felles runtime-, `gh`- og
  Git-grenser.
- **Gi OpenCode permanent tokenconfig:** ville skrevet en sensitiv credential
  til disk og gitt dårligere oppryddings- og previewegenskaper.
- **Aktiver Copilots innebygde GitHub MCP:** ville gitt en separat
  capabilityflate uten cplts dokumenterte `gh`-guard.
