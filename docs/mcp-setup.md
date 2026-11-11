# Valgfritt MCP-oppsett

MCP-er er valgfrie capabilities. Velg bare dem som passer oppgaven, og
installer dem fra [Navs verktøykatalog](https://min-copilot.ansatt.nav.no/verktoy),
som forvaltes i
[`navikt/copilot`](https://github.com/navikt/copilot/tree/main/apps/mcp-registry).

- **Aksel MCP** gir oppslag i Aksels komponenter, props, tokens, ikoner og
  migreringer. Den anbefales for alle som jobber med frontend eller design:
  `aksel` bruker den når den er tilkoblet, og et oppslag der bruker langt mindre
  kontekst enn å hente en hel dokumentasjonsside. Uten den henter skillen
  dokumentasjonen fra [aksel.nav.no](https://aksel.nav.no/llm.md). Serveren heter
  `io.github.navikt/aksel-mcp` i katalogen og kjører på
  `https://aksel-mcp.nav.no/mcp`. `/doctor` sier fra når et repo som bruker Aksel,
  mangler verktøyene i økten.
- **Figma MCP** brukes til å lese og lage Figma-skisser.
- **Playwright MCP** inspiserer lokale sider i klienter uten nettleserfane.

Uten et nettleserverktøy kan du bruke Figma eller legge ved et skjermbilde.
