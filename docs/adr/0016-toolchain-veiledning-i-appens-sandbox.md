---
status: accepted
date: 2026-10-09
---

# Toolchain-veiledning i appens sandbox

## Kontekst

Appen fanger shell-miljøet ved øktstart. En Java-pin aktiverer ikke mise av seg
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

Slice 2 legger til en opt-in shell-profile-blokk og en målrettet reparasjon av
Gradle toolchain-stier; detaljene fylles inn av slice 2. Innstrammingene i #83
(~/.config allowlist, strict code roots og credential scanning) er utsatt.

## Konsekvenser

Instructions er veiledning, ikke håndheving av riktig versjon i hver kommando.
`verify` kjøres fra prosjektmappen i en ny sandboxet økt og skiller
miljøfeil, seatbelt-feil og manglende installasjon. Vellykkede fixture-tester
beviser ikke appens faktiske oppstartsmiljø eller sandbox-håndheving.
Bekreftede backup-flyttinger skjer etter DB-commit og sletter ikke kopiene;
en flyttefeil varsles uten å rulle tilbake policyen.
