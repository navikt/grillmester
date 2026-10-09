# Valgfritt MCP-oppsett

MCP-er er valgfrie capabilities. Velg bare dem som passer oppgaven, og
installer dem fra [Navs verktøykatalog](https://min-copilot.ansatt.nav.no/verktoy),
som forvaltes i
[`navikt/copilot`](https://github.com/navikt/copilot/tree/main/apps/mcp-registry).

- **Aksel MCP** gir oppdatert dokumentasjon om komponenter og tokens.
- **Figma MCP** brukes til å lese og lage Figma-skisser.
- **Playwright MCP** inspiserer lokale sider og kontrollerer Visual Companion.
  Den kan brukes ved arbeid mot en eksisterende flate.

I Copilot-appens sandbox kan ikke lokal Chromium kjøre. `/app-sandbox-setup`
tilbyr bekreftet installasjon av to Playwright-wrappere: en headless
Docker-variant i sandboxen og en vanlig variant for innloggede flyter med
sandbox av. Imaget må hentes utenfor sandboxen. Docker-socketen gir nær
usandboxet vertstilgang; credential masking på nekter loopback og bryter
også Docker-varianten.

Visual Companion-serveren kjører uten Playwright. Uten et nettleserverktøy
kan du bruke Figma eller legge ved et skjermbilde.
