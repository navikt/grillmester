---
status: accepted
date: 2026-10-29
---

# Skrivebeskyttet skisseinspeksjon

## Bakgrunn

Canvas-tilstand og dokumentstruktur viser ikke hvordan en skisse ser ut.
Verkstedets eksisterende forhåndsvisningsadresse deler kontrollmyndighet med
innspillsflyten og skal ikke åpnes av en separat nettleser for visuell kontroll.

## Beslutning

`open_inspection` lager en kortlivet, uforanderlig gjengivelse av den publiserte
HTML-skissen med eksakt `expectedScreen`. Et appkoblet HTML-forslag krever også
sin egen `proposalId`. Samme rensing, Aksel-stiler og deklarerte samspill som i
verkstedet brukes. Resultatet oppgir kilde, stilkvittering og utløp, men har
verken innspillsverktøylinje, redigering, foreldreforbindelse eller kontrollnøkkel.

Visningen serveres fra en egen, tilfeldig loopback-port med en ny, avgrenset
lesekapabilitet. Den aksepterer bare GET for eksakt vert og dokumentsti, og
serverer ingen kildefiler, skrivetjenester eller andre adresser. Innholdet holdes
i minnet. Det finnes høyst én inspeksjon per skisse; ny inspeksjon erstatter den
forrige. Den utløper etter ti minutter. Publisering, lukking og avslutning
kaller den tilbake. `close_inspection` avslutter bare den angitte inspeksjonen.

Klientens tilgjengelige nettleser kan åpne denne visningen i bakgrunnen og
returnere bilder og prøve deklarerte interaksjoner. Designeren blir i sitt
verksted. Nettleseren må støtte slik bakgrunnsåpning; en manglende egenskap gir
en tydelig avgrensning, ikke installasjon, svakere sandkasse eller et nytt synlig
arbeidssted. En eid bakgrunnsfane gjenbrukes når nettleseren støtter det. Hvis
klienten mangler lukkehandling, tilbakekalles lesevisningen og fanen kan lukkes
med faneknappen; automatisk fanelukking loves ikke. Inspeksjonsadresser skal
ikke lagres eller deles. Tilbakekalling stopper ny
innlasting; den fjerner ikke bilder som allerede er levert.

## Avgrensning

- Dette er selvstendig gjengivelse av publisert innhold, ikke skjermfangst av
  vertsappen eller brukerens levende canvas-tilstand.
- Tilstand starter med deklarerte verdier. Fokus, ulagret tekst og native
  leveringsflyt må prøves separat. Bilder dokumenterer bare den viste flaten.
- Kjørende apper bruker sin eksisterende observasjon og godkjente demoside.
- Ingen egen nettleserbinær, ny modell, kildeeditor eller bildejournal innføres.
- Tester dekker eierskap, feil versjon, utløp, tilbakekalling, konkurrerende
  lukking/publisering, manglende skriverett og deklarert samspill.
