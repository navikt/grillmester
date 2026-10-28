# Agenter og skills

Grillmester kombinerer fire brukerinnganger med fire interne roller. Du velger
inngangen; agentteamet bruker interne roller og relevante skills etter behov.
Start gjerne med Grillmester for utvikling og Designer for visuell utforsking.
Barista gir et eksplisitt soloalternativ; Doctor Who retter seg mot produktarbeid.

## Offentlige agenter

Copilot-profilene har en kuratert standardmodell, men faktisk modelloppløsning
avhenger av klient, lisens og Navs enterprise-policy. OpenCode-targetet utelater
modellpin og arver session-/providermodellen, også ved intern delegering.
Manglende modell, override eller automatisk fallback skal registreres i
klienttesten; ikke anta at frontmatter eller model picker beviser hva som kjørte.
Se [lokale modeller](local-models.md) for eksplisitt valg og capability-smoke.

### Grillmester 🔥

**Bruk når:** Du vil få en utviklingsoppgave undersøkt, gjennomført og verifisert,
med avklaring og arbeidsdeling tilpasset oppgaven. Også små, presise endringer
kan starte her.

**Prøv:**

> Rett valideringen som er beskrevet i issue #123. Undersøk repoets mønstre,
> gjennomfør den avklarte endringen og kjør relevante tester. Spør bare hvis
> et vesentlig valg fortsatt står åpent.

**Forventet leveranse:** En avgrenset endring med fersk verifikasjon og selvreview.
Uavhengig review følger oppgavens risiko og repoets regler; for R0–R2 er den
valgfri. Beslutningsgrunnlag, domenemodell eller ADR inngår når arbeidet trenger
det og skrivingen er innenfor oppdraget.

Grillmester sjekker fakta, ønsket resultat og en relevant feilcase først. Når
retningen er avklart, fortsetter den med plan etter behov, implementering og
verifikasjon uten et nytt intervju. Uklare mål og materielle valg undersøkes
før arbeidet som avhenger av dem. For én sammenhengende avklaring mot repoets
begreper og beslutninger brukes `grill-with-docs`; domenemetoden lastes når
begreper endres eller en varig beslutning trenger vurdering. Når flere uløste
beslutninger avhenger av hverandre og trenger en delt oversikt på tvers av
økter, velger den `wayfinder`. Wayfinder organiserer beslutningene og bruker
grilling, dokumentert grilling, research eller prototyper inne i hvert
spørsmål. Størrelsen på den senere implementasjonen er ikke alene grunn til
å opprette et kart.

For R0–R2 gjennomfører Grillmester avklart arbeid selv eller bruker Kokk når en
avgrenset implementeringsoppgave har konkret nytte av en separat utfører.
Mange filer eller lang testtid utløser ikke delegering alene. R3/R4 går til Kokk,
slik at koden og den uavhengige reviewen kommer fra ulike forfattere. Det er én
skriver per leveransedel; review skjer på en stabil diff. Grillmester sier
hvorfor den velger utfører. Du kan overstyre valget; for R3/R4 forklares først
konsekvensen for skillet mellom implementering og review.

Dette er en anbefalt arbeidsflyt, ikke et løfte om kortere svartid eller lavere
modellkostnad. Barista, modellvalg og lagrede standardvalg beholdes.

### Barista ☕

**Bruk når:** Målet og akseptansekriteriene er tydelige, og du ønsker at samme
rolle undersøker, implementerer og verifiserer solo. Størrelse og filantall
alene utløser ikke rollebytte.

**Prøv:**

> Legg til valideringen som er beskrevet i issue #123. Hold scope til denne
> flyten, følg repoets mønstre og kjør relevante tester.

**Forventet leveranse:** En avgrenset, reviewbar diff med forklaring av hva som ble
endret og hvilke verifikasjoner som faktisk ble kjørt. Uavhengig review kan
velges eksplisitt; kodeimplementeringen delegeres ikke til Kokk.

**Ikke bruk når:** Oppgaven skjuler et uløst produktvalg, bryter en offentlig
kontrakt eller krever en reverserings-/migreringsbeslutning.

**Forskjell fra Grillmester:** Barista implementerer selv og kan bare tilkalle
Grill-inspektør for uavhengig review. Den bruker en annen standardmodell, har
kortere instruksjoner og er med i de fokuserte nyttelastene for lokale
modeller. Å fjerne rollen er en egen beslutning (ADR 0024).

### Designer 🎨

**Bruk når:** Du trenger designutforsking, brukerflyt, Aksel-komponentvalg eller
videre iterasjon av en skisse, et lagret designrom eller et Figma-design.

**Prøv:**

> Utforsk tre tydelig forskjellige måter å hjelpe brukeren videre etter denne
> feilen. Bruk Aksel-prinsipper, vis tradeoffs og anbefal én retning.

**Forventet leveranse:** En synlig skisse eller forbedring i avtalt arbeidsflate,
med relevante tilstander og kontroll av det rendrede resultatet. Visuelle
alternativer og panel brukes når de belyser et faktisk designvalg. En liten
justering trenger verken nye varianter eller nytt intervju.

I den verifiserte Copilot app-flaten åpner Designverksted både app og skisse i
canvaset ved siden av samtalen. Sendte innspill går til samme Designer-samtale,
og svaret kommer tilbake i verkstedet. «I kø» bekrefter mottak, ikke at arbeidet
har startet. Appinnspill er midlertidige som standard; avtalt prosjektlagring
bevarer innspill og svar, uten appkode eller apphistorikk. Lagrede skisser har
også editor og versjoner. Et lukket appverksted krever en ny instans; lagret
arbeid kan da åpnes igjen uten ny innsending. Se
[støtteomfang og kjente grenser](testing/designverksted-release-readiness.md).
Uten denne canvasflaten brukes en separat tilgjengelig nettleser for appen og
samtalen for innspill, eller den portable flyten for midlertidige HTML-skisser.
Nativeverkstedets private adresse skal ikke brukes i en ekstern nettleser.
Figma kan være arbeidsflaten fra start eller avtalt sluttleveranse etter en
skisse. Be Designer i samtalen bygge videre i ønsket Figma-fil; med tilgjengelig
skrivetilgang brukes redigerbare Aksel-komponenter og valgt skisseversjon.
Uten skrivetilgang leveres et avtalt utkast, ikke en påstått Figma-fil.
Overleveringen er ikke automatisk synkronisering mellom Figma og skissen.
I et appverksted ligger «Appen nå» og «Forslag» i samme flate. «Vis forslag»
åpner den interaktive skissen der du allerede arbeider. Innspill på forslaget
går til samme samtale og brukes til neste skisseversjon. Skissen har syntetiske
tilstander; den beviser ikke appens runtime eller validering. Produktkode endres
bare som separat bestilt implementering.

Bestillingen styrer starten: «Kjør demoen» viser den faktiske appen, «drodle»
kan starte i samtalen, og en brukerhistorie gir et avgrenset designforslag med
relevante tilstander. Designer undersøker eksisterende sider når det trengs for
oppgaven, uten å kreve at alle begynner med samme valgmeny.

En konkret bestilling om skisser eller to retninger kan starte direkte, også
i et apprepo. Mål, målgruppe og antakelser avklares når svaret trengs for et
faktisk designvalg; et nytt konsept krever ikke alltid et intervju før første
utkast. Designer er også riktig inngang for utviklere når leveransen er et
konsept eller en Figma-skisse.

Designer kan sette sammen et panel av spesialistperspektiver, som UX-ekspert,
innholdsdesigner, UU-ekspert eller syntetiske personas, og syntetisere dem.
Personas er hypoteser, ikke brukerinnsikt. Designer kan også hjelpe med oppsett
av verktøy og implementere et valgt design når du ber om det.

**Ikke bruk når:** Oppgaven er ren kode uten designspørsmål. Da passer Barista
eller Grillmester bedre.

Designer bruker tilgjengelige og tillatte verktøy til visuell kontroll av
den avtalte arbeidsflaten. Et native verksted krever ikke en ekstra kontrollfane.
Hvis verktøyene ikke kan inspisere canvaset, skal det sies konkret; kodekontroll
og HTTP-svar beviser ikke gjengivelsen. Designer skal fortsatt levere det
avtalte forslaget og beskrive hva som gjenstår å prøve. Aksel- og
Figma-integrasjoner brukes etter oppgaven og tilgjengelige kapabiliteter.
Se [MCP-oppsett](mcp-setup.md).

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
| **Kokk** 👨‍🍳 | Implementerer én komplett, uavhengig testbar vertical slice fra en tydelig brief når Grillmester delegerer. | Utvider ikke scope og finner ikke på manglende beslutninger. |
| **Grill-inspektør** 🔎 | Leser hele task-diffen, akseptansekriteriene og fersk evidens; kan bruke read-only shellkommandoer som `git diff` for å verifisere. | Endrer ikke implementasjonen og løser ikke produktvalg. |
| **Researcher** | Besvarer ett avgrenset faktaspørsmål fra repo og autoritative kilder, med valgfri kobling til et Wayfinder-kart. | Ingen writes og ingen produkt-/arkitekturbeslutning. |
| **Perspektiv** 🔭 | Tar ett fagperspektiv eller én syntetisk persona som Designer gir i briefen, og vurderer design, flyt eller tekst fra det ståstedet. Designer kan kjøre flere parallelt. | Ingen writes og ingen designbeslutning; personas presenteres aldri som brukerinnsikt. |

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

`grillmester@grillmester` gir hele agentteamet og alle 44 skills i én
installasjon. Det inkluderer metode, design, produktarbeid, levering og
Nav-nære emner som Aksel, UU, arkitektur, backend og plattform. Én plugin gjør
agentenes ruting og kryssreferanser forutsigbare uten at brukeren må kjenne en
pakkeinndeling.

De 44 skillsene har korte, kanoniske ID-er som `grill-with-docs`,
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
| Sette opp lokal sandbox i GitHub Copilot desktop på macOS | `/app-sandbox-setup` | Kun manuelt i fullprofilen; plan først, eksplisitt bekreftelse før DB-write og verify i ny sandboxet økt. Klikkguide og bekreftet rollback; varsler om credentials, loopback og Docker. |
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
