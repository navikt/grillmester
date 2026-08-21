# Bruke Grillmester i OpenCode

Grillmester har et komplett, native target for den release-gatede klienten
OpenCode `1.18.19` i `targets/opencode-v1/`. Targetet inneholder 7 agenter, 42
skills og 42 slash commands. Det er ikke en Copilot-plugin pakket inn på nytt:
agentmodus, toolnavn, delegering og permissions er oversatt til OpenCodes egne
kontrakter. Andre OpenCode 1-versjoner er `UNVERIFIED` til de har passert samme
gate; «nyeste stabile» er derfor ikke en støttet installasjonsinstruksjon.

OpenCode 2 er fortsatt beta og er ikke en støttet Grillmester-klientflate ennå.
Bruk binæren `opencode`, ikke `opencode2`, når du trenger den release-gatede
flaten. Se [grensen mot V2](#grensen-mot-opencode-2).

## Installer eksakt klient og reviewet source-SHA

Grillmesters release-tag peker på en catalog-only commit. Selve OpenCode-
targetet ligger i source-commit-en som katalogen og release notes navngir.
Bruk den eksakte 40-tegns source-SHA-en som er oppgitt for payloaden — ikke
`main` og ikke release-taggen som checkout-ref:

```bash
npm install --global opencode-ai@1.18.19
test "$(opencode --version)" = "1.18.19"

git clone https://github.com/navikt/grillmester.git /path/to/grillmester
git -C /path/to/grillmester checkout --detach REVIEWED_SOURCE_SHA
```

Versjonstesten skal lykkes før du fortsetter. `opencode-ai@1.18.19` er samme
eksakte klient som release-gaten bruker; en nyere OpenCode 1-binær må gates og
dokumenteres før den erstatter denne pinnen. Se også OpenCodes
[offisielle installasjonsguide](https://opencode.ai/docs). Grillmester har
foreløpig ingen OpenCode-marketplace eller Grillmester-installer, og skriver
ingen filer i consumer-repoet.

## Start Grillmester i et repo

`targets/opencode-v1/` ligger med vilje ikke i consumerens `.opencode/`.
Aktiver den reviewede checkouten for prosessen du starter:

```bash
cd /path/to/consumer-repo
OPENCODE_CONFIG_DIR=/absolute/path/to/grillmester/targets/opencode-v1 \
  opencode --agent grillmester
```

OpenCode dokumenterer at `OPENCODE_CONFIG_DIR` oppdages som en vanlig config
directory med blant annet `agents/`, `commands/` og `skills/`. Den lastes etter
globale og prosjektlokale config directories. Se
[custom directory og precedence](https://opencode.ai/docs/config#custom-directory).

Velg provider og modell med OpenCodes vanlige `/connect`- og `/models`-flyt.
Targetet pinner ingen modell: primary-agenten bruker sessionmodellen, og de
interne subagentene arver den. Se [lokale modeller](local-models.md) hvis du vil
kjøre Qwen eller en annen OpenAI-kompatibel modell lokalt.

Targetets minimale `opencode.json` endrer ikke OpenCodes `default_agent`.
`--agent grillmester` velger derfor Grillmester eksplisitt ved oppstart, mens
OpenCodes innebygde agenter fortsatt er tilgjengelige. I TUI-en kan du bruke
`Tab` for å bytte mellom blant annet de fire Grillmester-primary-agentene:

- `grillmester` for viktig, uklart eller tverrgående arbeid
- `barista` for en tydelig, vanlig repooppgave
- `designer` for designutforsking
- `doctor-who` for produkt-, team- og Nav-arkitekturarbeid

Kokk, Grill-inspektør og Researcher er skjulte subagenter. De er tilgjengelige
for native `task`-delegering, men vises ikke som ordinære startpunkt. Skills
lastes progressivt med OpenCodes native `skill`-tool. Command-wrapperne gir
også eksplisitt slash-bruk, for eksempel:

```text
/grillmester-security-review Review auth-endringen i denne diffen
```

## Verifiser discovery før en ekte oppgave

Kjør først i et tomt eller disponibelt testrepo:

```bash
OPENCODE_CONFIG_DIR=/absolute/path/to/grillmester/targets/opencode-v1 \
  opencode agent list

OPENCODE_CONFIG_DIR=/absolute/path/to/grillmester/targets/opencode-v1 \
  opencode run --agent barista \
  "Les repoets AGENTS.md og oppsummer build- og testkommandoene. Ikke gjør endringer."
```

Bekreft at rosteret har 7 Grillmester-agenter, at de fire Grillmester-primary-
agentene kan velges ved siden av eventuelle innebygde agenter, og at slash-
listen har `grillmester-`-commands. Test deretter i en disponibel fixture:

1. en read-only oppgave uten nettverk
2. én ufarlig write som krever forventet godkjenning
3. én avvist write uten sideeffekt
4. Grillmester-delegering til Kokk og uavhengig Grill-inspektør
5. en representativ skill med relative references eller scripts

Ikke bruk `--auto` før permissiontesten er bestått. OpenCode dokumenterer at
auto-mode godkjenner det som ellers ville vært `ask`; eksplisitte `deny`-regler
gjelder fortsatt. Agentprompten er uansett ikke en sikkerhetsgrense. Se
[OpenCode permissions](https://opencode.ai/docs/permissions).

## Repo-kontekst og kollisjoner

Behold consumerens `AGENTS.md` i consumer-repoet. Både OpenCode og GitHub
Copilot støtter filen som stående repo-instruksjon, mens Grillmester leverer
valgbare roller og oppgaveorienterte skills. Se
[hva som skal ligge hvor](repository-context.md#hva-skal-ligge-hvor).

OpenCode nøkkelsetter agents, commands og skills med ID. Siden custom config
directory lastes sent, kan et Grillmester-ID skygge en global eller repo-lokal
definisjon med samme navn. Kontroller kjente kollisjoner før pilot; ikke bruk en
navnelik overstyring som en skjult patch av Grillmester.

Targetet konfigurerer ikke MCP. Figma, GitHub Projects og andre eksterne
capabilities finnes bare når OpenCode-runtime faktisk har en reviewet server,
riktig autorisasjon og riktige permissions. Manglende capability skal gi et
reviewbart utkast eller `NEEDS_CONTEXT`, ikke shell-/API-fallback.

## Oppdatering og rollback

OpenCode-targetet har ingen skjult sync eller auto-update. Oppdater ved å
sjekke ut en ny reviewet source-SHA og starte en ny session:

```bash
git -C /path/to/grillmester fetch origin
git -C /path/to/grillmester checkout --detach NEW_REVIEWED_SOURCE_SHA
```

Rollback er samme kommando med forrige source-SHA. En aktiv session kan ha
lastet gamle prompts og skills; avslutt den før du vurderer resultatet.

## Grensen mot OpenCode 2

OpenCode oppgir at V2-betaen leser støttede V1-agentfiler, commands og skills,
men V2 bruker andre native permissionnavn og nye plugin-/server-API-er. V1-
plugins fungerer ikke i V2. Grillmester-targetet bruker ingen OpenCode-plugin,
men forventet filkompatibilitet er ikke det samme som verifisert runtime-
paritet.

Kjør derfor V2 kun som en eksplisitt beta-smoke. Ikke konverter den delte
target-configen til V2-format og bruk den samtidig fra V1. OpenCode anbefaler å
beholde V1-oppsettet til provider, agents, permissions, skills og øvrige
capabilities er verifisert. Se den offisielle
[V1-til-V2-guiden](https://opencode.ai/v2/docs/migrate-v1).

Arkitekturbegrunnelsen ligger i
[ADR 0001](decisions/0001-native-opencode-v1-target.md).
