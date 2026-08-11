---
name: grillmester-nav-architecture-review
description: "Reviews consequential Nav architecture choices and drafts ADRs across system boundaries, ownership, data flow, Nais, authentication, security and privacy. Use for new services, integrations, storage, event contracts, platform changes or deviations from established patterns."
license: MIT
---

# Nav Architecture Review

Gjør en Nav-spesifikk arkitekturgjennomgang fra tre perspektiver: arkitektur,
sikkerhet/personvern og plattform. En ADR er et mulig resultat, ikke et krav for
alle tekniske valg.

## Før gjennomgangen

Oppdag konteksten i consumer-repositoryet før du anbefaler noe:

1. Les relevante repository-instruksjoner, eksisterende ADR-er, manifest,
   kontrakter og arkitekturdokumentasjon.
2. Identifiser beslutningen, ønsket utfall, eier, berørte systemer og team,
   dataflyt, datakategorier, nåværende stack og driftsmiljø.
3. Finn repositoryets egen ADR-konvensjon: språk, katalog, nummerering, status
   og mal. Ikke anta at en bestemt katalog eller statusmodell brukes.
4. Skill eksplisitt mellom verifiserte repositoryfakta, eksterne føringer,
   tolkninger og manglende kontekst. Spør om nødvendige fakta som ikke kan
   finnes.

For regler eller plattformegenskaper som kan ha endret seg, bruk oppdatert,
autoritativ dokumentasjon før du gir en konsekvensfull anbefaling. Presenter
ikke denne skillens eksempler som gjeldende policy uten verifisering.

## Når en tyngre review er relevant

- Ny tjeneste, integrasjon, lagring, eventkontrakt eller systemgrense.
- Endret autentisering, autorisering eller access policy.
- Ny eller vesentlig endret behandling av personopplysninger.
- Plattformmigrering, ny teknologi eller avvik fra etablerte mønstre.
- Endring som påvirker andre teams kontrakter, drift eller eierskap.

Et lokalt bibliotekvalg eller en intern refaktorering trenger vanligvis ikke en
formell ADR med mindre consumer-repositoryet krever det.

## Tre perspektiver

Bruk spørsmålene i
[perspektiv-sjekklister.md](./references/perspektiv-sjekklister.md) selektivt.
Rapporter per perspektiv:

- relevante fakta og kilde
- risiko eller bekymring
- anbefaling og gjenværende usikkerhet

Ved endring av eksisterende system, ta også med bakoverkompatibilitet,
utrulling, observability, rollback, exit criteria og dekommisjonering.

## Alternativer og råd

Dokumenter minst to reelle alternativer og konsekvensen av å fortsette som i
dag. Sammenlign dem mot eksplisitte beslutningskriterier. Identifiser hvem som
eier beslutningen og hvem som bør gi råd; ikke presenter rådgivning som en
sentral godkjenning.

Ikke kontakt andre team eller del et utkast uten brukerens eksplisitte
godkjenning. Vis mottaker, kanal og utkast først.

## ADR-utkast

Bruk consumer-repositoryets format når det finnes. Ellers kan
[adr-template.md](./references/adr-template.md) tilbys som et tilpassbart
utgangspunkt etter at språk, plassering og statusmodell er avklart.

Hold én beslutning per ADR. Ikke skriv filen, åpne en PR eller endre status uten
godkjenning etter at målfil og fullstendig utkast er vist.

## Relaterte skills

- grillmester-nais-manifest for manifeststruktur og Nais-ressurser
- grillmester-auth-overview for aktuelle autentiseringsmønstre
- grillmester-security-review for dypere sikkerhetsgjennomgang
- grillmester-observability-setup for målinger, logger, tracing og varsling
- grillmester-nav-troubleshoot for driftsdiagnose

## Grenser

### Alltid

- Vurder arkitektur, sikkerhet/personvern og plattform.
- Vis alternativer, beslutningskriterier og konsekvenser.
- Verifiser relevante, tidsfølsomme føringer mot autoritative kilder.
- Merk uavklarte eiere, datakategorier og tverrteam-avhengigheter.

### Spør først

- Skrive eller publisere en ADR.
- Kontakte berørte team eller dele beslutningsmateriale.
- Foreslå en beslutning som avviker fra verifiserte standardmønstre.

### Aldri

- Fatte beslutningen på vegne av teamet.
- Bruke sjekklisten som compliance-, personvern- eller sikkerhetsgodkjenning.
- Dokumentere personopplysninger, secrets eller andre beskyttede detaljer i
  ADR-en.
