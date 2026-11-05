# Bruke Grillmester i OpenCode

Teamets hovedvei er [Copilot-appen](installation.md#copilot-app) med lokal
sandbox. OpenCode er støttet for dem som vil bruke den klienten.

Grillmester har et komplett, native target for OpenCode 2 fra `2.2.5`: 6
agenter, 33 skills og 33 slash commands. Agentmodus, toolnavn, delegering og
permissions er oversatt til OpenCodes egne kontrakter; det er ikke
Copilot-pluginen pakket inn på nytt. `2.2.5` er release-testbaselinen, mens
launcheren godtar kompatible nyere 2.x-versjoner. Targetet heter fortsatt
`opencode-v1`. Det er navnet på filformatet, som OpenCode 2 leser uendret.

## Kom i gang

OpenCode kan foreløpig
piloteres fra en lokal Grillmester-checkout; videre terminaldistribusjon
samordnes med nav-pilot. Installer den bruker-eide OpenCode-klienten:

```bash
brew install opencode
```

Vil du ha en sandbox rundt klienten, installerer du også cplt:

```bash
brew install navikt/tap/cplt
```

OpenCode er en brukerinstallert terminalklient. Grillmester resolver
`opencode` fra `PATH`; den installerer, erstatter eller skygger aldri klienten.
Den vises derfor ikke som app i Launchpad eller `/Applications`.

Du trenger en lokal checkout av `navikt/grillmester`. Den er utviklings- og
pilotinput, ikke en installert eller immutable release. Kontroller oppsettet og
start deretter fra repoet du vil arbeide i:

```bash
cd /path/to/consumer-repo
python3 /absolute/path/to/grillmester/scripts/grillmester.py doctor
python3 /absolute/path/to/grillmester/scripts/grillmester.py \
  --client opencode --agent grillmester
```

I resten av guiden brukes `grillmester` som kortform. I checkout-piloten
erstattes den med
`python3 /absolute/path/to/grillmester/scripts/grillmester.py`.

Launcheren binder det distribuerte targetet og starter OpenCode gjennom cplt
når cplt er installert. Uten cplt, eller med `--no-cplt`, starter OpenCode
direkte. Da gjelder bare OpenCodes egne permissions, ikke cplts grenser for
filer, nettverk, `gh` og Git. Launcheren skriver en linje om dette når klienten
starter. Er cplt installert, men for gammel, stopper launcheren i stedet for å
droppe sandboxen; oppdater med `brew upgrade navikt/tap/cplt`, eller velg bort
cplt med `--no-cplt`.

Den vanlige kommandoen velger ikke provider eller modell; bruk din brukereide
OpenCode-config og `/models`. OpenCode 2 leser ikke `~/.config/opencode` når
`OPENCODE_CONFIG_DIR` peker på targetet. Uten cplt peker launcheren derfor
`OPENCODE_CONFIG` på din `opencode.json` eller `opencode.jsonc`, men ikke på
begge. Under cplt leser OpenCode ikke denne filen, og launcheren sier fra når du
har en. Da virker providere fra `/connect`, `OPENCODE_CONFIG_CONTENT` og
`grillmester local`. Egne agenter, skills og plugins i `~/.config/opencode`
lastes ikke i noen av tilfellene.

Versjonsproben har timeout og outputgrense og kjører i en midlertidig mappe, ikke
i consumer-repoet.

### Lokal modell på macOS

Lokale modeller krever cplt, fordi det er cplt som holder modellrequestene på
loopback. Start en OpenAI-kompatibel modellserver på loopback og bruk checkoutens
virkelige launcherpath, ikke en ikke-installert `grillmester`-kommando:

```bash
cd /path/to/consumer-repo
python3 /absolute/path/to/grillmester/scripts/grillmester.py local setup --client opencode
python3 /absolute/path/to/grillmester/scripts/grillmester.py local doctor
python3 /absolute/path/to/grillmester/scripts/grillmester.py local launch
python3 /absolute/path/to/grillmester/scripts/grillmester.py \
  local run "Fiks den avgrensede oppgaven og kjør testene"
```

`setup` bruker `http://127.0.0.1:8080/v1` som default og leser modellene fra
`/v1/models`; oppgi `--base-url http://127.0.0.1:1234/v1` for LM Studio.
Focused Grillmester er default. Engangsvalg endrer ikke lagret default.
`local run` kjører én foreground, non-interaktiv prompt og auto-godkjenner
OpenCodes tools; bruk et rent, dedikert worktree og kontroller diff og tester
etterpå. Se [kontrakten for avgrenset kjøring](local-models.md#avgrenset-kjøring).

Local betyr lokal inference, ikke offline. Modellrequests bindes til loopback,
mens websearch, dokumentasjon og GitHub kan brukes gjennom OpenCodes
permissions og cplts forced proxy, `gh`-guard og Git-guard når den effektive
cplt-policyen tillater trafikken. Launcheren åpner den eksakte localhost-porten,
men overstyrer ikke brukerens eller organisasjonens domeneconfig og gir ingen
egen egressattest. Den bruker samme kompatible OpenCode 2.x- og cplt-versjoner
som standardlauncheren, ikke en egen klientpin.

OpenCode 2 spør ved første websearch hvilken søkeleverandør du vil bruke, for
eksempel Exa. Søketeksten går deretter til leverandøren gjennom den effektive
cplt-nettverkspolicyen. Interaktiv launch spør gjennom OpenCodes
permissionmodell; `local run` auto-godkjenner tool-et sammen med øvrige tools.
Bruk ikke websearch for tekst som skal bli på maskinen.

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
  --pass-env MODEL_PROVIDER_API_KEY
```

Velg modell i OpenCode-configen, med `OPENCODE_CONFIG_CONTENT` eller med
`/models`. TUI-en i OpenCode 2 har ikke flagget `--model`, men det har `run`:

```bash
grillmester --client opencode --agent grillmester \
  --pass-env MODEL_PROVIDER_API_KEY \
  -- run --model provider/model-id "Fiks den avgrensede oppgaven"
```

Flagg før `--` går til cplt; flagg etter `--` går til OpenCode. Uten cplt gir
cplt-flagg en feilmelding, og klienten arver miljøet ditt direkte. HTTPS-port
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

Resten er for utvikling og releaseverifisering. Normal bruk trenger ikke
disse stegene.

### Bind et checkout-target manuelt

Fra en Grillmester-checkout kan en vedlikeholder binde targetet uten launcheren:

```bash
GRILLMESTER_ROOT=/absolute/path/to/grillmester
CONFIG_DIR="$GRILLMESTER_ROOT/targets/opencode-v1"

OPENCODE_CONFIG_DIR="$CONFIG_DIR" \
OPENCODE_CONFIG_CONTENT='{"default_agent":"grillmester"}' \
opencode --standalone
```

TUI-en i OpenCode 2 godtar ikke `--agent`, så agenten velges med
`default_agent`. `--standalone` gir klienten en privat server. Uten flagget
starter OpenCode en delt bakgrunnstjeneste og skriver `service.json` med
tjenestens passord i `OPENCODE_CONFIG_DIR`, som her er targetet.

Med cplt bruker du i stedet:

```bash
OPENCODE_CONFIG_DIR="$CONFIG_DIR" \
OPENCODE_CONFIG_CONTENT='{"default_agent":"grillmester"}' \
cplt --agent opencode \
  --project-dir "$PWD" \
  --allow-read "$CONFIG_DIR" \
  --pass-env OPENCODE_CONFIG_DIR \
  --pass-env OPENCODE_CONFIG_CONTENT
```

cplt kjører en egen tjeneste for hver økt og gir den en egen config-mappe.
Flagget `--standalone` feiler under cplt. På macOS kan cplt nekte prosesskjøring fra
`/private/tmp` og `/private/var/folders`; bruk en vanlig brukereid plassering.

### Installer den eksakte testbaselinen manuelt

Eksakte versjoner brukes for reproduserbar CI-evidens, ikke som runtimekrav for
vanlige brukere:

```bash
npm install --global @opencode/cli@2.2.5
test "$(opencode --version)" = "opencode v2.2.5"

brew install navikt/tap/cplt
test "$(cplt --version)" = "cplt 2026.11.02-225238-10a2882"
```

Releasegaten verifiserer de committede artifact-digestene før disse binærene
brukes som testinput. Det distribuerer ikke klientene og gjør dem ikke til
runtimepinner.

### Hent og verifiser en Grillmester-bundle

En GitHub Release publiserer én deterministisk terminal-`tar.gz` og en
detached `.sha256`. GitHubs automatisk genererte source-arkiv er ikke
installasjonsartefaktet:

```bash
tag=vREPLACE_WITH_VERSION
asset="grillmester-terminal-${tag}.tar.gz"
release_dir="/path/to/user-owned/releases/$tag"
shasum -a 256 -c "${asset}.sha256" &&
  mkdir "$release_dir" &&
  tar -xzf "$asset" -C "$release_dir"
```

Foreldrekatalogen `/path/to/user-owned/releases` må finnes. `mkdir` skal
opprette en **ny, tom, versjonert katalog** og feile dersom den allerede finnes;
ikke erstatt kommandoen med `mkdir -p` eller pakk ut over en eldre installasjon.
Arkivet har roten `grillmester-terminal-v1`. Bruk den nye launcheren direkte:

```bash
python3 "$release_dir/grillmester-terminal-v1/scripts/grillmester.py" doctor
```

Oppdater eventuelt din eksisterende launcherlenke eller snarvei på `PATH`
til den nye absolutte scriptpathen. Behold tidligere versjonskatalog for
rollback og `~/.config/grillmester` for lagrede valg. `tar` fjerner ikke
utgåtte filer ved utpakking over en gammel katalog; for eksempel vil en gammel
Barista-fil gjøre den nye payloadens manifest ugyldig. Repo- eller brukereide
agent-/skillkopier endres ikke av denne installasjonen.

Bundle-en er nå klar. Den inneholder Grillmester-payloadene og launcheren, men
ingen OpenCode-, Copilot- eller cplt-binær.

## Hva launcheren faktisk gjør

For OpenCode:

1. resolver `opencode` og eventuelt `cplt` fra `PATH`
2. kontrollerer kompatibel versjon, gjennom cplt hvis den er i bruk
3. peker `OPENCODE_CONFIG_DIR` på det distribuerte targetet
4. velger offentlig agent med `default_agent` i `OPENCODE_CONFIG_CONTENT`, og
   med `--agent` for `run`; annen inline config beholdes
5. slår av OpenCodes gratismodeller, siden OpenCode ellers sender koden til en
   av dem når ingen provider er satt opp; `OPENCODE_DISABLE_FREE_MODELS=false`
   slår dem på igjen
6. lar cplt eie sandbox, proxy, repo-policy og `gh`-/Git-guards, eller starter
   OpenCode med `--standalone` når cplt ikke er i bruk

Den installerer ingen klient og skriver ingen agent-/skillfiler i
consumer-repoet. OpenCodes vanlige brukerconfig eier provider og modell i
standardmodus. Local-modus krever cplt, digestverifiserer targetet, kopierer de
samme bytene til en privat `OPENCODE_CONFIG_DIR`, bruker privat providerconfig
og avviser ambient komponenter som kan skygge den distribuerte payloaden.

Targetets `opencode.json` setter disse standardreglene for alle agenter:

- `external_directory` spør før OpenCode leser eller skriver utenfor prosjektet.
  Skills i `OPENCODE_CONFIG_DIR` er unntatt, ellers ville hver referansefil
  utløst et spørsmål. OpenCode 2 tillater dette ellers uten å spørre.
- `execute` er avslått. Code Mode kan gjøre HTTP-kall som `webfetch: deny` ikke
  stopper.
- `opencode_*` er avslått, slik at modellen ikke flytter økter eller oppretter
  worktrees. `opencode_worktree_remove` vises fortsatt, men OpenCode krever
  samme godkjenning for den som for `edit`.

Dette er standardregler, ikke tekniske grenser. Brukerens og repoets
OpenCode-config kan overstyre dem, og et repo kan kjøre egen kode gjennom
`.opencode/plugins`. Under cplt begrenser sandboxen fortsatt filer og nettverk.
Uten cplt er det ingenting rundt klienten. Bruk derfor cplt i repoer du ikke
stoler på, eller sett `OPENCODE_DISABLE_PROJECT_CONFIG=1`. Det slår også av
repoets `AGENTS.md`.

## Agenter, commands og forwarding

OpenCode-targetet har seks native agenter. De tre offentlige velges direkte;
Grill-inspektør, Researcher og Perspektiv brukes gjennom delegering. Skills lastes
progressivt med OpenCodes native `skill`-tool, og de 33 commands speiler
skillinngangene.

TUI-en får agenten fra `default_agent`, som vinner over et `default_agent` i
consumer-repoet. For `run` plasserer launcheren valgt agent etter subkommandoen:

```bash
grillmester --client opencode --agent grillmester -- run "Fiks den avgrensede oppgaven"
```

Argumenter før `--` går til cplt; argumenter etter `--` går til OpenCode.
Reserverte agent-, project- og `--standalone`-flagg kan ikke overstyre
launcherbindingen. Uten cplt avviser launcheren OpenCodes egne kommandoer `acp`,
`pair`, `serve`, `service`, `uninstall`, `update` og `upgrade`, fordi de ikke
starter en agentøkt. Kjør dem med `opencode` direkte.

## Verifiser discovery før en ekte oppgave

Fra en checkout:

```bash
python3 scripts/generate_opencode.py --check
python3 scripts/generate_context_projections.py --check
python3 scripts/validate.py
python3 scripts/smoke_opencode.py --require-binary --cplt cplt
```

Smoken kontakter ingen ekte modell. En deterministisk loopbackprovider styrer
tool-kallene, og hver økt starter gjennom launcheren: direkte, og gjennom cplt
når `--cplt` er oppgitt. Den beviser binding, permissions, skill-lasting og
stoppede lesinger og writes, ikke kvaliteten til en vilkårlig modell. Linux-CI
kjører den direkte, mens macOS-gaten også går gjennom cplt.

## Oppdatering og rollback

Hvis Homebrew-kanalen aktiveres senere, vil `grillmester update` oppdatere den
installerte Grillmester-formelen. Kommandoen er ikke del av dagens
checkout-pilot. OpenCode og cplt følger sine egne pakkekanaler. En kompatibel
2.x-oppgradering krever normalt ingen Grillmester-release.

En immutable Grillmester-release rulles tilbake ved å installere forrige
reviewede versjon eller repinne marketplace-ref-en. Start en ny agentsesjon;
en pågående session beholder allerede lastet kontekst.

## Bytte fra OpenCode 1

Launcheren støtter ikke lenger OpenCode 1. Fjern den gamle klienten før du
installerer OpenCode 2. Fra npm:

```bash
npm uninstall --global opencode-ai
brew install opencode
```

Fra OpenCodes tap:

```bash
brew uninstall anomalyco/tap/opencode
brew install opencode
```

`--model` på TUI-en virker ikke lenger; se [Cloud-provider](#cloud-provider).
