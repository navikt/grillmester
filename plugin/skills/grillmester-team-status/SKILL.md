---
name: grillmester-team-status
description: "Builds evidence-based team status, goal progress and prioritisation summaries from explicitly confirmed sources. Use for weekly status, planning-period reviews, cross-repository work overviews or prioritisation; GitHub Projects is supported but never assumed."
license: MIT
---

# Teamstatus

Bygg en sporbar statusrapport fra kildene teamet faktisk bruker. GitHub Projects
er én mulig kilde, ikke en forutsetning. Standardmodusen er read-only.

## 1. Avklar statusoppdraget

Finn eller spør om:

- team eller produktområde
- rapporttype, periode og målgruppe
- beslutningen rapporten skal støtte
- autoritative kilder for mål, arbeid, kapasitet og feltsemantikk
- hvilke repositories, prosjekter og andre systemer som inngår

Les relevante consumer-eide instruksjoner og dokumenter først. Et remote-navn,
en project-lenke eller en projects-verdi i en issue-mal er bare et spor til det
er bekreftet av eksplisitt teamkontekst eller brukeren.

Ved arbeid på tvers av repositories må scope være navngitt eller bekreftet.
Ikke gjør organisasjonsbrede søk og kall resultatet «teamstatus».

## 2. Etabler kildegrunnlaget

Lag en kort intern kildeliste med:

- kilde og scope
- når data ble hentet
- hvilke felter eller dokumenter som er brukt
- tilgangshull og kjente svakheter

Hvis en nødvendig kilde, periode eller semantikk mangler, spør ett konkret
spørsmål. Hvis kilden ikke kan leses, be brukeren dele et relevant utdrag og
merk begrensningen i rapporten.

For GitHub Projects:

1. Få owner og project number fra en bekreftet lenke eller teamkilde.
2. Hent felt, opsjoner og items dynamisk.
3. Finn teamets forklaring av kolonner og felter. Ikke utled «aktiv»,
   «ferdig», mål, periode, størrelse eller prioritet bare fra feltnavnet.
4. Bruk [projects-v2.md](./references/projects-v2.md) for tekniske
   leseoppskrifter når relevant.

Issue-maler kan brukes til å foreslå et prosjekt som brukeren kan bekrefte, men
de definerer ikke automatisk teamets tavle eller hele rapportscopet.

## 3. Bygg rapporten

Velg malen som passer fra [rapportmaler.md](./references/rapportmaler.md):

| Rapport | Formål |
|---|---|
| Ukesoversikt | Synliggjøre arbeid, blokkeringer og nylige endringer |
| Periodestatus | Koble verifiserte resultatsignaler og arbeid til teamets mål |
| Prioriteringsunderlag | Sammenligne avklarte kandidater mot mål og kriterier |

Rapporten skal skille mellom:

1. **Kildegrunnlag** — hva som er lest, med tidspunkt og scope.
2. **Verifiserte observasjoner** — det kildene faktisk viser.
3. **Tolkning** — mønstre og konsekvenser du utleder.
4. **Datagap og antagelser** — hva som ikke kunne verifiseres.
5. **Neste avklaring** — hva teamet bør undersøke eller beslutte.

En tracker dokumenterer arbeid, ikke nødvendigvis effekt. Ikke vurder
måloppnåelse fra issue-status alene; bruk måledata eller merk effektstatus som
ukjent.

Før et prioriteringsunderlag må anledning, mål, kriterier, kapasitet og
kandidater være avklart. Ikke fyll manglende kandidater med en antatt backlog.

## Tavle- eller feltguide mangler

Tilby et kort intervju:

1. Hva betyr hver relevant kolonne eller status?
2. Hvilke felter brukes til mål, periode, prioritet og størrelse?
3. Hvilke unntak og overgangsregler finnes?

Lever først guiden som et utkast i samtalen. Avklar deretter riktig
consumer-eid målsted. Opprett issue, fil eller PR bare etter eksplisitt
godkjenning.

## Eksterne endringer

Statusarbeid er read-only med mindre brukeren ber om noe annet. Før du endrer en
issue, prosjektverdi, guide eller rapport:

1. vis eksakt repository, prosjekt, item og felt eller dokument
2. vis gammel og ny verdi eller fullstendig utkast
3. be om eksplisitt godkjenning

Ikke endre feltdefinisjoner eller opsjoner som en bieffekt av rapportering.

## Grenser

### Alltid

- Bekreft scope og kilder.
- Hent prosjektfelter dynamisk når GitHub Projects brukes.
- Skill kildedata, tolkning, antagelser og datagap.
- Oppgi tidspunkt for data som kan endre seg.

### Spør først

- Opprette eller endre issues, prosjektitems, feltverdier, guider eller PR-er.
- Utvide analysen til repositories eller systemer utenfor bekreftet scope.

### Aldri

- Gjette prosjekt, feltsemantikk, teamgrense eller målperiode.
- Presentere trackeraktivitet som dokumentert bruker- eller samfunnseffekt.
- Endre ekstern tilstand uten vist utkast og eksplisitt godkjenning.
