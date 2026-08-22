---
status: accepted
date: 2026-08-22
---

# Gi terminalklientene én Grillmester-inngang gjennom cplt

## Kontekst

GitHub Copilot CLI og OpenCode kan begge kjøre det samme Grillmester-agentteamet,
men klientene oppdager innholdet på ulike måter. Copilot CLI laster den kanoniske
pluginen, mens OpenCode laster det genererte OpenCode 1-targetet. Den første
OpenCode-flyten krevde at brukeren lastet ned en release-bundle, verifiserte den,
pakket den ut, fant target-pathen og satte `OPENCODE_CONFIG_DIR` og flere cplt-
flagg ved hver launch. Den var eksplisitt og testbar, men ikke en rimelig normal
onboarding.

`cplt` er organisasjonens felles sandbox-inngang for terminalagentene. Den
starter både Copilot CLI og OpenCode, men kjenner ikke Grillmesters publiserte
plugin- og target-paths. Det manglende laget er derfor en tynn, deterministisk
adapter over cplt, ikke en ny agentruntime eller en ny synkroniseringstjeneste.

Copilot app og VS Code er andre runtimeflater. Copilot app har en native
Plugins-UI og startes ikke gjennom cplt. VS Code har en separat
plugin-/extension-livssyklus som ikke er release-verifisert for denne
beslutningen.

## Beslutning

Grillmester publiserer én terminalkommando, `grillmester`, for de to støttede
terminalklientene:

```text
grillmester --client copilot  -> cplt --agent copilot  -> Copilot CLI
grillmester --client opencode -> cplt --agent opencode -> OpenCode
```

Kommandoen gjør bare klientbindingen som må være lik og repeterbar:

- finner den distribuerte pluginen og OpenCode-targetet relativt til sin egen
  verifiserte distribution root
- velger cplt-agent eksplisitt; den faller aldri tilbake til direkte,
  usandboxet klientstart
- sender den distribuerte pluginen til Copilot CLI med det native
  `--plugin-dir`-flagget
- setter og videresender `OPENCODE_CONFIG_DIR`, samt gir eksakt read-tilgang til
  targetet, for OpenCode
- velger den samme offentlige Grillmester-rollen i begge klienter
- videresender eksplisitte cplt-flagg før `--` og klientflagg etter `--`
- tilbyr en modellfri `doctor` som kontrollerer payload, klienter og release-
  gatede versjoner uten å starte en agentsesjon

Når `grillmester` kjøres uten argumenter i en interaktiv terminal, viser den en
liten klient- og rollevelger. Første valg kan lagres som en brukerpreferanse;
senere kjøringer tilbyr lagret kombinasjon som ett-Enter-default og
`grillmester choose` åpner hele velgeren igjen. Preferansen inneholder bare
`client` og `role`, aldri provider, modell, credentials, cplt-policy eller
consumer-path. Eksplisitte `--client`- og `--role`-flagg overstyrer preferansen
for den ene kjøringen uten å endre den.

Launcheren velger ikke provider, modell, credentials, MCP-er eller consumer-
policy. Den skriver ikke til consumer-repoet, `~/.config/opencode`, Copilots
pluginlager eller cplts konfigurasjon. Den eneste brukerfilen den kan skrive er
den eksplisitt valgte klient-/rollepreferansen under brukerens vanlige config-
område. Flagg som kunne bytte bort fra den valgte
Grillmester-rollen eller erstatte den distribuerte pluginpathen avvises; brukeren
kan velge en annen offentlig Grillmester-rolle med launcherens `--role`.

Den deterministiske release-bundle-en utvides med den kanoniske `plugin/`-flaten
og launcheren. OpenCode-manageren fra ADR 0002 forblir den eneste valgfrie,
managed/high-assurance livssyklusen. Den nye kommandoen er normal terminal-UX,
ikke en ny filsynk eller installasjon inn i klientenes globale configområder.

Homebrew er den anbefalte distribusjonsinngangen for terminalflyten. Formelen
installerer den checksummede Grillmester-bundle-en, de eksakte reviewede cplt-
og OpenCode-binærene og eksponerer `grillmester`-kommandoen. De private
klientbinærene velges per macOS-arkitektur fra den committede artefaktlåsen og
legges først på `PATH` bare for Grillmester-launcheren. Dermed endrer ikke en
senere oppstrøms Homebrew-oppdatering den installerte releasekombinasjonen.
GitHub Copilot CLI er fortsatt en separat, valgfri klientinstallasjon fordi den
ikke inngår i Grillmesters distribusjonsartefakter. `grillmester doctor` feiler
tydelig dersom den faktiske kombinasjonen ikke er støttet.

Copilot app installerer den samme publiserte pluginreleasen gjennom appens
native Plugins-UI. Homebrew og cplt påstås ikke å installere, starte eller
sandboxe appen. VS Code tas ut av normal onboarding og omtales bare som en
ikke-verifisert kompatibilitetsflate til en separat løsning er testet.

## Konsekvenser

- Terminalbrukere trenger ikke kjenne tarball-layout,
  `OPENCODE_CONFIG_DIR`, `--plugin-dir` eller Grillmesters interne pathstruktur.
- Begge terminalklientene går gjennom samme cplt-grense, samtidig som hver
  klient beholder sitt native innholdsformat.
- Copilot CLI kan fortsatt bruke vanlig marketplace-installasjon uten
  launcheren. Homebrew-flyten laster den byte-identiske pluginpayloaden fra
  bundle-en og endrer ikke brukerens pluginlager.
- Copilot app beholder en selvstendig, native installasjonsflyt og påvirkes ikke
  av terminalvalg.
- En ny Grillmester-release oppdaterer plugin, OpenCode-target, launcher og de
  terminalklientbytene Grillmester eier atomisk. Copilot CLI må fortsatt
  re-gates når upstreamkontrakten endres.
- Homebrew-formelen må publiseres fra den immutable release-bundle-en og dens
  checksum; en source-checkout eller flytende branch er ikke en stabil
  distribusjonskilde.

## Forkastede alternativer

- **Kopier Grillmester inn i `~/.config/opencode`:** innfører en ekstra global
  synk-/konfliktlivssyklus og kan skygge brukerens egne komponenter.
- **Installer Copilot-pluginen ved å kopiere filer fra Homebrew:** omgår den
  native pluginmodellen og gjør Copilot CLI og app vanskeligere å holde
  konsistente.
- **La launcheren starte klientene direkte når cplt mangler:** bryter den avtalte
  sandboxgrensen og gjør samme kommando sikkerhetsmessig situasjonsavhengig.
- **La launcheren velge cplt automatisk når den finnes og ellers kjøre direkte:**
  gjør fravær av en binær til et stille sikkerhets-opt-out. Manglende cplt skal
  alltid stoppe med installasjonsveiledning.
- **Bruk cplt for Copilot app eller VS Code:** cplt starter terminalprosesser og
  gir ingen dokumentert installasjons- eller runtimegrense for disse klientene.
- **Gjør lifecycle-manageren obligatorisk:** påfører normal bruk dens smale
  providerprofil, private klientstaging og high-assurance-policy uten at brukeren
  har valgt det behovet.
