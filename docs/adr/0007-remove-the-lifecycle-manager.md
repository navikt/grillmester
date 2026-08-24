---
status: accepted
date: 2026-08-24
---

# Fjern lifecycle-manageren og bruk cplt som eneste runtimegrense

## Kontekst

ADR 0002 introduserte en valgfri manager for immutable installasjon, private
klientkopier, runtimeprofiler, staging og rollback. Den ble bygget før den
vanlige cplt-integrasjonen og local-launcheren var ferdig, og ble aldri
publisert i en Grillmester-release.

Etter ADR 0004 og ADR 0006 bruker både vanlig og lokal terminalflyt
brukerinstallerte systemklienter gjennom cplt. Manageren dupliserer dermed
klient- og sandboxeierskap, har egne eksakte pinner og profiler og gjør bundle,
releasegater og dokumentasjon vesentlig større uten å forbedre normalreisen.
cplt er riktig sted for filesystem-, miljø-, nettverks-, `gh`- og Git-policy.

## Beslutning

Lifecycle-manageren, runtimeprofilene og den private `trusted-bin`-/staging-
livssyklusen fjernes fra produktet og release-bundle-en. Det finnes ingen
Grillmester-eid `local-only`-profil eller `--direct`-bakvei.

Terminal-launcheren eier bare:

- valg av OpenCode eller Copilot CLI fra `PATH`
- binding av kanonisk eller focused Grillmester-payload
- binding av eksplisitt provider og modell for `grillmester local`
- kompatibilitetskontroll og handlingsrettede diagnoser

cplt eier runtimegrensen. OpenCode og Copilot CLI eies og oppdateres av sine
egne pakkekanaler. `scripts/release_test_baseline.py` kan fortsatt binde og
verifisere eksakte klientversjoner for reproduserbare release- og
kompatibilitetstester. Kontrakten er ikke en runtimepin, installasjonsmetadata
eller en alternativ distribusjon av klientbinærer.

ADR 0002 beholdes som historikk, men supersedes i sin helhet av denne
beslutningen. Ingen migrering eller rollbackmekanisme er nødvendig fordi
manageren aldri ble publisert.

## Konsekvenser

- Release-bundle, installasjon, dokumentasjon og testmatrise får én
  terminalarkitektur i stedet for to.
- En kompatibel 1.x-klientoppgradering krever normalt ingen Grillmester-release.
- Grillmester lover ikke en egen offline- eller byteverifisert klientruntime.
- Team som trenger strengere egress enn normal cplt-policy må løse og forvalte
  det i cplt eller organisasjonens runtimepolicy, ikke i en parallell
  Grillmester-manager.
