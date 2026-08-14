# Offline HTML report format

Render the architecture review as one inert, self-contained HTML file in the OS
temp directory. Put all CSS in one inline `<style>` element. Do not load fonts,
styles, images, modules, or other resources from the network. Do not include
JavaScript. Build diagrams from semantic HTML and CSS so the report remains
useful without Mermaid or any other runtime dependency.

## Safety contract

Treat repository names, paths, domain terms, ADR text, and all other discovered
content as untrusted data.

1. HTML-escape every dynamic value before inserting it. Use a standard HTML
   escaper with quote escaping enabled. If substitution is manual, replace in
   this order: `&` -> `&amp;`, `<` -> `&lt;`, `>` -> `&gt;`, `"` -> `&quot;`, and
   `'` -> `&#39;`.
2. Insert escaped dynamic values only into text nodes, including text inside
   `<code>`. Never insert dynamic content into tag names, attributes, URLs, CSS,
   comments, or raw HTML.
3. Generate candidate IDs from their ordinal position (`candidate-1`,
   `candidate-2`, and so on), never from repository content. Use only the fixed
   classes and badge values in this guide.
4. Do not include source snippets. Summarize the architectural evidence and list
   escaped file paths instead. This avoids turning repository-controlled markup
   into report markup.
5. Do not add scripts, event handlers, external links, forms, frames, embedded
   objects, SVG, `data:` content, or CSS `url()` values. Keep the restrictive
   Content Security Policy from the scaffold.

The `{{escaped-...}}` markers below denote escaped text, not a browser-side
template language. Replace every marker while writing the final file.

## Scaffold

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta
      http-equiv="Content-Security-Policy"
      content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; font-src 'none'; connect-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'"
    />
    <meta name="referrer" content="no-referrer" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Architecture review — {{escaped-repo-name}}</title>
    <style>
      :root {
        color-scheme: light;
        font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
          "Segoe UI", sans-serif;
        color: #0f172a;
        background: #fafaf9;
      }
      * { box-sizing: border-box; }
      body { margin: 0; background: #fafaf9; }
      main { width: min(72rem, 100%); margin: 0 auto; padding: 3rem 1.5rem; }
      header, section { margin-bottom: 3rem; }
      h1, h2, h3, p { margin-top: 0; }
      h1 { font-size: clamp(2rem, 5vw, 3.5rem); letter-spacing: -0.04em; }
      h2 { font-size: 1.6rem; }
      h3 { font-size: 1.2rem; }
      a { color: #047857; }
      code { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
      .legend, .badges, .comparison, .flow, .mass-row { display: flex; gap: .75rem; }
      .legend, .badges { flex-wrap: wrap; align-items: center; }
      .legend { color: #475569; font-size: .85rem; }
      .candidate, .recommendation, .diagram {
        border: 1px solid #cbd5e1;
        border-radius: .8rem;
        background: #fff;
      }
      .candidate { padding: 1.5rem; margin-bottom: 2rem; }
      .recommendation { padding: 1.5rem; border-width: 2px; border-color: #047857; }
      .badge {
        display: inline-block;
        border-radius: 999px;
        padding: .25rem .65rem;
        font-size: .75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: .05em;
        background: #e2e8f0;
      }
      .badge.strong { color: #065f46; background: #d1fae5; }
      .badge.explore { color: #92400e; background: #fef3c7; }
      .badge.speculative { color: #334155; background: #e2e8f0; }
      .files { padding-left: 1.25rem; }
      .comparison { align-items: stretch; margin: 1.25rem 0; }
      .diagram { flex: 1 1 0; min-height: 15rem; padding: 1rem; overflow: hidden; }
      .diagram-label {
        color: #64748b;
        font-size: .7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: .09em;
      }
      .flow {
        min-height: 10rem;
        margin: 1rem 0 0;
        padding: 0;
        list-style: none;
        align-items: center;
        justify-content: center;
        flex-wrap: wrap;
      }
      .flow > li {
        position: relative;
        border: 1px solid #94a3b8;
        border-radius: .45rem;
        padding: .65rem .8rem;
        text-align: center;
      }
      .flow > li + li::before { content: "→"; margin-right: .75rem; color: #64748b; }
      .module.deep { color: #fff; background: #172033; border: 4px solid #172033; }
      .module.leak { color: #991b1b; border-color: #dc2626; border-style: dashed; }
      .cross-section { display: grid; gap: .35rem; margin-top: 1rem; }
      .cross-section > div { border-left: 4px solid #64748b; padding: .55rem .75rem; background: #f1f5f9; }
      .cross-section > .deep { min-height: 8rem; color: #fff; background: #172033; }
      .mass-row { align-items: end; min-height: 11rem; margin-top: 1rem; }
      .mass { flex: 1; text-align: center; }
      .interface-surface { padding: .35rem; color: #065f46; background: #d1fae5; border: 1px solid #059669; }
      .implementation-mass { min-height: 7rem; padding: .75rem; color: #fff; background: #172033; }
      .adr { border-left: 4px solid #d97706; padding: .8rem 1rem; background: #fffbeb; }
      .benefits { columns: 2; }
      @media (max-width: 48rem) {
        .comparison { display: block; }
        .diagram + .diagram { margin-top: 1rem; }
        .benefits { columns: 1; }
      }
    </style>
  </head>
  <body>
    <main>
      <header>
        <p class="diagram-label">Architecture review</p>
        <h1>{{escaped-repo-name}}</h1>
        <p>{{escaped-date}}</p>
        <div class="legend">
          <span>solid box = module</span>
          <span>dashed red box = leak</span>
          <span>thick dark box = deep module</span>
        </div>
      </header>

      <section id="candidates" aria-labelledby="candidates-heading">
        <h2 id="candidates-heading">Candidates</h2>
        <article class="candidate" id="candidate-1">
          <h3>{{escaped-candidate-title}}</h3>
          <div class="badges">
            <span class="badge strong">Strong</span>
            <span class="badge">ports &amp; adapters</span>
          </div>
          <h4>Files</h4>
          <ul class="files"><li><code>{{escaped-file-path}}</code></li></ul>
          <div class="comparison">
            <div class="diagram">
              <p class="diagram-label">Before</p>
              <ol class="flow">
                <li class="module">{{escaped-module-name}}</li>
                <li class="module leak">{{escaped-leaking-module-name}}</li>
              </ol>
            </div>
            <div class="diagram">
              <p class="diagram-label">After</p>
              <ol class="flow">
                <li class="module deep">{{escaped-deep-module-name}}</li>
              </ol>
            </div>
          </div>
          <p><strong>Problem:</strong> {{escaped-problem}}</p>
          <p><strong>Solution:</strong> {{escaped-solution}}</p>
          <h4>Benefits</h4>
          <ul class="benefits"><li>{{escaped-benefit}}</li></ul>
          <p class="adr"><strong>ADR:</strong> {{escaped-adr-callout}}</p>
        </article>
      </section>

      <section class="recommendation" id="top-recommendation">
        <p class="diagram-label">Top recommendation</p>
        <h2>{{escaped-top-candidate-title}}</h2>
        <p>{{escaped-recommendation-reason}}</p>
        <a href="#candidate-1">See candidate 1</a>
      </section>
    </main>
  </body>
</html>
```

Duplicate the candidate article as needed and increment only its ordinal ID. Use
one of the fixed recommendation badges: `strong`, `explore`, or `speculative`.
Use one fixed dependency label: `in-process`, `locally-substitutable`, `ports &
adapters`, or `mock`. Omit the ADR callout when it is not relevant.

## Header

Show the escaped repository name, date, and the compact legend from the
scaffold. No introductory paragraph: go straight into the candidates.

## Candidate cards

The diagrams carry the weight. Prose is sparse and uses the vocabulary (module,
interface, depth, seam, adapter, locality, leverage) without ceremony.

Each candidate contains:

- **Title** — short and names the deepening.
- **Badge row** — recommendation strength plus a dependency category.
- **Files** — escaped paths in a monospaced list.
- **Before/after diagram** — the centerpiece, side by side on wide screens.
- **Problem** — one sentence describing what hurts.
- **Solution** — one sentence describing what changes.
- **Benefits** — bullets of at most six words each.
- **ADR callout** — one line, only when relevant.

No explanatory paragraphs. If the diagram needs a paragraph, draw it again.

## Static diagram patterns

Use only the fixed markup and classes from the scaffold. Vary the pattern where
that improves the explanation.

### Dependency or call flow

Use `<ol class="flow">` with one escaped module label per `<li class="module">`.
Add the fixed `leak` or `deep` class when appropriate. CSS supplies the arrows;
do not construct dynamic SVG or style attributes.

### Cross-section

Use `<div class="cross-section">` with one child `<div>` per shallow module. The
after view contains one `<div class="deep">` whose escaped text names the
consolidated responsibility.

### Mass diagram

Use `<div class="mass-row">`, with each `.mass` containing one fixed
`.interface-surface` and one `.implementation-mass`. Their escaped labels show
whether the interface is nearly as large as the implementation or meaningfully
smaller.

### Call-graph collapse

Use the flow pattern for the before view. In the after view, put one deep module
around a short escaped list of the calls that become internal.

## Style guide

- Editorial, not a corporate dashboard. Keep generous whitespace.
- Use emerald as the accent, red for leaks, and yellow for warnings.
- Keep before/after diagrams around 15–20rem tall.
- Use the fixed diagram-label class for module labels.
- Keep the report static and readable in a browser with networking disabled.

## Top recommendation

Use one larger card with the candidate name, one sentence explaining why it
comes first, and an internal link whose target is the ordinal candidate ID.

## Tone

Plain English, concise — but the architectural nouns and verbs come straight
from the vocabulary. Concision is no excuse for drifting.

**Use exactly:** module, interface, implementation, depth, deep, shallow, seam,
adapter, leverage, locality.

**Never substitute with:** component, service, unit (for module) · API,
signature (for interface) · boundary (for seam) · layer, wrapper (for module,
when you mean module).

**Phrasings that fit the style:**

- "The notification-ingest module is shallow — the interface is almost as wide
  as the implementation."
- "The external lookup leaks across the seam."
- "Deepen it: one interface, one place to test."
- "Two adapters defend the seam: HTTP in prod, in-memory in test."

Benefit bullets name the benefit in the vocabulary: *"locality: the bugs
concentrate in one module"*, *"leverage: one interface, N call sites"*, *"the
interface shrinks; the implementation absorbs the wrappers"*. Do not write
*"easier to maintain"* or *"cleaner code"*.

No hedging, throat-clearing, or "it is worth noting that…". If a sentence can be
a bullet, make it a bullet. If a bullet can be cut, cut it.
