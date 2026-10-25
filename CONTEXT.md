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

**OpenCode 1-target**:
Det deterministisk genererte klienttargetet for den støttede OpenCode 1-flaten,
med `1.18.20` som første testbaseline.
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
kanoniske pluginen, OpenCode 1-targetet og terminal-launcheren.
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

**Designrom**:
Samlingen av skisser, innspill og valg i ett arbeid. Versjonene vises under
«Versjoner», og et prosjektlagret rom kan åpnes igjen med samme lagrede innhold.
_Avoid_: samtale, produktkode

**Skisseversjon**:
En lagret, uforanderlig revisjon av skissen og dens eventuelle deklarerte
kontroller. «Vis» viser den uten å endre noe; gjenoppretting lager en ny
versjon og bevarer historikken.
_Avoid_: runde, gjeldende utkast

**Runde**:
Ett uforanderlig sett med innspill og valg fra en eksplisitt innsending.
En ny skisseversjon er ikke en ny runde.
_Avoid_: versjon, samtaletur

**Innspill**:
Kommentarer, tekstforslag og deklarerte valg til skissen. Lagrede, usendte
innspill er ikke en bestilling om behandling.
_Avoid_: automatisk kildeendring, ny fullmakt

**Beholdt valg**:
«Behold dette» ber agenten ta med en valgt del og eventuelle innstillinger
videre. Det er en bestilling til agenten, ikke bevis på at neste skisse er
visuelt lik. «Slutt å beholde» trekker den tilbake.
_Avoid_: lagret felt, føring, automatisk låsing

**Lagret felt**:
En editorverdi som blokkerer motstridende overskriving til designeren velger
«Tillat senere endring». Verdien beholdes da, men senere versjoner kan endre den.
_Avoid_: beholdt valg, føring, usendt tekstforslag

**Leveringsstatus**:
Status for sending til samtalen. `queued` bekrefter mottak i køen; `unknown`
betyr at mottaket er uavklart. Ingen av dem beviser behandling eller resultat,
og ukjent mottak gir ikke automatisk ny innsending.
_Avoid_: behandlingsstatus, ferdig

### Runtime

**Native cplt-flyt**:
Den normale terminalintegrasjonen der cplt starter valgt klient og klienten
laster sin native Grillmester-representasjon. `grillmester` binder den
distribuerte pathen, men eier ikke klientens sandbox.
_Avoid_: direkte klientstart, Grillmester-sandbox

**Terminal-launcher**:
Den tynne `grillmester`-adapteren som velger Copilot CLI eller OpenCode, binder
riktig klientpayload og starter en kompatibel systemklient gjennom cplt. Den
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
Den eksakte `.gitignore`-markøren fra OpenCode 1.18.20-testbaselinen. Targetet
inkluderer den, og terminal-launcheren oppretter bare den manglende brukerfilen
før cplt gjør OpenCode-configen read-only.
_Avoid_: configsynk, managed OpenCode-config
