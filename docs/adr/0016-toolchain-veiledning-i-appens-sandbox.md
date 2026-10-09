---
status: accepted
date: 2026-10-09
---

# Toolchain-veiledning i appens sandbox

## Kontekst

Appen fanger shell-miljøet ved appstart. En Java-pin aktiverer ikke mise av seg
selv, og macOS-stubben `/usr/bin/java` finner ikke JDK via Spotlight i sandboxen.
En vellykket Java-probe utenfor sandboxen er derfor ikke tilstrekkelig bevis.

## Beslutning

Plan/apply håndterer en kort per-project blokk i `projects.instructions`.
Pins og validerte JDK-hjem oppdages uten å kjøre Java. Blokken gir én
toolchain-beslutning per verktøy; fungerende node/pnpm på øktens PATH beholdes.
`<!-- app-sandbox-setup:toolchain:begin v1 -->` og
`<!-- app-sandbox-setup:toolchain:end -->` avgrenser vår tekst. Bare denne
blokken og separatoren ved append/fjerning endres; brukertext utenfor bevares.
Ufullstendige eller dupliserte markører betyr at prosjektet hoppes over.
Diff og digest binder endringen; apply skriver i samme transaksjon som
policyen, med backup. Rollback gjenoppretter instructions sammen med
sandbox-feltene. `--no-instructions` velger dette bort.

Top-level `instructions` i `.github/github-app.yml` kan overstyre DB-feltet;
presedens er ikke verifisert. Vi skriver derfor ikke DB-blokken der, men viser
trust-status og en blokk brukeren kan legge inn manuelt. Global
`settings.instructions` og repo-konfigurasjonen endres aldri.

Shell-profile-blokken er opt-in med separat `profile plan` og
`profile apply --confirm DIGEST`, aldri en del av vanlig plan/apply. Beslutningen
tas per verktøy: Java-stubben med tom `JAVA_HOME` trenger hjelp, mens node/pnpm
som allerede finnes på øktens PATH beholdes. zsh leser `.zprofile` før `.zshrc`,
slik at nvm fortsatt kan legge sin node først senere. Vi respekterer `ZDOTDIR`,
bruker bashs første eksisterende login-profil eller en fish `conf.d`-fil, og
skriver aldri `~/.zshenv`. Ukjente shell får bare veiledning.

Blokken mellom `# >>> app-sandbox-setup:toolchain v1 >>>` og
`# <<< app-sandbox-setup:toolchain v1 <<<` legger til mise shims med en statisk
PATH-guard, uten aktiveringshook ved hvert prompt. Uten mise kreves eksplisitt
`--java-home PATH` eller `auto`. JDK valideres ved oppsett, og eksisterende
`JAVA_HOME` overskrives aldri. Ulike prosjektmajorer avviser `auto`; per-project
instructions håndterer forskjellen. Vi bevarer tekst utenfor markørene, avviser
symlinker og feil markører, tar 0600-backup og erstatter filen atomisk med samme
modus. Fjerning krever egen preview og bekreftelse og fjerner bare vår blokk.

Før aktivering committes readonly for login-filen, shims og mise-binærens katalog under
HOME i alle prosjektpolicyer via eksisterende transaksjons-/backupflyt.
Én digest binder DB- og filendringen. Oppdagelsesfaktumet «profile opt-in active»
holder den betingede regelen aktiv ved vanlig plan/apply. Etter fjerning kan
samme shell-/toolchain-miljø brukes til å droppe regelen ved neste plan/apply.
Smalt readonly vinner over bredere rw `~/.local/share` (verifisert live).
Installasjoner og `mise reshim` må derfor kjøres utenfor sandboxen.
Filfeil etter DB-commit rapporteres eksplisitt; readonly forblir committet.
Appen må avsluttes og startes helt på nytt; `/restart-session` er ikke nok.

`gradle-toolchains plan|apply|remove` har separat bekreftelse. Reparasjon krever
en Gradle toolchain-pin og en validert JDK med riktig major som ikke allerede
oppdages. Vi bruker samme per-project beslutning som instructions:
`mise exec` starter prosjektets pinnede Java, mens `JAVA_HOME=<home>` starter
den validerte JDK-en. Når ønsket toolchain-major matcher denne JVM-en,
trengs ingen reparasjon: `CurrentInstallationSupplier` oppdager JVM-en som
kjører Gradle, og `EnvironmentVariableJavaHomeInstallationSupplier` håndterer
`JAVA_HOME`. Uten en Java-beslutning er manglende oppdagelse ikke bevist;
vi foreslår da ingen automatisk reparasjon.

Bare forskjellige majorer kan gi en reparasjonskandidat, eksempelvis mise
Java 25 med `jvmToolchain(21)`. En validert JDK med ønsket major må finnes
utenfor asdf/SDKMAN! og ikke allerede være konfigurert. Vi prioriterer mise
installs, deretter brukerens Library og systemets Library, med høyeste
versjon innen samme major i hver katalog. Plan forklarer resultatet per prosjekt.
Primærkildene fra Gradle 9.8.0, kontrollert 2026-10-09, viser ingen
mise-supplier, og macOS-supplieren bruker sandbox-utilgjengelig `java_home -V`.
Disse katalogfaktaene alene beviser likevel ikke behov for reparasjon.
JDK-er som allerede oppdages via asdf/SDKMAN!, trenger ingen reparasjon.
Vi merger bare nødvendige
JDK-hjem i `org.gradle.java.installations.paths`, bevarer øvrige linjer og
kommentarer, og merker stiene vi selv la til for selektiv fjerning.
Dette gir ikke Gradle-wrapperen en Java å starte med; instructions gjør det.
Gradle-prosjekter uten Java-pin får én advarsel, ikke et automatisk Java-valg.

Innstrammingene i #83
(~/.config allowlist, strict code roots og credential scanning) er utsatt.

## Konsekvenser

Instructions er veiledning, ikke håndheving av riktig versjon i hver kommando.
`verify` kjøres fra prosjektmappen i en ny sandboxet økt og skiller
miljøfeil, seatbelt-feil og manglende installasjon. Vellykkede fixture-tester
beviser ikke appens faktiske oppstartsmiljø eller sandbox-håndheving.
Bekreftede backup-flyttinger skjer etter DB-commit og sletter ikke kopiene;
en flyttefeil varsles uten å rulle tilbake policyen.

**Rest-risiko:** mise `installs/` forblir skrivbar. En sandboxet prosess kan
derfor fortsatt endre en JDK-binær som senere kjøres utenfor sandboxen.
Risikoen er uendret fra før; denne PR-en dokumenterer den, og readonly shims
løser ikke dette. Fixture-tester beviser filhåndtering, digest og commit-rekkefølge,
ikke appens faktiske oppstartsmiljø, Gradle-suppliers i alle versjoner eller
sandbox-håndheving på macOS.
