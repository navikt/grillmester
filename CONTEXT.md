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
Samlingen av underlag, innspill og valg i ett arbeid. En selvstendig skisse
eller en kjørende app med et tilhørende forslag kan være underlaget.
«Versjoner» gjelder lagrede skisser. Et prosjektlagret rom kan åpnes igjen med
samme innspill; approm lagrer ikke kode eller apptilstand.
_Avoid_: samtale, produktkode

**Midlertidig skisse**:
En skisse i designverkstedet som ikke er lagret i prosjektet. Den og
innspillene følger den levende økten og har ingen lagrede versjoner eller
«Rediger». Et midlertidig forslag i et appverksted loves ikke bevart etter
lukking. Prosjektlagring velges når det er bestilt; en midlertidig skisse
krever ikke et eget lagringsspørsmål.
_Avoid_: prosjektlagring og designrom overfor designeren

**Gi innspill**:
Appen eller skissen kan brukes som vanlig. «Gi innspill» lar designeren velge
en del eller hele siden; etter valget kan siden brukes igjen. «Send innspill»
sender det ferdige innspillet direkte. «Legg til flere» samler flere notater
til en uttrykkelig innsending med synlig antall. Ingenting sendes automatisk.
Skisser kan også ha deklarerte varianter, lokale visningsvalg og lagret redigering.
_Avoid_: Prøv og Endre som to vedvarende arbeidsmoduser

**Skisseversjon**:
En lagret, uforanderlig revisjon av skissen og dens eventuelle deklarerte
kontroller. «Vis» viser den uten å endre noe; gjenoppretting lager en ny
versjon og bevarer historikken.
_Avoid_: runde, gjeldende utkast

**Kjørende app**:
En faktisk lokal app med repoets komponenter, navigasjon og skjemaoppførsel.
Designverksted viser den i canvas og samler innspill, uten å lese eller
redigere kilden. Verkstedet er knyttet til Designer-samtalen.
«Appen nå» og «Forslag» er faner i samme verksted. Forslaget er en HTML-skisse
eller en separat kjørende appkopi. Endringer i kopien avtales og utføres med
vanlige verktøy; canvaset har ikke kildeeditor eller kodehistorikk. Referansen
beholdes uendret. Tilkobling og observerte appfeil er separate statuser.
_Avoid_: statisk kopi, skjermbilde, lagret appversjon

**Tilkobling til verkstedet**:
Bindingen mellom én aktiv visning, designrommet og samme samtale. Omlasting av
samme aktive fane kan gjenoppta forbindelsen og hovedappens kommentarutkast.
Uavklart sending krever samme uttrykkelige forsøk igjen. Dette lover ikke
bevaring av uferdige forslagstekster eller appens skjematilstand. Lukking av
et appverksted avslutter den instansen. En ny instans kan åpne et lagret rom
uten å sende tidligere runder på nytt; ulagret tekst, midlertidige forslag og
appens skjematilstand må ikke omtales som gjenopprettet.
_Avoid_: flyttet samtale, automatisk synkronisert app

**Forslag**:
Et anbefalt design i samme verksted som «Appen nå». Den har egne innspill og
eventuelle skisseversjoner. Samtalen eller en faktisk innsendt apprunde kan
bestille forslaget; det kreves ikke et kunstig innspill. Midlertidig forslag er
standard uten avtalt lagring. En uttrykkelig bestilling om å lagre hele verkstedet
omfatter også forslag innenfor avtalt designmappe. I et allerede lagret approm
kan et midlertidig HTML-forslag lagres senere uten å bytte rom eller miste innspill.
«Vis forslag» viser faktisk registrert arbeid.
_Avoid_: implementert appendring, ekstra canvas, automatisk kopiert runtime

**Midlertidige appinnspill**:
Innspill til en kjørende app uten lagring i prosjektet. Eksplisitt valgt lagring
bevarer innspill og svar; det lagrer ikke appkoden eller nettleserens tilstand.
_Avoid_: automatisk prosjektlagring

**Runde**:
Ett uforanderlig sett med innspill og valg fra en eksplisitt innsending.
En ny skisseversjon eller en åpnet appside er ikke en ny runde.
_Avoid_: versjon, samtaletur

**Innspill**:
Kommentarer til skissen eller appen, samt tekstforslag og deklarerte valg som
skissen støtter. Appinnspill beholder side-, mål- og visningskonteksten fra da
de ble skrevet; de identifiserer ingen kildeversjon. Lagrede, usendte innspill
er ikke en bestilling om behandling.
_Avoid_: automatisk kildeendring, ny fullmakt

**Behold denne delen**:
Et vanlig innspill som ber agenten beholde en del, med valgte innstillinger,
i neste versjon. Det sendes med neste runde som andre innspill og er ikke bevis
på at neste skisse er visuelt lik.
_Avoid_: beholdt valg, lagret felt, automatisk låsing

**Lagret felt**:
En verdi i skissens editor som blokkerer motstridende overskriving til designeren
velger «Tillat senere endring». Verdien beholdes da, men senere skisseversjoner
kan endre den. Dette feltvernet gjelder ikke appens kildefiler.
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
