"use strict";

const { randomInt } = require("node:crypto");

// Browser storage and service workers outlive a listener. Never reuse an app
// origin for a trusted surface, even after the original preview has closed.
const APPLICATION_PORT_MIN = 20000;
const APPLICATION_PORT_MAX = 29999;
const MAX_BIND_ATTEMPTS = 32;
const isApplicationPort = port => Number.isInteger(port) && port >= APPLICATION_PORT_MIN && port <= APPLICATION_PORT_MAX;

function portError(code, message) { return Object.assign(new Error(message), { code }); }
function bind(server, port, host) {
  return new Promise((resolve, reject) => {
    const cleanup = () => { server.off("listening", ready); server.off("error", failed); server.off("close", closed); };
    const ready = () => { cleanup(); resolve(); };
    const failed = error => { cleanup(); reject(error); };
    const closed = () => failed(portError("ERR_LOCAL_LISTENER_CLOSED", "The local view was closed while opening."));
    server.once("listening", ready); server.once("error", failed); server.once("close", closed);
    try { server.listen(port, host); } catch (error) { failed(error); }
  });
}
function close(server) {
  return new Promise(resolve => { server.close(resolve); server.closeAllConnections?.(); });
}

// Callers keep their request handler inactive until this promise succeeds.
// They also attach lifetime close/error observers only after the accepted bind.
async function listenLocal(server, { role, host = "127.0.0.1", port = 0 }) {
  if (!["application", "control"].includes(role) || !Number.isInteger(port) || port < 0 || port > 65535) {
    throw portError("ERR_LOCAL_PORT_OPTIONS", "Invalid local view port options.");
  }
  if (port && isApplicationPort(port) !== (role === "application")) {
    throw portError("ERR_LOCAL_PORT_ROLE", role === "control"
      ? "Ports 20000 through 29999 are reserved for application previews. Choose another --port or use 0."
      : "Application previews must use a port from 20000 through 29999.");
  }
  if (server.listening) throw portError("ERR_SERVER_ALREADY_LISTEN", "The local view is already listening.");
  const tried = new Set();
  for (let attempt = 0; attempt < MAX_BIND_ATTEMPTS; attempt += 1) {
    let candidate = port;
    if (!candidate && role === "application") {
      candidate = randomInt(APPLICATION_PORT_MIN, APPLICATION_PORT_MAX + 1);
      while (tried.has(candidate)) candidate = candidate === APPLICATION_PORT_MAX ? APPLICATION_PORT_MIN : candidate + 1;
      tried.add(candidate);
    }
    try { await bind(server, candidate, host); }
    catch (error) {
      if (!port && role === "application" && error.code === "EADDRINUSE") continue;
      throw error;
    }
    const address = server.address();
    if (!address) throw portError("ERR_LOCAL_LISTENER_CLOSED", "The local view was closed while opening.");
    if (typeof address === "object" && Number.isInteger(address.port) && address.port > 0 && address.port <= 65535 &&
        (!port || address.port === port) && isApplicationPort(address.port) === (role === "application")) return;
    await close(server);
    if (port) throw portError("ERR_LOCAL_PORT_ROLE", "The local view did not bind to the requested port role.");
  }
  throw portError("ERR_LOCAL_PORT_EXHAUSTED", "No local view port is available. Close unused previews and try again.");
}

module.exports = { listenLocal, isApplicationPort, APPLICATION_PORT_MIN, APPLICATION_PORT_MAX, MAX_BIND_ATTEMPTS };
