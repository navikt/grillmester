# Oppgavebasert gjennomgang av Visual Companion

Disse casene prøver hele arbeidsoppgaver gjennom den faktiske nettleserskissen
og den samme innspillskøen som designeren leser. Rollene er simulerte
perspektiver, ikke intervjuer med eller observerte tester av faktiske brukere.
Gjennomgangen kan avdekke brudd og friksjon; den dokumenterer ikke hvor lett
nye brukere oppdager funksjonene eller en full tilgjengelighetsgodkjenning.

## Kjøring

Bruk en eksisterende Playwright-installasjon og en installert nettleser:

```bash
node scripts/smoke_visual_scenarios.cjs \
  --playwright-module /absolute/path/to/node_modules/playwright \
  --browser-channel chrome \
  --headed \
  --evidence-dir /tmp/visual-companion-scenarios
```

`--aksel-project /absolute/path/to/project` gjør komponentprøven konkret:
skriptet verifiserer at prosjektets installerte `@navikt/ds-react` og
`@navikt/ds-css` har samme versjon, rendrer faktiske komponenter med
`react-dom/server` og kopierer CSS til en disponibel prøveinstallasjon.
Kildeprosjektet endres ikke. Uten dette flagget bruker casene en enkel
HTML-skisse, og rapporten oppgir at Aksel ikke ble verifisert.

Ingen avhengigheter installeres. Hvert case starter en egen lokal server,
skriver skisser bare til dens private `screen_dir`, bruker oppdiktede data og
rydder prosesser og prøvefiler etterpå. Skjermbilder og en JSON-rapport blir
liggende i valgt evidensmappe. Rapporten inneholder ikke sesjons-URL eller
tilgangstoken. Programmet avslutter med feilstatus hvis ett eller flere case
feiler, men fortsetter med resten slik at én feil ikke skjuler andre problemer.

Bruk `--case four-directions` eller et annet navn nedenfor for en avgrenset
ny prøve etter retting. På macOS brukes synlig Chrome: bakgrunnsmodus har gitt
misvisende pekerresultater etter endring av størrelsen på en sandboxet iframe.
Ikke last siden på nytt for å komme rundt en slik feil i en utkastprøve.

## Oppgaver og akseptansekriterier

| Case | Rolle og designspørsmål | Oppgave | Hva skal kunne observeres? |
| --- | --- | --- | --- |
| `four-directions` | Designer: Hvilken arbeidsoversikt hjelper med prioritering? | Bytt fra liste/brett til tidslinje/ukeoversikt, velg en retning, og behold gode deler fra liste og brett. | Sammenlignede flater har lik bredde. Foretrukket retning finnes blant de viste variantene. Ønsker om å beholde deler med samme navn viser hvilken variant de tilhører. Én innsending gir én preferanse og de to riktige ønskene, uten beholdte valg. Sendte ønsker beholder opprinnelige navn når neste skisse endrer etiketter. |
| `target-drafts` | Designer som utforsker flere deler samtidig | Skriv ulike merknader og prøv tetthet i to deler. Bytt frem og tilbake, tilbakestill én visning og send begge. | Merknader og innstillinger følger riktig del. Tilbakestilling av visning sletter ikke skrevet tekst. Mottakeren får hver merknad knyttet til riktig variant. |
| `slow-adjustment` | Deltaker som navigerer mens lagring tar tid | Legg til en justering, åpne innspillslisten mens svaret er forsinket, og send når lagringen er ferdig. | To paneler legger seg ikke oppå hverandre. Merknaden er intakt mens forespørselen pågår. Justeringen lagres og sendes én gang. |
| `norwegian-copy` | Innholdsdesigner: Hvordan forklare en avtale? | Forhåndsvis en lengre tekst med norske tegn og bokstavelig markup, angre, prøv tekst over størrelsesgrensen og kort ned. | Teksten rendres som tekst. Angring gjenoppretter ordlyden. En størrelsesfeil beholder utkastet og peker på feltet som må kortes ned. Det komplette gyldige forslaget når mottakeren. |
| `recover-send` | Førstegangsdeltaker som opplever en feil | Legg et utkast til side, gjenoppta det, lag to innspill, prøv en innsending som feiler og send på nytt. Last siden igjen og les svar. | Begge innspill overlever feilen og sendes samlet én gang. Listen og statusfiltrene virker etter ny lasting. Tekst skrevet i selve prototypens prøvefelt havner ikke i køen. |
| `interactive-card` | Deltaker som prøver et skjema i et konseptkort | Skriv i felt, lag en ny linje, endre avkryssing og trykk en knapp før en egen valgknapp aktiveres. | Mellomrom, linjeskift og avkryssing fungerer normalt. Skjemainteraksjoner lager ingen variantvalg; kort med skjema fungerer som innholdsbeholdere. En egen valgknapp lager det avtalte variantvalget. Valgt retning og tilkoblingsstatus er synlige uten overlapp eller horisontal rulling også ved 320 px. |
| `keyboard-review` | Gjennomleser som bare bruker tastatur | Finn Endre med Tab, velg overskrift, skriv, legg utkastet til side med Escape, gjenoppta og send. | Hele oppgaven kan fullføres uten peker eller programmatisk fokusflytting. Escape gir fokus tilbake til valgt innhold. Det innsendte innspillet er komplett. |
| `compact-landscape` | Designer på liten skjerm | Juster ved 667 × 375, rull panelet og åpne det igjen. Kommenter, roter til 375 × 667, og sammenlign tredje og fjerde variant. | Merknadsfelt og handlinger kan nås uten å bli klemt bort. Tilkoblingsstatus dekker ikke lukkeknappen. Gjenåpnet panel viser kontrollen som får fokus. Rotasjon bevarer utkastet. Det er mulig å velge et par som ikke inneholder første variant. En ny variant vises før en preferanse sendes. |

Alle case sjekker nettleserfeil og at ingen ekstern ressurs fullfører lasting.
Installerte stiler kan inneholde fontadresser som nettleseren forsøker å hente;
serverens innholdspolicy skal blokkere dem. Et blokkert forsøk regnes ikke som
vellykket ekstern lasting.

De eksisterende skriptene `smoke_visual_companion.cjs` og
`smoke_visual_workshop.cjs` dekker fortsatt punkt-/områdemarkering, gamle
versjoner, synlige svar, ugyldige deklarasjoner, tvetydige delnøkler og
føringer som ikke er innarbeidet i neste skisse. Scenarioene her supplerer
disse med lengre oppgaver og kombinasjoner av funksjonene.

## Manuell oppfølging

Åpne skjermbildene fra både desktop, smal stående skjerm og liggende skjerm.
Kontroller spesielt at sammenligningslinjen ikke dekker første overskrift,
at aktive paneler ikke skjuler hverandre, at lange tekster brytes lesbart og
at den valgte delen fortsatt kan forstås bak innspillsverktøyet.

Ved en test med faktiske deltakere, gi oppgaven uten knappnavn først. Noter
hvor de leter etter kommentarer, hva de tror «Behold denne delen» gjør, om de
forstår forskjellen mellom lokal prøve og innsendt valg, og om de oppfatter
når innspill er mottatt. Dette er åpne undersøkelsesspørsmål; de automatiserte
casene gir ikke svar på dem.
