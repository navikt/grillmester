---
status: accepted
date: 2026-11-04
---

# Bevis at referanser blir lest

Supplerer ADR 0035.

Gjemt informasjon er verdiløs. Målingen i
[baseline for referanser](../testing/reference-reads-baseline.md) viste at
agentene leste under to av tre referanser når skillen allerede var lastet, og at
pekeren avgjorde det. Med samme oppsett ble en tabell øverst lest i 38 av 39 økter,
et «se» i teksten i 10 av 24 og en lenkeliste til slutt i 1 av 9. Kildene sier det
samme: pekerens ordlyd avgjør, og den må si når referansen skal leses.

En skill med referanser bruker derfor en av to pekere. Hovedregelen er en seksjon
Read first (Les først) øverst i `SKILL.md`, eller en tilsvarende tabell, fra gren
til referanse. En referanse bare ett senere steg trenger, kan i stedet stå i det
steget, med betingelse og handling, når målingen viser at det virker. Innhold hver
gren trenger, står i `SKILL.md`, slik `review` nå har smells selv. Validering krever
at hver referanse er lenket direkte fra `SKILL.md`, og at en referanse over hundre
linjer starter med en innholdsliste. Hver referanse har et scenario i
`scripts/measure_reference_reads.py`, og en test feiler hvis det mangler. Selve
målingen koster kreditter og kjøres ved endring, ikke i CI.

Konsekvensen er at agenten også leser noen referanser den ikke trenger. Det koster
litt kontekst, men er bedre enn at den mangler en regel. Målingen sier ikke om
skillen lastes uten hint; det står i
[baseline for skillvalg](../testing/skill-routing-baseline.md).
