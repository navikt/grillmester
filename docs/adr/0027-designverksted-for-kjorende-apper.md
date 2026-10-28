---
status: accepted
date: 2026-10-27
---

# Ett designverksted for skisser og kjørende apper

## Kontekst

Designverksted publiserer avgrensede HTML-skisser med deklarerte tilstander.
Dette passer visuell utforsking, men kan ikke bevare en eksisterende apps
komponenter, navigasjon og skjemaoppførsel. En bestilling om å åpne en demo
skal derfor ikke ende i en rekonstruert, statisk side.

En kjørende app har også en annen tillitsgrense enn en renset skisse: appens
JavaScript kan ikke få tilgang til innsendings-, lagrings- eller kildehandlinger.
Agentic UIs lokale proxy og elementmarkering viser en relevant arkitektur,
men en separat utvidelse ville gitt to brukerflater og to innspillsmodeller.

## Beslutning

Grillmester leverer ett Designverksted. En appoppgave har én eiet canvasinstans
og én sammenhengende arbeidsflate med «Appen nå» og «Forslag». Forslaget er et
logisk skissedokument i samme arbeid, ikke et nytt native canvas. Selvstendige
HTML-rom kan fortsatt åpnes alene. Den første appflyten har verkstedet inne i
Copilot app ved siden av samtalen, med empirisk verifisert støtteomfang beskrevet
nedenfor. Ekstern nettlesertransport er utsatt og er ingen automatisk fallback;
app og forslag skal aldri splittes mellom nettleser og native canvas.
Designer velger underlaget fra
oppgaven og tilgjengelige kapabiliteter; brukeren skal ikke måtte velge transport
eller installere et eget kommenteringsverktøy.
Eksisterende HTML-rom beholdes uten automatisk omskriving.

### Appvisning og innspill

Appvisningen kobles til en verifisert lokal HTTP(S)-adresse. Startsidens sti og
trygge query-parametre beholdes. Serveren startes etter consumerens dokumenterte
oppskrift; en canvasåpning utfører ikke vilkårlige oppstartskommandoer. Feil ved
oppstart gir en konkret forklaring, ikke automatisk overgang til statiske sider.

Verktøylinje, innspillskurv og handlinger kjører på en betrodd kontroll-origin.
Appen vises gjennom en separat lokal proxy-origin. Appen mottar ikke
kontrolltoken, filtilgang eller rett til å sende en runde. Et injisert
markeringslag kan bare foreslå avgrenset element-, rute- og visningskontekst.
Disse dataene er ubekreftet appinnhold, også når de ligner en React-kildesti.
Bare den betrodde flaten oppretter innspill og utfører eksplisitt innsending.

Proxyen bruker eksakt `localhost:<port>` i én native appinstans;
kontrollflaten bruker eksakt `127.0.0.1:<port>`. Begge lyttere bindes bare til
`127.0.0.1`. App- og transportcookies er vertsbundne og partisjonerte
(`SameSite=None; Secure; Partitioned`). Kontrollflaten deler ikke cookiehost
med appen. Én instans beholder samme oppstrømsapp, proxylytter og origin
hele levetiden; en ny app skal ikke bindes bak den gamle proxyen.
DNS-oppslaget for oppstrømsappen
valideres én gang til bare loopback-adresser, og tilkoblingen kan prøve både
IPv4 og IPv6 fra dette låste resultatet. Eksakt Host og Origin kontrolleres
fortsatt. CSP-tilpasningen bevarer appens effektive inline-regler og legger
bare til tillatelse for markeringsskriptet; appens øvrige skript får ikke nonce.

Beslutningen er oppdatert etter nativeprøver 28. oktober 2026. Separat
lagring mellom canvasinstanser ble observert i den prøvde verten; den samlede
app-/forslagsflyten ble prøvd i Copilot app 1.1.33 på macOS. Det er empirisk
støtte, ikke en offentlig SDK-kontrakt for datalagerisolasjon. Andre verter og
versjoner må prøves særskilt. En canvas-kapabilitet, User-Agent eller fravær
av én canary er ikke et generelt isolasjonsbevis.

Den tidligere nativeprøven med tilfeldig `*.localhost` nådde ikke appen.
Et rent vertsnavnbytte i vanlig Chrome beholdt kontrollvern, men samtidige
visninger delte appcookies, og tvunget portgjenbruk arvet en gammel worker.
Separate porter alene er derfor utilstrekkelig. Nativevariantens private
adresse må aldri åpnes i en delt nettleserkontekst. En eventuell senere
nettlesertransport trenger egen originisolasjon og en uttrykkelig overgang
av skriveransvar; den skal ikke gjenbruke native-URL eller anta samme
lagringsgrenser. Ingen vertsinnstillinger eller systemregler endres som omvei.

En konstant URL og pinnet DNS er ikke appprosessens identitet. Ved tap eller
bytte av oppstrømsprosessen må tilhørende nativeinstanser avsluttes før en ny
app kobles til. Den observerte nativeprøven håndhevet dette med én kjent
egeneid server og et uttrykkelig forbud mot restart bak åpne visninger.
Generell verifikasjon av en vilkårlig utviklingsservers identitet er fortsatt
en separat produktgrense.

### Tilkobling og gjenåpning

Den eksisterende lokale appserveren leverer verkstedet direkte i canvaset.
Den gjenbruker HTML-motorens eksisterende backend for ett forslag. Dette er en
eiet barneprosess, ikke en ny bakgrunnstjeneste eller samtalekø.
Åpning returnerer en privat, inaktiv renderer-kandidat. Kontrollskallet
aktiverer kandidaten eksplisitt før appen lastes. Adresser og transportnøkler
forblir private og midlertidige; det finnes ikke en knapp som flytter dette
verkstedet til en annen nettleser.

En hentet åpningsside gir ikke skriverrett. Nettleserdokumentet må aktivere sin
egen kapasitet; bare ett dokument vinner. Gjentatt aktivering fra samme dokument
er idempotent. Alle lesinger og skrivinger krever aktiv dokumentmyndighet;
myndigheten kontrolleres igjen etter asynkron innlesing av en forespørsel, før
noen tilstand endres. Dermed kan en gammel treg forespørsel ikke skrive etter
at instansen er avsluttet.

Åpning av samme fortsatt levende instans fokuserer den eksisterende visningen.
Kontrollskall-reload eller duplisering kan ikke overta den aktive skriveren.
Vanlig iframe-retry laster den samme appen gjennom samme proxy og kan beholde
cookies og worker; det er ikke en fersk lagringskontekst. Utløpt invitasjon
betyr ikke at et allerede aktivert dokument har mistet myndigheten.

Canvaslukking avviser nye adapterhandlinger straks og tilbakekaller renderer,
proxy og forslagets child-lease mens eide backender ryddes. Backendtap og
uventet tap av kontroll- eller proxylytter avslutter også instansen. Den gamle
identiteten kan ikke åpnes igjen. En ny instans kan åpne det samme lagrede
rommet og dets verifiserte forslag uten å sende historiske runder på nytt.
Gjenåpning starter på rommets lagrede startside, ikke nødvendigvis sist
observerte rute. En lås fra pågående rydding skal ikke fjernes for å tvinge
åpning. Midlertidige forslag, appens skjematilstand og ulagret tekst loves ikke
bevart etter lukking. Selvstendige HTML-rom beholder sin eksisterende levetid.

Å bytte mellom Appen nå og Forslag endrer ikke bindingen og lar monterte
visninger beholde sine lokale utkast. Canvaslukking stopper ikke en separat
utviklingsserver. Serverens eierskap og avslutning må følge dens dokumenterte
oppstartsavtale. Samtalestartede demoer bruker den avgrensede CLI-hjelperen i
[ADR 0028](0028-eid-livslop-for-lokale-demoer.md) gjennom vanlig shellautoritet.
Den returnerer kort etter oppstart og tilbyr status og uttrykkelig stopp for
den eide prosessgruppen. Den verifiserer ikke appens URL eller gir canvaset
rett til å starte kommandoer. `queued` bekrefter én mottatt runde, ikke at samtalen er ledig
eller at behandlingen har startet. Stopp av en oppgave må ikke tolkes som
bestilling om automatisk restart av dens demo.

Browser-MSW støttes på den isolerte origin. Chrome sender ikke de partisjonerte
cookiene når den henter worker-filen eller når en aktiv worker videresender
forespørsler. Worker-henting bruker derfor en separat visningskapasitet i en
reservert transportparameter: bare GET med worker-headere, eksakt lokal Host
og riktig nøkkel godtas; parameteren fjernes før oppstrømskallet. Svaret må være
JavaScript, og workerens scope må bli innenfor samme app-origin. En avgrenset
fetch-tilpasning i worker-filen bruker en annen kapasitet for workerens egne
appforespørsler. Den godtas bare på samme preview-origin og fjernes før
videresending; den gir ikke kontrolltoken, innspillsmyndighet eller filtilgang.
Logisk worker-adresse beholdes slik at MSW kan finne registreringen. Disse
transportdetaljene skal ikke inngå i rommetadata, delte logger eller rapporter.
Registrering, worker-oppdatering og iframe-omlasting er kontrollert med MSW.
Worker-filer med egne `importScripts`- eller modulimporter støttes foreløpig
ikke når importene hentes uten cookies; de krever en egen vurdering og skal
ikke gis bredere tilgang automatisk. Retry i samme instans kan beholde
workerregistreringen. En ny nativeinstans får en ny eid proxy, men
lagringsisolasjon ved eventuelt portgjenbruk avhenger av den verifiserte verten.

Appinnspill og skisseinnspill bruker samme FeedbackStore og CanvasState,
samme uforanderlige innsendingsrunder og samme kvitteringssemantikk.
Et appunderlag får en uttrykkelig type og innspillsidentitet; en localhost-adresse
skal ikke late som den er en HTML-revisjon. Siden, visningsbredden og relevant
elementkontekst følger innspillet. Hemmelige URL-parametre og feltverdier skal
ikke inngå i denne konteksten.

«Vis stedet» kan gjenfinne den lagrede elementkonteksten på siden som er åpen.
Handlingen ruller og markerer; den aktiverer eller fokuserer ikke appkontroller
og navigerer ikke til en annen side. Et skjult, endret eller tvetydig mål gir
en forklaring fremfor et antatt treff. Dette innfører ingen ny lagret identitet
eller rett til å opprette eller sende innspill. Smale flater gir en uttrykkelig
retur til samme innspillskort og beholder uferdig tekst.

### Avgrenset første release

Appflyten lar designeren prøve den faktiske appen, velge en del eller hele siden,
lagre innspill i kurven og sende en samlet runde. Den tilbyr ingen lesing eller
skriving av appkilde, kildeendringsforslag, angre, gjenoppretting, referansebilder
eller apphistorikk. Slike handlinger distribueres ikke i canvasens verktøykatalog.
HTML-skissenes publisering, editor, versjonsvisning og gjenoppretting beholdes;
delte skissehandlinger forklarer at de bare gjelder HTML. I approm krever de
det registrerte forslagets identitet; uten den avvises appunderlaget.

### Ett forslag i samme arbeid

Et konkret designønske innenfor oppgaven skal normalt gi et synlig, avgrenset
HTML-forslag under «Forslag», med faktisk app som referanse. Bestillingen kan
komme direkte i samtalen eller fra en innsendt apprunde. Samtalebestillinger skal
ikke kreve kunstige kommentarer eller automatisk innsending. Rene observasjoner,
review-only og ingen-HTML bestiller ikke et forslag. Avklart skisselagring
brukes; ellers blir oppfølgingen midlertidig uten et nytt lagringsspørsmål.
Lagrede appinnspill gir ikke i seg selv mandat til lagrede skissefiler. En
uttrykkelig bestilling om å lagre hele verkstedet omfatter også forslag innenfor
den avtalte designmappen.

`publish_proposal` oppretter høyst ett forslag med enten `source: "conversation"`
eller `source: "app-feedback"` og de faktiske innsendte kommentarene. Senere
endringer bruker eksisterende skissepublisering med samme `proposalId` og
skjermvakt. Forslagets innspill og versjoner beholdes i HTML-motoren. Alle
verktøyhandlinger og leveringsreferanser skiller eksplisitt mellom app og forslag;
valgt fane bestemmer aldri hvilken runde som besvares. Ett forslag kan inneholde
flere deklarerte varianter når de hjelper et reelt designvalg.

Den betrodde appflaten eier fanene. Et smalt visningsmellomledd på samme origin
rammer inn HTML-skallet med nøyaktig angitt child-origin; ytre flate tillater
ikke vilkårlige loopback-rammer. HTML-skallet og dets isolerte innerpreview
navngir bare den eksakte foreldre-origin i sine ancestor-regler. Skisseinnholdet
beholder sin opaque sandbox og får aldri kontrollnøkler. En hentet child-side
er inaktiv inntil riktig forelder aktiverer akkurat dens dokumentkapasitet;
en kopiert adresse gir ikke en ekstra skriver. Tilbakekalling gjelder også
HTML-forespørsler som allerede leser request-body. Private adresser og nøkler
kommer aldri i modellresultater eller lagrede romfiler.

Når både appinnspill og forslag er lagret etter bestilling, inneholder apprommet
en avgrenset `workspace.sketch`-relasjon med prosjekt-relativ sti, eksakt
skisseworkspace-identitet, logisk forslag-ID og kildebestilling. Ved gjenåpning
valideres sti, identitet og HTML-type på nytt. En manglende eller erstattet mappe
vises som utilgjengelig; den opprettes ikke automatisk. Midlertidige relasjoner
lever bare i den eide samtalen. Ved overlevering velges en faktisk skisserevisjon
og dens registrerte filpar verifiseres; relasjonen er ikke en app- eller
kildeversjon. Rettigheten til å lagre er fortsatt særskilt fra å skissere.

Et midlertidig forslag i et allerede lagret approm kan lagres senere med
`save_proposal`, etter en uttrykkelig bestilling og en ny prosjekt-relativ
målmappe. Forslag-ID, kildebestilling, alle registrerte skisseversjoner og hele
innspillshistorikken beholdes. Den levende HTML-visningen byttes ikke ut;
handlingen sender ingen runder på nytt. Skjerm- og innspillsrevisjon kontrolleres
før lagringen. Et fullt midlertidig approm kan ikke oppgraderes med denne
handlingen; det avvises uten å påstå at hele verkstedet er lagret.

Apprommet registrerer en avgrenset `pendingSketchSave` før HTML-lagringen.
Etter bekreftet lagring erstattes den med den verifiserte skissekoblingen.
Et tapt svar eller en ubekreftet lagring gjentas med samme forslag, mål og
forventede tilstand. Filer som allerede er lagret, fjernes ikke på grunn av en
senere feil. Ved gjenåpning må en uferdig lagring peke på akkurat det samme
lagrede rommet; en manglende eller erstattet målmappe opprettes eller adopteres
ikke automatisk. Hvis prosessen avsluttes før de midlertidige skissefilene er
lagret, kan disse ikke gjenopprettes fra bare lagringsintensjonen. De lagrede
appinnspillene forblir tilgjengelige.

Skissen bruker deklarerte kontroller og klikkbare steg; egne skript fjernes som
før. Simulerte situasjoner merkes. Forslaget er ikke bevis på appens runtime,
validering eller backend. Automatisk sideopptak, stilkopiering og synkronisering
av appens skjematilstand innføres ikke. «Vis forslag» viser registrert arbeid;
vanlige svar forklarer kort hva designeren kan prøve, uten interne stier og ID-er.

Appinnspill er midlertidige som standard og bruker privat runtime-lagring uten
å åpne prosjektets kildefiler. Prosjektlagring velges uttrykkelig med en navngitt
mappe og bevarer innspill, svar og eventuell uttrykkelig lagret forslagrelasjon.
Et lagret approm har `mode: "feedback"`, appens navn, startside og eventuell querypolicy. Navnet er beskrivende; ved
senere åpning kan port og navn endres, mens startside og querypolicy må stemme.
Rommet kan leses i en annen checkout uten fysisk mappeidentitet. Dette gir ingen
binding mellom kildekatalog og kjørende server og skal ikke fremstilles slik.
Et ugjennomsiktig checkpoint skiller innspillskontekst, ikke kildeversjoner.
Tidligere uutgitte rom med kildehistorikk avvises forståelig uten å endre filene.

Queryverdier som identifiserer syntetiske offentlige ressurser kan være UUID-er.
En begrenset, eksplisitt liste over querynavn deklareres ved åpning og bindes
til rommet. Listen gir ikke tillatelse til personopplysninger, autentisering
eller andre hemmeligheter, og appinnhold kan ikke utvide den.

Appinnspill gir ikke skrivemandat. Separat bestilte kodeendringer følger en egen
arbeidsflyt utenfor canvas i en uttrykkelig eid kopi. Denne flyten må kontrollere
at serveren bruker den valgte kopien og bevare originalprosjektet og uvedkommende
arbeid; en Git-worktree alene beviser ikke at kopien er disponibel. Verken
DOM-kontekst, en lokal URL eller en samtales arbeidsmappe beviser kildebindingen.
En komplett integrert endringsflyt er utsatt til eierskap, kilde-/runtimebinding,
feilhåndtering og gjenopptak kan håndheves og testes samlet.

### Når byggeformatet skal vurderes på nytt

Utvid byggeformatet først når gjentatte, reelle designoppgaver i Nav viser at
forslagene trenger eksisterende appoppførsel eller dataflyt som ikke kan
uttrykkes godt med deklarerte skissetilstander. Behovet skal demonstreres med
brukere og konkrete oppgaver; panelvurderinger eller flere tekniske muligheter
alene er ikke tilstrekkelig. Egen JavaScript-runtime eller integrert kildecanvas
krever da en separat arkitektur- og tillitsbeslutning med avklart eierskap,
kjøregrenser og verifikasjon. Denne beslutningen åpner ikke de funksjonene.

### Distribusjon og ansvar

Integrasjonen eies, distribueres og testes som del av Grillmester.
Appcanvasets runtime følger den kanoniske Copilot-pluginen. OpenCode-targetet
utelater disse canvasfilene og beholder bare kontraktfiler som den delte
innspillsvalideringen trenger; den portable HTML-flyten beholdes.
Ingen ny MCP-server, installasjonshook, parallell synkronisering eller
skytjeneste innføres. Referanseprosjektets arkitektur kan informere designet;
kopiering eller distribusjon av kildekode forutsetter avklart gjenbruksrett.
Inntil da implementeres de avgrensede kontraktene selvstendig.

Designer-agenten beskriver om arbeidet er en skisse, en kjørende prototype
eller en produktendring, og hva som er kontrollert. En samlet innsending er
fortsatt et bevisst valg; navigasjon og feltbruk starter ingen modelloppgave.

## Alternativer og konsekvenser

- Bare HTML ville beholdt en enkel og avgrenset runtime, men krevd at faktisk
  appoppførsel rekonstrueres og vedlikeholdes to steder.
- Bare appvisning ville gitt god komponentfidelitet, men fjernet en nyttig
  skisseflyt og svekket kompatibiliteten med allerede lagrede designrom.
- To separate utvidelser ville vært raskere å koble sammen løst, men gjort
  transport, innspill og lagring til designerens ansvar.

Den valgte løsningen beholder to interne visningsmåter og én brukerflyt.
Det øker testansvaret: proxy, appinnspill og gjenopptak må kontrolleres
separat fra den eksisterende HTML-sanitizeren. Ingen av dem kan erstatte den
andres sikkerhetsmodell.

## Aksept før levering

1. Eksisterende rom og innsendte runder kan åpnes og leses uendret.
2. En ekte app beholder startside/basepath, navigasjon, komponentoppførsel,
   lokale API-kall og utviklingsoppdatering gjennom visningen.
3. Ubetrodd appinnhold kan ikke sende runder, lese kontrolltoken, bytte
   oppstrømsadresse eller utføre kilde-/historikkhandlinger.
4. Midlertidig appbruk og forslag lager ingen prosjektmappe. Kilde- og
   bildehandlinger er utilgjengelige; eksisterende HTML-rom bevarer funksjonene.
   Nytt forslag, innspill og iterasjon blir i samme arbeidsflate og samtale.
5. Lagrede innspill og svar overlever gjenåpning med opprinnelig sidekontekst,
   uten å hevde at appkode eller nettlesertilstand er gjenopprettet.
6. Tastatur, smale paneler, zoom, feiltilstander, avbrudd og tvetydig levering
   har observerbare og forståelige resultater.
7. App- og forslag-runde med samme nummer rutes riktig. Lukking, gjenåpning,
   kopiert child-adresse og gamle langsomme skrivinger gir ingen ekstra skriver.
8. Lagrede lenker overlever kontrollert gjenåpning; manglende/erstattet rom gir
   tydelig utilgjengelighet uten nyoppretting.
9. Hele arbeidsflyten prøves i Copilot-appen med syntetiske data og faktiske
   frontendkopier. Lokal browser-/SDK-smoke erstatter ikke nativeprøven.
   Visuell kontroll, tastatur og menneskelig utprøving registreres separat.
10. Avsluttet oppgave med en eid demo lar en ny innspillsrunde starte normalt.
    Normal avslutning og avbrudd stopper bare eid arbeid uten uønsket restart.
    To samtidige canvas prøves også når den valgte, gjenåpnede instansen lukkes.

Beslutningen gir rammer for implementeringen. Den er ikke en påstand om at
akseptpunktene er oppfylt eller en godkjenning av release.
Observerte resultater, åpne funn og nødvendige porter samles i
[leveringsgrunnlaget](../testing/designverksted-release-readiness.md).

## Referanser

- [Appadapter og innsendingskontrakt](0022-app-canvas-adapter.md).
- [Prosjektlagrede designrom](0023-prosjektlagret-designrom.md).
- [Agentic UI: proxy for lokale apper](https://github.com/navikt/agentic-ui-canvas/blob/ce79929f5d2b27cc5610690bca19c4450dd530b6/docs/adr/0001-instrument-previews-through-a-loopback-proxy.md).
