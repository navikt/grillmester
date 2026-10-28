"use strict";

// Deliberate application rejections are safe, authored diagnostics. Native I/O
// errors remain private and must never be forwarded with local paths or URLs.
class ApplicationError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

module.exports = { ApplicationError };
