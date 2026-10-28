"use strict";

// The application is an untrusted document on a separate origin. This module
// never receives a control-surface token or access to a project filesystem.
const http = require("node:http");
const https = require("node:https");
const dns = require("node:dns").promises;
const net = require("node:net");
const crypto = require("node:crypto");
const zlib = require("node:zlib");
const { promisify } = require("node:util");
const { parseApplication } = require("./application-contract.js");
const { ApplicationError } = require("./application-error.js");

const MAX_BODY = 8 * 1024 * 1024;
const MAX_INSPECTOR = 256 * 1024;
const MAX_REQUESTS = 64;
const MAX_SOCKETS = 128;
const MAX_WEBSOCKETS = 16;
const TIMEOUT = 15000;
const WORKER_QUERY = "__designverksted_worker";
const PRIVATE_HEADER = /^(?:x-designverksted-|x-feedback-|x-visual-companion-)/i;
const COOKIE_NAME = /^[!#$%&'*+.^_`|~0-9A-Za-z-]+$/;
const HOP_HEADERS = new Set(["connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade"]);
const decode = { gzip: promisify(zlib.gunzip), deflate: promisify(zlib.inflate), br: promisify(zlib.brotliDecompress) };

function failure(status, message) { return new ApplicationError(status, message); }
function loopback(address) {
  const value = address.replace(/^\[|\]$/g, "").replace(/^::ffff:/i, "");
  return net.isIP(value) === 4 ? value.startsWith("127.") : value === "::1";
}
function validSecret(received, expected) {
  if (typeof received !== "string") return false;
  const actual = Buffer.from(received), target = Buffer.from(expected);
  return actual.length === target.length && crypto.timingSafeEqual(actual, target);
}
function cookieValue(header, name) {
  const values = String(header || "").split(";").map(part => part.trim()).filter(part => part.startsWith(`${name}=`));
  return values.length === 1 ? values[0].slice(name.length + 1) : null;
}
function commonHeaders(response) {
  response.setHeader("Cache-Control", "no-store");
  response.setHeader("Referrer-Policy", "no-referrer");
  response.setHeader("X-Content-Type-Options", "nosniff");
  response.setHeader("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=(), clipboard-read=()");
}
function errorResponse(response, status, message) {
  if (response.headersSent) { response.destroy(); return; }
  commonHeaders(response);
  response.writeHead(status, { "Content-Type": "text/plain; charset=utf-8", "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'" });
  response.end(message);
}
function documentRequest(request) {
  const destination = request.headers["sec-fetch-dest"], mode = request.headers["sec-fetch-mode"];
  if (destination !== undefined || mode !== undefined) return ["document", "iframe"].includes(destination) && mode === "navigate";
  return ["GET", "POST"].includes(request.method) && /(?:^|,)\s*(?:text\/html|application\/xhtml\+xml)(?:\s*;|\s*,|$)/i.test(String(request.headers.accept || ""));
}
function documentErrorResponse(response, status, shellOrigin) {
  if (response.headersSent) { response.destroy(); return; }
  commonHeaders(response);
  response.writeHead(status, { "Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": `default-src 'none'; frame-ancestors ${shellOrigin}; base-uri 'none'; form-action 'none'` });
  response.end('<!doctype html><html lang="nb"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Appen kunne ikke vises</title><body><main><h1>Appen kunne ikke vises</h1><p>Kontroller at den lokale demoen kjører, og last visningen på nytt i Designverksted.</p><p>Du kan fortsatt gå tilbake til innspillene dine.</p></main></body></html>');
}

// Reject absolute-form and protocol-relative targets instead of allowing a
// request URL to select a different host. Query strings here belong to the app
// transport (including HMR), not to the persisted design-evidence contract.
function proxyTarget(target, upstreamOrigin) {
  if (typeof target !== "string" || Buffer.byteLength(target) > 16384 || !target.startsWith("/") || target.startsWith("//") || /[\\\u0000-\u0020\u007f#]/.test(target)) throw failure(400, "The application request path is invalid.");
  let parsed;
  try { parsed = new URL(target, upstreamOrigin); } catch { throw failure(400, "The application request path is invalid."); }
  if (parsed.origin !== upstreamOrigin || parsed.username || parsed.password) throw failure(400, "The application request path is invalid.");
  return parsed;
}

function appCookiesForUpstream(header, prefix) {
  const result = [];
  for (const item of String(header || "").split(";")) {
    const pair = item.trim(), equals = pair.indexOf("=");
    if (equals < 1 || !pair.startsWith(prefix)) continue;
    const name = pair.slice(prefix.length, equals);
    if (!COOKIE_NAME.test(name)) continue;
    result.push(name + pair.slice(equals));
  }
  return result.join("; ");
}

function rewriteAppCookie(cookie, prefix) {
  if (typeof cookie !== "string" || Buffer.byteLength(cookie) > 8192 || /[\r\n\0]/.test(cookie)) return null;
  const parts = cookie.split(";"), equals = parts[0].indexOf("=");
  if (equals < 1) return null;
  const name = parts[0].slice(0, equals).trim();
  if (!COOKIE_NAME.test(name)) return null;
  // The app uses localhost, separate from the 127.0.0.1 control host. Partitioning keeps its cookies
  // usable inside the shell without depending on third-party cookie access.
  // The upstream receives only the original logical application cookie names.
  const attributes = parts.slice(1).map(part => part.trim()).filter(part => !/^(?:domain\s*=|samesite\s*=|secure$|partitioned$)/i.test(part));
  return `${prefix}${name}${parts[0].slice(equals)}${attributes.length ? "; " + attributes.join("; ") : ""}; Secure; SameSite=None; Partitioned`;
}

function connectionHeaders(headers) {
  return new Set([...HOP_HEADERS, ...String(headers.connection || "").toLowerCase().split(",").map(value => value.trim()).filter(Boolean)]);
}
function proxyRequestHeaders(headers, upstream, previewOrigin, cookiePrefix) {
  const ignored = connectionHeaders(headers), output = {};
  for (const [name, value] of Object.entries(headers)) {
    const lower = name.toLowerCase();
    if (ignored.has(lower) || lower === "host" || lower === "cookie" || PRIVATE_HEADER.test(lower) || lower.startsWith("proxy-") || lower.startsWith("forwarded") || lower.startsWith("x-forwarded-")) continue;
    if (lower === "origin") { if (value === previewOrigin) output.origin = upstream.origin; continue; }
    if (lower === "referer") {
      try { const url = new URL(value); if (url.origin === previewOrigin) output.referer = upstream.origin + url.pathname + url.search; } catch { /* A referrer is optional. */ }
      continue;
    }
    output[lower] = value;
  }
  output.host = upstream.host;
  output["accept-encoding"] = "identity";
  const cookie = appCookiesForUpstream(headers.cookie, cookiePrefix);
  if (cookie) output.cookie = cookie;
  return output;
}

// Add permission only for the inspector element. Adding a nonce to a policy
// with effective unsafe-inline would disable the application's inline scripts.
// Keep that policy's meaning by allowing the exact inspector URL instead.
// script-src stays unchanged so handlers, eval and worker fallbacks retain
// their original policy; frame ancestors are narrowed to the shell.
function contentSecurityPolicy(policy, shellOrigin, nonce, inspectorUrl) {
  if (Array.isArray(policy) || String(policy || "").includes(",")) throw failure(502, "Multiple application security policies are not supported by this preview.");
  const directives = new Map();
  for (const entry of String(policy || "").split(";")) {
    const parts = entry.trim().split(/\s+/), name = parts.shift()?.toLowerCase();
    if (name && !directives.has(name)) directives.set(name, parts);
  }
  const current = directives.get("script-src-elem") || directives.get("script-src") || directives.get("default-src");
  if (current) {
    const effectiveInline = current.some(value => value.toLowerCase() === "'unsafe-inline'") &&
      !current.some(value => value.toLowerCase() === "'strict-dynamic'" || /^'(?:nonce-|sha(?:256|384|512)-)[a-z0-9+/_-]+={0,2}'$/i.test(value));
    let permission = `'nonce-${nonce}'`;
    if (effectiveInline) {
      if (typeof inspectorUrl !== "string" || !/^http:\/\/localhost:\d+\/\.designverksted\/[a-f0-9]{24}\/inspect\.js$/.test(inspectorUrl)) throw failure(502, "The application inspector address is invalid.");
      permission = inspectorUrl;
    }
    directives.set("script-src-elem", [...current.filter(value => value.toLowerCase() !== "'none'"), permission]);
  }
  // The proxy is intentionally HTTP loopback; retaining this directive would
  // upgrade its own injected resource to a TLS endpoint that does not exist.
  directives.delete("upgrade-insecure-requests");
  directives.delete("report-uri");
  directives.delete("report-to");
  directives.set("frame-ancestors", [shellOrigin]);
  return [...directives].map(([name, values]) => [name, ...values].join(" ")).join("; ");
}

function replaceOrigin(text, upstreamOrigin, previewOrigin) {
  const escaped = upstreamOrigin.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return text.replace(new RegExp(escaped + "(?=[/\\\"'\\s?#<)]|$)", "g"), previewOrigin);
}
function instrumentHtml(html, { upstreamOrigin, previewOrigin, inspectorPath, nonce }) {
  const content = replaceOrigin(html, upstreamOrigin, previewOrigin);
  const injection = `<script nonce="${nonce}" src="${inspectorPath}"></script>`;
  // Insert before application scripts and before any meta CSP. The script is
  // parser-blocking so request/cookie compatibility is ready at app startup.
  const doctype = /^(\uFEFF?\s*<!doctype\s[^>]*>)/i.exec(content);
  return doctype ? content.slice(0, doctype[0].length) + injection + content.slice(doctype[0].length) : injection + content;
}

// Executed only in the untrusted app document. These shims restore the common
// dev-server assumptions changed by proxying; none grants control privileges.
function browserCompatibility(config) {
  const { upstreamOrigin, previewOrigin, cookiePrefix, workerKey } = config;
  function mapUrl(input, socket = false) {
    try {
      const url = new URL(String(input), location.href);
      if (socket) {
        const comparable = new URL(url.href);
        if (comparable.protocol === "ws:") comparable.protocol = "http:";
        else if (comparable.protocol === "wss:") comparable.protocol = "https:";
        if (comparable.origin === upstreamOrigin) { url.protocol = "ws:"; url.host = new URL(previewOrigin).host; }
        else if (url.protocol === "http:") url.protocol = "ws:";
        else if (url.protocol === "https:") url.protocol = "wss:";
      } else if (url.origin === upstreamOrigin) { url.protocol = "http:"; url.host = new URL(previewOrigin).host; }
      return url.href;
    } catch { return input; }
  }
  const nativeFetch = window.fetch;
  if (nativeFetch) window.fetch = function(input, init) {
    if (input instanceof Request) {
      const mapped = mapUrl(input.url);
      return nativeFetch.call(this, mapped === input.url ? input : new Request(mapped, input), init);
    }
    return nativeFetch.call(this, mapUrl(input), init);
  };
  const open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) { return open.call(this, method, mapUrl(url), ...rest); };
  for (const name of ["WebSocket", "EventSource"]) {
    const Native = window[name];
    if (!Native) continue;
    function Proxied(url, ...rest) {
      if (!new.target) throw new TypeError("Use the constructor with new.");
      return Reflect.construct(Native, [mapUrl(url, name === "WebSocket"), ...rest], new.target === Proxied ? Native : new.target);
    }
    Object.setPrototypeOf(Proxied, Native);
    Proxied.prototype = Native.prototype;
    window[name] = Proxied;
  }
  for (const method of ["pushState", "replaceState"]) {
    const native = history[method];
    history[method] = function(state, title, url) { return native.call(this, state, title, url == null ? url : mapUrl(url)); };
  }
  const descriptor = Object.getOwnPropertyDescriptor(Document.prototype, "cookie");
  if (descriptor?.get && descriptor.set) Object.defineProperty(document, "cookie", {
    configurable: false,
    get() { return descriptor.get.call(this).split(";").map(part => part.trim()).filter(part => part.startsWith(cookiePrefix)).map(part => part.slice(cookiePrefix.length)).join("; "); },
    set(value) {
      const parts = String(value).split(";"), equals = parts[0].indexOf("=");
      if (equals < 1) return;
      const attributes = parts.slice(1).filter(part => !/^\s*(?:domain\s*=|samesite\s*=|secure\s*$|partitioned\s*$)/i.test(part));
      descriptor.set.call(this, cookiePrefix + parts[0].trim() + (attributes.length ? ";" + attributes.join(";") : "") + "; Secure; SameSite=None; Partitioned");
    },
  });
  // Workers (including browser MSW) stay on this preview's unique hostname.
  // A later preview never reuses its origin or its worker registrations.
  if (navigator.serviceWorker?.register) {
    const register = navigator.serviceWorker.register;
    navigator.serviceWorker.register = function(script, options) {
      const url = new URL(mapUrl(script), location.href);
      if (url.origin === previewOrigin) {
        if (url.searchParams.has("__designverksted_worker")) return Promise.reject(new Error("The worker address contains a reserved preview parameter."));
        // Chrome omits partitioned cookies when retrieving a worker script.
        // This separate capability can retrieve only a worker JavaScript
        // response; it grants no ordinary app request or control access.
        url.search += `${url.search ? "&" : "?"}__designverksted_worker=${workerKey}`;
      }
      return register.call(this, url.href, options?.scope === undefined ? options : { ...options, scope: mapUrl(options.scope) });
    };
    // MSW locates its existing registration by exact script URL. Expose the
    // application's logical address while the browser keeps the private URL
    // for its own update requests; retain all other query bytes unchanged.
    if (typeof ServiceWorker === "function") {
      const script = Object.getOwnPropertyDescriptor(ServiceWorker.prototype, "scriptURL");
      if (script?.get && script.configurable) Object.defineProperty(ServiceWorker.prototype, "scriptURL", {
        ...script, get() {
          const value = script.get.call(this);
          try {
            const url = new URL(value);
            if (url.origin === previewOrigin) url.search = url.search.slice(1).split("&").filter(part => part.split("=")[0] !== "__designverksted_worker").join("&");
            return url.href;
          } catch { return value; }
        },
      });
    }
  }
  document.addEventListener("click", event => {
    const anchor = event.composedPath().find(node => node instanceof HTMLAnchorElement);
    if (anchor && anchor.href) { const mapped = mapUrl(anchor.href); if (mapped !== anchor.href) anchor.href = mapped; }
  }, true);
  document.addEventListener("submit", event => {
    if (event.target instanceof HTMLFormElement) event.target.action = mapUrl(event.target.action);
  }, true);
}

// Worker passthrough fetches also omit partitioned cookies in Chrome. This
// capability is confined to the worker's own preview transport, never the
// shell. Upstream forwarding strips the private headers before delivery.
function workerCompatibility({ previewOrigin, workerTransportKey }) {
  const fetch = self.fetch;
  self.fetch = function(input, init) {
    const url = new URL(input instanceof Request ? input.url : String(input), self.location.href);
    if (url.origin !== previewOrigin) return fetch.call(this, input, init);
    const navigation = input instanceof Request && input.mode === "navigate" && ["document", "iframe"].includes(input.destination);
    const request = new Request(input, init), headers = new Headers(request.headers);
    headers.set("x-designverksted-worker", workerTransportKey);
    if (navigation) headers.set("x-designverksted-worker-navigation", "1");
    else headers.delete("x-designverksted-worker-navigation");
    return fetch.call(this, new Request(request, { headers }));
  };
}

async function readBounded(stream, maximum = MAX_BODY) {
  const chunks = []; let bytes = 0;
  const timeout = setTimeout(() => stream.destroy(failure(502, "The application document did not finish loading.")), TIMEOUT);
  try {
    for await (const chunk of stream) {
      bytes += chunk.length;
      if (bytes > maximum) { stream.destroy(); throw failure(502, "The application document is too large to inspect."); }
      chunks.push(chunk);
    }
  } finally { clearTimeout(timeout); }
  return Buffer.concat(chunks, bytes);
}
async function decodeBody(body, encoding) {
  for (const value of String(encoding || "identity").split(",").map(entry => entry.trim().toLowerCase()).reverse()) {
    if (value === "identity" || value === "") continue;
    if (!decode[value]) throw failure(502, "The application uses an unsupported document encoding.");
    body = await decode[value](body, { maxOutputLength: MAX_BODY });
  }
  return body;
}
function responseHeaders(headers, { shellOrigin, nonce, upstreamOrigin, requestUrl, previewOrigin, inspectorPath, cookiePrefix, transformed = false }) {
  const ignored = connectionHeaders(headers), output = {};
  for (const [name, value] of Object.entries(headers)) {
    const lower = name.toLowerCase();
    if (ignored.has(lower) || PRIVATE_HEADER.test(lower) || lower.startsWith("access-control-") || ["x-frame-options", "content-security-policy", "content-security-policy-report-only", "clear-site-data", "alt-svc", "report-to", "reporting-endpoints", "nel"].includes(lower)) continue;
    if (transformed && ["content-length", "content-encoding", "etag", "content-md5", "digest", "content-range", "accept-ranges"].includes(lower)) continue;
    if (lower === "set-cookie") {
      const cookies = (Array.isArray(value) ? value : [value]).map(cookie => rewriteAppCookie(cookie, cookiePrefix)).filter(Boolean);
      if (cookies.length) output[lower] = cookies;
    } else if (lower === "service-worker-allowed") {
      let scope;
      try { scope = new URL(value, requestUrl || upstreamOrigin); } catch { throw failure(502, "The application worker scope is invalid."); }
      if (scope.origin !== upstreamOrigin || scope.search || scope.hash || scope.username || scope.password) throw failure(502, "The application worker scope is invalid.");
      output[lower] = previewOrigin + scope.pathname;
    } else if (lower === "location") {
      let redirect;
      try { redirect = new URL(value, upstreamOrigin); } catch { throw failure(502, "The application redirect is invalid."); }
      if (redirect.origin !== upstreamOrigin) throw failure(502, "The application redirected outside its local address. Use its demo or mock sign-in.");
      output[lower] = previewOrigin + redirect.pathname + redirect.search + redirect.hash;
    } else output[lower] = value;
  }
  output["content-security-policy"] = contentSecurityPolicy(headers["content-security-policy"], shellOrigin, nonce, previewOrigin + inspectorPath);
  output["cache-control"] = "no-store";
  output["referrer-policy"] = "no-referrer";
  output["x-content-type-options"] = "nosniff";
  output["permissions-policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), clipboard-read=()";
  return output;
}

async function createApplicationProxy({ application, shellOrigin, inspectorSource, onClose, onStatus } = {}) {
  let app, shell;
  try {
    app = parseApplication({ name: application?.name, url: application?.url,
      ...(application?.resourceQueryKeys !== undefined ? { resourceQueryKeys: application.resourceQueryKeys } : {}) });
    if (application.origin !== undefined && application.origin !== app.origin || application.startPath !== undefined && application.startPath !== app.startPath) throw new Error();
    shell = new URL(shellOrigin);
    if (shell.origin !== shellOrigin || shell.protocol !== "http:" || shell.hostname !== "127.0.0.1" || !shell.port || shell.username || shell.password) throw new Error();
  } catch { throw failure(400, "The local application or control surface address is invalid."); }
  if (typeof inspectorSource !== "string" || Buffer.byteLength(inspectorSource) > MAX_INSPECTOR || inspectorSource.includes("\0") || onClose !== undefined && typeof onClose !== "function" || onStatus !== undefined && typeof onStatus !== "function") throw failure(400, "The application inspector configuration is invalid.");
  const upstream = new URL(app.origin);
  const hostname = upstream.hostname.replace(/^\[|\]$/g, "");
  let addresses;
  try { addresses = net.isIP(hostname) ? [{ address: hostname, family: net.isIP(hostname) }] : await dns.lookup(hostname, { all: true, verbatim: true }); }
  catch { throw failure(502, "The local application address could not be resolved."); }
  if (!addresses.length || addresses.some(item => !loopback(item.address))) throw failure(400, "The application must resolve only to loopback addresses.");
  // Keep the complete verified lookup result. Development servers may bind
  // only one localhost family; Node can try both without resolving DNS again.
  const pinned = addresses.map(({ address, family }) => ({ address, family }));
  const privateId = crypto.randomBytes(12).toString("hex"), secret = crypto.randomBytes(32).toString("base64url");
  const workerKey = crypto.randomBytes(32).toString("base64url");
  const workerTransportKey = crypto.randomBytes(32).toString("base64url");
  const authCookie = `dv_preview_${privateId}_auth`, cookiePrefix = `dv_app_${privateId}_`;
  const internal = `/.designverksted/${privateId}`, bootstrapPath = `${internal}/open/${secret}`, inspectorPath = `${internal}/inspect.js`;
  const sockets = new Set(), upstreamRequests = new Set(), webSockets = new Set();
  let origin, authority, closed = false, closePromise, activeRequests = 0, navigation = 0, lastStatus = "";
  function reportStatus(id, state, httpStatus) {
    if (!id || id !== navigation || closed) return;
    const value = { state, ...(Number.isInteger(httpStatus) && httpStatus >= 100 && httpStatus <= 599 ? { httpStatus } : {}) };
    const serialized = JSON.stringify(value);
    if (serialized === lastStatus) return;
    lastStatus = serialized;
    try { Promise.resolve(onStatus?.(Object.freeze(value))).catch(() => {}); } catch { /* An observer cannot interrupt application transport. */ }
  }

  function requestAllowed(request, socket = false) {
    if (closed || !loopback(String(request.socket.remoteAddress || "")) || request.headers.host !== authority) return false;
    if (request.headers.origin !== undefined && request.headers.origin !== origin) return false;
    if (socket || !["GET", "HEAD"].includes(request.method)) if (request.headers.origin !== origin) return false;
    return validSecret(cookieValue(request.headers.cookie, authCookie), secret);
  }
  function upstreamRequest(url, options) {
    const transport = upstream.protocol === "https:" ? https : http;
    const request = transport.request(url, { ...options, agent: false, autoSelectFamily: true, autoSelectFamilyAttemptTimeout: 100,
      lookup: (_host, settings, callback) => settings?.all ? callback(null, pinned) : callback(null, pinned[0].address, pinned[0].family),
    });
    upstreamRequests.add(request);
    request.once("close", () => upstreamRequests.delete(request));
    request.setTimeout(TIMEOUT, () => request.destroy(failure(504, "The local application did not respond in time.")));
    return request;
  }
  const server = http.createServer((request, response) => {
    commonHeaders(response);
    if (closed || !loopback(String(request.socket.remoteAddress || "")) || request.headers.host !== authority) { errorResponse(response, 403, "This preview accepts only its local address."); return; }
    let target;
    try { target = proxyTarget(request.url, app.origin); } catch { errorResponse(response, 400, "The application request path is invalid."); return; }
    if (target.pathname === bootstrapPath && !target.search && request.method === "GET") {
      if (request.headers.origin !== undefined && ![origin, shellOrigin].includes(request.headers.origin)) { errorResponse(response, 403, "This preview cannot be opened from that origin."); return; }
      response.writeHead(303, { Location: app.startPath, "Set-Cookie": `${authCookie}=${secret}; HttpOnly; SameSite=None; Secure; Partitioned; Path=/`, "Content-Security-Policy": `default-src 'none'; frame-ancestors ${shellOrigin}` });
      response.end(); return;
    }
    const workerValues = target.searchParams.getAll(WORKER_QUERY);
    const workerRequest = workerValues.length > 0;
    const workerTransport = request.headers["x-designverksted-worker"] !== undefined;
    if (workerRequest) {
      if (request.method !== "GET" || workerValues.length !== 1 || !validSecret(workerValues[0], workerKey)
        || request.headers["service-worker"] !== "script" || request.headers["sec-fetch-dest"] !== "serviceworker"
        || request.headers["sec-fetch-mode"] !== "same-origin" || request.headers["sec-fetch-site"] !== "same-origin"
        || request.headers.origin !== undefined && request.headers.origin !== origin || target.pathname.startsWith(internal + "/")) {
        errorResponse(response, 403, "This worker requires its private application connection."); return;
      }
      target.search = target.search.slice(1).split("&").filter(part => {
        try { return decodeURIComponent(part.split("=")[0]) !== WORKER_QUERY; } catch { return true; }
      }).join("&");
    } else if (workerTransport) {
      if (!validSecret(request.headers["x-designverksted-worker"], workerTransportKey) || request.headers["sec-fetch-site"] !== "same-origin"
        || request.headers.origin !== undefined && request.headers.origin !== origin || target.pathname.startsWith(internal + "/")) {
        errorResponse(response, 403, "This worker requires its private application connection."); return;
      }
    } else if (!requestAllowed(request)) { errorResponse(response, 403, "This preview requires its private connection."); return; }
    if (target.pathname === inspectorPath && !target.search) {
      if (!["GET", "HEAD"].includes(request.method)) { errorResponse(response, 405, "This inspector resource is read-only."); return; }
      response.writeHead(200, { "Content-Type": "text/javascript; charset=utf-8" });
      const source = `;(${browserCompatibility.toString()})(${JSON.stringify({ upstreamOrigin: app.origin, previewOrigin: origin, cookiePrefix, workerKey })});\n${inspectorSource}`;
      response.end(request.method === "HEAD" ? "" : source); return;
    }
    if (target.pathname.startsWith(internal + "/")) { errorResponse(response, 409, "This resource is unavailable in the design preview."); return; }
    if (!/^(?:GET|HEAD|POST|PUT|PATCH|DELETE|OPTIONS)$/.test(request.method)) { errorResponse(response, 405, "This application method is unavailable."); return; }
    const navigationId = documentRequest(request) || workerTransport && request.headers["x-designverksted-worker-navigation"] === "1" ? ++navigation : 0;
    const failRequest = (status, message) => {
      if (response.writableEnded || response.destroyed) return;
      reportStatus(navigationId, "unavailable", status);
      if (navigationId) documentErrorResponse(response, status, shellOrigin);
      else errorResponse(response, status, message);
    };
    reportStatus(navigationId, "loading");
    if (activeRequests >= MAX_REQUESTS) { failRequest(429, "The application preview is busy. Try again shortly."); return; }
    if (Number(request.headers["content-length"] || 0) > MAX_BODY) { failRequest(413, "The application request is too large."); request.resume(); return; }
    activeRequests += 1;
    let finished = false;
    const finish = () => { if (!finished) { finished = true; activeRequests -= 1; } };
    response.once("close", finish);
    const outgoing = upstreamRequest(target, { method: request.method, headers: proxyRequestHeaders(request.headers, upstream, origin, cookiePrefix) });
    response.once("close", () => { if (!response.writableFinished) outgoing.destroy(); });
    request.once("aborted", () => outgoing.destroy());
    let bodyBytes = 0;
    request.on("data", chunk => {
      bodyBytes += chunk.length;
      if (bodyBytes > MAX_BODY) { request.unpipe(outgoing); outgoing.destroy(); failRequest(413, "The application request is too large."); request.resume(); }
    });
    outgoing.once("error", error => failRequest(error.status === 504 ? 504 : 502, error.status === 504 ? "The local application did not respond in time." : "The local application is unavailable. Check that its demo server is running."));
    outgoing.once("response", async incoming => {
      const nonce = crypto.randomBytes(18).toString("base64url");
      try {
        const contentType = String(incoming.headers["content-type"] || "").toLowerCase();
        if (workerRequest && (incoming.statusCode !== 200 || !/^(?:text|application)\/(?:javascript|ecmascript)(?:;|$)/.test(contentType))) throw failure(502, "The application worker must be a JavaScript resource.");
        const html = /^(?:text\/html|application\/xhtml\+xml)(?:;|$)/.test(contentType);
        const css = /^text\/css(?:;|$)/.test(contentType);
        const transformed = workerRequest || request.method !== "HEAD" && ![204, 304].includes(incoming.statusCode) && (html || css);
        const headers = responseHeaders(incoming.headers, { shellOrigin, nonce, upstreamOrigin: app.origin, requestUrl: target.href, previewOrigin: origin, inspectorPath, cookiePrefix, transformed });
        if (workerRequest) {
          const decoded = await decodeBody(await readBounded(incoming), incoming.headers["content-encoding"]);
          const source = decoded.toString("utf8");
          if (!Buffer.from(source, "utf8").equals(decoded)) throw failure(502, "The application worker must use UTF-8.");
          const content = `;(${workerCompatibility.toString()})(${JSON.stringify({ previewOrigin: origin, workerTransportKey })});\n${source}`;
          headers["content-length"] = Buffer.byteLength(content);
          response.writeHead(incoming.statusCode, headers); response.end(content); return;
        }
        // Resolve relative Location against the current upstream route, while
        // requiring the originally selected origin before returning it.
        if (incoming.headers.location) {
          const destination = new URL(incoming.headers.location, target);
          if (destination.origin !== app.origin) throw failure(502, "The application redirected outside its local address. Use its demo or mock sign-in.");
          headers.location = origin + destination.pathname + destination.search + destination.hash;
        }
        if (!transformed) {
          response.writeHead(incoming.statusCode || 502, headers);
          incoming.once("error", () => { reportStatus(navigationId, "unavailable", 502); response.destroy(); });
          incoming.once("end", () => {
            if (incoming.statusCode < 300 || incoming.statusCode >= 400) reportStatus(navigationId, "unavailable", incoming.statusCode || 502);
          });
          incoming.pipe(response); return;
        }
        if (incoming.statusCode === 206) throw failure(502, "Partial application documents cannot be inspected. Reload the page.");
        const decoded = await decodeBody(await readBounded(incoming), incoming.headers["content-encoding"]);
        const charset = /charset\s*=\s*["']?([^;\s"']+)/i.exec(contentType)?.[1];
        if (charset && !["utf-8", "utf8", "us-ascii"].includes(charset)) throw failure(502, "The application document must use UTF-8 in this preview.");
        let content = decoded.toString("utf8");
        if (!Buffer.from(content, "utf8").equals(decoded)) throw failure(502, "The application document must use UTF-8 in this preview.");
        content = html ? instrumentHtml(content, { upstreamOrigin: app.origin, previewOrigin: origin, inspectorPath, nonce }) : replaceOrigin(content, app.origin, origin);
        headers["content-length"] = Buffer.byteLength(content);
        response.writeHead(incoming.statusCode || 502, headers); response.end(content);
        if (incoming.statusCode < 300 || incoming.statusCode >= 400) reportStatus(navigationId, html && incoming.statusCode < 400 ? "ready" : "unavailable", incoming.statusCode || 502);
      } catch (error) {
        incoming.destroy();
        failRequest(502, error.status === 502 ? error.message : "The application response could not be inspected.");
      }
    });
    request.pipe(outgoing);
  });
  server.requestTimeout = 30000;
  server.once("close", () => { if (!closed) void close(); });
  server.headersTimeout = 10000;
  server.keepAliveTimeout = 5000;
  server.maxRequestsPerSocket = 1000;
  server.on("connection", socket => {
    if (sockets.size >= MAX_SOCKETS) { socket.destroy(); return; }
    sockets.add(socket); socket.once("close", () => sockets.delete(socket));
  });
  server.on("clientError", (_error, socket) => socket.end("HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n"));
  server.on("upgrade", (request, socket, head) => {
    // HTTP no longer owns this socket after upgrade, including while access
    // is being denied or the upstream handshake is still pending.
    socket.on("error", () => socket.destroy());
    const deny = (status, reason) => { if (!socket.destroyed && !socket.writableEnded) socket.end(`HTTP/1.1 ${status} ${reason}\r\nConnection: close\r\n\r\n`); };
    if (!requestAllowed(request, true)) { deny(403, "Forbidden"); return; }
    if (request.headers.upgrade?.toLowerCase() !== "websocket" || request.method !== "GET" || webSockets.size >= MAX_WEBSOCKETS) { deny(409, "Unavailable"); return; }
    let target;
    try { target = proxyTarget(request.url, app.origin); } catch { deny(400, "Bad Request"); return; }
    if (target.pathname.startsWith(internal + "/")) { deny(403, "Forbidden"); return; }
    const outgoing = upstreamRequest(target, { method: "GET", headers: { ...proxyRequestHeaders(request.headers, upstream, origin, cookiePrefix), connection: "Upgrade", upgrade: "websocket" } });
    socket.once("close", () => outgoing.destroy());
    outgoing.once("upgrade", (incoming, upstreamSocket, upstreamHead) => {
      upstreamSocket.on("error", () => socket.destroy());
      outgoing.setTimeout(0); upstreamSocket.setTimeout(0);
      if (closed || webSockets.size >= MAX_WEBSOCKETS) { upstreamSocket.destroy(); deny(409, "Unavailable"); return; }
      webSockets.add(upstreamSocket);
      let headers;
      try { headers = responseHeaders(incoming.headers, { shellOrigin, nonce: crypto.randomBytes(18).toString("base64url"), upstreamOrigin: app.origin, previewOrigin: origin, inspectorPath, cookiePrefix }); }
      catch { upstreamSocket.destroy(); deny(502, "Bad Gateway"); return; }
      headers.connection = "Upgrade"; headers.upgrade = "websocket";
      const lines = Object.entries(headers).flatMap(([name, value]) => (Array.isArray(value) ? value : [value]).map(item => `${name}: ${item}\r\n`)).join("");
      socket.write(`HTTP/1.1 101 Switching Protocols\r\n${lines}\r\n`);
      if (upstreamHead.length) socket.write(upstreamHead);
      if (head.length) upstreamSocket.write(head);
      socket.once("close", () => upstreamSocket.destroy());
      upstreamSocket.once("close", () => { webSockets.delete(upstreamSocket); socket.destroy(); });
      upstreamSocket.pipe(socket).pipe(upstreamSocket);
    });
    outgoing.once("response", incoming => { incoming.resume(); deny(502, "Bad Gateway"); });
    outgoing.once("error", () => deny(502, "Bad Gateway"));
    outgoing.end();
  });
  try {
    await new Promise((resolve, reject) => {
      server.once("error", reject);
      server.listen(0, "127.0.0.1", () => { server.off("error", reject); resolve(); });
    });
  } catch { throw failure(503, "The local application preview could not start."); }
  // Explicit native test variant: one immutable listener/upstream per canvas.
  // localhost separates the app cookie host from the 127.0.0.1 control host.
  // Storage isolation between native instances remains host-specific evidence,
  // not an SDK guarantee or permission to use this variant in a normal browser.
  authority = `localhost:${server.address().port}`;
  origin = `http://${authority}`;
  function close() {
    if (closePromise) return closePromise;
    closed = true;
    closePromise = (async () => {
      for (const request of upstreamRequests) request.destroy();
      for (const socket of webSockets) socket.destroy();
      for (const socket of sockets) socket.destroy();
      await new Promise(resolve => server.close(resolve));
      try { await onClose?.(); } catch { /* An observer cannot prevent cleanup. */ }
    })();
    return closePromise;
  }
  return { origin, url: origin + bootstrapPath, close };
}

module.exports = { createApplicationProxy, proxyTarget, appCookiesForUpstream, rewriteAppCookie, proxyRequestHeaders, contentSecurityPolicy, instrumentHtml, decodeBody, browserCompatibility, workerCompatibility };
