"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const http = require("node:http");
const crypto = require("node:crypto");
const { ApplicationWorkspace } = require("./application-workspace.js");
const { ApplicationError } = require("./application-error.js");
const { createApplicationProxy } = require("./application-proxy.js");
const { createConnectionState } = require("./application-connection-state.js");
const { ApplicationProposals } = require("./application-proposals.js");
const { createProposalViews } = require("./application-proposal-view.js");
const { renderInactive } = require("./application-connection-view.js");
const { FeedbackError, FeedbackMutationReceipts, MAX_BODY_BYTES, keys } = require("./feedback-store.js");

const CHANNEL = "visual-companion-canvas";
const VERSION = 1;
const MAX_IPC_BYTES = 128 * 1024;
const requireValue = (ok, status, message) => { if (!ok) throw new FeedbackError(status, message); };
const loopback = value => value === "127.0.0.1" || value === "::1" || value === "::ffff:127.0.0.1";
const jsonScript = value => JSON.stringify(value).replace(/</g, "\\u003c").replace(/>/g, "\\u003e").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
function errorResponse(error) {
  const status = Number.isInteger(error?.status) && error.status >= 400 && error.status <= 599 ? error.status : 500;
  return { status, ...(error?.code === "renderer-stale" ? { code: error.code } : {}), error: error instanceof FeedbackError || error instanceof ApplicationError ? error.message : status === 409
    ? "Arbeidsrommet er opptatt eller endret utenfra. Kontroller prosjektfilene før du prøver igjen."
    : status === 404 ? "Arbeidsrommet finnes ikke. Opprett et nytt arbeid eller velg et eksisterende."
    : status === 503 ? "Den lokale appvisningen kunne ikke startes. Kontroller at appen kjører."
    : "Handlingen kunne ikke bekreftes. Les oppdatert status før du prøver igjen." };
}
function requestHeaders(req, name) {
  let count = 0;
  for (let index = 0; index < (req.rawHeaders?.length || 0); index += 2) if (req.rawHeaders[index].toLowerCase() === name) count += 1;
  return count <= 1 && typeof req.headers[name] === "string" ? req.headers[name] : null;
}
function authorizedRequest(req, { origin, token }, privileged = true) {
  if (!loopback(req.socket?.remoteAddress) || requestHeaders(req, "host") !== new URL(origin).host) return false;
  const source = requestHeaders(req, "origin");
  if (Object.hasOwn(req.headers, "origin") && source === null) return false;
  if (req.method === "POST" ? source !== origin : source !== null && source !== origin) return false;
  if (!privileged) return true;
  const given = requestHeaders(req, "x-designverksted-token");
  if (!given || Buffer.byteLength(given) !== Buffer.byteLength(token)) return false;
  return crypto.timingSafeEqual(Buffer.from(given), Buffer.from(token));
}
function headers(res, contentType = "application/json; charset=utf-8") {
  res.setHeader("Content-Type", contentType);
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.setHeader("Referrer-Policy", "no-referrer");
  res.setHeader("X-Frame-Options", "DENY");
  res.setHeader("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'");
}
function send(res, status, value) {
  headers(res); res.statusCode = status; res.end(JSON.stringify(value));
}
function readBody(req) {
  requireValue(/^application\/json(?:\s*;\s*charset=utf-8)?$/i.test(requestHeaders(req, "content-type") || ""), 415, "Send a JSON request body.");
  const length = requestHeaders(req, "content-length");
  requireValue(length === null || /^\d+$/.test(length) && Number(length) <= MAX_BODY_BYTES, 413, "The request body is too large.");
  return new Promise((resolve, reject) => {
    let size = 0, chunks = [], done = false;
    const finish = (error, value) => {
      if (done) return; done = true; clearTimeout(timer);
      req.off("data", data); req.off("end", end); req.off("error", failed); req.off("aborted", aborted);
      if (error) { req.resume(); reject(error); } else resolve(value);
    };
    const data = chunk => {
      size += Buffer.byteLength(chunk);
      if (size > MAX_BODY_BYTES) finish(new FeedbackError(413, "The request body is too large."));
      else chunks.push(Buffer.from(chunk));
    };
    const end = () => {
      try {
        const bytes = Buffer.concat(chunks), text = bytes.toString("utf8"); chunks = [];
        requireValue(Buffer.from(text).equals(bytes), 400, "The request body must be valid UTF-8.");
        const value = JSON.parse(text);
        requireValue(value !== null && typeof value === "object" && !Array.isArray(value), 400, "Send a JSON object.");
        finish(null, value);
      } catch (error) { finish(error instanceof FeedbackError ? error : new FeedbackError(400, "Invalid JSON request body.")); }
    };
    const failed = () => finish(new FeedbackError(400, "The request body could not be read."));
    const aborted = () => finish(new FeedbackError(400, "The request was interrupted."));
    const timer = setTimeout(() => finish(new FeedbackError(408, "The request body timed out.")), 15000); timer.unref?.();
    req.on("data", data); req.once("end", end); req.once("error", failed); req.once("aborted", aborted);
  });
}
// Browser observation is volatile and is not a workspace mutation or proof that
// the whole application works. HTTP transport and shell readiness stay separate.
function createPreviewStatus() {
  let active = false, generation = null, sequence = 0, observed = null;
  let transport = { state: "unavailable" };
  return {
    open() { active = true; generation = null; sequence = 0; observed = null; transport = { state: "loading" }; },
    close() { active = false; generation = null; sequence = 0; observed = null; transport = { state: "unavailable" }; },
    bootstrap() {
      requireValue(active, 409, "The application view is closed.");
      // A full shell reload retires reports still in flight from its old page.
      generation = crypto.randomBytes(16).toString("hex"); sequence = 0; observed = null;
      return generation;
    },
    transport(value) { if (active) transport = { ...value }; },
    report(input) {
      const reasons = { loading: "waiting-for-app", ready: "inspector-ready", unavailable: ["inspector-timeout", "application-unavailable"] };
      requireValue(keys(input, ["generation", "sequence", "state", "reason"]) && typeof input.generation === "string" && /^[a-f0-9]{32}$/.test(input.generation) &&
        typeof input.state === "string" && typeof input.reason === "string" &&
        Number.isSafeInteger(input.sequence) && input.sequence > 0 && Object.hasOwn(reasons, input.state) &&
        (Array.isArray(reasons[input.state]) ? reasons[input.state].includes(input.reason) : reasons[input.state] === input.reason), 400, "Invalid application view status.");
      requireValue(active && generation !== null && input.generation === generation, 409, "This application view status belongs to an older page.");
      requireValue(input.sequence > sequence || input.sequence === sequence && observed?.state === input.state && observed?.reason === input.reason,
        409, "This application view status has been superseded.");
      sequence = input.sequence;
      observed = { state: input.state, reason: input.reason };
    },
    snapshot() {
      let previewStatus = observed ? { ...observed } : { state: transport.state === "unavailable" ? "unavailable" : "loading", reason: active ? "waiting-for-view" : "view-closed" };
      // Known transport failure is terminal even before the shell has polled it.
      // Preserve a more precise browser timeout, but never keep old loading/ready.
      if (active && transport.state === "unavailable" && previewStatus.reason !== "inspector-timeout") {
        previewStatus = { state: "unavailable", reason: "application-unavailable" };
      } else if (previewStatus.state === "ready" && transport.state !== "ready") {
        previewStatus = { state: "loading", reason: "waiting-for-app" };
      }
      previewStatus.retryAvailable = active && generation !== null && previewStatus.state === "unavailable";
      return { previewStatus, transportStatus: { ...transport } };
    },
  };
}
function snapshot(workspace, full = false, preview) {
  const current = workspace.current();
  return { ...(full ? workspace.feedback.snapshot() : workspace.canvas.summary()), screen: current.screen,
    application: { ...current, route: current.source.route, checkpoint: current.source.checkpoint, ...(preview ? preview.snapshot() : {}) }, workspace: workspace.summary() };
}
// The handler is separately testable without a listening socket. Application
// evidence never reaches it directly: every operation belongs to the shell.
function createApplicationRequestHandler({ workspace, authority, receipts = new FeedbackMutationReceipts(), onSubmitted = () => {} }) {
  return async (req, res) => {
    try {
      requireValue(typeof req.url === "string" && req.url.startsWith("/") && !req.url.startsWith("//") &&
        req.url.length <= 4096 && !/[\\\u0000-\u0020\u007f#]/.test(req.url), 400, "Invalid request path.");
      const target = new URL(req.url, authority.origin);
      const bootstrap = req.url === authority.openPath && req.method === "GET";
      const connection = authority.connection;
      const browser = connection && req.method === "GET" && req.url.startsWith("/browser/");
      const controller = connection && authority.connectionStatus && ["/connection/status", "/connection/reopen"].includes(target.pathname);
      const activation = connection && req.method === "POST" && target.pathname === "/renderer/activate";
      const proposalFrame = req.method === "GET" && /^\/proposal-frame\/[a-f0-9]{64}$/.test(req.url);
      const proposalActivation = req.method === "POST" && req.url === "/proposal/activate";
      requireValue(authorizedRequest(req, authority, false), 403, "This request does not belong to the open design workspace.");
      authority.assertActive?.(); workspace.assertOpen();
      const writeHtml = rendered => {
        headers(res, "text/html; charset=utf-8"); res.setHeader("Content-Security-Policy", rendered.csp);
        res.statusCode = 200; res.end(rendered.html);
      };
      if (bootstrap) { writeHtml(connection ? authority.renderPanel() : authority.renderShell ? authority.renderShell() : authority); return; }
      if (browser) {
        try { writeHtml(authority.renderShell(connection.candidate(req.url))); }
        catch (error) { if (error.code !== "renderer-stale") throw error; writeHtml(renderInactive()); }
        return;
      }
      if (proposalFrame) {
        requireValue(authority.proposalViews, 404, "The proposal view is unavailable.");
        const rendered = authority.proposalViews.render(req.url);
        headers(res, "text/html; charset=utf-8"); res.removeHeader?.("X-Frame-Options");
        res.setHeader("Content-Security-Policy", rendered.csp); res.statusCode = 200; res.end(rendered.html); return;
      }
      if (proposalActivation) {
        const input = await readBody(req); authority.assertActive?.(); workspace.assertOpen();
        requireValue(authority.proposalViews, 404, "The proposal view is unavailable.");
        send(res, 200, authority.proposalViews.activate(input)); return;
      }
      if (controller) {
        const control = { ...authority, token: authority.controlToken };
        const given = requestHeaders(req, "x-designverksted-connection");
        requireValue(given && Buffer.byteLength(given) === Buffer.byteLength(control.token) && crypto.timingSafeEqual(Buffer.from(given), Buffer.from(control.token)), 403, "This request does not belong to the connection panel.");
        requireValue(!target.search, 400, "This action does not accept query parameters.");
        if (req.method === "GET" && target.pathname === "/connection/status") { send(res, 200, authority.connectionStatus()); return; }
        requireValue(req.method === "POST" && target.pathname === "/connection/reopen", 405, "This request method is unavailable.");
        const input = await readBody(req); authority.assertActive?.();
        requireValue(keys(input, ["generation", "requestId"]) && typeof input.generation === "string" && /^[a-f0-9]{32}$/.test(input.generation) && typeof input.requestId === "string" && /^[a-f0-9]{32}$/.test(input.requestId), 400, "Invalid connection opening request.");
        await authority.reopen(input); authority.assertActive?.();
        send(res, 200, authority.connectionStatus()); return;
      }
      const documentToken = requestHeaders(req, "x-designverksted-token");
      const authorize = () => {
        authority.assertActive?.(); workspace.assertOpen();
        if (connection) connection.authorize(documentToken);
        else requireValue(authorizedRequest(req, authority), 403, "This request does not belong to the open design workspace.");
      };
      if (activation) {
        const input = await readBody(req); authority.assertActive?.();
        requireValue(keys(input, []), 400, "No arguments expected.");
        send(res, 200, connection.activate(documentToken, authority.activationBootstrap)); return;
      }
      authorize();
      requireValue(["GET", "POST"].includes(req.method), 405, "This request method is unavailable.");
      requireValue(!target.search, 400, "This action does not accept query parameters.");
      const state = async () => authority.readState ? authority.readState(true) : snapshot(workspace, true, authority.preview);
      if (req.method === "GET" && target.pathname === "/state") { const result = await state(); authorize(); send(res, 200, result); return; }
      requireValue(req.method === "POST", 404, "The requested action is unavailable.");
      const deletion = /^\/comments\/([a-f0-9]{24})\/delete$/.exec(target.pathname);
      const edit = /^\/comments\/([a-f0-9]{24})\/edit$/.exec(target.pathname);
      requireValue(["/view", "/preview/status", "/comments", "/submit", "/proposal/open", "/proposal/selection"].includes(target.pathname) || deletion || edit, 404, "The requested action is unavailable.");
      const input = await readBody(req);
      authorize(); // A slow body cannot retain authority after a replacement or close.
      if (target.pathname === "/proposal/open") {
        requireValue(keys(input, ["proposalId"]) && authority.openProposal, 400, "Invalid proposal opening request.");
        const result = await authority.openProposal(input.proposalId, authorize); authorize(); send(res, 200, result); return;
      }
      if (target.pathname === "/proposal/selection") {
        requireValue(keys(input, ["proposalId"]) && authority.selectProposal, 400, "Invalid proposal selection.");
        authority.selectProposal(input.proposalId); const result = await state(); authorize(); send(res, 200, result); return;
      }
      if (target.pathname === "/preview/status") {
        requireValue(authority.preview, 409, "The application view is unavailable.");
        authority.preview.report(input);
        send(res, 200, authority.preview.snapshot()); return;
      }
      if (target.pathname === "/view") {
        requireValue(keys(input, ["route", "expectedCheckpoint"], ["capture"]) && (!Object.hasOwn(input, "capture") || input.capture === true), 400, "Invalid application page.");
        workspace.observeRoute({ route: input.route, expectedCheckpoint: input.expectedCheckpoint });
      } else {
        const mutation = requestHeaders(req, "x-feedback-mutation");
        requireValue(typeof mutation === "string" && /^[a-f0-9]{32}$/.test(mutation), 400, "A feedback mutation identifier is required.");
        const previous = workspace.feedback.state.submission;
        try {
          receipts.run(mutation, req.method, target.pathname, input, value => {
            if (target.pathname === "/comments") workspace.createComment(value);
            else if (target.pathname === "/submit") workspace.feedback.submit(value);
            else if (edit) workspace.feedback.editDraft(edit[1], value);
            else {
              const current = workspace.feedback.state.comments.find(item => item.id === deletion[1]);
              requireValue(!current || current.submission === 0 && current.lastSubmission === 0, 409, "Submitted comments remain in their review round.");
              workspace.feedback.delete(deletion[1], value);
            }
          });
        } finally {
          // A post-rename durability error has committed state; do not lose its
          // delivery signal or send a second one when the same request retries.
          if (workspace.feedback.state.submission > previous) { try { onSubmitted(workspace.feedback.state.submission); } catch { /* An observer cannot roll back a committed round. */ } }
        }
      }
      const result = await state(); authorize(); send(res, 200, result);
    } catch (error) {
      const result = errorResponse(error); send(res, result.status, { error: result.error, ...(result.code ? { code: result.code } : {}) });
    }
  };
}
function renderShell({ previewUrl, previewOrigin, epoch, title, token, reportGeneration, activationRequired = false }) {
  const nonce = crypto.randomBytes(24).toString("base64url");
  const content = name => fs.readFileSync(path.join(__dirname, name), "utf8");
  const values = { NONCE: nonce, APPLICATION_STYLE: content("application-shell.css"),
    APPLICATION_SCRIPT: content("application-shell.js"), APPLICATION_CONFIG: jsonScript(activationRequired ? { title, token, activationRequired } : { previewUrl, previewOrigin, epoch, title, token, reportGeneration }) };
  const html = content("application-shell.tmpl").replace(/\{\{(NONCE|APPLICATION_STYLE|APPLICATION_SCRIPT|APPLICATION_CONFIG)\}\}/g, (_, name) => values[name]);
  return { html, csp: `default-src 'none'; script-src 'nonce-${nonce}'; style-src 'nonce-${nonce}'; connect-src 'self'; img-src blob:; frame-src 'self' ${previewOrigin}; frame-ancestors 'none'; base-uri 'none'; form-action 'none'` };
}
async function stopServer(server) {
  if (!server?.listening) return;
  await new Promise(resolve => { server.close(resolve); server.closeAllConnections?.(); });
}
function createApplicationServer({ projectDir, workspacePath, create = false, title, application, onSubmitted, proposalBackendFactory, onViewLost } = {}) {
  requireValue(onSubmitted === undefined || typeof onSubmitted === "function", 400, "Invalid submission observer.");
  requireValue(onViewLost === undefined || typeof onViewLost === "function", 400, "Invalid view observer.");
  const directory = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "design-workspace-")));
  const owned = fs.lstatSync(directory);
  const cleanup = () => {
    try { const current = fs.lstatSync(directory); if (current.dev === owned.dev && current.ino === owned.ino && current.isDirectory() && !current.isSymbolicLink()) fs.rmSync(directory, { recursive: true, force: true }); } catch { /* Never remove a replacement directory. */ }
  };
  let workspace;
  try { workspace = new ApplicationWorkspace({ projectDir, workspacePath, stateDir: directory, create, title, application,
    ...(create ? { checkpoint: crypto.randomBytes(32).toString("hex") } : {}) }); }
  catch (error) { cleanup(); throw error; }
  const proposals = new ApplicationProposals({ workspace, projectDir, onSubmitted,
    backendFactory: proposalBackendFactory || (async options => {
      const { createServerBackend } = await import("../../../extensions/visual-companion/backend.mjs");
      return createServerBackend(options);
    }) });
  let view = null, viewRetired = false, retired = false, closed = false, queue = Promise.resolve(), closing = null;
  const preview = createPreviewStatus();
  const receipts = new FeedbackMutationReceipts();
  const enqueue = operation => { const result = queue.then(operation); queue = result.catch(() => {}); return result; };
  function invalidate(current) {
    if (!current) return;
    current.live = false; current.connection.close(); current.proposalViews?.revoke();
    current.proposalClosure = proposals.closeViews(); preview.close();
  }
  function lostView(current) {
    if (!current.live) return;
    viewRetired = true; invalidate(current);
    void close().then(() => { try { onViewLost?.(); } catch { /* Cleanup is already complete. */ } }).catch(() => {});
  }
  async function closeView() {
    viewRetired = true;
    const current = view; view = null; invalidate(current);
    if (current) await Promise.allSettled([current.proxy?.close(), current.proposalClosure, stopServer(current.server)]);
  }
  async function preparePreview(current) {
    current.authority.assertActive();
    requireValue(!current.prepared, 410, "Open a fresh workshop instance to reconnect the application.");
    current.prepared = true;
    const epoch = crypto.randomBytes(16).toString("hex"); current.epoch = epoch; preview.open();
    const inspectorSource = fs.readFileSync(path.join(__dirname, "application-inspector.js"), "utf8")
      .replace("__DESIGN_INSPECTOR_CONFIG__", () => jsonScript({ shellOrigin: current.origin, epoch }));
    const resumedApplication = { name: workspace.connection.name, url: workspace.connection.origin + workspace.current().source.route,
      ...(workspace.connection.resourceQueryKeys ? { resourceQueryKeys: workspace.connection.resourceQueryKeys } : {}) };
    const proxy = await createApplicationProxy({ application: resumedApplication, shellOrigin: current.origin, inspectorSource,
      onStatus: status => { if (current.live && current.epoch === epoch) preview.transport(status); },
      onClose: () => lostView(current) });
    current.proxy = proxy;
    try { current.authority.assertActive(); } catch (error) { await proxy.close(); current.proxy = null; throw error; }
    current.connection.prepare();
  }
  async function openView() {
    requireValue(!viewRetired, 410, "This application view is closed. Open a fresh workshop instance.");
    if (view?.live && view.result) return view.result;
    requireValue(workspace.connection, 409, "Reconnect the local application before opening its view.");
    const connection = createConnectionState(), authority = {};
    const current = { server: null, proxy: null, connection, authority, live: true, result: null }; view = current;
    authority.assertActive = () => {
      if (closed || retired || view !== current || !current.live) { const error = new FeedbackError(410, "Visningen er lukket. Åpne Designverksted igjen fra samtalen."); error.code = "renderer-stale"; throw error; }
    };
    let handler;
    current.server = http.createServer((req, res) => {
      if (!handler) { send(res, 503, { error: "The application view is starting." }); return; }
      void handler(req, res);
    });
    const server = current.server;
    server.once("close", () => lostView(current));
    server.requestTimeout = 20000; server.headersTimeout = 15000; server.keepAliveTimeout = 1000;
    try {
      await new Promise((resolve, reject) => {
        const ready = () => { server.off("error", failed); resolve(); };
        const failed = () => { server.off("listening", ready); reject(new FeedbackError(503, "The local application view could not start.")); };
        server.once("error", failed); server.once("listening", ready); server.listen(0, "127.0.0.1");
      });
      authority.assertActive(); current.origin = `http://127.0.0.1:${server.address().port}`;
      current.proposalViews = createProposalViews(current.origin);
      Object.assign(authority, { origin: current.origin, connection, preview, proposalViews: current.proposalViews,
        readState: state, selectProposal: id => proposals.select(id),
        openProposal: (id, authorize) => enqueue(async () => {
          authorize();
          const generation = connection.generation;
          const child = await proposals.openView(id, { parentOrigin: current.origin, leaseId: generation });
          authorize(); requireValue(generation === connection.generation, 410, "This workshop view has been replaced.");
          return current.proposalViews.open(id, child);
        }) });
      await preparePreview(current);
      Object.assign(authority, {
        renderShell: token => renderShell({ previewOrigin: current.proxy.origin, title: workspace.summary().title, token, activationRequired: true }),
        activationBootstrap: () => ({ previewUrl: current.proxy.url, previewOrigin: current.proxy.origin, epoch: current.epoch, reportGeneration: preview.bootstrap() }),
      });
      handler = createApplicationRequestHandler({ workspace, authority, receipts, onSubmitted });
      current.result = { url: current.origin + connection.path, title: workspace.summary().title,
        status: "Prøvevisningen åpnes i Designverksted. Ved avbrutt visning eller omlasting: kopier eventuell ulagret tekst, lukk canvaset først, og be så i samtalen om å åpne verkstedet igjen. Lagrede rom beholdes; midlertidige forslag kan gå tapt." };
      return current.result;
    } catch (error) {
      viewRetired = true;
      invalidate(current); if (view === current) view = null;
      await Promise.allSettled([current.proxy?.close(), stopServer(server)]); throw error;
    }
  }
  async function state(full = false) {
    const result = snapshot(workspace, full, preview);
    result.application.connection = view?.live ? view.connection.status() : { state: "closed", invitationExpired: true };
    result.proposals = await proposals.summary(); result.selectedProposalId = proposals.selected;
    return result;
  }
  async function execute(method, params) {
    requireValue(!closed && !retired, 410, "The application workspace is closed.");
    requireValue(typeof method === "string" && params !== null && typeof params === "object" && !Array.isArray(params), 400, "Invalid application operation.");
    workspace.assertOpen();
    if (Object.hasOwn(params, "proposalId")) return proposals.action(method, params);
    if (method === "publishProposal") return proposals.publish(params);
    if (["publishRevision", "readRevision", "restoreRevision", "listHistory"].includes(method)) throw new FeedbackError(409, "This room is for trying an application and sending feedback. Sketch versions are available only in HTML rooms.");
    if (method === "readSubmission") return workspace.canvas.read(params);
    if (method === "reviewSubmission") { workspace.canvas.review(params); return state(); }
    if (method === "updateComment") { workspace.canvas.updateComment(params); return state(); }
    if (method === "markDelivery") { workspace.canvas.delivery(params); return state(); }
    requireValue(keys(params, []), 400, "No arguments expected.");
    if (method === "readState") return state();
    if (method === "openView") return openView();
    if (method === "closeView") { await closeView(); return { closed: true }; }
    if (method === "retire") { retired = true; await closeView(); await proposals.close(); workspace.close(); cleanup(); return { retired: true }; }
    throw new FeedbackError(400, "Unknown application operation.");
  }
  function command(method, params = {}) {
    // Reject renderer work immediately, even while a startup/HTTP body is pending.
    if ((method === "closeView" || method === "retire") && keys(params, [])) { viewRetired = true; invalidate(view); }
    return enqueue(() => execute(method, params));
  }
  function close() {
    if (closing) return closing;
    closed = true; invalidate(view);
    closing = queue.then(async () => { await closeView(); await proposals.close(); workspace.close(); cleanup(); });
    return closing;
  }
  return { command, close };
}
function validEnvelope(message) {
  try { return keys(message, ["channel", "version", "id", "method", "params"]) && message.channel === CHANNEL && message.version === VERSION &&
    Number.isSafeInteger(message.id) && message.id > 0 && typeof message.method === "string" && message.method.length <= 64 &&
    message.params !== null && typeof message.params === "object" && !Array.isArray(message.params) && Buffer.byteLength(JSON.stringify(message)) <=
      (message.method === "publishProposal" || message.method === "publishRevision" ? 2 * 1024 * 1024 + MAX_IPC_BYTES : MAX_IPC_BYTES); }
  catch { return false; }
}
function parseArguments(args) {
  const options = {}, mapping = { "--project-dir": "projectDir", "--workspace-dir": "workspacePath", "--workspace-create": "create", "--workspace-title": "title", "--application": "application" };
  requireValue(Array.isArray(args) && args.length % 2 === 0, 400, "Invalid application startup options.");
  for (let index = 0; index < args.length; index += 2) {
    const name = Object.hasOwn(mapping, args[index]) ? mapping[args[index]] : undefined, value = args[index + 1];
    requireValue(name && !Object.hasOwn(options, name) && typeof value === "string", 400, "Invalid application startup options.");
    if (name === "create") { requireValue(value === "true", 400, "Invalid workspace creation option."); options.create = true; }
    else if (name === "application") { try { options.application = JSON.parse(value); } catch { throw new FeedbackError(400, "Invalid application configuration."); } }
    else options[name] = value;
  }
  requireValue(typeof options.projectDir === "string" && options.application !== undefined, 400, "A project context and local application are required.");
  return options;
}
async function run() {
  let server, ending = false;
  const send = message => { if (process.connected) process.send({ channel: CHANNEL, version: VERSION, ...message }, () => {}); };
  const shutdown = async () => { if (ending) return; ending = true; await server?.close(); if (process.connected) process.disconnect(); };
  try {
    server = createApplicationServer({ ...parseArguments(process.argv.slice(2)), onViewLost: () => void shutdown(), onSubmitted: (submission, proposalId) => send({ event: "submitted", submission, ...(proposalId ? { proposalId } : {}) }) });
    process.on("message", message => {
      if (message?.channel !== CHANNEL || message?.version !== VERSION || !Number.isSafeInteger(message?.id) || message.id < 1 || ending) return;
      if (!validEnvelope(message)) { send({ id: message.id, ok: false, status: 400, error: "Invalid application request." }); return; }
      void server.command(message.method, message.params).then(result => {
        if (message.method === "retire") {
          if (process.connected) process.send({ channel: CHANNEL, version: VERSION, id: message.id, ok: true, result }, () => void shutdown());
          else void shutdown();
        } else send({ id: message.id, ok: true, result });
      }, error => send({ id: message.id, ok: false, ...errorResponse(error) }));
    });
    process.once("disconnect", () => void shutdown()); process.once("SIGTERM", () => void shutdown()); process.once("SIGINT", () => void shutdown());
    send({ event: "ready", info: { type: "server-started" } });
  } catch (error) {
    const result = errorResponse(error);
    if (process.connected) process.send({ channel: CHANNEL, version: VERSION, event: "startup-error", ...result }, () => { process.disconnect(); process.exitCode = 2; });
    else { process.stderr.write(JSON.stringify({ type: "error", message: result.error }) + "\n"); process.exitCode = 2; }
    await server?.close();
  }
}
if (require.main === module) void run();
module.exports = { createApplicationServer, createPreviewStatus, createApplicationRequestHandler, authorizedRequest, renderShell, validEnvelope, parseArguments };
