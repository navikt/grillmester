# ADR 0001: Generer et eget, native OpenCode 1-target

- **Status:** Akseptert; installasjon og aktivering er supersedert av
  [ADR 0002](0002-install-and-launch-opencode-bundles.md)
- **Dato:** 2026-08-21

## Kontekst

Grillmester har én reviewet GitHub Copilot-plugin i `plugin/`. OpenCode kan
lese Agent Skills direkte, men Copilot- og OpenCode-agentprofiler bruker ulike
felt, toolnavn, delegerings-ID-er og permission-modeller. `AGENTS.md` løser
repo-instruksjoner på tvers av klienter; den er ikke et universelt format for
agentprofiler, skills eller slash commands.

Vi trenger hele Grillmester-flaten i OpenCode 1: fire offentlige innganger, tre
interne roller, alle skills, eksplisitte slash-innganger, native delegering og
native permissions. Første release-gatede klientversjon er `1.18.20`;
kompatibilitet med andre OpenCode 1-versjoner skal ikke antas. Samtidig skal
consumer-repoer eie sin egen kontekst, og brukeren skal kunne velge lokal eller
ekstern modell uten å endre Grillmester-innholdet.

OpenCode 2 er en separat beta. Oppstrøms sier at støttede V1-agentfiler,
commands og skills skal være kompatible, men V2 har en ny permissionmodell og
nye plugin-/server-API-er. Betaen er derfor ikke en stabil målplattform for
denne beslutningen.

## Beslutning

`plugin/` forblir reviewet kildemateriale. Et deterministisk bygg genererer og
committer et eget target i `targets/opencode-v1/` med:

- syv native agentfiler i `agents/`; offentlige roller er `primary`, interne
  roller er skjulte `subagent`-er
- 42 native `SKILL.md`-trær i `skills/`, inkludert relative scripts,
  referanser og assets
- 42 native command-wrappere i `commands/` som beholder den eksplisitte
  `/grillmester-*`-opplevelsen og sender argumenter videre til riktig skill
- en minimal `opencode.json` med schemareferanse, men uten valg av provider,
  modell, MCP-server, credentials eller standardagent
- eksplisitte, reviewede transformasjoner av Copilot-felter, toolnavn,
  delegerings-ID-er og klientspesifikk tekst

Generert innhold skal aldri håndredigeres. Validator og generatorens
`--check`-modus skal avvise drift, manglende filer, ugyldige kryssreferanser og
rester av Copilot-only runtimekontrakter.

OpenCode-agentene har ingen modellpin. En primary agent bruker sessionens eller
brukerens valgte modell, og en subagent arver modellen til primary-agenten som
delegerte oppgaven. Dette følger OpenCodes dokumenterte
[modelloppløsning](https://opencode.ai/docs/agents#model) og gjør samme target
brukbart med både lokale og tillatte eksterne providers.

Targetet ligger bevisst utenfor en consumers `.opencode/`. Denne ADR-en valgte
opprinnelig eksplisitt aktivering fra en reviewet checkout. Det er ikke lenger
repositoryets managed/high-assurance installasjons- eller launchflyt: ADR 0002
erstatter den med en checksummet release-`tar.gz`, manifestverifisert
installasjon og read-only stage. Native `cplt --agent opencode` er den normale
brede kompatibilitetsveien; ADR 0002-manageren er valgfri hardening. `--direct`
gjennom manageren er et eksplisitt opt-out fra dens cplt-kontrakt.

Native unmanaged OpenCode/cplt laster targetets custom config directory sammen
med vanlige globale og prosjektlokale configkilder. Et likt agent-, command-
eller skill-ID kan da bli skygget og må undersøkes som en kollisjon, ikke som en
stille extension-mekanisme. ADR 0002-manageren setter derimot
`OPENCODE_DISABLE_PROJECT_CONFIG`, isolerer XDG-config og rekonstruerer bare
auditerte project-instructions/permission-denies og eksplisitt valgte providers.
Se OpenCodes [config precedence](https://opencode.ai/docs/config#custom-directory).

Grillmester distribuerer ikke `AGENTS.md`, provideroppsett eller en kopi inn i
consumer-repoet. `AGENTS.md` forblir consumerens stående repo-kontrakt.
Provider, modell, credentials, MCP og strengere organisasjonspolicy eies av
bruker/organisasjon. Targetet er instruksjon og minste capability-policy, ikke
en sikkerhetssandkasse.

## Hva «full OpenCode-støtte» betyr

Full støtte betyr dekning av den avtalte Grillmester-flaten i den release-gatede
OpenCode 1.18.20-klienten:
agentvalg, intern delegering, progressive skills, eksplisitte slash commands,
permissions og modellnøytral kjøring. Det betyr ikke at Copilots marketplace,
Navs MCP-oppsett eller GitHub-spesifikke capabilities finnes automatisk i
OpenCode. En capability som mangler i runtime skal fortsatt gi en eksplisitt
fallback eller `NEEDS_CONTEXT`, aldri et falskt suksesskrav.

Dette er heller ikke et løfte om modellkvalitetsparitet med GitHub Copilot.
Provider, modell, kvantisering og contextprofil må valideres separat.

Støtten regnes ikke som stabil release-evidens før det genererte targetet fra
en immutable source-SHA er kjørt gjennom discovery-, permission-,
delegerings- og write/deny-smoke i OpenCode 1.18.20.

## OpenCode 2-grense

OpenCode 2.0 er beta og installeres side om side som `opencode2`. Oppstrøms
lover V1-kompatibilitet for støttede agent-, command- og skillfiler, men
permissionnavn og native configform er endret, og V1-plugins virker ikke i V2.
Grillmester bruker ingen OpenCode-plugin, så targetet har en god forventet
migreringsbane, men dette er ikke verifisert full V2-støtte. Se OpenCodes
[V1-migreringsguide](https://opencode.ai/v2/docs/migrate-v1) og
[betaavgrensning](https://opencode.ai/v2/docs).

Vi gjør derfor følgende:

1. støtter og release-gater OpenCode 1.18.20; en versjonsoppgradering krever
   samme gate på nytt
2. kan kjøre en ikke-blokkerende kompatibilitetssmoke mot V2-beta
3. lager først et native `opencode-v2`-target hvis betaforskjeller faktisk
   krever det etter at kontraktene stabiliseres

## Konsekvenser

- Én innholdskilde og deterministiske target gir mindre semantisk drift enn
  manuell kopiering eller to håndredigerte produkter.
- Modellvalg blir en runtimebeslutning i OpenCode, ikke en innholdsrelease.
- Sluttbrukeren henter den publiserte, deterministiske OpenCode-bundle-en med
  dens detached checksum. Native cplt binder det utpakkede targetet direkte;
  bare brukere som velger high-assurance-livssyklusen installerer den gjennom
  manageren som ADR 0002 beskriver.
- Endringer i canonical innhold må vurderes mot begge klienters validatorer og
  live smoke.
- Release-taggen peker på en catalog-only commit, men GitHub-releasen publiserer
  en separat, source-SHA-bundet OpenCode-asset. OpenCode-brukere skal bruke
  denne asseten og dens detached checksum, ikke taggens source-arkiv.

## Forkastede alternativer

- **Gjør alt til `AGENTS.md`:** blander stående repo-sannhet med valgbare
  roller og oppgaveorienterte skills, og mister native permissions/delegering.
- **Bruk Copilot-frontmatter direkte i OpenCode:** filene kan parses, men
  ukjente felt og feil tool-/agentnavn gir stille semantisk tap.
- **Synk targetet inn i consumer-repoer:** innfører et ekstra eierskap og en
  konfliktfylt fil-livssyklus. ADR 0002 holder i stedet en
  manifestverifisert, read-only runtime-stage utenfor consumeren og source-
  checkouten.
- **Bygg en OpenCode-plugin nå:** er unødvendig for agents/commands/skills, og
  V2-plugin-API-et er fortsatt beta og inkompatibelt med V1.
- **Pin én lokal modell i targetet:** gjør kvalitet, maskinkrav og provider til
  en Grillmester-releasebeslutning og blokkerer reell valgfrihet.
