# ADR 0002: Installer og start OpenCode fra verifiserte brukerartefakter

- **Status:** Akseptert
- **Dato:** 2026-08-21
- **Superseder:** Aktiverings- og rollbackdelen av
  [ADR 0001](0001-native-opencode-v1-target.md), men ikke beslutningen om et
  generert native target

## Kontekst

ADR 0001 valgte et deterministisk generert OpenCode-target utenfor consumerens
`.opencode/`, men lot en reviewet source-checkout være runtime-path. Det gir tre
problemer:

1. release-taggen er catalog-only, så brukeren må kjenne en separat source-SHA
2. OpenCode kan behandle config directory som runtimeområde; en checkout skal
   verken få dependency-/cachefiler eller være agentens skrivbare policyflate
3. source-SHA alene verifiserer ikke at filinventar, innhold og modus fortsatt
   er eksakt når prosessen starter

OpenCode `1.18.20` skrev ikke `package.json`, `node_modules` eller andre filer i
den isolerte runtime-smoken. Det er likevel ikke grunn til å gi write: agenter og
permissions kan lastes fra config directory, så en skrivbar stage ville la en
kompromittert prosess forsøke å endre sin egen policy under kjøring.

Navs `cplt` støtter OpenCode som egen agent. I den siste reviewede releasen,
`2026.08.17-062831-1008a92`, er ikke `OPENCODE_CONFIG_DIR` en automatisk
videresendt variabel, og en egendefinert Grillmester-path er ikke blant
OpenCodes vanlige configområder. Launcheren må derfor eksplisitt videresende
variabelen og gi read-tilgang til den eksakte stage-pathen. cplt blokkerer også
localhost som standard og krever én eksplisitt `--allow-localhost <PORT>` per
lokal provider. Hele cplt-grensesnittet — CLI-flagg, sandboxprofil, innebygde
allowlister og enforcement — er versjonsbundet; alle cplt-baserte profiler må
derfor kreve denne eksakte releasen.

## Beslutning

Repositoryet får én eksplisitt livssyklus-CLI,
`scripts/manage_opencode.py`, med subkommandoene `install`, `launch` og
`rollback`. Dette er repositoryets eneste eide, managed/high-assurance
install-/aktiveringslivssyklus for det native OpenCode-targetet. Native
`cplt --agent opencode` er den normale kompatibilitetsveien og trenger ikke
manageren; lifecycle-flyten er valgfri hardening for strengere releasegarantier.

### Klientbootstrap

Managerens klientautentisering begynner ved de ferdige binærbytene den får
lese. En normal npm-installasjon av `opencode-ai@1.18.20` kjører først pakkens
installkode: `postinstall` kjører `verifyBinary` før managerens hashkontroll.
Homebrew er tilsvarende bare en bekvemmelighetsinstallasjon av cplt.

Høy-assurance-flyten må hente den eksakte npm-plattformpakken og den eksakte
cplt-releaseasseten, verifisere upstream-arkivchecksum og inventar, pakke ut
uten installkode og verifisere den reviewede binærdigesten før første kjøring.
Manageren kan så reautentisere de ferdige bytene og stage private kopier, men
kan ikke retroaktivt sikre bootstrapen eller package-managerkode som allerede
har kjørt.

### Distribusjon og installasjon

En publisert OpenCode-asset beholder samme relative layout som repositoryet:

```text
grillmester-opencode-v1/
├── scripts/manage_opencode.py
├── scripts/compose_opencode_permissions.py
├── scripts/verify_client_artifact.py
├── profiles/opencode/*.json
├── policy/client-artifacts.json
├── policy/content-lock.json
├── targets/opencode-v1/**
├── LICENSE
├── PROVENANCE.md
├── THIRD_PARTY_NOTICES.md
└── DISTRIBUTION-MANIFEST.json
```

Den publiserte `tar.gz`-asseten og dens detached checksum er primær
sluttbrukerinstallasjon; en source-checkout eller GitHubs automatisk genererte
source-arkiv er ikke en erstatning. Releasebygget eier den ytre,
deterministiske `tar.gz`-en, dens
`DISTRIBUTION-MANIFEST.json` og en detached SHA-256. Arkivet bygges med sortert
inventar, normaliserte uid/gid/modus og fast timestamp. Bygget kjører ikke
source-kode med release-write-token; det pakker bare allerede validerte filer.

`install` verifiserer deretter targetets indre `manifest.json` før aktivering:

- eksakt inventar; ingen manglende eller ekstra filer
- SHA-256 og deklarert modus for hver fil
- ingen symlinker, path traversal eller ikke-regulære filer
- target- og manifest-skjema som forventet

SHA-256 av manifestets eksakte bytes er release-ID. En release kopieres atomisk
til bruker-eid data under den auditerte cplt-lokasjonen
`~/.local/share/grillmester/opencode/releases/<id>/bundle`, der `~` kommer fra
OS-kontoen og ikke callerens `HOME`/XDG-miljø. Den verifiseres på nytt og gjøres
`0444`/`0555`. En privat, atomisk `state.json` peker på `active` og `previous`.
Samme installasjon er en no-op, en ny installasjon beholder forrige release, og
`rollback` bytter de to etter ny manifestverifikasjon. Ingen release slettes
automatisk. Custom lifecycle home er fortsatt mulig for installasjon, rollback
og eksplisitt `--direct`, men ikke for en cplt-basert launch. Lifecycle home og
distribution source får aldri overlappe i noen retning; ellers kunne install
endre inputen mens den etablerer release, lock og state.

### Launch og staging

`launch` verifiserer aktiv release på nytt og kopierer configen til en unik
per-prosess-stage under `<lifecycle-home>/runtime/sessions/`. Configen
verifiseres og forsegles `0444`/`0555` før ordinær launch. I cplt-modus
pre-seedes en managerkontrollert, digestverifisert, transient `.gitignore` med
det eksakte innholdet OpenCode 1.18.20 ellers forsøker å skrive ved
config-resolusjon. Den finnes både i runtime-configen og i den isolerte
XDG-configen, inngår i de forseglede runtime-inventarene og gir ingen generell
write-grant. Den pinnede OpenCode 1.18.20/Bun-prosessen kan i tillegg miste
halen av en stor enkeltstående stdout-write gjennom en pipe. Resolved-
structure-proben bruker derfor en forseglet, digestbundet projeksjon med
forkortede agent- og skilltekster og uten generert permission-bulk; frontmatter,
kommandoer, skill-assets og resten av strukturen bevares eksakt. Hver full
originalfil og projisert fil bindes med digest. Permission-bulken valideres
separat per agent mot den fulle, forseglede configen; skillroster, description,
projisert content og origin valideres mot projeksjonen. En 48 KiB
release-ratchet gir avstand til den observerte 64 KiB pipe-flushgrensen.
OpenCode kan returnere cplts tillatte `external_directory/allow`-mønstre i
ulik rekkefølge, og cplt velger en ny 32-heks scratch-ID per probe. TOCTOU-
digesten canonicaliserer bare sammenhengende grupper med akkurat denne
permission/action-kombinasjonen og bare det strengt validerte nonce-leddet.
Exact composed suffix, managerbundet XDG tool-output-path, deny-rekkefølge og
alle øvrige agentfelt forblir digest-signifikante.
Deretter
checksum-autentiserer manageren de offisielle OpenCode `1.18.20`- og cplt-
plattformbinærene, kopierer begge byte-identisk til sessionens private
`trusted-bin` og forsegler katalogen før OpenCode-preflight. Den opprinnelige
OpenCode-binæren blir bare lest og startes aldri. Stage er separat fra source og
installert release og ryddes når klientprosessen avsluttes; en rest etter hard
process-kill er bare runtime-data, aldri aktiv release eller consumerdata.

Stage ligger med vilje ikke under `~/.cache`: cplts OpenCode-profil gir brede
cachepaths ambient write-tilgang, og `--allow-read` kan ikke trekke tilbake en
slik tillatelse. Custom `--runtime-root` må ligge under
`<lifecycle-home>/runtime`, og lifecycle home kan ikke overlappe cplts skrivbare
consumer-project eller kjente ambient OpenCode/cache-writeområder.

Standardstart går gjennom cplt og sender eksplisitt:

cplt har allerede native valg av OpenCode med `--agent opencode`; Grillmester
eier ingen parallell sandbox. Launcheren legger bare installert config,
versjonsgate og deklarativ profil oppå denne eksisterende integrasjonen.

Managed cplt-launch på Linux krever GNU/glibc i denne releasen. OpenCode har
pinnede musl-artefakter, men cplt-releasen har ingen musl-asset; musl er derfor
bare støttet gjennom den native/unmanaged OpenCode+cplt-kontrakten brukeren selv
kan realisere, ikke gjennom managerens assurance-claim.

- `--agent opencode`
- `--pass-env OPENCODE_CONFIG_DIR`
- `--pass-env OPENCODE_MODELS_PATH` til en manager-eid, read-only tom katalog
- `--allow-read <per-process-stage>` og aldri `--allow-write` til target/stage
- `--allow-localhost <PORT>` bare for porter brukeren navngir
- ingen `--allow-port`; managed cloud-endepunkter bruker proxyfiltrert HTTPS
  `443`, fordi cplts portflagg ellers gir direkte any-host-egress
- `--allow-private-domain <DOMAIN>` bare når samme eksakte hostname både er
  navngitt som provider og eksplisitt optet inn for privat/intern DNS-resolusjon
- `--preset strict` for en fail-closed standardallowlist, pluss en ephemeral
  `--allowed-domains`-fil for brukerens navngitte cloud-providerhostnavn; cplt
  matcher hvert navn som exact-or-subdomain

Før prosessen startes krever manageren eksakt OpenCode `1.18.20` og eksakt cplt
`2026.08.17-062831-1008a92`, både som offisiell plattformchecksum og observert
versjon fra de private kopiene. Det gjelder `local`, `cloud-open-weight`,
`hybrid` og `local-only`, ikke bare profilen med den strengeste egressgrensen.

Providerhemmeligheter videresendes bare som variabelnavn brukeren oppgir med
`--pass-env`; verdiene skrives ikke i release, profile, state eller policyfil.
Managed mode krever dessuten eksplisitt `--provider-id`, én launcher-eid
`--provider-base-url ID=URL` og minst én `--provider-model ID/MODEL` per valgt
provider. Den resolved configen må matche disse eksakt. Bare reviewet boolsk
capabilitymetadata, enum-avgrensede modalities og positive `limit.context`/
`limit.output` kopieres. Kosmetiske navn, variants og vilkårlige options
kopieres ikke. Provider/modellvalg eies fortsatt av brukeren, ikke
releaseprofilen.

Alle profiler sender en modellnøytral baseline med
`OPENCODE_CONFIG_CONTENT={"autoupdate":false,"share":"disabled"}`,
`OPENCODE_DISABLE_AUTOUPDATE=true` og `OPENCODE_PURE=true`. Baseline er ikke
garantert siste configlag; OpenCodes managed/MDM-config kan merge etterpå.
Manageren bruker derfor den staged klienten til å resolve effektiv config og
avviser launch når resultatet ikke matcher kontrakten.
`OPENCODE_DISABLE_SHARE=true` blokkerer sharing uavhengig av merge-rekkefølgen.
OpenCode `1.18.20` kan importere en ekstern pluginmodul før pure mode stopper
initialisering. Derfor avviser manageren eksterne pluginfiler og plugin-
deklarasjoner fra bruker- og prosjektconfig før klienten starter; pure er et
ekstra lag, ikke importgrensen.

`--direct` bruker samme verifiserte, read-only config-stage, men starter den
opprinnelige caller-resolverte `opencode` uten offisiell checksumkontroll,
private binærstaging eller cplt. Det er et eksplisitt trusted-code-opt-out fra
sandbox- og egresspolicy og kan derfor ikke brukes med profilen `local-only`.

### Deklarative runtimeprofiler

`profiles/opencode/` eier fire reviewbare profiler uten provider, modell,
credential eller token:

- `local`: eksplisitt localhost-port; cplt strict beholder OpenCodes innebygde
  infrastrukturallowlist ved siden av localhost. Profilen er lokal-kapabel, men
  attesterer ikke valgt modell og stenger ikke OpenCodes egen cloud-inference
- `cloud-open-weight`: ett eller flere offentlige providerhostnavn; ingen
  localhost-port, IP-litteral eller privat-domene-opt-in. Navnet uttrykker
  tiltenkt bruk, ikke attestasjon av modell, vekter eller lisens
- `hybrid`: både navngitte providerhostnavn og localhost-porter; eksplisitt
  `--private-provider-domain` for et privat/internt providernavn hører hjemme her
- `local-only`: bare eksplisitte localhost-porter; remote providerdomener er
  forbudt, remote OpenCode-funksjoner slås av, og ekstern egress blokkeres

cplt tolker en tom allowlist som allow-all og kan merge agentens innebygde
allowlist fra global config. `local-only` bruker derfor en ikke-tom `.invalid`-
sentinel i både allow- og blocklisten, samt en blocklist som dekker hele
OpenCode-defaultlisten i den reviewede cplt-releasen. Alle profiler nekter å
kjøre med en annen cplt-versjon
før kontrakten er reviewet på nytt; `local-only` binder i tillegg sin eksakte
blocklist til releasen. Siden cplt union-merger
globale og repo-eide `allow.localhost`-lister, peker manageren `CPLT_CONFIG` på
en tom, kortlivet fil og avviser enhver repo-`[propose]` før `local-only`
starter. De tre vanlige profilene beholder brukerens normale cplt-config for
kompatibilitetssikre deler som corporate upstream-proxy. Launcheren avviser
globale `allow.*`, pass/inherit-env, svakere proxy/default-allowlist, farlige
sandboxtoggler, guard-overrides og enhver repo-`[propose]`; dette hindrer at en
tilsynelatende streng Grillmester-profile skjuler en additiv relaxation. Dette
gjør «local-only» til en håndhevet profil, ikke bare noen OpenCode-
miljøvariabler, samtidig som normalprofilene beholder nødvendig maskin-
kompatibilitet uten å arve vilkårlig cplt-policy.
Manageren snapshotter og revaliderer både global config og `HEAD:.cplt.toml`,
men den pinnede cplt-klienten mangler sealed repo-config og leser repo-inputen
live etter siste managerkontroll. Samtidig fiendtlig kode med samme same-UID er
derfor eksplisitt utenfor assurance-grensen; full lukking krever en upstream
cplt-parameter for en forseglet configsnapshot.
Garantien gjelder harnesset på macOS, der Seatbelt kan pinne forced-proxy-egress
til samme host. Seatbelts `localhost`-selector omfatter alle adresser som
tilhører Mac-en, så manageren låser providerens base-URL separat til loopback og
aksepterer en dokumentert restflate mot andre host-lokale tjenester på den
valgte porten. Eksterne hoster på samme port forblir blokkert. På Linux er
Landlock-reglene portbaserte: kernel `6.7` eller
nyere etterlater en smal ekstern kanal på proxyens ephemeral-port, mens eldre
kernels bare har filesystem-enforcement. `local-only` skal derfor feile lukket
på Linux med denne cplt-pinnen. Localhost-providerprosessen kjører utenfor cplt
og er en separat tillits- og egressgrense.

`cloud-open-weight` gjør ingen DNS-preflight. Et hostname kan endre svar mellom
en slik kontroll og faktisk bruk; cplt-proxyen resolver derfor navnet og
håndhever private-/loopbackgrensen på tilkoblingstidspunktet. Siden cloudprofilen
ikke tillater `--private-provider-domain`, kan ikke denne flaggflaten kortslutte
den public-only-grensen. Privat/intern DNS er en eksplisitt `hybrid`-flyt.

For alle manager-herdede cplt-profiler peker `OPENCODE_MODELS_PATH` på en
manager-eid tom JSON-katalog. Bare provider-/modelloppføringer som både er
eksplisitt valgt i launcherinput og matcher effektiv config beholdes, og
eksekverbar providerkode må bruke nøyaktig `@ai-sdk/openai-compatible`.
`enabled_providers` bindes til eksakt utvalg og `disabled_providers` må være
tomt. Avgrensningen reduserer ambient katalog- og providerflate, men er en
Grillmester-tradeoff og ikke et teknisk cplt-krav.
Unmanaged `cplt --agent opencode` beholder OpenCodes bredere provider- og
modellstøtte.

CLI-argumenter kan erstattes av de deklarative miljøvariablene
`GRILLMESTER_OPENCODE_PROFILE`, `GRILLMESTER_OPENCODE_LOCAL_PORTS`,
`GRILLMESTER_OPENCODE_PROVIDER_DOMAINS`,
`GRILLMESTER_OPENCODE_PROVIDER_IDS`,
`GRILLMESTER_OPENCODE_PROVIDER_BASE_URLS`,
`GRILLMESTER_OPENCODE_PROVIDER_MODELS`,
`GRILLMESTER_OPENCODE_AUTH_PROVIDERS`,
`GRILLMESTER_OPENCODE_PRIVATE_PROVIDER_DOMAINS` og
`GRILLMESTER_OPENCODE_PASS_ENV`.
Ingen provider, modell eller credential ligger i den distribuerte bundle-en.

`--direct` arver eksisterende absolutte XDG-røtter etter overlap-validering.
Managed profiler leser bare eksplisitt valgte API-authoppføringer, setter ellers
`OPENCODE_AUTH_CONTENT={}`, og erstatter XDG config/data/state/cache med private
per-process-kataloger. Den innledende resolved-config-proben gir cplt read-only-
tilgang til nøyaktig den forhåndsskannede `$XDG_CONFIG_HOME/opencode`-katalogen,
også for en custom XDG-rot utenfor brukerens hjem, før denne ambient-flaten
erstattes og kontrolleres på nytt. Bare de launcher-valgte, sanitiserte provider-
og modelloppføringene rekonstrueres i sessionconfigen; ambient XDG-config
kopieres ikke. Launcher-kontrollerte OpenCode-verdier kan ikke erstattes med
`--pass-env`.
Validerte absolutte toolchain-røtter kan videreføres, men en tool-rootvariabel
utelates i sin helhet dersom én verdi overlapper en manager-eid eller kjent
ambient-skrivbar rot; listevariabler delbeholdes ikke. Dette unngår at standard
`PNPM_HOME=~/Library/pnpm` blir en kunstig kompatibilitetsfeil uten å gjøre
området mer eller mindre tillatt i cplts egen plattformpolicy.
Ekstra filesystem-/socket-grants er ikke del av launchergrensesnittet. Brukere
som trenger vilkårlig, bevisst cplt-policy kan bruke cplts native OpenCode-agent
direkte, men er da utenfor managerens auditerte profil- og stagingkontrakt.

## Konsekvenser

- Consumer-repoet får ingen installasjons-, manifest-, config- eller
  stagingfiler. Dets egen `AGENTS.md` og eventuelle `.cplt.toml` forblir i
  kraft.
- Source-targetet og installerte releases er immutable evidens; generert innhold
  kan ikke være runtime scratch.
- En prosess kan fortsatt skrive i consumer-repoet innenfor cplts vanlige
  prosjektpolicy. Denne beslutningen gjør bare Grillmester-policyflaten
  read-only.
- Oppdatering er en ny manifestverifisert installasjon, ikke fetch eller sync i
  en aktiv config directory. Rollback er atomisk og krever ingen Git-checkout.
- Direkte OpenCode gjennom lifecycle-manageren er et eksplisitt opt-out for
  kompatibilitet og diagnose; det har ingen offisiell OpenCode-byteautentisering, private
  binærkopi eller cplt sandbox-, secret- eller egressgaranti.
- Native `cplt --agent opencode` er den normale, brede kompatibilitetsveien;
  manageren er valgfri når releasebundet high-assurance er nødvendig.
- `nav-pilot-agent`, Copilot-plugininstallasjonen og Copilot-agentene er ikke
  avhengigheter. Manageren, bundle-en og de native OpenCode-agentene står på
  egne ben. cplt er en generell, separat sikkerhetswrapper.
- Verifisert surface/runtime betyr ikke modellkvalitetsparitet med Copilot
  eller andre providers; hver konkret modellprofil må kvalitetsgates separat.
- Nye OpenCode- eller cplt-versjoner må gates før de endrer pin, flagg eller
  local-only-listen.

## Forkastede alternativer

- **Gjør direkte kjøring fra source-targetet til managerens assurance-flyt:**
  ville blande generert source, releaseevidens og runtimeområde. Native
  unmanaged cplt kan fortsatt binde et checkout-target for pilotbruk eller det
  utpakkede, checksummede bundle-targetet for ordinær bruk; den flyten påstår
  ikke managerens lifecycle-, staging- eller integritetsgarantier.
- **Kopier inn i consumerens `.opencode/`:** introduserer filsynk, konflikt og
  uklart eierskap i hvert repo.
- **Gi stage `--allow-write`:** gjør agent-/permissionfilene til en mulig
  hot-reload-/self-modification-flate. OpenCode 1.18.20-smoken viser ikke et
  runtimebehov som forsvarer tilgangen.
- **Bruk installert release direkte:** er sikrere enn source-checkout, men
  kobler fremtidige klientartefakter til immutable releasepath. En kortlivet
  read-only stage gir et tydelig runtimegrensesnitt uten å svekke release.
- **Tom allowlist for local-only:** betyr allow-all i cplt og er derfor det
  motsatte av navnet.
- **Legg modell/provider i profilen:** gjør hardware, leverandør og credentials
  til Grillmester-releasepolicy og ødelegger modellnøytraliteten.
- **Arv OpenCodes ambient modellkatalog i managerprofilene:** utvider den
  reviewede flaten med modeller og providerpakker brukeren ikke eksplisitt har
  konfigurert. Unmanaged cplt er kompatibilitetsflaten for dette behovet.
