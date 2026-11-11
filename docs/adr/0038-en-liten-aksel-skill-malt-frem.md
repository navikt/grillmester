---
status: accepted
date: 2026-11-11
---

# Én liten Aksel-skill, målt frem

Supplerer ADR 0035 og ADR 0037.

Aksel har fått en MCP-server, og Aksel-teamet har en egen skill, `aksel-builder`,
i `navikt/copilot`. Grillmester hadde `aksel-design` og `figma-workflow` fra en
eldre utgave via Hovmester. `figma-workflow` hadde en fargetabell med token-navn
som ikke finnes lenger.

Vi vurderte å ta inn `aksel-builder` uendret. Målingene i
[baseline for Aksel](../testing/aksel-outcomes-baseline.md) viste at det ikke
holdt. De er gjort på Haiku 5.5, med vanlige bestillinger til Grillmester i et
repo der de ekte pakkene er installert:

- Uten noen Aksel-skill slo agenten selv opp i de installerte pakkene og besto 82 %
  av sjekkene. Den feilet på avviklede komponenter, som fortsatt eksporteres og
  kompilerer, og på migrering. `aksel-builder` løftet de elleve første oppgavene
  fra 91 til 93 %.
- `aksel-builder` ble lastet i 7 av 22 økter, og i 3 av 22 når Aksel MCP var
  tilkoblet. En skill som ikke lastes, hjelper ikke. Den er på 15 KB med ti
  referanser, og referansen ble lest i 15 av 30 økter der skillen var navngitt.
- Flere av teamets apper på versjon 8 bruker fortsatt avviklede komponenter, så
  regelen om å følge nærmeste eksempel sprer dem videre.

Grillmester har derfor én Aksel-skill, `aksel`, som er skrevet for å bli lastet og
for å rette det modellen faktisk gjør feil:

- Beskrivelsen navngir fellen, avviklede komponenter som fortsatt kompilerer.
  Beskrivelsen er alltid i kontekst, så advarselen er der også når skillen ikke
  lastes. Det hjelper, men ikke alene.
- Grillmester-prompten ber om skillen før frontendkode i et prosjekt som bruker
  `@navikt/ds-react`. Designer forhåndslaster den sammen med `design-prototype`,
  siden nesten alle forslag i en Nav-app bruker Aksel.
- `SKILL.md` har tre regler som overstyrer hukommelsen, og oppslagsveien:
  installert pakke, Aksel MCP, og ellers Aksels publiserte dokumentasjon. Regelen
  om avviklede komponenter hviler på mange økter. Reglene om `data-color` og om
  navngitte deler hviler på én feilende økt hver. Fem andre regler ble tatt ut
  igjen: fire fordi agenten gjorde det riktig uten dem, og én fordi den ikke
  stemte med Aksels dokumentasjon.
- Skillen kopierer ikke Aksels dokumentasjon. Les først-tabellen peker til to egne
  referanser, for Figma til kode og for oppgradering, og til tre sider hos Aksel.
- Pluginen leverer fortsatt ingen MCP-server. Skillen bruker Aksel MCP når den er
  tilkoblet, men målingene viser ikke at økter med MCP gir bedre resultat.

På Haiku 5.5 ble den endelige teksten lastet i 26 av 32 økter, og agenten besto
84 av 88 sjekker, mot 72 av 88 uten skill. Begge referansene ble lest i 3 av 3
økter. Opus 5.5, som agentene bruker, løste fem av fem oppgaver både med og uten
en tidligere variant av skillen, lastet den hver gang og brukte ikke flere
credits med den. Den endelige teksten er kjørt i én økt på Opus, med samme
resultat. For Opus er skillen altså en forsikring og en kilde til det modellen
ikke kan lese ut av pakkene, ikke en forutsetning.

Oppslagsveien, tillitsrekkefølgen for Figma og tabellen over codemods er hentet
fra `aksel-builder`. Forbedringene kan foreslås hos Aksel-teamet.

Konsekvensen er at mønstrene i `aksel-design/references/patterns.md` og
brief-modusen i `figma-workflow` forsvinner. Et team som også har `aksel-builder`
fra `navikt/copilot`, får to Aksel-skills. Tabellen over avviklede komponenter er
et øyeblikksbilde av versjon 8, så den varige regelen er å se etter `@deprecated`
i de installerte typene. Skillen må måles på nytt når Aksel kommer i ny
hovedversjon. Målingene dekker Haiku 5.5 i full bredde og Opus 5.5 med noen få
økter, og ingen av dem er gjort i Copilot-appen. På Haiku lastes skillen i
rundt åtte av ti økter, og sjeldnere når Aksel MCP er tilkoblet. Når den ikke
lastes i en fil som alt bruker en avviklet komponent, kopierer agenten den.

Dette reverserer valget fra 5. november om å beholde `figma-workflow` som egen
skill.
