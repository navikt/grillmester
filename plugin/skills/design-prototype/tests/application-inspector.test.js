"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { bounded, shortLabel, available, textEvidence, nameOf, contextualName, targetPath, buildEvidence, currentRoute, validLocationContext, locateTarget, installInspector } = require("../scripts/application-inspector.js");
const { validApplicationContext } = require("../scripts/application-contract.js");

class Events {
  constructor() { this.listeners = new Map(); }
  addEventListener(type, callback) { const items = this.listeners.get(type) || []; items.push(callback); this.listeners.set(type, items); }
  removeEventListener(type, callback) { this.listeners.set(type, (this.listeners.get(type) || []).filter(item => item !== callback)); }
  fire(type, values = {}) {
    const event = { type, target: this, prevented: false, stopped: false, preventDefault() { this.prevented = true; }, stopImmediatePropagation() { this.stopped = true; }, ...values };
    for (const callback of this.listeners.get(type) || []) { callback(event); if (event.stopped) break; }
    return event;
  }
}
class Element extends Events {
  constructor(tag, attrs = {}, text = "") {
    super(); this.nodeType = 1; this.tagName = tag.toUpperCase(); this.attrs = new Map(Object.entries(attrs)); this.childNodes = []; this.parentElement = null; this.style = {}; this.labels = []; this.hidden = false;
    if (text) this.textContent = text;
  }
  get ownerDocument() { let node = this; while (node.parentElement) node = node.parentElement; return node._document; }
  get isConnected() { let node = this; while (node.parentElement) node = node.parentElement; return node.tagName === "HTML"; }
  get previousElementSibling() { const siblings = (this.parentElement?.childNodes || []).filter(node => node.nodeType === 1); return siblings[siblings.indexOf(this) - 1] || null; }
  get textContent() { return this.childNodes.map(node => node.nodeType === 3 ? node.nodeValue : node.textContent).join(""); }
  set textContent(value) { this.childNodes = [{ nodeType: 3, nodeValue: value, parentElement: this }]; }
  getAttribute(name) { return this.attrs.get(name) ?? null; }
  hasAttribute(name) { return this.attrs.has(name); }
  setAttribute(name, value) { this.attrs.set(name, String(value)); }
  append(...nodes) { for (const node of nodes) { node.remove?.(); node.parentElement = this; this.childNodes.push(node); } }
  contains(node) { for (let current = node; current; current = current.parentElement) if (current === this) return true; return false; }
  appendChild(node) { this.append(node); return node; }
  replaceChildren(...nodes) { for (const node of this.childNodes) node.parentElement = null; this.childNodes = []; this.append(...nodes); }
  remove() { if (this.parentElement) this.parentElement.childNodes = this.parentElement.childNodes.filter(node => node !== this); this.parentElement = null; }
  attachShadow() { this.shadowRoot = new Element("div"); return this.shadowRoot; }
  getBoundingClientRect() { return { left: 12, top: 20, width: 160, height: 40 }; }
  getClientRects() { return this.hidden ? [] : [this.getBoundingClientRect()]; }
  scrollIntoView() { this.scrolled = (this.scrolled || 0) + 1; }
  focus() { this.focused = true; }
  closest(selector) {
    const matches = (node, raw) => {
      const item = raw.trim(); const tag = item.match(/^[a-z][a-z0-9-]*/)?.[0];
      if (tag && node.tagName.toLowerCase() !== tag) return false;
      const attribute = item.match(/\[([^=\]]+)(?:=([^\]]+))?\]/);
      if (attribute && (!node.hasAttribute(attribute[1]) || (attribute[2] && node.getAttribute(attribute[1]) !== attribute[2].replace(/^['"]|['"]$/g, "")))) return false;
      return Boolean(tag || attribute);
    };
    for (let node = this; node; node = node.parentElement) if (selector.split(",").some(item => matches(node, item))) return node;
    return null;
  }
}
function fixture() {
  const doc = new Events(); doc.documentElement = new Element("html"); doc.body = new Element("body"); doc.documentElement.append(doc.body); doc.documentElement._document = doc;
  const heading = new Element("h1", {}, "Velg møte"); const button = new Element("button", {}, "Fortsett"); doc.body.append(heading, button);
  doc.createElement = tag => new Element(tag);
  doc.getElementById = id => {
    const queue = [doc.documentElement];
    while (queue.length) { const node = queue.shift(); if (node.getAttribute?.("id") === id) return node; queue.push(...(node.childNodes || [])); }
    return null;
  };
  doc.querySelectorAll = selector => {
    const found = [], walk = node => {
      if (node.nodeType !== 1) return;
      if (selector === "dialog:modal" ? node.tagName === "DIALOG" && node.modal === true : selector.split(",").some(part => {
        if (part === "input:not([type=hidden])") return node.tagName === "INPUT" && node.getAttribute("type") !== "hidden";
        return node.closest(part) === node;
      })) found.push(node);
      for (const child of node.childNodes) walk(child);
    };
    walk(doc.body); return found;
  };
  const win = new Events(); win.location = new URL("http://127.0.0.1:3333/demo?mode=mock"); win.innerWidth = 800; win.innerHeight = 600; win.scrollX = 0; win.scrollY = 100;
  doc.defaultView = win; win.getComputedStyle = node => ({ visibility: node.style.visibility || "visible", display: node.style.display || "block", contentVisibility: node.style.contentVisibility || "visible", opacity: node.style.opacity ?? "1" });
  const sent = []; win.parent = { postMessage: (message, origin) => sent.push({ message, origin }) };
  win.history = {
    pushState(_data, _unused, route) { win.location = new URL(route, win.location); return "push-result"; },
    replaceState(_data, _unused, route) { win.location = new URL(route, win.location); return "replace-result"; },
  };
  win.queueMicrotask = callback => callback();
  win.MutationObserver = class { constructor(callback) { win.mutate = callback; } observe() {} disconnect() {} };
  win.fetch = () => { throw new Error("The inspector must not make requests."); };
  const config = { shellOrigin: "http://127.0.0.1:4444", epoch: "test-epoch" };
  const command = (mode, extra = {}) => win.fire("message", { source: win.parent, origin: config.shellOrigin, data: { type: "set-mode", epoch: config.epoch, mode }, ...extra });
  return { doc, win, heading, button, sent, config, command };
}

test("bounded evidence respects UTF-8 bytes and removes invisible directional controls", () => {
  assert.equal(bounded("ååå", 5), "åå");
  assert.equal(bounded("Trygg\u202etekst", 100), "Trygg tekst");
  assert.equal(Buffer.byteLength(bounded("😀😀", 6)), 4);
});

test("text evidence excludes input values, textarea defaults, options and editable descendants", () => {
  const root = new Element("section", {}, "Trygg overskrift");
  root.append(new Element("input", { value: "HEMMELIG_INPUT" }), new Element("textarea", {}, "HEMMELIG_TEKST"), new Element("select", {}, "HEMMELIG_VALG"), new Element("div", { contenteditable: "true" }, "HEMMELIG_REDIGERING"));
  root.append(new Element("span", {}, "Vanlig hjelpetekst"));
  assert.equal(textEvidence(root), "Trygg overskrift Vanlig hjelpetekst");
  assert.equal(textEvidence(root.childNodes[4]), "");
});

test("selected containers omit hidden, inert, aria-hidden and CSS-hidden descendant text", () => {
  const { doc, win } = fixture();
  const region = new Element("section", {}, "Synlig innledning");
  for (const attrs of [{ hidden: "" }, { inert: "" }, { "aria-hidden": "true" }]) {
    const hidden = new Element("div", attrs); hidden.append(new Element("span", {}, "PRIVATE ATTRIBUTE TEXT")); region.append(hidden);
  }
  for (const style of [{ display: "none" }, { visibility: "hidden" }, { visibility: "collapse" }, { contentVisibility: "hidden" }]) {
    const hidden = new Element("div"); Object.assign(hidden.style, style);
    hidden.append(new Element("span", {}, "PRIVATE CSS TEXT")); region.append(hidden);
  }
  const contents = new Element("div"); contents.style.display = "contents";
  contents.append(new Element("span", {}, "Synlig detalj")); region.append(contents); doc.body.append(region);
  assert.equal(textEvidence(region), "Synlig innledning Synlig detalj");
  assert.equal(buildEvidence(region, win, doc).context.target.text, "Synlig innledning Synlig detalj");
  assert.equal(textEvidence(region.childNodes[1].childNodes[0]), "");
  region.setAttribute("inert", "");
  assert.equal(textEvidence(contents), "");
});

test("field labels are evidence while current values and password labels are not", () => {
  const { doc, win } = fixture();
  const label = new Element("label", {}, "Møtetype");
  const input = new Element("input", { type: "text", placeholder: "HEMMELIG_PLACEHOLDER" });
  Object.defineProperty(input, "value", { get() { throw new Error("Do not read values"); } });
  label.append(input); input.labels = [label]; doc.body.append(label);
  assert.equal(nameOf(input, doc), "Møtetype");
  assert.equal(buildEvidence(input, win, doc).context.target.text, "");
  const password = new Element("input", { type: "password", "aria-label": "HEMMELIG_NAVN" }); doc.body.append(password);
  assert.equal(nameOf(password, doc), "Passordfelt");
});

test("structural paths distinguish repeated siblings and reject disconnected targets", () => {
  const { doc, button } = fixture(); const second = new Element("button", {}, "Fortsett"); doc.body.append(second);
  assert.equal(targetPath(button, doc), "html:nth-of-type(1) > body:nth-of-type(1) > button:nth-of-type(1)");
  assert.equal(targetPath(second, doc), "html:nth-of-type(1) > body:nth-of-type(1) > button:nth-of-type(2)");
  assert.equal(targetPath(new Element("button"), doc), null);
});

test("collected context satisfies the application contract and captures document coordinates", () => {
  const { doc, win, button } = fixture(); const evidence = buildEvidence(button, win, doc);
  assert.ok(validApplicationContext(evidence.context));
  assert.equal(evidence.anchor.rect.y, 120);
  assert.equal(evidence.context.viewport.scrollY, 100);
  assert.equal(evidence.label, "Fortsett");
  assert.equal(evidence.context.route, "/demo?mode=mock");
});

test("invalid parent configuration is rejected without adding UI", () => {
  const f = fixture();
  assert.equal(installInspector(f.win, f.doc, { ...f.config, token: "must-not-be-here" }), null);
  assert.equal(installInspector(f.win, f.doc, { ...f.config, shellOrigin: f.win.location.origin }), null);
  assert.equal(f.doc.body.childNodes.length, 2);
});

test("forged source, origin, epoch and extra authority cannot enter annotation mode", () => {
  const f = fixture(); const controller = installInspector(f.win, f.doc, f.config);
  f.command("comment", { source: {} });
  f.command("comment", { origin: "http://localhost:9999" });
  f.command("comment", { data: { type: "set-mode", epoch: "old", mode: "comment" } });
  f.command("comment", { data: { type: "set-mode", epoch: f.config.epoch, mode: "comment", action: "submit" } });
  const event = f.doc.fire("click", { target: f.button });
  assert.equal(event.prevented, false);
  assert.deepEqual(f.sent.map(item => item.message.type), ["design-view-available", "design-route"]);
  controller.dispose();
});

test("selection blocks the underlying click and sends bounded evidence only to the exact parent", () => {
  const f = fixture(); installInspector(f.win, f.doc, f.config); f.command("comment");
  const event = f.doc.fire("click", { target: f.button });
  assert.equal(event.prevented, true); assert.equal(event.stopped, true);
  const { message, origin } = f.sent.at(-1);
  assert.equal(origin, f.config.shellOrigin);
  assert.deepEqual(Object.keys(message).sort(), ["anchor", "context", "epoch", "label", "type", "view"]);
  assert.equal(message.type, "design-selection");
  assert.ok(validApplicationContext(message.context));
  assert.equal(message.context.target.name, "Fortsett");
  assert.equal(JSON.stringify(message).includes("token"), false);
});

test("keyboard selection does not capture field values and browsing remains untouched", () => {
  const f = fixture(); const field = new Element("textarea", { "aria-label": "Merknad" }, "PRIVATE DRAFT"); f.doc.body.append(field);
  installInspector(f.win, f.doc, f.config);
  assert.equal(f.doc.fire("keydown", { target: field, key: "Enter" }).prevented, false);
  f.command("comment");
  assert.equal(f.doc.fire("keydown", { target: field, key: "Enter" }).prevented, true);
  assert.equal(f.sent.at(-1).message.context.target.text, "");
  assert.equal(JSON.stringify(f.sent).includes("PRIVATE DRAFT"), false);
});

test("Escape exits locally and proposes only a presentation change to the shell", () => {
  const f = fixture(); installInspector(f.win, f.doc, f.config); f.command("comment");
  const event = f.doc.fire("keydown", { target: f.button, key: "Escape" });
  assert.equal(event.prevented, true);
  assert.deepEqual(f.sent.at(-1).message, { type: "design-exit", epoch: f.config.epoch, view: null });
  assert.equal(f.doc.fire("click", { target: f.button }).prevented, false);
});

test("navigation reports pathname, query and hash without silently treating hash routes as the same page", () => {
  const f = fixture(); installInspector(f.win, f.doc, f.config);
  assert.equal(f.win.history.pushState({}, "", "/nested/meeting?mode=mock"), "push-result");
  assert.equal(f.sent.at(-1).message.route, "/nested/meeting?mode=mock");
  f.win.location.hash = "#/different-page"; f.win.fire("hashchange");
  assert.equal(currentRoute(f.win), "/nested/meeting?mode=mock#/different-page");
  assert.equal(f.sent.at(-1).message.route, "/nested/meeting?mode=mock#/different-page");
  const count = f.sent.length; f.win.fire("hashchange"); assert.equal(f.sent.length, count);
});

test("reinitialization owns one overlay and restores only its own history wrappers", () => {
  const f = fixture(); const original = f.win.history.pushState;
  const old = installInspector(f.win, f.doc, f.config); const fresh = installInspector(f.win, f.doc, f.config);
  assert.equal(f.doc.body.childNodes.filter(node => node.hasAttribute?.("data-design-inspector")).length, 1);
  old.dispose(); f.command("comment"); assert.equal(f.doc.fire("click", { target: f.button }).prevented, true);
  fresh.dispose(); assert.equal(f.win.history.pushState, original);
  assert.equal(f.doc.body.childNodes.filter(node => node.hasAttribute?.("data-design-inspector")).length, 0);
  assert.equal(f.doc.fire("click", { target: f.button }).prevented, false);
});

test("disposal leaves a newer application history wrapper intact", () => {
  const f = fixture(); const controller = installInspector(f.win, f.doc, f.config); const other = () => "application-wrapper";
  f.win.history.pushState = other; controller.dispose(); assert.equal(f.win.history.pushState, other);
});

test("contenteditable nodes and semantic textboxes never contribute edited contents", () => {
  const f = fixture(); const editable = new Element("div", { contenteditable: "true" }, "PRIVATE CONTENT");
  const span = new Element("span", {}, "NESTED PRIVATE"); editable.append(span); f.doc.body.append(editable);
  assert.equal(nameOf(span, f.doc), "Redigerbart felt");
  assert.equal(buildEvidence(span, f.win, f.doc).context.target.text, "");
  const textbox = new Element("div", { role: "textbox", "aria-label": "Notat" }, "PRIVATE RICH TEXT"); f.doc.body.append(textbox);
  assert.equal(textEvidence(textbox), "");
});


test("contextual names distinguish repeated controls by their visible semantic region", () => {
  const f = fixture();
  const first = new Element("section", { "aria-label": "Første avtale" });
  const second = new Element("section", { "aria-label": "Andre avtale" });
  const a = new Element("button", {}, "Velg tidspunkt"), b = new Element("button", {}, "Velg tidspunkt");
  first.append(a); second.append(b); f.doc.body.append(first, second);
  assert.equal(contextualName(a, f.doc), "Velg tidspunkt · Første avtale");
  assert.equal(buildEvidence(b, f.win, f.doc).context.target.name, "Velg tidspunkt · Andre avtale");
  assert.equal(buildEvidence(b, f.win, f.doc).label, "Velg tidspunkt · Andre avtale");
});

test("context hints use one visible direct heading and never descendant form values", () => {
  const f = fixture();
  const region = new Element("section");
  const heading = new Element("h2", {}, "Andre avtale");
  const button = new Element("button", {}, "Fortsett");
  const field = new Element("input", { value: "PRIVATE VALUE" });
  Object.defineProperty(field, "value", { get() { throw new Error("Never read a field value"); } });
  region.append(heading, field, button); f.doc.body.append(region);
  assert.equal(contextualName(button, f.doc), "Fortsett · Andre avtale");
  region.append(new Element("h3", {}, "Another heading"));
  assert.equal(contextualName(button, f.doc), "Fortsett");
});

test("hidden and editable heading text do not become context hints", () => {
  const f = fixture(); const region = new Element("section");
  const button = new Element("button", {}, "Fortsett");
  const heading = new Element("h2", { hidden: "" }, "PRIVATE HEADING");
  region.append(heading, button); f.doc.body.append(region);
  assert.equal(contextualName(button, f.doc), "Fortsett");
  heading.attrs.delete("hidden"); heading.setAttribute("contenteditable", "true");
  assert.equal(contextualName(button, f.doc), "Fortsett");
});

test("context labels stay inside the application contract byte limit", () => {
  const f = fixture(); const region = new Element("section", { "aria-label": "Ø".repeat(120) });
  const button = new Element("button", {}, "Å".repeat(240)); region.append(button); f.doc.body.append(region);
  const evidence = buildEvidence(button, f.win, f.doc);
  assert.ok(Buffer.byteLength(evidence.context.target.name) <= 240);
  assert.ok(Buffer.byteLength(evidence.label) <= 200);
  assert.ok(validApplicationContext(evidence.context));
});

test("only the exact parent can focus the picker while selection mode is active", () => {
  const f = fixture(); installInspector(f.win, f.doc, f.config);
  const host = f.doc.body.childNodes.find(node => node.hasAttribute?.("data-design-inspector"));
  const select = host.shadowRoot.childNodes[2].childNodes[1].childNodes[0];
  const command = { source: f.win.parent, origin: f.config.shellOrigin, data: { type: "focus-picker", epoch: f.config.epoch } };
  f.win.fire("message", command); assert.equal(select.focused, undefined);
  f.command("comment");
  f.win.fire("message", { ...command, origin: "http://localhost:9999" }); assert.equal(select.focused, undefined);
  f.win.fire("message", { ...command, data: { ...command.data, authority: "save" } }); assert.equal(select.focused, undefined);
  f.win.fire("message", command); assert.equal(select.focused, true);
  assert.deepEqual(f.sent.map(item => item.message.type), ["design-view-available", "design-route"]);
});

function pickerOf(f) {
  const host = f.doc.querySelectorAll("[data-design-inspector]")[0];
  const picker = host.shadowRoot.childNodes[2], row = picker.childNodes[1], pages = picker.childNodes[3];
  return { host, picker, select: row.childNodes[0], choose: row.childNodes[1], help: picker.childNodes[2], previous: pages.childNodes[0], pageInfo: pages.childNodes[1], next: pages.childNodes[2] };
}

test("container labels use a short heading instead of every descendant's text", () => {
  const f = fixture(), section = new Element("section");
  section.append(new Element("h2", {}, "Møtedetaljer"), new Element("p", {}, "Lang innholdstekst ".repeat(60)), new Element("input", { value: "PRIVATE" }));
  f.doc.body.append(section);
  assert.equal(nameOf(section, f.doc), "Del av siden: Møtedetaljer");
  assert.equal(nameOf(f.doc.body, f.doc), "Hele siden: Velg møte");
  assert.ok(Array.from(nameOf(new Element("p", {}, "Norsk tekst ".repeat(30)), f.doc)).length <= 60);
  assert.ok(shortLabel("😀".repeat(80)).endsWith("…"));
  assert.ok(Buffer.byteLength(shortLabel("😀".repeat(80))) <= 240);
});

test("picker includes paragraphs, late headings, alerts and menu items, but excludes hidden and inert targets", () => {
  const f = fixture();
  for (const node of [new Element("p", {}, "Forklaring"), new Element("h6", {}, "Detalj"), new Element("div", { role: "alert" }, "Feil"), new Element("div", { role: "menuitem" }, "Menyvalg")]) f.doc.body.append(node);
  const hidden = new Element("section", { "aria-hidden": "true" }); hidden.append(new Element("button", {}, "Skjult")); f.doc.body.append(hidden);
  const inert = new Element("button", { inert: "" }, "Inaktiv"); f.doc.body.append(inert);
  const invisible = new Element("button", {}, "Usynlig"); invisible.style.visibility = "hidden"; f.doc.body.append(invisible);
  installInspector(f.win, f.doc, f.config); f.command("comment");
  const text = pickerOf(f).select.textContent;
  for (const expected of ["Forklaring", "Detalj", "Feil", "Menyvalg"]) assert.ok(text.includes(expected));
  for (const rejected of ["Skjult", "Inaktiv", "Usynlig"]) assert.ok(!text.includes(rejected));
  assert.equal(available(inert, f.win), false);
});

test("repeated target identity from the picker remains in selected evidence", () => {
  const f = fixture(); f.doc.body.append(new Element("button", {}, "Fortsett"));
  installInspector(f.win, f.doc, f.config); f.command("comment");
  const picker = pickerOf(f);
  const option = picker.select.childNodes.find(node => node.textContent.includes("2 av 2"));
  assert.ok(option); picker.select.value = option.value; picker.choose.fire("click");
  assert.equal(f.sent.at(-1).message.context.target.name, "Fortsett · 2 av 2");
  assert.equal(f.sent.at(-1).message.label, "Fortsett · 2 av 2");
});

test("picker pages past the first hundred targets and visibly explains its hard bound", () => {
  const f = fixture(); for (let index = 0; index < 1005; index++) f.doc.body.append(new Element("p", {}, `Del ${index}`));
  installInspector(f.win, f.doc, f.config); f.command("comment");
  const picker = pickerOf(f);
  assert.equal(picker.select.childNodes.length, 100);
  assert.match(picker.help.textContent, /begrenset til 1000/);
  picker.next.fire("click");
  assert.equal(picker.select.childNodes[0].value, "100");
  picker.select.value = "100"; picker.choose.fire("click");
  assert.equal(f.sent.at(-1).message.context.target.name, "Del 98");
  assert.equal(picker.select.focused, true);
});

test("picker host joins only an active native modal and leaves the application's modal state untouched", () => {
  const f = fixture(), dialog = new Element("dialog", { open: "" }); dialog.modal = true;
  const target = new Element("button", {}, "I dialogen"); dialog.append(target); f.doc.body.append(dialog);
  installInspector(f.win, f.doc, f.config); f.command("comment");
  const picker = pickerOf(f);
  assert.equal(picker.host.parentElement, dialog);
  assert.ok(picker.select.textContent.includes("I dialogen"));
  assert.ok(!picker.select.textContent.includes("Fortsett"));
  f.win.fire("message", { source: f.win.parent, origin: f.config.shellOrigin, data: { type: "focus-picker", epoch: f.config.epoch } });
  assert.equal(picker.select.focused, true);
  f.command("browse");
  assert.equal(picker.host.parentElement, f.doc.body);
  assert.equal(dialog.modal, true); assert.equal(dialog.hasAttribute("open"), true);
});

test("blocked link and form navigation sends only a fixed presentation signal", () => {
  const f = fixture(); installInspector(f.win, f.doc, f.config);
  for (const href of ["https://example.test/private", "mailto:synthetic@example.test", "http://127.0.0.1:5555/", "javascript:void(0)"]) {
    const link = new Element("a", { href }, "Lenke"); f.doc.body.append(link);
    const event = f.doc.fire("click", { target: link }); assert.equal(event.prevented, true);
    assert.deepEqual(f.sent.at(-1), { message: { type: "design-navigation-blocked", epoch: f.config.epoch, view: null }, origin: f.config.shellOrigin });
  }
  const local = new Element("a", { href: "/next" }, "Neste"); f.doc.body.append(local);
  assert.equal(f.doc.fire("click", { target: local }).prevented, false);
  local.setAttribute("target", "_blank"); assert.equal(f.doc.fire("click", { target: local }).prevented, true);
  const form = new Element("form", { action: "https://example.test/post" }); f.doc.body.append(form);
  assert.equal(f.doc.fire("submit", { target: form }).prevented, true);
  form.setAttribute("method", "dialog"); assert.equal(f.doc.fire("submit", { target: form }).prevented, false);
  f.command("comment"); f.doc.fire("click", { target: local });
  assert.equal(f.sent.at(-1).message.type, "design-selection");
});


test("an empty picker remains focusable and nested menu text selects its semantic action", () => {
  const f = fixture(); f.heading.hidden = true; f.button.hidden = true;
  installInspector(f.win, f.doc, f.config); f.command("comment");
  f.win.fire("message", { source: f.win.parent, origin: f.config.shellOrigin, data: { type: "focus-picker", epoch: f.config.epoch } });
  const picker = pickerOf(f); assert.equal(picker.select.disabled, true); assert.equal(picker.picker.focused, true);
  const menu = new Element("div", { role: "menuitem" }, "Valg"), nested = new Element("span", {}, " i meny"); menu.append(nested); f.doc.body.append(menu);
  f.doc.fire("click", { target: nested });
  assert.equal(f.sent.at(-1).message.context.target.role, "menuitem");
});

test("pointing mode leaves app controls uncovered until the keyboard list is requested", () => {
  const f = fixture(); installInspector(f.win, f.doc, f.config); f.command("comment");
  assert.equal(pickerOf(f).picker.hidden, true);
  f.win.fire("message", { source: f.win.parent, origin: f.config.shellOrigin, data: { type: "focus-picker", epoch: f.config.epoch } });
  assert.equal(pickerOf(f).picker.hidden, false);
  f.command("browse"); assert.equal(pickerOf(f).picker.hidden, true);
});


test("only a bounded challenge from the exact shell binds a document's later evidence", () => {
  const f = fixture(); installInspector(f.win, f.doc, f.config);
  const first = "a".repeat(32), second = "b".repeat(32);
  const ping = (view, extra = {}) => f.win.fire("message", { source: f.win.parent, origin: f.config.shellOrigin, data: { type: "check-view", epoch: f.config.epoch, view }, ...extra });
  const initial = f.sent.length;
  ping(first, { source: {} }); ping(first, { origin: "http://localhost:9999" }); ping("x".repeat(32)); ping(first, { data: { type: "check-view", epoch: "old", view: first } });
  assert.equal(f.sent.length, initial);
  ping(first);
  assert.deepEqual(f.sent.slice(-3).map(item => item.message.type), ["design-view-ready", "design-health", "design-route"]);
  assert(f.sent.slice(-3).every(item => item.message.view === first));
  f.command("comment"); f.doc.fire("click", { target: f.button });
  assert.equal(f.sent.at(-1).message.view, first);
  ping(second); f.win.history.pushState({}, "", "/next");
  assert.equal(f.sent.at(-1).message.view, second);
  assert.equal(f.sent.at(-1).message.route, "/next");
  f.win.fire("pagehide");
  assert.deepEqual(f.sent.at(-1).message, { type: "design-view-leaving", epoch: f.config.epoch, view: second });
  const suspendedCount = f.sent.length; ping(first); assert.equal(f.sent.length, suspendedCount);
  f.win.fire("pageshow", { persisted: true });
  assert.deepEqual(f.sent.at(-1).message, { type: "design-view-available", epoch: f.config.epoch, view: null });
});

test("external links in an open shadow tree are intercepted without collecting the destination", () => {
  const f = fixture(); installInspector(f.win, f.doc, f.config);
  const host = new Element("div"), link = new Element("a", { href: "https://outside.invalid/private" }, "Les mer");
  const event = f.doc.fire("click", { target: host, composedPath: () => [link, host, f.doc] });
  assert.equal(event.prevented, true);
  assert.deepEqual(f.sent.at(-1).message, { type: "design-navigation-blocked", epoch: f.config.epoch, view: null });
  assert.equal(JSON.stringify(f.sent).includes("outside.invalid"), false);
});


function locationCommand(f, context, extra = {}) {
  const view = "a".repeat(32), request = "b".repeat(32);
  f.win.fire("message", { source: f.win.parent, origin: f.config.shellOrigin,
    data: { type: "check-view", epoch: f.config.epoch, view } });
  return { source: f.win.parent, origin: f.config.shellOrigin,
    data: { type: "show-location", epoch: f.config.epoch, view, request, context }, ...extra };
}
function locationOutline(f) {
  return f.doc.querySelectorAll("[data-design-inspector]")[0].shadowRoot.childNodes.at(-1);
}

test("showing a saved location requires path plus unique semantic evidence and never field values", () => {
  const f = fixture(); const context = buildEvidence(f.button, f.win, f.doc).context;
  assert.equal(validLocationContext(context), true);
  assert.equal(locateTarget(context, f.win, f.doc).target, f.button);
  const other = new Element("button", {}, "Fortsett"); f.doc.body.append(other);
  assert.equal(locateTarget(context, f.win, f.doc).status, "ambiguous");
  other.textContent = "Et annet valg";
  assert.equal(locateTarget(context, f.win, f.doc).target, f.button);
  f.button.remove(); f.doc.body.append(f.button); // The path now points to another control.
  assert.equal(locateTarget(context, f.win, f.doc).status, "unavailable");
  const field = new Element("input", { "aria-label": "Kontaktform" });
  Object.defineProperty(field, "value", { get() { throw new Error("Never read a current field value"); } });
  f.doc.body.append(field);
  assert.equal(locateTarget(buildEvidence(field, f.win, f.doc).context, f.win, f.doc).target, field);
});

test("showing a saved location rejects changed context, hidden targets and changed routes", () => {
  const f = fixture(), section = new Element("section", { "aria-label": "Første avtale" });
  section.append(f.button); f.doc.body.append(section);
  const context = buildEvidence(f.button, f.win, f.doc).context;
  section.setAttribute("aria-label", "En annen avtale");
  assert.equal(locateTarget(context, f.win, f.doc).status, "unavailable");
  section.setAttribute("aria-label", "Første avtale"); section.setAttribute("hidden", "");
  assert.equal(locateTarget(context, f.win, f.doc).status, "unavailable");
  section.attrs.delete("hidden"); f.button.style.visibility = "hidden";
  assert.equal(locateTarget(context, f.win, f.doc).status, "unavailable");
  f.button.style.visibility = "visible";
  f.win.history.pushState({}, "", "/other");
  assert.equal(locateTarget(context, f.win, f.doc).status, "different-route");
});

test("a saved keyboard ordinal never disguises two interchangeable targets", () => {
  const f = fixture(); f.doc.body.append(new Element("button", {}, "Fortsett"));
  installInspector(f.win, f.doc, f.config); f.command("comment");
  const picker = pickerOf(f), option = picker.select.childNodes.find(node => node.textContent.includes("2 av 2"));
  picker.select.value = option.value; picker.choose.fire("click");
  const context = f.sent.at(-1).message.context;
  assert.equal(locateTarget(context, f.win, f.doc).status, "ambiguous");
  f.button.remove();
  assert.equal(locateTarget(context, f.win, f.doc).status, "ambiguous");
});

test("show location scrolls and marks but never clicks, focuses or changes selection mode", () => {
  const f = fixture(); installInspector(f.win, f.doc, f.config);
  const context = buildEvidence(f.button, f.win, f.doc).context;
  const command = locationCommand(f, context);
  f.win.fire("message", command);
  assert.equal(f.button.scrolled, 1); assert.equal(f.button.focused, undefined);
  assert.equal(locationOutline(f).hidden, false);
  assert.deepEqual(f.sent.at(-1), { origin: f.config.shellOrigin, message: {
    type: "design-location-result", epoch: f.config.epoch, view: command.data.view,
    request: command.data.request, status: "shown",
  } });
  assert.equal(f.doc.fire("click", { target: f.button }).prevented, false);
  f.win.fire("message", { ...command, data: { type: "clear-location", epoch: f.config.epoch, view: command.data.view } });
  assert.equal(locationOutline(f).hidden, true);
});

test("show location rejects forged origin source epoch view request extra fields and malformed context", () => {
  const f = fixture(); installInspector(f.win, f.doc, f.config);
  const command = locationCommand(f, buildEvidence(f.button, f.win, f.doc).context);
  const before = f.sent.length;
  for (const forged of [
    { ...command, source: {} }, { ...command, origin: "http://localhost:8888" },
    { ...command, data: { ...command.data, epoch: "old" } },
    { ...command, data: { ...command.data, view: "c".repeat(32) } },
    { ...command, data: { ...command.data, request: "not-a-request" } },
    { ...command, data: { ...command.data, action: "save" } },
    { ...command, data: { ...command.data, context: { ...command.data.context, private: "extra" } } },
    { ...command, data: { ...command.data, context: { ...command.data.context, target: { ...command.data.context.target, path: "button, input" } } } },
  ]) f.win.fire("message", forged);
  assert.equal(f.sent.length, before); assert.equal(f.button.scrolled, undefined);
  assert.equal(locationOutline(f).hidden, true);
  f.win.fire("pagehide"); const suspended = f.sent.length;
  f.win.fire("message", command); assert.equal(f.sent.length, suspended);
});

test("a new document challenge invalidates old location commands and clears its mark", () => {
  const f = fixture(); installInspector(f.win, f.doc, f.config);
  const command = locationCommand(f, buildEvidence(f.button, f.win, f.doc).context);
  f.win.fire("message", command); assert.equal(locationOutline(f).hidden, false);
  f.win.fire("message", { ...command, data: { type: "check-view", epoch: f.config.epoch, view: "d".repeat(32) } });
  const before = f.sent.length; f.win.fire("message", command);
  assert.equal(f.sent.length, before); assert.equal(locationOutline(f).hidden, true);
});

test("whole-page feedback is explained without scrolling or targeting an arbitrary control", () => {
  const f = fixture(); installInspector(f.win, f.doc, f.config);
  const context = buildEvidence(f.doc.body, f.win, f.doc).context;
  context.target = { tag: "body", role: "main", name: "Hele siden", text: "", path: targetPath(f.doc.body, f.doc) };
  f.win.fire("message", locationCommand(f, context));
  assert.equal(f.sent.at(-1).message.status, "page");
  assert.equal(f.doc.body.scrolled, undefined); assert.equal(locationOutline(f).hidden, true);
});

test("native modals hide underlying locations without changing the modal or application focus", () => {
  const f = fixture(); const context = buildEvidence(f.button, f.win, f.doc).context;
  const dialog = new Element("dialog", { open: "" }); dialog.modal = true;
  const inside = new Element("button", {}, "Bekreft avtalen"); dialog.append(inside); f.doc.body.append(dialog);
  installInspector(f.win, f.doc, f.config);
  f.win.fire("message", locationCommand(f, context));
  assert.equal(f.sent.at(-1).message.status, "unavailable");
  f.win.fire("message", locationCommand(f, buildEvidence(inside, f.win, f.doc).context));
  assert.equal(f.sent.at(-1).message.status, "shown");
  assert.equal(f.doc.querySelectorAll("[data-design-inspector]")[0].parentElement, dialog);
  assert.equal(dialog.modal, true); assert.equal(inside.focused, undefined);
});

test("a changed or detached marked node clears the mark; a deliberate request can resolve an unambiguous rerender", () => {
  const f = fixture(); installInspector(f.win, f.doc, f.config);
  const command = locationCommand(f, buildEvidence(f.button, f.win, f.doc).context);
  f.win.fire("message", command);
  f.button.textContent = "Et nytt valg"; f.win.mutate();
  assert.equal(locationOutline(f).hidden, true); assert.equal(f.sent.at(-1).message.status, "unavailable");
  f.button.remove(); const replacement = new Element("button", {}, "Fortsett"); f.doc.body.append(replacement);
  f.win.fire("message", command);
  assert.equal(f.sent.at(-1).message.status, "shown"); assert.equal(replacement.scrolled, 1);
  replacement.remove(); f.win.mutate();
  assert.equal(locationOutline(f).hidden, true); assert.equal(f.sent.at(-1).message.status, "unavailable");
});


test("location display suppresses hover and focus outlines without changing annotation mode", () => {
  const f = fixture(); installInspector(f.win, f.doc, f.config); f.command("comment");
  f.doc.fire("pointermove", { target: f.heading });
  const hoverOutline = f.doc.querySelectorAll("[data-design-inspector]")[0].shadowRoot.childNodes[1];
  assert.equal(hoverOutline.hidden, false);
  const command = locationCommand(f, buildEvidence(f.button, f.win, f.doc).context);
  f.win.fire("message", command);
  assert.equal(hoverOutline.hidden, true); assert.equal(locationOutline(f).hidden, false);
  f.doc.fire("pointermove", { target: f.heading }); f.doc.fire("focusin", { target: f.heading });
  assert.equal(hoverOutline.hidden, true); assert.equal(locationOutline(f).hidden, false);
  f.win.fire("message", { ...command, data: { type: "clear-location", epoch: f.config.epoch, view: command.data.view } });
  f.doc.fire("pointermove", { target: f.heading });
  assert.equal(hoverOutline.hidden, false); assert.equal(locationOutline(f).hidden, true);
  assert.equal(f.doc.fire("click", { target: f.button }).prevented, true, "Endre still prevents application activation");
});

test("early runtime health records categories without retaining exception data", () => {
  const { observeRuntime } = require("../scripts/application-inspector.js");
  const win = new Events();
  const health = observeRuntime(win);
  win.fire("error", { message: "module factory is not available: PRIVATE ERROR DETAIL" });
  win.fire("unhandledrejection", { reason: new Error("PRIVATE REJECTION") });
  assert.deepEqual(health.snapshot(), { script: 0, module: 1, rejection: 1 });
  assert(!JSON.stringify(health).includes("PRIVATE"));
  health.dispose(); win.fire("error", { message: "failure" });
  assert.equal(health.snapshot().script, 0);
});

test("inspection reads visible structure on request without field values or hidden content", () => {
  const { inspectDocument } = require("../scripts/application-inspector.js");
  const { doc, win } = fixture();
  const hidden = new Element("h2", { hidden: "" }, "PRIVATE HIDDEN");
  const input = new Element("input", { "aria-label": "Ditt spørsmål" });
  Object.defineProperty(input, "value", { get() { throw Error("Never read a field value"); } });
  doc.body.append(hidden, input);
  const result = inspectDocument(win, doc);
  assert.deepEqual(result.elements.map(item => item.name), ["Velg møte", "Fortsett", "Ditt spørsmål"]);
  assert.equal(result.elements[2].text, "");
  assert.equal(result.viewport.width, 800);
  assert(!JSON.stringify(result).includes("PRIVATE"));
});

test("inspection answers only the current view challenge from its exact owner", () => {
  const f = fixture(); installInspector(f.win, f.doc, f.config);
  const view = "c".repeat(32), request = "d".repeat(32);
  const send = (data, extra = {}) => f.win.fire("message", { source: f.win.parent, origin: f.config.shellOrigin, data, ...extra });
  const inspect = { type: "inspect-view", epoch: f.config.epoch, view, request };
  const before = f.sent.length; send(inspect); assert.equal(f.sent.length, before);
  send({ type: "check-view", epoch: f.config.epoch, view });
  const bound = f.sent.length;
  send(inspect, { source: {} }); send(inspect, { origin: "http://localhost:5555" });
  send({ ...inspect, view: "b".repeat(32) }); send({ ...inspect, evaluate: "document.cookie" });
  assert.equal(f.sent.length, bound);
  send(inspect); assert.equal(f.sent.at(-1).message.type, "design-inspection");
  assert.equal(f.sent.at(-1).message.request, request);
  f.win.fire("pagehide"); const ended = f.sent.length; send(inspect); assert.equal(f.sent.length, ended);
});

test("transparent elements and their children never become visible inspection or target evidence", () => {
  const { inspectDocument } = require("../scripts/application-inspector.js");
  const { doc, win } = fixture();
  const transparent = new Element("section"), child = new Element("h2", {}, "HIDDEN TRANSPARENT");
  transparent.style.opacity = "0"; transparent.append(child); doc.body.append(transparent);
  assert.equal(available(transparent, win), false); assert.equal(available(child, win), false);
  assert.equal(textEvidence(transparent), "");
  assert(!JSON.stringify(inspectDocument(win, doc)).includes("HIDDEN TRANSPARENT"));
  transparent.style.opacity = "1";
  assert.equal(available(child, win), true);
  assert(inspectDocument(win, doc).elements.some(item => item.name === "HIDDEN TRANSPARENT"));
});
