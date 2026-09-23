---
status: accepted
date: 2026-09-23
---

# Release ved versjonsbump på main

## Kontekst

Etter ADR 0009 og 0011 krevde hver utrulling tre manuelle steg:

1. merge kildeendringen med versjonsbump;
2. dispatch katalogpubliseringen med en eksakt kilde-SHA;
3. merge en egen request-only-PR med katalog-SHA-en.

Utrullingen av 0.4.1 (#73 og #74) krevde to PR-er, én dispatch, kopiering av
to SHA-er og en ny kjøring av en ustabil macOS-jobb midt i løpet.

Request-PR-en skulle være et reviewet beslutningspunkt. I praksis merger samme
maintainer den med administrator-bypass, så den er seremoni og ikke en
uavhengig kontroll. Maintaineren vil fortsatt bestemme når det rulles ut, men
uten seremonien.

## Beslutning

Én workflow, `Release`, erstatter `publish-marketplace.yml`,
`publish-release.yml` og `promote-release.yml`. Den starter når en push til
`main` endrer `plugin/plugin.json`, og kan dispatches fra `main`.

En lesende plan-jobb avgjør hva som releases:

- ingenting når `v<versjon>` allerede er en publisert release; en annen feil
  enn 404 fra oppslaget stopper løpet;
- katalogens eksakte kilde når `marketplace`-tippen allerede har versjonen,
  slik at et avbrutt løp gjenopptas;
- ellers nyeste `main`.

Plan-jobben ser bare på om versjonen er publisert, ikke på om push-en endret
versjonen. Dermed gjenopptar enhver senere kjøring en versjon som ble avbrutt,
også når en ny push eller en kansellert kjøring i køen kom imellom.

Den skrivende releasejobben sjekker den forseglede kilden og katalogen mot
plan-jobben og katalogpubliseringen, uavhengig av jobben som kjørte kode fra
kilden. Den erstatter bindingen til request-filen som forsvinner.

`.github/release-request.json` og request-PR-en fjernes. Beslutningen om å
rulle ut er merge av PR-en som bumper versjonen. Uavhengig
Grill-inspektør-review anbefales før den merges, men er ikke påkrevd.

`scripts/bump_version.py` bumper versjonen og regenererer alle mål. Når
rettighetsomfattet importert innhold er endret, nekter skriptet til
rettighetsjournalen bindes på nytt med `--rights-review` og PR-en som
reviewer innholdet.

Copilot-kompatibilitet og den native macOS-matrisen kjøres én gang per
release. Releasestadiet gjenbruker dem, siden de gjelder samme kilde.

Dette beholdes uendret:

- kravet om at hver jobb kjører fra nyeste `main`;
- eksakt binding mellom katalog og kilde;
- forsegling før skriving;
- adskilte lese- og skrivejobber, der skrivejobbene ikke kjører kildekode;
- miljøet `grillmester-release`;
- uforanderlig tag og release;
- rettighetsjournalen;
- alle deterministiske porter.

## Konsekvenser

- Utrulling er én merge. Et avbrutt løp gjenopptas av neste kjøring av
  `Release`, enten en push som endrer `plugin/plugin.json` eller en manuell
  kjøring fra `main`.
- Katalogen går ut til den flytende kanalen før den uforanderlige releasen er
  forseglet. Feiler releasesteget, har brukerne på kanalen allerede versjonen,
  og neste kjøring fullfører releasen.
- Det finnes ikke lenger et eget reviewet request-punkt. Den som merger en
  versjonsbump, publiserer til den flytende kanalen og lager en uforanderlig
  release. Det er samme tillitsnivå som gjaldt i praksis, der maintaineren
  merget request-PR-en selv.
- Endringer kan merges uten å bli rullet ut. De går ut med neste versjonsbump.
- En versjon som får katalog, men ikke release, før en nyere versjon bumpes,
  blir stående uten uforanderlig release. Det aksepteres.
- Den manuelle lesende preflighten `Validate immutable release` forsvinner.
  Den samme valideringen kjører som del av hver release før skriving.

For å stanse eller reversere beslutningen gjenoppretter en administrator
required reviewers på `grillmester-release` (se ADR 0011), slik at skrivende
steg venter på godkjenning. Alternativt fjernes push-triggeren, slik at
release bare kan startes manuelt.
