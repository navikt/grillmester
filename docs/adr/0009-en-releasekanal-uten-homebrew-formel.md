---
status: accepted
date: 2026-09-04
---

# Én releasekanal, og ingen Homebrew-formel

## Kontekst

Grillmester hadde to koblede seremonier rundt hver utrulling.

Den ene var Homebrew-formelen. Den var den tredje av releasens tre assets, og
hadde en egen macOS-matrise i release-gaten. Kanalen ble aldri aktivert:
tap-bootstrap-PR-en ble aldri åpnet, dokumentasjonen beskrev kanalen som satt på
vent, og ingen installerte Grillmester gjennom den. Intel-jobben i den matrisen
begynte dessuten å henge i en Cellar-lås under `brew uninstall` og holdt `main`
rød.

Den andre var RC/stabil-splitten. En stabil release måtte promotere en navngitt
RC med byte-identisk payload, og katalogpublisereren revaliderte RC-ens tre
publiserte assets før den skrev en stabil katalog. Kontrollen skulle gi soak-tid.
Den ga det ikke: i 0.3.0-syklusen kom rc.13, rc.14, rc.15 og stabil samme dag,
og stabil 77 minutter etter rc.15. En kandidat som lever i 77 minutter er ikke
en kandidat som evalueres, den er et påkrevd mellomartefakt.

De to hang sammen. Fjernet man bare formelen, brøt katalogpubliserernes
stabilgate, som teller tre assets. Fjernet man bare kanalsplitten, sto
formelmaskineriet igjen uten formål.

## Beslutning

Vi fjerner begge.

Releasen har nøyaktig to assets: terminalbundelen og den detachede
checksummen. `scripts/generate_homebrew_formula.py`, dens test og
`macos-homebrew-compatibility.yml` er borte, sammen med formelgenerering,
forsegling, opplasting og revalidering i alle tre publiseringsworkflowene.
`grillmester update` er fjernet; Grillmester oppdateres ved å pakke ut en nyere
bundle.

Det finnes én releasekanal. `channel` og `rc_tag` er borte fra
dispatch-inputene, fra `.github/release-request.json` og fra
`release_contract.py`. En versjon er bare en versjon: et strengt
SemVer-prerelease-suffiks markerer GitHub-releasen som prerelease, en ren
versjon markerer den som siste stabile. Ingen release promoteres fra en annen,
og `validate_stable_promotion` med sine parity-sjekker er fjernet.

Rettighetsgodkjenningen i `policy/stable-rights-approval.json` gjaldt tidligere
bare stabilkanalen. Uten kanaler valideres den alltid. Den er en
rettighetsjournal, ikke release-seremoni, og skal gjelde hver publisering.

## Konsekvenser

- Utrulling er dispatch av katalogen, én miljøgodkjenning, og en
  request-fil-PR. Omtrent 3 000 linjer workflow- og kontraktkode forsvinner.
- Tillitsgrensen er uendret: den skrivende jobben kjører fortsatt ingen kode fra
  kildecommiten den publiserer, og assetene krysser miljøgrensen som én
  digest-bundet artifact.
- Uforanderligheten er uendret. Allerede publiserte releaser beholder sine tre
  assets; de kan ikke lenger brukes som RC-forelder, men det finnes ikke lenger
  noen slik rolle.
- Byte-identitetsgarantien mellom en kandidat og dens stabile tvilling er borte,
  fordi rollen er borte. Det som beviser en release er nå gaten den passerer,
  ikke at den er identisk med en tidligere publisering.
- Terminalbundelen består. Den er fortsatt eneste distribusjonsvei for
  OpenCode- og cplt-brukere til nav-pilot-agentpakka er rullet ut, og skal
  først fjernes når den veien faktisk er tatt i bruk.
- TUI-smoken lå i Homebrew-matrisen og kjøres nå fra den native
  macOS-matrisen mot den utpakkede launcheren.
