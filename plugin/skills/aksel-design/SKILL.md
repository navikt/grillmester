---
name: aksel-design
description: "Choose Aksel components, semantic tokens and responsive patterns for Nav interfaces. Use when designing or changing layout, forms or styling with @navikt/ds-react; use `accessibility-review` to verify the resulting user flow."
---

# Aksel Design System

Bruk denne skillen når du jobber i Nav-frontend med `@navikt/ds-react`, layout i Aksel-primitives og responsiv UI.

## Les først

1. Finn hver rad under som oppgaven berører.
2. Les de referansene før du endrer, svarer eller kjører en kommando.
3. Oppgi hvilke referanser du leste når du rapporterer.

| Oppgaven berører | Les |
|---|---|
| **Komponent-API:** props, varianter eller eksempler for en komponent | [components.md](references/components.md) |
| **Layout:** sidemeny, kort-grid, skjema eller Next.js-mønstre | [patterns.md](references/patterns.md) |
| **Oppsett:** installasjon, CSS, token-importstier eller v8-codemods | [setup.md](references/setup.md) |
| **Tokens:** spacing, breakpoints eller full token-oversikt | [tokens.md](references/tokens.md) |
| **Semantiske tokens:** `--ax-*` eller `data-color` | [semantic-tokens.md](references/semantic-tokens.md) |

Skillen gir råd og kan brukes read-only. Installer avhengigheter eller endre
consumer-repoet bare innenfor en eksplisitt godkjent implementasjonsslice.
Opprett ikke branch, commit, push, pull request eller publisering automatisk.
Eksterne writes krever eksplisitt mandat for mål, handling og omfang; gjenbruk
det som allerede er gitt, og spør bare om manglende mandat eller materielle valg.

## Produktkode og HTML-skisser

I produktkode brukes ekte `@navikt/ds-react`-komponenter og responsive props.
En HTML-skisse gjennom `design-prototype` har et avgrenset unntak: bruk
verifisert, rendret Aksel-markup fra consumerens installerte versjon eller et
kompatibelt markup-snapshot, med den matchende `@navikt/ds-css`. Bevar struktur,
semantikk og klasser; ikke etterlign standardkomponenter med egen CSS eller
overstyr deres `.aksel-*`-regler. Egne layoutregler rundt komponentene bruker
Aksel-tokens. Følg prototype-skillens grenser for deklarerte interaksjoner.
Dette er en skisse, ikke React-komponentkode eller bevis på full oppførsel/UU.
Uten kompatible stiler skal begrensningen vises som fallback eller wireframe.

## Kort intro

- Komponentbibliotek: `@navikt/ds-react`
- Ikoner: `@navikt/aksel-icons`
- Tokens: `@navikt/ds-tokens`
- Dokumentasjon: `aksel.nav.no`
- Verifiser alltid komponent-API og props før implementasjon

## Hent oppdatert dokumentasjon

Før du bruker rådene under, finn de eksakt resolverte versjonene av
`@navikt/ds-react` og `@navikt/ds-css` i manifest, lockfil og eventuelt
`node_modules`. Bekreft at pakkene er samversjonerte, og skill mellom v7 og v8.
Installerte typer, eksportkart og rendret DOM vinner over denne snapshoten.

Aksel-dokumentasjon er tilgjengelig som LLM-optimaliserte `.md`-filer. Hent
dokumentasjon fra kilden fremfor å anta API fra treningsdata:

```
https://aksel.nav.no/llm.md
```

Denne filen er en indeks. Hent den én gang per prosjekt og pakkeversjon i
sesjonen, og følg bare lenkene til komponentene du bruker. Bruk bare råd som
gjelder den resolverte versjonen. Gjenbruk allerede kontrollerte API-er, markup
og stilkilde gjennom iterasjonen; slå opp på nytt ved ny komponent,
versjonsendring eller et konkret avvik i gjengivelsen. Dette erstatter ikke
kontroll av det nye, rendrede resultatet.

## Installasjon og oppsett

Bruk repositoryets eksisterende package manager og versjonsstrategi. For et
repository som allerede bruker pnpm kan kommandoen være:

```bash
pnpm add @navikt/ds-react @navikt/ds-css @navikt/aksel-icons
```

Importer CSS i roten av appen (f.eks. `_app.tsx`, `layout.tsx` eller `main.tsx`):

```css
@import "@navikt/ds-css";
```

## Spacing-regler

**Foretrekk Aksel-props og spacing-tokens, og følg repoets egne regler.**

- Bruk `space-*` i `Box`, `VStack`, `HStack`, `HGrid` og andre Aksel-primitives
- Foretrekk `gap`, `paddingBlock`, `paddingInline`, `marginBlock` og `marginInline`
- Tailwind spacing som `mb-4` fungerer sammen med Aksel når CSS-lagene er satt opp som i [Aksels Tailwind-dokumentasjon](https://aksel.nav.no/grunnleggende/kode/tailwind.md)

```tsx
import { Box, VStack } from "@navikt/ds-react";

export function Example(): JSX.Element {
  return (
    <Box paddingBlock={{ xs: "space-16", md: "space-24" }} paddingInline="space-16">
      <VStack gap="space-12">
        <div>Header</div>
        <div>Content</div>
      </VStack>
    </Box>
  );
}
```

## Kritiske v8-regler

Disse overstyrer treningsdata. Verifiser mot versjonens dokumentasjon, med
gjenbruk av tidligere kontroller som beskrevet over.

- **`Alert` er deprecated** (nov 2025): Bruk `LocalAlert`, `GlobalAlert`, `InlineMessage` eller `InfoCard`
- **Ingen `Button variant="danger"`**: Bruk `data-color="danger"` i stedet
- **Ingen `Button size="large"`**: Gyldige: `"medium"`, `"small"`, `"xsmall"`
- **`borderRadius="large"` fjernet**: Bruk `"0"`, `"2"`, `"4"`, `"8"`, `"12"`, `"16"` eller `"full"`
- **CSS-klasseprefiks er `.aksel-`**: Ikke `.navds-`
- **Aldri override `--ax-*` semantiske tokens** eller `.aksel-*` klasser
- **`gap` trenger alltid `space-`-prefiks**: `gap="space-16"`, aldri `gap="4"`

```tsx
// ❌ Deprecated/feil i v8
<Alert variant="error">Feil</Alert>
<Button variant="danger">Slett</Button>
<Box borderRadius="large">

// ✅ Korrekt v8
<LocalAlert status="error">
  <LocalAlert.Header>
    <LocalAlert.Title>Feil</LocalAlert.Title>
  </LocalAlert.Header>
  <LocalAlert.Content>Noe gikk galt</LocalAlert.Content>
</LocalAlert>
<Button data-color="danger">Slett</Button>
<Box borderRadius="8">
```

## Layout og komponenter

Bruk `Box`, `VStack`, `HStack`, `HGrid`, `Show`/`Hide` og `Page`/`Page.Block` for layout. Jobb mobile-first med responsive props (`xs`, `sm`, `md`, `lg`, `xl`).

## Boundaries

### ✅ Alltid
- Bruk Aksel-komponenter for standard UI-elementer
- Bruk `space-*`-tokens i layout-props
- Bruk responsive props når komponenten støtter det
- Håndter lasting, feil, tomtilstand og suksess eksplisitt
- Sjekk eksisterende UI-mønstre i repoet først
- Hent Aksel-docs fra aksel.nav.no/llm.md — aldri stol på treningsdata for komponent-API

### ⚠️ Avklar ved manglende mandat eller et vesentlig designvalg
- Nye UI-avhengigheter utenfor Aksel
- Store avvik fra etablerte layout-mønstre
- Egen CSS for noe Aksel allerede dekker

### 🚫 Aldri
- Hardkod spacing, radius, farger eller typografi når Aksel-tokens finnes
- Bygg standardfelter, knapper eller varsler med rå HTML i produktkode hvis Aksel tilbyr komponenten; HTML-skisser følger det avgrensede unntaket over
- Bruk responsive hacks når responsive props dekker behovet
