# Grillmester 🔥

<p align="center">
  <img src="docs/assets/grillmester-hero.jpg" alt="En retro robotgrillmester ved en kullgrill i et norsk landskap" width="100%">
</p>

> **Grill antakelsene før de havner i produksjon.**

Grillmester er et agentteam for GitHub Copilot som hjelper Nav-team fra uklar
oppgave til avklart retning, liten implementasjon og verifiserbar levering.
Installer én gang; bruk det på tvers av repoer uten å kopiere agentfiler.

Grillmønsteret bygger på Matt Pococks
[`grill-me`- og `grilling`-skills](https://github.com/mattpocock/skills/tree/2ab958093e83e0ec752e6c1c5932da465bf23e0c/skills/productivity)
og er videreutviklet gjennom pilotering i Nav.

> **Status: POC.** Pakken kan piloteres i Nav nå. Stabil/offentlig promotering
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

### Copilot CLI — POC nå

```bash
copilot plugin marketplace add navikt/grillmester#marketplace
copilot plugin install grillmester@grillmester
copilot plugin list
```

Dette installerer pluginen for Copilot-brukeren på maskinen og gjør den
tilgjengelig i alle repoer. `marketplace` er en flytende POC-kanal: katalogen
kan avanseres, men hver publisert katalog peker på en eksakt plugin-SHA. En
reviewet pluginendring som merges til `main` og passerer publisheren, er dermed
tilgjengelig for eksplisitt innmeldte POC-brukere ved neste trusted
CLI-sesjon. CI, `COPILOT_AUTO_UPDATE=false` og `--no-auto-update` hopper over
den automatiske hentingen.

For å følge POC-kanalen automatisk ved nye CLI-sesjoner må du eksplisitt
aktivere `autoUpdate` i din egen `~/.copilot/settings.json`. Grillmester kan
ikke slå på dette fra pluginmanifestet. Den anbefalte, preview-først
konfigurasjonen og det trygge bootstrap-scriptet
[`scripts/configure_autoupdate.py`](scripts/configure_autoupdate.py) ligger i
[installasjonsguiden](docs/installation.md#anbefalt-personlig-oppsett-med-automatisk-oppdatering).

Start Copilot slik du vanligvis gjør i Nav, åpne `/agent`, og velg
`grillmester:grillmester`.

Når en reviewet kandidat finnes under
[Releases](https://github.com/navikt/grillmester/releases), kan du erstatte
`marketplace` med den eksakte `v<versjon>`-taggen når reproduserbarhet er
viktigere enn automatisk oppdatering. Se
[installasjon og aktivering](docs/installation.md).

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
Nav-arkitektur. Prøv:

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

## Én plugin

`grillmester@grillmester` inneholder hele agentteamet: 7 roller og 44
kuraterte skills for avklaring, implementasjon, review, design, produktarbeid
og relevante Nav-teknologier. Det finnes ingen separat fagpakke å velge eller
holde oppdatert.

Lumi er en ordinær capability i pakken. Alle skills har `grillmester-`-prefiks
for å redusere utilsiktede navnekollisjoner og gjøre opphav synlig. En lokal
eller personlig komponent med samme eksakte ID kan fortsatt skygge
plugin-komponenten.

## Samspill med `navikt/copilot`

Grillmester erstatter ikke Navs øvrige Copilot-oppsett. `navikt/copilot` er i
dag en bred plattform med agents, skills, instructions, MCP Registry,
`nav-pilot`-collections/sync og onboarding som kan anbefale repo-tilpasninger.
Grillmester bidrar med ett sammenhengende agentteam og et kuratert sett med 44
skills. Noen fagområder overlapper med `navikt/copilot`;
prefikset gjør opphavet synlig, og `/grillmester-doctor` kan avdekke semantisk
overlapp før et team bestemmer hva repoet skal bruke.

Repo-lokale komponenter fra `nav-pilot` kan ha høyere presedens enn en plugin,
og to semantisk like skills kan konkurrere selv uten samme ID. Kjør
`/grillmester-doctor` før co-installering. Før stabil lansering bredt i Nav skal
Team Copilot og Grillmester-eierne avtale katalog/onboarding, MCP Registry-ID-er
og eierskap; POC-en er fortsatt en separat, eksplisitt installasjon.

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

## Tillit og tools

Agentinstruksjoner styrer arbeidsmåte; de er ikke en sikkerhetsgrense. De fire
offentlige agentene arver hele toolflaten som klienten tilbyr, slik de piloterte
Hovmester-/Budstikka-agentene gjør. De tre interne rollene har små eksplisitte
toolsett. Navs MCP Registry, klienten, brukerens godkjenninger og enterprise-
policy avgjør hva som faktisk kan kjøres.

Grillmester konfigurerer ikke runtime-isolasjon; i Nav eies dette av det
sentralt forvaltede [`cplt`-oppsettet](https://github.com/navikt/cplt) og
eventuell repo-policy. Se
[tillit, tools og klientstøtte](docs/trust-and-client-support.md) for skillet
mellom arbeidsmåte og teknisk håndheving.

## Hvis noe ikke dukker opp

1. Kjør `copilot plugin list` og start en ny sesjon.
2. Åpne `/agent`; se etter `grillmester:grillmester` eller
   `grillmester:barista`.
3. Sjekk om repoet har en lokal agent med samme ID. Repo-lokalt innhold kan
   skygge pluginagenten.
4. Kjør `/grillmester-doctor` for en read-only kontroll av aktivering,
   instructions og navnekollisjoner.

Mangler Designer Figma-verktøy, skal den tilby konsept/Visual Companion eller
et Figma-klart utkast — aldri late som en Figma-write skjedde.

Fortsatt fast? [Opprett et issue](https://github.com/navikt/grillmester/issues/new/choose)
med klient og versjon, plugin-tag, valgt agent/skill, reproduksjon og scrubbet
diagnostikk. Legg aldri secrets, personopplysninger eller sårbarhetsdetaljer i
et offentlig issue; bruk [private vulnerability reporting](SECURITY.md).

### Oppdater eller rull tilbake personlig installasjon

Med den anbefalte flytende kanalen og `autoUpdate: true` sjekker Copilot CLI
etter en ny Grillmester-versjon ved starten av en trusted CLI-sesjon. CI og en
eksplisitt `COPILOT_AUTO_UPDATE=false`/`--no-auto-update` hopper over dette. Du
kan også oppdatere eksplisitt:

```bash
copilot plugin marketplace update grillmester
copilot plugin update grillmester@grillmester
```

For å pinne eller rulle tilbake til en immutable kandidat:

```bash
copilot plugin uninstall grillmester@grillmester
copilot plugin marketplace remove grillmester
copilot plugin marketplace add navikt/grillmester#NEW_REVIEWED_RELEASE_TAG
copilot plugin install grillmester@grillmester
```

For teamrepo og cloud agent brukes `.github/copilot/settings.json`; personlig
CLI-oppsett ligger i `~/.copilot/settings.json`. Feltene er
`extraKnownMarketplaces` og `enabledPlugins`, mens enterprise kan bruke
`strictKnownMarketplaces`. Repo- og enterprise-settings kan installere eller
aktivere pluginen, men kan ikke slå på CLIs auto-update for en egendefinert
marketplace. Eksakte eksempler og rollback finnes i
[installasjonsguiden](docs/installation.md).

## Dokumentasjon

- [Installere, aktivere, oppdatere og rulle tilbake](docs/installation.md)
- [Agenter, interne roller og skillfamilier](docs/agents-and-skills.md)
- [Repo-eid kontekst, instructions og templates](docs/repository-context.md)
- [Tillit, tools, klientstøtte og releasegater](docs/trust-and-client-support.md)
- [Migrere en eksisterende Hovmester-consumer](docs/consumer-pilot-runbook.md)
- [Publisere immutable releases](docs/release-runbook.md)
- [Utvikle og verifisere pluginen](docs/development.md)
- [Rapportere sårbarheter privat](SECURITY.md)

Grillmester vedlikeholdes av Team eSyfo **for Nav**, etter en lengre pilot i
`syfo-budstikka`. Prosjektet er en kurert POC frem til klient- og releasegatene
er dokumentert grønne. Det er tilgjengelig under [MIT-lisensen](LICENSE);
kildegrunnlag og bildeproveniens finnes i [PROVENANCE.md](PROVENANCE.md) og
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
