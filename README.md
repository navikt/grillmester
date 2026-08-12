# Grillmester 🔥

<p align="center">
  <img src="docs/assets/grillmester-hero.jpg" alt="En retro robotgrillmester ved en kullgrill i et norsk landskap" width="100%">
</p>

> **Grill antakelsene før de havner i produksjon.**

Grillmester er et agentteam for GitHub Copilot. Det hjelper Nav-team med å
avklare viktige oppgaver, ta synlige valg og levere med verifiserbar evidens —
uten å kopiere agentfiler mellom repoer.

Pakken består av **7 agenter og 44 progressivt lastede skills**. Den er en
kurert **POC**, basert på oppsettet Team eSyfo har pilotert i
`syfo-budstikka`. Copilot CLI er den verifiserte referanseklienten;
Copilot app og cloud agent har egne ende-til-ende-gater før stabil release.

## Kom i gang

Velg først en reviewet kandidat fra
[Releases](https://github.com/navikt/grillmester/releases). En release-tag har
formen `v<plugin-versjon>`, peker på den reviewede marketplace-katalogen og
pinner derfra plugininnholdet til en eksakt commit-SHA. Bruk denne taggen i CLI
og eventuell repoaktivering; ikke erstatt den med `main` når resultatet skal
være reproduserbart.

### Copilot app

1. [Legg til Grillmester-markedsplassen](https://github.com/copilot/app/launch?open=ghapp%3A%2F%2Fplugins%2Fmarketplace%2Fadd%3Fsource%3Dnavikt%252Fgrillmester)
2. [Installer Grillmester](https://github.com/copilot/app/launch?open=ghapp%3A%2F%2Fplugins%2Finstall%3Fsource%3Dgrillmester%2540grillmester)

Lenkene bruker GitHubs offisielle
[`ghapp://`-pluginflyt](https://docs.github.com/en/enterprise-cloud@latest/copilot/how-tos/github-copilot-app/open-with-deep-links#open-plugin-flows).
De åpner **Settings → Plugins** med riktig verdi ferdig utfylt; ingenting legges
til eller installeres før du bekrefter i appen. Denne installasjonen er
personlig i Copilot app og endrer ingen repo-filer.

GitHub dokumenterer bare `OWNER/REPO` eller en Git-URL som marketplace-kilde i
App-lenken — ikke CLIs `OWNER/REPO#ref`-form. Lenken over følger derfor repoets
default branch og er en enkel App-POC, ikke evidens for en immutable RC. Før
stabil release må App-gaten enten bevise og registrere eksakt katalog- og
source-SHA, eller eksplisitt avgrense App fra den reproduserbare releaseveien.

### Copilot CLI

Den eksakte personlige installasjonsflyten er:

```bash
copilot plugin marketplace add navikt/grillmester#REVIEWED_RELEASE_TAG
copilot plugin install grillmester@grillmester
copilot plugin list
copilot --agent=grillmester:grillmester
```

Den dokumenterte
[`owner/repo#ref`-formen](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference#copilot-plugins-marketplace-subcommands)
gjør at CLI registrerer den reviewede release-taggen, ikke en flytende branch.
Installasjonen ligger i brukerens Copilot-home og er tilgjengelig i alle repoer
på maskinen. Den aktiverer ikke Copilot cloud agent i et repo; bruk
repoaktivering nedenfor når teamet og cloud agent skal få samme versjon.

Prøv for eksempel:

> Kartlegg hva som må avklares før vi endrer denne flyten. Skill mellom fakta,
> antakelser og reelle beslutninger. Ikke implementer før retningen er
> godkjent.

Velg agent med `/agent` i en interaktiv sesjon; klienten viser normalt det
kvalifiserte navnet `grillmester:<agent>`. En personlig eller repo-lokal agent
med samme ID kan derimot skygge pluginagenten helt. Fjern eller gi den lokale
kopien nytt navn — kvalifisering er ikke en sikker omgåelse.

## Fire innganger, ett lag

| Agent | Velg den når |
| --- | --- |
| **Grillmester** 🔥 | Oppgaven er viktig eller uklar og trenger speccing, domenemodellering, arkitekturvalg eller ADR før en avgrenset implementasjon og uavhengig review. |
| **Barista** ☕ | Oppgaven er enkel eller allerede godt spesifisert og kan løses i en lett, solo-first flyt. |
| **Designer** 🎨 | Du trenger designutforsking, Aksel- og Figma-arbeid eller en tydelig designleveranse. Designer implementerer ikke kode. |
| **Doctor Who** 🕰️ | Du jobber med mål, prioritering, discovery, workshops, teamhelse, produktfag eller Nav-spesifikke arkitekturvalg. |

`Kokk` implementerer avgrensede slices, `Grill-inspektor` reviewer uavhengig,
og `Researcher` løser ett avgrenset, kildebelagt Wayfinder-research-ticket uten
writes. De tre er interne subagenter og er ikke manuelt valgbare.

De 44 skillene dekker blant annet grilling, domenemodellering, ADR,
sikkerhetsreview, TDD, integrasjonstester, NAV/NAIS, Kotlin, PostgreSQL,
observability, Aksel, Figma og produktarbeid. Runtime-ID-ene har prefikset
`grillmester-`; selve innholdet og referansene lastes først når de trengs.

Full Figma-lesing og -leveranse krever at klienten har en godkjent Figma MCP.
Uten den skal Designer degradere tydelig til konsept, Visual Companion eller et
Figma-klart utkast — aldri late som en Figma-endring er utført.

Designer og Doctor Who har eksplisitte, kryssklient verktøylister. Ingen av dem
kan delegere til en annen agent. Doctor Who har heller ikke shell/execute;
rollen kan lese relevante repo-, issue-, PR- og prosjektkilder og, etter
preview og eksplisitt godkjenning, skrive produktartefakter, issues og
Projects-felter. Designer har bare navngitte Figma-verktøy, et lite
Playwright-sett uten evaluate/run-code, NAVs Aksel-oppslag og GitHub
Issue-lesing/-skriving.

Det gjenstår en bevisst POC-risiko: Copilots innebygde `edit` og `execute` kan
ikke teknisk avgrenses per sti eller kommando i agent-frontmatter. Designer har
derfor disse to brede kapabilitetene, men agentkontrakten tillater dem kun for
den bundlede Visual Companion-serveren og dens eksakte private
`screen_dir`-tempsti fra startup-JSON; de gir ikke tillatelse til produktkode,
Git, pakkeinstallasjon eller vilkårlige prosesser.
Tilsvarende kan GitHubs `issue_write` og `projects_write` utføre flere
operasjoner innen sitt domene. Preview-/godkjenningsgatene begrenser intensjon,
men er ikke en sandbox. Den publiserte RC-en må derfor app-testes med både
godkjent og avvist write før stabil release.

Allowlisten installerer ikke en MCP-server og gir ikke OAuth-scopes. Figma og
GitHub Projects virker derfor bare når klienten faktisk eksponerer de navngitte
verktøyene med riktige tilganger. Hvis en kapabilitet mangler, skal agenten
stoppe med `NEEDS_INPUT` eller tilby en eksplisitt avgrenset fallback.

## Velg riktig aktiveringsnivå

Installasjon og aktivering er ikke det samme på alle flater:

| Behov | Eier og plassering | Gjelder for | Viktig avgrensning |
| --- | --- | --- | --- |
| Prøve i Copilot app | Brukeren, **Settings → Plugins** eller lenkene ovenfor | Brukerens Copilot app | Skriver ikke repo-settings; den dokumenterte deep-link-kilden er ikke release-pinnet og beviser heller ikke cloud-aktivering. |
| Prøve i Copilot CLI | Brukeren, installasjonskommandoene eller `~/.copilot/settings.json` | Alle CLI-repoer for brukeren | Personlig aktivering; andre utviklere og cloud agent får den ikke automatisk. |
| Aktivere i ett teamrepo | Repoet, `.github/copilot/settings.json` | Copilot CLI og cloud agent i dette repoet | Commit reviewes som kode; pluginen forblir deaktivert i andre repoer. |
| Styre for virksomheten | Enterprise-admin, managed settings | Klientene GitHubs managed-settings-matrise angir | Kan tillate, kreve eller blokkere marketplace/plugin; dette er policy, ikke en consumer-fil. |

Copilot CLI støtter den samme deklarative pluginblokken i personlig
`~/.copilot/settings.json` og i repoets `.github/copilot/settings.json`. Lagre
den personlig for global CLI-aktivering, eller commit den i repoet når teamet og
cloud agent skal bruke samme release:

```json
{
  "extraKnownMarketplaces": {
    "grillmester": {
      "source": {
        "source": "github",
        "repo": "navikt/grillmester",
        "ref": "REVIEWED_RELEASE_TAG"
      }
    }
  },
  "enabledPlugins": {
    "grillmester@grillmester": true
  }
}
```

GitHubs
[konfigurasjonsreferanse](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference#repository-settings-githubcopilotsettingsjson)
dokumenterer at repoets to pluginfelt leses av både Copilot CLI og cloud agent,
og at en kun repoaktivert plugin forblir deaktivert globalt. Enterprise-policyen
må samtidig tillate marketplacen og modellene agentene bruker.

Enterprise-adminer bruker de samme `extraKnownMarketplaces`- og
`enabledPlugins`-nøklene i managed settings. De kan i tillegg bruke
`strictKnownMarketplaces`; en tom liste betyr full marketplace-lockdown. Se
[enterprise managed settings](https://docs.github.com/en/copilot/reference/enterprise-administrators/enterprise-managed-settings).
En bruker- eller repoendring kan ikke omgå en slik blokkering.

Oppgradering er en vanlig PR som endrer `ref` til en nyere reviewet tag.
Rollback er den samme endringen tilbake til forrige tag. Dermed er både
endringen og gjenopprettingen synlig i Git-historikken, mens hver katalog
fortsatt peker på byte-eksakt plugininnhold via en 40-tegns SHA.

Repoer som fortsatt mottar agenter fra Hovmester må ikke bare legge til denne
filen: repo-lokale agent-ID-er kan skygge pluginen, og en aktiv sync kan legge
dem tilbake. Følg den baseline- og rollback-bundne
[consumer-pilot-runbooken](docs/consumer-pilot-runbook.md) for første migrering.

En personlig CLI-installasjon bytter immutable tag ved å binde marketplacen på
nytt. Bruk samme flyt med forrige tag for rollback:

```bash
copilot plugin uninstall grillmester@grillmester
copilot plugin marketplace remove grillmester
copilot plugin marketplace add navikt/grillmester#NEW_REVIEWED_RELEASE_TAG
copilot plugin install grillmester@grillmester
```

Kontroller installasjonen med:

```bash
copilot plugin list
copilot --agent=grillmester:barista
```

## Instructions følger ikke med — med vilje

Pluginen distribuerer felles **metode** gjennom agenter og skills. Den
distribuerer ikke `.github/copilot-instructions.md`, `AGENTS.md` eller
path-scoped `.github/instructions/*.instructions.md`.

Det gir ett distribusjonsløp for Grillmester og lar path-scoped regler beholde
den presisjonen bare consumer-repoet har. Til gjengjeld må hvert repo eie sitt
faktiske lokale delta:

- korrekte build-, test- og kjørekommandoer
- kanoniske domeneord og språk for varige artefakter, inkludert ADR-er
- data- og sikkerhetsklassifisering, autentisering og lokale trust boundaries
- regler og invariants som bare gjelder bestemte mapper eller filtyper

Felles språk- og sikkerhetsgulv ligger i de aktive Grillmester-agentene og
reviewskillene:
norske domeneord bevares, tekniske identifikatorer forblir engelske, og
sensitive data, autorisasjon og trust boundaries behandles eksplisitt. Lokale
instructions skal beskrive repoets sannhet, ikke være en kopi av hele
Grillmester-manualen.

Dette gulvet er ikke automatisk aktivt i default Copilot, innebygd code review
eller andre AI-verktøy. Hvis en regel må gjelde på disse flatene, må consumeren
eie den som én tynn, stående kontrakt — helst `AGENTS.md` for kryssverktøyregler,
og path-scoped instructions bare når en regel faktisk må aktiveres av filsti.
Instructions og agentprompter er kontekst, ikke en teknisk sikkerhetsgrense;
obligatoriske kontroller håndheves fortsatt med CI, rulesets og CODEOWNERS.

Konsekvensen av manglende lokal kontekst er også tilsiktet: agentene skal
inspisere repoet, spørre eller stoppe med et tydelig kontekstbehov — ikke finne
på kommandoer, språkpraksis eller sikkerhetsregler. Repo-lokale agenter og
skills med samme ID har dessuten presedens over plugininnhold; unngå slike navn
med mindre overstyringen er bevisst.

Kjør `/grillmester-doctor` for en manuell, read-only kontroll av aktivering,
instruksjonskilder, lokale policygap og navnekollisjoner. Doctor skriver eller
synker aldri filer; et eventuelt forslag implementeres først i en separat,
eksplisitt godkjent oppgave. Start uten å opprette nye instruction-filer;
Doctor anbefaler bare et lokalt delta når repo-evidens og deterministiske gates
ikke er tilstrekkelige.

## Klientstøtte

| Klient | Status i POC-en |
| --- | --- |
| **Copilot CLI** | Primær referanse: lokal mount, installasjon, oppgradering, rollback og avinstallering er smoke-testet. |
| **Copilot app** | Primær pilotflate: den dokumenterte deep-link-UX-en finnes, men release-pinning, agentvalg og kvalifisert delegering må verifiseres manuelt før stabil release. |
| **Copilot cloud agent** | Repoaktivering via `.github/copilot/settings.json`, marketplace-policy og agentdiscovery må bestå en egen ende-til-ende-gate. |
| **VS Code** | Sekundær kompatibilitetskontroll, ikke styrende distribusjonsflate. |
| **OpenCode** | Eksperimentell skills-only-støtte. Copilot-agentene og marketplacen følger ikke med. |

### Gate fra RC til stabil release

- Installer den eksakte, immutable RC-ref-en og bekreft modelloppløsning i
  Copilot CLI.
- Kjør App-flyten og registrer hvilken katalog-ref og source-SHA den faktisk
  resolver. Hvis App ikke kan bindes til og bevises mot samme RC, består den
  ikke releasegaten selv om den upinnede onboarding-lenken virker.
- Bekreft at de fire offentlige agentene er valgbare, mens Kokk,
  Grill-inspektor og Researcher bare kan delegeres med gyldige briefs.
- La Kokk gjøre én avgrenset, ufarlig write i et disponibelt fixture-repo; kjør
  Inspector, Researcher og `/grillmester-doctor` read-only. Ingen test skal
  endre et reelt consumer-repo.
- Avvis én foreslått write og bekreft at agenten stopper uten sideeffekt.
- Kontroller at Designer og Doctor Who ikke kan delegere, at Doctor Who ikke
  får shell/execute, og at Designer ikke får Playwright evaluate/run-code eller
  server-wildcards. Bekreft samtidig at de navngitte Figma-, Issue- og
  Projects-verktøyene faktisk resolver i både CLI og app.
- Gjenta mot samme publiserte RC i repoaktivert cloud agent med NAVs faktiske
  enterprise-policy. Når alle gatene er grønne, publiser en ny stabil
  manifestversjon og katalog. Plugininnholdet skal være byte-identisk med RC-en
  bortsett fra `plugin.json.version`; RC-taggen flyttes aldri.

Den eksakte RC-/stable-prosedyren, repository controls og incident rollback er
beskrevet i [release-runbooken](docs/release-runbook.md).

En enkelt reviewet skill kan prøves i OpenCode user-scope:

```bash
gh skill install navikt/grillmester grillmester-dulting \
  --agent opencode --scope user --pin REVIEWED_SOURCE_SHA
```

Bruk source-SHA-en som kandidatens marketplace-katalog peker på; katalog-taggen
inneholder bare katalogen, ikke skillfilene. Dette er ikke et løfte om at alle
44 skills er fullt portabilitetsauditert. OpenCode får heller ikke
Grillmester-agentenes felles språk- og sikkerhetsgulv; stående obligatoriske
regler må derfor ligge i consumerens `AGENTS.md`.

## Utvikle pluginen lokalt

Utviklere kan mounte en checkout uten å endre sin vanlige installasjon:

```bash
git clone git@github.com:navikt/grillmester.git
cd /path/to/a/disposable-test-repo
copilot --plugin-dir /path/to/grillmester/plugin \
  --agent=grillmester:grillmester
```

Bruk et disponibelt testrepo. Releasekatalogen genereres fra
`plugin/plugin.json`, og CI verifiserer katalogpinning, innholdslås, agent- og
skillroster, progressive lenker, evalkontrakt og hele
install–oppgradering–rollback–avinstallering-livsløpet.

Kjør den lokale hovedgaten med:

```bash
python3 scripts/generate_marketplace.py --mode development --check
python3 scripts/validate.py
python3 scripts/validate_evals.py
python3 -m unittest discover -s tests -v
node --check plugin/skills/grillmester-design-prototype/scripts/server.js
node --check plugin/skills/grillmester-design-prototype/scripts/helper.js
node --test plugin/skills/grillmester-design-prototype/tests/server.test.js
python3 scripts/smoke_plugin_install.py
```

Grillmester utvikles av Team eSyfo i Nav og er tilgjengelig under
[MIT-lisensen](LICENSE). Kildegrunnlag og tredjepartsmerknader finnes i
[PROVENANCE.md](PROVENANCE.md) og
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
