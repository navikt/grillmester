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

De 16 oppgavene er varsel og rød knapp, ikonknapp, layout med sidemeny og kort,
egen CSS, skjema med feiloppsummering, søkbart nedtrekk, mørk modus, migrering
fra `--a-`-variabler, Tailwind 4, Server Component med dialog, en Figma-lenke
uten Figma-verktøy, lenkekort, ramme med tokens, melding om at hele tjenesten er
nede, en ny melding i filen som bruker `Alert`, og mer avrundede knapper.

Fire forbehold:

- Sjekkene er grove og fanger ikke alt som gjør en løsning god.
- Måleskriptet ligger ikke i repoet. Tallene kan derfor ikke kjøres på nytt
  herfra uten å bygge det opp igjen.
- Engangsrepoet har ikke `@navikt/ds-tokens`. Typesjekken en økt selv kjører,
  fanger derfor ikke et spacing-token som ikke finnes.
- En økt blir stoppet etter 28 verktøykall. Den telles ut fra filene den rakk å
  skrive.

Tabellene teller to økter per oppgave, så hver oppgave veier like mye.
Til sammen er det kjørt 379 slike økter på Haiku 5.5 og 14 på Opus 5.5.

## Haiku 5.5

Haiku er brukt som en billig stresstest, for å finne det som ryker. På de elleve
oppgavene alle variantene er målt på:

| Variant | Sjekker bestått | Økter der alt var riktig | Lastet skillen |
| --- | --- | --- | --- |
| Uten Aksel-skill | 53/58 (91 %) | 18/22 | – |
| `aksel-builder` fra `navikt/copilot` | 54/58 (93 %) | 20/22 | 7/22 |
| `aksel-builder` med Aksel MCP | 56/58 (97 %) | 20/22 | 3/22 |
| `aksel` med åtte regler | 58/58 (100 %) | 22/22 | 17/22 |
| `aksel`, den endelige teksten | 57/58 (98 %) | 21/22 | 19/22 |

De fem siste oppgavene kom til underveis, fordi de første var for lette. De
handler mest om avviklede komponenter. Med dem er tallene:

| Variant | Økter | Sjekker bestått | Økter der alt var riktig | Ingen avviklet komponent |
| --- | --- | --- | --- | --- |
| Uten Aksel-skill | 32 | 72/88 (82 %) | 23/32 | 5/12 |
| `aksel` med åtte regler | 30 | 84/84 (100 %) | 30/30 | 12/12 |
| `aksel`, den endelige teksten | 32 | 84/88 (95 %) | 30/32 | 11/12 |

Varianten med åtte regler er ikke kjørt på oppgaven med avrundede knapper. Den ble
lastet i 24 av 30 økter, og den endelige teksten i 26 av 32.

Den endelige teksten har tre regler. Fem ble tatt ut etter kjøringen med åtte:

- Tre hadde ingen målt effekt. En variant uten dem besto 26 av 26 sjekker på de
  fem oppgavene de gjaldt.
- Regelen om Aksels egne klasser trengtes ikke. Uten skill var begge øktene
  riktige.
- Regelen om at mørk modus er `Theme`-komponenten, stemte ikke med Aksels egen
  dokumentasjon, som også beskriver klassene `light` og `dark`. Den ble erstattet
  av en rad i Les først som peker til Aksels side om tema.

To økter med den endelige teksten feilet:

- I layoutoppgaven skrev én økt `marginBlock="space-24 0"`. Typene i Aksel godtar
  ikke `0` alene, men et eksempel i pakkens egen kommentar viser den formen. Uten
  skill var begge øktene riktige her, så dette er én glipp, ikke en virkning av
  regelen som ble tatt ut.
- I filen som alt bruker `Alert`, lastet én økt ikke skillen og la til en ny
  `Alert`. Seks økter til på samme oppgave ga det samme i én av dem. Med den
  endelige teksten ble det altså riktig i seks av åtte økter, mot tolv av tolv i
  de tidligere variantene.

Fire økter med den endelige teksten ble stoppet på 28 verktøykall: begge i
skjemaoppgaven, én i søkbart nedtrekk og én i Server Component. Filene de rakk å
skrive, besto sjekkene. Uten skill ble ingen stoppet. Skillen gir i snitt tre
verktøykall mer per økt på Haiku, det samme som `aksel-builder`.

## Hva som endret tallene

- **Uten skill** slår agenten opp i `node_modules` og klarer det meste. Den
  bruker `Alert` fordi den fortsatt eksporteres. I de tre oppgavene som ber om en
  melding, kom en avviklet komponent inn i åtte av åtte økter.
- **`aksel-builder`** retter feilene når den lastes, men den ble sjelden lastet.
  Med Aksel MCP tilkoblet brukte agenten et `aksel_*`-verktøy i 12 av 28 økter og
  lastet skillen i 3. I 15 økter brukte den ingen av delene.
- **Fellen i beskrivelsen.** Beskrivelsen av `aksel` navngir de avviklede
  komponentene, og den er alltid i kontekst. Det hjelper, men ikke alene: i
  meldingsoppgavene der skillen ikke ble lastet, unngikk agenten avviklede
  komponenter i fire av seks økter uten MCP og tre av ti med.
- **Utløseren i Grillmester-prompten.** Da prompten ba om skillen før en fil som
  importerer `@navikt/ds-react`, ble den lastet i 24 av 24 økter på seks oppgaver
  og 28 av 28 på sju. På alle femten oppgavene ga den ordlyden 37 av 44. Den
  endelige ordlyden gjelder frontendkode og stiler i hele prosjektet og ga 24 av
  30 og 26 av 32. Forskjellen mellom de to ordlydene er innenfor støyen.
- **Regler fra feil.** Regel 1, om avviklede komponenter, hviler på mange økter.
  Regel 2, om `data-color`, og regel 3, om navngitte deler som
  `LocalAlertContent`, hviler på én feilende økt hver. Raden om Tailwind kom etter
  en økt som fant på et klassenavn.

## Opus 5.5

Grillmester og Designer bruker Opus 5.5, så det er denne modellen som teller.
Fem oppgaver, én økt hver: ny melding i filen som bruker `Alert`, varsel og rød
knapp, tjenesten er nede, Tailwind 4 og migrering. Disse øktene gikk med
varianten med åtte regler.

| Variant | Riktig | Lastet skillen | Credits |
| --- | --- | --- | --- |
| Uten Aksel-skill | 5/5 | – | 107 |
| `aksel` med åtte regler | 5/5 | 5/5 | 99 |

På de tre oppgavene `aksel-builder` også ble kjørt på:

| Variant | Riktig | Lastet skillen | Credits |
| --- | --- | --- | --- |
| Uten Aksel-skill | 3/3 | – | 69 |
| `aksel-builder` | 3/3 | 3/3 | 78 |
| `aksel` med åtte regler | 3/3 | 3/3 | 56 |

Den endelige teksten er kjørt i én økt på Opus, på oppgaven med filen som bruker
`Alert`. Skillen ble lastet, den nye meldingen ble `LocalAlert`, den gamle
`Alert` sto urørt, og økten kostet 25 credits.

Opus klarer disse oppgavene uten skill. Den leser de installerte typene, ser
`@deprecated` og velger erstatningen. Skillen endrer altså ikke resultatet på
Opus her. Den ble lastet i seks av seks økter, riktig referanse ble lest i
migreringsoppgaven, og den kostet ikke mer enn å la være. `aksel-builder` ga
samme resultat for rundt 40 % flere credits enn `aksel`. Med én økt per oppgave
viser tallene retning, ikke mer.

Nytten av `aksel` ligger dermed i øktene som ikke går på Opus, for eksempel når
klienten velger modell selv, og i det modellen ikke kan lese ut av pakkene:
oppgradering, oppsett av Tailwind og Figma til kode.

## Det som ikke er løst

- Haiku laster skillen i rundt åtte av ti økter. Når den ikke lastes i en fil som
  alt bruker en avviklet komponent, kopierer agenten den.
- Med Aksel MCP tilkoblet lastes skillen sjeldnere på Haiku: i 20 av 34 økter på
  sju oppgaver. I den lille endringen i filen som alt bruker `Alert`, ble den
  ikke lastet i noen av åtte økter, og agenten la til en ny `Alert` i seks av dem.
  Uten MCP ble den lastet i 18 av 20, og de 18 ble riktige.
- Den endelige teksten er kjørt i én økt på Opus, og ikke med Aksel MCP.
- Designer er bare prøvd i noen få økter. Se
  [baseline for skillvalg](skill-routing-baseline.md).
- To økter per oppgave viser bare store forskjeller.
