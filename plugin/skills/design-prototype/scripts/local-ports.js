"use strict";

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

// Callers keep their request handler inactive until this promise succeeds.
// They also attach lifetime close/error observers only after the accepted bind.
async function listenLocal(server, { host = "127.0.0.1", port = 0 } = {}) {
  if (!Number.isInteger(port) || port < 0 || port > 65535) {
    throw portError("ERR_LOCAL_PORT_OPTIONS", "Invalid local view port options.");
  }
  if (server.listening) throw portError("ERR_SERVER_ALREADY_LISTEN", "The local view is already listening.");
  await bind(server, port, host);
  if (!server.address()) throw portError("ERR_LOCAL_LISTENER_CLOSED", "The local view was closed while opening.");
}

module.exports = { listenLocal };
