---
status: accepted
date: 2026-11-04
---

# OpenCode 2 og valgfri cplt

Erstatter delvis ADR 0001, 0003 og 0004.

Teamets hovedvei er Copilot-appen med lokal sandbox, der cplt ikke virker. Én
person bruker OpenCode, så terminalveien skal fortsatt virke, men den skal ikke
kreve mer enn nødvendig. `brew install opencode` gir nå OpenCode 2, som
launcheren avviste, og nav-pilot støtter den allerede.

Launcheren krever derfor OpenCode `>=2.2.5,<3` og godtar ikke lenger OpenCode 1.
Targetet beholder navnet `opencode-v1`, fordi OpenCode 2 leser filformatet
uendret. TUI-en har ikke `--agent` eller `--model`, så launcheren velger agent
med `default_agent` i `OPENCODE_CONFIG_CONTENT`.

cplt er valgfri for standardlauncheren. Med cplt på `PATH` starter klienten
inne i sandboxen. Uten cplt, eller med `--no-cplt`, starter klienten direkte, og
launcheren sier fra om det. En installert cplt som ikke består versjonssjekken
stopper launch, så ingen mister sandboxen uten å ha valgt det. `grillmester
local` krever fortsatt cplt, fordi cplt holder modellrequestene på loopback.
Direkte launch bruker `--standalone`; ellers skriver OpenCode `service.json` med
tjenestens passord i det distribuerte targetet. Flagget feiler under cplt, som
har sin egen tjeneste for hver økt.

OpenCode 2 bruker `OPENCODE_CONFIG_DIR` i stedet for brukerens config-mappe, ikke
i tillegg til den. Direkte launch peker derfor `OPENCODE_CONFIG` på brukerens
`opencode.json`. cplt bestemmer selv den variabelen, så der sier launcheren fra
om filen ikke blir lest. Vi kopierer den ikke til `OPENCODE_CONFIG_CONTENT`,
fordi nøkler da havner i miljøet til verktøyene.

Targetets `opencode.json` bevarer grensene fra OpenCode 1. `external_directory`
spør, med unntak for skills i
`OPENCODE_CONFIG_DIR`, siden OpenCode 2 ellers leser utenfor prosjektet uten å
spørre. `execute` er avslått, fordi Code Mode kan gjøre HTTP-kall som
`webfetch: deny` ikke stopper. `opencode_*` er avslått, fordi OpenCodes egne
verktøy for økter og worktrees ikke er vurdert for rollene våre.

Én liten smoke erstatter de to gamle. Den starter øktene gjennom launcheren,
direkte og gjennom cplt, mot en loopbackprovider. Linux-CI tester direkte, fordi
cplt krever bubblewrap for OpenCode 2 på Linux; macOS-gaten tester begge veier.
