# Provenance

This repository owns the operative Grillmester package content: the standard
agent team under `plugin/` and the optional, skills-only NAV add-on under
`plugin-nav/`. The sources below record attribution and the reviewed import
boundary. They are not runtime dependencies and do not create a synchronization
relationship.

The authoritative component-by-component bill of materials is
[`policy/content-lock.json`](policy/content-lock.json). It records every agent
and skill, its source path, its reviewed disposition, and the exact source
revision.

Agent IDs preserve their reviewed source names. Runtime skill IDs are prefixed
with `grillmester-` to reduce accidental collisions. A project- or user-level
component with the same exact ID still wins and can silently shadow the plugin
payload; qualification is not a bypass. The source names below remain
unprefixed so the import boundary can be audited directly; the content lock
records the canonical runtime IDs and their original `sourcePath` values.

## Pilot baseline

Source: `navikt/syfo-budstikka` at
`1fd62c10dc9608a0f34b600a5cec19648167a15d`.

The agent and skill trees are byte-identical on that repository's separately
reviewed `origin/main` revision
`763d19a569bee4908b8f6dc827629f69f1e2fcaa`.

Imported agents:

- `grillmester`, `barista`, `kokk`, `grill-inspektor`, `researcher`

Imported skills:

- `api-design`, `architecture-review`, `auth-overview`, `create-a-skill`,
  `diagnosing-bugs`, `domain-modeling`, `e2e-tests`, `grill-me`,
  `grill-with-docs`, `grilling`, `handoff`,
  `improve-codebase-architecture`, `integration-tests`, `issue-management`,
  `kafka-topic`, `klarsprak`, `kotlin-ktor`, `nais-manifest`,
  `nav-troubleshoot`, `observability-setup`, `postgresql-review`, `prototype`,
  `pull-request`, `readme-update`, `review`, `security-review`, `tdd`,
  `to-issues`, `to-spec`, `triage`, `wayfinder`

The portable adaptation preserves the pilot's role split, risk routing,
one-writer boundary, specification and ADR workflows, deterministic evidence,
independent review, and progressive skill resources. It removes only
Budstikka-specific package names, file paths, build commands, runtime facts,
data classifications, repository instructions, issue routing, and deployment
assumptions. Cross-component calls are plugin-qualified where required.

## Hovmester additions

Source: `navikt/hovmester` at
`48483bf32c2b6f89c31e7d50e25b5fe6fac45ca2`.

The pinned source did not contain an explicit license file. Git history for the
exact imported paths records Audun Sørheim as the sole human author, plus
automation. Audun, as contributing maintainer, explicitly approved reuse and
public POC distribution of those paths in Grillmester on 2026-08-13. This is a
recorded POC authorization, not a substitute for final organizational rights
and brand review. Before stable promotion, the repository owner must record
the relevant NAV rights-holder approval or replace material whose terms cannot
be established. The public agent name and characterization “Doctor Who” also
requires a NAV legal/brand decision or a rename before stable promotion.

Imported agents:

- `designer`, `doctor-who`

Hovmester's internal `konditor` agent and Designer's delegated source-code
prototype phase are intentionally excluded. Grillmester's Designer ends at
visual exploration, Figma, and an optional development Issue; implementation
starts only through a separate user-initiated Barista or Grillmester workflow.

Imported skills:

- `accessibility-review`, `aksel-design`, `figma-workflow`,
  `nav-architecture-review`, `okr`, `produktledelse`, `team-status`,
  `workshop-design`, `dulting`, `kotlin-spring`, `lumi-survey`
- Hovmester's visual `prototype` workflow is imported as `design-prototype`;
  the pilot's behavior-oriented `prototype` retains its original ID.

The portable adaptation keeps the design, Aksel, Figma, product, workshop,
team-status, architecture, and visual-prototype workflows. It removes ambient
repository synchronization, fixed Team eSyfo repositories or project boards,
template placeholders, and automatic external writes. Figma, GitHub, and
delivery side effects require an explicit
preview and approval. All four public roles intentionally inherit the
runtime's broad tool surface, matching the piloted Hovmester/Budstikka model
and avoiding a drifting matrix of client-specific aliases. Their behavioral
contracts remain narrower: neither Designer nor Doctor Who delegates; Doctor
Who does not use shell commands, and Designer's edit/execute use is limited to the
bundled Visual Companion server and the exact private `screen_dir` path returned
by its active startup JSON. Technical containment and approval remain client-
and enterprise-owned; see `docs/runtime-safety.md`.

### Visual Companion lineage

Hovmester's Visual Companion was derived from the brainstorming workflow in
`obra/superpowers`. The exact historical upstream revision used by Hovmester was
not recorded, so this repository does not invent one. The implementation and
license boundary were reviewed against `obra/superpowers` at
`44c9b2d6e889982ac18c27d05a19fefe335194e1`, specifically the
`skills/brainstorming` skill and its Visual Companion resources.

Grillmester keeps its independently hardened server: loopback-only networking,
session tokens, strict Host/Origin checks, a sandboxed opaque iframe, CSP without
external network access, private OS-temp state, bounded opaque events and
marker-bound cleanup. From the reviewed upstream it adopts the useful lifecycle
and interaction ideas—just-in-time visual use, readiness checks, paused-state
feedback, per-screen event isolation and an idle timeout that polling cannot keep
alive—without copying remote binds, repository state, generic file serving,
external assets or raw event text. See the full MIT notice in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

### Aksel generated-reference lineage

The generated component markup and icon reference material is based on
`@navikt/ds-react@8.12.0` and `@navikt/aksel-icons@8.12.0`. Both packages point
to `navikt/aksel` revision
`59ebc666cfa4a78945c293f546d0d8121abfbfec` and are distributed under the MIT
license, Copyright 2025 Nav (Arbeids- og velferdsdirektoratet). Grillmester's
snapshots are reference material, not an authoritative replacement for the
live Aksel libraries; the complete notice is included in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Consumer-owned material

Budstikka's `copilot-instructions.md` and path-scoped language, security, and
GitHub Actions instructions are deliberately not plugin components. Their
portable methods are represented in agents and skills; repository identity,
commands, language mappings, security facts, and path-specific invariants stay
with each consumer.

Hovmester collections, sync workflows, generated mirrors, repository forms,
and consumer templates are distribution or repository infrastructure and are
not part of either plugin payload. The issue and PR templates in this source
repository govern contributions to `navikt/grillmester`; they are not shipped
to consumers.

`grillmester-doctor` consolidates the reviewed ownership boundary from the
pinned Budstikka and Hovmester instruction sources into a read-only audit. It
does not copy their repository facts, create consumer files, or establish a
continuing synchronization relationship.

## Visual identity

`docs/assets/grillmester-hero.jpg` and `docs/assets/grillmester-avatar.png` are
original artwork generated for this repository with OpenAI image generation
and selected by the maintainers. No source image or third-party character asset
was used.

Reviewed SHA-256 digests:

- `grillmester-hero.jpg`: `4699ba58533d68d088e5767aaad10390991f43810aeb6fb5799e665c750daffb`
- `grillmester-avatar.png`: `25fedb436679b5dcd5b7d79741ea61d93e73f9ad6577a8ed85d6ce499fe2122b`

## Third-party lineage

Several pilot skills were originally copied or adapted from
`mattpocock/skills` at
`2ab958093e83e0ec752e6c1c5932da465bf23e0c`. They remain subject to that
project's MIT license; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

The UI prototype guidance was also compared with current `mattpocock/skills` at
`84fdeffd12f2ee307994d1eb6feb48173b6e0502`. Its relevant
`skills/engineering/prototype/UI.md` is byte-identical to the already reviewed
revision above. Grillmester therefore
keeps the existing source pin while applying the reviewed principles of one
named design question, structurally distinct alternatives, comparable synthetic
data and an explicit record of the winner, rationale and borrowed elements.

When imported material changes, update the content lock and this document in
the same change. Advancing a source revision means reviewing the concrete
upstream diff; changing only the recorded pin is insufficient.
