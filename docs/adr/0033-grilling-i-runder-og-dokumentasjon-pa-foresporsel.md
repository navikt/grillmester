---
status: accepted
date: 2026-11-02
---

# Grilling i runder og dokumentasjon på forespørsel

> Rundene er erstattet av
> [ADR 0039](0039-grilling-med-ett-sporsmal-om-gangen.md). Resten gjelder.

Erstatter delvis ADR 0010.

Agentene skrev mange lange Markdown-filer som teamene ikke klarte å
vedlikeholde, fordi flere skills ga lov til å skrive uten å spørre og lange
ADR-er ble mal for de neste. Grillmester foreslår derfor ordlisteoppføringer og
ADR-er i én linje og skriver dem når brukeren sier ja, ber om det med
`/grill-with-docs`, eller repoets policy krever det. Nye ADR-er er korte,
ordlisten heter `GLOSSARY.md` (en eksisterende `CONTEXT.md` brukes der den
ligger), og grilling stiller alle spørsmål som kan avklares samtidig i én
nummerert runde med en anbefaling til hvert.
