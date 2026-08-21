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

## Toolstrategi

Grillmester, Barista, Designer og Doctor Who er offentlige, interaktive roller
som må kunne virke på tvers av Copilot CLI, app og cloud. De utelater derfor
`tools` og arver hele runtimeflaten. Dette er samme enkle modell som de
piloterte agentene i Hovmester og Budstikka, og unngår en stor aliasmatrise som
drifter mellom klienter og Navs MCP Registry. Det gir også en bredere teknisk
flate: rolleprompten er arbeidsmåte, ikke kapabilitetsisolasjon.

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
| **Copilot CLI** | Referanseklient. Lokal mount, install-/oppgraderings-/rollbackflyt, personlig installasjon, deklarativ auto-install og oppdatering ved sesjonsstart er bekreftet i reelle sesjoner for den tidligere pakken med 7 agenter og 44 skills. | Den nye pakken med 42 skills, immutable kandidat, resolved modell, delegering og runtime-toolbruk på representativt repo. |
| **Copilot app** | Plugins-UI-installasjon og discovery er bekreftet i en reell sesjon for den tidligere pakken med 7 agenter og 44 skills. Appen tilbyr også BYOK mot blant annet LM Studio og OpenAI-kompatible endepunkter i public preview. | Discovery av den nye pakken med 42 skills, custom-marketplace-oppdatering, eksakt resolved katalog/source, delegering, tilgjengelige MCP-tools og godkjent/avvist write. Grillmester + lokal BYOK-modell og appens nettverkstrafikk er `UNVERIFIED`; app-guiden lover ikke CLI-ens offline-modus. |
| **Copilot cloud agent** | Repoaktivering er dokumentert gjennom `.github/copilot/settings.json`. | Navs enterprise-policy, plugin-discovery og samme publiserte RC i en representativ consumer. |
| **VS Code** | Sekundær kompatibilitetsflate. VS Code dokumenterer update-sjekk hver 24. time når `extensions.autoUpdate` er aktivert. | Verifiser faktisk custom-marketplace-oppdatering med to Grillmester-versjoner; den styrer ikke første Nav-release. |
| **OpenCode 1.18.19** | Eget, deterministisk generert target med 7 native agenter, 42 skills, 42 slash commands og projiserte native permission-/delegeringskontrakter. Isolert no-model-smoke bekrefter resolved config, discovery, native read av consumerens `AGENTS.md`, fravær av target-modellpin og en bruker-eid override som pinner bare Kokk lokalt. Aktivering skjer eksplisitt med `OPENCODE_CONFIG_DIR`; innebygde agenter beholdes. | Samme immutable source-SHA må fortsatt gjennom at `AGENTS.md` påvirker modellsvar, skill/command med modell, delegering, godkjent/avvist write og representativ model/tool-smoke før status kan kalles release-verifisert. Det finnes ingen marketplace/auto-update. |
| **OpenCode 2 beta** | Oppstrøms forventer V1-kompatibilitet for støttede agent-, command- og skillfiler. Grillmester bruker ingen OpenCode-plugin. | Full runtimeparitet er `UNVERIFIED`. V2-permissions og provider/model-adferd må testes separat; betaen styrer ikke OpenCode 1-release. |
| **Copilot CLI + lokal BYOK** | GitHub dokumenterer OpenAI-kompatible lokale providers, tool calling/streaming-krav og `COPILOT_OFFLINE=true`. Grillmesters agentpin kan overstyres eksplisitt med `subagents.agents.<name>.model: "inherit"`. | Den eksakte lokale modellen, kvantiseringen, contextprofilen, tool calls, delegeringen og permissionadferden må gjennom samme capability-smoke. 32k laptop-context er under GitHubs anbefalte 128k og skal rapporteres som en begrensning. |

OpenCode-smoken over kontakter ingen modell. Den har derfor ikke utført
modelldrevet skillbruk, semantisk orkestrering/delegering, write-godkjenning
eller kvalitetsvurdering; dette står eksplisitt igjen i høyre kolonne.

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
agentene har ingen modellpin og arver session/provider. Copilot-pluginen
beholder sin reviewede pin; Copilot CLI faller tilbake til sessionmodellen hvis
en deklarert agentmodell ikke kan brukes, men en lokal pilot bør sette
`inherit` eksplisitt i brukerens subagentsettings fremfor å være avhengig av
fallback. Se [lokale modeller og capability-smoke](local-models.md).

«Lokal modell» betyr bare at inferensen går til det lokale endepunktet.
Webtools, MCP-er, telemetry og update-/modellkatalogkall vurderes separat.
Copilot CLI har en dokumentert offline-modus. Grillmesters vanlige OpenCode-
target er ikke i seg selv en local-only-profil; en slik profil må i tillegg
deny-e remote capabilities og håndheve egress. Ikke rapporter en session som
lokal-only bare fordi valgt modell kjører på `127.0.0.1`.

Den flytende `marketplace`-branchen er oppdateringskanalen. Når en maintainer
har eksplisitt promotert en eksakt validert source-SHA fra `main`, kan
CLI-brukere som har valgt `autoUpdate: true`, hente endringen ved neste trusted
CLI-sesjon. En vanlig merge til `main` flytter ikke `marketplace`. CI,
`COPILOT_AUTO_UPDATE=false` og `--no-auto-update` hopper over hentingen.
Auto-update-testen er derfor post-deploy-evidens; en separat godkjenningsport
krever en immutable release-tag i stedet.

## Gate for release-verifisert OpenCode 1.18.19

Et generert target er støttet kildekode, men er ikke alene bevis på at en
konkret runtime, provider og modell oppfører seg riktig. For samme immutable
source-SHA:

1. Kjør `python3 scripts/generate_opencode.py --check`, validatoren og hele
   testpakken uten drift.
2. Kjør `python3 scripts/smoke_opencode.py --require-binary` med den pinnede
   OpenCode 1.18.19-binæren. Bekreft eksakt roster, commands, skills,
   fravær av modellpin, deklarerte native permissionregler og consumerens
   `AGENTS.md` i isolert config. Denne smoken er med vilje uten modell.
3. Start targetet fra et disponibelt consumer-repo med den samme source-SHA-en
   og observer en skill/command, delegering, godkjent write og avvist write.
4. Gjenta den representative oppgaven med provider-/modellprofilen som skal
   omtales som støttet. For en lokal modell må også
   [capability-smoken](local-models.md#capability-smoke-før-modellen-får-bakgrunnsarbeid)
   bestås.

Rapporter OpenCode 2, andre OpenCode 1-versjoner og uprøvde modeller som
`UNVERIFIED`; filkompatibilitet eller et vellykket chat-svar oppgraderer ikke
statusen alene.

## Gate fra RC til stabil Copilot-release

Bruk den versjonerte
[macOS-klientvalideringsprotokollen](macos-client-validation-protocol.md) og
evidensmalen for den repeterbare CLI-, App- og VS Code-delen av gaten. Resten av
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
