"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
function renderInactive() {
  const nonce = crypto.randomBytes(24).toString("base64url");
  const style = fs.readFileSync(path.join(__dirname, "application-connection.css"), "utf8");
  return { html: `<!doctype html><html lang="nb"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Åpne Designverksted på nytt</title><style nonce="${nonce}">${style}</style><main><p class="wordmark">Designverksted</p><h1>Denne visningen er ikke aktiv</h1><p class="intro">Verkstedet er lukket. Be om å åpne det igjen i samtalen.</p><p class="footnote">Lagrede rom beholdes. Kopier eventuell ulagret tekst før du fortsetter. Denne visningen sender ingen innspill.</p></main></html>`,
    csp: `default-src 'none'; style-src 'nonce-${nonce}'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'` };
}

module.exports = { renderInactive };
