# Tillit, klientstøtte og releasegater

Grillmester er instruksjoner og arbeidsmetode for en agentisk klient. Det er
ikke en autorisasjonsmekanisme eller en erstatning for menneskelig review og
deterministiske gates. Denne siden forklarer hva Grillmester eier, og hva hver
klientflate faktisk er verifisert for.

## Ansvarsdeling

| Lag | Eies av | Hva det faktisk styrer |
| --- | --- | --- |
| Agentprompt og skills | Grillmester | Rolle, arbeidsflyt, evidenskrav og forventet atferd. |
| Tilgjengelige tools | Klient, pluginprofil og konfigurerte MCP-er | Hvilke handlinger modellen kan foreslå å bruke. |
| Tool-/path-/URL-godkjenninger | Bruker og enterprise-policy | Om en konkret handling får kjøre uten å stoppes. |
| Runtime- og organisasjonspolicy | Team Copilot og consumer-/organisasjonseier | Tekniske grenser for prosess, data, nettverk og eksterne tjenester. |
| CI, rulesets og CODEOWNERS | Consumer-/organisasjonseier | Deterministiske leveranse- og mergekrav. |

Et verktøy i en agentprofil gir ikke OAuth-scope, installerer ikke en MCP og
omgår ikke klientens godkjenninger. Motsatt er en promptregel som «ikke skriv»
ikke en teknisk blokkering dersom klienten faktisk tilbyr write.

## Bootstrap-tillit for OpenCode og cplt

Standardlauncheren bruker OpenCode og Copilot CLI fra brukerens `PATH`.
Grillmesters Homebrew-checksum binder Grillmester-bundle-en, ikke disse
klientbinærene. cplt installeres gjennom sin separate Homebrew-formel. Bootstrap-
og oppdateringstillit for systemklientene eies derfor av brukeren,
organisasjonen og den valgte pakkekanalen; standardflyten gir ingen
byteproveniens for dem.

Standardlauncherens presence-discovery og `--print-command` kjører ingen
klientbinær. Når versjon må bevises for `choose`, `doctor` eller launch, kjøres
klientens strenge `--version` gjennom cplt mot en tom 0700-prosjektmappe med
timeout, outputgrense og prosessgruppe-cleanup. Consumer-repoet gis først til
den eksplisitte, endelige launch-kjeden.

Managerens klientchecksum gjelder først når manageren får lese de ferdige
binærene. En vanlig `npm install --global opencode-ai@1.18.20` har allerede
kjørt npm-pakkens installkode: `postinstall` kjører `verifyBinary` før denne
kontrollen. Standardlauncheren verken kopierer eller kjører klienter fra en
privat Grillmester-katalog.

En høy-assurance bootstrap henter den eksakte npm-plattformpakken og den eksakte
cplt-releaseasseten, verifiserer upstream-arkivchecksum og forventet inventar,
pakker ut uten å kjøre installkode og verifiserer den reviewede binærdigesten
før første kjøring. Deretter kan manageren reautentisere og kopiere de samme
bytene til `trusted-bin`. Den kontrollen kan ikke retroaktivt sikre bootstrapen
eller kode som npm, Homebrew eller en annen package manager allerede har kjørt.

I high-assurance-flyten binder npm-integriteten, GitHub Release API-ens
asset-digest og cplts `SHA256SUMS` de reviewede bytene, men er ikke en separat
verifisert maintainer-signatur eller artifact-attestation. Den pinnede
cplt-releasen er eksplisitt registrert som mutable oppstrøms; en senere
byteendring skal derfor feile mot den committede arkiv- og binærlåsen, ikke
omtales som kryptografisk publisher-provenance.

## Toolstrategi

Grillmester, Barista, Designer og Doctor Who er offentlige, interaktive agenter
som må kunne virke på tvers av Copilot CLI, app og cloud. De utelater derfor
`tools` og arver hele runtimeflaten. Dette er samme enkle modell som de
piloterte agentene i Hovmester og Budstikka, og unngår en stor aliasmatrise som
drifter mellom klienter og Navs MCP Registry. Det gir også en bredere teknisk
flate: agentprompten er arbeidsmåte, ikke kapabilitetsisolasjon.

Navs MCP Registry og enterprise-policy bestemmer hvilke MCP-servere og tools
som faktisk kan være tilgjengelige. Manglende GitHub Projects- eller Figma-
write skal gi chatutkast, Visual Companion eller `NEEDS_INPUT`, aldri shell-/
API-fallback eller et falskt suksesskrav. OAuth-scope, godkjenninger og
serverautorisasjon avgjør hvilke eksterne sideeffekter som faktisk kan skje.
Før stabil lansering må de effektive toolsettene gjennomgås med Team Copilot
mot live Registry og testes i hver støttet klient.

Interne roller har smalere oppdrag: Kokk implementerer og verifiserer én slice
og kan lese autoritative webkilder når lokal evidens ikke er nok,
Grill-inspektør bruker blant annet read-only shellinspeksjon som `git diff`, og
Researcher gjør kildebelagt research uten writes. Rolleprompten styrer
arbeidsmåten; klient, enterprise-policy og godkjenninger styrer den tekniske
grensen.

GitHubs
[custom-agentreferanse](https://docs.github.com/en/copilot/reference/custom-agents-configuration#tools)
dokumenterer at utelatt `tools` betyr alle tilgjengelige tools, mens en navngitt
liste filtrerer både built-ins og MCP-tools. Gjennomfør klienttest med observerte
tool calls, godkjent write og avvist write før stabil release.

## Klientstøtte

| Klient | Nåstatus | Hva som fortsatt må bevises før stabil |
| --- | --- | --- |
| **Copilot CLI** | Referanseklient. Native marketplace-installasjon er bevart; den felles Homebrew-launcheren laster den samme pluginpayloaden med `--plugin-dir` og starter CLI gjennom cplt. Lokal mount, install-/oppgraderings-/rollbackflyt, personlig installasjon, deklarativ auto-install og oppdatering ved sesjonsstart er bekreftet i reelle sesjoner for den tidligere pakken med 7 agenter og 44 skills. | Den nye pakken med 42 skills, immutable kandidat, launcherbinding, resolved modell, delegering og runtime-toolbruk på representativt repo. |
| **Copilot app** | Plugins-UI-installasjon og discovery er bekreftet i en reell sesjon for den tidligere pakken med 7 agenter og 44 skills. Appen tilbyr også BYOK mot blant annet LM Studio og OpenAI-kompatible endepunkter i public preview. | Discovery av den nye pakken med 42 skills, custom-marketplace-oppdatering, eksakt resolved katalog/source, delegering, tilgjengelige MCP-tools og godkjent/avvist write. Grillmester + lokal BYOK-modell og appens nettverkstrafikk er `UNVERIFIED`; app-guiden lover ikke CLI-ens offline-modus. |
| **Copilot cloud agent** | Repoaktivering er dokumentert gjennom `.github/copilot/settings.json`. | Navs enterprise-policy, plugin-discovery og samme publiserte RC i en representativ consumer. |
| **VS Code** | Sekundær, ikke-verifisert kompatibilitetsflate utenfor første onboarding og release-løfte. VS Code dokumenterer update-sjekk hver 24. time når `extensions.autoUpdate` er aktivert. | Verifiser faktisk installasjon og custom-marketplace-oppdatering med to Grillmester-versjoner før flaten flyttes inn i normal bruk. |
| **OpenCode 1.x fra 1.18.20, standardlauncher** | Eget, deterministisk generert target med 7 native agenter, 42 skills og 42 slash commands. Launcheren resolver brukerens OpenCode fra `PATH`, starter den gjennom cplt og installerer eller skygger ingen klient. `1.18.20` og cplt `2026.08.17-062831-1008a92` er den eksakte release-testbaselinen; standardflyten godtar nyere OpenCode 1.x og nyere datostemplede cplt-releaser. Isolert discovery- og runtime-smoke bekrefter config, delegering, blokkert `.env`, progressiv skill-reference og write/deny uten ekstern modell. | Hver nyere klientkombinasjon er en kompatibilitetsflate, ikke managerens byteverifiserte runtime. Den konkrete lokale eller eksterne modellen må kvalitetsvalideres separat. |
| **Local-model-launcher (OpenCode + Copilot CLI)** | `grillmester local` krever eksakt reviewet cplt, en separat installert klient og én eksplisitt loopbackmodell. Forced proxy, privat HOME/XDG/klientstate, avvisning av ambient prosjektkomponenter og ingen cloud-fallback er gates. Den deterministiske 4×-smoken bruker ekte pinnede klienter og tvinger Copilot-delegering med eksakt lokal modell i hovedagent, Grill-inspektør og returkall. En Qwen3.8-27B Q6-pilot er gjennomført i begge klienter og kontekststørrelser uten premium requests. | Modellserverens binær, vekter, logging og egress er en egen trustgrense. Den konkrete modellen/kvantiseringen må bestå capability- og kvalitetsgate. Copilots modellgenererte `task.model` kan fortsatt overstyre modell-ID-en per delegasjon, men forced proxy holder requestet på valgt loopback-provider. |
| **OpenCode high-assurance-manager** | Den valgfrie manageren krever eksakt OpenCode `1.18.20` og cplt `2026.08.17-062831-1008a92`. Offisielle klientbytes checksum-autentiseres og kjøres fra en privat `trusted-bin`; den opprinnelige OpenCode-binæren startes ikke. På en ekte macOS-runner gates cplt-policy, rå-socket-hostpin og faktisk `local-only`-launch. Managed Linux er GNU/glibc-only i denne releasen. | Samme checksummede, immutable bundle må prøves med den konkrete modellen før akkurat den modellprofilen kan kalles kvalitetsverifisert. |
| **OpenCode 2 beta** | Oppstrøms forventer V1-kompatibilitet for støttede agent-, command- og skillfiler. Grillmester bruker ingen OpenCode-plugin. | Full runtimeparitet er `UNVERIFIED`. V2-permissions og provider/model-adferd må testes separat; betaen styrer ikke OpenCode 1-release. |

Discovery-smoken kontakter ingen modell. OpenCodes generelle runtime-smoke
kjører toolkjeden mot en deterministisk loopback-provider, slik at permission-
og delegeringskontrakten gates uten ekstern modell eller modellvarians. Den er
ikke kernel-evidens for null ekstern
trafikk alene.

Den separate local-smoken starter både OpenCode og Copilot CLI gjennom eksakt
cplt med forced proxy for focused og full kontekst. Den krever riktig payload,
eksakt modell-ID, scrubbet credential-canary og urørt consumer-repo. For
Copilot tvinger provideren et `task`-kall til `grillmester:grill-inspektor` og
krever samme lokale modell i hovedkall, underagent og retur. Smoken bruker en
deterministisk protokollstub og beviser derfor klientbinding og normal
modellpresedens, ikke kvaliteten til en konkret lokal modell.

De uavhengige CI-gatene `macos-homebrew-compatibility` og
`macos-live-compatibility` har hver sin matrise på Apple Silicon og GitHubs
hostede Intel-miljø. Homebrew-gaten bygger bundle-en deterministisk to ganger,
provisjonerer klientene som separate testinput og kjører strict audit,
installasjon, `brew test`, launcher-doctor, en avgrenset PTY-oppstart av den
installerte OpenCode-TUI-en gjennom cplt og avinstallasjon. Den bekrefter at
launcheren resolver systemklientene og at formelen ikke har private
`libexec/clients`-kopier. PTY-en avsluttes før prompt eller modellkall. I
releaseflyten må formelen dessuten være den byteidentiske, uavhengig verifiserte
releaseformelen.

Den native gaten verifiserer de eksakte pinnede Darwin-ressursene:
arkivstørrelse, upstream-digest, eksakt tar-roster, binærstørrelse og
binærdigest før første klientkjøring, inkludert Copilot CLI-artefaktet som
brukes av local-smoken. Den kjører native
discovery/runtime-smoke og cplts virkelige `check --json`-prober med managerens
`local-only`-nettverksflagg, targeted allow/block-klassifisering og rå
`/usr/bin/nc`-målinger: samme listenerport må være nåbar både via loopback og en
annen adresse som tilhører runneren, fordi Seatbelts `localhost`-selector betyr
samme host. En dokumentasjonsadresse på samme port må samtidig klassifiseres som
blokkert. Manageren binder fortsatt modell-providerens base-URL til eksakt
loopback. Til slutt installerer gaten den deterministiske bundle-en og kjører
den ekte managerflyten
`local-only ... -- models ci-local --verbose` gjennom cplt med en eksplisitt lokal
OpenAI-kompatibel provider, eksakt loopback-base-URL, modell-ID og positive
context-/outputgrenser. Managerens fail-closed preflight validerer den eksakte
provider-/modellbindingen før exec. Den avsluttende provider-filtrerte kommandoen
bruker verbose metadata og validerer modell-ID samt context-/outputgrensene på
nytt. Workflowen venter avgrenset på at den ferske lokale listeneren er klar før
installasjon og launch. Den generiske cplt-batterien forventer
at OpenCodes standarddomene er tillatt; `local-only` blokkerer det med vilje, så
gaten validerer hvert JSON-item og den ene strengere mismatchen eksplisitt i
stedet for å tolke exit code alene. Dette er konkret Seatbelt-/proxy-/host-
evidens for den pinnede macOS-runneren, ikke modellkvalitet, providerprosessens
egress eller en garanti for andre OS-/klientversjoner.

GitHub dokumenterer at Copilot app kan installere plugins via **Settings →
Plugins**, og at CLI-konfigurerte skills/MCP-er kan bli tilgjengelige i appen.
Det er ikke i seg selv evidens for samme runtimeadferd; klientene testes
separat.

Custom-marketplace auto-update i Copilot CLI er en bruker-eid opt-in. Et repo
eller en managed policy kan registrere og aktivere pluginen, men GitHub sier
eksplisitt at `autoUpdate: true` der ignoreres. Copilot app har ingen
dokumentert tilsvarende garanti. VS Code har en egen
[oppdateringsmekanisme](https://code.visualstudio.com/docs/agent-customization/agent-plugins#_update-plugins).
Disse tre mekanismene må derfor rapporteres separat, ikke som én felles
«Copilot auto-update»-status.

OpenCode-targetet og Copilot BYOK løser modellvalg på ulike måter. OpenCode-
agentene har ingen modellpin og arver session/provider. Den kanoniske Copilot-
pluginen beholder sine reviewede pinner, mens local-launcheren setter eksplisitt
lokal hovedmodell og kvalifisert `inherit` for alle
`grillmester:<agent>`-subagenter i et privat `COPILOT_HOME`. Ukvalifiserte
settingsnøkler er ikke tilstrekkelige og skal ikke dokumenteres som løsningen.

Copilots `task`-tool lar modellen sende et eksplisitt `model`-felt som har
høyere presedens enn `inherit`. En faktisk test viser at dette alternative
navnet fortsatt sendes til den forced loopback-provideren; det skaper ingen
cloudrute. Provideren må avvise ukjente modell-ID-er eller bruke en bevisst
aliaspolicy. Grillmester lover eksakt modell for normal/default delegering, ikke
mot et modellgenerert eksplisitt override. Se
[lokale modeller og capability-smoke](local-models.md).

«Lokal modell» betyr bare at inferensen går til det lokale endepunktet.
Webtools, MCP-er, telemetry og update-/modellkatalogkall vurderes separat.
Copilot CLI har en dokumentert offline-modus. Grillmesters vanlige OpenCode-
target er ikke i seg selv en local-only-profil; en slik profil må i tillegg
deny-e remote capabilities og håndheve egress. Ikke rapporter en session som
lokal-only bare fordi valgt modell kjører på `127.0.0.1`.

Grillmesters `local`-profil er lokal-kapabel, men beholder cplts innebygde
OpenCode-infrastruktur og attesterer ikke sessionens aktive modell.
`cloud-open-weight` attesterer heller ikke modellvekter eller lisens og godtar
bare offentlige hostnavn, ikke localhost, IP-litteraler eller privat-domene-
opt-in. Private og interne providernavn hører hjemme i `hybrid`. Manageren gjør
ingen DNS-preflight; den pinnede cplt-proxyen håndhever private-/loopbackgrensen
når forbindelsen opprettes for å unngå DNS-TOCTOU. Den fulle `local-only`-
grensen gjelder harnesset på macOS med den pinnede cplt-releasen. Linux har en
dokumentert restkanal fordi Landlock-reglene er portbaserte, også med kernel
`6.7` eller nyere, og profilen skal derfor feile lukket der. Providerprosessen
på localhost er en separat tillits- og egressgrense.

I managerens herdede cplt-profiler peker `OPENCODE_MODELS_PATH` på en manager-
eid, read-only tom katalog. Bare eksplisitt konfigurerte provider-/modellpar med
nøyaktig npm-pakke `@ai-sdk/openai-compatible` godtas. Det reduserer ambient
modellkatalog og eksekverbar providerkode, men er en Grillmester-tradeoff, ikke
et cplt-krav; unmanaged cplt beholder OpenCodes bredere provider- og modellflate.
Profilconfigen er dessuten bare en baseline fordi managed/MDM-config kan merge
senere. Manageren validerer derfor effektivt resolved config før launch, mens
`OPENCODE_DISABLE_SHARE=true` blokkerer sharing uavhengig av merge-rekkefølgen.

Den flytende `marketplace`-branchen er oppdateringskanalen. Når en maintainer
har eksplisitt promotert en eksakt validert source-SHA fra `main`, kan
CLI-brukere som har valgt `autoUpdate: true`, hente endringen ved neste trusted
CLI-sesjon. En vanlig merge til `main` flytter ikke `marketplace`. CI,
`COPILOT_AUTO_UPDATE=false` og `--no-auto-update` hopper over hentingen.
Auto-update-testen er derfor post-deploy-evidens; en separat godkjenningsport
krever en immutable release-tag i stedet.

## Gate for OpenCode 1.18.20-testbaselinen

Et generert target er støttet kildekode, men er ikke alene bevis på at en
konkret runtime, provider og modell oppfører seg riktig. Den publiserte,
deterministiske `tar.gz`-en med detached SHA-256 er installasjonsartefakten; en
source-checkout er ikke release-evidens. For samme immutable source-SHA:

1. Kjør `python3 scripts/generate_opencode.py --check`, validatoren og hele
   testpakken uten drift. Bygg bundle-en to ganger og krev byte-identiske
   `tar.gz`-filer, korrekt `DISTRIBUTION-MANIFEST.json` og detached SHA-256.
2. Kjør `python3 scripts/smoke_opencode.py --require-binary` med den pinnede
   OpenCode 1.18.20-binæren. Bekreft eksakt roster, commands, skills,
   fravær av modellpin, deklarerte native permissionregler og consumerens
   `AGENTS.md` i isolert config. Denne smoken er med vilje uten modell.
3. Krev eksakt `cplt 2026.08.17-062831-1008a92`, og kjør
   `python3 scripts/smoke_opencode_runtime.py --require-binary --cplt cplt`
   mot samme OpenCode-binær. Den deterministiske provideren må bevise
   delegering, `.env`-deny, skill-reference, godkjent write og avvist write
   gjennom cplt uten ekstern modell. Ingen forventet remote flyt skal observeres,
   men null ekstern egress krever en separat fail-closed nettverksmåling. Alle
   lifecycle-managerens cplt-baserte profiler deler denne versjonspinnen.
4. Kjør managerkontrakten og krev at offisielle OpenCode- og cplt-bytes
   checksum-autentiseres, kopieres byte-identisk til en forseglet privat
   `trusted-bin`, og at den opprinnelige OpenCode-binæren ikke startes. Bekreft
   også den tomme manager-eide modellkatalogen, resolved-config-valideringen og
   `OPENCODE_DISABLE_SHARE=true`. `--direct` er et eksplisitt trusted opt-out og
   teller ikke som denne evidensen.
5. Gjenta en representativ oppgave med provider-/modellprofilen som skal
   omtales som støttet. For en lokal modell må også
   [capability-smoken](local-models.md#capability-smoke-før-modellen-får-bakgrunnsarbeid)
   bestås.

OpenCode 2 og OpenCode-versjoner før `1.18.20` er utenfor standardgrensen. En
nyere 1.x-versjon er støttet av standardlauncheren, men er ikke den eksakte
release-testbaselinen: registrer den observerte versjonen og kjør relevant
kompatibilitetssmoke før du gjør sterkere runtimepåstander. Uprøvde modeller er
fortsatt `UNVERIFIED`; filkompatibilitet eller et vellykket chat-svar beviser
ikke modellkvalitetsparitet med Copilot.

## Gate fra RC til stabil Copilot-release

Bruk den versjonerte
[macOS-klientvalideringsprotokollen](macos-client-validation-protocol.md) og
evidensmalen for den repeterbare CLI- og App-delen av gaten. VS Code-observasjon
er separat og styrer ikke denne første releasen. Resten av
denne gaten dekker bredere organisasjons- og releaseavklaringer.

1. Installer den eksakte, immutable RC-ref-en og bekreft modelloppløsning i
   Copilot CLI.
2. Bekreft at den ene pluginen gir nøyaktig 7 agenter og 42 skills uten
   agent-/skillkollisjoner eller døde referanser.
3. Bekreft at de fire offentlige agentene er valgbare, mens Kokk,
   Grill-inspektør og Researcher bare delegeres med gyldige briefs.
4. La Kokk gjøre én ufarlig write i en disponibel fixture. La
   Grill-inspektør bruke execute til read-only diff-/statuskontroll.
5. Avvis én foreslått write og bekreft at ingen fil, Git-ref eller ekstern
   ressurs endres.
6. Kjør Designer og Doctor Who med representative oppgaver og logg hvilke tools
   som faktisk resolver. Manglende capability skal gi tydelig fallback eller
   `NEEDS_INPUT`, ikke et falskt suksesskrav.
7. Gjenta mot samme publiserte RC i Copilot app og repoaktivert cloud agent med
   Navs enterprise-policy.
8. Verifiser med Team Copilot at pluginen er forståelig i `nav-pilot`/MCP-
   onboarding, at live MCP Registry ikke gir skjulte eller overlappende
   capabilities, og at eier-/supportgrensene er navngitt.
9. Registrer Nav-eierens rettighets-/relisensieringsavklaring for materiale fra
   kilder uten eksplisitt lisens, og avklar eller erstatt Doctor Who-navnet før
   offentlig stabil promotering. Verifiser også at private vulnerability
   reporting faktisk kan åpnes av en vanlig reporter; repository-eier er
   ansvarlig for kanalen.
10. Test oppgradering og rollback i det piloterte referanserepoet og minst to
    representative Nav-consumere. Manglende evidens er `UNVERIFIED`, aldri
    `PASS`.
11. Publiser to påfølgende RC-versjoner og bekreft at en isolert personlig
    CLI-konfigurasjon med `autoUpdate: true` går fra den første til den andre
    ved neste trusted CLI-sesjon uten manuell update-kommando. Observer App og
    VS Code separat.

Stable skal bruke nytt versjonsnummer, source commit, catalog commit, tag og
GitHub Release. RC-taggen flyttes aldri. Den komplette prosedyren ligger i
[release-runbooken](release-runbook.md).

## Incident og rollback

Hvis en kandidat oppfører seg uventet:

1. stopp videre adopsjon
2. avslutt berørte sesjoner
3. repinn consumeren eller personlig installasjon til forrige reviewede tag
4. registrer katalog-SHA, source-SHA, klientversjon, agent, modell, tool calls
   og observerte sideeffekter
5. publiser en ny korrigert versjon; aldri flytt eller overskriv en release-tag

Repinning endrer ikke en allerede startet sesjons lastede kontekst. Start en ny
sesjon etter rollback.

## Videre

- [Installer og aktiver i riktig scope](installation.md)
- [Velg riktig agent og skillfamilie](agents-and-skills.md)
- [Behold repoets stående regler og templates lokalt](repository-context.md)
- [Kjør en kontrollert consumer-pilot](consumer-pilot-runbook.md)
