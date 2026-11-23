# Valgfritt MCP-oppsett

MCP-er er valgfrie capabilities. Velg bare dem som passer oppgaven, og
installer dem fra [Navs verktøykatalog](https://min-copilot.ansatt.nav.no/verktoy),
som forvaltes i
[`navikt/copilot`](https://github.com/navikt/copilot/tree/main/apps/mcp-registry).

- **Aksel MCP** gir oppslag i Aksels komponenter, props, tokens, ikoner og
  migreringer. `aksel` bruker den når den er tilkoblet, og henter ellers
  dokumentasjonen fra [aksel.nav.no](https://aksel.nav.no/llm.md). Målingene våre
  viser ikke at økter med MCP gir bedre resultat eller lavere kostnad.
- **Figma MCP** brukes til å lese og lage Figma-skisser.
- **Playwright MCP** inspiserer lokale sider i klienter uten nettleserfane.

Uten et nettleserverktøy kan du bruke Figma eller legge ved et skjermbilde.

## Velg kilde ved sikkerhetstriage

I Copilot-appen er GitHub MCP og Nais MCP førstevalget. I terminalen kan
`gh` og `nais` brukes til de samme spørsmålene når rollen har lesetilgang.
Velg én lesemåte per oppslag og sjekk hvilke varseltyper og miljøer den dekker.

| Spørsmål | Første oppslag | Hva må stemme? |
| --- | --- | --- |
| Hva kan én bruker lese om en annen, eller hva havner i en logg? | Les den aktuelle kodebanen og nærmeste tilgangs- eller loggtest i repoet. | Testen må dekke riktig tilfelle og revisjon. For produksjon må testet kode og relevant konfigurasjon kunne knyttes til utrullingen. |
| Hvilke varsler har GitHub, og hva dekket analysen? | Bruk de tilgjengelige leseverktøyene i GitHub MCP eller `gh api` når rollen har CLI-tilgang. For GitHub Actions kan siste zizmor- eller CodeQL-kjøring gi mer presise holdepunkter. | Kontroller gren, revisjon, analyse og paginering. Ved hemmelighetsvarsler må verdien være maskert før resultatet når modellen. |
| Hvilke arbeidslaster er berørt? | Bruk Nais MCP til å lese sårbarhetsoversikten for teamet og miljøet. Med CLI gir `nais vulnerability summary` teamoversikten og `nais vulnerability list summary` resultat per arbeidslast. | Knytt funnet til pakkeversjonen og en fersk rapport for imaget som faktisk kjører. |

En repobundet klient kan bruke et avgrenset, maskert utdrag fra en person
med eksisterende innsyn. [Nais MCP](https://github.com/nais/cli/blob/main/MCP.md)
