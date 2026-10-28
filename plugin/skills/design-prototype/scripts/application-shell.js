/* The control surface is separate from the application origin. App messages
 * carry evidence only; only deliberate controls here can save or send feedback. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const rawConfig = window.__designApplication;
  delete window.__designApplication;
  let config;
  function previewConfig(value, token, title) {
    const preview = new URL(value.previewUrl);
    const origin = new URL(value.previewOrigin).origin;
    if (preview.origin !== origin || origin === location.origin || !["http:", "https:"].includes(preview.protocol)
      || typeof token !== "string" || !token || typeof value.epoch !== "string" || !value.epoch || !/^[a-f0-9]{32}$/.test(value.reportGeneration || "")) throw new Error();
    return Object.freeze({ previewUrl: preview.href, previewOrigin: origin, token, epoch: value.epoch, reportGeneration: value.reportGeneration, title });
  }
  try {
    if (rawConfig?.activationRequired === true) {
      if (typeof rawConfig.token !== "string" || !/^[a-f0-9]{64}$/.test(rawConfig.token)) throw new Error();
      config = Object.freeze({ token: rawConfig.token, title: rawConfig.title, activationRequired: true });
    } else config = previewConfig(rawConfig, rawConfig.token, rawConfig.title);
  } catch {
    $("app-status").textContent = "Visningen kunne ikke åpnes";
    $("stage-message").replaceChildren(message("strong", "Arbeidet mangler en gyldig appforbindelse"), message("p", "Be i samtalen om å åpne Designverksted på nytt. Ingen innspill er sendt."));
    return;
  }
  let frame = $("app-preview");
  let frameCheckpoint = null;
  let frameReady = false;
  let routeReady = false;
  let previewRequest = null;
  let previewTimer = null;
  let previewMissing = false;
  let state = null;
  let mode = "browse";
  let activePanel = null;
  let opener = $("mode-change");
  let activeTab = "pending";
  let selection = null;
  let replacement = null;
  let busy = false;
  let pendingSave = null;
  let pendingSubmit = null;
  let submissionNotice = null;
  let progressSignature = "";
  let activeSurface = "application";
  let proposalView = null;
  let proposalRequest = 0;
  let proposalTimer = null;
  let proposalBusy = false;
  let awaitingProposal = false;
  let restoredSurface = false;
  let surfaceChosenLocally = false;
  let proposalSeenScreen = null;
  let proposalSignature = "";
  let selectionQueue = Promise.resolve();
  let appPanelBeforeProposal = null;
  let pendingDelete = null;
  let pendingEdit = null;
  let editingComment = null;
  let editError = "";
  let previewState = "loading";
  let previewReportSequence = 0;
  let previewReportSignature = "";
  let pendingPreviewReport = null;
  let previewReporting = false;
  const narrowLayout = window.matchMedia("(max-width: 760px)");
  let ready = false;
  let latestRoute = "/";
  let viewQueue = Promise.resolve();
  let selectionRequest = 0;
  let stateRequest = 0;
  let lastListSignature = "";
  let pollTimer = null;
  let pollError = false;
  let routeSeen = null;
  let retired = false;
  let lastAnnouncement = "";
  let locationRequest = null;
  let locationTimer = null;
  let locationNotice = null;
  let locationPeeking = false;
  const MAX_TEXT_BYTES = 2000;
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const exact = (value, names) => object(value) && Object.keys(value).length === names.length && names.every(name => own(value, name));
  const finite = (value, minimum, maximum) => Number.isFinite(value) && value >= minimum && value <= maximum;
  const plain = (value, maximum) => typeof value === "string" && value.length <= maximum && !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value);
  const safeRoute = value => plain(value, 2048) && value.startsWith("/") && !value.startsWith("//") && !/[\\\r\n]/.test(value);
  const bytes = value => new TextEncoder().encode(value).length;
  const mutationId = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), value => value.toString(16).padStart(2, "0")).join("");
  const pendingComments = () => (state?.comments || []).filter(comment => comment.submission === 0);
  const sentComments = () => (state?.comments || []).filter(comment => Number.isSafeInteger(comment.submission) && comment.submission > 0);
  const hasDraft = () => Boolean($("comment-text").value.trim() || pendingSave);
  const getScreen = value => value?.screen || value?.application?.screen || "";
  const validScreen = value => typeof value === "string" && /^[a-f0-9]{32}$/.test(value);

  const locationReturnBar = document.createElement("div");
  locationReturnBar.id = "location-return-bar"; locationReturnBar.className = "location-return-bar"; locationReturnBar.hidden = true;
  const locationReturnNote = document.createElement("p"); locationReturnNote.id = "location-return-note"; locationReturnNote.className = "sr-only";
  locationReturnNote.textContent = "Stedet er markert i appen. Innspillene dine er beholdt.";
  const locationReturnButton = document.createElement("button");
  locationReturnButton.id = "location-return"; locationReturnButton.type = "button"; locationReturnButton.className = "button secondary";
  locationReturnButton.textContent = "Tilbake til innspill"; locationReturnButton.setAttribute("aria-describedby", locationReturnNote.id);
  locationReturnButton.addEventListener("click", returnToFeedback);
  locationReturnBar.append(locationReturnNote, locationReturnButton); $("workspace-tools").append(locationReturnBar);

  function message(tag, text, className) {
    const node = document.createElement(tag);
    node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function announce(text) {
    if (!text || text === lastAnnouncement) return;
    lastAnnouncement = text;
    $("announcement").textContent = text;
  }
  function errorAt(id, text) {
    $(id).textContent = text || "";
    $(id).hidden = !text;
  }
  function globalError(text) {
    $("global-message-text").textContent = text;
    $("global-message").hidden = !text;
  }
  function focusAvailable(...nodes) {
    const target = nodes.find(node => node?.isConnected && !node.disabled && !node.closest("[hidden],[inert]") && node.getClientRects().length);
    target?.focus();
    return target;
  }
  function commentCard(id) {
    return [...$("feedback-list").querySelectorAll("[data-comment]")].find(card => card.dataset.comment === id);
  }
  function feedbackOwnsFocus(id) {
    const active = document.activeElement;
    return activePanel === "feedback" && (active === document.body || active === $("feedback-list") || active === $("panel-title") || active?.closest?.("[data-comment]")?.dataset.comment === id);
  }
  function focusComment(id, key) {
    const card = commentCard(id);
    focusAvailable(...[...(card?.querySelectorAll("[data-focus-key]") || [])].filter(node => node.dataset.focusKey === key), card?.querySelector("h3"), $(`${activeTab}-tab`), $("panel-title"));
  }
  function routeLabel(route) {
    try {
      const url = new URL(route, config.previewOrigin);
      // Only server-validated current or saved context may expose its public query.
      const registered = route === state?.application?.route || (state?.comments || []).some(item => item.applicationContext?.route === route)
;
      return url.pathname + (registered ? url.search : "");
    } catch { return "/"; }
  }
  function syncPanelAccess() {
    const modal = Boolean(activePanel && narrowLayout.matches && !locationPeeking);
    $("panel-backdrop").hidden = !modal;
    $("side-panel").setAttribute("role", modal ? "dialog" : "complementary");
    if (modal) $("side-panel").setAttribute("aria-modal", "true");
    else $("side-panel").removeAttribute("aria-modal");
    document.querySelector(".preview-stage").inert = modal;
    document.querySelector(".app-header").inert = modal;
    $("workspace-tools").inert = modal;
    // Connection recovery belongs to the active dialog while it covers the app.
    for (const id of ["global-message", "navigation-message"]) {
      if (modal) $("side-panel").append($(id));
      else document.body.append($(id));
    }
    if (modal && !$("side-panel").contains(document.activeElement)) $("panel-title").focus();
  }
  function renderPreviewStatus(value) {
    const next = previewMissing ? "unavailable" : value?.state === "ready" && !frameReady ? "loading" : value?.state;
    if (!["loading", "ready", "unavailable"].includes(next)) return;
    const changed = next !== previewState;
    const statusHeldFocus = $("stage-message").contains(document.activeElement);
    previewState = next;
    $("stage-message").hidden = next === "ready";
    $("retry-preview").hidden = next !== "unavailable";
    $("stage-title").textContent = previewMissing ? "Appvisningen svarer ikke" : next === "unavailable" ? "Appen er ikke tilgjengelig" : "Åpner appen";
    $("stage-help").textContent = next === "unavailable"
      ? "Innspill og utkast er beholdt. Prøv å åpne appens startside igjen. Skjemaverdier i appen kan nullstilles. Har adressen endret seg, be i samtalen om å åpne appen på nytt."
      : "Venter på den lokale appen. Innspill og utkast er beholdt.";
    if (changed && next === "unavailable") announce("Appen er ikke tilgjengelig. Innspill og utkast er beholdt. Du kan prøve å åpne appen igjen.");
    else if (changed && next === "ready") announce("Appen er klar.");
    if (statusHeldFocus && next === "ready") focusAvailable(activePanel && narrowLayout.matches ? $("panel-title") : frame);
    const reason = next === "loading" ? "waiting-for-app" : next === "ready" ? "inspector-ready" : previewMissing ? "inspector-timeout" : "application-unavailable";
    const signature = `${next}:${reason}`;
    if (signature !== previewReportSignature) {
      previewReportSignature = signature;
      pendingPreviewReport = { generation: config.reportGeneration, sequence: ++previewReportSequence, state: next, reason };
    }
    void flushPreviewStatus();
  }
  async function flushPreviewStatus() {
    if (previewReporting || retired || !pendingPreviewReport) return;
    previewReporting = true;
    try {
      while (pendingPreviewReport && !retired) {
        const report = pendingPreviewReport;
        try { await api("/preview/status", { body: report }); }
        catch (error) {
          // A retired page must not reclaim diagnostics. Transient loss retries
          // only the latest observation on the existing state-poll schedule.
          if (error.status === 409 && pendingPreviewReport === report) pendingPreviewReport = null;
          return;
        }
        if (pendingPreviewReport === report) pendingPreviewReport = null;
      }
    } finally { previewReporting = false; }
  }
  const proposalList = () => (Array.isArray(state?.proposals) ? state.proposals : []).filter(item => object(item)
    && /^[a-f0-9]{24}$/.test(item.id || "") && plain(item.title, 200) && item.title.trim()
    && typeof item.available === "boolean" && (validScreen(item.screen) || !item.available && item.screen === ""));
  function proposalMessage(title, help, back = false) {
    if ($("proposal-message-title").textContent !== title) $("proposal-message-title").textContent = title;
    if ($("proposal-message-help").textContent !== help) $("proposal-message-help").textContent = help;
    if ($("proposal-back").hidden !== !back) $("proposal-back").hidden = !back;
    if ($("proposal-message").hidden) $("proposal-message").hidden = false;
  }
  function pendingProposalMessage() {
    const round = [...(state?.canvas?.rounds || [])].filter(item => !item.previousSession)
      .sort((left, right) => right.submission - left.submission)[0];
    if (round?.review === "working") {
      proposalMessage("Arbeider med innspillene …", "Du får svar under Sendt i Innspill. Nye skisseforslag vises her. Du kan prøve appen mens du venter.", true);
    } else if (round?.review === "answered") {
      proposalMessage("Innspillene er besvart", "Les svaret under Sendt i Innspill. Ikke alle innspill trenger et nytt forslag.", true);
    } else if (round?.delivery === "unknown") {
      proposalMessage("Mottaket er ikke bekreftet", "Innspillene er beholdt. Se Sendt i Innspill for neste steg.", true);
    } else if (round) {
      proposalMessage("Innspillene er sendt", "Venter på at de blir behandlet. Du kan prøve appen mens du venter.", true);
    } else {
      proposalMessage("Ingen forslag ennå", "Beskriv hva du vil endre i samtalen, eller gi et innspill i Appen nå. Forslaget vises her.");
    }
  }
  function rememberSurface(proposalId) {
    selectionQueue = selectionQueue.catch(() => {}).then(() => {
      if (retired) return;
      return api("/proposal/selection", { body: { proposalId } });
    }).catch(() => {
      if (!retired) announce("Valgt visning kunne ikke huskes. Innspillene dine er beholdt.");
    });
  }
  function selectSurface(surface, { remember = true, proposalId = null } = {}) {
    if (remember) surfaceChosenLocally = true;
    const changed = activeSurface !== surface;
    if (surface === "proposal" && changed) {
      appPanelBeforeProposal = activePanel;
      closePanel(false);
    }
    activeSurface = surface;
    if (surface === "application") awaitingProposal = false;
    for (const [id, selected] of [["app-tab", surface === "application"], ["proposal-tab", surface === "proposal"]]) {
      $(id).setAttribute("aria-selected", String(selected)); $(id).tabIndex = selected ? 0 : -1;
    }
    $("app-surface").hidden = surface !== "application";
    $("proposal-surface").hidden = surface !== "proposal";
    document.body.classList.toggle("showing-proposal", surface === "proposal");
    if (surface === "application" && changed && appPanelBeforeProposal) {
      openPanel(appPanelBeforeProposal, $("open-feedback"), false);
      appPanelBeforeProposal = null;
    }
    if (remember) rememberSurface(surface === "proposal" ? proposalId : null);
  }
  function proposalReady() {
    const proposal = proposalList().find(item => item.id === proposalView?.id);
    if (!proposalView || !proposal?.available || proposalView.renderedScreen !== proposal.screen) return;
    clearTimeout(proposalTimer);
    const newlyReady = !proposalView.ready || proposalView.confirmedScreen !== proposal.screen;
    proposalView.ready = true; proposalView.confirmedScreen = proposal.screen;
    $("proposal-preview").hidden = false;
    $("proposal-message").hidden = true;
    if (activeSurface === "proposal") {
      proposalSeenScreen = proposal.screen; $("proposal-new").hidden = true;
      if (newlyReady) announce(`${proposal.title} er klar. Du kan prøve skissen og gi innspill her.`);
    }
  }
  function renderProposals() {
    const proposals = proposalList(), proposal = proposals[0];
    $("proposal-new").hidden = !proposal?.available || proposal.screen === proposalSeenScreen;
    $("proposal-tab").setAttribute("aria-label", proposal?.available && proposal.screen !== proposalSeenScreen ? "Forslag, nytt forslag klart" : "Forslag");
    const signature = JSON.stringify(proposals.map(item => [item.id, item.title, item.screen, item.available]));
    if (signature !== proposalSignature) {
      const previouslyKnown = Boolean(proposalSignature && proposalSignature !== "[]");
      proposalSignature = signature;
      if (proposal?.available && proposal.screen !== proposalSeenScreen && (restoredSurface || previouslyKnown)) announce("Forslaget er klart. Velg Forslag for å se det.");
      if (proposal && !proposal.available && activeSurface === "proposal") proposalMessage("Forslaget er ikke tilgjengelig", "Innspill og svar er beholdt. Be i samtalen om å åpne forslaget igjen.", true);
    }
    if (!proposal && activeSurface === "proposal") pendingProposalMessage();
    proposalReady();
    // A designer may choose this tab before the first authenticated state has
    // arrived. Fulfil that existing choice once; do not move another tab or
    // retry failed activation automatically.
    if (awaitingProposal && activeSurface === "proposal" && proposal?.available && !proposalView && !proposalBusy) {
      awaitingProposal = false;
      void openProposal(proposal.id);
    }
    if (!restoredSurface) {
      restoredSurface = true;
      if (!surfaceChosenLocally && typeof state?.selectedProposalId === "string" && proposals.some(item => item.id === state.selectedProposalId)) {
        void openProposal(state.selectedProposalId, { restore: true });
      }
    }
  }
  function validatedProposalView(value, id) {
    if (!object(value) || !plain(value.url, 4096) || !plain(value.origin, 256) || !plain(value.title, 200)
      || !/^[a-f0-9]{64}$/.test(value.activationKey || "") || !/^[a-f0-9]{32}$/.test(value.leaseId || "")) throw new Error("Invalid proposal view.");
    const url = new URL(value.url), origin = new URL(value.origin);
    if (url.origin !== origin.origin || value.origin !== origin.origin || url.origin !== location.origin || url.protocol !== "http:"
      || !/^\/proposal-frame\/[a-f0-9]{64}$/.test(url.pathname) || url.username || url.password || url.search || url.hash) throw new Error("Invalid proposal origin.");
    return { id, url: url.href, origin: url.origin, title: value.title, activationKey: value.activationKey, leaseId: value.leaseId, ready: false, renderedScreen: null };
  }
  async function openProposal(id, { restore = false } = {}) {
    if (!restore) surfaceChosenLocally = true;
    const proposal = proposalList().find(item => item.id === id);
    if (retired) {
      if (proposalView?.id === id) selectSurface("proposal", { remember: false });
      else announce("Denne visningen er ikke aktiv. Åpne verkstedet igjen fra samtalen.");
      return;
    }
    if (!proposal) {
      selectSurface("proposal", { remember: false });
      awaitingProposal = true;
      pendingProposalMessage(); return;
    }
    awaitingProposal = false;
    selectSurface("proposal", { remember: !restore, proposalId: id });
    if (!proposal.available) { proposalMessage("Forslaget er ikke tilgjengelig", "Innspill og svar er beholdt. Be i samtalen om å åpne forslaget igjen.", true); return; }
    if (proposalView?.id === id) { proposalReady(); return; }
    if (proposalBusy) return;
    const request = ++proposalRequest;
    proposalBusy = true;
    proposalMessage("Åpner forslaget …", "Appen og innspillene dine er beholdt.");
    try {
      const value = await api("/proposal/open", { body: { proposalId: id } });
      if (retired || request !== proposalRequest) return;
      proposalView = validatedProposalView(value, id);
      $("proposal-preview").title = proposalView.title || proposal.title;
      $("proposal-preview").src = proposalView.url;
      // This is the authenticated bridge, not authored content. Its loading
      // and retry controls stay reachable before real sketch readiness.
      $("proposal-preview").hidden = false;
      $("proposal-message").hidden = true;
      clearTimeout(proposalTimer);
      proposalTimer = setTimeout(() => {
        if (retired || request !== proposalRequest || proposalView?.ready) return;
        proposalMessage("Forslaget svarer ikke", "Appen og innspillene er beholdt. Fortsett i Appen nå. Hvis problemet varer, åpne verkstedet på nytt fra samtalen. Uferdig tekst følger ikke med til en ny visning.", true);
      }, 15000);
    } catch {
      if (!retired && request === proposalRequest) proposalMessage("Forslaget kunne ikke åpnes", "Appen og innspillene dine er beholdt. Fortsett i Appen nå, eller be i samtalen om å åpne forslaget igjen.", true);
    } finally { proposalBusy = false; }
  }
  window.addEventListener("message", event => {
    const data = event.data;
    if (retired || !proposalView || event.source !== $("proposal-preview").contentWindow || event.origin !== proposalView.origin
      || !object(data) || data.channel !== "design-workshop-embed" || data.version !== 1 || data.leaseId !== proposalView.leaseId) return;
    if (data.event === "ready" && exact(data, ["channel", "version", "event", "leaseId"])) {
      $("proposal-preview").contentWindow?.postMessage({ channel: "design-workshop-embed", version: 1, command: "activate", leaseId: proposalView.leaseId, activationKey: proposalView.activationKey }, proposalView.origin);
    } else if (data.event === "activated" && exact(data, ["channel", "version", "event", "leaseId", "screen"]) && validScreen(data.screen)) {
      proposalView.renderedScreen = data.screen; proposalReady();
    }
  });
  function markConnection(ok) {
    if (retired) return;
    $("connection-dot").className = `connection-dot ${ok ? "connected" : "failed"}`;
    $("app-status").textContent = ok ? "Innspill koblet til samtalen" : "Forbindelsen må sjekkes";
  }
  function safeError(error, fallback) {
    if (error?.code === "renderer-stale" || retired) return "Verkstedet er lukket. Be om å åpne det igjen i samtalen. Lagrede rom beholdes. Kopier eventuell ulagret tekst før du fortsetter.";
    if (error?.status === 409) return "Arbeidet har endret seg. Utkastet ditt er beholdt. Hent siste tilstand før du prøver igjen.";
    if (error?.status === 429 || error?.status === 413) return "Arbeidet har nådd en grense. Utkastet ditt er beholdt. Be i samtalen om hjelp til å fortsette.";
    return fallback;
  }
  function retireRenderer() {
    if (retired) return;
    retired = true; ready = false; frameReady = false; routeReady = false;
    clearTimeout(pollTimer); clearTimeout(previewTimer); clearTimeout(locationTimer); clearTimeout(proposalTimer);
    proposalRequest += 1;
    // Keep the already mounted sketch available for copying unfinished text.
    // The backend revokes its writer; removing the frame would erase its draft.
    pendingPreviewReport = null; stateRequest += 1; selectionRequest += 1;
    const retained = [];
    if ($("comment-text").value.trim()) retained.push("Uferdig innspill:\n" + $("comment-text").value);
    if (editingComment?.text?.trim()) retained.push("Uferdig redigering:\n" + editingComment.text);
    $("local-draft-copy").value = retained.join("\n\n");
    closePanel(false);
    $("show-local-draft").hidden = retained.length === 0;
    $("retired-message").hidden = false;
    $("global-message").hidden = true; $("navigation-message").hidden = true;
    $("connection-dot").className = "connection-dot failed";
    $("app-status").textContent = "Denne visningen er ikke aktiv";
    frame.removeAttribute("src");
    $("stage-message").hidden = false; $("retry-preview").hidden = true;
    $("stage-title").textContent = "Verkstedet er lukket";
    $("stage-help").textContent = "Be om å åpne verkstedet igjen i samtalen. Kopier eventuell ulagret tekst først.";
    document.body.classList.add("renderer-retired");
    updateControls();
    $("retired-title").focus();
    announce("Denne visningen er ikke aktiv. Lagrede innspill er beholdt. Eventuell ulagret tekst kan fortsatt kopieres her.");
  }
  async function api(path, { body, mutation } = {}) {
    if (retired) throw Object.assign(new Error("View is inactive."), { status: 410, code: "renderer-stale" });
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(path, {
        method: body === undefined ? "GET" : "POST",
        credentials: "same-origin", cache: "no-store", redirect: "error", signal: controller.signal,
        headers: { "X-Designverksted-Token": config.token, ...(body === undefined ? {} : { "Content-Type": "application/json" }), ...(mutation ? { "X-Feedback-Mutation": mutation } : {}) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      if (!response.ok) {
        const value = await response.json().catch(() => ({}));
        const code = value.code === "renderer-stale" ? value.code : undefined;
        if (code) retireRenderer();
        throw Object.assign(new Error("Request failed."), { status: response.status, code });
      }
      return await response.json();
    } finally { clearTimeout(timer); }
  }
  function adoptState(value) {
    if (retired) return state;
    const next = value?.state || value;
    if (!object(next) || !Number.isSafeInteger(next.revision) || next.revision < 0 || !Array.isArray(next.comments)
      || !Number.isSafeInteger(next.submission) || next.submission < 0) throw new Error("Invalid control state.");
    if (state && next.revision < state.revision) return state;
    const wasReady = ready;
    const previousRounds = new Map((state?.canvas?.rounds || []).map(round => [round.submission, round]));
    state = next;
    const checkpoint = state.application?.checkpoint;
    if (/^[a-f0-9]{64}$/.test(checkpoint || "")) {
      if (!frameCheckpoint) frameCheckpoint = checkpoint;
    }
    if (pendingDelete && state.revision > pendingDelete.baseline && !state.comments.some(comment => comment.id === pendingDelete.idOfComment)) {
      pendingDelete = null;
      errorAt("submit-error", "");
      announce("Innspillet er fjernet.");
    }
    if (pendingSubmit && pendingSubmit.commentIds.length && pendingSubmit.commentIds.every(id =>
      state.comments.some(comment => comment.id === id && comment.lastSubmission === pendingSubmit.expectedSubmission))) {
      const submission = pendingSubmit.expectedSubmission;
      pendingSubmit = null;
      errorAt("submit-error", "");
      confirmSubmission(submission);
    }
    const name = plain(state.application?.name, 200) && state.application.name ? state.application.name : config.title || "Lokal app";
    $("app-title").textContent = name;
    frame.title = name;
    document.title = `${name} – Designverksted`;
    if (!ready && safeRoute(state.application?.route)) setRoute(state.application.route);
    ready = true;
    $("reopened-note").hidden = !state.workspace?.recovered;
    $("storage-note").textContent = state.workspace?.storage === "project"
      ? "Lagrede innspill beholdes i prosjektet. Utkast lagres først når du velger Lagre innspill."
      : "Midlertidig økt · innspillene er ikke lagret i prosjektet.";
    markConnection(true);
    if (pollError || !wasReady) globalError("");
    pollError = false;
    renderPreviewStatus(state.application?.transportStatus);
    if (wasReady) {
      const changedRound = (state.canvas?.rounds || []).filter(round => {
        const before = previousRounds.get(round.submission);
        return before && before.review !== round.review && ["working", "answered"].includes(round.review);
      }).at(-1);
      if (changedRound) announce(changedRound.review === "answered"
        ? `Runde ${changedRound.submission} har fått svar. Åpne Sendt i Innspill for å lese det.`
        : `Runde ${changedRound.submission} arbeides med.`);
    }
    renderProposals();
    renderFeedback();
    updateControls();
    return state;
  }
  async function refreshState() {
    const request = ++stateRequest;
    const value = await api("/state");
    if (request === stateRequest) return adoptState(value);
    return state;
  }
  async function settle(operation) {
    const result = await api(operation.path, { body: operation.body, mutation: operation.id });
    const value = result?.state || result;
    if (object(value) && Array.isArray(value.comments) && Number.isSafeInteger(value.revision)) adoptState(value);
    else await refreshState();
    return result;
  }
  function checkPreview(timeout) {
    clearLocation();
    clearTimeout(previewTimer);
    frameReady = false;
    routeReady = false;
    previewMissing = false;
    routeSeen = null;
    selectionRequest += 1;
    previewRequest = mutationId();
    const request = previewRequest;
    renderPreviewStatus({ state: "loading" });
    updateControls();
    previewTimer = setTimeout(() => {
      if (retired || request !== previewRequest || frameReady) return;
      previewMissing = true;
      renderPreviewStatus({ state: "unavailable" });
      updateControls();
    }, timeout);
    frame.contentWindow?.postMessage({ type: "check-view", epoch: config.epoch, view: request }, config.previewOrigin);
  }
  function attachPreview() {
    const currentFrame = frame;
    currentFrame.addEventListener("load", () => {
      if (retired || currentFrame !== frame) return;
      // The WindowProxy survives navigation. Only this document's reply may
      // confirm readiness or provide new route/selection evidence.
      checkPreview(5000);
      void refreshState().catch(() => {});
    });
  }
  function openPreview() {
    // Re-enter through the private bootstrap so retry also restores a lost
    // preview cookie. No app-provided route is used as a recovery address.
    const replacement = frame.cloneNode(false);
    replacement.removeAttribute("src");
    frame.replaceWith(replacement);
    frame = replacement;
    attachPreview();
    checkPreview(20000);
    frame.src = config.previewUrl;
  }
  function postMode() {
    if (retired || !config.previewOrigin) return;
    frame.contentWindow?.postMessage({ type: "set-mode", epoch: config.epoch, mode }, config.previewOrigin);
  }
  function setRoute(route) {
    latestRoute = route;
    $("app-route").textContent = routeLabel(route);
    $("app-route").title = routeLabel(route);
    renderSelectionNotice();
  }
  function registerView(route, capture = false) {
    // Route observations are volatile. Only a deliberate save persists context.
    // Keep the room identity captured by this request across retries.
    const requestedCheckpoint = frameCheckpoint;
    const documentRequest = previewRequest;
    const operation = async () => {
      if (documentRequest !== previewRequest) throw new Error("The app view changed.");
      if (!state) await refreshState();
      if (documentRequest !== previewRequest) throw new Error("The app view changed.");
      const expectedCheckpoint = requestedCheckpoint || frameCheckpoint;
      if (!/^[a-f0-9]{64}$/.test(expectedCheckpoint || "")) throw new Error("The room identity is unavailable.");
      // Capture this request's room identity. A conflict must never retarget it.
      const result = await api("/view", { body: { route, expectedCheckpoint, ...(capture ? { capture: true } : {}) } });
      if (documentRequest !== previewRequest) throw new Error("The app view changed.");
      const value = result?.state || result;
      if (Array.isArray(value?.comments)) adoptState(value);
      const screen = getScreen(value);
      if (!validScreen(screen)) throw new Error("The view did not return a screen identity.");
      if (route === routeSeen) {
        setRoute(value.application.route);
        routeReady = true;
        updateControls();
      }
      return { screen, checkpoint: expectedCheckpoint, route: value.application.route };
    };
    const result = viewQueue.catch(() => {}).then(operation);
    viewQueue = result;
    return result;
  }
  function validContext(value) {
    return exact(value, ["route", "target", "viewport"]) && safeRoute(value.route)
      && exact(value.target, ["tag", "role", "name", "text", "path"])
      && plain(value.target.tag, 64) && /^[a-z][a-z0-9-]*$/.test(value.target.tag)
      && plain(value.target.role, 64) && plain(value.target.name, 240) && bytes(value.target.name) <= 240
      && plain(value.target.text, 1000) && bytes(value.target.text) <= 1000 && plain(value.target.path, 512)
      && exact(value.viewport, ["width", "height", "scrollX", "scrollY"])
      && finite(value.viewport.width, 1, 20000) && finite(value.viewport.height, 1, 20000)
      && finite(value.viewport.scrollX, 0, 1000000) && finite(value.viewport.scrollY, 0, 1000000);
  }
  function validAnchor(value) {
    return exact(value, ["path", "role", "rect", "viewport"]) && plain(value.path, 512)
      && /^[a-z][a-z0-9-]*:nth-of-type\([1-9][0-9]{0,5}\)(?: > [a-z][a-z0-9-]*:nth-of-type\([1-9][0-9]{0,5}\))*$/.test(value.path)
      && plain(value.role, 64) && exact(value.rect, ["x", "y", "width", "height"])
      && finite(value.rect.x, 0, 1000000) && finite(value.rect.y, 0, 1000000)
      && finite(value.rect.width, 0, 100000) && finite(value.rect.height, 0, 100000)
      && exact(value.viewport, ["width", "height"]) && finite(value.viewport.width, 1, 20000) && finite(value.viewport.height, 1, 20000);
  }
  async function chooseTarget(context, anchor, label) {
    if (mode !== "comment" || busy || pendingSave || !frameReady || !routeReady || ![routeSeen, latestRoute].includes(context.route)) return;
    const request = ++selectionRequest;
    try {
      const view = await registerView(context.route, true);
      if (request !== selectionRequest || mode !== "comment") return;
      const chosen = { context: { ...JSON.parse(JSON.stringify(context)), route: view.route }, anchor: JSON.parse(JSON.stringify(anchor)), screen: view.screen, checkpoint: view.checkpoint, label: plain(label, 200) && label.trim() ? label : context.target.name || context.target.tag };
      if (hasDraft() && selection) {
        replacement = chosen;
        openPanel("compose", $("mode-change"), false);
        $("draft-change").hidden = false;
        $("keep-draft").focus();
        announce("Du har et uferdig innspill. Velg om du vil fortsette eller bytte del.");
      } else useTarget(chosen);
    } catch (error) {
      if (request !== selectionRequest) return;
      globalError(safeError(error, "Delen kunne ikke knyttes til arbeidet. Innspillet ditt er beholdt. Prøv å velge delen igjen."));
    }
  }
  function useTarget(chosen) {
    selection = chosen;
    replacement = null;
    $("draft-change").hidden = true;
    $("comment-text").value = "";
    errorAt("comment-error", "");
    renderSelection();
    openPanel("compose", $("mode-change"), false);
    $("comment-text").focus();
    announce(`Valgt: ${selection.label}. Skriv innspillet ditt.`);
  }
  function renderSelectionNotice() {
    $("selection-stale").hidden = !selection || selection.context.route === latestRoute;
  }
  function renderSelection() {
    $("selection-empty").hidden = Boolean(selection);
    $("comment-form").hidden = !selection;
    if (selection) {
      $("target-label").textContent = selection.label;
      $("target-route").textContent = routeLabel(selection.context.route);
      renderSelectionNotice();
    }
    updateControls();
  }
  function setMode(value, { showPanel = true, keepPanel = false, announceChange = true } = {}) {
    clearLocation();
    mode = value;
    ++selectionRequest;
    $("mode-browse").setAttribute("aria-pressed", String(mode === "browse"));
    $("mode-change").setAttribute("aria-pressed", String(mode === "comment"));
    $("preview-label").textContent = mode === "browse" ? "Prøv appen som vanlig" : "Velg det du vil endre";
    postMode();
    if (mode === "comment" && showPanel) openPanel("compose", $("mode-change"));
    else if (mode === "browse" && !keepPanel && (activePanel === "compose" || narrowLayout.matches)) closePanel(false);
    if (announceChange) announce(mode === "browse" ? "Prøv. Appen kan brukes som vanlig." : "Endre. Velg et element for å gi innspill.");
    updateControls();
  }
  function openPanel(name, source, focus = true) {
    if (name !== "feedback") clearLocation();
    activePanel = name;
    opener = source || opener;
    $("side-panel").hidden = false;
    $("workspace").classList.add("has-panel");
    $("compose-pane").hidden = name !== "compose";
    $("feedback-pane").hidden = name !== "feedback";
    $("panel-title").textContent = name === "compose" ? "Nytt innspill" : "Innspill";
    $("open-feedback").setAttribute("aria-expanded", String(name === "feedback"));
    syncPanelAccess();
    if (focus) $("panel-title").focus();
    updateControls();
  }
  function closePanel(focus = true) {
    clearLocation();
    activePanel = null;
    $("side-panel").hidden = true;
    $("workspace").classList.remove("has-panel");
    $("open-feedback").setAttribute("aria-expanded", "false");
    syncPanelAccess();
    if (focus) (opener?.getClientRects().length ? opener : $("mode-browse")).focus();
    updateControls();
  }
  function pickPart() {
    if (busy || pendingSave || previewState === "unavailable") return;
    setMode("comment", { showPanel: false });
    closePanel(false);
    frame.focus();
    frame.contentWindow?.postMessage({ type: "focus-picker", epoch: config.epoch }, config.previewOrigin);
    announce("Velg en del i appens liste, eller pek på delen. Escape går tilbake til Prøv.");
  }
  function setTab(tab, focus = false) {
    clearLocation();
    activeTab = tab;
    for (const name of ["pending", "sent"]) {
      const node = $(`${name}-tab`);
      node.setAttribute("aria-selected", String(name === tab));
      node.tabIndex = name === tab ? 0 : -1;
    }
    $("feedback-list").setAttribute("aria-labelledby", `${tab}-tab`);
    $("basket-footer").hidden = tab !== "pending";
    renderFeedback(true);
    if (focus) $(`${tab}-tab`).focus();
  }
  const locationMessages = {
    checking: "Finner stedet på siden som er åpen …",
    shown: "Stedet er markert i appen. Innspill og uferdig tekst er beholdt.",
    page: "Innspillet gjelder hele siden som er åpen, ikke en bestemt del.",
    "different-route": "Innspillet gjelder en annen side. Åpne siden i appen selv, og velg Vis stedet igjen.",
    ambiguous: "Flere deler kan ligne på dette stedet. Ingenting er markert, så du ikke vises feil del.",
    unavailable: "Stedet kan ikke gjenfinnes sikkert i denne visningen. Det kan være endret, skjult eller fjernet. Ingenting er markert.",
    waiting: "Vent til siden er klar, og prøv igjen. Innspillet er beholdt.",
    timeout: "Appvisningen svarte ikke. Innspillet er beholdt. Prøv Vis stedet igjen når siden er klar.",
  };
  function renderLocations() {
    for (const card of $("feedback-list").querySelectorAll("[data-comment]")) {
      const button = card.querySelector(".show-location"), note = card.querySelector(".location-notice");
      if (!button || !note) continue;
      const current = locationNotice?.id === card.dataset.comment ? locationNotice.status : null;
      note.textContent = current ? locationMessages[current] : "";
      note.hidden = !current;
      button.setAttribute("aria-busy", String(current === "checking"));
    }
    const wasPeeking = locationPeeking;
    locationPeeking = activePanel === "feedback" && narrowLayout.matches && locationNotice?.status === "shown";
    locationReturnBar.hidden = !locationPeeking;
    document.body.classList.toggle("showing-location", locationPeeking);
    $("open-feedback").setAttribute("aria-expanded", String(activePanel === "feedback" && !locationPeeking));
    $("side-panel").hidden = !activePanel || locationPeeking;
    syncPanelAccess();
    if (locationPeeking && !wasPeeking) locationReturnButton.focus();
  }
  function returnToFeedback() {
    const id = locationNotice?.id;
    clearLocation();
    focusComment(id, "location");
  }
  function clearLocation() {
    clearTimeout(locationTimer); locationTimer = null; locationRequest = null; locationNotice = null;
    if (previewRequest) frame.contentWindow?.postMessage({ type: "clear-location", epoch: config.epoch, view: previewRequest }, config.previewOrigin);
    renderLocations();
  }
  function locationStatus(id, status) {
    locationNotice = { id, status }; renderLocations();
    announce(locationMessages[status]);
  }
  function showLocation(id) {
    clearLocation();
    const context = state?.comments?.find(comment => comment.id === id)?.applicationContext;
    if (!validContext(context)) { locationStatus(id, "unavailable"); return; }
    if (!frameReady || !routeReady || previewMissing || !ready) { locationStatus(id, "waiting"); return; }
    if (context.route !== latestRoute || context.route !== routeSeen) { locationStatus(id, "different-route"); return; }
    const request = mutationId();
    locationRequest = { id, request, view: previewRequest, route: latestRoute };
    locationStatus(id, "checking");
    locationTimer = setTimeout(() => {
      if (locationRequest?.request !== request) return;
      clearLocation(); locationStatus(id, "timeout");
    }, 2500);
    frame.contentWindow?.postMessage({ type: "show-location", epoch: config.epoch, view: previewRequest, request, context }, config.previewOrigin);
  }
  function renderComment(comment, sent, replyText = comment.reply) {
    const card = message("article", "", "feedback-card");
    card.dataset.comment = comment.id;
    const context = comment.applicationContext;
    const heading = message("div", "", "feedback-card-heading");
    const title = message("h3", context?.target?.name || context?.target?.tag || "Innspill til appen");
    title.tabIndex = -1;
    heading.append(title);
    if (sent && comment.status === "fixed") heading.append(message("span", "Fulgt opp", "status-badge"));
    card.append(heading);
    if (safeRoute(context?.route)) card.append(message("p", routeLabel(context.route), "route"));
    card.append(message("p", typeof comment.text === "string" ? comment.text : "", "feedback-text"));
    if (replyText) {
      const reply = message("div", "", "feedback-reply");
      appendReply(reply, replyText, `comment-${comment.id}`);
      card.append(reply);
    }
    const show = message("button", "Vis stedet", "button secondary show-location");
    show.type = "button"; show.dataset.focusKey = "location";
    show.setAttribute("aria-label", `Vis stedet for innspillet om ${context?.target?.name || "appen"}`);
    const notice = message("p", "", "location-notice"); notice.id = `location-${comment.id}`; notice.hidden = true;
    show.setAttribute("aria-describedby", notice.id);
    show.addEventListener("click", () => showLocation(comment.id));
    card.append(show, notice);
    if (!sent && comment.lastSubmission === 0) {
      if (editingComment?.id === comment.id) {
        card.append(renderEdit(comment));
        return card;
      }
      const edit = message("button", "Rediger innspill", "button quiet edit-comment");
      edit.type = "button"; edit.dataset.focusKey = "edit";
      edit.disabled = busy || Boolean(pendingSave || pendingSubmit || pendingDelete || editingComment);
      edit.setAttribute("aria-label", `Rediger innspill om ${context?.target?.name || "appen"}`);
      edit.addEventListener("click", () => {
        editingComment = { id: comment.id, context: comment.applicationContext, unavailable: false, text: comment.text, originalText: comment.text, expectedRevision: state.revision, conflict: false };
        editError = ""; updateControls(); renderFeedback(true);
        $("feedback-list").querySelector(".edit-text")?.focus();
      });
      card.append(edit);
      const remove = message("button", pendingDelete?.idOfComment === comment.id ? "Prøv samme fjerning igjen" : "Fjern innspill", "button quiet remove-comment");
      remove.type = "button"; remove.dataset.focusKey = "remove";
      remove.disabled = busy || Boolean(pendingSave || pendingSubmit || editingComment) || Boolean(pendingDelete && pendingDelete.idOfComment !== comment.id);
      remove.setAttribute("aria-label", `Fjern innspill om ${context?.target?.name || "appen"}`);
      remove.addEventListener("click", () => void deleteComment(comment.id));
      card.append(remove);
    }
    return card;
  }
  function renderEdit(comment) {
    const form = message("form", "", "edit-form");
    const inputId = `edit-${comment.id}`;
    const label = message("label", "Rediger innspillet", "field-label"); label.htmlFor = inputId;
    const input = message("textarea", "", "edit-text"); input.id = inputId; input.rows = 4;
    input.value = editingComment.text; input.dataset.focusKey = "text";
    input.readOnly = busy || Boolean(pendingEdit);
    const help = message("p", "Målet og siden beholdes. Endringen sendes først når du sender innspillene.", "quiet-help"); help.id = `${inputId}-help`;
    input.setAttribute("aria-describedby", `${inputId}-help ${inputId}-error`);
    const error = message("p", editError, "error-message"); error.id = `${inputId}-error`; error.setAttribute("role", "alert"); error.hidden = !editError;
    const actions = message("div", "", "button-row");
    const save = message("button", busy && pendingEdit ? "Lagrer …" : pendingEdit ? "Prøv samme lagring igjen" : "Lagre innspill", "button primary");
    save.type = "submit"; save.dataset.focusKey = "save";
    const valid = () => Boolean(editingComment.text.trim()) && bytes(editingComment.text) <= MAX_TEXT_BYTES;
    save.disabled = busy || editingComment.unavailable || editingComment.conflict || (!pendingEdit && !valid());
    input.setAttribute("aria-invalid", String(bytes(editingComment.text) > MAX_TEXT_BYTES));
    input.addEventListener("input", () => {
      editingComment.text = input.value;
      save.disabled = busy || editingComment.unavailable || editingComment.conflict || !valid();
      const tooLong = bytes(input.value) > MAX_TEXT_BYTES;
      input.setAttribute("aria-invalid", String(tooLong));
      help.textContent = tooLong ? "Teksten er for lang. Kort ned før du lagrer." : "Målet og siden beholdes. Endringen sendes først når du sender innspillene.";
    });
    const cancel = message("button", "Avbryt redigering", "button quiet"); cancel.type = "button"; cancel.dataset.focusKey = "cancel"; cancel.disabled = busy || Boolean(pendingEdit);
    cancel.addEventListener("click", () => { editingComment = null; editError = ""; updateControls(); focusComment(comment.id, "edit"); announce("Redigeringen er avbrutt. Det lagrede innspillet er beholdt."); });
    actions.append(save, cancel); form.append(label, input, help);
    if (editingComment.conflict && !editingComment.unavailable) {
      form.append(message("p", `Lagret tekst nå: ${comment.text}`, "notice"));
      const accept = message("button", "Behold min tekst på dette grunnlaget", "button secondary"); accept.type = "button"; accept.dataset.focusKey = "baseline";
      accept.disabled = busy;
      accept.addEventListener("click", () => { editingComment.originalText = comment.text; editingComment.expectedRevision = state.revision; editingComment.conflict = false; editError = ""; updateControls(); focusComment(comment.id, "text"); });
      form.append(accept);
    }
    form.append(error, actions);
    form.addEventListener("submit", event => { event.preventDefault(); if (!save.disabled) void saveEdit(); });
    return form;
  }
  async function saveEdit() {
    if (busy || !editingComment) return;
    const commentId = editingComment.id;
    if (!pendingEdit) pendingEdit = { id: mutationId(), path: `/comments/${editingComment.id}/edit`, body: { text: editingComment.text.trim(), expectedRevision: editingComment.expectedRevision } };
    busy = true; editError = ""; updateControls();
    try {
      await settle(pendingEdit);
      pendingEdit = null; editingComment = null;
      announce("Innspillet er oppdatert. Ingen bestilling er sendt.");
    } catch (error) {
      if ([400, 404, 409, 413, 422, 429].includes(error.status)) pendingEdit = null;
      if (error.status === 409) {
        await refreshState().catch(() => {});
        const latest = state.comments.find(comment => comment.id === editingComment.id);
        if (latest && latest.submission === 0 && latest.lastSubmission === 0) {
          editingComment.conflict = latest.text !== editingComment.originalText;
          if (!editingComment.conflict) editingComment.expectedRevision = state.revision;
          editError = editingComment.conflict ? "Innspillet har fått en nyere tekst. Din tekst er beholdt. Les den lagrede teksten før du velger grunnlag." : "Arbeidet ble oppdatert. Teksten din er beholdt. Prøv å lagre igjen.";
        } else editError = "Innspillet kan ikke lenger redigeres. Din tekst er beholdt; kopier den før du avbryter.";
      } else editError = safeError(error, "Lagringen er ikke bekreftet. Teksten er beholdt. Prøv samme lagring igjen.");
    } finally {
      const restoreFocus = feedbackOwnsFocus(commentId);
      busy = false; updateControls();
      if (restoreFocus) focusComment(commentId, pendingEdit ? "save" : editingComment ? "text" : "edit");
    }
  }
  const replyIdentity = value => typeof value === "string" ? value.trim().replace(/\s+/gu, " ") : "";
  function appendReply(parent, text, key) {
    if (typeof text !== "string" || !text.trim()) return;
    // Existing replies remain available in full. New concise summaries should
    // be authored as such, never manufactured by clipping a longer answer.
    if (Array.from(text).length <= 320) parent.append(message("p", text));
    else {
      const detail = message("details", "", "reply-details"); detail.dataset.replyKey = key;
      detail.append(message("summary", "Les hele svaret"), message("p", text));
      parent.append(detail);
    }
  }
  function confirmSubmission(submission) {
    if (!submissionNotice || submissionNotice.submission !== submission || submissionNotice.registered) return;
    submissionNotice.phase = "registered"; submissionNotice.registered = true;
    if (mode === "comment" && !hasDraft() && !editingComment && !pendingEdit && !pendingSave && !pendingDelete) {
      setMode("browse", { showPanel: false, keepPanel: true, announceChange: false });
    }
  }
  function renderReviewProgress() {
    const rounds = (state?.canvas?.rounds || []).filter(round => !round.previousSession);
    const round = submissionNotice ? rounds.find(item => item.submission === submissionNotice.submission)
      : [...rounds].sort((left, right) => right.submission - left.submission)[0];
    const proposal = round && proposalList().find(item => item.available && item.sourceSubmission === round.submission);
    const showProposal = proposal && activeTab !== "sent";
    let phase = "", title = "", help = "";
    if (showProposal) {
      phase = "proposal"; title = "Forslaget er klart"; help = "Prøv skissen og gi flere innspill i samme verksted.";
    } else if (round?.review === "answered") {
      if (activeTab !== "sent") { phase = "answered"; title = "Svar klart"; help = "Åpne Sendt for å lese svaret."; }
    } else if (round?.review === "working") {
      phase = "working"; title = "Arbeider med innspillene …"; help = "Du kan prøve appen mens du venter.";
    } else if (round?.delivery === "queued") {
      phase = "queued"; title = "Sendt – venter på svar"; help = "Du kan prøve appen mens du venter.";
    } else if (round?.delivery === "unknown") {
      phase = "unknown"; title = "Mottaket er ikke bekreftet"; help = "Innspillene er beholdt. Se Sendt for neste steg.";
    } else if (round) {
      phase = "registered"; title = "Innspillene er lagret"; help = "Bekrefter sending til samtalen …";
    } else if (submissionNotice?.phase === "sending") {
      phase = "sending"; title = "Sender innspill …"; help = "Venter på bekreftelse. Innspillene dine er beholdt.";
    } else if (submissionNotice?.phase === "uncertain") {
      phase = "unknown"; title = "Sendingen er ikke bekreftet"; help = "Prøv samme sending igjen. Innspillene dine er beholdt.";
    }
    if (phase && hasDraft()) help += " Uferdig tekst er ikke sendt.";
    const signature = JSON.stringify([phase, title, help, showProposal ? proposal.id : null]);
    if (signature === progressSignature) return;
    progressSignature = signature;
    $("review-progress").hidden = !phase;
    $("review-progress").dataset.phase = phase;
    $("review-progress-title").textContent = title;
    $("review-progress-help").textContent = help;
    $("review-progress-proposal").hidden = !showProposal;
    $("review-progress-proposal").dataset.proposal = showProposal ? proposal.id : "";
  }
  function renderFeedback(force = false) {
    renderReviewProgress();
    const pending = pendingComments();
    const sent = sentComments();
    $("feedback-count").textContent = String(pending.length);
    $("pending-count").textContent = String(pending.length);
    $("sent-count").textContent = String(sent.length);
    const signature = JSON.stringify([state?.revision, proposalSignature, activeTab, busy, pendingDelete?.idOfComment, editingComment?.id, editingComment?.conflict, pendingEdit?.id, editError]);
    if (!force && lastListSignature === signature) return;
    lastListSignature = signature;
    const list = $("feedback-list");
    const expandedReplies = new Set([...list.querySelectorAll("details[open][data-reply-key]")].map(node => node.dataset.replyKey));
    const focused = document.activeElement;
    const focusedReply = focused?.closest?.("details[data-reply-key]")?.dataset.replyKey;
    const focusedId = focused?.closest?.("[data-comment]")?.dataset.comment;
    const focusKey = focused?.dataset?.focusKey;
    const selectionRange = focused?.tagName === "TEXTAREA" ? [focused.selectionStart, focused.selectionEnd] : null;
    const content = document.createDocumentFragment();
    const comments = activeTab === "pending" ? pending : sent;
    const orphanedEdit = activeTab === "pending" && editingComment && !pending.some(comment => comment.id === editingComment.id && comment.lastSubmission === 0);
    if (orphanedEdit) {
      editingComment.unavailable = true;
      const preserved = message("article", "", "feedback-card"); preserved.dataset.comment = editingComment.id;
      preserved.append(message("h3", "Uferdig redigering"), message("p", "Det opprinnelige innspillet er sendt eller fjernet. Teksten din er beholdt her og kan kopieres før du avbryter.", "notice"), renderEdit({ id: editingComment.id }));
      content.append(preserved);
    }
    if (!comments.length && !orphanedEdit) {
      const empty = message("div", "", "empty-feedback");
      empty.append(message("h3", activeTab === "pending" ? "Ingen innspill klare ennå" : "Ingen innspill er sendt"), message("p", activeTab === "pending" ? "Velg Endre, pek på noe i appen og beskriv ønsket ditt. Send når du er klar." : "Etter sending finner du innspillene og svarene her."));
      content.append(empty);
    } else if (activeTab === "pending") pending.forEach(comment => content.append(renderComment(comment, false)));
    else {
      const rounds = new Map((state?.canvas?.rounds || []).map(round => [round.submission, round]));
      const numbers = [...new Set(sent.map(comment => comment.submission))].sort((a, b) => b - a);
      for (const number of numbers) {
        const round = rounds.get(number);
        const title = message("div", "", "round-heading");
        const label = round?.review === "answered" ? "Svar klart" : round?.review === "working" ? "Arbeider med innspillene" : round?.delivery === "unknown" ? "Mottak ikke bekreftet" : round?.delivery === "queued" ? "Venter på svar" : "Bekrefter sending";
        title.append(message("h3", `Runde ${number}`), message("span", label, `status-badge ${round?.review === "answered" ? "answered" : ""}`));
        content.append(title);
        if (round?.previousSession) content.append(message("p", "Fra tidligere samtale. Sendes ikke på nytt.", "round-note"));
        if (round?.delivery === "unknown" && round?.review === "unread") content.append(message("p", `Mottaket er ikke bekreftet. Skriv «se runde ${number}» i samtalen. Ikke send samme runde på nytt.`, "notice"));
        const seenReplies = new Set();
        if (round?.reply) {
          const reply = message("div", "", "round-reply");
          appendReply(reply, round.reply, `round-${number}`); content.append(reply);
          seenReplies.add(replyIdentity(round.reply));
        }
        const proposal = proposalList().find(item => item.sourceSubmission === number);
        if (proposal?.available) {
          const showProposal = message("button", "Vis forslag", "button primary show-proposal");
          showProposal.type = "button"; showProposal.dataset.proposal = proposal.id;
          showProposal.addEventListener("click", () => { void openProposal(proposal.id); $("proposal-tab").focus(); });
          content.append(showProposal);
        }
        for (const comment of sent.filter(item => item.submission === number)) {
          const identity = replyIdentity(comment.reply);
          content.append(renderComment(comment, true, identity && !seenReplies.has(identity) ? comment.reply : ""));
          if (identity) seenReplies.add(identity);
        }
      }
    }
    list.replaceChildren(content);
    for (const detail of list.querySelectorAll("details[data-reply-key]")) detail.open = expandedReplies.has(detail.dataset.replyKey);
    renderLocations();
    if (retired) updateControls();
    if (focusedReply) {
      const detail = [...list.querySelectorAll("details[data-reply-key]")].find(node => node.dataset.replyKey === focusedReply);
      focusAvailable(detail?.querySelector("summary"), $(`${activeTab}-tab`));
    } else if (focusedId) {
      const sameCard = [...list.querySelectorAll("[data-comment]")].find(card => card.dataset.comment === focusedId);
      const target = focusAvailable(
        focusKey && [...(sameCard?.querySelectorAll("[data-focus-key]") || [])].find(node => node.dataset.focusKey === focusKey),
        sameCard?.querySelector("h3"), ...[...(sameCard?.querySelectorAll("button") || [])], $(`${activeTab}-tab`), list);
      if (selectionRange && target?.tagName === "TEXTAREA") target.setSelectionRange(...selectionRange);
    }
  }
  function updateControls() {
    if (retired) {
      for (const id of ["mode-browse", "mode-change", "pick-part", "whole-page", "save-comment", "submit-feedback", "clear-draft", "keep-draft", "discard-for-target", "retry-state", "retry-preview"]) $(id).disabled = true;
      for (const button of document.querySelectorAll(".edit-comment,.remove-comment,.edit-form button,.show-location")) button.disabled = true;
      for (const textarea of document.querySelectorAll("textarea")) textarea.readOnly = true;
      return;
    }
    $("mode-browse").disabled = config.activationRequired === true;
    $("mode-change").disabled = config.activationRequired === true;
    const text = $("comment-text").value;
    const count = bytes(text);
    $("comment-limit").textContent = count > MAX_TEXT_BYTES ? "Teksten er for lang" : `${Array.from(text).length} tegn`;
    $("comment-help").textContent = count > MAX_TEXT_BYTES ? "Kort ned teksten for å legge den til i Innspill." : "Beskriv ønsket. Samle flere innspill før du sender.";
    $("comment-text").setAttribute("aria-invalid", String(count > MAX_TEXT_BYTES));
    $("comment-text").readOnly = busy || Boolean(pendingSave);
    $("save-comment").disabled = busy || !ready || !selection || (!pendingSave && (!text.trim() || count > MAX_TEXT_BYTES)) || Boolean(pendingSubmit || pendingDelete);
    $("save-comment").textContent = busy && pendingSave ? "Lagrer …" : pendingSave ? "Prøv samme lagring igjen" : "Lagre innspill";
    $("clear-draft").disabled = busy || Boolean(pendingSave);
    $("comment-retry-note").hidden = !pendingSave || busy;
    $("whole-page").disabled = busy || !ready || !frameReady || !routeReady || Boolean(pendingSave) || previewState === "unavailable";
    $("pick-part").disabled = busy || !ready || !frameReady || !routeReady || Boolean(pendingSave) || previewState === "unavailable";
    $("resume-draft").hidden = !hasDraft() || activePanel === "compose";
    const unknown = (state?.canvas?.rounds || []).find(round => round.delivery === "unknown" && round.review === "unread");
    const blocked = !ready || !pendingComments().length || busy || Boolean(pendingSave || pendingDelete || editingComment || unknown);
    $("submit-feedback").disabled = blocked;
    $("submit-feedback").textContent = busy && pendingSubmit ? "Sender …" : pendingSubmit ? "Prøv samme sending igjen" : pendingComments().length ? `Send ${pendingComments().length} innspill` : "Send innspill";
    $("submit-help").textContent = editingComment ? "Lagre eller avbryt redigeringen før du sender innspillene." : unknown ? `Avklar mottaket av runde ${unknown.submission} i samtalen før du sender mer.`
      : pendingSave || pendingDelete ? "Bekreft den uavklarte lagringen eller fjerningen før du sender."
        : !ready ? "Venter på forbindelsen til arbeidet."
          : !pendingComments().length ? "Legg til et innspill i Endre før du sender."
            : busy && pendingSubmit ? "Innspillene beholdes mens vi venter på bekreftelse."
              : pendingSubmit ? "Sendingen er ikke bekreftet. Prøv samme sending igjen; innspillene bevares."
                : `${pendingComments().length} innspill sendes samlet til samtalen. ${hasDraft() ? "Uferdig tekst er ikke med." : "Du velger selv når."}`;
    $("keep-draft").disabled = busy;
    $("discard-for-target").disabled = busy || Boolean(pendingSave);
    $("retry-state").disabled = busy;
    renderFeedback();
  }
  async function saveComment(event) {
    event.preventDefault();
    if ($("save-comment").disabled || !selection) return;
    if (!pendingSave) pendingSave = {
      id: mutationId(), path: "/comments", body: {
        screen: selection.screen, kind: "point", anchor: selection.anchor,
        text: $("comment-text").value.trim(), applicationContext: selection.context,
      },
    };
    busy = true;
    errorAt("comment-error", "");
    updateControls();
    try {
      await settle(pendingSave);
      pendingSave = null;
      $("comment-text").value = "";
      selection = null;
      replacement = null;
      $("draft-change").hidden = true;
      renderSelection();
      setTab("pending");
      openPanel("feedback", $("open-feedback"));
      announce("Innspillet er lagret i Klar til sending. Ingen bestilling er sendt ennå.");
    } catch (error) {
      if ([400, 409, 413, 422, 429].includes(error.status)) pendingSave = null;
      errorAt("comment-error", safeError(error, "Lagringen ble ikke bekreftet. Teksten er beholdt. Prøv samme lagring igjen."));
    } finally {
      busy = false; updateControls();
      if (activePanel === "compose" && [document.body, $("save-comment"), $("comment-text"), $("panel-title")].includes(document.activeElement)) focusAvailable($("save-comment"), $("comment-text"));
    }
  }
  async function submitFeedback() {
    if ($("submit-feedback").disabled) return;
    if (!pendingSubmit) pendingSubmit = { id: mutationId(), path: "/submit", body: { revision: state.revision }, commentIds: pendingComments().map(comment => comment.id), expectedSubmission: state.submission + 1 };
    const operation = pendingSubmit;
    submissionNotice = { submission: operation.expectedSubmission, phase: "sending", registered: false };
    if (document.activeElement === $("submit-feedback")) $("pending-tab").focus();
    busy = true;
    errorAt("submit-error", "");
    updateControls();
    try {
      await settle(operation);
      pendingSubmit = null;
      confirmSubmission(operation.expectedSubmission);
      const ownsFocus = activePanel === "feedback" && [$("pending-tab"), $("submit-feedback"), $("feedback-list")].includes(document.activeElement);
      setTab("sent", ownsFocus);
    } catch (error) {
      submissionNotice.phase = "uncertain";
      if ([400, 409, 413, 422, 429].includes(error.status)) { pendingSubmit = null; submissionNotice = null; await refreshState().catch(() => {}); }
      errorAt("submit-error", safeError(error, "Sendingen ble ikke bekreftet. Prøv samme sending igjen. Innspillene dine er beholdt."));
    } finally {
      busy = false; updateControls();
      if (activePanel === "feedback" && activeTab === "pending" && [document.body, $("pending-tab"), $("submit-feedback")].includes(document.activeElement)) focusAvailable($("submit-feedback"), $("pending-tab"));
    }
  }
  async function deleteComment(id) {
    if (busy || pendingSave || pendingSubmit || (pendingDelete && pendingDelete.idOfComment !== id)) return;
    if (typeof id !== "string" || !/^[a-f0-9]{24}$/.test(id)) return;
    if (!pendingDelete) pendingDelete = { id: mutationId(), idOfComment: id, baseline: state.revision, path: `/comments/${id}/delete`, body: {} };
    busy = true;
    errorAt("submit-error", "");
    updateControls();
    try {
      await settle(pendingDelete);
      pendingDelete = null;
      announce("Innspillet er fjernet fra Klar til sending.");
    } catch (error) {
      if ([400, 404, 409, 422].includes(error.status)) pendingDelete = null;
      errorAt("submit-error", safeError(error, "Fjerningen ble ikke bekreftet. Prøv samme fjerning igjen."));
    } finally {
      const restoreFocus = feedbackOwnsFocus(id);
      busy = false; updateControls();
      if (restoreFocus) focusComment(state.comments.some(comment => comment.id === id) ? id : pendingComments()[0]?.id, pendingDelete ? "remove" : "edit");
    }
  }
  function wholePage() {
    if ($("whole-page").disabled) return;
    const viewport = { width: Math.max(1, frame.clientWidth), height: Math.max(1, frame.clientHeight) };
    const path = "html:nth-of-type(1) > body:nth-of-type(1)";
    void chooseTarget({ route: latestRoute, target: { tag: "body", role: "main", name: "Hele siden", text: "", path }, viewport: { ...viewport, scrollX: 0, scrollY: 0 } }, { path, role: "main", rect: { x: 0, y: 0, ...viewport }, viewport }, "Hele siden");
  }
  function setWidth(width, notify = true) {
    $("preview-viewport").dataset.width = width;
    for (const option of ["fit", "desktop", "mobile"]) $(`width-${option}`).setAttribute("aria-pressed", String(option === width));
    $("width-label").textContent = width === "mobile" ? "Mobil · 375 px" : width === "desktop" ? "Stor skjerm · 1280 px" : "Tilpasset bredde";
    if (notify) announce($("width-label").textContent);
  }
  window.addEventListener("message", event => {
    if (retired || event.source !== frame.contentWindow || event.origin !== config.previewOrigin || !object(event.data) || event.data.epoch !== config.epoch) return;
    const data = event.data;
    if (data.type === "design-view-available" && exact(data, ["type", "epoch", "view"]) && data.view === null && previewRequest) {
      // A late inspector can answer the current challenge. Availability alone
      // never confirms a document or extends its deadline.
      if (frameReady) checkPreview(20000);
      else frame.contentWindow?.postMessage({ type: "check-view", epoch: config.epoch, view: previewRequest }, config.previewOrigin);
      return;
    }
    if (data.view !== previewRequest) return;
    if (data.type === "design-view-ready" && exact(data, ["type", "epoch", "view"])) {
      frameReady = true;
      previewMissing = false;
      clearTimeout(previewTimer);
      renderPreviewStatus(state?.application?.transportStatus);
      updateControls();
      postMode();
      return;
    }
    if (!frameReady) return;
    if (data.type === "design-view-leaving" && exact(data, ["type", "epoch", "view"])) {
      checkPreview(20000);
      return;
    }
    if (data.type === "design-location-result") {
      if (!exact(data, ["type", "epoch", "view", "request", "status"]) || !locationRequest
        || data.request !== locationRequest.request || data.view !== locationRequest.view || !routeReady
        || locationRequest.route !== latestRoute || locationRequest.route !== routeSeen
        || !["shown", "page", "different-route", "ambiguous", "unavailable"].includes(data.status)) return;
      clearTimeout(locationTimer); locationTimer = null;
      const id = locationRequest.id;
      if (data.status !== "shown") locationRequest = null;
      locationStatus(id, data.status);
      return;
    }
    if (data.type === "design-exit" && exact(data, ["type", "epoch", "view"])) {
      setMode("browse", { showPanel: false });
      $("mode-browse").focus();
    } else if (data.type === "design-navigation-blocked" && exact(data, ["type", "epoch", "view"])) {
      $("navigation-message").hidden = false;
      syncPanelAccess();
      focusAvailable($("return-to-app"));
      announce("Lenken går utenfor den lokale appen og er ikke åpnet.");
    } else if (data.type === "design-route" && exact(data, ["type", "epoch", "view", "route"]) && safeRoute(data.route)) {
      if (data.route === routeSeen) return;
      clearLocation();
      routeSeen = data.route;
      routeReady = false;
      selectionRequest += 1;
      updateControls();
      const observedView = previewRequest;
      // Only server-validated routes enter the visible status.
      // Only view registration is permitted from route evidence, never feedback.
      void registerView(data.route).catch(error => {
        if (observedView === previewRequest && data.route === routeSeen) globalError(safeError(error, "Siden kunne ikke knyttes til arbeidet. Eksisterende innspill er beholdt."));
      });
      postMode();
    } else if (data.type === "design-selection" && mode === "comment" && frameReady) {
      const shape = Object.keys(data).every(key => ["type", "epoch", "view", "context", "anchor", "label"].includes(key));
      if (!shape || !validContext(data.context) || !validAnchor(data.anchor) || (own(data, "label") && !plain(data.label, 200))) {
        globalError("Delen mangler gyldig kontekst. Ingen innspill er lagret. Prøv en annen del eller gi innspill til hele siden.");
        return;
      }
      void chooseTarget(data.context, data.anchor, data.label);
    }
  });
  $("app-tab").addEventListener("click", () => selectSurface("application"));
  $("proposal-tab").addEventListener("click", () => { const proposal = proposalList()[0]; void openProposal(proposal?.id); });
  $("review-progress-proposal").addEventListener("click", () => {
    const id = $("review-progress-proposal").dataset.proposal;
    if (id) { void openProposal(id); $("proposal-tab").focus(); }
  });
  $("proposal-back").addEventListener("click", () => { selectSurface("application"); $("app-tab").focus(); });
  for (const id of ["app-tab", "proposal-tab"]) $(id).addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home" ? "app-tab" : event.key === "End" ? "proposal-tab" : id === "app-tab" ? "proposal-tab" : "app-tab";
    $(next).focus(); $(next).click();
  });
  $("mode-browse").addEventListener("click", () => setMode("browse"));
  $("mode-change").addEventListener("click", () => setMode("comment"));
  $("open-feedback").addEventListener("click", () => locationPeeking ? returnToFeedback() : activePanel === "feedback" ? closePanel() : openPanel("feedback", $("open-feedback")));
  $("close-panel").addEventListener("click", () => closePanel());
  $("resume-draft").addEventListener("click", () => { setMode("comment", { showPanel: false }); openPanel("compose", $("resume-draft"), false); $("comment-text").focus(); });
  $("whole-page").addEventListener("click", wholePage);
  $("pick-part").addEventListener("click", pickPart);
  $("panel-browse").addEventListener("click", () => { setMode("browse"); $("mode-browse").focus(); });
  $("retry-preview").addEventListener("click", () => {
    openPreview();
    $("stage-title").focus();
  });
  $("return-to-app").addEventListener("click", () => {
    $("navigation-message").hidden = true;
    closePanel(false);
    setMode("browse", { showPanel: false });
    frame.focus();
  });
  narrowLayout.addEventListener("change", () => {
    const returnHeldFocus = document.activeElement === locationReturnButton;
    renderLocations();
    if (returnHeldFocus && !locationPeeking) focusComment(locationNotice?.id, "location");
  });
  $("comment-form").addEventListener("submit", event => void saveComment(event));
  $("comment-text").addEventListener("input", () => { errorAt("comment-error", ""); updateControls(); });
  $("keep-draft").addEventListener("click", () => { replacement = null; $("draft-change").hidden = true; $("comment-text").focus(); });
  $("discard-for-target").addEventListener("click", () => { if (replacement && !busy && !pendingSave) useTarget(replacement); });
  $("clear-draft").addEventListener("click", () => {
    if (busy || pendingSave) return;
    selection = null; replacement = null; $("comment-text").value = ""; $("draft-change").hidden = true;
    errorAt("comment-error", ""); renderSelection(); $("whole-page").focus(); announce("Utkastet er forkastet. Lagrede innspill er beholdt.");
  });
  $("submit-feedback").addEventListener("click", () => void submitFeedback());
  $("pending-tab").addEventListener("click", () => setTab("pending"));
  $("sent-tab").addEventListener("click", () => setTab("sent"));
  for (const name of ["pending", "sent"]) $(`${name}-tab`).addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    setTab(event.key === "Home" ? "pending" : event.key === "End" ? "sent" : activeTab === "pending" ? "sent" : "pending", true);
  });
  for (const width of ["fit", "desktop", "mobile"]) $(`width-${width}`).addEventListener("click", () => setWidth(width));
  $("show-local-draft").addEventListener("click", () => {
    $("local-draft-copy").hidden = false; $("local-draft-copy").focus(); $("local-draft-copy").select();
  });
  $("retry-state").addEventListener("click", () => {
    if (config.activationRequired) { void start(); return; }
    void refreshState().then(() => {
    const heldFocus = document.activeElement === $("retry-state");
    globalError("");
    if (heldFocus || document.activeElement === document.body) focusAvailable(activePanel ? $("panel-title") : $("mode-browse"));
  }).catch(() => { globalError("Forbindelsen er fortsatt utilgjengelig. Innspill og utkast er beholdt."); if (!retired) $("retry-state").focus(); });
  });
  document.addEventListener("keydown", event => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      if (locationPeeking || $("side-panel").hidden) { event.preventDefault(); return; }
      if (activePanel === "compose" && !$("comment-form").hidden) { event.preventDefault(); $("comment-form").requestSubmit(); }
      else if (activePanel === "feedback" && editingComment) { event.preventDefault(); $("feedback-list").querySelector(".edit-form")?.requestSubmit(); }
      return;
    }
    if (event.key === "Tab" && activePanel && narrowLayout.matches) {
      const elements = [...$("side-panel").querySelectorAll("button,textarea,a[href],select,input,[tabindex]")].filter(node => !node.disabled && node.tabIndex >= 0 && node.getClientRects().length);
      const first = elements[0], last = elements.at(-1);
      if (event.shiftKey && (document.activeElement === first || document.activeElement === $("panel-title"))) { event.preventDefault(); (last || $("panel-title")).focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); (first || $("panel-title")).focus(); }
      return;
    }
    if (event.key !== "Escape") return;
    if (locationPeeking) { event.preventDefault(); returnToFeedback(); return; }
    if (replacement) { event.preventDefault(); replacement = null; $("draft-change").hidden = true; $("comment-text").focus(); }
    else if (activePanel) { event.preventDefault(); closePanel(); }
    else if (mode === "comment") { event.preventDefault(); setMode("browse", { showPanel: false }); $("mode-browse").focus(); }
  });
  window.addEventListener("beforeunload", event => {
    if (!hasDraft() && !editingComment && !pendingSubmit && !pendingDelete) return;
    event.preventDefault(); event.returnValue = "";
  });
  window.addEventListener("pagehide", () => { retired = true; clearTimeout(pollTimer); clearTimeout(previewTimer); clearTimeout(locationTimer); clearTimeout(proposalTimer); });
  async function poll() {
    if (retired) return;
    if (!document.hidden && !busy) {
      try { await refreshState(); }
      catch {
        if (retired) return;
        markConnection(false);
        if (!pollError) announce("Forbindelsen til innspill er utilgjengelig. Utkastet ditt er beholdt.");
        pollError = true;
      }
    }
    if (!retired) pollTimer = setTimeout(poll, 3000);
  }
  const layoutObserver = new ResizeObserver(() => {
    document.documentElement.style.setProperty("--header-height", `${document.querySelector(".app-header").offsetHeight}px`);
    document.documentElement.style.setProperty("--tools-height", `${$("workspace-tools").offsetHeight}px`);
  });
  layoutObserver.observe(document.querySelector(".app-header"));
  layoutObserver.observe($("workspace-tools"));
  renderSelection();
  updateControls();
  async function start() {
    try {
      if (config.activationRequired) {
        const activated = await api("/renderer/activate", { body: {} });
        if (retired) return;
        config = previewConfig(activated, config.token, config.title);
      }
      openPreview();
      await refreshState();
    } catch {
      if (!retired) globalError("Visningen kunne ikke kobles til. Prøv igjen, eller åpne Designverksted på nytt fra samtalen. Ingen innspill er sendt.");
    } finally { if (!retired && !config.activationRequired) pollTimer = setTimeout(poll, 3000); }
  }
  void start();
})();
