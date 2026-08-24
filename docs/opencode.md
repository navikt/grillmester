# Bruke Grillmester i OpenCode

Grillmester har et komplett, native target for OpenCode 1.x fra `1.18.20`: 7
agenter, 42 skills og 42 slash commands. Agentmodus, toolnavn, delegering og
permissions er oversatt til OpenCodes egne kontrakter; det er ikke
Copilot-pluginen pakket inn på nytt. `1.18.20` er release-testbaselinen, mens
launcheren godtar kompatible nyere 1.x-versjoner.

## Kom i gang

Den felles macOS-launcheren er ferdig, men Homebrew-oppføringen publiseres først
etter første stabile release og review i `navikt/homebrew-tap`. Kommandoen er
derfor foreløpig **ikke tilgjengelig**:

```bash
brew install navikt/tap/cplt navikt/tap/grillmester
brew install opencode
```

OpenCode er en brukerinstallert terminalklient. Grillmester resolver
`opencode` fra `PATH`; den installerer, erstatter eller skygger aldri klienten.
Den vises derfor ikke som app i Launchpad eller `/Applications`.

Start fra repoet du vil arbeide i:

```bash
cd /path/to/consumer-repo
grillmester
```

Velg **OpenCode** og deretter Grillmester, Barista, Designer eller Doctor Who.
Bare valgt klient versjonssjekkes gjennom cplt mot en tom mappe før valget kan
lagres. `grillmester choose` endrer defaulten. Mangler OpenCode, får du
`brew install opencode`; det skjer ingen stille fallback til Copilot.

En eksplisitt sesjon ser slik ut:

```bash
grillmester --client opencode --agent grillmester
```

Launcheren binder det distribuerte targetet og starter alltid OpenCode gjennom
cplt. Den vanlige kommandoen velger ikke provider eller modell; bruk din
brukereide OpenCode-config og `/models`.

Kontroller installasjonen uten å starte en agentsesjon:

```bash
grillmester doctor --client opencode
```

Proben har timeout og outputgrense, bruker en disponibel 0700-prosjektmappe og
gir aldri klienten skriverettighet i consumer-repoet.

### Lokal modell på macOS

Start en OpenAI-kompatibel modellserver på loopback og kjør:

```bash
cd /path/to/consumer-repo
grillmester local setup --client opencode
grillmester local
grillmester local run "Fiks den avgrensede oppgaven og kjør testene"
grillmester local --full --agent grillmester
```

Fra en checkout bruker du den virkelige launcherpathen, ikke en ikke-installert
`grillmester`-kommando:

```bash
cd /path/to/consumer-repo
python3 /absolute/path/to/grillmester/scripts/grillmester.py local setup
python3 /absolute/path/to/grillmester/scripts/grillmester.py local doctor
python3 /absolute/path/to/grillmester/scripts/grillmester.py local launch
python3 /absolute/path/to/grillmester/scripts/grillmester.py \
  local run "Fiks den avgrensede oppgaven og kjør testene"
```

`setup` bruker `http://127.0.0.1:8080/v1` som default og leser modellene fra
`/v1/models`; oppgi `--base-url http://127.0.0.1:1234/v1` for LM Studio.
Focused Barista er default. Engangsvalg endrer ikke lagret default.
`local run` kjører én foreground, non-interaktiv prompt og auto-godkjenner
OpenCodes tools; bruk et rent, dedikert worktree og kontroller diff og tester
etterpå. Se [kontrakten for avgrenset kjøring](local-models.md#avgrenset-kjøring).

Local betyr lokal inference, ikke offline. Modellrequests bindes til loopback,
mens websearch, dokumentasjon og GitHub kan brukes gjennom OpenCodes
permissions og cplts forced proxy, `gh`-guard og Git-guard når den effektive
cplt-policyen tillater trafikken. Launcheren åpner den eksakte localhost-porten,
men overstyrer ikke brukerens eller organisasjonens domeneconfig og gir ingen
egen egressattest. Den bruker samme kompatible OpenCode 1.x- og cplt-versjoner
som standardlauncheren, ikke en egen klientpin.

Grillmester velger Exa for OpenCodes websearch. Når tool-et brukes, sendes
søketeksten til Exa gjennom den effektive cplt-nettverkspolicyen. Interaktiv
launch spør gjennom OpenCodes permissionmodell; `local run` auto-godkjenner
tool-et sammen med øvrige tools. Bruk ikke websearch for tekst som skal bli på
maskinen.

Local-flyten skjermer tokenvariabler, rå `gh`-config og caller-PATH-verktøy for
begge klienter. OpenCode gir i tillegg hard isolasjon fra den ambient
GitHub-kontoen; Copilots cplt-profil tillater macOS Keychain og gir ikke samme
garanti. For en autentisert sesjon setter brukeren eksplisitt `GH_TOKEN` og
velger `--github-access` fra riktig consumer-repo:

```bash
cd /path/to/consumer-repo
GH_TOKEN="$(gh auth token)" \
  grillmester local --client opencode --github-access
```

Launcheren verifiserer at `gh` finnes uten å starte det, og skriver ikke tokenet
til config, sessionstate eller preview. Klienten og godkjente
tool-subprosesser kan lese og eventuelt persistere det i skrivbar sessionstate,
så dette er en myk grense. Bruk riktig konto og minst mulig scope. Uten opt-in
virker offentlig web fortsatt når cplt-policyen tillater det. Samme eksplisitte
form brukes med `--client copilot`.

Se [lokalmodellguiden](local-models.md) for LM Studio, `llama.cpp`, Qwen,
Copilot CLI og capability-smoke.

### Cloud-provider

Videresend bare credentialvariabelen som providerconfigen faktisk bruker:

```bash
export MODEL_PROVIDER_API_KEY='set-locally-never-in-the-bundle'
grillmester --client opencode --agent grillmester \
  --pass-env MODEL_PROVIDER_API_KEY \
  -- --model provider/model-id
```

Flagg før `--` går til cplt; flagg etter `--` går til OpenCode. HTTPS-port
`443` er standard. Begrensede providerdomener er en eksplisitt cplt-policy, ikke
noe Grillmester vedlikeholder parallelt.

OpenCodes innebygde GitHub Copilot-provider kan brukes etter normal `/connect`.
Autentiseringen tilhører OpenCode og krever verken `nav-pilot-agent` eller en
ekstra Grillmester-runtime. Releasegaten kjører med vilje ingen autentisert
providerforespørsel.

Hvis global cplt-config bruker en fail-closed allowlist, må nødvendige
providerdomener legges til i den policyen. Ikke bruk `--allow-all-domains` som
en skjult kompatibilitetsfiks når målet er en lukket allowlist. Local-launcheren
beholder den effektive cplt-policyen og åpner bare den valgte loopback-porten.

## Avansert: manuell binding og verifisering

Resten er for utvikling og releaseverifisering. Normal Homebrew-bruk trenger
ikke disse stegene.

### Bind et checkout-target manuelt

Fra en Grillmester-checkout kan en vedlikeholder binde targetet uten launcheren:

```bash
GRILLMESTER_ROOT=/absolute/path/to/grillmester
CONFIG_DIR="$GRILLMESTER_ROOT/targets/opencode-v1"
USER_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
SUPPORT_FILE="$USER_CONFIG_DIR/.gitignore"

mkdir -p "$USER_CONFIG_DIR"
if [[ -L "$SUPPORT_FILE" || ( -e "$SUPPORT_FILE" && ! -f "$SUPPORT_FILE" ) ]]; then
  echo "OpenCode runtime support must be a regular file: $SUPPORT_FILE" >&2
  exit 1
fi
if [[ ! -e "$SUPPORT_FILE" ]]; then
  install -m 600 "$CONFIG_DIR/.gitignore" "$SUPPORT_FILE"
fi

OPENCODE_CONFIG_DIR="$CONFIG_DIR" \
cplt --agent opencode \
  --project-dir "$PWD" \
  --allow-read "$CONFIG_DIR" \
  --pass-env OPENCODE_CONFIG_DIR \
  -- --agent grillmester
```

OpenCode 1.18.20 forsøker å skrive `.gitignore` i configområdet ved oppstart.
Støttefilen må derfor finnes før cplt gjør targetet read-only. Endre aldri en
eksisterende brukerfil automatisk. På macOS kan cplt nekte prosesskjøring fra
`/private/tmp` og `/private/var/folders`; bruk en vanlig brukereid plassering.

### Installer den eksakte testbaselinen manuelt

Eksakte versjoner brukes for reproduserbar CI-evidens, ikke som runtimekrav for
vanlige brukere:

```bash
npm install --global opencode-ai@1.18.20
test "$(opencode --version)" = "1.18.20"

brew install navikt/tap/cplt
test "$(cplt --version)" = "cplt 2026.08.17-062831-1008a92"
```

Releasegaten verifiserer de committede artifact-digestene før disse binærene
brukes som testinput. Det distribuerer ikke klientene og gjør dem ikke til
runtimepinner.

### Hent og verifiser en Grillmester-bundle

En GitHub Release publiserer én deterministisk terminal-`tar.gz`, detached
`.sha256` og Homebrew-formelen. GitHubs automatisk genererte source-arkiv er
ikke installasjonsartefaktet:

```bash
tag=vREPLACE_WITH_VERSION
asset="grillmester-terminal-${tag}.tar.gz"
shasum -a 256 -c "${asset}.sha256"
tar -xzf "$asset" -C /path/to/user-owned/extraction
```

For vanlig, native cplt-bruk er bundle-en nå klar. Den inneholder Grillmester-
payloadene og launcheren, men ingen OpenCode-, Copilot- eller cplt-binær.

## Hva launcheren faktisk gjør

For OpenCode:

1. resolver `cplt` og `opencode` fra `PATH`
2. kontrollerer kompatibel versjon gjennom cplt
3. binder det genererte targetet med `OPENCODE_CONFIG_DIR` og `--allow-read`
4. setter valgt offentlig agent på riktig plass for TUI eller `run`
5. lar cplt eie sandbox, proxy, repo-policy og `gh`-/Git-guards

Den installerer ingen klient, skriver ingen agent-/skillfiler i consumer-repoet
og har ingen direkte fallback uten cplt. OpenCodes vanlige brukerconfig eier
provider og modell i standardmodus. Local-modus bruker privat providerconfig og
avviser ambient komponenter som kan skygge den distribuerte payloaden.

## Agenter, commands og forwarding

OpenCode-targetet har syv native agenter. De fire offentlige velges direkte;
Kokk, Grill-inspektør og Researcher brukes gjennom delegering. Skills lastes
progressivt med OpenCodes native `skill`-tool, og de 42 commands speiler
skillinngangene.

For `run` plasserer launcheren valgt agent etter subkommandoen:

```bash
grillmester --client opencode --agent barista -- run "Fiks den avgrensede oppgaven"
```

Argumenter før `--` går til cplt; argumenter etter `--` går til OpenCode.
Reserverte agent-, config- og project-flagg kan ikke overstyre launcherbindingen.

## Verifiser discovery før en ekte oppgave

Fra en checkout:

```bash
python3 scripts/generate_opencode.py --check
python3 scripts/generate_context_projections.py --check
python3 scripts/validate.py
python3 scripts/smoke_opencode.py --require-binary
python3 scripts/smoke_opencode_runtime.py --require-binary --cplt cplt
```

Discovery-smoken kontakter ingen modell. Runtime-smoken bruker en deterministisk
loopbackprovider og beviser binding, permissions, delegering og blocked/allowed
writes—ikke kvaliteten til en vilkårlig modell.

## Oppdatering og rollback

`grillmester update` oppdaterer den installerte Grillmester-formelen. OpenCode
og cplt følger sine egne pakkekanaler. En kompatibel 1.x-oppgradering krever
normalt ingen Grillmester-release.

En immutable Grillmester-release rulles tilbake ved å installere forrige
reviewede versjon eller repinne marketplace-ref-en. Start en ny agentsesjon;
en pågående session beholder allerede lastet kontekst.

## Grensen mot OpenCode 2

OpenCode 2 er beta og utenfor første release-løfte. V1-targetfilene forventes å
være strukturelt kompatible, men permissions, provider/model-adferd og faktisk
runtimeparitet må testes separat før `opencode2` omtales som støttet. Bruk
`opencode` for den støttede OpenCode 1-flaten.
