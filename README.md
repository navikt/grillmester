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

Når en reviewet RC-tag er publisert, tar installasjonen i Copilot CLI under ett
minutt:

```bash
copilot plugin marketplace add navikt/grillmester#REVIEWED_RELEASE_TAG
copilot plugin install grillmester@grillmester
copilot --agent=grillmester:grillmester
```

Bruk kandidat-taggen fra repoets
[Releases](https://github.com/navikt/grillmester/releases). Taggen pinner en
marketplace-katalog som igjen pinner plugininnholdet til en eksakt commit-SHA.
Ikke erstatt den med `main` hvis resultatet skal være reproduserbart.

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

## Aktiver Grillmester for et teamrepo

Personlig CLI-installasjon er fin for utprøving. For et teamrepo er den
anbefalte kontrakten én reviewet fil: `.github/copilot/settings.json`.

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

Copilot CLI og Copilot cloud agent leser de samme pluginfeltene. Aktivering fra
repoet gjelder bare der: pluginen blir ikke slått på i andre prosjekter.
Enterprise-policyen må samtidig tillate marketplacen og modellene agentene
bruker.

Oppgradering er en vanlig PR som endrer `ref` til en nyere reviewet tag.
Rollback er den samme endringen tilbake til forrige tag. Dermed er både
endringen og gjenopprettingen synlig i Git-historikken, mens hver katalog
fortsatt peker på byte-eksakt plugininnhold via en 40-tegns SHA.

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
| **Copilot app** | Primær pilotflate: installasjon i Settings → Plugins, agentvalg og kvalifisert delegering verifiseres manuelt før stabil release. |
| **Copilot cloud agent** | Repoaktivering via `.github/copilot/settings.json`, marketplace-policy og agentdiscovery må bestå en egen ende-til-ende-gate. |
| **VS Code** | Sekundær kompatibilitetskontroll, ikke styrende distribusjonsflate. |
| **OpenCode** | Eksperimentell skills-only-støtte. Copilot-agentene og marketplacen følger ikke med. |

### Gate fra RC til stabil release

- Installer den eksakte, immutable RC-ref-en og bekreft modelloppløsning i
  Copilot CLI og app.
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
  enterprise-policy. Promoter først den godkjente katalogcommiten til stabil
  release etter at alle gatene er grønne.

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
