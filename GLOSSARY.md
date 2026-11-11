# Grillmester

Grillmester distribuerer portabel arbeidsmetode som agenter og skills til flere
klienter, mens hvert consumer-repo beholder eierskapet til sin egen stående
sannhet.

## Language

### Distribution

**Kanonisk plugin**:
Den reviewede Copilot-pluginen som er kilde for klientuavhengig metode og
promptinnhold.
_Avoid_: source-target, Copilot-only plugin

**Klienttarget**:
En klientspesifikk representasjon av den kanoniske pluginen.
_Avoid_: plugin-kopi, consumer-config

**OpenCode-target**:
Det deterministisk genererte klienttargetet i formatet `opencode-v1`, som OpenCode 2 leser,
med `2.2.5` som testbaseline.
_Avoid_: OpenCode-plugin, håndskrevet target

**Fokusert kontekstprojeksjon**:
Et deterministisk, redusert klienttarget avledet fra den kanoniske pluginen og
det fulle klienttargetet. Projeksjonen begrenser Grillmesters ambient agent-,
skill- og commandflate for eksplisitt lokal modellkjøring, men velger ikke
provider, modell, sandbox eller egresspolicy.
_Avoid_: lite-plugin, local-only-target, runtimeprofil

**Agentpakke**:
Den manifestdeklarerte samlingen av Grillmesters eksisterende klienttargeter
som `nav-pilot` kan validere, stage og starte. Manifestet peker på full og
fokusert kontekst for Copilot CLI og OpenCode; det kopierer ikke innhold og
overtar ikke eierskapet til generering, modellvalg eller runtimepolicy.
_Avoid_: distro, ny plugin, innholdssync, nav-pilot-fork

**Release-bundle**:
Det immutable, checksumverifiserbare sluttbrukerartefaktet som pakker den
kanoniske pluginen, OpenCode-targetet og terminal-launcheren.
_Avoid_: source-arkiv, checkout

### Ownership

**Consumer-repo**:
Repoet der Grillmester brukes, og som eier domenefakta, instrukser og lokale
samarbeidskontrakter.
_Avoid_: managed repo, installasjonstarget

**Stående sannhet**:
Varig repo-eid kontekst som gjelder uavhengig av valgt agent eller klient.
_Avoid_: plugininnhold, genererte instructions

### Design

**Kjørende app**:
En faktisk app med repoets komponenter, navigasjon og skjemaoppførsel, vist i
klientens nettleserfane. Lokal demo er førstevalget. Originalprosjektet beholdes
uendret.
_Avoid_: statisk kopi, skjermbilde, lagret appversjon

**Eid kopi**:
En disponibel kopi av appen som demoen og forslag kjører fra, med privat
Git-historikk som versjoner og angre. Endringer her er ikke produktkode.
_Avoid_: worktree uten bevis for at den er disponibel, originalprosjektet

**Pick & Polish**:
Copilot-appens plukker i nettleserfanen. Designeren velger en del av siden eller
et område, og valget følger neste melding i samtalen. Valget er innspill og
ubetrodd sideinnhold, ikke mandat. Det lagres ikke utenfor samtalen.
_Avoid_: Canvas Dev Mode

**Forslag**:
En synlig endring i den eide kopien, laget med appens ekte komponenter. En ny idé
uten app er en liten Aksel-app. Forslaget er midlertidig til det er lagret som patch
og brief etter avtale, og det endrer ikke produktet før implementering er bestilt.
_Avoid_: implementert appendring, skisse som dagens app

**Variant**:
Et alternativ til et reelt retningsvalg, bygget i samme kopi bak en query-parameter
og vist i egen fane.
_Avoid_: små justeringer, egne kopier per alternativ

### Runtime

**Native cplt-flyt**:
Den normale terminalintegrasjonen der cplt starter valgt klient og klienten
laster sin native Grillmester-representasjon. `grillmester` binder den
distribuerte pathen, men eier ikke klientens sandbox.
_Avoid_: direkte klientstart, Grillmester-sandbox

**Terminal-launcher**:
Den tynne `grillmester`-adapteren som velger Copilot CLI eller OpenCode, binder
riktig klientpayload og starter en kompatibel systemklient, gjennom cplt når cplt
er installert. Den
installerer, oppdaterer eller skygger aldri OpenCode eller Copilot CLI.
_Avoid_: agentruntime, universell app-installer, cplt-erstatning

**Local-model-launcher**:
Den eksplisitte `grillmester local`-flyten som binder én bruker-eid,
OpenAI-kompatibel loopbackmodell til OpenCode eller Copilot CLI gjennom cplt.
«Local» beskriver inferensen, ikke at resten av klienten er offline: web- og
GitHub-verktøy kan fortsatt brukes gjennom klientens godkjenninger og cplts
runtimegrenser.
_Avoid_: local-only-launcher, offlineprofil, modellserver, bundled klient,
auto-detektert BYOK

**Modellens kontekstkontrakt**:
Det eksplisitt lagrede, aktive kontekstvinduet og maksimale outputbudsjettet
for den bruker-eide lokalmodellen. Begge klientene får samme kontrakt:
OpenCode kan dermed komprimere før provider-overflow, og Copilot CLI får et
tilsvarende samlet tokenbudsjett. Kontrakten må matche modellserveren og er
verken reasoning-budgett, runtimeprofil eller klientpin.
_Avoid_: context-hint, launcher-compaction, antatt modellgrense

**Avgrenset kjøring**:
Den eksplisitte `grillmester local run`-formen for én ferdig spesifisert,
non-interaktiv oppgave. Prosessen kjører i foreground, mens klienten
auto-godkjenner tools, prosjektwrites og URL-er innenfor cplts effektive
runtimepolicy. Kjøringen hører hjemme i et rent, dedikert worktree og krever
menneskelig kontroll av sluttsvar, diff og tester.
_Avoid_: bakgrunnsjobb, unattended run, autonom køarbeider

**Systemklient**:
En separat bruker- eller organisasjonsinstallert OpenCode- eller Copilot CLI-
binær som standardlauncheren resolver fra `PATH`. Klientens installasjon og
oppdatering eies av dens egen pakkekanal; Grillmester eier bare
kompatibilitetsgrensen og bindingen.
_Avoid_: bundled klient, privat klient, Grillmester-eid klient

**Launcherpreferanse**:
Brukerens valg av default terminalklient og offentlig Grillmester-agent. Den
inneholder aldri provider, modell, credentials, consumer-path eller policy.
_Avoid_: runtimeprofil, managed config

**OpenCode runtime-støttefil**:
`.gitignore`-filen i targetet. Den holder filer OpenCode kan lage i config-mappen
utenfor Git.
_Avoid_: configsynk, managed OpenCode-config
