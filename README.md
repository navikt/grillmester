# Grillmester 🔥

<p align="center">
  <img src="docs/assets/grillmester-hero.jpg" alt="En retro robotgrillmester ved en kullgrill i et norsk landskap" width="100%">
</p>

Grillmester er en GitHub Copilot-plugin med agenter og skills for utvikling,
design og produktarbeid i Nav.

## Agentene

Velg agent ut fra hva du skal gjøre:

| Agent | Bruk når |
| --- | --- |
| **Grillmester** 🔥 | Oppgaven er uklar, viktig eller tverrgående. Grillmester avklarer valg og risiko før en avgrenset løsning implementeres og vurderes. |
| **Barista** ☕ | Målet er tydelig og oppgaven kan løses som vanlig repoarbeid. Barista forstår, implementerer og verifiserer i en lett flyt. |
| **Designer** 🎨 | Du vil utforske brukerflyt, konsepter, Aksel, Visual Companion eller Figma. Designer utforsker alternativer og lager en designleveranse, men implementerer ikke produktkode. |
| **Doctor Who** 🕰️ | Du trenger støtte til discovery, mål, prioritering, workshops, teamhelse, produktfag eller Nav-arkitektur. |

Kokk, Grill-inspektør og Researcher er interne roller som agentene bruker ved
behov. [Se alle agenter og skills](docs/agents-and-skills.md).

Designer har mest nytte av Aksel MCP og Figma MCP. Playwright MCP er valgfritt
for nettleserinspeksjon. Se [anbefalt MCP-oppsett](docs/mcp-setup.md).

## Installer

Kjør dette én gang:

```bash
copilot plugin marketplace add navikt/grillmester#marketplace
copilot plugin install grillmester@grillmester
```

Start en ny Copilot-sesjon, åpne `/agent`, og velg en agent under
`grillmester`.

### Automatisk oppdatering

Legg Grillmester til i `~/.copilot/settings.json`. Behold eventuelle andre
innstillinger i filen:

```json
{
  "extraKnownMarketplaces": {
    "grillmester": {
      "source": {
        "source": "github",
        "repo": "navikt/grillmester",
        "ref": "marketplace"
      },
      "autoUpdate": true
    }
  },
  "enabledPlugins": {
    "grillmester@grillmester": true
  }
}
```

Copilot CLI sjekker da etter nye versjoner når en ny sesjon starter. Se
[installasjonsguiden](docs/installation.md) for manuell oppdatering, fast
versjon, Copilot-appen og aktivering i et teamrepo.

## Bruk

Velg agent med `/agent`, og beskriv ønsket resultat, relevant kontekst og
eventuelle avgrensninger. Du trenger vanligvis ikke velge skills selv; agenten
laster dem ved behov.

Eksempel med Grillmester:

> Kartlegg hva som må avklares før vi endrer denne flyten. Skill mellom fakta,
> antakelser og reelle beslutninger. Ikke implementer før retningen er
> godkjent.

Eksempel med Barista:

> Gjør denne valideringsfeilen tydelig for brukeren. Hold endringen liten, følg
> repoets mønstre og kjør relevante tester.

## Samspill med `navikt/copilot`

Noen skills overlapper faglig med `navikt/copilot`, men har
`grillmester-`-prefiks og kan installeres side om side. Kjør
`/grillmester-doctor` for å kontrollere overlapp og lokale kollisjoner.
Repoets `AGENTS.md`, instructions og PR-/issue-maler beholdes som før.

## Hvis agentene ikke dukker opp

1. Kjør `copilot plugin list`.
2. Start en ny Copilot-sesjon og åpne `/agent`.
3. Kjør `/grillmester-doctor`.

Fortsatt problemer? [Opprett et issue](https://github.com/navikt/grillmester/issues/new/choose).
Ikke legg secrets, personopplysninger eller sårbarhetsdetaljer i et offentlig
issue; bruk [private vulnerability reporting](SECURITY.md) for sårbarheter.

## Mer dokumentasjon

- [Installere, oppdatere og aktivere](docs/installation.md)
- [Agenter og skills](docs/agents-and-skills.md)
- [Anbefalt MCP-oppsett](docs/mcp-setup.md)
- [Repo-eid kontekst, instructions og templates](docs/repository-context.md)
- [Utvikling og bidrag](docs/development.md)

Grillmester vedlikeholdes av Team eSyfo for Nav og er tilgjengelig under
[MIT-lisensen](LICENSE). Grillmønsteret bygger på Matt Pococks
[`grill-me`- og `grilling`-skills](https://github.com/mattpocock/skills/tree/2ab958093e83e0ec752e6c1c5932da465bf23e0c/skills/productivity).
Se [proveniens og tredjepartslisenser](PROVENANCE.md).
