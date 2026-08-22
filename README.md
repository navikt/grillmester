# Grillmester 🔥

<p align="center">
  <img src="docs/assets/grillmester-hero.jpg" alt="En retro robotgrillmester ved en kullgrill i et norsk landskap" width="100%">
</p>

Grillmester er et agentteam for utvikling, design og produktarbeid i Nav. Det
leveres som plugin for GitHub Copilot og som et eget target for OpenCode, med
fire agenter du kan velge, tre interne roller og 42 skills. Tilgang og tillatt
bruk styres av Navs gjeldende policy.

## Kom i gang

Velg klienten du allerede bruker. Begge gir tilgang til det samme agentteamet
og de samme arbeidsmetodene.

### GitHub Copilot

**Installer:**

```bash
copilot plugin marketplace add navikt/grillmester#marketplace
copilot plugin install grillmester@grillmester
```

**Start:** Åpne en ny Copilot-sesjon, bruk `/agent`, og velg
`grillmester:grillmester` eller en av de andre Grillmester-agentene.

Se [installasjonsguiden](docs/installation.md) for automatisk oppdatering,
Copilot app, fast versjon og aktivering i et teamrepo.

### OpenCode via cplt

**Forutsetninger:** Installer OpenCode `1.18.20` og cplt
`2026.08.17-062831-1008a92` som beskrevet i
[klientguiden](docs/opencode.md#installer-eksakte-klienter).

**Hent Grillmester:** Last ned, verifiser og pakk ut OpenCode-bundle-en fra en
reviewet [Grillmester-release](https://github.com/navikt/grillmester/releases).
Bruk en release som inneholder både `tar.gz`- og `.sha256`-asseten, og følg
[verifiseringsstegene](docs/opencode.md#hent-og-verifiser-en-grillmester-bundle).

**Velg modell:** For lokale og cloudbaserte providere bruker du det tilhørende
oppsettet og startkommandoen i
[providerguiden](docs/opencode.md#native-cplt-kom-raskt-i-gang). De legger til
port- eller credential-tilgangen cplt trenger. OpenCodes GitHub Copilot-provider
kobles i stedet til med `/connect` etter oppstart.

**Start med GitHub Copilot-provider:** Start OpenCode gjennom cplt med den
utpakkede Grillmester-pakken, og bruk deretter `/connect` i OpenCode:

```bash
GRILLMESTER_ROOT=/absolute/path/to/extracted/grillmester-opencode-v1
CONFIG_DIR="$GRILLMESTER_ROOT/targets/opencode-v1"
cd /path/to/consumer-repo
OPENCODE_CONFIG_DIR="$CONFIG_DIR" \
  cplt --agent opencode --project-dir "$PWD" \
    --allow-read "$CONFIG_DIR" --pass-env OPENCODE_CONFIG_DIR \
    -- --agent grillmester
```

Grillmester velger ikke provider eller modell. Trenger du en kontrollert,
immutable installasjon med profiler og rollback, kan du velge den [avanserte
lifecycle-flyten](docs/opencode.md#valgfri-lifecycle-manager). Den er ikke
nødvendig for vanlig cplt-bruk.

## Velg agent

| Agent | Bruk når |
| --- | --- |
| **Grillmester** 🔥 | Oppgaven er uklar, viktig eller tverrgående. Grillmester avklarer valg og risiko før en avgrenset løsning implementeres og vurderes. |
| **Barista** ☕ | Målet er tydelig og oppgaven kan løses som vanlig repoarbeid. Barista forstår, implementerer og verifiserer i en lett flyt. |
| **Designer** 🎨 | Du vil utforske brukerflyt, konsepter, Aksel, Visual Companion eller Figma. Designer lager en designleveranse, men implementerer ikke produktkode. |
| **Doctor Who** 🕰️ | Du trenger støtte til discovery, mål, prioritering, workshops, teamhelse, produktfag eller Nav-arkitektur. |

Beskriv ønsket resultat, relevant kontekst og avgrensninger. Agenten laster
normalt riktige skills selv. Kokk, Grill-inspektør og Researcher er interne
roller som agentteamet bruker ved behov. [Se alle agenter og
skills](docs/agents-and-skills.md).

## Støtte og avgrensninger

GitHub Copilot CLI er best testet. Copilot app støtter personlig
plugininstallasjon; VS Code er ikke fullt verifisert. OpenCode-støtten gjelder
den eksakte klientkombinasjonen over, og hver konkret lokal eller cloudbasert
modell må kvalitetsvalideres separat. Se [klientstatus og tekniske
releasegater](docs/trust-and-client-support.md).

Grillmester kan brukes sammen med `navikt/copilot`. Se hvordan [repo-eid
kontekst, overlapp og eventuelle
kollisjoner](docs/repository-context.md#samspill-med-naviktcopilot) håndteres.

## Dokumentasjon

- **Installere:** [GitHub Copilot](docs/installation.md) · [OpenCode via cplt](docs/opencode.md)
- **Velge modeller:** [Lokale og cloudbaserte modeller](docs/local-models.md)
- **Bruke agentteamet:** [Agenter og skills](docs/agents-and-skills.md) · [valgfritt MCP-oppsett](docs/mcp-setup.md)
- **Forstå og bidra:** [Repo-kontekst](docs/repository-context.md) · [utvikling](docs/development.md)

Problemer eller forslag? [Opprett et issue](https://github.com/navikt/grillmester/issues/new/choose).
Ikke legg secrets, personopplysninger eller sårbarhetsdetaljer i et offentlig
issue; bruk [private vulnerability reporting](SECURITY.md) for sårbarheter.

Grillmester vedlikeholdes av Team eSyfo for Nav og er tilgjengelig under
[MIT-lisensen](LICENSE). Se [proveniens og tredjepartslisenser](PROVENANCE.md).
