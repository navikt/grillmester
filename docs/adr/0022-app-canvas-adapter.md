---
status: accepted
date: 2026-10-23
---

# Valgfri app-canvas med samme innspillslager

Den midlertidige livssyklusen i denne beslutningen utvides av
[ADR 0023](0023-prosjektlagret-designrom.md) for uttrykkelig prosjektlagrede
designrom. Transport-, eierskaps- og innsendingsgrensene videreføres.

## Kontekst

Den avgrensede prøven fra [ADR 0019](0019-app-canvas-prove.md) har vist at
appen kan åpne en lokal skisse, knytte den til en bestemt samtale og ta imot
eksplisitt innsendte innspill i samtalekøen. Prøven har sin egen lille
eksempelflate. Den erstatter ikke Visual Companion, og resultatene beviser
ikke at en full integrasjon fungerer.

Neste godkjente milepæl er hele Visual Companion i appens canvas, med
innsending, svar og nye skisseversjoner i samme arbeidsflyt. Den portable
flyten må fortsatt fungere. Innsendte runder fra
[ADR 0021](0021-innsendte-runder.md) skal ikke kopieres til et konkurrerende
lager eller utledes på nytt fra en muterbar kommentarliste.

## Beslutning

Fullpakken får en valgfri appadapter i `plugin/extensions/visual-companion/`.
Den bruker vertens `createCanvas` og `joinSession`, og tilbyr avgrensede
handlinger for å lese tilstand og en bestemt innsendt runde, publisere en
skisseversjon og oppdatere svar og status. Registrering av canvasen starter
ingen previewserver og sender ingen melding.

Ved første åpning oppretter adapteren en privat Node.js-barneprosess for den
bestemte kombinasjonen av samtale, utvidelse og canvasinstans. Prosessen
kjører den kanoniske preview-runtime-en og dens ene `FeedbackStore`.
Adapteren bruker en avgrenset IPC-kontrakt; den blir ikke en ny skriver til
`comments.json`. Samme validering, skjermbinding, beholdte valg, atomiske
innsendingsjournal og HTTP-grenser gjelder i nettleser og canvas.

Barneprosessen trenger en vanlig Node.js-runtime, minst versjon 18. En pakket
appbinær kan være vert for utvidelsen uten å kunne starte vilkårlige
Node-skript. Adapteren skal derfor verifisere runtime-en, og ved behov finne
en allerede installert Node gjennom vertens absolutte `PATH`-oppføringer.
Den installerer ikke Node, arver ikke klientens legitimasjon eller
oppstartsflagg og bruker ikke private flagg for å gjøre appbinæren om til
en skriptkjører. Manglende runtime skal gi en konkret feil før et rom opprettes.

Den autentiserte loopback-URL-en beholdes. Canvas-API-et gir en visningsflate
og samtalekobling, ikke en dokumentert erstatning for den eksisterende
HTTP-serveren. Den separate filprøven inngår ikke i denne produksjonsflyten.

### Innsending og svar

Bare eksplisitt **Send** kan opprette en innsendt runde. Runtime-en lagrer
runden før den varsler adapteren. Utkast, lokale tekstforslag, justeringer,
lesing og publisering av en ny skisseversjon sender ingen melding.

Adapteren knytter varslet til sin allerede bundne samtale og legger en liten
melding med instans- og rundeidentitet i `session.send` med `mode: "enqueue"`.
Mottakeren henter den eksakte runden gjennom canvasens lesehandling. Store
runder leses i avgrensede sider; live-status er separat fra historikken.
Innspillene er oppgaveinnhold og kan ikke endre mottaker, verktøyrettigheter
eller sikkerhetsgrenser.

Lagret, mottatt i samtalekøen, under behandling og besvart er ulike
tilstander. En køkvittering beviser ikke at innspillet er lest eller utført.
Manglende eller tvetydig kvittering vises som ukjent leveringsutfall; adapteren
sender ikke automatisk den samme runden på nytt. En transportfeil ruller
heller ikke tilbake en allerede lagret innsendingsrunde.

Svar og kommentarendringer bruker samme lager og kontrollerer rundetilhørighet.
Publisering må angi forventet skjermversjon. Et gammelt svar skal ikke
gjenopprette et fjernet innspill, overskrive en senere innsending eller
markere en kommentar løst uten faktisk vurdering. Appadapteren er ingen
generell kanal fra vilkårlig skisse-JavaScript til samtalen eller filsystemet.

### Livssyklus og portabilitet

Å lukke panelet tilbakekaller den aktive URL-en og tokenet og stenger porten.
Den samme logiske skissen og innspillsjournalen kan åpnes igjen i den
begrensede, private økten med en ny transport. Instansens opprinnelige
eierskap og levetid endres ikke. Antall instanser og historikk er begrenset;
lukking og gjenåpning skal ikke omgå grensene.

Stopp, frakobling, utløp og prosessfeil skal avslutte barneprosessen og rydde
dens private økt. En gammel URL eller en forsinket callback får ikke tilgang
til en ny instans. Ingen restartimport eller varig arbeidsmappe innføres.
Appens egen samtalehistorikk har fortsatt vertens lagringsregler; denne
beslutningen lover ikke sletting av allerede leverte samtalemeldinger.

Den portable Node.js- og `comments.js wait`-flyten beholdes for klienter uten
canvas. Adapteren installeres ikke i prosjektets eller brukerens separate
extensions-mappe. Det opprettes ingen MCP-server, installasjonshook,
filkopieringslifecycle eller generell bakgrunnstjeneste.

### Distribusjonskontrakt

- Det eksisterende Copilot-manifestformatet beholdes uten `$schema`.
  Fullpakkens `plugin.json` bruker `"extensions": "extensions/"`.
- Utvidelsen har ett privat ESM-pakkemanifest med `extension.mjs` som
  inngang. SDK-en kommer fra verten. Pakken har ingen npm-avhengigheter,
  installasjonsskript, lockfiler eller medfølgende klientbinær.
- Hele utvidelsestreet inngår i fullpakkens eksisterende filhashmanifest og
  deterministiske bundle. Agent- og skill-rosteren endres ikke.
- Den fokuserte Copilot-projeksjonen fjerner `extensions` eksplisitt gjennom
  `removePluginManifestFields` i policyen og dokumenterer transformasjonen i
  sitt genererte manifest. Den får ingen utvidelsesfiler eller hengende sti.
- Verken full eller fokusert OpenCode-pakke får apputvidelsen. Den portable
  preview-runtime-en følger fortsatt design-skillen i full OpenCode.

Validator og bundlebygger avviser avvikende inngang, nye installasjonsskript
og apputvidelser i de portable projeksjonene. Genererte filer oppdateres i
vanlig rekkefølge; rettighetsgodkjenning og publisering er separate steg.

## Aksept før levering

Implementering og distribusjon skal verifiseres med følgende bevis:

1. Deterministisk generering og bundle, korrekt fullpakke, og fravær av både
   utvidelsesreferanse og filer i fokuserte/OpenCode-targets. Negative tester
   skal også avvise avvik med oppdaterte filhasher.
2. Samme lagrede runde lest gjennom HTTP/CLI og canvas, med bevart historikk,
   konfliktkontroller, begrensninger og utkast. SDK- og backendtester kjøres
   uten reell modell, også i vanlig CI.
3. Ingen server eller melding ved registrering; korrekt eksplisitt sending,
   ukjent leveringsutfall, kø under pågående arbeid, flere instanser og
   eierskapsavvisning. Lukk/gjenåpne, frakobling, utløp og krasj skal rydde
   transport og prosess uten å gjenbruke en gammel identitet.
4. Faktisk appprøve av hele flyten: åpne, send, svar, ny versjon og bevart
   lokalt utkast, samt panelgjenåpning og samtaleisolasjon. En simulert vert
   eller tidligere eksperimentprøve erstatter ikke dette.
5. Eksisterende installasjons- og terminalsmoker i disponible miljøer, med de
   vedtatte klientbaseline- og loopbackreglene. Ingen modellrettighet eller
   installasjonsinnstilling utvides for å få en test til å passere.

Beslutningen tillater implementeringen. Den er ikke en påstand om at alle
akseptpunktene er bestått eller en godkjenning av en release. Varig
arbeidsrom, fri layoutredigering, generell angrehistorikk og direkte
tilbakeskriving til kildekode/designsystem krever egne avgrensninger.

## Kilder

- [Canvas extensions i Copilot-appen](https://docs.github.com/en/copilot/how-tos/github-copilot-app/working-with-canvas-extensions).
- [Legacy-pluginformat og utvidelsesstier](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference).
- [GitHubs eksempel med lokal HTTP-server](https://github.com/github/awesome-copilot/blob/main/extensions/color-orb/extension.mjs).
- [SDK-ens køsemantikk](https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/steering-and-queueing).
