# Tillit, klientstøtte og releasegater

Grillmester er instruksjoner og arbeidsmetode for en agentisk klient. Det er
ikke en autorisasjonsmekanisme eller en erstatning for menneskelig review og
deterministiske gates. Denne siden forklarer hva Grillmester eier, og hva hver
klientflate faktisk er verifisert for.

## Ansvarsdeling

| Lag | Eies av | Hva det faktisk styrer |
| --- | --- | --- |
| Agentprompt og skills | Grillmester | Rolle, arbeidsflyt, evidenskrav og forventet atferd. |
| Provider og modell | Bruker, klient og organisasjon | Hvor inferensen kjører og hvilken modell som svarer. |
| Tilgjengelige tools | Klient, pluginprofil og konfigurerte MCP-er | Hvilke handlinger modellen kan foreslå å bruke. |
| Tool-, path- og URL-godkjenninger | Bruker og enterprise-policy | Om en konkret handling får kjøre. |
| Sandbox, nettverk, `gh` og Git | cplt og organisasjonspolicy | Tekniske runtimegrenser for terminalflyten. |
| CI, rulesets og CODEOWNERS | Consumer-/organisasjonseier | Deterministiske leveranse- og mergekrav. |

Et verktøy i en agentprofil gir ikke OAuth-scope, installerer ikke en MCP og
omgår ikke klientens godkjenninger. Motsatt er en promptregel som «ikke skriv»
ikke en teknisk blokkering dersom klienten faktisk tilbyr write.

## Bootstrap-tillit for systemklienter

Standardlauncheren bruker OpenCode og Copilot CLI fra brukerens `PATH`; cplt
resolveres fra samme miljø.
Grillmesters bundle-checksum binder Grillmester-bundle-en, ikke disse
klientbinærene. Installasjons- og oppdateringstillit for systemklientene eies av
brukeren, organisasjonen og valgt pakkekanal; Grillmester distribuerer, kopierer
eller skygger dem ikke.

Presence-discovery og `--print-command` kjører ingen klientbinær. Når versjon må
bevises for `choose`, `doctor` eller launch, kjøres klientens strenge
`--version` gjennom cplt mot en tom 0700-prosjektmappe med timeout, outputgrense
og prosessgruppe-cleanup.

`scripts/release_test_baseline.py` er den ene kjørbare kontrakten for eksakte
versjoner, URLs, størrelser, arkivroster og digester i reproduserbare release-
og kompatibilitetstester. Det er release-gatekode, ikke runtimepinner eller en
alternativ klientdistribusjon. Normal launch godtar OpenCode `>=1.18.20,<2`,
Copilot CLI `>=1.0.79,<2` og cplt fra testbaselinen eller en nyere, gyldig
datostemplet release.

## Toolstrategi

De fire offentlige agentene må fungere på tvers av Copilot CLI, app og cloud.
De utelater derfor `tools` og arver runtimeflaten. Navs MCP Registry,
enterprise-policy og brukerens godkjenninger avgjør hvilke tools og
sideeffekter som faktisk er tilgjengelige.

Manglende GitHub Projects- eller Figma-write skal gi et reviewbart utkast,
Visual Companion eller `NEEDS_INPUT`, aldri falsk suksess. Interne roller har
smalere oppdrag, men rolleprompten er arbeidsmåte—klienten og policyen er den
tekniske grensen.

## Klientstøtte

| Klient | Nåstatus | Hva som fortsatt må bevises før stabil |
| --- | --- | --- |
| **Copilot CLI** | Referanseklient. Native marketplace-installasjon og terminal-launch gjennom cplt bruker samme pluginpayload. | Den nye 43-skill-pakken, immutable kandidat, resolved modell, delegering og runtime-toolbruk i representativt repo. |
| **Copilot app** | Native Plugins-UI. Appen tilbyr også BYOK mot LM Studio og OpenAI-kompatible endepunkter i public preview. | Discovery, oppdatering, resolved source, delegering, write/deny og lokal BYOK må observeres i appen; terminalens cplt-grense gjelder ikke. |
| **Copilot cloud agent** | Repoaktivering er dokumentert gjennom `.github/copilot/settings.json`. | Navs enterprise-policy, plugin-discovery og samme publiserte RC i en representativ consumer. |
| **VS Code** | Sekundær, ikke-verifisert kompatibilitetsflate utenfor første release-løfte. | Faktisk installasjon og oppdatering med to Grillmester-versjoner. |
| **OpenCode 1.x fra 1.18.20** | Deterministisk target med 7 agenter, 43 skills og 43 commands. Brukerinstallert klient startes gjennom cplt. | Hver konkret modell må kvalitetsvalideres; nyere 1.x er kompatibilitetsflate, ikke de eksakte testbytene. |
| **Local-model-launcher** | `grillmester local` binder én eksplisitt loopbackmodell i OpenCode eller Copilot CLI. Interaktiv launch bruker klientgodkjenninger; `grillmester local run` er en avgrenset kjøring med auto-godkjente tools. Begge krever cplts forced proxy, `gh`- og Git-guards uten å overstyre effektiv domeneconfig. | Dette er lokal inference, ikke offline. Web avhenger av cplt-policy; eksplisitte GitHub- og package-tokens krever separate opt-in-flagg. OpenCode isolerer ambient GitHub-konto, mens Copilot-profilen kan mediere en native Keychain-credential. `run` krever et separat worktree og etterkontroll. |
| **OpenCode 2 beta** | Forventet filkompatibilitet, men ingen støttet runtimeflate. | Permissions, provider/model-adferd og full runtimeparitet må testes separat. |

Discovery-smoken kontakter ingen modell. OpenCodes runtime-smoke bruker en
deterministisk loopbackprovider og beviser config, delegering, `.env`-deny,
progressiv skill-reference og write/deny uten modellvarians.

Local-smoken starter både OpenCode og Copilot CLI gjennom release-testbaselinens
cplt og klienter for focused og full kontekst. Den krever riktig payload,
eksakt loopbackmodell, scrubbet credential-canary og urørt consumer-repo. For
Copilot tvinger provideren delegering til Grill-inspektøren og krever samme
lokale modell i hovedkall, underagent og retur. Dette beviser protokoll og
binding, ikke modellkvalitet eller fravær av ekstern egress. En syntetisk
ambient `gh`-konto gir bare et canary-token dersom session-isolasjonen
regresserer. Normal local-launch godtar kompatible klientversjoner.

## Lokal inference og GitHub

`grillmester local` binder modellproviderens base-URL til localhost og åpner den
eksakte porten i cplt. Launcheren krever forced proxy, `gh`-guard og Git-guard,
men beholder brukerens og organisasjonens effektive cplt-domeneconfig. Websearch,
dokumentasjon og GitHub kan fungere når policyen og klientens godkjenninger
tillater det. Grillmester tilbyr ingen egen `local-only`-profil; strengere
egress eies og verifiseres i cplt eller organisasjonens runtimepolicy.

Local-launcheren deaktiverer Copilots innebygde GitHub MCP. For begge klienter
får cplt-parenten en tom, session-eid `GH_CONFIG_DIR`, child får session-eid
XDG-config, eksisterende host-config deny-es, og en privat trusted-bin hindrer
caller-PATH-varianter av `gh`, `git`, `which` og `sandbox-exec` fra å bli
parent-verktøy. OpenCode gir dermed hard isolasjon fra den ambient GitHub-kontoen.
Copilots cplt-profil tillater fortsatt macOS Keychain og kan mediere en native
credential; Copilot-local lover derfor ikke hard ambient-kontoisolasjon. Bare
når brukeren både setter `GH_TOKEN` i caller-miljøet og velger
`--github-access`, validerer Grillmester tokenet og at `gh` finnes uten å starte
det, og sender tokenet til valgt child-miljø. Dette trekker ikke tilbake
Copilot-profilens Keychain-tilgang.

Grillmester skriver ikke caller-tokenet til config, sessionstate eller preview.
Klienten og godkjente tool-subprosesser kan likevel lese og eventuelt persistere
det i skrivbar sessionstate, skrive det til terminaloutput/klientlogger eller
bruke det utenom `gh`-guarden. cplt kan ikke redigere modellens output i
etterkant. Det eksplisitte tokenet og cplts `gh`-guard er derfor myke,
best-effort-grenser. Bruk riktig konto og minst mulig scope, og godkjenn
sideeffekter bevisst. Uten opt-in virker offentlig web fortsatt når den
effektive cplt-policyen tillater det.

Private package registries har en egen capability. Ambient package-tokens
videresendes aldri, og package manageren får tomme, session-eide npm user- og
globalconfigfiler i stedet for hostconfig. Med `--npm-access` velges nøyaktig
én kjent `_authToken=${NAME}`-placeholder fra consumerens prosjekt-eide
`.npmrc`; `--npm-token-env NAME` kreves for et custom navn og impliserer opt-in.
Navnet må følge en package-`*_TOKEN`-konvensjon og kan ikke kollidere med
launcher- eller klientkontroll. Det caller-eide
tokenet valideres, redigeres fra launcherens preview og persisteres ikke.
Prosjektets `.npmrc` bestemmer likevel registry-destinasjonen, og modellen eller
godkjente subprocesser kan lese eller lekke tokenet. Bruk et dedikert
package-read-token og la cplt-policyen begrense nettverkstrafikken.

`grillmester local run` er bevisst annerledes enn den interaktive reisen:
OpenCode og Copilot auto-godkjenner prosjektwrites, shelltools og URLs.
Copilot-run auto-godkjenner i tillegg klientens path-lag; cplt forblir den
håndhevende filesystemgrensen for hele klientprosessen.
Ingen av klientene får GitHub-token med mindre brukeren eksplisitt velger
`--github-access`. Copilot-run legger i tillegg inn `shell(gh:*)`-deny som
defense-in-depth; andre shellformer kan omgå den. Med opt-in kan
GitHub-skrivinger som er autorisert i prompten skje uten en ny dialog. Bruk et
dedikert, fine-grained token med minst mulig scope. Child kan lese tokenet, og
direkte API-kall kan omgå cplts `gh`-wrapper; repo-guard og credentialbro er
derfor fortsatt en myk grense, ikke hard repository-scoping. Kjør `run` i et
rent, dedikert worktree uten samtidige endringer, og verifiser sluttsvar, diff
og tester selv. cplt beskytter ikke prosjektfilene mot modellens egne writes.
Git-guard blokkerer all push som default. Brukeren kan velge cplts globale
`git_guard.protect_default_branch_only=true` for å tillate feature-branch-push
og draft-PR. Beskyttelsen av default branch, force-push og merge er fortsatt en
best-effort cplt-kommandogrense; repository rules og branch protection er
autoritative. Grillmester sender fortsatt `--git-guard` og kan ikke svekke en
strengere organisjonspolicy.

OpenCode-local velger Exa som websearch-provider. Når websearch brukes, mottar
Exa den oppgaveavledede søketeksten gjennom den effektive cplt-
nettverkspolicyen. Interaktiv launch krever klientgodkjenning; `local run`
auto-godkjenner tool-et. Dette er en tredjeparts datagrense og skal ikke omtales
som lokal-only selv om modellinferensen går til loopback.

Eksisterende host-paths som GitHub CLI kan bruke som rå credentialstore er
eksplisitte cplt `--deny-path`-er for child-klientene. Den session-eide
`GH_CONFIG_DIR` og private `gh`-stubben hindrer cplt-parentens CLI-baserte
tokenbro fra å slå opp den ambient `gh`-kontoen. Det trekker ikke tilbake
Copilot-profilens Keychain-tilgang.
Local-launcheren bruker samtidig `--no-audit`
fordi den pinnede cplt-releasens parent-side Git-audit kan kjøre repo-eide Git-
helpers utenfor sandboxen. Sandbox, forced proxy og Git-guard gjelder fortsatt;
audit skal først slås på igjen når denne upstreamgrensen er lukket og regresjons-
testet.

Modellserveren kjører utenfor cplt. Grillmester attesterer ikke serverbinær,
modellvekter, lisens, logging, aliaspolicy eller serverens egen egress. «Lokal»
betyr bare at inference-requestet går til det valgte loopbackendepunktet.

## Releasegater

Den uavhengige macOS-gaten kjører på Apple Silicon og Intel. Den bygger
bundle-en deterministisk, validerer manifestene, resolver systemklienter fra
`PATH`, kjører doctor og starter en avgrenset OpenCode-TUI gjennom cplt uten
modellkall. Bundle-en må aldri inneholde en privat klientkatalog.

Den native gaten henter de eksakte OpenCode-, Copilot CLI- og cplt-artefaktene
registrert som testinput, verifiserer arkiv- og binærdigester før første kjøring
og kjører discovery-, runtime- og local-smokene. Dette er reproduserbar
releaseevidens; det endrer ikke launcherens kompatible runtimeintervaller.

Før en RC omtales som klar for lokalmodellpilot, kjør samme immutable RC mot en
faktisk tillatt lokal modell i begge klienter. Registrer modellartifact,
kvantisering, serverversjon, maskin, context, focused/full inputtokens, tool
calls, delegering og outputkvalitet. En Qwen-pilot utvider ikke støttekravet til
andre modeller eller kvantiseringer.

## Gate fra RC til stabil Copilot-release

Bruk den versjonerte
[macOS-klientvalideringsprotokollen](macos-client-validation-protocol.md).
Minstekrav:

1. Installer eksakt immutable RC og bekreft modelloppløsning i Copilot CLI.
2. Bekreft 7 agenter og 43 skills uten kollisjoner eller døde referanser.
3. Test de fire offentlige agentene og gyldig delegering til interne roller.
4. Godkjenn én ufarlig write og avvis én; bekreft faktiske sideeffekter.
5. Gjenta i Copilot app og repoaktivert cloud agent med Navs policy.
6. Avklar live MCP Registry, eier-/supportgrense og overlapp med `nav-pilot`.
7. Test oppgradering og rollback i minst to representative consumere.
8. Bekreft native CLI auto-update mellom to RC-er; observer app og VS Code
   separat.

Manglende evidens er `UNVERIFIED`, aldri `PASS`. Stable får nytt versjonsnummer,
source commit, catalog commit, tag og GitHub Release; RC-taggen flyttes aldri.

## Incident og rollback

Hvis en kandidat oppfører seg uventet:

1. stopp videre adopsjon og avslutt berørte sesjoner
2. repinn pluginen eller installer forrige reviewede Grillmester-release
3. registrer source-/catalog-SHA, klientversjon, agent, modell, tool calls og
   sideeffekter
4. publiser en ny korrigert versjon; aldri flytt en release-tag eller erstatt en
   publisert asset

Start en ny sesjon etter rollback; en pågående sesjon beholder allerede lastet
kontekst.

## Videre

- [Installer og aktiver i riktig scope](installation.md)
- [Velg lokal modell og kjør capability-smoke](local-models.md)
- [Behold repoets stående regler lokalt](repository-context.md)
- [Kjør en kontrollert consumer-pilot](consumer-pilot-runbook.md)
