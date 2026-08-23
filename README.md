# Grillmester 🔥

<p align="center">
  <img src="docs/assets/grillmester-hero.jpg" alt="En retro robotgrillmester ved en kullgrill i et norsk landskap" width="100%">
</p>

Grillmester er et agentteam for utvikling, design og produktarbeid i Nav. Det
leveres for GitHub Copilot og OpenCode, med fire valgbare agenter, tre interne
roller og 42 skills. Tilgang og tillatt bruk styres av Navs gjeldende policy.

## Kom i gang

### Copilot CLI og OpenCode i terminalen

Homebrew-oppføringen aktiveres etter stabil release og reviewet tap-bootstrap. Kommandoen er **ikke tilgjengelig ennå**; bruk Copilot app eller [native Copilot-installasjon](docs/installation.md#alternativ-native-copilot-cli-installasjon-med-automatisk-oppdatering).
Når tapen er live, installeres Grillmester, OpenCode og cplt:

```bash
brew install navikt/tap/grillmester
```

Copilot CLI er en separat klient. Installer den hvis du vil bruke Copilot i
terminalen:

```bash
brew install --cask copilot-cli
```

Start så Grillmester:

```bash
grillmester
```

Første gang velger du **GitHub Copilot CLI** eller **OpenCode** og én av de fire
offentlige agentene. Valget lagres som default; neste gang starter Enter samme
kombinasjon. Bruk `grillmester choose` for å velge på nytt.

Du kan også være eksplisitt:

```bash
grillmester --client copilot --agent grillmester
grillmester --client opencode --agent barista
grillmester doctor
```

Når du bruker `grillmester`, startes begge terminalklientene alltid gjennom
cplt. Launcheren velger ikke provider eller modell. Flagg før `--` går til cplt; flagg
etter `--` går til klienten. En lokal OpenCode-provider på port `1234` startes
slik:

```bash
grillmester --client opencode --agent grillmester --allow-localhost 1234 \
  -- --model lmstudio/your-model
```

Se [terminalinstallasjon og alternativer](docs/installation.md) og
[provideroppsett for OpenCode](docs/opencode.md).

### Oppdatere terminalinstallasjonen

Brew-kanalen oppdaterer ikke automatisk. Kjør `grillmester update` for å hente
en ny reviewet Grillmester- og klientkombinasjon. Native Copilot-installasjoner
kan i stedet følge marketplace med opt-in auto-update.

### Copilot app

Copilot app startes ikke gjennom cplt. Bruk appens native pluginflyt:

1. [Legg til Grillmester-markedsplassen](https://github.com/copilot/app/launch?open=ghapp%3A%2F%2Fplugins%2Fmarketplace%2Fadd%3Fsource%3Dnavikt%252Fgrillmester)
2. [Installer Grillmester](https://github.com/copilot/app/launch?open=ghapp%3A%2F%2Fplugins%2Finstall%3Fsource%3Dgrillmester%2540grillmester)

Lenkene åpner **Settings → Plugins** med ferdig utfylt verdi; ingenting
installeres før du bekrefter. Se [appdetaljer og native
Copilot-alternativer](docs/installation.md#copilot-app).

## Velg agent

| Agent | Bruk når |
| --- | --- |
| **Grillmester** 🔥 | Oppgaven er uklar, viktig eller tverrgående. Grillmester avklarer valg og risiko før en avgrenset løsning implementeres og vurderes. |
| **Barista** ☕ | Målet er tydelig og oppgaven kan løses som vanlig repoarbeid. Barista forstår, implementerer og verifiserer i en lett flyt. |
| **Designer** 🎨 | Du vil utforske brukerflyt, konsepter, Aksel, Visual Companion eller Figma. Designer lager en designleveranse, men implementerer ikke produktkode. |
| **Doctor Who** 🕰️ | Du trenger støtte til discovery, mål, prioritering, workshops, teamhelse, produktfag eller Nav-arkitektur. |

Beskriv ønsket resultat, kontekst og avgrensninger. Agenten laster normalt
riktige skills selv. Kokk, Grill-inspektør og Researcher er interne roller som
brukes ved behov. [Se alle agenter og skills](docs/agents-and-skills.md).

## Støtte og avgrensninger

GitHub Copilot CLI er referanseklienten. Copilot app har egen plugininstallasjon.
Homebrew-pakken støttes bare på macOS; Linux er utenfor pakkens release-løfte.
VS Code er utenfor første onboarding og release-løftet. OpenCode-støtten gjelder
den release-gatede klientkombinasjonen, og hver lokal eller cloudbasert modell
må kvalitetsvalideres separat.
Se [klientstatus og tekniske releasegater](docs/trust-and-client-support.md).

Grillmester kan brukes sammen med `navikt/copilot`. Se hvordan [repo-eid
kontekst, overlapp og eventuelle
kollisjoner](docs/repository-context.md#samspill-med-naviktcopilot) håndteres.

## Dokumentasjon

- **Installere:** [Terminal og Copilot app](docs/installation.md) · [OpenCode og providere](docs/opencode.md)
- **Velge modeller:** [Lokale og cloudbaserte modeller](docs/local-models.md)
- **Bruke agentteamet:** [Agenter og skills](docs/agents-and-skills.md) · [valgfritt MCP-oppsett](docs/mcp-setup.md)
- **Forstå og bidra:** [Repo-kontekst](docs/repository-context.md) · [utvikling](docs/development.md)

Problemer eller forslag? [Opprett et issue](https://github.com/navikt/grillmester/issues/new/choose).
Ikke legg secrets, personopplysninger eller sårbarhetsdetaljer i et offentlig
issue; bruk [private vulnerability reporting](SECURITY.md) for sårbarheter.

Grillmester vedlikeholdes av Team eSyfo for Nav og er tilgjengelig under
[MIT-lisensen](LICENSE). Se [proveniens og tredjepartslisenser](PROVENANCE.md).
