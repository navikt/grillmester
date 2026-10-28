# Designverksted: grunnlag for native levering

Status 28. oktober 2026: Native kjerneløp er prøvd i Copilot app 1.1.33 på
macOS. Det gir grunnlag for videre leveringsarbeid, ikke en erklæring om at
alle porter nedenfor er bestått. Nye rettelser må få egne resultater mot den
endelige kilderevisjonen; tidligere prøvebevis gjelder innholdet som ble prøvd.

## Avgrenset leveranse

Appen nå, bevisste innspillsrunder og ett HTML-forslag hører til samme canvas
og samtale. Forslaget har egne runder og lagrede versjoner. Ingen appkilde
endres fra flaten. Direkte idéutforsking kan gi midlertidige skisser uten
demooppstart; bare-visning bestiller ikke et forslag.

Den første nativeleveransen har ingen ekstern nettlesertransport. Den private
rendereradressen skal aldri brukes i en annen nettleser. En senere valgfri
nettleserflate trenger egen originisolasjon og tydelig skriveransvar.
Støtteomfanget er den undersøkte nativeverten. SDK-ets canvasstøtte er ingen
garanti for lagringspartisjonering, og andre verter eller versjoner er ikke
dekket automatisk. Se [tillitsgrensene](../trust-and-client-support.md#designverksted-og-overlevering-mellom-klienter)
og [ADR 0027](../adr/0027-designverksted-for-kjorende-apper.md).

## Hva som faktisk er prøvd

Tidligere nativeprøver og Lumi-prøvene gjelder ulike kandidater. Siste
gjennomførte Lumi-prøve omfatter hele innspillsløkken nedenfor. Gjenåpning i en
ny samtale med den forkortede åpningsreferansen er også bekreftet. En ny runde
etter gjenåpningen startet automatisk og ga versjon 3 med bare den bestilte
setningen fjernet. Samspillet var beholdt.

| Bevis | Resultat og grense |
| --- | --- |
| Tidligere native kjerneløp | Kjørende app, appinnspill, automatisk oppfølging, klikkbart forslag i samme canvas, skisseinnspill og synlig versjon 2 bestod. |
| Tidligere apptransport i native | Faktisk MSW-avskjæring og oppstrømskall bestod. HMR-endringen var synlig med feltverdi beholdt; dokumentidentitet ble ikke målt i native. |
| Tidligere lagret arbeid | Ny instans åpnet lagret approm og forslag v2 med begge runder og svar. Ingen replay ble observert. Lagrede runder, kildekoblinger og versjonsdigester ble kontrollert separat; dette er ikke en påstand om identiske workspace-filer. |
| Tidligere prøve med to samtidige canvas | B virket etter lukking av A. Etter senere lukking av valgt A2 ble B stående på vertens «Loading canvas…». Den kom tilbake før diagnosehandlingen kjørte, og et nytt serverkall virket. Årsaken er ukjent. |
| Tidligere naturlige bestillinger | Bare-visning åpnet appen, og en presis senere tekstrevisjon bestod. En midlertidig bestilling om to retninger startet først demoen og trengte én presisering. |
| Tidligere innspill mens samtalen var opptatt | En runde ble stående i kø etter synlig sluttforklaring mens demoserveren var en aktiv bakgrunnsjobb. Manuell videreføring startet riktig runde. Sammenhengen med serverjobben er ikke bevist som årsak. |
| Lumi: bare-visning før pause | Appen åpnet i samme native canvas, «Vis mer» virket, og ingen forslag ble laget. Samtalen ble Idle mens demoen fortsatt kjørte gjennom den eide CLI-hjelperen. Unødvendig analyse av mockdata etter åpningen gjorde at hensikten med bare-visning ikke bestod. Innspillsutkastet ble verken lagret eller sendt før pausen; automatisk videreføring er derfor ikke prøvd med denne kandidaten. |
| Siste Lumi-prøve: oppstart | Den eide CLI-hjelperen startet demoen, appen åpnet i ett native canvas, og samtalen ble Idle mens demoen fortsatt virket. «Vis mer» åpnet syntetiske svar. Ingen forslag eller ekstra mockanalyse ble laget ved bare-visning. |
| Siste Lumi-prøve: appinnspill → forslag | Sending fra appflaten viste status umiddelbart og gikk tilbake til Prøv. Én automatisk oppfølging startet uten chatmelding eller «Send now». Appen kunne brukes under arbeidet. Forslaget kom under Forslag i samme canvas; knappen viste tre oppdiktede eksempelsvar, med synlig merking av eksempeldata. |
| Siste Lumi-prøve: forslag → revisjon | Et punktinnspill om overskriften startet neste oppfølging automatisk. «Vis oppdatert forslag» viste versjon 2. Lagret HTML-diff viste bare den bestilte overskriftsendringen; temaene var beholdt, og eksempelknappen virket fortsatt. |
| Siste Lumi-prøve: eksplisitt avslutning | Designer stoppet den eide demoen; porten stengte uten observert restart. Testeren lukket canvaset med UI-knappen etter at Designer opplyste at et lukkeverktøy manglet. Prøven beviser ikke at samtalen alene kan lukke flaten. |
| Lumi: ny samtale og gjenåpning | Ett native canvas viste appen og lagret forslag v2. Appens gamle runde viste «Fra tidligere samtale. Sendes ikke på nytt.». «Vis forslag» åpnet v2, eksempelknappen virket, og forrige skisserunde var besvart med kommentaren markert som fulgt opp. Ingen replay ble observert. |
| Lumi: nytt innspill etter gjenåpning | Et nytt punktinnspill i forslaget ble sendt uten chatmelding og startet automatisk oppfølging. Versjon 3 fjernet bare den bestilte avsnittslinjen; øvrige bytes var uendret. Den nye versjonen var synlig, og eksempelknappen virket fortsatt. |
| Eksakte releaseklienter på macOS arm64 | Checksumkontrollerte OpenCode 1.18.20, Copilot CLI 1.0.80 og cplt 2026.08.17-062831-1008a92 ble installert isolert. Discovery, runtime og alle fire lokale focused/full-scenarier bestod, inkludert npm- og GitHub-guardprøver. To feil i testharnesset ble rettet og uavhengig gjennomgått; produkt/runtime og sikkerhetsgrenser ble ikke endret. Annen arkitektur er ikke bevist av denne kjøringen. |
| Lokal protokoll og rendering | Adapter, proxy, HTML-barn, lagring og browserflyt ble prøvd med syntetiske data og simulert samtalevert. Faktisk MSW/HMR, gammel myndighet etter close/proxytap og pågående action ved close ble kontrollert. Dette beviser ikke nativevertens panelhåndtering eller samtalekø. |

Oppstarten hadde fortsatt mange tekniske mellomoppdateringer og interne
stier, også etter at den forkortede åpningsreferansen ble brukt. Et tidligere
sluttsvar sa at forhåndsvisning manglet selv om forslaget var synlig. Med
presisert svarveiledning hadde siste sluttsvar tre korte setninger, ingen
interne stier og en korrekt grense for manglende visuell kontroll. Skissens
misvisende plassholder ble fjernet gjennom innspillet etter gjenåpningen.
Dette er en målt forbedring i siste svar, ikke bevis for konsekvent god
språkføring. Den tekniske kjerneløkken er prøvd; sømløs bred utrulling er
fortsatt ikke bekreftet.

Forskjellige feltverdier alene beviser ikke lagringsisolasjon. En separat
browserprøve eller vellykket HTTP-respons er heller ikke native visuell kontroll.
Prøvene er praktisk gjennomføring og teknisk verifikasjon, ikke en brukertest
med uavhengige designere eller en skjermleserprøve.

## Porter før utrulling

1. **Samlet innhold og beslutning.** Samordne runtime, Designer-veiledning,
   README og tillits-/arkitekturbeskrivelse. Ingen påstand om automatisk
   behandling fra `queued`, fungerende gjengivelse fra readiness eller ny
   lagringskontekst fra iframe-retry. Behold én synlig arbeidsflate og oppgi
   manglende visuell verifikasjon konkret.
2. **Demoens levetid.** Prøv både forhåndsstartet demo og demo startet fra
   samtalen gjennom [den eide CLI-hjelperen](../adr/0028-eid-livslop-for-lokale-demoer.md).
   Hjelperens lokale prosessregresjoner erstatter ikke prøven av samtalekøen.
   Første oppgave må kunne avsluttes mens appen brukes, og en ny
   innspillsrunde må starte én gang. Prøv uttrykkelig avslutning og avbrudd:
   bare eid arbeid skal stoppes, uten uønsket restart. En URL og pinnet DNS er
   ikke bevis for prosessidentitet; restart eller tapt eierskap krever at
   tilhørende nativevisninger avsluttes før ny tilkobling.
3. **Native livsløp etter rettelser.** Prøv hele app–forslag–revisjon-løkken
   på endelig kandidat. Åpne A og B, lukk A mens B brukes, gjenåpne lagret A
   som A2, og lukk valgt A2 før retur til B. Krev ny interaksjon og nytt
   serverkall fra B. Dokumenter eventuelt panelheng som et åpent avvik.
   Prøv også reload, gamle kapabiliteter, lagrede runder og ingen replay.
4. **Kilde- og nettverksgrenser.** Bruk eide, disponible testkopier og
   syntetiske data. Oppstart kan skrive frameworkmetadata og låsefiler;
   registrer før-/etter-tilstand og bevar originalene. Ikke endre
   sandboxpolicy som automatisk reparasjon. Skill bind/listen, direkte
   lokaltilkobling og rendererlasting i feilsøkingen.
5. **Lokal regresjon og determinisme.** Kjør de påkrevde kontrollene i
   [AGENTS.md](../../AGENTS.md), inkludert app- og workbenchsmoke, Python,
   Node, manifestvalidering og alle generatorer. Generer fra kanoniske
   kilder og kontroller identiske resultater over to kjøringer. Gjennomgå
   nye failures; ikke skjul rettighetsporter som miljøfeil.
6. **Eksakte releaseklienter.** Bruk den checksumverifiserte kontrakten i
   [release_test_baseline.py](../../scripts/release_test_baseline.py):
   OpenCode 1.18.20, Copilot CLI 1.0.80 og cplt
   2026.08.17-062831-1008a92. Minimumskompatibiliteten med Copilot CLI
   1.0.79 prøves separat. Begge macOS-arkitekturer og alle fire
   focused/full-scenarier må gjennomføres med deterministisk loopbackprovider,
   isolerte hjem og disponibelt consumer-repo. Ingen skymodell eller ambient
   providercredential skal brukes. Den isolerte macOS arm64-kjøringen beskrevet
   over bestod med eksakte klienter; den erstatter ikke den andre arkitekturen
   eller minimumsklientprøven. En nyere appbundet CLI erstatter ikke gaten.
7. **Rettigheter og releaseidentitet.** Designer, design-prototype og
   PROVENANCE er endret fra journalens tidligere innholdsreview. Endelig
   innhold trenger en reell, konkret review før ny binding i
   [stable-rights-approval.json](../../policy/stable-rights-approval.json),
   med underliggende beslutning bevart. En gammel reviewreferanse eller bare
   nye hashverdier er ikke ny godkjenning. Velg ny versjon gjennom
   [bump_version.py](../../scripts/bump_version.py) med den faktiske
   `--rights-review`-referansen etter releaseoppskriften; ikke gjenbruk versjon
   for andre bytes. Denne siden endrer ingen godkjenning eller versjon.
8. **Distribusjon og etterkontroll.** Følg
   [release-runbook](../release-runbook.md): bygg den deterministiske bunten
   to ganger mot eksakt source-SHA, kontroller identiske bytes, manifest og
   løs SHA-256. Verifiser gjeldende beskyttelser og immutable-release-kravet.
   Katalog, tag og publisering skjer bare gjennom den eksisterende flyten.
   Etter publisering kontrolleres eksakt tag/installasjon og oppdatering;
   app-, CLI- og øvrig klientatferd skal ikke utledes fra hverandre.

Lokalt kan kode, dokumentasjon, genererte mål, tester, bundle og reviewgrunnlag
klargjøres før eksterne writes. En ferdig lokal prøve erstatter ikke
innholdsreview, publiseringsporter eller etterkontroll. Rettelser av et
vertsavvik må beskrives som prøvd først når den faktiske sekvensen er gjentatt.
