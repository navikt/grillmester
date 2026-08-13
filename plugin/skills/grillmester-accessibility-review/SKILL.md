---
name: grillmester-accessibility-review
description: "UU/WCAG-review for Nav-frontend — tastaturflyt, skjermleser, axe, kontrast, fokus, feilmeldinger, skjema og Aksel-bruk. Brukes via /grillmester-accessibility-review før PR eller release."
license: MIT
---
# Tilgjengelighet-review

Review-prosess for universell utforming (UU) i Nav-flater. Offentlig sektor er
omfattet av norske krav til universell utforming av ikt; gjeldende standard og
virkeområde skal alltid verifiseres mot
[Uu-tilsynet](https://www.uutilsynet.no/regelverk/regelverk/149) før juridiske
konklusjoner trekkes. Per siste kildekontroll er WCAG 2.1 nivå A og AA det
forskriftsfestede utgangspunktet. Bruk WCAG 2.2 som en fremoverlent
kvalitetsreferanse når consumerens policy eller risikobilde tilsier det, ikke
som en umerket påstand om gjeldende norsk minstekrav.

## Avgrensning mot consumer-eid policy

Denne skillen er for review-arbeid og større UI-flyter. Ikke anta at pluginen
har installert path-spesifikke instructions. Følg consumerens gjeldende policy
når den finnes; bruk denne skillen for konkrete sjekkpunkter, testoppskrifter
og Nav-spesifikke heuristikker.

Når du koder nytt: følg repoets lokale føringer. Når du skal gjennomgå en diff,
flate eller ekstern leveranse før produksjon: bruk denne skillen. Review er
read-only som standard; publisering av funn eller andre eksterne writes krever
eksplisitt godkjenning.

## Kodemønstre som skal sjekkes

### Semantikk og struktur

- Bruk `<main>`, `<nav>`, `<article>`, `<section>`, `<button>` og `<a>` der semantikken finnes.
- Overskriftsnivåer (`h1`–`h6`) skal følge en logisk hierarkisk struktur uten hopp.
- Dokumentet skal ha riktig `lang` og sidetittel der app-strukturen eier dette.

### Skjema og feil

- Bruk Aksel `TextField`, `Textarea`, `Select`, `Checkbox`, `Radio` og tilsvarende der de finnes.
- Alle felter skal ha synlig label.
- Feltfeil skal være koblet til feltet og være konkrete på klarspråk.
- Flere feil i samme skjema skal samles i `ErrorSummary` øverst.

### Interaksjon

- Alle interaktive elementer skal ha tilgjengelig navn og synlig fokus.
- Ikonknapper skal ha et meningsfullt tilgjengelig navn via synlig tekst,
  `aria-label`, `aria-labelledby` eller komponentens dokumenterte Aksel-API.
  `title` kan være supplerende informasjon, men er ikke tilstrekkelig alene.
- Ikke bruk `<div onClick>` uten rolle, `tabIndex`, tastaturhåndtering og fokusstil.
- Bruk beskrivende lenketekst, ikke "Klikk her".

### Dynamisk innhold

- Loading, feil, tomtilstand og suksess skal annonseres når de påvirker brukerflyten.
- Bruk `aria-live`, `aria-busy` eller Aksel-komponentenes innebygde mønstre der semantikken ikke allerede er dekket.
- Modal, meny og tabs skal ha korrekt fokusrekkefølge og kunne lukkes/navigeres med tastatur.

## Testoppskrifter

### Tastatur

1. Tab gjennom hele endret flyt uten mus.
2. Kontroller at fokus er synlig hele veien.
3. Kontroller at rekkefølgen følger visuell og logisk flyt.
4. Bruk Enter/Space på knapper og lenker.
5. Bruk Escape for modal/meny der relevant.

### `jest-axe`

```tsx
import { axe, toHaveNoViolations } from "jest-axe";

expect.extend(toHaveNoViolations);

it("har ingen automatiske tilgjengelighetsfeil", async () => {
  const { container } = render(<MyComponent />);
  expect(await axe(container)).toHaveNoViolations();
});
```

### Playwright + axe-core

```tsx
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("side har ingen alvorlige tilgjengelighetsfeil", async ({ page }) => {
  await page.goto("/skjema");
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
```

## Bruk Aksel i bunn

Aksel-komponenter (`@navikt/ds-react`) gir testede semantiske mønstre og er som
regel et bedre utgangspunkt enn håndlagde alternativer. De er **ikke** en
garanti for WCAG-samsvar: riktig bruk, innhold og hele sidekonteksten må fortsatt
testes. Første review-spørsmål er: *brukes Aksel-komponenter der det finnes, og
er de brukt riktig i denne flyten?*

Se `grillmester-aksel-design`-skillen for komponentvalg, tokens og mønstre.

## Manuell + automatisk testing

Kombiner automatiske og manuelle metoder fordi de finner ulike feil. Velg et
representativt, risikobasert utvalg av sider og flyter; ikke påstå en fast
dekningsprosent eller testfrekvens uten en autoritativ kilde eller lokal policy.

- **Automatisk:** `axe-core` (via `@axe-core/react` eller Playwright-integrasjon) i CI. Lighthouse for rask sanity-sjekk.
- **Manuell tastatur-test:** Tab gjennom hele flyten uten mus. Fokus skal være synlig, rekkefølgen logisk, ingen feller.
- **Skjermleser-test:** NVDA (Windows) eller VoiceOver (macOS/iOS) på minst én kritisk flyt. JAWS for eksterne revisjoner.
- **Zoom og reflow:** 200 % zoom og 400 % (reflow-krav), samt tekstavstand per WCAG 1.4.10/1.4.12.
- **Farger:** Kontrast gjennom Aksel-tokens; verifiser med devtools dersom custom farger brukes.

## Klarspråk er tilgjengelighet

Nav skriver for folk i sårbare situasjoner. Klart språk er avgjørende for at
innhold og handlinger kan forstås, men WCAG 3.1.5 kan ikke brukes som en
universell etikett på all uklar tekst. Vurder suksesskriteriet mot faktisk
målgruppe og innhold; gjør uansett feilmeldinger, labels og hjelpetekst konkrete
og handlingsrettede. Se `grillmester-klarsprak`-skillen.

## Hvem tester

- **Teamet selv:** test den endrede eller mest risikoutsatte flyten med relevante
  automatiske og manuelle metoder. Consumerens policy bestemmer hvilke checks
  som er obligatoriske per PR.
- **Fagressurs/designer:** involver ved større eller komplekse flyter.
- **Uavhengig faglig review:** vurder ved nye eller vesentlig endrede tjenester
  og ellers ut fra risiko, regelverk og consumerens revisjonsplan.
- **Brukertesting med assistive teknologier** bør inngå i større leveranser — ikke alt fanges av heuristikker.

## Review-sjekkliste

- [ ] Aksel-komponenter brukt der det finnes tilsvarende
- [ ] `axe-core` uten `serious`/`critical` funn på endrede sider
- [ ] Full tastatur-gjennomgang av endret flyt
- [ ] Skjermleser-test på nye eller endrede skjemaer og modaler
- [ ] Synlig fokus og logisk fokus-rekkefølge
- [ ] Feilmeldinger er koblet til felt (`aria-describedby`) og på klarspråk
- [ ] Logisk overskriftshierarki (`h1`–`h6`) uten hopp
- [ ] Språk-attributt (`lang="nb"`) og korrekt dokumenttittel
- [ ] Kontrast og reflow ved 200/400 % zoom
- [ ] Kjente avvik er vurdert mot løsningens gjeldende tilgjengelighetserklæring
      og consumerens publiseringsansvar

## Kilder

- [uutilsynet.no](https://www.uutilsynet.no) — tilsyn, regelverk, tilgjengelighetserklæring
- [WCAG 2.2](https://www.w3.org/TR/WCAG22/) — W3C-standard; vurder 2.2-suksesskriterier der relevant (forskriftskravet er per i dag 2.1 A/AA — verifiser mot uutilsynet.no)
- [Aksel: frontend-kode og tilgjengelighet](https://aksel.nav.no/god-praksis/artikler/utvikling) — komponenter må brukes og testes i kontekst
- [Aksel: Test less!](https://aksel.nav.no/god-praksis/artikler/test-less) — representativ og risikobasert testing
- [WCAG-EM](https://www.w3.org/TR/WCAG-EM/) — metodikk for eksterne revisjoner
