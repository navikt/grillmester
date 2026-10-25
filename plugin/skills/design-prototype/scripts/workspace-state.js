"use strict";

const crypto = require("node:crypto");
const { FeedbackError, keys, ID, SCREEN, validPersistedFeedback } = require("./feedback-store.js");
const { validDesign, validEditableText } = require("./design-contract.js");
const { editorFields, validHolds, conflictingHolds, holdFor, setField } = require("./editor-contract.js");
const { validateEditorBindings, materializeEditorValues } = require("./editor-bindings.js");

const PAGE_BYTES = 64 * 1024;
const filenamePattern = /^[a-z0-9][a-z0-9-]{0,95}\.html$/;
const hashPattern = /^[a-f0-9]{64}$/;
const integer = (value, minimum = 0, maximum = Number.MAX_SAFE_INTEGER) => Number.isSafeInteger(value) && value >= minimum && value <= maximum;
const text = (value, maximum = 200) => typeof value === "string" && value.trim().length > 0 && Buffer.byteLength(value) <= maximum && !/[\u0000-\u001f\u007f]/.test(value);
const requireValue = (value, status, message) => { if (!value) throw new FeedbackError(status, message); };

function validWorkspaceState(state) {
  try {
    if (!validPersistedFeedback(state) || !state.canvas || state.canvas.rounds.some(round => typeof round.previousSession !== "boolean") || !keys(state.workspace, ["id", "title", "version", "revisions"], ["holds"])) return false;
    const workspace = state.workspace;
    if (typeof workspace.id !== "string" || !ID.test(workspace.id) || !text(workspace.title) || !integer(workspace.version, 0, 100) ||
        !Array.isArray(workspace.revisions) || workspace.revisions.length !== workspace.version || state.screens.length !== workspace.version) return false;
    if (!validHolds(workspace.holds ?? [], state.screens.at(-1)?.design ?? null)) return false;
    const filenames = new Set();
    return workspace.revisions.every((item, index) => {
      if (!keys(item, ["revisionId", "filename", "hash", "designHash", "bytes", "screen", "label", "createdAt"], ["restoredFrom"]) ||
          item.revisionId !== index + 1 || typeof item.filename !== "string" || !filenamePattern.test(item.filename) || filenames.has(item.filename) ||
          typeof item.hash !== "string" || !hashPattern.test(item.hash) || !(item.designHash === null || typeof item.designHash === "string" && hashPattern.test(item.designHash)) ||
          !integer(item.bytes, 1, 2 * 1024 * 1024) || typeof item.screen !== "string" || !SCREEN.test(item.screen) || !text(item.label) ||
          typeof item.createdAt !== "string" || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(item.createdAt) || !Number.isFinite(Date.parse(item.createdAt)) ||
          Object.hasOwn(item, "restoredFrom") && !integer(item.restoredFrom, 1, index) ||
          state.screens[index].screen !== item.screen || state.screens[index].filename !== item.filename) return false;
      filenames.add(item.filename);
      return true;
    });
  } catch { return false; }
}

function screenIdentity(filename, html, design) {
  const digest = crypto.createHash("sha256").update(filename).update("\0").update(html);
  if (design !== null) digest.update("\0design\0").update(JSON.stringify(design));
  return digest.digest("hex").slice(0, 32);
}

// State and review history are committed by FeedbackStore in workspace.json.
// Revision files are immutable inputs to that one atomic state transition.
class WorkspaceState {
  constructor(feedback, store, { path, recovered = false }) {
    this.feedback = feedback;
    this.store = store;
    this.path = path;
    this.recovered = recovered;
    // Verify the current pair before use. Older pairs are verified by their
    // hashes when read or restored, so one damaged old file cannot lock the room.
    for (const revision of feedback.state.workspace.revisions.slice(-1)) {
      const content = store.readRevision(revision);
      if (content.design?.version === 2) validateEditorBindings(content.html, content.design);
      requireValue(screenIdentity(revision.filename, content.html, content.design) === revision.screen, 409, "A saved sketch no longer matches its recorded version.");
      const screen = feedback.state.screens.find(item => item.screen === revision.screen);
      requireValue(JSON.stringify(screen?.design ?? null) === JSON.stringify(content.design), 409, "Saved design controls no longer match the recorded version.");
    }
    if (recovered && feedback.state.canvas.rounds.length) {
      const state = JSON.parse(JSON.stringify(feedback.state));
      for (const round of state.canvas.rounds) {
          round.previousSession = true;
          if (round.delivery === "sending") round.delivery = "unknown";
      }
      // No client from the old process survives its token/IPC boundary. Mark that
      // in memory only: opening a room never rewrites it, so a read-only checkout
      // opens and version control shows no change. The next real write saves it.
      feedback.state = state;
    }
  }
  summary() {
    const { id, title, version, revisions } = this.feedback.state.workspace;
    return { id, title, path: this.path, version, recovered: this.recovered, historyCount: revisions.length, storage: "project",
      preservedFields: (this.feedback.state.workspace.holds ?? []).map(({ id, label, value }) => ({ id, label, value })) };
  }
  current() {
    const workspace = this.feedback.state.workspace;
    if (!workspace.version) return null;
    const revision = workspace.revisions[workspace.version - 1];
    const { html, design } = this.store.readRevision(revision);
    return { filename: revision.filename, screen: revision.screen, content: html, design, designError: false };
  }
  find(revisionId) {
    requireValue(integer(revisionId, 1), 400, "Invalid sketch version.");
    const revision = this.feedback.state.workspace.revisions.find(item => item.revisionId === revisionId);
    requireValue(revision, 404, "Sketch version was not found in this workspace.");
    return revision;
  }
  history(input) {
    requireValue(keys(input, [], ["after", "limit"]) && (!Object.hasOwn(input, "after") || integer(input.after)) &&
      (!Object.hasOwn(input, "limit") || integer(input.limit, 1, 20)), 400, "Invalid version history page.");
    const after = input.after ?? 0, limit = input.limit ?? 20;
    requireValue(after <= this.feedback.state.workspace.version, 409, "History cursor belongs to a different workspace version.");
    const candidates = this.feedback.state.workspace.revisions.filter(item => !after || item.revisionId < after).slice().reverse();
    const items = candidates.slice(0, limit).map(({ revisionId, filename, label, createdAt, restoredFrom }) =>
      ({ revisionId, filename, label, createdAt, ...(restoredFrom === undefined ? {} : { restoredFrom }) }));
    const hasMore = candidates.length > items.length;
    return { items, nextAfter: hasMore ? items[items.length - 1].revisionId : null, hasMore };
  }
  // A stored version shown read-only: its saved values are written into the
  // HTML exactly as a restore would publish them, and nothing is changed.
  view(revisionId) {
    const revision = this.find(revisionId);
    const saved = this.store.readRevision(revision);
    return { revisionId: revision.revisionId, filename: revision.filename, screen: revision.screen,
      html: materializeEditorValues(saved.html, saved.design), design: saved.design };
  }
  read(input) {
    requireValue(keys(input, ["revisionId", "part"], ["offset"]) && ["html", "design"].includes(input.part) &&
      (!Object.hasOwn(input, "offset") || integer(input.offset)), 400, "Invalid sketch version page.");
    const revision = this.find(input.revisionId);
    const saved = this.store.readRevision(revision);
    const source = input.part === "html" ? saved.html : JSON.stringify(saved.design);
    const offset = input.offset ?? 0;
    requireValue(offset <= source.length && !(offset > 0 && /[\uDC00-\uDFFF]/.test(source[offset] || "") && /[\uD800-\uDBFF]/.test(source[offset - 1])), 400, "Invalid content offset.");
    let end = Math.min(source.length, offset + 32 * 1024);
    const result = () => ({ revisionId: revision.revisionId, part: input.part, content: source.slice(offset, end),
      nextOffset: end < source.length ? end : null, hasMore: end < source.length, totalCharacters: source.length });
    while (Buffer.byteLength(JSON.stringify(result())) > PAGE_BYTES) end = offset + Math.floor((end - offset) / 2);
    if (end < source.length && /[\uD800-\uDBFF]/.test(source[end - 1] || "")) end -= 1;
    return result();
  }
  publish({ expectedScreen, filename, html, design = null, label }, restoredFrom, editedHolds) {
    const workspace = this.feedback.state.workspace;
    requireValue(typeof filename === "string" && filenamePattern.test(filename) && typeof html === "string" && html.trim() &&
      (design === null || validDesign(design)) && (label === undefined || text(label)), 400, "Invalid sketch revision.");
    const before = workspace.revisions[workspace.version - 1];
    requireValue(expectedScreen === (before?.screen || ""), 409, "The sketch changed. Read the current version before publishing.");
    requireValue(workspace.version < 100, 429, "This workspace has reached its version limit.");
    requireValue(!workspace.revisions.some(item => item.filename === filename), 409, "Use a new filename for each sketch version.");
    const holds = editedHolds ?? workspace.holds ?? [];
    const conflicts = conflictingHolds(holds, design).map(({ id, label }) => ({ id, label }));
    if (conflicts.length) throw this.editorConflict(`The revision changes a manually saved field (${conflicts.map(item => item.label).join(", ")}). Preserve its value and declaration, or ask the designer to allow later changes in the editor.`, conflicts);
    if (design?.version === 2) validateEditorBindings(html, design);
    const saved = this.store.writeRevision({ filename, html, design });
    const revisionId = workspace.version + 1;
    const screen = screenIdentity(filename, html, design);
    try {
      this.feedback.change(state => {
        state.workspace.revisions.push({ ...saved, revisionId, screen,
          label: label || (restoredFrom ? `Gjenopprettet fra versjon ${restoredFrom}` : filename.replace(/\.html$/i, "")),
          createdAt: new Date().toISOString(), ...(restoredFrom ? { restoredFrom } : {}) });
        state.workspace.version = revisionId;
        if (editedHolds !== undefined) state.workspace.holds = editedHolds;
        state.screens.push({ screen, filename, ...(design === null ? {} : { design }) });
      });
    } catch (error) {
      if (error.committed !== true) {
        try { this.store.discardRevision(saved); } catch { /* Leave an uncommitted artifact when ownership is uncertain. */ }
      }
      throw error;
    }
    return this.summary();
  }
  editorConflict(message, conflicts = []) {
    return Object.assign(new FeedbackError(409, message), { errorCode: "editor-conflict", conflicts });
  }
  editorRead(input) {
    requireValue(keys(input, []), 400, "Invalid editor read.");
    const current = this.current();
    const holds = this.feedback.state.workspace.holds ?? [];
    const fields = editorFields(current?.design).map(({ signature, ...field }) => ({ ...field, locked: holds.some(hold => hold.id === field.id) }));
    return { screen: current?.screen ?? "", revision: this.feedback.state.revision, workspaceVersion: this.feedback.state.workspace.version,
      fields, holds: holds.map(({ id, label, value }) => ({ id, label, value })) };
  }
  checkEditorVersion(input) {
    requireValue(integer(input.expectedRevision) && typeof input.screen === "string" && SCREEN.test(input.screen), 400, "Invalid editor version.");
    const current = this.current();
    requireValue(input.expectedRevision === this.feedback.state.revision && input.screen === current?.screen, 409, "The workspace changed. Review the current version before saving.");
    requireValue(current.design?.version === 2, 409, "This sketch has no editable source fields.");
    return current;
  }
  editorSave(input) {
    requireValue(keys(input, ["screen", "expectedRevision", "changes"]) && Array.isArray(input.changes) && input.changes.length > 0 && input.changes.length <= 32 &&
      input.changes.every(item => keys(item, ["id", "value"]) && typeof item.id === "string" && validEditableText(item.value)) &&
      new Set(input.changes.map(item => item.id)).size === input.changes.length, 400, "Invalid source edits.");
    const current = this.checkEditorVersion(input);
    const fields = editorFields(current.design);
    const nextDesign = JSON.parse(JSON.stringify(current.design));
    const holds = new Map((this.feedback.state.workspace.holds ?? []).map(item => [item.id, item]));
    let changed = false;
    for (const change of input.changes) {
      const field = fields.find(item => item.id === change.id);
      requireValue(field && (field.kind === "text" || field.options.some(option => option.value === change.value)), 400, "Unknown editable field or value.");
      if (field.value === change.value) continue;
      if (field.kind === "control") {
        const [variant, target, control] = field.id.slice("control:".length).split("/");
        if (this.feedback.state.decisions.some(item => item.state === "active" && item.variant === variant && item.target === target &&
          Object.hasOwn(item.values, control) && item.values[control] !== change.value)) {
          throw this.editorConflict("The edit conflicts with a kept choice. Release or update that choice before saving.");
        }
      }
      changed = true;
      setField(nextDesign, field.id, change.value);
      holds.set(field.id, holdFor({ ...field, value: change.value }));
    }
    requireValue(changed, 400, "There are no changed source fields to save.");
    const version = this.feedback.state.workspace.version + 1;
    return this.publish({ expectedScreen: current.screen, filename: `edited-v${version}-${crypto.randomBytes(4).toString("hex")}.html`,
      html: materializeEditorValues(current.content, nextDesign), design: nextDesign, label: "Redigert skisse" }, undefined, [...holds.values()]);
  }
  editorRelease(input) {
    requireValue(keys(input, ["screen", "expectedRevision", "ids"]) && Array.isArray(input.ids) && input.ids.length > 0 && input.ids.length <= 32 &&
      input.ids.every(id => typeof id === "string") && new Set(input.ids).size === input.ids.length, 400, "Invalid field release.");
    this.checkEditorVersion(input);
    const holds = this.feedback.state.workspace.holds ?? [];
    requireValue(input.ids.every(id => holds.some(item => item.id === id)), 409, "A preserved field changed. Review the editor before releasing it.");
    this.feedback.change(state => { state.workspace.holds = holds.filter(item => !input.ids.includes(item.id)); });
    return this.summary();
  }
  restore(input) {
    requireValue(keys(input, ["revisionId", "expectedRevision"]) && integer(input.expectedRevision), 400, "Invalid version restore.");
    requireValue(input.expectedRevision === this.feedback.state.revision, 409, "The workspace changed. Review its current state before restoring.");
    const revision = this.find(input.revisionId);
    const saved = this.store.readRevision(revision);
    const current = this.feedback.state.workspace;
    return this.publish({ expectedScreen: current.revisions[current.version - 1]?.screen || "",
      filename: `restored-${revision.revisionId}-v${current.version + 1}-${crypto.randomBytes(4).toString("hex")}.html`,
      html: materializeEditorValues(saved.html, saved.design), design: saved.design }, revision.revisionId);
  }
}

module.exports = { WorkspaceState, validWorkspaceState, screenIdentity };
