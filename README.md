# Grillmester 🔥

<p align="center">
  <img src="docs/assets/grillmester-hero.jpg" alt="En retro robotgrillmester ved en kullgrill i et norsk landskap" width="100%">
</p>

Grillmester er Navs agentteam for GitHub Copilot og OpenCode: fire agenter, tre interne roller og 43 skills. Tilgang og tillatt bruk styres av Navs gjeldende policy.

## Kom i gang

### Copilot CLI og OpenCode i terminalen

Grillmester-formelen er **ikke tilgjengelig ennå**. Installer cplt og én klient,
og kjør checkouten fra consumer-repoet:

```bash
brew install navikt/tap/cplt
brew install opencode
# eller: brew install --cask copilot-cli
cd /path/to/consumer-repo
python3 /absolute/path/to/grillmester/scripts/grillmester.py
python3 /absolute/path/to/grillmester/scripts/grillmester.py doctor
```

[Native GitHub Copilot CLI](docs/installation.md#alternativ-native-copilot-cli-installasjon-med-automatisk-oppdatering) kan i stedet installere pluginen direkte. Etter tap-review blir terminalinstallasjonen:

```bash
brew install navikt/tap/cplt navikt/tap/grillmester
```

Start deretter den installerte launcheren:

```bash
grillmester
```

Launcheren viser klienter fra `PATH`. Alle terminalsesjoner går gjennom cplt; valgt klient versjonssjekkes før lagring. `grillmester choose` bytter. En manglende klient gir installasjonskommando, aldri fallback.

Eksplisitt:

```bash
grillmester --client copilot --agent grillmester
grillmester --client opencode --agent barista
grillmester doctor
```

Standardkommandoen beholder hele agentteamet og klientens vanlige modellregler.
For loopback starter du først en OpenAI-kompatibel modellserver og kjører fra
consumer-repoet:

```bash
cd /path/to/consumer-repo
python3 /absolute/path/to/grillmester/scripts/grillmester.py local setup
python3 /absolute/path/to/grillmester/scripts/grillmester.py local launch  # interaktivt
python3 /absolute/path/to/grillmester/scripts/grillmester.py local run "Fiks den avgrensede oppgaven og kjør testene"  # alternativt
```

`launch` og `run` er alternativer. `run` krever eget, rent worktree. Web/GitHub følger cplt-policy. Uten opt-in sendes ingen støttet `GH_TOKEN`. OpenCode isolerer ambient GitHub-konto; Copilot kan mediere native credential via macOS Keychain. Se [lokale modeller](docs/local-models.md).

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
`1.0.79` og cplt fra testbaselinen. Hver modell må kvalitetsvalideres separat.
Se [klientstatus og releasegater](docs/trust-and-client-support.md).

Grillmester kan brukes sammen med `navikt/copilot`. Se hvordan [repo-eid kontekst,
overlapp og kollisjoner](docs/repository-context.md#samspill-med-naviktcopilot) håndteres.

## Dokumentasjon

- **Installere:** [Terminal og Copilot app](docs/installation.md) · [OpenCode og providere](docs/opencode.md)
- **Velge modeller:** [Lokale og cloudbaserte modeller](docs/local-models.md)
- **Bruke agentteamet:** [Agenter og skills](docs/agents-and-skills.md) · [valgfritt MCP-oppsett](docs/mcp-setup.md)
- **Forstå og bidra:** [Repo-kontekst](docs/repository-context.md) · [utvikling](docs/development.md)

Problemer eller forslag? [Opprett et issue](https://github.com/navikt/grillmester/issues/new/choose). Ikke legg secrets, personopplysninger eller sårbarhetsdetaljer i et offentlig issue; bruk [private vulnerability reporting](SECURITY.md) for sårbarheter.

Grillmester vedlikeholdes av Team eSyfo for Nav og er tilgjengelig under
[MIT-lisensen](LICENSE). Se [proveniens og tredjepartslisenser](PROVENANCE.md).
