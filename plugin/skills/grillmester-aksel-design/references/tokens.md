# Tokens

Denne hurtigreferansen er kontrollert mot Aksel 8.16.1. Consumerens resolverte
pakker, typer og live-dokumentasjon er alltid autoritative.

## Spacing-skala for props (`space-*`)

Bruk disse tokenene i Aksel-props som `gap`, `padding`, `paddingInline`, `paddingBlock`, `margin`, `marginInline` og `marginBlock`.

| Token | Verdi |
|---|---:|
| `space-0` | 0px |
| `space-1` | 1px |
| `space-2` | 2px |
| `space-4` | 4px |
| `space-6` | 6px |
| `space-8` | 8px |
| `space-12` | 12px |
| `space-16` | 16px |
| `space-20` | 20px |
| `space-24` | 24px |
| `space-28` | 28px |
| `space-32` | 32px |
| `space-36` | 36px |
| `space-40` | 40px |
| `space-44` | 44px |
| `space-48` | 48px |
| `space-56` | 56px |
| `space-64` | 64px |
| `space-72` | 72px |
| `space-80` | 80px |
| `space-96` | 96px |
| `space-128` | 128px |

## Legacy migreringstabell (pre-v7 → v7)

> **Merk**: Denne migrasjonsguiden dekker pre-v7 (`--navds-*`) til v7
> (`--a-spacing-*` / `--a-border-radius-*`). For v7 → v8, bruk de aktuelle
> codemodene i [setup.md](setup.md), ikke denne legacy-tabellen.

Bruk denne tabellen bare når du rydder i eldre CSS-variabler. For
komponent-props bruker du `space-*` og radiusverdier i prop-API-et. Dagens v8
CSS-eksempler lenger ned bruker `--ax-*`; `--a-*` hører til v7-delen.

### Spacing-variabler (legacy)

| Pre-v7 | v7 |
|---|---|
| `--navds-spacing-1` | `--a-spacing-1` |
| `--navds-spacing-2` | `--a-spacing-2` |
| `--navds-spacing-4` | `--a-spacing-4` |
| `--navds-spacing-8` | `--a-spacing-8` |
| `--navds-spacing-12` | `--a-spacing-12` |
| `--navds-spacing-16` | `--a-spacing-16` |
| `--navds-spacing-20` | `--a-spacing-20` |
| `--navds-spacing-24` | `--a-spacing-24` |
| `--navds-spacing-32` | `--a-spacing-32` |

### Radius-variabler (legacy)

| Pre-v7 | v7 |
|---|---|
| `--navds-border-radius-small` | `--a-border-radius-small` |
| `--navds-border-radius-medium` | `--a-border-radius-medium` |
| `--navds-border-radius-large` | `--a-border-radius-large` |
| `--navds-border-radius-xlarge` | `--a-border-radius-xlarge` |
| `--navds-border-radius-full` | `--a-border-radius-full` |

## Border radius

| `Box borderRadius` | CSS-variabel | Verdi |
|---|---|---:|
| `"0"` | – | 0px |
| `"2"` | `--ax-radius-2` | 2px |
| `"4"` | `--ax-radius-4` | 4px |
| `"8"` | `--ax-radius-8` | 8px |
| `"12"` | `--ax-radius-12` | 12px |
| `"16"` | `--ax-radius-16` | 16px |
| `"full"` | `--ax-radius-full` | 9999px |

Det finnes ikke et `radius-0`-token.

## Brytepunkter

Aksel responsive props bygger på disse breakpointene:

| Token | Verdi | Typisk bruk |
|---|---:|---|
| `xs` | 0px | Mobil som standard |
| `sm` | 480px | Stor mobil / lite nettbrett |
| `md` | 768px | Nettbrett / liten desktop |
| `lg` | 1024px | Desktop |
| `xl` | 1280px | Bred desktop |

Det finnes også `2xl` (1440px) i tokenlaget, men de fleste layout-eksempler i repoet bruker `xs` til `xl`.

## Semantiske tokens

Vanlige v8-valg er `--ax-bg-default`, `--ax-bg-neutral-soft`,
`--ax-border-neutral-subtle`, `--ax-border-neutral`, `--ax-text-neutral` og
`--ax-text-neutral-subtle`. Se [semantic-tokens.md](semantic-tokens.md) og den
installerte pakkens eksport for resten; ikke cache fargeverdiene her.

## CSS-variabler

> **Merk**: Sjekk faktisk installert Aksel-major og eksporterte tokens i
> prosjektet. Eksemplene under er v8 og bruker `--ax-*`. Behold `--a-*` bare
> når repositoryet fortsatt er på v7.

Når du må skrive CSS, bruk Aksel sine variabler direkte og hold prop-token og CSS-variabel i samme familie.

### Spacing
- `space-4` i prop-API ↔ `var(--ax-space-4)` i CSS
- `space-16` i prop-API ↔ `var(--ax-space-16)` i CSS
- `space-24` i prop-API ↔ `var(--ax-space-24)` i CSS
- `space-40` i prop-API ↔ `var(--ax-space-40)` i CSS
- `space-128` i prop-API ↔ `var(--ax-space-128)` i CSS

### Surface / border / text
- `var(--ax-bg-default)`
- `var(--ax-bg-neutral-soft)`
- `var(--ax-border-neutral-subtle)`
- `var(--ax-border-neutral)`
- `var(--ax-text-neutral)`
- `var(--ax-text-neutral-subtle)`

### Brytepunkter

Variablene `--ax-breakpoint-*` finnes, men CSS custom properties kan normalt
ikke brukes i selve betingelsen til en media query. Bruk responsive prop-aliaser
(`sm`, `md`, `lg`, `xl`, `2xl`) eller statiske verdier fra den installerte
`@navikt/ds-tokens`-eksporten i `@media (...)`.

## Tommelfingerregler

- I React-props: bruk `space-*` og responsive objekt-props
- I v8-CSS: bruk `var(--ax-space-*)`, `var(--ax-radius-*)` og semantiske
  tokens som den installerte pakken faktisk eksporterer
- Foretrekk semantiske surface-/text-/border-tokens foran rå farger
