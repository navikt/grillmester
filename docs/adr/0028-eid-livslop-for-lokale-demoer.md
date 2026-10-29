---
status: accepted
date: 2026-10-28
---

# Eid livsløp for lokale demoer

## Kontekst

En lokal demo må være tilgjengelig uten å holde samtalen opptatt. Uttrykkelig
stopp skal ikke utløse omstart, og bare oppgavens egne prosesser skal stoppes.
Canvaset skal ikke få rett til å starte vilkårlig prosjektkode eller signalisere
andre prosesser på samme port.

## Beslutning

`design-prototype/scripts/app-runtime.js` er en liten CLI-hjelper som kjøres
av klientens vanlige shellverktøy. Den er ingen hook, installasjonsjobb eller
canvas-handling. `start` får en uttrykkelig valgt prosjektmappe, en lokal
oppgavenøkkel og et avgrenset argv etter `--`. Oppstarten bruker samme
shellautoritet og arver dens sandkasse. Hjelperen endrer ingen klient- eller
systemregler og prøver ikke på nytt utenfor sandkassen ved avvisning.

```
node <skill>/scripts/app-runtime.js start --project-dir <isolert-prosjekt> \
  --session mote --env IS_DEMO_MODE=true -- <dokumentert-program> <argumenter>
node <skill>/scripts/app-runtime.js status --project-dir <isolert-prosjekt> --session mote
node <skill>/scripts/app-runtime.js stop --project-dir <isolert-prosjekt> --session mote
```

Før oppstart må Designer ha kontrollert consumerens oppskrift, syntetiske data,
nettverkskrav og tillatelse til å kjøre kommandoen. Hjelperen verifiserer ikke
at data er syntetiske, at appen bare skriver i kopien eller at en valgt port
faktisk tilhører denne kommandoen. Appens URL og synlige innhold kontrolleres
separat før canvaset åpnes. Ingen oppstartskommando kan sendes gjennom HTTP
eller gjennom canvasadapteren.

### Kort oppstart og avgrenset kontroll

`start` returnerer etter en kort IPC-håndtrykk når kommandoen er startet,
uten å vente på serverens levetid. Det er en vanlig synkron shellkommando;
den skal ikke kjøres som en langvarig bakgrunnsjobb i klienten. Stdin er
frakoblet, og stdout/stderr går til en privat logg med høyst 1 MiB per kjøring.
Status returnerer loggens sti, men aldri kontrollnøkkelen eller logginnholdet.
«running» betyr prosessstatus, ikke at appens HTTP-adresse er klar.

En separat supervisor er leder for en egen prosessgruppe. En privat Unix-socket
på macOS og Linux tilbyr bare status og stopp. Mappene er eid av brukeren og
har modus 0700; tilstand, logg og socket er private. Kontrollen krever en
slumpmessig nøkkel og generasjon. Filbindingen inkluderer kanonisk prosjektmappe
og oppgavenøkkel. Symlenker, hardlenker, åpne rettigheter og feil binding
avvises. PID-er leses aldri fra disk for å signalisere en prosess.

Kontrollsocketen ligger i den vanlige midlertidige mappen og må ha en kort
nok sti. En for lang eller utilgjengelig sti gir en konkret feil; det byttes
ikke automatisk til en annen mappe eller TCP-port. Windows støttes foreløpig
ikke av hjelperen.

Miljøet er minimalt. Demo-/mockflagg må sendes med `--env NAME=value`;
vanlige slike flagg i det omgivende miljøet avvises dersom de ellers ville
blitt borte. Hemmelighets- og preload-lignende overstyringer avvises. Dette er
ikke en full klassifisering av alle mulige miljøvariabler eller en ny
nettverksgrense. Consumerens behov for godkjente offentlige ressurser og egne
skrivbare cacher må fortsatt håndteres i den gjennomgåtte demooppskriften.

### Levetid og stopp

Å lukke canvaset stopper visningen, ikke den eide demoen. Det gjør gjenåpning
forutsigbar. `stop` og `cancel` er samme uttrykkelige handling og skal brukes
når brukeren avslutter demonstrasjonen. Uventet prosessavslutning rapporteres
som stoppet; ingen automatisk omstart eller melding til samtalen sendes.

Standard levetid er fire timer, maksimalt åtte timer. Utløp, eksplisitt stopp,
feilet oppstart og kommandoens egen avslutning rydder den eide prosessgruppen
med TERM og deretter KILL. Dette gjelder også vanlige barn som ignorerer TERM.
Feil i tilstandsskriving må aldri forhindre denne oppryddingen. Et avbrutt
oppstartshåndtrykk rydder gruppen; etter fullført håndtrykk kan den korte
startkommandoen avslutte mens demoen fortsetter.

Gjentatt `start` med samme prosjekt, nøkkel og oppskrift gjenbruker en bekreftet
kjøring. En annen oppskrift krever først stopp eller en uttrykkelig separat
oppgave. En utilgjengelig controller gir ingen automatisk omstart og ingen
PID-basert opprydding. Et uttrykkelig `stop` kan rydde en utløpt, privat
oppstartslås uten lytter; ukjente filer røres ikke. En forsinket supervisor
revaliderer oppstartsleien før kommandoen kan starte.

Kommandoen og dens barn må beholde prosessgruppen: daemonisering og `setsid`
er ikke støttet. Dette er livsløpsstyring for en gjennomgått demo, ikke
innesperring av ondsinnet kode. En supervisor drept med SIGKILL kan heller
ikke garantere opprydding; tilstanden blir da utilgjengelig og krever særskilt
undersøkelse. Hjelperen gjetter aldri eierskap ut fra port, prosessnavn eller
lagret PID.

## Verifikasjon

[Prosessregresjonene](../../plugin/skills/design-prototype/tests/app-runtime.test.js)
dekker eierskap, gjenbruk, privat kontroll, avbrudd og opprydding med syntetiske
prosesser. App- og verkstedsmokene bruker den faktiske adapteren med simulert
vert. Ledig samtale, neste innspillsrunde og stopp uten omstart må også prøves
i støttet klient; se [leveringsgrunnlaget](../testing/designverksted-release-readiness.md).
Hjelperen distribueres ikke i OpenCode-målet, som ikke har denne appcanvas-flyten.
