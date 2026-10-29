---
status: accepted
date: 2026-10-29
---

# Direkte innspill og gjenopptatt visning

## Bakgrunn

En enkelt kommentar krever unødvendige steg når den først må lagres i en kurv.
Vedvarende markeringsmodus gjør det dessuten uklart når prototypen kan brukes.
En omlasting av en aktiv appvisning kunne avvise sin egen forbindelse, og en
avvist forhåndsvisning kunne beholde en eldre HTTP 200-status.

## Beslutning

Appen og skissen kan brukes som vanlig. «Gi innspill» aktiverer målvalg én gang.
Den ferdige kommentaren kan sendes direkte. «Legg til flere» beholder muligheten
til å samle notater; knappen viser hvor mange den uttrykkelige sendingen omfatter.
Det er ingen tidsstyrt sending eller sammenslåing av allerede sendte runder.
Dette erstatter de vedvarende «Prøv»/«Endre»-modusene fra ADR 0025 og den
obligatoriske kurven i ADR 0027, men bevarer innspillsdata og versjonsbinding.

Direktesending oppretter kommentar, eventuell appsidereferanse, uforanderlig
innsendt runde og leveringsstatus i én lagring. Gjeldende revisjon og hele settet
av ventende kommentar-ID-er må stemme med det som vises. Et tapt svar bruker
samme operasjonskvittering; usikker sending beholdes for identisk nytt forsøk.
En feil ved lesing etter lagring må aldri presenteres som en sikkert avvist
sending. Bare sendte runder gir beskjed til samtalen.

Samme appfane kan etter omlasting gjenbruke sin allerede validerte kontrollnøkkel
fra origin- og fanebundet sessionStorage. Serveren validerer nøkkelen igjen.
Et gjenopptak fornyer bare rapportgenerasjonen, med egen idempotent forespørsel.
En offentlig invitasjon, ny fane, utløpt kandidat eller gammelt canvas får ingen
ny skriver. Et validert gjenopptak fornyer innrammingen av eksisterende forslag,
med samme eier og tilbakekalling av gamle nøkler, uten å avslutte forslagsdataene. Hovedappens
kommentartekst, valgte mål og eventuelt uavklart sendeforsøk kan også bevares i
avgrenset sessionStorage. Gjenoppretting validerer formen og romtilknytningen;
serveren kontrollerer handlingen på nytt. Uavklart sending krever et uttrykkelig
nytt forsøk med samme kvittering. Appfelt og utkast i forslag med ny innramming
loves ikke gjenopprettet. Lukking avslutter fortsatt instansen; varig gjenåpning
krever et lagret rom.

Proxyfeil kan svare med et fast diagnostikkdokument uten hemmeligheter eller
appinnhold. Diagnostikk fra dokumentet oppdaterer status bare når kontrollskallet
bekrefter den aktive rammen med eksakt origin, epoch og forespørsel. Proxyen
rapporterer også transportstatus for den avtalte åpningen av appen. Avviste
bakgrunnsforespørsler kan ikke overskrive forbindelsesstatusen. En bekreftet feil
erstatter eldre suksess, med et konkret neste steg i brukerflaten.

## Avgrensning og kontroll

- Valg mellom dagens app og forslag, skissevarianter og lagrede versjoner er
  fortsatt ulike ting. De skal ikke dele samme faner eller få tvetydige navn.
- Endringen gir ingen kildeeditor, automatisk appomstart eller svakere sandbox.
- Dokumentstruktur fra `read_preview` er ikke piksler eller visuell kontroll.
  Selvstendig gjengivelse beviser heller ikke tilstanden i den åpne nativevisningen.
- Figma-overlevering, vernede felt og lagrede HTML-/descriptor-par bevares.
- Regresjoner skal dekke atomisk sending, tapte svar, endret kø, fokus,
  smale flater, gjenlasting, konkurrerende visninger og presis feildiagnose.
- Nettleserprøver erstatter ikke native prøve med sandkassen på eller utprøving
  med designere før bred utrulling.
