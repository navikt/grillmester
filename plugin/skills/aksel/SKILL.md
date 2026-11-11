---
name: aksel
description: "Build and change Nav user interface with Aksel (`@navikt/ds-react`). Aksel retires components that still compile, such as `Alert`, `Panel`, `LinkPanel` and `ConfirmationPanel`, so load this before writing or changing code that imports an `@navikt/ds-*` or `@navikt/aksel-*` package, before calling an `aksel_*` tool, before answering how to set up or use Aksel, its tokens or Tailwind, before an upgrade, and before turning a Figma design into code. Use `design-prototype` to explore a design and `accessibility-review` to review a finished flow."
---

# Aksel

The installed packages decide which names exist. Aksel's documentation decides
how they are meant to be used. The rules here cover what neither shows when you
write from memory.

## Read first

1. Find every row below that the task touches.
2. Read that reference before you edit, answer or run a command.
3. Name the references you read when you report.

| The task touches | Read |
|---|---|
| **Figma:** a Figma link or frame to turn into code | [figma-to-code.md](references/figma-to-code.md) |
| **Upgrade:** a new major version, `--a-` variables, `.navds-` classes, a codemod, or old Aksel code to clean up | [migration.md](references/migration.md) |
| **Tailwind:** setting it up with Aksel, or an Aksel class name. A class is the utility, `ax` and the whole token name: `bg-ax-bg-accent-strong`, `text-ax-text-danger` | `https://aksel.nav.no/grunnleggende/kode/tailwind.md` |
| **Form validation:** error messages, an error summary, or a multi-step application | `https://aksel.nav.no/monster-maler/soknadsdialog/monster-for-skjemavalidering.md` |

A row with an address is a page in Aksel's documentation. Fetch it, or read it
with `aksel_get_doc` when the Aksel MCP server is connected.

## Rules that override memory

These rules describe version 8. On an older major version the installed types
decide: use the names that version exports, and upgrade only when asked.

1. **Retired components still compile.** They are exported and typed, so nothing
   warns you, and older code in the same project often still uses them. Before
   you use a component, open its `.d.ts` under
   `node_modules/@navikt/ds-react/esm/` and look for `@deprecated`; the comment
   names the replacement. New code uses the replacement even when the file beside
   it uses the retired component. Leave existing uses alone unless the task is to
   migrate them. In version 8 that means:

   | Retired | Use |
   |---|---|
   | `Alert` | `LocalAlert` for an event in part of the page, placed near it; `GlobalAlert` for an event that affects the whole service, at the top; `InlineMessage` for a short status inside the content; `InfoCard` to highlight information that is not an alert |
   | `LinkPanel` | `LinkCard` |
   | `Panel`, `Box.New` | `Box` |
   | `ConfirmationPanel` | `Checkbox` |
   | `Ingress` | `BodyLong size="large"` |

2. **Colour is `data-color`, emphasis is `variant`.** Write
   `<Button variant="primary" data-color="danger">`, not `variant="danger"`. The
   same split applies to `Tag`, `Chips`, `ToggleGroup`, `Accordion` and `Link`.
3. **A compound component's parts come two ways.** From the package root you
   write `LocalAlert.Content`. The named part `LocalAlertContent` exists only on
   the component's own entry point, `@navikt/ds-react/LocalAlert`, which is the
   form a Server Component needs.
4. **Dark mode is the `Theme` component.** Wrap the content in
   `<Theme theme="dark">`; do not set a class or an attribute of your own.

## Look it up, then write

1. Read the installed version in `node_modules/@navikt/ds-react/package.json`.
   Its exports and types decide what exists, so check every name you have not
   already confirmed in this session.
2. For which component fits, how it is composed and what a prop means, read
   Aksel's documentation:
   - With the Aksel MCP server: `aksel_find_docs` for the page, then
     `aksel_get_doc` or `aksel_get_component_info`; `aksel_get_token_details`
     for a token; `aksel_find_icons` for an icon.
   - Without it: fetch the index `https://aksel.nav.no/llm.md`, then the one
     `.md` page you need.

   Take every path from the search result or the index. A path you construct
   returns the wrong page or nothing. Leave the collection pages such as
   `komponenter.md` alone; that one is about a megabyte.
3. The documentation describes the newest release. Where it differs from the
   installed package, the installed package wins, and you say so.
4. Answer a question about setup, or about how something is meant to be used,
   from the documentation page. The installed files show what exists, not what
   Aksel recommends.

## Before you finish

Run the project's type check and lint on the files you changed, and fix what
your change introduced. Name the sources you used and anything you could not
confirm.
