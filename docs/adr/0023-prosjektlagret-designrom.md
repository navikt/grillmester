---
status: accepted
date: 2026-10-24
---

# Prosjektlagret designrom

## Kontekst

Appadapteren fra [ADR 0022](0022-app-canvas-adapter.md) kobler skissen til en
bestemt samtale, men beholder hittil innholdet i en midlertidig økt. En designer
må kunne lukke arbeidet og senere åpne samme skisse, innspill og beslutninger.
Prosjektlagring er valgt som neste milepæl. Appflyten prioriteres; dette er
ikke et krav om tilsvarende nye grensesnitt i alle terminal- og editorklienter.

Å flytte den private øktmappen inn i prosjektet er utilstrekkelig. Den
inneholder transportopplysninger, slettes ved stopp og oppretter et tomt
innspillslager ved oppstart. Lagring må derfor skille rommets varige innhold
fra den aktive prosessen og samtalen.

## Beslutning

Et designrom opprettes eller åpnes uttrykkelig under den tilknyttede
samtalens faktiske prosjektmappe, normalt `designs/<navn>/`. Opprettelse krever
en tom målmappe; skjulte filer som operativsystemet legger igjen, for eksempel
`.DS_Store`, teller ikke. Åpning av et eksisterende rom validerer hele
tilstanden og det gjeldende skisseparet. Eldre par kontrolleres mot sine
hasher først når de leses eller gjenopprettes, slik at én skadet gammel fil
bare gjør sin egen versjon utilgjengelig. Ugyldige eller ukjente data
overskrives ikke med en ny, tom økt, og skadede filer repareres eller
omskrives ikke. Det finnes ingen import av gamle midlertidige previewøkter.

Rommet består av vanlige prosjektfiler:

- `workspace.json` er den ene autoritative tilstanden: romidentitet, tittel,
  gjeldende versjon, revisjonsregister og samme `FeedbackStore` med kommentarer,
  beslutninger, uforanderlige innsendte runder og deres svar/status.
- `revisions/<filnavn>.html` og en eventuell tilhørende `.design.json` er
  uforanderlige skisseversjoner. Registeret inneholder filhasher, størrelse,
  skjermidentitet og et eksplisitt, sekvensielt revisjonsnummer. Navn som
  aldri kan registreres, for eksempel `.DS_Store`, `._<navn>` og editorens
  bytte- og sikkerhetskopier, ignoreres og teller ikke mot grensene.
- Runtime-token, URL, port, prosess-ID, aktiv samtalebinding og skriverlås
  inngår ikke i prosjektfilene. De forblir midlertidige runtimeopplysninger.

Det innføres ingen speiling av innspillskøen, separat database eller ny
bakgrunnstjeneste. `WorkspaceStore` håndterer filer og skriverett; den
eksisterende `FeedbackStore` eier fortsatt tilstandsendringene. SDK-adapteren
leser og endrer rommet gjennom samme bundne backend.

### Atomisk lagring og revisjoner

En ny revisjon skrives først som nye, eksklusive filer. HTML og deklarerte
kontroller valideres, og hasher beregnes fra de eksakte lagrede bytene. Først
deretter publiseres revisjonen ved én atomisk utskifting av `workspace.json`.
Den gjeldende skissen følger registeret, aldri nyeste filnavn eller mtime.

HTML-filen må fortsatt ha nøyaktig de registrerte bytene. Deklarasjonen
lagres som `JSON.stringify(verdi)` pluss ett linjeskift, og `designHash` gjelder
denne kanoniske formen. En fil som er omformatert, men har samme verdi, godtas
derfor; endret innhold avvises. `workspace.json` leses som JSON og skrives
kompakt igjen ved neste lagring.

Et krasj før tilstandslagringen kan etterlate en ureferert revisjonsfil. Den
blir ikke automatisk gjeldende, gjenbrukt eller slettet. En avvist publisering
kan rydde akkurat sine egne upubliserte filer dersom identitet og innhold
fortsatt stemmer. Refererte eller eksternt endrede filer skal beholdes.

Vellykket `rename` av tilstandsfilen er commitgrensen. En påfølgende feil i
disksynkronisering eller opprydding rapporteres som en allerede utført
lagring med usikker holdbarhet. Minne, retryidentitet og refererte revisjoner
må gjenspeile commiten; feilen kan ikke behandles som en rollback eller et
mandat til å slette innholdet.

Historikk leses i avgrensede sider. Gjenoppretting av en tidligere skisse
oppretter en ny revisjon med referanse til opphavet. Tidligere revisjoner,
innsendte runder og senere innspill slettes eller omskrives ikke. Brukeren
må først fullføre eller forkaste et lokalt utkast og usendte innspill som
ville blitt avbrutt av versjonsbyttet.

### Én skriver og riktig prosjekt

Stien er relativ, avgrenset og uten traversal, skjulte komponenter eller
symbolske lenker. Filer må være vanlige filer uten hardlinkaliaser.
Worktrees bruker hver sin faktiske prosjektmappe; `git-common-dir` og den
aktive samtalen i en annen fane brukes aldri som snarvei til et rom.

Alle egne skrivere tar en prosesslås for det fysiske rommets enhets-/inode-
identitet. Låsen ligger privat i en fast, felles OS-mappe og er uavhengig av
`TMPDIR`, `HOME` og skrivemåten til prosjektstien. Den første implementasjonen
støtter Unix-verter. En annen plattform skal avvises tydelig til tilsvarende
låse- og filgarantier er implementert og prøvd.

En avvist åpning sier hva som er galt, uten å endre filer: rommet er åpent i
en annen økt, en navngitt lagret fil stemmer ikke med registeret, mappen for
et nytt rom er ikke tom, eller verten støttes ikke. En filfeil skal ikke
beskrives som en annen økt. Etter oppstart videreformidles lagringsfeil med
klientstatus til agenten i stedet for en generisk melding.

Hver prosess bruker et unikt claimnavn og en tofaset billettrekkefølge.
Aktive og ukjente eiere avvises; alder alene kan aldri overføre låsen.
Et claim fra en påvist død prosess kan fjernes uten at filnavnet gjenbrukes
av en ny eier. PID-gjenbruk eller uavklart eierskap gir konservativ avvisning.
Ingen separat låseserver eller installert hjelpepakke er nødvendig.

Før lagring kontrolleres katalogidentitet og de sist leste tilstandsbytene
på nytt. En observert endring utenfra gir konflikt. Dette er ikke en atomisk
lås mot en vilkårlig ekstern editor eller Git-operasjon: romfilene skal ikke
redigeres eller sjekkes ut samtidig som rommet er åpent. En filoperasjon
mellom siste sammenligning og rename kan ikke generelt oppdages av denne
kontrakten. Andre worktrees og kopier av rommet er selvstendige filer og
kan ikke overta den opprinnelige runtimebindingen.

### Restart uten ny innsending

Gjenåpning oppretter ny transport og samtalebinding. Den gjenoppretter
lagrede innspill, valg, historikk og svar, men sender ingen av dem på nytt.
Et avbrutt leveringsforsøk har ukjent utfall. En tidligere køkvittering eller
status «under behandling» er historikk fra forrige økt, ikke bevis på at den
nye samtalen arbeider. Grensesnittet må vise dette skillet og beholde svar.

Bare en ny, uttrykkelig brukerhandling kan sende arbeid til den nye samtalen.
Dette gjelder også dersom appen gjenåpner et lagret canvas. Gamle tokens,
forsinkede callbacks og en annen samtale får ingen rettigheter fra innholdet
i `workspace.json`. Stopp, frakobling og utløp rydder transport og egen lås;
de sletter ikke rommet.

### Avgrenset editor og beholdte endringer

En versjon 2 av deklarasjonen tilbyr navngitte tekstfelter og gjør utvalgte
egenskaper redigerbare. Tekstfelter har stabile ID-er, etikett og eksplisitt
verdi. Egenskaper må være merket `editable: true` og beholder de allerede
deklarerte, endelige alternativene. Versjon 1 beholder sin tidligere rolle
som lokal variant- og justeringsutforsking.

Det er høyst 16 tekstfelter og 32 redigerbare felter totalt. Hvert tekstfelt
bruker høyst 2000 UTF-8-byte, og versjon 2-deklarasjonen høyst 24 KiB slik at
felt og beholdte verdier kan leses innenfor transportgrensen. Ingen vilkårlig
CSS, selektorer, skript, attributter eller frie HTML-fragmenter inngår.

En lagret manuell endring lager en ny skisseversjon og en varig føring i samme
tilstandsovergang. Det sender ingen melding. HTML og sidecar er den parede
kanoniske kilden; rå HTML alene er ikke en full eksport av endringene.
Forhåndsvisningen bruker de deklarerte verdiene gjennom støttede bindinger.
Et manglende, duplisert eller ustøttet felt skal ikke fremstå som vellykket
redigert. Verdien og føringen må bevares mens avviket synliggjøres.

Regenerering kan ikke stilltiende endre eller fjerne en manuell føring. Den
må bevare feltets betydning og verdi, eller avvises som konflikt som må
avstemmes. Bare en uttrykkelig brukerhandling kan frigjøre en føring.
Publisering, historikkgjenoppretting og behandlingsstatus gir ikke slik
frigivelsesrett. Revisjonskontroll beskytter mot at en eldre editorvisning
overskriver en nyere manuell endring.

### Grenser og brukerens mandat

Tilstandsfilen er høyst 2 MiB; hver HTML-fil høyst 2 MiB og hver deklarasjon
høyst 32 KiB. Rommet har høyst 100 skisseversjoner og 64 MiB samlet innhold.
De eksisterende grensene på 200 kommentarer, beslutninger og innsendte runder
videreføres. Ingen historikk kastes automatisk for å gi plass. Gjenåpning må
også fungere ved en full, ellers gyldig tilstand; gjenopprettingsmetadata må
ikke kreve ledig innholdsplass som ikke var reservert ved lagring. Fordi en ny
økt åpner det samme fulle rommet, peker grensemeldingene i et lagret rom på et
nytt rom (og for kommentarer på sletting av eldre), ikke på en ny økt.

Nye filer opprettes med private rettigheter, men vanlige klonede prosjektfiler
med leseadgang for andre kan åpnes. Eksisterende rettigheter endres ikke.
Rommet kan følge prosjektets vanlige versjonskontroll, men opprettelse av
rommet gjør ingen branch, commit, push eller publisering.

Versjonskontroll forutsetter at rommappen holdes utenfor prosjektets
formatering og linjeskiftkonvertering. Det betyr unntak i formaterer og
pre-commit-hooks (for eksempel Biome, Prettier og end-of-file-fiksere) og
`-text` i `.gitattributes`, for eksempel `designs/** -text`. Romfilene leses
skrivebeskyttet og lagres aldri fra en editor. Disse unntakene er endringer i
forbrukerrepoet og gjøres bare når brukeren ber om det. En omformatert
deklarasjon og fremmede filer i `revisions/` tåles, men en endret HTML-fil
kan bare hentes tilbake fra versjonskontroll.

Design-skillens tidligere absolutte regel om at all previewlagring skjer
utenfor repoet avgrenses: bestilt prosjektlagring gir mandat til det valgte
designrommet. Det gir ikke mandat til produktkode, avhengigheter, Figma eller
andre eksterne mål. Midlertidig preview uten valgt rom beholder sin gamle
opprydding. Skill og grensesnitt må si hva som er lagret varig, hva som bare
er et lokalt utkast, og at **Send** er en egen handling.

## Avgrensning og aksept

Dette steget gir varige skisser, gjennomgang og deklarerte redigeringsfelter,
ikke fri layoutredigering eller automatisk tilbakeskriving til produktkode.
Eksisterende tekstforslag i innspill er fortsatt forslag og må skilles fra
lagrede editorendringer. DOM-posisjoner alene er ikke varige
redigeringsidentiteter.

Uforanderlige HTML-/deklarasjonsfiler garanterer heller ikke identiske piksler
etter endring av prosjektets eksterne stilavhengigheter. Stil- og
designsystemversjonering er en egen avgrensning dersom det blir nødvendig.

Filtester skal bevise gjenåpning, uforanderlighet, korrupsjonsavvisning,
grenser, tapt kvittering og feil på begge sider av commitgrensen. De skal også
bevise at omformatert JSON og OS- og editorfiler ikke låser rommet, og at en
skadet eldre versjon avvises ved lesing og gjenoppretting uten å stenge
rommet eller endre filer. Faktiske
parallelle prosesser, ulike miljøvariabler, casealiaser og drept skriver skal
prøve låsen. Samlede backend-/nettleserprøver skal bevise historikk,
utkastvern, gjenoppretting som ny revisjon og fravær av automatisk resend.
Dette erstatter ikke den avsluttende prøven av hele arbeidsflyten i appen.
