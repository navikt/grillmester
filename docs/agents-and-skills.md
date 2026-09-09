# Agenter og skills

Grillmester kombinerer fire brukerinnganger med tre interne roller. Du velger
inngangen; agentteamet bruker interne roller og relevante skills etter behov.

## Offentlige agenter

Copilot-profilene har en kuratert standardmodell, men faktisk modelloppløsning
avhenger av klient, lisens og Navs enterprise-policy. OpenCode-targetet utelater
modellpin og arver session-/providermodellen, også ved intern delegering.
Manglende modell, override eller automatisk fallback skal registreres i
klienttesten; ikke anta at frontmatter eller model picker beviser hva som kjørte.
Se [lokale modeller](local-models.md) for eksplisitt valg og capability-smoke.

### Grillmester 🔥

**Bruk når:** Oppgaven er viktig, uklar eller tverrgående, eller trenger
produkt-/arkitekturvalg før kode.

**Prøv:**

> Vi vurderer å endre denne flyten. Skill mellom fakta, antakelser og
> beslutninger, utforsk reelle alternativer og foreslå den minste trygge
> leveransen. Ikke implementer før jeg har godkjent retningen.

**Forventet leveranse:** Et forståelig beslutningsgrunnlag, eventuelt domenemodell
eller ADR, én komplett vertical slice, fersk verifikasjon og uavhengig review.

Grillmester undersøker fakta og utfordrer uklare mål, antakelser og valg fra
start. For én sammenhengende avklaring bruker den `grill-with-docs` når
begreper eller varige beslutninger skal dokumenteres. Når flere uløste
beslutninger avhenger av hverandre og trenger en delt oversikt på tvers av
økter, velger den `wayfinder`. Wayfinder organiserer beslutningene og bruker
grilling, dokumentert grilling, research eller prototyper inne i hvert
spørsmål. Størrelsen på den senere implementasjonen er ikke alene grunn til
å opprette et kart.

**Ikke bruk når:** Oppgaven er liten og ferdig spesifisert. Da er Barista
raskere og enklere.

### Barista ☕

**Bruk når:** Målet og akseptansekriteriene er tydelige, og oppgaven kan løses
som vanlig repoarbeid uten tung orkestrering.

**Prøv:**

> Legg til valideringen som er beskrevet i issue #123. Hold scope til denne
> flyten, følg repoets mønstre og kjør relevante tester.

**Forventet leveranse:** En liten, reviewbar diff med forklaring av hva som ble
endret og hvilke verifikasjoner som faktisk ble kjørt.

**Ikke bruk når:** Oppgaven skjuler et uløst produktvalg, bryter en offentlig
kontrakt eller krever en reverserings-/migreringsbeslutning.

### Designer 🎨

**Bruk når:** Du trenger designutforsking, brukerflyt, Aksel-komponentvalg,
Visual Companion eller en Figma-leveranse.

**Prøv:**

> Utforsk tre tydelig forskjellige måter å hjelpe brukeren videre etter denne
> feilen. Bruk Aksel-prinsipper, vis tradeoffs og anbefal én retning.

**Forventet leveranse:** Visuelle alternativer, begrunnet anbefaling og et
konsept, en Visual Companion eller Figma-klar/Figma-basert leveranse avhengig av
tilgjengelige verktøy.

**Ikke bruk når:** Du vil implementere produktkode. Godkjent design går videre
til Barista eller Grillmester.

Designer fungerer best med Aksel MCP og Figma MCP. Ved arbeid mot en kjørende
app anbefales også Playwright MCP. Se [MCP-oppsett](mcp-setup.md).

### Doctor Who 🕰️

**Bruk når:** Arbeidet handler om mål, prioritering, discovery, produktfag,
workshops, teamhelse eller Nav-spesifikk arkitektur.

**Prøv:**

> Vi diskuterer om dette initiativet skal prioriteres nå. Kartlegg hva vi vet,
> hvilke antakelser som driver valget, hvilke alternativer vi har og det minste
> eksperimentet som reduserer mest usikkerhet.

**Forventet leveranse:** Kildebevisst syntese, alternativer, anbefaling og et
konkret neste steg. Eksterne writes skal forhåndsvises og godkjennes.

**Ikke bruk når:** Målet primært er å endre kode. Bruk Barista eller
Grillmester og trekk inn relevante produkt-/Nav-skills der.

## Interne roller

| Rolle | Oppdrag | Viktig grense |
| --- | --- | --- |
| **Kokk** 👨‍🍳 | Implementerer én komplett, uavhengig testbar vertical slice fra en tydelig brief. | Utvider ikke scope og finner ikke på manglende beslutninger. |
| **Grill-inspektør** 🔎 | Leser hele task-diffen, akseptansekriteriene og fersk evidens; kan bruke read-only shellkommandoer som `git diff` for å verifisere. | Endrer ikke implementasjonen og løser ikke produktvalg. |
| **Researcher** | Besvarer ett avgrenset faktaspørsmål fra repo og autoritative kilder, med valgfri kobling til et Wayfinder-kart. | Ingen writes og ingen produkt-/arkitekturbeslutning. |

I Copilot er de interne rollene `user-invocable: false`. I OpenCode er de
`mode: subagent` og `hidden: true`. Begge deler hindrer at de presenteres som
ordinære startpunkt, mens agentteamet fortsatt kan delegere med en komplett
brief gjennom klientens native mekanisme.

## Skillfamilier

Skills er oppgaveorienterte metoder. Copilot matcher naturlige forespørsler mot
beskrivelsen og laster innholdet progressivt. Du kan også velge en skill
eksplisitt, for eksempel `/security-review`.

Skillsettet er ikke begrenset til Team eSyfo. Nav-spesialiseringene er skrevet
mot repoevidens og autoritative kilder, ikke mot ett teams faste repo, prosjekt
eller arbeidsrytme.

Tabellen grupperer innholdet etter brukerbehov, ikke etter intern mappe:

| Familie | Bruk ved | Representative skills |
| --- | --- | --- |
| **Avklaring og beslutninger** | Planen må grilles, domeneord avklares eller en beslutning dokumenteres. | Grilling, Grill with docs, Domain modeling, To spec, Architecture review, Prototype |
| **Beslutningskart og oppdeling** | Avhengige, uavklarte beslutninger trenger et varig kart, eller avklart arbeid skal deles i selvstendige leveranser. | Wayfinder, To issues, Issue management |
| **Overlevering** | Brukeren ber om å flytte pågående arbeid til en annen sesjon, klient eller kollega. | Handoff (manuell) |
| **Implementasjon og kvalitet** | Feilsøking, teststrategi, review eller sikkerhet/personvern. | Diagnosing bugs, TDD, Integration tests, E2E tests, Review, Guided review, Security review |
| **Kodebase og levering** | Arkitekturforbedring, README, PR eller skillvedlikehold. | Improve codebase architecture, README update, Pull request, Create a skill |
| **Design og UU** | Aksel, universell utforming, designutforsking eller Figma-to-code. | Aksel design, Accessibility review, Design prototype, Figma workflow |
| **Produkt og tjeneste** | Mål, discovery, teamarbeid, workshop, klarspråk eller ansvarlig atferdsdesign. | OKR, Produktledelse, Team status, Workshop design, Klarspråk, Dulting |
| **Nav backend og plattform** | Kontrakter, identitet, runtime, data og operasjon i Nav/Nais. | API design, Auth overview, Kafka topic, Kotlin/Ktor, Nais manifest, Nav troubleshoot, Observability, PostgreSQL review |
| **Nav-produktcapabilities** | En Nav-spesifikk tjenestekomponent eller arbeidsmåte trengs. | Lumi Survey |

Lumi Survey er en ordinær Nav-capability. Som alle integrasjonsskills skal den
verifisere gjeldende pakke/API og repoets faktiske auth-/Nais-oppsett; den skal
ikke gjette detaljer fra minnet.

## Én komplett plugin

`grillmester@grillmester` gir hele agentteamet og alle 43 skills i én
installasjon. Det inkluderer metode, design, produktarbeid, levering og
Nav-nære emner som Aksel, UU, arkitektur, backend og plattform. Én plugin gjør
agentenes ruting og kryssreferanser forutsigbare uten at brukeren må kjenne en
pakkeinndeling.

De 43 skillsene har korte, kanoniske ID-er som `grill-with-docs`,
`design-prototype` og `review`. Nav-pilot eier valg og distribusjon av
agentpakken; pakkevalg er ikke et eget runtime-navnerom. De reviewede
agent-ID-ene er bevart. Klientens aktive oversikt avgjør hvilke skills som
faktisk er lastet og hvilken ID det native skillverktøyet godtar.

Noen fagområder overlapper med `navikt/copilot`, lokale tilpasninger og eldre
Hovmester-oppsett. Repo- og brukerkilder med samme ID kan skygge for pakken,
og forskjellige ID-er kan fortsatt beskrive samme metode. Bruk `/doctor`
når et team vil kartlegge aktive kilder, kollisjoner og gamle referanser før
opprydding. Kortere navn forutsetter at denne migreringen gjennomføres;
pakkeinstallasjon alene fjerner ikke eldre repo- eller brukerkopier.

## Finn riktig skill

Du trenger vanligvis ikke lære alle navnene. Beskriv resultatet du ønsker:

- «Diagnostiser hvorfor denne bare feiler i produksjon.»
- «Review auth- og personvernkonsekvensene før vi endrer accessPolicy.»
- «Bryt den godkjente specen i uavhengig nyttige issues.»
- «Gjør denne teksten kortere og tydeligere uten å endre betydningen.»

Bruk klientens skilloversikt hvis du vil kontrollere hva som er tilgjengelig.
Agentene skal laste den eksakte ID-en oversikten tilbyr med klientens native
skillverktøy. De skal ikke gjette prefiks, alias eller filsti, eller kjøre
slash-navn som shellkommandoer.

Hvis en dokumentert skill mangler, kontroller aktiv pakkeversjon,
full/fokusert profil og synlig kilde. En skill kan være utelatt fra en
fokusert profil, deaktivert eller skygget av en eldre repo-/brukerkopi.
Kjør `/doctor` hvis den finnes i oversikten. Feilrapporten bør oppgi
forespurt ID, tilgjengelig katalogoppføring, kilde/profil når klienten viser
dem, og den faktiske feilen; ukjente detaljer skal merkes som ukjente.

Disse grensene gjør overlappende metoder enklere å velge:

| Behov | Metode | Avgrensning |
| --- | --- | --- |
| Avklare ett spørsmål mot dokumenterte begreper og beslutninger | `grill-with-docs` | Dokumenterer bare avklarte begreper og kvalifiserende beslutninger. |
| Holde flere avhengige, uløste beslutninger navigerbare over flere økter | `wayfinder` | Bruker grilling og andre metoder per spørsmål; kartet avsluttes når veien er klar. |
| Finne hvorfor eksisterende moduler er vanskelige å endre eller teste | `improve-codebase-architecture` | Finner refaktoreringsmuligheter; `architecture-review` vurderer et konkret forslag. |
| Vurdere tjenester, systemgrenser eller kostbare arkitekturvalg | `architecture-review` | Gir funn og beslutningskandidater; `domain-modeling` eier ADR-vurderingen. |
| Prøve datamodell, tilstandsmaskin eller feiloppførsel | `prototype` | Kjørbart eksperiment med avgrenset spørsmål. |
| Se layout, hierarki eller en brukerflyt | `design-prototype` | Visuell skisse; `figma-workflow` bruker et eksisterende design som grunnlag. |
| Bevise en ekte adapterkontrakt eller en hel applikasjonsflyt | `integration-tests` / `e2e-tests` | Førstnevnte holder grensen smal; sistnevnte starter hele appen. `tdd` styrer arbeidsrekkefølgen. |
| Kontrollere en ferdig diff eller forstå den sammen | `review` / `guided-review` | Egenkontroll versus interaktiv gjennomgang; `security-review` brukes ved relevante sikkerhets- og personvernspørsmål. |

Skillvalg krever ikke at brukeren kan navnene. En forespørsel om en spec eller
oppdeling i tickets kan uttrykkes i vanlig språk. Det oppretter ingen
automatisk kjede fra grilling til spec og videre til issues. Fullmakt til
konkrete eksterne handlinger følger brukerens oppdrag og gjeldende grenser;
et skillskifte er ikke i seg selv en ny fullmakt.

## Videre

- [Installer Grillmester](installation.md)
- [Bruk Grillmester i OpenCode](opencode.md)
- [Velg og test en lokal modell](local-models.md)
- [Legg repoets stående sannhet på riktig sted](repository-context.md)
- [Forstå tools, tillit og klientstøtte](trust-and-client-support.md)
