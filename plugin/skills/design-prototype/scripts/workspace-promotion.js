"use strict";

const crypto = require("node:crypto");
const { FeedbackError, validPersistedFeedback, keys, ID, SCREEN } = require("./feedback-store.js");
const { WorkspaceStore, MAX_STATE_BYTES, MAX_HTML_BYTES, MAX_DESIGN_BYTES, MAX_WORKSPACE_BYTES, MAX_REVISIONS } = require("./workspace-store.js");
const { WorkspaceState, validWorkspaceState, screenIdentity } = require("./workspace-state.js");
const { validDesign } = require("./design-contract.js");
const { validateEditorBindings } = require("./editor-bindings.js");

const requireValue = (ok, status, message) => { if (!ok) throw new FeedbackError(status, message); };
const digest = value => crypto.createHash("sha256").update(value).digest("hex");
const copy = value => JSON.parse(JSON.stringify(value));

// The live child owns this synchronous transition. No renderer is replaced and
// no feedback is resubmitted. The caller owns the durable app/sketch relationship
// and retries an already adopted workspace by its exact identity, not by create.
function promoteTemporaryWorkspace({ feedback, projectDir, workspacePath, workspaceId, title,
  expectedScreen, expectedRevision, currentScreen, readPair, storeFactory = options => new WorkspaceStore(options) } = {}) {
  requireValue(feedback && feedback.persistence == null && feedback.state?.workspace === undefined &&
    validPersistedFeedback(feedback.state) && feedback.state.canvas && typeof readPair === "function" && typeof storeFactory === "function", 409,
  "Only an intact temporary sketch can be saved here.");
  requireValue(typeof workspaceId === "string" && ID.test(workspaceId) && typeof title === "string" && title.trim() &&
    Buffer.byteLength(title.trim()) <= 200 && !/[\u0000-\u001f\u007f]/.test(title), 400, "Invalid saved sketch identity.");
  requireValue(typeof expectedScreen === "string" && SCREEN.test(expectedScreen) && Number.isSafeInteger(expectedRevision) && expectedRevision >= 0,
    400, "Invalid expected sketch state.");
  requireValue(expectedScreen === currentScreen && expectedRevision === feedback.state.revision && feedback.state.screens.at(-1)?.screen === currentScreen,
    409, "The sketch or its feedback changed. Read the current state before saving.");
  requireValue(expectedRevision < Number.MAX_SAFE_INTEGER, 429, "Feedback revision limit reached.");
  requireValue(feedback.state.screens.length > 0 && feedback.state.screens.length <= MAX_REVISIONS, 429, "The sketch exceeds the saved version limit.");

  const original = JSON.stringify(feedback.state), next = JSON.parse(original), filenames = new Set(), pairs = [];
  const savedAt = new Date().toISOString();
  let contentBytes = 0;
  for (const screen of next.screens) {
    requireValue(typeof screen.filename === "string" && /^[a-z0-9][a-z0-9-]{0,95}\.html$/.test(screen.filename) && !filenames.has(screen.filename),
      409, "Temporary sketch versions need distinct, valid filenames.");
    filenames.add(screen.filename);
    const pair = readPair(copy(screen));
    requireValue(keys(pair, ["html", "design"]) && typeof pair.html === "string" && pair.html.trim() &&
      (pair.design === null || validDesign(pair.design)), 409, "A temporary sketch version is unavailable or invalid.");
    const html = pair.html, design = pair.design === null ? null : copy(pair.design), bytes = Buffer.byteLength(html);
    const descriptor = design === null ? null : `${JSON.stringify(design)}\n`;
    requireValue(bytes <= MAX_HTML_BYTES && (descriptor === null || Buffer.byteLength(descriptor) <= MAX_DESIGN_BYTES), 413,
      "A temporary sketch version exceeds its size limit.");
    requireValue(screenIdentity(screen.filename, html, design) === screen.screen && JSON.stringify(screen.design ?? null) === JSON.stringify(design),
      409, "A temporary sketch version changed. Its feedback has not been moved.");
    if (design?.version === 2) validateEditorBindings(html, design);
    contentBytes += bytes + (descriptor === null ? 0 : Buffer.byteLength(descriptor));
    requireValue(contentBytes <= MAX_WORKSPACE_BYTES, 429, "The sketch exceeds the saved workspace size limit.");
    pairs.push({ html, design, meta: { filename: screen.filename, hash: digest(html), designHash: descriptor === null ? null : digest(descriptor), bytes,
      revisionId: pairs.length + 1, screen: screen.screen, label: screen.filename.slice(0, -5), createdAt: savedAt } });
  }
  next.workspace = { id: workspaceId, title: title.trim(), version: pairs.length, revisions: pairs.map(pair => pair.meta) };
  next.revision += 1;
  for (const round of next.canvas.rounds) if (!Object.hasOwn(round, "previousSession")) round.previousSession = false;
  requireValue(validWorkspaceState(next), 409, "The full sketch feedback cannot be saved without changing its history.");
  const stateBytes = Buffer.byteLength(`${JSON.stringify(next)}\n`);
  requireValue(stateBytes <= MAX_STATE_BYTES && stateBytes + contentBytes <= MAX_WORKSPACE_BYTES, 429, "The sketch exceeds the saved workspace size limit.");
  requireValue(JSON.stringify(feedback.state) === original, 409, "The sketch feedback changed before saving.");

  let store, workspaceState, committedError;
  const written = [];
  try {
    store = storeFactory({ projectDir, workspacePath, create: true, title: title.trim(), validateState: validWorkspaceState });
    for (const pair of pairs) {
      const meta = store.writeRevision({ filename: pair.meta.filename, html: pair.html, design: pair.design });
      written.push(meta);
      requireValue(["filename", "hash", "designHash", "bytes"].every(key => meta[key] === pair.meta[key]), 409, "The saved sketch version could not be verified.");
    }
    for (const pair of pairs) {
      const saved = store.readRevision(pair.meta);
      requireValue(saved.html === pair.html && JSON.stringify(saved.design) === JSON.stringify(pair.design), 409,
        "A saved sketch version changed before the workspace was committed.");
    }
    // Validate the saved current pair before the commit. Constructing the handle
    // after commit could fail and leave the caller unable to adopt a saved room.
    workspaceState = new WorkspaceState({ state: next }, store, { path: workspacePath });
    requireValue(JSON.stringify(feedback.state) === original, 409, "The sketch feedback changed before saving.");
    try { store.persist(next); }
    catch (error) { if (error.committed !== true) throw error; committedError = error; }
  } catch (error) {
    for (const meta of written.reverse()) { try { store?.discardRevision(meta); } catch { /* Keep artifacts whose identity is uncertain. */ } }
    try { store?.close(); } catch { /* Preserve the original precommit failure. */ }
    throw error;
  }
  // These are in-memory assignments only. Even a post-rename durability error
  // must return the live handles and retain every committed revision for retry.
  feedback.persistence = store;
  feedback.state = next;
  workspaceState.feedback = feedback;
  return { store, workspaceState, ...(committedError ? { committedError } : {}) };
}

module.exports = { promoteTemporaryWorkspace };
