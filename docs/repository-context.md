# Repo-eid kontekst, instructions og templates

Grillmester distribuerer felles **metode** gjennom agenter og skills. Det
synker ikke en sentral kopi av instructions, PR-maler eller issue-maler til
consumer-repoer.

Dette er et bevisst skille:

- pluginen eier arbeidsflyt, roller og gjenbrukbar fagmetode
- repoet eier sin stående sannhet og sine samarbeidskontrakter
- deterministiske krav håndheves med kode, CI, rulesets og CODEOWNERS

Prompter og instructions er kontekst, ikke en teknisk sikkerhetsgrense.

## Hva skal ligge hvor?

GitHub skiller mellom stående regler og oppgaveorienterte skills:

| Mekanisme | Bruk til | Eksempler |
| --- | --- | --- |
| `AGENTS.md` | Stående regler som skal deles på tvers av AI-verktøy og agenter. | Build/test-kommandoer, repoarkitektur, domenespråk, sikkerhetsgrenser. |
| `.github/copilot-instructions.md` | Repo-wide regler som bare gjelder GitHub Copilot. | Copilot-spesifikke arbeidsregler eller kontekst. |
| `.github/instructions/**/*.instructions.md` | Regler som bare er sanne for bestemte stier eller filtyper. | Frontendregler i `apps/web/**`, migreringsregler i `db/migrations/**`. |
| Grillmester skills | Oppgaveorientert metode som lastes når den trengs. | Sikkerhetsreview, TDD, API-design, workshopdesign. |
| CI/rulesets/CODEOWNERS | Krav som må håndheves deterministisk. | Tester, formattering, branch protection, obligatorisk review. |

Se GitHubs
[sammenligning av custom instructions, AGENTS.md og skills](https://docs.github.com/en/copilot/concepts/agents/code-review#choosing-between-custom-instructions-agentsmd-and-skills).

## Consumerens minste nyttige kontrakt

Start tynt. Et repo trenger ikke kopiere Grillmester-manualen. Dokumenter bare
det en agent ikke kan utlede sikkert fra repoet:

1. eksakte build-, test-, lint- og kjørekommandoer
2. kanoniske domeneord og språk for varige artefakter, inkludert ADR-er
3. data-/sikkerhetsklassifisering, auth og lokale trust boundaries
4. arkitekturgrenser eller invariants som ikke er synlige i koden
5. regler som bare gjelder bestemte mapper eller filtyper
6. eier og kilde for volatile team-/plattformregler

Ikke skriv inn versionsnumre, kommandoer eller policies som raskt drifter hvis
repoet eller en autoritativ kilde allerede kan gi svaret. Lenker er heller ikke
nok for kritiske regler dersom klienten ikke garantert kan lese målet.

Når lokal kontekst mangler, skal agenten inspisere repoet, spørre eller stoppe
med et tydelig kontekstbehov — ikke finne på kommandoer eller sikkerhetsregler.

## Path-scoped instructions er fortsatt nyttige

Plugin-distribusjon og path-scoped instructions løser forskjellige problemer.
Pluginen er god for versjonert, gjenbrukbar metode på tvers av repoer.
Path-scoped instructions er bedre når en regel bare er sann i en konkret del av
ett repo.

Eksempler:

- bruk Aksel-komponenter i `apps/frontend/**`
- migreringer i `db/migrations/**` skal være bakoverkompatible
- generert kode i `clients/generated/**` skal ikke redigeres manuelt

Ikke flytt slike regler inn i en global skill bare fordi pluginen er enklere å
distribuere. Da mister modellen presis aktivering, og regelen kan bli feil i
andre repoer.

## PR- og issue-templates blir i repoet

Behold `.github/PULL_REQUEST_TEMPLATE*` og `.github/ISSUE_TEMPLATE/` i
consumer-repoet. De er samarbeidskontrakter for både mennesker og verktøy, ikke
en del av Grillmesters runtime. En liten, generell Nav-default kan eventuelt
eies av et offentlig `navikt/.github`; lokale templates overstyrer imidlertid
organisasjonsdefaulten, og issue-template-mapper merges ikke.

En organisasjonsarvet template finnes ikke i consumerens checkout. Verifiser
derfor klientatferden med en unik markør før det loves at CLI eller app følger
en slik default; den dokumenterte GitHub.com-/coding-agentadferden er ikke
automatisk evidens for alle lokale klientflater.

Dette har praktisk verdi i GitHub Copilot:

- Copilot CLI følger repoets eksisterende PR-template når `/pr create`
  genererer tittel og beskrivelse.
- Copilots issueoppretting kan mappe brukerens prompt til repoets issue form
  eller template når den finnes.

Kilder:
[PR-oppretting i Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/manage-pull-requests) og
[issueoppretting med Copilot](https://docs.github.com/en/copilot/how-tos/copilot-on-github/copilot-for-github-tasks/use-copilot-to-create-or-update-issues).

Ikke gjeninnfør en managed byte-sync gjennom pluginen. Når et repo trenger en
lokal variant, bør en fremtidig setup-flyt analysere repoet, vise full diff og
opprette den én gang etter eksplisitt godkjenning. Filen er consumer-eid fra
første commit og oppdateres aldri automatisk fra Grillmester. Obligatoriske
organisasjonskrav hører hjemme i org-policy eller deterministiske gates, ikke i
en mal som 27 repoer forventes å holde byte-lik.

Issue- og PR-malene i selve `navikt/grillmester` gjelder bidrag til pluginen;
de distribueres ikke til consumer-repoer.

## Samspill med `navikt/copilot`

`navikt/copilot` og Grillmester kan brukes sammen. `navikt/copilot` omfatter i
dag agents, skills, instructions, MCP Registry, `nav-pilot`-collections/sync og
en onboardingflate som kan vurdere agent readiness og foreslå repo-kontekst.
De to produktene har ulike, men overlappende roller:

- `navikt/copilot` kan fortsatt levere Navs eksisterende instructions og skills
- `grillmester@grillmester` leverer agentteamet og alle 43 skills i den
  kuraterte arbeidsflyten

Grillmester-skills bruker `grillmester-`-prefiks. Det gjør eksakte kollisjoner
mindre sannsynlige, men semantisk overlapp kan fortsatt finnes. Installer bare
én Grillmester-plugin, og bruk `/grillmester-doctor` til å synliggjøre overlapp
før teamet eventuelt rydder i repo-lokale komponenter.

Før stabil lansering bredt i Nav må eierne avtale om Grillmester skal anbefales
eller katalogføres gjennom `nav-pilot`/onboarding, hvilke MCP Registry-ID-er som
er støttet, og hvem som eier overlappende innhold. Inntil det er avklart
installeres Grillmester separat og eksplisitt — det er ikke en stille del av
den andre synkflyten.

En repo-lokal agent eller skill med samme ID kan ha presedens og skygge
plugininnhold. Unngå slike navn med mindre overstyringen er bevisst og testet.

## Fra Hovmester-sync til plugin

Ikke stopp Hovmester-sync og slett alle lokale customizations i én operasjon.
Et consumer-repo kan ha:

- andre agenter eller skills som ikke finnes i Grillmester
- teamspesifikke collections
- instructions og templates som skal bevares byte-identisk
- en workflow som kan legge gamle kollisjoner tilbake ved neste schedule eller
  manuelle dispatch

Følg [consumer-pilot-runbooken](consumer-pilot-runbook.md). Den binder baseline,
eksakte kollisjoner, tillatt diff og rollback før migreringen.

## `/grillmester-doctor`: sjekk før du legger til mer kontekst

Kjør `/grillmester-doctor` når du eksplisitt vil undersøke oppsettet. Skillen er
read-only og vurderer:

- om riktig plugin og agent faktisk er aktiv
- lokale agent-/skillkollisjoner
- hvilke instructions klientflatene kan se
- om repoet mangler en liten, stående kontrakt
- om en regel heller bør være CI/ruleset enn prompttekst

`/grillmester-doctor` synker eller oppretter ikke filer. Et forslag blir først en endring i en
separat, godkjent oppgave.

## Videre

- [Installer og aktiver riktig scope](installation.md)
- [Velg agent og skillfamilie](agents-and-skills.md)
- [Forstå trust-, tool- og klientgrensene](trust-and-client-support.md)
