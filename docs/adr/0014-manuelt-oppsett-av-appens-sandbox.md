---
status: accepted
date: 2026-10-08
---

# Manuelt oppsett av appens sandbox

## Kontekst

GitHub Copilot desktop på macOS lagrer sandbox-innstillinger i
`~/.copilot/data.db`, ikke i `settings.json`. Det finnes ingen sandbox-konfig
per repo. Gradle daemon, Testcontainers og andre lokale tjenester trenger
loopback, men appens credential proxy tvinger loopback deny når
credential masking er på, selv med `allowLocalNetwork=true`.

## Beslutning

`app-sandbox-setup` er en manual-only skill med et medfølgende Python-script:
oppdag stier → vis plan/diff → få eksplisitt bekreftelse → skriv etter
digest- og skjemasjekk, med SQLite-backup. Scriptet kjøres med sandbox av eller
i vanlig terminal. Ved skjemamismatch brukes en konkret klikkguide.

Credential masking er av som standard for alle prosjekter for å få loopback
til å fungere. Vi aksepterer at ekte GH_TOKEN og git credentials da er synlige
for sandboxede prosesser, og kan eksfiltreres av byggscript eller avhengigheter
med tillatt outbound. `--mask-credentials` velger masking på med den nevnte
loopback-konsekvensen.

Kodetilgang deles mellom prosjektene: parent til hvert prosjekts repo og
parent.parent til worktree-stier. Symlinker løses først; aldri gi tilgang til
selve `$HOME`, dets forfedre eller systemområder. Utrygge røtter faller tilbake
til den konkrete prosjekt-/worktree-mappen hvis den er trygg. Eksisterende
policy merges, ikke overskrives; sensitive stier nektes alltid. Rerun er
idempotent og nødvendig etter nye prosjekter eller verktøy.

## Konsekvenser

Backuper ligger i en nektet mappe med 0700/0600-rettigheter. Planen skriver
ikke; apply bekrefter hele endringssettet i en transaksjon. Endringer gjelder
nye økter eller etter `/restart-session`, ikke den fortsatt usandboxede økten.

Sandbox er guardrails, ikke containment. Skrivetilgang til kode, `~/.config`,
`~/.nvm`, `~/.local/share`, `~/.bun` og lignende lar sandboxet kode plante
git hooks, git/gh-konfig, shell-sourced scripts eller toolchain-binærer som
senere kjører usandboxet. Masking fjerner ikke denne restrisikoen.
Løsningen avhenger også av et udokumentert app-DB-skjema som kan endres ved
oppgradering; skjemasjekk og klikkguide er fallback, ikke en stabil app-API.
