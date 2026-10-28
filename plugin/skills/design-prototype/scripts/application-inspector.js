/* Application-side evidence collector. It has no control token and no saving,
 * sending, file or recovery capability. The owning shell validates all evidence. */
(() => {
  "use strict";
  const FIELD_TAGS = new Set(["input", "textarea", "select", "option"]);
  const FIELD_ROLES = new Set(["textbox", "searchbox", "combobox", "spinbutton", "slider"]);
  const ROLES = new Set(["", "button", "link", "textbox", "heading", "img", "navigation", "main", "region", "group", "list", "listitem", "checkbox", "radio", "radiogroup", "combobox", "option", "listbox", "switch", "slider", "spinbutton", "searchbox", "tab", "tablist", "tabpanel", "table", "row", "cell", "columnheader", "rowheader", "grid", "gridcell", "alert", "status", "dialog", "form", "menu", "menuitem", "separator", "progressbar", "presentation", "none"]);
  const ANCHOR_ROLES = new Set(["", "button", "link", "textbox", "heading", "img", "navigation", "main", "region", "group", "list", "listitem", "checkbox", "radio", "combobox", "tab", "tabpanel", "table", "row", "cell", "alert", "status", "presentation", "none"]);
  const OMIT_TAGS = new Set(["input", "textarea", "select", "option", "script", "style", "noscript", "template"]);
  const CANDIDATES = "h1,h2,h3,h4,h5,h6,p,button,a[href],input:not([type=hidden]),textarea,select,main,nav,section,article,dialog,[role=button],[role=tab],[role=radio],[role=checkbox],[role=menuitem],[role=alert],[role=status],[contenteditable]";
  const PAGE_SIZE = 100, MAX_CANDIDATES = 1000;
  const OWNER = "data-design-inspector";
  const KEY = "__designApplicationInspector";
  const CONTROL = /[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/g;
  const exact = (value, names) => value !== null && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).length === names.length && names.every(name => Object.prototype.hasOwnProperty.call(value, name));
  const tagOf = node => typeof node?.tagName === "string" ? node.tagName.toLowerCase() : "";
  const attr = (node, name) => node?.getAttribute?.(name) || "";
  const isElement = node => node?.nodeType === 1;
  const editable = node => Boolean(node?.closest?.("[contenteditable]"));
  function bounded(value, maximum) {
    const text = String(value || "").replace(CONTROL, " ").replace(/\s+/g, " ").trim();
    const encoder = new TextEncoder();
    let result = "";
    let count = 0;
    for (const character of text) {
      const size = encoder.encode(character).length;
      if (count + size > maximum) break;
      result += character; count += size;
    }
    return result;
  }
  function shortLabel(value, maximum = 60) {
    const text = Array.from(bounded(value, maximum * 4 + 4));
    return text.length <= maximum ? text.join("") : text.slice(0, maximum - 1).join("").trimEnd() + "…";
  }
  function hiddenFromEvidence(node, win = node?.ownerDocument?.defaultView) {
    for (let current = node; isElement(current); current = current.parentElement) {
      if (current.hidden || current.hasAttribute?.("hidden") || current.inert || current.hasAttribute?.("inert") || attr(current, "aria-hidden") === "true") return true;
      const style = win?.getComputedStyle?.(current);
      if (style && (style.display === "none" || ["hidden", "collapse"].includes(style.visibility) || style.contentVisibility === "hidden")) return true;
    }
    return false;
  }
  function available(node, win) {
    return isElement(node) && Boolean(node.getClientRects?.().length) && !hiddenFromEvidence(node, win);
  }
  function roleOf(node) {
    const explicit = attr(node, "role").trim().split(/\s+/)[0];
    if (ROLES.has(explicit) && explicit) return explicit;
    const tag = tagOf(node);
    if (/^h[1-6]$/.test(tag)) return "heading";
    if (tag === "a" && attr(node, "href")) return "link";
    if (tag === "input") {
      const type = attr(node, "type").toLowerCase();
      return ["button", "submit", "reset", "image"].includes(type) ? "button" : ["checkbox", "radio"].includes(type) ? type
        : type === "range" ? "slider" : type === "number" ? "spinbutton" : type === "search" ? "searchbox" : "textbox";
    }
    if (editable(node)) return "textbox";
    return ({ button: "button", select: "combobox", textarea: "textbox", img: "img", nav: "navigation", main: "main", section: "region", form: "form", ul: "list", ol: "list", li: "listitem", table: "table", tr: "row", td: "cell", th: "columnheader", dialog: "dialog" })[tag] || "";
  }
  function textEvidence(node, maximum = 1000) {
    if (!isElement(node) || editable(node) || OMIT_TAGS.has(tagOf(node)) || FIELD_ROLES.has(roleOf(node))) return "";
    const fragments = [];
    let visited = 0;
    let total = 0;
    function walk(current) {
      if (++visited > 500 || total > maximum * 2) return;
      if (current.nodeType === 3) {
        const part = bounded(current.nodeValue, maximum);
        fragments.push(part); total += part.length; return;
      }
      if (!isElement(current) || hiddenFromEvidence(current) || OMIT_TAGS.has(tagOf(current)) || current.hasAttribute?.(OWNER) || current.hasAttribute?.("contenteditable") || FIELD_ROLES.has(roleOf(current))) return;
      for (const child of current.childNodes || []) walk(child);
    }
    walk(node);
    return bounded(fragments.join(" "), maximum);
  }
  function nameOf(node, doc) {
    if (editable(node)) return "Redigerbart felt";
    if (tagOf(node) === "input" && attr(node, "type").toLowerCase() === "password") return "Passordfelt";
    const labelled = attr(node, "aria-labelledby").trim().split(/\s+/).filter(Boolean).slice(0, 8);
    const fromLabels = labelled.map(id => textEvidence(doc.getElementById(id), 240)).filter(Boolean).join(" ");
    if (fromLabels) return shortLabel(fromLabels);
    const aria = attr(node, "aria-label");
    if (aria) return shortLabel(aria);
    if (FIELD_TAGS.has(tagOf(node))) {
      // Read labels, never .value, selected options, placeholder or textarea text.
      const labels = Array.from(node.labels || []).slice(0, 4).map(label => textEvidence(label, 240)).join(" ");
      return shortLabel(labels || ({ input: "Felt", textarea: "Tekstfelt", select: "Valgliste", option: "Valg" })[tagOf(node)]);
    }
    if (tagOf(node) === "img") return shortLabel(attr(node, "alt") || "Bilde");
    const container = ({ main: "Hovedinnhold", nav: "Navigasjon", section: "Del av siden", article: "Artikkel", body: "Hele siden", form: "Skjema", fieldset: "Feltgruppe", dialog: "Dialog", ul: "Liste", ol: "Liste", table: "Tabell" })[tagOf(node)];
    if (container || tagOf(node) === "div" && ["region", "group", "list", "dialog", "form"].includes(roleOf(node))) {
      const headings = [...(node.children || node.childNodes || [])].filter(child => isElement(child) && /^(h[1-6]|legend)$/.test(tagOf(child)) && available(child, doc.defaultView));
      return shortLabel(headings.length === 1 ? `${container || "Del av siden"}: ${textEvidence(headings[0], 160)}` : container || "Del av siden");
    }
    return shortLabel(textEvidence(node, 240) || ({ p: "Avsnitt", div: "Del av siden", span: "Tekst" })[tagOf(node)] || tagOf(node));
  }
  function contextualName(node, doc) {
    const base = nameOf(node, doc);
    let parent = node.parentElement;
    for (let depth = 0; parent && depth < 8 && parent !== doc.body; depth++, parent = parent.parentElement) {
      if (parent.hasAttribute?.("hidden") || attr(parent, "aria-hidden") === "true" || editable(parent)) continue;
      const tag = tagOf(parent), role = roleOf(parent);
      if (!["section", "article", "fieldset", "dialog", "li"].includes(tag) && !["region", "group", "dialog", "listitem"].includes(role)) continue;
      let hint = "";
      const labelled = attr(parent, "aria-labelledby").trim().split(/\s+/).filter(Boolean).slice(0, 8);
      if (labelled.length) hint = labelled.map(id => {
        const label = doc.getElementById(id);
        return label && !label.hasAttribute?.("hidden") && attr(label, "aria-hidden") !== "true" && label.getClientRects?.().length ? textEvidence(label, 100) : "";
      }).filter(Boolean).join(" ");
      if (!hint) hint = attr(parent, "aria-label");
      if (!hint) {
        const headings = [...(parent.children || parent.childNodes || [])].filter(child => isElement(child) && /^(h[1-6]|legend)$/.test(tagOf(child)) && !child.hasAttribute?.("hidden") && attr(child, "aria-hidden") !== "true" && child.getClientRects?.().length);
        if (headings.length === 1 && headings[0] !== node) hint = textEvidence(headings[0], 100);
      }
      hint = bounded(hint, 100);
      if (hint && hint !== base) return shortLabel(`${shortLabel(base, 32)} · ${shortLabel(hint, 25)}`);
    }
    return base;
  }
  function targetPath(node, doc) {
    const parts = [];
    let current = node;
    while (isElement(current)) {
      const tag = tagOf(current);
      if (!/^[a-z][a-z0-9-]{0,63}$/.test(tag)) return null;
      let position = 1;
      for (let previous = current.previousElementSibling; previous; previous = previous.previousElementSibling) if (tagOf(previous) === tag) position++;
      if (position > 999999) return null;
      parts.unshift(`${tag}:nth-of-type(${position})`);
      if (parts.join(" > ").length > 512) return null;
      if (current === doc.documentElement) return parts.join(" > ");
      current = current.parentElement;
    }
    return null;
  }
  function currentRoute(win) {
    // A hash router is deliberately not mistaken for the same page. Unsupported
    // fragments reach the control boundary and receive an explicit rejection.
    return `${win.location.pathname}${win.location.search}${win.location.hash}`;
  }
  function buildEvidence(node, win, doc, selectedName) {
    if (!isElement(node) || !node.isConnected || node.closest?.(`[${OWNER}]`)) return null;
    const path = targetPath(node, doc);
    if (!path) return null;
    const role = roleOf(node);
    const tag = tagOf(node);
    const name = selectedName ? shortLabel(selectedName) : contextualName(node, doc);
    const rect = node.getBoundingClientRect();
    const number = (value, maximum) => Math.min(maximum, Math.max(0, Math.round(Number(value) || 0)));
    const viewport = { width: Math.max(1, number(win.innerWidth, 20000)), height: Math.max(1, number(win.innerHeight, 20000)) };
    const scrollX = number(win.scrollX, 1000000), scrollY = number(win.scrollY, 1000000);
    return {
      context: { route: currentRoute(win), target: { tag, role, name, text: FIELD_TAGS.has(tag) || FIELD_ROLES.has(role) || editable(node) ? "" : textEvidence(node), path }, viewport: { ...viewport, scrollX, scrollY } },
      anchor: { path, role: ANCHOR_ROLES.has(role) ? role : "", rect: { x: number(rect.left + scrollX, 1000000), y: number(rect.top + scrollY, 1000000), width: number(rect.width, 100000), height: number(rect.height, 100000) }, viewport },
      label: bounded(name, 200),
    };
  }
  function validLocationContext(value) {
    const text = (value, maximum) => typeof value === "string" && new TextEncoder().encode(value).length <= maximum && !/[\u0000-\u001f\u007f-\u009f]/.test(value);
    const number = (value, minimum, maximum) => Number.isFinite(value) && value >= minimum && value <= maximum;
    return exact(value, ["route", "target", "viewport"]) && text(value.route, 2048) && value.route.startsWith("/") && !value.route.startsWith("//")
      && exact(value.target, ["tag", "role", "name", "text", "path"])
      && typeof value.target.tag === "string" && /^[a-z][a-z0-9-]{0,63}$/.test(value.target.tag) && ROLES.has(value.target.role)
      && text(value.target.name, 240) && text(value.target.text, 1000) && text(value.target.path, 512)
      && /^[a-z][a-z0-9-]*:nth-of-type\([1-9][0-9]{0,5}\)(?: > [a-z][a-z0-9-]*:nth-of-type\([1-9][0-9]{0,5}\))*$/.test(value.target.path)
      && exact(value.viewport, ["width", "height", "scrollX", "scrollY"])
      && number(value.viewport.width, 1, 20000) && number(value.viewport.height, 1, 20000)
      && number(value.viewport.scrollX, 0, 1000000) && number(value.viewport.scrollY, 0, 1000000);
  }
  function locateTarget(context, win, doc) {
    if (!validLocationContext(context)) return { status: "unavailable" };
    if (context.route !== currentRoute(win)) return { status: "different-route" };
    const saved = context.target;
    if (saved.tag === "body" && saved.path === "html:nth-of-type(1) > body:nth-of-type(1)") return { status: "page" };
    // Picker ordinals describe an order, not a stable identity. Never choose
    // between indistinguishable controls, even when their old path still exists.
    if (/ · [1-9][0-9]* av [1-9][0-9]*$/.test(saved.name)) return { status: "ambiguous" };
    let modal = null;
    try { modal = [...doc.querySelectorAll("dialog:modal")].filter(node => available(node, win)).at(-1) || null; } catch {}
    let match = null, count = 0;
    for (const node of doc.querySelectorAll(saved.tag)) {
      if (++count > MAX_CANDIDATES) return { status: "ambiguous" };
      if (node.closest?.(`[${OWNER}]`) || !available(node, win) || modal && !modal.contains(node)) continue;
      if (roleOf(node) !== saved.role || contextualName(node, doc) !== saved.name || textEvidence(node) !== saved.text) continue;
      if (match) return { status: "ambiguous" };
      match = node;
    }
    if (!match || targetPath(match, doc) !== saved.path) return { status: "unavailable" };
    return { status: "shown", target: match };
  }
  function installInspector(win, doc, config, nonce = "") {
    if (!exact(config, ["shellOrigin", "epoch"]) || typeof config.shellOrigin !== "string" || typeof config.epoch !== "string" || !config.epoch || config.epoch.length > 200 || win.parent === win) return null;
    let origin;
    try { origin = new URL(config.shellOrigin).origin; if (origin !== config.shellOrigin || !/^https?:$/.test(new URL(origin).protocol) || origin === win.location.origin) return null; }
    catch { return null; }
    if (!doc.body) return null;
    if (typeof win[KEY]?.dispose === "function") win[KEY].dispose();
    let mode = "browse", highlighted = null, disposed = false, lastRoute = null, queued = false, view = null, suspended = false;
    const listeners = [];
    const originalPush = win.history.pushState;
    const originalReplace = win.history.replaceState;
    const host = doc.createElement("div");
    host.setAttribute(OWNER, "");
    const root = host.attachShadow({ mode: "open" });
    const style = doc.createElement("style");
    style.nonce = nonce;
    style.textContent = `@media(forced-colors:active){.outline{border-color:Highlight!important;background:transparent!important}}.location-outline{border-width:3px;box-shadow:0 0 0 2px white}:host{all:initial;position:fixed;inset:0;z-index:2147483645;pointer-events:none;font-family:ui-sans-serif,system-ui,sans-serif;color:#29232e;font-size:12px;line-height:1.4;color-scheme:light}*{box-sizing:border-box}[hidden]{display:none!important}.outline{position:fixed;border:2px solid #7133a2;border-radius:4px;background:#7133a209;pointer-events:none}.picker{pointer-events:auto;position:fixed;left:12px;top:12px;width:min(340px,calc(100vw - 24px));max-height:calc(100dvh - 24px);overflow:auto;padding:11px 12px;background:#fff;border:1px solid #dfd4e8;border-radius:10px;box-shadow:0 3px 18px #25163826}.row{display:flex;align-items:center;gap:6px}label{display:block;font-size:12px;font-weight:650;margin-bottom:6px}select,button{font:inherit;border:1px solid #d5cadd;border-radius:6px;min-height:40px;padding:6px;color:inherit;background:white}select{min-width:0;flex:1}button{cursor:pointer;font-weight:600;background:#7133a2;color:white;padding:6px 10px}button:disabled{opacity:.5;cursor:default}button:focus-visible,select:focus-visible{outline:3px solid #5d3bc1;outline-offset:2px}.pages{display:flex;align-items:center;justify-content:space-between;gap:6px;margin-top:8px}.pages button{background:white;color:#7133a2}.pages span{font-size:12px}p{margin:7px 0 0;font-size:12px;color:#6d6575}.status{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}`;
    const outline = doc.createElement("div"); outline.className = "outline"; outline.hidden = true;
    const picker = doc.createElement("section"); picker.className = "picker"; picker.hidden = true; picker.tabIndex = -1; picker.setAttribute("aria-label", "Velg del i appen");
    const label = doc.createElement("label"); label.textContent = "Velg en del med tastatur"; label.htmlFor = "design-target";
    const row = doc.createElement("div"); row.className = "row";
    const select = doc.createElement("select"); select.id = "design-target";
    const choose = doc.createElement("button"); choose.type = "button"; choose.textContent = "Velg del";
    const help = doc.createElement("p"); help.textContent = "Eller pek på noe i appen. Escape går tilbake til Prøv.";
    const status = doc.createElement("p"); status.className = "status"; status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
    const pages = doc.createElement("div"); pages.className = "pages";
    const previousPage = doc.createElement("button"), nextPage = doc.createElement("button"), pageInfo = doc.createElement("span");
    previousPage.type = nextPage.type = "button"; previousPage.textContent = "Forrige"; nextPage.textContent = "Neste";
    previousPage.setAttribute("aria-label", "Forrige deler"); nextPage.setAttribute("aria-label", "Flere deler");
    pageInfo.setAttribute("role", "status"); pages.append(previousPage, pageInfo, nextPage);
    row.append(select, choose); picker.append(label, row, help, pages); root.append(style, outline, picker, status); doc.body.append(host);
    const locationOutline = doc.createElement("div"); locationOutline.className = "outline location-outline"; locationOutline.hidden = true;
    locationOutline.setAttribute("aria-hidden", "true"); root.append(locationOutline);
    let located = null;
    let candidates = [], candidateNames = new Map(), page = 0;
    function activeModal() {
      try { return [...doc.querySelectorAll("dialog:modal")].filter(node => tagOf(node) === "dialog" && available(node, win)).at(-1) || null; }
      catch { return null; }
    }
    function mountPicker() {
      // Our own host may join the application's native modal. Never change its
      // inertness, modal state, focus trap or app-owned children.
      const parent = mode === "comment" ? activeModal() || doc.body : doc.body;
      if (host.parentElement !== parent) parent.append(host);
      return parent === doc.body ? null : parent;
    }
    function listen(target, type, handler, capture = false) { target.addEventListener(type, handler, capture); listeners.push([target, type, handler, capture]); }
    function post(data) { if (!disposed) win.parent.postMessage({ ...data, epoch: config.epoch, view }, origin); }
    function ownEvent(event) { return event.target === host || Boolean(event.composedPath?.().includes(host)); }
    function targetFor(event) {
      if (!isElement(event.target) || ownEvent(event)) return null;
      const target = event.target.closest?.("button,a[href],input,textarea,select,[role=button],[role=checkbox],[role=radio],[role=tab],[role=menuitem],[contenteditable]") || event.target;
      return target.closest?.(`[${OWNER}]`) ? null : target;
    }
    function showOutline(target) {
      if (located || mode !== "comment" || !target?.isConnected) { outline.hidden = true; highlighted = null; return; }
      highlighted = target;
      const rect = target.getBoundingClientRect();
      outline.style.left = `${rect.left}px`; outline.style.top = `${rect.top}px`; outline.style.width = `${Math.max(0, rect.width)}px`; outline.style.height = `${Math.max(0, rect.height)}px`;
      outline.hidden = false;
    }
    function clearLocation(notify = false) {
      const previous = located;
      located = null; locationOutline.hidden = true;
      if (notify && previous) post({ type: "design-location-result", request: previous.request, status: "unavailable" });
    }
    function refreshLocation() {
      if (!located) return;
      const result = locateTarget(located.context, win, doc);
      // A replacement node with identical text is still not the node we showed.
      if (result.status !== "shown" || result.target !== located.target) { clearLocation(true); return; }
      const parent = activeModal() || doc.body;
      if (host.parentElement !== parent) parent.append(host);
      const rect = located.target.getBoundingClientRect();
      locationOutline.style.left = `${rect.left}px`; locationOutline.style.top = `${rect.top}px`;
      locationOutline.style.width = `${Math.max(0, rect.width)}px`; locationOutline.style.height = `${Math.max(0, rect.height)}px`;
      locationOutline.hidden = false;
    }
    function showLocation(data) {
      clearLocation();
      showOutline(null);
      const result = locateTarget(data.context, win, doc);
      if (result.status === "shown") {
        located = { context: data.context, request: data.request, target: result.target };
        // Scroll only. Focusing or activating a real app control can change it.
        result.target.scrollIntoView({ block: "center", inline: "nearest", behavior: "instant" });
        refreshLocation();
      }
      post({ type: "design-location-result", request: data.request, status: result.status === "shown" && !located ? "unavailable" : result.status });
    }
    function routeChanged() {
      const route = currentRoute(win);
      if (route === lastRoute) return;
      lastRoute = route;
      clearLocation(true);
      if (new TextEncoder().encode(route).length <= 2048) post({ type: "design-route", route });
      else status.textContent = "Adressen er for lang til å brukes som innspill. Velg en vanlig demoside.";
      showOutline(null);
    }
    function refreshCandidates() {
      if (mode !== "comment") return;
      const modal = mountPicker(), previous = candidates[Number(select.value)];
      candidates = [];
      let truncated = false;
      for (const node of doc.querySelectorAll(CANDIDATES)) {
        if (node.closest?.(`[${OWNER}]`) || !available(node, win) || modal && !modal.contains(node) || !targetPath(node, doc)) continue;
        if (candidates.length === MAX_CANDIDATES) { truncated = true; break; }
        candidates.push(node);
      }
      const names = candidates.map(node => contextualName(node, doc));
      const counts = new Map(); names.forEach(name => counts.set(name, (counts.get(name) || 0) + 1));
      const seen = new Map(); candidateNames = new Map();
      names.forEach((name, index) => {
        const occurrence = (seen.get(name) || 0) + 1; seen.set(name, occurrence);
        candidateNames.set(candidates[index], counts.get(name) > 1 ? `${shortLabel(name, 42)} · ${occurrence} av ${counts.get(name)}` : name);
      });
      page = Math.min(page, Math.max(0, Math.ceil(candidates.length / PAGE_SIZE) - 1));
      const start = page * PAGE_SIZE, end = Math.min(start + PAGE_SIZE, candidates.length);
      const options = candidates.slice(start, end).map((node, offset) => {
        const role = ({ heading: "overskrift", button: "knapp", link: "lenke", textbox: "tekstfelt", combobox: "valgliste", radio: "radioknapp", checkbox: "avkryssing", main: "hovedinnhold", navigation: "navigasjon", menuitem: "menyvalg", alert: "varsel", status: "status" })[roleOf(node)] || "del";
        const option = doc.createElement("option"); option.value = String(start + offset); option.textContent = `${candidateNames.get(node)} · ${role}`; return option;
      });
      if (!options.length) { const option = doc.createElement("option"); option.textContent = "Ingen deler tilgjengelige"; option.value = ""; options.push(option); }
      select.replaceChildren(...options);
      const previousIndex = candidates.indexOf(previous);
      select.value = String(previousIndex >= start && previousIndex < end ? previousIndex : start);
      choose.disabled = !candidates.length; select.disabled = !candidates.length;
      pages.hidden = candidates.length <= PAGE_SIZE;
      previousPage.disabled = page === 0; nextPage.disabled = end >= candidates.length;
      pageInfo.textContent = `${start + 1}–${end} av ${candidates.length}`;
      help.textContent = truncated
        ? "Listen er begrenset til 1000 deler. Avgrens appens visning, pek på en del eller gi innspill til hele siden. Escape går tilbake til Prøv."
        : `${modal ? "Viser deler i den åpne dialogen. " : ""}Eller pek på noe i appen. Escape går tilbake til Prøv.`;
    }
    function setMode(next) {
      if (next !== mode) clearLocation(true);
      mode = next;
      // Pointing must not be blocked by a list covering the top of the app.
      // The shell opens this list explicitly through its keyboard picker action.
      picker.hidden = true;
      if (mode === "browse") { showOutline(null); mountPicker(); }
      else { refreshCandidates(); status.textContent = "Endre. Pek på en del, eller bruk listen til å velge med tastatur."; }
    }
    function selectTarget(target) {
      const evidence = available(target, win) ? buildEvidence(target, win, doc, candidateNames.get(target)) : null;
      if (!evidence) { status.textContent = "Delen kunne ikke markeres. Velg en annen del eller gi innspill til hele siden."; return; }
      showOutline(target);
      post({ type: "design-selection", ...evidence });
    }
    const onMessage = event => {
      if (disposed || suspended || event.source !== win.parent || event.origin !== origin || event.data?.epoch !== config.epoch) return;
      if (exact(event.data, ["type", "epoch", "view"]) && event.data.type === "check-view" && typeof event.data.view === "string" && /^[a-f0-9]{32}$/.test(event.data.view || "")) {
        clearLocation();
        view = event.data.view;
        post({ type: "design-view-ready" });
        lastRoute = null;
        routeChanged();
        return;
      }
      if (view && event.data.view === view) {
        if (exact(event.data, ["type", "epoch", "view", "request", "context"]) && event.data.type === "show-location"
          && typeof event.data.request === "string" && /^[a-f0-9]{32}$/.test(event.data.request) && validLocationContext(event.data.context)) { showLocation(event.data); return; }
        if (exact(event.data, ["type", "epoch", "view"]) && event.data.type === "clear-location") { clearLocation(); return; }
      }
      if (exact(event.data, ["type", "epoch"]) && event.data.type === "focus-picker" && mode === "comment") { picker.hidden = false; refreshCandidates(); (select.disabled ? picker : select).focus(); return; }
      if (!exact(event.data, ["type", "epoch", "mode"]) || event.data.type !== "set-mode" || !["browse", "comment"].includes(event.data.mode)) return;
      setMode(event.data.mode);
    };
    function blockNavigation(event, value, target = "") {
      let destination;
      try { destination = new URL(value || win.location.href, doc.baseURI || win.location.href); } catch { destination = null; }
      if (destination && destination.origin === win.location.origin && ["http:", "https:"].includes(destination.protocol)
          && (!target || target === "_self")) return false;
      event.preventDefault(); event.stopImmediatePropagation();
      post({ type: "design-navigation-blocked" });
      return true;
    }
    const onClick = event => {
      if (ownEvent(event)) return;
      if (mode !== "comment") {
        const link = (event.composedPath?.() || [event.target]).map(node => node?.closest?.("a[href],area[href]")).find(Boolean);
        if (link) blockNavigation(event, attr(link, "href"), attr(link, "target").toLowerCase());
        return;
      }
      event.preventDefault(); event.stopImmediatePropagation();
      const target = targetFor(event); if (target) selectTarget(target);
    };
    const onPointerDown = event => { if (mode === "comment" && !ownEvent(event)) { event.preventDefault(); event.stopImmediatePropagation(); } };
    const onKey = event => {
      if (mode !== "comment") return;
      if (event.key === "Escape") { event.preventDefault(); event.stopImmediatePropagation(); setMode("browse"); post({ type: "design-exit" }); return; }
      if (!ownEvent(event) && ["Enter", " "].includes(event.key)) { event.preventDefault(); event.stopImmediatePropagation(); const target = targetFor(event); if (target) selectTarget(target); }
    };
    listen(win, "message", onMessage);
    listen(doc, "click", onClick, true);
    listen(doc, "auxclick", onClick, true);
    listen(doc, "submit", event => {
      if (mode === "comment" || ownEvent(event) || tagOf(event.target) !== "form") return;
      const submitter = event.submitter;
      if ((attr(submitter, "formmethod") || attr(event.target, "method")).toLowerCase() === "dialog") return;
      blockNavigation(event, attr(submitter, "formaction") || attr(event.target, "action"), (attr(submitter, "formtarget") || attr(event.target, "target")).toLowerCase());
    }, true);
    listen(doc, "pointerdown", onPointerDown, true);
    listen(doc, "keydown", onKey, true);
    listen(doc, "pointermove", event => { if (mode === "comment" && !ownEvent(event)) showOutline(targetFor(event)); }, true);
    listen(doc, "focusin", event => { if (mode === "comment" && !ownEvent(event)) showOutline(targetFor(event)); }, true);
    listen(win, "scroll", () => { if (highlighted) showOutline(highlighted); refreshLocation(); }, true);
    listen(win, "resize", () => {
      if (highlighted) showOutline(highlighted);
      refreshLocation();
      if (located) {
        const rect = located.target.getBoundingClientRect();
        if (rect.top < 0 || rect.bottom > win.innerHeight || rect.left < 0 || rect.right > win.innerWidth) {
          located.target.scrollIntoView({ block: "center", inline: "nearest", behavior: "instant" });
        }
      }
      refreshLocation();
    });
    listen(win, "pagehide", () => { suspended = true; clearLocation(); post({ type: "design-view-leaving" }); });
    listen(win, "pageshow", event => {
      suspended = false;
      if (!event.persisted) return;
      view = null;
      post({ type: "design-view-available" });
    });
    listen(win, "popstate", routeChanged);
    listen(win, "hashchange", routeChanged);
    listen(select, "change", () => { const target = candidates[Number(select.value)]; if (target) { target.scrollIntoView({ block: "center", inline: "nearest", behavior: "instant" }); showOutline(target); } });
    for (const [button, direction] of [[previousPage, -1], [nextPage, 1]]) listen(button, "click", () => {
      if (button.disabled) return;
      page += direction; refreshCandidates(); select.focus();
    });
    listen(choose, "click", () => { const target = candidates[Number(select.value)]; if (target) selectTarget(target); });
    function pushState(...args) { const result = Reflect.apply(originalPush, this, args); routeChanged(); return result; }
    function replaceState(...args) { const result = Reflect.apply(originalReplace, this, args); routeChanged(); return result; }
    win.history.pushState = pushState;
    win.history.replaceState = replaceState;
    const observer = new win.MutationObserver(() => {
      if (queued || disposed) return;
      queued = true;
      win.queueMicrotask(() => { queued = false; if (!disposed) { refreshCandidates(); if (highlighted) showOutline(highlighted); refreshLocation(); } });
    });
    observer.observe(doc.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["open", "hidden", "inert", "aria-hidden", "aria-label", "aria-labelledby", "role", "type", "id", "alt", "class", "style", "contenteditable"] });
    const controller = { dispose() {
      if (disposed) return;
      disposed = true;
      for (const [target, type, handler, capture] of listeners) target.removeEventListener(type, handler, capture);
      observer.disconnect(); host.remove();
      if (win.history.pushState === pushState) win.history.pushState = originalPush;
      if (win.history.replaceState === replaceState) win.history.replaceState = originalReplace;
      if (win[KEY] === controller) delete win[KEY];
    } };
    win[KEY] = controller;
    post({ type: "design-view-available" });
    routeChanged();
    return controller;
  }
  if (typeof module === "object" && module.exports) module.exports = { bounded, shortLabel, available, textEvidence, nameOf, contextualName, roleOf, targetPath, buildEvidence, currentRoute, validLocationContext, locateTarget, installInspector };
  if (typeof window !== "object" || typeof document !== "object") return;
  const config = __DESIGN_INSPECTOR_CONFIG__;
  const nonce = document.currentScript?.nonce || "";
  const start = () => installInspector(window, document, config, nonce);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
