"use strict";

const crypto = require("node:crypto");
const { FeedbackError } = require("./feedback-store.js");
const INVITATION_MS = 5 * 60 * 1000;
const MAX_CANDIDATES = 8;
function stale() {
  const error = new FeedbackError(410, "Visningen er ikke aktiv. Kopier eventuell ulagret tekst. Lukk dette canvaset før du ber i samtalen om å åpne verkstedet igjen.");
  error.code = "renderer-stale"; return error;
}
// All authority is volatile. A fetched invitation is a candidate, never a writer.
function createConnectionState({ now = Date.now } = {}) {
  let invitation = null, generation = null, expires = 0, active = null, bootstrap = null, resumed = null, closed = false;
  const candidates = new Map();
  const secret = () => crypto.randomBytes(32).toString("hex");
  return {
    prepare() {
      if (closed) throw stale();
      invitation = `/browser/${secret()}`; generation = crypto.randomBytes(16).toString("hex"); expires = now() + INVITATION_MS;
      active = null; bootstrap = null; resumed = null; candidates.clear(); return invitation;
    },
    revoke() { invitation = null; active = null; bootstrap = null; resumed = null; candidates.clear(); },
    close() { closed = true; this.revoke(); },
    get path() { return invitation; },
    get generation() { return generation; },
    candidate(requestPath) {
      if (closed || requestPath !== invitation || now() >= expires) throw stale();
      for (const [token, expiry] of candidates) if (expiry <= now() && token !== active) candidates.delete(token);
      if (candidates.size >= MAX_CANDIDATES) throw new FeedbackError(429, "For mange åpneforsøk. Kopier eventuell ulagret tekst. Lukk dette canvaset før du ber i samtalen om å åpne verkstedet igjen.");
      const token = secret(); candidates.set(token, Math.min(expires, now() + INVITATION_MS)); return token;
    },
    bootstrapCandidate(requestPath) {
      if (closed || requestPath !== invitation) throw stale();
      // Reloading may present the already validated capability from this tab.
      // The public invitation itself never recovers or replaces a writer.
      if (active || now() >= expires || candidates.size >= MAX_CANDIDATES) return null;
      return this.candidate(requestPath);
    },
    activate(token, createBootstrap, resume) {
      if (closed || typeof token !== "string" || !/^[a-f0-9]{64}$/.test(token)) throw stale();
      if (resume && (!resume || Object.keys(resume).length !== 2 || !/^[a-f0-9]{32}$/.test(resume.resumeId || "") || !/^[a-f0-9]{32}$/.test(resume.expectedReportGeneration || ""))) throw stale();
      if (active === token) {
        if (!resume || resumed?.resumeId === resume.resumeId && resumed.expectedReportGeneration === resume.expectedReportGeneration) return bootstrap;
        if (resume.expectedReportGeneration !== bootstrap.reportGeneration) throw stale();
        // Renew only page diagnostics, never the writer or application proxy.
        bootstrap = createBootstrap(); resumed = { ...resume }; return bootstrap;
      }
      if (resume) throw stale();
      if (active || !candidates.has(token) || candidates.get(token) <= now() || now() >= expires) throw stale();
      bootstrap = createBootstrap(); active = token; return bootstrap;
    },
    authorize(token) {
      if (closed || typeof token !== "string" || !/^[a-f0-9]{64}$/.test(token) || !active || !crypto.timingSafeEqual(Buffer.from(active), Buffer.from(token))) throw stale();
    },
    status() {
      // Expiry limits opening, not the lifetime of an already active view.
      return { state: closed ? "closed" : active ? "connected" : candidates.size ? "connecting" : "waiting", invitationExpired: !active && (!invitation || now() >= expires) };
    },
  };
}
module.exports = { createConnectionState, INVITATION_MS, MAX_CANDIDATES };
