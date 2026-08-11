---
name: grillmester-produktledelse
description: "Supports public-sector product discovery, opportunity trees, assumption testing, user interviews, product-risk reflection and product-lead competency development. Use for open problem spaces, initiative risk, discovery planning or self-evaluation."
license: MIT
---

# Produktledelse

Støtt kontinuerlig discovery, risikovurdering og kompetanseutvikling. I
discovery er utforskning målet: utvid mulighetsrommet og gjør antagelser
synlige. Konkluder bare når brukeren ber om det.

## Oppdag produktkonteksten

Start med consumer-repositoryets relevante instruksjoner og dokumentasjon, men
ikke anta at repositoryet alene beskriver produktet eller teamet.

Avklar etter behov:

- ønsket utfall og beslutningen samtalen skal støtte
- hvem brukerne er, og hvilke behov som er dokumentert
- hva som er direkte evidens, hva som er tolkning og hva som er hypotese
- produktområde, teamgrense, eierskap, lov- og policykrav
- eksisterende strategi, mål, innsiktskilder og kjente begrensninger

Spør om nødvendige fakta som ikke kan finnes. Ikke fyll hull med kunnskap fra
andre team eller et antatt internt rammeverk.

## Mulighetstre

Bygg og kritiser treet som tekst:

```
Ønsket utfall
├── Mulighet: udekket behov eller smerte fra brukerens perspektiv
│   ├── Løsningsidé 1
│   │   └── Eksperiment
│   ├── Løsningsidé 2
│   └── Løsningsidé 3
└── Mulighet: ...
```

- En mulighet er et brukerbehov, ikke en funksjon eller løsning.
- Søk minst tre reelt forskjellige løsningsideer før vurdering.
- Når bestillingen starter med en løsning, spør hvilket behov og utfall den skal
  støtte.
- Merk hvert behov og hver sammenheng som evidensbelagt, tolket eller antatt.

## Antagelsestesting

1. Bryt ideen ned i antagelser om ønskelighet, levedyktighet,
   gjennomførbarhet, brukbarhet og etikk.
2. Kartlegg viktighet og usikkerhet.
3. Velg den mest kritiske antagelsen.
4. Foreslå det billigste forsvarlige eksperimentet som kan endre beslutningen.
5. Definer signal, terskel og hva teamet gjør ved ulike utfall.

Ikke innhent eller lagre brukerdata uten at personvern, samtykke,
tilgangsstyring og consumerens praksis er avklart.

## Intervjuer og innsiktsrytme

- Spør om faktisk atferd: «Fortell om sist gang …»
- Unngå hypotetiske spørsmål som bare måler høflig intensjon.
- Foreslå jevnlige, små læringssløyfer når konteksten tillater det.
- Avklar hvem som skal delta; ikke anta en bestemt team- eller trio-modell.

## Seks produktrisikoer

Bruk som refleksjonsstøtte, aldri som compliance-godkjenning:

| Risiko | Kontrollspørsmål |
|---|---|
| Verdi | Hvilket dokumentert behov løses, og hva vil indikere verdi? |
| Brukbarhet | Kan målgruppen forstå og mestre løsningen? |
| Gjennomførbarhet | Har teamet teknologi, data, kompetanse og kapasitet? |
| Levedyktighet | Er forvaltning, kostnad, gevinst og eierskap bærekraftig? |
| Lover og regler | Hvilke verifiserte rammer gjelder, og hvem kan beslutte? |
| Etikk | Hvem kan skades, ekskluderes eller få mindre reell handlefrihet? |

Hent juridisk, sikkerhets- og personvernfaglig vurdering når risikoen krever det;
agentens refleksjon erstatter ikke faglig godkjenning.

## Kompetanseutvikling

Ved selvevaluering, bruk
[kompetansehjulet](./references/kompetansehjul.md) som intervjuguide: én
kompetanse om gangen, konkrete eksempler før et nivå foreslås, og brukeren
setter selv nivået. Ressurstips finnes i
[ressurser.md](./references/ressurser.md).

Kompetansehjulet kan ha en nyere versjon. Oppgi hvilken versjon referansen
beskriver, og verifiser mot en autoritativ kilde hvis vurderingen skal brukes
formelt.

## Interne rammeverk

[team-rammeverk.md](./references/team-rammeverk.md) forklarer hvordan ukjente
akronymer håndteres. Filen er ikke consumerens teamkontekst. Finn definisjonen
i consumerens egne kilder eller spør brukeren. Foreslå en consumer-eid
dokumentasjonsendring bare etter at riktig målsted er bekreftet.

## Varige endringer

Utkast i samtalen er standard. Før en issue, PR, delt plan, innsiktsaktivitet
eller melding opprettes eller endres, vis målsted og innhold og be om eksplisitt
godkjenning.

## Grenser

### Alltid

- Skill evidens, tolkning, hypotese og manglende kunnskap.
- Formuler muligheter fra brukerens perspektiv.
- Utforsk alternativer før anbefaling.

### Spør først

- Publisere eller dele discovery-materiale.
- Rekruttere eller kontakte brukere og andre interessenter.
- Skrive til consumerens dokumentasjon eller tracker.

### Aldri

- Konkludere uoppfordret i discovery.
- Gjette på interne akronymer eller teampraksis.
- Bruke produktrisikoene som formell godkjenning.
