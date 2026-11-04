---
status: accepted
date: 2026-11-04
---

# Bevis at referanser blir lest

Supplerer ADR 0035.

Gjemt informasjon er verdiløs. Målingen i
[baseline for referanser](../testing/reference-reads-baseline.md) viste at
agentene leste under to av tre referanser når skillen allerede var lastet, og at
pekeren avgjorde det. En tabell øverst ble lest nesten alltid. En liste med lenker
til slutt eller et «se» midt i en tekst ble nesten aldri lest. Kildene sier det
samme: pekerens ordlyd avgjør, og den må si når referansen skal leses.

Hver skill med referanser har derfor en seksjon Read first (Les først) øverst i
`SKILL.md`, med tre steg og en tabell fra gren til referanse. Et steg som selv er
pekeren, kan stå når målingen viser at det virker. Innhold hver gren trenger,
står i `SKILL.md`, slik `review` nå har smells selv. Validering krever at hver
referanse er lenket direkte fra `SKILL.md`, og at en referanse over hundre linjer
starter med en innholdsliste. Hver referanse har et scenario i
`scripts/measure_reference_reads.py`, og en test feiler hvis det mangler. Selve
målingen koster kreditter og kjøres ved endring, ikke i CI.

Konsekvensen er at agenten også leser noen referanser den ikke trenger. Det koster
litt kontekst, men er bedre enn at den mangler en regel. Målingen sier ikke om
skillen lastes uten hint. Der er små modeller fortsatt svake, og
`skills`-feltet i agenten løste det ikke.
