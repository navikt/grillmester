---
status: accepted
date: 2026-10-23
---

# Deklarerte justeringer og beholdte valg

Delvis erstattet av [ADR 0023](0023-prosjektlagret-designrom.md) for
prosjektlagrede rom: skisseversjoner og innspill lagres varig, og en avgrenset
editor kan lagre feltendringer. Delvis erstattet av
[ADR 0025](0025-behold-som-innspill-og-juster-visning-i-prov.md): «Behold denne
delen» er et vanlig innspill, nye beholdte valg lages ikke, og «Juster visning»
ligger i «Prøv». Eksisterende beholdte valg leses og frigis som beskrevet under.

## Kontekst

Kommentarer beskriver ønskede endringer, men designeren trenger også å prøve
avgrensede valg direkte, sammenligne retninger og ta med gode deler videre.
Vilkårlig DOM- eller CSS-redigering ville gjort koblingen til neste skisse
uklar og utvidet runtime-kontrakten betydelig.

## Beslutning

En valgfri `<stem>.design.json` ved siden av HTML-fragmentet deklarerer
navngitte varianter, deler og tillatte innstillinger. Serveren leser bare en
trygg regulær fil i samme private sesjon, validerer et lukket skjema og binder
deklarasjonen til skjermversjonen. Manglende deklarasjon gir vanlig skisse;
ugyldig deklarasjon gir et synlig varsel og ingen justeringskontroller.

Kontroller endrer bare deklarerte `data-vc-setting-*`-attributter til oppgitte
verdier. Forfatterens CSS bestemmer det visuelle resultatet. Deler identifiseres
med stabile, eksplisitte nøkler innenfor en variant. Tvetydige eller manglende
DOM-mål deaktiverer handlingen. Ingen vilkårlige selektorer eller stiluttrykk
mottas fra nettleseren, og HTML-kilden endres ikke.
Velavsluttede stilblokker i fragmentet får serverens stilnonce etter
markupfiltrering. Skissens skript er fortsatt fjernet, og CSP tillater ingen
eksterne stil-, font- eller nettverksressurser.

Sammenligning viser deklarerte seksjoner fra samme fragment med lik bredde,
eller én om gangen i smale vinduer. Et eksplisitt variantvalg og konkrete
innstillinger lagres som innspill. Visning alene er ikke et valg.

«Behold dette» lagrer en egen beslutning med variant, del og eventuelle
innstillinger. Beslutningen følger innsendingsrundene til den frigis. Sist
innsendte beslutning beholdes separat fra utkast; en lokal endring eller
frigivelse trer først i kraft for mottakeren ved neste innsending. Ved
skjermbytte vurderer grensesnittet deklarerte startverdier mot beholdte valg;
manglende deler eller avvik vises som noe som må følges opp. Dette er en
bevaringsbeskjed, ikke automatisk låsing eller bevis for at designet er likt.

Samme autentiserte bro, eneste serverskriver, private tilbakemeldingsfil og
opprydding som i ADR 0017 brukes. Ingen ny tjeneste, hook eller livssyklus
innføres. Grenser for deklarasjoner, innspill og beslutninger håndheves av
serveren. Den tekstfrie klikkloggen endres ikke.

## Konsekvenser

Forfatteren må velge meningsfulle kontroller og holde nøkler stabile der
semantikken er den samme. Fullt fri layoutredigering og historisk gjengivelse
av tidligere HTML-versjoner er ikke del av kontrakten. Alle innspill må
fortsatt vurderes og innarbeides i en ny, visuelt verifisert skisse.
