"use strict";

const { FeedbackError, keys, ID } = require("./feedback-store.js");
const PAGE_BYTES = 64 * 1024;
function requireValue(ok, status, message) { if (!ok) throw new FeedbackError(status, message); }
function text(value) { return typeof value === "string" && Buffer.byteLength(value) <= 2000 && !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value); }
function submission(value) { return Number.isSafeInteger(value) && value > 0; }

// This is an interface to the existing store, not another queue or writer.
class CanvasState {
  constructor(feedback) { this.feedback = feedback; }
  round(number) {
    requireValue(submission(number), 400, "Invalid submitted round.");
    const round = this.feedback.state.canvas?.rounds.find(item => item.submission === number);
    requireValue(round, 404, "Round does not belong to this canvas.");
    return round;
  }
  summary() {
    const state = this.feedback.state;
    return { revision: state.revision, submission: state.submission,
      canvas: { rounds: state.canvas.rounds.map(({ reply, ...round }) => ({ ...round, replyAvailable: Boolean(reply) })) } };
  }
  read(input) {
    requireValue(keys(input, ["submission"], ["offset"]) && (!Object.hasOwn(input, "offset") || Number.isSafeInteger(input.offset) && input.offset >= 0), 400, "Invalid round page.");
    const round = this.round(input.submission);
    const batch = this.feedback.nextSubmission(input.submission - 1);
    requireValue(batch.submission === input.submission, 404, "Round is unavailable.");
    const entries = [
      ...batch.screens.map(value => ({ type: "screen", value })),
      ...batch.comments.map((value, index) => ({ type: "comment", value, current: batch.currentComments[index] })),
    ];
    const offset = input.offset ?? 0;
    requireValue(offset <= entries.length, 400, "Round page offset is out of range.");
    const page = { submission: batch.submission, revision: batch.revision, submittedAt: batch.submittedAt,
      round: { ...round }, items: [], nextOffset: null, hasMore: false };
    let cursor = offset;
    while (cursor < entries.length && page.items.length < 32) {
      const entry = entries[cursor];
      if (Buffer.byteLength(JSON.stringify({ ...page, items: [...page.items, entry] })) > PAGE_BYTES - 128) break;
      page.items.push(entry); cursor += 1;
    }
    requireValue(cursor > offset || offset === entries.length, 413, "Round entry exceeds the page limit.");
    page.hasMore = cursor < entries.length;
    page.nextOffset = page.hasMore ? cursor : null;
    return JSON.parse(JSON.stringify(page));
  }
  delivery(input) {
    requireValue(keys(input, ["submission", "status"]) && ["queued", "unknown"].includes(input.status), 400, "Invalid delivery acknowledgement.");
    const round = this.round(input.submission);
    requireValue(!round.previousSession, 409, "This delivery belongs to a previous session.");
    // A late timeout cannot undo an actual receipt, or an explicit review.
    if (round.delivery === input.status || round.delivery === "queued" || input.status === "unknown" && round.review !== "unread") return;
    this.feedback.change(state => { state.canvas.rounds.find(item => item.submission === input.submission).delivery = input.status; });
  }
  review(input) {
    requireValue(keys(input, ["submission", "status", "reply"]) && ["working", "answered"].includes(input.status) && text(input.reply) && (input.status !== "answered" || input.reply.trim()), 400, "Invalid round review.");
    const round = this.round(input.submission);
    requireValue(round.review !== "answered" || input.status === "answered", 409, "An answered round cannot return to working.");
    if (round.review === input.status && round.reply === input.reply && !round.previousSession) return;
    this.feedback.change(state => {
      const target = state.canvas.rounds.find(item => item.submission === input.submission);
      target.review = input.status; target.reply = input.reply;
      target.previousSession = false;
    });
  }
  updateComment(input) {
    requireValue(keys(input, ["id", "submission"], ["status", "reply"]) && typeof input.id === "string" && ID.test(input.id) && (Object.hasOwn(input, "status") || Object.hasOwn(input, "reply")), 400, "Invalid comment review.");
    this.round(input.submission);
    const batch = this.feedback.state.submissions.find(item => item.submission === input.submission);
    requireValue(batch.comments.some(item => item.id === input.id), 404, "Comment is not part of this round.");
    const { id, submission: expectedSubmission, ...patch } = input;
    return this.feedback.patch(id, { ...patch, expectedSubmission });
  }
}
module.exports = { CanvasState, PAGE_BYTES };
