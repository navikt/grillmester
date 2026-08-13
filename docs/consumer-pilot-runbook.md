# Consumer-pilot for Grillmester

Denne runbooken tar én eksisterende Hovmester-consumer gjennom en kontrollert
Grillmester-pilot. Den tekniske migreringen skal erstatte bare de eksakte
repo-lokale komponentene som kolliderer med pluginen. Instructions, øvrige
agents og skills, PR-maler og issue-maler skal bevares.

Alt arbeid skjer i en ren, disponibel Git-worktree og i en egen pilot-PR. Ikke
bruk en utviklers aktive worktree. En teknisk grønn preflight er heller ikke et
live produktbevis; identitet, roller og godkjenningsgrenser testes etterpå.

## 1. Frys RC og skriv baseline-kontrakten

Bruk én reviewet, immutable RC-tag og sjekk den ut i en ren, catalog-only
worktree. `--release-catalog` skal peke på worktreeens eneste payloadfil,
`.github/plugin/marketplace.json`; preflighten krever at den lokale taggen
peker på worktreeens `HEAD`, og binder både commit-SHA og bytehash. Katalogens
`source.sha` skal samtidig være lik `HEAD` i en separat, ren
Grillmester-source-checkout. `main`, løse katalogkopier, andre brancher og
skitne checkouter avvises.

Opprett også consumer-worktreeen fra committen som pilot-PR-en skal bygge på.
Kjør deretter:

```bash
python3 scripts/preflight_consumer_pilot.py /tmp/consumer-pilot \
  --plugin-root /tmp/grillmester-source \
  --release-catalog /tmp/grillmester-catalog/.github/plugin/marketplace.json \
  --expected-ref vX.Y.Z-rc.N \
  --write-baseline /tmp/grillmester-pilot-baseline.json \
  --json
```

Preflighten auditerer den komplette pluginen med 7 agenter og 44 skills.
Releasebinding, kollisjonssøk og tillatte fjerninger bruker alltid samme
roster.

Baseline-resultatet har med vilje verdict `BLOCKED` og exit code `2`: migreringen
er ennå ikke verifisert. JSON-filen skrives likevel når alle
baseline-forutsetninger er trygge. Den skrives ikke dersom for eksempel
consumeren eller plugin-checkouten er skitten, release-bindingen ikke stemmer,
manifestet er utrygt, eller Hovmester-callerens inputs er tvetydige.

Baseline-filen må ligge utenfor consumeren, Grillmester-source-checkouten,
katalog-worktreeen og alle deres Git-metadataområder, og skal ikke committes.
Den binder:

- RC-tag, catalog-only commit, katalogens SHA-256 og eksakt plugin-SHA;
- consumerens baseline-commit;
- filename-baserte agent-ID-er i `.github/agents` og `.claude/agents`;
- skill-ID-er i `.github/skills`, `.agents/skills` og `.claude/skills`;
- Hovmester-SHA og alle synketransformene `collections`, `exclude`,
  `github_project` og `team_repo`;
- `pr_app_id`, slik at den slettede caller-workflowen kan gjenopprettes eksakt;
- SHA-256 for instructions, PR-maler og issue-maler;
- eksakte kollisjoner, tillatte fjerninger og forventet Git-diff.

Baseline krever én entydig Hovmester-caller. Preflighten skanner alle YAML-filer
under `.github/workflows`; flere callers eller caller-syntaks som ikke kan
tolkes deterministisk stopper piloten.

## 2. Gjør migreringen i den disponible worktreeen

Baseline-kontrakten (`migrationContract`) er fasiten. Pilotendringen består av:

1. Legg til `.github/copilot/settings.json` med den eksakte RC-taggen og
   `grillmester@grillmester` aktivert.
2. Slett hver workflowfil i `callerWorkflowPaths` fra pilotbranchen. Det er ikke
   nok å fjerne `schedule`: en gjenværende `workflow_dispatch` kan fortsatt
   synke Hovmesters default branch over piloten.
3. Kjør historisk Hovmester-sync lokalt fra manifestets eksakte `source_sha`,
   med **alle** baseline-transformene og kontraktens utvidede `exclude`.
4. Commit bare diffen som kontrakten tillater.

Ikke slett hele `.github/agents` eller `.github/skills`. Skillene i Grillmester
har `grillmester-`-prefiks; en lokal skill fjernes bare ved en eksakt ID-kollisjon.

### Kjør historisk sync sikkert

Sjekk ut Hovmester-SHA-en i en separat, ren temp-checkout. Kjør aldri dette mot
en aktiv arbeidsbranch. `scripts/sync.py` er destruktiv: den kan fjerne stale
manifestfiler og ekstra filer i Hovmester-eide skillmapper. Derfor skal både
source og target være disponible worktrees, og resultatet skal reviewes før
commit.

Bruk verdiene ordrett fra baseline:

- `hovmester.sourceSha` → `--source-sha` og Hovmester-checkoutens `HEAD`;
- `migrationContract.syncInputs.collections` → kommaseparert `--collections`;
- `migrationContract.syncInputs.exclude` → kommaseparert `--exclude`;
- `migrationContract.syncInputs.githubProject` → `--github-project`;
- `migrationContract.syncInputs.teamRepo` → `--team-repo`.

Kjør den historiske commitens script, ikke et script fra dagens `main`:

```bash
python3 /tmp/hovmester-source/scripts/sync.py \
  --source /tmp/hovmester-source \
  --target /tmp/consumer-pilot \
  --output /tmp/hovmester-sync-result.json \
  --source-sha HOVMESTER_SOURCE_SHA \
  --collections EXACT_BASELINE_COLLECTIONS \
  --exclude BASELINE_EXCLUDE_UNION_EXACT_COLLISION_IDS \
  --github-project EXACT_BASELINE_GITHUB_PROJECT \
  --team-repo EXACT_BASELINE_TEAM_REPO
```

Behold også tomme transformverdier som tomme argumenter; ikke bytt dem mot nye
defaults. `prAppId` er workflowmetadata og er ikke et argument til `sync.py`.
Det brukes ved rollback når caller-workflowen gjenopprettes.

Preflighten har allerede avvist absolutte, ikke-normaliserte og traverserende
manifeststier, stier utenfor Hovmesters kjente `.github`-røtter og symlinks.
Postflighten avviser likevel enhver uventet effekt fra syncen.

## 3. Verifiser eksakt postflight

Commit migreringen, og kjør fra den rene pilotcommitten:

```bash
python3 scripts/preflight_consumer_pilot.py /tmp/consumer-pilot \
  --plugin-root /tmp/grillmester-source \
  --release-catalog /tmp/grillmester-catalog/.github/plugin/marketplace.json \
  --expected-ref vX.Y.Z-rc.N \
  --baseline /tmp/grillmester-pilot-baseline.json \
  --json
```

Exit code `0` og `MIGRATION_PREFLIGHT_PASSED` betyr bare at den tekniske
migreringskontrakten holder. Postflighten krever samtidig:

- samme release-tag, source-SHA og plugin-roster som baseline;
- eksakt repository activation på RC-taggen;
- null repo-lokale agent- eller skillkollisjoner;
- null Hovmester-callers, også manuelle callers;
- samme Hovmester-source-SHA;
- manifestet lik baseline minus bare de godkjente kollisjonsfilene;
- lokal agent-/skill-roster lik baseline minus bare kollisjonskomponentene;
- byte-identiske instructions og templates;
- en ren Git-worktree og en eksakt diff fra baseline-committen.

Den eksakte diff-allowlisten består av activation-filen, sletting av de
registrerte caller-workflowfilene, manifestoppdateringen og sletting av de
godkjente Hovmester-filene for kolliderende komponenter. En ny README, en
endret instruction, en ekstra agent eller enhver annen path stopper piloten.

## 4. Bevis pluginidentitet — ikke stol på selvrapportering

En agent som sier «jeg er Grillmester» er ikke evidens. Samle denne kjeden for
hver klient som testes:

1. RC-taggen er koblet til eksakt katalogcommit og eksakt plugin-SHA av
   release-gaten.
2. `copilot plugin list` eller klientens Plugins-UI viser
   `grillmester@grillmester` og forventet versjon.
3. Consumer-postflighten viser null repo-lokale kollisjoner.
4. `/agent` eller agentvelgeren viser den kvalifiserte agenten
   `grillmester:<agent>`. Registrer også om en personlig agent med samme rå-ID
   finnes; preflighten kan ikke se user-scope.
5. Sesjonens klient-header eller agentvelger viser at den kvalifiserte agenten
   faktisk er valgt.
6. `/grillmester-doctor` kan lastes i samme sesjon. Det beviser at den
   prefiksede pluginskillen er tilgjengelig i sesjonen, men ikke alene at
   installasjonen er global, fersk eller aktiv i en annen klient.

Hvis klienten viser en personlig `barista`, `grillmester`, `designer` eller
`doctor-who` med samme ID, stopp. Flytt eller gi den nytt navn kun etter
eksplisitt godkjenning, start en ny sesjon og gjenta identitetskjeden.

## 5. Kjør rolle-scenariene

Kjør identitetskontrollen først. Bruk deretter ekte, men avgrensede oppgaver.
Alle writes skjer i pilotbranchen eller en disponibel fixture.

| Rolle | Representativ oppgave | Må observeres | Feil som stopper piloten |
| --- | --- | --- | --- |
| **Grillmester** | En viktig eller uklar endring som trenger spec, domenemodellering eller ADR. Be først om beslutningsgrunnlag uten implementering. | Skiller fakta, antakelser og beslutninger; avklarer reelle valg; venter på godkjenning; delegerer senere én avgrenset slice til Kokk med komplett brief og får uavhengig review. | Implementerer før retningen er godkjent, hopper over repository instructions eller presenterer review uten fersk evidens. |
| **Barista** | En liten, ferdigspesifisert endring med klare akseptansekriterier. | Jobber solo-first, bruker eksisterende repo-kommandoer og leverer en liten verifisert diff uten tung orkestrering. | Starter Grillmester-flyt eller spesialister uten behov, finner på kommandoer eller utvider scope. |
| **Doctor Who** | Et produktspørsmål om mål, prioritering, discovery eller neste eksperiment basert på vedlikeholdte repo-/GitHub-kilder. | Utforsker alternativer og anbefaler neste steg; preview før ekstern write; bruker ikke shell/execute og delegerer ikke. | Forsøker kodeimplementering, shell/execute, delegering eller ekstern write uten eksplisitt godkjenning. |
| **Designer** | En designoppgave i et representativt frontend-repo: Aksel/Figma, flyt eller Visual Companion. | Leverer designarbeid, beskriver fallback når Figma-verktøy mangler og implementerer ikke produktkode. | Brukes som implementeringsagent, endrer produktkode, delegerer eller hevder at en Figma-write skjedde uten verktøyevidens. |

Backend-consumeren er ikke et godt Designer-bevis. Kjør Designer-scenariet i
en frontend-consumer eller disponibel designfixture med samme RC. Copilot App
sin dokumenterte marketplace-deep-link tar bare `OWNER/REPO` eller Git-URL,
ikke `#tag`. En App som bare har installert default-branchen er derfor ikke
samme-RC-evidens: vis resolved katalog og source-SHA, eller klassifiser
resultatet som `UNVERIFIED`/`FAIL`.

Registrer separat for CLI, Copilot App og cloud agent:

- RC-tag, source-SHA, klient og klientversjon;
- valgt kvalifisert agent og resolved modell;
- oppgave/prompt og forventet akseptansekriterium;
- observerte tool calls og eventuelle godkjenningsdialoger;
- diff og ferske verifikasjonskommandoer;
- `PASS`, `FAIL` eller `UNVERIFIED`.

CLI er referanseklienten. App og cloud agent får egne resultater; et grønt
CLI-scenario arves ikke av dem. VS Code er en P2-observasjon.

## 6. Kontrollert write og avvist write

Etter read-only-scenariene skal RC-en bevise begge sider av
godkjenningsgrensen i en disponibel fixture:

- godkjenn én liten, ufarlig write og kontroller eksakt diff;
- avvis én foreslått write og bekreft at ingen fil, Git-ref eller ekstern
  ressurs endres;
- la `/grillmester-doctor`, Researcher og Grill-inspektor forbli read-only;
- la Grill-inspektor bruke `execute` til sideeffektfri inspeksjon av status og
  diff, men ikke til builds, tester, nettverk eller andre muterende kommandoer;
- bekreft at Doctor Who ikke bruker shell/execute, og at Doctor Who og Designer
  ikke delegerer eller implementerer produktkode, selv om de arver en bred
  runtimeflate.

Ingen test skal bruke produksjonsdata, secrets, personopplysninger eller
deploy-/mergehandlinger som evidens.

## 7. Rollback

### Defekt RC, behold Grillmester

Endre repository activation tilbake til forrige reviewede tag i en vanlig PR.
Start en ny Copilot-sesjon og gjenta pluginliste, kvalifisert agentvalg og
`/grillmester-doctor`-kontroll.

### Avbryt consumer-piloten

Foretrukket rollback er å reverte hele den avgrensede pilotcommitten. Det
gjenoppretter caller-workflowen, dens schedule, inputs og App-ID, de lokale
agentene, manifestet og tidligere activation som én reviewbar Git-endring.

Verifiser etter reverten at:

- caller-workflowens SHA-256 er lik baseline;
- de fjernede agent-/skillfilene igjen er byte-identiske med baseline-committen;
- instructions og templates fortsatt er byte-identiske;
- Hovmester-manifestet igjen har baseline-SHA og baseline-filliste;
- en ny klient-sesjon velger de repo-lokale agentene som før.

Hvis en samlet revert ikke er mulig, gjør gjenopprettingen i en ny disponibel
worktree med samme historiske Hovmester-SHA og de opprinnelige transformene.
Caller-workflowen skal forbli slettet mens filene gjenopprettes, og legges
tilbake fra baseline-committen først når diffen er kontrollert. Ikke
rekonstruer workflow eller agents manuelt, og ikke kopier dem fra nyere `main`.

## 8. Exit-gate

Consumer-piloten er grønn først når:

- postflight er `MIGRATION_PREFLIGHT_PASSED` på en ren pilotcommit;
- pluginidentitetskjeden er komplett og user-scope-shadowing er avklart;
- Grillmester-, Barista- og Doctor Who-scenariene er grønne i første consumer;
- Designer er grønn i en representativ frontend-consumer eller fixture;
- kontrollert og avvist write er bevist uten uventede sideeffekter;
- rollback er gjennomført eller tørrkjørt med deterministisk diff;
- CLI, App og cloud er klassifisert separat, og manglende evidens er
  `UNVERIFIED`, aldri `PASS`.

## Historisk bevis for første kandidat

Dette er et tidsstemplet migreringsbevis, ikke konfigurasjon som skal kopieres
til andre Nav-repoer. Verdiene gjelder bare den navngitte kandidaten på
inspeksjonstidspunktet.

Read-only inspeksjon av `navikt/syfo-oppfolgingsplan-backend` 12. august 2026
fant:

- Hovmester collection `backend` på source-SHA
  `48483bf32c2b6f89c31e7d50e25b5fe6fac45ca2`;
- reusable Hovmester-workflow på `@main`; workflowfilen må fjernes under
  piloten fordi en manuell dispatch fortsatt ville klonet default branch;
- `github_project=navikt/157`, tom `team_repo` og `pr_app_id=2906300`, som alle
  må beholdes i baseline-/rollback-kontrakten;
- syv lokale Hovmester-agenter og 23 lokale, uprefiksede skills;
- eksakt agentkollisjon på `barista` og `kokk`, men ingen skillkollisjon;
- syv instruction-filer og syv template-filer som skal bevares;
- ingen `.github/copilot/settings.json`;
- en aktiv worktree med annet utviklerarbeid, som derfor ikke skal brukes.

En simulert sync fra den eksakte registrerte Hovmester-SHA-en med
`collections=backend` og `exclude=barista,kokk` ga `0 added`, `0 changed`,
`2 removed` og `74 unchanged`. Bare de to kolliderende agentfilene forsvant fra
payloaden, og manifestet ble oppdatert. Dette er et tidsstemplet utgangspunkt,
ikke en erstatning for en ny baseline og postflight på pilotcommitten.
