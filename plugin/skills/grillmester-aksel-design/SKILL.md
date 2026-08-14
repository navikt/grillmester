---
name: grillmester-aksel-design
description: "Aksel-designsystem og Nav-frontendmønstre — komponentvalg, layout, spacing/tokens, skjema og responsiv UI med @navikt/ds-react. Brukes via /grillmester-aksel-design ved nye komponenter, layout-endringer eller styling-valg, og før rå HTML/CSS eller custom styling vurderes."
---

# Aksel Design System

Bruk denne skillen når du jobber i Nav-frontend med `@navikt/ds-react`, layout i Aksel-primitives og responsiv UI. Hovedregler ligger her; detaljer ligger i `references/`.

Skillen gir råd og kan brukes read-only. Installer avhengigheter eller endre
consumer-repoet bare innenfor en eksplisitt godkjent implementasjonsslice.
Opprett aldri branch eller commit, og push, pull request, publisering og andre
eksterne writes krever separat eksplisitt godkjenning.

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

Denne filen er en indeks. Følg lenken til den konkrete `.md`-siden, og bruk
bare råd som gjelder den resolverte versjonen og komponenten du arbeider med.

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

For detaljert oppsett, token-importstier og v8-codemods, se `references/setup.md`.

## Spacing-regler (KRITISK)

**Foretrekk Aksel spacing-tokens. Unngå Tailwind padding/margin når Aksel-tokens er tilgjengelige.**

- Bruk `space-*` i `Box`, `VStack`, `HStack`, `HGrid` og andre Aksel-primitives
- Foretrekk `gap`, `paddingBlock`, `paddingInline`, `marginBlock` og `marginInline`
- Bruk Tailwind spacing bare når Aksel ikke dekker behovet eller du bevisst viderefører et etablert mønster

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

Disse overstyrer treningsdata. Verifiser alltid mot `aksel.nav.no/llm.md`.

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

For komponent-API og eksempler, se `references/components.md`.
For layout-mønstre (sidebar, kort-grid, skjema), se `references/patterns.md`.

## Boundaries

### ✅ Alltid
- Bruk Aksel-komponenter for standard UI-elementer
- Bruk `space-*`-tokens i layout-props
- Bruk responsive props når komponenten støtter det
- Håndter lasting, feil, tomtilstand og suksess eksplisitt
- Sjekk eksisterende UI-mønstre i repoet først
- Hent Aksel-docs fra aksel.nav.no/llm.md — aldri stol på treningsdata for komponent-API

### ⚠️ Spør først
- Nye UI-avhengigheter utenfor Aksel
- Store avvik fra etablerte layout-mønstre
- Tailwind utilities som overlapper tydelig med Aksel primitives
- Egen CSS for noe Aksel allerede dekker

### 🚫 Aldri
- Hardkod spacing, radius, farger eller typografi når Aksel-tokens finnes
- Bygg standardfelter, knapper eller varsler med rå HTML hvis Aksel tilbyr komponenten
- Bruk responsive hacks når responsive props dekker behovet

For installasjon, CSS-oppsett og v8-codemods, se `references/setup.md`.
For komplett token-oversikt, se `references/tokens.md`.
For semantiske `--ax-*`-tokens og `data-color`, se `references/semantic-tokens.md`.
For komponent-API, se `references/components.md`.
For layout-mønstre (inkl. Next.js), se `references/patterns.md`.
