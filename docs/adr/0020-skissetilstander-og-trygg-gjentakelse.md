---
status: accepted
date: 2026-10-23
---

# Klikkbare skissetilstander og trygg gjentakelse

## Kontekst

Skisser med flere situasjoner trenger en naturlig vei mellom dem. En kommentar
til en bekreftelse må beholde denne konteksten når designeren går tilbake.
Nettleserprøving viste også at en vellykket lagring med tapt kvittering kunne
føre til dupliserte innspill når samme kladd ble forsøkt lagret igjen.

## Beslutning

En `button` med `type="button"`, `data-vc-control` og `data-vc-value` kan velge
en eksisterende innstilling i nærmeste entydig bundne `data-vc-key`-del.
Runtime validerer kontroll og alternativ mot skjermens deklarasjon og bruker
samme lokale tilstand som justeringspanelet. Knappen kjører bare i utforsking;
kommentering beholder sin vanlige betydning. Ingen vilkårlige skript,
selektorer, feltinnsamling eller nye nettverksmuligheter innføres.
Avgrensede lokale fragmentlenker kan fokusere ett synlig, entydig ID-mål i
skissen, slik at feiloppsummeringer kan brukes. Runtime behandler dette som
lokal fokusflytting, avbryter standardnavigasjon og lagrer ikke DOM-ID-en.

Punkt-, område- og tekstinnspill i justerbare deler kan lagre et lukket
`context`-objekt med deklarert variant, del og innstillinger. Mottakeren får
dermed riktig situasjon sammen med skjermversjonen. Brukeren kan be om å vise
samme situasjon igjen i gjeldende skisse. Andre deler og merknader bevares;
historisk HTML eller skjemaets verdier rekonstrueres ikke.

Hver nettlesermutasjon får en tilfeldig identitet. Samme uendrede intensjon
gjenbruker identiteten ved nytt lagringsforsøk. Serveren lagrer et avtrykk
etter vellykket atomisk lagring og avviser gjenbruk med annen operasjon.
Gjentakelse returnerer gjeldende kø uten å skrive på nytt, også hvis objektet
senere er slettet. Opptil 2048 kvitteringer beholdes i samme serverprosess;
ingen kastes for å gi plass til nye. Nøkler og avtrykk er ikke innspillsdata.

## Konsekvenser

Skisser kan prøve forhåndsdefinerte steg og situasjoner uten at de blir
kjørbare forretningsprosesser. Forfatteren må vise at resultatene er simulerte.
Bare eksplisitt innsending gjør innspill tilgjengelige for neste runde.
Endret kladd etter usikker lagring er en ny intensjon, og erstatter ikke det
første innspillet. Kø, lagring og opprydding fra ADR 0017–0018 består; ingen
ny tjeneste eller filsynkronisering innføres. Kvitteringene er ikke varige.
