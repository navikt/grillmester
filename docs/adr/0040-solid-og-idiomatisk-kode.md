---
status: accepted
date: 2026-11-13
---

# SOLID og idiomatisk kode fra start

Erstatter delvis ADR 0035. Resten gjelder.

Brukerne måtte minne Grillmester om SOLID og idiomatisk kode i nesten hver
endring. Prompten ba den kopiere nærmeste eksempel, også i rotete repoer, og
ansvarsdelingen ble først vurdert i `review` til slutt.

Derfor:

- Grillmester former endringen etter SOLID før den skriver kode, skalert etter
  størrelsen: hva hver enhet har ansvar for, hvilken modul som eier den, og
  hvilken vei avhengighetene går. `tdd` planlegger testene ut fra formen.
- Domeneregler holdes fri for I/O, for eksempel database, nett og klokke, så de
  kan testes direkte. En regel som best uttrykkes i en spørring, blir i
  spørringen. Parsing og validering av inndata og oppsett av ruter og
  avhengigheter blir der rammeverket eller repoet allerede har dem.
- Den følger repoets dokumenterte regler og konsekvente konvensjoner. Et
  eksempel i nærheten viser konvensjonene, men er ikke en mal for struktur.
  Rotete struktur kopieres ikke, fordi kopier sprer den: ny logikk legges der
  den kan testes, kalles fra den gamle koden, og avviket nevnes i
  sluttmeldingen.
- Koden skal være idiomatisk for språket.
- Hver skive skrives i den planlagte formen. `tdd` er fortsatt rød–grønn, og
  refaktorering hører fortsatt til `review`.
- `review` sjekker ny kode mot SOLID og språkets idiomer, og får smellene
  «Non-idiomatic code», «Fat interface» og «Hard-wired dependency». Den som
  skrev koden, retter reelle smells i kode den la til, og det endringen gjorde
  verre i kode den endret. Gjør repoet SOLID eller idiomer obligatorisk, hindrer
  et brudd `APPROVED`.

Prisen er litt mer arbeid før koden skrives og en risiko for overstrukturering.
Formen skaleres derfor etter endringen, noen få dype enheter foretrekkes framfor
mange tynne, og en abstraksjon kommer først ved andre gangs bruk eller der en
test må erstatte en systemgrense. «Speculative generality» og «Shallow module»
virker fortsatt. En `doctor`-sjekk for språklinter er utsatt
fordi den ikke er gjennomførbar nå. Effekten er ikke målt; se
[scenariene](../testing/copilot-workflow-validation.md).
