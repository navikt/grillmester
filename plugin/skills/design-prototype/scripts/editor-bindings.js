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

function invalid() {
  // Source and marker values are deliberately absent from this public error.
  throw Object.assign(new Error("Editable fields need unique, well-formed HTML bindings."), { status: 400, errorCode: "invalid-editor-bindings" });
}

function startTag(source, start) {
  const nameMatch = /^[A-Za-z][A-Za-z0-9-]*/.exec(source.slice(start + 1));
  if (!nameMatch) invalid();
  const name = nameMatch[0].toLowerCase();
  const attrs = new Map();
  let pos = start + 1 + nameMatch[0].length;
  while (pos < source.length) {
    const beforeSpace = pos;
    while (/[\t\n\f\r ]/.test(source[pos] || "") && pos < source.length) pos += 1;
    if (source[pos] === ">") return { name, attrs, end: pos + 1, selfClosing: false };
    if (source[pos] === "/" && source[pos + 1] === ">") return { name, attrs, end: pos + 2, selfClosing: true };
    if (beforeSpace === pos) invalid();
    const attrMatch = /^[A-Za-z_:][A-Za-z0-9_.:-]*/.exec(source.slice(pos));
    if (!attrMatch) invalid();
    const attr = attrMatch[0].toLowerCase();
    if (attrs.has(attr)) invalid();
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
        if (end < 0) invalid();
        value = source.slice(pos + 1, end);
        pos = end + 1;
      } else {
        const match = /^[^\t\n\f\r >"'`=<]+/.exec(source.slice(pos));
        if (!match) invalid();
        value = match[0];
        pos += value.length;
      }
    } else pos = attributeEnd;
    attrs.set(attr, value);
  }
  invalid();
}

function validateNesting(name, stack, foreign) {
  if (foreign) return;
  const parent = stack.at(-1)?.name;
  const has = candidate => stack.some(node => node.name === candidate);
  if (["plaintext", "frameset", "frame", "image", "isindex", "listing", "nobr", "keygen", "basefont", "bgsound", "command", "menuitem", "spacer"].includes(name)) invalid();
  if (has("p") && P_BREAKERS.has(name)) invalid();
  if (["a", "button", "form"].includes(name) && has(name)) invalid();
  if (/^h[1-6]$/.test(name) && stack.some(node => /^h[1-6]$/.test(node.name))) invalid();
  if (name === "li" && !["ul", "ol", "menu"].includes(parent)) invalid();
  if (["dt", "dd"].includes(name) && parent !== "dl") invalid();
  if (TABLE_PARENTS.has(name) && !TABLE_PARENTS.get(name).includes(parent)) invalid();
  if (TABLE_CHILDREN.has(parent) && !TABLE_CHILDREN.get(parent).has(name)) invalid();
  if (parent === "select" && !["option", "optgroup", "hr"].includes(name)) invalid();
  if (parent === "optgroup" && name !== "option") invalid();
  if (parent === "option") invalid();
  if (name === "option" && !["select", "optgroup", "datalist"].includes(parent)) invalid();
  if (name === "optgroup" && parent !== "select") invalid();
  // These document tags are otherwise silently moved or ignored by HTML parsing.
  if (name === "html" && stack.length) invalid();
  if (["head", "body"].includes(name) && parent !== "html") invalid();
  if (parent === "html" && !["head", "body"].includes(name)) invalid();
  if (parent === "head" && !["base", "link", "meta", "title", "style", "script", "noscript", "template"].includes(name)) invalid();
}

// This deliberately validates a conservative, explicitly closed HTML subset.
// It is not a browser parser or an HTML rewriter. Older preview descriptors are
// unaffected; v2 source must have one unambiguous target for every editor field.
function validateEditorBindings(html, design) {
  if (design === null || design?.version === 1) return true;
  if (!validDesign(design) || design.version !== 2 || typeof html !== "string" ||
      Buffer.byteLength(html) > 2 * 1024 * 1024 || /\u0000/.test(html)) invalid();
  const declaredTexts = new Set(design.texts.map(text => text.id));
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
    if ((TABLE_CHILDREN.has(stack.at(-1)?.name) || ["html", "head"].includes(stack.at(-1)?.name)) && /\S/.test(content)) invalid();
    pos = textEnd;
    if (pos === html.length) break;
    if (html.startsWith("<!--", pos)) {
      const end = html.indexOf("-->", pos + 4);
      const body = html.slice(pos + 4, end);
      if (end < 0 || stack.at(-1)?.textMarker || body.startsWith(">") || body.startsWith("->") || body.includes("--")) invalid();
      pos = end + 3;
      continue;
    }
    if (/^<!doctype html\s*>/i.test(html.slice(pos))) {
      if (stack.length || documentTags.size) invalid();
      pos += /^<!doctype html\s*>/i.exec(html.slice(pos))[0].length;
      continue;
    }
    if (html.startsWith("</", pos)) {
      const match = /^<\/([A-Za-z][A-Za-z0-9-]*)[\t\n\f\r ]*>/.exec(html.slice(pos));
      if (!match || !stack.length || stack.at(-1).name !== match[1].toLowerCase()) invalid();
      stack.pop();
      pos += match[0].length;
      continue;
    }
    if (stack.at(-1)?.textMarker) invalid();
    const tag = startTag(html, pos);
    const foreign = stack.some(node => node.name === "svg" || node.name === "math") || ["svg", "math"].includes(tag.name);
    validateNesting(tag.name, stack, foreign);
    if (["html", "head", "body"].includes(tag.name)) {
      if (documentTags.has(tag.name)) invalid();
      documentTags.add(tag.name);
    }
    if (tag.selfClosing && !foreign && !VOID.has(tag.name)) invalid();
    const blocked = BLOCKED.has(tag.name) || stack.some(node => BLOCKED.has(node.name));
    const variantMarker = tag.attrs.get("data-vc-variant");
    const targetMarker = tag.attrs.get("data-vc-key");
    const textMarker = tag.attrs.get("data-vc-text");
    if ([variantMarker, targetMarker, textMarker].some(value => value !== undefined && !validKey(value))) invalid();
    if ((blocked || NO_MARKERS.has(tag.name)) && [variantMarker, targetMarker, textMarker].some(value => value !== undefined)) invalid();
    if (variantMarker !== undefined) {
      if (!variants.has(variantMarker) || stack.some(node => node.variantMarker !== undefined)) invalid();
      variantCounts.set(variantMarker, (variantCounts.get(variantMarker) || 0) + 1);
      if (variantCounts.get(variantMarker) > 1) invalid();
    }
    const variant = variantMarker ?? stack.findLast(node => node.variantMarker !== undefined)?.variantMarker ?? "";
    if (targetMarker !== undefined) {
      const key = `${variant}\0${targetMarker}`;
      // The renderer searches descendants of a variant wrapper, not the wrapper
      // itself. Reject this ambiguous shorthand for opted-in editor controls.
      if (variantMarker !== undefined && design.targets.some(target => target.variant === variant && target.key === targetMarker &&
          target.controls.some(control => control.editable === true))) invalid();
      targetCounts.set(key, (targetCounts.get(key) || 0) + 1);
    }
    if (textMarker !== undefined) {
      if (tag.name !== "span" || !declaredTexts.has(textMarker)) invalid();
      textCounts.set(textMarker, (textCounts.get(textMarker) || 0) + 1);
      if (textCounts.get(textMarker) > 1) invalid();
    }
    pos = tag.end;
    if (RAW.has(tag.name) && !foreign) {
      const close = new RegExp(`<\\/${tag.name}(?=[\\t\\n\\f\\r />])`, "ig");
      close.lastIndex = pos;
      const match = close.exec(html);
      if (!match) invalid();
      const canonicalClose = new RegExp(`^<\\/${tag.name}[\\t\\n\\f\\r ]*>`, "i").exec(html.slice(match.index));
      if (!canonicalClose || tag.name === "script" && /<!--|<script(?:[\t\n\f\r />])/i.test(html.slice(pos, match.index))) invalid();
      pos = match.index + canonicalClose[0].length;
    } else if (!VOID.has(tag.name) && !tag.selfClosing) {
      if (stack.length >= 256) invalid();
      stack.push({ name: tag.name, variantMarker, textMarker });
    }
  }
  if (stack.length) invalid();
  for (const id of declaredTexts) if (textCounts.get(id) !== 1) invalid();
  for (const target of design.targets) {
    if (!target.controls.some(control => control.editable === true)) continue;
    if (targetCounts.get(`${target.variant}\0${target.key}`) !== 1 || target.variant && variantCounts.get(target.variant) !== 1) invalid();
  }
  return true;
}

module.exports = { validateEditorBindings };
