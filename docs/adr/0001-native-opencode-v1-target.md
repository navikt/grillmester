---
status: accepted
date: 2026-08-21
---

# Generer et eget, native OpenCode 1-target

Installasjons- og aktiveringsdelen er supersedert av
[ADR 0002](0002-install-and-launch-opencode-bundles.md) og deretter
[ADR 0003](0003-one-terminal-entrypoint-through-cplt.md). Standardflytens
klienteierskap og kompatibilitetsgrense er videre supersedert av
[ADR 0004](0004-use-user-installed-terminal-clients.md), og den upubliserte
lifecycle-manageren fra ADR 0002 er fjernet av
[ADR 0007](0007-remove-the-lifecycle-manager.md). Beslutningen om et generert
native target gjelder fortsatt; manager-, profil- og stagingbeskrivelsene gjør
ikke det.

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
opprinnelig eksplisitt aktivering fra en reviewet checkout. Normalflyten er nå
den checksummede terminalbundle-en og `grillmester`-launcheren fra ADR 0003 og
0004, med en brukerinstallert OpenCode-klient gjennom cplt. Checkout-binding er
bare en utviklingsvei; ADR 0007 fjernet manageren, private klientkopier,
runtimeprofiler og read-only staging.

Direkte targetbinding laster OpenCodes vanlige globale og prosjektlokale
configkilder. Et likt agent-, command- eller skill-ID kan da bli skygget og må
undersøkes som en kollisjon, ikke som en stille extension-mekanisme. Den
eksplisitte local-launcheren fra ADR 0006 isolerer klient-/XDG-state og avviser
kjente ambientkomponenter, mens cplt eier runtimegrensen. Se OpenCodes
[config precedence](https://opencode.ai/docs/config#custom-directory).

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

1. støtter OpenCode 1.x fra `1.18.20`; eksakt `1.18.20` forblir reproduserbart
   release-testinput, mens kompatible nyere 1.x ikke er runtimepinnet
2. kan kjøre en ikke-blokkerende kompatibilitetssmoke mot V2-beta
3. lager først et native `opencode-v2`-target hvis betaforskjeller faktisk
   krever det etter at kontraktene stabiliseres

## Konsekvenser

- Én innholdskilde og deterministiske target gir mindre semantisk drift enn
  manuell kopiering eller to håndredigerte produkter.
- Modellvalg blir en runtimebeslutning i OpenCode, ikke en innholdsrelease.
- Sluttbrukeren installerer den publiserte, deterministiske terminalbundle-en
  med dens detached checksum gjennom Homebrew. Launcheren binder det utpakkede
  targetet og starter den brukerinstallerte OpenCode-klienten gjennom cplt.
- Endringer i canonical innhold må vurderes mot begge klienters validatorer og
  live smoke.
- Release-taggen peker på en catalog-only commit, mens GitHub-releasen
  publiserer en separat, source-SHA-bundet terminalbundle for både OpenCode- og
  Copilot CLI-payloaden. Det er et installasjonsartefakt, i motsetning til
  taggens automatisk genererte source-arkiv.

## Forkastede alternativer

- **Gjør alt til `AGENTS.md`:** blander stående repo-sannhet med valgbare
  roller og oppgaveorienterte skills, og mister native permissions/delegering.
- **Bruk Copilot-frontmatter direkte i OpenCode:** filene kan parses, men
  ukjente felt og feil tool-/agentnavn gir stille semantisk tap.
- **Synk targetet inn i consumer-repoer:** innfører et ekstra eierskap og en
  konfliktfylt fillivssyklus. Launcheren binder i stedet targetet fra den
  source-SHA-bundne terminalbundle-en uten å kopiere det inn i consumeren.
- **Bygg en OpenCode-plugin nå:** er unødvendig for agents/commands/skills, og
  V2-plugin-API-et er fortsatt beta og inkompatibelt med V1.
- **Pin én lokal modell i targetet:** gjør kvalitet, maskinkrav og provider til
  en Grillmester-releasebeslutning og blokkerer reell valgfrihet.
