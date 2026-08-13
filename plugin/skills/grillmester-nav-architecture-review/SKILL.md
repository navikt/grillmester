---
name: grillmester-nav-architecture-review
description: Review architecture choices that specifically depend on NAV or NAIS platform, integration, identity, deployment, security, privacy, operability, or team-governance constraints. Use for NAV services, cross-team contracts, NAIS resources and migrations, NAV authentication or accessPolicy changes, and NAV data flows; use grillmester-architecture-review for platform-independent review.
license: MIT
---

# Review NAV architecture

Gjør en NAV-spesifikk arkitekturgjennomgang av en foreslått endring. Denne
skillen er spesialiseringen for beslutninger der NAV- eller NAIS-konteksten kan
endre anbefalingen. Bruk `/grillmester-architecture-review` når vurderingen er
plattformuavhengig.

Reviewen gir funn, råd og beslutningskandidater; den forfatter ikke
beslutningen. `/grillmester-domain-modeling` eier både ADR-kvalifiseringen og et
eventuelt ADR-utkast eller en varig endring, og brukes først etter at brukeren
eksplisitt velger den ruten.

## Avgrens NAV-overflaten

Oppdag consumer-repositoryets faktiske kontekst før du anbefaler noe:

1. Les relevante repository-instruksjoner, kode, eksisterende beslutninger,
   manifester, kontrakter og arkitekturdokumentasjon.
2. Identifiser ønsket utfall, beslutningseier, berørte apper og team,
   produsenter og konsumenter, dataflyt, datakategorier, caller-identiteter og
   driftsmiljø.
3. Finn hvilke NAV-flater som faktisk berøres: NAIS-ressurser, nettverk og
   deploy, identitet og tokens, tilgangspolicy, data eller events,
   observability, plattformtjenester eller tverrteam-governance.
4. Skill mellom verifiserte repositoryfakta, gjeldende autoritative føringer,
   tolkninger og manglende kontekst. Rapporter manglende fakta som åpne spørsmål.

For plattformegenskaper, identitetsmekanismer, sikkerhetskrav eller andre
tidsfølsomme føringer, bruk oppdatert autoritativ dokumentasjon. Eksemplene i
denne skillen er spor til hva som må verifiseres, ikke gjeldende policy i seg
selv.

## Når spesialiseringen er relevant

- Ny eller vesentlig endret NAV-tjeneste, systemgrense eller tverrteam-kontrakt.
- NAIS-ressurs, plattformintegrasjon, data- eller eventflyt, eller migrering.
- Endret NAV-autentisering, tokenflyt, autorisering eller `accessPolicy`.
- Ny eller vesentlig endret behandling av personopplysninger i NAV-kontekst.
- Plattformavvik eller operasjonell beslutning som påvirker NAV-governance,
  andre team eller produksjonsberedskap.

Et internt refaktoreringsvalg eller en portabel teknologiavveining hører
vanligvis hjemme i `/grillmester-architecture-review`. Bruk denne
spesialiseringen bare for NAV-delen dersom en større review inneholder begge.

## Tre NAV-perspektiver

Last [perspektiv-sjekklistene](./references/perspektiv-sjekklister.md), og bruk
bare grenene som passer den verifiserte konteksten:

1. **Arkitektur og governance** — teamautonomi, kontrakteierskap,
   plattformkapabiliteter, avvik og behov for råd fra berørte team.
2. **Sikkerhet og personvern** — datakategorier, formål og retention,
   caller-identitet, tokenflyt, autorisering, `accessPolicy`, PII, audit og
   behov for spesialistvurdering.
3. **NAIS-plattform og drift** — deklarerte ressurser, nettverk, kapasitet,
   observability, levering, failure handling, migrering, rollback og
   dekommisjonering.

For hvert relevant perspektiv, rapporter fakta og kilde, risiko eller
bekymring, anbefaling og gjenværende usikkerhet. Bruk
`/grillmester-security-review` når en konkret design, konfigurasjon eller
trusselgrense krever dypere sikkerhets- eller personverngjennomgang.

## Alternativer og råd

Sammenlign reelle alternativer mot eksplisitte beslutningskriterier når det
finnes et valg. Ta med nåtilstanden bare når det å beholde den er et troverdig
alternativ. Ikke konstruer et bestemt antall alternativer eller tving inn
"gjøre ingenting".

Identifiser hvem som eier beslutningen, hvem som eier eller bruker kontraktene,
og hvilke råd som trengs. Architecture Advice informerer teamets beslutning;
det er ikke en sentral godkjenning. Ikke hevde at noen er rådspurt uten evidens.
Ikke kontakt andre team eller del materiale uten brukerens eksplisitte
godkjenning; vis mottaker, kanal og utkast først.

## Returner review, ikke ADR

Returner:

- **Scope og evidens** — inkludert hvilke NAV-flater som er verifisert;
- **Funn per relevant NAV-perspektiv** — prioritert etter konsekvens, med
  evidens, påvirkning og anbefaling;
- **Alternativer og trade-offs** — når det finnes et reelt valg;
- **Åpne spørsmål** — med hvem eller hvilken autoritativ kilde som kan svare;
- **Samlet anbefaling** — med usikkerhet, residual risiko og nødvendig råd;
- **Beslutningskandidater** — vanskelige å reversere valg der NAV-konteksten
  forklarer en ellers overraskende trade-off.

Ikke avgjør ADR-kvalifisering, lag ADR-utkast, rediger beslutningsdokumentasjon
eller endre status. Forklar hvorfor en kandidat kan fortjene varig
dokumentasjon, spør brukeren om den skal rutes videre, og bruk
`/grillmester-domain-modeling` først etter et eksplisitt valg.

## Relaterte skills

- `/grillmester-architecture-review` for plattformuavhengige arkitekturspørsmål
- `/grillmester-security-review` for dypere sikkerhets- og personvernreview

Når den valgfrie NAV-fagpakken fra samme marketplace er installert, kan reviewen også
anbefale `grillmester-nais-manifest` for konkret manifestarbeid,
`grillmester-auth-overview` for identitetsmekanismer,
`grillmester-observability-setup` for telemetri og varsling, eller
`grillmester-nav-troubleshoot` for driftsdiagnose. De er fordypninger, ikke
forutsetninger; fullfør denne reviewen og rapporter manglende evidens dersom
add-on-pakken ikke er installert.

## Grenser

### Alltid

- Vurder bare de NAV-perspektivene som kan endre anbefalingen.
- Vis evidens, trade-offs, beslutningseier og gjenværende usikkerhet.
- Verifiser tidsfølsomme føringer mot autoritative kilder.
- Merk uavklarte eiere, datakategorier og tverrteam-avhengigheter.

### Spør først

- Kontakte berørte team eller dele review- eller beslutningsmateriale.
- Gjøre eksterne eller varige endringer basert på anbefalingen.

### Aldri

- Fatte eller dokumentere beslutningen på vegne av teamet.
- Opprette, skrive eller endre en ADR i denne skillen.
- Bruke reviewen som compliance-, personvern- eller sikkerhetsgodkjenning.
- Dokumentere personopplysninger, secrets eller andre beskyttede detaljer i
  review- eller beslutningsmateriale.
