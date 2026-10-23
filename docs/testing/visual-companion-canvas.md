# Visual Companion: prøve av app-canvas

Denne protokollen undersøker om eksplisitte innspill fra skissen kan leveres
til riktig samtale uten manuell varsling. Den skiller mellom kildekontroll,
simulert vert og faktisk appkjøring. Beslutningen om det avgrensede forsøket
står i [ADR 0019](../adr/0019-app-canvas-prove.md).

## Hva som kan erstattes

Dagens preview kjører i `server.js` med Node.js. Python brukes av andre
repoverktøy, men hoster ikke Visual Companion. En canvas er ikke i seg selv en
servererstatning: den kontrollerte sesjons-SDK-en lar utvidelsen returnere en
URL til panelet. Kontrakten støtter også `file://` for lokale forhåndsvisninger,
så en selvstendig HTML-skisse kan klare seg uten HTTP-server. Vi har ikke
påvist en innebygd forbindelse fra denne HTML-filens knapper til samtalen,
eller en tilsvarende tjeneste for innspillslagring i denne kontrakten.

| Ansvar i dag | Mulig appflyt | Hva som fortsatt trengs |
| --- | --- | --- |
| Åpne lokal URL i nettleseren | Canvasens åpnehandling viser URL-en i appens panel | Hosting og verifisert tilgang fra panelet |
| `comments.js wait` venter på en innsendt runde | Eksplisitt Send legger en melding i den bundne sesjonens kø | Lagret runde, kvittering, feilhåndtering og deduplisering |
| `comments.js` leser og besvarer innspill | Smale canvas-handlinger leser innsendte runder og svarer | Lukket skjema, korrekt cursor og skille mellom utkast og beslutning |
| HTML-sandbox, CSP og autentisert bro | Gjenbrukes i panelet | Samme isolasjon fra skisseinnhold og ekstern trafikk |
| `helper.js` med notater, tekstforslag og nåler | Gjenbrukes | Fokus, utkast, kontrast, reflow og tilgjengelighet |
| `workshop.js` med varianter, justeringer og beholdte deler | Gjenbrukes | Deklarerte kontroller, stabile nøkler og bevisst innsending |
| `feedback-store.js` med revisjoner, grenser og atomisk lagring | Én felles autoritativ kø | Ingen parallelle skrivere eller toveis filsynkronisering |
| Privat økt og opprydding | Utvidelsen knytter runtime til sesjon og canvas-instans | Eksakt eierskap, utløp, stopp og krasjhåndtering |

## Alternativene vurdert

| Alternativ | Vurdering |
| --- | --- |
| Erstatte all runtime med app-canvas | Avvises som global retning. Det krever vertskapabiliteter som ikke er påvist og fjerner portabilitet til andre klienter. |
| Valgfri appadapter med portabel fallback | Anbefalt mål. Samme innspillsmodell kan brukes, mens appen får en tettere forbindelse til samtalen. |
| Bare vise dagens localhost-side i en canvas | Nyttig første steg, men løser ikke varsling alene. Må kombineres med eksplisitt innsending gjennom den bundne sesjonen. |
| Lokal HTML-fil uten HTTP-server | Egnet til selvstendige skisser og lokale interaksjoner. En egen toveis forbindelse må fortsatt løses for innspill og svar. |

### Filprøve uten server

Den separate `file-preview.mjs`-prøven har to lokale wireframes: timevalg med
validering/oppsummering og et prioriteringsbrett. Seks automatiserte prøver
består med faktisk installert SDK mot testvert og vanlig Chrome: private
filer, eksakt eierskap, utløp, opprydding, lokale interaksjoner og smale vinduer.
Ingen HTTP-server, nettverkstrafikk eller modellkall brukes. Prøven registreres
fortsatt av en Node-utvidelse. Den beviser ikke at Node-kjøremiljøet kan fjernes.

Faktisk `file://`-visning i appen gjenstår. Filprøven ble ikke åpnet der fordi
skjermen var låst; testrepoets tillit og arkiverte sesjon ble ikke endret.
Se [kjøreoppsett og presise grenser](../../experiments/canvas-review/README.md#local-html-without-an-http-server).

Før en produksjonsadapter må en annen kontrakt også avklares: innsendte
kommentarer i den portable køen kan fortsatt slettes eller åpnes igjen.
En sender som leser senere, kan derfor se en nyere versjon av listen.
Canvas-levering må velge eksplisitt mellom tilbaketrekking og et uforanderlig
innsendt øyeblikksbilde; den skal ikke tolke en kvittering som varig historikk.

## Kildekontroll og prøvens bevisverdi

GitHubs [canvas-dokumentasjon](https://docs.github.com/en/copilot/how-tos/github-copilot-app/working-with-canvas-extensions)
beskriver en flate som både brukeren og sesjonen kan endre, med handlinger
sesjonen kan kalle. Den beskriver også pluginlevering og valgfrie JSON-artefakter.
Dette fastsetter ikke vår lagringspolicy, leveringsgaranti eller opprydding.

GitHubs [color-orb-eksempel](https://github.com/github/awesome-copilot/blob/main/extensions/color-orb/extension.mjs)
viser en konkret kjede fra nettleserhandling via lokal HTTP-server til
`session.send`, og tilbake til flaten gjennom canvas-handlinger. Dette støtter
valg av prøveretning. Eksemplets begrensede demo er ikke sikkerhetskontrakten
for våre fritekstinnspill; autentisering, grenser og kvitteringer må håndheves
av forsøket selv.

Den undersøkte, installerte SDK-en har følgende konkrete kontrakt:

- `joinSession({ canvases: [...] })` knytter en utvidelse til eksisterende
  sesjon; `createCanvas` deklarerer åpne-, lukke- og handlingsbehandlere.
- Handlerne får identiteter for sesjon, utvidelse, canvas og instans.
- `CanvasProviderOpenResult` har `url`, `title` og `status`. Den undersøkte
  kontrakten kan rapportere canvas-støtte, men `host.capabilities.canvases`
  i åpnecallbacken er valgfritt.
- `session.send` returnerer meldings-ID når meldingen er tatt inn. Videre
  behandling er asynkron. Kømodus er `enqueue`.
- `onClose` er valgfri og har ingen bekreftet oppryddingstransaksjon.
- Canvas-typene er merket eksperimentelle.

GitHubs [dokumentasjon om kø og styring](https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/steering-and-queueing)
skiller kømodus fra styring av en pågående tur. Den presiserer at mottak av
meldings-ID ikke beviser konsumert innhold, og at manglende synlig svar ikke
er grunnlag for automatisk ny sending. Forsøket bruker kømodus for bevisst
innsendt brukerfeedback; kilde og leveringsmodus endrer ikke tillatelsene til
innholdet.

En prøve mot disse faktiske SDK-filene kan avdekke ugyldige deklarasjoner,
feil RPC-form, feil sesjonsbinding og feilbehandling. En simulert vert kan
ikke bevise at appen åpner URL-en, viderefører en avsluttet samtaletur,
overlever vindusbytte eller tillater loopback i sitt faktiske miljø.

## Avgrenset forsøk

Forsøkskoden ligger i `experiments/canvas-review/`, utenfor pluginpayloaden.
Det bruker et avgrenset JSON-format for oppdiktet innhold og et lite sett med
innspill, ikke hele Visual Companion-grensesnittet. En loopback-server per
canvas-instans gjør eierskap og isolasjon etterprøvbart. Les SDK-en fra en
eksplisitt valgt sti; ikke installer avhengigheter eller kopier SDK-en inn i
pluginen. Den automatiserte kontraktprøven skal ikke starte Copilot eller
kontakte en modell.

Prøven lagrer data bare i prosessens minne. «Lagret» betyr derfor tilgjengelig
i den kjørende prøveøkten, ikke sikret mot krasj eller restart. Den har opptil
fire beholdte skisser, 50 innsendte runder og 50 skisserevisjoner per instans,
og en absolutt levetid på 20 minutter. Lukking stopper panelets HTTP-server og
tilbakekaller URL-en. Gjenåpning av samme ID gir nytt token og samme skisse,
historikk og innsendte runder. Det forlenger ikke levetiden eller endrer konseptet.
Usendte nettleserutkast overlever ikke panellukking. Utløpte instans-ID-er kan
ikke gjenbrukes i samme utvidelsesprosess. Etter 20 utløpte instanser må forsøket
startes på nytt. Ingen token-URL lagres i delt testevidens.

SDK-ens lukkecallback har ingen visningsgenerasjon. En forsinket callback kan
derfor lukke en nylig gjenåpnet visning, men kan ikke slette eller nullstille
skissen; den kan åpnes igjen. Endelig utløp eller avsluttet utvidelse forkaster
skissen og avviser videre handlinger. Dette er midlertidig gjenoppretting i
minnet, ikke varig lagring.

En lokal tekstkladd holder den synlige skisseversjonen tilbake når en ny
revisjon publiseres. Innsendingen bindes til denne opprinnelige versjonen og
beholder dens forfattede tittel og beskrivelse. Dette er begrenset JSON-kontekst,
ikke innsamling av DOM-tekst eller fri historikk av hele HTML-skisser.

Test to ulike operasjoner: Brukeren sender en lagret runde til sesjonen, og
sesjonen bruker en deklarert handling til å lese eller besvare innspill.
Navn på slike handlinger er forsøkets egen kontrakt, ikke innebygde SDK-navn.
Valg av kontroll, skriving, panelåpning og reconnect skal ikke sende meldinger.

Bind handlerne til sesjonen de ble opprettet for. Ikke slå opp den til enhver
tid aktive samtalen på nytt ved hvert klikk. Godkjent innsending lagres før
leveringsforsøket, og leveringsstatus må skilles fra utført arbeid:

- **Lagret:** innspillene finnes i riktig kø.
- **Levert til samtalen:** sesjonen har returnert et meldings-ID.
- **Behandles:** faktisk sesjonsaktivitet knyttet til runden er observert.
- **Ferdig:** endringen er utført og relevant visuell kontroll er gjennomført.

`session.send` gir ikke alene nøyaktig én levering ved krasj mellom mottak og
lokal kvittering. Ved usikkert utfall skal grensesnittet bevare runden og si
hva som er usikkert. Automatisk gjentakelse må ikke starte duplisert arbeid.

## Panel og nye case

Perspektivene under er en simulert faglig gjennomgang, ikke menneskelig
brukerforskning. Oppgavene skal prøves både som protokoll og, før produktbruk,
i den virkelige appen.

| Perspektiv | Oppgave | Observerbart beståttkriterium |
| --- | --- | --- |
| Tjenestedesigner | Lag tre innspill mens samtalen står stille; send samlet | Ingen arbeidstur under skriving. Én runde leveres til riktig samtale etter Send, med korrekt synlig kvittering. |
| Fagansvarlig | Behold én del og legg ved et forbehold; endre deretter et usendt utkast | Bare innsendte føringer er bindende. Utkastet endrer ikke instruksjonen som allerede er sendt. |
| Møteleder | Send runde to mens runde én behandles | Rekkefølge og innhold bevares. Første cursor hopper ikke over andre runde; køstatus fremstilles korrekt. |
| Designer med to prosjekter | Åpne to like navngitte prosjekter og bytt aktiv samtale | Hver canvas sender til sin opprinnelig bundne sesjon og instans. Ingen kryssing av tekst eller beslutninger. |
| Bruker med forstørret visning | Kommenter og sammenlign i smalt panel ved faktisk 200 % zoom | Alle handlinger kan nås med tastatur; fokus er synlig og skjult kontroll kan bringes inn i visningen. |
| Drift og klientstøtte | Lukk panelet, åpne igjen, stopp sesjonen og avbryt forbindelsen | Ingen foreldreløse servere, feil gjenbruk av instans eller lovnad om behandling etter stopp. Utkast kan reddes når mulig. |
| Sikkerhetsreviewer | Send ugyldig melding, annen origin og skisseinnhold med aktivt skript | Ingen generell prompt- eller verktøytilgang. Lukkede skjemaer, token, sandbox og CSP håndheves. |
| Grillmester-forvalter | Bygg alle targetene med og uten appkapabilitet | Ingen hengende extensions-stier, SDK-avhengighet i OpenCode eller endret oppførsel i portable klienter. |

## Resultater fra den avgrensede prøven

Kontrollert 2026-10-23 med oppdiktede data. De automatiserte prøvene under
startet ingen klient eller modell. En senere, avgrenset prøve i appen er
registrert separat nedenfor. Ingen personlig utvidelsesmappe er endret.

| Prøvelag | Resultat | Hva det beviser |
| --- | --- | --- |
| Node-tester av HTTP og levetid | 16 bestått | Token, Host, Origin, lukket skjema, tekstgrenser, parallelle åpninger og lukkinger, isolasjon, utløp, sene kvitteringer, historisk skissekontekst og valgfrie kapabilitetsfelt |
| Installert SDK mot deterministisk stdio-vert | 18 bestått | Registrering, eksakt sesjonsbinding, kømelding, deduplisering, handlinger, isolasjon, uavklart levering, valgfrie kapabilitetsfelt og lukking gjennom SDK-ens faktiske protokoll |
| Chrome mot den faktiske prøveflaten med simulert sesjon | 8 bestått | Tastatur, utkast under ny revisjon, smal visning, norsk langtekst, lesing på tvers av runder, tapt HTTP-kvittering og uavklart SDK-levering; ingen eksterne ressurskall eller nettleserfeil |

SDK-prøven brukte filene fra appversjon 1.1.31, protokollversjon 3 og
SDK-inngangsfilens SHA-256
`a8faeb5d4c8379ce6d8473c86e001fc4e2cd5d260e064d4c622f72c35102871d`.
I dette automatiserte prøvelaget ble appen bare undersøkt som filer.
Reproduserbare kommandoer står i
[forsøkets README](../../experiments/canvas-review/README.md).

Den faktiske appprøven brukte versjon 1.1.31 på macOS og en disponibel
testmappe med prosjektutvidelsen. Designer ble valgt fra appens katalog,
deretter ble modellen valgt manuelt. Prøven bekreftet oppdagelse gjennom
`list_canvas_capabilities`, rendering i appens panel og behandling av ett
eksplisitt innspill fra en ledig sesjon. CSP beholdt `frame-ancestors 'none'`.

I den første prøven ble `guided` valgt og én runde med ønsket tittel og
beskrivelse sendt.
Innsendingen startet en ny tur uten ekstra chatmelding. Sesjonen kalte
`open_canvas` og `invoke_canvas_action`, markerte runden som under behandling,
publiserte revisjonen og besvarte runden. Panelet viste «Forbered deg til møtet»,
beskrivelsen «Skriv ned to spørsmål du vil ta opp. Ta med notatene til møtet.»,
skisseversjon 2 og «Runde 1 Besvart» med synlig svar. Totalt ble to
arbeidsforespørsler sendt: den første chatmeldingen og innspillet fra panelet.

To hindringer ble observert før denne kjeden bestod. Prøvefiltret avviste
manglende valgfrie kapabilitetsfelt. Det tillater nå manglende felt først etter
verifisert binding til den tilknyttede sesjonen og eierskap i callbacken;
uttrykkelig `false` og ugyldige verdier avvises fortsatt. Runtime-en stanset
også videre kjøring med feil om for stor statisk system- og
verktøykontekst. Brukeren valgte kontekstrammen 1,1M, og oppfølgingsrunden
bestod med samme manuelt valgte modell og Designer. Dette avklarer ikke den
generelle årsaken til feilen. Visningen av 23 % kontekstbruk før endringen
beviste ikke tilstrekkelig inputbudsjett: respons og headroom reserveres separat.
[Kontekstdokumentasjonen](https://docs.github.com/en/copilot/concepts/prompting-and-context/context-management)
beskriver dette skillet. [App-rapport 4612](https://github.com/github/app/issues/4612)
viser samme feilmelding i en annen installasjon, men beviser ikke årsaken her.

Normal panellukking stengte den konkrete loopback-porten. Tilliten til den
disponible testmappen ble trukket tilbake, og innstillingene viste «Not accepted».
Prøveøkten ble arkivert; ingen av dens utvidelsesprosesser var igjen.
En ny appomgang prøvde to separate instanser i samme sesjon: møteforberedelse
og arbeidsoversikt. Innspill til arbeidsoversikten ble sendt mens den første
runden var under arbeid. Appen viste «1 queued message», tok deretter opp den
andre runden automatisk og viste riktig tittel, beskrivelse og svar i hver
skisse. Et nytt usendt utkast beholdt teksten og skisseversjon 1 mens versjon 2
ventet. Tømming av utkastet viste den nye skissen. En tekst med 1001 «ø» ble
stoppet lokalt med feltfeil og fokus tilbake i feltet; ingen ny runde ble sendt.
«Se siste svar» flyttet fokus til den besvarte runden.

Den siste appprøven lastet inn rettelsene for levetid og gjenåpning. Panelet ble
lukket mens et kvittert innspill ble behandlet, og den konkrete porten stengte.
Verten avviste videre canvas-handlinger fordi panelet var lukket. Sesjonen åpnet
derfor samme instans igjen, fant den beholdte runden og fullførte oppdatering og
svar. Ny manuell lukking og gjenåpning fra canvasmenyen beholdt skisseversjon 2,
innspillets ID og svaret, med en ny URL og uten ny melding. Lukking er dermed
ikke kansellering av allerede innsendt arbeid; panelet kan åpnes igjen av den
pågående behandlingen. En produksjonsadapter må avklare og synliggjøre dette.

Totalt omfattet appprøvene seks eksplisitte arbeidsforespørsler: to
oppsettsmeldinger og fire innsendte runder. Fanetitlene er nå forskjellige for
møteforberedelse, arbeidsoversikt og timebestilling. Etter siste prøve var
samtlige konkrete prøveporter stengt, testtilliten trukket tilbake, økten
bekreftet arkivert og ingen prøveutvidelsesprosesser igjen. To samtidige sesjoner,
krasj, faktisk 200 % zoom, skjermleser og lagring av token-URL er fortsatt ikke
validert i appen. Samme-instans-gjenåpning beviser ikke varig lagring ved restart.

Den simulerte faglige gjennomgangen førte til konkrete rettelser: utkast holder
på skissen det gjelder, innsendte runder beholder den opprinnelige tittelen og
beskrivelsen, og en gjenfunnet HTTP-kvittering fjerner gammel feiltekst uten å
slette et nyere utkast.
En bekreftet behandling av riktig runde tillater neste runde selv om den første
leveringskvitteringen mangler. Vanlig statusoppdatering bevarer tekstmarkering
slik at svar kan kopieres. Hoppelenker går til innspillsfeltet og sist oppdaterte
svar. Statusvarsler endres bare ved en faktisk tilstandsendring, og en for lang
norsk tekst får en feltkoblet feil uten å miste innholdet. Ved tekstvalideringsfeil
flyttes fokus tilbake til feltet. Oppdatering av én runde bevarer markert tekst
i en annen.
Samtidig lukking av panel og økt venter på samme opprydding før den kvitterer,
og gjentatt lukking etter avslutning beholder eierkontrollen. En nyere lukking
kansellerer en ventende gjenåpning. Forsinkede HTTP-innsendinger fra en lukket
visning kan ikke nå den gjenåpnede skissen. En besvart runde kan ikke utilsiktet
settes tilbake til under behandling.

Nettleserprøven bruker innhold, arbeidsoversikt og timebestilling som tre
oppgavetekster i samme lille grensesnitt. Den beviser ikke tre komplette
produktkonsepter. 390 og 415 px bredde og 720 × 456 px viewport er prøvd; sistnevnte
er ikke faktisk 200 % zoom. Skjermleser, faktisk 200 % zoom og appens
fokusrekkefølge er ikke verifisert. Tilstanden ligger i minnet og tåler ikke
restart.

## Porter før produksjonsintegrasjon

| Prioritet | Port | Bevis som kreves |
| --- | --- | --- |
| P0 | Riktig sesjon | Samtidige sesjoner, worktrees og instanser; gjentatt åpning av eksisterende instans; ingen bruk av global sist aktive økt. |
| P0 | Privilegert bro | Negative tester av origin, token, skjema, frame-avsender, vilkårlig prompt og ikke-innsendte handlinger. |
| P0 | Levering og gjentakelse | Dobbeltklikk, stale revisjon, feil før lagring, feil før sending og tapt kvittering etter mottak; ingen skjult automatisk duplisering. |
| P0 | Portabel distribusjon | Alle genererte manifester og klientmål validerer; klienter uten kapabiliteten bruker eksisterende flyt. |
| P1 | Virkelig panel | Faktisk appvisning med gjeldende CSP og sandbox; ingen wildcard-utvidelse for å få embedding til å virke. |
| P1 | Avsluttet og pågående tur | Begge tilfellene måles separat i appen. Kvittert kømelding omtales ikke som utført arbeid. |
| P1 | Livssyklus | Normal lukking, session-stopp, krasj, frakobling og gjenåpning; eksakt opprydding, avgrenset levetid og ingen løs bakgrunnsvakt. |
| P1 | Lagring og privatliv | Hvor appen lagrer URL og innhold dokumenteres; ingen token-URL i delt testevidens og ingen utilsiktet varig lagring av midlertidige innspill. |
| P1 | Tilgjengelighet | Virkelig panelbredde, 200 % zoom, tastatur, fokus, redusert bevegelse og lange tekster. |
| P1 | Føringer og revisjoner | Samme utkast-, innsending-, gjenåpning- og behold-semantikk som den portable runtime-en. |
| P2 | Versjoner | Valgte app-/SDK-versjoner registreres separat fra CLI på PATH; manglende eksperimentelt API gir tydelig fallback. |

## Distribusjonsfellen

Den kanoniske pluginen bruker i dag det eldre manifestformatet.
[Pluginreferansen](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference)
beskriver `extensions` som stier i dette formatet. Et nyere manifestformat har
en annen betydning av feltet og andre plasseringer for klientspesifikke
komponenter. Vi skal ikke bytte format som en del av forsøket.

Den fulle manifestgeneratoren kan binde nye regulære payloadfiler. Det er
likevel utilstrekkelig: den fokuserte Copilot-projeksjonen kopierer
`plugin.json` byte-eksakt, men kopierer bare utvalgte agenter og skills. En
ny utvidelsessti kan dermed bli distribuert uten innholdet den peker på.
Før integrasjon må en eksplisitt genereringspolicy enten utelate appdelen fra
den fokuserte manifesten eller distribuere den i en separat pakke. OpenCode
skal ikke arve en appspesifikk SDK-runtime.

Forsøket endrer derfor verken installasjon, pluginmanifest, targets eller
standardvalg. Det skal gjøre en senere beslutning konkret, med bevis for
samspillet som brukeren faktisk trenger.
