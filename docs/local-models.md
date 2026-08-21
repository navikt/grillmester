# Lokale modeller med Grillmester

En lokal modell krever ikke lenger automatisk et annet harness enn GitHub
Copilot. Velg inngang etter hvilken klient- og nettverksprofil du trenger:

OpenCode-eksemplene på denne siden forutsetter den release-gatede klienten
`1.18.19`; installer og versjonskontroller den som beskrevet i
[OpenCode-guiden](opencode.md#installer-eksakt-klient-og-reviewet-source-sha).

| Behov | Anbefalt inngang |
| --- | --- |
| Behold Copilot-pluginen og kjent CLI-flyt | Copilot CLI med BYOK mot LM Studio eller `llama-server` |
| Behold Copilot-appens UI | Copilot app BYOK i public preview; verifiser Grillmester-agent og modellvalg eksplisitt |
| Kjør Grillmester i et uavhengig, modellnøytralt harness | Det native OpenCode 1-targetet |
| Dokumenterbart ingen GitHub-trafikk fra harnesset | Copilot CLI med `COPILOT_OFFLINE=true` og lokal provider |
| Eksperimenter med provider/modell per session | OpenCode; targetet arver valgt sessionmodell |
| Behold primary-agenten i skyen, men kjør Kokk lokalt | OpenCode med bruker-eid `agent.kokk.model`-override |

Modellvalg endrer ikke data-, tool- eller godkjenningspolicy. Kontroller fortsatt
Navs gjeldende regler for modellartefakt, lisens, data, logging, oppdatering,
MCP-er og egress. En modell som kjører på maskinen gjør ikke webtools, MCP-er,
telemetri eller update-sjekker lokale av seg selv.

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

## Anbefalt først: LM Studio

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

## Koble OpenCode til den lokale serveren

Grillmesters OpenCode-target velger ikke provider. Merge en lokal provider i
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

Start deretter Grillmester-targetet og velg `lmstudio/<model-id>` eller
`llamacpp/qwen3.8-27b-local` i `/models`:

```bash
cd /path/to/consumer-repo
OPENCODE_CONFIG_DIR=/absolute/path/to/grillmester/targets/opencode-v1 \
  opencode --agent grillmester
```

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
OPENCODE_CONFIG_DIR=/absolute/path/to/grillmester/targets/opencode-v1 \
  opencode run \
    --agent barista \
    --model lmstudio/replace-with-id-from-v1-models \
    "Gjør denne tydelig avgrensede oppgaven og kjør de avtalte testene."
```

OpenCode dokumenterer `--agent` og `--model provider/model` for
[`opencode run`](https://opencode.ai/docs/cli#run). Kokk er en skjult subagent
som brukes gjennom Grillmester-delegering. Barista er riktig direkte inngang
for en ferdig spesifisert bakgrunnsoppgave. Start bare én tung lokal
agentoppgave om gangen med denne laptopbaselinen.

## Alternativ: behold Copilot CLI og bruk BYOK

GitHub dokumenterer nå lokale OpenAI Chat Completions-kompatible providers,
blant annet Ollama, vLLM og andre lokale endepunkter. Modellen må støtte både
streaming og tool calling; GitHub anbefaler minst 128k context for best resultat.
Qwen-piloten på 32k er derfor en bevisst redusert laptopprofil som må testes
mot Grillmesters reelle oppgaver, ikke en påstått fullgod standard.

Mot LM Studio:

```bash
export COPILOT_PROVIDER_TYPE=openai
export COPILOT_PROVIDER_BASE_URL=http://127.0.0.1:1234/v1
export COPILOT_MODEL=REPLACE_WITH_LM_STUDIO_MODEL_ID
export COPILOT_OFFLINE=true
copilot
```

Mot `llama-server` bruker du port `8080` og
`COPILOT_MODEL=qwen3.8-27b-local`. Se GitHubs
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
      "grillmester": { "model": "inherit" },
      "barista": { "model": "inherit" },
      "designer": { "model": "inherit" },
      "doctor-who": { "model": "inherit" },
      "kokk": { "model": "inherit" },
      "grill-inspektor": { "model": "inherit" },
      "researcher": { "model": "inherit" }
    }
  }
}
```

`subagents.agents.<name>.model = "inherit"` har høyere prioritet enn agentens
frontmatter og bruker parent/sessionmodellen ved dispatch. Se GitHubs
[settingsreferanse](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference#user-settings-copilotsettingsjson)
og
[modelloppløsning for custom agents](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference#custom-agent-frontmatter-fields).

Installer eller oppdater Grillmester-pluginen før du går offline. Med
`COPILOT_OFFLINE=true` forsøker CLI-en ikke GitHub-auth, sender ikke telemetri og
gjør bare nettverkskall til BYOK-provider. Når provider også er localhost, er
dette GitHubs dokumenterte local-only-flyt. `/delegate`, GitHub MCP og GitHub
Code Search er da ikke tilgjengelige. Se
[autentisering og offline mode](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/authenticate-copilot-cli#offline-mode).

## Copilot app med lokal provider er en egen pilot

GitHub Copilot app kan også kobles til LM Studio, Ollama eller et vilkårlig
OpenAI-kompatibelt HTTP-endepunkt gjennom **Settings → Model providers**. Dette
er foreløpig public preview. Appen krever GitHub-innlogging, og GitHubs
dokumentasjon gir ikke samme `COPILOT_OFFLINE`-garanti som CLI-guiden.

Behandle derfor app + Grillmester-plugin + lokal Qwen som en separat
klientprofil: bekreft plugin-/agentdiscovery, faktisk valgt modell, tool calls,
delegering og nettverkstrafikk før den omtales som lokal eller local-only. Se
GitHubs [BYOK-guide for Copilot app](https://docs.github.com/en/copilot/how-tos/github-copilot-app/use-byok-models).

## «Lokal modell» og «local-only» er to profiler

Hold disse valgene eksplisitt atskilt:

- **Local model:** inference går til localhost, men harnesset kan fortsatt ha
  webtools, MCP-er, telemetry, model-catalog-fetch og update-sjekker.
- **Local-only:** eneste tillatte nettverksmål er den lokale providerprosessen;
  remote providers, webtools, remote MCP-er, deling og update-/catalog-fetch er
  av, helst håndhevet med organisasjons- eller OS-egresskontroll.

Copilot CLI har en dokumentert `COPILOT_OFFLINE`-profil. OpenCode 1 har lokale
providers og brytere som `OPENCODE_DISABLE_AUTOUPDATE` og
`OPENCODE_DISABLE_MODELS_FETCH`, men Grillmesters standardtarget tillater
bevisst web-research når runtime og bruker godkjenner det. Targetet alene er
derfor **ikke** en local-only-garanti.

En fremtidig, eksplisitt OpenCode local-only-profil bør genereres og gates
separat med provider-allowlist, deny for `webfetch`/`websearch` og alle remote
MCP-tools, deaktiverte remote fetch/update-funksjoner, localhost-binding og en
platformhåndhevet egress-test. Ikke legg dette stille inn i standardtargetet;
det ville endre Designer/Researcher-capabilities for alle brukere.

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
