---
status: accepted
date: 2026-10-09
---

# Playwright i appens sandbox

## Kontekst

Lokal Chromium blokkeres av macOS IPC-reglene i Copilot-appens sandbox.
Playwright MCP trenger derfor en ekstern browser for å inspisere lokale
flater uten å slå av sandboxen. ADR 0014 eier fortsatt appens policyoppsett.

## Beslutning

Pluginen distribuerer to executable wrappere og en separat Python-helper i
`app-sandbox-setup`. Etter plan og eksplisitt digest-bekreftelse installerer
helperen wrapperne i brukerens bin-dir (standard `~/.local/bin`) og oppdaterer
`~/.copilot/mcp-config.json`. Eksisterende args, env, ekstra felt og andre
servere bevares. For eksisterende oppføringer endres bare `command`; manglende
`type` og `tools` forblir fraværende. Bare nye oppføringer får `type: "stdio"`
og `tools: ["*"]`. Planen viser eksisterende args bare som `<N args preserved>`,
aldri innholdet eller env. Launcher-lignende args gir ett varsel per oppføring:
de vil sendes til MCP-serveren, så brukeren bør vurdere å fjerne dem.
MCP-konfigens nøkkelrekkefølge bevares. MCP-konfig sikkerhetskopieres først i den nektede backup-mappen
med 0700/0600-rettigheter; writes er atomiske per fil, og reruns er idempotente.
Helperen leser ikke `data.db`. Pluginen selv leverer ingen hook eller MCP-server.

Docker-wrapperen bruker Playwright 1.63.0 og MCP 0.0.80, en ikke-root container
(`pwuser`), `--rm --init --cap-drop=ALL --security-opt no-new-privileges
--shm-size=1g`, kun loopback-publisering og `run-server --path`
med en tilfeldig, URL-sikker token. Token genereres ved apply og lagres bare
i endpointet i en 0600 `docker.json`; den vises aldri i planen, men er synlig
ved kjøring som beskrevet under. Container med avvikende path/port eller
herding erstattes via inspisert container-ID, ikke navn. En matchende kjørende
container fjernes aldri. Ved samtidig oppstart inspiseres containeren på nytt
etter mislykket `docker run`, og en matchende kjørende container gjenbrukes.
`--unsafe`, `--no-sandbox` og `--ipc=host` legges ikke til.
Imaget hentes av brukeren **utenfor sandboxen**, aldri automatisk (`--pull=never`).
Readiness bruker loopback direkte med `curl --noproxy '*'`.

Docker-konfigen setter `browser.isolated: true`, `browser.browserName:
"chromium"` og `remoteEndpoint.browserName: "chromium"`. Begge browserName-felt
beholdes for å samsvare med live-verifisert konfig. `remoteEndpoint.exposeNetwork`
settes til `"<loopback>"`. Planen viser eksisterende verdier som overstyres
for disse valgene og sier eksplisitt fra før string-valued remoteEndpoint
erstattes; endpointet vises ikke.

## Konsekvenser

Docker-browseren er headless og uten innlogging. Vanlig headed MCP brukes med
sandbox av for innloggede flyter; lokale browser-testsuiter kjøres fortsatt
utenfor sandboxen. En ny bin-dir krever rerun av policyoppsettet og restart av
åpne økter, etterfulgt av lesbarhetssjekk i en ny sandboxet økt. Etter hver apply
må åpne økter restartes eller lukkes også for MCP-konfigendringen, selv om
bin-dir allerede hadde grant.

Docker-socketen gir nær usandboxet vertstilgang. Path-token beskytter mot
drive-by WebSocket-tilkoblinger til loopback-porten, for eksempel fra nettsider.
Den er synlig for lokale prosesser via `ps`, `docker inspect` og
`docker ps --no-trunc` (sandboxen har Docker-socketen), og kan forekomme i
Playwrights connect-feilmeldinger. Disse outputene og endpointet skal ikke
skrives ut. Token er **ikke en autentiseringsgrense mot lokal kode**, som kan
styre browseren. Chromiums egen sandbox er av inne i Playwright-containere
som standard; **containeren er grensen**.
`exposeNetwork: "<loopback>"` lar browseren nå vertens lokale tjenester;
credential masking på bryter også denne varianten. Containeren henter pinned
`playwright@1.63.0` via npx ved start, med tilhørende supply-chain-risiko;
`PW_IMAGE` tillater digest-pinning. Versjonsendringer må holde MCPs
Playwright-avhengighet og imaget kompatible.
