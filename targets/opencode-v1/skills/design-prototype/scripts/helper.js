(() => {
  "use strict";

  const channel = "grillmester-visual-companion";
  const screen = window.__grillmesterVisualCompanionScreen;
  const nonce = document.currentScript?.nonce || "";
  const selected = new Map();
  const indicator = document.getElementById("indicator");
  const indicatorText = document.getElementById("indicator-text");
  const interactive = "a[href],button,input,textarea,select,label,summary,[contenteditable],audio[controls],video[controls]";
  // A layout card containing a form is not a selectable concept card.
  const choices = Array.from(document.querySelectorAll(".option, .card")).filter((element) =>
    !element.matches("input,textarea,select,label,summary,[contenteditable]") && !element.querySelector(interactive));
  let persistenceStatus = "idle";
  let pendingEvent = null;
  const post = (value) => parent.postMessage({ channel, version: 1, ...value }, "*");

  choices.forEach((element, index) => {
    element.dataset.vcChoiceId = `choice-${index + 1}`;
    if (!element.hasAttribute("tabindex")) element.setAttribute("tabindex", "0");
    element.setAttribute("role", "button");
    element.setAttribute("aria-pressed", "false");
    element.removeAttribute("onclick");
  });

  function visibleLabel(element) {
    return (element.querySelector("h3, .content h3")?.textContent || element.textContent || "Valg")
      .replace(/\s+/g, " ").trim().substring(0, 120);
  }

  function postSelection(type, choice) {
    if (!/^[a-f0-9]{32}$/.test(screen || "")) return;
    persistenceStatus = "saving";
    pendingEvent = { type, choice };
    post({ event: { type, choice, screen } });
  }

  function updateIndicator() {
    if (!indicator || !indicatorText) return;
    if (!selected.size) {
      indicator.classList.remove("visible");
      indicatorText.textContent = "Valgt";
      return;
    }
    indicator.classList.add("visible");
    const names = Array.from(selected.values());
    const selection = names.length === 1 ? `Valgt: ${names[0]}` : `${names.length} valgt`;
    const status = persistenceStatus === "saving" ? " · lagrer …"
      : persistenceStatus === "saved" ? " · lagret"
        : persistenceStatus === "failed" ? " · ikke lagret — si valget i chatten" : "";
    indicatorText.textContent = selection + status;
  }

  function toggleSelect(element) {
    const choice = element.dataset.vcChoiceId;
    if (!/^choice-[1-9][0-9]{0,3}$/.test(choice || "")) return;
    const container = element.closest(".options, .cards");
    const isMulti = container?.hasAttribute("data-multiselect") || false;
    if (!isMulti && container) {
      container.querySelectorAll(".option, .card").forEach((other) => {
        if (other === element) return;
        other.classList.remove("selected");
        other.setAttribute("aria-pressed", "false");
        selected.delete(other.dataset.vcChoiceId);
      });
    }
    element.classList.toggle("selected");
    const isSelected = element.classList.contains("selected");
    element.setAttribute("aria-pressed", String(isSelected));
    if (isSelected) {
      selected.set(choice, visibleLabel(element));
      postSelection("click", choice);
    } else {
      selected.delete(choice);
      postSelection("deselect", choice);
    }
    updateIndicator();
  }

  function choiceFor(target) {
    const choice = target.closest(".option, .card");
    if (!choice || !choices.includes(choice)) return null;
    const control = target.closest(interactive);
    return control && control !== choice ? null : choice;
  }

  // The controls live outside the prototype's styles. Only explicit user input
  // and structural anchors cross the sandbox bridge; page content stays here.
  const host = document.createElement("div");
  host.setAttribute("data-visual-feedback", "");
  document.body.appendChild(host);
  const root = host.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.nonce = nonce;
  style.textContent = `
    :host{all:initial;position:fixed;inset:0;z-index:2147483646;pointer-events:none;color:#232330;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;line-height:1.45;color-scheme:light}
    *,*::before,*::after{box-sizing:border-box} [hidden]{display:none!important}
    button,input,textarea{font:inherit} button{appearance:none;border:0;cursor:pointer;color:inherit;background:transparent;border-radius:8px;line-height:1.35;min-height:36px;padding:8px 11px;font-weight:600}button:hover{background:#f0edf4}button:disabled{cursor:default;opacity:.45}button:focus-visible,textarea:focus-visible{outline:3px solid #6852ce;outline-offset:3px}button:disabled:hover{background:transparent}button.primary{background:#7133a2;color:white}button.primary:hover{background:#5e2889}button.primary:disabled{background:#7133a2}
    svg{width:17px;height:17px;flex-shrink:0;vertical-align:-3px;stroke:currentColor;fill:none;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}.row{display:flex;align-items:center;gap:8px}.between{justify-content:space-between}.muted{color:#71717e;font-size:12px}.small{font-size:12px}.divider{width:1px;height:24px;background:#e7e3eb;flex-shrink:0}.sr{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}
    .toolbar{pointer-events:auto;position:fixed;bottom:max(16px,env(safe-area-inset-bottom));left:50%;transform:translateX(-50%);display:flex;align-items:center;gap:4px;padding:7px;background:#fff;border:1px solid #e1dce8;border-radius:14px;box-shadow:0 8px 36px #25163824;max-width:calc(100vw - 24px)}
    .toolbar button{white-space:nowrap}.toolbar button[aria-pressed=true],.tools button[aria-pressed=true]{color:#7133a2;background:#f1e8f7}.count{display:inline-flex;align-items:center;justify-content:center;min-width:20px;height:20px;padding:0 5px;border-radius:6px;background:#ece9f0;font-size:11px;margin-left:5px}.tools{display:flex;gap:2px}.tools button{font-size:12px;padding:8px}.toolbar .update{background:#eaf1ff;color:#254c95;font-size:12px}.draft-button{color:#7133a2}
    .hint{position:fixed;top:64px;left:50%;transform:translateX(-50%);max-width:calc(100vw - 24px);padding:9px 14px;border:1px solid #e8d7f1;border-radius:10px;box-shadow:0 3px 15px #25163812;background:#fcf8ff;color:#68368a;font-size:12px;text-align:center}
    .panel{pointer-events:auto;position:fixed;right:16px;top:64px;bottom:86px;width:min(366px,calc(100vw - 32px));display:flex;flex-direction:column;background:#fff;border:1px solid #e1dce8;border-radius:16px;box-shadow:0 12px 48px #25163826;overflow:hidden}
    .panel-head{padding:18px 18px 12px;border-bottom:1px solid #ece8f0}.panel h2,.composer h2{margin:0;font-size:17px;font-weight:700;letter-spacing:-.3px}.close{min-width:34px;min-height:34px;padding:5px;font-size:22px;color:#74707d;font-weight:400}.panel-intro{margin:7px 0 13px;font-size:12px;color:#797381}.filters{display:flex;gap:4px}.filters button{padding:7px 12px;min-height:32px;font-size:12px}.filters button[aria-pressed=true]{background:#f0e8f7;color:#6e3197}.list{overflow-y:auto;overscroll-behavior:contain;flex:1;min-height:0;padding:14px}.empty{padding:28px 16px;text-align:center;color:#787180}.empty svg{width:32px;height:32px;color:#a784c0;margin-bottom:9px}.empty strong{display:block;font-size:14px;color:#393040;margin-bottom:6px}.empty p{margin:0;font-size:12px;line-height:1.6}
    .comment{border:1px solid #e7e1ec;border-radius:12px;padding:13px;margin-bottom:10px;background:#fff;overflow-wrap:anywhere}.comment:focus{outline:2px solid #b264cc;outline-offset:2px}.comment:last-child{margin-bottom:0}.comment.fixed{background:#fbfdfb}.comment .row{flex-wrap:wrap}.comment .number{width:23px;height:23px;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;background:#aa267e;color:white;font-size:11px;font-weight:700;flex-shrink:0}.comment.fixed .number{background:#34845a}.badge{font-size:10px;font-weight:600;color:#78607f;background:#f3edf6;padding:3px 6px;border-radius:5px}.badge.old{background:#f0eff1;color:#6e6b73}.comment p{white-space:pre-wrap;margin:11px 0;font-size:13px;line-height:1.55}.comment .reply{border-left:2px solid #d1badf;padding-left:10px;font-size:12px;color:#65556f}.reply strong{display:block;font-size:10px;letter-spacing:.03em;text-transform:uppercase;margin-bottom:4px}.comment-actions{display:flex;flex-wrap:wrap;gap:2px;margin:8px -5px -5px}.comment-actions button{font-size:11px;padding:7px 6px;min-height:30px}.danger{color:#9c3c53}.proposal{white-space:pre-wrap;padding:9px;background:#f5f0fa;border-radius:7px;font-size:12px;margin-top:7px}.proposal-label{font-size:10px;display:block;color:#79598c;margin-bottom:5px;font-weight:700;text-transform:uppercase;letter-spacing:.04em}
    .panel-foot{padding:13px 16px;border-top:1px solid #ece8f0;background:#fcfbfd}.panel-foot .primary{width:100%;margin-top:10px}.connection{display:flex;align-items:center;gap:6px;font-size:11px;color:#787180}.connection::before{content:"";width:6px;height:6px;border-radius:50%;background:#aaa3af}.connection.live::before{background:#3b9166}.foot-status{font-size:11px;color:#685c74;margin:8px 0 0;line-height:1.4}.error{color:#ad2849;font-size:12px;line-height:1.5;margin:8px 0 0}.composer{pointer-events:auto;position:fixed;width:min(340px,calc(100vw - 24px));max-height:calc(100dvh - 105px);overflow-y:auto;overscroll-behavior:contain;padding:18px;background:#fff;border:1px solid #d8c2e5;border-radius:15px;box-shadow:0 12px 48px #32143f30}.composer .anchor-label{font-size:11px;color:#706578;margin-top:3px}.composer label{display:block;font-size:12px;font-weight:600;margin:15px 0 7px}.composer textarea{display:block;width:100%;min-height:88px;max-height:200px;resize:vertical;padding:10px;border:1px solid #8b7a9a;border-radius:8px;background:#fff;color:#282230;line-height:1.5;font-size:13px}.composer textarea::placeholder{color:#706578}.composer .compose-actions{display:flex;justify-content:flex-end;gap:6px;margin-top:15px}.composer .proposal-toggle{font-size:12px;padding:7px 0;color:#7133a2;text-align:left;margin-top:8px}.composer .proposal-toggle:hover{background:transparent;text-decoration:underline}.composer .preview-button{font-size:11px;background:#f3edf7;margin-top:8px}.composer .help{font-size:10px;color:#706578;margin-top:9px}.composer .save{min-width:82px}.outline{position:fixed;pointer-events:none;border:2px solid #b52e8c;background:#b52e8c0d;border-radius:4px}.pins{position:fixed;inset:0;pointer-events:none}.pin{position:absolute;pointer-events:auto;min-height:26px;width:26px;height:26px;padding:0;border-radius:50%;background:#aa267e;color:#fff;border:2px solid #fff;box-shadow:0 2px 8px #421b393d;font-size:11px;transform:translate(-50%,-50%)}.pin:hover,.pin:focus{background:#7c145d}.pin.fixed{background:#34845a}.pin.fixed:hover{background:#1e6740}.preview-bar{pointer-events:auto;position:fixed;top:64px;left:50%;transform:translateX(-50%);background:#fff7e7;border:1px solid #e8d4a8;border-radius:11px;padding:8px 12px;box-shadow:0 4px 20px #39250018;font-size:12px;max-width:calc(100vw - 24px);display:flex;align-items:center;gap:12px}.preview-bar button{font-size:12px;background:#f4e4c3;white-space:nowrap}
    @media(max-width:600px){.toolbar{bottom:max(10px,env(safe-area-inset-bottom));gap:2px;padding:5px;flex-wrap:wrap;justify-content:center;width:max-content;max-width:calc(100vw - 16px)}.toolbar button{font-size:12px;padding:8px}.toolbar .tools{border-left:1px solid #e7e3eb;padding-left:3px}.toolbar .divider{display:none}.panel{top:64px;right:10px;bottom:106px;width:calc(100vw - 20px)}.hint{font-size:11px}.composer{max-height:calc(100dvh - 120px)}.toolbar svg{width:15px;height:15px}}
    @media(max-height:540px){.panel{overflow-y:auto;overscroll-behavior:contain}.panel-head,.panel-foot,.list{flex-shrink:0}.list{flex:none;overflow:visible}}
    .panel,.list,.composer{scroll-padding:8px}
    @media(prefers-reduced-motion:no-preference){button{transition:background .12s ease}}
  `;
  root.appendChild(style);
  const ui = document.createElement("div");
  ui.innerHTML = `
    <div class="outline" hidden></div><div class="pins"></div>
    <div class="hint" hidden></div>
    <div class="preview-bar" hidden><span>Lokal tekstvisning</span><button type="button" data-action="undo">Tilbakestill</button></div>
    <section class="panel" aria-label="Innspill til prototypen" hidden>
      <div class="panel-head"><div class="row between"><h2>Innspill <span class="count total">0</span></h2><button type="button" class="close" data-action="close-panel" aria-label="Lukk innspill">×</button></div>
        <p class="panel-intro">Pek på det du vil forbedre. Send samlet når du er klar. Innspillene lagres bare i denne økten.</p>
        <div class="filters" role="group" aria-label="Filtrer innspill"><button type="button" data-filter="all" aria-pressed="true">Alle</button><button type="button" data-filter="open" aria-pressed="false">Åpne</button><button type="button" data-filter="fixed" aria-pressed="false">Ordnet</button></div>
      </div><div class="list"></div>
      <div class="panel-foot"><div class="row between"><span class="pending muted">Ingen nye innspill</span><span class="connection">Lagres lokalt</span></div><button type="button" class="primary send" data-action="send" disabled>Send innspill</button><p class="foot-status" role="status"></p><p class="error panel-error" role="alert" hidden></p></div>
    </section>
    <section class="composer" role="dialog" aria-modal="false" aria-labelledby="compose-title" hidden>
      <div class="row between"><h2 id="compose-title">Nytt innspill</h2><button type="button" class="close" data-action="hide-draft" aria-label="Legg utkast til side">×</button></div><div class="anchor-label"></div>
      <label for="feedback-note">Hva vil du endre?</label><textarea id="feedback-note" maxlength="2000" placeholder="For eksempel: Gi overskriften mer luft …"></textarea>
      <button type="button" class="proposal-toggle" data-action="proposal" aria-expanded="false" hidden>Foreslå ny tekst</button>
      <div class="proposal-fields" hidden><label for="feedback-proposal">Ny tekst</label><textarea id="feedback-proposal" maxlength="2000" placeholder="Skriv inn teksten du foreslår"></textarea><button type="button" class="preview-button" data-action="preview-draft">Forhåndsvis teksten</button><p class="help">Kun en lokal forhåndsvisning. Forslaget sendes som et innspill.</p></div>
      <p class="error compose-error" role="alert" hidden></p><div class="compose-actions"><button type="button" data-action="discard">Forkast</button><button type="button" class="primary save" data-action="save">Lagre innspill</button></div><div class="help">⌘/Ctrl + Enter lagrer · Esc legger utkastet til side</div>
    </section>
    <div class="toolbar" role="toolbar" aria-label="Verktøy for prototype"><button type="button" data-action="browse" aria-pressed="true"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 3l10 7-5 1-2 5z"/></svg> Utforsk</button><button type="button" data-action="comment" aria-pressed="false"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 4h12v9H9l-5 3z"/></svg> Kommenter</button><div class="tools" role="group" aria-label="Type markering" hidden><button type="button" data-action="point" aria-pressed="true">Punkt</button><button type="button" data-action="area" aria-pressed="false">Område</button></div><span class="divider"></span><button type="button" data-action="panel" aria-expanded="false">Innspill<span class="count total">0</span></button><button type="button" class="draft-button" data-action="resume" hidden>Fortsett utkast</button><button type="button" class="update" data-action="refresh" hidden>Vis ny versjon</button></div>
    <div class="sr" role="status" aria-live="polite" aria-atomic="true"></div>
  `;
  root.appendChild(ui);
  const el = (selector) => root.querySelector(selector);
  const all = (selector) => Array.from(root.querySelectorAll(selector));
  const panel = el(".panel");
  const composer = el(".composer");
  const note = el("#feedback-note");
  const proposalInput = el("#feedback-proposal");
  const outline = el(".outline");
  const pinLayer = el(".pins");
  let snapshot = { revision: -1, comments: [], screens: [], listeningUntil: 0 };
  let mode = "browse";
  let marker = "point";
  let filter = "all";
  let draft = null;
  let savingDraft = null;
  let workshop = null;
  let drag = null;
  let preview = null;
  let updateAvailable = false;
  let lastBusy = null;
  let requestCounter = 0;
  let submitting = false;
  let sentCount = 0;
  let layoutPending = false;
  let connectionLost = false;
  let addedTabStops = [];
  let originalTouchAction = document.documentElement.style.touchAction;
  const requests = new Map();
  const safeRoles = new Set(["button", "link", "textbox", "heading", "img", "navigation", "main", "region", "group", "list", "listitem", "checkbox", "radio", "combobox", "tab", "tabpanel", "table", "row", "cell", "alert", "status", "presentation", "none"]);

  function announce(text) { el(".sr").textContent = text; }
  function ownEvent(event) { return event.composedPath().includes(host); }
  function usableTarget(target) {
    return target instanceof Element && target !== host && !host.contains(target)
      && !["HTML", "BODY", "SCRIPT", "STYLE", "NOSCRIPT"].includes(target.tagName);
  }
  function targetPath(target) {
    const parts = [];
    for (let node = target; node && node !== document.documentElement; node = node.parentElement) {
      const tag = node.localName;
      if (!/^[a-z][a-z0-9-]*$/.test(tag)) return "";
      let index = 1;
      for (let other = node.previousElementSibling; other; other = other.previousElementSibling) {
        if (other.localName === tag) index += 1;
      }
      parts.unshift(`${tag}:nth-of-type(${index})`);
    }
    const value = parts.join(" > ");
    return value.length <= 512 ? value : "";
  }
  function resolveTarget(anchor) {
    if (!/^[a-z][a-z0-9-]*:nth-of-type\([1-9][0-9]{0,5}\)(?: > [a-z][a-z0-9-]*:nth-of-type\([1-9][0-9]{0,5}\))*$/.test(anchor?.path || "")) return null;
    try { return document.querySelector(anchor.path); } catch { return null; }
  }
  function documentRect(rect) {
    return { x: Math.max(0, Math.round(rect.left + window.scrollX)), y: Math.max(0, Math.round(rect.top + window.scrollY)), width: Math.max(1, Math.round(rect.width)), height: Math.max(1, Math.round(rect.height)) };
  }
  function anchorFor(target, rect) {
    const role = target.getAttribute("role") || "";
    return { path: targetPath(target), role: safeRoles.has(role) ? role : "", rect: documentRect(rect || target.getBoundingClientRect()), viewport: { width: window.innerWidth, height: window.innerHeight } };
  }
  function eligibleText(target) {
    return usableTarget(target) && /^(P|H[1-6]|SPAN|BUTTON|A|LABEL|LI|TD|TH|CAPTION|LEGEND|STRONG|EM|SMALL)$/.test(target.tagName)
      && !target.childElementCount && Array.from(target.childNodes).some((node) => node.nodeType === Node.TEXT_NODE);
  }
  function pendingComments() { return [...snapshot.comments, ...(snapshot.decisions || [])].filter((item) => item.submission === 0); }
  function busy() { return Boolean(draft || drag || preview || pendingComments().length || requests.size || workshop?.isBusy()); }
  function saving() { return Boolean(savingDraft || workshop?.isSaving()); }
  function topInset() { return Math.max(64, Math.ceil((document.body.querySelector(":scope > .vc-header")?.getBoundingClientRect().bottom || 0) + 10)); }
  function updateBusy() {
    const value = busy();
    if (value !== lastBusy) { lastBusy = value; post({ action: "feedback-busy", screen, busy: value }); }
    all(".toolbar button,.pin").forEach((button) => { button.disabled = saving(); });
    const refresh = el('[data-action="refresh"]');
    refresh.hidden = !updateAvailable;
    refresh.disabled = value;
    refresh.title = value ? "Fullfør utkast, send innspill og avslutt forhåndsvisningen først" : "Åpne den nye versjonen";
    scheduleLayout();
  }
  function request(action, payload) {
    if (connectionLost && action !== "comments-list") return Promise.reject(new Error("Økten er frakoblet. Kopier utkastet før du starter en ny økt."));
    const requestId = ++requestCounter;
    return new Promise((resolve, reject) => {
      const timer = window.setTimeout(() => {
        requests.delete(requestId);
        updateBusy();
        reject(new Error("Kunne ikke lagre. Kontroller at forhåndsvisningen fortsatt er åpen, og prøv igjen."));
      }, 12000);
      requests.set(requestId, { resolve, reject, timer });
      updateBusy();
      post({ action, requestId, payload });
    });
  }
  function errorAt(selector, message) {
    const target = el(selector);
    target.textContent = message || "";
    target.hidden = !message;
  }
  function setPanel(open, focus = false) {
    if (open && saving()) return;
    if (open) workshop?.close();
    panel.hidden = !open;
    el('[data-action="panel"]').setAttribute("aria-expanded", String(open));
    if (open && draft && !composer.hidden) hideDraft();
    if (open && focus) el('[data-action="close-panel"]').focus();
    if (!open && focus) el('[data-action="panel"]').focus();
    updateHint();
  }
  function updateHint() {
    const hint = el(".hint");
    hint.hidden = mode !== "comment" || !panel.hidden || !composer.hidden || Boolean(preview);
    hint.textContent = marker === "area" ? workshop?.isComparing() ? "Avslutt sammenligning for å markere et område · Punkt kan brukes nå" : "Dra rundt et område · eller fokuser et element og trykk Enter" : "Trykk på et element · eller bruk Tab og Enter · Esc avslutter";
    document.documentElement.style.touchAction = mode === "comment" && marker === "area" && !workshop?.isComparing() ? "none" : originalTouchAction;
  }
  function setMode(next, nextMarker = marker) {
    if (saving()) return;
    mode = next;
    marker = nextMarker;
    for (const value of ["browse", "comment"]) el(`[data-action="${value}"]`).setAttribute("aria-pressed", String(mode === value));
    for (const value of ["point", "area"]) el(`[data-action="${value}"]`).setAttribute("aria-pressed", String(marker === value));
    el(".tools").hidden = mode !== "comment";
    document.documentElement.style.touchAction = mode === "comment" && marker === "area" ? "none" : originalTouchAction;
    if (mode === "comment" && !addedTabStops.length) {
      addedTabStops = Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6,p,img,label,li"))
        .filter((target) => !target.hasAttribute("tabindex") && !target.closest("a,button,[contenteditable]"));
      addedTabStops.forEach((target) => target.setAttribute("tabindex", "0"));
    } else if (mode === "browse") {
      addedTabStops.forEach((target) => target.removeAttribute("tabindex"));
      addedTabStops = [];
      outline.hidden = true;
      drag = null;
    }
    if (mode === "comment") { workshop?.close(); setPanel(false); }
    updateBusy();
    updateHint();
  }
  function showOutline(rect) {
    if (!rect || rect.width < 1 || rect.height < 1) { outline.hidden = true; return; }
    outline.hidden = false;
    outline.style.left = `${rect.left}px`;
    outline.style.top = `${rect.top}px`;
    outline.style.width = `${rect.width}px`;
    outline.style.height = `${rect.height}px`;
  }
  function resetPreview() {
    if (preview) {
      preview.nodes.forEach(({ node, value }) => { if (node.parentNode === preview.target) node.data = value; });
      preview = null;
    }
    el(".preview-bar").hidden = true;
    el('[data-action="preview-draft"]').textContent = "Forhåndsvis teksten";
    updateBusy();
    updateHint();
    scheduleLayout();
  }
  function showPreview(target, value) {
    resetPreview();
    if (!eligibleText(target) || !value.trim()) return false;
    const nodes = Array.from(target.childNodes).filter((node) => node.nodeType === Node.TEXT_NODE).map((node) => ({ node, value: node.data }));
    preview = { target, nodes };
    nodes.forEach(({ node }, index) => { node.data = index === 0 ? value : ""; });
    el(".preview-bar").hidden = false;
    el('[data-action="preview-draft"]').textContent = "Tilbakestill tekstvisning";
    updateBusy();
    updateHint();
    scheduleLayout();
    return true;
  }
  function restoreFocus(target) {
    if (target?.isConnected && typeof target.focus === "function") {
      target.focus({ preventScroll: true });
      if ((root.activeElement || document.activeElement) === target) return;
    }
    el('[data-action="comment"]').focus();
  }
  function focusPrototype(target) {
    if (!usableTarget(target)) { restoreFocus(null); return; }
    if (!target.hasAttribute("tabindex") && !target.matches("a[href],button,input,select,textarea")) {
      target.setAttribute("tabindex", "-1");
      target.addEventListener("blur", () => target.removeAttribute("tabindex"), { once: true });
    }
    restoreFocus(target);
  }
  function beginDraft(target, kind, rect, position) {
    if (saving()) return;
    if (!usableTarget(target)) return;
    if (draft) { resumeDraft(); announce("Fullfør eller forkast utkastet før du lager et nytt innspill."); return; }
    if (kind === "area" && workshop?.isComparing()) { announce("Avslutt sammenligning for å markere et område. Punkt kan brukes nå."); return; }
    const anchor = anchorFor(target, rect);
    if (!anchor.path) { announce("Dette elementet kan ikke markeres. Velg et mindre detaljert område."); return; }
    resetPreview();
    draft = { target, kind, anchor, proposal: false, focus: root.activeElement || document.activeElement, position: position || { x: Math.max(12, target.getBoundingClientRect().left), y: Math.max(12, target.getBoundingClientRect().bottom) } };
    note.value = "";
    proposalInput.value = "";
    errorAt(".compose-error", "");
    el(".anchor-label").textContent = kind === "area" ? "Markert område" : `Valgt element · ${target.localName}`;
    el('[data-action="proposal"]').hidden = kind !== "point" || !eligibleText(target);
    el('[data-action="proposal"]').setAttribute("aria-expanded", "false");
    el(".proposal-fields").hidden = true;
    resumeDraft();
    updateBusy();
  }
  function resumeDraft() {
    if (!draft || saving()) return;
    if (draft.kind === "area") workshop?.endComparison();
    setPanel(false);
    composer.hidden = false;
    el('[data-action="resume"]').hidden = true;
    showDraftOutline();
    positionComposer();
    note.focus({ preventScroll: true });
    updateHint();
  }
  function hideDraft() {
    if (!draft || savingDraft) return;
    resetPreview();
    composer.hidden = true;
    outline.hidden = true;
    el('[data-action="resume"]').hidden = false;
    restoreFocus(draft.focus);
    updateHint();
  }
  function discardDraft() {
    if (savingDraft) return;
    const focus = draft?.focus;
    resetPreview();
    draft = null;
    composer.hidden = true;
    el('[data-action="resume"]').hidden = true;
    outline.hidden = true;
    restoreFocus(focus);
    updateBusy();
    updateHint();
  }
  function positionComposer() {
    if (!draft || composer.hidden) return;
    const bottomSpace = Math.max(80, window.innerHeight - el(".toolbar").getBoundingClientRect().top + 12);
    const topSpace = topInset();
    composer.style.maxHeight = `calc(100dvh - ${bottomSpace + topSpace}px)`;
    const bounds = composer.getBoundingClientRect();
    composer.style.left = `${Math.max(12, Math.min(draft.position.x + 14, window.innerWidth - bounds.width - 12))}px`;
    composer.style.top = `${Math.max(topSpace, Math.min(draft.position.y + 12, window.innerHeight - bounds.height - bottomSpace))}px`;
  }
  function showDraftOutline() {
    if (!draft || composer.hidden) return;
    if (draft.kind === "point") showOutline(draft.target.getBoundingClientRect());
    else showOutline({ left: draft.anchor.rect.x - scrollX, top: draft.anchor.rect.y - scrollY, ...draft.anchor.rect });
  }
  async function saveDraft() {
    if (!draft || el(".save").disabled) return;
    const text = note.value.trim();
    if (!text) { errorAt(".compose-error", "Skriv et innspill før du lagrer."); note.focus(); return; }
    if (new TextEncoder().encode(text).length > 2000) { errorAt(".compose-error", "Innspillet er for langt. Kort det ned før du lagrer."); note.focus(); return; }
    if (draft.proposal && new TextEncoder().encode(proposalInput.value.trim()).length > 2000) { errorAt(".compose-error", "Tekstforslaget er for langt. Kort det ned før du lagrer."); proposalInput.focus(); return; }
    if (draft.proposal && !proposalInput.value.trim()) { errorAt(".compose-error", "Skriv inn teksten du foreslår."); proposalInput.focus(); return; }
    const payload = { screen, kind: draft.proposal ? "edit" : draft.kind, anchor: draft.anchor, text };
    if (draft.proposal) payload.proposal = { property: "text", value: proposalInput.value.trim() };
    const submittedDraft = draft;
    savingDraft = submittedDraft;
    composer.setAttribute("aria-busy", "true");
    composer.querySelectorAll("button, textarea").forEach((target) => { target.disabled = true; });
    el(".save").textContent = "Lagrer …";
    errorAt(".compose-error", "");
    try {
      await request("comment-create", payload);
      if (draft !== submittedDraft) return;
      savingDraft = null;
      discardDraft();
      setPanel(true, true);
      announce("Innspillet er lagret lokalt. Send innspill når du er klar.");
    } catch (error) { errorAt(".compose-error", error.message); }
    finally {
      savingDraft = null;
      composer.setAttribute("aria-busy", "false");
      composer.querySelectorAll("button, textarea").forEach((target) => { target.disabled = false; });
      el(".save").textContent = "Lagre innspill";
      if (draft === submittedDraft) note.focus({ preventScroll: true });
      updateBusy();
    }
  }
  function commentRect(item) {
    if (item.screen !== screen) return null;
    const target = resolveTarget(item.anchor);
    if (!usableTarget(target) || !target.getClientRects().length || getComputedStyle(target).visibility === "hidden") return null;
    if (item.kind !== "area") {
      const rect = target.getBoundingClientRect();
      return rect && rect.width > 0 && rect.height > 0 ? rect : null;
    }
    if (workshop?.isComparing() || Math.abs(item.anchor.viewport.width - innerWidth) > 2) return null;
    const rect = item.anchor.rect;
    return { left: rect.x - scrollX, top: rect.y - scrollY, width: rect.width, height: rect.height, right: rect.x - scrollX + rect.width, bottom: rect.y - scrollY + rect.height };
  }
  function scheduleLayout() {
    if (layoutPending) return;
    layoutPending = true;
    requestAnimationFrame(() => {
      layoutPending = false;
      const toolbarTop = el(".toolbar").getBoundingClientRect().top;
      panel.style.bottom = `${Math.max(80, innerHeight - toolbarTop + 12)}px`;
      for (const target of [panel, el(".hint"), el(".preview-bar")]) target.style.top = `${topInset()}px`;
      for (const button of pinLayer.children) {
        const item = snapshot.comments.find((entry) => entry.id === button.dataset.id);
        const rect = item && commentRect(item);
        button.hidden = !rect || rect.bottom < 0 || rect.top > toolbarTop - 14 || rect.right < 0 || rect.left > innerWidth;
        if (!button.hidden) {
          button.style.left = `${Math.max(14, Math.min(innerWidth - 14, rect.left + Math.min(rect.width, 18)))}px`;
          button.style.top = `${Math.max(14, Math.min(toolbarTop - 14, rect.top + Math.min(rect.height, 10)))}px`;
        }
      }
      showDraftOutline();
      positionComposer();
    });
  }
  function button(text, action, id, className) {
    const result = document.createElement("button");
    result.type = "button";
    result.textContent = text;
    result.dataset.action = action;
    if (id) result.dataset.id = id;
    if (className) result.className = className;
    return result;
  }
  function span(text, className) { const result = document.createElement("span"); result.textContent = text; if (className) result.className = className; return result; }
  function renderComments() {
    const active = root.activeElement;
    const activeAction = active?.dataset.action;
    const activeId = active?.dataset.id;
    const activeDecision = active?.closest("[data-decision]")?.dataset.decision;
    const list = el(".list");
    const restoreCommentFocus = active && (list.contains(active) || pinLayer.contains(active));
    const focusIndex = Math.max(0, Array.from(list.children).indexOf(active?.closest(".comment,.workshop-decision")));
    list.replaceChildren();
    pinLayer.replaceChildren();
    let shown = 0;
    snapshot.comments.forEach((item, index) => {
      const previous = item.screen !== screen;
      if (filter !== "all" && item.status !== filter) return;
      if (!previous) {
        const pin = button(String(index + 1), "pin", item.id, `pin${item.status === "fixed" ? " fixed" : ""}`);
        pin.setAttribute("aria-label", `Innspill ${index + 1}, ${item.status === "fixed" ? "ordnet" : "åpent"}`);
        pin.hidden = true;
        pinLayer.appendChild(pin);
      }
      shown += 1;
      const card = document.createElement("article");
      card.className = `comment${item.status === "fixed" ? " fixed" : ""}`;
      card.dataset.id = item.id;
      card.tabIndex = -1;
      card.setAttribute("aria-label", `Innspill ${index + 1}`);
      const head = document.createElement("div");
      head.className = "row";
      head.append(span(String(index + 1), "number"), span(item.status === "fixed" ? "Ordnet" : "Åpent", "small"));
      if (previous) head.appendChild(span("Tidligere versjon", "badge old"));
      if (item.submission === 0) head.appendChild(span("Ikke sendt", "badge"));
      card.appendChild(head);
      const text = document.createElement("p");
      text.textContent = item.text;
      card.appendChild(text);
      if (item.proposal) {
        const value = document.createElement("div");
        value.className = "proposal";
        value.appendChild(span("Tekstforslag", "proposal-label"));
        value.appendChild(document.createTextNode(item.proposal.value));
        card.appendChild(value);
      }
      if (item.adjustment || item.variant) {
        const details = document.createElement("div");
        details.className = "proposal";
        const label = document.createElement("span");
        label.className = "proposal-label";
        label.textContent = item.adjustment ? "Justering" : "Foretrukket variant";
        details.appendChild(label);
        details.appendChild(document.createTextNode(workshop?.describeComment(item) || item.variant || ""));
        card.appendChild(details);
      }
      if (item.reply) {
        const reply = document.createElement("p");
        reply.className = "reply";
        const label = document.createElement("strong");
        label.textContent = "Svar";
        reply.append(label, document.createTextNode(item.reply));
        card.appendChild(reply);
      }
      if (!previous && item.kind === "area" && Math.abs(item.anchor.viewport.width - innerWidth) > 2) card.appendChild(span("Markering skjult ved denne vindusbredden", "muted"));
      else if (!previous && item.kind === "area" && workshop?.isComparing()) card.appendChild(span("Områdemarkering skjult under sammenligning", "muted"));
      const actions = document.createElement("div");
      actions.className = "comment-actions";
      if (!previous && commentRect(item)) actions.appendChild(button("Vis sted", "locate", item.id));
      if (!previous && item.proposal && eligibleText(resolveTarget(item.anchor))) actions.appendChild(button("Forhåndsvis tekst", "preview-saved", item.id));
      actions.append(button(item.status === "fixed" ? "Åpne igjen" : "Marker ordnet", "status", item.id), button("Slett", "delete", item.id, "danger"));
      card.appendChild(actions);
      list.appendChild(card);
    });
    if (filter === "all") shown += workshop?.appendFeedback(list) || 0;
    if (!shown) {
      const empty = document.createElement("div");
      empty.className = "empty";
      const title = document.createElement("strong");
      title.textContent = filter === "all" ? "Hva kan bli bedre?" : "Ingen innspill her ennå";
      const text = document.createElement("p");
      text.textContent = filter === "all" ? "Velg Kommenter, og pek på et element eller marker et område. Innspillene samles her." : "Velg et annet filter for å se resten.";
      empty.append(title, text);
      list.appendChild(empty);
    }
    all(".total").forEach((target) => { target.textContent = String(snapshot.comments.length + (snapshot.decisions?.length || 0)); });
    if (restoreCommentFocus) {
      const previousButton = activeAction && Array.from(list.querySelectorAll("button")).find((target) => !target.disabled && target.dataset.action === activeAction && (activeDecision ? target.dataset.decision === activeDecision : target.dataset.id === activeId));
      const cards = Array.from(list.querySelectorAll(".comment,.workshop-decision"));
      const target = previousButton || cards.find((card) => activeDecision ? card.dataset.decision === activeDecision : card.dataset.id === activeId) || cards[Math.min(focusIndex, cards.length - 1)] || el(`[data-filter="${filter}"]`);
      target.focus({ preventScroll: true });
    }
    renderFooter();
    scheduleLayout();
  }
  function renderFooter() {
    const count = pendingComments().length;
    const live = !connectionLost && Date.now() < (snapshot.listeningUntil || 0);
    el(".pending").textContent = count ? `${count} innspill ${count === 1 ? "klart" : "klare"} til sending` : sentCount ? `${sentCount} innspill sendt` : "Ingen nye innspill";
    el(".send").disabled = !count || submitting || connectionLost;
    el(".send").textContent = count ? `Send ${count} innspill` : "Send innspill";
    el(".connection").textContent = connectionLost ? "Frakoblet" : live ? "Følger med" : "Lagres lokalt";
    el(".connection").classList.toggle("live", live);
    const status = connectionLost ? "Innspill kan ikke lagres nå. Kopier teksten du vil beholde før du starter en ny økt." : live ? "Innspillene hentes når du sender." : "Skriv «se innspillene» i samtalen når du har sendt.";
    if (el(".foot-status").textContent !== status) el(".foot-status").textContent = status;
    updateBusy();
  }
  function applySnapshot(value) {
    if (!value || !Array.isArray(value.comments) || !Number.isSafeInteger(value.revision)) return;
    if (value.revision < snapshot.revision) return;
    const changed = snapshot.revision !== value.revision;
    snapshot = value;
    workshop?.render(snapshot);
    if (changed) renderComments();
    else renderFooter();
  }
  async function mutateComment(action, item) {
    errorAt(".panel-error", "");
    try {
      if (action === "delete") await request("comment-delete", { id: item.id });
      else {
        const reopening = item.status === "fixed";
        await request("comment-update", { id: item.id, status: reopening ? "open" : "fixed", ...(reopening ? { resubmit: true } : {}) });
        if (reopening) announce("Innspillet er åpnet igjen. Send innspill for å ta det opp i neste runde.");
      }
    } catch (error) { errorAt(".panel-error", error.message); }
  }
  function locate(item, focus = false) {
    if (!item || item.screen !== screen) return;
    const target = resolveTarget(item.anchor);
    if (item.kind === "area") window.scrollTo({ top: Math.max(0, item.anchor.rect.y - innerHeight / 3), behavior: "auto" });
    else target?.scrollIntoView({ block: "center", behavior: "auto" });
    showOutline(commentRect(item));
    if (focus) {
      setPanel(true);
      const card = Array.from(el(".list").children).find((entry) => entry.dataset.id === item.id);
      card?.scrollIntoView({ block: "nearest" });
      card?.focus({ preventScroll: true });
    } else focusPrototype(target);
  }

  root.addEventListener("click", (event) => {
    const target = event.target.closest("button");
    if (!target || target.disabled || saving()) return;
    const action = target.dataset.action;
    const item = snapshot.comments.find((entry) => entry.id === target.dataset.id);
    if (target.dataset.filter) {
      filter = target.dataset.filter;
      all("[data-filter]").forEach((entry) => entry.setAttribute("aria-pressed", String(entry.dataset.filter === filter)));
      renderComments();
    } else if (action === "browse" || action === "comment") setMode(action);
    else if (action === "point" || action === "area") setMode("comment", action);
    else if (action === "panel") setPanel(panel.hidden, true);
    else if (action === "close-panel") setPanel(false, true);
    else if (action === "save") void saveDraft();
    else if (action === "discard") discardDraft();
    else if (action === "hide-draft") hideDraft();
    else if (action === "resume") resumeDraft();
    else if (action === "undo") {
      const original = preview?.target;
      resetPreview();
      if (!composer.hidden) proposalInput.focus();
      else focusPrototype(original);
    }
    else if (action === "proposal" && draft) {
      draft.proposal = !draft.proposal;
      target.setAttribute("aria-expanded", String(draft.proposal));
      el(".proposal-fields").hidden = !draft.proposal;
      if (!draft.proposal) resetPreview();
      positionComposer();
      if (draft.proposal) proposalInput.focus();
    } else if (action === "preview-draft" && draft) {
      if (preview) resetPreview();
      else if (!showPreview(draft.target, proposalInput.value)) { errorAt(".compose-error", "Skriv inn teksten du vil forhåndsvise."); proposalInput.focus(); }
    } else if (action === "preview-saved" && item) {
      showPreview(resolveTarget(item.anchor), item.proposal.value);
      setPanel(false);
      el('[data-action="undo"]').focus();
    } else if ((action === "status" || action === "delete") && item) void mutateComment(action, item);
    else if (action === "pin" && item) {
      if (filter !== "all" && filter !== item.status) {
        filter = "all";
        all("[data-filter]").forEach((entry) => entry.setAttribute("aria-pressed", String(entry.dataset.filter === filter)));
        renderComments();
      }
      locate(item, true);
    } else if (action === "locate" && item) { setPanel(false); locate(item); }
    else if (action === "refresh" && !busy()) post({ action: "refresh-now", screen });
    else if (action === "send" && !submitting) {
      submitting = true;
      const count = pendingComments().length;
      target.disabled = true;
      errorAt(".panel-error", "");
      request("comments-submit", { revision: snapshot.revision }).then(() => {
        sentCount = count;
        announce("Innspillene er sendt. Skriv «se innspillene» i samtalen hvis ingen følger med.");
      }).catch((error) => errorAt(".panel-error", error.message)).finally(() => { submitting = false; renderFooter(); });
    }
  });
  proposalInput.addEventListener("input", () => {
    if (preview && draft?.proposal) showPreview(draft.target, proposalInput.value);
  });
  root.addEventListener("keydown", (event) => {
    if (saving()) return;
    if (event.target.closest(".toolbar") && ["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      const buttons = all(".toolbar button").filter((target) => !target.disabled && target.getClientRects().length);
      const index = buttons.indexOf(event.target.closest("button"));
      const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
      event.preventDefault();
      buttons[next]?.focus();
    }
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && !composer.hidden) { event.preventDefault(); void saveDraft(); }
    if (event.key !== "Escape") return;
    event.preventDefault();
    event.stopPropagation();
    if (!composer.hidden) hideDraft();
    else if (!panel.hidden) setPanel(false, true);
    else if (preview) resetPreview();
    else { setMode("browse"); el('[data-action="browse"]').focus(); }
  });

  document.addEventListener("click", (event) => {
    if (ownEvent(event)) return;
    if (workshop?.onPrototypeClick(event)) { event.preventDefault(); event.stopImmediatePropagation(); return; }
    if (mode === "comment") {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (marker === "point") beginDraft(event.target, "point", null, { x: event.clientX, y: event.clientY });
      return;
    }
    const link = event.target.closest("a, area");
    if (link) { event.preventDefault(); return; }
    const choice = choiceFor(event.target);
    if (!choice) return;
    event.preventDefault();
    toggleSelect(choice);
  }, true);
  document.addEventListener("pointerdown", (event) => {
    if (mode !== "comment" || marker !== "area" || ownEvent(event) || event.button !== 0 || !usableTarget(event.target)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (workshop?.isComparing()) { announce("Avslutt sammenligning for å markere et område. Punkt kan brukes nå."); return; }
    if (draft) { resumeDraft(); return; }
    drag = { x: event.clientX, y: event.clientY, target: event.target, pointerId: event.pointerId };
    updateBusy();
    showOutline({ left: drag.x, top: drag.y, width: 1, height: 1 });
  }, true);
  document.addEventListener("pointermove", (event) => {
    if (mode !== "comment") return;
    if (drag) {
      event.preventDefault();
      showOutline({ left: Math.min(drag.x, event.clientX), top: Math.min(drag.y, event.clientY), width: Math.abs(event.clientX - drag.x), height: Math.abs(event.clientY - drag.y) });
    } else if (!draft && !ownEvent(event) && usableTarget(event.target)) showOutline(event.target.getBoundingClientRect());
    else if (!draft && ownEvent(event)) outline.hidden = true;
  }, { capture: true, passive: false });
  document.addEventListener("pointerup", (event) => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const start = drag;
    drag = null;
    const rect = Math.abs(event.clientX - start.x) + Math.abs(event.clientY - start.y) < 8 ? start.target.getBoundingClientRect()
      : { left: Math.min(start.x, event.clientX), top: Math.min(start.y, event.clientY), width: Math.max(1, Math.abs(event.clientX - start.x)), height: Math.max(1, Math.abs(event.clientY - start.y)) };
    beginDraft(start.target, "area", rect, { x: event.clientX, y: event.clientY });
    updateBusy();
  }, true);
  document.addEventListener("pointercancel", () => { drag = null; if (!draft) outline.hidden = true; updateBusy(); }, true);
  document.addEventListener("focusin", (event) => {
    if (mode === "comment" && !draft && !ownEvent(event) && usableTarget(event.target)) showOutline(event.target.getBoundingClientRect());
  });
  for (const eventName of ["auxclick", "contextmenu"]) {
    document.addEventListener(eventName, (event) => {
      if (!ownEvent(event) && event.target.closest("a, area")) event.preventDefault();
    }, true);
  }
  document.addEventListener("submit", (event) => event.preventDefault(), true);
  document.addEventListener("keydown", (event) => {
    if (ownEvent(event)) return;
    if (event.key === "Escape") {
      if (!composer.hidden) hideDraft();
      else if (preview) resetPreview();
      else if (!panel.hidden) setPanel(false, true);
      else setMode("browse");
      return;
    }
    if (mode === "comment" && (event.key === "Enter" || event.key === " ") && usableTarget(event.target)) {
      event.preventDefault();
      beginDraft(event.target, marker, marker === "area" ? event.target.getBoundingClientRect() : null);
      return;
    }
    const choice = choiceFor(event.target);
    if (!choice || (event.key !== "Enter" && event.key !== " ")) return;
    event.preventDefault();
    toggleSelect(choice);
  });
  window.addEventListener("scroll", scheduleLayout, { passive: true });
  window.addEventListener("resize", () => { renderComments(); });
  if (typeof ResizeObserver === "function") {
    const observer = new ResizeObserver(scheduleLayout);
    observer.observe(document.body);
    observer.observe(el(".toolbar"));
    const header = document.body.querySelector(":scope > .vc-header");
    if (header) observer.observe(header);
  }

  window.addEventListener("message", (message) => {
    if (message.source !== parent || !message.data) return;
    const data = message.data;
    if (data.channel !== channel || data.version !== 1) return;
    if (data.command === "connection-lost" || data.command === "connection-restored") {
      connectionLost = data.command === "connection-lost";
      renderFooter();
      announce(connectionLost ? "Forbindelsen er brutt. Utkast kan kopieres, men ikke lagres nå." : "Forbindelsen er tilbake.");
      return;
    }
    if (data.command === "refreshing") {
      document.getElementById("refresh-indicator")?.classList.add("visible");
      return;
    }
    if (data.command === "update-available") {
      document.getElementById("refresh-indicator")?.classList.remove("visible");
      updateAvailable = true;
      updateBusy();
      announce("En ny versjon er klar. Fullfør innspillene og velg Vis ny versjon.");
      return;
    }
    if (data.command === "comments-snapshot") { applySnapshot(data.snapshot); return; }
    if (data.command === "comments-result") {
      const pending = requests.get(data.requestId);
      if (!pending) return;
      window.clearTimeout(pending.timer);
      requests.delete(data.requestId);
      if (data.snapshot) applySnapshot(data.snapshot);
      updateBusy();
      if (data.ok) pending.resolve(data.snapshot);
      else pending.reject(new Error(data.conflict === true ? "Listen er endret. Se gjennom innspillene og send på nytt." : "Kunne ikke lagre innspillet. Behold utkastet og prøv igjen."));
      return;
    }
    if (data.command !== "selection-status" || data.screen !== screen || !pendingEvent || data.type !== pendingEvent.type || data.choice !== pendingEvent.choice || (data.status !== "saved" && data.status !== "failed")) return;
    persistenceStatus = data.status;
    pendingEvent = null;
    updateIndicator();
  });
  if (typeof window.__grillmesterInitializeWorkshop === "function") {
    workshop = window.__grillmesterInitializeWorkshop({
      root, screen, nonce, request, anchorFor, announce, topInset,
      getSnapshot: () => snapshot,
      onBusyChange: updateBusy,
      onPresentationChange: () => { updateHint(); renderComments(); },
      refreshFeedback: renderComments,
      showFeedbackError: (message) => errorAt(".panel-error", message),
      isComposing: () => Boolean(draft && !composer.hidden),
      prepareOpen: () => {
        if (savingDraft) return false;
        if (draft && !composer.hidden) hideDraft();
        setMode("browse"); setPanel(false); return true;
      },
      openFeedback: () => setPanel(true, true),
    });
  }
  post({ action: "feedback-ready", screen });
  renderComments();
  request("comments-list", {}).catch((error) => errorAt(".panel-error", error.message));
  window.setInterval(renderFooter, 1000);
})();
