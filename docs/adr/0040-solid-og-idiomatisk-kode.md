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

- Grillmester former endringen etter SOLID før den skriver kode, og `tdd`
  planlegger testene ut fra formen.
- Den følger repoets konvensjoner, men kopierer aldri rotete struktur.
- Koden skal være idiomatisk for språket.
- Formen sjekkes etter hver grønne skive. `tdd` er fortsatt rød–grønn.
- `review` får smellene «Non-idiomatic code», «Fat interface» og «Hard-wired
  dependency», og den som skrev koden, retter alle reelle smells den
  innførte. Gjør repoet SOLID eller idiomer obligatorisk, hindrer et brudd
  `APPROVED`.

Prisen er litt mer arbeid før koden skrives og en risiko for overstrukturering.
Formen skaleres derfor etter endringen, og «Speculative generality» og
«Shallow module» virker fortsatt. En `doctor`-sjekk for språklinter er utsatt
fordi den ikke er gjennomførbar nå. Effekten er ikke målt; se
[scenariene](../testing/copilot-workflow-validation.md).
