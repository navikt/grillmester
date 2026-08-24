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
Når tapen er live, installeres Grillmester med cplt som ekstern Homebrew-avhengighet:

```bash
brew install navikt/tap/grillmester
```

Installer OpenCode og/eller GitHub Copilot CLI separat. Grillmester bruker dem
fra `PATH` uten å endre dem:

```bash
brew install opencode
brew install --cask copilot-cli
```

Start så Grillmester:

```bash
grillmester
```

Launcheren viser installerte klienter fra `PATH` uten å starte dem. Alle
terminalsesjoner går alltid gjennom cplt; før lagring versjonssjekkes valgt klient
mot en tom, midlertidig mappe.
`grillmester choose` bytter. En manglende klient gir
installasjonskommando, aldri fallback.

Du kan også være eksplisitt:

```bash
grillmester --client copilot --agent grillmester
grillmester --client opencode --agent barista
grillmester doctor
```

Standardkommandoen beholder hele agentteamet og klientens vanlige modellregler.
For en eksplisitt loopback-modell bruker du den lokale flyten:

```bash
grillmester local setup
grillmester local
grillmester local --client copilot
grillmester local --full --agent grillmester
```

`setup` oppdager klient og modell; focused Barista er default, uten cloud-fallback.
Se [lokale modeller](docs/local-models.md) og [klientoppsett](docs/opencode.md).

### Oppdatere terminalinstallasjonen

Brew-kanalen oppdaterer ikke automatisk. `grillmester update` oppdaterer
Grillmester; OpenCode, Copilot CLI og cplt følger sine egne pakkekanaler. Native
Copilot-installasjoner kan følge marketplace med opt-in auto-update.

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

GitHub Copilot CLI er referanseklienten; Copilot app har egen plugininstallasjon.
Homebrew støttes på macOS. Linux og VS Code er utenfor release-løftet.
Standardlauncheren støtter OpenCode 1.x fra `1.18.20`, Copilot CLI 1.x fra
`1.0.79` og cplt fra testbaselinen. High-assurance-manageren har eksakte pinner. Hver
modell må kvalitetsvalideres separat. Se [klientstatus og releasegater](docs/trust-and-client-support.md).

Grillmester kan brukes sammen med `navikt/copilot`. Se hvordan [repo-eid
kontekst, overlapp og eventuelle
kollisjoner](docs/repository-context.md#samspill-med-naviktcopilot) håndteres.

## Dokumentasjon

- **Installere:** [Terminal og Copilot app](docs/installation.md) · [OpenCode og providere](docs/opencode.md)
- **Velge modeller:** [Lokale og cloudbaserte modeller](docs/local-models.md)
- **Bruke agentteamet:** [Agenter og skills](docs/agents-and-skills.md) · [valgfritt MCP-oppsett](docs/mcp-setup.md)
- **Forstå og bidra:** [Repo-kontekst](docs/repository-context.md) · [utvikling](docs/development.md)

Problemer eller forslag? [Opprett et issue](https://github.com/navikt/grillmester/issues/new/choose). Ikke legg secrets, personopplysninger eller sårbarhetsdetaljer i et offentlig issue; bruk [private vulnerability reporting](SECURITY.md) for sårbarheter.

Grillmester vedlikeholdes av Team eSyfo for Nav og er tilgjengelig under
[MIT-lisensen](LICENSE). Se [proveniens og tredjepartslisenser](PROVENANCE.md).
