"use strict";
const test = require("node:test"), assert = require("node:assert/strict");
const { renderInactive } = require("../scripts/application-connection-view.js");
test("a retired native view explains reopening without scripts or authority", () => {
  const result = renderInactive();
  assert.match(result.html, /Verkstedet er lukket/);
  assert.match(result.html, /Be om å åpne det igjen i samtalen/);
  assert.doesNotMatch(result.html, /<script|<iframe|token=|controlToken|window.open|Åpne Designverksted i nettleseren/);
  assert.match(result.csp, /default-src 'none'/);
  assert.match(result.csp, /frame-ancestors 'none'/);
  assert.doesNotMatch(result.csp, /unsafe-inline/);
});
