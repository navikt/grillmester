---
status: accepted
date: 2026-08-25
---

# Publiser en Tier 2-agentpakke for nav-pilot

## Kontekst

Grillmester har allerede fire deterministiske klientpayloads: full og fokusert
kontekst for både Copilot CLI og OpenCode. Terminal-launcherne kan installeres
separat, men Nav har også en etablert `nav-pilot`-flate for distribusjon,
oppdatering og discoverability. Å kopiere Grillmester-innhold inn i
`navikt/copilot`, eller å bygge enda en sync-livssyklus, ville gitt to kilder
til sannhet og gjeninnført vedlikehold Grillmester nettopp har fjernet.

Agentpakke-kontrakt v1 i `nav-pilot` støtter en Tier 2-pakke som peker på
ferdige klientpayloads med egne manifester. Kontrakten kan uttrykke klientenes
kompatibilitetsintervaller, primæragenter, standardmodell og standardkontekst
uten å overta innholds- eller runtimeeierskap.

## Beslutning

Grillmester publiserer `.nav-pilot/agentpakke.json`. Manifestet genereres
deterministisk av `scripts/generate_agentpakke_manifest.py` og peker på:

- `plugin/` og `targets/copilot-cli-focused-v1/` for Copilot CLI
- `targets/opencode-v1/` og `targets/opencode-v1-focused/` for OpenCode

Generatoren avleder primæragentene fra launcherens offentlige agenter og
verifiserer dem mot innholdslåsen. Kompatibilitetsintervallene avledes fra
standardstøtten i release-testkontrakten. Alle fire payloadstier og
payloadmanifestenes target-identitet valideres før agentpakkemanifestet kan
oppdateres.

Begge klienter bruker `defaultModel: inherit`. Agentpakken velger dermed aldri
en cloud- eller lokal modell på brukerens vegne. Begge bruker full kontekst som
standard, mens fokusert kontekst er et eksplisitt valg for lokal modell eller
andre kontekstbegrensede kjøringer.

Manifestet inneholder foreløpig ingen `minNavPilotVersion`, policyprofil eller
provenance-påstand. De feltene legges først til når en faktisk runtimekontrakt
eller en sann, digestbundet base finnes. Den releasete nav-pilot-binæren brukes
som ekstern konformansvalidator i CI, men er ikke en Grillmester-runtime-
avhengighet.

## Konsekvenser

- Grillmester beholder én kanonisk plugin og sine eksisterende generatorer.
- nav-pilot kan stage eksakt de samme payloadene som de frittstående
  launcherne, uten å håndredigere eller vendore dem.
- Endringer i offentlig agentroster, standard klientstøtte eller payloadtarget
  gjør manifestet stale og blokkeres av validatoren til det regenereres.
- nav-pilot-installasjon annonseres ikke før Tier 2-staging og launch er levert
  og differensialtestet for alle fire klient-/kontekstscenarier.
- Terminalbundle og eksisterende pluginflyt fortsetter å virke uavhengig av
  nav-pilot.
