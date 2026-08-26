# Lokale modeller med Grillmester

En lokal modell kan brukes i både OpenCode og Copilot CLI uten et eget
sikkerhetsharness. `grillmester local` binder inferensen til én eksplisitt
loopbackprovider og lar cplt eie sandbox, nettverk, GitHub- og Git-grenser.
Web, dokumentasjon og GitHub kan være tilgjengelig når cplt-policyen tillater
det; kommandoen er ikke en offlineprofil.

Local-flyten bruker brukerinstallerte systemklienter med samme
kompatibilitetsgrense som standardlauncheren: OpenCode `>=1.18.20,<2`, Copilot
CLI `>=1.0.79,<2` og cplt fra testbaselinen eller en nyere, gyldig datostemplet
release. De eksakte versjonene i CI er release-testinput, ikke pinner som gjør
hver klientoppgradering til en Grillmester-release. Grillmester tilbyr ingen
egen offlineprofil; strengere egress må konfigureres og eies i cplt eller
organisasjonens runtimepolicy.

| Behov | Anbefalt inngang |
| --- | --- |
| Behold Copilot-pluginen og kjent CLI-flyt | Copilot CLI med BYOK mot LM Studio eller `llama-server` |
| Behold Copilot-appens UI | Copilot app BYOK i public preview; verifiser Grillmester-agent og modellvalg eksplisitt |
| Kjør Grillmester i et uavhengig, modellnøytralt harness | Det native OpenCode 1-targetet |
| Bruk lokal modell med web og GitHub | `grillmester local` med OpenCode eller Copilot CLI på macOS |
| Eksperimenter med provider/modell per session | OpenCode; targetet arver valgt sessionmodell |
| Behold primary-agenten i skyen, men kjør Kokk lokalt | OpenCode med bruker-eid `agent.kokk.model`-override |

Modellvalg endrer ikke data-, tool- eller godkjenningspolicy. Kontroller fortsatt
Navs gjeldende regler for modellartefakt, lisens, data, logging, oppdatering,
MCP-er og egress. En modell som kjører på maskinen gjør ikke webtools, MCP-er,
telemetri eller update-sjekker lokale av seg selv.

Native OpenCode-discovery og deterministisk runtime-smoke validerer plumbing og
permissions, ikke modellkvalitet. Ingen lokal eller open-weight cloudmodell kan
omtales som «like god som Copilot» uten en separat, representativ kvalitetsgate.

## Anbefalt flyt: ett lokalt oppsett, begge terminalklienter

Start en OpenAI-kompatibel modellserver på loopback først. Grillmester eier
ikke serveren, modellfilen eller klientbinærene. Kjør deretter:

```bash
cd /path/to/consumer-repo
grillmester local setup
grillmester local
```

Før Homebrew-formelen er publisert, kjører du de samme stegene fra en checkout:

```bash
cd /path/to/consumer-repo
python3 /absolute/path/to/grillmester/scripts/grillmester.py local setup
python3 /absolute/path/to/grillmester/scripts/grillmester.py local doctor
python3 /absolute/path/to/grillmester/scripts/grillmester.py local launch
```

Uten opt-in sender launcheren ingen støttet GitHub-tokenvariabel til child.
OpenCode starter uten ambient GitHub-konto; Copilot kan likevel mediere en
native credential via macOS Keychain som beskrevet nedenfor. Gjør et eksplisitt
token tilgjengelig når sesjonen trenger autentiserte GitHub-operasjoner:

```bash
cd /path/to/consumer-repo
GH_TOKEN="$(gh auth token)" \
  python3 /absolute/path/to/grillmester/scripts/grillmester.py \
  local launch --client opencode --github-access
```

Her kjører du selv `gh auth token` i skallet før launcheren starter. Grillmester
verifiserer at `gh` finnes på `PATH`, men starter det ikke. Installer GitHub CLI
ved behov med `brew install gh`. Samme `--github-access`-form brukes med
`--client copilot`. For begge klienter skjermer launcheren ambient tokenvariabler,
rå `gh`-config og caller-kontrollerte PATH-verktøy. Copilots cplt-profil tillater
likevel macOS Keychain; velg OpenCode dersom hard isolasjon fra en ambient
GitHub-konto er et krav.

Private npm-pakker er en separat opt-in. Local-flyten videresender aldri et
ambient package-token og bruker ikke hostens npm user- eller globalconfig. Når
consumer-repoets egen `.npmrc` peker på en privat registry, gi child-klienten
ett caller-eid token med `--npm-access`:

```bash
NPM_AUTH_TOKEN="$NAV_PACKAGE_READ_TOKEN" \
  grillmester local run --npm-access \
  "Fiks oppgaven og kjør repoets deklarerte verifikasjon"
```

Bruk et dedikert token med bare nødvendige package-read-rettigheter. Launcheren
leser kun `_authToken=${NAME}`-direktiver i en avgrenset, vanlig prosjektfil.
`NPM_AUTH_TOKEN`, `NODE_AUTH_TOKEN` og `NPM_TOKEN` gjenkjennes automatisk når
nøyaktig ett navn er deklarert. Et custom navn må velges eksplisitt med
`--npm-token-env NAME` og må stå i samme `.npmrc`. Navnet må beskrive en
package-credential og ende på `_TOKEN`:

```bash
NAV_PACKAGE_READ_TOKEN="$TOKEN" \
  grillmester local run --npm-token-env NAV_PACKAGE_READ_TOKEN \
  "Fiks oppgaven og kjør repoets deklarerte verifikasjon"
```

Kontrollvariabler som `HOME`, `NPM_CONFIG_*`, `OPENCODE_*` og `COPILOT_*` kan
ikke velges som package-token. Launcheren validerer tokenformatet, redigerer
verdien fra egne previews og skriver den ikke til config eller sessionstate.
Tomme, session-eide npm user- og globalconfigfiler hindrer package manageren i
å bruke hostconfig; prosjektets `.npmrc` bestemmer hvilken registry tokenet kan
sendes til. Modellen og godkjente subprocesser kan lese tokenet, og cplts
effektive nettverkspolicy er fortsatt autoritativ. Valget gjelder bare den ene
sesjonen og lagres aldri som default. Runtimekontrakten forteller modellen om
package-tilgangen: med `--npm-access` kan repoets deklarerte package manager
installere det som trengs for verifikasjonen brukeren ba om; uten flagget skal
modellen bruke det som allerede er installert og rapportere manglende
dependencies.

`setup` finner OpenCode og Copilot CLI på `PATH` uten å starte dem. Finnes én
klient, velges den automatisk; finnes begge, spør launcheren. OpenCode-sessions
bruker ripgrep fra `PATH`; installer det med `brew install ripgrep` dersom
`grillmester local doctor` varsler. Standardendepunktet er
`http://127.0.0.1:8080/v1`. Launcheren leser `/v1/models`, velger automatisk
når serveren annonserer én modell og lagrer tilkoblingsbeskrivelsen og
modellens kontekstkontrakt i `~/.config/grillmester/local.json`. Defaulten er
57 344 tokens trygt klientbudsjett og 8 192 tokens maksimal output, beregnet
for en modellserver med 65 536 tokens context. Den ekstra servermarginen på
8 192 tokens tar høyde for protokoll-, tool- og harness-overhead som ikke
nødvendigvis vises likt i klientens budsjett. Defaultene kan angis eksplisitt
når oppsettet skal være selvforklarende:

```bash
grillmester local setup \
  --context-window 57344 \
  --max-output-tokens 8192
```

OpenCode får grensene i providerkonfigurasjonen og kan dermed komprimere
automatisk før modellen overskrider vinduet. Copilot CLI får det samme samlede
budsjettet. Grillmester injiserer ikke egne context-hints og har ingen separat
komprimeringsmekanisme. Sett et lavere klientbudsjett hvis serveren har mindre
context eller maskinen får memory pressure. Kjør `setup` på nytt hvis serverens
aktive kontekstvindu endres.

En API-nøkkel lagres aldri; bruk eventuelt
`--api-key-env NAVN` eller `--api-key-file /absolutt/privat/fil` med Copilot
CLI. Miljøvariabelen må være dedikert og kan ikke være en bevart terminal-
variabel som `LANG` eller `TERM`. Nøkkelfilen må være bruker-eid, 0600, uten
hardlinks og utenfor prosjektet;
originalpathen deny-es også eksplisitt i cplt. OpenCode 1.18.20 lar tool-
subprosesser arve provider-miljøet og godtar derfor bare en nøkkelfri loopback-
server i local-flyten. Dette feiler lukket i `setup`; bruk Copilot CLI når
lokalserveren krever autentisering.

Hver launch bruker focused Barista med sju utviklingsskills. Bytt klient eller
be om full 7-agent/43-skill-kontekst for én sesjon uten å endre defaulten:

```bash
grillmester local --client copilot
grillmester local --client opencode
grillmester local --full --agent grillmester
```

`grillmester local status` viser valget og tokenbudsjettet. `grillmester local
doctor` verifiserer og viser cplt-/klientpath og versjon, prosjekt, agent,
kontekst, kontekstvindu, maksimal output, endpoint, modell og payload.
`grillmester local --help` og
`grillmester local launch --help` viser hele brukerflaten, og
`grillmester local --print-command` viser en redigert kommando uten å lese
nøkkelen, skrive sessionstate eller kjøre klientprober. Previewen er bevisst
ikke en copy/paste-kommando fordi kortlivede policyfiler og secret-miljø ikke
materialiseres. Kjør `setup` på nytt for å endre lagret default.

Vanlig `grillmester local` er en direkte, interaktiv klientreise: du snakker
med den valgte agenten i OpenCode- eller Copilot-TUI-en, og modellen svarer
normalt etter eget skjønn. Launcheren krever eller tolker ingen strukturert
sluttstatus.

### Avgrenset kjøring

`run` kjører én prompt non-interaktivt med lagret klient og modell, focused
Barista som default og automatiske tool-godkjenninger:

```bash
cd /path/to/clean-dedicated-worktree
grillmester local run "Fiks den avgrensede oppgaven og kjør testene"
```

Kommandoen kjører i foreground; la den stå i en egen terminal mens du gjør noe
annet. Bruk alltid et rent, dedikert worktree, ingen samtidige menneske- eller
agentendringer og én `run` per worktree.
OpenCode bruker `run --auto`, mens Copilot CLI bruker sin non-interaktive
promptmodus. Begge auto-godkjenner prosjektwrites, shellkommandoer og URL-er
innenfor den effektive klient- og cplt-policyen. cplt beskytter ikke
prosjektfilene mot overskriving, sletting eller destruktive Git-operasjoner som
modellen selv starter.

Launcheren legger en kort runtimekontrakt foran oppgaveteksten i `run`. Den
forklarer modellen at `EPERM`, `Operation not permitted` og eksplisitte
blokkeringer kan være tilsiktet cplt-policy, at en policyblokk ikke skal
feilsøkes eller omgås, og at uavhengig implementasjon skal fortsette selv om én
verifikasjon er blokkert. Et Git-avvik som modellen ikke kan lese, skal ikke
tilskrives kjøringen eller røres; det rapporteres separat som uavklart. Vanlige
oppgavespesifikke Git- og GitHub-operasjoner som cplt tillater, forblir tillatt.
Den opprinnelige oppgaven står uendret etter kontrakten. Dette gjelder bare
non-interaktiv `local run`; den kanoniske agentpakken og vanlig
Copilot-/OpenCode-bruk får ingen ekstra promptstøy.

`run` er derfor for små til middels store oppgaver med tydelig mål, scope og
verifikasjon. En exitkode `0` betyr at klientprosessen fullførte, ikke at
oppgaven er semantisk løst. Modellen kan fortsatt avslutte med
`Status: NEEDS_INPUT` eller `Status: NEEDS_FULL_CONTEXT`. Les sluttsvaret og
kontroller minst `git status`, hele diffen og avtalte tester før du bruker
resultatet. Statusene er menneskelesbare agent-signaler, ikke en protokoll som
launcheren parser eller bruker til å stoppe prosessen; en vanlig oppgave trenger
ikke en egen `Status: DONE`-kontrakt. `--agent` og `--full` er
engangsoverstyringer; lagret default endres ikke. `--print-command` viser den
redigerte kommandoformen uten å probe modellen eller klientversjonen.

Autentisert GitHub-tilgang er av som default for begge klientene. Copilot legger
i tillegg inn en `shell(gh:*)`-deny som defense-in-depth, ikke som en hard
sikkerhetsgrense. Når en oppgave faktisk trenger GitHub, sett caller-eid
`GH_TOKEN` og bruk `--github-access`:

```bash
GH_TOKEN="$GRILLMESTER_RUN_GITHUB_TOKEN" \
  grillmester local run --github-access \
  "Opprett den ferdig spesifiserte issuen i dette repoet og verifiser resultatet"
```

Denne opt-in-flyten krever GitHub CLI på `PATH`; installer den med
`brew install gh` dersom den mangler.

Dette autoriserer en non-interaktiv child: GitHub-skrivinger som er eksplisitt
autorisert i prompten kan skje uten en ny tool-dialog. Bruk et dedikert,
fine-grained token begrenset til nødvendig repository og minste nødvendige
permissions, ikke et bredt personlig standardtoken. Tokenet er en myk grense:
child-klienten kan lese det, og direkte API-kall kan omgå cplts best-effort
`gh`-guard. Ikke behandle flagget som hard repository-scoping. Hvis eksakt
issueinnhold eller annen bruker-eid beslutning ikke allerede er autorisert, skal
Barista returnere et utkast med `Status: NEEDS_INPUT` i stedet for å skrive.

Oppgaver som må installere eller verifisere private npm-pakker bruker
`--npm-access` i tillegg. `--github-access` og `--npm-access` er separate fordi
GitHub API-/CLI-tilgang og package registry-tilgang kan ha ulike tokens og
rettigheter. Hvis repoets deklarerte verifikasjon stopper på manglende
credentials, dependencies eller eksakt verktøy, skal Barista rapportere den
blokkerte kommandoen. Den skal ikke hente en navnelik erstatningspakke med
`npx` eller på annen måte svekke verifikasjonen.

Local-flyten har ingen cloudmodell-fallback, men den kan være tilkoblet.
Launcheren åpner den valgte localhost-porten og krever cplts forced proxy,
`gh`-guard og Git-guard. Brukerens og organisasjonens cplt-config forblir
autoritativ; Grillmester åpner ikke alle domener eller legger en annen sandbox
oppå. Webverktøy og dokumentasjonskilder virker når den effektive policyen og
klientens godkjenninger tillater det. Dette er ikke en egen Grillmester-
egressattest.

For begge klienter får cplt-parenten en tom, session-eid `GH_CONFIG_DIR`, child
får session-eid XDG-config, eksisterende host-config deny-es, og en privat
trusted-bin skjermer parenten fra caller-kontrollerte `gh`, `git`, `which` og
`sandbox-exec`. Copilots innebygde GitHub MCP er av. OpenCode får dermed hard
isolasjon fra den ambient GitHub-kontoen. Copilots cplt-profil tillater fortsatt
macOS Keychain og kan derfor mediere en native credential; local-flyten lover
ikke hard ambient-kontoisolasjon for Copilot. Uten `--github-access` sendes ingen
støttet tokenvariabel. Copilot markerer kjente GitHub-tokenvariabler som secrets
og deny-er dessuten det direkte `shell(gh:*)`-toolet som defense-in-depth. Den
tool-denyen kan omgås av en annen shellform og er ikke sikkerhetsgrensen.

Når brukeren eksplisitt setter `GH_TOKEN` i caller-miljøet og velger
`--github-access`, validerer launcheren tokenet og at `gh` finnes uten å starte
det, og sender tokenet til valgt child-klient. Dette velger en eksplisitt
tool-credential, men trekker ikke tilbake Copilot-profilens Keychain-tilgang.
Launcheren skriver ikke tokenet
til config, sessionstate eller preview, men klienten og godkjente
tool-subprosesser kan lese og eventuelt persistere det i sin skrivbare
sessionstate. En lokal modell kan også skrive tokenet til terminaloutput eller
klientlogger; cplt kan ikke redigere modellens output i etterkant. Bruk riktig
konto og minst mulig scope. Interaktiv launch spør før sideeffekter;
`local run` utfører den eksakt autoriserte prompten uten en ny tool-dialog.

Høy-nivåkommandoer som `gh issue create` går fortsatt gjennom cplts `gh`-guard,
og Git push går gjennom Git-guard. `gh`-guarden er en myk, best-effort
kommandogrense; et eksplisitt token kan også brukes i direkte API-kall.

Som default blokkerer Git-guard all push. For en dedikert agent-worktree kan
brukeren velge cplts smalere leveringspolicy globalt. Innstillingen
`git_guard.protect_default_branch_only=true` settes slik:

```bash
cplt config set git_guard.protect_default_branch_only true --force
```

Da kan cplt-wrappede agentkommandoer normalt pushe vanlige feature branches og
kjøre `gh pr create --draft` for det aktuelle repoet. cplt-policyen er ment å
fortsette å blokkere push til `main`/`master`, force-push og PR-merge, men er en
best-effort-kommandogrense — ikke hard branch-autorisasjon. Repository rules og
branch protection er den autoritative default-branch-grensen. Dette er
cplt-config, ikke et Grillmester-flagg, og påvirker alle cplt-sesjoner for
brukeren. Kontroller effektiv verdi med
`cplt config get git_guard.protect_default_branch_only`. Grillmester sender
fortsatt alltid `--git-guard` og tilbyr ingen `--no-git-guard`-omvei.

OpenCodes websearch er aktiv,
og Grillmester velger Exa som provider. Når websearch brukes, sendes
søketeksten til Exa: interaktiv launch krever klientgodkjenning, mens `local
run` auto-godkjenner tool-et. Trafikken går gjennom den effektive cplt-
nettverkspolicyen; lokal inference betyr derfor ikke at søketeksten forblir på
maskinen.

Hver launch lar cplt-parenten beholde hostens `HOME`, men gir child-klienten
isolert XDG-, provider- og klientstate og den
distribuerte payloaden. OpenCode får en byteidentisk, sessioneid kopi etter at
manifest og digester er verifisert, slik at klientens runtime-packagefiler ikke
kan forsøple release-targetet. Copilot leser pluginpayloaden direkte.
Ambient OpenCode- og Copilot-komponenter som kan skygge agentteamet avvises;
repoets vanlige `AGENTS.md` kan fortsatt gi stående prosjektkontekst. Dette er
payloadisolasjon, ikke en egen runtime-sandbox. Bare de to nyeste avsluttede
sessionmappene beholdes ved sekvensiell bruk; `doctor` og preview oppretter ingen
sessionmappe.

For OpenCode kan prosjektets `.opencode/` fortsatt inneholde vanlig, inert
metadata som `.gitignore`, packagefiler og `node_modules`, samt andre filer som
ikke er en lastbar klientkomponent. Prosjektets `opencode.json` og lastbare
agent-, command-, mode-, plugin-, skill-, theme- og toolrøtter avvises fortsatt.
Legg stående prosjektinstrukser i `AGENTS.md` i repo-roten; en
`.opencode/AGENTS.md` kan eksistere, men er ikke OpenCodes dokumenterte
prosjektregelsti og bindes ikke av Grillmester.

Copilot-local feiler konservativt på enhver ikke-tom repo-lokal agent- eller
skillrot fordi klienten ikke tilbyr full discovery-disable. Det omfatter også
ikke-kolliderende innhold synket av nav-pilot. Standard/pluginflyten kan fortsatt
sameksistere med slikt innhold; for local bruker du OpenCode eller en eksplisitt
pilotbranch/fixture uten røttene.

En reell Qwen3.8-27B Q6-pilot med samme korte oppgave målte 8 024 mot 13 667
inputtokens i OpenCode focused/full og 15 841 mot 20 117 i Copilot CLI. Det er
henholdsvis 41,3 og 21,3 prosent mindre inputkontekst. Piloten brukte den
opprinnelige focused-rosteren med seks skills, før issue management ble lagt
til. Alle fire kjedene gikk gjennom cplt til loopback, og Copilot rapporterte
null premium requests. Tallene er historisk runtime-evidens, ikke en måling av
dagens sju-skill-roster eller generell kvalitetsparitet.

Vanlig `grillmester` beholder hele agentteamet og klientens normale
modellregler. Den eksplisitte local-flyten binder i stedet valgt
loopbackmodell og setter kvalifisert `inherit` for normal
subagentdelegering. Provideren bør avvise ukjente modell-ID-er eller ha en
bevisst aliaspolicy; se [trustgrensen](trust-and-client-support.md).

## Qwen3.8-27B på M4 Pro: forstå innstillingene

Qwens offisielle
[Qwen3.8-27B-modellkort](https://huggingface.co/Qwen/Qwen3.8-27B/blob/main/README.md)
beskriver en tett 27B-modell med tool-/agentfokus og 262k native context. Den
oppgitte modellgrensen er ikke et minnebudsjett for en laptop.

«6bit XL og 8b KV» betyr normalt to forskjellige kvantiseringer:

- `UD-Q6_K_XL` er en tredjeparts GGUF-kvantisering av **modellvektene**.
  Unsloths nåværende artifact er omtrent 25,3 GB. `UD`/`XL` er
  artifact-utgiverens variantnavn, ikke en Qwen-modellstørrelse.
- `q8_0` KV er 8-bit lagring av attentionens key/value-cache under kjøring.
  Det er ikke en 8B-modell og endrer ikke 27B-parameterantallet.

Se den konkrete
[GGUF-artifactlisten](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF) og pin
både revision og checksum dersom artifactet skal brukes i arbeidssammenheng.
Det er et separat tillitsvalg fra den Apache-2.0-lisensierte upstreammodellen.

Som en grov båndbredde-inferens oppgir Apple 273 GB/s for
[M4 Pro](https://www.apple.com/newsroom/2024/10/apple-introduces-m4-pro-and-m4-max/).
`273 / 25,3 ≈ 10,8` fulle vektskanninger per sekund før compute-, cache- og
runtimekostnader. Teamets observerte 9–10 tokens/s er derfor plausibelt for
decode, men dette er et tak-estimat — ikke en benchmark av akkurat deres
maskin, build eller prompt.

Fra modellarkitekturen gir `q8_0` K/V grovt omtrent 1,1 / 2,1 / 4,3 GiB ved
32k / 64k / 128k context; `f16` er omtrent dobbelt. Estimatet utelater blant
annet DeltaNet-state, allocator, batching, vision og midlertidige buffere, så
mål faktisk memory pressure i stedet for å fylle hele den native contextgrensen.

Teamets foreløpige M4 Pro-utgangspunkt er:

- Q6 XL bare når unified memory har god margin over vektfilen; 24 GB er for
  lite, og også større maskiner trenger plass til KV-cache, runtime, OS, IDE og
  repoarbeid
- 65 536 server-context, mens Grillmester annonserer et konservativt
  klientbudsjett på 57 344 med 8 192 maksimal output
- `f16` for både K og V som correctness-baseline når memory pressure er grønt;
  fall tilbake til `q8_0` hvis maskinen begynner å swappe eller trenger mer
  margin til IDE og repoarbeid
- én server-slot og én tung lokal agentoppgave om gangen
- preserved reasoning og `medium` reasoning effort
- ingen MTP-/draftmodell i første correctness-baseline; støtten er lovende,
  men eksperimentell og må A/B-måles mot samme oppgave og runtimeversjon
- en separat Git-worktree per avgrenset kjøring som kan skrive

På en minnebåndbreddebegrenset maskin gjør flere samtidige requests vanligvis
ikke at totalarbeidet blir tilsvarende raskere. De deler samme båndbredde og
øker samtidig KV-/contexttrykket. Ved omtrent 9–10 genererte tokens/s bør
avgrensede kjøringer derfor være små, godt briefet og uavhengig verifiserbare.
Parallelliser gjerne menneskelig arbeid, repo-research eller oppgaver på en
annen provider; kø tunge lokale Kokk-oppdrag sekvensielt.

## Start modellserver: LM Studio

LM Studio er den enkleste piloten på Apple Silicon fordi modellvalg, estimering
og load-parametere er synlige før serveren startes. LM Studio dokumenterer både
[lokal modellasting](https://lmstudio.ai/docs/app/basics),
[`lms load` med context og GPU-offload](https://lmstudio.ai/docs/cli/local-models/load)
og et
[OpenAI-kompatibelt API](https://lmstudio.ai/docs/developer/openai-compat) på
`http://localhost:1234/v1`.

1. Last ned eller importer en reviewet Qwen3.8-27B GGUF og verifiser artifact-
   revision/checksum.
2. Bruk memory-estimatet før lasting. På den testede M4 Pro-profilen starter du
   med 65 536 context, maksimal trygg GPU-offload og én parallell request.
   Reduser først context dersom memory pressure eller swapping tilsier det.
3. Start den lokale serveren i Developer-fanen eller med `lms server start`.
4. Hent det eksakte model-ID-et fra `GET /v1/models`; ikke gjett filnavnet:

```bash
curl http://127.0.0.1:1234/v1/models

python3 /absolute/path/to/grillmester/scripts/probe_local_model.py \
  --model REPLACE_WITH_LM_STUDIO_MODEL_ID
```

`probe_local_model.py` krever loopback som standard og sjekker at model-ID-et
finnes, at Chat Completions streamer med SSE og at server/modell returnerer én
tvunget, strukturert tool call. Mot `llama-server` bruker du også
`--base-url http://127.0.0.1:8080/v1`. Proben utfører ikke tool call-en og
skriver ikke i repoet. Den er en capability-smoke, ikke en kvalitetsbenchmark,
en context-/minnetest eller bevis på at resten av prosessen har null egress.

LM Studio eksponerer ikke nødvendigvis samme detaljerte KV-cachevalg i alle
engine-/appversjoner. Når eksakt `f16` eller `q8_0` for K og V er en del av
forsøket, bruk den reproduserbare `llama.cpp`-flyten under og registrer
binærversjonen.

## Reproduserbar baseline med llama.cpp

Installer en reviewet
[`llama.cpp`-release](https://github.com/ggml-org/llama.cpp/releases), og bruk
en allerede nedlastet, checksummet GGUF. Denne teksten er en startkonfigurasjon,
ikke et løfte om optimal ytelse på alle M4 Pro-varianter:

```bash
llama-server \
  --model /absolute/path/to/Qwen3.8-27B-UD-Q6_K_XL.gguf \
  --alias qwen3.8-27b-local \
  --host 127.0.0.1 \
  --port 8080 \
  --ctx-size 65536 \
  --parallel 1 \
  --n-gpu-layers all \
  --flash-attn on \
  --cache-type-k f16 \
  --cache-type-v f16 \
  --no-mmproj \
  --jinja \
  --reasoning on \
  --reasoning-effort medium \
  --reasoning-preserve \
  --chat-template-kwargs '{"preserve_thinking":true}' \
  --temp 1.0 \
  --top-p 0.95 \
  --top-k 20 \
  --min-p 0 \
  --presence-penalty 0 \
  --repeat-penalty 1
```

`--no-mmproj` holder tekst-/kodepiloten mindre; fjern flagget og last den
reviewede vision-projectoren bare når oppgaven faktisk trenger bilder.
`llama-server` dokumenterer cachetype for K og V, contextstørrelse,
parallelle slots, Metal/GPU-offload og localhost-binding i sin
[serverreferanse](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).
Samplingverdiene følger Qwens anbefalte thinking-profil i modellkortet.
`medium` er Grillmesters anbefalte correctness-baseline for utviklingsoppgaver;
`--reasoning-preserve` og template-flagget bevarer reasoning mellom turer. Det
settes ikke et separat hardt reasoning-budgett. MTP kan prøves separat med
llama.cpps draft-MTP-støtte, men er fortsatt eksperimentelt og er derfor ikke
med i baselinekommandoen. Registrer innstillingene, tidsbruk, komprimering og
resultatkvalitet som del av forsøket i stedet for å la en appversjon endre dem
stille.

Hvis modellen ikke lastes uten memory pressure eller swapping, reduser context
først. Deretter vurder Q5 XL eller Q4 XL som et eksplisitt kvalitets-/minnevalg;
ikke la runtime bytte artifact stille. Registrer minst:

- modellrepo, revision, filnavn og SHA-256
- LM Studio-/llama.cpp-versjon og faktisk API model-ID
- context, K/V-cachetype, parallel slots og thinking/reasoning-innstilling
- prompt- og decodehastighet, maksimal resident memory og eventuell swapping
- resultatet av capability-smoken under

## Avansert: manuell OpenCode-binding

Bruk normalt `grillmester local setup`; den bygger en isolert providerconfig
uten å endre brukerens OpenCode-oppsett. For debugging eller en bevisst
model-neutral session kan du i stedet merge en lokal provider i
din bruker-eide `~/.config/opencode/opencode.json`. For LM Studio erstatter du
model-ID-et med den eksakte verdien fra `/v1/models`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "lmstudio": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "LM Studio (local)",
      "options": {
        "baseURL": "http://127.0.0.1:1234/v1"
      },
      "models": {
        "replace-with-id-from-v1-models": {
          "name": "Qwen3.8-27B local",
          "tool_call": true,
          "modalities": {
            "input": ["text"],
            "output": ["text"]
          },
          "limit": {
            "context": 57344,
            "output": 8192
          }
        }
      }
    }
  }
}
```

For `llama-server` bruker du samme form med provider-ID `llamacpp`, base URL
`http://127.0.0.1:8080/v1` og model-ID `qwen3.8-27b-local`. Dette følger
OpenCodes offisielle provideroppsett for
[LM Studio](https://opencode.ai/docs/providers#lm-studio) og
[llama.cpp](https://opencode.ai/docs/providers#llama-cpp).

`tool_call: true` gjør den forventede capabilityen synlig for OpenCode;
`modalities` er med vilje tekst-only så lenge llama-baselinen bruker
`--no-mmproj`. Feltene er deklarasjoner, ikke evidens. Kjør proben mot samme
base URL og model-ID før bruk:

```bash
python3 /absolute/path/to/grillmester/scripts/probe_local_model.py \
  --base-url http://127.0.0.1:8080/v1 \
  --model qwen3.8-27b-local
```

Start deretter den normale native cplt-veien og velg `lmstudio/<model-id>` eller
`llamacpp/qwen3.8-27b-local` i `/models`:

```bash
cd /path/to/consumer-repo
grillmester --client opencode --agent grillmester \
  --allow-localhost 1234 \
  -- --model lmstudio/replace-with-id-from-v1-models
```

Bruk `--allow-localhost 8080` for `llama-server`. Dette er nok for vanlig
kompatibilitet; ingen annen runtime eller `nav-pilot-agent` er nødvendig.

OpenCode-agentene har ingen modellpin. Når Grillmester delegerer til Kokk,
Grill-inspektør eller Researcher, arver subagenten primary-agentens valgte
lokalmodell.

## Hybrid: cloud-primary og lokal Kokk

Du kan beholde Grillmester eller Barista på sessionens valgte cloudmodell og
bare pinne en intern rolle til den lokale provideren. Legg dette ved siden av
provideroppsettet i den bruker-eide `~/.config/opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "agent": {
    "kokk": {
      "model": "lmstudio/replace-with-id-from-v1-models"
    }
  }
}
```

OpenCode merger configkildene. Den genererte Kokk-filen definerer rolle og
permissions, men utelater `model`, så denne ikke-konfliktende brukeroverriden
bevares. Grillmester bruker fortsatt sessionmodellen; en delegert Kokk-oppgave
bruker den pinnede lokalmodellen. Det er en bruker-/maskinprofil, ikke noe som
skal committes inn i Grillmester-targetet. Se OpenCodes dokumenterte
[config-merge](https://opencode.ai/docs/config#locations) og
[agentmodell-override](https://opencode.ai/docs/agents#model).

Legg eventuelt samme override på `researcher` eller `grill-inspektor` først
etter at hver rolle har bestått capability- og kvalitetssmoken. På én M4 Pro
bør serveren fortsatt ha én slot; parallelle delegeringer må køes for å unngå
at modellene konkurrerer om samme minnebåndbredde og KV-cache.

Når du vil starte en eksplisitt avgrenset kjøring, bruk en offentlig
primary-agent i en egen worktree i stedet for å behandle Kokk som en generell
startagent:

```bash
cd /path/to/dedicated-worktree
grillmester local run --client opencode \
  "Gjør denne tydelig avgrensede oppgaven og kjør de avtalte testene."
```

OpenCode dokumenterer `--agent` og `--model provider/model` for
[`opencode run`](https://opencode.ai/docs/cli#run). Kokk er en skjult subagent
som brukes gjennom Grillmester-delegering. Barista er riktig direkte inngang
for en ferdig spesifisert avgrenset kjøring. Start bare én tung lokal
agentoppgave om gangen med denne laptopbaselinen.

## Avansert: manuell Copilot CLI BYOK

Bruk normalt `grillmester local --client copilot`; launcheren bygger og
saniterer BYOK-miljøet for deg. Den manuelle formen under er kun for debugging
og sammenligning. GitHub dokumenterer lokale OpenAI Chat
Completions-kompatible providers,
blant annet Ollama, vLLM og andre lokale endepunkter. Modellen må støtte både
streaming og tool calling; GitHub anbefaler minst 128k context for best resultat.
Qwen-piloten bruker derfor en bevisst redusert laptopprofil: 65 536 på serveren
og et trygt klientbudsjett på 57 344. Den må testes mot Grillmesters reelle
oppgaver, ikke behandles som en påstått fullgod standard.

Mot LM Studio setter du den eksakte modellen fra `/v1/models`. `local` under er
en ufarlig plassholder når serveren ikke krever autentisering; bruk en egen
lokal servernøkkel når den gjør det:

```bash
export COPILOT_PROVIDER_TYPE=openai
export COPILOT_PROVIDER_BASE_URL=http://127.0.0.1:1234/v1
export COPILOT_PROVIDER_API_KEY=local
export COPILOT_PROVIDER_WIRE_API=completions
export COPILOT_PROVIDER_MODEL_ID=REPLACE_WITH_LM_STUDIO_MODEL_ID
export COPILOT_PROVIDER_WIRE_MODEL=REPLACE_WITH_LM_STUDIO_MODEL_ID
export COPILOT_MODEL=REPLACE_WITH_LM_STUDIO_MODEL_ID
export COPILOT_PROVIDER_MAX_PROMPT_TOKENS=49152
export COPILOT_PROVIDER_MAX_OUTPUT_TOKENS=8192
export COPILOT_AUTO_UPDATE=false
export COPILOT_OTEL_ENABLED=false
export NO_PROXY=127.0.0.1,localhost

grillmester --client copilot --agent barista \
  --allow-localhost 1234 \
  --pass-env COPILOT_PROVIDER_TYPE \
  --pass-env COPILOT_PROVIDER_BASE_URL \
  --pass-env COPILOT_PROVIDER_API_KEY \
  --pass-env COPILOT_PROVIDER_WIRE_API \
  --pass-env COPILOT_PROVIDER_MODEL_ID \
  --pass-env COPILOT_PROVIDER_WIRE_MODEL \
  --pass-env COPILOT_PROVIDER_MAX_PROMPT_TOKENS \
  --pass-env COPILOT_PROVIDER_MAX_OUTPUT_TOKENS \
  --pass-env COPILOT_MODEL \
  --pass-env COPILOT_AUTO_UPDATE \
  --pass-env COPILOT_OTEL_ENABLED \
  --pass-env NO_PROXY \
  -- --model "$COPILOT_MODEL" --effort medium \
  --no-auto-update --no-remote --no-remote-export \
  --disable-builtin-mcps \
  --secret-env-vars=COPILOT_PROVIDER_API_KEY
```

Mot `llama-server` bruker du port `8080` og
modell-ID `qwen3.8-27b-local` i de tre modellvariablene. Tilpass prompt- og
outputgrensene til serverens faktiske contextbudsjett. Kommandoen går gjennom
Grillmester-launcheren og cplt, og launcheren binder den reviewede pluginen;
den starter aldri `copilot` direkte. Se GitHubs
[BYOK-guide](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-byok-models).

Copilot-profilene i Grillmester beholder foreløpig sin reviewede modellpin.
GitHub dokumenterer at en agentpin som ikke kan brukes faller tilbake til
sessionmodellen, men deterministisk lokal kjøring bør ikke være avhengig av
fallback. Merge derfor en eksplisitt, bruker-eid override i
`~/.copilot/settings.json`, eller sett den interaktivt med `/subagents`:

```json
{
  "subagents": {
    "agents": {
      "grillmester:grillmester": { "model": "inherit" },
      "grillmester:barista": { "model": "inherit" },
      "grillmester:designer": { "model": "inherit" },
      "grillmester:doctor-who": { "model": "inherit" },
      "grillmester:kokk": { "model": "inherit" },
      "grillmester:grill-inspektor": { "model": "inherit" },
      "grillmester:researcher": { "model": "inherit" }
    }
  }
}
```

`subagents.agents.grillmester:<id>.model = "inherit"` har høyere prioritet enn
agentens frontmatter og bruker parent/sessionmodellen ved dispatch. Den
plugin-kvalifiserte nøkkelen er påkrevd; en ukvalifisert agent-ID overstyrer
ikke Grillmester-pluginagenten. Se GitHubs
[settingsreferanse](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference#user-settings-copilotsettingsjson)
og
[modelloppløsning for custom agents](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference#custom-agent-frontmatter-fields).

Homebrew-launcheren bruker sin bundle-inkluderte plugin gjennom `--plugin-dir`,
slik kommandoen over viser. Grillmester legger ikke en egen offlinevariant oppå
denne manuelle BYOK-flyten; strengere egress eies av cplt eller organisasjonens
runtimepolicy.

## Copilot app med lokal provider er en egen pilot

GitHub Copilot app kan også kobles til LM Studio, Ollama eller et vilkårlig
OpenAI-kompatibelt HTTP-endepunkt gjennom **Settings → Model providers**. Dette
er foreløpig public preview, og appen krever GitHub-innlogging.

Behandle derfor app + Grillmester-plugin + lokal Qwen som en separat
klientprofil: bekreft plugin-/agentdiscovery, faktisk valgt modell, tool calls,
delegering og nettverkstrafikk før den omtales som lokal. Se
GitHubs [BYOK-guide for Copilot app](https://docs.github.com/en/copilot/how-tos/github-copilot-app/use-byok-models).

## Lokal inference er ikke offline

`grillmester local` binder modellrequests til localhost. Web, dokumentasjon og
GitHub kan virke når klientgodkjenninger og den effektive cplt-policyen tillater
det. Launcheren krever forced proxy, `gh`-guard og Git-guard, men overstyrer ikke
brukerens eller organisasjonens domeneconfig og gir ingen egen Grillmester-
egressattest. Modellserveren kjører utenfor cplt og må vurderes for binær,
vekter, logging og egen nettverkstrafikk.

Grillmester tilbyr ingen egen `local-only`-profil. Dersom arbeidet krever at
hele harnesset er offline eller har en eksplisitt domeneallowlist, må den
kontrakten eies og verifiseres i cplt eller organisasjonens runtimepolicy. Ikke
rapporter en vanlig local-session som offline bare fordi inferensen går til
`127.0.0.1`.

## Capability-smoke før modellen får en avgrenset kjøring

Et godt svar i chat er ikke nok. Test den eksakte modellen, kvantiseringen,
serveren, contextprofilen og harnesset sammen i et disponibelt repo:

1. **Protokoll:** `/v1/models`, streaming og en enkel tool call fullføres uten
   parserfeil.
2. **Read-only:** agenten leser `AGENTS.md`, finner en fil og kjører en ufarlig
   repoinspeksjon uten å skrive.
3. **Permission:** én write godkjennes og én write avvises; avvisningen gir
   ingen fil- eller Git-sideeffekt.
4. **Skill:** én Grillmester-skill lastes progressivt og følger en relativ
   reference eller et bundled script korrekt.
5. **Delegering:** Grillmester gir én avgrenset brief til Kokk og får en
   uavhengig Grill-inspektør-vurdering.
6. **Lang oppgave:** kjør en representativ vertical slice med tester og mål
   tool-call-feil, context/compaction, hastighet og memory pressure.
7. **Kvalitet:** sammenlign diff og reviewfunn mot teamets nåværende referanse-
   modell før modellen får uovervåket arbeid.

Start med Barista på små, tydelige oppgaver. Bruk Grillmester/Kokk først når
delegeringssmoken er stabil. På en enkelt M4 Pro bør Kokk-oppgaver normalt
køes, mens menneskelig arbeid kan fortsette i en annen worktree eller session.
