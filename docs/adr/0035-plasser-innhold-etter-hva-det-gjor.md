---
status: accepted
date: 2026-11-04
---

# Plasser innhold etter hva det gjør

Erstatter delvis ADR 0026.

Grillmester har 44 skills. Av dem modellen kan velge selv, nevnes 13 ikke av noen
agent, og mye av teksten overlapper. Det gjør det vanskelig å forutsi hva som
lastes når, og lange funksjoner slipper gjennom fordi ingen del av flyten stopper
dem. Hver bit innhold testes derfor i denne rekkefølgen:

1. Endrer det ikke hva modellen gjør, slettes det.
2. Gjelder det ett repo eller team, flyttes det dit.
3. Må det alltid gjelde, hører det hjemme i agentprompten eller en automatisk
   sjekk.
4. Er det et faktum modellen ikke kan vite, blir det en referanse.
5. Bare det som har egen utløser og eget resultat, er en skill.

Grillmester-prompten navngir fem faser med skillene sine: Clarify, Build, Debug,
Check og Deliver. Den fokuserte profilen nevner bare skillene den har med. Regler
for all kode står i prompten, ikke i en egen skill, så
de gjelder selv om ingen skill er lastet. `tdd` er igjen rød–grønn, og
refaktorering hører til `review`, der den som skrev koden, retter smells i egen
kode. Grill-inspektør er standard fra R2, siden den som skrev koden, ellers også
vurderer den. En sperre mot for store funksjoner hører hjemme i repoene, så
`doctor` melder fra når den mangler.
