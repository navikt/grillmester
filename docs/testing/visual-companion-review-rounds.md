# Flere runder med innspill

Disse scenarioene supplerer den første
[oppgavebaserte gjennomgangen](visual-companion-scenarios.md) med nye
arbeidssituasjoner over tid. Perspektivene er simulerte testhypoteser, ikke
intervjuer eller observasjoner av faktiske deltakere. De prøver konkrete
oppgaver i nettleseren og kontrollerer hva mottakeren faktisk får gjennom
innspillskøen.

## Kjøring

```bash
node scripts/smoke_visual_review_rounds.cjs \
  --playwright-module /absolute/path/to/node_modules/playwright \
  --browser-channel chrome \
  --headed \
  --aksel-project /absolute/path/to/project-with-installed-aksel \
  --evidence-dir /tmp/visual-companion-review-rounds
```

Ingen pakker installeres. Aksel-flagget bruker eksisterende, samsvarende
versjoner av `@navikt/ds-react` og `@navikt/ds-css`, rendrer komponentene og
kopierer CSS til en disponibel prøveinstallasjon. Uten flagget brukes enkel
HTML, og rapporten oppgir at Aksel ikke ble verifisert.

Skriptet oppretter en egen midlertidig nettleserprofil. Forstørrelsescaset
velger 200 % i nettleserens egne innstillinger og kontrollerer at CSS-viewporten
halveres og `devicePixelRatio` dobles. Endringen skjer via nettleserens
zoominnstilling. En emulert halvert viewport med doblet enhetsskala beviser
ikke nettleserzoom. Bruk Chrome eller
Chromium med den støttede innstillingssiden; en ukjent side eller en zoom som
ikke slår inn, skal gi feil, ikke en falsk bestått prøve. Brukerens vanlige
profil og zoominnstilling berøres ikke.

Hvert case starter en egen midlertidig lokal server og skriver bare til
serverens oppgitte `screen_dir`. Alle data er oppdiktede. Prosesser, profil og
prøvefiler ryddes etterpå. Skjermbilder og `review-rounds-results.json` blir
liggende i evidensmappen, uten sesjons-URL eller token. En feil i ett case
stopper ikke de andre. Hele kjøringen får feilstatus hvis noen case feiler.
Bruk `--case <navn>` for en målrettet prøve etter retting.

## Panel og oppgaver

| Case | Perspektiv og spørsmål | Oppgave | Akseptansekriterier |
| --- | --- | --- | --- |
| `shared-review` | Møteleder med to åpne faner: Vet jeg hva jeg sender? | Lag ett innspill, åpne en annen fane, og legg til et nytt innspill der mens første fane har en utdatert liste. Send fra første fane, hent oppdatert liste og fullfør runden. | Usete tillegg sendes ikke ubemerket. Begge innspill vises i begge faner når listen oppdateres. Mottakeren får det bevisst innsendte innholdet uten duplikater. |
| `change-direction` | Tjenestedesigner: Kan vi endre retning etter to gjennomganger? | Behold et stegvis konsept, kommenter andre skisse mens tredje blir klar, og bytt deretter til en samtale først. Velg «Slutt å beholde» på den gamle føringen og behold den nye. | Ny skisse venter på utkastet. Det innsendte innspillet beholder riktig skjermversjon. Avvik fra den gamle føringen er synlig. Frigivelse og ny føring kommer som en eksplisitt runde. |
| `qualified-approval` | Fagansvarlig: Hvordan skiller vi aksept fra et åpent forbehold? | Behold en oppsummering, send et eget forbehold, les svaret etter neste skisse og åpne forbeholdet igjen. Send det på nytt. | Beholdt del og forbehold er separate. Svaret forsvinner ikke når forbeholdet åpnes igjen. Det åpne innspillet kan sendes som en ny runde, mens den aksepterte delen fortsatt gjelder. |
| `zoomed-review` | Deltaker som trenger 200 % zoom og redusert bevegelse: Kan hele oppgaven gjennomføres? | Åpne og lukk justeringene, velg del og mer forklaring, skriv en merknad, send, sammenlign retninger og avslutt sammenligningen. | Reell zoom er målt. Handlinger kan nås uten tvunget klikk eller programmatisk lagring. Merknaden når riktig del. Sammenligning og lukking virker med den mindre CSS-viewporten. |
| `disconnected-draft` | Møtedeltaker: Hva skjer med teksten når den lokale økten stopper? | Skriv et utkast, simuler et midlertidig brudd i innspillsforbindelsen og prøv å lagre. Gjenopprett forbindelsen og send samme utkast. Skriv deretter et nytt utkast, stopp serveren, åpne skissen igjen for kopiering og velg teksten. Prøv å lagre. | Midlertidig brudd gir ingen falsk lagring. Samme utkast kan lagres og sendes én gang etter gjenoppretting, uten omlasting. Frakobling etter faktisk serverstopp utgir seg heller ikke for vellykket lagring. Utkastet kan fortsatt nås og kopieres. Lagringsfeilen bevarer teksten, og veien til en ny økt forklares. |

Casene sjekker også at ingen nettleserunntak oppstår og at ingen ekstern
ressurs fullfører lasting. En eventuell ekstern fontadresse fra installert
CSS skal blokkeres av innholdspolicyen; et blokkert forsøk regnes ikke som
vellykket lasting.

## Hva en faktisk brukertest bør undersøke

Gi de samme oppgavene uten å navngi knappene. Undersøk særlig om deltakerne
forstår hvem en felles innspillsliste tilhører, hva «Behold dette» lover,
hvordan de signaliserer at et svar ikke løste problemet, og hvor de forventer
at utkastet finnes etter en avsluttet økt. Kontroller også skjermleserbruk og
behov for større tekst enn den automatiserte zoomprøven dekker.

Denne gjennomgangen bekrefter ikke en faktisk modellklients integrasjon,
at en avsluttet samtale vekkes automatisk, eller varig lagring av økter.
Serverens innspill er midlertidige og fjernes ved normal opprydding.
