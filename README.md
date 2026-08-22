# Grillmester 🔥

<p align="center">
  <img src="docs/assets/grillmester-hero.jpg" alt="En retro robotgrillmester ved en kullgrill i et norsk landskap" width="100%">
</p>

Grillmester leverer native agenter og skills for GitHub Copilot og den release-
gatede OpenCode-versjonen 1.18.20, for utvikling, design og produktarbeid i Nav.
Tilgang og tillatt bruk styres av Navs gjeldende policy.

## Agentene

Velg agent ut fra hva du skal gjøre:

| Agent | Bruk når |
| --- | --- |
| **Grillmester** 🔥 | Oppgaven er uklar, viktig eller tverrgående. Grillmester avklarer valg og risiko før en avgrenset løsning implementeres og vurderes. |
| **Barista** ☕ | Målet er tydelig og oppgaven kan løses som vanlig repoarbeid. Barista forstår, implementerer og verifiserer i en lett flyt. |
| **Designer** 🎨 | Du vil utforske brukerflyt, konsepter, Aksel, Visual Companion eller Figma. Designer utforsker alternativer og lager en designleveranse, men implementerer ikke produktkode. |
| **Doctor Who** 🕰️ | Du trenger støtte til discovery, mål, prioritering, workshops, teamhelse, produktfag eller Nav-arkitektur. |

Kokk, Grill-inspektør og Researcher er interne roller. [Se alle agenter og
skills](docs/agents-and-skills.md), eller aktiver Designers
[valgfrie verktøy med valgfritt MCP-oppsett](docs/mcp-setup.md).

## Start med OpenCode

Denne flaten krever ikke Copilot: cplt støtter OpenCode direkte out of the box,
og Grillmester legger bare til config-dir-bindingen fra checkout eller release-bundle:

```bash
GRILLMESTER_ROOT=/absolute/path/to/checkout-or-extracted-bundle
CONFIG_DIR="$GRILLMESTER_ROOT/targets/opencode-v1"
cd /path/to/consumer-repo
OPENCODE_CONFIG_DIR="$CONFIG_DIR" \
  cplt --agent opencode --project-dir "$PWD" \
    --allow-read "$CONFIG_DIR" --pass-env OPENCODE_CONFIG_DIR \
    -- --agent grillmester
```

Se [native quick-start med lokale og cloudbaserte modeller](docs/opencode.md#native-cplt-kom-raskt-i-gang).
For de fleste stopper oppsettet her. Release-manageren er en valgfri assurance-profil
– ikke et cplt-krav eller en forhåndsgodkjent Nav-standard – og krever
Python `3.11`, pinnede klienter og en checksumverifisert bundle.

## Installer med Copilot

Kjør dette én gang:

```bash
copilot plugin marketplace add navikt/grillmester#marketplace
copilot plugin install grillmester@grillmester
```

Start en ny Copilot-sesjon, åpne `/agent`, og velg en agent under
`grillmester`.

### Valgfri automatisk oppdatering i Copilot CLI

Legg dette til i `~/.copilot/settings.json`, uten å fjerne andre innstillinger:

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

## Klientstatus

- **Copilot CLI:** Referanseklient med valgfri auto-oppdatering.
- **Copilot app:** Oppdater en installert plugin manuelt med **Update**.
- **VS Code:** Egen oppdateringsmekanisme; custom marketplace er ikke verifisert.
- **OpenCode 1.18.20 + pinnet cplt:** Native, modellnøytralt target. Modeller
  kvalitetsvalideres separat.

Se [installasjonsguiden](docs/installation.md) for manuell oppdatering, fast
versjon, Copilot-appen og aktivering i et teamrepo.

## Bruk

I Copilot velger du `/agent`. I OpenCode bytter du agent med **Tab**, eller
starter med `--agent grillmester`. Beskriv resultat og avgrensninger; agenten
laster skills ved behov.

## Samspill med `navikt/copilot`

Skill- og command-ID-er har `grillmester-`-prefiks. Agent-ID-ene er bevart og
kan kollidere; native OpenCode kan merge nav-pilot-eksport, mens manager-modus
isolerer den. Se [den eksakte grensen](docs/opencode.md#hva-launcheren-faktisk-gjør).

## Hvis agentene ikke dukker opp

I Copilot: kjør `copilot plugin list`, start på nytt og prøv `/grillmester-doctor`.
I OpenCode: bekreft `OPENCODE_CONFIG_DIR`, start på nytt og kjør
`opencode agent list` eller velg agent med **Tab**.

Fortsatt problemer? [Opprett et issue](https://github.com/navikt/grillmester/issues/new/choose).
Ikke legg secrets, personopplysninger eller sårbarhetsdetaljer i et offentlig
issue; bruk [private vulnerability reporting](SECURITY.md) for sårbarheter.

## Mer dokumentasjon

- [Installasjon](docs/installation.md), [agenter og skills](docs/agents-and-skills.md)
- [OpenCode](docs/opencode.md), [lokale modeller](docs/local-models.md), [utvikling](docs/development.md)

Grillmester vedlikeholdes av Team eSyfo for Nav og er tilgjengelig under
[MIT-lisensen](LICENSE). Grillmønsteret bygger på Matt Pococks
[`grill-me`- og `grilling`-skills](https://github.com/mattpocock/skills/tree/2ab958093e83e0ec752e6c1c5932da465bf23e0c/skills/productivity). Se [proveniens og tredjepartslisenser](PROVENANCE.md).
