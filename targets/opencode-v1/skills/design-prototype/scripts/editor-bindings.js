"use strict";

const { validDesign, validKey } = require("./design-contract.js");

const VOID = new Set("area base br col embed hr img input link meta param source track wbr".split(" "));
const RAW = new Set("script style textarea title noscript xmp".split(" "));
const BLOCKED = new Set("template svg math select option optgroup object applet iframe noembed noframes noscript script style textarea title xmp frameset frame".split(" "));
const NO_MARKERS = new Set("html head body base embed link meta".split(" "));
const P_BREAKERS = new Set("address article aside blockquote center details dialog dir div dl fieldset figcaption figure footer form h1 h2 h3 h4 h5 h6 header hgroup hr li main menu nav ol p pre search section summary table ul".split(" "));
const TABLE_PARENTS = new Map([
  ["caption", ["table"]], ["colgroup", ["table"]], ["col", ["colgroup"]],
  ["thead", ["table"]], ["tbody", ["table"]], ["tfoot", ["table"]],
  ["tr", ["thead", "tbody", "tfoot"]], ["td", ["tr"]], ["th", ["tr"]],
]);
const TABLE_CHILDREN = new Map([
  ["table", new Set(["caption", "colgroup", "thead", "tbody", "tfoot"])],
  ["colgroup", new Set(["col"])], ["thead", new Set(["tr"])],
  ["tbody", new Set(["tr"])], ["tfoot", new Set(["tr"])], ["tr", new Set(["td", "th"])],
]);

const GENERIC_ERROR = "Editable fields need unique, well-formed HTML bindings.";
const REASONS = Object.freeze({
  "html-syntax": "Use explicitly closed tags and well-formed, non-duplicate attributes.",
  "html-nesting": "Use explicit HTML nesting; table rows need tbody, thead or tfoot.",
  "marker-invalid": "Use declared marker IDs with exact spelling.",
  "marker-context": "Move bindings out of removed, raw-text, foreign or inert HTML contexts.",
  "variant-binding": "Variant markers need declared, unique, non-nested wrappers.",
  "text-element": "A text binding must be on an ordinary span.",
  "text-content": "A text span must contain text only, without nested tags or comments.",
  "text-missing": "Add exactly one span for this declared text field.",
  "text-duplicate": "Use this text ID only once across the entire HTML, including all variants.",
  "target-on-wrapper": "Place the editable target inside its variant wrapper, not on the wrapper itself.",
  "target-missing": "Add exactly one target inside its declared variant, or outside variants when variant is empty.",
  "target-duplicate": "Use the editable target key only once within its declared variant.",
});

function editorBindingErrorMessage(error) {
  const detail = error?.bindingDiagnostic;
  if (error?.errorCode !== "invalid-editor-bindings" || !detail || typeof detail.reason !== "string" || !Object.hasOwn(REASONS, detail.reason)) return GENERIC_ERROR;
  const bounded = (value, maximum) => Number.isInteger(value) && value >= 0 && value <= maximum;
  const locations = [];
  if (bounded(detail.textIndex, 15)) locations.push(`texts[${detail.textIndex}]`);
  if (bounded(detail.targetIndex, 23)) locations.push(`targets[${detail.targetIndex}]`);
  if (bounded(detail.offset, 2 * 1024 * 1024)) locations.push(`HTML offset ${detail.offset} (zero-based UTF-16)`);
  // Never forward error.message, source, marker values, labels or paths. The
  // public message contains only fixed advice and bounded numeric coordinates.
  return `${GENERIC_ERROR} [${detail.reason}]${locations.length ? ` ${locations.join(",")}.` : ""} ${REASONS[detail.reason]}`;
}

function invalid(reason, coordinates = {}) {
  const error = Object.assign(new Error(GENERIC_ERROR), { status: 400, errorCode: "invalid-editor-bindings" });
  if (typeof reason === "string" && Object.hasOwn(REASONS, reason)) error.bindingDiagnostic = { reason, ...coordinates };
  error.message = editorBindingErrorMessage(error);
  throw error;
}

function startTag(source, start) {
  const nameMatch = /^[A-Za-z][A-Za-z0-9-]*/.exec(source.slice(start + 1));
  if (!nameMatch) invalid("html-syntax", { offset: start });
  const name = nameMatch[0].toLowerCase();
  const attrs = new Map();
  let pos = start + 1 + nameMatch[0].length;
  while (pos < source.length) {
    const beforeSpace = pos;
    while (/[\t\n\f\r ]/.test(source[pos] || "") && pos < source.length) pos += 1;
    if (source[pos] === ">") return { name, attrs, end: pos + 1, selfClosing: false };
    if (source[pos] === "/" && source[pos + 1] === ">") return { name, attrs, end: pos + 2, selfClosing: true };
    if (beforeSpace === pos) invalid("html-syntax", { offset: pos });
    const attrMatch = /^[A-Za-z_:][A-Za-z0-9_.:-]*/.exec(source.slice(pos));
    if (!attrMatch) invalid("html-syntax", { offset: pos });
    const attr = attrMatch[0].toLowerCase();
    if (attrs.has(attr)) invalid("html-syntax", { offset: pos });
    pos += attrMatch[0].length;
    const attributeEnd = pos;
    while (/[\t\n\f\r ]/.test(source[pos] || "") && pos < source.length) pos += 1;
    let value = "";
    if (source[pos] === "=") {
      pos += 1;
      while (/[\t\n\f\r ]/.test(source[pos] || "") && pos < source.length) pos += 1;
      const quote = source[pos];
      if (quote === "\"" || quote === "'") {
        const end = source.indexOf(quote, pos + 1);
        if (end < 0) invalid("html-syntax", { offset: pos });
        value = source.slice(pos + 1, end);
        pos = end + 1;
      } else {
        const match = /^[^\t\n\f\r >"'`=<]+/.exec(source.slice(pos));
        if (!match) invalid("html-syntax", { offset: pos });
        value = match[0];
        pos += value.length;
      }
    } else pos = attributeEnd;
    attrs.set(attr, value);
  }
  invalid("html-syntax", { offset: start });
}

function validateNesting(name, stack, foreign, offset) {
  if (foreign) return;
  const reject = () => invalid("html-nesting", { offset });
  const parent = stack.at(-1)?.name;
  const has = candidate => stack.some(node => node.name === candidate);
  if (["plaintext", "frameset", "frame", "image", "isindex", "listing", "nobr", "keygen", "basefont", "bgsound", "command", "menuitem", "spacer"].includes(name)) reject();
  if (has("p") && P_BREAKERS.has(name)) reject();
  if (["a", "button", "form"].includes(name) && has(name)) reject();
  if (/^h[1-6]$/.test(name) && stack.some(node => /^h[1-6]$/.test(node.name))) reject();
  if (name === "li" && !["ul", "ol", "menu"].includes(parent)) reject();
  // HTML permits one direct div grouping terms/descriptions inside a dl.
  // Do not broaden this to arbitrary wrappers or implicit end-tag repair.
  if (["dt", "dd"].includes(name) && parent !== "dl" && !(parent === "div" && stack.at(-2)?.name === "dl")) reject();
  if (TABLE_PARENTS.has(name) && !TABLE_PARENTS.get(name).includes(parent)) reject();
  if (TABLE_CHILDREN.has(parent) && !TABLE_CHILDREN.get(parent).has(name)) reject();
  if (parent === "select" && !["option", "optgroup", "hr"].includes(name)) reject();
  if (parent === "optgroup" && name !== "option") reject();
  if (parent === "option") reject();
  if (name === "option" && !["select", "optgroup", "datalist"].includes(parent)) reject();
  if (name === "optgroup" && parent !== "select") reject();
  // These document tags are otherwise silently moved or ignored by HTML parsing.
  if (name === "html" && stack.length) reject();
  if (["head", "body"].includes(name) && parent !== "html") reject();
  if (parent === "html" && !["head", "body"].includes(name)) reject();
  if (parent === "head" && !["base", "link", "meta", "title", "style", "script", "noscript", "template"].includes(name)) reject();
}

// This deliberately validates a conservative, explicitly closed HTML subset.
// It is not a browser parser or an HTML rewriter. Older preview descriptors are
// unaffected; v2 source must have one unambiguous target for every editor field.
function validateEditorBindings(html, design, locations = null) {
  if (design === null || design?.version === 1) return true;
  if (!validDesign(design) || design.version !== 2 || typeof html !== "string" ||
      Buffer.byteLength(html) > 2 * 1024 * 1024 || /\u0000/.test(html)) invalid();
  const declaredTexts = new Set(design.texts.map(text => text.id));
  const textIndices = new Map(design.texts.map((text, index) => [text.id, index]));
  const textCounts = new Map();
  const variants = new Set(design.variants.map(variant => variant.key));
  const variantCounts = new Map();
  const targetCounts = new Map();
  const stack = [];
  const documentTags = new Set();
  let pos = 0;
  while (pos < html.length) {
    const next = html.indexOf("<", pos);
    const textEnd = next < 0 ? html.length : next;
    const content = html.slice(pos, textEnd);
    if ((TABLE_CHILDREN.has(stack.at(-1)?.name) || ["html", "head"].includes(stack.at(-1)?.name)) && /\S/.test(content)) invalid("html-nesting", { offset: pos });
    pos = textEnd;
    if (pos === html.length) break;
    if (html.startsWith("<!--", pos)) {
      const end = html.indexOf("-->", pos + 4);
      const body = html.slice(pos + 4, end);
      if (end < 0 || stack.at(-1)?.textMarker || body.startsWith(">") || body.startsWith("->") || body.includes("--")) {
        invalid(stack.at(-1)?.textMarker ? "text-content" : "html-syntax", { offset: pos, textIndex: textIndices.get(stack.at(-1)?.textMarker) });
      }
      pos = end + 3;
      continue;
    }
    if (/^<!doctype html\s*>/i.test(html.slice(pos))) {
      if (stack.length || documentTags.size) invalid("html-syntax", { offset: pos });
      pos += /^<!doctype html\s*>/i.exec(html.slice(pos))[0].length;
      continue;
    }
    if (html.startsWith("</", pos)) {
      const match = /^<\/([A-Za-z][A-Za-z0-9-]*)[\t\n\f\r ]*>/.exec(html.slice(pos));
      if (!match || !stack.length || stack.at(-1).name !== match[1].toLowerCase()) invalid("html-syntax", { offset: pos });
      const closed = stack.pop();
      if (locations && closed.textMarker !== undefined) locations.texts.set(closed.textMarker, { start: closed.contentStart, end: pos });
      pos += match[0].length;
      continue;
    }
    if (stack.at(-1)?.textMarker) invalid("text-content", { offset: pos, textIndex: textIndices.get(stack.at(-1).textMarker) });
    const tag = startTag(html, pos);
    const foreign = stack.some(node => node.name === "svg" || node.name === "math") || ["svg", "math"].includes(tag.name);
    validateNesting(tag.name, stack, foreign, pos);
    if (["html", "head", "body"].includes(tag.name)) {
      if (documentTags.has(tag.name)) invalid("html-nesting", { offset: pos });
      documentTags.add(tag.name);
    }
    if (tag.selfClosing && !foreign && !VOID.has(tag.name)) invalid("html-syntax", { offset: pos });
    const blocked = BLOCKED.has(tag.name) || stack.some(node => BLOCKED.has(node.name));
    const variantMarker = tag.attrs.get("data-vc-variant");
    const targetMarker = tag.attrs.get("data-vc-key");
    const textMarker = tag.attrs.get("data-vc-text");
    if ([variantMarker, targetMarker, textMarker].some(value => value !== undefined && !validKey(value))) invalid("marker-invalid", { offset: pos });
    if ((blocked || NO_MARKERS.has(tag.name)) && [variantMarker, targetMarker, textMarker].some(value => value !== undefined)) invalid("marker-context", { offset: pos });
    if (variantMarker !== undefined) {
      if (!variants.has(variantMarker) || stack.some(node => node.variantMarker !== undefined)) invalid("variant-binding", { offset: pos });
      variantCounts.set(variantMarker, (variantCounts.get(variantMarker) || 0) + 1);
      if (variantCounts.get(variantMarker) > 1) invalid("variant-binding", { offset: pos });
    }
    const variant = variantMarker ?? stack.findLast(node => node.variantMarker !== undefined)?.variantMarker ?? "";
    if (targetMarker !== undefined) {
      const key = `${variant}\0${targetMarker}`;
      // The renderer searches descendants of a variant wrapper, not the wrapper
      // itself. Reject this ambiguous shorthand for opted-in editor controls.
      if (variantMarker !== undefined && design.targets.some(target => target.variant === variant && target.key === targetMarker &&
          target.controls.some(control => control.editable === true))) invalid("target-on-wrapper", {
        offset: pos, targetIndex: design.targets.findIndex(target => target.variant === variant && target.key === targetMarker),
      });
      targetCounts.set(key, (targetCounts.get(key) || 0) + 1);
      if (locations) locations.targets.set(key, { start: pos, end: tag.end });
    }
    if (textMarker !== undefined) {
      if (tag.name !== "span" || !declaredTexts.has(textMarker)) invalid(declaredTexts.has(textMarker) ? "text-element" : "marker-invalid", { offset: pos, textIndex: textIndices.get(textMarker) });
      textCounts.set(textMarker, (textCounts.get(textMarker) || 0) + 1);
      if (textCounts.get(textMarker) > 1) invalid("text-duplicate", { offset: pos, textIndex: textIndices.get(textMarker) });
    }
    pos = tag.end;
    if (RAW.has(tag.name) && !foreign) {
      const close = new RegExp(`<\\/${tag.name}(?=[\\t\\n\\f\\r />])`, "ig");
      close.lastIndex = pos;
      const match = close.exec(html);
      if (!match) invalid("html-syntax", { offset: pos });
      const canonicalClose = new RegExp(`^<\\/${tag.name}[\\t\\n\\f\\r ]*>`, "i").exec(html.slice(match.index));
      if (!canonicalClose || tag.name === "script" && /<!--|<script(?:[\t\n\f\r />])/i.test(html.slice(pos, match.index))) invalid("html-syntax", { offset: pos });
      pos = match.index + canonicalClose[0].length;
    } else if (!VOID.has(tag.name) && !tag.selfClosing) {
      if (stack.length >= 256) invalid();
      stack.push({ name: tag.name, variantMarker, textMarker, contentStart: tag.end });
    }
  }
  if (stack.length) invalid("html-syntax", { offset: html.length });
  for (const id of declaredTexts) if (textCounts.get(id) !== 1) invalid("text-missing", { textIndex: textIndices.get(id) });
  for (const [targetIndex, target] of design.targets.entries()) {
    if (!target.controls.some(control => control.editable === true)) continue;
    if (targetCounts.get(`${target.variant}\0${target.key}`) !== 1 || target.variant && variantCounts.get(target.variant) !== 1) {
      invalid(targetCounts.get(`${target.variant}\0${target.key}`) > 1 ? "target-duplicate" : "target-missing", { targetIndex });
    }
  }
  return true;
}

const escapeText = value => value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const escapeAttribute = value => value.replace(/"/g, "&quot;");

// Write a version 2 descriptor's text values and editable settings into its
// validated HTML, so the saved HTML alone shows the saved values. Only the
// declared text spans and the start tags of editable targets are rewritten.
function materializeEditorValues(html, design) {
  if (design?.version !== 2) return html;
  const locations = { texts: new Map(), targets: new Map() };
  validateEditorBindings(html, design, locations);
  const edits = [];
  for (const text of design.texts) {
    const at = locations.texts.get(text.id);
    if (at) edits.push({ ...at, value: escapeText(text.value) });
  }
  for (const target of design.targets) {
    const editable = target.controls.filter(control => control.editable === true);
    const at = locations.targets.get(`${target.variant}\0${target.key}`);
    if (!editable.length || !at) continue;
    const tag = startTag(html, at.start);
    const settings = new Set(editable.map(control => `data-vc-setting-${control.id}`));
    let value = `<${html.slice(at.start + 1, at.start + 1 + tag.name.length)}`;
    for (const [name, attribute] of tag.attrs) if (!settings.has(name)) value += ` ${name}="${escapeAttribute(attribute)}"`;
    for (const control of editable) value += ` data-vc-setting-${control.id}="${control.initial}"`;
    edits.push({ start: at.start, end: tag.end, value: `${value}${tag.selfClosing ? " />" : ">"}` });
  }
  let result = html;
  for (const edit of edits.sort((left, right) => right.start - left.start)) result = result.slice(0, edit.start) + edit.value + result.slice(edit.end);
  return result;
}

module.exports = { validateEditorBindings, editorBindingErrorMessage, materializeEditorValues };
