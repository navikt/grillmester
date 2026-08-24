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

OpenCode får ikke GitHub-credential som default. Gjør tilgangen eksplisitt når
sesjonen trenger autentiserte GitHub-operasjoner:

```bash
cd /path/to/consumer-repo
GH_TOKEN="$(gh auth token)" \
  python3 /absolute/path/to/grillmester/scripts/grillmester.py \
  local launch --client opencode --github-access
```

Her kjører du selv `gh auth token` i skallet før launcheren starter; Grillmester-
launcheren resolver eller kjører ikke `gh`. GitHub CLI må finnes på `PATH`;
installer den ved behov med `brew install gh`. Copilot-local bruker i stedet
cplts native Copilot-profil og kan normalt bruke kontoen cplt medierer. Bruk
samme `--github-access`-form med `--client copilot` bare når du vil velge tokenet
eksplisitt.

`setup` finner OpenCode og Copilot CLI på `PATH` uten å starte dem. Finnes én
klient, velges den automatisk; finnes begge, spør launcheren. OpenCode-sessions
bruker ripgrep fra `PATH`; installer det med `brew install ripgrep` dersom
`grillmester local doctor` varsler. Standardendepunktet er
`http://127.0.0.1:8080/v1`. Launcheren leser `/v1/models`, velger automatisk
når serveren annonserer én modell og lagrer bare tilkoblingsbeskrivelsen i
`~/.config/grillmester/local.json`. En API-nøkkel lagres aldri; bruk eventuelt
`--api-key-env NAVN` eller `--api-key-file /absolutt/privat/fil` med Copilot
CLI. Miljøvariabelen må være dedikert og kan ikke være en bevart terminal-
variabel som `LANG` eller `TERM`. Nøkkelfilen må være bruker-eid, 0600, uten
hardlinks og utenfor prosjektet;
originalpathen deny-es også eksplisitt i cplt. OpenCode 1.18.20 lar tool-
subprosesser arve provider-miljøet og godtar derfor bare en nøkkelfri loopback-
server i local-flyten. Dette feiler lukket i `setup`; bruk Copilot CLI når
lokalserveren krever autentisering.

Hver launch bruker focused Barista med sju utviklingsskills. Bytt klient eller
be om full 7-agent/42-skill-kontekst for én sesjon uten å endre defaulten:

```bash
grillmester local --client copilot
grillmester local --client opencode
grillmester local --full --agent grillmester
```

`grillmester local status` viser valget, `grillmester local doctor` verifiserer
og viser cplt-/klientpath og versjon, prosjekt, agent, kontekst, endpoint,
modell og payload. `grillmester local --help` og
`grillmester local launch --help` viser hele brukerflaten, og
`grillmester local --print-command` viser en redigert kommando uten å lese
nøkkelen, skrive sessionstate eller kjøre klientprober. Previewen er bevisst
ikke en copy/paste-kommando fordi kortlivede policyfiler og secret-miljø ikke
materialiseres. Kjør `setup` på nytt for å endre lagret default.

### Avgrensede bakgrunnsoppgaver

`run` kjører én prompt non-interaktivt med lagret klient og modell, focused
Barista som default og automatiske tool-godkjenninger:

```bash
cd /path/to/clean-dedicated-worktree
grillmester local run "Fiks den avgrensede oppgaven og kjør testene"
```

Kommandoen kjører i foreground; legg den i en egen terminal når den skal jobbe
i bakgrunnen mens du gjør noe annet. Bruk alltid et rent, dedikert worktree,
ingen samtidige menneske- eller agentendringer og én `run` per worktree.
OpenCode bruker `run --auto`, mens Copilot CLI bruker sin non-interaktive
promptmodus. Begge auto-godkjenner prosjektwrites, shellkommandoer og URL-er
innenfor den effektive klient- og cplt-policyen. cplt beskytter ikke
prosjektfilene mot overskriving, sletting eller destruktive Git-operasjoner som
modellen selv starter.

`run` er derfor for små til middels store oppgaver med tydelig mål, scope og
verifikasjon. En exitkode `0` betyr at klientprosessen fullførte, ikke at
oppgaven er semantisk løst. Modellen kan fortsatt avslutte med
`Status: NEEDS_INPUT` eller `Status: NEEDS_FULL_CONTEXT`. Les sluttsvaret og
kontroller minst `git status`, hele diffen og avtalte tester før du bruker
resultatet. `--agent` og `--full` er engangsoverstyringer; lagret default endres
ikke. `--print-command` viser den redigerte kommandoformen uten å probe modellen
eller klientversjonen.

Autentisert GitHub-tilgang er av som default for OpenCode-run, og Copilot-run
nekter `gh`-shelltools uten eksplisitt opt-in. Når en oppgave faktisk trenger
GitHub, sett caller-eid `GH_TOKEN` og bruk `--github-access`:

```bash
GH_TOKEN="$GRILLMESTER_RUN_GITHUB_TOKEN" \
  grillmester local run --github-access \
  "Opprett den ferdig spesifiserte issuen i dette repoet og verifiser resultatet"
```

Denne opt-in-flyten krever GitHub CLI på `PATH`; installer den med
`brew install gh` dersom den mangler.

Dette autoriserer en unattended child: GitHub-skrivinger som er eksplisitt
autorisert i prompten kan skje uten en ny tool-dialog. Bruk et dedikert,
fine-grained token begrenset til nødvendig repository og minste nødvendige
permissions, ikke et bredt personlig standardtoken. Tokenet er en myk grense:
child-klienten kan lese det, og direkte API-kall kan omgå cplts best-effort
`gh`-guard. Ikke behandle flagget som hard repository-scoping. Hvis eksakt
issueinnhold eller annen bruker-eid beslutning ikke allerede er autorisert, skal
Barista returnere et utkast med `Status: NEEDS_INPUT` i stedet for å skrive.

Local-flyten har ingen cloudmodell-fallback, men den kan være tilkoblet.
Launcheren åpner den valgte localhost-porten og krever cplts forced proxy,
`gh`-guard og Git-guard. Brukerens og organisasjonens cplt-config forblir
autoritativ; Grillmester åpner ikke alle domener eller legger en annen sandbox
oppå. Webverktøy og dokumentasjonskilder virker når den effektive policyen og
klientens godkjenninger tillater det. Dette er ikke en egen Grillmester-
egressattest.

GitHub-auth følger klientens native cplt-profil. Copilot-local bruker
`cplt --agent copilot`; cplt kan derfor mediere brukerens vanlige Copilot-/GitHub-
credential fra GitHub CLI eller Keychain også uten `--github-access`.
Copilots innebygde GitHub MCP er fortsatt av, så agentens GitHub-kommandoer går
gjennom guarded `gh` og cplts repo-scope. cplt dokumenterer denne tokenbroen og
`gh`-guarden som en myk, best-effort kommandogrense, ikke som hemmelighold mot
en prosess med samme bruker-ID.

OpenCode får ingen GitHub-credential som default. Når brukeren eksplisitt setter
`GH_TOKEN` i caller-miljøet og velger `--github-access`, validerer launcheren
verdien uten å kjøre `gh` og sender den til valgt child-klient. Det samme flagget
kan brukes med Copilot for å velge en eksplisitt tokenverdi i stedet for cplts
normale kontooppslag. Launcheren skriver ikke caller-tokenet til config,
sessionstate eller preview, men klienten og godkjente tool-subprosesser kan lese
og eventuelt persistere det i sin skrivbare sessionstate. En lokal modell kan
også skrive tokenet til terminaloutput eller klientlogger hvis den inspiserer
miljøet; cplt kan ikke redigere modellens output i etterkant. Bruk riktig konto
og minst mulig scope. Interaktiv launch spør før sideeffekter; `local run`
utfører den eksakt autoriserte prompten uten en ny tool-dialog.

Child-prosessen får ikke lese eksisterende GitHub CLI-config direkte. Copilot-
profilens eventuelle credentialmediering eies av cplt; OpenCode ser bare et
eksplisitt opt-in-token. Høy-nivåkommandoer som `gh issue create` forblir under
`gh`-guard, og Git push forblir under Git-guard. OpenCodes websearch er aktiv,
og Grillmester velger Exa som provider. Når websearch brukes, sendes
søketeksten til Exa: interaktiv launch krever klientgodkjenning, mens `local
run` auto-godkjenner tool-et. Trafikken går gjennom den effektive cplt-
nettverkspolicyen; lokal inference betyr derfor ikke at søketeksten forblir på
maskinen.

Hver launch lar cplt-parenten beholde hostens `HOME`, men gir child-klienten
isolert XDG-, provider- og klientstate og den
distribuerte payloaden. Ambient OpenCode- og Copilot-komponenter som kan skygge
agentteamet avvises; repoets vanlige `AGENTS.md` kan fortsatt gi stående
prosjektkontekst. Dette er payloadisolasjon, ikke en egen runtime-sandbox. Bare
de to nyeste avsluttede sessionmappene beholdes ved sekvensiell bruk; `doctor`
og preview oppretter ingen sessionmappe.

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

Et forsiktig M4 Pro-utgangspunkt er:

- Q6 XL bare når unified memory har god margin over vektfilen; 24 GB er for
  lite, og også større maskiner trenger plass til KV-cache, runtime, OS, IDE og
  repoarbeid
- 32k context først; mål 64k etterpå hvis memory pressure og lange prefill-
  tider er akseptable
- `q8_0` for både K og V som et testbart cachekompromiss; sammenlign kvalitet
  og hastighet med `f16` før du standardiserer
- én server-slot og én tung lokal agentoppgave om gangen
- ingen MTP-/draftmodell i første correctness-baseline; mål det separat senere
- en separat Git-worktree per bakgrunnsoppgave som kan skrive

På en minnebåndbreddebegrenset maskin gjør flere samtidige requests vanligvis
ikke at totalarbeidet blir tilsvarende raskere. De deler samme båndbredde og
øker samtidig KV-/contexttrykket. Ved omtrent 9–10 genererte tokens/s bør
bakgrunnsoppgaver derfor være små, godt briefet og uavhengig verifiserbare.
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
2. Bruk memory-estimatet før lasting. Start med 32k context, maksimal trygg
   GPU-offload og én parallell request.
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
engine-/appversjoner. Når eksakt `q8_0` for K og V er en del av forsøket, bruk
den reproduserbare `llama.cpp`-flyten under og registrer binærversjonen.

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
  --ctx-size 32768 \
  --parallel 1 \
  --n-gpu-layers all \
  --flash-attn on \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --no-mmproj \
  --jinja \
  --reasoning on \
  --reasoning-effort xhigh \
  --temp 1.0 \
  --top-p 0.95 \
  --top-k 20 \
  --min-p 0 \
  --presence-penalty 0 \
  --repeat-penalty 1
```

`--no-mmproj` holder tekst-/kodepiloten mindre; fjern flagget og last den
reviewede vision-projectoren bare når oppgaven faktisk trenger bilder.
`llama-server` dokumenterer `q8_0` for begge cachetypene, contextstørrelse,
parallelle slots, Metal/GPU-offload og localhost-binding i sin
[serverreferanse](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).
Sampling- og thinkingverdiene følger Qwens anbefalte thinking-profil i
modellkortet; registrer dem som del av forsøket i stedet for å la en appversjon
endre dem stille.

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
            "context": 32768,
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

Når du vil starte en eksplisitt lokal bakgrunnsoppgave, bruk en offentlig
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
for en ferdig spesifisert bakgrunnsoppgave. Start bare én tung lokal
agentoppgave om gangen med denne laptopbaselinen.

## Avansert: manuell Copilot CLI BYOK

Bruk normalt `grillmester local --client copilot`; launcheren bygger og
saniterer BYOK-miljøet for deg. Den manuelle formen under er kun for debugging
og sammenligning. GitHub dokumenterer lokale OpenAI Chat
Completions-kompatible providers,
blant annet Ollama, vLLM og andre lokale endepunkter. Modellen må støtte både
streaming og tool calling; GitHub anbefaler minst 128k context for best resultat.
Qwen-piloten på 32k er derfor en bevisst redusert laptopprofil som må testes
mot Grillmesters reelle oppgaver, ikke en påstått fullgod standard.

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
export COPILOT_PROVIDER_MAX_PROMPT_TOKENS=28672
export COPILOT_PROVIDER_MAX_OUTPUT_TOKENS=4096
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
  -- --model "$COPILOT_MODEL" --effort low \
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

## Capability-smoke før modellen får bakgrunnsarbeid

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
