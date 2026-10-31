"use strict";

const http = require("node:http");
const crypto = require("node:crypto");
const { FeedbackError } = require("./feedback-store.js");
const { listenLocal } = require("./local-ports.js");
const MAX_SNAPSHOT_BYTES = 12 * 1024 * 1024;
const INSPECTION_TTL_MS = 10 * 60 * 1000;

// A separate origin serves one immutable document. It never receives the
// workshop token, reads project files, or implements feedback/control routes.
function createHtmlInspection({ ttlMs = INSPECTION_TTL_MS } = {}) {
  let current = null, epoch = 0;
  const revoke = entry => {
    if (!entry) return Promise.resolve();
    entry.active = false; clearTimeout(entry.timer);
    if (current === entry) current = null;
    return new Promise(resolve => {
      entry.server.close(resolve); entry.server.closeAllConnections?.();
    });
  };
  return {
    async open({ html, csp, ...metadata }) {
      if (typeof html !== "string" || !html || Buffer.byteLength(html) > MAX_SNAPSHOT_BYTES || typeof csp !== "string" ||
          !csp || /[\r\n]/.test(csp) || Buffer.byteLength(JSON.stringify(metadata)) > 8192) throw new FeedbackError(413, "The inspection snapshot is too large.");
      const openingEpoch = ++epoch;
      await revoke(current);
      if (epoch !== openingEpoch) throw new FeedbackError(410, "The inspection was closed before opening.");
      const inspectionId = crypto.randomBytes(16).toString("hex"), capability = crypto.randomBytes(32).toString("base64url");
      const route = `/snapshot/${capability}`, bytes = Buffer.from(html), expiresAt = Date.now() + ttlMs;
      const entry = { active: true, server: null, timer: null, host: "", inspectionId };
      entry.server = http.createServer((req, res) => {
        const allowed = entry.active && Date.now() < expiresAt && req.method === "GET" && req.url === route &&
          req.headers.host === entry.host && req.socket.remoteAddress === "127.0.0.1" &&
          req.rawHeaders.filter((value, index) => index % 2 === 0 && value.toLowerCase() === "host").length === 1 &&
          !req.headers["transfer-encoding"] && (!req.headers["content-length"] || req.headers["content-length"] === "0");
        res.setHeader("Cache-Control", "no-store"); res.setHeader("Referrer-Policy", "no-referrer");
        res.setHeader("X-Content-Type-Options", "nosniff"); res.setHeader("Cross-Origin-Resource-Policy", "same-origin");
        res.setHeader("Connection", "close");
        res.setHeader("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()");
        if (!allowed) { res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" }); res.end("Not found."); return; }
        res.setHeader("Content-Security-Policy", csp.replace(/frame-ancestors[^;]*/g, "frame-ancestors 'none'") + "; sandbox allow-scripts");
        res.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Content-Length": bytes.length }); res.end(bytes);
      });
      entry.server.requestTimeout = 3000; entry.server.headersTimeout = 3000;
      entry.server.keepAliveTimeout = 1000; entry.server.maxHeadersCount = 24; entry.server.maxConnections = 8;
      try {
        try { await listenLocal(entry.server, { role: "control" }); }
        catch { throw new FeedbackError(503, "The inspection could not be opened."); }
        entry.host = `127.0.0.1:${entry.server.address().port}`;
        if (epoch !== openingEpoch) throw new FeedbackError(410, "The inspection was closed while opening.");
        current = entry;
        entry.timer = setTimeout(() => { void revoke(entry); }, ttlMs); entry.timer.unref();
        return { ...metadata, inspectionId, url: `http://${entry.host}${route}`, expiresAt,
          observation: "Independent immutable HTML render with declared initial state; not the live canvas state." };
      } catch (error) { await revoke(entry); throw error; }
    },
    async close(inspectionId) {
      if (typeof inspectionId !== "string" || !/^[a-f0-9]{32}$/.test(inspectionId) || current?.inspectionId !== inspectionId) throw new FeedbackError(404, "The inspection does not belong to this view.");
      epoch += 1; await revoke(current); return { closed: true };
    },
    revokeAll() { epoch += 1; return revoke(current); },
  };
}

module.exports = { createHtmlInspection, MAX_SNAPSHOT_BYTES, INSPECTION_TTL_MS };
