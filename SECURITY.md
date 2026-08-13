# Sikkerhet

Ikke rapporter sårbarheter, tokens, personopplysninger eller sensitiv NAV-
diagnostikk i en offentlig issue.

Bruk GitHubs
[private vulnerability reporting](https://github.com/navikt/grillmester/security/advisories/new)
for sårbarheter i Grillmester-pluginen, distribusjonskjeden eller bundlede
scripts. Beskriv berørt release-tag og source-SHA, klient, minste reproduksjon,
forventet påvirkning og eventuelle observerte sideeffekter. Fjern reelle secrets
og personopplysninger også fra den private rapporten.

Generelle sikkerhetskrav eller forbedringsforslag uten en utnyttbar sårbarhet
kan opprettes som et vanlig forslag.

## Avgrensning

Agentprompter og skills er atferdskontrakter, ikke teknisk sandbox eller
autorisasjon. Se [runtime-sikkerhet](docs/runtime-safety.md) for påkrevd
sandbox-, approval- og credential-policy ved NAV-bruk.
