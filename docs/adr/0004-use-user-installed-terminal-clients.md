---
status: accepted
date: 2026-08-23
---

# Bruk systeminstallerte terminalklienter i standardflyten

## Kontekst

[ADR 0003](0003-one-terminal-entrypoint-through-cplt.md) ga Copilot CLI og
OpenCode én felles `grillmester`-kommando gjennom cplt. Den første
Homebrew-formelen pakket samtidig eksakte OpenCode- og cplt-binærer privat og
la dem først på launcherens `PATH`. Det ga en hermetisk releasekombinasjon, men
gjorde Grillmester til eier av klientinstallasjon, klientstørrelse og
oppdateringstakt.

Copilot CLI var allerede en separat klientinstallasjon. OpenCode-brukere
forventer på samme måte å kunne installere, konfigurere og oppdatere OpenCode
gjennom klientens egen pakkekanal. En privat OpenCode-kopi er dessuten vanskelig
å oppdage som vanlig installasjon og gjør hver kompatibel klientoppgradering til
en ny Grillmester-distribusjon. Den ekstra koblingen er ikke nødvendig for den
normale cplt-integrasjonen.

Den valgfrie lifecycle-manageren fra
[ADR 0002](0002-install-and-launch-opencode-bundles.md) løser et annet behov.
Der er eksakt checksum, versjonspin og privat `trusted-bin` selve
assurance-kontrakten og skal ikke svekkes av standardflytens enklere eierskap.

## Beslutning

Standardinstallasjonen eier Grillmester-innholdet, det genererte
OpenCode-targetet og terminal-launcheren. Den eier ikke OpenCode- eller Copilot
CLI-binæren.

- Homebrew-formelen installerer den checksummede Grillmester-bundle-en og
  Python-runtimen. cplt er en ekstern, påkrevd dependency fra
  `navikt/tap/cplt`, ikke en privat Grillmester-resource.
- OpenCode og Copilot CLI er valgfrie systemklienter. Brukeren installerer og
  oppdaterer dem gjennom deres egne pakkekanaler, og kan ha én eller begge.
- Launcheren resolver `cplt`, `opencode` og `copilot` fra `PATH`. Den installerer,
  erstatter, kopierer eller skygger aldri OpenCode eller Copilot CLI.
- cplt er fortsatt en hard runtimegrense. Manglende cplt stopper launcheren; det
  finnes ingen direkte eller stille fallback.
- Førstegangsvelgeren finner klienter på `PATH` uten å kjøre dem og viser bare
  installerte valg. Bare valgt klient versjonssjekkes, og proben går gjennom
  cplt mot en disposable 0700-prosjektmappe i stedet for consumer-repoet. Et eksplisitt valg av en
  manglende klient stopper med riktig installasjonskommando. `doctor` rapporterer
  en manglende, ikke-valgt klient som `skip`, men feiler for et eksplisitt valg
  eller når ingen støttet klient finnes.
- Standard kompatibilitetsgrense er OpenCode `>=1.18.20,<2`, Copilot CLI
  `>=1.0.79,<2` og cplt fra testbaselinen `2026.08.17-062831-1008a92` eller en
  nyere, gyldig datostemplet release. Releasegaten bruker fortsatt den eksakte
  baselinen som repeterbart testinput. Nyere tillatte klienter er en
  kompatibilitetsflate, ikke checksum-attesterte Grillmester-bytes.
- `grillmester update` oppdaterer Grillmester-formelen. OpenCode og Copilot CLI
  følger sine egne oppdateringsmekanismer; cplt følger sin separate
  Homebrew-formel. Vanlig launch gjør fortsatt ingen oppdaterings- eller
  nettverkskontroll utenfor cplt.
- `--print-command` er ren inspeksjon: den resolver presence/path, men kjører
  verken cplt eller klienten og hevder derfor heller ingen versjonsvalidering.
  Et interaktivt valg som bare trengs for utskriften persisteres ikke.

Homebrew-gaten provisjonerer OpenCode separat, beviser hvilken systempath
launcheren resolver, og avviser private `libexec/clients`-kopier. Samlet beviser
launcher- og Homebrew-testene manglende OpenCode, installert Copilot CLI uten
OpenCode, installert OpenCode gjennom cplt og avinstallasjon uten å fjerne de
brukereide klientene.

Lifecycle-manageren fra ADR 0002 beholder sin eksakte OpenCode
`1.18.20`-/cplt `2026.08.17-062831-1008a92`-pin, klientlås, checksumkontroll og
private `trusted-bin`. Denne manageren er den eksplisitte high-assurance-kanalen;
garantiene dens gjelder aldri automatisk for standardlauncheren.

Copilot CLI kan fortsatt installere Grillmester direkte fra marketplace uten
Homebrew-launcheren. Copilot app beholder sin native Plugins-UI og påvirkes ikke
av denne beslutningen.

## Konsekvenser

- Standardinstallasjonen blir mindre og følger den samme klient-eide modellen
  for OpenCode og Copilot CLI.
- En allerede installert Copilot CLI virker uten at OpenCode installeres, og
  motsatt. Brukeren kan oppdatere klientene uavhengig av Grillmester-innholdet.
- Terminalbrukere trenger fortsatt ikke kjenne `OPENCODE_CONFIG_DIR`,
  `--plugin-dir` eller Grillmesters interne pathstruktur.
- Standardflyten er ikke lenger en hermetisk klientkombinasjon. En tillatt,
  nyere klient kan drifte semantisk selv om CLI-formatet fortsatt er kompatibelt;
  releasegater, supportdata og konkrete feilrapporter må derfor registrere den
  observerte klientversjonen.
- Grillmester-bundle-ens checksum sier ingenting om de separat installerte
  klientbytene. Team med behov for slik binding må velge lifecycle-manageren.
- En ny Grillmester-release er nødvendig når payload, launcher,
  kompatibilitetsgrense eller high-assurance-pin endres, men ikke bare fordi en
  bruker oppdaterer en klient innenfor den støttede standardgrensen.

## Forkastede alternativer

- **Fortsett å bundle OpenCode og cplt privat:** gir hermetiske bytes, men gjør
  Grillmester til klientdistributør og skygger brukerens valgte OpenCode. Denne
  assurance-egenskapen hører hjemme i den eksplisitte managerflyten.
- **Installer OpenCode automatisk som påkrevd dependency:** påfører Copilot-only
  brukere en klient de ikke har valgt og gjør OpenCode til en skjult del av
  Grillmester-oppgradering.
- **Start en annen klient når den valgte mangler:** gjør en lokal
  installasjonsfeil til en stille semantisk endring. Fravær skal være synlig og
  handlingsrettet.
- **Fjern cplt-kravet i standardflyten:** bryter den felles sandboxgrensen fra
  ADR 0003. Systemklienter endrer eierskap til klientbytes, ikke kravet om cplt.
- **Fjern klientlåsen og managerens private staging:** ville svekke en separat,
  eksplisitt valgt high-assurance-kontrakt uten å gjøre standardflyten enklere.
