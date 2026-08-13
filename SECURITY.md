# Sikkerhet

Ikke rapporter sårbarheter, tokens, personopplysninger eller sensitiv Nav-
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

Agentprompter og skills er atferdskontrakter, ikke teknisk autorisasjon.
Runtime-isolasjon, credentials og organisasjonspolicy forvaltes utenfor
pluginen av Navs sentrale plattform og den aktuelle consumeren.
