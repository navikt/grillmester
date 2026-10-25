// Loaded in <head>: keep this script's nonce now and start once the sketch is parsed.
((scriptNonce, start) => (document.readyState === "loading"
  ? document.addEventListener("DOMContentLoaded", () => start(scriptNonce), { once: true })
  : start(scriptNonce)))(document.currentScript?.nonce || "", (scriptNonce) => {
  "use strict";

  const channel = "grillmester-visual-companion";
  const screen = window.__grillmesterVisualCompanionScreen;
  // Set when a stored version is shown read-only instead of the current sketch.
  const view = window.__grillmesterVisualCompanionView || null;
  const nonce = scriptNonce;
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
    if (view) return;
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
    .toolbar.viewing{flex-wrap:wrap;justify-content:center;width:max-content}.view-banner{display:contents}.view-text{flex:1 1 100%;text-align:center;font-weight:600;padding:4px 8px;color:#23262a}
    .endre-bar,.vis-bar{pointer-events:auto;position:fixed;left:50%;transform:translateX(-50%);bottom:76px;width:max-content;max-width:calc(100vw - 24px);display:flex;flex-direction:column;gap:6px;padding:6px;background:#fff;border:1px solid #e1dce8;border-radius:14px;box-shadow:0 8px 36px #25163824}.row.with-endre-tabs>h2,.row.with-vis-tabs>h2{display:none}.row.with-endre-tabs .endre-tabs,.row.with-vis-tabs .vis-tabs{flex:1;min-width:0}.row.with-endre-tabs .endre-tabs button,.row.with-vis-tabs .vis-tabs button{padding:8px 9px}.endre-tabs,.endre-ask,.vis-tabs{display:flex;flex-wrap:wrap;align-items:center;gap:4px}.endre-tabs button[aria-pressed=true],.endre-tabs button[aria-expanded=true],.vis-tabs button[aria-pressed=true],.vis-tabs button[aria-expanded=true]{background:#f0e8f7;color:#6e3197}.endre-ask select{flex:1 1 140px;min-width:0;min-height:34px;font:inherit;font-size:13px;border:1px solid #d9d2e2;border-radius:9px;padding:0 8px;background:#fff}
    .toolbar{pointer-events:auto;position:fixed;bottom:max(16px,env(safe-area-inset-bottom));left:50%;transform:translateX(-50%);display:flex;align-items:center;gap:4px;padding:7px;background:#fff;border:1px solid #e1dce8;border-radius:14px;box-shadow:0 8px 36px #25163824;max-width:calc(100vw - 24px)}
    .toolbar button{white-space:nowrap}.toolbar button[aria-pressed=true],.tools button[aria-pressed=true]{color:#7133a2;background:#f1e8f7}.count{display:inline-flex;align-items:center;justify-content:center;min-width:20px;height:20px;padding:0 5px;border-radius:6px;background:#ece9f0;font-size:11px;margin-left:5px}.tools{display:flex;gap:2px}.tools button{font-size:12px;padding:8px}.toolbar .update{background:#eaf1ff;color:#254c95;font-size:12px}.draft-button{color:#7133a2}
    .hint{position:fixed;top:64px;left:50%;transform:translateX(-50%);max-width:calc(100vw - 24px);padding:9px 14px;border:1px solid #e8d7f1;border-radius:10px;box-shadow:0 3px 15px #25163812;background:#fcf8ff;color:#68368a;font-size:12px;text-align:center}
    .panel{pointer-events:auto;position:fixed;right:16px;top:64px;bottom:86px;width:min(366px,calc(100vw - 32px));display:flex;flex-direction:column;background:#fff;border:1px solid #e1dce8;border-radius:16px;box-shadow:0 12px 48px #25163826;overflow:hidden}
    .panel-head{padding:18px 18px 12px;border-bottom:1px solid #ece8f0}.panel h2,.composer h2{margin:0;font-size:17px;font-weight:700;letter-spacing:-.3px}.close{min-width:34px;min-height:34px;padding:5px;font-size:22px;color:#74707d;font-weight:400}.panel-intro{margin:7px 0 13px;font-size:12px;color:#797381}.filters{display:flex;gap:4px}.list .filters{margin-bottom:12px}.basket-tabs{display:flex;gap:4px;margin-top:10px}.basket-tabs button{padding:7px 12px;min-height:34px;font-size:13px}.basket-tabs button[aria-selected=true]{background:#f0e8f7;color:#6e3197}.filters button{padding:7px 12px;min-height:32px;font-size:12px}.filters button[aria-pressed=true]{background:#f0e8f7;color:#6e3197}.list{overflow-y:auto;overscroll-behavior:contain;flex:1;min-height:0;padding:14px}.empty{padding:28px 16px;text-align:center;color:#787180}.empty svg{width:32px;height:32px;color:#a784c0;margin-bottom:9px}.empty strong{display:block;font-size:14px;color:#393040;margin-bottom:6px}.empty p{margin:0;font-size:12px;line-height:1.6}
    .comment{border:1px solid #e7e1ec;border-radius:12px;padding:13px;margin-bottom:10px;background:#fff;overflow-wrap:anywhere}.comment:focus{outline:2px solid #b264cc;outline-offset:2px}.comment:last-child{margin-bottom:0}.comment.fixed{background:#fbfdfb}.comment .row{flex-wrap:wrap}.comment .number{width:23px;height:23px;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;background:#aa267e;color:white;font-size:11px;font-weight:700;flex-shrink:0}.comment.fixed .number{background:#34845a}.badge{font-size:10px;font-weight:600;color:#78607f;background:#f3edf6;padding:3px 6px;border-radius:5px}.badge.old{background:#f0eff1;color:#6e6b73}.comment p{white-space:pre-wrap;margin:11px 0;font-size:13px;line-height:1.55}.comment .reply{border-left:2px solid #d1badf;padding-left:10px;font-size:12px;color:#65556f}.reply strong{display:block;font-size:10px;letter-spacing:.03em;text-transform:uppercase;margin-bottom:4px}.comment-actions{display:flex;flex-wrap:wrap;gap:2px;margin:8px -5px -5px}.comment-actions button{font-size:11px;padding:7px 6px;min-height:30px}.danger{color:#9c3c53}.proposal{white-space:pre-wrap;padding:9px;background:#f5f0fa;border-radius:7px;font-size:12px;margin-top:7px}.proposal-label{font-size:10px;display:block;color:#79598c;margin-bottom:5px;font-weight:700;text-transform:uppercase;letter-spacing:.04em}
    .panel-foot{padding:13px 16px;border-top:1px solid #ece8f0;background:#fcfbfd}.panel-foot .primary{width:100%;margin-top:10px}.connection{display:flex;align-items:center;gap:6px;font-size:11px;color:#787180}.connection::before{content:"";width:6px;height:6px;border-radius:50%;background:#aaa3af}.connection.live::before{background:#3b9166}.foot-status{font-size:11px;color:#685c74;margin:8px 0 0;line-height:1.4}.error{color:#ad2849;font-size:12px;line-height:1.5;margin:8px 0 0}.composer{pointer-events:auto;position:fixed;width:min(340px,calc(100vw - 24px));max-height:calc(100dvh - 105px);overflow-y:auto;overscroll-behavior:contain;padding:18px;background:#fff;border:1px solid #d8c2e5;border-radius:15px;box-shadow:0 12px 48px #32143f30}.composer .anchor-label{font-size:11px;color:#706578;margin-top:3px}.composer label{display:block;font-size:12px;font-weight:600;margin:15px 0 7px}.composer textarea{display:block;width:100%;min-height:88px;max-height:200px;resize:vertical;padding:10px;border:1px solid #8b7a9a;border-radius:8px;background:#fff;color:#282230;line-height:1.5;font-size:13px}.composer textarea::placeholder{color:#706578}.composer .compose-actions{display:flex;justify-content:flex-end;gap:6px;margin-top:15px}.composer .proposal-toggle{font-size:12px;padding:7px 0;color:#7133a2;text-align:left;margin-top:8px}.composer .proposal-toggle:hover{background:transparent;text-decoration:underline}.composer .preview-button{font-size:11px;background:#f3edf7;margin-top:8px}.composer .help{font-size:10px;color:#706578;margin-top:9px}.composer .save{min-width:82px}.outline{position:fixed;pointer-events:none;border:2px solid #b52e8c;background:#b52e8c0d;border-radius:4px}.pins{position:fixed;inset:0;pointer-events:none}.pin{position:absolute;pointer-events:auto;min-height:26px;width:26px;height:26px;padding:0;border-radius:50%;background:#aa267e;color:#fff;border:2px solid #fff;box-shadow:0 2px 8px #421b393d;font-size:11px;transform:translate(-50%,-50%)}.pin:hover,.pin:focus{background:#7c145d}.pin.fixed{background:#34845a}.pin.fixed:hover{background:#1e6740}.preview-bar{pointer-events:auto;position:fixed;top:64px;left:50%;transform:translateX(-50%);background:#fff7e7;border:1px solid #e8d4a8;border-radius:11px;padding:8px 12px;box-shadow:0 4px 20px #39250018;font-size:12px;max-width:calc(100vw - 24px);display:flex;align-items:center;gap:12px}.preview-bar button{font-size:12px;background:#f4e4c3;white-space:nowrap}
    @media(max-width:600px){.toolbar{bottom:max(10px,env(safe-area-inset-bottom));gap:2px;padding:5px;flex-wrap:wrap;justify-content:center;width:max-content;max-width:calc(100vw - 16px)}.toolbar button{font-size:12px;padding:8px}.toolbar .tools{border-left:1px solid #e7e3eb;padding-left:3px}.toolbar .divider{display:none}.panel{top:64px;right:10px;bottom:106px;width:calc(100vw - 20px)}.hint{font-size:11px}.composer{max-height:calc(100dvh - 120px)}.toolbar svg{width:15px;height:15px}}
    @media(max-height:540px){.panel{overflow-y:auto;overscroll-behavior:contain}.panel-head,.panel-foot,.list{flex-shrink:0}.list{flex:none;overflow:visible}.panel-foot{position:sticky;bottom:0;z-index:1}}
    .preview-bar{width:max-content;flex-wrap:wrap;justify-content:center}.preview-bar span{flex:1 1 100%;text-align:center}.preview-bar:has([data-action="edit-preview"][hidden]) span{flex:initial}
    @media(min-width:600px){.preview-bar span{flex:initial}}
    .panel,.list,.composer{scroll-padding:8px}
    .compose-error,.workshop-error{margin-bottom:8px}
    .compose-scope{font-size:12px;line-height:1.45;color:#5b426b;background:#f6f1fa;border-radius:8px;padding:8px 10px;margin:10px 0 0}
    .canvas-rounds{margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid #e7e1ec}.canvas-rounds h3{font-size:13px;margin:0 0 10px}.canvas-round{border:1px solid #e7e1ec;border-radius:9px;padding:10px;margin-bottom:8px;overflow-wrap:anywhere}.canvas-round .row{flex-wrap:wrap;font-size:12px}.canvas-round p{font-size:12px;white-space:pre-wrap;margin:8px 0 0}.canvas-round summary,.canvas-history>summary{font-size:12px;cursor:pointer;padding:7px 0;min-height:32px}.canvas-round summary:focus-visible,.canvas-history>summary:focus-visible{outline:3px solid #6852ce;outline-offset:2px}.canvas-round[data-status=unknown]{border-color:#c99a45;background:#fffaf0}.canvas-round[data-status=answered] .badge{background:#e9f4ed;color:#286640}.canvas-close-hint{font-size:11px;color:#685c74;margin:10px 0 0;line-height:1.5}
    .workspace-panel{pointer-events:auto;position:fixed;right:16px;top:64px;bottom:86px;width:min(366px,calc(100vw - 32px));display:flex;flex-direction:column;background:#fff;border:1px solid #e1dce8;border-radius:16px;box-shadow:0 12px 48px #25163826;overflow:hidden}.workspace-head{padding:14px 16px;border-bottom:1px solid #ece8f0;flex-shrink:0}.workspace-head h2{font-size:17px;margin:0}.workspace-body{padding:16px;overflow-y:auto;overscroll-behavior:contain;min-height:0;scroll-padding:12px}.workspace-body h3{font-size:14px;margin:0 0 8px;overflow-wrap:anywhere}.workspace-body p{font-size:12px;line-height:1.5;margin:8px 0;overflow-wrap:anywhere}.workspace-path{display:block;overflow-wrap:anywhere;font-size:11px;color:#685c74}.workspace-revision,.workspace-confirm{border:1px solid #e7e1ec;border-radius:9px;padding:12px;margin:10px 0}.workspace-revision .row{flex-wrap:wrap}.workspace-revision button{font-size:12px}.workspace-confirm{background:#fffaf0;border-color:#c99a45}.workspace-confirm:focus{outline:2px solid #6852ce;outline-offset:2px}.workspace-actions{display:flex;flex-wrap:wrap;gap:5px}.workspace-status{color:#5b426b}.workspace-dirty{color:#80591d}.workspace-history-tools{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:18px}.workspace-history-tools h3{margin:0}.workspace-history-tools button{font-size:12px}.workspace-error{margin:8px 0}.workspace-previous{color:#78607f}
    @media(max-width:600px){.workspace-panel{right:10px;width:calc(100vw - 20px)}}
    .workspace-storage-details{font-size:12px;margin:8px 0}.workspace-storage-details summary{cursor:pointer;min-height:32px;padding:7px 0}.workspace-storage-details summary:focus-visible{outline:3px solid #6852ce;outline-offset:2px}
    @media(prefers-reduced-motion:no-preference){button{transition:background .12s ease}}
  `;
  root.appendChild(style);
  const ui = document.createElement("div");
  ui.innerHTML = `
    <div class="outline" hidden></div><div class="pins"></div>
    <div class="hint" hidden></div>
    <div class="preview-bar" hidden><span>Lokal tekstvisning</span><button type="button" data-action="edit-preview" hidden>Fortsett å redigere</button><button type="button" data-action="undo">Tilbakestill</button></div>
    <section class="panel" aria-label="Innspill til prototypen" hidden>
      <div class="panel-head"><div class="row between"><h2>Innspill <span class="count total">0</span></h2><button type="button" class="close" data-action="close-panel" aria-label="Lukk innspill">×</button></div>
        <p class="panel-intro">Pek på det du vil forbedre. Send samlet når du er klar. Innspillene lagres bare i denne økten.</p>
        <div class="basket-tabs" role="tablist" aria-label="Innspill"><button type="button" role="tab" id="basket-ready" data-tab="ready" aria-selected="true" aria-controls="basket-list">Klar til sending <span class="count ready-count">0</span></button><button type="button" role="tab" id="basket-sent" data-tab="sent" aria-selected="false" aria-controls="basket-list" tabindex="-1">Sendt <span class="count sent-count">0</span></button></div>
      </div><div class="list" id="basket-list" role="tabpanel" aria-labelledby="basket-ready"><div class="filters" role="group" aria-label="Filtrer sendte innspill" hidden><button type="button" data-filter="all" aria-pressed="true">Alle</button><button type="button" data-filter="open" aria-pressed="false">Åpne</button><button type="button" data-filter="fixed" aria-pressed="false">Ordnet</button></div><section class="canvas-rounds" aria-label="Sendte runder" hidden><h3>Sendte runder</h3><div class="canvas-recent"></div><details class="canvas-history" hidden><summary></summary><div class="canvas-older"></div></details></section><div class="comment-list"></div></div>
      <div class="panel-foot"><div class="row between"><span class="pending muted">Ingen nye innspill</span><span class="connection">Lagres lokalt</span></div><button type="button" class="primary send" data-action="send" disabled>Send innspill</button><p class="foot-status" role="status"></p><p class="error panel-error" role="alert" hidden></p></div>
    </section>
    <section class="workspace-panel" aria-label="Versjoner og lagring" hidden><div class="workspace-head"><div class="row between"><h2>Versjoner</h2><button type="button" class="close" data-action="workspace-close" aria-label="Lukk versjoner">×</button></div></div><div class="workspace-body"><h3 class="workspace-title"></h3><p class="workspace-storage"></p><code class="workspace-path"></code><p class="workspace-unsaved" hidden>Lagre utkast før du lukker skissen eller samtalen.</p><details class="workspace-storage-details"><summary>Om lagring og gjenåpning</summary><p class="workspace-help"></p></details><p class="workspace-temporary-help" hidden></p><p class="workspace-recovered" hidden>Arbeidet er åpnet fra prosjektet. Tidligere runder sendes ikke på nytt.</p><p class="workspace-dirty" hidden></p><div class="workspace-confirm" tabindex="-1" hidden><h3 class="workspace-confirm-title"></h3><p>Dette lager en ny skisseversjon. Innspill, svar og innsendte runder beholdes.</p><p class="workspace-restore-warning"></p><div class="workspace-actions"><button type="button" class="primary" data-action="workspace-restore">Bruk som ny versjon</button><button type="button" class="primary" data-action="workspace-release-restore" hidden>Tillat endring og bruk versjonen</button><button type="button" data-action="workspace-cancel">Avbryt</button></div></div><p class="error workspace-error" role="alert" hidden></p><p class="workspace-status" role="status"></p><div class="workspace-history" hidden><div class="workspace-history-tools"><h3>Versjonshistorikk</h3><button type="button" data-action="workspace-reload">Oppdater</button></div><div class="workspace-history-list"></div><button type="button" data-action="workspace-more" hidden>Vis flere versjoner</button></div></div></section>
    <div class="endre-bar" role="group" aria-label="Endre skissen" hidden><div class="endre-tabs"><button type="button" data-action="change-ask" aria-pressed="false">Be om endring</button></div><div class="endre-ask" hidden><div class="tools" role="group" aria-label="Type markering"><button type="button" data-action="point" aria-pressed="true">Punkt</button><button type="button" data-action="area" aria-pressed="false">Område</button></div><select id="change-part" aria-label="Velg en del"><option value="">Eller velg en del …</option></select></div></div>
    <div class="vis-bar" role="group" aria-label="Vis" hidden><div class="vis-tabs"><button type="button" data-action="vis-compare" aria-pressed="false">Sammenlign varianter</button></div></div>
    <section class="composer" role="dialog" aria-modal="false" aria-labelledby="compose-title" hidden>
      <div class="row between"><h2 id="compose-title">Nytt innspill</h2><button type="button" class="close" data-action="hide-draft" aria-label="Legg utkast til side">×</button></div><div class="anchor-label"></div>
      <p class="compose-scope" hidden>Gjelder den lagrede versjonen. Ulagrede endringer i «Rediger» er ikke med.</p>
      <label for="feedback-note">Hva vil du endre?</label><textarea id="feedback-note" maxlength="2000" placeholder="For eksempel: Gi overskriften mer luft …"></textarea>
      <button type="button" class="proposal-toggle" data-action="proposal" aria-expanded="false" hidden>Foreslå ny tekst</button>
      <div class="proposal-fields" hidden><label for="feedback-proposal">Ny tekst</label><textarea id="feedback-proposal" maxlength="2000" placeholder="Skriv inn teksten du foreslår"></textarea><button type="button" class="preview-button" data-action="preview-draft">Forhåndsvis teksten</button><button type="button" class="preview-button" data-action="inspect-preview" hidden>Se i skissen</button><p class="help">Kun en lokal forhåndsvisning. Forslaget sendes som et innspill.</p></div>
      <p class="error compose-error" role="alert" hidden></p><div class="compose-actions"><button type="button" data-action="discard">Forkast</button><button type="button" class="primary save" data-action="save">Lagre innspill</button></div><div class="help">⌘/Ctrl + Enter lagrer · Esc legger utkastet til side</div><p class="canvas-close-hint" hidden>Lukker du skissen i appen, går ulagrede utkast og merknader tapt. Lagre dem som innspill først.</p>
    </section>
    <div class="toolbar" role="toolbar" aria-label="Verktøy for prototype"><button type="button" data-action="browse" aria-pressed="true"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 3l10 7-5 1-2 5z"/></svg> Prøv</button><button type="button" data-action="comment" aria-pressed="false"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 4h12v9H9l-5 3z"/></svg> Endre</button><span class="divider"></span><button type="button" data-action="panel" aria-expanded="false">Innspill<span class="count total">0</span></button><button type="button" class="draft-button" data-action="resume" hidden>Fortsett utkast</button><button type="button" class="update" data-action="refresh" hidden>Vis ny versjon</button></div>
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
  // «Klar til sending» holds what the next round sends; «Sendt» holds rounds and sent feedback.
  let tab = "ready";
  let draft = null;
  let savingDraft = null;
  let workshop = null;
  let editor = null;
  let frameRefreshing = false;
  let savedVersionWaiting = false;
  const refreshDisabled = new Map();
  let drag = null;
  let preview = null;
  let previewSpacer = null;
  let updateAvailable = false;
  let lastBusy = null;
  let requestCounter = 0;
  let submitting = false;
  let submissionRetry = {};
  let sentCount = 0;
  let layoutPending = false;
  let connectionLost = false;
  let addedTabStops = [];
  let originalTouchAction = document.documentElement.style.touchAction;
  const requests = new Map();
  const commentRetries = new Map();
  const canvasCards = new Map();
  const canvasStatuses = new Map();
  let canvasRendered = false;
  let canvasSignature = "";
  let workspaceLoading = false;
  let workspaceRestoring = false;
  let workspaceRestoreOpen = false;
  let workspaceEntries = [];
  let workspaceNextAfter = null;
  let workspaceConfirmation = null;
  const workspaceButton = button("Versjoner", "workspace-open");
  workspaceButton.hidden = true;
  workspaceButton.setAttribute("aria-expanded", "false");
  el(".toolbar").insertBefore(workspaceButton, el('[data-action="panel"]'));
  const endreBar = el(".endre-bar"), visBar = el(".vis-bar");
  // Endre stays open across its tools until the designer chooses Prøv.
  let endreSticky = false;
  // Declared parts can be chosen directly instead of pointing in the sketch.
  const declared = window.__grillmesterVisualCompanionDesign;
  const content = () => document.body.querySelector(":scope > .vc-content");
  const partOptions = [["whole", "Hele skissen"]];
  for (const target of Array.isArray(declared?.targets) ? declared.targets : []) {
    if (typeof target?.key === "string" && typeof target.label === "string") partOptions.push([`target:${target.variant || ""}/${target.key}`, target.label]);
  }
  for (const text of declared?.version === 2 && Array.isArray(declared.texts) ? declared.texts : []) {
    if (typeof text?.id === "string" && typeof text.label === "string") partOptions.push([`text:${text.id}`, text.label]);
  }
  for (const [value, label] of partOptions) { const option = document.createElement("option"); option.value = value; option.textContent = label; el("#change-part").appendChild(option); }
  // A stored version starts from its declared values, as the current preview
  // does through «Juster visning».
  function applyDeclaredStart() {
    for (const target of Array.isArray(declared?.targets) ? declared.targets : []) {
      const element = typeof target?.key === "string" ? partElement(`target:${target.variant || ""}/${target.key}`) : null;
      for (const control of element && Array.isArray(target.controls) ? target.controls : []) {
        if (/^[a-z][a-z0-9-]{0,47}$/.test(control?.id || "") && typeof control.initial === "string") element.setAttribute(`data-vc-setting-${control.id}`, control.initial);
      }
    }
  }
  function partElement(value) {
    if (value === "whole") return content();
    const exact = (name, key, within = document) => Array.from(within.querySelectorAll(`[${name}]`)).filter((node) => node.getAttribute(name) === key);
    if (value.startsWith("text:")) { const found = exact("data-vc-text", value.slice(5)); return found.length === 1 ? found[0] : null; }
    const [variant, key] = value.slice(7).split("/");
    const wrappers = variant ? exact("data-vc-variant", variant) : [document];
    const found = wrappers.length === 1 ? exact("data-vc-key", key, wrappers[0]).filter((node) => variant ? node.closest("[data-vc-variant]") === wrappers[0] : !node.closest("[data-vc-variant]")) : [];
    return found.length === 1 ? found[0] : null;
  }
  // Feedback, adjustments and editing belong to the current version, so a
  // stored version only offers going back or using it as a new version.
  if (view) {
    for (const action of ["comment", "panel", "resume", "refresh"]) el(`[data-action="${action}"]`).hidden = true;
    el(".toolbar .divider").hidden = true;
    pinLayer.hidden = true;
    const banner = document.createElement("div"); banner.className = "view-banner";
    const text = span(view.unavailable ? `Versjon ${view.revisionId || ""} kan ikke vises.` : `Viser lagret versjon ${view.revisionId}. Ingen ny versjon er laget.`, "view-text");
    text.setAttribute("role", "status");
    banner.append(text, button("Tilbake til gjeldende versjon", "view-current"));
    if (!view.unavailable) banner.append(button("Bruk som ny versjon", "view-restore"));
    el(".toolbar").prepend(banner);
    el(".toolbar").classList.add("viewing");
  }
  const safeRoles = new Set(["button", "link", "textbox", "heading", "img", "navigation", "main", "region", "group", "list", "listitem", "checkbox", "radio", "combobox", "tab", "tabpanel", "table", "row", "cell", "alert", "status", "presentation", "none"]);

  function announce(text) { el(".sr").textContent = text; }
  function ownEvent(event) { return event.composedPath().includes(host); }
  function usableTarget(target) {
    return target instanceof Element && target !== host && target !== previewSpacer && !host.contains(target)
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
  function canvasRounds() { return Array.isArray(snapshot.canvas?.rounds) ? snapshot.canvas.rounds : null; }
  function canvasStatus(round) { return round.review === "answered" ? "answered" : round.previousSession ? "previous" : round.review === "working" ? "working" : round.delivery; }
  function uncertainDelivery() { return canvasRounds()?.some((round) => !round.previousSession && round.delivery === "unknown" && round.review === "unread") || false; }
  function sendingDelivery() { return canvasRounds()?.some((round) => !round.previousSession && round.delivery === "sending" && round.review === "unread") || false; }
  function busy() { return Boolean(draft || drag || preview || !el(".workspace-panel").hidden || pendingComments().length || requests.size || workshop?.isBusy() || editor?.isDirty() || editor?.isOpen() || editor?.isSaving()); }
  function blocksRefresh() { return Boolean(draft || drag || preview || pendingComments().length || requests.size || workshop?.isSaving() || workshop?.hasRemarks() || editor?.isDirty() || editor?.isSaving()); }
  function saving() { return Boolean(savingDraft || workshop?.isSaving() || workspaceRestoring || editor?.isSaving() || frameRefreshing || savedVersionWaiting); }
  function lockRefreshControls() {
    if (!frameRefreshing && !savedVersionWaiting) return;
    all("button,textarea,input,select").forEach(node => { if (!refreshDisabled.has(node)) refreshDisabled.set(node, node.disabled); node.disabled = true; });
  }
  function setRefreshing(value) {
    frameRefreshing = value;
    if (!value && !savedVersionWaiting) { for (const [node, disabled] of refreshDisabled) if (node.isConnected) node.disabled = disabled; refreshDisabled.clear(); }
    updateBusy(); editor?.refreshControls();
  }
  function refreshNow() { savedVersionWaiting = false; setRefreshing(true); post({ action: "refresh-now", screen }); }
  function headerInset() { return Math.max(64, Math.ceil((document.body.querySelector(":scope > .vc-header")?.getBoundingClientRect().bottom || 0) + 10)); }
  function topInset() { return headerInset(); }
  // On narrow portrait screens, «Juster visning» and Rediger open as a bottom
  // sheet so the top of the sketch stays visible while values change.
  function sheetTop() {
    if (innerWidth >= 760 || innerHeight < 700) return topInset();
    const below = innerHeight - controlsTop() + 12;
    return Math.max(topInset(), Math.round(innerHeight - below - Math.max(440, innerHeight * 0.55)));
  }
  // The Endre bar sits just above the toolbar; layout keeps content clear of both.
  function controlsTop() {
    return Math.min(el(".toolbar").getBoundingClientRect().top, ...[endreBar, visBar].filter((bar) => !bar.hidden).map((bar) => bar.getBoundingClientRect().top));
  }
  function syncEndre() {
    const tool = Boolean(editor?.isOpen());
    if (tool) endreSticky = true;
    const active = !view && (endreSticky || mode === "comment" || tool);
    const visible = active && panel.hidden && el(".workspace-panel").hidden;
    // An open Rediger shows the Endre tabs in its title row instead of the bar.
    const head = editor?.isOpen() ? root.querySelector(".source-editor-head .row") : null;
    const tabs = el(".endre-tabs"), home = head || endreBar;
    if (tabs.parentElement !== home) home.prepend(tabs);
    for (const row of root.querySelectorAll(".with-endre-tabs")) if (row !== head) row.classList.remove("with-endre-tabs");
    head?.classList.add("with-endre-tabs");
    // With «Be om endring» as the only tool, its markers speak for themselves.
    tabs.hidden = !Array.from(tabs.children).some((button) => button.dataset.action !== "change-ask" && !button.hidden);
    // Rediger locks every button inside it, the tabs included while they sit
    // there; in the bar they follow the shared saving and refresh state instead.
    if (!head) for (const button of tabs.querySelectorAll("button")) button.disabled = saving() || frameRefreshing || savedVersionWaiting;
    // In Prøv, Vis offers comparison and «Juster visning» when the sketch declares
    // them. An open «Juster visning» shows the Vis buttons in its title row.
    const comparing = Boolean(workshop?.isComparing());
    el('[data-action="vis-compare"]').hidden = !workshop?.canCompare();
    const visHead = workshop?.isOpen() ? root.querySelector(".workshop-head .row") : null;
    const visTabs = el(".vis-tabs"), visHome = visHead || visBar;
    if (visTabs.parentElement !== visHome) visHome.prepend(visTabs);
    for (const row of root.querySelectorAll(".with-vis-tabs")) if (row !== visHead) row.classList.remove("with-vis-tabs");
    visHead?.classList.add("with-vis-tabs");
    if (!visHead) for (const button of visTabs.querySelectorAll("button")) {
      button.disabled = saving() || frameRefreshing || savedVersionWaiting || (button.dataset.action === "workshop-open" && Boolean(workshop?.isSaving()));
    }
    const vis = !view && !active && Boolean(workshop?.canCompare() || workshop?.canAdjust()) && !visHead && panel.hidden && el(".workspace-panel").hidden;
    // The bar shows the tabs, the ask tools in «Be om endring», or both; never neither.
    const endre = visible && !head && (!tabs.hidden || mode === "comment");
    const changed = endreBar.hidden === endre || visBar.hidden === vis;
    endreBar.hidden = !endre;
    visBar.hidden = !vis;
    el('[data-action="vis-compare"]').setAttribute("aria-pressed", String(comparing));
    host.toggleAttribute("data-endre", visible);
    el(".endre-ask").hidden = mode !== "comment";
    el('[data-action="change-ask"]').setAttribute("aria-pressed", String(mode === "comment"));
    el('[data-action="comment"]').setAttribute("aria-pressed", String(active));
    el('[data-action="browse"]').setAttribute("aria-pressed", String(!active));
    if (changed) scheduleLayout();
  }
  function updateBusy() {
    const value = busy();
    if (value !== lastBusy) { lastBusy = value; post({ action: "feedback-busy", screen, busy: value }); }
    all(".toolbar button,.pin").forEach((button) => { button.disabled = saving(); });
    const refresh = el('[data-action="refresh"]');
    refresh.hidden = !updateAvailable;
    const blocked = blocksRefresh();
    const discardView = !blocked && workshop?.isBusy();
    refresh.disabled = blocked || frameRefreshing || savedVersionWaiting;
    refresh.textContent = discardView ? "Nullstill og vis ny versjon" : "Vis ny versjon";
    refresh.title = blocked ? "Fullfør utkast, send innspill og avslutt forhåndsvisningen først" : discardView ? "Lokale visningsvalg nullstilles. Lagrede innspill beholdes." : "Åpne den nye versjonen";
    renderWorkspaceSummary();
    lockRefreshControls();
    syncEndre();
    scheduleLayout();
  }
  function request(action, payload, retry = {}) {
    if (connectionLost && action !== "comments-list") return Promise.reject(new Error("Økten er frakoblet. Kopier utkastet før du starter en ny økt."));
    let mutationId;
    if (!["comments-list", "workspace-history", "workspace-editor-read"].includes(action)) {
      const intent = JSON.stringify([action, payload]);
      if (retry.intent !== intent) {
        retry.intent = intent;
        retry.mutationId = Array.from(crypto.getRandomValues(new Uint8Array(16)), (value) => value.toString(16).padStart(2, "0")).join("");
      }
      mutationId = retry.mutationId;
    }
    const requestId = ++requestCounter;
    return new Promise((resolve, reject) => {
      const timer = window.setTimeout(() => {
        requests.delete(requestId);
        updateBusy();
        reject(new Error(action === "workspace-history" ? "Historikken kunne ikke hentes. Prøv igjen." : action === "workspace-restore" ? "Gjenopprettingen ble ikke bekreftet. Prøv samme handling igjen før du velger en annen versjon."
          : action.startsWith("workspace-editor-") ? "Handlingen ble ikke bekreftet. Utkastet ditt er beholdt. Prøv samme handling igjen." : "Lagringen ble ikke bekreftet. Behold utkastet og prøv samme innspill igjen."));
      }, 12000);
      requests.set(requestId, { resolve, reject, timer, action });
      updateBusy();
      post({ action, requestId, payload, ...(mutationId ? { mutationId } : {}) });
    });
  }
  function errorAt(selector, message) {
    const target = el(selector);
    target.textContent = message || "";
    target.hidden = !message;
  }
  function composeError(message, field) {
    const error = el(".compose-error");
    field.before(error);
    errorAt(".compose-error", message);
    field.focus();
    error.scrollIntoView({ block: "nearest" });
  }
  function setPanel(open, focus = false) {
    if (open && saving()) return;
    if (open) { editor?.close(); workshop?.close(); closeWorkspace(); }
    panel.hidden = !open;
    el('[data-action="panel"]').setAttribute("aria-expanded", String(open));
    if (open && draft && !composer.hidden) hideDraft();
    if (open && focus) el('[data-action="close-panel"]').focus();
    if (!open && focus) el('[data-action="panel"]').focus();
    syncEndre();
    updateHint();
  }
  // Unsent comments and kept-part changes wait in «Klar til sending»; sent
  // feedback, standing kept parts and rounds are under «Sendt».
  function tabHasItems(name) {
    return name === "ready" ? pendingComments().length > 0
      : [...snapshot.comments, ...(snapshot.decisions || [])].some((item) => item.submission > 0) || Boolean(canvasRounds()?.length);
  }
  function feedbackTab({ commentId, decisionId }) {
    const item = decisionId ? snapshot.decisions?.find((entry) => entry.id === decisionId) : snapshot.comments.find((entry) => entry.id === commentId);
    return item?.submission > 0 ? "sent" : "ready";
  }
  function setTab(next, focus = false) {
    tab = next;
    all("[data-tab]").forEach((entry) => { const selected = entry.dataset.tab === tab; entry.setAttribute("aria-selected", String(selected)); entry.tabIndex = selected ? 0 : -1; });
    el(".list").setAttribute("aria-labelledby", `basket-${tab}`);
    el(".filters").hidden = tab !== "sent";
    if (tab === "ready") filter = "all";
    all("[data-filter]").forEach((entry) => entry.setAttribute("aria-pressed", String(entry.dataset.filter === filter)));
    renderComments();
    if (focus) el(`[data-tab="${tab}"]`).focus();
  }
  function revealFeedback({ comment, commentId, decisionId } = {}) {
    const id = commentId || (comment && snapshot.comments.slice().reverse().find((item) =>
      Object.entries(comment).every(([key, value]) => JSON.stringify(item[key]) === JSON.stringify(value)))?.id);
    filter = "all";
    setTab(feedbackTab({ commentId: id, decisionId }));
    setPanel(true);
    const card = Array.from(el(".comment-list").children).find((entry) => decisionId ? entry.dataset.decision === decisionId : id && entry.dataset.id === id);
    if (card) { card.scrollIntoView({ block: "nearest" }); card.focus({ preventScroll: true }); }
    else el('[data-action="close-panel"]').focus();
  }
  function updateHint() {
    const hint = el(".hint");
    hint.hidden = mode !== "comment" || !panel.hidden || !el(".workspace-panel").hidden || !composer.hidden || Boolean(preview);
    hint.textContent = marker === "area" ? workshop?.isComparing() ? "Avslutt sammenligning for å markere et område · Punkt kan brukes nå" : "Dra rundt et område · eller fokuser et element og trykk Enter" : "Trykk på et element · eller bruk Tab og Enter · Esc avslutter";
    document.documentElement.style.touchAction = mode === "comment" && marker === "area" && !workshop?.isComparing() ? "none" : originalTouchAction;
  }
  function setMode(next, nextMarker = marker) {
    if (saving()) return;
    editor?.close();
    closeWorkspace();
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
    previewSpacer?.remove(); previewSpacer = null;
    el('[data-action="edit-preview"]').hidden = true;
    el('[data-action="inspect-preview"]').hidden = true;
    el('[data-action="preview-draft"]').textContent = "Forhåndsvis teksten";
    updateBusy();
    updateHint();
    scheduleLayout();
  }
  function showPreview(target, value, owner = null) {
    resetPreview();
    if (!eligibleText(target) || !value.trim()) return false;
    const nodes = Array.from(target.childNodes).filter((node) => node.nodeType === Node.TEXT_NODE).map((node) => ({ node, value: node.data }));
    preview = { target, nodes, owner };
    nodes.forEach(({ node }, index) => { node.data = index === 0 ? value : ""; });
    el(".preview-bar").hidden = false;
    el('[data-action="inspect-preview"]').hidden = !draft || owner !== draft;
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
  function followLocalFragment(link) {
    if (mode !== "browse" || draft || preview || saving() || link.localName !== "a" || link.hasAttribute("disabled") || link.closest('[inert],[aria-disabled="true"],[aria-hidden="true"]')) return false;
    const fragment = link.getAttribute("href") || "";
    if (!/^#[A-Za-z][A-Za-z0-9_.:-]{0,127}$/.test(fragment)) return false;
    const id = fragment.slice(1);
    const target = document.getElementById(id);
    const content = document.body.querySelector(":scope > .vc-content");
    // Treat the fragment as an exact ID, never as a selector or a URL.
    // Duplicate IDs are ambiguous even if the first match is in the sketch.
    if (!target || !content?.contains(target)
      || Array.from(document.querySelectorAll("[id]")).filter((element) => element.getAttribute("id") === id).length !== 1
      || target.closest('[inert],[aria-disabled="true"],[aria-hidden="true"]')
      || target.matches(":disabled") || !target.getClientRects().length
      || getComputedStyle(target).visibility !== "visible") return false;
    target.scrollIntoView({ block: "center", behavior: "auto" });
    focusPrototype(target);
    return true;
  }
  function beginDraft(target, kind, rect, position) {
    if (saving()) return;
    if (!usableTarget(target)) return;
    if (draft) { resumeDraft(); announce("Fullfør eller forkast utkastet før du lager et nytt innspill."); return; }
    if (kind === "area" && workshop?.isComparing()) { announce("Avslutt sammenligning for å markere et område. Punkt kan brukes nå."); return; }
    const anchor = anchorFor(target, rect);
    if (!anchor.path) { announce("Dette elementet kan ikke markeres. Velg et mindre detaljert område."); return; }
    resetPreview();
    draft = { target, kind, anchor, context: workshop?.contextFor(target), retry: {}, proposal: false, focus: root.activeElement || document.activeElement, position: position || { x: Math.max(12, target.getBoundingClientRect().left), y: Math.max(12, target.getBoundingClientRect().bottom) } };
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
    closeWorkspace();
    if (preview && preview.owner !== draft) resetPreview();
    if (draft.kind === "area") workshop?.endComparison();
    setPanel(false);
    if (composer.hidden && draft.context) workshop?.restoreContext(draft.context);
    // A wish names the saved sketch; unsaved Rediger values stay in their own draft.
    el(".compose-scope").hidden = !editor?.isDirty();
    composer.hidden = false;
    if (preview) preview.inspecting = false;
    previewSpacer?.remove(); previewSpacer = null;
    el('[data-action="edit-preview"]').hidden = true;
    el('[data-action="resume"]').hidden = true;
    showDraftOutline();
    positionComposer();
    note.focus({ preventScroll: true });
    updateHint();
  }
  function inspectPreview() {
    if (!draft || !preview || preview.owner !== draft || saving()) return;
    composer.hidden = true;
    outline.hidden = true;
    el('[data-action="resume"]').hidden = false;
    el('[data-action="edit-preview"]').hidden = false;
    preview.inspecting = true;
    preview.needsReveal = true;
    if (!previewSpacer) {
      previewSpacer = document.createElement("div");
      previewSpacer.setAttribute("aria-hidden", "true");
      previewSpacer.style.cssText = "all:initial!important;display:block!important;pointer-events:none!important;";
      document.body.insertBefore(previewSpacer, host);
    }
    el('[data-action="edit-preview"]').focus({ preventScroll: true });
    announce("Viser tekstforslaget i skissen. Fortsett å redigere for å gå tilbake til utkastet.");
    updateHint();
    scheduleLayout();
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
    const bottomSpace = Math.max(80, window.innerHeight - controlsTop() + 12);
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
    if (!text) { composeError("Skriv et innspill før du lagrer.", note); return; }
    if (new TextEncoder().encode(text).length > 2000) { composeError("Innspillet er for langt. Kort det ned før du lagrer.", note); return; }
    if (draft.proposal && new TextEncoder().encode(proposalInput.value.trim()).length > 2000) { composeError("Tekstforslaget er for langt. Kort det ned før du lagrer.", proposalInput); return; }
    if (draft.proposal && !proposalInput.value.trim()) { composeError("Skriv inn teksten du foreslår.", proposalInput); return; }
    const payload = { screen, kind: draft.proposal ? "edit" : draft.kind, anchor: draft.anchor, text };
    if (draft.context) payload.context = draft.context;
    if (draft.proposal) payload.proposal = { property: "text", value: proposalInput.value.trim() };
    const submittedDraft = draft;
    savingDraft = submittedDraft;
    composer.setAttribute("aria-busy", "true");
    composer.querySelectorAll("button, textarea").forEach((target) => { target.disabled = true; });
    el(".save").textContent = "Lagrer …";
    errorAt(".compose-error", "");
    try {
      await request("comment-create", payload, submittedDraft.retry);
      if (draft !== submittedDraft) return;
      savingDraft = null;
      discardDraft();
      revealFeedback({ comment: payload });
      announce("Innspillet er lagret lokalt. Send innspill når du er klar.");
    } catch (error) { composeError(error.message, note); }
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
      for (const bar of [endreBar, visBar]) bar.style.bottom = `${Math.max(0, innerHeight - el(".toolbar").getBoundingClientRect().top) + 8}px`;
      const toolbarTop = controlsTop();
      const toolbarSpace = Math.max(80, innerHeight - toolbarTop + 12);
      document.documentElement.style.scrollPaddingBottom = `${toolbarSpace}px`;
      document.body.style.paddingBottom = `${toolbarSpace}px`;
      panel.style.bottom = `${Math.max(80, innerHeight - toolbarTop + 12)}px`;
      el(".workspace-panel").style.bottom = `${Math.max(80, innerHeight - toolbarTop + 12)}px`;
      for (const target of [panel, el(".workspace-panel"), el(".hint")]) target.style.top = `${topInset()}px`;
      const previewBar = el(".preview-bar");
      const inspecting = preview?.inspecting && composer.hidden;
      previewBar.style.top = inspecting ? "auto" : `${topInset()}px`;
      previewBar.style.bottom = inspecting ? `${innerHeight - toolbarTop + 12}px` : "auto";
      if (inspecting && previewSpacer) {
        previewSpacer.style.setProperty("height", `${innerHeight - previewBar.getBoundingClientRect().top + 12}px`, "important");
        if (preview.needsReveal) {
          preview.needsReveal = false;
          const comparison = el(".compare-bar");
          const top = Math.max(topInset(), comparison && !comparison.hidden ? comparison.getBoundingClientRect().bottom + 12 : 0);
          const bottom = previewBar.getBoundingClientRect().top - 12;
          const rect = preview.target.getBoundingClientRect();
          if (rect.top < top || rect.bottom > bottom) window.scrollBy({ top: rect.top - top - Math.max(0, (bottom - top - rect.height) / 2), behavior: "auto" });
        }
      }
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
    const list = el(".comment-list");
    const restoreCommentFocus = active && (list.contains(active) || pinLayer.contains(active));
    const focusIndex = Math.max(0, Array.from(list.children).indexOf(active?.closest(".comment,.workshop-decision")));
    list.replaceChildren();
    pinLayer.replaceChildren();
    let shown = 0;
    snapshot.comments.forEach((item, index) => {
      const previous = item.screen !== screen;
      if (filter !== "all" && item.status !== filter) return;
      // Pins keep showing where all feedback on this screen points; cards follow the tab.
      if (!previous) {
        const pin = button(String(index + 1), "pin", item.id, `pin${item.status === "fixed" ? " fixed" : ""}`);
        pin.setAttribute("aria-label", `Innspill ${index + 1}, ${item.status === "fixed" ? "ordnet" : "åpent"}`);
        pin.hidden = true;
        pinLayer.appendChild(pin);
      }
      if (tab === "ready" ? item.submission > 0 : item.submission === 0) return;
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
      const lastSubmission = item.lastSubmission || item.submission;
      if (item.submission === 0) head.appendChild(span(lastSubmission > 0 ? "Ny runde ikke sendt" : "Ikke sendt", "badge"));
      if (lastSubmission > 0) head.appendChild(span(`Sendt i runde ${lastSubmission}`, "badge"));
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
      if (item.context) {
        const context = document.createElement("p");
        context.className = "proposal";
        context.append(span("Situasjon", "proposal-label"), document.createTextNode(workshop?.describeContext(item) || ""));
        card.appendChild(context);
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
      if (!previous && item.context && workshop?.canRestoreContext(item.context)) actions.appendChild(button("Vis situasjon", "locate", item.id));
      else if (!previous && commentRect(item)) actions.appendChild(button("Vis sted", "locate", item.id));
      if (!previous && item.proposal && eligibleText(resolveTarget(item.anchor))) actions.appendChild(button("Forhåndsvis tekst", "preview-saved", item.id));
      actions.append(button(item.status === "fixed" ? "Åpne igjen" : "Marker ordnet", "status", item.id), button(lastSubmission > 0 ? "Fjern fra listen" : "Slett", "delete", item.id, "danger"));
      card.appendChild(actions);
      list.appendChild(card);
    });
    if (tab === "ready") shown += workshop?.appendFeedback(list, (decision) => decision.submission === 0) || 0;
    else if (filter === "all") shown += workshop?.appendFeedback(list, (decision) => decision.submission > 0) || 0;
    if (!shown && !(tab === "sent" && filter === "all" && canvasRounds()?.length)) {
      const empty = document.createElement("div");
      empty.className = "empty";
      const title = document.createElement("strong");
      title.textContent = tab === "ready" ? "Hva kan bli bedre?" : filter === "all" ? "Ingen sendte innspill ennå" : "Ingen innspill her ennå";
      const text = document.createElement("p");
      text.textContent = tab === "ready" ? "Velg Endre, og pek på et element, marker et område eller velg en del. Innspillene samles her til du sender dem."
        : filter === "all" ? "Sendte innspill og svar vises her." : "Velg et annet filter for å se resten.";
      empty.append(title, text);
      list.appendChild(empty);
    }
    all(".total").forEach((target) => { target.textContent = String(snapshot.comments.length + (snapshot.decisions?.length || 0)); });
    el(".ready-count").textContent = String(pendingComments().length);
    el(".sent-count").textContent = String([...snapshot.comments, ...(snapshot.decisions || [])].filter((item) => item.submission > 0).length);
    if (restoreCommentFocus) {
      const previousButton = activeAction && Array.from(list.querySelectorAll("button")).find((target) => !target.disabled && target.dataset.action === activeAction && (activeDecision ? target.dataset.decision === activeDecision : target.dataset.id === activeId));
      const cards = Array.from(list.querySelectorAll(".comment,.workshop-decision"));
      const target = previousButton || cards.find((card) => activeDecision ? card.dataset.decision === activeDecision : card.dataset.id === activeId) || cards[Math.min(focusIndex, cards.length - 1)] || (tab === "sent" ? el(`[data-filter="${filter}"]`) : el(`[data-tab="${tab}"]`));
      target.focus({ preventScroll: true });
    }
    renderFooter();
    scheduleLayout();
  }
  function workspaceStored() { return snapshot.workspace?.storage === "project"; }
  function workspaceDrafts() { return Boolean(draft || drag || preview || workshop?.hasRemarks() || editor?.isDirty()); }
  function workspaceText(selector, text) { const node = el(selector); if (node.textContent !== text) node.textContent = text; }
  function displayedRevision() {
    if (view) return view.revisionId;
    const filename = snapshot.screens?.find((item) => item.screen === screen)?.filename;
    return workspaceEntries.find((entry) => entry.filename === filename)?.revisionId;
  }
  function renderWorkspaceSummary() {
    const stored = workspaceStored();
    workspaceButton.hidden = !stored && canvasRounds() === null;
    workspaceText(".workspace-title", stored ? snapshot.workspace.title : "Midlertidig økt");
    workspaceText(".workspace-storage", stored ? `Lagret i prosjektet · versjon ${snapshot.workspace.version}` : "Dette arbeidet er bare tilgjengelig i den midlertidige økten.");
    workspaceText(".workspace-path", stored ? snapshot.workspace.path : "");
    el(".workspace-storage-details").hidden = !stored;
    el(".workspace-unsaved").hidden = !stored;
    el(".workspace-temporary-help").hidden = stored;
    workspaceText(".workspace-help", "Lagrede innspill og skisseversjoner beholdes i prosjektet. Å lukke dette panelet beholder utkastene. Ulagrede utkast går tapt hvis du lukker selve skissen eller samtalen. Be i samtalen om å åpne arbeidet igjen. Å lukke skissen frigjør ikke arbeidet for en annen samtale. Forhåndsvisningen bruker systemfont fordi Aksel-fonten ikke lastes fra nettet.");
    workspaceText(".workspace-temporary-help", "Be i samtalen om å opprette eller åpne et prosjektarbeid for varig lagring. Denne midlertidige økten blir ikke automatisk kopiert dit.");
    el(".workspace-recovered").hidden = !stored || !snapshot.workspace.recovered;
    el(".workspace-history").hidden = !stored;
    const dirty = workspaceDrafts();
    el(".workspace-dirty").hidden = !dirty;
    workspaceText(".workspace-dirty", "Du har et ulagret utkast, en merknad eller en tekstvisning. Fullfør eller forkast dette før du bruker en eldre versjon.");
    el(".workspace-confirm").hidden = !workspaceConfirmation;
    if (workspaceConfirmation) {
      workspaceText(".workspace-confirm-title", `Bruk versjon ${workspaceConfirmation.entry.revisionId} som utgangspunkt?`);
      workspaceText(".workspace-restore-warning", dirty ? "Gjenoppretting er satt på vent. Utkastet ditt er beholdt."
        : workshop?.isBusy() ? "Lokale visningsvalg nullstilles når den nye versjonen åpnes. Lagrede innspill beholdes."
          : "Skissen åpnes som en ny versjon. Ingen innspill blir sendt til samtalen.");
    }
    const restore = el('[data-action="workspace-restore"]');
    restore.disabled = !stored || !workspaceConfirmation || workspaceConfirmation.conflict || workspaceConfirmation.capacity || dirty || connectionLost || workspaceLoading || savingDraft || workshop?.isSaving() || workspaceRestoring;
    restore.textContent = workspaceRestoring ? "Lagrer ny versjon …" : workspaceConfirmation?.capacity ? "Lagringsgrensen er nådd" : workspaceConfirmation?.retry.intent ? "Prøv samme gjenoppretting igjen" : "Bruk som ny versjon";
    all(".workspace-panel button").forEach(node => {
      const current = node.dataset.action === "workspace-choose" && Number(node.dataset.revisionId) === snapshot.workspace?.version;
      if (node.dataset.action === "workspace-choose") node.textContent = current ? "Gjeldende versjon" : "Bruk som ny versjon";
      if (node !== restore && node.dataset.action !== "workspace-release-restore") node.disabled = workspaceRestoring || (workspaceLoading && node.dataset.action !== "workspace-close") || current;
      if (node.dataset.revisionId && ["workspace-view", "view-current"].includes(node.dataset.action)) {
        const shown = Number(node.dataset.revisionId) === displayedRevision();
        node.textContent = shown ? "Vises nå" : "Vis";
        node.disabled ||= shown || dirty || connectionLost;
      }
    });
    const releaseRestore = el('[data-action="workspace-release-restore"]');
    const held = workspaceConfirmation?.conflicts?.length ? workspaceConfirmation.conflicts : null;
    releaseRestore.hidden = !held;
    releaseRestore.disabled = !held || dirty || connectionLost || workspaceLoading || savingDraft || workspaceRestoring;
    if (held) releaseRestore.textContent = workspaceRestoring ? "Lagrer ny versjon …" : `Tillat endring og bruk versjon ${workspaceConfirmation.entry.revisionId}`;
    el('[data-action="workspace-more"]').hidden = workspaceNextAfter === null;
    el(".workspace-panel").setAttribute("aria-busy", String(workspaceLoading || workspaceRestoring));
  }
  function closeWorkspace(focus = false) {
    if (workspaceRestoring) return;
    const wasOpen = !el(".workspace-panel").hidden;
    el(".workspace-panel").hidden = true;
    workspaceButton.setAttribute("aria-expanded", "false");
    if (wasOpen && focus) workspaceButton.focus();
    syncEndre();
  }
  async function openWorkspace() {
    if (saving()) return;
    if (draft && !composer.hidden) hideDraft();
    workshop?.close(); setPanel(false); endreSticky = false; setMode("browse");
    el(".workspace-panel").hidden = false;
    workspaceButton.setAttribute("aria-expanded", "true");
    el('[data-action="workspace-close"]').focus();
    renderWorkspaceSummary(); updateBusy(); updateHint();
    if (workspaceStored() && !workspaceEntries.length && !workspaceLoading) await loadWorkspaceHistory();
  }
  function renderWorkspaceHistory() {
    const list = el(".workspace-history-list");
    list.replaceChildren();
    for (const entry of workspaceEntries.slice().sort((a, b) => b.revisionId - a.revisionId)) {
      const card = document.createElement("article"); card.className = "workspace-revision";
      card.dataset.revisionId = String(entry.revisionId);
      const title = document.createElement("h3"); title.textContent = `Versjon ${entry.revisionId} · ${entry.label || entry.filename}`;
      const detail = document.createElement("p"); detail.className = "muted";
      const date = new Date(entry.createdAt);
      detail.textContent = `${Number.isNaN(date.getTime()) ? "" : date.toLocaleString("nb-NO", { dateStyle: "short", timeStyle: "short" })}${entry.restoredFrom ? ` · Fra versjon ${entry.restoredFrom}` : ""}`;
      const current = entry.revisionId === snapshot.workspace?.version;
      const choose = button(current ? "Gjeldende versjon" : "Bruk som ny versjon", "workspace-choose");
      choose.dataset.revisionId = String(entry.revisionId); choose.disabled = current;
      // Viewing is read-only and separate from using a version as a new one.
      const show = button("Vis", view && current ? "view-current" : "workspace-view");
      show.dataset.revisionId = String(entry.revisionId);
      show.setAttribute("aria-label", `Vis versjon ${entry.revisionId}`);
      card.append(title, detail, show, choose); list.appendChild(card);
    }
    if (!workspaceEntries.length) list.appendChild(span("Ingen skisseversjoner er lagret ennå.", "muted"));
    renderWorkspaceSummary();
  }
  async function loadWorkspaceHistory(more = false) {
    if (!workspaceStored() || workspaceLoading || workspaceRestoring) return;
    workspaceLoading = true;
    errorAt(".workspace-error", "");
    workspaceText(".workspace-status", "Henter versjonshistorikk …");
    renderWorkspaceSummary();
    try {
      const value = await request("workspace-history", { after: more ? workspaceNextAfter : 0, limit: 20 });
      if (!value || !Array.isArray(value.items) || typeof value.hasMore !== "boolean") throw new Error("Historikken kunne ikke leses.");
      workspaceEntries = more ? [...workspaceEntries, ...value.items.filter(entry => !workspaceEntries.some(known => known.revisionId === entry.revisionId))] : value.items;
      workspaceNextAfter = value.hasMore ? value.nextAfter : null;
      if (!more && (!workspaceConfirmation?.retry.intent || workspaceConfirmation.conflict)) workspaceConfirmation = null;
      renderWorkspaceHistory();
      workspaceText(".workspace-status", `${workspaceEntries.length} skisseversjoner i listen.`);
    } catch (error) { errorAt(".workspace-error", error.message); }
    finally {
      workspaceLoading = false; renderWorkspaceSummary();
    }
  }
  async function restoreWorkspace() {
    const chosen = workspaceConfirmation;
    if (!chosen || el('[data-action="workspace-restore"]').disabled) return;
    workspaceRestoring = true;
    errorAt(".workspace-error", ""); updateBusy();
    try {
      await request("workspace-restore", { revisionId: chosen.entry.revisionId, expectedRevision: chosen.expectedRevision }, chosen.retry);
      workspaceConfirmation = null;
      workspaceRestoreOpen = true;
      workspaceText(".workspace-status", "En ny skisseversjon er lagret. Innspill og svar er beholdt.");
      announce("En ny skisseversjon er lagret. Ingen innspill er sendt.");
      if (view) post({ action: "view-current" });
      else if (updateAvailable) refreshNow();
    } catch (error) {
      if (error.conflict) chosen.conflict = true;
      if (error.capacity) chosen.capacity = true;
      if (error.editorConflict) chosen.conflicts = error.conflicts || [];
      const fields = (chosen.conflicts || []).map(item => `«${item.label}»`).join(", ");
      errorAt(".workspace-error", error.unavailable ? "Versjonen kan ikke brukes fordi en lagret fil er endret eller mangler. Ingen ny versjon er laget, og de andre versjonene kan fortsatt brukes."
        : error.editorConflict ? fields ? `Versjon ${chosen.entry.revisionId} endrer felt du har lagret: ${fields}. Velg «Tillat endring og bruk versjon ${chosen.entry.revisionId}» for å bruke den. Verdiene beholdes til en ny versjon endrer dem.`
          : `Versjon ${chosen.entry.revisionId} endrer felt du har lagret. Tillat senere endring av feltene i «Rediger skissen», og velg versjonen på nytt.`
        : error.conflict ? "Arbeidet er endret. Oppdater historikken og velg versjonen på nytt." : error.message);
    } finally { workspaceRestoring = false; updateBusy(); }
  }
  // Release exactly the preserved fields that blocked this restore, then restore.
  // Each step keeps its exact payload, so retrying after a lost response reuses
  // that step's receipt instead of starting a different change.
  async function releaseAndRestore() {
    const chosen = workspaceConfirmation;
    if (!chosen?.conflicts?.length || el('[data-action="workspace-release-restore"]').disabled) return;
    workspaceRestoring = true;
    errorAt(".workspace-error", ""); updateBusy();
    try {
      if (!chosen.release) {
        // The release names the current version, which a stored version on screen is not.
        const current = await request("workspace-editor-read", {});
        chosen.release = { payload: { screen: current.screen, expectedRevision: current.revision, ids: chosen.conflicts.map(item => item.id) }, retry: {} };
      }
      await request("workspace-editor-release", chosen.release.payload, chosen.release.retry);
      chosen.conflicts = []; chosen.conflict = false; chosen.release = null;
      // A retry through «Prøv samme gjenoppretting igjen» sends this same restore.
      chosen.expectedRevision = snapshot.revision; chosen.retry = {};
      await request("workspace-restore", { revisionId: chosen.entry.revisionId, expectedRevision: chosen.expectedRevision }, chosen.retry);
      workspaceConfirmation = null;
      workspaceRestoreOpen = true;
      workspaceText(".workspace-status", "Senere endring er tillatt, og en ny skisseversjon er lagret. Innspill og svar er beholdt.");
      announce("En ny skisseversjon er lagret. Ingen innspill er sendt.");
      if (view) post({ action: "view-current" });
      else if (updateAvailable) refreshNow();
    } catch (error) {
      if (error.conflict) { chosen.conflict = true; chosen.release = null; }
      errorAt(".workspace-error", error.conflict ? "Arbeidet er endret. Oppdater historikken og velg versjonen på nytt." : error.message);
    } finally { workspaceRestoring = false; updateBusy(); }
  }
  function renderCanvasRounds() {
    const rounds = canvasRounds();
    el(".composer .canvas-close-hint").hidden = rounds === null;
    el(".canvas-rounds").hidden = !rounds?.length || tab !== "sent";
    const signature = JSON.stringify(rounds);
    if (signature === canvasSignature) return;
    canvasSignature = signature;
    if (!rounds) return;
    const labels = { sending: "Sender …", queued: "I kø", unknown: "Levering ikke bekreftet", working: "Behandles", answered: "Besvart", previous: "Fra tidligere samtale" };
    const ordered = rounds.slice().sort((a, b) => b.submission - a.submission);
    const active = root.activeElement;
    const changes = [];
    for (const [index, round] of ordered.entries()) {
      const status = canvasStatus(round);
      let card = canvasCards.get(round.submission);
      if (!card) {
        card = document.createElement("article");
        card.className = "canvas-round";
        card.dataset.canvasSubmission = String(round.submission);
        card.setAttribute("aria-label", `Runde ${round.submission}`);
        const head = document.createElement("div"); head.className = "row";
        const title = document.createElement("strong"); title.textContent = `Runde ${round.submission}`;
        head.append(title, span("", "badge"));
        const uncertain = document.createElement("p"); uncertain.className = "canvas-uncertain";
        uncertain.textContent = `Runden er lagret. Levering til samtalen er ikke bekreftet, og den sendes ikke på nytt automatisk. Skriv «se runde ${round.submission}» i samtalen for å få den behandlet.`;
        const answer = document.createElement("details"); answer.className = "canvas-answer";
        const summary = document.createElement("summary"); summary.textContent = "Vis svar";
        const previous = document.createElement("p"); previous.className = "workspace-previous";
        answer.append(summary, document.createElement("p")); card.append(head, uncertain, previous, answer);
        canvasCards.set(round.submission, card);
      }
      if (card.dataset.status !== status) {
        card.dataset.status = status;
        card.querySelector(".badge").textContent = labels[status] || "Levering ikke bekreftet";
      }
      card.querySelector(".canvas-uncertain").hidden = status !== "unknown";
      const previous = card.querySelector(".workspace-previous");
      previous.hidden = !round.previousSession;
      const previousText = round.previousSession ? round.review === "answered" ? "Svaret er fra en tidligere samtale."
        : ["unknown", "sending"].includes(round.delivery) ? "Tidligere levering er uavklart. Runden sendes ikke på nytt automatisk."
          : "Runden ble sendt tidligere. Pågående behandling er ikke bekreftet i denne samtalen." : "";
      if (previous.textContent !== previousText) previous.textContent = previousText;
      const answer = card.querySelector(".canvas-answer"), reply = typeof round.reply === "string" ? round.reply : "";
      answer.hidden = !reply || round.review !== "answered";
      if (answer.querySelector("p").textContent !== reply) answer.querySelector("p").textContent = reply;
      const container = el(index < 3 ? ".canvas-recent" : ".canvas-older"), position = index < 3 ? index : index - 3;
      if (container.children[position] !== card) container.insertBefore(card, container.children[position] || null);
      if (canvasRendered && canvasStatuses.get(round.submission) !== status) changes.push(`Runde ${round.submission}: ${labels[status] || "Levering ikke bekreftet"}.`);
      canvasStatuses.set(round.submission, status);
    }
    for (const [submission, card] of canvasCards) {
      if (!rounds.some((round) => round.submission === submission)) { card.remove(); canvasCards.delete(submission); canvasStatuses.delete(submission); }
    }
    const history = el(".canvas-history");
    history.hidden = ordered.length <= 3;
    const historyLabel = `Tidligere runder (${Math.max(0, ordered.length - 3)})`;
    if (history.querySelector("summary").textContent !== historyLabel) history.querySelector("summary").textContent = historyLabel;
    if (active?.isConnected && el(".canvas-rounds").contains(active)) {
      if (el(".canvas-older").contains(active)) history.open = true;
      if (root.activeElement !== active) active.focus({ preventScroll: true });
    }
    canvasRendered = true;
    if (changes.length) announce(changes.slice(0, 3).join(" "));
  }
  function renderFooter() {
    renderCanvasRounds();
    const count = pendingComments().length;
    const canvas = canvasRounds() !== null, uncertain = uncertainDelivery(), sending = sendingDelivery();
    const unconfirmed = uncertain ? canvasRounds().find((round) => !round.previousSession && round.delivery === "unknown" && round.review === "unread").submission : null;
    el(".panel-intro").textContent = workspaceStored()
      ? "Lagrede innspill beholdes i prosjektet. Ulagrede utkast og merknader går tapt ved lukking."
      : canvas ? "Lagrede innspill beholdes i økten. Ulagrede utkast og merknader går tapt hvis du lukker skissen i appen."
      : snapshot.submission > 0
      ? "Send nye innspill samlet. Sendte runder bevares i denne økten, også når du fjerner innspill fra listen."
      : "Pek på det du vil forbedre. Send samlet når du er klar. Innspillene lagres bare i denne økten.";
    const live = !connectionLost && Date.now() < (snapshot.listeningUntil || 0);
    el(".pending").textContent = count ? `${count} innspill ${count === 1 ? "klart" : "klare"} til sending` : sentCount ? `${sentCount} innspill sendt` : "Ingen nye innspill";
    el(".send").disabled = !count || submitting || connectionLost || uncertain || sending;
    el(".send").textContent = count ? `Send ${count} innspill` : "Send innspill";
    el(".connection").textContent = connectionLost ? "Frakoblet" : canvas ? "Knyttet til samtalen" : live ? "Følger med" : "Lagres lokalt";
    el(".connection").classList.toggle("live", canvas ? !connectionLost : live);
    const status = connectionLost ? "Innspill kan ikke lagres nå. Kopier teksten du vil beholde før du starter en ny økt."
      : canvas ? uncertain ? `Levering av runde ${unconfirmed} er ikke bekreftet. Skriv «se runde ${unconfirmed}» i samtalen, så avklares den. Du kan lagre flere innspill imens.`
        : sending ? "Forrige runde sendes. Du kan lagre flere innspill mens du venter på bekreftelse."
        : "Send legger runden i samtalens kø. Lukking av skissen avbryter ikke arbeid som er mottatt."
        : live ? "Innspillene hentes når du sender." : "Skriv «se innspillene» i samtalen når du har sendt.";
    if (el(".foot-status").textContent !== status) el(".foot-status").textContent = status;
    updateBusy();
  }
  function applySnapshot(value) {
    if (!value || !Array.isArray(value.comments) || !Number.isSafeInteger(value.revision)) return;
    if (value.revision < snapshot.revision) return;
    const changed = snapshot.revision !== value.revision;
    snapshot = value;
    workshop?.render(snapshot);
    editor?.onSnapshot(snapshot);
    if (changed) renderComments();
    else renderFooter();
  }
  async function mutateComment(action, item) {
    errorAt(".panel-error", "");
    const retryKey = `${action}/${item.id}`;
    if (!commentRetries.has(retryKey)) commentRetries.set(retryKey, {});
    const retry = commentRetries.get(retryKey);
    try {
      if (action === "delete") {
        await request("comment-delete", { id: item.id }, retry);
        announce((item.lastSubmission || item.submission) > 0 ? "Innspillet er fjernet fra listen. Den sendte runden er beholdt." : "Innspillet er slettet.");
      }
      else {
        const reopening = item.status === "fixed";
        await request("comment-update", { id: item.id, status: reopening ? "open" : "fixed", ...(reopening ? { resubmit: true } : {}) }, retry);
        if (reopening) { revealFeedback({ commentId: item.id }); announce("Innspillet er åpnet igjen. Send innspill for å ta det opp i neste runde."); }
      }
      commentRetries.delete(retryKey);
    } catch (error) { errorAt(".panel-error", error.message); }
  }
  function locate(item, focus = false) {
    if (!item || item.screen !== screen) return;
    if (item.context) { resetPreview(); workshop?.restoreContext(item.context); }
    const target = resolveTarget(item.anchor);
    if (item.kind === "area") window.scrollTo({ top: Math.max(0, item.anchor.rect.y - innerHeight / 3), behavior: "auto" });
    else target?.scrollIntoView({ block: "center", behavior: "auto" });
    showOutline(commentRect(item));
    if (focus) {
      setPanel(true);
      const card = Array.from(el(".comment-list").children).find((entry) => entry.dataset.id === item.id);
      card?.scrollIntoView({ block: "nearest" });
      card?.focus({ preventScroll: true });
    } else focusPrototype(target);
  }

  root.addEventListener("click", (event) => {
    const target = event.target.closest("button");
    if (!target || target.disabled || saving()) return;
    const action = target.dataset.action;
    const item = snapshot.comments.find((entry) => entry.id === target.dataset.id);
    if (target.dataset.tab) setTab(target.dataset.tab);
    else if (target.dataset.filter) {
      filter = target.dataset.filter;
      all("[data-filter]").forEach((entry) => entry.setAttribute("aria-pressed", String(entry.dataset.filter === filter)));
      renderComments();
    } else if (action === "browse") { editor?.close(); endreSticky = false; setMode("browse"); }
    else if (action === "comment" || action === "change-ask") { endreSticky = true; setMode("comment"); }
    else if (action === "vis-compare") { workshop?.toggleComparison(); updateBusy(); }
    else if (action === "point" || action === "area") setMode("comment", action);
    else if (action === "panel") {
      // Waiting feedback opens «Klar til sending»; otherwise the chosen tab stays
      // unless it is empty and the other is not.
      const other = tab === "ready" ? "sent" : "ready";
      if (panel.hidden && pendingComments().length) setTab("ready");
      else if (panel.hidden && !tabHasItems(tab) && tabHasItems(other)) setTab(other);
      setPanel(panel.hidden, true);
    }
    else if (action === "close-panel") setPanel(false, true);
    else if (action === "workspace-open") void openWorkspace();
    else if (action === "workspace-close") { closeWorkspace(true); updateBusy(); updateHint(); }
    else if (action === "workspace-reload") void loadWorkspaceHistory();
    else if (action === "workspace-more") void loadWorkspaceHistory(true);
    else if (action === "workspace-cancel") { workspaceConfirmation = null; renderWorkspaceSummary(); el('[data-action="workspace-reload"]').focus(); }
    else if (action === "workspace-choose") {
      const entry = workspaceEntries.find(value => value.revisionId === Number(target.dataset.revisionId));
      if (entry) {
        workspaceConfirmation = { entry, expectedRevision: snapshot.revision, retry: {} };
        errorAt(".workspace-error", ""); renderWorkspaceSummary();
        el(".workspace-confirm").scrollIntoView({ block: "nearest" }); el(".workspace-confirm").focus({ preventScroll: true });
      }
    }
    else if (action === "workspace-view") { if (!workspaceDrafts()) post({ action: "view-revision", revisionId: Number(target.dataset.revisionId) }); }
    else if (action === "view-current") post({ action: "view-current" });
    else if (action === "view-restore" && view) {
      void openWorkspace().then(() => {
        workspaceConfirmation = { entry: workspaceEntries.find(value => value.revisionId === view.revisionId) || { revisionId: view.revisionId }, expectedRevision: snapshot.revision, retry: {} };
        errorAt(".workspace-error", ""); renderWorkspaceSummary();
        el(".workspace-confirm").scrollIntoView({ block: "nearest" }); el(".workspace-confirm").focus({ preventScroll: true });
      });
    }
    else if (action === "workspace-restore") void restoreWorkspace();
    else if (action === "workspace-release-restore") void releaseAndRestore();
    else if (action === "save") void saveDraft();
    else if (action === "discard") discardDraft();
    else if (action === "hide-draft") hideDraft();
    else if (action === "resume") resumeDraft();
    else if (action === "inspect-preview") inspectPreview();
    else if (action === "edit-preview") { resumeDraft(); proposalInput.focus(); }
    else if (action === "undo") {
      const original = preview?.target;
      resetPreview();
      if (!composer.hidden) proposalInput.focus();
      else if (draft) el('[data-action="resume"]').focus();
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
      else if (!showPreview(draft.target, proposalInput.value, draft)) composeError("Skriv inn teksten du vil forhåndsvise.", proposalInput);
    } else if (action === "preview-saved" && item) {
      if (item.context) { resetPreview(); workshop?.restoreContext(item.context); }
      showPreview(resolveTarget(item.anchor), item.proposal.value);
      setPanel(false);
      el('[data-action="undo"]').focus();
    } else if ((action === "status" || action === "delete") && item) void mutateComment(action, item);
    else if (action === "pin" && item) {
      const wanted = item.submission > 0 ? "sent" : "ready";
      if (tab !== wanted || (filter !== "all" && filter !== item.status)) { filter = "all"; setTab(wanted); }
      locate(item, true);
    } else if (action === "locate" && item) { setPanel(false); locate(item); }
    else if (action === "refresh" && !blocksRefresh()) refreshNow();
    else if (action === "send" && !submitting && !uncertainDelivery() && !sendingDelivery()) {
      submitting = true;
      const count = pendingComments().length;
      target.disabled = true;
      errorAt(".panel-error", "");
      request("comments-submit", { revision: snapshot.revision }, submissionRetry).then(() => {
        submissionRetry = {};
        sentCount = count;
        setTab("sent");
        if (canvasRounds() === null) announce("Innspillene er sendt. Skriv «se innspillene» i samtalen hvis ingen følger med.");
      }).catch((error) => errorAt(".panel-error", error.message)).finally(() => { submitting = false; renderFooter(); });
    }
  });
  el("#change-part").addEventListener("change", (event) => {
    const value = event.target.value, element = value ? partElement(value) : null;
    event.target.value = "";
    if (element) beginDraft(element, "point", null);
    else if (value) announce("Delen finnes ikke i denne versjonen.");
  });
  proposalInput.addEventListener("input", () => {
    if (preview?.owner === draft && draft?.proposal) showPreview(draft.target, proposalInput.value, draft);
  });
  root.addEventListener("keydown", (event) => {
    if (saving()) return;
    if (event.target.closest(".basket-tabs") && ["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      setTab(event.key === "Home" ? "ready" : event.key === "End" ? "sent" : tab === "ready" ? "sent" : "ready", true);
      return;
    }
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
    else if (!el(".workspace-panel").hidden) { closeWorkspace(true); updateBusy(); updateHint(); }
    else if (preview) { const original = preview.target; resetPreview(); if (draft) el('[data-action="resume"]').focus(); else focusPrototype(original); }
    else { endreSticky = false; setMode("browse"); el('[data-action="browse"]').focus(); }
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
    if (workshop?.onPrototypeAction(event)) { event.preventDefault(); event.stopImmediatePropagation(); return; }
    const link = event.target.closest("a, area");
    if (link) { event.preventDefault(); followLocalFragment(link); return; }
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
      else if (!el(".workspace-panel").hidden) { closeWorkspace(true); updateBusy(); updateHint(); }
      else { endreSticky = false; setMode("browse"); }
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
  window.addEventListener("resize", () => { if (preview?.inspecting) preview.needsReveal = true; renderComments(); });
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
      if (connectionLost) { workspaceRestoreOpen = false; savedVersionWaiting = false; setRefreshing(false); }
      renderFooter();
      announce(connectionLost ? "Forbindelsen er brutt. Utkast kan kopieres, men ikke lagres nå." : "Forbindelsen er tilbake.");
      return;
    }
    if (data.command === "refreshing") {
      setRefreshing(true);
      document.getElementById("refresh-indicator")?.classList.add("visible");
      return;
    }
    if (data.command === "update-available") {
      if (view) return;
      const cancelledRefresh = frameRefreshing;
      setRefreshing(false);
      document.getElementById("refresh-indicator")?.classList.remove("visible");
      updateAvailable = true;
      updateBusy();
      if (workspaceRestoreOpen && !workspaceDrafts() && !cancelledRefresh) { refreshNow(); return; }
      if (cancelledRefresh) workspaceRestoreOpen = false;
      announce("En ny versjon er klar. Fullfør innspillene og velg Vis ny versjon.");
      return;
    }
    if (data.command === "comments-snapshot") { applySnapshot(data.snapshot); return; }
    if (data.command === "comments-result" || data.command === "workspace-result") {
      const pending = requests.get(data.requestId);
      if (!pending) return;
      if ((data.command === "workspace-result") !== pending.action.startsWith("workspace-")) return;
      window.clearTimeout(pending.timer);
      requests.delete(data.requestId);
      if (data.snapshot) applySnapshot(data.snapshot);
      updateBusy();
      if (data.ok) pending.resolve(data.result ?? data.snapshot);
      else {
        const failure = new Error(pending.action.startsWith("workspace-") && data.errorCode === "capacity" ? "Arbeidet har nådd en lagringsgrense. Historikk og innspill er beholdt. Be i samtalen om å opprette et nytt arbeid."
          : pending.action === "workspace-editor-read" ? "Feltene kunne ikke hentes. Prøv igjen."
          : pending.action.startsWith("workspace-editor-") ? data.conflict === true ? "Arbeidet er endret. Utkastet ditt er beholdt. Oppdater grunnlaget før du lagrer." : "Handlingen ble ikke bekreftet. Utkastet ditt er beholdt. Prøv samme handling igjen."
          : pending.action === "workspace-history" ? "Historikken kunne ikke hentes. Prøv igjen."
          : pending.action === "workspace-restore" ? "Gjenopprettingen ble ikke bekreftet. Prøv samme handling igjen før du velger en annen versjon."
          : data.conflict === true ? "Listen er endret. Se gjennom innspillene og send på nytt."
          : data.errorCode === "capacity" ? workspaceStored() ? "Arbeidet har nådd en lagringsgrense. Innspill og utkast er beholdt. En ny økt åpner det samme arbeidet, så be i samtalen om å opprette et nytt arbeid."
            : "Økten har nådd en lagringsgrense. Innspill og utkast er beholdt. Kopier teksten du vil ta vare på før du starter en ny økt."
            : "Lagringen ble ikke bekreftet. Behold utkastet og prøv samme innspill igjen.");
        failure.conflict = data.conflict === true;
        failure.capacity = data.errorCode === "capacity";
        failure.editorConflict = data.errorCode === "editor-conflict";
        failure.unavailable = data.errorCode === "revision-unavailable";
        failure.conflicts = Array.isArray(data.conflicts) ? data.conflicts.filter((item) => item && typeof item.id === "string" && typeof item.label === "string").slice(0, 32) : [];
        pending.reject(failure);
      }
      return;
    }
    if (data.command !== "selection-status" || data.screen !== screen || !pendingEvent || data.type !== pendingEvent.type || data.choice !== pendingEvent.choice || (data.status !== "saved" && data.status !== "failed")) return;
    persistenceStatus = data.status;
    pendingEvent = null;
    updateIndicator();
  });
  if (view) applyDeclaredStart();
  if (!view && typeof window.__grillmesterInitializeWorkshop === "function") {
    workshop = window.__grillmesterInitializeWorkshop({
      root, screen, nonce, request, anchorFor, announce, topInset,
      onPanelChange: syncEndre,
      panelTop: sheetTop,
      compareOpener: () => [el('[data-action="vis-compare"]'), el('[data-action="workshop-open"]'), el('[data-action="comment"]')].find((node) => node?.getClientRects().length) || el('[data-action="browse"]'),
      getSnapshot: () => snapshot,
      onBusyChange: updateBusy,
      onPresentationChange: () => { updateHint(); renderComments(); },
      refreshFeedback: renderComments,
      showFeedbackError: (message) => errorAt(".panel-error", message),
      isComposing: () => Boolean(draft && !composer.hidden),
      canTry: () => mode === "browse" && !draft && !preview && !saving() && !editor?.isOpen() && !editor?.isDirty(),
      focusPrototype,
      prepareOpen: () => {
        if (saving()) return false;
        editor?.close();
        closeWorkspace();
        if (draft && !composer.hidden) hideDraft();
        // «Juster visning» belongs to Prøv, so opening it leaves Endre.
        endreSticky = false; setMode("browse"); setPanel(false); return true;
      },
      openFeedback: revealFeedback,
    });
  }
  if (!view && typeof window.__grillmesterInitializeEditor === "function") {
    editor = window.__grillmesterInitializeEditor({
      root, screen, nonce, request, announce, topInset,
      onPanelChange: syncEndre,
      panelTop: sheetTop,
      onBusyChange: updateBusy,
      isRefreshing: () => frameRefreshing || savedVersionWaiting,
      focusOpener: () => (el('[data-action="editor-open"]:not([hidden])') || el('[data-action="workshop-open"]'))?.focus(),
      prepareOpen: () => {
        if (!workspaceStored() || saving()) return false;
        if (draft || drag || preview || workshop?.hasRemarks()) {
          // Show what is unfinished: the wish draft, or the merknad in «Juster visning».
          const message = "Fullfør eller forkast utkastet og merknadene før du redigerer skissen.";
          if (draft) resumeDraft();
          else if (workshop?.hasRemarks()) {
            workshop.open(); errorAt(".workshop-error", message);
            const error = el(".workshop-error"); error.tabIndex = -1; error.focus(); error.scrollIntoView({ block: "nearest" });
          }
          announce(message); return false;
        }
        workshop?.close(); closeWorkspace(); setPanel(false); setMode("browse"); return true;
      },
      openSavedVersion: () => { workspaceRestoreOpen = true; savedVersionWaiting = true; updateBusy(); if (updateAvailable) refreshNow(); },
    });
  }
  post({ action: "feedback-ready", screen });
  renderComments();
  request("comments-list", {}).catch((error) => errorAt(".panel-error", error.message));
  window.setInterval(renderFooter, 1000);
});
