---
status: accepted
date: 2026-10-23
---

# Avgrenset prøve av app-canvas

## Kontekst

Visual Companion gir innspill, tekstforslag, deklarerte justeringer og
beholdte valg gjennom en nettleserskisse. Runtime-en er en lokal Node.js-server,
ikke en Python-server. Den portable flyten bruker `comments.js wait` til å
hente en innsendt runde mens samtalen fortsatt behandler et verktøykall.
Vanlig nettleserinnhold kan ikke på egen hånd starte neste samtaletur.

Copilot-appens canvas-utvidelser kan knytte en visuell flate til samme sesjon.
Den kontrollerte SDK-en har `createCanvas`, `joinSession` og `session.send`.
En canvas kan bidra med handlinger som sesjonen kaller. Dette gir et konkret
spor for å levere eksplisitt innsendte innspill uten en separat chatmelding.

Det er ikke det samme som en ferdig erstatning for preview-runtime-en.
`CanvasProviderOpenResult` oppgir URL, tittel og status. Den kontrollerte
sesjonskontrakten inneholder ingen HTML-host, filserver eller delt,
transaksjonell lagring. Canvas-API-et er dessuten merket eksperimentelt.
GitHubs eget `color-orb`-eksempel bruker også en lokal Node.js-server og lar
en UI-handling sende en melding gjennom den tilknyttede sesjonen.

## Beslutning

Vi gjennomfører en avgrenset prøve i `experiments/canvas-review/`, utenfor
pluginpayloaden. Den skal bruke den faktiske SDK-kontrakten og en disponibel
testflate med oppdiktede data. Ingen personlig installasjon, klientinnstilling,
pluginmanifest eller generert target endres av prøven.

Prøven undersøker denne kjeden:

1. En utvidelse blir med i en eksisterende sesjon og deklarerer en canvas.
2. Canvasens åpnehandling returnerer en autentisert loopback-URL.
3. Brukeren samler innspill og sender én eksplisitt runde.
4. Utvidelsen lagrer runden før den forsøker å legge en melding i den samme
   sesjonens kø med `session.send` og `mode: "enqueue"`.
5. Et returnert meldings-ID er kvittering for mottak i køen. Det beviser ikke
   at runden er lest, utført eller visuelt verifisert.

En prøve med simulert vert kan kontrollere SDK-koblingen og feilhåndteringen
uten å starte en klient eller kontakte en modell. Den teller ikke som en
bestått prøve i Copilot-appen. Produksjonsintegrasjon utsettes til faktisk
panelvisning, avsluttet tur, pågående tur, sesjonsisolasjon og opprydding er
prøvd i appen. Akseptkriteriene er beskrevet i
[canvas-protokollen](../testing/visual-companion-canvas.md).

En eventuell produksjonsløsning skal være en valgfri appadapter med dagens
portable flyt som fallback. Node.js-hostingen beholdes inntil et støttet
alternativ er påvist. Den første adapteren skal gjenbruke validering,
innsendingsrunder og én autoritativ innspillskø, ikke synkronisere to separate
implementasjoner.

En UI-endring alene er aldri en innsendelse. Bare den betrodde delen av
grensesnittet kan be om å levere en validert, lagret runde til den bundne
sesjonen. Skisseinnhold får ingen generell adgang til `session.send`, verktøy,
filsystem eller utvidelsens rettigheter. Samlet innsending, utkast, skjermbinding
og beholdte beslutninger fra ADR 0017 og 0018 videreføres.

## Avgrensning og videre beslutning

Denne beslutningen godkjenner forsøket, ikke automatisk aktivering i
Grillmester. Den innfører ingen MCP-server, installasjonshook, generell
bakgrunnsvakt eller ny filsynkronisering i konsumentrepoer. En prosjektmappe
eller personlig extensions-mappe blir ikke opprettet automatisk.

Før distribusjon må vi beslutte og teste hvordan apputvidelsen inngår i de
deterministiske targetene. Den fokuserte Copilot-projeksjonen kopierer i dag
`plugin.json` byte-eksakt, men bare utvalgte agenter og skills. Et nytt
`extensions`-felt kan derfor peke på filer som ikke følger med. Dette må løses
eksplisitt i genereringspolicyen eller gjennom en separat pakke. OpenCode og
klienter uten canvas skal fortsatt fungere. En overgang til et annet
pluginmanifestformat inngår ikke i forsøket.

Vi må også avklare om appen lagrer canvas-URL eller innhold i historikken.
Midlertidige innspill skal ikke bli varige prosjektartefakter uten en egen
beslutning om lagring og opprydding. En lukkehendelse er ikke tilstrekkelig
oppryddingsgaranti; stopp, krasj og avbrutt forbindelse må håndteres.

## Konsekvenser

Det mest lovende fremskrittet er tettere forbindelse mellom skissen og
samtalen: automatisk åpning i panelet, eksplisitt levering av innspill og
synlige kvitteringer. Det fjerner ikke nødvendigvis serveren, og gir ikke
automatisk fri layoutredigering eller varig historikk.

Vi kan teste dette uten å endre den fungerende portable løsningen. En bredere
integrasjon krever dokumentert vertskompatibilitet og en oppdatert
distribusjonsbeslutning, før den blir del av en release.

## Kilder

- [Canvas extensions i Copilot-appen](https://docs.github.com/en/copilot/how-tos/github-copilot-app/working-with-canvas-extensions).
- [Pluginformat og utvidelsesstier](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference).
- [GitHubs canvas-eksempel med lokal HTTP-server](https://github.com/github/awesome-copilot/blob/main/extensions/color-orb/extension.mjs).
- [SDK-ens kø- og kvitteringssemantikk](https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/steering-and-queueing).
- SDK-typene `canvas.d.ts`, `extension.d.ts`, `session.d.ts`, `types.d.ts` og
  `generated/rpc.d.ts` som fulgte den undersøkte appinstallasjonen. Prøven
  bruker en eksplisitt SDK-sti og dokumenterer hvilken versjon som er kontrollert.
