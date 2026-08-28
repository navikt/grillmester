# Grillmester 🔥

<p align="center">
  <img src="docs/assets/grillmester-hero.jpg" alt="En retro robotgrillmester ved en kullgrill i et norsk landskap" width="100%">
</p>

Grillmester er Navs agentteam for GitHub Copilot og OpenCode: fire agenter, tre interne roller og 43 skills. Tilgang og tillatt bruk styres av Navs gjeldende policy.

## Kom i gang

### Copilot CLI — anbefalt nå

Installer Grillmester fra Copilot CLI sin pluginmarkedsplass:

```bash
copilot plugin marketplace add navikt/grillmester#marketplace
copilot plugin install grillmester@grillmester
```

Start Copilot som vanlig, kjør `/agent`, og velg
`grillmester:grillmester`. Marketplace-kanalen oppdateres bare til gjennomgått
plugininnhold. Se [oppdatering,
pinning og rollback](docs/installation.md#oppdatere-og-rulle-tilbake).

### Copilot app

Copilot app bruker sin native pluginflyt:

1. [Legg til Grillmester-markedsplassen](https://github.com/copilot/app/launch?open=ghapp%3A%2F%2Fplugins%2Fmarketplace%2Fadd%3Fsource%3Dnavikt%252Fgrillmester)
2. [Installer Grillmester](https://github.com/copilot/app/launch?open=ghapp%3A%2F%2Fplugins%2Finstall%3Fsource%3Dgrillmester%2540grillmester)

Lenkene åpner **Settings → Plugins** med ferdig utfylt verdi; ingenting
installeres før du bekrefter. Appen startes ikke gjennom cplt. Se
[appdetaljer](docs/installation.md#copilot-app). App-lenken følger repoets
default branch; bruk Copilot CLI med en reviewet versjonstagg når pinning er
påkrevd.

### OpenCode og lokale modeller — pilot fra checkout

OpenCode laster ikke Copilot-plugins. Homebrew-kanalen for Grillmester er ikke
aktivert; OpenCode og lokale modeller kan foreløpig piloteres fra en checkout.
Videre terminaldistribusjon samordnes med nav-pilot. Installer cplt og ønsket
klient:

```bash
brew install navikt/tap/cplt opencode
# eller for Copilot CLI: brew install --cask copilot-cli
```

Du trenger en lokal checkout av `navikt/grillmester`. Den er pilotinput, ikke en
installert eller immutable release. Fra repoet du vil arbeide i:

```bash
cd /path/to/consumer-repo
python3 /absolute/path/to/grillmester/scripts/grillmester.py doctor
python3 /absolute/path/to/grillmester/scripts/grillmester.py --client opencode --agent barista
```

For en lokal modell starter du først en OpenAI-kompatibel modellserver på
loopback og kjører:

```bash
python3 /absolute/path/to/grillmester/scripts/grillmester.py local setup --client opencode
python3 /absolute/path/to/grillmester/scripts/grillmester.py local doctor
python3 /absolute/path/to/grillmester/scripts/grillmester.py local launch
```

Launcheren lager isolert OpenCode-config og kjører terminalsesjonen gjennom
cplt. Se [OpenCode-guiden](docs/opencode.md) og [guiden for lokale
modeller](docs/local-models.md).

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
OpenCode og lokale modeller er foreløpig en checkout-pilot på macOS. Linux og
VS Code er utenfor release-løftet. Checkout-launcheren støtter OpenCode 1.x fra
`1.18.20`, Copilot CLI 1.x fra `1.0.79` og cplt fra testbaselinen. Hver modell
må kvalitetsvalideres separat. Se [klientstatus og
releasegater](docs/trust-and-client-support.md).

Grillmester kan brukes sammen med `navikt/copilot`. Se hvordan [repo-eid kontekst,
overlapp og kollisjoner](docs/repository-context.md#samspill-med-naviktcopilot) håndteres.

## Dokumentasjon

- **Installere:** [Copilot og terminalpilot](docs/installation.md) · [OpenCode og providere](docs/opencode.md)
- **Velge modeller:** [Lokale og cloudbaserte modeller](docs/local-models.md)
- **Bruke agentteamet:** [Agenter og skills](docs/agents-and-skills.md) · [valgfritt MCP-oppsett](docs/mcp-setup.md)
- **Forstå og bidra:** [Repo-kontekst](docs/repository-context.md) · [utvikling](docs/development.md)

Problemer eller forslag? [Opprett et issue](https://github.com/navikt/grillmester/issues/new/choose). Ikke legg secrets, personopplysninger eller sårbarhetsdetaljer i et offentlig issue; bruk [private vulnerability reporting](SECURITY.md) for sårbarheter.

Grillmester vedlikeholdes av Team eSyfo for Nav og er tilgjengelig under
[MIT-lisensen](LICENSE). Se [proveniens og tredjepartslisenser](PROVENANCE.md).
