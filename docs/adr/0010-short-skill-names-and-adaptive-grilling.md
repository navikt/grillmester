---
status: accepted
date: 2026-09-09
---

# Korte skillnavn og automatisk valg av grillflyt

## Kontekst

Prefikset `grillmester-` gjør katalogen vanskelig å skanne og har ført til
forveksling mellom gamle og nye kall. Den tidligere consumer-piloten bevarte
gamle skills uten eksakt ID-kollisjon. nav-pilot distribuerer og starter valgt
agentpakke, men erstatter ikke klientens regler for repo- og brukerskills.

Grillmester krevde eksplisitt valg av både Grill with docs og Wayfinder, selv
om brukerens oppgave allerede ga grunnlag for å velge riktig arbeidsflyt.
Resultatet var at dokumentert grilling uteble eller krevde at brukeren kjente
skillnavnene.

## Beslutning

- Bruk korte, oppgaveorienterte skill-ID-er som matcher mappenavnene. Behold
  agent-ID-ene og original kildeidentitet i proveniens. Ikke distribuer gamle
  prefiksnavn som alias-skills; de ville duplisere katalogen og beholde uklarheten.
- Agentene velger fra klientens faktiske skillkatalog og bruker klientens
  native lastemekanisme. Slashkommandoer er brukerinnganger; de er ikke
  shellkommandoer eller en universell syntaks for verktøykall.
- Grillmester starter med grilling tilpasset usikkerheten. Grill with docs er
  standard for en sammenhengende avklaring. Wayfinder brukes når avhengige,
  uløste beslutninger krever et varig kart på tvers av økter. Mye ferdig
  spesifisert implementering utløser ikke Wayfinder.
- Wayfinder bruker dokumentert grilling for relevante beslutninger i kartet.
  Når veien er avklart, går arbeidet videre med den letteste leveranseflyten.
- Skillvalg er agentens ansvar. Materielle brukervalg og manglende fullmakt
  avklares; fullmakt som allerede dekker handlingen skal ikke etterspørres igjen.
  Domeneord og kvalifiserende beslutninger dokumenteres innenfor oppdragets og
  consumer-repoets rammer. Skillvalg gir ikke i seg selv fullmakt til eksterne
  trackerhandlinger.
- Handoff forblir manuelt aktivert for brukerbestilt overlevering til en annen
  sesjon, klient eller kollega. Klienten eier vanlig kontekstkomprimering;
  kontekstpress, lange samtaler og fasebytte utløser ingen automatisk rotasjon.
- Migrering kartlegger gamle komponenter, kildeeierskap, lokale tilpasninger,
  sync-workflows og instruksreferanser før eksakte endringer utføres. Den
  innfører ingen ny sync-livssyklus og sletter aldri hele skillrøtter.

## Konsekvenser

Navneendringen bryter gamle direkte skillkall. Consumer-kopier og henvisninger
må migreres sammen med oppdateringen av pakka; en eksisterende økt må laste
den nye katalogen. Repo- og brukerskills med samme navn kan fortsatt skygge
pakka, og faktisk kilde må kontrolleres ved feil.

Generatorer og validatorer kontrollerer korte skillreferanser mot den valgte
rosteren, inkludert skills som er utelatt fra fokusert kontekst. Strukturell
validering, native lasting og valg av arbeidsflyt er separate bevis: en tvunget
loopback-respons beviser ikke at en modell velger riktig metode av seg selv.

Tidligere release- og rettighetsbevis beholdes som historiske bevis for sitt
opprinnelige innhold; en navneendring skal ikke omskrive hva som ble godkjent.
