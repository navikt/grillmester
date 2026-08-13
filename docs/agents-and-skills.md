# Agenter og skills

Grillmester kombinerer fire brukerinnganger med tre interne roller. Du velger
inngangen; agentteamet bruker interne roller og relevante skills etter behov.

## Offentlige agenter

Agentprofilene har en kuratert standardmodell, men faktisk modelloppløsning
avhenger av klient, lisens og NAVs enterprise-policy. Manglende modell eller
automatisk fallback skal registreres i klienttesten; ikke anta at navnet i
frontmatter beviser runtime-modellen.

### Grillmester 🔥

**Bruk når:** Oppgaven er viktig, uklar eller tverrgående, eller trenger
produkt-/arkitekturvalg før kode.

**Prøv:**

> Vi vurderer å endre denne flyten. Skill mellom fakta, antakelser og
> beslutninger, utforsk reelle alternativer og foreslå den minste trygge
> leveransen. Ikke implementer før jeg har godkjent retningen.

**Forventet leveranse:** Et forståelig beslutningsgrunnlag, eventuelt domenemodell
eller ADR, én komplett vertical slice, fersk verifikasjon og uavhengig review.

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

Full Figma-lesing og -skriving krever at klienten eksponerer en godkjent Figma
MCP med riktige scopes. Uten den skal Designer si hva som mangler og tilby en
ærlig fallback — aldri hevde at en Figma-write skjedde.

### Doctor Who 🕰️

**Bruk når:** Arbeidet handler om mål, prioritering, discovery, produktfag,
workshops, teamhelse eller NAV-spesifikk arkitektur.

**Prøv:**

> Vi diskuterer om dette initiativet skal prioriteres nå. Kartlegg hva vi vet,
> hvilke antakelser som driver valget, hvilke alternativer vi har og det minste
> eksperimentet som reduserer mest usikkerhet.

**Forventet leveranse:** Kildebevisst syntese, alternativer, anbefaling og et
konkret neste steg. Eksterne writes skal forhåndsvises og godkjennes.

**Ikke bruk når:** Målet primært er å endre kode. Bruk Barista eller
Grillmester og trekk inn relevante produkt-/NAV-skills der.

## Interne roller

| Rolle | Oppdrag | Viktig grense |
| --- | --- | --- |
| **Kokk** 👨‍🍳 | Implementerer én komplett, uavhengig testbar vertical slice fra en tydelig brief. | Utvider ikke scope og finner ikke på manglende beslutninger. |
| **Grill-inspektør** 🔎 | Leser hele task-diffen, akseptansekriteriene og fersk evidens; kan bruke read-only shellkommandoer som `git diff` for å verifisere. | Endrer ikke implementasjonen og løser ikke produktvalg. |
| **Researcher** | Besvarer ett avgrenset Wayfinder-spørsmål fra repo og autoritative kilder. | Ingen writes og ingen produkt-/arkitekturbeslutning. |

De interne rollene er `user-invocable: false`. Det hindrer at de presenteres som
ordinære startpunkt, men agentteamet kan delegere til dem med en komplett brief.

## Skillfamilier

Skills er oppgaveorienterte metoder. Copilot matcher naturlige forespørsler mot
beskrivelsen og laster innholdet progressivt. Du kan også velge en skill
eksplisitt, for eksempel `/grillmester-security-review`.

Fagpakken er ikke begrenset til Team eSyfo. NAV-spesialiseringene er skrevet
mot repositoryevidens og autoritative kilder, ikke mot én teams faste repo,
prosjekt eller cadence.

Tabellen grupperer innholdet etter brukerbehov, ikke etter intern mappe:

| Familie | Bruk ved | Representative skills |
| --- | --- | --- |
| **Avklaring og beslutninger** | Planen må grilles, domeneord avklares eller en beslutning dokumenteres. | Grilling, Grill with docs, Domain modeling, To spec, Architecture review, Prototype |
| **Større arbeid** | Oppgaven må brytes ned uten å miste den vertikale verdien. | Wayfinder, To issues, Issue management, Handoff |
| **Implementasjon og kvalitet** | Feilsøking, teststrategi, review eller sikkerhet/personvern. | Diagnosing bugs, TDD, Integration tests, E2E tests, Review, Security review |
| **Kodebase og levering** | Arkitekturforbedring, README, PR eller skillvedlikehold. | Improve codebase architecture, README update, Pull request, Create a skill |
| **Design og UU** | Aksel, universell utforming, designutforsking eller Figma-to-code. | Aksel design, Accessibility review, Design prototype, Figma workflow |
| **Produkt og tjeneste** | Mål, discovery, teamarbeid, workshop, klarspråk eller ansvarlig atferdsdesign. | OKR, Produktledelse, Team status, Workshop design, Klarspråk, Dulting |
| **NAV backend og plattform** | Kontrakter, identitet, runtime, data og operasjon i NAV/NAIS. | API design, Auth overview, Kafka topic, Kotlin/Ktor, Kotlin/Spring, Nais manifest, NAV troubleshoot, Observability, PostgreSQL review |
| **NAV produktcapabilities** | En NAV-spesifikk tjenestekomponent eller arbeidsmåte trengs. | NAV architecture review, Lumi Survey |

Lumi Survey er en ordinær NAV-capability. Som alle integrasjonsskills skal den
verifisere gjeldende pakke/API og repoets faktiske auth-/Nais-oppsett; den skal
ikke gjette detaljer fra minnet.

## Standardpakken og NAV-tillegget

`grillmester@grillmester` gir agentteamet og et kuratert skillsett for metode,
design, produktarbeid og levering. Det inkluderer NAV-nære emner som Aksel, UU
og NAV-arkitektur fordi de er direkte del av de offentlige agentenes oppdrag.
`grillmester-nav@grillmester` legger til backend-, plattform- og
integrasjonsfagkunnskap uten å installere agentene en gang til. Installer begge
for full dekning; NAV-pakken er ikke ment brukt uten standardpakken.

Noen arbeidsflyter ruter mellom flere skills. Standardpakken valideres som
selvstendig agentopplevelse. NAV-pakken valideres både strukturelt alene og
funksjonelt sammen med standardpakken; kryssreferanser skal gi en tydelig
fallback eller installasjonsbeskjed, ikke en død lenke.

## Finn riktig skill

Du trenger vanligvis ikke lære alle navnene. Beskriv resultatet du ønsker:

- «Diagnostiser hvorfor denne bare feiler i produksjon.»
- «Review auth- og personvernkonsekvensene før vi endrer accessPolicy.»
- «Bryt den godkjente specen i uavhengig nyttige issues.»
- «Gjør denne teksten kortere og tydeligere uten å endre betydningen.»

Bruk klientens skilloversikt hvis du vil kontrollere hva som er tilgjengelig.
Hvis en backend-, plattform- eller integrasjonsskill mangler, sjekk at
NAV-tillegget er installert. Hvis matchingen
velger feil metode, velg skillen eksplisitt og si hvorfor.

## Videre

- [Installer standard- eller NAV-pakken](installation.md)
- [Legg repoets stående sannhet på riktig sted](repository-context.md)
- [Forstå tools, sandbox og klientstøtte](trust-and-client-support.md)
