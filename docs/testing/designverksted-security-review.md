# Designverksted: avklaring av to statiske varsler

Gjennomgått 28. oktober 2026 mot `4048fb8` i
[PR #90](https://github.com/navikt/grillmester/pull/90).
Begge CodeQL-varslene er lukket som **falske positiver** etter kodegjennomgang,
regresjonstester og HTTP-prøver. Ingen analyseregler eller kontrolljobber er endret.

## Varsel 53: aktivering av forslag

`js/user-controlled-bypass` i `application-server.js` gjelder eksakt
`POST /proposal/activate`. Ruten krever en kjent kandidat og en egen 256-bit
nøkkel sammenlignet i konstant tid, samt gyldig Host, Origin og aktivt arbeidsrom.
Aktivering gir bare den bundne skissens visning og innspillsflate; den gir
ingen myndighet til apprommets kontroll-API.

[Serverregresjonen](../../plugin/skills/design-prototype/tests/application-server.test.js)
`proposal activation requires its own capability and never authorizes workspace routes`
og [visningsregresjonene](../../plugin/skills/design-prototype/tests/application-proposal-view.test.js)
dekker feil nøkler, kandidater, origins, ruter og tilbakekalte visninger.
Avviste forespørsler utfører ingen beskyttede lesinger eller mutasjoner.

## Varsel 56: lokal demokontroll

`js/file-access-to-http` i `app-runtime.js` følger kontrollnøkkelen til
`http.request`. Transporten går utelukkende over en privat Unix-socket med
`socketPath` og `agent: false`. Tilstandsfilen velger aldri et TCP-mål.
Eier, filtype, rettigheter, lenketall, størrelse, prosjektbinding, socketsti,
nøkkel og generasjon kontrolleres; bare status og stopp er tilgjengelig.

[Prosessregresjonene](../../plugin/skills/design-prototype/tests/app-runtime.test.js)
dekker ekte lokal IPC, feil nøkler, endret socketsti og falske TCP-felt.
TCP-lytteren mottar ingen forespørsler, og vilkårlig filinnhold sendes ikke.

## Gyldighet

Vurderingene gjelder disse to kontrollflytene. Endret autentisering, ruting,
eierskap eller transport krever ny gjennomgang og eventuell gjenåpning.
Prosesser med full tilgang som samme operativsystembruker er ikke en separat
sikkerhetsgrense for den lokale utviklingsøkten.
