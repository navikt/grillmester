---
status: accepted
date: 2026-10-23
---

# Uforanderlige innsendte runder

## Kontekst

Den portable innspillskøen har hittil levert innsendte kommentarer fra den
gjeldende listen. Hvis et innspill slettes, åpnes igjen eller sendes på nytt
før mottakeren leser det, kan den opprinnelige runden forsvinne fra dette
utvalget. Status og svar kan også ha endret seg siden innsendingen. En senere
canvasadapter må kunne levere samme runde uavhengig av slike endringer.

## Beslutning

`FeedbackStore` beholder én journal i eksisterende `comments.json`. Hver
vellykkede innsending legger til et uforanderlig øyeblikksbilde av akkurat
den rundens kommentarer og endrede beslutninger, med innsendingens nummer,
revisjon og tidspunkt. Journal, gjeldende liste og publiserte føringer lagres
i samme atomiske operasjon. Ingen annen skriver, tjeneste eller kø innføres.
Utkast, statusendringer og lesing oppretter ingen nye runder.

`list` beholder rollen som oversikt over nåtilstanden. Den vanlige
nettleserpollingen henter ikke hele journalen. `wait --after N` leser gjennom
det autentiserte `GET /comments/submissions?after=N` og returnerer én neste
runde i rekkefølge:

- `submission` er nummeret på runden som faktisk ble levert.
- `comments` er rundens opprinnelige kommentarer, med opprinnelig skjermbinding.
- `decisions` inneholder aktive innsendte føringer ved denne runden og
  frigivelser som ble sendt i akkurat denne runden. Senere runder påvirker
  ikke denne visningen.
- `currentComments` gir separat, avgrenset nåtilstand for de samme ID-ene,
  inkludert om et innspill er fjernet fra listen. Historikken omskrives ikke.
- `latestSubmission` og `hasMore` viser om flere runder venter. De er ikke
  kvitteringer for utført arbeid.

Mottakeren behandler alle innspill i svaret før den flytter sin markør til
svarets `submission`. Ved `hasMore` hentes neste runde med denne markøren.
Lesing kvitterer ikke eller sletter historikk på serveren. Markøren må fortsatt
holdes sammen med riktig `session_id` og `state_dir`; den gjelder bare denne
previewøkten. En markør foran øktens siste innsending avvises.

Historiske innspill skal vurderes sammen med nåtilstanden. En fjernet eller
gjenåpnet kommentar skal ikke gjenopprettes eller få et foreldet svar bare
fordi den finnes i en eldre runde. `resolve` og `reopen` kan derfor bruke
`--submission N`, som sendes som `expectedSubmission` til samme lager.
Oppdateringen avvises hvis live-kommentaren tilhører et annet innsendingsnummer,
også når den er et nytt utkast med nummer 0. Dette er en avgrenset kontroll av
rundetilhørighet, ikke låsing av alle samtidige status- og svarendringer.

Beholdte valg har også sin egen `revision`. Lagring og frigivelse kan ta
`expectedRevision`, som sammenlignes med akkurat den beslutningen, ikke med
alle endringer i køen. Nettleseren binder kontrollen til versjonen den så da
et lokalt utkast begynte. En nyere lagring i en annen fane gir konflikt og
bevarer både det lokale utkastet og den nyere lagrede føringen. Grensesnittet
viser de lagrede verdiene og merknaden. **Bruk mitt valg i stedet** gjør et
nytt forsøk mot den viste beslutningsrevisjonen; en ny samtidig endring gir
konflikt igjen. **Forkast mitt utkast** rydder bare det lokale utkastet.
Den sist innsendte føringen endres fortsatt først ved neste eksplisitte Send.

For et tidligere innsendt innspill betyr **Fjern fra listen** at live-oppføringen
fjernes. Grensesnittet forklarer at den innsendte runden bevares. Det er ikke en
sletting av historikk eller en kvittering på kansellert arbeid.

Journalen har høyst 200 runder og inngår i øktens eksisterende grense på 2 MiB.
Ingen eldre runde kastes automatisk. Når en grense nås, avvises hele den nye
innsendingen uten å flytte revisjon, innsendingsnummer eller utkast. Tapt
HTTP-kvittering håndteres fortsatt med samme operasjonsnøkkel fra ADR 0020;
gjentakelse skal ikke legge til en ny runde.

## Konsekvenser

Flere innsendinger mens mottakeren arbeider blir lest i rekkefølge, også når
de bruker samme kommentar-ID. Vanlige listefelt beholder sin nåbetydning,
mens mottakerens arbeidsflyt må hente og avstemme én runde om gangen. En nyere
CLI skal avvise en server uten journalgrensesnittet fremfor å utlede tapte
runder fra den mutable listen. Server og leseskript skal brukes fra samme
runtimeversjon.

Dette er fortsatt privat, midlertidig øktlagring. Normal stopp og opprydding
fjerner journalen sammen med resten av økten. Ny serverøkt starter fra 0;
restartgjenoppretting, import og migrering fra en eldre prosess innføres ikke.
Journalen samler ikke nye typer personopplysninger, DOM-tekst eller feltverdier.

Beslutningen aktiverer ingen canvasadapter, installasjonshook, ny lifecycle
eller automatisk levering. En senere adapter skal lese denne samme journalen.
Kvittering fra en samtalekø, faktisk behandling og visuelt verifisert resultat
må fortsatt være separate tilstander, som beskrevet i ADR 0019.
