---
status: accepted
date: 2026-09-10
---

# Automatisk release etter deterministiske porter

## Kontekst

`grillmester-release` er den privilegerte grensen før marketplace-publisering
og opprettelse av en uforanderlig GitHub Release. Før denne beslutningen måtte
et Team eSyfo-medlem godkjenne miljøet, og request-forfatteren kunne ikke
godkjenne selv.

Releasen er allerede bundet til en reviewet, request-only PR på `main`.
Lesende jobber validerer den eksakte katalogen og kildecommiten, bygger og
forsegler terminalassetene deterministisk, og verifiserer artifact-ID, digest,
filer og kilde på nytt før den skrivende jobben får kjøre. Den skrivende jobben
er fortsatt isolert fra valgt kildekode, har minimale rettigheter og bruker
`grillmester-release` for både main-restriksjonen og den miljøeksklusive
`IMMUTABLE_RELEASES_ADMIN_READ_TOKEN`.

Den manuelle miljøgodkjenningen stopper en autorisert releasesti etter at alle
disse portene er grønne. Den er en separat annenpersonskontroll, ikke en del av
bindingen mellom request, katalog, kilde og uforanderlige assets.

## Beslutning

Vi fjerner bare `required_reviewers`-beskyttelsesregelen fra
`grillmester-release`. Dermed fjernes også kravet om en annen reviewer og
prevent-self-review for denne miljøgodkjenningen. Den eksisterende
main-restriksjonen, administrator-bypass-innstillingen og secret-rosteren
endres ikke.

`grillmester-release` beholdes i begge skrivende jobber som deployment- og
secretgrense. Den reviewede request-only PR-en, beskyttet `main`, rulesets,
eksakt katalog-/kildebinding, adskilte lese- og skrivejobber, minimale
rettigheter, uforanderlige artifacts og GitHub Releases, samt alle
deterministiske valideringsporter beholdes.

Endringen av den levende GitHub Environment-konfigurasjonen utføres først av
Grillmester etter at denne endringen er merget.

## Konsekvenser

Marketplace-publisering kan fullføres av én autorisert maintainer etter grønne
porter. En uforanderlig release krever fortsatt den reviewede request-only
PR-en, men ikke et separat klikk i miljøet.

Vi aksepterer at kompromiss eller misbruk av en allerede autorisert workflow-sti
ikke lenger stanser ved en annenpersons miljøgodkjenning. Dette er ikke bevis
for streng kryptografisk separasjon mellom alle repository-skrivere; de
beholdte kontrollene begrenser hva den faste skrivende jobben kan publisere.

Ved behov for å stanse eller reversere denne beslutningen gjenoppretter en
autorisert administrator required reviewers og prevent-self-review på
`grillmester-release`. Da stanser skrivende releasesteg igjen ved
miljøgodkjenningen uten å flytte secrets eller endre releasekontrakten.
