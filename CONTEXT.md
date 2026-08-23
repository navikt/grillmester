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
Det deterministisk genererte klienttargetet for den release-gatede OpenCode
1-versjonen.
_Avoid_: OpenCode-plugin, håndskrevet target

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
riktig klientpayload og starter den gjennom cplt.
_Avoid_: agentruntime, universell app-installer, cplt-erstatning

**Launcherpreferanse**:
Brukerens valg av default terminalklient og offentlig Grillmester-agent. Den
inneholder aldri provider, modell, credentials, consumer-path eller policy.
_Avoid_: runtimeprofil, managed config

**OpenCode runtime-støttefil**:
Den eksakte `.gitignore`-markøren OpenCode 1.18.20 skriver hvis den mangler.
Targetet inkluderer den, og terminal-launcheren oppretter bare den manglende
brukerfilen før cplt gjør OpenCode-configen read-only.
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
garantere fravær av annen nettverkstrafikk.
_Avoid_: local-only

**`local-only`**:
En fail-closed runtimeprofil som tillater en navngitt lokal provider og
blokkerer ekstern egress innenfor den dokumenterte plattformgrensen.
_Avoid_: local
