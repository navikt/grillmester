---
name: design-prototype
description: "Explore running local apps, visual concepts and user flows in Designverksted or Figma; read saved design rooms for implementation or briefs. Use `prototype` for uncertain data/state/failure contracts and `figma-workflow` for a chosen Figma design to code or brief."
---
# Fra designspørsmål til synlig resultat

> **OpenCode v1:** Skill names below are exact IDs from the active catalog, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Utforsk konsepter, hierarki og brukerflyt i den arbeidsflaten designeren ønsker.
Et lagret designrom kan være ferdig leveranse; Figma er ingen obligatorisk
neste fase. En eksisterende demo åpnes som den kjørende appen, ikke som en
HTML-rekonstruksjon. Behold lette HTML-skisser for nye konsepter og gamle rom.
Et konkret designønske i samtalen eller en innsendt runde innenfor oppgaven gir
normalt et synlig, avgrenset forslag. I et apparbeid finnes **Appen nå** og **Forslag**
i samme verksted; bruk `publish_proposal`, ikke et ekstra canvas. Rene
spørsmål, observasjoner, «bare review» og «ingen HTML» bestiller ikke en skisse.
En uttrykkelig bestilling om å lagre verkstedet/arbeidet omfatter også forslaget
i det avtalte designområdet; gjenbruk valget uten nytt spørsmål. Bare lagring av
innspill, eller et allerede lagret approm, bestiller ikke skissefiler. Uten avtalt
lagring er oppfølgingen midlertidig uten nytt lagringsspørsmål; si det én gang.
En ny selvstendig skisseoppgave følger lagringsavklaringen i designromreferansen.
Senere lagring av et midlertidig forslag i et lagret approm bruker `save_proposal`
i samme verksted, med innspill og historikk intakt; følg designromreferansen.
Handlingen oppgraderer ikke et helt midlertidig approm.
Merk syntetiske tilstander: forslaget beviser ikke appens validering eller backend.
Bruk `prototype` når spørsmålet gjelder en usikker datamodell,
tilstandsmaskin eller feilkontrakt, ikke bare fordi designunderlaget kjører.
En skisse med simulerte situasjoner beviser ikke backendlogikk. Bruk `figma-workflow` når et
valgt Figma-design skal oversettes til kode eller implementeringsbrief.

## Implementering eller brief fra lagret designrom

Når bestillingen er å implementere eller lage en brief fra et lagret designrom,
les [overleveringsreferansen](references/design-handoff.md) direkte. Avklar først
om rommet gjelder en app eller en skisse. For en skisse, les valgt
registrert HTML-/descriptor-par og relevante beslutninger som vanlige filer;
rå HTML alene kan mangle lagrede tekst- og kontrollverdier. Verifiser registrert
SHA-256 og byteantall etter overleveringsreferansen før enhver skriving som
avhenger av et lagret par; stopp og rapporter ved avvik. Dette krever ikke
canvas, Node, Figma eller eierskap til rommet. Ikke åpne rommet, start en
previewserver eller endre designfilene for å lese underlaget.

Ved en chatbestilling om å endre et felt designeren har lagret i editoren, i en
ny skisseversjon eller en gjenoppretting i rommet, kan ikke agenten tillate
endringen. Be designeren endre feltet i editoren eller velge **Tillat senere
endring**, og fortsett med resten av bestillingen. Ved implementering eller
brief er en ønsket verdi i produktet et krav i bestillingen, ikke en endring av
rommet, og den krever ingen slik tillatelse.

- **Behold denne delen** → *keep wish*: et vanlig innspill som ber agenten
  beholde en del i neste versjon.
- **Lagret felt** → *preserved field*: editorverdi som sperrer overskriving til
  designeren velger **Tillat senere endring**.
- **Runde** → *round*: en innsendt samling innspill og valg.

Gå deretter tilbake til den aktive agentens implementerings- eller brief-flyt.
Bruk repoets produktkomponenter og verifikasjon; skissens rammeverk og simulerte
handlinger er ikke ferdig produktkode. En bestilling av brief gir ikke mandat
til implementering. Oppstart, visuell iterasjon og avslutning nedenfor gjelder
bare når den arbeidsflaten faktisk er valgt, ikke ved denne leseflyten.

## Velg fra hensikten

Tolk «prototype» fra oppgaven, ikke som en kommando om å åpne alle verktøy.
Les akkurat nok av README, oppstartsoppskrift, brukerhistorie og relevant kilde
for å velge. Ikke anta Next.js, Vite, React eller en bestemt monorepomappe.
Repoets dokumenterte mockkommando og observerte rute er kilden til oppstart.
Bruk eksemplene som beslutningsstøtte, ikke en spørsmålsliste:

| Bestilling | Første nyttige handling | Unngå |
|---|---|---|
| «Kjør demoen» | Følg [appåpning](references/application-opening.md), åpne ønsket side og avslutt etter åpningskontrollen. | Automatisk visuell review eller samspillstest; skisser når bare visning er bestilt. |
| «Løs denne brukerhistorien» | Les mål/akseptkriterier og eksisterende flyt; lag et avgrenset forslag når design er oppgaven. | Å kalle skissen implementert eller løst produktkode. |
| «Prototype dette skjemaet» | Bruk relevant eksisterende skjema som referanse og vis et forslag i samme verksted. | Krav om et dummyinnspill før en chatbestilling kan utføres. |
| «Drodle», «vis to retninger» | Skissér direkte med nødvendig kildekontekst, også i et eksisterende apprepo. | Demooppstart før retning er valgt, eller nye lagringsspørsmål når midlertidig arbeid er bestilt. |
| «Review dette, ingen endringer» | Undersøk og gi konkrete funn. | Automatisk publisering eller nye filer. |
| «Implementer forslaget» | Verifiser valgt lagret versjon etter overleveringsreferansen, eller den tilgjengelige aktuelle midlertidige skissen og bestilte krav. Følg kodebestillingen. | Oppdiktet lagret versjon, krav om ekstra lagring eller endring av et vernet skissefelt som skjult port til implementering. |

Uttrykkelig idéutforsking går foran standardløpet for eksisterende flater.
Start ikke appen bare fordi repoet har en. «Vent med forslag» bevarer appvisning
uten skisse; «midlertidig» bevarer arbeidet uten prosjektlagring. Bare visning
er ferdig når verkstedet bekrefter åpning på riktig rute. Kontrollkravene for
vurdering, skisser og implementering nedenfor utvider ikke denne bestillingen.

Hvis en vesentlig tvetydighet gjenstår, still ett avgrenset spørsmål og fortsett
uavhengig lesing. Ellers si antakelsen kort og arbeid videre. Velg etter hensikt
og faktiske kapabiliteter, ikke fra ordene «prototype» eller «canvas» alene.

## Velg én aktiv arbeidsflate

Gjenbruk bestilt format og avklart retning. Hvis nettleserprototype allerede er
bestilt, start uten å spørre på nytt. Ellers tilby den én gang når et konkret
designspørsmål blir lettere å besvare visuelt; krav og avveininger kan tas i
chatten. Ikke be designeren velge transport, og ikke last alle oppskriftene.

| Bestilling og faktisk kapabilitet | Les før første handling |
|---|---|
| Bare åpne eksisterende lokal app, og klienten tilbyr **Designverksted** (`design-workspace`) | Bare [appåpning](references/application-opening.md). Innspills-, skisse- og feilsøkingsreferanser leses ved behov. |
| Vurdere eller forbedre eksisterende lokal app, og klienten tilbyr **Designverksted** (`design-workspace`) | [Appåpning](references/application-opening.md) når appen trenger oppstart, deretter [innspill og forslag](references/design-workspace.md#running-application) og relevant visuell kontroll. |
| Nettleserskisse, og klienten tilbyr **Designverksted** (`design-workspace`) | [Designrom](references/design-workspace.md): åpning, prosjektlagring, publisering, innspillsrunder, historikk og lukking |
| Nettleserskisse uten canvas, med lokal Node.js ≥ 18 og klienttilgjengelig loopback | [Midlertidig nettleserflyt](references/visual-companion.md): oppstart, private tempstier, CLI-innspill og opprydding |
| Bestilt redigering eller redigerbare komponenter i Figma | Bekreft read og write separat; ved faktisk create/edit-kapabilitet, les [Figma-oppskriften](references/figma-prototype.md). For lagret rom, les hashverifisert registrert par via [overleveringsreferansen](references/design-handoff.md): descriptorens `texts[].value` og redigerbare `controls[].initial` overstyrer HTML-tekst og innstillingsattributter; bygg aldri fra rå HTML alene. |

For eksisterende apper brukes repoets faktiske oppstart og komponenter; bevar
den observerte adressens sti og offentlige query. Uten appstøtte i canvas,
åpne den faktiske appen i tilgjengelig nettleser og ta innspill i samtalen.
Forklar hvilken integrert funksjon som mangler. Bytt ikke ut appen med en statisk
skisse uten et avtalt formatbytte. Forslag-fanen beholder Appen nå som referanse; den erstatter ikke den kjørende appen.

Bruk klientens faktiske verktøy og skjemaer. Start ikke ekstra previewserver eller
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

Lesing og analyse er read-only. Bare den portable flyten uten canvas skriver
HTML direkte til privat `screen_dir` fra aktiv startup-JSON utenfor repoet.
Canvas-skisser og Forslag publiseres gjennom den eide canvasens handlinger. Når brukeren har
bestilt lagring eller videre arbeid i et designrom, skriver canvas-handlingene
skisseversjoner og innspill i avtalt prosjektmappe. Overskriv aldri historiske
revisjonsfiler. Et designrom gir ikke alene mandat til å endre produktkode.
Appflyten prøver og kommenterer; den har ingen kildeeditor, appversjoner eller
angre. Appinnspill gir ikke mandat til endringer i produktkode. Separat bestilt kodearbeid
utføres utenfor canvas i en uttrykkelig eid kopi, med avgrenset filomfang og
kontroll av at den kjørende serveren faktisk bruker kopien. En Git-worktree
alene beviser ikke at mappen er disponibel. Bevar originalprosjektet og
urelatert arbeid, og gjenbruk mandat som allerede gjelder denne endringen.
Lagring av innspill gjør ingen Git- eller publiseringshandling.

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

Når oppgaven er å forbedre en konkret eksisterende flate, kontroller faktisk
visuell nåtilstand før du trekker konklusjoner om den og lager et verifisert
forslag. En uttrykkelig idé-/retningsbestilling trenger ikke demooppstart:

- Bruk kilden bestillingen gjelder: faktisk app ved appoppgave, valgt Figma-node
  ved Figma-oppgave, ellers en annen tillatt visuell kilde eller et skjermbilde. Verifiser riktig side/node. Ikke
  rekonstruer den fra kode og presenter rekonstruksjonen som dagens løsning.
- Bruk en faktisk tilgjengelig nettleserkapabilitet. I Designverksted, følg
  [visuell kontroll](references/design-workspace.md#inspect-the-rendered-sketch):
  åpne arbeidsflaten tidlig og kontroller samme visning, eller bruk tilgjengelig
  usynlig, lesende kontroll av samme side/versjon. Ikke åpne en ekstra synlig
  kontrollfane. Playwright er ett alternativ, ikke et krav. Mangler tillatt
  visuell kontroll, si det én gang og be om målrettet underlag bare når et
  konkret designvalg avhenger av det. Fortsett uavhengig behovsavklaring.
- Fjern ufarlig modal-/cookiestøy før bilde; ikke omgå innlogging eller utfør
  produktoperasjoner. Delte bilder skal være redigert for personopplysninger.
  Figma-import krever eget skrivemandat.
- Sammenlign før/etter ved sammenlignbart utsnitt, viewport, innhold og data.
  Kontroller at brukte bilder faktisk lastes (`naturalWidth > 0`). En ren
  Figma-oppgave trenger ingen nettleserøkt.

## Skisser og vurder resultatet

Lag den minste sammenhengende skissen som svarer på spørsmålet, og kontroller
gjengivelsen før du melder den klar. En synlig skisse uten visuell kontroll
er et ukontrollert utkast, ikke en verifisert leveranse. Ved åpent retningsvalg, lag strukturelt ulike
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
  publisering, innspill og skissens avgrensede editor. Knapper skal ha en reell,
  deklarert lokal handling eller merkes ved selve kontrollen som statiske
  eksempler; et banner langt unna er ikke nok. Teksten skal svare til utfallet:
  «Se eksempler (36 svar)» når bare noen få eksempler kan åpnes, ikke «Les 36 svar».
  Simulert kvittering skal ikke se ut som en faktisk innsending.
- Merk illustrative tall og foreslåtte terskler ved vurderingen de brukes til.
  Ikke gi dem mer sikkerhet gjennom rangering, farger eller konklusjoner enn
  underlaget tillater. Skill mengde svar fra alvorlighet og fra sikker kunnskap.
- Kontroller relevant layout ved faktisk smal panel-/innholdsbredde, ikke
  bare stor nettleserbredde. Se etter skjult viktig innhold, kollisjoner,
  lange tekster og tetthet. Kontroller berørte normal-, feil-, tom- og
  bekreftelsestilstander og tastatur/fokus for endrede handlinger. Full
  kontroll av uendret flyt trengs ikke ved hver liten rettelse.
- Gi tette tabeller og grafer en uttrykt smalskjermstrategi: stablede kort,
  prioriterte kolonner eller et navngitt rulleområde (`role="region"`,
  `aria-label`, `tabindex="0"`) med synlig rullehint. Kontroller ved 320 px og
  200 % zoom at sidens bredde ikke flyter over, og at verdier fortsatt kan leses.
- Knytt kritikk til konkret element og observert tilstand. Skill målt feil,
  designavveining og hypotese til brukertest. Inspiser utsnitt og tilgjengelig
  scrolling før innhold omtales som manglende. Et panel gir perspektiver,
  ikke observerte brukerreaksjoner.
- Ved kosmetikk eller språkvask, kontroller at berørte tall, meningsbærende
  tekst, komponenttilstander og delene designeren ba om å beholde ikke ble
  endret utilsiktet.

Følg innspillsløkken for den valgte arbeidsflaten. La skissen stå i ro mens
innspill samles. Les full innsendt runde og riktig versjon; usendte notater er
ikke bestillinger. Endringer publiseres og verifiseres før de meldes fikset.
Spørsmål og bekreftelser besvares uten ny versjon. Bevar innsendte valg og
manuelle føringer; frigiv dem aldri bare fordi du lager neste skisse.


Vurder leveransen med fire enkle spørsmål: Viser den riktig oppgave? Kan neste
steg forstås uten teknisk forklaring? Er det mulig å prøve de relevante valgene?
Er det tydelig hva som er simulert eller uavklart? Et godt resultat trenger
ikke flere funksjoner; fjern friksjon før du legger til nye alternativer.

## Lever og avslutt i den valgte flaten

Returner bare URL/Figma-lenke som faktisk finnes, eller prosjektsti og eksakt
valgt versjon når overleveringen trenger det. I verkstedets vanlige svar holder
det med hva designeren kan prøve under Forslag; hold interne ID-er og stier i
verktøykall og eventuell avtalt overlevering. Bevar en observerbar referanse til
retningen: skjermbilde når mulig, ellers kildepar/versjon og eksplisitt valg.
Merk utkast, gjenstående spørsmål og det som ikke er verifisert. Et midlertidig
forslag lover ikke gjenåpning etter samtaleøkten. Opprett Issue bare med mandat; inkluder valgt design, tilstander, komponenter og UU-funn.

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
