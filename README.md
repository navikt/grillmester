# Grillmester 🔥

<p align="center">
  <img src="docs/assets/grillmester-hero.jpg" alt="En retro robotgrillmester ved en kullgrill i et norsk landskap" width="100%">
</p>

Grillmester er Navs agentteam for GitHub Copilot: fire agenter, fire interne roller og 44 skills, samlet i én plugin. Tilgang og tillatt bruk styres av Navs gjeldende policy.

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

Designverksted krever vanlig Node.js på appens `PATH`; utvidelsen støtter
Node.js 18 eller nyere, og gjeldende LTS anbefales. Prosjektlagrede designrom
støttes bare på Unix-verter som macOS og Linux. Forhåndsvisningen bruker en
privat lokal loopback-server. Se [forutsetninger](docs/installation.md#før-du-begynner).

Designverksted samler **Appen nå**, innspill og **Forslag** i samme canvas
ved samtalen. Bruk lokale demoer med syntetiske data; forslag kan bestilles
direkte. Forslaget kan være en HTML-skisse eller en avtalt separat appkopi.
Appinnspill er midlertidige som standard. Avtalt lagring bevarer arbeidet,
uten å endre appkode. Et lukket appverksted åpnes som en ny instans.
Nativeflyten er prøvd i Copilot app på macOS; se
[støtteomfang og leveringsporter](docs/testing/designverksted-release-readiness.md)
og [arbeidsflyten](plugin/skills/design-prototype/references/design-workspace.md#running-application).

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
| **Grillmester** 🔥 | Anbefalt for utviklingsoppgaver. Går rett videre når retningen er avklart, og avklarer valg og risiko når det trengs. Leverer en verifisert endring. |
| **Barista** ☕ | Målet er tydelig og du ønsker eksplisitt soloarbeid. Forstår, implementerer og verifiserer i samme samtale, også når oppgaven er større. |
| **Designer** 🎨 | Du vil utforske eller forbedre skisser, brukerflyt og konsepter. Bruker tilgjengelig canvas, nettleser eller Figma, og kan implementere når du ber om det. |
| **Doctor Who** 🕰️ | Du trenger støtte til discovery, mål, prioritering, workshops, teamhelse, produktfag eller Nav-arkitektur. |

Beskriv ønsket resultat, kontekst og avgrensninger. Agenten laster normalt
riktige skills selv. Kokk, Grill-inspektør, Researcher og Perspektiv er interne roller som
brukes ved behov. [Se alle agenter og skills](docs/agents-and-skills.md).

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
