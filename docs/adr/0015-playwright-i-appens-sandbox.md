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
servere bevares. MCP-konfig sikkerhetskopieres først i den nektede backup-mappen
med 0700/0600-rettigheter; writes er atomiske per fil, og reruns er idempotente.
Helperen leser ikke `data.db`. Pluginen selv leverer ingen hook eller MCP-server.

Docker-wrapperen bruker Playwright 1.63.0 og MCP 0.0.80, en ikke-root container
(`pwuser`), `--rm --init`, kun loopback-publisering og `run-server --path`
med en tilfeldig, URL-sikker token. Token genereres ved apply og lagres bare
i endpointet i en 0600 `docker.json`; den vises aldri i planen. Container med
avvikende path/port erstattes. `--unsafe` og `--no-sandbox` legges ikke til.
Imaget hentes av brukeren **utenfor sandboxen**, aldri automatisk.

## Konsekvenser

Docker-browseren er headless og uten innlogging. Vanlig headed MCP brukes med
sandbox av for innloggede flyter; lokale browser-testsuiter kjøres fortsatt
utenfor sandboxen. En ny bin-dir krever rerun av policyoppsettet og restart av
åpne økter, etterfulgt av lesbarhetssjekk i en ny sandboxet økt.

Docker-socketen gir nær usandboxet vertstilgang. Token-path på loopback er ikke
sterk autentisering: lokale prosesser som kan lese konfigen kan styre browseren.
`exposeNetwork: "<loopback>"` lar browseren nå vertens lokale tjenester;
credential masking på bryter også denne varianten. Containeren henter pinned
`playwright@1.63.0` via npx ved start, med tilhørende supply-chain-risiko;
`PW_IMAGE` tillater digest-pinning. Versjonsendringer må holde MCPs
Playwright-avhengighet og imaget kompatible.
