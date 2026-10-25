---
name: design-prototype
description: "Explore visual concepts, user flows and Figma designs, or read a saved design room as implementation or brief input. Use for layout, hierarchy and visual alternatives; use `prototype` for executable behavior and `figma-workflow` for a chosen Figma design to code or brief."
---
# Fra designspørsmål til synlig skisse

> **OpenCode v1:** Skill names below are exact IDs from the active catalog, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Utforsk konsepter, hierarki og brukerflyt i den arbeidsflaten designeren ønsker.
Et lagret designrom kan være ferdig leveranse; Figma er ingen obligatorisk
neste fase. Bruk `prototype` når usikkerheten gjelder faktisk kjørbar
oppførsel, datamodell, tilstandsmaskin eller feilkontrakt. En skisse med
simulerte situasjoner beviser ikke backendlogikk. Bruk `figma-workflow` når et
valgt Figma-design skal oversettes til kode eller implementeringsbrief.

## Implementering eller brief fra lagret designrom

Når bestillingen er å implementere eller lage en brief fra et lagret designrom,
les [overleveringsreferansen](references/design-handoff.md) direkte. Les valgt
registrert HTML-/descriptor-par og relevante beslutninger som vanlige filer;
rå HTML alene kan mangle lagrede tekst- og kontrollverdier. Verifiser registrert
SHA-256 og byteantall etter overleveringsreferansen før enhver skriving som
avhenger av et lagret par; stopp og rapporter ved avvik. Dette krever ikke
canvas, Node, Figma eller eierskap til rommet. Ikke åpne rommet, start en
previewserver eller endre designfilene for å lese underlaget.

Ved en chatbestilling om å endre et felt designeren har lagret i editoren, kan
ikke agenten tillate endringen. Be designeren endre feltet i editoren eller velge
**Tillat senere endring**, og fortsett med resten av bestillingen.

- **Behold dette** → *kept choice*: ber agenten beholde en del av skissen.
- **Lagret felt** → *preserved field*: editorverdi som sperrer overskriving til
  designeren velger **Tillat senere endring**.
- **Runde** → *round*: en innsendt samling innspill og valg.

Gå deretter tilbake til den aktive agentens implementerings- eller brief-flyt.
Bruk repoets produktkomponenter og verifikasjon; skissens rammeverk og simulerte
handlinger er ikke ferdig produktkode. En bestilling av brief gir ikke mandat
til implementering. Oppstart, visuell iterasjon og avslutning nedenfor gjelder
bare når den arbeidsflaten faktisk er valgt, ikke ved denne leseflyten.

## Velg én aktiv arbeidsflate

Gjenbruk bestilt format og avklart retning. Hvis nettleserprototype allerede er
bestilt, start uten å spørre på nytt. Ellers tilby den én gang når et konkret
designspørsmål blir lettere å besvare visuelt; krav og avveininger kan tas i
chatten. Ikke be designeren velge transport, og ikke last alle oppskriftene.

| Bestilling og faktisk kapabilitet | Les før første handling |
|---|---|
| Nettleserskisse, og klienten tilbyr **Designverksted** (`design-workspace`) | [Designrom](references/design-workspace.md): åpning, prosjektlagring, publisering, innspillsrunder, historikk og lukking |
| Nettleserskisse uten canvas, med lokal Node.js ≥ 18 og klienttilgjengelig loopback | [Midlertidig nettleserflyt](references/visual-companion.md): oppstart, private tempstier, CLI-innspill og opprydding |
| Bestilt redigering eller redigerbare komponenter i Figma | Bekreft read og write separat; ved faktisk create/edit-kapabilitet, les [Figma-oppskriften](references/figma-prototype.md). For lagret rom, les hashverifisert registrert par via [overleveringsreferansen](references/design-handoff.md): descriptorens `texts[].value` og redigerbare `controls[].initial` overstyrer HTML-tekst og innstillingsattributter; bygg aldri fra rå HTML alene. |

I appen brukes det tilgjengelige Designverksted-canvaset for nettleserskisser.
Bruk klientens faktiske verktøy og skjemaer. Start ikke ekstra server eller
`comments.js wait` ved siden av canvas-leveringen. En feil i et annonsert
canvas er ikke bevis på at kapabiliteten mangler: les feilen og gjeldende
binding, og bevar rommet. Ikke bytt automatisk til en konkurrerende skriver
eller midlertidig økt. Et senere bestilt bytte av arbeidsflate er mulig; avklar
hvilken versjon som skal være førende og hvilke lagrings-/innspillsegenskaper
som følger med.

Når du skal skrive HTML, les `aksel-design` og de relevante felles avsnittene
om [Aksel-markup](references/visual-companion.md#aksel-korrekthet-viktig) og
[deklarerte interaksjoner](references/visual-companion.md#justerbare-skisser).
Canvas bruker disse innholdsreglene, ikke den portable oppstarts- og
innspillsløkken. En lesegjennomgang eller bekreftelse trenger ikke laste hele
markup-katalogen. Gjenbruk verifiserte komponenter og stiler for uendret prosjekt
og pakkeversjon; les på nytt ved ny komponent eller konkret avvik.

## Mandat og grenser

Lesing og analyse er read-only. Midlertidig nettleservisning skriver bare til
privat `screen_dir` fra aktiv startup-JSON utenfor repoet. Når brukeren har
bestilt lagring eller videre arbeid i et designrom, skriver canvas-handlingene
skisseversjoner og innspill i avtalt prosjektmappe. Overskriv aldri historiske
revisjonsfiler. Designrom gir ikke mandat til å endre produktkode.

Figma-, Issue- og andre eksterne writes krever eksplisitt mandat for mål,
handling og omfang. Brukerens konkrete bestilling kan gi mandatet; gjenbruk det
for nødvendige operasjoner. Ved manglende mandat eller et vesentlig valg: vis
mål og utkast og spør bare om det som mangler. Nye mål eller utvidet omfang
trenger eget mandat; fasebytte trenger ingen ny godkjenning. Ikke opprett
branch, commit, push, pull request eller deploy automatisk.

Bruk bare representative, syntetiske data og redigerte skjermbilder uten ekte
personopplysninger, secrets eller autentisert produksjonsinnhold. Installer
ikke pakker eller utvidelser, endre klientinnstillinger, `.gitignore` eller
lockfiler, eller feilsøk bygg som del av preview. Nødvendig oppsett må være en
separat bestilt endring innenfor agentens mandat.

## Forstå og vise det som skal endres

Start med ett navngitt designspørsmål: hva skal brukeren finne, forstå eller
gjøre, og hva vil utforskingen hjelpe designeren å velge? En avklart liten
endring trenger ikke nytt intervju, flere alternativer eller en egen plan.

Ved endring av en eksisterende flate, kontroller faktisk visuell nåtilstand
før første forslag. Ved tvil om siden er ny eller eksisterende, behandle den
som eksisterende:

- Bruk valgt Figma-node; ellers en tilgjengelig lokal app, annen tillatt
  visuell kilde eller et skjermbilde. Verifiser riktig side/node. Ikke
  rekonstruer den fra kode og presenter rekonstruksjonen som dagens løsning.
- Bruk en faktisk tilgjengelig nettleserkapabilitet, inkludert innebygd
  nettlesercanvas. Playwright er ett alternativ, ikke et krav. Mangler alle
  tillatte visuelle kilder, be om skjermbilde og merk hva som ikke kan vurderes.
  Fortsett uavhengig behovsavklaring.
- Fjern ufarlig modal-/cookiestøy før bilde; ikke omgå innlogging eller utfør
  produktoperasjoner. Delte bilder skal være redigert for personopplysninger.
  Figma-import krever eget skrivemandat.
- Sammenlign før/etter ved sammenlignbart utsnitt, viewport, innhold og data.
  Kontroller at brukte bilder faktisk lastes (`naturalWidth > 0`). En ren
  Figma-oppgave trenger ingen nettleserøkt.

## Skisser og vurder resultatet

Lag den minste sammenhengende skissen som svarer på spørsmålet, og kontroller
gjengivelsen før du viser den. Ved åpent retningsvalg, lag strukturelt ulike
alternativer i antallet spørsmålet trenger; ulik farge eller ordlyd alene er
ikke en ny retning. Behold valgt retning ved detaljjustering. Bruk samme
representative datasett og omtrent samme innholdstetthet for rettferdig
sammenligning. Be designeren vurdere hvordan alternativene støtter oppgaven,
ikke bare hvilken de liker best. Fang valgt retning og begrunnelsen.

Skaler fidelitet og kontroll etter det som endres:

- Bruk verifisert Aksel-markup og tokens i HTML-skisser. Snapshotet i
  [markup-referansen](references/aksel-markup-fasit.md) er en versjonert
  startreferanse; installert pakke, aktuell dokumentasjon og rendret DOM vinner
  ved avvik. Uten kompatible stiler, vis ærlig fallback/wireframe. Lastet CSS
  alene beviser ikke riktig font eller komponentfidelitet.
- Deklarer bare meningsfulle direkte justeringer. Følg valgt oppskrift for
  publisering, beholdte valg og source editing. Knapper skal ha en reell,
  deklarert lokal handling eller tydelig være statiske eksempler. Simulert
  kvittering skal ikke se ut som en faktisk innsending.
- Kontroller relevant layout ved faktisk smal panel-/innholdsbredde, ikke
  bare stor nettleserbredde. Se etter skjult viktig innhold, kollisjoner,
  lange tekster og tetthet. Kontroller berørte normal-, feil-, tom- og
  bekreftelsestilstander og tastatur/fokus for endrede handlinger. Full
  kontroll av uendret flyt trengs ikke ved hver liten rettelse.
- Knytt kritikk til konkret element og observert tilstand. Skill målt feil,
  designavveining og hypotese til brukertest. Inspiser utsnitt og tilgjengelig
  scrolling før innhold omtales som manglende. Et panel gir perspektiver,
  ikke observerte brukerreaksjoner.
- Ved kosmetikk eller språkvask, kontroller at berørte tall, meningsbærende
  tekst, komponenttilstander og beholdte valg ikke ble endret utilsiktet.

Følg innspillsløkken for den valgte arbeidsflaten. La skissen stå i ro mens
innspill samles. Les full innsendt runde og riktig versjon; usendte notater er
ikke bestillinger. Endringer publiseres og verifiseres før de meldes fikset.
Spørsmål og bekreftelser besvares uten ny versjon. Bevar innsendte valg og
manuelle føringer; frigiv dem aldri bare fordi du lager neste skisse.

## Lever og avslutt i den valgte flaten

Returner bare URL/Figma-lenke som faktisk finnes, eller prosjektsti og eksakt
valgt versjon. Bevar en observerbar referanse til retningen: skjermbilde når
mulig, ellers kildepar/versjon og eksplisitt valg. Merk utkast, midlertidig
lagring, gjenstående spørsmål og det som ikke er verifisert. Opprett Issue bare
med mandat; inkluder valgt design, tilstander, komponenter og UU-funn.

Kontroller relevant kontrast, klarspråk og semantikk før designleveranse.
Dette er en UU-forhåndssjekk. Full live-kontroll av implementert UI følger
`accessibility-review` før release. Ved bestilt Figma-leveranse skal komponenter
være redigerbare, tilstander helst samles på en `Tilstand`-akse, og resultatet
sammenlignes med avtalt kilde/retning. Bruk aktivt Aksel-bibliotek og
Figma-referansens preflight og kontekstregler.

Mangler nødvendig kapabilitet, oppgi konkret hva som ikke kan gjøres. Uten
Figma-write kan du levere avtalt skisse eller Figma-/Issue-utkast, ikke en
påstått opprettet fil. Når canvas ikke tilbys og den midlertidige nettleserflyten
mangler lokal Node eller tilgjengelig loopback, bruk chat eller bestilt
Figma-flyt; ikke installer eller lag en omvei. Dette er ikke en grunn til å
forlate et fungerende canvas. Manglende Figma endrer ikke en bestilt
nettleserleveranse.

Følg den valgte oppskriftens opprydding: midlertidig serverøkt avsluttes gjennom
den eksakte sesjonen som startet den. Canvas lukkes gjennom panelets
lukkehandling; klienten eier prosessen og prosjektlagret designrom bevares.
