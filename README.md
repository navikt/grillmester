# Grillmester 🔥

<p align="center">
  <img src="docs/assets/grillmester-hero.jpg" alt="En retro robotgrillmester ved en kullgrill i et norsk landskap" width="100%">
</p>

Grillmester er Navs plugin for GitHub Copilot: én hovedagent for utvikling, egne innganger for design og produktarbeid, tre interne roller og 44 skills. Tilgang og tillatt bruk styres av Navs gjeldende policy.

## Kom i gang

### Copilot app

Copilot app bruker sin native pluginflyt:

1. [Legg til Grillmester-markedsplassen](https://github.com/copilot/app/launch?open=ghapp%3A%2F%2Fplugins%2Fmarketplace%2Fadd%3Fsource%3Dnavikt%252Fgrillmester)
2. [Installer Grillmester](https://github.com/copilot/app/launch?open=ghapp%3A%2F%2Fplugins%2Finstall%3Fsource%3Dgrillmester%2540grillmester)

Lenkene åpner **Customize → Plugins** med ferdig utfylt verdi; ingenting
installeres før du bekrefter. Oppdater pluginen med **Update** under
**Customize → Plugins**; automatisk oppdatering nedenfor gjelder CLI. Se
[appdetaljer](docs/installation.md#copilot-app). App-lenken følger repoets
default branch; bruk Copilot CLI med en reviewet versjonstagg når pinning er
påkrevd.

Bruk `/app-sandbox-setup` for manuelt sandbox-oppsett i Copilot app på macOS med plan, bekreftelse, verify og rollback.

Kjørende apper vises i Copilot-appens nettleserfane. Designeren peker med
**Pick & Polish** (⌘⇧C) og skriver ønsket i samtalen, og forslag lages i en eid
kopi av appen med ekte komponenter. En ny idé uten app bygges som en liten Aksel-app
på samme måte. Bruk demoer med syntetiske data, fordi sidens tekst, HTML og adresse
går til modellen. Demoer krever Node.js på appens `PATH`. Se
[designflyten](plugin/skills/design-prototype/references/application-opening.md).

### Copilot CLI

Installer Grillmester fra Copilot CLI sin pluginmarkedsplass:

```bash
copilot plugin marketplace add navikt/grillmester#marketplace
copilot plugin install grillmester@grillmester
```

### Automatisk oppdatering i Copilot CLI

Legg dette til i `~/.copilot/settings.json`. Behold eksisterende innstillinger,
og slå sammen feltene hvis de allerede finnes:

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

Copilot sjekker etter pluginoppdateringer ved starten av en ny sesjon i en
mappe du har gitt tillit. Marketplace-kanalen oppdateres bare til gjennomgått
plugininnhold. Automatisk oppdatering må være tillatt globalt; CI,
`--no-auto-update` og `COPILOT_AUTO_UPDATE=false` hindrer oppdateringen.
Se [oppsett og detaljer](docs/installation.md#valgfritt-automatisk-oppdatering-i-copilot-cli)
eller [manuell oppdatering, pinning og rollback](docs/installation.md#oppdatere-og-rulle-tilbake).

## Velg agent

| Agent | Bruk når |
| --- | --- |
| **Grillmester** 🔥 | Undersøker, planlegger, implementerer og verifiserer utviklingsoppgaver i samme samtale. Avklarer vesentlige valg og bruker uavhengig review etter risiko. |
| **Designer** 🎨 | Du vil utforske eller forbedre apper, brukerflyt og konsepter med ekte komponenter. Bruker nettleserfanen eller Figma, og kan implementere når du ber om det. |
| **Doctor Who** 🕰️ | Du trenger støtte til discovery, mål, prioritering, workshops, teamhelse, produktfag eller Nav-arkitektur. |

Beskriv ønsket resultat, kontekst og avgrensninger. Agenten laster normalt
riktige skills selv. Grill-inspektør gir uavhengig review; Researcher og
Perspektiv brukes ved behov. Barista og Kokk er erstattet av Grillmester.
[Se alle agenter og skills](docs/agents-and-skills.md).

## Støtte og avgrensninger

GitHub Copilot CLI er referanseklienten; Copilot app har egen plugininstallasjon.
Linux og VS Code er utenfor release-løftet. Hver modell må kvalitetsvalideres
separat. Se [klientstatus og
releasegater](docs/trust-and-client-support.md).

Grillmester kan brukes sammen med `navikt/copilot`. Se hvordan [repo-eid kontekst,
overlapp og kollisjoner](docs/repository-context.md#samspill-med-naviktcopilot) håndteres.

## Dokumentasjon

- **Installere:** [Pluginoppsett, oppdatering og pinning](docs/installation.md)
- **Bruke agentteamet:** [Agenter og skills](docs/agents-and-skills.md) · [valgfritt MCP-oppsett](docs/mcp-setup.md)
- **Forstå og bidra:** [Repo-kontekst](docs/repository-context.md) · [utvikling](docs/development.md)

Problemer eller forslag? [Opprett et issue](https://github.com/navikt/grillmester/issues/new/choose). Ikke legg secrets, personopplysninger eller sårbarhetsdetaljer i et offentlig issue; bruk [private vulnerability reporting](SECURITY.md) for sårbarheter.

Grillmester vedlikeholdes av Team eSyfo for Nav og er tilgjengelig under
[MIT-lisensen](LICENSE). Se [proveniens og tredjepartslisenser](PROVENANCE.md).

Pågående arbeid: [nav-pilot, OpenCode og lokale modeller](docs/nav-pilot.md).
