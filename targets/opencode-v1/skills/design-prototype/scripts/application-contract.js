"use strict";

const crypto = require("node:crypto");
const { ApplicationError } = require("./application-error.js");

const MAX_ROUTE_BYTES = 2048;
const MAX_URL_BYTES = 4096;
const MAX_QUERY_ITEMS = 16;
const HASH = /^[a-f0-9]{64}$/;
const SCREEN = /^[a-f0-9]{32}$/;
const CONTROL = /[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
const DOM_PATH = /^[a-z][a-z0-9-]*:nth-of-type\([1-9][0-9]{0,5}\)(?: > [a-z][a-z0-9-]*:nth-of-type\([1-9][0-9]{0,5}\))*$/;
const ROLES = new Set(["", "button", "link", "textbox", "heading", "img", "navigation", "main", "region", "group", "list", "listitem", "checkbox", "radio", "radiogroup", "combobox", "option", "listbox", "switch", "slider", "spinbutton", "searchbox", "tab", "tablist", "tabpanel", "table", "row", "cell", "columnheader", "rowheader", "grid", "gridcell", "alert", "status", "dialog", "form", "menu", "menuitem", "separator", "progressbar", "presentation", "none"]);
const FIELD_TAGS = new Set(["input", "textarea", "select", "option"]);
const FIELD_ROLES = new Set(["textbox", "searchbox", "combobox", "spinbutton", "slider"]);
const SENSITIVE_QUERY = /(?:token|auth|password|passwd|secret|credential|session|cookie|assertion|signature|csrf|xsrf|jwt|saml|apikey|privatekey|clientkey|accesskey|clientsecret|redirect|returnurl|callback|email|personident|fodselsnummer|foedselsnummer|fødselsnummer|personnummer|nationalid|passcode|onetimepassword)/i;
const SENSITIVE_EXACT = new Set(["code", "state", "key", "sig", "sid", "pwd", "ticket", "fnr", "ssn", "pid", "nonce", "relaystate", "otp", "pin", "ident", "pnr", "dnr", "telefon", "phone", "tlf", "navn", "name", "adresse", "address"]);
const RESOURCE_UUID = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i;

function fail(message) { throw new ApplicationError(400, message); }
function exact(value, required) {
  return value !== null && typeof value === "object" && !Array.isArray(value) &&
    Object.keys(value).length === required.length && required.every(key => Object.hasOwn(value, key));
}
function boundedText(value, maximum, empty = true) {
  return typeof value === "string" && (empty || value.trim().length > 0) && Buffer.byteLength(value, "utf8") <= maximum &&
    !CONTROL.test(value) && Buffer.from(value, "utf8").toString("utf8") === value;
}
function safeQueryName(name) {
  const normalized = typeof name === "string" ? name.toLowerCase().replace(/[-_.]/g, "") : "";
  return boundedText(name, 64, false) && /^[a-zA-Z][a-zA-Z0-9_.-]{0,63}$/.test(name) &&
    !SENSITIVE_QUERY.test(normalized) && !SENSITIVE_EXACT.has(normalized);
}
function normalizeResourceQueryKeys(value) {
  if (!Array.isArray(value) || value.length > 8 || Array.from(value).some(name => !safeQueryName(name)) ||
      new Set(value.map(name => name.toLowerCase())).size !== value.length) fail("Choose at most eight distinct public resource query names. Authentication and personal-data parameters are never supported.");
  return value.map(name => name.toLowerCase()).sort();
}
function safeQueryValue(value) {
  if (!boundedText(value, 200) || /[%\\<>\[\]{}]/.test(value) || /(?:https?:)?\/\//i.test(value)) return false;
  const inspected = value.normalize("NFKC");
  if (/(?:bearer|basic)\s+\S+/i.test(inspected) || /\b(?:gh[pousr]_|github_pat_|sk[-_]|AKIA)[a-z0-9_-]+/i.test(inspected)) return false;
  if (/^[a-z0-9_-]+\.[a-z0-9_-]+\.[a-z0-9_-]+$/i.test(inspected) || /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(inspected)) return false;
  // Long opaque identifiers and obvious personal identifiers do not belong in
  // saved route evidence. This is deliberately conservative, not a DLP claim.
  if (/[a-z0-9_+/=-]{24,}/i.test(inspected) || /\d{11,}/.test(inspected.replace(/[\s.+-]/g, "")) || /[^\s@]+@[^\s@]+\.[^\s@]+/.test(inspected)) return false;
  return true;
}

function normalizedRoute(value, resourceQueryKeys = []) {
  const publicResources = new Set(normalizeResourceQueryKeys(resourceQueryKeys));
  if (!boundedText(value, MAX_ROUTE_BYTES, false) || !value.startsWith("/") || value.startsWith("//") || /[\\#]/.test(value)) fail("Use a local application path without a fragment or unsafe characters.");
  const question = value.indexOf("?");
  const pathname = question < 0 ? value : value.slice(0, question);
  const search = question < 0 ? "" : value.slice(question + 1);
  let decodedPath;
  try {
    decodedPath = decodeURIComponent(pathname);
    // URLSearchParams tolerates malformed escapes and invalid UTF-8; the
    // explicit decode prevents storing a silently changed route instead.
    decodeURIComponent(search.replace(/\+/g, " "));
  } catch { fail("The application path contains invalid URL encoding."); }
  if (!boundedText(decodedPath, MAX_ROUTE_BYTES, false) || /[%\\?#]/.test(decodedPath) ||
      /%2f/i.test(pathname) || decodedPath.startsWith("//") || decodedPath.split("/").some(part => part === "." || part === "..")) fail("The application path contains an unsafe path segment.");
  // Path segments are persisted as evidence too. Apply the same conservative
  // credential/identifier policy; never strip a segment or turn it into a
  // different navigable route. UUID exceptions apply only to declared query keys.
  if (decodedPath.split("/").some(part => part && !safeQueryValue(part))) fail("The application path contains a private or unsupported path segment. Use a public mock route.");
  const parameters = new URLSearchParams(search);
  const entries = [...parameters];
  if (entries.length > MAX_QUERY_ITEMS) fail("The application path has too many query parameters.");
  const names = new Set();
  for (const [name, entry] of entries) {
    if (!safeQueryName(name) || names.has(name.toLowerCase()) ||
        !(safeQueryValue(entry) || publicResources.has(name.toLowerCase()) && RESOURCE_UUID.test(entry))) fail("The application path contains a private, ambiguous or unsupported query parameter. Use a public mock route.");
    names.add(name.toLowerCase());
  }
  const normalized = new URL(pathname, "http://localhost").pathname + (entries.length ? `?${parameters.toString()}` : "");
  if (Buffer.byteLength(normalized, "utf8") > MAX_ROUTE_BYTES) fail("The application path is too long.");
  return normalized;
}

function validApplicationRoute(value, resourceQueryKeys = []) {
  try { normalizedRoute(value, resourceQueryKeys); return true; } catch { return false; }
}

// Persisted evidence has no connection authority. Its workspace separately
// checks the declared resource-key policy before registering any screen. This
// structural validator permits UUID evidence only under otherwise public keys;
// it never turns an unregistered route into a permitted page or comment.
function evidenceRoute(value) {
  if (typeof value !== "string") fail("Invalid application evidence route.");
  const query = value.includes("?") ? value.slice(value.indexOf("?") + 1) : "";
  const resourceKeys = [...new URLSearchParams(query)].filter(([, entry]) => RESOURCE_UUID.test(entry)).map(([name]) => name);
  return normalizedRoute(value, resourceKeys);
}

function parseApplication(value) {
  if (!(exact(value, ["name", "url"]) || exact(value, ["name", "url", "resourceQueryKeys"])) || !boundedText(value.name, 200, false) || !boundedText(value.url, MAX_URL_BYTES, false) || value.url.trim() !== value.url) fail("Provide an application name and a local HTTP or HTTPS address.");
  const resourceQueryKeys = normalizeResourceQueryKeys(Object.hasOwn(value, "resourceQueryKeys") ? value.resourceQueryKeys : []);
  const match = /^(https?):\/\/([^/?#]+)([^?#]*)(\?[^#]*)?$/i.exec(value.url);
  if (!match || /[@%\\]/.test(match[2])) fail("Use a local HTTP or HTTPS address without credentials or a fragment.");
  let parsed;
  try { parsed = new URL(value.url); } catch { fail("The local application address is invalid."); }
  const authority = match[2];
  const host = authority.startsWith("[") ? authority.slice(0, authority.indexOf("]") + 1) : authority.split(":")[0];
  const ipv4 = /^127\.(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})$/.exec(host);
  const loopback = host.toLowerCase() === "localhost" || ipv4 && ipv4.slice(1).every(part => Number(part) <= 255) ||
    /^\[[0-9a-f:]+\]$/i.test(host) && parsed.hostname === "[::1]";
  if (!loopback || parsed.port === "0") fail("The application address must use localhost or a loopback IP with a valid port.");
  // Reject nonstandard numeric host spellings, empty ports, and URL parser
  // authority repairs. Canonical IPv6 and normal default ports remain valid.
  const port = authority.slice(host.length);
  if (port && !/^:[1-9][0-9]{0,4}$/.test(port)) fail("The local application port is invalid.");
  const startPath = normalizedRoute((match[3] || "/") + (match[4] || ""), resourceQueryKeys);
  return { name: value.name.trim(), url: parsed.origin + startPath, origin: parsed.origin, startPath, ...(resourceQueryKeys.length ? { resourceQueryKeys } : {}) };
}

function screenIdentity(checkpoint, route) {
  if (typeof checkpoint !== "string" || !HASH.test(checkpoint)) fail("The application checkpoint is invalid.");
  return crypto.createHash("sha256").update("application\0").update(checkpoint).update("\0").update(evidenceRoute(route)).digest("hex").slice(0, 32);
}

function validApplicationScreen(value) {
  try {
    return exact(value, ["screen", "source"]) && typeof value.screen === "string" && SCREEN.test(value.screen) &&
      exact(value.source, ["kind", "checkpoint", "route"]) && value.source.kind === "application" &&
      typeof value.source.checkpoint === "string" && HASH.test(value.source.checkpoint) && Boolean(evidenceRoute(value.source.route)) &&
      value.screen === screenIdentity(value.source.checkpoint, value.source.route);
  } catch { return false; }
}

function validApplicationContext(value) {
  try {
    if (!exact(value, ["route", "target", "viewport"]) || !evidenceRoute(value.route) ||
        !exact(value.target, ["tag", "role", "name", "text", "path"]) || !exact(value.viewport, ["width", "height", "scrollX", "scrollY"])) return false;
    const { target, viewport } = value;
    if (typeof target.tag !== "string" || !/^[a-z][a-z0-9-]{0,63}$/.test(target.tag) || !ROLES.has(target.role) ||
        !boundedText(target.name, 240) || !boundedText(target.text, 1000) || !boundedText(target.path, 512, false) || !DOM_PATH.test(target.path)) return false;
    // Accessible labels may describe a field. Its current value, selected
    // option and editable text are never part of this evidence contract.
    if ((FIELD_TAGS.has(target.tag) || FIELD_ROLES.has(target.role)) && target.text !== "") return false;
    return ["width", "height"].every(key => Number.isFinite(viewport[key]) && viewport[key] >= 1 && viewport[key] <= 20000) &&
      ["scrollX", "scrollY"].every(key => Number.isFinite(viewport[key]) && viewport[key] >= 0 && viewport[key] <= 1000000);
  } catch { return false; }
}

module.exports = { parseApplication, normalizeApplicationRoute: normalizedRoute, normalizeResourceQueryKeys, validApplicationRoute, validApplicationScreen, validApplicationContext, screenIdentity };
