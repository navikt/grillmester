---
status: accepted
date: 2026-10-08
---

# Manuelt oppsett av appens sandbox

## Kontekst

GitHub Copilot desktop på macOS lagrer sandbox-innstillinger i
`~/.copilot/data.db`, ikke i `settings.json`: én policy per prosjekt, men ingen
repo-eid konfigurasjonsfil. Gradle daemon, Testcontainers og lokale tjenester trenger
loopback, men appens credential proxy tvinger loopback deny når
credential masking er på, selv med `allowLocalNetwork=true`.

## Beslutning

`app-sandbox-setup` er en manual-only skill med et medfølgende Python-script:
oppdag stier → vis plan/diff → få eksplisitt bekreftelse → skriv etter
digest- og skjemasjekk, med SQLite-backup. Kjør plan først; ved nektet tilgang
ber skillen om «Run outside the sandbox? → Run once» for den ene kommandoen,
og igjen for apply etter bekreftelse. `/sandbox off` eller vanlig terminal er
alternativer. Ved skjemamismatch brukes en konkret klikkguide.

Nye policyer har credential masking av for å få loopback til å fungere.
Rerun bevarer eksisterende credential-valg; `--mask-credentials` og
`--no-mask-credentials` setter begge eksplisitt. Vi aksepterer at ekte
GH_TOKEN og git credentials med masking av er synlige
for sandboxede prosesser, og kan eksfiltreres av byggscript eller avhengigheter
med tillatt outbound. `--mask-credentials` velger masking på med den nevnte
loopback-konsekvensen. Masking dekker bare credentials appen injiserer,
ikke filer på disk som `.npmrc`, `gradle.properties` eller `hosts.yml`.
Gh- og Docker-konfig med inline credentials beholdes lesbare, men readonly
og med innholdsfrie varsler.

Kodetilgang deles mellom prosjektene: parent til hvert prosjekts repo og
parent.parent til worktree-stier. Symlinker løses først; aldri gi tilgang til
selve `$HOME`, dets forfedre eller systemområder. Utrygge røtter faller tilbake
til den konkrete prosjekt-/worktree-mappen hvis den er trygg. Eksisterende
policy merges, ikke overskrives; sensitive stier nektes etter reglene nedenfor.
Utrygge foreldre som Downloads, Documents og Library brukes ikke som koderøtter.
Brukerens deniedPaths filtrerer tillegg; ugyldige stier fjernes og brede
eksisterende grants varsles. En korrupt policy hoppes over uten å blokkere
andre prosjekter. JDK-/verktøyoppsett oppdages uten krav om mise.

Readonly hardening av app-eide cacher, git-/shell-/tool-konfigurasjon og
Gradle init-filer stenger de verste «plant nå, kjør usandboxet senere»-rutene.
Hardening-stier listes alltid, også når de ikke finnes ennå, men readonly
gjelder først når stien finnes; verktøygrants
hoppes over når stiene mangler.
Smalere readonly vinner over bredere readwrite. Tool-installasjoner forblir
skrivbare. `~/.copilot/session-state` gis **ikke lenger** readwrite; rerun
fjerner den gamle granten, og appen gir nødvendig tilgang til egen økt.
Rerun er idempotent og nødvendig etter nye prosjekter, verktøy og appoppdateringer
som lager nye versjonsnavngitte cachemapper.

## Konsekvenser

Live-tester 2026-10-08 viser at manglende readonly-stier kan opprettes med
touch, mkdir, symlink, hardlink og rename; readonly håndheves først når stien
finnes i senere kommandoer. Manglende deny-stier håndheves ved at appen lager
tomme placeholder-mapper som blir liggende, også ved filstier; dette kan
ødelegge blant annet netrc/Copilot-konfig og gi GPG-permisjonsvarsler.
`$HOME` er ikke skrivbar, og `~/.copilot` er verken lesbar eller skrivbar
utenom appens egne grants til øktfiler, logger, agenter, extensions,
installed-plugins og marketplace-cache. Beslutning B er å beholde manglende
hardening-stier som readonly uten forhåndsoppretting; opprettelse er akseptert
restrisiko ved siden av git hooks i kode, skrivbare tool-installasjoner og
Docker-socketen. Deny følger forventet type og behovet for å blokkere
opprettelse under skrivbare foreldre; tomme placeholdere ved filstier og
direkte under HOME/`~/.copilot` fjernes etter bekreftet plan med `rmdir`
etter policy-commit. Backup-mappen er alltid nektet og unntatt fra fjerning.
`data.db-wal` og `data.db-shm` nektes ikke lenger fordi `~/.copilot` allerede
er ulesbar i sandboxen og deny-placeholdere kan ødelegge appens SQLite WAL.

Backuper ligger i en nektet mappe med 0700/0600-rettigheter. Planen skriver
ikke policyer; lesekommandoer bruker mode=rw med query_only for lukkede WAL-DB-er.
Apply bekrefter endringssettet i en transaksjon. Mislykkede writes rulles
tilbake og den ferske backupen slettes. De nyeste 10 egne backupene beholdes.
`rollback --from` viser diff/digest og gjenoppretter bare sandbox-felt og
policyrader for felles prosjekter etter bekreftelse, med ny backup først.
Hele DB-filen erstattes aldri.

Endringer gjelder nye økter eller etter `/restart-session`. `/sandbox off`
og `/sandbox on` virker umiddelbart i gjeldende økt; valget består også etter
restart og overstyrer prosjektets standard. Etter off trengs on + restart,
eller ny økt. `verify` i en ny sandboxet økt er avsluttende port:
adferdsprober, ingen lesing av DB-innhold eller session-state-policyfiler.
Enterprise managed settings kan gi avvik.

Sandbox er guardrails, ikke containment. Skrivetilgang til kode, `~/.config`,
`~/.nvm`, `~/.local/share`, `~/.bun` og lignende lar sandboxet kode plante
git hooks, shell-sourced scripts eller toolchain-binærer som senere kjører
usandboxet. Readonly hardening reduserer dette, men skrivbare tool-installasjoner
og kode beholder restrisikoen; masking fjerner den ikke. En sandboxet Gradle-klient
kan dessuten gjenbruke en usandboxet daemon startet fra IntelliJ/terminal,
slik at selve bygget kjører utenfor sandboxen.

Sandboxet kode kan fortsatt forhåndsopprette nye versjonsnavngitte app-cachemapper
direkte under `~/Library/Caches`, for eksempel `copilot-desktop-gh-<ny versjon>`,
fordi mappen forblir skrivbar for tool-cacher. Rerun etter appoppdateringer
herder bare mapper som allerede finnes.

Readwrite på `~/.docker` og `~/.rd` trengs for Testcontainers, men
socket-tilgangen kan brukes til å mounte `$HOME`, lese `.ssh`, skrive
LaunchAgents og omgå deny-listen. Docker er derfor nær usandboxet host-tilgang;
`--no-docker` utelater Docker-grants og fjerner våre eksakte eksisterende
rw-grants som opt-out. Da virker ikke Docker/Testcontainers i sandboxen.
Opt-out utelater også readonly-tilleggene `.docker/cli-plugins` og
`.docker/config.json`, som ligger under Docker-grants. Eksisterende readonly-
og bredere brukergrants fjernes ikke.

Live-tester viser at `/usr/bin/java` og `/usr/libexec/java_home` ikke finner
JDK-er i sandboxen: Spotlight-oppslag er utilgjengelig der. JDK-mappene er
lesbare; sett `JAVA_HOME` eller bruk en valgfri version manager (mise, sdkman,
asdf, jenv osv.). Planen lister direkte installerte JDK-er under
`~/Library/Java/JavaVirtualMachines` og `/Library/Java/JavaVirtualMachines`
uten subprocess, med HOME-relative stier og nyeste etter mappenavn først.

Appen beskytter `~/Library/pnpm` (`PNPM_HOME`) selv om policyen gir readwrite.
Globale pnpm-installasjoner og lenker feiler i sandboxen; prosjektinstallasjoner
virker. Granten beholdes.

Live-retest bekrefter at Playwright/Chromium ikke kan kjøre i appens sandbox:
sandboxen nekter nødvendig macOS IPC (Mach bootstrap/crashpad handshake og
sandbox extensions). Ingen path-grant hjelper; rerun fjerner den tidligere
readwrite-granten til `~/Library/Application Support/Google/Chrome for Testing`.
Kjør browser-tester og Playwright MCP utenfor sandboxen: godkjenn
«Run outside the sandbox → Run once» for kommandoen, eller bruk en økt med `/sandbox off`.
App-cachene forblir readonly; `APP_CACHE_WRITABLE` er tomt.

Prosesser fra tidligere shell-kall kan ikke inspiseres eller signaliseres
i sandboxen; stopp bakgrunnsservere i samme kall eller via port.

Bevisst blokkert: nais/kubectl/gcloud, inkludert nav-troubleshoot sine
kubectl-steg; SSH-remotes og commit-signering (`.ssh`/`.gnupg` nektes);
private `docker pull` via osxkeychain (pull utenfor sandboxen).
`gh auth status` med exit 1 er kosmetisk når GH_TOKEN virker. Stock python3
kan utløse dialog for Xcode Command Line Tools.

Løsningen avhenger også av et udokumentert app-DB-skjema som kan endres ved
oppgradering; skjemasjekk og klikkguide er fallback, ikke en stabil app-API.
