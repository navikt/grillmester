"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

// This executes only in the privileged control origin, before the app shell.
// sessionStorage is tab-scoped; neither the preview nor a public invitation gets
// an existing writer. Its contents are still revalidated by the server.
function activateRenderer(start) {
  "use strict";
  const config = window.__designApplication;
  const tokenPattern = /^[a-f0-9]{64}$/, idPattern = /^[a-f0-9]{32}$/;
  const key = "designverksted.renderer.v1:" + config.connectionId;
  const store = value => { try { if (value) sessionStorage.setItem(key, JSON.stringify(value)); else sessionStorage.removeItem(key); } catch { /* Storage may be unavailable; never broaden authority. */ } };
  let saved = null;
  try { saved = JSON.parse(sessionStorage.getItem(key)); } catch { /* Missing or disabled storage cannot resume a writer. */ }
  if (!saved || Object.keys(saved).some(name => !["token", "reportGeneration", "pendingResumeId"].includes(name)) || !tokenPattern.test(saved.token || "") || !idPattern.test(saved.reportGeneration || "") || saved.pendingResumeId !== undefined && !idPattern.test(saved.pendingResumeId)) saved = null;
  // New tabs can inherit a copy from their opener. Only an actual reload may
  // reuse storage, and an opener never qualifies. Clear the local copy so a
  // subsequent reload of that new tab cannot convert it into writer authority.
  if (window.opener || performance.getEntriesByType("navigation")[0]?.type !== "reload") { store(null); saved = null; }
  try { window.opener = null; } catch { /* No opener access is needed. */ }
  const token = saved?.token || config.token;
  let body = {};
  if (saved) {
    const resumeId = saved.pendingResumeId || Array.from(crypto.getRandomValues(new Uint8Array(16)), value => value.toString(16).padStart(2, "0")).join("");
    body = { resumeId, expectedReportGeneration: saved.reportGeneration };
    // Persist only a previously validated token. Retaining the resume request
    // makes an ambiguous reply retryable without creating another generation.
    store({ ...saved, pendingResumeId: resumeId });
  }
  const controls = [...document.querySelectorAll("button,input,textarea,select")].map(node => [node, node.disabled]);
  for (const [node] of controls) node.disabled = true;
  const node = id => document.getElementById(id);
  let connecting = false, started = false;
  async function connect() {
    if (connecting || started) return;
    connecting = true;
    const retry = node("retry-state"); if (retry) retry.disabled = true;
    const abort = new AbortController(), timer = setTimeout(() => abort.abort(), 10000);
    try {
      if (!tokenPattern.test(token || "")) throw Object.assign(new Error(), { status: 410 });
      const response = await fetch("/renderer/activate", { method: "POST", headers: { "Content-Type": "application/json", "X-Designverksted-Token": token }, body: JSON.stringify(body), credentials: "omit", cache: "no-store", redirect: "error", signal: abort.signal });
      if (!response.ok) throw Object.assign(new Error(), { status: response.status });
      const value = await response.json(), preview = new URL(value.previewUrl), origin = new URL(value.previewOrigin).origin;
      if (preview.origin !== origin || origin === location.origin || !["http:", "https:"].includes(preview.protocol) || !idPattern.test(value.epoch || "") || !idPattern.test(value.reportGeneration || "")) throw new Error();
      store({ token, reportGeneration: value.reportGeneration });
      window.__designApplication = { ...value, token, title: config.title };
      started = true;
      for (const [control, disabled] of controls) control.disabled = disabled;
      if (retry) retry.removeEventListener("click", connect);
      if (node("global-message")) node("global-message").hidden = true;
      start();
    } catch (error) {
      const stale = error.status === 410;
      if (stale) store(null);
      if (node("app-status")) node("app-status").textContent = stale ? "Visningen er ikke aktiv" : "Forbindelsen er ikke bekreftet";
      if (node("stage-title")) node("stage-title").textContent = stale ? "Åpne Designverksted igjen fra samtalen" : "Visningen kunne ikke kobles til";
      if (node("stage-help")) node("stage-help").textContent = "Ingen innspill er sendt. Lagrede innspill beholdes.";
      if (node("global-message-text")) node("global-message-text").textContent = stale ? "Denne fanen har ingen aktiv forbindelse. Lukk canvaset og be i samtalen om å åpne verkstedet igjen." : "Forbindelsen kunne ikke bekreftes. Prøv samme tilkobling igjen.";
      if (node("global-message")) node("global-message").hidden = false;
      if (retry) { retry.hidden = stale; retry.disabled = stale; }
    } finally { clearTimeout(timer); connecting = false; }
  }
  node("retry-state")?.addEventListener("click", connect);
  return connect();
}

function renderActivationScript(shellSource) {
  return `(${activateRenderer.toString()})(() => {\n${shellSource}\n});`;
}
function renderInactive() {
  const nonce = crypto.randomBytes(24).toString("base64url");
  const style = fs.readFileSync(path.join(__dirname, "application-connection.css"), "utf8");
  return { html: `<!doctype html><html lang="nb"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Åpne Designverksted på nytt</title><style nonce="${nonce}">${style}</style><main><p class="wordmark">Designverksted</p><h1>Denne visningen er ikke aktiv</h1><p class="intro">Kopier eventuell ulagret tekst. Lukk dette canvaset, og be deretter om å åpne verkstedet igjen i samtalen.</p><p class="footnote">Lagrede rom beholdes. Midlertidig arbeid kan gå tapt ved lukking. Denne visningen sender ingen innspill.</p></main></html>`,
    csp: `default-src 'none'; style-src 'nonce-${nonce}'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'` };
}

module.exports = { renderInactive, renderActivationScript };
