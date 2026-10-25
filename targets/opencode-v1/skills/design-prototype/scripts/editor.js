// Loaded in <head>: read declared bindings once the sketch is parsed.
((start) => (document.readyState === "loading"
  ? document.addEventListener("DOMContentLoaded", start, { once: true })
  : start()))(() => {
  "use strict";
  const design = window.__grillmesterVisualCompanionDesign;
  const descriptor = design?.version === 2 ? design : null;
  const bindings = new Map();
  const matches = (name, value, within = document) => Array.from(within.querySelectorAll(`[${name}]`)).filter(node => node.getAttribute(name) === value);
  let valid = Boolean(descriptor);
  for (const field of descriptor?.texts || []) {
    const found = matches("data-vc-text", field.id);
    const node = found.length === 1 ? found[0] : null;
    if (!node || node.tagName !== "SPAN" || node.childElementCount || !document.body.querySelector(":scope > .vc-content")?.contains(node)) valid = false;
    bindings.set(`text:${field.id}`, { node, kind: "text", value: field.value });
  }
  for (const target of descriptor?.targets || []) {
    const wrappers = target.variant ? matches("data-vc-variant", target.variant) : [document];
    const wrapper = wrappers.length === 1 ? wrappers[0] : null;
    const found = wrapper ? matches("data-vc-key", target.key, wrapper).filter(node => target.variant ? node.closest("[data-vc-variant]") === wrapper : !node.closest("[data-vc-variant]")) : [];
    for (const control of target.controls.filter(item => item.editable === true)) {
      const node = found.length === 1 ? found[0] : null;
      if (!node) valid = false;
      bindings.set(`control:${target.variant || ""}/${target.key}/${control.id}`, { node, kind: "control", attribute: `data-vc-setting-${control.id}`, value: control.initial });
    }
  }
  // Validate every binding before applying any canonical text. Untrusted markup
  // cannot pick an arbitrary selector, collect form values or supply an action.
  if (valid) for (const binding of bindings.values()) if (binding.kind === "text") binding.node.textContent = binding.value;

  window.__grillmesterInitializeEditor = api => {
    const { root, nonce, request, announce } = api;
    const style = document.createElement("style"); style.nonce = nonce;
    style.textContent = `.source-editor{pointer-events:auto;position:fixed;right:16px;top:64px;bottom:90px;width:min(366px,calc(100vw - 32px));display:flex;flex-direction:column;background:#fff;border:1px solid #dfd8e8;border-radius:16px;box-shadow:0 12px 48px #25163826;overflow:hidden}.source-editor h2{font-size:17px;margin:0}.source-editor h3{font-size:13px;margin:0}.source-editor-head{padding:14px 16px;border-bottom:1px solid #ece8f0;flex-shrink:0}.source-editor-head p,.source-editor-foot p{font-size:12px;margin:8px 0;line-height:1.5}.source-editor-body{padding:16px;overflow:auto;overscroll-behavior:contain;min-height:0;scroll-padding:12px}.source-editor-foot{padding:12px 16px;border-top:1px solid #ece8f0;flex-shrink:0}.source-editor-field{margin-bottom:18px}.source-editor-field label{display:block;font-size:12px;font-weight:600;margin-bottom:7px}.source-editor-field textarea,.source-editor-field select{width:100%;font:inherit;font-size:13px;color:#302737;background:#fff;border:1px solid #8b7a9a;border-radius:8px;padding:9px}.source-editor-field textarea{min-height:76px;resize:vertical}.source-editor-field select:focus-visible{outline:3px solid #6852ce;outline-offset:2px}.source-editor-field p{font-size:11px;margin:6px 0;line-height:1.5}.source-editor-field button{font-size:11px;padding:6px}.source-editor-hold{color:#65506f}.source-editor-actions{display:flex;flex-wrap:wrap;gap:6px}.source-editor-error{margin:0 0 12px}.source-editor-conflict{font-size:12px;color:#80591d;margin:0 0 12px}.source-editor-change-count{font-size:12px;color:#685c74}.source-editor-status:empty{display:none}@media(max-width:600px){.source-editor{right:10px;width:calc(100vw - 20px)}}@media(max-height:540px){.source-editor{overflow-y:auto}.source-editor-body{overflow:visible;flex-shrink:0}.source-editor-foot{position:sticky;bottom:0;background:#fff;z-index:1}}`;
    root.appendChild(style);
    const markup = document.createElement("div");
    markup.innerHTML = `<section class="source-editor" aria-label="Rediger skissen" hidden><div class="source-editor-head"><div class="row between"><h2>Rediger skissen</h2><button type="button" class="close" data-editor-action="close" aria-label="Lukk redigering">×</button></div><p>Lagre tekst og valg som en ny versjon. Ingen innspill sendes.</p></div><div class="source-editor-body"><p id="source-editor-error" class="source-editor-error error" role="alert" hidden></p><p class="source-editor-conflict" hidden>En nyere versjon eller et nylig lagret felt er tilgjengelig. Utkastet ditt er beholdt. Kopier det du vil ta videre, eller forkast endringene før du åpner den nye versjonen.</p><div class="source-editor-fields"></div></div><div class="source-editor-foot"><p class="source-editor-change-count"></p><div class="source-editor-actions"><button type="button" class="primary" data-editor-action="save">Lagre som ny versjon</button><button type="button" data-editor-action="discard">Forkast endringer</button><button type="button" data-editor-action="read" hidden>Hent feltene igjen</button></div><p class="source-editor-status" role="status"></p></div></section>`;
    root.appendChild(markup);
    const el = selector => markup.querySelector(selector), pane = el(".source-editor");
    // A direct toolbar entry: editing saved text should not hide behind "Juster".
    const toolbarButton = document.createElement("button");
    toolbarButton.type = "button"; toolbarButton.dataset.action = "editor-open"; toolbarButton.textContent = "Rediger"; toolbarButton.hidden = true;
    toolbarButton.addEventListener("click", () => { if (!toolbarButton.disabled) void open(); });
    root.querySelector(".toolbar").appendChild(toolbarButton);
    let baseline = null, fields = [], holds = [], values = new Map(), loading = false, writing = false, stale = false, needsRebase = false, capacity = false, saved = false;
    let saveRetry = {}, releaseRetries = new Map();
    const preview = new Map();
    const dirty = () => fields.some(field => values.get(field.id) !== field.value);
    const changes = () => fields.filter(field => values.get(field.id) !== field.value).map(field => ({ id: field.id, value: values.get(field.id) }));
    const status = value => { if (el(".source-editor-status").textContent !== value) el(".source-editor-status").textContent = value; };
    function error(value, input) {
      const target = el(".source-editor-error"); target.textContent = value || ""; target.hidden = !value;
      if (input) input.before(target); else el(".source-editor-body").prepend(target);
      if (value) { if (input) input.focus(); target.scrollIntoView({ block: "nearest" }); }
    }
    function restorePreview() {
      for (const [id, value] of preview) {
        const binding = bindings.get(id);
        if (!binding?.node?.isConnected) continue;
        if (binding.kind === "text") binding.node.textContent = value;
        else if (value === null) binding.node.removeAttribute(binding.attribute);
        else binding.node.setAttribute(binding.attribute, value);
      }
      preview.clear();
    }
    function showPreview() {
      if (!valid || pane.hidden || saved) return;
      for (const field of fields) {
        const binding = bindings.get(field.id), value = values.get(field.id);
        if (!binding) continue;
        if (!preview.has(field.id)) preview.set(field.id, binding.kind === "text" ? binding.node.textContent : binding.node.getAttribute(binding.attribute));
        if (binding.kind === "text") binding.node.textContent = value;
        else binding.node.setAttribute(binding.attribute, value);
      }
    }
    function layout() {
      pane.style.top = `${api.topInset()}px`;
      pane.style.bottom = `${Math.max(80, innerHeight - root.querySelector(".toolbar").getBoundingClientRect().top + 12)}px`;
    }
    function update() {
      const count = changes().length, blocked = loading || writing || api.isRefreshing();
      const sameRetry = baseline && saveRetry.intent === JSON.stringify(["workspace-editor-save", { screen: baseline.screen, expectedRevision: baseline.revision, changes: changes() }]);
      pane.setAttribute("aria-busy", String(blocked));
      markup.querySelectorAll("button,textarea,select").forEach(node => { node.disabled = blocked; });
      el('[data-editor-action="save"]').disabled = blocked || !baseline || !count || stale || needsRebase || capacity || saved;
      el('[data-editor-action="save"]').textContent = writing ? "Lagrer …" : capacity ? "Lagringsgrensen er nådd" : sameRetry ? "Prøv samme lagring igjen" : "Lagre som ny versjon";
      el('[data-editor-action="discard"]').disabled = blocked || !count;
      el('[data-editor-action="read"]').hidden = Boolean(baseline) && !needsRebase || loading || saved;
      el('[data-editor-action="read"]').textContent = baseline ? "Oppdater grunnlaget" : "Hent feltene igjen";
      if (saved) markup.querySelectorAll("textarea,select,[data-editor-action=release]").forEach(node => { node.disabled = true; });
      el(".source-editor-conflict").hidden = !stale;
      el(".source-editor-change-count").textContent = count ? `${count} ${count === 1 ? "ulagret endring" : "ulagrede endringer"}` : "Ingen ulagrede endringer";
      api.onBusyChange(); layout();
    }
    function renderFields() {
      el(".source-editor-body").prepend(el(".source-editor-error"));
      const container = el(".source-editor-fields"); container.replaceChildren();
      for (const [index, field] of fields.entries()) {
        const group = document.createElement("div"); group.className = "source-editor-field"; group.dataset.fieldId = field.id;
        const label = document.createElement("label"), input = document.createElement(field.kind === "text" ? "textarea" : "select");
        input.id = `source-editor-field-${index}`; label.htmlFor = input.id; label.textContent = field.label;
        input.setAttribute("aria-describedby", "source-editor-error");
        if (field.kind === "text") input.maxLength = 2000;
        else for (const option of field.options || []) { const item = document.createElement("option"); item.value = option.value; item.textContent = option.label; input.appendChild(item); }
        input.value = values.get(field.id);
        input.addEventListener(field.kind === "text" ? "input" : "change", () => {
          if (writing || loading || api.isRefreshing()) return;
          values.set(field.id, input.value); input.removeAttribute("aria-invalid"); error(""); showPreview(); update();
        });
        group.append(label, input);
        if (field.locked || holds.some(hold => hold.id === field.id)) {
          const kept = document.createElement("p"); kept.className = "source-editor-hold"; kept.textContent = "Din lagrede verdi beholdes ved nye versjoner. Du kan endre den her.";
          const release = document.createElement("button"); release.type = "button"; release.dataset.editorAction = "release"; release.dataset.fieldId = field.id; release.textContent = "Tillat senere endring"; release.setAttribute("aria-label", `Tillat senere endring for ${field.label}`);
          const explain = document.createElement("p"); explain.textContent = "Verdien beholdes nå, men senere versjoner kan endre den.";
          group.append(kept, release, explain);
        }
        container.appendChild(group);
      }
      update();
    }
    async function read() {
      if (loading || writing || dirty() && !needsRebase) return;
      const rebasing = Boolean(baseline && needsRebase);
      let accepted = false;
      loading = true; error(""); status("Henter redigerbare felt …"); update();
      try {
        const result = await request("workspace-editor-read", {});
        if (!valid || !result || result.screen !== api.screen || !Array.isArray(result.fields) || !Array.isArray(result.holds) || result.fields.some(field => !bindings.has(field.id) || field.kind !== bindings.get(field.id).kind)) throw new Error("Feltene stemmer ikke med denne versjonen. Åpne den nyeste versjonen før du redigerer.");
        if (baseline && dirty() && (result.screen !== baseline.screen || fields.some(field => result.fields.find(other => other.id === field.id)?.value !== field.value))) { stale = true; throw new Error("Skissekilden er endret. Utkastet ditt er beholdt. Forkast endringene før du åpner den nye versjonen."); }
        const retained = dirty() ? values : null;
        baseline = result; fields = result.fields; holds = result.holds; values = new Map(fields.map(field => [field.id, retained?.get(field.id) ?? field.value])); stale = false; needsRebase = false; saveRetry = {}; releaseRetries.clear();
        renderFields(); showPreview(); status(retained ? "Grunnlaget er oppdatert. Utkastet ditt er beholdt. Se gjennom og lagre når du er klar." : fields.length ? "" : "Denne skissen har ingen redigerbare felt.");
        accepted = true;
      } catch (failure) { error(failure.message); status(""); }
      finally { loading = false; update(); if (rebasing && accepted) el('[data-editor-action="save"]').focus(); }
    }
    async function open() {
      if (!descriptor || !api.prepareOpen()) return;
      pane.hidden = false; layout(); el('[data-editor-action="close"]').focus();
      if (!valid) { error("Skissens tekstfelt er ikke entydige. Be om å rette skissekilden før du redigerer."); update(); return; }
      if (!baseline) await read(); else { showPreview(); update(); }
    }
    function close(focus = false) {
      if (writing || api.isRefreshing()) return;
      restorePreview(); pane.hidden = true; api.onBusyChange();
      if (focus) api.focusOpener();
    }
    function discard() {
      if (writing || api.isRefreshing()) return;
      restorePreview(); values = new Map(fields.map(field => [field.id, field.value])); saveRetry = {}; error("");
      if (stale || needsRebase) { baseline = null; fields = []; values.clear(); stale = false; needsRebase = false; pane.hidden = true; api.onBusyChange(); api.focusOpener(); announce("Redigeringsutkastet er forkastet. Den nye versjonen kan åpnes."); return; }
      renderFields(); status("Endringene er forkastet.");
    }
    async function save() {
      if (el('[data-editor-action="save"]').disabled) return;
      for (const field of fields) {
        const value = values.get(field.id), input = Array.from(el(".source-editor-fields").children).find(node => node.dataset.fieldId === field.id)?.querySelector("textarea,select");
        if (field.kind === "text" && new TextEncoder().encode(value).length > 2000) { input?.setAttribute("aria-invalid", "true"); error("Teksten er for lang. Kort den ned før du lagrer.", input); return; }
        if (field.kind === "control" && !field.options?.some(option => option.value === value)) { error("Velg et av de tilgjengelige alternativene.", input); return; }
      }
      writing = true; error(""); status("Lagrer en ny skisseversjon …"); update();
      try {
        await request("workspace-editor-save", { screen: baseline.screen, expectedRevision: baseline.revision, changes: changes() }, saveRetry);
        restorePreview(); fields = fields.map(field => ({ ...field, value: values.get(field.id) })); saved = true;
        status("Den nye versjonen er lagret. Ingen innspill er sendt.");
        api.openSavedVersion();
      } catch (failure) {
        if (failure.conflict || failure.editorConflict) { needsRebase = true; if (!failure.editorConflict) stale = true; }
        if (failure.capacity) capacity = true;
        error(failure.editorConflict ? "Endringen strider mot en del du har valgt å beholde. Utkastet ditt er beholdt. Lukk redigeringen og velg «Slutt å beholde» eller oppdater «Behold dette» før du fortsetter." : failure.message);
        status("");
      } finally { writing = false; update(); }
    }
    async function release(id) {
      if (!baseline || writing || loading || api.isRefreshing()) return;
      let released = false;
      if (!releaseRetries.has(id)) releaseRetries.set(id, {});
      writing = true; error(""); status("Tillater senere endring …"); update();
      try {
        const result = await request("workspace-editor-release", { screen: baseline.screen, expectedRevision: baseline.revision, ids: [id] }, releaseRetries.get(id));
        baseline.revision = result.revision; holds = holds.filter(hold => hold.id !== id); fields = fields.map(field => field.id === id ? { ...field, locked: false } : field);
        releaseRetries.delete(id); renderFields(); status("Senere endring er tillatt. Verdien er beholdt, og ingen innspill er sendt."); released = true;
      } catch (failure) { if (failure.conflict) { stale = true; needsRebase = true; } error(failure.message); status(""); }
      finally { writing = false; update(); if (released) Array.from(el(".source-editor-fields").children).find(node => node.dataset.fieldId === id)?.querySelector("textarea,select")?.focus(); }
    }
    markup.addEventListener("click", event => {
      const target = event.target.closest("button[data-editor-action]"); if (!target || target.disabled) return;
      const action = target.dataset.editorAction;
      if (action === "close") close(true); else if (action === "save") void save(); else if (action === "discard") discard(); else if (action === "read") void read(); else if (action === "release") void release(target.dataset.fieldId);
    });
    markup.addEventListener("keydown", event => { if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(true); } });
    window.addEventListener("resize", layout);
    return {
      open, close, isDirty: dirty, isOpen: () => !pane.hidden, isSaving: () => writing || loading,
      refreshControls: update,
      onSnapshot(snapshot) { toolbarButton.hidden = !descriptor || snapshot.workspace?.storage !== "project"; if (baseline && snapshot.workspace?.version !== baseline.workspaceVersion && dirty() && !writing && !saveRetry.intent) { stale = true; needsRebase = true; } if (!pane.hidden) update(); },
    };
  };
});
