# Baseline for Aksel

Målt 11. november 2026 med Copilot CLI 1.0.105. Målingen spør om resultatet blir
riktig, ikke bare om en skill lastes eller en referanse leses. Den lå til grunn
for [ADR 0038](../adr/0038-en-liten-aksel-skill-malt-frem.md).

## Oppsett

Hver økt er en ny økt med Grillmester i et engangsrepo. Repoet har en liten
frontend med `@navikt/ds-react`, `@navikt/ds-css` og `@navikt/aksel-icons` 8.19.2
installert, og én fil som fortsatt bruker den avviklede `Alert`, slik flere av
teamets apper gjør. Bestillingen er skrevet slik en utvikler ville skrevet den,
og nevner aldri en skill. Etterpå sjekker et skript filene økten skrev, og svaret:

- at alt som importeres fra Aksel-pakkene, finnes i den installerte versjonen
- at ingen avviklet komponent kommer inn i ny kode
- at spacing, bakgrunn og kant bruker tokens som finnes
- at svaret navngir riktig codemod, oppsett eller klasse

Sjekkene er grove og fanger ikke alt som gjør en løsning god. De 15 oppgavene er
varsel og rød knapp, ikonknapp, layout med sidemeny og kort, egen CSS, skjema med
feiloppsummering, søkbart nedtrekk, mørk modus, migrering fra `--a-`-variabler,
Tailwind 4, Server Component med dialog, en Figma-lenke uten Figma-verktøy,
lenkekort, ramme med tokens, melding om at hele tjenesten er nede, og en ny
melding i filen som bruker `Alert`.

Måleskriptet ligger ikke i repoet. Tallene under kan derfor ikke kjøres på nytt
herfra uten å bygge det opp igjen.

## Haiku 5.5

På de elleve oppgavene alle variantene er målt på, to økter per oppgave:

| Variant | Sjekker bestått | Økter der alt var riktig | Lastet skillen |
| --- | --- | --- | --- |
| Uten Aksel-skill | 53/58 (91 %) | 18/22 | – |
| `aksel-builder` fra `navikt/copilot` | 54/58 (93 %) | 20/22 | 7/22 |
| `aksel-builder` med Aksel MCP | 56/58 (97 %) | 20/22 | 3/22 |
| `aksel` | 58/58 (100 %) | 22/22 | 17/22 |

De fire siste oppgavene kom til underveis, fordi de første var for lette. De
handler mest om avviklede komponenter. Med dem er tallene:

| Variant | Økter | Sjekker bestått | Økter der alt var riktig | Ingen avviklet komponent |
| --- | --- | --- | --- | --- |
| Uten Aksel-skill | 32 | 70/92 (76 %) | 21/32 | 5/14 |
| `aksel` | 30 | 84/84 (100 %) | 30/30 | 12/12 |

`aksel` ble lastet i 24 av de 30 øktene. Til sammen er dette 329 økter på Haiku
5.5, medregnet versjonene underveis, for 277 credits.

## Hva som endret tallene

- **Uten skill** slår agenten opp i `node_modules` og klarer det meste. Den
  bruker `Alert` fordi den fortsatt eksporteres, og i filen som alt bruker
  `Alert`, la den til en ny i 4 av 4 økter.
- **`aksel-builder`** retter feilene når den lastes, men den ble sjelden lastet.
  Med Aksel MCP tilkoblet gikk agenten rett til verktøyene.
- **Fellen i beskrivelsen.** Da beskrivelsen av `aksel` navnga de avviklede
  komponentene, forsvant `Alert` også i økter der skillen ikke ble lastet.
  Beskrivelsen er alltid i kontekst.
- **Utløseren i Grillmester-prompten.** Da prompten ba om skillen før en fil som
  importerer `@navikt/ds-react`, ble den lastet i 52 av 52 økter på de sju
  oppgavene som skiller mest. Den endelige ordlyden gjelder frontendkode og
  stiler i hele prosjektet og ga 24 av 30 på alle oppgavene.
- **Regler fra feil.** Navngitte deler som `LocalAlertContent` fra pakkeroten,
  feil Tailwind-klasse og mørk modus uten `Theme` dukket opp underveis. Hver ga
  én regel eller én rad i Les først.

## Opus 5.5

Grillmester og Designer bruker Opus 5.5, så det er denne modellen som teller.
Fem oppgaver, én økt hver: ny melding i filen som bruker `Alert`, varsel og rød
knapp, tjenesten er nede, Tailwind 4 og migrering.

| Variant | Riktig | Lastet skillen | Credits |
| --- | --- | --- | --- |
| Uten Aksel-skill | 5/5 | – | 107 |
| `aksel` | 5/5 | 5/5 | 99 |

På de tre oppgavene `aksel-builder` også ble kjørt på:

| Variant | Riktig | Lastet skillen | Credits |
| --- | --- | --- | --- |
| Uten Aksel-skill | 3/3 | – | 69 |
| `aksel-builder` | 3/3 | 3/3 | 78 |
| `aksel` | 3/3 | 3/3 | 56 |

Opus klarer disse oppgavene uten skill. Den leser de installerte typene, ser
`@deprecated` og velger erstatningen. Skillen endrer altså ikke resultatet på
Opus her. Den lastes hver gang, riktig referanse blir lest, og den koster ikke
mer enn å la være. `aksel-builder` ga samme resultat for rundt 40 % flere
credits. Med én økt per oppgave viser tallene retning, ikke mer.

Nytten av `aksel` ligger dermed i øktene som ikke går på Opus, for eksempel når
klienten velger modell selv, og i det pakkene ikke viser: oppgradering, Tailwind
og Figma til kode.

## Det som ikke er løst

- Med Aksel MCP tilkoblet lastes skillen sjeldnere på Haiku. I den lille
  endringen i filen som alt bruker `Alert`, ble den ikke lastet i noen av åtte
  økter, og agenten la til en ny `Alert` i seks av dem. Uten MCP ble den lastet i
  tolv av tolv, og alle ble riktige.
- Designer er bare prøvd i noen få økter. Se
  [baseline for skillvalg](skill-routing-baseline.md).
- To økter per oppgave viser bare store forskjeller.
