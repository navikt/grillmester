"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { validateEditorBindings } = require("../scripts/editor-bindings.js");

function design(overrides = {}) {
  return { version: 2, texts: [{ id: "heading", label: "Heading", value: "Saved heading" }], variants: [], targets: [], ...overrides };
}
function control(editable = true) {
  return { id: "density", label: "Density", type: "select", initial: "clear", options: [
    { value: "clear", label: "Clear" }, { value: "compact", label: "Compact" },
  ], editable };
}
const target = (variant = "", editable = true) => ({ key: "card", variant, label: "Card", controls: [control(editable)] });
const span = '<span data-vc-text="heading">Source &amp; heading</span>';
function rejected(html, descriptor = design()) {
  assert.throws(() => validateEditorBindings(html, descriptor), error => error.status === 400 &&
    error.message === "Editable fields need unique, well-formed HTML bindings.");
}

test("v1 and plain previews retain their existing HTML contract", () => {
  assert.equal(validateEditorBindings('<p><b>Optional endings<script>anything', { version: 1 }), true);
  assert.equal(validateEditorBindings('<span data-vc-text="anything">Old markup', null), true);
});

test("v2 supports source spans, quoted attributes, boolean attributes, and inert decorative SVG", () => {
  const html = `<!doctype html><html lang="nb"><head><meta charset="UTF-8"><title>Page</title>
    <style>.card::before { content: ">"; }</style></head><body><main>
    <svg viewBox="0 0 10 10"><path d="M0 0"/></svg>
    <h1><span hidden class="heading" title="A > B" data-vc-text='heading'>Source &lt; heading</span></h1>
    <section data-vc-key=card><button type="button" disabled>Continue</button></section>
    </main></body></html>`;
  const descriptor = design({ targets: [target()] });
  const before = JSON.stringify(descriptor);
  assert.equal(validateEditorBindings(html, descriptor), true);
  assert.equal(JSON.stringify(descriptor), before, "validation never mutates canonical source");
});

test("one marker per global text ID is required, with plain leaf text only", () => {
  for (const html of ["<p>Missing</p>", span + span, '<div data-vc-text="heading">Wrong tag</div>',
    '<span data-vc-text="unknown">Unknown</span>' + span,
    '<span data-vc-text="heading"><b>Nested</b></span>',
    '<span data-vc-text="heading">Text<!-- comment --></span>',
    '<span data-vc-text="heading">Line<br>break</span>',
    '<span data-vc-text="heading"/>', '<span data-vc-text="heading"></span><span data-vc-text="extra"></span>']) rejected(html);
  assert.equal(validateEditorBindings('<span data-vc-text="heading"></span>', design()), true);
  assert.equal(validateEditorBindings('<SPAN DATA-VC-TEXT="heading">A &lt;b&gt; B</SPAN>', design()), true);
});

test("comment and raw-text contents never satisfy a binding or create an extra binding", () => {
  for (const wrapper of [value => `<!--${value}-->`, value => `<script>const sample = '${value}'</script>`,
    value => `<style>/* ${value} */</style>`, value => `<textarea>${value}</textarea>`,
    value => `<title>${value}</title>`, value => `<noscript>${value}</noscript>`, value => `<xmp>${value}</xmp>`]) {
    rejected(wrapper(span));
    assert.equal(validateEditorBindings(wrapper(span) + span, design()), true);
  }
  rejected(`<script><!--<script></script>${span}</script>${span}`);
  rejected(`<textarea>sample</textarea ignored>${span}</textarea>${span}`);
  rejected(`<!-->${span} -->${span}`);
  rejected(`<!--->${span} -->${span}`);
});

test("bindings inside parser namespaces and removed or inert contexts are rejected", () => {
  for (const html of [`<template>${span}</template>`, `<svg>${span}</svg>`,
    `<svg><foreignObject>${span}</foreignObject></svg>`, `<math><mtext>${span}</mtext></math>`,
    `<select><option>${span}</option></select>`, `<object>${span}</object>`,
    `<iframe>${span}</iframe>${span}`, `<noembed>${span}</noembed>${span}`, `<noframes>${span}</noframes>${span}`,
    '<textarea data-vc-text="heading">Text</textarea>', '<svg data-vc-key="card"></svg>' + span,
    '<template data-vc-variant="first"></template>' + span]) rejected(html);
});

test("marker spelling is exact, with no entity aliases or duplicate attributes", () => {
  for (const html of ['<span data-vc-text="hea&#100;ing">Alias</span>',
    '<span data-vc-text="heading" DATA-VC-TEXT="other">Duplicate</span>',
    '<span class="one" CLASS="two" data-vc-text="heading">Duplicate</span>',
    '<span data-vc-text>Empty</span>', '<span data-vc-text=" heading">Space</span>',
    '<span data-vc-text="heading"title="No separator">Text</span>',
    '<span data-vc-text="heading\u0000">Null</span>']) rejected(html);
});

test("editable controls require a unique target; noneditable controls add no editor requirement", () => {
  const descriptor = design({ targets: [target()] });
  assert.equal(validateEditorBindings(`<article data-vc-key="card">${span}</article>`, descriptor), true);
  rejected(span, descriptor);
  rejected(`<article data-vc-key="card">${span}</article><div data-vc-key="card"></div>`, descriptor);
  assert.equal(validateEditorBindings(span, design({ targets: [target("", false)] })), true);
});

test("variant control binding uses its nearest wrapper and requires a descendant target", () => {
  const variants = [{ key: "first", label: "First" }, { key: "second", label: "Second" }];
  const descriptor = design({ variants, targets: [target("first"), target("second")] });
  assert.equal(validateEditorBindings(`${span}<section data-vc-variant="first"><article data-vc-key="card"></article></section>
    <section data-vc-variant="second"><article data-vc-key="card"></article></section>`, descriptor), true);
  rejected(`${span}<section data-vc-variant="first" data-vc-key="card"></section>
    <section data-vc-variant="second"><article data-vc-key="card"></article></section>`, descriptor);
  rejected(`${span}<section data-vc-variant="first"><section data-vc-variant="second"><article data-vc-key="card"></article></section></section>`, descriptor);
  rejected(`${span}<section data-vc-variant="first" data-vc-key="card"></section><section data-vc-variant="first"></section>`, descriptor);
  rejected(`${span}<section data-vc-variant="unknown" data-vc-key="card"></section>`, descriptor);
  rejected(`${span}<section data-vc-variant="first"><article data-vc-key="card"></article></section>`, design({ variants, targets: [target()] }));
});

test("well-formed tables bind inside cells without browser foster parenting", () => {
  assert.equal(validateEditorBindings(`<table><thead><tr><th>Heading</th></tr></thead><tbody><tr><td>${span}</td></tr></tbody></table>`, design()), true);
  for (const html of [`<table>${span}</table>`, `<table><tr><td>${span}</td></tr></table>`,
    `<table>Text<tbody><tr><td>${span}</td></tr></tbody></table>`, `<div><td>${span}</td></div>`]) rejected(html);
});

test("obsolete parser-repair elements cannot move a control out of its declared variant", () => {
  const descriptor = design({ variants: [{ key: "first", label: "First" }, { key: "second", label: "Second" }], targets: [target("first")] });
  for (const tag of ["center", "dir", "summary"]) rejected(`${span}<p data-vc-variant="first"><${tag} data-vc-key="card">Text</${tag}></p>`, descriptor);
  for (const tag of ["keygen", "basefont", "bgsound", "image", "command", "menuitem", "spacer"]) {
    rejected(`${span}<${tag} data-vc-variant="first"><div data-vc-key="card">Text</div></${tag}>`, descriptor);
  }
  rejected(`${span}<section data-vc-variant="first"><div data-vc-key="card"></div><section data-vc-variant="second"></section></section>`, descriptor);
});

test("browser repair ambiguities are rejected instead of guessing a target tree", () => {
  for (const html of [`<p><div>${span}</div></p>`, `<a href="#one"><a href="#two">${span}</a></a>`,
    `<form><div><form>${span}</form></div></form>`, `<button><span><button>${span}</button></span></button>`,
    `<h1><h2>${span}</h2></h1>`, `<div/><div>${span}</div>`, `<select><div>${span}</div></select>`,
    `<html><head>${span}</head></html>`, `<html><body>${span}</body><body></body></html>`,
    `<plaintext>${span}</plaintext>`, `<image>${span}</image>`, `<div>${span}</section>`, `<!-- unclosed ${span}`,
    `<script>unclosed${span}`, `<div>${span}`, `<![CDATA[${span}]]>`]) rejected(html);
});

test("document wrappers and removed void tags cannot impersonate a control target", () => {
  const descriptor = design({ targets: [target()] });
  for (const html of [`<html data-vc-key="card"><body>${span}</body></html>`,
    `<html><body data-vc-key="card">${span}</body></html>`, `<base data-vc-key="card">${span}`,
    `<meta data-vc-key="card">${span}`, `<link data-vc-key="card">${span}`, `<embed data-vc-key="card">${span}`]) rejected(html, descriptor);
});

test("unknown or malformed v2 descriptors and excessive nesting fail with a closed safe error", () => {
  assert.throws(() => validateEditorBindings(span, undefined), error => error.status === 400);
  for (const descriptor of [{}, { version: 3 }, design({ extra: "private-value" }),
    design({ texts: [{ id: "heading", label: "Heading", value: "text", arbitrary: true }] })]) rejected(span, descriptor);
  rejected("<div>".repeat(257) + span + "</div>".repeat(257));
  rejected("x".repeat(2 * 1024 * 1024) + span);
});
