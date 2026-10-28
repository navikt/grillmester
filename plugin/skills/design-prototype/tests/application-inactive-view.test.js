"use strict";
const test = require("node:test"), assert = require("node:assert/strict");
const { renderInactive } = require("../scripts/application-connection-view.js");
test("a retired native view explains reopening without scripts or authority", () => {
  const result = renderInactive();
  assert.match(result.html, /Denne visningen er ikke aktiv/);
  assert.match(result.html, /Kopier eventuell ulagret tekst\. Lukk dette canvaset, og be deretter om å åpne verkstedet igjen i samtalen/);
  assert.match(result.html, /Midlertidig arbeid kan gå tapt ved lukking/);
  assert.doesNotMatch(result.html, /<script|<iframe|token=|controlToken|window.open|Åpne Designverksted i nettleseren/);
  assert.match(result.csp, /default-src 'none'/);
  assert.match(result.csp, /frame-ancestors 'none'/);
  assert.doesNotMatch(result.csp, /unsafe-inline/);
});
