#!/usr/bin/env node

/**
 * Visual Companion Server
 *
 * A loopback-only, zero-dependency preview server. Agent-authored HTML is
 * rendered in a sandboxed, opaque-origin iframe. The fixed parent shell owns
 * all HTTP interaction and persists only validated, opaque selection IDs.
 *
 * Usage:
 *   node server.js --project-dir /path/to/project [--port PORT] [--host LOOPBACK]
 *   node server.js --project-dir /path/to/project --cleanup SESSION_ID
 */

"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");

const MAX_CONTENT_BYTES = 2 * 1024 * 1024;
const MAX_CSS_BYTES = 8 * 1024 * 1024;
const MAX_EVENT_BODY_BYTES = 1024;
const MAX_EVENT_FILE_BYTES = 64 * 1024;
const MAX_EVENTS = 100;
const TIMEOUT_MS = 30 * 60 * 1000;
const SESSION_ID_PATTERN = /^[a-f0-9]{24}$/;
const SESSION_MARKER = ".visual-companion-session.json";
const PROJECT_MARKER = ".visual-companion-project.json";
const TOOL_ID = "grillmester-visual-companion";
const args = process.argv.slice(2);

function failCli(message) {
  console.error(JSON.stringify({ type: "error", message }));
  process.exit(2);
}

if (args.includes("--cleanup-all")) {
  failCli(
    "Broad cleanup is not supported. Preview exact session IDs and clean them one at a time with --cleanup SESSION_ID.",
  );
}

function getArg(name, fallback) {
  const flag = `--${name}`;
  const index = args.indexOf(flag);
  if (index === -1) return fallback;
  const value = args[index + 1];
  if (!value || value.startsWith("--")) {
    failCli(`${flag} requires a value.`);
  }
  return value;
}

function assertKnownArgs() {
  const valueOptions = new Set([
    "--project-dir",
    "--port",
    "--host",
    "--cleanup",
  ]);
  for (let index = 0; index < args.length; index += 1) {
    const argument = args[index];
    if (!valueOptions.has(argument)) {
      failCli(`Unknown option: ${argument}`);
    }
    index += 1;
    if (index >= args.length || args[index].startsWith("--")) {
      failCli(`${argument} requires a value.`);
    }
  }
}

assertKnownArgs();

function normalizeHost(value) {
  return String(value || "")
    .trim()
    .replace(/^\[(.*)\]$/, "$1")
    .toLowerCase();
}

function isIpv4Octet(value) {
  return /^\d+$/.test(value) && Number(value) >= 0 && Number(value) <= 255;
}

function isLoopbackIpv4(value) {
  const parts = value.split(".");
  return parts.length === 4 && parts[0] === "127" && parts.every(isIpv4Octet);
}

function isLoopbackHost(value) {
  const normalized = normalizeHost(value);
  return (
    normalized === "localhost" ||
    normalized === "::1" ||
    isLoopbackIpv4(normalized)
  );
}

function isLoopbackAddress(value) {
  const normalized = normalizeHost(String(value || "").replace(/^::ffff:/, ""));
  return isLoopbackHost(normalized);
}

function formatHostForUrl(value) {
  const normalized = normalizeHost(value);
  return normalized.includes(":") ? `[${normalized}]` : normalized;
}

function canonicalProjectDirectory(value) {
  const requested = path.resolve(value);
  let stat;
  try {
    stat = fs.lstatSync(requested);
  } catch (error) {
    failCli(`--project-dir must exist: ${error.message}`);
  }
  if (stat.isSymbolicLink() || !stat.isDirectory()) {
    failCli("--project-dir must be an existing, non-symlink directory.");
  }
  return fs.realpathSync(requested);
}

function isPathInside(parentPath, candidatePath) {
  const parent = path.resolve(parentPath);
  const candidate = path.resolve(candidatePath);
  return candidate === parent || candidate.startsWith(`${parent}${path.sep}`);
}

function assertOwnedByCurrentUser(stat, target) {
  if (typeof process.getuid === "function" && stat.uid !== process.getuid()) {
    throw new Error(`Refusing path not owned by the current user: ${target}`);
  }
}

function ensurePrivateDirectory(target, expectedParent) {
  if (!fs.existsSync(target)) {
    try {
      fs.mkdirSync(target, { mode: 0o700 });
    } catch (error) {
      if (error.code !== "EEXIST") throw error;
    }
  }
  const stat = fs.lstatSync(target);
  if (stat.isSymbolicLink() || !stat.isDirectory()) {
    throw new Error(`Refusing unsafe runtime directory: ${target}`);
  }
  assertOwnedByCurrentUser(stat, target);
  fs.chmodSync(target, 0o700);
  const realTarget = fs.realpathSync(target);
  if (expectedParent && !isPathInside(expectedParent, realTarget)) {
    throw new Error(`Runtime directory escaped its parent: ${target}`);
  }
  return realTarget;
}

function existingPrivateDirectory(target, expectedParent) {
  if (!fs.existsSync(target)) return null;
  const stat = fs.lstatSync(target);
  if (stat.isSymbolicLink() || !stat.isDirectory()) {
    throw new Error(`Refusing unsafe runtime directory: ${target}`);
  }
  assertOwnedByCurrentUser(stat, target);
  const realTarget = fs.realpathSync(target);
  if (expectedParent && !isPathInside(expectedParent, realTarget)) {
    throw new Error(`Runtime directory escaped its parent: ${target}`);
  }
  return realTarget;
}

function openReadOnlyNoFollow(target) {
  const noFollow = fs.constants.O_NOFOLLOW || 0;
  return fs.openSync(target, fs.constants.O_RDONLY | noFollow);
}

function readRegularFile(target, allowedRoot, maxBytes) {
  const lexicalTarget = path.resolve(target);
  const root = fs.realpathSync(allowedRoot);
  if (!isPathInside(root, lexicalTarget)) {
    throw new Error(`Path is outside its allowed root: ${target}`);
  }
  const linkStat = fs.lstatSync(lexicalTarget);
  if (linkStat.isSymbolicLink() || !linkStat.isFile()) {
    throw new Error(`Refusing non-regular or symlink file: ${target}`);
  }
  const realTarget = fs.realpathSync(lexicalTarget);
  if (!isPathInside(root, realTarget)) {
    throw new Error(`Resolved file escaped its allowed root: ${target}`);
  }
  const descriptor = openReadOnlyNoFollow(realTarget);
  try {
    const stat = fs.fstatSync(descriptor);
    if (!stat.isFile()) {
      throw new Error(`Refusing non-regular file: ${target}`);
    }
    if (stat.size > maxBytes) {
      throw new Error(`File exceeds ${maxBytes} bytes: ${target}`);
    }
    return fs.readFileSync(descriptor, "utf8");
  } finally {
    fs.closeSync(descriptor);
  }
}

function writePrivateJson(target, value, flag = "w") {
  fs.writeFileSync(target, `${JSON.stringify(value, null, 2)}\n`, {
    encoding: "utf8",
    flag,
    mode: 0o600,
  });
  fs.chmodSync(target, 0o600);
}

function readJsonMarker(target, allowedRoot) {
  const content = readRegularFile(target, allowedRoot, 4096);
  return JSON.parse(content);
}

const projectDir = canonicalProjectDirectory(
  getArg("project-dir", process.cwd()),
);
const host = getArg("host", "127.0.0.1");
if (!isLoopbackHost(host)) {
  failCli(`Refusing non-local bind host "${host}".`);
}
const requestedPort = Number(getArg("port", "0"));
if (!Number.isInteger(requestedPort) || requestedPort < 0 || requestedPort > 65535) {
  failCli("--port must be an integer from 0 through 65535.");
}

const tempRoot = fs.realpathSync(os.tmpdir());
const runtimeRootPath = path.join(
  tempRoot,
  `grillmester-visual-companion-${
    typeof process.getuid === "function" ? process.getuid() : "user"
  }`,
);
const projectHash = crypto
  .createHash("sha256")
  .update(projectDir)
  .digest("hex")
  .slice(0, 24);
const projectRootPath = path.join(runtimeRootPath, projectHash);
const sessionsRootPath = path.join(projectRootPath, "sessions");

function verifyProjectMarker(projectRoot) {
  const marker = readJsonMarker(path.join(projectRoot, PROJECT_MARKER), projectRoot);
  if (
    marker.schemaVersion !== 1 ||
    marker.tool !== TOOL_ID ||
    marker.projectHash !== projectHash
  ) {
    throw new Error(`Refusing runtime directory with invalid project marker.`);
  }
}

function ensureProjectRuntime() {
  const runtimeRoot = ensurePrivateDirectory(runtimeRootPath, tempRoot);
  const projectRoot = ensurePrivateDirectory(projectRootPath, runtimeRoot);
  const markerPath = path.join(projectRoot, PROJECT_MARKER);
  if (!fs.existsSync(markerPath)) {
    try {
      writePrivateJson(
        markerPath,
        { schemaVersion: 1, tool: TOOL_ID, projectHash },
        "wx",
      );
    } catch (error) {
      if (error.code !== "EEXIST") throw error;
    }
  }
  verifyProjectMarker(projectRoot);
  const sessionsRoot = ensurePrivateDirectory(sessionsRootPath, projectRoot);
  return { runtimeRoot, projectRoot, sessionsRoot };
}

function locateProjectRuntime() {
  const runtimeRoot = existingPrivateDirectory(runtimeRootPath, tempRoot);
  if (!runtimeRoot) return null;
  const projectRoot = existingPrivateDirectory(projectRootPath, runtimeRoot);
  if (!projectRoot) return null;
  verifyProjectMarker(projectRoot);
  const sessionsRoot = existingPrivateDirectory(sessionsRootPath, projectRoot);
  if (!sessionsRoot) return null;
  return { runtimeRoot, projectRoot, sessionsRoot };
}

function removeOwnedSession(sessionId) {
  if (!SESSION_ID_PATTERN.test(sessionId)) {
    throw new Error("Session ID must be exactly 24 lowercase hexadecimal characters.");
  }
  const runtime = locateProjectRuntime();
  if (!runtime) return null;
  const sessionPath = path.join(runtime.sessionsRoot, sessionId);
  const sessionRoot = existingPrivateDirectory(sessionPath, runtime.sessionsRoot);
  if (!sessionRoot) return null;
  const marker = readJsonMarker(path.join(sessionRoot, SESSION_MARKER), sessionRoot);
  if (
    marker.schemaVersion !== 1 ||
    marker.tool !== TOOL_ID ||
    marker.projectHash !== projectHash ||
    marker.sessionId !== sessionId
  ) {
    throw new Error("Refusing cleanup because the session marker is invalid.");
  }
  fs.rmSync(sessionRoot, { recursive: true });
  return sessionRoot;
}

const cleanupSessionId = getArg("cleanup", null);
if (cleanupSessionId) {
  try {
    const removed = removeOwnedSession(cleanupSessionId);
    console.log(
      JSON.stringify(
        removed
          ? { type: "cleanup", session_id: cleanupSessionId, removed }
          : {
              type: "cleanup",
              session_id: cleanupSessionId,
              message: "nothing to clean",
            },
      ),
    );
    process.exit(0);
  } catch (error) {
    failCli(error.message);
  }
}

const runtime = ensureProjectRuntime();
let sessionId;
let sessionRoot;
for (let attempt = 0; attempt < 5; attempt += 1) {
  const candidateId = crypto.randomBytes(12).toString("hex");
  const candidatePath = path.join(runtime.sessionsRoot, candidateId);
  try {
    fs.mkdirSync(candidatePath, { mode: 0o700 });
    sessionId = candidateId;
    sessionRoot = fs.realpathSync(candidatePath);
    break;
  } catch (error) {
    if (error.code !== "EEXIST") throw error;
  }
}
if (!sessionRoot) {
  throw new Error("Could not allocate a unique Visual Companion session.");
}

const contentDir = ensurePrivateDirectory(
  path.join(sessionRoot, "content"),
  sessionRoot,
);
const stateDir = ensurePrivateDirectory(
  path.join(sessionRoot, "state"),
  sessionRoot,
);
writePrivateJson(
  path.join(sessionRoot, SESSION_MARKER),
  {
    schemaVersion: 1,
    tool: TOOL_ID,
    projectHash,
    sessionId,
    createdAt: new Date().toISOString(),
  },
  "wx",
);

const scriptsDir = fs.realpathSync(__dirname);
const frameTemplate = readRegularFile(
  path.join(scriptsDir, "frame-template.tmpl"),
  scriptsDir,
  512 * 1024,
);
const helperJs = readRegularFile(
  path.join(scriptsDir, "helper.js"),
  scriptsDir,
  128 * 1024,
);

function loadAkselCss() {
  const candidates = [
    path.join(projectDir, "node_modules/@navikt/ds-css/dist/index.min.css"),
    path.join(projectDir, "node_modules/@navikt/ds-css/dist/index.css"),
  ];
  const failures = [];
  for (const candidate of candidates) {
    if (!fs.existsSync(candidate)) continue;
    try {
      return readRegularFile(candidate, projectDir, MAX_CSS_BYTES);
    } catch (error) {
      failures.push(error.message);
    }
  }
  console.error(
    JSON.stringify({
      type: "warning",
      message: failures.length
        ? `Aksel CSS was rejected: ${failures.join("; ")}`
        : "Aksel CSS is unavailable. Preview continues with fallback styles; do not install dependencies without explicit approval.",
    }),
  );
  return null;
}

const akselCss = loadAkselCss();

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function serializeForInlineScript(value) {
  return JSON.stringify(value)
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/&/g, "\\u0026")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}

function safeInlineStyle(value) {
  return String(value).replace(/<\/style/gi, "<\\/style");
}

function stripActivePreviewMarkup(value) {
  return String(value)
    .replace(/<script\b[^>]*>[\s\S]*?<\/script\s*>/gi, "")
    .replace(/<script\b[^>]*\/?\s*>/gi, "")
    .replace(/<\s*(?:meta|base|link|iframe|object|embed)\b[^>]*>/gi, "")
    .replace(
      /\s(?:src|href|xlink:href|action|formaction|poster|ping)\s*=\s*(["'])\s*(?:https?:|\/\/|file:|ftp:|javascript:)[\s\S]*?\1/gi,
      "",
    )
    .replace(
      /\s(?:src|href|xlink:href|action|formaction|poster|ping)\s*=\s*(?:https?:|\/\/|file:|ftp:|javascript:)[^\s>]*/gi,
      "",
    );
}

function newestContent() {
  const candidates = [];
  for (const entry of fs.readdirSync(contentDir, { withFileTypes: true })) {
    if (!entry.name.endsWith(".html") || !entry.isFile()) continue;
    const candidate = path.join(contentDir, entry.name);
    try {
      const stat = fs.lstatSync(candidate);
      if (stat.isSymbolicLink() || !stat.isFile() || stat.size > MAX_CONTENT_BYTES) {
        continue;
      }
      candidates.push({
        filename: entry.name,
        path: candidate,
        mtimeMs: stat.mtimeMs,
        size: stat.size,
      });
    } catch {
      // Ignore a file that changed during directory enumeration.
    }
  }
  candidates.sort(
    (left, right) =>
      right.mtimeMs - left.mtimeMs || left.filename.localeCompare(right.filename),
  );
  for (const candidate of candidates) {
    try {
      return {
        filename: candidate.filename,
        version: `${candidate.filename}:${candidate.mtimeMs}:${candidate.size}`,
        content: readRegularFile(
          candidate.path,
          contentDir,
          MAX_CONTENT_BYTES,
        ),
      };
    } catch {
      // A concurrent writer may have replaced the file; try the next safe one.
    }
  }
  return null;
}

function wrapInFrame(content, filename, nonce) {
  const safeFilename = escapeHtml(filename || "untitled");
  const safeContent = stripActivePreviewMarkup(content);
  const akselStyle = akselCss
    ? `<style nonce="${nonce}">\n${safeInlineStyle(akselCss)}\n</style>`
    : "";
  const cssWarning = akselCss
    ? ""
    : `<div role="status" style="background:#fef0f0;border:2px solid #c30000;padding:16px;margin-bottom:16px;border-radius:8px;font-family:sans-serif">
        <strong>⚠️ Aksel CSS mangler</strong><br>Forhåndsvisningen bruker fallback-stiler. Installer aldri avhengigheter uten eksplisitt godkjenning.
      </div>`;
  return frameTemplate
    .replace(/\{\{FILENAME\}\}/g, safeFilename)
    .replace(/\{\{NONCE\}\}/g, nonce)
    .replace(/\{\{AKSEL_STYLE\}\}/g, () => akselStyle)
    .replace(
      /\{\{HELPER_SCRIPT\}\}/g,
      () => `<script nonce="${nonce}">\n${helperJs}\n</script>`,
    )
    .replace(/\{\{CONTENT\}\}/g, () => cssWarning + safeContent);
}

function renderShellPage(nonce, accessToken, title) {
  const previewPath = `/preview?token=${encodeURIComponent(accessToken)}`;
  const versionPath = `/version?token=${encodeURIComponent(accessToken)}`;
  const eventsPath = `/events?token=${encodeURIComponent(accessToken)}`;
  return `<!DOCTYPE html>
<html lang="nb">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Visual Companion — ${escapeHtml(title || "prototype")}</title>
  <style nonce="${nonce}">
    html, body { width: 100%; height: 100%; margin: 0; background: #f7f7f7; }
    iframe { display: block; width: 100%; height: 100%; border: 0; }
  </style>
</head>
<body>
  <iframe id="vc-preview" sandbox="allow-scripts" referrerpolicy="no-referrer" title="Designskisse" src="${escapeHtml(previewPath)}"></iframe>
  <script nonce="${nonce}">
    (() => {
      "use strict";
      const channel = "grillmester-visual-companion";
      const frame = document.getElementById("vc-preview");
      const versionUrl = ${serializeForInlineScript(versionPath)};
      const eventsUrl = ${serializeForInlineScript(eventsPath)};
      let lastVersion = null;

      function hasExactKeys(value, keys) {
        if (!value || typeof value !== "object" || Array.isArray(value)) return false;
        const actual = Object.keys(value).sort();
        const expected = [...keys].sort();
        return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
      }

      function validSelectionMessage(data) {
        return hasExactKeys(data, ["channel", "version", "event"]) &&
          data.channel === channel &&
          data.version === 1 &&
          hasExactKeys(data.event, ["type", "choice"]) &&
          (data.event.type === "click" || data.event.type === "deselect") &&
          /^choice-[1-9][0-9]{0,3}$/.test(data.event.choice);
      }

      window.addEventListener("message", (message) => {
        if (message.source !== frame.contentWindow || !validSelectionMessage(message.data)) return;
        fetch(eventsUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(message.data.event),
          credentials: "same-origin",
        }).catch(() => {});
      });

      setInterval(() => {
        fetch(versionUrl, { credentials: "same-origin", cache: "no-store" })
          .then((response) => response.ok ? response.text() : "")
          .then((version) => {
            if (lastVersion === null) {
              lastVersion = version;
            } else if (version && version !== lastVersion) {
              lastVersion = version;
              frame.contentWindow.postMessage({ channel, version: 1, command: "refreshing" }, "*");
              setTimeout(() => {
                const next = new URL(${serializeForInlineScript(previewPath)}, window.location.origin);
                next.searchParams.set("v", version);
                frame.src = next.pathname + next.search;
              }, 400);
            }
          })
          .catch(() => {});
      }, 2000);
    })();
  </script>
</body>
</html>`;
}

function shellCsp(nonce) {
  return [
    "default-src 'none'",
    `script-src 'nonce-${nonce}'`,
    `style-src 'nonce-${nonce}'`,
    "connect-src 'self'",
    "frame-src 'self'",
    "img-src 'none'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
    "frame-ancestors 'none'",
  ].join("; ");
}

function previewCsp(nonce) {
  return [
    "default-src 'none'",
    `script-src 'nonce-${nonce}'`,
    "script-src-attr 'none'",
    `style-src 'nonce-${nonce}'`,
    `style-src-elem 'nonce-${nonce}'`,
    "style-src-attr 'unsafe-inline'",
    "connect-src 'none'",
    "img-src data: blob:",
    "font-src data:",
    "media-src 'none'",
    "frame-src 'none'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
    "frame-ancestors 'self'",
    "navigate-to 'none'",
  ].join("; ");
}

function setCommonHeaders(res) {
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("Cross-Origin-Resource-Policy", "same-origin");
  res.setHeader("Referrer-Policy", "no-referrer");
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.setHeader(
    "Permissions-Policy",
    "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  );
}

const accessToken = crypto.randomBytes(32).toString("base64url");
const tokenBuffer = Buffer.from(accessToken);
let authority = null;
let eventCount = 0;
let lastActivity = Date.now();
let activeSessionRemoved = false;

function validToken(candidate) {
  if (typeof candidate !== "string") return false;
  const candidateBuffer = Buffer.from(candidate);
  return (
    candidateBuffer.length === tokenBuffer.length &&
    crypto.timingSafeEqual(candidateBuffer, tokenBuffer)
  );
}

function validEvent(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const keys = Object.keys(value).sort();
  return (
    keys.length === 2 &&
    keys[0] === "choice" &&
    keys[1] === "type" &&
    (value.type === "click" || value.type === "deselect") &&
    typeof value.choice === "string" &&
    /^choice-[1-9][0-9]{0,3}$/.test(value.choice)
  );
}

function appendEvent(event) {
  if (eventCount >= MAX_EVENTS) return false;
  const eventPath = path.join(stateDir, "events.jsonl");
  const line = `${JSON.stringify({
    type: event.type,
    choice: event.choice,
    timestamp: Date.now(),
  })}\n`;
  const noFollow = fs.constants.O_NOFOLLOW || 0;
  const descriptor = fs.openSync(
    eventPath,
    fs.constants.O_WRONLY |
      fs.constants.O_CREAT |
      fs.constants.O_APPEND |
      noFollow,
    0o600,
  );
  try {
    const stat = fs.fstatSync(descriptor);
    if (!stat.isFile() || stat.size + Buffer.byteLength(line) > MAX_EVENT_FILE_BYTES) {
      return false;
    }
    fs.writeSync(descriptor, line, null, "utf8");
    fs.fchmodSync(descriptor, 0o600);
    eventCount += 1;
    return true;
  } finally {
    fs.closeSync(descriptor);
  }
}

function readEventBody(req, res) {
  let chunks = [];
  let size = 0;
  let rejected = false;
  req.on("data", (chunk) => {
    if (rejected) return;
    size += chunk.length;
    if (size > MAX_EVENT_BODY_BYTES) {
      rejected = true;
      chunks = [];
      res.writeHead(413, { "Content-Type": "application/json; charset=utf-8" });
      res.end('{"error":"payload too large"}');
      return;
    }
    chunks.push(chunk);
  });
  req.on("end", () => {
    if (rejected || res.writableEnded) return;
    let event;
    try {
      event = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    } catch {
      res.writeHead(400, { "Content-Type": "application/json; charset=utf-8" });
      res.end('{"error":"invalid json"}');
      return;
    }
    if (!validEvent(event)) {
      res.writeHead(400, { "Content-Type": "application/json; charset=utf-8" });
      res.end('{"error":"invalid event"}');
      return;
    }
    if (!appendEvent(event)) {
      res.writeHead(429, { "Content-Type": "application/json; charset=utf-8" });
      res.end('{"error":"event limit reached"}');
      return;
    }
    lastActivity = Date.now();
    res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
    res.end('{"ok":true}');
  });
}

const server = http.createServer((req, res) => {
  setCommonHeaders(res);
  if (!isLoopbackAddress(req.socket.remoteAddress)) {
    res.writeHead(403, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Remote access is disabled.");
    return;
  }
  if (!authority || String(req.headers.host || "").toLowerCase() !== authority) {
    res.writeHead(403, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Invalid host.");
    return;
  }

  let requestUrl;
  try {
    requestUrl = new URL(req.url, `http://${authority}`);
  } catch {
    res.writeHead(400, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Invalid URL.");
    return;
  }
  if (!validToken(requestUrl.searchParams.get("token"))) {
    res.writeHead(403, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Invalid session token.");
    return;
  }
  const expectedOrigin = `http://${authority}`;
  if (req.headers.origin && req.headers.origin !== expectedOrigin) {
    res.writeHead(403, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Invalid origin.");
    return;
  }

  if (requestUrl.pathname === "/events") {
    if (req.method !== "POST") {
      res.setHeader("Allow", "POST");
      res.writeHead(405, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Method not allowed.");
      return;
    }
    if (req.headers.origin !== expectedOrigin) {
      res.writeHead(403, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Event writes require the exact server origin.");
      return;
    }
    if (!String(req.headers["content-type"] || "").startsWith("application/json")) {
      res.writeHead(415, { "Content-Type": "application/json; charset=utf-8" });
      res.end('{"error":"application/json required"}');
      return;
    }
    readEventBody(req, res);
    return;
  }

  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    res.writeHead(405, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Method not allowed.");
    return;
  }

  if (requestUrl.pathname === "/health") {
    res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
    res.end(JSON.stringify({ status: "ok", session: sessionId }));
    return;
  }

  const newest = newestContent();
  if (requestUrl.pathname === "/version") {
    lastActivity = Date.now();
    res.writeHead(200, { "Content-Type": "text/plain; charset=utf-8" });
    res.end(newest ? newest.version : "");
    return;
  }

  if (requestUrl.pathname === "/") {
    lastActivity = Date.now();
    const nonce = crypto.randomBytes(18).toString("base64url");
    res.setHeader("Content-Security-Policy", shellCsp(nonce));
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(renderShellPage(nonce, accessToken, newest?.filename || "prototype"));
    return;
  }

  if (requestUrl.pathname === "/preview") {
    lastActivity = Date.now();
    const nonce = crypto.randomBytes(18).toString("base64url");
    res.setHeader("Content-Security-Policy", previewCsp(nonce));
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    const content = newest
      ? newest.content
      : `<div style="display:flex;align-items:center;justify-content:center;min-height:60vh">
          <div style="text-align:center">
            <h2>Venter på innhold …</h2>
            <p class="subtitle">Agenten skriver en skisse. Siden oppdateres automatisk.</p>
          </div>
        </div>`;
    res.end(wrapInFrame(content, newest?.filename || "waiting", nonce));
    return;
  }

  res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
  res.end("Not found.");
});
server.requestTimeout = 5_000;
server.headersTimeout = 5_000;
server.keepAliveTimeout = 5_000;
server.maxHeadersCount = 64;

function cleanupActiveSession() {
  if (activeSessionRemoved) return;
  activeSessionRemoved = true;
  try {
    removeOwnedSession(sessionId);
  } catch {
    // Cleanup must not mask the original shutdown reason.
  }
}

function shutdown(reason) {
  console.log(JSON.stringify({ type: "server-stopped", reason }));
  server.close();
  server.closeAllConnections?.();
  cleanupActiveSession();
  process.exit(0);
}

setInterval(() => {
  if (Date.now() - lastActivity > TIMEOUT_MS) shutdown("inactivity");
}, 60_000).unref();

process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));
process.on("exit", cleanupActiveSession);

server.on("error", (error) => {
  cleanupActiveSession();
  console.error(
    JSON.stringify({ type: "error", message: `Server failed: ${error.message}` }),
  );
  process.exit(1);
});

server.listen(requestedPort, normalizeHost(host), () => {
  const address = server.address();
  const port = typeof address === "object" && address ? address.port : requestedPort;
  authority = `${formatHostForUrl(host)}:${port}`.toLowerCase();
  const url = `http://${authority}/?token=${encodeURIComponent(accessToken)}`;
  const info = {
    type: "server-started",
    pid: process.pid,
    port,
    url,
    screen_dir: contentDir,
    state_dir: stateDir,
    session_id: sessionId,
  };
  writePrivateJson(path.join(stateDir, "server-info.json"), info);
  console.log(JSON.stringify(info));
});
