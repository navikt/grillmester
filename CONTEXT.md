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

**Release-bundle**:
Det immutable, checksumverifiserbare sluttbrukerartefaktet som pakker den
kanoniske pluginen, OpenCode 1-targetet, terminal-launcheren og den valgfrie
lifecycle-manageren.
_Avoid_: source-arkiv, checkout

### Ownership

**Consumer-repo**:
Repoet der Grillmester brukes, og som eier domenefakta, instrukser og lokale
samarbeidskontrakter.
_Avoid_: managed repo, installasjonstarget

**Stående sannhet**:
Varig repo-eid kontekst som gjelder uavhengig av valgt agent eller klient.
_Avoid_: plugininnhold, genererte instructions

### Runtime

**Native cplt-flyt**:
Den normale terminalintegrasjonen der cplt starter valgt klient og klienten
laster sin native Grillmester-representasjon. `grillmester` kan binde den
distribuerte pathen, men gjør ingen managed staging eller configsynk.
_Avoid_: managerflyt, direkte klientstart

**Terminal-launcher**:
Den tynne `grillmester`-adapteren som velger Copilot CLI eller OpenCode, binder
riktig klientpayload og starter en kompatibel systemklient gjennom cplt. Den
installerer, oppdaterer eller skygger aldri OpenCode eller Copilot CLI.
_Avoid_: agentruntime, universell app-installer, cplt-erstatning

**Local-model-launcher**:
Den eksplisitte `grillmester local`-flyten som binder én bruker-eid,
OpenAI-kompatibel loopbackmodell til OpenCode eller Copilot CLI gjennom eksakt
reviewet cplt. Den bruker privat runtime, avviser ambient klientkomponenter og
har ingen cloud-fallback. Begrepet beskriver kommandoen og trustgrensen, ikke
lifecycle-managerens runtimeprofil `local`.
_Avoid_: lokal profil, modellserver, bundled klient, auto-detektert BYOK

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

**Lifecycle-manager**:
Den valgfrie high-assurance-flyten for verifisert installasjon, launch og
rollback av en release-bundle.
_Avoid_: påkrevd cplt-oppsett, native cplt-flyt

**Runtimeprofil**:
Et modellnøytralt sett med deklarative grenser for lokal, cloudbasert eller
hybrid kjøring gjennom lifecycle-manageren.
_Avoid_: modellpreset, providerkonfigurasjon

**`local`**:
En lokal-kapabel runtimeprofil som tillater en navngitt lokal provider uten å
garantere fravær av annen nettverkstrafikk. Dette er en lifecycle-manager-
profil, ikke kommandoen `grillmester local`.
_Avoid_: local-only, local-model-launcher

**`local-only`**:
En fail-closed runtimeprofil som tillater en navngitt lokal provider og
blokkerer ekstern egress innenfor den dokumenterte plattformgrensen.
_Avoid_: local
