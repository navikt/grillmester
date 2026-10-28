# Designverksted: avklaring av to statiske varsler

Gjennomgått 28. oktober 2026 mot `4048fb80faaef185466999e8fa03bffc21164448`
i [PR #90](https://github.com/navikt/grillmester/pull/90). Kodegjennomgang,
49 relevante regresjoner og en separat prøve med 27 ekte HTTP-forespørsler
bekreftet grensene nedenfor. Prøvene bruker bare syntetiske data og eide
prosesser. Ingen CodeQL-regler, alvorlighetsterskler eller kontrolljobber endres.

## Aktivering av forslaget: varsel 53

`js/user-controlled-bypass` i `application-server.js` gjelder en rute som
bruker en annen autentisering enn arbeidsrommets API. Den eksakte
`POST /proposal/activate` går til `createProposalViews().activate()`. Den
krever både en kjent renderer-kandidat og riktig 256-bit aktiveringsnøkkel,
sammenlignet i konstant tid. Felles kontroll av Host, Origin og levende
arbeidsrom gjelder før aktivering, og livsløpet kontrolleres igjen etter
innlesing av kroppen.

Aktivering gir den bundne skissens visningskapabilitet med dens egen
innspillsflate. Den oppretter ingen myndighet til apprommets kontroll-API og
kan ikke bruke apprommets `/state`, innspills- eller innsendingsruter.
Disse rutene krever fortsatt det aktive kontrolldokumentets
myndighet. Ugyldige nøkler, kandidater, fremmed Origin, endrede ruter og
tilbakekalte visninger avvises. Tapt svar kan prøves på nytt fra samme kandidat.

Kjørbare regresjoner finnes i `application-server.test.js` og
`application-proposal-view.test.js`, særlig
`proposal activation requires its own capability and never authorizes workspace routes`.
Den separate HTTP-prøven kontrollerte også at ingen beskyttede lesinger eller
mutasjoner ble utført under de avviste forespørslene.

Vurdering: **falsk positiv**. Rutevalget er ikke en mulighet til å hoppe over
apprommets autentisering; aktiveringen har en egen, avgrenset kapabilitet.

## Lokal demokontroll: varsel 56

`js/file-access-to-http` i `app-runtime.js` følger kontrollerens lagrede nøkkel
til `http.request`. HTTP brukes som protokoll over en privat Unix-socket,
utelukkende valgt med `socketPath` og `agent: false`. Ingen hostname, port,
nettverks-URL eller proxy velges fra tilstandsfilen.

Tilstandsfilen åpnes uten å følge symlenker. Eier, filtype, lenketall,
rettigheter, størrelse, prosjektbinding og nøkler valideres. Socketstien må
være nøyaktig den beregnede stien for denne oppgaven; socketen må være eid av
brukeren og privat. Bare metodene status og stopp kan sendes. Kontrolleren
krever nøkkel og generasjon, og status inneholder ingen kontrollnøkkel.

`app-runtime.test.js` prøver ekte lokal IPC, feil nøkler, manipulerte
socketstier og tilstandsdata med falske TCP-mål. Den falske TCP-lytteren får
ingen forespørsler. Kontrollen sender heller ikke vilkårlig filinnhold.

Vurdering: **falsk positiv**. Fil-til-HTTP-sporet er nødvendig autentisering
mot den eide lokale kontrolleren, ikke utgående nettverkstrafikk.

## Videre kontroll

Varslene registreres med begrunnelsen `false positive` og konkrete
testreferanser etter [GitHubs triageflyt](https://docs.github.com/en/code-security/how-tos/manage-security-alerts/manage-code-scanning-alerts/triage-alerts-in-pull-requests).
Dette er en avklaring av disse to funnene, ikke et unntak for hele filene eller
fremtidige endringer. Endres kapabilitetskontrollen, rutingen, eierskapsgrensen
eller sockettransporten, må vurderingen gjøres på nytt og varslene gjenåpnes
ved behov. Prosesser med full tilgang som samme operativsystembruker er ikke
en separat sikkerhetsgrense for den lokale utviklingsøkten.
