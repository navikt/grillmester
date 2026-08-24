---
status: accepted
date: 2026-08-23
---

# Bruk en eksplisitt local-launcher med systemklienter og fail-closed grense

## Kontekst

Grillmester skal kunne bruke samme reviewede arbeidsmetode i OpenCode og
Copilot CLI med en lokal OpenAI-kompatibel modell. Brukeren skal samtidig eie
modellserveren og klientinstallasjonen. Grillmester skal ikke distribuere en
skjult OpenCode- eller Copilot-binær, velge lokal modus heuristisk eller falle
tilbake til en cloudmodell dersom lokal konfigurasjon ikke virker.

En vanlig klientstart er for åpen som local-only-kontrakt. Begge klientene kan
oppdage bruker- og prosjektkomponenter, lagret state, MCP-er, hooks, plugins og
innstillinger utenfor den distribuerte payloaden. Copilot-agentenes kanoniske
`model:`-pinner og klientens subagentpresedens kan dessuten velge en annen
modell enn hovedsessionen. Et localhost-endepunkt alene sier heller ingenting
om klientens øvrige egress.

Lifecycle-managerens `local-only`-profil har en sterk, men tyngre installasjons-
og stagingkontrakt. Den er ikke nødvendig for den vanlige terminalreisen. Det
trengs derfor en liten, eksplisitt launcher som gjenbruker cplt som teknisk
grense, men fortsatt bruker klientbinærene brukeren har installert.

## Beslutning

### Egen kommando og egen konfigurasjon

`grillmester local` er en separat kommando med denne brukerflaten:

- `grillmester local setup` oppdager klienter fra `PATH` uten å kjøre dem,
  validerer et eksakt loopback-endepunkt, leser `/v1/models` og lagrer valget
- `grillmester local` starter lagret klient med focused Barista
- `--client`, `--agent` og `--full` er engangsvalg og endrer ikke defaulten
- `status` leser lokal konfigurasjon, mens `doctor` og launch beviser klient,
  cplt, payload, endpoint og eksakt annonsert modell
- `--print-command` er en ren, redigert preview som ikke leser credentials,
  materialiserer sessionstate eller kjører klientbinærer

Valget lagres i `local.json`, separat fra terminalens `preferences.json`.
Skjemaet inneholder klient, offentlig agent, focused/full, provider-ID,
loopback-base-URL, modell-ID og eventuelt navnet på en env-variabel eller en
absolutt privat nøkkelfil. Nøkkelfilen må være eiet av brukeren, utilgjengelig
for gruppe/andre, uten hardlinks og utenfor consumer-prosjektet. Den
kanonikaliserte originalpathen deny-es dessuten eksplisitt i cplt. Selve
nøkkelen lagres aldri. Ugyldig, ukjent eller symlinket konfigurasjon feiler med
en eksplisitt vei tilbake til `setup`.

Auth-selector støttes bare for Copilot CLI, som får nøkkelen markert med
`--secret-env-vars`. OpenCode 1.18.20 lar Bash/tool-subprosesser arve hele
provider-miljøet; local-launcheren avviser derfor `apiKeyEnv`/`apiKeyFile` for
OpenCode og krever en nøkkelfri loopback-server. En fremtidig autentisert
OpenCode-flyt krever en separat, reviewet secret-grense, ikke bare skjult config.
For Copilot avvises `apiKeyEnv` også når navnet kolliderer med en bevart
terminalvariabel, slik at nøkkelen bare finnes under den markerte child-variabelen.

Ingen provider-ID, modellnavn, eksisterende config eller installert klient
aktiverer local-modus automatisk. Kommandoen har ingen direkte klientstart og
ingen cloud-fallback.

### Systemklienter, eksakt cplt og privat runtime

OpenCode og Copilot CLI må være separat installert. Parent-launcheren resolver
de absolutte binærpathene og utfører en egen checksum-bundet, sandboxet
versjonssjekk for local-modus før identitetene sendes til local-modulen.
Local-modus på macOS krever den eksakte reviewede cplt-releasen; nyere, uprøvde
releaser er ikke en implisitt kompatibilitetsflate.
Det samme gjelder klienten: første roster er OpenCode `1.18.20` og Copilot CLI
`1.0.80`. Standardlauncheren kan støtte kompatible ranges, men local-flytens
argumentallowlist, discovery-avslag, modellbinding og secret-grense må bevises
på nytt før en klientversjon legges til den eksplisitte rosteren.

Local-modus kjører ikke ambient cplt for å oppdage versjonen. Den resolver
pathen uten kjøring, matcher en privat kopi mot plattformens executable-SHA i
`policy/client-artifacts.json`, og kjører først deretter `--version` i et
credential-fritt miljø. Klienten kopieres og probes på samme måte; SHA-en fra
proben må matche en ny privat kopi rett før sluttstart. Final PATH inneholder
bare disse staged kopiene og systemverktøy, slik at Homebrew-/PATH-aliaser ikke
kan byttes mellom probe og launch.

Hver launch får en unik, privat sessionrot med HOME, XDG-kataloger,
klientkonfigurasjon og cplt-policy. To nyeste avsluttede sessioner beholdes for
diagnostikk ved sekvensiell bruk; parallelle aktive sessioner kan midlertidig
etterlate flere til neste launch. Eldre inaktive sessioner ryddes, mens
levende, ukjente, symlinkede eller feil-eide paths aldri slettes. Owner binder
både PID og prosessens startidentitet slik at PID-gjenbruk ikke holder død state
kunstig levende. `doctor` og preview lager ingen sessionrot. Copilot får i
tillegg et privat
`COPILOT_HOME`; et caller-supplied `--config-dir` eller andre reserverte flagg
kan ikke erstatte den grensen.

Launcheren starter alltid `cplt exec` med forced proxy, en policy som bare
åpner den valgte loopback-porten, et sanitert miljø og den eksakte
klientbindingen. Providerens base-URL må bruke `localhost` eller en literal
loopback-adresse.
Repoets `.cplt.toml` valideres mot den pinnede deny/propose-schemaen før start;
ukjente eller utrygge deny-felt avvises slik at cplt aldri kan droppe en ment
deny-policy og fortsette åpent. Alle ikke-tomme proposals avvises.
Modellserveren kjører utenfor cplt og er en separat tillitsgrense; launcheren
kan ikke attestere dens binær, modellvekter, logging eller egen egress.

### Ingen ambient klientkomponenter

Den reviewede payloaden skal ikke kunne skygges av auto-discovery i local-
modus. Launcheren avviser kjente prosjektkomponenter fra fysisk Git-rot til
valgt arbeidskatalog:

- OpenCode-prosjektconfig, `.opencode/` og eksterne skillrøtter
- Copilot-agenter, skills, MCP, LSP, hooks, extensions og settings
- både arbeidskopiens og commitens ikke-tomme `.cplt.toml`-forslag

Eksisterende personlige Copilot-/agent-/skill-/konto-/keychainpaths deny-es,
mens den private runtimekonfigurasjonen slår av update, remote/export,
experimental, memory, hooks, innebygde MCP-er og irrelevante innebygde
cloud-/media-skills. OpenCode får tilsvarende eksplisitte disable-flagg for
project config, eksterne skills/plugins, sharing, model-fetch og eksperimenter.
Consumerens vanlige `AGENTS.md` beholdes som stående prosjektkontekst; ønsker
brukeren en helt kontekstfri kjøring, er det et separat valg.

Klientargumenter som kan endre modell, agent, payload, configrot, egress,
permissions eller deaktiverte runtimeflater eies av launcheren og avvises i
både splittet, `=`-bundet og kjente short-cluster-former. Ukjente short-
clusters feiler lukket.

### Focused default og Copilot-delegering

Focused-projeksjonen fra ADR 0005 er default. `--full` bruker fortsatt den
kanoniske 7-agent/42-skill-payloaden, ikke en ny kopiert fullvariant.

OpenCode-agentene arver valgt sessionmodell. For Copilot setter launcheren
eksplisitt lokal hovedmodell og kvalifiserte
`subagents.agents.grillmester:<id>.model: inherit`-regler for alle syv agenter.
Release-smoken tvinger en normal `task`-delegering og krever eksakt lokal
modell i hovedkall, underagentkall og returkall for både focused og full.

Copilots `task`-schema tillater likevel at modellen selv fyller et eksplisitt
`model`-felt per delegasjon. Dette feltet har høyere presedens enn `inherit`, og
klienten tilbyr foreløpig ingen kjent policy som fjerner feltet. Forced proxy
gjør at et slikt modellnavn fortsatt bare sendes til valgt loopback-provider;
det kan ikke åpne en GitHub-/cloudrute. Provideren bør avvise ukjente
modellnavn eller ha en bevisst aliaspolicy. Dette dokumenteres som en
tilgjengelighets- og kvalitetsrest, ikke skjules som en absolutt modellgaranti.

### Releasebevis

Bundle-manifestet binder local-launcheren, focused policy og begge focused-
targets til source-SHA. Publisering må avvise re-manifestert drift ved å kjøre
generatorens uavhengige `--check` før bygg.

En deterministisk loopback-provider gates gjennom ekte, pinnet cplt, OpenCode
og Copilot CLI for alle fire kombinasjoner: OpenCode/Copilot × focused/full.
Gaten krever riktig payload og modell, scrubbet credential-canary, tomt
consumer-repo og den tvungne Copilot-delegeringen over. Den kontakter ingen
cloudmodell. En separat reell lokal modellpilot vurderer tokenbruk, tool calls,
delegeringskvalitet og oppgavekvalitet; protocol-smoken kan ikke bevise dette.

## Konsekvenser

- Samme korte kommando og konfigurasjon virker med begge terminalklienter,
  mens brukeren fortsatt eier klient- og modellserverlivssyklusen.
- Normal `grillmester`, marketplace-pluginen og Copilot app beholder full
  kontekst og sine vanlige modell-/runtime-regler.
- Local-modus er mer restriktiv enn direkte BYOK-bruk. Repoer som med vilje har
  prosjektagenter, skills, MCP-er eller hooks må bruke normal flyt eller en
  disponibel ren worktree; de ignoreres aldri stille.
- Local-modus er macOS-only så lenge den dokumenterte fail-closed cplt-grensen
  ikke har ekvivalent Linux-evidens.
- Klientoppgraderinger forblir brukerens valg, men hver støttet kombinasjon må
  regresjonstestes. Eksakt releasebaseline er ikke det samme som automatisk
  eierskap til klientbinærene.

## Forkastede alternativer

- **Bundle OpenCode og Copilot CLI:** ville flyttet klientoppdatering,
  sikkerhetskadens og binærproveniens inn i Grillmester og gjort installasjonen
  unødig tung.
- **Start klienten direkte uten cplt:** ville gjort local-only til en
  prompt-/konfigurasjonspåstand uten teknisk egress- og filesystemgrense.
- **Auto-detekter lokal provider:** provider- og modellnavn er ikke en
  tillitsgrense og kan representere lokal, cloud eller hybrid kjøring.
- **Arv brukerens vanlige HOME/config:** ville tillatt ureviewede plugins,
  agents, skills, MCP-er, hooks, approvals og credentials inn i sessionen.
- **Skriv providerconfig i consumer-repoet:** ville innført en ny install-/sync-
  livssyklus og blandet brukerstate med repoets stående sannhet.
- **Generer en ny full Copilot-local-plugin:** kvalifisert `inherit` i privat
  config løser normal delegering uten enda en 7/42-kopi. Resten for eksplisitt
  per-task-modell forsvinner heller ikke av å fjerne frontmatterpinnen.
- **Skru av Copilots `task`-tool:** ville fjerne den sentrale agentteam-
  arbeidsflyten for å løse en modellnavnrest som allerede er egress-isolert.
