"use strict";

const crypto = require("node:crypto");
const { FeedbackError, keys, ID } = require("./feedback-store.js");
const { relativeDirectory } = require("./application-workspace.js");
const { validDesign, MAX_DESIGN_BYTES } = require("./design-contract.js");
const { validateEditorBindings, editorBindingErrorMessage } = require("./editor-bindings.js");
const fail = (condition, status, message) => { if (!condition) throw new FeedbackError(status, message); };
const text = value => typeof value === "string" && value.trim() && Buffer.byteLength(value) <= 200 && !/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/.test(value);
const routed = new Set(["readState", "readSubmission", "publishRevision", "reviewSubmission", "updateComment", "markDelivery", "listHistory", "readRevision", "restoreRevision"]);
const copy = value => JSON.parse(JSON.stringify(value));
const requestHash = input => crypto.createHash("sha256").update(JSON.stringify([input.source ?? "app-feedback", input.sourceSubmission ?? null, [...(input.commentIds || [])].sort(), input.title,
  input.filename, input.html, input.design ?? null, input.workspacePath ?? null, input.create ?? null, input.styleProjectPath ?? ""])).digest("hex");
// Child errors cross an IPC boundary. Preserve fixed recovery advice, never
// arbitrary messages containing file paths, source text or field labels.
const publicErrors = new Map([
  [400, new Set(["Invalid sketch revision.", "Invalid sketch version.", "Invalid version restore.", "Invalid content offset."])],
  [404, new Set(["Sketch version was not found in this workspace."])],
  [409, new Set(["Use a new filename for each sketch revision.", "Use a new filename for each sketch version.",
    "Revision filenames are immutable. Use a new filename.", "The sketch changed. Read the current screen before publishing.",
    "The sketch changed. Read the current version before publishing.", "The workspace changed. Review its current state before restoring.",
    "History cursor belongs to a different workspace version.", "A saved sketch no longer matches its recorded version.",
    "Saved design controls no longer match the recorded version.",
    "Mappen for det nye arbeidsrommet er ikke tom. Ingen filer er endret. Velg en annen mappe, eller åpne det eksisterende arbeidet."])],
  [429, new Set(["This workspace has reached its version limit.", "Design workspace storage limit reached.", "Design workspace state limit reached."])],
]);
function proposalError(error) {
  if (error instanceof FeedbackError) return error;
  if (error?.errorCode === "invalid-editor-bindings") return new FeedbackError(400, editorBindingErrorMessage(error));
  const status = Number.isInteger(error?.status) && error.status >= 400 && error.status <= 599 ? error.status : 500;
  if (publicErrors.get(status)?.has(error?.message)) return new FeedbackError(status, error.message);
  if (status === 409 && typeof error?.message === "string" && error.message.startsWith("The revision changes a manually saved field (")) {
    return new FeedbackError(409, "The revision changes a manually saved field. Preserve its value and declaration, or ask the designer to allow later changes in the editor.");
  }
  return new FeedbackError(status, status === 400 ? "Forslaget kunne ikke publiseres. Kontroller innholdet og les gjeldende skissestatus før et nytt forsøk."
    : status === 409 ? "Forslaget kunne ikke bekreftes. Les gjeldende skissestatus og kontroller versjonen før et nytt forsøk."
    : "Forslaget er ikke tilgjengelig akkurat nå. Innspillene dine er beholdt. Les gjeldende status før et nytt forsøk.");
}
function validateBindings(html, design) {
  try { validateEditorBindings(html, design); } catch (error) { throw proposalError(error); }
}

// One proposal uses the existing HTML engine and its own FeedbackStore. This
// registry owns the relationship, lifecycle and exact delivery route; it is not
// another review queue. Runtime capabilities never enter saved workspace data.
class ApplicationProposals {
  constructor({ workspace, projectDir, backendFactory, onSubmitted = () => {} }) {
    this.workspace = workspace; this.projectDir = projectDir; this.backendFactory = backendFactory; this.onSubmitted = onSubmitted;
    const saved = workspace.feedback.state.workspace.sketch, pending = workspace.feedback.state.workspace.pendingSketchSave;
    this.entry = saved ? { binding: copy(saved) } : pending ? { binding: copy(pending.binding), recoveringSave: true } : null;
    this.selected = null; this.epoch = 0; this.closed = false;
  }
  assertOpen() { fail(!this.closed, 410, "This design workshop is closed."); this.workspace.assertOpen(); }
  async ensure(entry) {
    this.assertOpen();
    if (!entry.backend) {
      const binding = entry.binding;
      entry.backend = Promise.resolve().then(() => this.backendFactory({ projectDir: this.projectDir,
        ...(binding.workspacePath === undefined ? {} : { workspacePath: binding.workspacePath }),
        ...(entry.create ? { create: true, title: binding.title } : {}),
        ...(binding.styleProjectPath === undefined ? {} : { styleProjectPath: binding.styleProjectPath }),
        onSubmitted: submission => { if (!this.closed && this.entry === entry) this.onSubmitted(submission, binding.id); },
      })).then(async backend => {
        try {
          await backend.closeView({});
          const state = await backend.readState({});
          if (binding.workspaceId) fail(state.workspace?.id === binding.workspaceId, 409, "The linked sketch has been replaced. Its feedback has not been connected to this work.");
          entry.state = state;
          if (this.closed || this.entry !== entry) { await backend.retire({}); throw new FeedbackError(410, "This design workshop is closed."); }
          return backend;
        } catch (error) { await backend.retire({}).catch(() => {}); throw proposalError(error); }
      }, error => {
        const saved = this.workspace.feedback.state.workspace;
        // Only a never-ready child whose shutdown is confirmed is safe to
        // replace. A durable/pending link or uncertain startup stays bound.
        if (error?.backendStopped === true && error.backendWasReady === false && this.entry === entry &&
            !binding.workspaceId && !entry.recoveringSave && !saved.sketch && !saved.pendingSketchSave) this.entry = null;
        throw proposalError(error);
      });
    }
    return entry.backend;
  }
  async publish(input) {
    this.assertOpen();
    fail(keys(input, ["title", "filename", "html"], ["source", "sourceSubmission", "commentIds", "design", "workspacePath", "create", "styleProjectPath"]) && text(input.title) &&
      typeof input.filename === "string" && /^[a-z0-9][a-z0-9-]{0,95}\.html$/.test(input.filename) && typeof input.html === "string" && input.html.trim() && Buffer.byteLength(input.html) <= 2 * 1024 * 1024 &&
      [undefined, "conversation", "app-feedback"].includes(input.source), 400, "Invalid proposal publication.");
    const source = input.source ?? "app-feedback";
    fail(input.design === undefined || validDesign(input.design) && Buffer.byteLength(JSON.stringify(input.design)) <= MAX_DESIGN_BYTES, 400, "Invalid proposal controls.");
    if (input.design?.version === 2) validateBindings(input.html, input.design);
    if (source === "conversation") fail(!Object.hasOwn(input, "sourceSubmission") && !Object.hasOwn(input, "commentIds"), 400, "A conversation proposal does not invent a feedback round.");
    else fail(Number.isSafeInteger(input.sourceSubmission) && input.sourceSubmission > 0 && Array.isArray(input.commentIds) && input.commentIds.length > 0 && input.commentIds.length <= 200 &&
      new Set(input.commentIds).size === input.commentIds.length && input.commentIds.every(id => typeof id === "string" && ID.test(id)), 400, "Invalid proposal feedback source.");
    fail(input.workspacePath === undefined ? input.create === undefined : relativeDirectory(input.workspacePath) && input.create === true,
      400, "A saved proposal needs an explicitly chosen new workspace.");
    fail(input.styleProjectPath === undefined || input.styleProjectPath === "" || relativeDirectory(input.styleProjectPath), 400, "Invalid proposal style project.");
    if (source === "app-feedback") {
      const batch = this.workspace.feedback.state.submissions.find(item => item.submission === input.sourceSubmission);
      fail(batch && input.commentIds.every(id => batch.comments.some(comment => comment.id === id)), 404, "The proposal must answer comments in this app's exact submitted round.");
    }
    fail(input.workspacePath === undefined || input.workspacePath !== this.workspace.path, 409, "The app reference and sketch have separate saved content.");
    const fingerprint = requestHash(input);
    if (this.entry) fail(this.entry.binding.requestHash === fingerprint, 409, "This work already has a proposal. Read it with proposalId and publish its next revision.");
    else this.entry = { create: input.create === true, binding: { id: crypto.randomBytes(12).toString("hex"), title: input.title.trim(),
      source, ...(source === "app-feedback" ? { sourceSubmission: input.sourceSubmission, commentIds: [...input.commentIds] } : {}), requestHash: fingerprint,
      ...(input.workspacePath === undefined ? {} : { workspacePath: input.workspacePath }),
      ...(input.styleProjectPath === undefined ? {} : { styleProjectPath: input.styleProjectPath }) } };
    const entry = this.entry, backend = await this.ensure(entry);
    this.assertOpen();
    let before;
    try { before = await backend.readState({}); } catch (error) { throw proposalError(error); }
    if (!this.workspace.temporary && input.workspacePath !== undefined) {
      fail(typeof before.workspace?.id === "string" && ID.test(before.workspace.id), 409, "The sketch workspace identity could not be verified.");
      entry.binding.workspaceId = before.workspace.id;
      // Record the relationship before publication. A stopped first publication
      // remains an empty, retryable sketch, never an untracked duplicate.
      this.workspace.bindSketch(entry.binding);
    }
    if (!before.screen) {
      try { entry.state = await backend.publishRevision({ expectedScreen: "", filename: input.filename, html: input.html,
        ...(input.design === undefined ? {} : { design: input.design }) }); }
      catch (error) { throw proposalError(error); }
    }
    else entry.state = before; // Same initial request after a lost reply is one proposal.
    return this.describe(entry);
  }
  describe(entry) {
    const { id, title, source, sourceSubmission, commentIds } = entry.binding, state = entry.state;
    const pending = this.workspace.feedback.state.workspace.pendingSketchSave || entry.saveConfirmation;
    return { id, title, source, ...(source === "app-feedback" ? { sourceSubmission, commentIds: [...commentIds] } : {}), available: Boolean(state?.screen), screen: state?.screen || "",
      ...(state?.workspace?.version ? { revisionId: state.workspace.version } : {}), storage: entry.binding.workspacePath !== undefined && !pending ? "project" : "temporary",
      ...(pending ? { pendingSave: { workspacePath: pending.binding.workspacePath, expectedScreen: pending.expectedScreen, expectedRevision: pending.expectedRevision } } : {}) };
  }
  async summary() {
    this.assertOpen();
    const entry = this.entry;
    if (!entry) return [];
    try { const backend = await this.ensure(entry); entry.state = await backend.readState({}); }
    catch { entry.state = null; }
    return this.entry === entry ? [this.describe(entry)] : [];
  }
  async action(method, input) {
    this.assertOpen();
    const { proposalId, ...params } = input;
    fail(typeof proposalId === "string" && ID.test(proposalId) && this.entry?.binding.id === proposalId, 404, "The proposal does not belong to this workshop.");
    if (method === "saveProposal") return this.save(params);
    fail(routed.has(method), 400, "This proposal action is unavailable.");
    fail(this.entry.binding.workspacePath !== undefined || !["listHistory", "readRevision", "restoreRevision"].includes(method), 409,
      "Forslaget er midlertidig og har ingen lagret versjonshistorikk. Bruk read_state for gjeldende skisse. Ingen filer er endret.");
    if (method === "publishRevision" && params.design?.version === 2 && validDesign(params.design) &&
        typeof params.html === "string" && Buffer.byteLength(params.html) <= 2 * 1024 * 1024) validateBindings(params.html, params.design);
    const backend = await this.ensure(this.entry);
    let result;
    try { result = await backend[method](params); } catch (error) { throw proposalError(error); }
    if (result?.screen !== undefined) this.entry.state = result;
    return result;
  }
  async save(input) {
    this.assertOpen();
    fail(keys(input, ["workspacePath", "expectedScreen", "expectedRevision"]) && relativeDirectory(input.workspacePath) &&
      typeof input.expectedScreen === "string" && /^[a-f0-9]{32}$/.test(input.expectedScreen) && Number.isSafeInteger(input.expectedRevision) && input.expectedRevision >= 0,
      400, "Invalid proposal save request.");
    fail(!this.workspace.temporary, 409, "Apprommet er midlertidig. Senere lagring av hele dette verkstedet støttes ikke ennå. Ingenting er flyttet eller lagret som et nytt verksted.");
    fail(input.workspacePath !== this.workspace.path && !input.workspacePath.startsWith(this.workspace.path + "/") && !this.workspace.path.startsWith(input.workspacePath + "/"),
      409, "Velg en egen ny mappe for forslaget ved siden av apprommet.");
    const entry = this.entry;
    let pending = this.workspace.feedback.state.workspace.pendingSketchSave;
    if (!pending && entry.binding.workspacePath !== undefined) {
      fail(entry.binding.workspacePath === input.workspacePath, 409, "Forslaget er allerede lagret et annet sted. Det er ikke flyttet eller kopiert.");
      const backend = await this.ensure(entry); entry.state = await backend.readState({});
      fail(entry.state.workspace?.id === entry.binding.workspaceId, 409, "Det lagrede forslaget har en annen identitet.");
      if (entry.saveConfirmation) {
        fail(entry.saveConfirmation.expectedScreen === input.expectedScreen && entry.saveConfirmation.expectedRevision === input.expectedRevision, 409,
          "Gjenta den samme lagringshandlingen fra pendingSave for å bekrefte koblingen.");
        try { this.workspace.confirmSketchSave(entry.saveConfirmation); }
        catch { throw new FeedbackError(503, "Koblingen er skrevet, men lagringen er fortsatt ikke bekreftet. Gjenta samme lagringshandling."); }
        delete entry.saveConfirmation;
      }
      return this.describe(entry);
    }
    if (pending) fail(pending.binding.id === entry.binding.id && pending.binding.workspacePath === input.workspacePath &&
      pending.expectedScreen === input.expectedScreen && pending.expectedRevision === input.expectedRevision, 409,
      "En lagring venter på bekreftelse. Gjenta den samme lagringshandlingen fra pendingSave i read_state.");
    let backend;
    try { backend = await this.ensure(entry); }
    catch (error) {
      if (!pending) throw error;
      throw new FeedbackError(409, "Den påbegynte lagringen kan ikke åpnes og verifiseres. Ingen erstatning er opprettet. Behold prosjektfilene og kontroller den valgte målmappen før lagringen fortsettes.");
    }
    if (!pending) {
      const before = await backend.readState({});
      fail(before.screen === input.expectedScreen && before.revision === input.expectedRevision && !before.workspace, 409,
        "Forslaget eller innspillene er endret. Les gjeldende skissestatus før lagring.");
      pending = { binding: { ...copy(entry.binding), workspacePath: input.workspacePath, workspaceId: crypto.randomBytes(12).toString("hex") },
        expectedScreen: input.expectedScreen, expectedRevision: input.expectedRevision };
      this.workspace.beginSketchSave(pending);
    }
    try {
      entry.state = await backend.saveWorkspace({ workspacePath: pending.binding.workspacePath, workspaceId: pending.binding.workspaceId, title: pending.binding.title,
        expectedScreen: pending.expectedScreen, expectedRevision: pending.expectedRevision });
    } catch (error) {
      // The child emits these statuses only before its commit. A timeout or
      // durability warning is uncertain: preserve the durable recovery link.
      const beforeCommit = !entry.recoveringSave && [400, 409, 413, 429].includes(error?.status);
      if (beforeCommit) this.workspace.cancelSketchSave(pending);
      throw new FeedbackError(beforeCommit ? 409 : 503, beforeCommit
        ? "Forslaget ble ikke lagret. Kontroller at målmappen er ny og at skissen og innspillene er uendret; les gjeldende status før et nytt forsøk."
        : "Lagringen er ikke bekreftet. Gjenta samme lagringshandling; det er ikke opprettet et nytt forslag.");
    }
    fail(entry.state.workspace?.id === pending.binding.workspaceId, 503, "Lagringen kunne ikke knyttes til riktig forslag. Gjenta samme lagringshandling.");
    try { this.workspace.finishSketchSave(pending); }
    catch {
      if (!this.workspace.feedback.state.workspace.pendingSketchSave && this.workspace.feedback.state.workspace.sketch?.workspaceId === pending.binding.workspaceId) {
        entry.binding = copy(pending.binding); entry.recoveringSave = false;
        entry.saveConfirmation = copy(pending);
      }
      throw new FeedbackError(503, "Forslaget er skrevet til prosjektet, men koblingen er ikke bekreftet. Gjenta samme lagringshandling for å fullføre; ikke opprett et nytt forslag.");
    }
    entry.binding = copy(pending.binding); entry.recoveringSave = false;
    return this.describe(entry);
  }
  select(id) {
    this.assertOpen(); fail(id === null || typeof id === "string" && ID.test(id) && this.entry?.binding.id === id, 404, "The proposal does not belong to this workshop.");
    this.selected = id;
  }
  async openView(id, embedding) {
    this.assertOpen(); fail(typeof id === "string" && ID.test(id) && this.entry?.binding.id === id, 404, "The proposal does not belong to this workshop.");
    const epoch = this.epoch, entry = this.entry, backend = await this.ensure(entry);
    fail(!this.closed && epoch === this.epoch, 410, "This workshop view has been replaced.");
    if (entry.view && entry.view.epoch === epoch && entry.view.parentOrigin === embedding.parentOrigin && entry.view.leaseId === embedding.leaseId) return entry.view.result;
    const state = await backend.readState({}); entry.state = state;
    fail(state.screen, 409, "Forslaget er ikke klart ennå. Innspillene dine er beholdt.");
    const result = await backend.openView({ embedding });
    if (this.closed || epoch !== this.epoch) { await backend.closeView({}); throw new FeedbackError(410, "This workshop view has been replaced."); }
    entry.view = { epoch, ...embedding, result };
    return result;
  }
  closeViews() {
    this.epoch += 1;
    if (this.entry) this.entry.view = null;
    const backend = this.entry?.backend;
    return backend ? backend.then(value => value.closeView({}), () => {}).then(() => {}) : Promise.resolve();
  }
  async close() {
    this.closed = true; this.epoch += 1;
    if (this.entry?.backend) await this.entry.backend.then(value => value.retire({}), () => {});
  }
}
module.exports = { ApplicationProposals };
