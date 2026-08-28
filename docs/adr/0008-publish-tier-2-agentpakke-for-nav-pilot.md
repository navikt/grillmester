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

Hver payload oppgir sine egne `primaryAgents`. Full payload bruker de fire
offentlige agentene Grillmester, Barista, Designer og Doctor Who. Focused-
payload bruker Barista og Grill-inspektør, med Barista først og dermed som
standard. Generatoren avleder fullrosteren fra launcherens offentlige agenter,
verifiserer den mot innholdslåsen og krever at focused-rosteren stemmer med
både focused-policyen og de to genererte payloadmanifestene.

Kompatibilitetsintervallene avledes fra standardstøtten i release-
testkontrakten. Alle fire payloadstier, agentrostre og payloadmanifestenes
target-identitet valideres før agentpakkemanifestet kan oppdateres.

Begge klienter bruker `defaultModel: inherit`. Agentpakkemanifestet velger
dermed ingen fallbackmodell på brukerens vegne. Modellfelt som allerede finnes
i den valgte payloadens agentfrontmatter beholder klientens normale presedens;
full Copilot-payload beholder de reviewede agentmodellene, mens focused-
payloadene arver modell fra klienten eller brukervalget. Begge klienter bruker
full kontekst som standard, mens fokusert kontekst er et eksplisitt valg for
lokal modell eller andre kontekstbegrensede kjøringer.

Manifestet krever nav-pilot `2026.08.28-091813-dc3e4ff` eller nyere. Dette er
første release som både forstår payloadspesifikke primæragenter og installerer
en ekstern Tier 2-pakke som en lokal, revisjonspinnet materialisering. Den
samme releasete nav-pilot-binæren brukes som ekstern konformansvalidator i CI,
men er ikke en avhengighet for Grillmesters frittstående launchere.

For pinnede repo-kilder verifiserer nav-pilot hele pakken ved installasjon og
den valgte payloaden mot manifestdigestene ved launch. Dette oppdager endringer
i payloadfiler, men manifestet er ikke kryptografisk signert: en prosess med
samme brukertilgang kan endre både en fil og den tilhørende digesten. Denne
grensen er akseptert i nav-pilots kontrakt. cplt beholder ansvaret for
runtimeisolasjon; agentpakkemanifestet gjør ingen sterkere provenance-påstand.

## Konsekvenser

- Grillmester beholder én kanonisk plugin og sine eksisterende generatorer.
- nav-pilot kan installere eksakt de samme payloadene som de frittstående
  launcherne, uten å håndredigere eller vendore dem.
- Endringer i offentlig agentroster, standard klientstøtte eller payloadtarget
  gjør manifestet stale og blokkeres av validatoren til det regenereres.
- Manifestet deklarerer bare klientpayloads og ingen nav-pilot-layout. Det kan
  derfor ikke treffe tvetydigheten som gjør at en Tier 2-pakke med begge deler
  avvises.
- Bred nav-pilot-bruk annonseres først når alle fire klient-/kontekstscenarier
  er differensialtestet mot Grillmesters egne launchere.
- Terminalbundle og eksisterende pluginflyt fortsetter å virke uavhengig av
  nav-pilot.
