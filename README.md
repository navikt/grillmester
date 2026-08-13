# Grillmester 🔥

<p align="center">
  <img src="docs/assets/grillmester-hero.jpg" alt="En retro robotgrillmester ved en kullgrill i et norsk landskap" width="100%">
</p>

> **Grill antakelsene før de havner i produksjon.**

Grillmester er et agentteam for GitHub Copilot som hjelper NAV-team fra uklar
oppgave til avklart retning, liten implementasjon og verifiserbar levering.
Installer én gang; bruk det på tvers av repoer uten å kopiere agentfiler.

> **Status: POC.** Pakken kan piloteres i NAV nå. Stabil/offentlig promotering
> krever fortsatt klient-/MCP-evidens, Team Copilot-avklaring og de dokumenterte
> rettighets-/branding-gatene.

## Grillmester eller Barista?

Dette er valget du vanligvis trenger å ta:

| Start med | Når | Hva som skjer |
| --- | --- | --- |
| **Grillmester** 🔥 | Oppgaven er viktig, uklar, tverrgående eller har reelle produkt-/arkitekturvalg. | Avklarer fakta, antakelser og beslutninger før én avgrenset slice implementeres og reviewes uavhengig. |
| **Barista** ☕ | Oppgaven er liten eller allerede godt spesifisert. | Forstår, implementerer og verifiserer i en lett, solo-first flyt. |

Tommelfingerregel: Hvis du kan forklare ønsket resultat og akseptansekriteriene
på et par minutter, velg Barista. Hvis ikke, velg Grillmester.

## Installer på under ett minutt

### Copilot CLI — reviewet og pinnet

Velg en kandidat fra [Releases](https://github.com/navikt/grillmester/releases)
og bruk taggen i stedet for `REVIEWED_RELEASE_TAG`:

```bash
copilot plugin marketplace add navikt/grillmester#REVIEWED_RELEASE_TAG
copilot plugin install grillmester@grillmester
copilot plugin list
copilot --experimental --sandbox --agent=grillmester:grillmester
```

Dette installerer pluginen for Copilot-brukeren på maskinen og gjør den
tilgjengelig i alle repoer. Taggen pinner en reviewet katalog som igjen pinner
eksakt plugin-SHA. Hvis det ennå ikke finnes en release, bruk
[lokal POC-flyt](docs/installation.md#lokal-poc-og-utvikling) — ikke bytt ut
taggen med `main` og kall det reproduserbart.

### Copilot app — to bekreftelser

1. [Legg til Grillmester-markedsplassen](https://github.com/copilot/app/launch?open=ghapp%3A%2F%2Fplugins%2Fmarketplace%2Fadd%3Fsource%3Dnavikt%252Fgrillmester)
2. [Installer Grillmester](https://github.com/copilot/app/launch?open=ghapp%3A%2F%2Fplugins%2Finstall%3Fsource%3Dgrillmester%2540grillmester)

Lenkene åpner **Settings → Plugins** med verdiene ferdig utfylt. Du må selv
bekrefte begge handlingene. GitHubs App-lenke støtter ikke CLIs `#tag`-form og
følger derfor marketplace-repoets default branch; bruk CLI eller repoaktivering
når eksakt releaseidentitet er et krav. Se
[installasjon og aktivering](docs/installation.md).

## Første prompt

Velg `grillmester:grillmester` med `/agent`, og prøv:

> Kartlegg hva som må avklares før vi endrer denne flyten. Skill mellom fakta,
> antakelser og reelle beslutninger. Ikke implementer før retningen er
> godkjent.

For en liten oppgave velger du `grillmester:barista`:

> Gjør denne valideringsfeilen tydelig for brukeren. Hold endringen liten,
> følg repoets mønstre og kjør relevante tester.

## Fire innganger

### Grillmester 🔥

Bruk ved avklaring, domenemodell, arkitekturvalg, ADR eller risiko. Prøv:

> Vi skal endre en brukerflyt på tvers av to systemer. Grill planen før kode.

Du får avklart retning, synlige beslutninger, én avgrenset implementasjon og
uavhengig review. Ikke velg Grillmester når oppgaven allerede er liten og
ferdigspekket.

### Barista ☕

Bruk til vanlig repoarbeid med tydelig mål og håndterbart scope. Prøv:

> Legg til feltet, oppdater testen og verifiser.

Du får en liten, verifisert diff uten unødvendig orkestrering. Velg Grillmester
i stedet når det finnes uløste produkt- eller arkitekturvalg.

### Designer 🎨

Bruk til designutforsking, Aksel/Figma, brukerflyt eller en konkret
designleveranse. Prøv:

> Utforsk tre tydelig ulike løsninger for denne feilsituasjonen.

Du får en begrunnet designretning, visualisering eller et Figma-klart utkast.
Designer implementerer ikke produktkode.

### Doctor Who 🕰️

Bruk ved mål, prioritering, discovery, workshop, teamhelse, produktfag eller
NAV-arkitektur. Prøv:

> Hva bør vi lære før vi prioriterer dette initiativet?

Du får syntese, alternativer, anbefaling og et konkret neste steg. Velg en
engineering-agent når oppgaven primært er en kodeendring.

Tre interne roller holder leveransen ryddig: **Kokk** implementerer én komplett
vertical slice, **Grill-inspektør** reviewer diff og evidens uavhengig, og
**Researcher** undersøker ett avgrenset faktaspørsmål med kilder. De delegeres
av agentteamet og er ikke ment som startpunkt i agentvelgeren.

[Se hele agent- og skillkartet](docs/agents-and-skills.md).

## Slik jobber teamet

```text
Forstå oppgaven → grill reelle valg → godkjenn retning
    → implementer én vertical slice → verifiser → uavhengig review
```

Flyten skaleres etter oppgaven. Grillmester bruker mer struktur når risiko og
uklarhet krever det; Barista hopper ikke gjennom en tung prosess for en enkel
endring. Skills lastes progressivt når oppgaven matcher, så hele fagbiblioteket
trenger ikke ligge i kontekst samtidig.

## Velg pakke

Marketplace-katalogen har to komponerbare pakker:

| Installer | Innhold | Passer når |
| --- | --- | --- |
| `grillmester@grillmester` | Agentteamet (7 roller) og 34 kuraterte skills for metode, design, produktarbeid og levering — inkludert Aksel, UU og NAV-arkitektur. | Anbefalt start, også når repoet allerede bruker `navikt/copilot`. |
| `grillmester-nav@grillmester` | 10 valgfrie backend-, plattform- og integrasjonsskills som auth, Kafka, Kotlin, Nais, observability, PostgreSQL og Lumi. | Teamet vil ha NAV-fagpakken i tillegg. |

«Full» betyr å installere begge; NAV-pakken er et tillegg til standardpakken,
ikke et selvstendig agentprodukt eller en tredje kopi av agentene:

```bash
copilot plugin install grillmester@grillmester
copilot plugin install grillmester-nav@grillmester
```

Lumi er en ordinær NAV-capability i NAV-pakken, ikke en preview. Alle skills har
`grillmester-`-prefiks for å unngå eksakte navnekollisjoner og gjøre opphav
synlig.

## Samspill med `navikt/copilot`

Grillmester erstatter ikke NAVs øvrige Copilot-oppsett. `navikt/copilot` er i
dag en bred plattform med agents, skills, instructions, MCP Registry,
`nav-pilot`-collections/sync og onboarding som kan anbefale repo-tilpasninger.
Installer Grillmesters standardpakke for agentteamet og den kuraterte
arbeidsflyten. Installer NAV-tillegget bare når du også vil ha Grillmesters
backend-, plattform- og integrasjonsspesialiseringer.

Repo-lokale komponenter fra `nav-pilot` kan ha høyere presedens enn en plugin,
og to semantisk like skills kan konkurrere selv uten samme ID. Kjør
`/grillmester-doctor` før
co-installering. Før stabil NAV-bred lansering skal Team Copilot og Grillmester-
eierne avtale katalog/onboarding, MCP Registry-ID-er og eierskap; POC-en er
fortsatt en separat, eksplisitt installasjon.

Pluginen synker ikke instructions, PR-maler eller issue-maler. Repoet eier
fortsatt:

- `AGENTS.md` og repo-/path-scoped instructions for lokale, stående regler
- korrekte build-, test- og kjørekommandoer
- domeneord, sikkerhetsklassifisering og lokale trust boundaries
- `.github/PULL_REQUEST_TEMPLATE*` og `.github/ISSUE_TEMPLATE/`

Dette unngår drift mellom en sentral kopi og repoets faktiske virkelighet.
Copilot CLI følger eksisterende PR-template ved `/pr create`, og Copilots
issueflyt kan mappe et utkast til repoets issue forms/templates. Se
[repo-eid kontekst og templates](docs/repository-context.md).

## Tillit, tools og sandbox

Agentinstruksjoner styrer arbeidsmåte; de er ikke en sikkerhetsgrense. De fire
offentlige agentene arver hele toolflaten som klienten tilbyr, slik de piloterte
Hovmester-/Budstikka-agentene gjør. De tre interne rollene har små eksplisitte
toolsett. NAVs MCP Registry, klienten, brukerens godkjenninger og enterprise-
policy avgjør hva som faktisk kan kjøres.

For NAV-bruk er sandbox et krav. I Copilot CLI:

```text
/settings experimental on
/sandbox enable
/sandbox
```

Sandbox er fortsatt en eksperimentell CLI-funksjon. Start helst sesjonen med
`copilot --experimental --sandbox ...`; i en allerede startet sesjon må du
først slå på eksperimentelle funksjoner som vist over. Bekreft `sandbox
enabled` i statuslinjen. Kjør deretter `/sandbox` uten argument for å åpne
policyvisningen og kontroller den effektive policyen.
NAV-profilen skal ha `sandbox.allowBypass=false`, deaktivert allow-all/bypass og
aktive, eksplisitte godkjenninger. Sandbox kan ellers fortsatt tillate nettverk,
Git/`gh`, writes i arbeidsrepoet og eksterne MCP-sideeffekter. Pluginen kan ikke
slå på eller håndheve dette for deg. Følg
[runtime-sikkerhetspolicyen](docs/runtime-safety.md) og se
[klient- og releasegatene](docs/trust-and-client-support.md).

## Hvis noe ikke dukker opp

1. Kjør `copilot plugin list` og start en ny sesjon.
2. Åpne `/agent`; se etter `grillmester:grillmester` eller
   `grillmester:barista`.
3. Sjekk om repoet har en lokal agent med samme ID. Repo-lokalt innhold kan
   skygge pluginagenten.
4. Kjør `/grillmester-doctor` for en read-only kontroll av aktivering,
   instructions og navnekollisjoner.

Mangler du en backend-, plattform- eller integrasjonsskill, sjekk at
`grillmester-nav@grillmester` er installert.
Mangler Designer Figma-verktøy, skal den tilby konsept/Visual Companion eller
et Figma-klart utkast — aldri late som en Figma-write skjedde.

Fortsatt fast? [Opprett et issue](https://github.com/navikt/grillmester/issues/new/choose)
med klient og versjon, plugin-tag, valgt agent/skill, reproduksjon og scrubbet
diagnostikk. Legg aldri secrets, personopplysninger eller sårbarhetsdetaljer i
et offentlig issue; bruk [private vulnerability reporting](SECURITY.md).

### Oppdater eller rull tilbake personlig installasjon

```bash
copilot plugin uninstall grillmester-nav@grillmester  # hvis installert
copilot plugin uninstall grillmester@grillmester
copilot plugin marketplace remove grillmester
copilot plugin marketplace add navikt/grillmester#NEW_REVIEWED_RELEASE_TAG
copilot plugin install grillmester@grillmester
copilot plugin install grillmester-nav@grillmester    # hvis ønsket
```

For teamrepo og cloud agent brukes `.github/copilot/settings.json`; personlig
CLI-oppsett ligger i `~/.copilot/settings.json`. Feltene er
`extraKnownMarketplaces` og `enabledPlugins`, mens enterprise kan bruke
`strictKnownMarketplaces`. Eksakte eksempler og rollback finnes i
[installasjonsguiden](docs/installation.md).

## Dokumentasjon

- [Installere, aktivere, oppdatere og rulle tilbake](docs/installation.md)
- [Agenter, interne roller og skillfamilier](docs/agents-and-skills.md)
- [Repo-eid kontekst, instructions og templates](docs/repository-context.md)
- [Påkrevd runtime-sikkerhet og sandbox](docs/runtime-safety.md)
- [Klientstøtte og releasegater](docs/trust-and-client-support.md)
- [Migrere en eksisterende Hovmester-consumer](docs/consumer-pilot-runbook.md)
- [Publisere immutable releases](docs/release-runbook.md)
- [Utvikle og verifisere pluginen](docs/development.md)
- [Rapportere sårbarheter privat](SECURITY.md)

Grillmester vedlikeholdes av Team eSyfo **for NAV**, etter en lengre pilot i
`syfo-budstikka`. Prosjektet er en kurert POC frem til klient- og releasegatene
er dokumentert grønne. Det er tilgjengelig under [MIT-lisensen](LICENSE);
kildegrunnlag og bildeproveniens finnes i [PROVENANCE.md](PROVENANCE.md) og
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
