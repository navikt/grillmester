# Bruke Grillmester i OpenCode

Grillmester har et komplett, native target for den release-gatede klienten
OpenCode `1.18.20`: 7 agenter, 42 skills og 42 slash commands. Agentmodus,
toolnavn, delegering og permissions er oversatt til OpenCodes egne kontrakter;
det er ikke Copilot-pluginen pakket inn på nytt. Andre OpenCode 1-versjoner er
`UNVERIFIED` til de har passert samme gate.

## Native cplt: kom raskt i gang

cplt støtter OpenCode out of the box med `cplt --agent opencode`.
Grillmester legger bare til én config-dir-binding; ingen wrapper eller
lifecycle-manager er nødvendig for kompatibilitet.

For en rask pilot bruker du targetet direkte fra en checkout. For utrulling
pakker du ut den checksummede release-bundle-en beskrevet under; begge har samme
relative targetsti:

```bash
GRILLMESTER_ROOT=/absolute/path/to/checkout-or-extracted-bundle
CONFIG_DIR="$GRILLMESTER_ROOT/targets/opencode-v1"
cd /path/to/consumer-repo
```

Kommandoene under forutsetter at provideren og den eksakte modellen allerede
er deklarert i brukerens `~/.config/opencode/opencode.json`. Bruk det
[komplette lokale provider-eksempelet](local-models.md#koble-opencode-til-den-lokale-serveren)
eller [cloud-eksempelet](#åpen-modell-i-cloud), og velg modellen med `/models`
etter oppstart. GitHub Copilot-provider er unntaket: den kobles til med
OpenCodes vanlige `/connect`.

### Lokal modell på macOS

For en lokal provider på LM Studios standardport `1234`:

```bash
OPENCODE_CONFIG_DIR="$CONFIG_DIR" \
  cplt --agent opencode \
    --project-dir "$PWD" \
    --allow-read "$CONFIG_DIR" \
    --pass-env OPENCODE_CONFIG_DIR \
    --allow-localhost 1234 \
    -- --agent grillmester
```

Bruk `--allow-localhost 8080` i stedet dersom provideren lytter på port `8080`.
Dette er unmanaged cplt på macOS, ikke managerprofilen `local-only`.

### Cloud-provider

Bruk den samme config-dir-bindingen og videresend bare credentialvariabelen som
providerconfigen refererer til:

```bash
export MODEL_PROVIDER_API_KEY='set-locally-never-in-the-bundle'
OPENCODE_CONFIG_DIR="$CONFIG_DIR" \
  cplt --agent opencode \
    --project-dir "$PWD" \
    --allow-read "$CONFIG_DIR" \
    --pass-env OPENCODE_CONFIG_DIR \
    --pass-env MODEL_PROVIDER_API_KEY \
    -- --agent grillmester
```

HTTPS-port `443` er standard. Begrensede providerdomener er managerpolicy eller
en eksplisitt, custom cplt-proxypolicy; de er ikke nødvendig for å binde inn
Grillmester-configen i den native unmanaged-flyten.

OpenCodes innebygde GitHub Copilot-provider kan brukes i samme native kommando
etter normal `/connect` i OpenCode; cplt beskriver dette som støtte for en
eksisterende GitHub Copilot-subscription. Autentiseringen tilhører OpenCode og
krever verken `nav-pilot-agent` eller Grillmesters manager. Denne PR-gaten
kjører med vilje ikke en autentisert Copilot-/providerforespørsel; den validerer
config, discovery, permissions og lokale fake-provider-scenarier uavhengig.
Managerens smalere `--provider-id`-filter gjelder bare den valgfrie
high-assurance-flyten for eksplisitte OpenAI-compatible providers.

cplts vanlige `standard`-profil har ingen fail-closed domeneallowlist, så den
samme kommandoen er nok for `/connect`. Hvis du eller global cplt-config bruker
`--preset strict`, `--default-allowlist` eller
`proxy.default_allowlist=true`, velger cplt derimot OpenCode-agentens
infrastrukturliste, ikke Copilot-agentens providerliste. Legg da følgende
eksakte domener fra den pinnede cplt-releasens Copilot-liste i en brukereid fil:

```text
githubcopilot.com
api.github.com
github.com
copilot-proxy.githubusercontent.com
actions.githubusercontent.com
default.exp2.cds.s9ch.io
```

Bind filen til samme native launch med
`--allowed-domains /absolute/path/to/opencode-copilot-domains.txt`. cplt merger
filen med OpenCodes egne standarddomener og package-registries. Bare domener
som faktisk trengs for den pinnede OpenCode-/cplt-kombinasjonen skal stå der;
les `BLOCKED-ALLOWLIST` i proxyloggen ved en kontrollert oppgradering. Ikke bruk
`--allow-all-domains` som kompatibilitetsfiks, fordi den slår av den
fail-closed domenegrensen.

| Egenskap | Native `cplt --agent opencode` | Valgfri manager |
| --- | --- | --- |
| Providerflate | OpenCodes vanlige providers, inkludert GitHub Copilot | Eksplisitte OpenAI-compatible providers |
| `navikt/copilot` | Kan merge en allerede synket nav-pilot-eksport | Isolert; nav-pilot-eksport brukes ikke |
| Grillmester-binding | `OPENCODE_CONFIG_DIR` + `--allow-read` | Immutable installasjon og kortlivet stage |
| Sikkerhetsprofil | cplts vanlige policy + eksplisitte grants | Checksums, resolved-config-gate og deklarative profiler |

Unmanaged cplt over er den normale kompatibilitetsflyten. Når et team eller en
runtimeeier eksplisitt krever den strengere assurance-kontrakten, kan de velge
en manifestverifisert installasjon i brukerdata og en kortlivet runtime-stage gjennom
[cplt](https://github.com/navikt/cplt). Configen er read-only, mens checksummede
OpenCode- og cplt-bytes kjøres fra en privat, forseglet `trusted-bin`. Verken
installasjon eller staging skriver i consumer-repoet, og ingen OpenCode-prosess
kjører direkte fra det genererte source-targetet. Manageren og de syv native
agentene er selvstendige: de krever verken `nav-pilot-agent`,
Copilot-plugininstallasjon eller en Copilot-agent i runtime. Manageren er ikke
en forhåndsgodkjent Nav-standard og er ikke nødvendig for cplt-kompatibilitet.

Denne støtten betyr at agent-, skill-, delegerings- og permissionflaten er
verifiserbar i OpenCode. Den er ikke et løfte om at en vilkårlig lokal eller
cloudmodell leverer samme kvalitet som GitHub Copilot. Hver konkret modell,
kvantisering, provider og contextprofil må bestå sin egen capability- og
kvalitetssmoke.

OpenCode 2 er fortsatt beta og er ikke en støttet Grillmester-klientflate. Bruk
binæren `opencode`, ikke `opencode2`, for den release-gatede flaten. Se
[grensen mot OpenCode 2](#grensen-mot-opencode-2).

## Installer eksakte klienter

Skill mellom en bekvemmelighetsinstallasjon og bootstrap-evidens. Ved en vanlig
`npm install --global opencode-ai@1.18.20` kjører pakkens installkode:
`postinstall` kjører `verifyBinary` før manageren kan hashe den installerte
binæren. Homebrew er en bekvemmelighetsinstallasjon for cplt, ikke bevis på en
høy-assurance bootstrap.

Ved vanlig utvikling kan de pinnede convenience-kommandoene brukes:

Lifecycle-manageren bruker bare Python-standardbiblioteket, men krever
Python `3.11` eller nyere (`tomllib`). Kontroller den sammen med
OpenCode-versjonen først:

```bash
python3 -c 'import sys; assert sys.version_info >= (3, 11)'
npm install --global opencode-ai@1.18.20
test "$(opencode --version)" = "1.18.20"
```

Standardlauncheren bruker cplt. Den reviewede nettverkskontrakten er pinnet til
cplt [`2026.08.17-062831-1008a92`](https://github.com/navikt/cplt/releases/tag/2026.08.17-062831-1008a92).
Homebrew-formelen må faktisk resolve denne releasen:

```bash
brew install navikt/tap/cplt
test "$(cplt --version)" = "cplt 2026.08.17-062831-1008a92"
```

`cplt doctor` er en valgfri, global maskindiagnose, ikke en nødvendig
OpenCode-sjekk. I denne cplt-pinnen prober den alle installerte agenter og kan
kjøre `copilot --version` samt GitHub-authdiagnostikk når Copilot finnes på
maskinen. Bruk derfor den eksakte versjonskontrollen over og OpenCode-smokene
under for en OpenCode-only validering.

For høy assurance: hent den eksakte npm-plattformpakken for OpenCode
`1.18.20` og den eksakte cplt-releaseasseten direkte. Verifiser
upstream-arkivchecksummen, forventet inventar og den reviewede binærdigesten før
første kjøring. Legg først deretter de verifiserte binærene på `PATH` for
manageren. Managerens senere checksum- og stagingkontroll kan ikke retroaktivt
sikre bootstrapen eller kode som en package manager allerede har kjørt.

Bundle-ens [immutable klientlås](../policy/client-artifacts.json) inneholder URL,
arkivstørrelse, upstream-digest, eksakt tar-roster og binærdigest. Den bundled
verifieren velger én eksakt OS/arkitektur/libc/variant-rad, printer bare den
autentiserte URL-en og ekstraherer uten nettverk eller klientkjøring. Dette
copy/paste-eksemplet er for Apple Silicon; bruk `x86_64` på Intel Mac. Managed
cplt på Linux er i denne releasen låst til GNU/glibc-asseten; OpenCode har også
musl-bytes for native/unmanaged bruk, men ingen tilsvarende cplt-musl-asset og
derfor ingen managed musl-garanti:

```bash
bundle=/absolute/path/to/grillmester-opencode-v1
verify="$bundle/scripts/verify_client_artifact.py"
lock="$bundle/policy/client-artifacts.json"
host_os=darwin
host_arch=arm64
opencode_libc=none
cplt_libc=none
variant=default
downloads="$PWD/client-downloads"
verified_bin="$PWD/verified-bin"
mkdir -m 700 "$downloads" "$verified_bin"

opencode_url="$(python3 -I -S "$verify" --lock "$lock" --client opencode \
  --os "$host_os" --arch "$host_arch" --libc "$opencode_libc" \
  --variant "$variant" --print-url)"
cplt_url="$(python3 -I -S "$verify" --lock "$lock" --client cplt \
  --os "$host_os" --arch "$host_arch" --libc "$cplt_libc" \
  --variant default --print-url)"
curl --fail --location --proto '=https' --tlsv1.2 \
  --output "$downloads/opencode.tgz" "$opencode_url"
curl --fail --location --proto '=https' --tlsv1.2 \
  --output "$downloads/cplt.tar.gz" "$cplt_url"
python3 -I -S "$verify" --lock "$lock" --client opencode \
  --os "$host_os" --arch "$host_arch" --libc "$opencode_libc" \
  --variant "$variant" --archive "$downloads/opencode.tgz" \
  --output-dir "$verified_bin"
python3 -I -S "$verify" --lock "$lock" --client cplt \
  --os "$host_os" --arch "$host_arch" --libc "$cplt_libc" \
  --variant default --archive "$downloads/cplt.tar.gz" \
  --output-dir "$verified_bin"
```

Bruk deretter de absolutte filene som `--opencode "$verified_bin/opencode"`
og `--cplt "$verified_bin/cplt"`. En feil selector, ekstra tar-member, feil
størrelse eller digest publiserer ingen kjørbar output.

Se OpenCodes [offisielle CLI-guide](https://opencode.ai/docs/cli/) og cplts
[offisielle installasjon](https://github.com/navikt/cplt#install). En nyere
OpenCode-binær er ikke automatisk dekket av Grillmesters release-gate. Alle
cplt-baserte profiler nekter å starte med en annen cplt-release; pinnen dekker
CLI-flagg, sandboxprofil, innebygde allowlister og enforcement som ett reviewet
runtimegrensesnitt. I cplt-modus krever manageren i tillegg at den resolverte
OpenCode-binæren er byte-identisk med en offisiell plattformbinær fra npm-
distribusjonen av `opencode-ai@1.18.20`. Den opprinnelige binæren leses og
checksummes, men startes ikke.

## Installer en immutable Grillmester-bundle

Den primære installasjonskilden er OpenCode-assetene på den reviewede
[GitHub-releasen](https://github.com/navikt/grillmester/releases): én
deterministisk `tar.gz` og dens detached `.sha256`. Ikke bruk GitHubs automatisk
genererte source-arkiv som OpenCode-bundle. Last ned begge assetene fra samme
release, bruk de eksakte filnavnene som releasen oppgir, og verifiser før
utpakking, for eksempel:

```bash
cd /path/to/downloads
tag=vREPLACE_WITH_VERSION
asset="grillmester-opencode-${tag}.tar.gz"
shasum -a 256 -c "${asset}.sha256"
tar -xzf "${asset}" -C /path/to/user-owned/extraction
```

Bundle-en inneholder manageren, profilene og targetet under roten
`grillmester-opencode-v1/`. Inspiser at
`DISTRIBUTION-MANIFEST.json` binder den forventede source-SHA-en, OpenCode
`1.18.20`, cplt `2026.08.17-062831-1008a92` og eksakt filinventar. Installer
deretter:

```bash
cd /path/to/extracted/grillmester-opencode-v1
python3 -I -S scripts/manage_opencode.py install
```

Bruk en eksplisitt betrodd Python 3.11+ og behold `-I -S` på `install`,
`launch` og `rollback`. Manageren er stdlib-only; flaggene ignorerer
`PYTHONPATH`/user-site og laster ikke `site`/`sitecustomize` før managerens egne
kontroller. Selve Python-binæren er fortsatt en bootstrap-tillitsrot. Manageren
avviser managed lifecycle-kall som startes uten disse flaggene; native cplt og
den eksplisitte `--direct`-opt-out-en er uavhengige av dette laget.

Manageren verifiserer også targetets indre manifest: eksakt filinventar,
SHA-256, filmodus, targettype og fravær av symlinker/path traversal. Deretter
installeres en content-addressed, read-only release under den auditerte
standardlokasjonen `~/.local/share/grillmester/opencode/`, der `~` er
OS-kontoens home og ikke en caller-styrt `HOME`-verdi. Samme bundle er en
idempotent no-op. En ny bundle aktiveres atomisk og beholder forrige release
for rollback. Behold den checksumverifiserte, utpakkede bundle-en på en
bruker-eid plassering: manageren kjøres derfra ved launch og rollback, mens
targetpayloaden ligger i lifecycle home.

En source-checkout er bare utviklingsinput for vedlikeholdere og er ikke den
støttede sluttbrukerinstallasjonen. `main`, GitHubs source-arkiv og løse kopier
av `targets/opencode-v1/` erstatter ikke den checksummede release-bundle-en.

## Velg runtimeprofil

Bundle-en velger aldri provider, modell eller credential. I en manager-herdet
cplt-session peker `OPENCODE_MODELS_PATH` på en manager-eid, read-only tom
modellkatalog. Dermed kommer modeller bare fra en provider og modell som er
eksplisitt deklarert i den effektive OpenCode-configen. For denne flaten må
provideren bruke nøyaktig npm-pakken `@ai-sdk/openai-compatible`; andre
providerpakker avvises før launch. Dette er en bevisst Grillmester-avgrensning av
eksekverbar providerkode, ikke et krav i cplt. Ordinær, unmanaged cplt kan bruke
OpenCodes ambient modellkatalog og bredere providerstøtte.

Velg én eksplisitt profil ved hver start:

| Profil | Lokal inference | Cloud-inference | Annen ekstern egress |
| --- | --- | --- | --- |
| `local` | Mulig på eksplisitte porter | Ikke sperret via OpenCode-infrastrukturen | cplt strict sin innebygde OpenCode-allowlist |
| `cloud-open-weight` | Ingen localhost-port | Eksakt valgte provider-ID-er, HTTPS-base-URL-er og modeller | cplt strict sin innebygde OpenCode-allowlist |
| `hybrid` | Mulig på eksplisitte porter | Navngitte provider-hostnavn | cplt strict sin innebygde OpenCode-allowlist |
| `local-only` | Eksplisitte porter | Blokkert med full håndheving på macOS | Blokkert med full håndheving på macOS |

`local` er altså en lokal-kapabel profil, ikke et bevis på at faktisk inference
er lokal. Manageren binder configens eksakte provider-ID, base-URL og tillatte
modell-ID-er til launcherinput, men attesterer ikke modellvekter, lisens,
kvalitet eller hva serveren faktisk leverer bak en modell-ID. cplt strict
tillater fortsatt blant annet `opencode.ai`. Bare `local-only` stenger den
innebygde OpenCode-infrastrukturen.

Alle profiler leverer en modellnøytral baseline med `share: "disabled"` og
`autoupdate: false`; den er ikke garantert å være siste configlag. OpenCodes
managed/MDM-config kan merge senere. Manageren lar derfor den privat staged
klienten resolve effektiv config og avviser launch hvis det resolved resultatet
ikke matcher den herdede kontrakten. Sharing blokkeres uavhengig av
merge-rekkefølgen med `OPENCODE_DISABLE_SHARE=true`, mens
`OPENCODE_DISABLE_AUTOUPDATE=true` slår av klientoppdatering.

Manageren setter også den kanoniske boolverdien `OPENCODE_PURE=true` for hver
launch og eier verdien; callerens `--pure`/`--no-pure` avvises. OpenCode
`1.18.20` har likevel en separat core V2-loader som verken respekterer pure mode
eller `OPENCODE_DISABLE_PROJECT_CONFIG` for prosjektets `.opencode`-flate.
Manageren kompenserer for en stabil oppstartsflate ved å avvise alle
prosjektkomponenter i `.opencode` unntatt `opencode.json[c]`, og disse filene
må være restriction-only: bare `$schema`, monotone `ask`/`deny`, deaktiverte
tools og tilsvarende restriksjoner for de syv kjente agentene. Alle cplt-debug-
og permissionprober bruker et tomt, disposable preflight-project, og
`OPENCODE_TEST_HOME` peker på en forseglet, tom sessionkatalog. Før hver
cplt-basert launch kontrollerer manageren både OpenCode `1.18.20` og cplt
`2026.08.17-062831-1008a92` med checksum og eksakt versjonslikhet. Bruk ordinær,
unmanaged `cplt --agent opencode` hvis en ekstern OpenCode-plugin faktisk er
tilsiktet; den flyten har ikke managerens resolved-config-, plugin- eller
pure-mode-garanti.

### Lokal modell

Når brukerconfigen peker på LM Studio på port `1234`:

```bash
cd /path/to/consumer-repo
python3 -I -S /path/to/grillmester-opencode-v1/scripts/manage_opencode.py launch \
  --profile local \
  --provider-id lmstudio \
  --provider-base-url lmstudio=http://127.0.0.1:1234/v1 \
  --provider-model lmstudio/replace-with-id-from-v1-models \
  --local-port 1234
```

cplt blokkerer localhost som standard. Launcheren åpner bare portene som står i
kommandoen; den bruker ikke `--allow-localhost-any`. Se
[lokale modeller](local-models.md) for providerconfig og capability-smoke.
Det komplette lokale configeksempelet der bruker samme eksplisitte
`@ai-sdk/openai-compatible`-provider og `baseURL` på loopback; den
manager-eide tomme modellkatalogen fjerner ikke eksplisitt deklarerte modeller.
`--provider-id` velger eksakt provider og binder den resolverte `baseURL`-en til
den deklarerte loopback-porten. Uvalgte providers og credentials kopieres ikke
til sessionen; `enabled_providers` låses til utvalget. Bruk `local-only` når
også OpenCodes innebygde infrastruktur-egress skal stenges.

### Åpen modell i cloud

Profilnavnet beskriver den tiltenkte bruken, men manageren attesterer ikke at
modellvektene er åpne eller at lisensen er godkjent. Cloudprofilen velger ikke
leverandør eller modell. Deklarer først den eksakte modellen i brukerens
`~/.config/opencode/opencode.json`, for eksempel mot et generisk offentlig,
OpenAI-kompatibelt endepunkt:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "openweight-cloud": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Reviewed open-weight cloud endpoint",
      "options": {
        "baseURL": "https://inference.example.org/v1",
        "apiKey": "{env:MODEL_PROVIDER_API_KEY}"
      },
      "models": {
        "replace-with-provider-model-id": {
          "name": "Reviewed open-weight model",
          "tool_call": true,
          "modalities": {"input": ["text"], "output": ["text"]},
          "limit": {"context": 32768, "output": 8192}
        }
      }
    }
  }
}
```

Oppgi deretter bare de faktiske offentlige hostnavnene cplt må tillate, og
navnene på credentialvariablene configen bruker:

```bash
export MODEL_PROVIDER_API_KEY='set-locally-never-in-the-bundle'

cd /path/to/consumer-repo
python3 -I -S /path/to/grillmester-opencode-v1/scripts/manage_opencode.py launch \
  --profile cloud-open-weight \
  --provider-id openweight-cloud \
  --provider-base-url openweight-cloud=https://inference.example.org/v1 \
  --provider-model openweight-cloud/replace-with-provider-model-id \
  --provider-domain inference.example.org \
  --pass-env MODEL_PROVIDER_API_KEY
```

`--pass-env` lagrer bare variabelnavnet i prosessargumentene; manageren
rekonstruerer providerens `apiKey` som `{env:MODEL_PROVIDER_API_KEY}`, så
credentialverdien skrives ikke i bundle, profile, state, composed config eller
cplt-allowlisten. Hver `--provider-id` krever én eksakt
`--provider-base-url ID=URL` og minst én `--provider-model ID/MODEL`; kosmetiske
provider-/modellnavn kopieres ikke. Modellens `limit.context` og `limit.output`
må være positive. Bruk `--provider-domain` og `--pass-env` per behov. cplt
matcher hvert domene som
«samme hostname eller et subdomene», så oppgi det smaleste faktiske
provider-hostnavnet; `example.org` tillater også `*.example.org`. cplt strict
merger disse suffixene med sin innebygde OpenCode-liste (`opencode.ai`,
`models.dev` og registries) og blokkerer andre eksterne domener. Den innebygde
listen betyr samtidig at profilnavnet ikke er en teknisk attestasjon av aktiv
modell eller provider. Managed mode bruker proxyfiltrert HTTPS-port `443`.
Andre providerporter avvises: cplts `--allow-port` er en direkte any-host-
kernelregel og kan ikke bindes til providerdomenet. Bruk native unmanaged cplt
med denne eksplisitte tradeoff-en, eller vent på en upstream scoped proxy-port.
`cloud-open-weight` avviser
localhostnavn, IP-litteraler og `--private-provider-domain`; bruk `hybrid` for
et eksplisitt privat eller internt endpoint. Manageren gjør ingen DNS-preflight,
fordi et hostname kan endre svar mellom preflight og tilkobling. Den pinnede
cplt-proxyen resolver og håndhever public/private- og loopbackgrensen på
tilkoblingstidspunktet, som unngår denne TOCTOU-feilen.

### Hybrid

Hybrid åpner både den eksakte lokale porten og de navngitte cloud-hostnavnene
med samme exact-or-subdomain-semantikk som over:

```bash
python3 -I -S /path/to/grillmester-opencode-v1/scripts/manage_opencode.py launch \
  --profile hybrid \
  --provider-id openweight-cloud \
  --provider-id lmstudio \
  --provider-base-url openweight-cloud=https://inference.example.org/v1 \
  --provider-base-url lmstudio=http://127.0.0.1:1234/v1 \
  --provider-model openweight-cloud/replace-with-provider-model-id \
  --provider-model lmstudio/replace-with-id-from-v1-models \
  --local-port 1234 \
  --provider-domain inference.example.org \
  --pass-env MODEL_PROVIDER_API_KEY
```

Dette passer når primary-agenten bruker sessionens cloudmodell mens for
eksempel Kokk har en bruker-eid lokal modelloverride. Grillmester-targetet
pinner ingen av dem. Et privat eller internt providernavn må i denne profilen
oppgis både som `--provider-domain inference.internal.example` og
`--private-provider-domain inference.internal.example`. Managed mode støtter
bare HTTPS-port `443` for cloud-endepunktet.

### Local-only

`local-only` er strengere enn «modellen er lokal»:

```bash
python3 -I -S /path/to/grillmester-opencode-v1/scripts/manage_opencode.py launch \
  --profile local-only \
  --provider-id lmstudio \
  --provider-base-url lmstudio=http://127.0.0.1:1234/v1 \
  --provider-model lmstudio/replace-with-id-from-v1-models \
  --local-port 1234
```

Profilen forbyr providerdomener, deaktiverer OpenCodes update-, model-catalog-,
LSP-download-, default-plugin-, share- og Exa-flyter, og bruker cplts forced
proxy med en fail-closed allow-/blocklist. Listen dekker cplts komplette
OpenCode-defaults i den pinnede cplt-releasen; bare den navngitte localhost-
porten slipper gjennom. En tom cplt-allowlist betyr allow-all og brukes derfor
aldri. En ikke-tom `.invalid`-sentinel aktiverer allowlist-modus og står også i
blocklisten, slik at sentinelen selv ikke er et nettverksmål.

Denne garantien gjelder harnessprosessen, ikke providerprosessen som lytter på
localhost. LM Studio, `llama-server` eller en annen lokal provider kjører
utenfor cplt-sandboxen og må selv være betrodd og ha en separat egresspolicy
hvis hele kjeden skal være offline.

Den pinnede cplt-releasen har full forced-proxy-håndheving på macOS: Seatbelt
kan pinne egress til proxyens localhost-port. Linux er ikke ekvivalent. Kernel
`6.7` eller nyere gir Landlock TCP-regler, men de er portbaserte og etterlater
en smal kanal til en ekstern host som tilfeldigvis svarer på proxyens
ephemeral-port; eldre Linux har bare filesystem-enforcement. Launcheren skal
derfor feile lukket for `local-only` på Linux med denne cplt-pinnen. En vanlig
`local`-profil kan fortsatt brukes der uten en absolutt offlinepåstand.
På Linux er også `--allow-localhost PORT` en portregel som kan nå en ekstern
host på samme port. `local` og `hybrid` på Linux er derfor sandboxede
kompatibilitetsprofiler, ikke full hostname-egressisolasjon.

For `local-only` erstatter manageren global `CPLT_CONFIG` med en tom,
kortlivet config og avviser alle repoets `[propose]`-relaxations før start.
Profilen arver dermed ikke flere localhost-porter eller andre allow-regler fra
maskin eller repo. De vanlige `local`, `cloud-open-weight` og `hybrid`-profilene
beholder bare kompatibilitetssikre deler av brukerens normale cplt-config, blant
annet corporate upstream-proxy, og lar den pinnede cplt-klienten sanitere det
normale hostmiljøet. Skjulte relaxations som `sandbox.inherit_env`, globale
`allow.*`, svakere proxy/default-allowlist og alle repoets `[propose]` avvises;
bruk de eksplisitte Grillmester-flaggene som faktisk finnes, og les cplts
launchoppsummering før du godkjenner. Dette er en strengere releasepolicy enn
bar `cplt --agent opencode` ut av boksen. Ekstra filesystem- eller socket-grants
er ikke eksponert av den auditerte launcheren.

Managed launch starter med en fersk in-memory OpenCode-sesjonsdatabase, deaktiverer
native `build`/`plan`/`general`/`explore` og gjør bare valgt Grillmester-primary
synlig; `--session`, `--continue` og `--fork` avvises. Velg **Allow once** ved
`ask`. OpenCodes **Always** er en eksplisitt prosessvid relaxasjon som evalueres
etter agentreglene; TUI-ens auto-approve er en tilsvarende bevisst relaxasjon.
Restart manageren for å tømme prosessgodkjenninger. Garantien om deny gjelder
derfor fersk launch uten Always eller auto-approve. Manageren setter også
`--no-audit`: cplts parent-side change-audit bruker `git status` før sandboxen og
kan ellers trigge repoets `core.fsmonitor`. Unmanaged cplt kan beholde denne
auditen når den lokale Git-konfigurasjonen er betrodd.

Uten `--auth-provider` leser manageren ikke kontoens `auth.json` og sender
`{}`. Et gjentatt `--auth-provider ID` (eller
`GRILLMESTER_OPENCODE_AUTH_PROVIDERS`) velger eksplisitt én oppføring; først
etter at samme custom provider-ID og SDK er validert, leses den bounded
auth-snapshoten og akkurat den valgte `api`-oppføringen blir canonical
`OPENCODE_AUTH_CONTENT`. Alle uvedkommende credentials utelates, og
`local-only` tillater ingen auth-selector. En valgt
`wellknown` avvises fordi typen ellers merger fjernkonfig per prosess, og en
valgt OAuth-oppføring avvises fordi den bare har consumers i provider-/plugin-
loaderne som managed mode forbyr. Credentialverdier legges ikke i argv, state
eller logger. `OPENCODE_DB=:memory:` betyr også at AccountTable ikke gjenbrukes.
Bruk helst en eksplisitt provider-credential-variabel. Native unmanaged cplt
beholder OpenCodes vanlige auth- og accountmodell.

Manageren leser og fingerprinter cwd→repo-root-kjeden av `AGENTS.md` og
`CONTEXT.md`, kopierer de eksakte byteverdiene til den private config-stagen og
peker `instructions` på disse `0444`-filene før hele stagen forsegles. Senere
endringer i originalfilene kan derfor ikke endre denne launchens toppnivåprompt.
En stock-klientgrense står likevel igjen: OpenCode 1.18.20 kan oppdage en ny,
nestet `AGENTS.md` eller `CONTEXT.md` når en fil under katalogen leses, også med
project-config deaktivert. Agentpromptene behandler dem som ubetrodd
repoinnhold; releasegarantien er derfor ikke en påstand om eksklusiv
promptkilde. Full eliminering krever en upstream-bryter eller en patchet
OpenCode-binær.

Manageren tar dessuten snapshots av global cplt-config og repoets
`HEAD:.cplt.toml`, validerer dem og sjekker dem igjen rett før start. Den pinnede
cplt-klienten har imidlertid ingen sealed repo-config-modus og leser repo-
configen live etter at childprosessen er startet. En annen prosess med samme
same-UID kan derfor fortsatt vinne det siste check/use-vinduet, på samme måte
som den kan endre en ny prosjektplugin etter siste OpenCode-scan. Managed
hardening beskytter mot ambient og stabil repo-config, ikke mot samtidig
fiendtlig kode med samme brukerkonto. Å lukke dette fullt krever upstream cplt-
støtte for en forseglet configsnapshot og OpenCode-støtte som faktisk slår av
all prosjekt- og nested-instruction-discovery.

`local-only` kan ikke kombineres med `--direct`. En OpenCode-miljøvariabel er
ikke en OS-egressgrense; profilen får bare navnet når den eksakt pinnede cplt-
releasen håndhever den. De tre andre cplt-baserte profilene har samme
versjonspin, selv om nettverksreglene deres er mindre restriktive.

### Deklarativt miljø

CI-/maskinprofiler kan uttrykke samme input uten å endre bundle-en:

```bash
export GRILLMESTER_OPENCODE_PROFILE=hybrid
export GRILLMESTER_OPENCODE_LOCAL_PORTS=1234
export GRILLMESTER_OPENCODE_PROVIDER_DOMAINS=inference.example.org
export GRILLMESTER_OPENCODE_PROVIDER_IDS=openweight-cloud,lmstudio
export GRILLMESTER_OPENCODE_PROVIDER_BASE_URLS=openweight-cloud=https://inference.example.org/v1,lmstudio=http://127.0.0.1:1234/v1
export GRILLMESTER_OPENCODE_PROVIDER_MODELS=openweight-cloud/replace-with-provider-model-id,lmstudio/replace-with-id-from-v1-models
export GRILLMESTER_OPENCODE_PRIVATE_PROVIDER_DOMAINS=inference.example.org
export GRILLMESTER_OPENCODE_PASS_ENV=MODEL_PROVIDER_API_KEY

python3 -I -S /path/to/grillmester-opencode-v1/scripts/manage_opencode.py launch
```

Flere verdier er kommaseparerte. `GRILLMESTER_OPENCODE_HOME` og
`GRILLMESTER_OPENCODE_RUNTIME_ROOT` kan overstyre henholdsvis data- og
runtime-lokasjon ved installasjon, rollback og eksplisitt `--direct`-kjøring.
En cplt-basert launch godtar derimot bare den auditerte lifecycle-lokasjonen
`~/.local/share/grillmester/opencode`; en custom manager-home kan ikke velges
via `XDG_DATA_HOME`. En custom runtime-root må uansett være under
`<GRILLMESTER_OPENCODE_HOME>/runtime`; den kan ikke flyttes til `~/.cache` eller
consumer-repoet. Provider- og modellvalg skal fortsatt ikke inn i en distribuert
Grillmester-profile.

`--direct` arver eksisterende absolutte XDG-røtter etter overlap-validering og
er et eksplisitt trusted-code-opt-out. Managed profiler leser bare en eksplisitt
valgt `XDG_DATA_HOME/opencode/auth.json`-oppføring. Etter én read-only,
sandboxet resolved-config-probe rekonstrueres bare eksplisitt valgte
provider-ID-er, launcher-eide base-URL-er, modell-ID-er og reviewet
capabilitymetadata med enum-avgrensede modalities i den manager-eide configen.
Kosmetiske navn, `{file:...}`-
verdier og agent-variants kopieres ikke. XDG config/data/state/cache erstattes så
med private per-process-kataloger. Det
hindrer OpenCode i å skrive tilbake til ambient auth, legacy-auth, MCP-auth,
sessions, TUI-config eller cache, og katalogene fjernes ved exit.
Launcher-kontrollerte verdier kan ikke legges tilbake via `--pass-env`.
Managed mode beholder validerte, absolutte toolchain-røtter, men utelater hele
miljøvariabelen når én oppgitt sti overlapper consumeren, lifecycle-området,
midlertidige kataloger eller kjente ambient-skrivbare toolområder. Dermed er en
vanlig macOS-verdi som `PNPM_HOME=~/Library/pnpm` ikke en launch-feil og blir
heller ikke annonsert til OpenCode; listevariabler filtreres aldri delvis.

## Hva launcheren faktisk gjør

cplt støtter allerede OpenCode direkte med `cplt --agent opencode`. Grillmester
erstatter ikke den integrasjonen eller sandboxen. En minimal, unmanaged start
fra et checksumverifisert og utpakket target kan se slik ut:

```bash
CONFIG_DIR=/absolute/path/to/grillmester-opencode-v1/targets/opencode-v1
OPENCODE_CONFIG_DIR="$CONFIG_DIR" \
  cplt --agent opencode \
    --project-dir "$PWD" \
    --allow-read "$CONFIG_DIR" \
    --pass-env OPENCODE_CONFIG_DIR \
    -- --agent grillmester
```

Ingen custom wrapper er nødvendig for denne native integrasjonen. Lifecycle-
manageren er valgfri hardening oppå den: immutable installasjon og rollback,
offisielle klientchecksums, private binærkopier, resolved-config- og
permissionvalidering, en tom modellkatalog og deklarative nettverksprofiler.
I både den forseglede, kortlivede config-stagen og den isolerte XDG-configen
pre-seeder manageren også den eksakte `.gitignore`-filen OpenCode 1.18.20 ellers
forsøker å opprette ved oppstart; det gir kompatibilitet uten write-tilgang til
agent- og permissionfilene.
Unmanaged cplt-kommandoen arver OpenCodes vanlige config-, plugin-, provider- og
modellflate og har ingen av disse managergarantiene.

Den pinnede OpenCode 1.18.20/Bun-prosessen kan miste halen av en stor,
enkeltstående stdout-write når output går gjennom en pipe. Manageren bruker
derfor en forseglet resolved-structure-projeksjon med forkortede agent- og
skilltekster og uten den permission-bulken som valideres separat mot den fulle
configen per agent. Agent- og skill-frontmatter, kommandoer, skill-assets og
alle øvrige configfelt bevares eksakt. Hver full originalfil og hver projisert
fil bindes med digest, skill-ID/description/origin/marker-body og den pinnede
builtin-skillens identity/origin valideres, og config-, agent- og skillprober må
holde seg under en 48 KiB release-ratchet før launch.

OpenCode kan returnere cplts tillatte `external_directory`-mønstre i ulik
rekkefølge mellom prosesser, og cplt bruker en ny 32-heks scratch-ID per probe.
Same-stage-digesten sorterer derfor bare sammenhengende
`external_directory/allow`-grupper, normaliserer bare dette validerte nonce-
leddet og krever fortsatt den eksakte composed permission-suffiksen og den
managerbundne XDG `tool-output`-regelen. Deny-regler og grenser mellom ulike
permissions/actions beholdes i rå rekkefølge.

Når en normal, bevisst custom cplt-policy er viktigere enn denne fail-closed
profilkontrakten, er ordinær `cplt --agent opencode` fortsatt den native
out-of-the-box-flyten. Da må Grillmester-configen bindes inn manuelt, og
managerens lifecycle-, staging- og `local-only`-garantier skal ikke hevdes for
den sessionen.

Før hver prosess verifiserer manageren aktiv release på nytt, kopierer configen
til en unik stage under `<lifecycle-home>/runtime/sessions/`, verifiserer kopien
og gjør det ferdige configtreet `0444`/`0555`. I cplt-modus checksum-
autentiseres de offisielle OpenCode `1.18.20`- og cplt-binærene før de kopieres
byte-identisk til sessionens private `trusted-bin`; katalogen forsegles før
OpenCode-preflight og launch. `PATH` bindes til den staged OpenCode-kopien. Den
opprinnelige OpenCode-binæren startes aldri i denne modusen og kan heller ikke
endres gjennom sessionens `trusted-bin`. Hele stage-området er separat fra både
source og release og fjernes når klienten avslutter.

Install nekter også lifecycle home som er lik, inneholder eller ligger under
den verifiserte distribution source-katalogen. Installasjonen kan dermed ikke
skrive release-, lock- eller statefiler inn i inputen den samtidig verifiserer.

Denne plasseringen er en sikkerhetsgrense. cplts OpenCode-profil har brede
ambient write-regler under `~/.cache`; `--allow-read` kan ikke oppheve en write
som allerede gjelder fra en annen regel. Manageren avviser derfor cachepaths,
OpenCodes egne skrivbare data-/stateområder og alle lifecycle homes som
overlapper consumerens project directory.

Standardkommandoen tilsvarer konseptuelt:

```text
cplt --agent opencode \
  --preset strict \
  --allow-read <read-only-stage> \
  --pass-env OPENCODE_CONFIG_DIR \
  ...profilens eksakte nettverk/env... \
  -- <OpenCode-argumenter>
```

Det finnes med vilje ingen `--allow-write` for Grillmester-stage eller release.
Agent- og permissionfiler er en policyflate og skal ikke kunne endres eller
hot-reloades av prosessen. Consumer-repoet er fortsatt cplts vanlige
project directory og kan endres når agentens permissions og brukerens
godkjenning tillater det.

Den managerstyrte flyten setter `OPENCODE_DISABLE_PROJECT_CONFIG=true`, men
OpenCode 1.18.20s core V2-loader ignorerer flagget. Manageren avviser derfor
alle andre prosjektlokale OpenCode-felt og `.opencode`-komponenter enn
restriction-only `opencode.json[c]`. Consumerens `AGENTS.md`/`CONTEXT.md`-kjede
blir fingerprintede project-instructions, mens bare auditerte permissionregler
med `ask`/`deny` fra de statisk validerte prosjektfilene komponeres monotont inn:
`ask` kan bare stramme inn eksisterende `allow`, og `deny` kan aldri svekkes.
Manageren validerer
deretter den faktisk resolverte configen, agentene, commands, skills og
instruksjonslisten i et disposable preflight-project før launch. Dette beviser
den stabile inputflaten, ikke fravær av en samtidig same-UID-mutasjon etter
siste sjekk.

Den minimale unmanaged cplt-flyten over setter ikke denne managergrensen.
Der følger `OPENCODE_CONFIG_DIR` OpenCodes normale globale og prosjektlokale
merge- og precedence-regler; se OpenCodes
[custom directory og precedence](https://opencode.ai/docs/config#custom-directory).
Et likt agent-, command- eller skill-ID kan da skygge en annen definisjon.
Behandle kollisjonen som konfigurasjon som må undersøkes, ikke som en skjult
patchmekanisme.

Den importerte arkitekturlinjens proveniens er låst til `navikt/copilot`
`2d0911b353a91ec9091d252b481acb5777de7059` i
[`policy/content-lock.json`](../policy/content-lock.json). Det er ikke en
påstand om klientkompatibilitet med akkurat den revisjonen. Uavhengig av denne
linjeproveniensen ble samspillet beskrevet her kontrollert mot den nyere
kompatibilitetsrevisjonen
[`0c96b8f`](https://github.com/navikt/copilot/blob/0c96b8fe7c8167a4dd9fc99e50ea18de08e6bb02/cli/nav-pilot/internal/artifacts/opencode_sync.go).
Der kan `EnsureOpenCodeNavContext` materialisere `AGENTS.md`, skills, commands og
agents under `~/.config/opencode`; den tilhørende
[launchkoden](https://github.com/navikt/copilot/blob/0c96b8fe7c8167a4dd9fc99e50ea18de08e6bb02/cli/nav-pilot/internal/provider/opencode_launch.go)
starter OpenCode gjennom cplt. I native/unmanaged cplt
kan OpenCode merge dette med Grillmesters `OPENCODE_CONFIG_DIR`; prefiksede
skill- og command-ID-er reduserer kollisjoner, mens de bevarte agent-ID-ene
fortsatt må doctor-sjekkes. Managed high-assurance isolerer derimot XDG og
avviser ambient skills, agents og plugins. Den modusen er bevisst eksklusiv og
bruker ikke nav-pilot-eksporten.

## Direkte OpenCode

For en avgrenset klientdiagnose kan brukeren eksplisitt velge å starte samme
manifestverifiserte config-stage uten cplt:

```bash
python3 -I -S /path/to/grillmester-opencode-v1/scripts/manage_opencode.py launch \
  --profile local \
  --local-port 1234 \
  --direct
```

Dette bevarer bundle-integritet, read-only config-stage og de faste
miljøgrensene, men starter den opprinnelige, caller-resolverte OpenCode-binæren.
`--direct` omgår dermed managerens offisielle OpenCode-checksum, private
`trusted-bin`, cplt-sandbox og egresspolicy; eksakt `--version`-output er ikke en
byteautentisering. Direkte mode er et eksplisitt trusted-code-opt-out, ikke
anbefalt normalflyt, og kan ikke brukes med `local-only`.

## Agenter, commands og forwarding

Launch uten ekstra argumenter starter TUI med `grillmester`. Velg en annen
offentlig rolle med `--runtime-agent barista`, `designer` eller `doctor-who`.
Kokk, Grill-inspektør og Researcher er skjulte subagenter for native `task`-
delegering.

OpenCode-argumenter etter `--` videresendes. For eksempel:

```bash
python3 -I -S /path/to/grillmester-opencode-v1/scripts/manage_opencode.py launch \
  --profile local \
  --local-port 1234 \
  --runtime-agent barista \
  -- run "Les AGENTS.md og oppsummer build- og testkommandoene. Ikke skriv."

python3 -I -S /path/to/grillmester-opencode-v1/scripts/manage_opencode.py launch \
  --profile local \
  --local-port 1234 \
  -- agent list
```

Manageren plasserer `--agent` på den posisjonen OpenCode dokumenterer for TUI
og `opencode run`; managementkommandoer som `agent list` videresendes uten et
irrelevant agentvalg.

Skills lastes progressivt med OpenCodes native `skill`-tool. De 42 command-
wrapperne gir eksplisitt slash-bruk, for eksempel:

```text
/grillmester-security-review Review auth-endringen i denne diffen
```

Targetet konfigurerer ikke MCP. Figma, GitHub Projects og andre eksterne
capabilities finnes bare når bruker/organisasjon har konfigurert en reviewet
server, autorisasjon, cplt-domener og riktige permissions. Manglende capability
skal gi et reviewbart utkast eller `NEEDS_CONTEXT`, ikke shell-/API-fallback.

## Verifiser discovery før en ekte oppgave

Kjør først i et tomt eller disponibelt testrepo. Bekreft at rosteret har 7
Grillmester-agenter, at de fire primary-agentene kan velges, og at slash-listen
har `grillmester-`-commands. Test deretter i en disponibel fixture:

1. en read-only oppgave uten nettverk
2. én ufarlig write som krever forventet godkjenning
3. én avvist write uten sideeffekt
4. Grillmester-delegering til Kokk og uavhengig Grill-inspektør
5. en representativ skill med relative references eller scripts

Ikke bruk `--auto` før permissiontesten er bestått. OpenCode dokumenterer at
auto-mode godkjenner det som ellers ville vært `ask`; eksplisitte `deny`-regler
gjelder fortsatt. Agentprompten er ikke en sikkerhetsgrense. Se
[OpenCode permissions](https://opencode.ai/docs/permissions).

## Oppdatering og rollback

Oppdatering er en ny, verifisert installasjon fra den nye release-asseten:

```bash
cd /path/to/new/extracted/grillmester-opencode-v1
python3 -I -S scripts/manage_opencode.py install
```

Verifiser alltid den nye assetens detached checksum før kommandoen. En
source-checkout eller GitHubs automatisk genererte source-arkiv er ikke en
oppdateringskanal for en installert OpenCode-bundle.

Aktiv release byttes atomisk først etter full verifikasjon. Avslutt en pågående
session før du vurderer ny payload; den kan allerede ha lastet gamle prompts og
skills.

Rollback krever ikke Git eller consumerendringer:

```bash
python3 -I -S /path/to/grillmester-opencode-v1/scripts/manage_opencode.py rollback
```

Kommandoen verifiserer både aktiv og forrige release før `active`/`previous`
byttes atomisk. Installerte releases slettes ikke automatisk.

## Grensen mot OpenCode 2

OpenCode oppgir at V2-betaen leser støttede V1-agentfiler, commands og skills,
men V2 har andre native permissionnavn og nye plugin-/server-API-er. V1-plugins
fungerer ikke i V2. Grillmester-targetet bruker ingen OpenCode-plugin, men
forventet filkompatibilitet er ikke det samme som verifisert runtimeparitet.

Kjør derfor V2 kun som en eksplisitt beta-smoke. Ikke gjenbruk V1-managerens
versjons-, cplt- eller local-only-garanti for `opencode2`. Se den offisielle
[V1-til-V2-guiden](https://opencode.ai/v2/docs/migrate-v1).

Arkitekturbegrunnelsen ligger i
[ADR 0001](decisions/0001-native-opencode-v1-target.md) for targetformatet og
[ADR 0002](decisions/0002-install-and-launch-opencode-bundles.md) for
installasjon, staging, cplt og profiler.
