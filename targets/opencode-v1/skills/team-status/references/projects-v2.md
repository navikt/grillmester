# GitHub Projects v2 — kapabilitetsstyrt tilgang

Oppskrifter for å lese en eksplisitt bekreftet GitHub Projects v2-tavle og,
etter særskilt godkjenning, endre en konkret verdi. Felter, opsjoner og ID-er er
prosjektspesifikke: hent dem ved kjøring. Ikke bruk eksemplene til å oppdage
eller anta teamets prosjekt.

## Godkjent GitHub-/Projects-integrasjon

Bruk den semantiske GitHub-/Projects-integrasjonen som faktisk er tilgjengelig
og godkjent i runtime. Et vanlig MCP-oppsett kan for eksempel tilby:

- `projects_list` — lister prosjekter for en owner
- `projects_get` — henter ett prosjekt, inkludert felter og items
- `projects_write` — oppretter/oppdaterer items med feltverdier; bruk bare
  etter vist diff og eksplisitt godkjenning

Tilgjengelighet og autorisasjon må verifiseres ved kjøring. To forutsetninger
som ofte mangler:

1. Toolset-et må eksplisitt aktiveres i serveroppsettet (typisk `--toolsets=projects` eller tilsvarende toolset-konfig)
2. Tokenet må ha project-scope

Verktøyene kan skjules uten riktig aktivering eller scope. Fravær av et
verktøy er ikke tillatelse til å bytte til shell, `gh`, rå GraphQL, `curl` eller
en annen nettverksvei. Ikke be brukeren kjøre slike kommandoer på vegne av
Doctor Who.

## Når integrasjonen mangler

Be brukeren lime inn eller eksportere det minste nødvendige, med tidspunkt:

- bekreftet owner, project number og prosjekttittel
- relevante feltdefinisjoner, opsjoner og iterasjoner
- alle items som inngår i rapportens avtalte scope
- feltverdier og item-lenker som påstandene skal spores til

Returner deretter:

```text
Status: NEEDS_INPUT
Mangler: <Projects-kilde eller kapabilitet>
Hvorfor: <hvilken påstand eller handling som ikke kan verifiseres>
Fortsett med: <eksakt eksportert eller innlimt utdrag>
```

Analyser et innlimt eller eksportert øyeblikksbilde som et eksplisitt avgrenset
kildegrunnlag. Oppgi tidspunktet, og ikke presenter det som live status. Hvis
en godkjent skriveintegrasjon mangler, kan Doctor Who bare vise det konkrete
endringsutkastet; brukeren må enten gjøre endringen i GitHub-grensesnittet eller
gjøre integrasjonen tilgjengelig før arbeidet kan fortsette.

## API-semantikk som integrasjonen må bevare

Feltverdier kan ha forskjellige typer, blant annet tekst, single-select og
iterasjon. Bevar typen og ikke flat ut bort feltidentitet eller item-lenker når
evidensen hentes eller eksporteres.

- **Oppdatering av single-select/iterasjon krever opsjon-ID/iterasjons-ID**, ikke navnet på verdien. Hent feltmetadata først gjennom den godkjente integrasjonen og slå opp ID-en.
- **Tømming av felt** har egen mutation: `clearProjectV2ItemFieldValue`. Du kan ikke sette verdien til null.
- **Lukkede iterasjoner** ligger i feltets `configuration.completedIterations`, separat fra de aktive i `configuration.iterations` — sjekk begge når du leter etter en forrige iterasjon.
- **Feltdefinisjoner kan IKKE endres via API.** Det finnes ingen mutations for å legge til eller endre single-select-opsjoner. Foreslå teksten — et menneske legger den inn i prosjektinnstillingene.

## Feilsøking

| Symptom | Sannsynlig årsak | Brukeren bør sjekke |
|---|---|---|
| `projects_*`-verktøyene finnes ikke | Toolset ikke aktivert | At `projects` står i `--toolsets`/toolset-konfigen for GitHub MCP-serveren |
| Verktøyene mangler selv om toolset er aktivert | Token uten project-scope | Token-scopene; PAT/App-token med project-scope. I Actions: default `GITHUB_TOKEN` når aldri Projects-API-et |
| Prosjektet finnes ikke / tom respons | Org-prosjekt utilgjengelig for tokenet | At owner/nummer stemmer, at brukeren ser tavla i nettleseren, og at tokenet er autorisert for org-en (SSO) |

Ikke endre runtime-, MCP- eller tokenkonfigurasjon som en del av statusarbeidet.
Hvis den godkjente integrasjonen fortsatt ikke gir tilgang, bruk
`NEEDS_INPUT`-flyten over.
