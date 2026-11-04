# Agenter og skills

Grillmester kombinerer tre brukerinnganger med tre interne roller. Du velger
inngangen; hovedagenten bruker relevante skills og interne roller etter behov.
Start gjerne med Grillmester for utvikling og Designer for visuell utforsking.
Doctor Who retter seg mot produktarbeid.

## Offentlige agenter

Copilot-profilene har en kuratert standardmodell, men faktisk modelloppløsning
avhenger av klient, lisens og Navs enterprise-policy. OpenCode-targetet utelater
modellpin og arver session-/providermodellen, også ved intern delegering.
Manglende modell, override eller automatisk fallback skal registreres i
klienttesten; ikke anta at frontmatter eller model picker beviser hva som kjørte.
Se [lokale modeller](local-models.md) for eksplisitt valg og capability-smoke.

### Grillmester 🔥

**Bruk når:** Du vil få en utviklingsoppgave undersøkt, gjennomført og verifisert,
med avklaring tilpasset oppgaven og review tilpasset risikoen. Også små, presise endringer
kan starte her.

**Prøv:**

> Rett valideringen som er beskrevet i issue #123. Undersøk repoets mønstre,
> gjennomfør den avklarte endringen og kjør relevante tester. Spør bare hvis
> et vesentlig valg fortsatt står åpent.

**Forventet leveranse:** En avgrenset endring med fersk verifikasjon og selvreview.
Uavhengig review er ditt valg, fordi den bruker modellbudsjett, med mindre repoet
krever den. Fra R2 spør Grillmester om du vil ha den. Beslutningsgrunnlag, ordliste eller ADR foreslås i én linje når
arbeidet trenger det, og skrives når du ber om det, sier ja eller repoets
policy krever det.

Grillmester sjekker fakta, ønsket resultat og en relevant feilcase først. Når
retningen er avklart, fortsetter den med plan etter behov, implementering og
verifikasjon uten et nytt intervju. Uklare mål og materielle valg undersøkes
før arbeidet som avhenger av dem. Grillmester griller i runder: alle spørsmål
som kan stilles nå, nummerert og med en anbefaling til hvert, slik at «ja»
godtar anbefalingene. Begreper og beslutninger som bør skrives ned, foreslås i
én linje og skrives først når du sier ja. Med `/grill-with-docs` ber du om at
de skrives underveis. Når flere uløste beslutninger avhenger av hverandre og
trenger en delt oversikt på tvers av økter, velger den `wayfinder`. Wayfinder
organiserer beslutningene og bruker grilling, research eller prototyper inne i
hvert spørsmål. Størrelsen på den senere implementasjonen er ikke alene grunn til
å opprette et kart.

Grillmester eier plan, implementering, tester og leveranse på alle risikonivåer
og skriver koden selv. Høy risiko, mange filer eller lang testtid utløser ikke
en egen implementeringsagent. Review skjer på en stabil diff. Sier du ja, gir
Grill-inspektør en uavhengig vurdering i egen kontekst.

Før en endring fra R2 og oppover kan kalles klar til merge, må Grill-inspektør ha godkjent
den, et menneske uttrykkelig ha godtatt alle navngitte bekymringer, eller et
menneske uttrykkelig ha frafalt review for det aktuelle omfanget. Et nei når
Grillmester spør, regnes som at du frafaller den. Egen
gjennomgang og beståtte tester erstatter ikke dette kravet. Nye endringer
krever fersk verifikasjon og review når review brukes som leveransegrunnlag.

Arbeidet går gjennom fem faser, og Grillmester-prompten nevner skillene i hver
fase. Alle endringer kontrolleres, mens andre faser som ikke trengs, hoppes over.
Den fokuserte profilen for lokale modeller nevner bare skillene den har med.

| Fase | Skills | Når |
| --- | --- | --- |
| Avklare | `grilling`, `domain-modeling`, `wayfinder` | Målet eller et viktig valg er uklart |
| Bygge | `tdd` | Før oppførsel endres |
| Feilsøke | `diagnosing-bugs` | Noe er galt og årsaken er uklar |
| Kontrollere | `review`, `security-review` | Etter siste endring, og når sikkerhet berøres |
| Levere | `pull-request` | Når PR er bestilt |

Regler som gjelder all kode, står i prompten, så de virker uten at en skill er
lastet. Før den sier seg ferdig, leser Grillmester diffen som en reviewer og
retter smells i egen kode. Lange funksjoner stoppes best av en sperre i repoet;
`/doctor` melder fra når den mangler.

Dette er en anbefalt arbeidsflyt, ikke et løfte om kortere svartid eller lavere
modellkostnad. Den nye flyten må kvalitetsvurderes i hver klient og modellprofil.

### Fra Barista til Grillmester

Barista distribueres ikke lenger. Velg Grillmester for den samme sammenhengende
utviklingsflyten, også for små og avklarte oppgaver. Lagrede launchervalg med
`barista` leses som `grillmester`; klient, provider og eksplisitt modellvalg
beholdes. Et eksplisitt `--agent barista` gir veiledning om å bruke
`--agent grillmester`. Oppdater egne snarveier og klientkonfigurasjoner som
viser til `grillmester:barista`. De fokuserte nyttelastene for lokale modeller
inneholder Grillmester og Grill-inspektør med sju utviklingsskills.

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

**Ikke bruk når:** Oppgaven er ren kode uten designspørsmål. Da passer
Grillmester bedre.

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

**Ikke bruk når:** Målet primært er å endre kode. Bruk Grillmester og trekk inn
relevante produkt-/Nav-skills der.

## Interne roller

| Rolle | Oppdrag | Viktig grense |
| --- | --- | --- |
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
| **Implementasjon og kvalitet** | Feilsøking, teststrategi, review eller sikkerhet/personvern. | Diagnosing bugs, TDD, Review, Guided review, Security review |
| **Kodebase og levering** | Arkitekturforbedring, README, PR eller skillvedlikehold. | Improve codebase architecture, README update, Pull request, Create a skill |
| **Design og UU** | Aksel, universell utforming, designutforsking eller Figma-to-code. | Aksel design, Accessibility review, Design prototype, Figma workflow |
| **Produkt og tjeneste** | Mål, discovery, teamarbeid, workshop, klarspråk eller ansvarlig atferdsdesign. | OKR, Produktledelse, Team status, Workshop design, Klarspråk, Dulting |
| **Nav backend og plattform** | Identitet, Nais, Kafka, database, observability og feilsøking i Nav/Nais. | Nav platform |
| **Nav-produktcapabilities** | En Nav-spesifikk tjenestekomponent eller arbeidsmåte trengs. | Lumi Survey |

Lumi Survey er en ordinær Nav-capability. Som alle integrasjonsskills skal den
verifisere gjeldende pakke/API og repoets faktiske auth-/Nais-oppsett; den skal
ikke gjette detaljer fra minnet.

## Én komplett plugin

`grillmester@grillmester` gir hele agentteamet og alle 37 skills i én
installasjon. Det inkluderer metode, design, produktarbeid, levering og
Nav-nære emner som Aksel, UU, arkitektur, backend og plattform. Én plugin gjør
agentenes ruting og kryssreferanser forutsigbare uten at brukeren må kjenne en
pakkeinndeling.

De 37 skillsene har korte, kanoniske ID-er som `grill-with-docs`,
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
| Grille en plan og skrive ned begreper og beslutninger underveis | `/grill-with-docs` | Kun manuelt. Uten den foreslår Grillmester dokumentasjon i én linje og skriver når du sier ja. |
| Holde flere avhengige, uløste beslutninger navigerbare over flere økter | `wayfinder` | Bruker grilling og andre metoder per spørsmål; kartet avsluttes når veien er klar. |
| Finne hvorfor eksisterende moduler er vanskelige å endre eller teste | `improve-codebase-architecture` | Finner refaktoreringsmuligheter; `architecture-review` vurderer et konkret forslag. |
| Vurdere tjenester, systemgrenser eller kostbare arkitekturvalg | `architecture-review` | Gir funn og beslutningskandidater; `domain-modeling` eier ADR-vurderingen. |
| Prøve datamodell, tilstandsmaskin eller feiloppførsel | `prototype` | Kjørbart eksperiment med avgrenset spørsmål. |
| Se layout, hierarki eller en brukerflyt | `design-prototype` | Visuell skisse; `figma-workflow` bruker et eksisterende design som grunnlag. |
| Bestemme hvor testene skal ligge, også integrasjons- og e2e-tester | `tdd` | Lager en kort testplan og holder testene få og plassert så høyt som det fortsatt er raskt. |
| Kontrollere en ferdig diff eller forstå den sammen | `review` / `guided-review` | Egenkontroll versus interaktiv gjennomgang; `security-review` brukes ved relevante sikkerhets- og personvernspørsmål. |
| Bygge på eller feilsøke Nais, Texas, TokenX, Kafka, Cloud SQL eller observability | `nav-platform` | Rutetabell til én referanse per område, med både design og feilsøking. `diagnosing-bugs` finner og retter en kodefeil; `security-review` gir en bredere sikkerhetsvurdering. |
| Få forrige svar forklart enklere | `/wait-what` | Kun manuelt. Ny forklaring med litt kontekst, korte setninger og repoets begreper. |
| Forbedre agentmiljøet etter en økt som gikk tungt | `/agent-retro` | Kun manuelt. Foreslår pekere, automatiske sjekker, slankere instruksjonsfiler og bedre tilgang til logger og informasjon; endrer bare det du godtar. Team-retroer hører til `workshop-design`. |

Skillvalg krever ikke at brukeren kan navnene. En forespørsel om en spec eller
oppdeling i tickets kan uttrykkes i vanlig språk. Det oppretter ingen
automatisk kjede fra grilling til spec og videre til issues. Fullmakt til
konkrete eksterne handlinger følger brukerens oppdrag og gjeldende grenser;
et skillskifte er ikke i seg selv en ny fullmakt.

### Slash-navn som er borte

`/api-design`, `/auth-overview`, `/kafka-topic`, `/kotlin-ktor`,
`/nais-manifest`, `/nav-troubleshoot`, `/observability-setup` og
`/postgresql-review` finnes ikke lenger. Bruk `/nav-platform`, eller beskriv
oppgaven med vanlige ord. Skillen leser bare referansen for området oppgaven
gjelder. Eldre repo- og brukerkopier forsvinner ikke av seg selv; `/doctor` finner
dem.

## Videre

- [Installer Grillmester](installation.md)
- [Bruk Grillmester i OpenCode](opencode.md)
- [Velg og test en lokal modell](local-models.md)
- [Legg repoets stående sannhet på riktig sted](repository-context.md)
- [Forstå tools, tillit og klientstøtte](trust-and-client-support.md)
