# HTML report format

The architecture review is rendered as one self-contained HTML file in the OS temp directory. Tailwind and Mermaid are both fetched from CDN. Mermaid handles graph-shaped diagrams reliably; hand-built `<div>`s and inline SVG handle the more editorial visuals (mass diagrams, cross-sections). Mix the two — do not lean on Mermaid for everything, that is when it starts to look generic.

## Scaffold

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Architecture review — {{repo-name}}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script type="module">
      import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
      mermaid.initialize({ startOnLoad: true, theme: "neutral", securityLevel: "loose" });
    </script>
    <style>
      /* a small custom layer for what Tailwind does not cover cleanly:
         dashed seam lines, hand-drawn arrowheads and so on. */
      .seam { stroke-dasharray: 4 4; }
      .leak { stroke: #dc2626; }
      .deep { background: linear-gradient(135deg, #0f172a, #1e293b); }
    </style>
  </head>
  <body class="bg-stone-50 text-slate-900 font-sans">
    <main class="max-w-5xl mx-auto px-6 py-12 space-y-12">
      <header>...</header>
      <section id="candidates" class="space-y-10">...</section>
      <section id="top-recommendation">...</section>
    </main>
  </body>
</html>
```

## Header

Repo name, date and a compact legend: solid box = module, dashed line = seam, red arrow = leak, thick dark box = deep module. No introductory paragraph — straight into the candidates.

## Candidate cards

The diagrams carry the weight. Prose is sparse, plain, and uses the vocabulary (module, interface, depth, seam, adapter, locality, leverage) without ceremony.

Each candidate is one `<article>`:

- **Title** — short, names the deepening (e.g. "Merge the notification-ingest chain").
- **Badge row** — recommendation strength (`Strong` = emerald, `Worth exploring` = amber, `Speculative` = slate), plus a tag for the dependency category (`in-process`, `locally-substitutable`, `ports & adapters`, `mock`).
- **Files** — monospaced list, `font-mono text-sm` using paths discovered in the target repository.
- **Before/after diagram** — the centerpiece. Two columns side by side. See the patterns below.
- **Problem** — one sentence. What hurts.
- **Solution** — one sentence. What changes.
- **Benefits** — bullets, ≤6 words each. E.g. "Tests hit one interface", "Authentication stops leaking", "Delete 4 shallow wrappers".
- **ADR callout** (if relevant) — one line in a yellow-tinted box.

No explanatory paragraphs. If the diagram needs a paragraph to be understood, draw the diagram again.

## Diagram patterns

Pick the pattern that fits the candidate. Mix them. Do not let every diagram look the same — variation is part of the point.

### Mermaid graph (the workhorse for dependencies / call flow)

Use `flowchart` or `graph` when the point is "X calls Y calls Z, look at the mess". Wrap it in a Tailwind-styled card. Style with `classDef` to color leaking edges red and the deep module dark. A sequence diagram works well for "before: 6 round trips; after: 1".

```html
<div class="rounded-lg border border-slate-200 bg-white p-4">
  <pre class="mermaid">
    flowchart LR
      A[Request entry point] --> B[Coordinator]
      B --> C[Persistence adapter]
      C -.leak.-> D[External client]
      classDef leak stroke:#dc2626,stroke-width:2px;
      class C,D leak
  </pre>
</div>
```

### Hand-built boxes-and-arrows (when Mermaid's layout fights you)

Modules as `<div>`s with borders and labels. Arrows as inline SVG `<line>`/`<path>` positioned absolutely over a relative container. Use this when the "after" diagram should feel like one thick-bordered deep module with dimmed internal parts.

### Cross-section (good for layered shallowness)

Stack horizontal bands (`h-12 border-l-4`) to show the layers a call passes through. Before: 6 thin layers that each do nothing (Route → Service → Mapper → Repository → Client → DTO). After: 1 thick band with the consolidated responsibility.

### Mass diagram (good for "interface as wide as the implementation")

Two rectangles per module — one for interface surface, one for implementation. Before: the interface rectangle is almost as tall as the implementation (shallow). After: the interface is short, the implementation tall (deep).

### Call-graph collapse

Before: a tree of function calls as nested boxes. After: the same tree collapsed into one box, with the now-internal calls dimmed inside.

## Style guide

- Editorial, not corporate dashboard. Generous whitespace. Serif optional for headings (`font-serif` with stone/slate).
- Color sparingly: one accent (emerald or indigo) plus red for leaks and yellow for warnings.
- Keep diagrams ~320px tall so before/after sit comfortably side by side without scrolling.
- Use `text-xs uppercase tracking-wider` for module labels inside diagrams — they must read as schematic, not as UI.
- The only scripts are the Tailwind CDN and the Mermaid ESM import. The report is otherwise static — no app code, no interactivity beyond Mermaid's own rendering.

## Top recommendation section

One larger card. Candidate name, one sentence on why, anchor link to the card. Done.

## Tone

Plain English, concise — but the architectural nouns and verbs come straight from the vocabulary. Concision is no excuse for drifting.

**Use exactly:** module, interface, implementation, depth, deep, shallow, seam, adapter, leverage, locality.

**Never substitute with:** component, service, unit (for module) · API, signature (for interface) · boundary (for seam) · layer, wrapper (for module, when you mean module).

**Phrasings that fit the style:**

- "The notification-ingest module is shallow — the interface is almost as wide as the implementation."
- "The external lookup leaks across the seam."
- "Deepen it: one interface, one place to test."
- "Two adapters defend the seam: HTTP in prod, in-memory in test."

**Benefit bullets** name the benefit in the vocabulary: *"locality: the bugs concentrate in one module"*, *"leverage: one interface, N call sites"*, *"the interface shrinks; the implementation absorbs the wrappers"*. Do not write *"easier to maintain"* or *"cleaner code"* — those terms are not in the vocabulary and do not deserve the space.

No hedging, no throat-clearing, no "it is worth noting that…". If a sentence can be a bullet, make it a bullet. If a bullet can be cut, cut it.
