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
Det immutable, checksumverifiserbare sluttbrukerartefaktet som pakker OpenCode
1-targetet og den valgfrie lifecycle-manageren.
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
Den normale OpenCode-integrasjonen der cplt starter OpenCode og Grillmester bare
bindes inn som et klienttarget.
_Avoid_: Grillmester-wrapper, managerflyt

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
