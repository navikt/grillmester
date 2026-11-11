# Upgrading and cleaning up old Aksel code

## Find the codemods

Codemods do most of an upgrade. List them; do not recall them.

- With the Aksel MCP server: `aksel_find_docs` with `kind: "migrations"` and a
  query such as `v8`.
- Without it: `https://aksel.nav.no/grunnleggende/kode/codemods-config.md` lists
  the codemods, and the guide for each major version is under Migreringsguider
  in `https://aksel.nav.no/llm.md`. Version 8 is
  `https://aksel.nav.no/grunnleggende/migreringsguider/versjon-8.md`.

Run one with the project's package runner:

```bash
npx @navikt/aksel codemod <name>
```

Start from a clean working tree, so the diff holds only what the codemod did.
Read what it prints: it lists the places it could not change. Then run the
project's type check and tests.

## Version 8

| Old | New | Codemod |
|---|---|---|
| `--a-*` variables and the old token names, also in Tailwind classes | `--ax-*` | `v8-tokens`, named in the version 8 guide but missing from the codemod list |
| `Box` with old token values | new token values | `v8-box` |
| `Box.New`, `BoxNew` | `Box` | `v8-box-new` |
| Numbers as spacing on primitives | `space-*` tokens | `v8-primitive-spacing` |
| Props removed in version 8 | | `v8-prop-deprecate` |
| `List` with `title` and `description` | `Heading` and `BodyShort` beside it | `v8-list` |
| A colour in `variant` | `data-color` | `v8-button-variant`, `v8-tag-variant`, `v8-chips-variant`, `v8-toggle-group-variant`, `v8-accordion-variant`, `v8-link-variant` |
| `.navds-*` classes in your own CSS | `.aksel-*`, or better, your own wrapper | by hand |

Version 8 accepts both a colour in `variant` and `data-color`, so those codemods
can wait. The tokens cannot: the old variables are gone. The new ones start with
`--ax-`, and spacing is named by pixels, so one rem is `--ax-space-16`. The
codemod holds the full table from old names to new.

## Keep to the upgrade that was asked for

A small feature request is not a reason to migrate the app. Mention outdated
code you see, and leave it.
