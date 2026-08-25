---
status: accepted
date: 2026-08-22
---

# Gi terminalklientene én Grillmester-inngang gjennom cplt

Klienteierskapet og Homebrew-distribusjonen i denne ADR-en er senere supersedert
av [ADR 0004](0004-use-user-installed-terminal-clients.md): standardlauncheren
bruker systeminstallerte OpenCode- og Copilot CLI-binærer, mens beslutningen om
én inngang gjennom cplt uten direkte fallback gjelder fortsatt. Den valgfrie,
upubliserte lifecycle-manageren som ADR-en fortsatt henviste til, er fjernet av
[ADR 0007](0007-remove-the-lifecycle-manager.md).

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
- digestverifiserer OpenCode-targetet, kopierer de samme bytene til en privat
  sessionconfig og setter `OPENCODE_CONFIG_DIR` til den kopien; OpenCodes egne
  runtimefiler kan dermed ikke mutere release-targetet
- velger den samme offentlige Grillmester-agenten i begge klienter
- videresender eksplisitte cplt-flagg før `--` og klientflagg etter `--`
- tilbyr en modellfri `doctor` som kontrollerer payload, klienter og release-
  gatede versjoner uten å starte en agentsesjon

Når `grillmester` kjøres uten argumenter i en interaktiv terminal, viser den en
liten klient- og agentvelger. Første valg kan lagres som en brukerpreferanse;
senere kjøringer tilbyr lagret kombinasjon som ett-Enter-default og
`grillmester choose` åpner hele velgeren igjen. Preferansen inneholder bare
`client` og `agent`, aldri provider, modell, credentials, cplt-policy eller
consumer-path. Eksplisitte `--client`- og `--agent`-flagg overstyrer preferansen
for den ene kjøringen uten å endre den.

Launcheren velger ikke provider, modell, credentials, MCP-er eller consumer-
policy. Den skriver ikke til consumer-repoet, Copilots pluginlager eller cplts
konfigurasjon. Brukerfilene er avgrenset til klient-/agentpreferansen og, bare
når den mangler, OpenCode 1.18.20s eksakte `.gitignore`-markør under brukerens
OpenCode-config. Markøren pre-seedes også i targetet, slik at cplt kan holde
begge configflatene read-only når OpenCode starter; en eksisterende regulær fil
endres aldri. Flagg som kunne bytte bort fra den valgte Grillmester-agenten
eller erstatte den distribuerte pluginpathen avvises. `--role` beholdes som
kompatibelt alias for det kanoniske `--agent`.

Den deterministiske release-bundle-en utvides med den kanoniske `plugin/`-flaten
og launcheren. ADR 0007 fjerner den separate OpenCode-manageren, slik at
kommandoen er den eneste Grillmester-eide terminalflyten. Den er terminal-UX,
ikke en ny filsynk eller installasjon inn i klientenes globale configområder.

Den opprinnelige Homebrew-beslutningen, senere supersedert av ADR 0004,
installerte den checksummede Grillmester-bundle-en sammen med eksakte private
cplt- og OpenCode-binærer. ADR 0004 beholder Homebrew som anbefalt inngang, men
erstatter de private klientene med en ekstern cplt-dependency og brukerinstallerte
OpenCode-/Copilot CLI-binærer fra `PATH`.
I denne releasen støttes Homebrew-pakken bare på macOS; Linux er ikke en del av
pakkens release-løfte.
GitHub Copilot CLI er fortsatt en separat, valgfri klientinstallasjon fordi den
ikke inngår i Grillmesters distribusjonsartefakter. `grillmester doctor` feiler
tydelig dersom den faktiske kombinasjonen ikke er støttet.

Vanlig launch gjør ingen oppdaterings- eller nettverkskontroll utenfor cplt.
`grillmester update` er den eksplisitte mutasjonen: den kjører `brew update` og
erstatter deretter formelen med `brew upgrade grillmester`. Automatisk
fleetoppgradering tilhører organisasjonens maskinforvaltning, ikke launcheren.
Etter piloten vurderes observert versjonsspredning uten produkttelemetri. Bare
dersom representative installasjoner faktisk blir hengende etter, kan en
eksplisitt, brukerinitiert `grillmester doctor --check-updates` vurderes som et
senere, separat tiltak. En passiv oppdateringssjekk under vanlig launch inngår
ikke i denne beslutningen og ville kreve en ny tillitsbeslutning.

Copilot app installerer Grillmester gjennom appens native Plugins-UI. Katalog-
og source-identiteten appen faktisk resolver, må verifiseres separat. Homebrew
og cplt påstås ikke å installere, starte eller sandboxe appen. VS Code tas ut
av normal onboarding og omtales bare som en ikke-verifisert kompatibilitetsflate
til en separat løsning er testet.

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
- Denne ADR-ens opprinnelige atomiske klientoppdatering er supersedert av ADR
  0004. En ny Grillmester-release oppdaterer plugin, OpenCode-target og launcher;
  systemklientene følger egne pakkekanaler.
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
- **Behold en separat lifecycle-manager:** dupliserer cplts runtimeansvar og
  skaper en ekstra profil-, staging- og vedlikeholdsflate. ADR 0007 fjerner den.
