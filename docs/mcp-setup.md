# Anbefalt MCP-oppsett

Grillmester installerer ikke MCP-servere. Hvilke servere og verktøy som er
tilgjengelige styres av Copilot-klienten, Navs MCP-register og brukerens
godkjenninger. Agentene skal fungere uten oppsettet under, men enkelte flyter
blir mer presise og komplette med riktige MCP-er.

## Anbefalte servere

| Server | Brukes av | Hva den tilfører |
| --- | --- | --- |
| **Aksel MCP** (`io.github.navikt/aksel-mcp`) | Designer og andre agenter som gjør frontendarbeid | Fersk upstream-dokumentasjon, komponent-API-er, tokens, ikoner og migreringer. Bekreft versjonen som er installert i repoet; installerte typer og rendret DOM vinner ved avvik. |
| **Figma MCP** (`com.figma/figma-mcp`) | Designer | Designkontekst, bibliotekssøk, skjermbilder og, når klient, sete og filtilgang tillater det, skriving av ekte Figma-struktur. Designer skal kontrollere de faktisk tilgjengelige verktøyene før en endring hevdes utført. |
| **Playwright MCP** (`com.microsoft/playwright-mcp`) | Designer, og ved behov Grillmester eller Barista | Valgfri nettleserinspeksjon når klienten ikke allerede har et tilsvarende verktøy. Bruk først etter at det sentrale Nav-oppsettet er verifisert. |

Installer serverne fra [Navs verktøykatalog](https://min-copilot.ansatt.nav.no/verktoy),
som forvaltes gjennom
[`navikt/copilot` sitt MCP-register](https://github.com/navikt/copilot/tree/main/apps/mcp-registry).
Bruk registerinstallasjonen fremfor å kopiere statiske kommandoer eller
pakkeparametre. Da slipper Grillmester å eie konfigurasjon som kan drifte.
Behold den fullstendige server-ID-en som står i tabellen; Navs policy matcher
den registrerte ID-en.

Verifiser den sentrale Playwright-oppføringen i klienten før bruk. Hvis
katalogoppsettet ikke starter med dagens pakke, bruk et allerede verifisert
klientoppsett eller prosjektets egne Playwright-tester; ikke kopier utdaterte
pakkeparametre inn i Grillmester.

I Copilot CLI kan du kontrollere det effektive oppsettet med:

```bash
copilot mcp list
copilot mcp get io.github.navikt/aksel-mcp
copilot mcp get com.figma/figma-mcp
copilot mcp get com.microsoft/playwright-mcp
```

Dette bekrefter konfigurasjonen, ikke nødvendigvis aktiv OAuth. Før en
Figma-flyt bør Designer verifisere riktig konto med `whoami` og en read-only
lesing. Skriving krever i tillegg Full seat og redigeringstilgang til filen.

GitHub dokumenterer at MCP-er som er konfigurert for Copilot CLI eller repoet
også blir tilgjengelige i Copilot-appen. Det effektive verktøysettet avhenger
fortsatt av klient, policy og autentisering og må verifiseres i den faktiske
sesjonen. I VS Code finner du Nav-godkjente servere gjennom MCP-registeret.

## Visual Companion, Figma og Code Connect

Visual Companion brukes til å utforske og velge retning. Når resultatet skal
bli en redigerbar Figma-skisse, skal Designer bygge Figma-native struktur med
`use_figma` og bruke ekte instanser der det aktive Aksel-biblioteket har en
relevant komponent. En HTML-capture er bare visuell referanse.

Code Connect kobler publiserte Figma-komponenter og instansene deres til kode;
det konverterer ikke HTML-lag til Aksel-instanser. Designer kan kontrollere en
eksisterende kobling read-only med `get_code_connect_map`. Les først mappingens
`label`; bruk deretter den eksakte etiketten i `clientFrameworks` for både en
filtrert mappingkontroll og eventuell `get_design_context`. Et tomt svar for én
instans beviser ikke at hele Aksel-biblioteket mangler Code Connect. Designer
skal ikke opprette, endre eller publisere slike koblinger. Det aktive
Aksel-biblioteket er autoritativt; Grillmesters lokale katalog er en gjennomgått,
historisk fallback for komponentnøkler og kjente fallgruver.

Se [Figmas Code Connect-integrasjon](https://developers.figma.com/docs/figma-mcp-server/code-connect-integration/)
og [write-to-canvas-flyten](https://developers.figma.com/docs/figma-mcp-server/write-to-canvas/).

## Når en server mangler

- Uten Aksel MCP: bruk installert Aksel-versjon og de offentlige
  [LLM-dokumentene](https://aksel.nav.no/llm.md); ikke gjett API-er fra minnet.
- Uten Figma MCP: bruk Visual Companion, chat eller et reviewbart Issue-utkast;
  ikke hev at en Figma-fil ble opprettet eller endret.
- Uten Playwright MCP: bruk klientens nettleserverktøy eller repoets Playwright
  CLI/tester. Be ellers om skjermbilde eller annen representativ evidens.

Se også [Aksels MCP-dokumentasjon](https://aksel.nav.no/grunnleggende/kode/mcp-server),
[Navs MCP-register](https://mcp-registry.nav.no) og
[GitHubs MCP-oppsett for Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers).
