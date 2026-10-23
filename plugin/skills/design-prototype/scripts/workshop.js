(() => {
  "use strict";

  // The descriptor declares every available choice. Preview changes never read
  // source text, form values, or arbitrary selectors, and never edit source files.
  window.__grillmesterInitializeWorkshop = (api) => {
    const { root, screen, nonce, request, anchorFor, announce } = api;
    const design = window.__grillmesterVisualCompanionDesign;
    const descriptor = design && design.version === 1 ? design : null;
    const variants = descriptor?.variants || [];
    const targets = descriptor?.targets || [];
    const bindings = new Map();
    const variantBindings = new Map();
    const identifier = (target) => `${target.variant || ""}/${target.key}`;
    const signature = (values) => JSON.stringify(Object.entries(values).sort(([a], [b]) => a.localeCompare(b)));
    const initialValues = (target) => Object.fromEntries(target.controls.map((control) => [control.id, control.initial]));
    const matches = (attribute, value, within = document) => Array.from(within.querySelectorAll(`[${attribute}]`)).filter((element) => element.getAttribute(attribute) === value);
    for (const variant of variants) {
      const found = matches("data-vc-variant", variant.key);
      variantBindings.set(variant.key, { ...variant, element: found.length === 1 ? found[0] : null });
    }
    for (const target of targets) {
      const wrapper = target.variant ? variantBindings.get(target.variant)?.element : document;
      const found = wrapper ? matches("data-vc-key", target.key, wrapper).filter((element) => target.variant
        ? element.closest("[data-vc-variant]") === wrapper
        : !element.closest("[data-vc-variant]")) : [];
      const values = initialValues(target);
      bindings.set(identifier(target), { descriptor: target, element: found.length === 1 ? found[0] : null, values, accepted: signature(values), remark: "" });
    }
    const comparisonParent = variants.length >= 2 ? variantBindings.get(variants[0].key)?.element?.parentElement : null;
    const frameContent = document.body.querySelector(":scope > .vc-content");
    const comparisonAvailable = Boolean(document.querySelectorAll("[data-vc-variants]").length === 1 && comparisonParent?.hasAttribute("data-vc-variants") && variants.every((variant) => {
      const element = variantBindings.get(variant.key)?.element;
      return element && element.parentElement === comparisonParent;
    }));
    let selectedKey = bindings.keys().next().value || "";
    let comparing = false;
    let pair = variants.slice(0, 2).map((variant) => variant.key);
    let activeVariant = pair[0] || "";
    let preferredVariant = pair[0] || "";
    let locking = false;
    let lastRevision = -1;
    let snapshot = api.getSnapshot();
    const savedStyles = new Map();
    const saveRetries = new Map();
    const selected = () => bindings.get(selectedKey);
    const hasDraft = (binding) => Boolean(binding.conflict || binding.remark.trim() || signature(binding.values) !== binding.accepted);
    const pending = () => Array.from(bindings.values()).some(hasDraft);
    const currentDecision = (binding) => snapshot.decisions?.find((item) => item.variant === (binding.descriptor.variant || "") && item.target === binding.descriptor.key && (item.state === "active" || (item.state === "released" && item.submission === 0)));
    function beginEdit(binding) { if (binding.expectedRevision === undefined) binding.expectedRevision = currentDecision(binding)?.revision || 0; }

    const style = document.createElement("style");
    style.nonce = nonce;
    style.textContent = `
      .workshop{pointer-events:auto;position:fixed;right:16px;top:64px;bottom:92px;width:min(366px,calc(100vw - 32px));display:flex;flex-direction:column;background:#fff;border:1px solid #dfd8e8;border-radius:16px;box-shadow:0 12px 48px #25163826;overflow:hidden}.workshop h2{margin:0;font-size:17px;letter-spacing:-.3px}.workshop h3{font-size:13px;margin:0 0 10px}.workshop-head{padding:16px 18px 12px;border-bottom:1px solid #e9e3ef}.workshop-head p{font-size:12px;color:#706578;margin:8px 0 0}.workshop-body{padding:16px 18px;overflow-y:auto;overscroll-behavior:contain;min-height:0}.workshop label{display:block;font-size:12px;font-weight:600;margin:0 0 7px}.workshop select,.workshop textarea{width:100%;font:inherit;font-size:13px;color:#302737;background:#fff;border:1px solid #8b7a9a;border-radius:8px;padding:9px}.workshop select:focus-visible,.workshop input:focus-visible{outline:3px solid #6852ce;outline-offset:3px}.workshop textarea{min-height:68px;resize:vertical}.workshop-section{padding-bottom:16px;margin-bottom:16px;border-bottom:1px solid #ece7f1}.workshop-section:last-child{border-bottom:0;margin-bottom:0}.workshop-control{margin-top:17px}.workshop-control input[type=range]{width:100%;accent-color:#7133a2}.workshop-control input[type=checkbox]{accent-color:#7133a2;width:18px;height:18px;vertical-align:middle;margin:0 7px 0 0}.workshop-control output{display:block;color:#706578;font-size:11px;margin-top:5px}.workshop-actions{display:flex;flex-wrap:wrap;gap:7px;margin-top:13px}.workshop-actions button{font-size:12px}.workshop-actions .primary{flex:1}.workshop-foot{padding:12px 18px;border-top:1px solid #e9e3ef;font-size:11px;color:#706578}.workshop-status{font-size:12px;color:#5c3d70;margin:9px 0 0;min-height:17px}.workshop-warning{font-size:12px;line-height:1.5;color:#855514;background:#fff7e7;padding:10px;border-radius:8px;margin:12px 0}.workshop-empty{font-size:12px;color:#706578;line-height:1.5}.workshop-keep-list{display:grid;gap:10px}.workshop-decision{border:1px solid #dce6df;border-radius:9px;padding:11px;overflow-wrap:anywhere}.workshop-decision.followup{border-color:#e9d5ad;background:#fffcf6}.workshop-decision.released{border-color:#e6e1e9;background:#faf9fb}.workshop-decision h4{font-size:12px;margin:0 0 5px}.workshop-decision p{font-size:12px;white-space:pre-wrap;margin:7px 0}.workshop-decision .decision-state{font-size:11px;font-weight:600;color:#2d7350}.workshop-decision.followup .decision-state{color:#855514}.workshop-decision.released .decision-state{color:#706578}.workshop-decision ul{font-size:11px;line-height:1.6;margin:7px 0;padding-left:16px}.workshop-decision button{font-size:11px;min-height:30px;padding:6px 8px}.workshop-decision .badge{margin-left:5px}.compare-bar{pointer-events:auto;position:fixed;top:64px;left:16px;max-width:calc(100vw - 32px);padding:10px 12px;background:#fff;border:1px solid #dfd8e8;border-radius:12px;box-shadow:0 4px 22px #2516381a;display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12px}.compare-bar label{font-size:11px;color:#706578}.compare-bar select{font:inherit;max-width:145px;padding:6px;border:1px solid #8b7a9a;border-radius:6px;color:#302737;background:#fff}.compare-bar button{font-size:12px;min-height:31px;padding:6px 9px}.compare-tabs{display:flex;gap:4px}.compare-tabs button[aria-pressed=true]{background:#f0e8f7;color:#7133a2}.compare-bar .pair-select{display:flex;align-items:center;gap:5px}.compare-bar .prefer{color:#7133a2;background:#f6f0fa}.workshop-compare-button[aria-pressed=true]{background:#f0e8f7;color:#7133a2}
      @media(max-width:759px){.workshop{left:10px;right:10px;top:64px;width:auto}.compare-bar{top:62px;left:10px;right:10px;max-width:none}.compare-bar .pair-select{display:none}.compare-bar .prefer{font-size:11px}.workshop-body{padding:14px}}
      @media(max-height:540px){.workshop{overflow-y:auto;overscroll-behavior:contain}.workshop-head,.workshop-body,.workshop-foot{flex-shrink:0}.workshop-body{overflow:visible}.compare-bar{max-height:calc(100dvh - 110px);overflow-y:auto}}
      .workshop,.workshop-body,.compare-bar{scroll-padding:8px}
      .keep-conflict{overflow-wrap:anywhere}.keep-conflict p{white-space:pre-wrap}
      @media(max-width:759px){.compare-bar.has-many .pair-select{display:flex;flex:1 1 calc(50% - 8px);min-width:0}.compare-bar.has-many .pair-select select{width:100%;min-width:0}.compare-bar.has-many .pair-select label{flex-shrink:0}}
    `;
    root.appendChild(style);
    const markup = document.createElement("div");
    markup.innerHTML = `
      <section class="workshop" aria-label="Juster skissen" hidden>
        <div class="workshop-head"><div class="row between"><h2>Juster skissen</h2><button type="button" class="close" data-action="workshop-close" aria-label="Lukk justeringer">×</button></div><p>Prøv mulighetene i skissen. Legg valgene til innspill når du er klar.</p></div>
        <div class="workshop-body">
          <div class="workshop-section workshop-editor"><label for="workshop-target">Velg del</label><select id="workshop-target" aria-label="Velg del"></select><p class="workshop-warning target-warning" hidden></p><div class="workshop-controls"></div>
            <div class="workshop-actions"><button type="button" data-action="workshop-reset">Tilbakestill visning</button></div>
            <label for="workshop-remark">Merknad</label><textarea id="workshop-remark" maxlength="2000" placeholder="Valgfritt: forklar hva du vil ta videre"></textarea>
            <div class="workshop-warning keep-conflict" tabindex="-1" hidden><strong>Delen er endret et annet sted.</strong><p class="keep-conflict-summary"></p><p>Ditt valg og merknaden din er beholdt her.</p><button type="button" data-action="workshop-replace">Bruk mitt valg i stedet</button><button type="button" data-action="workshop-discard-conflict">Forkast mitt utkast</button></div>
            <div class="workshop-actions"><button type="button" class="primary" data-action="workshop-add">Legg til innspill</button><button type="button" data-action="workshop-keep">Behold dette</button></div>
          </div>
          <div class="workshop-section workshop-comparison"><h3>Se variantene sammen</h3><button type="button" class="workshop-compare-button" data-action="workshop-compare" aria-pressed="false">Sammenlign varianter</button><p class="workshop-warning compare-warning" hidden></p></div>
          <section aria-label="Beholdes videre"><h3>Beholdes videre</h3><div class="workshop-keep-list"></div></section>
        </div><div class="workshop-foot">Visningen endrer ikke kildefilene. «Behold dette» legger en føring for neste versjon.<p class="workshop-drafts" hidden></p><p class="workshop-status" role="status"></p><p class="error workshop-error" role="alert" hidden></p></div>
      </section>
      <div class="compare-bar" role="group" aria-label="Sammenligning" hidden><div class="pair-select"><label for="compare-left">Venstre</label><select id="compare-left" aria-label="Venstre variant"></select></div><div class="pair-select"><label for="compare-right">Høyre</label><select id="compare-right" aria-label="Høyre variant"></select></div><div class="compare-tabs" role="group" aria-label="Velg variant"></div><label for="compare-preferred" class="sr">Foretrukket variant</label><select id="compare-preferred" aria-label="Foretrukket variant"></select><button type="button" class="prefer" data-action="workshop-prefer">Foretrekk denne varianten</button><button type="button" data-action="workshop-stop-compare" aria-label="Avslutt sammenligning">×</button></div>
    `;
    root.appendChild(markup);
    const el = (selector) => markup.querySelector(selector);
    const pane = el(".workshop");
    const picker = el("#workshop-target");
    const remark = el("#workshop-remark");
    el(".compare-bar").classList.toggle("has-many", variants.length > 2);
    const toolbarButton = document.createElement("button");
    toolbarButton.type = "button";
    toolbarButton.dataset.action = "workshop-open";
    toolbarButton.textContent = "Juster";
    toolbarButton.setAttribute("aria-expanded", "false");
    toolbarButton.hidden = !descriptor;
    root.querySelector(".toolbar").appendChild(toolbarButton);
    const documentStyle = document.createElement("style");
    documentStyle.nonce = nonce;
    documentStyle.textContent = `[data-vc-workshop-comparing] > [data-vc-variant]::before{content:attr(data-vc-workshop-label);display:block;font:600 13px/1.4 system-ui,sans-serif;color:#5e3b76;background:#f3edf7;border:1px solid #e5d9ef;border-radius:7px;padding:9px 12px;margin:0 0 14px;box-sizing:border-box}`;
    document.head.appendChild(documentStyle);

    function option(label, value) {
      const node = document.createElement("option"); node.value = value; node.textContent = label; return node;
    }
    function status(text) { if (el(".workshop-status").textContent !== text) el(".workshop-status").textContent = text; }
    function error(text) { el(".workshop-error").textContent = text || ""; el(".workshop-error").hidden = !text; }
    function focus(target) { if (target?.isConnected) target.focus(); }
    function targetLabel(target, source = descriptor) {
      const variant = source?.variants.find((entry) => entry.key === target.variant);
      return `${target.label}${variant ? ` · ${variant.label}` : ""}`;
    }
    function updateDrafts() {
      let count = 0;
      for (const option of picker.options) {
        const binding = bindings.get(option.value);
        const draft = hasDraft(binding);
        if (draft) count += 1;
        option.textContent = `${targetLabel(binding.descriptor)}${binding.element ? "" : " · utilgjengelig"}${draft ? " · utkast" : ""}`;
      }
      el(".workshop-drafts").hidden = !count;
      el(".workshop-drafts").textContent = `${count} ${count === 1 ? "del har" : "deler har"} lokale utkast. Velg delen for å fortsette.`;
      toolbarButton.title = count ? `${count} ${count === 1 ? "del med lokalt utkast" : "deler med lokale utkast"}` : "Juster skissen";
      api.onBusyChange();
    }
    function updateLayout() {
      pane.style.bottom = `${Math.max(85, innerHeight - root.querySelector(".toolbar").getBoundingClientRect().top + 12)}px`;
      for (const target of [pane, el(".compare-bar")]) target.style.top = `${api.topInset()}px`;
      applyComparison();
    }
    function close(restore = false) {
      if (locking) return;
      pane.hidden = true;
      el(".compare-bar").hidden = !comparing;
      if (comparing) reserveComparisonSpace();
      toolbarButton.setAttribute("aria-expanded", "false");
      if (restore) focus(toolbarButton);
    }
    function open() {
      if (locking || !api.prepareOpen()) return;
      pane.hidden = false;
      toolbarButton.setAttribute("aria-expanded", "true");
      pane.scrollTop = 0;
      el(".workshop-body").scrollTop = 0;
      updateLayout();
      focus(bindings.size ? picker : el('[data-action="workshop-close"]'));
    }
    function writeValues(binding) {
      if (!binding?.element) return;
      for (const control of binding.descriptor.controls) binding.element.setAttribute(`data-vc-setting-${control.id}`, binding.values[control.id]);
    }
    function bindingAt(element) {
      const target = element?.closest?.("[data-vc-key]");
      return Array.from(bindings.values()).find((binding) => binding.element === target);
    }
    function contextBinding(context) {
      if (!context) return null;
      const binding = bindings.get(`${context.variant || ""}/${context.target}`);
      if (!binding?.element || !context.values || Object.keys(context.values).length !== binding.descriptor.controls.length) return null;
      return binding.descriptor.controls.every((control) => control.options.some((option) => option.value === context.values[control.id])) ? binding : null;
    }
    function refreshPreview(binding) {
      writeValues(binding);
      renderControls();
      status("Lokal visning · legg til innspill for å ta valget videre.");
      updateDrafts();
      api.onPresentationChange();
    }
    function restoreContext(context) {
      const binding = contextBinding(context);
      if (!binding || locking || api.isComposing()) return false;
      beginEdit(binding);
      selectedKey = identifier(binding.descriptor);
      binding.values = { ...context.values };
      if (comparing && context.variant) {
        if (!pair.includes(context.variant)) pair[1] = context.variant;
        activeVariant = context.variant; preferredVariant = context.variant;
        updateCompareSelects(); applyComparison();
      }
      refreshPreview(binding);
      announce("Viser situasjonen fra innspillet. Andre deler og merknader er beholdt. Visningen er lokal.");
      return true;
    }
    function controlValue(control, input) {
      return control.type === "select" ? input.value : control.type === "toggle" ? control.options[input.checked ? 1 : 0].value : control.options[Number(input.value)].value;
    }
    function refreshButtons() {
      const binding = selected();
      el('[data-action="workshop-add"]').disabled = locking || !binding?.element || !binding.descriptor.controls.length;
      el('[data-action="workshop-keep"]').disabled = locking || !binding?.element || Boolean(binding.conflict);
      el('[data-action="workshop-replace"]').disabled = locking || !binding?.element;
      el('[data-action="workshop-discard-conflict"]').disabled = locking;
      el('[data-action="workshop-reset"]').disabled = locking || !binding?.element || !binding.descriptor.controls.length;
      el('[data-action="workshop-compare"]').disabled = locking || !comparisonAvailable;
    }
    function renderControls() {
      const binding = selected();
      const container = el(".workshop-controls");
      container.replaceChildren();
      el(".workshop-editor").hidden = !bindings.size;
      picker.value = selectedKey;
      remark.value = binding?.remark || "";
      remark.disabled = !binding?.element || locking;
      el(".keep-conflict").hidden = !binding?.conflict;
      if (binding?.conflict) el(".keep-conflict-summary").textContent = binding.conflict.text;
      const unavailable = Boolean(binding && !binding.element);
      el(".target-warning").hidden = !unavailable;
      el(".target-warning").textContent = "Denne delen er utilgjengelig: markeringen mangler eller finnes flere steder i skissen.";
      if (binding) for (const control of binding.descriptor.controls) {
        const box = document.createElement("div"); box.className = "workshop-control";
        const label = document.createElement("label"); label.htmlFor = `workshop-control-${control.id}`; label.textContent = control.label;
        const input = document.createElement(control.type === "select" ? "select" : "input");
        input.id = label.htmlFor;
        input.setAttribute("aria-label", control.label);
        input.dataset.control = control.id;
        input.disabled = unavailable || locking;
        const output = document.createElement("output"); output.htmlFor = input.id;
        const updateOutput = () => {
          output.textContent = control.options.find((entry) => entry.value === binding.values[control.id])?.label || "";
          if (control.type === "range") input.setAttribute("aria-valuetext", output.textContent);
        };
        if (control.type === "select") { control.options.forEach((entry) => input.appendChild(option(entry.label, entry.value))); input.value = binding.values[control.id]; }
        else if (control.type === "toggle") { input.type = "checkbox"; input.checked = binding.values[control.id] === control.options[1].value; }
        else { input.type = "range"; input.min = "0"; input.max = String(control.options.length - 1); input.step = "1"; input.value = String(control.options.findIndex((entry) => entry.value === binding.values[control.id])); }
        input.addEventListener(control.type === "range" ? "input" : "change", () => {
          if (locking) return;
          beginEdit(binding);
          binding.values[control.id] = controlValue(control, input);
          writeValues(binding); updateOutput(); status("Lokal visning · legg til innspill for å ta valget videre."); updateDrafts();
        });
        updateOutput(); box.append(label, input, output); container.appendChild(box);
      }
      if (binding && !binding.descriptor.controls.length) {
        const text = document.createElement("p"); text.className = "workshop-empty"; text.textContent = "Denne delen har ingen justeringer. Du kan be om at den beholdes videre."; container.appendChild(text);
      }
      refreshButtons();
    }
    function captureStyles(element, properties) {
      if (savedStyles.has(element)) return;
      savedStyles.set(element, { hidden: element.hidden, properties: properties.map((name) => ({ name, value: element.style.getPropertyValue(name), priority: element.style.getPropertyPriority(name) })) });
    }
    function restoreStyles(element) {
      const saved = savedStyles.get(element); if (!saved) return;
      element.hidden = saved.hidden;
      for (const item of saved.properties) { if (item.value) element.style.setProperty(item.name, item.value, item.priority); else element.style.removeProperty(item.name); }
    }
    function updateCompareSelects() {
      const focusedVariant = root.activeElement?.dataset.variant;
      el("#compare-left").value = pair[0] || ""; el("#compare-right").value = pair[1] || "";
      el("#compare-preferred").value = preferredVariant;
      el(".compare-tabs").replaceChildren();
      for (const key of pair) {
        const button = document.createElement("button"); button.type = "button"; button.textContent = variantBindings.get(key)?.label || key; button.dataset.variant = key; button.setAttribute("aria-pressed", String(activeVariant === key));
        button.addEventListener("click", () => { if (locking) return; activeVariant = key; preferredVariant = key; applyComparison(); updateCompareSelects(); });
        el(".compare-tabs").appendChild(button);
      }
      if (focusedVariant) focus(Array.from(el(".compare-tabs").children).find((button) => button.dataset.variant === focusedVariant));
    }
    function reserveComparisonSpace() {
      if (!comparing || !frameContent) return;
      captureStyles(frameContent, ["margin-top"]);
      restoreStyles(frameContent);
      const bar = el(".compare-bar");
      const wasHidden = bar.hidden;
      bar.hidden = false;
      const bottom = bar.getBoundingClientRect().bottom;
      bar.hidden = wasHidden;
      const margin = parseFloat(getComputedStyle(frameContent).marginTop) || 0;
      const originalTop = frameContent.getBoundingClientRect().top + scrollY;
      const extra = Math.max(0, bottom + 12 - originalTop);
      frameContent.style.setProperty("margin-top", `${margin + extra}px`, "important");
    }
    function applyComparison() {
      el(".compare-bar").hidden = !comparing || !pane.hidden;
      if (!comparisonAvailable) return;
      const properties = ["display", "grid-template-columns", "gap", "align-items"];
      if (!comparing) {
        for (const [element] of savedStyles) restoreStyles(element);
        comparisonParent.removeAttribute("data-vc-workshop-comparing");
        for (const binding of variantBindings.values()) binding.element.removeAttribute("data-vc-workshop-label");
        api.onBusyChange();
        api.onPresentationChange();
        return;
      }
      captureStyles(comparisonParent, properties);
      comparisonParent.setAttribute("data-vc-workshop-comparing", "");
      comparisonParent.style.setProperty("display", "grid", "important");
      comparisonParent.style.setProperty("grid-template-columns", innerWidth < 760 ? "minmax(0, 1fr)" : "minmax(0, 1fr) minmax(0, 1fr)", "important");
      comparisonParent.style.setProperty("gap", "24px", "important");
      comparisonParent.style.setProperty("align-items", "start", "important");
      for (const binding of variantBindings.values()) {
        const element = binding.element;
        captureStyles(element, ["display", "min-width", "max-width", "width", "order"]);
        restoreStyles(element);
        const visible = pair.includes(binding.key) && (innerWidth >= 760 || activeVariant === binding.key);
        element.hidden = !visible;
        element.setAttribute("data-vc-workshop-label", binding.label);
        if (!visible) element.style.setProperty("display", "none", "important");
        else { if (getComputedStyle(element).display === "none") element.style.setProperty("display", "block", "important"); element.style.setProperty("min-width", "0", "important"); element.style.setProperty("max-width", "none", "important"); element.style.setProperty("width", "100%", "important"); element.style.setProperty("order", String(pair.indexOf(binding.key)), "important"); }
      }
      el(".compare-tabs").hidden = innerWidth >= 760;
      reserveComparisonSpace();
      api.onBusyChange();
      api.onPresentationChange();
    }
    function followup(decision) {
      const binding = bindings.get(`${decision.variant || ""}/${decision.target}`);
      return !binding?.element || Object.entries(decision.values || {}).some(([id, value]) => binding.descriptor.controls.find((control) => control.id === id)?.initial !== value);
    }
    function endComparison() {
      if (!comparing || locking) return;
      comparing = false;
      el('[data-action="workshop-compare"]').setAttribute("aria-pressed", "false");
      applyComparison();
    }
    function decisionCard(decision) {
      const binding = bindings.get(`${decision.variant || ""}/${decision.target}`);
      const original = sourceDesign(decision)?.targets.find((target) => target.key === decision.target && target.variant === decision.variant);
      const target = original || binding?.descriptor;
      const needsWork = decision.state === "active" && followup(decision);
      const card = document.createElement("article"); card.className = `workshop-decision${needsWork ? " followup" : ""}${decision.state === "released" ? " released" : ""}`; card.dataset.decision = decision.id; card.tabIndex = -1;
      const title = document.createElement("h4"); title.textContent = target ? targetLabel(target, original ? sourceDesign(decision) : descriptor) : decision.target; card.appendChild(title);
      const state = document.createElement("span"); state.className = "decision-state"; state.textContent = decision.state === "released" ? "Frigitt" : needsWork ? decision.screen === screen ? "Venter på neste versjon" : "Må følges opp" : "Beholdes videre"; card.appendChild(state);
      if (decision.submission === 0) { const badge = document.createElement("span"); badge.className = "badge"; badge.textContent = "Ikke sendt"; card.appendChild(badge); }
      if (decision.screen !== screen) { const old = document.createElement("p"); old.className = "muted"; old.textContent = "Fra en tidligere versjon"; card.appendChild(old); }
      if (decision.text) { const text = document.createElement("p"); text.textContent = decision.text; card.appendChild(text); }
      const entries = Object.entries(decision.values || {});
      if (entries.length) {
        const list = document.createElement("ul");
        for (const [id, value] of entries) { const control = target?.controls.find((entry) => entry.id === id) || original?.controls.find((entry) => entry.id === id); const row = document.createElement("li"); row.textContent = `${control?.label || id}: ${control?.options.find((entry) => entry.value === value)?.label || value}`; list.appendChild(row); }
        card.appendChild(list);
      }
      if (decision.state === "active") {
        const release = document.createElement("button"); release.type = "button"; release.textContent = "Frigi"; release.dataset.action = "workshop-release"; release.dataset.decision = decision.id; release.disabled = locking; card.appendChild(release);
      }
      return card;
    }
    function sourceDesign(item) { return snapshot.screens?.find((entry) => entry.screen === item.screen)?.design; }
    function renderDecisions() {
      const active = root.activeElement;
      const focusedId = active?.closest("[data-decision]")?.dataset.decision;
      const list = el(".workshop-keep-list");
      const restore = Boolean(active && list.contains(active));
      list.replaceChildren();
      const decisions = (snapshot.decisions || []).filter((entry) => entry.state === "active" || entry.submission === 0);
      for (const decision of decisions) list.appendChild(decisionCard(decision));
      if (!decisions.length) { const text = document.createElement("p"); text.className = "workshop-empty"; text.textContent = "Ingen føringer ennå. Velg en del og trykk «Behold dette» når noe bør tas med videre."; list.appendChild(text); }
      if (restore) focus(Array.from(list.children).find((card) => card.dataset.decision === focusedId)?.querySelector("button") || list.querySelector("[data-decision]") || toolbarButton);
      toolbarButton.hidden = !descriptor && !decisions.length;
    }
    function lock(value) {
      locking = value;
      pane.setAttribute("aria-busy", String(value));
      markup.querySelectorAll("button,input,select,textarea").forEach((target) => { target.disabled = value; });
      toolbarButton.disabled = value;
      if (!value) { renderControls(); renderDecisions(); api.refreshFeedback(); }
      api.onBusyChange();
    }
    async function save(action, decisionId, replace = false) {
      if (locking) return;
      const binding = selected();
      const text = action === "workshop-add" || action === "workshop-keep" ? binding?.remark.trim() || "" : "";
      if (new TextEncoder().encode(text).length > 2000) { error("Merknaden er for lang. Kort den ned før du lagrer."); focus(remark); return; }
      const retryKey = `${action}/${decisionId || (action === "workshop-prefer" ? preferredVariant : selectedKey)}`;
      if (!saveRetries.has(retryKey)) saveRetries.set(retryKey, {});
      const retry = saveRetries.get(retryKey);
      let operation, payload;
      if (action === "workshop-release") {
        if (retry.expectedRevision === undefined) retry.expectedRevision = snapshot.decisions?.find((item) => item.id === decisionId)?.revision || 0;
        operation = "decision-release"; payload = { id: decisionId, expectedRevision: retry.expectedRevision };
      }
      else if (action === "workshop-prefer") {
        const variant = variantBindings.get(preferredVariant);
        if (!variant?.element) return;
        operation = "comment-create"; payload = { screen, kind: "variant", anchor: anchorFor(variant.element), text: text || "Foretrekker denne varianten.", variant: variant.key };
      } else {
        if (!binding?.element) return;
        const values = { ...binding.values };
        if (action === "workshop-keep") {
          if (binding.conflict && !replace) return;
          beginEdit(binding);
          operation = "decision-keep"; payload = { screen, variant: binding.descriptor.variant || "", target: binding.descriptor.key, values, text: text || "Behold denne delen videre.", expectedRevision: replace ? binding.conflict.revision : binding.expectedRevision };
        }
        else { if (!binding.descriptor.controls.length) return; operation = "comment-create"; payload = { screen, kind: "adjustment", anchor: anchorFor(binding.element), text: text || "Ta med disse justeringene.", adjustment: { variant: binding.descriptor.variant || "", target: binding.descriptor.key, values } }; }
      }
      error(""); api.showFeedbackError(""); lock(true);
      try {
        await request(operation, payload, retry);
        saveRetries.delete(retryKey);
        if (binding && (action === "workshop-add" || action === "workshop-keep")) binding.accepted = signature(binding.values);
        if (binding && (action === "workshop-add" || action === "workshop-keep")) { binding.remark = ""; remark.value = ""; binding.expectedRevision = undefined; binding.conflict = null; }
        updateDrafts();
        status("Lagret i innspill. Send samlet når du er klar.");
        announce("Valget er lagt til innspill.");
        locking = false; close(); api.openFeedback();
      } catch (failure) {
        if (action === "workshop-keep" && failure.conflict && binding) {
          const current = currentDecision(binding);
          const source = snapshot.screens?.find((entry) => entry.screen === current?.screen)?.design;
          const controls = source?.targets.find((entry) => entry.key === current.target && entry.variant === current.variant)?.controls || [];
          const values = current ? Object.entries(current.values).map(([id, value]) => {
            const control = controls.find((entry) => entry.id === id);
            return `${control?.label || id}: ${control?.options.find((option) => option.value === value)?.label || value}`;
          }).join(" · ") : "";
          binding.conflict = { revision: current?.revision || 0, text: current ? `Lagret valg: ${values}${values ? ". " : ""}${current.text}` : "Det tidligere valget er frigitt. Ingen aktiv føring er lagret for denne delen." };
          error("Se gjennom det lagrede valget før du eventuelt erstatter det.");
          announce("Delen er endret et annet sted. Ditt valg og merknaden er beholdt.");
        } else {
          if (failure.conflict) delete retry.expectedRevision;
          error(failure.message); if (pane.hidden) api.showFeedbackError(failure.message);
        }
      }
      finally { lock(false); if (action === "workshop-keep" && binding?.conflict) focus(el(".keep-conflict")); }
    }

    for (const [key, binding] of bindings) {
      picker.appendChild(option(targetLabel(binding.descriptor), key));
      writeValues(binding);
    }
    for (const variant of variants) for (const selector of ["#compare-left", "#compare-right", "#compare-preferred"]) el(selector).appendChild(option(variant.label, variant.key));
    picker.addEventListener("change", () => {
      if (locking) return;
      selectedKey = picker.value; error(""); status(""); renderControls();
      const variant = selected()?.descriptor.variant;
      if (comparing && variant) { if (!pair.includes(variant)) pair[1] = variant; activeVariant = variant; preferredVariant = variant; updateCompareSelects(); applyComparison(); }
    });
    remark.addEventListener("input", () => { const binding = selected(); if (binding) { beginEdit(binding); binding.remark = remark.value; } updateDrafts(); });
    for (const [selector, index] of [["#compare-left", 0], ["#compare-right", 1]]) el(selector).addEventListener("change", (event) => {
      const previous = pair[index]; pair[index] = event.target.value;
      if (pair[0] === pair[1]) pair[1 - index] = previous;
      if (!pair.includes(activeVariant)) activeVariant = pair[0];
      if (!pair.includes(preferredVariant)) preferredVariant = pair[index];
      updateCompareSelects(); applyComparison();
    });
    el("#compare-preferred").addEventListener("change", (event) => {
      preferredVariant = event.target.value;
      if (!pair.includes(preferredVariant)) pair[1] = preferredVariant;
      activeVariant = preferredVariant;
      updateCompareSelects(); applyComparison();
    });
    root.addEventListener("click", (event) => {
      const button = event.target.closest("button"); if (!button || button.disabled) return;
      const action = button.dataset.action;
      if (action === "workshop-open") { if (pane.hidden) open(); else close(true); }
      else if (action === "workshop-close") close(true);
      else if (action === "workshop-reset" && !locking) { const binding = selected(); if (binding) { binding.values = initialValues(binding.descriptor); binding.accepted = signature(binding.values); writeValues(binding); renderControls(); status("Visningen er tilbakestilt. Merknaden og lagrede innspill er beholdt."); updateDrafts(); } }
      else if (action === "workshop-compare" && comparisonAvailable && !locking) { comparing = !comparing; button.setAttribute("aria-pressed", String(comparing)); updateCompareSelects(); applyComparison(); if (comparing) { close(); focus(innerWidth < 760 ? el(".compare-tabs button") : el("#compare-left")); } }
      else if (action === "workshop-stop-compare" && !locking) { endComparison(); focus(toolbarButton); }
      else if (["workshop-add", "workshop-keep", "workshop-prefer", "workshop-release"].includes(action)) void save(action, button.dataset.decision);
      else if (action === "workshop-replace" && selected()?.conflict) void save("workshop-keep", undefined, true);
      else if (action === "workshop-discard-conflict" && !locking) {
        const binding = selected();
        if (binding?.conflict) {
          binding.values = initialValues(binding.descriptor); binding.accepted = signature(binding.values);
          binding.remark = ""; binding.conflict = null; binding.expectedRevision = undefined;
          saveRetries.delete(`workshop-keep/${selectedKey}`);
          writeValues(binding); renderControls(); updateDrafts(); error("");
          status("Det lagrede valget er beholdt. Ditt lokale utkast er forkastet."); focus(picker);
        }
      }
    });
    markup.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault(); event.stopPropagation();
        if (locking) return;
        if (event.target.closest(".compare-bar")) { endComparison(); focus(toolbarButton); }
        else close(true);
      }
    });
    el(".workshop-comparison").hidden = variants.length < 2;
    el(".compare-warning").hidden = comparisonAvailable || variants.length < 2;
    el(".compare-warning").textContent = "Sammenligning er utilgjengelig: variantene må finnes én gang hver, i samme beholder.";
    renderControls(); updateCompareSelects(); renderDecisions(); updateDrafts();
    window.addEventListener("resize", updateLayout);
    if (typeof ResizeObserver === "function") {
      const observer = new ResizeObserver(updateLayout);
      observer.observe(root.querySelector(".toolbar"));
      observer.observe(el(".compare-bar"));
      const header = document.body.querySelector(":scope > .vc-header");
      if (header) observer.observe(header);
    }
    return {
      close,
      isSaving: () => locking,
      isBusy: () => locking || pending(),
      hasRemarks: () => Array.from(bindings.values()).some((binding) => Boolean(binding.remark.trim() || binding.conflict)),
      isComparing: () => comparing,
      endComparison,
      contextFor(target) {
        const binding = bindingAt(target);
        return binding?.descriptor.controls.length ? { variant: binding.descriptor.variant || "", target: binding.descriptor.key, values: { ...binding.values } } : undefined;
      },
      canRestoreContext: (context) => Boolean(contextBinding(context)),
      restoreContext,
      describeContext(item) {
        const source = sourceDesign(item);
        const target = source?.targets.find((entry) => entry.key === item.context.target && entry.variant === item.context.variant);
        return [target ? targetLabel(target, source) : item.context.target, ...Object.entries(item.context.values).map(([id, value]) => {
          const control = target?.controls.find((entry) => entry.id === id);
          return `${control?.label || id}: ${control?.options.find((entry) => entry.value === value)?.label || value}`;
        })].join("\n");
      },
      render(value) { snapshot = value; for (const binding of bindings.values()) if (!hasDraft(binding) && !locking && !saveRetries.has(`workshop-keep/${identifier(binding.descriptor)}`)) binding.expectedRevision = undefined; if (value.revision !== lastRevision) { lastRevision = value.revision; renderDecisions(); } },
      describeComment(item) {
        const original = sourceDesign(item);
        if (item.variant) return original?.variants.find((variant) => variant.key === item.variant)?.label || variantBindings.get(item.variant)?.label || item.variant;
        const change = item.adjustment;
        const binding = bindings.get(`${change.variant || ""}/${change.target}`);
        const originalTarget = original?.targets.find((target) => target.key === change.target && target.variant === change.variant);
        const target = originalTarget || binding?.descriptor;
        return [target ? targetLabel(target, originalTarget ? original : descriptor) : change.target, ...Object.entries(change.values).map(([id, value]) => {
          const control = target?.controls.find((entry) => entry.id === id) || originalTarget?.controls.find((entry) => entry.id === id);
          return `${control?.label || id}: ${control?.options.find((entry) => entry.value === value)?.label || value}`;
        })].join("\n");
      },
      appendFeedback(container) { const decisions = snapshot.decisions || []; decisions.forEach((decision) => container.appendChild(decisionCard(decision))); return decisions.length; },
      onPrototypeClick(event) {
        if (pane.hidden || api.isComposing()) return false;
        const target = event.target.closest?.("[data-vc-key]");
        const entry = Array.from(bindings).find(([, binding]) => binding.element === target);
        if (!entry) return false;
        if (!locking) { selectedKey = entry[0]; error(""); status(""); renderControls(); focus(picker); }
        return true;
      },
      onPrototypeAction(event) {
        const button = event.target.closest?.("button[data-vc-control]");
        if (!button) return false;
        if (locking || !api.canTry() || !pane.hidden || button.type !== "button" || button.disabled || button.closest('[inert],[aria-disabled="true"]')) return true;
        const binding = bindingAt(button);
        const control = binding?.descriptor.controls.find((entry) => entry.id === button.getAttribute("data-vc-control"));
        const option = control?.options.find((entry) => entry.value === button.getAttribute("data-vc-value"));
        if (!binding || !option) { announce("Denne handlingen mangler et gyldig valg i skissen."); return true; }
        selectedKey = identifier(binding.descriptor);
        beginEdit(binding);
        binding.values[control.id] = option.value;
        refreshPreview(binding);
        if (!button.getClientRects().length || getComputedStyle(button).visibility === "hidden") {
          if (binding.element.getClientRects().length && getComputedStyle(binding.element).visibility !== "hidden") {
            window.scrollTo({ top: Math.max(0, scrollY + binding.element.getBoundingClientRect().top - api.topInset()), behavior: "auto" });
            api.focusPrototype(binding.element);
          }
          else focus(toolbarButton);
        }
        announce(`${control.label}: ${option.label}. Lokal visning, ikke sendt.`);
        return true;
      },
    };
  };
})();
