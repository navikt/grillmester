# Klientstøtte og releasegater

Grillmester er instruksjoner og arbeidsmetode for en agentisk klient. Det er
ikke en sandbox, en autorisasjonsmekanisme eller en erstatning for menneskelig
review og deterministiske gates.

Den normative sikkerhetskontrakten for NAV-bruk ligger i
[runtime-sikkerhetspolicyen](runtime-safety.md). Den krever sandbox og aktive
godkjenningsgrenser, og beskriver effektive CLI-/App-kontroller. Denne siden
handler om hva hver klientflate faktisk er verifisert for.

## Ansvarsdeling

| Lag | Eies av | Hva det faktisk styrer |
| --- | --- | --- |
| Agentprompt og skills | Grillmester | Rolle, arbeidsflyt, evidenskrav og forventet atferd. |
| Tilgjengelige tools | Klient, pluginprofil og konfigurerte MCP-er | Hvilke handlinger modellen kan foreslå å bruke. |
| Tool-/path-/URL-godkjenninger | Bruker og enterprise-policy | Om en konkret handling får kjøre uten å stoppes. |
| Sandbox | Copilot CLI eller cloud-miljøet | Filsystem-, nettverks- og prosessgrensen handlingen kjører innenfor. |
| CI, rulesets og CODEOWNERS | Consumer-/organisasjonseier | Deterministiske leveranse- og mergekrav. |

Et verktøy i en agentprofil gir ikke OAuth-scope, installerer ikke en MCP og
omgår ikke klientens godkjenninger. Motsatt er en promptregel som «ikke skriv»
ikke en teknisk blokkering dersom klienten faktisk tilbyr write.

## Toolstrategi

Grillmester, Barista, Designer og Doctor Who er offentlige, interaktive roller
som må kunne virke på tvers av Copilot CLI, app og cloud. De utelater derfor
`tools` og arver hele runtimeflaten. Dette er samme enkle modell som de
piloterte agentene i Hovmester og Budstikka, og unngår en stor aliasmatrise som
drifter mellom klienter og NAVs MCP Registry. Det gir også en bredere teknisk
flate: rolleprompten er arbeidsmåte, ikke kapabilitetsisolasjon.

NAVs MCP Registry og enterprise-policy bestemmer hvilke MCP-servere og tools
som faktisk kan være tilgjengelige. Manglende GitHub Projects- eller Figma-
write skal gi chatutkast, Visual Companion eller `NEEDS_INPUT`, aldri shell-/
API-fallback eller et falskt suksesskrav. Remote HTTP/SSE-MCP-er ligger utenfor
OS-sandboxen; OAuth-scope, approval og serverautorisasjon er den reelle grensen.
Før stabil lansering må de effektive toolsettene gjennomgås med Team Copilot
mot live Registry og testes i hver støttet klient.

Interne roller har smalere oppdrag: Kokk implementerer og verifiserer én slice
og kan lese autoritative webkilder når lokal evidens ikke er nok,
Grill-inspektør bruker blant annet read-only shellinspeksjon som `git diff`, og
Researcher gjør kildebelagt research uten writes. Rolleprompten styrer
arbeidsmåten; klient/sandbox/approval styrer den tekniske grensen.

GitHubs
[custom-agentreferanse](https://docs.github.com/en/copilot/reference/custom-agents-configuration#tools)
dokumenterer at utelatt `tools` betyr alle tilgjengelige tools, mens en navngitt
liste filtrerer både built-ins og MCP-tools. Gjennomfør klienttest med observerte
tool calls, godkjent write og avvist write før stabil release.

## Klientstøtte

| Klient | POC-status | Hva som fortsatt må bevises før stabil |
| --- | --- | --- |
| **Copilot CLI** | Referanseklient. Lokal mount og install-/oppgraderings-/rollbackflyt testes deterministisk. | Publisert immutable kandidat, resolved modell, agentvalg, effektiv sandboxpolicy og runtime-toolbruk på representativt repo. |
| **Copilot app** | Dokumentert Plugins-UI og deep-link onboarding. | Cloud-sandbox som session location, eksakt resolved katalog/source, kvalifisert agentvalg, delegering, tilgjengelige MCP-tools og godkjent/avvist write. |
| **Copilot cloud agent** | Repoaktivering er dokumentert gjennom `.github/copilot/settings.json`. | NAV enterprise-policy, plugin-discovery og samme publiserte RC i en representativ consumer. |
| **VS Code** | Sekundær kompatibilitetsflate. | Observer og logg; den styrer ikke første NAV-release. |
| **OpenCode** | Skills-only eksperiment. | Hver skill må portabilitetsauditeres. Agentteam, marketplace og felles agentkontrakt følger ikke med. |

GitHub dokumenterer at Copilot app kan installere plugins via **Settings →
Plugins**, og at CLI-konfigurerte skills/MCP-er kan bli tilgjengelige i appen.
Det er ikke i seg selv evidens for samme runtimeadferd; klientene testes
separat.

## Gate fra RC til stabil release

1. Installer den eksakte, immutable RC-ref-en og bekreft modelloppløsning i
   Copilot CLI.
2. Bekreft standardpakken alene og standardpakken + NAV-tillegget uten
   agent-/skillkollisjoner eller døde referanser. Kjør i tillegg en strukturell
   install-/uninstall-smoke av NAV-pakken alene, men ikke kall den en komplett
   agentopplevelse uten standardpakken.
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
   NAVs enterprise-policy.
8. Verifiser med Team Copilot at pluginen er forståelig i `nav-pilot`/MCP-
   onboarding, at live MCP Registry ikke gir skjulte eller overlappende
   capabilities, og at eier-/supportgrensene er navngitt.
9. Registrer NAV-eierens rettighets-/relisensieringsavklaring for materiale fra
   kilder uten eksplisitt lisens, og avklar eller erstatt Doctor Who-navnet før
   offentlig stabil promotering. Verifiser også at private vulnerability
   reporting faktisk kan åpnes av en vanlig reporter; repository-eier er
   ansvarlig for kanalen.
10. Test oppgradering og rollback i det piloterte referanserepoet og minst to
   representative NAV-consumere. Manglende evidens er `UNVERIFIED`, aldri
   `PASS`.

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

- [Følg runtime-sikkerhetspolicyen](runtime-safety.md)
- [Installer og aktiver i riktig scope](installation.md)
- [Velg riktig agent og skillfamilie](agents-and-skills.md)
- [Behold repoets stående regler og templates lokalt](repository-context.md)
- [Kjør en kontrollert consumer-pilot](consumer-pilot-runbook.md)
