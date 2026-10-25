---
status: accepted
date: 2026-10-23
---

# Innspill i Visual Companion

## Kontekst

Nettleserskisser støtter valg av alternativer, men mangler kommentarer,
tilbakemelding om utførte endringer og en enkel måte å prøve ny ordlyd.
Designeren må beskrive plasseringen i chatten og varsle om hver runde.
Samtidig lagrer dagens klikklogg bare opake ID-er, og skissen kjører uten
nettverk i en sandbox med ugjennomsiktig origin.

## Beslutning

Kommentarer og eksplisitte tekstforslag følger samme helper → skall → lokal
HTTP-server som klikk. Tokenet blir i skallet. Sandbox, CSP, loopback-, host-
og origin-grensene videreføres. Skriving krever token, eksakt origin, JSON og
lukket skjema. Ingen ny MCP-server, hook, installasjon eller livssyklus innføres.

En separat, privat og størrelsesbegrenset `comments.json` i sesjonens
`state_dir` lagrer teksten brukeren selv skriver, svar og status. Automatisk
innsamling begrenses til taggsti, tillatt rolle, ramme og viewport; synlig
tekst, feltverdier, DOM-ID-er og klassenavn kopieres ikke. Den eksisterende
klikkloggen beholder sitt tekstfrie skjema. Ingen runtimefiler skrives i
konsumentrepoet. Samme sesjonsopprydding gjelder alle innspill.

Kommentarer tilhører en eksplisitt skjermversjon og overlever skjermbytte.
Tidligere versjoner vises som historikk, uten å gjenbruke nåler eller
redigeringer på nye elementer. Et begrenset tekstforslag kan prøves og angres
lokalt. Forslaget endrer ikke HTML-kilden og gir ikke mandat til eksterne writes.

Designeren samler innspill og sender en runde. Automatisk skjermbytte utsettes
under skriving og mens usendte innspill finnes. Et lokalt `comments.js`-skript
leser hele køen og oppdaterer svar/status gjennom serveren som eneste skriver.
`wait` venter avgrenset på en innsendt runde. Tilstedeværelse vises bare mens
en faktisk venter har en gyldig frist. Klientens videreføring av den aktive
verktøyrunden avgjør om nye innspill behandles uten en chatmelding.

## Konsekvenser

Lagringskontrakten utvides med brukerens bevisst skrevne fritekst, men ikke
automatisk uttrekk av skisseinnhold. Teksten er ubetrodd oppgavedata og kan
ikke endre mandat eller sikkerhetsgrenser. Alle grenser håndheves på serveren,
og filskriving er atomisk og avviser usikre filtyper.

Samlet innsending gir designeren arbeidsro. Direkte manipulering av layout,
generell CSS-redigering og oppvåkning av avsluttede chatsamtaler er ikke del
av denne kontrakten. Sistnevnte krever verifisert klientstøtte og en egen
beslutning dersom det innebærer en hook eller ny livssyklus.

Innspillene er en del av en midlertidig skisseøkt, ikke en varig oppgaveliste.
Brukeren må få vite at de forsvinner når økten ryddes. Versjonsnummeret endres
ikke; publisering av en ny release gjøres separat.
