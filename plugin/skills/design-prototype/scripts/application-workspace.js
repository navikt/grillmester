"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { WorkspaceStore } = require("./workspace-store.js");
const { FeedbackStore, FeedbackError, validPersistedFeedback, keys, ID } = require("./feedback-store.js");
const { CanvasState } = require("./canvas-state.js");
const { parseApplication, normalizeApplicationRoute, normalizeResourceQueryKeys, validApplicationScreen, screenIdentity } = require("./application-contract.js");

const hash = value => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const text = value => typeof value === "string" && value.trim().length > 0 && Buffer.byteLength(value, "utf8") <= 200 &&
  !/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/.test(value) && Buffer.from(value).toString("utf8") === value;
const requireValue = (ok, status, message) => { if (!ok) throw new FeedbackError(status, message); };
const copy = value => JSON.parse(JSON.stringify(value));
const relativeDirectory = value => typeof value === "string" && value.length > 0 && Buffer.byteLength(value) <= 240 && value.split("/").length <= 8 &&
  value.split("/").every(part => /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(part) && !/^(?:node_modules|__pycache__|con|prn|aux|nul|com[1-9]|lpt[1-9])$/i.test(part));
function validSketchBinding(value, state) {
  if (!keys(value, ["id", "title", "workspacePath", "workspaceId", "source", "requestHash"], ["styleProjectPath", "sourceSubmission", "commentIds", "application"]) ||
      typeof value.id !== "string" || !ID.test(value.id) || typeof value.workspaceId !== "string" || !ID.test(value.workspaceId) || !text(value.title) || !relativeDirectory(value.workspacePath) || !hash(value.requestHash) ||
      Object.hasOwn(value, "styleProjectPath") && value.styleProjectPath !== "" && !relativeDirectory(value.styleProjectPath)) return false;
  if (value.application) {
    if (Object.hasOwn(value, "styleProjectPath") || !keys(value.application, ["name", "startPath"], ["resourceQueryKeys"]) || !text(value.application.name)) return false;
    try { parseApplication({ name: value.application.name, url: "http://localhost" + value.application.startPath, ...(value.application.resourceQueryKeys ? { resourceQueryKeys: value.application.resourceQueryKeys } : {}) }); }
    catch { return false; }
  } else if (Object.hasOwn(value, "application")) return false;
  if (value.source === "conversation") return !Object.hasOwn(value, "sourceSubmission") && !Object.hasOwn(value, "commentIds");
  if (value.source !== "app-feedback" || !Array.isArray(value.commentIds) || value.commentIds.length < 1 || value.commentIds.length > 200 ||
      new Set(value.commentIds).size !== value.commentIds.length || !value.commentIds.every(id => typeof id === "string" && ID.test(id))) return false;
  const batch = state.submissions.find(item => item.submission === value.sourceSubmission);
  return Boolean(batch && value.commentIds.every(id => batch.comments.some(comment => comment.id === id)));
}
function validSketchSave(value, state) {
  return keys(value, ["binding", "expectedScreen", "expectedRevision"]) && !value.binding?.application && validSketchBinding(value.binding, state) &&
    typeof value.expectedScreen === "string" && /^[a-f0-9]{32}$/.test(value.expectedScreen) &&
    Number.isSafeInteger(value.expectedRevision) && value.expectedRevision >= 0;
}
function canonicalRoute(value, resourceQueryKeys = []) {
  try { return normalizeApplicationRoute(value, resourceQueryKeys) === value; } catch { return false; }
}

// A room records deliberate feedback, not source snapshots or permission to
// change an app. The opaque checkpoint scopes route identities to this room.
function validApplicationWorkspaceState(state) {
  try {
    if (!validPersistedFeedback(state) || !state.canvas || state.canvas.rounds.some(round => typeof round.previousSession !== "boolean") ||
        !keys(state.workspace, ["id", "title", "mode", "source", "checkpoint"], ["sketch", "pendingSketchSave"])) return false;
    const { id, title, mode, source, checkpoint } = state.workspace;
    if (mode !== "feedback" || typeof id !== "string" || !ID.test(id) || !text(title) || !hash(checkpoint) ||
        !keys(source, ["kind", "name", "startPath"], ["resourceQueryKeys"]) || source.kind !== "application" || !text(source.name)) return false;
    const resourceQueryKeys = source.resourceQueryKeys || [];
    if (JSON.stringify(normalizeResourceQueryKeys(resourceQueryKeys)) !== JSON.stringify(resourceQueryKeys) || !canonicalRoute(source.startPath, resourceQueryKeys)) return false;
    return (!Object.hasOwn(state.workspace, "sketch") || validSketchBinding(state.workspace.sketch, state)) &&
      (!Object.hasOwn(state.workspace, "pendingSketchSave") || !Object.hasOwn(state.workspace, "sketch") && validSketchSave(state.workspace.pendingSketchSave, state)) &&
      state.screens.every(screen => validApplicationScreen(screen) && screen.source.checkpoint === checkpoint && canonicalRoute(screen.source.route, resourceQueryKeys));
  } catch { return false; }
}

class ApplicationWorkspace {
  constructor({ projectDir, workspacePath, stateDir, create = false, title, application, checkpoint } = {}) {
    requireValue(typeof create === "boolean", 400, "Invalid application workspace creation option.");
    requireValue(typeof stateDir === "string" && path.isAbsolute(stateDir), 400, "An explicit private runtime directory is required.");
    const runtime = fs.lstatSync(stateDir);
    requireValue(runtime.isDirectory() && !runtime.isSymbolicLink() && (runtime.mode & 0o077) === 0 &&
      (typeof process.getuid !== "function" || runtime.uid === process.getuid()) && fs.realpathSync(stateDir) === path.resolve(stateDir), 409, "The application runtime directory is unsafe.");
    this.temporary = workspacePath === undefined;
    requireValue(!this.temporary || !create && title === undefined, 400, "Creating or naming a saved room requires an explicit workspace path.");
    this.connection = application === undefined ? null : parseApplication(application);
    const fresh = this.temporary || create;
    requireValue(!fresh || this.connection !== null, 400, "Opening a new application room requires a local application.");
    requireValue(checkpoint === undefined || hash(checkpoint), 400, "Invalid application feedback identity.");
    requireValue(title === undefined || create && text(title), 400, "A workspace title is only supplied when creating it.");
    this.path = workspacePath;
    this.recovered = !fresh;
    this.closed = false;
    try {
      // A temporary room never reads or writes the caller's project directory.
      this.store = new WorkspaceStore({ projectDir: this.temporary ? stateDir : projectDir, workspacePath: this.temporary ? "room" : workspacePath,
        create: fresh, title, validateState: validApplicationWorkspaceState, revisionFiles: false });
      if (fresh) {
        const workspace = { id: crypto.randomBytes(12).toString("hex"), title: title?.trim() || this.connection.name, mode: "feedback",
          source: { kind: "application", name: this.connection.name, startPath: this.connection.startPath,
            ...(this.connection.resourceQueryKeys ? { resourceQueryKeys: this.connection.resourceQueryKeys } : {}) },
          checkpoint: checkpoint || crypto.randomBytes(32).toString("hex") };
        this.store.persist({ schemaVersion: 1, revision: 0, submission: 0, screens: [], comments: [], submissions: [], canvas: { rounds: [] }, workspace });
      }
      const saved = this.store.load();
      requireValue(!this.connection || this.connection.startPath === saved.workspace.source.startPath &&
        JSON.stringify(this.connection.resourceQueryKeys || []) === JSON.stringify(saved.workspace.source.resourceQueryKeys || []), 409,
        "This connection has a different start path or query policy. Reopen with the room's saved settings, or create a new feedback room.");
      requireValue(checkpoint === undefined || checkpoint === saved.workspace.checkpoint, 409, "This feedback identity belongs to another room.");
      this.route = saved.workspace.source.startPath;
      this.feedback = new FeedbackStore(stateDir, { canvas: true, persistence: this.store });
      this.canvas = new CanvasState(this.feedback);
      if (this.recovered && this.feedback.state.canvas.rounds.length) {
        const next = copy(this.feedback.state);
        for (const round of next.canvas.rounds) { round.previousSession = true; if (round.delivery === "sending") round.delivery = "unknown"; }
        // Opening does not rewrite project files or resend historical rounds.
        this.feedback.state = next;
      }
    } catch (error) {
      try { this.store?.close(); } catch { /* Preserve the original startup failure. */ }
      throw error;
    }
  }
  assertOpen() { requireValue(!this.closed, 410, "The application workspace is closed."); this.store.assertOpen(); }
  summary() {
    this.assertOpen();
    const { id, title, source, checkpoint } = this.feedback.state.workspace;
    return copy({ id, title, ...(this.temporary ? {} : { path: this.path }), storage: this.temporary ? "temporary" : "project", recovered: this.recovered,
      mode: "feedback", source, checkpoint, currentRoute: this.route });
  }
  current() {
    this.assertOpen();
    const { source, checkpoint } = this.feedback.state.workspace;
    return { screen: screenIdentity(checkpoint, this.route), source: { kind: "application", checkpoint, route: this.route }, name: this.connection?.name || source.name };
  }
  observeRoute(input) {
    this.assertOpen();
    requireValue(keys(input, ["route", "expectedCheckpoint"]) && hash(input.expectedCheckpoint), 400, "Invalid application route update.");
    const workspace = this.feedback.state.workspace;
    requireValue(input.expectedCheckpoint === workspace.checkpoint, 409, "This page belongs to another feedback room. Reopen the app before selecting a part.");
    this.route = normalizeApplicationRoute(input.route, workspace.source.resourceQueryKeys || []);
    return screenIdentity(workspace.checkpoint, this.route);
  }
  commentScreen(value) {
    this.assertOpen();
    const workspace = this.feedback.state.workspace;
    const route = normalizeApplicationRoute(value?.applicationContext?.route, workspace.source.resourceQueryKeys || []);
    requireValue(route === value.applicationContext.route, 400, "The comment route must be canonical.");
    return { screen: screenIdentity(workspace.checkpoint, route), source: { kind: "application", checkpoint: workspace.checkpoint, route } };
  }
  createComment(value) {
    // Screen registration and comment creation share a single atomic commit.
    // Navigation and app-generated selections can never consume saved capacity.
    return this.feedback.create(value, this.commentScreen(value));
  }
  submitDraft(value) {
    return this.feedback.submitDraft(value, this.commentScreen(value?.comment));
  }
  bindSketch(value) {
    this.assertOpen();
    requireValue(!this.temporary && validSketchBinding(value, this.feedback.state), 400, "Invalid saved sketch connection.");
    const previous = this.feedback.state.workspace.sketch;
    requireValue(!previous || JSON.stringify(previous) === JSON.stringify(value), 409, "This work already has a sketch. Continue its existing versions.");
    if (!previous) this.feedback.change(state => { state.workspace.sketch = copy(value); });
  }
  beginSketchSave(value) {
    this.assertOpen();
    requireValue(!this.temporary && !this.feedback.state.workspace.sketch && validSketchSave(value, this.feedback.state), 400, "Invalid proposal save intent.");
    const previous = this.feedback.state.workspace.pendingSketchSave;
    requireValue(!previous || JSON.stringify(previous) === JSON.stringify(value), 409, "A different proposal save is pending. Read its current status before retrying.");
    if (!previous) this.feedback.change(state => { state.workspace.pendingSketchSave = copy(value); });
  }
  finishSketchSave(value) {
    this.assertOpen();
    const pending = this.feedback.state.workspace.pendingSketchSave;
    requireValue(!this.temporary && pending && JSON.stringify(pending) === JSON.stringify(value), 409, "The pending proposal save changed.");
    this.feedback.change(state => { state.workspace.sketch = copy(pending.binding); delete state.workspace.pendingSketchSave; });
  }
  confirmSketchSave(value) {
    this.assertOpen();
    requireValue(!this.temporary && !this.feedback.state.workspace.pendingSketchSave &&
      JSON.stringify(this.feedback.state.workspace.sketch) === JSON.stringify(value.binding), 409, "The saved proposal connection changed.");
    // Only an explicit retry after an uncertain commit calls this. Confirm the
    // existing bytes without inventing another feedback change or delivery.
    this.store.persist(this.feedback.state);
  }
  cancelSketchSave(value) {
    this.assertOpen();
    requireValue(JSON.stringify(this.feedback.state.workspace.pendingSketchSave) === JSON.stringify(value), 409, "The pending proposal save changed.");
    this.feedback.change(state => { delete state.workspace.pendingSketchSave; });
  }
  close() { if (this.closed) return; this.closed = true; this.store.close(); }
}

module.exports = { ApplicationWorkspace, validApplicationWorkspaceState, validSketchBinding, validSketchSave, relativeDirectory };
