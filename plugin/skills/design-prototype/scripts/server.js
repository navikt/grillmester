#!/usr/bin/env node

/**
 * Visual Companion Server
 *
 * A loopback-only, zero-dependency preview server. Agent-authored HTML is
 * rendered in a sandboxed, opaque-origin iframe. The fixed parent shell owns
 * all HTTP interaction. Opaque selections and explicitly authored feedback
 * are persisted separately in private, bounded session state.
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
const { FeedbackStore, FeedbackError, FeedbackMutationReceipts, MAX_BODY_BYTES, keys } = require("./feedback-store.js");
const { CanvasState } = require("./canvas-state.js");
const { createHtmlEmbedding, renderEmbeddingBootstrap } = require("./html-embedding.js");
const { WorkspaceStore, validWorkspacePath } = require("./workspace-store.js");
const { WorkspaceState, validWorkspaceState, screenIdentity } = require("./workspace-state.js");
const { promoteTemporaryWorkspace } = require("./workspace-promotion.js");
const { validDesign, MAX_DESIGN_BYTES } = require("./design-contract.js");
const { validateEditorBindings, editorBindingErrorMessage } = require("./editor-bindings.js");

const MAX_CONTENT_BYTES = 2 * 1024 * 1024;
const MAX_INLINE_IMAGE_URL_BYTES = MAX_CONTENT_BYTES;
const MAX_CSS_BYTES = 8 * 1024 * 1024;
const MAX_EVENT_BODY_BYTES = 1024;
const MAX_EVENT_FILE_BYTES = 64 * 1024;
const MAX_EVENTS = 100;
const DEFAULT_IDLE_TIMEOUT_MINUTES = 4 * 60;
const MAX_IDLE_TIMEOUT_MINUTES = 8 * 60;
const SESSION_ID_PATTERN = /^[a-f0-9]{24}$/;
const SESSION_MARKER = ".visual-companion-session.json";
const PROJECT_MARKER = ".visual-companion-project.json";
const TOOL_ID = "grillmester-visual-companion";
const args = process.argv.slice(2);
const canvasMode = typeof process.send === "function" && process.connected;
let workspaceStore = null;
let workspaceState = null;

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
    "--idle-timeout-minutes",
    "--workspace-dir",
    "--workspace-create",
    "--workspace-title",
    "--style-project-path",
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

function openExistingReadOnly(target) {
  const { O_NOFOLLOW, O_NONBLOCK } = fs.constants;
  if (!Number.isInteger(O_NOFOLLOW) || !Number.isInteger(O_NONBLOCK)) {
    throw new Error("Safe file opening requires O_NOFOLLOW and O_NONBLOCK support.");
  }
  // Refuse a symlink swapped in after validation, and never block if a file
  // becomes a FIFO. Descriptor checks below still verify identity before reads.
  // No O_CREAT: missing files stay missing; 0600 states the private-file policy.
  return fs.openSync(
    target,
    fs.constants.O_RDONLY | O_NOFOLLOW | O_NONBLOCK,
    0o600,
  );
}

function readDescriptorAtMost(descriptor, maxBytes, target) {
  const chunks = [];
  let total = 0;
  while (total <= maxBytes) {
    const remaining = maxBytes + 1 - total;
    const buffer = Buffer.allocUnsafe(Math.min(64 * 1024, remaining));
    const count = fs.readSync(descriptor, buffer, 0, buffer.length, null);
    if (count === 0) break;
    chunks.push(buffer.subarray(0, count));
    total += count;
  }
  if (total > maxBytes) {
    throw new Error(`File exceeds ${maxBytes} bytes: ${target}`);
  }
  return Buffer.concat(chunks, total);
}

function readRegularFile(target, allowedRoot, maxBytes, raw = false) {
  const lexicalTarget = path.resolve(target);
  const root = fs.realpathSync(allowedRoot);
  if (!isPathInside(root, lexicalTarget)) {
    throw new Error(`Path is outside its allowed root: ${target}`);
  }
  const linkStat = fs.lstatSync(lexicalTarget, { bigint: true });
  if (linkStat.isSymbolicLink() || !linkStat.isFile()) {
    throw new Error(`Refusing non-regular or symlink file: ${target}`);
  }
  const realTarget = fs.realpathSync(lexicalTarget);
  if (!isPathInside(root, realTarget)) {
    throw new Error(`Resolved file escaped its allowed root: ${target}`);
  }
  const descriptor = openExistingReadOnly(realTarget);
  try {
    const before = fs.fstatSync(descriptor, { bigint: true });
    if (!before.isFile()) {
      throw new Error(`Refusing non-regular file: ${target}`);
    }
    if (before.dev !== linkStat.dev || before.ino !== linkStat.ino) {
      throw new Error(`File changed while it was being opened: ${target}`);
    }
    if (before.size > BigInt(maxBytes)) {
      throw new Error(`File exceeds ${maxBytes} bytes: ${target}`);
    }
    const content = readDescriptorAtMost(descriptor, maxBytes, target);
    const after = fs.fstatSync(descriptor, { bigint: true });
    if (
      !after.isFile() ||
      after.dev !== before.dev ||
      after.ino !== before.ino ||
      after.mode !== before.mode ||
      after.nlink !== before.nlink ||
      after.size !== before.size ||
      after.mtimeNs !== before.mtimeNs ||
      after.ctimeNs !== before.ctimeNs ||
      BigInt(content.length) !== before.size
    ) {
      throw new Error(`File changed while it was being read: ${target}`);
    }
    return raw ? content : content.toString("utf8");
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
const workspacePath = getArg("workspace-dir", null);
const workspaceCreate = getArg("workspace-create", "false");
const workspaceTitle = getArg("workspace-title", null);
const styleProjectPath = getArg("style-project-path", "");
if (styleProjectPath && (Buffer.byteLength(styleProjectPath) > 240 || styleProjectPath.split("/").length > 8
    || styleProjectPath.split("/").some(part => !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(part)
      || /^(?:node_modules|__pycache__|con|prn|aux|nul|com[1-9]|lpt[1-9])$/i.test(part)))) {
  failCli("--style-project-path must be a bounded project-relative directory.");
}
if (!["true", "false"].includes(workspaceCreate) || (workspacePath && !canvasMode) ||
    (!workspacePath && (args.includes("--workspace-create") || workspaceTitle)) || (workspaceTitle && workspaceCreate !== "true")) {
  failCli("Project workspaces require a bound canvas and an explicit workspace directory.");
}
const host = getArg("host", "127.0.0.1");
if (!isLoopbackHost(host)) {
  failCli(`Refusing non-local bind host "${host}".`);
}
const requestedPort = Number(getArg("port", "0"));
if (!Number.isInteger(requestedPort) || requestedPort < 0 || requestedPort > 65535) {
  failCli("--port must be an integer from 0 through 65535.");
}
const idleTimeoutMinutes = Number(
  getArg("idle-timeout-minutes", String(DEFAULT_IDLE_TIMEOUT_MINUTES)),
);
if (
  !Number.isInteger(idleTimeoutMinutes) ||
  idleTimeoutMinutes < 1 ||
  idleTimeoutMinutes > MAX_IDLE_TIMEOUT_MINUTES
) {
  failCli(
    `--idle-timeout-minutes must be an integer from 1 through ${MAX_IDLE_TIMEOUT_MINUTES}.`,
  );
}
const idleTimeoutMs = idleTimeoutMinutes * 60 * 1000;

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
const workshopJs = readRegularFile(
  path.join(scriptsDir, "workshop.js"),
  scriptsDir,
  128 * 1024,
);
const editorJs = readRegularFile(path.join(scriptsDir, "editor.js"), scriptsDir, 128 * 1024);

function loadAkselCss() {
  const styleDirectory = path.join(projectDir, styleProjectPath);
  const candidates = [
    path.join(styleDirectory, "node_modules/@navikt/ds-css/dist/index.min.css"),
    path.join(styleDirectory, "node_modules/@navikt/ds-css/dist/index.css"),
  ];
  const failures = [];
  let allowedDirectory = true;
  if (fs.existsSync(styleDirectory)) {
    try {
      const resolved = fs.realpathSync(styleDirectory);
      if (!isPathInside(projectDir, resolved) || !fs.statSync(resolved).isDirectory()) throw new Error("Style project is outside the session project or is not a directory.");
    } catch (error) { failures.push(error.message); allowedDirectory = false; }
  }
  for (const candidate of allowedDirectory ? candidates : []) {
    if (!fs.existsSync(candidate)) continue;
    try {
      const bytes = readRegularFile(candidate, projectDir, MAX_CSS_BYTES, true);
      const css = bytes.toString("utf8");
      if (!css.trim()) throw new Error("Aksel CSS is empty.");
      let version = null;
      try {
        const metadata = JSON.parse(readRegularFile(path.join(styleDirectory, "node_modules/@navikt/ds-css/package.json"), projectDir, 64 * 1024));
        if (metadata.name === "@navikt/ds-css" && typeof metadata.version === "string"
            && /^\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?(?:\+[A-Za-z0-9.-]+)?$/.test(metadata.version)
            && metadata.version.length <= 100) version = metadata.version;
      } catch { /* CSS can be verified even when package version metadata is unavailable. */ }
      return { css, receipt: { styleProjectPath, status: "loaded", source: path.relative(projectDir, candidate).split(path.sep).join("/"),
        version, sha256: crypto.createHash("sha256").update(bytes).digest("hex") } };
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
  return { css: null, receipt: { styleProjectPath, status: "fallback", source: null, version: null, sha256: null,
    reason: failures.length ? "rejected" : "missing" } };
}

const { css: akselCss, receipt: styleReceipt } = loadAkselCss();

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

const FORBIDDEN_PREVIEW_ELEMENTS = new Set([
  "base",
  "embed",
  "iframe",
  "link",
  "meta",
  "noembed",
  "noframes",
  "object",
  "plaintext",
  "script",
  "template",
]);
// These elements switch the HTML tokenizer into a raw-text/RCDATA state. Keep
// well-formed elements (textarea and SVG title are useful in prototypes), but
// discard an opening tag that has no explicit close inside the agent fragment.
// Otherwise it could consume the fixed wrapper that follows {{CONTENT}} in
// frame-template.tmpl. The trusted helper scripts load before the fragment.
const RAW_TEXT_PREVIEW_ELEMENTS = new Set([
  "noscript",
  "style",
  "textarea",
  "title",
  "xmp",
]);
const NETWORK_CAPABLE_ATTRIBUTES = new Set([
  "action",
  "background",
  "cite",
  "codebase",
  "data",
  "formaction",
  "href",
  "ping",
  "poster",
  "src",
  "srcset",
  "xlink:href",
]);
const SAFE_RASTER_DATA_URL = /^data:image\/(?:gif|jpeg|png|webp);base64,([A-Za-z0-9+/]+={0,2})$/;

// The scanner follows the HTML tokenizer where it decides how markup starts and
// ends: no whitespace after "<" or "</", quotes only around attribute values,
// every comment ending, and raw text that ends at the first matching end tag.
// Tags are written back canonically, so the browser reads the same structure.
function isHtmlSpace(character) {
  return (
    character === " " ||
    character === "\t" ||
    character === "\n" ||
    character === "\r" ||
    character === "\f"
  );
}

function isAsciiAlpha(character) {
  return typeof character === "string" && /^[A-Za-z]$/.test(character);
}

function markupDeclarationEnd(source, start) {
  if (source.startsWith("<!--", start)) {
    // "<!-->" and "<!--->" are complete empty comments; otherwise the first
    // "-->" or "--!>" ends the comment.
    if (source[start + 4] === ">") return { end: start + 5, closed: true };
    if (source.startsWith("->", start + 4)) return { end: start + 6, closed: true };
    const ends = [source.indexOf("-->", start + 4), source.indexOf("--!>", start + 4)].filter((index) => index !== -1);
    if (!ends.length) return { end: source.length, closed: false };
    const first = Math.min(...ends);
    return { end: first + (source.startsWith("--!>", first) ? 4 : 3), closed: true };
  }
  // Doctypes, CDATA, processing instructions and other bogus comments end at ">".
  const close = source.indexOf(">", start + 1);
  return close === -1 ? { end: source.length, closed: false } : { end: close + 1, closed: true };
}

function scanHtmlTag(source, start) {
  if (source[start] !== "<") return null;
  const next = source[start + 1];
  if (next === "!" || next === "?") return { ...markupDeclarationEnd(source, start), name: null, comment: true };
  let cursor = start + 1;
  let closing = false;
  if (next === "/") {
    closing = true;
    cursor += 1;
    if (source[cursor] === ">") return { end: cursor + 1, closed: true, name: null, comment: true };
    if (!isAsciiAlpha(source[cursor])) return { ...markupDeclarationEnd(source, start), name: null, comment: true };
  } else if (!isAsciiAlpha(next)) {
    return null;
  }
  const nameStart = cursor;
  while (cursor < source.length && !isHtmlSpace(source[cursor]) && source[cursor] !== "/" && source[cursor] !== ">") cursor += 1;
  const tag = { name: source.slice(nameStart, cursor).toLowerCase(), closing, selfClosing: false, attributes: [], comment: false };
  while (cursor < source.length) {
    const character = source[cursor];
    if (isHtmlSpace(character)) { cursor += 1; continue; }
    if (character === ">") return { ...tag, end: cursor + 1, closed: true };
    if (character === "/") {
      cursor += 1;
      if (source[cursor] === ">") return { ...tag, selfClosing: true, end: cursor + 1, closed: true };
      continue;
    }
    // An attribute name runs to whitespace, "/", ">" or "="; its first character
    // always belongs to it, even "=".
    const attributeStart = cursor;
    cursor += 1;
    while (cursor < source.length && !isHtmlSpace(source[cursor]) && !"/>=".includes(source[cursor])) cursor += 1;
    const name = source.slice(attributeStart, cursor).toLowerCase();
    while (cursor < source.length && isHtmlSpace(source[cursor])) cursor += 1;
    let value = null;
    if (source[cursor] === "=") {
      cursor += 1;
      while (cursor < source.length && isHtmlSpace(source[cursor])) cursor += 1;
      const quote = source[cursor] === '"' || source[cursor] === "'" ? source[cursor] : null;
      if (quote) {
        const close = source.indexOf(quote, cursor + 1);
        if (close === -1) return { ...tag, end: source.length, closed: false };
        value = source.slice(cursor + 1, close);
        cursor = close + 1;
      } else if (source[cursor] === ">") {
        value = "";
      } else {
        const valueStart = cursor;
        while (cursor < source.length && !isHtmlSpace(source[cursor]) && source[cursor] !== ">") cursor += 1;
        value = source.slice(valueStart, cursor);
      }
    }
    tag.attributes.push({ name, value });
  }
  return { ...tag, end: source.length, closed: false };
}

// Raw text and RCDATA end at the first "</name" followed by whitespace, "/" or
// ">". Markup in between is not interpreted, exactly as in the browser.
function findClosingTag(source, start, name) {
  const candidate = new RegExp(`</${name}(?=[\\t\\n\\f\\r />])`, "gi");
  candidate.lastIndex = start;
  const match = candidate.exec(source);
  if (!match) return null;
  const tag = scanHtmlTag(source, match.index);
  return tag && tag.closed ? { start: match.index, end: tag.end } : null;
}

function isSafeRasterDataUrl(value) {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    Buffer.byteLength(value, "utf8") > MAX_INLINE_IMAGE_URL_BYTES
  ) {
    return false;
  }
  const match = SAFE_RASTER_DATA_URL.exec(value);
  return match !== null && match[1].length % 4 === 0;
}

function isSafeRasterSrcset(value) {
  if (typeof value !== "string") return false;
  const parts = value.trim().split(/[\t\n\f\r ]+/);
  if (parts.length === 1) return isSafeRasterDataUrl(parts[0]);
  if (parts.length !== 2 || !isSafeRasterDataUrl(parts[0])) return false;
  return /^(?:[1-9]\d*w|(?:[1-9]\d*(?:\.\d+)?|0?\.\d+)x)$/.test(parts[1]);
}

function mayKeepNetworkAttribute(elementName, attributeName, attributeValue) {
  if (elementName === "a" && attributeName === "href") {
    return typeof attributeValue === "string" && /^#[A-Za-z][A-Za-z0-9_.:-]{0,127}$/.test(attributeValue);
  }
  if (attributeName === "src" && elementName === "img") {
    return isSafeRasterDataUrl(attributeValue);
  }
  if (
    attributeName === "srcset" &&
    (elementName === "img" || elementName === "source")
  ) {
    return isSafeRasterSrcset(attributeValue);
  }
  return false;
}

const SAFE_TAG_NAME = /^[a-z][a-z0-9:-]*$/;
const SAFE_ATTRIBUTE_NAME = /^[a-z_:][a-z0-9_.:-]*$/;

// Write a start tag from its parsed attributes. The browser keeps the first of
// duplicate attributes, so later duplicates are never written.
function serializeStartTag(tag, styleNonce = null) {
  let result = `<${tag.name}`;
  if (tag.name === "style" && styleNonce) result += ` nonce="${styleNonce}"`;
  const seen = new Set();
  for (const { name, value } of tag.attributes) {
    if (seen.has(name)) continue;
    seen.add(name);
    if (!SAFE_ATTRIBUTE_NAME.test(name) || name.startsWith("on") || name === "nonce") continue;
    if (NETWORK_CAPABLE_ATTRIBUTES.has(name) && !mayKeepNetworkAttribute(tag.name, name, value)) continue;
    result += value === null ? ` ${name}` : ` ${name}="${value.replace(/"/g, "&quot;")}"`;
  }
  return `${result}${tag.selfClosing ? " /" : ""}>`;
}

function stripActivePreviewMarkup(value, styleNonce, markupContext = false) {
  const source = String(value);
  let result = "";
  let cursor = 0;
  const knownUnclosedRawTextElements = new Set();
  // Parsers without the relaxed select rules ignore raw-text openers inside
  // <select> until "</select>" (or an opener that closes it, which only makes
  // this flag stay set longer than needed).
  let selectOpen = false;
  while (cursor < source.length) {
    const tagStart = source.indexOf("<", cursor);
    if (tagStart === -1) {
      result += source.slice(cursor);
      break;
    }
    result += source.slice(cursor, tagStart);
    const tag = scanHtmlTag(source, tagStart);
    if (tag === null || (tag.comment && !tag.closed)) {
      // Plain text, or an unterminated comment that would otherwise swallow the
      // wrapper after the fragment: escape only the opener and keep sanitizing.
      result += "&lt;";
      cursor = tagStart + 1;
      continue;
    }
    if (tag.comment) {
      // Comments, doctypes and bogus comments do not render. Dropping them means
      // the browser never has to agree with this scanner on where they end.
      cursor = tag.end;
      continue;
    }
    if (!tag.closed) {
      // A tag cut off by the end of the fragment would continue into the fixed
      // wrapper. Its remaining text belongs to the tag, so nothing is written.
      cursor = source.length;
      break;
    }
    if (!SAFE_TAG_NAME.test(tag.name)) {
      cursor = tag.end;
      continue;
    }
    if (tag.closing) {
      if (tag.name === "select") selectOpen = false;
      result += `</${tag.name}>`;
      cursor = tag.end;
      continue;
    }
    // In SVG/MathML content the browser parses raw-text elements as markup.
    // The tree builder can stay there after a self-closing-looking tag or an
    // ignored end tag, so after any opener every later raw-text element is
    // treated as possibly foreign.
    if (tag.name === "svg" || tag.name === "math") markupContext = true;
    if (tag.name === "select") selectOpen = true;
    if (tag.name === "script") {
      const closing = findClosingTag(source, tag.end, "script");
      cursor = closing ? closing.end : source.length;
      continue;
    }
    if (RAW_TEXT_PREVIEW_ELEMENTS.has(tag.name)) {
      const closing = knownUnclosedRawTextElements.has(tag.name)
        ? null
        : findClosingTag(source, tag.end, tag.name);
      if (closing === null) {
        // Flatten malformed raw-text markup into the surrounding fragment. Its
        // contents continue through the normal sanitizer instead of swallowing
        // the wrapper that follows the fragment.
        knownUnclosedRawTextElements.add(tag.name);
        cursor = tag.end;
        continue;
      }
      // Text without a possible tag, comment or end tag opener reads the same
      // as raw text and as markup. Otherwise sanitize contents that may be
      // parsed as markup; noscript is markup wherever scripting is disabled.
      const content = source.slice(tag.end, closing.start);
      const asMarkup = (markupContext || selectOpen || tag.name === "noscript") && /<[A-Za-z!\/?]/.test(content);
      const inner = asMarkup ? stripActivePreviewMarkup(content, styleNonce, true) : content;
      // An opener written from contents parsed as markup keeps later raw text suspect.
      if (asMarkup && /<(?:svg|math)[\s/>]/.test(inner)) markupContext = true;
      if (asMarkup && /<select[\s/>]/.test(inner)) selectOpen = true;
      result += `${serializeStartTag(tag, styleNonce)}${inner}</${tag.name}>`;
      cursor = closing.end;
      continue;
    }
    if (FORBIDDEN_PREVIEW_ELEMENTS.has(tag.name)) {
      cursor = tag.end;
      continue;
    }
    result += serializeStartTag(tag, styleNonce);
    cursor = tag.end;
  }
  return result;
}

function readDesign(filename) {
  const descriptor = path.join(contentDir, filename.slice(0, -5) + ".design.json");
  try { fs.lstatSync(descriptor); }
  catch (error) {
    if (error.code === "ENOENT") return { design: null, designError: false, designSource: null };
    return { design: null, designError: true, designSource: "unavailable" };
  }
  let source;
  try {
    source = readRegularFile(descriptor, contentDir, MAX_DESIGN_BYTES, true);
    const design = JSON.parse(source.toString("utf8"));
    if (!validDesign(design)) throw new Error("Invalid design declaration.");
    return { design, designError: false, designSource: source };
  } catch {
    // A malformed or unsafe declaration never becomes trusted controls. Keep
    // the ordinary preview available with an explicit, content-free warning.
    return { design: null, designError: true, designSource: source ?? "unavailable" };
  }
}

function newestContent() {
  if (workspaceState) return workspaceState.current();
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
      const content = readRegularFile(
        candidate.path,
        contentDir,
        MAX_CONTENT_BYTES,
      );
      const declaration = readDesign(candidate.filename);
      const digest = crypto.createHash("sha256")
        .update(candidate.filename).update("\0").update(content);
      if (declaration.designSource !== null) digest.update("\0design\0").update(declaration.designSource);
      return {
        filename: candidate.filename,
        screen: digest.digest("hex").slice(0, 32),
        content,
        design: declaration.design,
        designError: declaration.designError,
      };
    } catch {
      // A concurrent writer may have replaced the file; try the next safe one.
    }
  }
  return null;
}

function wrapInFrame(content, filename, screen, nonce, design = null, designError = false, view = null, embedded = false) {
  const safeFilename = escapeHtml(filename || "untitled");
  const safeContent = stripActivePreviewMarkup(content, nonce);
  const akselStyle = akselCss
    ? `<style nonce="${nonce}">\n${safeInlineStyle(akselCss)}\n</style>`
    : "";
  const cssWarning = akselCss
    ? ""
    : `<div role="status" data-vc-notice style="background:#fef0f0;border:2px solid #c30000;padding:16px;margin-bottom:16px;border-radius:8px;font-family:sans-serif">
        <strong>⚠️ Aksel CSS mangler</strong><br>Skissen vises med reservestiler fordi prosjektets Aksel-stiler ikke ble funnet.
      </div>`;
  const designWarning = designError
    ? `<div role="alert" data-vc-notice style="background:#fff5df;border:2px solid #a86d00;padding:16px;margin-bottom:16px;border-radius:8px;font-family:sans-serif"><strong>«Juster visning» er utilgjengelig.</strong> Skisseoppsettet må rettes.</div>`
    : "";
  // One pass: inserted CSS, scripts and sketch markup are never scanned again
  // for placeholders.
  const values = {
    FILENAME: safeFilename,
    NONCE: nonce,
    AKSEL_STYLE: akselStyle,
    HELPER_SCRIPT:
      (embedded ? `<style nonce="${nonce}">
        body { background: var(--ax-bg-default, #fff); }
        body > .vc-header { padding: 0; border: 0; height: 0; position: static; background: transparent; }
        body > .vc-header .vc-header-left { display: none; }
        body > .vc-header .vc-indicator.visible { position: fixed; top: 8px; right: 8px; z-index: 101; }
        body > main.vc-content { margin: 0 auto; padding: 16px; min-height: 100vh; }
      </style>` : "") +
      `<script nonce="${nonce}">window.__grillmesterVisualCompanionScreen=${serializeForInlineScript(screen)};window.__grillmesterVisualCompanionDesign=${serializeForInlineScript(design)};window.__grillmesterVisualCompanionView=${serializeForInlineScript(view)};window.__grillmesterVisualCompanionEmbedded=${embedded ? "true" : "false"};</script>` +
      `<script nonce="${nonce}">\n${workshopJs}\n</script>` +
      `<script nonce="${nonce}">\n${editorJs}\n</script>` +
      `<script nonce="${nonce}">\n${helperJs}\n</script>`,
    CONTENT: cssWarning + designWarning + safeContent,
  };
  return frameTemplate.replace(/\{\{(FILENAME|NONCE|AKSEL_STYLE|HELPER_SCRIPT|CONTENT)\}\}/g, (_, key) => values[key]);
}

function renderShellPage(nonce, accessToken, title, screen, embeddedView = null) {
  const previewPath = `/preview?token=${encodeURIComponent(accessToken)}`;
  const versionPath = `/version?token=${encodeURIComponent(accessToken)}`;
  const eventsPath = `/events?token=${encodeURIComponent(accessToken)}`;
  const commentsPath = `/comments?token=${encodeURIComponent(accessToken)}`;
  return `<!DOCTYPE html>
<html lang="nb">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Visual Companion — ${escapeHtml(title || "prototype")}</title>
  <style nonce="${nonce}">
    html, body { width: 100%; height: 100%; margin: 0; background: #f7f7f7; }
    iframe { display: block; width: 100%; height: 100%; border: 0; }
    #vc-paused {
      position: fixed; inset: 0; z-index: 2; display: none;
      place-items: center; padding: 2rem; background: rgba(247,247,247,.96);
      color: #27262b; font: 1rem/1.5 system-ui, sans-serif; text-align: center;
    }
    #vc-paused.visible { display: grid; }
    #vc-paused strong { display: block; margin-bottom: .5rem; font-size: 1.25rem; }
    #vc-paused p { max-width: 34rem; }
    #vc-recover { font: inherit; padding: .65rem 1rem; margin-top: .5rem; border: 1px solid #665275; border-radius: .5rem; background: #fff; color: #27262b; cursor: pointer; }
    #vc-recover:focus-visible { outline: 3px solid #6852ce; outline-offset: 3px; }
    ${embeddedView ? "#vc-status[data-connected=\"true\"] { display: none; }" : ""}
    #vc-status {
      position: fixed; right: 1rem; top: 1rem; z-index: 3;
      border: 1px solid #b7b1a9; border-radius: 999px; padding: .35rem .7rem;
      background: rgba(255,255,255,.94); color: #27262b;
      font: 600 .8rem/1.2 system-ui, sans-serif;
    }
  </style>
</head>
<body>
  <iframe id="vc-preview" sandbox="allow-scripts" referrerpolicy="no-referrer" title="Designskisse" src="${escapeHtml(previewPath)}"></iframe>
  <div id="vc-paused" role="dialog" aria-modal="true" aria-labelledby="vc-paused-title">
    <div><strong id="vc-paused-title">Forhåndsvisningen er satt på pause</strong><p>Forbindelsen er brutt. Innspill kan ikke lagres nå. Du kan fortsatt se skissen og kopiere teksten du vil beholde. Gå tilbake til samtalen for å starte en ny økt.</p><button id="vc-recover" type="button">Se skissen og kopier utkast</button></div>
  </div>
  <div id="vc-status" role="status" aria-live="polite">Kobler til …</div>
  <script nonce="${nonce}">
    (() => {
      "use strict";
      const channel = "grillmester-visual-companion";
      const frame = document.getElementById("vc-preview");
      const paused = document.getElementById("vc-paused");
      const status = document.getElementById("vc-status");
      const recover = document.getElementById("vc-recover");
      const versionUrl = ${serializeForInlineScript(versionPath)};
      const eventsUrl = ${serializeForInlineScript(eventsPath)};
      const commentsUrl = ${serializeForInlineScript(commentsPath)};
      let lastVersion = ${serializeForInlineScript(screen || "")};
      let pendingVersion = null;
      let feedbackBusy = true;
      let frameReady = false;
      let provisionalScreen = null;
      let provisionalBusy = true;
      let readyEpoch = 0;
      let refreshing = false;
      // A stored version shown read-only; automatic refreshes wait until the
      // designer returns to the current version.
      let viewing = null;
      let newestVersion = "";
      let lastSuccessfulPoll = Date.now();
      let connectionLost = false;
      let recoveryOpen = false;
      let polling = false;

      recover.addEventListener("click", () => {
        recoveryOpen = true;
        paused.classList.remove("visible");
        frame.inert = false;
        frame.focus();
      });

      function markConnected() {
        lastSuccessfulPoll = Date.now();
        paused.classList.remove("visible");
        frame.inert = false;
        if (connectionLost) sendToPreview({ command: "connection-restored" });
        connectionLost = false;
        recoveryOpen = false;
        status.textContent = "Tilkoblet";
        status.dataset.connected = "true";
      }

      function markDisconnected() {
        delete status.dataset.connected;
        if (Date.now() - lastSuccessfulPoll >= 15_000) {
          if (!connectionLost) {
            sendToPreview({ command: "connection-lost" });
            paused.classList.add("visible");
            frame.inert = true;
            recover.focus();
          } else if (!recoveryOpen) paused.classList.add("visible");
          connectionLost = true;
          status.textContent = "Pauset";
        } else {
          status.textContent = "Kobler til …";
        }
      }

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
          hasExactKeys(data.event, ["type", "choice", "screen"]) &&
          (data.event.type === "click" || data.event.type === "deselect") &&
          /^choice-[1-9][0-9]{0,3}$/.test(data.event.choice) &&
          /^[a-f0-9]{32}$/.test(data.event.screen);
      }

      function closedKeys(value, required, optional = []) {
        return value && typeof value === "object" && !Array.isArray(value) &&
          required.every((key) => Object.hasOwn(value, key)) &&
          Object.keys(value).every((key) => required.includes(key) || optional.includes(key));
      }
      function validText(value) {
        return typeof value === "string" && new TextEncoder().encode(value).length <= 2000;
      }
      function validKey(value) {
        return typeof value === "string" && /^[a-z][a-z0-9-]{0,47}$/.test(value);
      }
      function validVariant(value) { return value === "" || validKey(value); }
      function validValues(value) {
        return value && typeof value === "object" && !Array.isArray(value) &&
          Object.keys(value).length <= 8 && Object.entries(value).every(([key, option]) => validKey(key) && validKey(option));
      }
      function validAnchor(value) {
        const finite = (number, min, max) => typeof number === "number" && Number.isFinite(number) && number >= min && number <= max;
        return hasExactKeys(value, ["path", "role", "rect", "viewport"]) &&
          typeof value.path === "string" && value.path.length <= 512 &&
          /^[a-z][a-z0-9-]*:nth-of-type\\([1-9][0-9]{0,5}\\)(?: > [a-z][a-z0-9-]*:nth-of-type\\([1-9][0-9]{0,5}\\))*$/.test(value.path) &&
          ["", "button", "link", "textbox", "heading", "img", "navigation", "main", "region", "group", "list", "listitem", "checkbox", "radio", "combobox", "tab", "tabpanel", "table", "row", "cell", "alert", "status", "presentation", "none"].includes(value.role) &&
          hasExactKeys(value.rect, ["x", "y", "width", "height"]) && finite(value.rect.x, 0, 1000000) && finite(value.rect.y, 0, 1000000) && finite(value.rect.width, 0, 100000) && finite(value.rect.height, 0, 100000) &&
          hasExactKeys(value.viewport, ["width", "height"]) && finite(value.viewport.width, 1, 20000) && finite(value.viewport.height, 1, 20000);
      }
      function feedbackOperation(data) {
        if (!closedKeys(data, ["channel", "version", "action", "requestId", "payload"], ["mutationId"]) || data.channel !== channel || data.version !== 1 || !Number.isInteger(data.requestId) || data.requestId < 1 || data.requestId > 1000000000 || (Object.hasOwn(data, "mutationId") && (typeof data.mutationId !== "string" || !/^[a-f0-9]{32}$/.test(data.mutationId)))) return null;
        const value = data.payload;
        const validScreen = (screen) => typeof screen === "string" && /^[a-f0-9]{32}$/.test(screen);
        const validId = (id) => typeof id === "string" && /^[a-f0-9]{24}$/.test(id);
        if (data.action === "workspace-history" && !Object.hasOwn(data, "mutationId") && hasExactKeys(value, ["after", "limit"]) && Number.isSafeInteger(value.after) && value.after >= 0 && Number.isInteger(value.limit) && value.limit >= 1 && value.limit <= 20) return { workspace: true, method: "GET", path: "/workspace/history", query: { after: value.after, limit: value.limit } };
        if (data.action === "workspace-restore" && hasExactKeys(value, ["revisionId", "expectedRevision"]) && Number.isSafeInteger(value.revisionId) && value.revisionId > 0 && Number.isSafeInteger(value.expectedRevision) && value.expectedRevision >= 0) return { workspace: true, method: "POST", path: "/workspace/restore", body: value };
        if (data.action === "workspace-editor-read" && !Object.hasOwn(data, "mutationId") && hasExactKeys(value, [])) return { workspace: true, method: "GET", path: "/workspace/editor" };
        const validFieldId = (id) => typeof id === "string" && id.length <= 160 && /^(?:text:[a-z][a-z0-9-]{0,47}|control:(?:[a-z][a-z0-9-]{0,47})?\\/[a-z][a-z0-9-]{0,47}\\/[a-z][a-z0-9-]{0,47})$/.test(id);
        if (["workspace-editor-save", "workspace-editor-release"].includes(data.action) && hasExactKeys(value, ["screen", "expectedRevision", data.action === "workspace-editor-save" ? "changes" : "ids"]) &&
            validScreen(value.screen) && Number.isSafeInteger(value.expectedRevision) && value.expectedRevision >= 0) {
          const saving = data.action === "workspace-editor-save";
          const items = saving ? value.changes : value.ids;
          if (Array.isArray(items) && items.length > 0 && items.length <= 32 && items.every(item => saving ? hasExactKeys(item, ["id", "value"]) && validFieldId(item.id) && validText(item.value) : validFieldId(item)))
            return { workspace: true, method: "POST", path: saving ? "/workspace/editor/save" : "/workspace/editor/release", body: value };
        }
        if (data.action === "comments-list" && hasExactKeys(value, [])) return { method: "GET", path: "/comments" };
        if (data.action === "comment-create" && closedKeys(value, ["screen", "kind", "anchor", "text"], ["proposal", "adjustment", "variant", "context"]) && validScreen(value.screen) && validAnchor(value.anchor) && validText(value.text)) {
          const baseKeys = ["screen", "kind", "anchor", "text"];
          const validContext = !Object.hasOwn(value, "context") || (hasExactKeys(value.context, ["variant", "target", "values"]) && validVariant(value.context.variant) && validKey(value.context.target) && validValues(value.context.values));
          const validPoint = ["point", "area"].includes(value.kind) && closedKeys(value, baseKeys, ["context"]) && validContext;
          const validEdit = value.kind === "edit" && closedKeys(value, [...baseKeys, "proposal"], ["context"]) && validContext && hasExactKeys(value.proposal, ["property", "value"]) && value.proposal.property === "text" && validText(value.proposal.value);
          const validAdjustment = value.kind === "adjustment" && hasExactKeys(value, [...baseKeys, "adjustment"]) && hasExactKeys(value.adjustment, ["variant", "target", "values"]) && validVariant(value.adjustment.variant) && validKey(value.adjustment.target) && validValues(value.adjustment.values) && Object.keys(value.adjustment.values).length > 0;
          const validChoice = value.kind === "variant" && hasExactKeys(value, [...baseKeys, "variant"]) && validKey(value.variant);
          if (validPoint || validEdit || validAdjustment || validChoice) return { method: "POST", path: "/comments", body: value };
        }
        if (data.action === "comments-submit" && closedKeys(value, ["revision"], ["screen"]) && Number.isSafeInteger(value.revision) && value.revision >= 0 && (!Object.hasOwn(value, "screen") || validScreen(value.screen))) return { method: "POST", path: "/comments/submit", body: value };
        if (data.action === "comment-delete" && hasExactKeys(value, ["id"]) && validId(value.id)) return { method: "DELETE", path: "/comments/" + value.id, body: {} };
        if (data.action === "comment-update" && closedKeys(value, ["id"], ["status", "reply", "resubmit"]) && validId(value.id) && Object.keys(value).length > 1 &&
          (!Object.hasOwn(value, "status") || ["open", "fixed"].includes(value.status)) && (!Object.hasOwn(value, "reply") || validText(value.reply)) &&
          (!Object.hasOwn(value, "resubmit") || (value.resubmit === true && value.status === "open"))) {
          const { id, ...body } = value;
          return { method: "PATCH", path: "/comments/" + id, body };
        }
        return null;
      }
      function sendToPreview(message) { frame.contentWindow.postMessage({ channel, version: 1, ...message }, "*"); }
      function showFrame(next) {
        frameReady = false;
        provisionalScreen = null;
        readyEpoch += 1;
        frame.src = next.pathname + next.search;
        feedbackBusy = true;
      }
      function refreshPreview(force = false) {
        if (!frameReady || !pendingVersion || refreshing || viewing !== null) return;
        refreshing = true;
        const version = pendingVersion;
        pendingVersion = null;
        sendToPreview({ command: "refreshing" });
        setTimeout(() => {
          if ((feedbackBusy && !force) || viewing !== null) {
            pendingVersion = pendingVersion || version;
            refreshing = false;
            if (viewing === null) sendToPreview({ command: "update-available", screen: pendingVersion });
            return;
          }
          lastVersion = version;
          if (pendingVersion === version) pendingVersion = null;
          const next = new URL(${serializeForInlineScript(previewPath)}, window.location.origin);
          next.searchParams.set("v", version);
          showFrame(next);
          refreshing = false;
        }, 400);
      }
      function acceptReady(snapshot) {
        if (frameReady || !provisionalScreen || !(snapshot.screens.some((item) => item.screen === provisionalScreen) || provisionalScreen === "00000000000000000000000000000000")) return;
        lastVersion = provisionalScreen;
        frameReady = true;
        ${embeddedView ? `window.parent.postMessage({channel:"design-workshop-embed",version:1,event:"activated",leaseId:${serializeForInlineScript(embeddedView.leaseId)},screen:lastVersion},${serializeForInlineScript(embeddedView.parentOrigin)});` : ""}
        feedbackBusy = provisionalBusy;
        if (pendingVersion === lastVersion) pendingVersion = null;
        if (pendingVersion) sendToPreview({ command: "update-available", screen: pendingVersion });
        if (!feedbackBusy) refreshPreview();
      }
      async function withReadDeadline(read) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 5000);
        try { return await read(controller.signal); }
        finally { clearTimeout(timeout); }
      }
      async function pollComments(signal, epoch = readyEpoch) {
        const response = await fetch(commentsUrl, { credentials: "same-origin", cache: "no-store", signal });
        if (!response.ok) throw new Error("feedback unavailable");
        const snapshot = await response.json();
        if (epoch !== readyEpoch) return;
        acceptReady(snapshot);
        sendToPreview({ command: "comments-snapshot", snapshot });
      }
      window.addEventListener("message", (message) => {
        if (message.source !== frame.contentWindow) return;
        const data = message.data;
        if (hasExactKeys(data, ["channel", "version", "action", "screen"]) && data.channel === channel && data.version === 1 && data.action === "feedback-ready" && typeof data.screen === "string" && /^[a-f0-9]{32}$/.test(data.screen)) {
          provisionalScreen = data.screen;
          provisionalBusy = true;
          frameReady = false;
          const epoch = ++readyEpoch;
          withReadDeadline(async (signal) => {
            const response = await fetch(commentsUrl, { credentials: "same-origin", cache: "no-store", signal });
            if (!response.ok) throw new Error("feedback unavailable");
            const snapshot = await response.json();
            if (epoch !== readyEpoch) return;
            acceptReady(snapshot);
            sendToPreview({ command: "comments-snapshot", snapshot });
          }).catch(markDisconnected);
          return;
        }
        if (hasExactKeys(data, ["channel", "version", "action", "screen", "busy"]) && data.channel === channel && data.version === 1 && data.action === "feedback-busy" && typeof data.busy === "boolean" && (data.screen === lastVersion || data.screen === provisionalScreen)) {
          if (!frameReady) {
            if (data.screen === provisionalScreen) provisionalBusy = data.busy;
            return;
          }
          feedbackBusy = data.busy;
          if (!feedbackBusy) refreshPreview();
          return;
        }
        if (hasExactKeys(data, ["channel", "version", "action", "screen"]) && data.channel === channel && data.version === 1 && data.action === "refresh-now" && data.screen === lastVersion) {
          refreshPreview(true);
          return;
        }
        if (hasExactKeys(data, ["channel", "version", "action", "revisionId"]) && data.channel === channel && data.version === 1 && data.action === "view-revision"
            && Number.isSafeInteger(data.revisionId) && data.revisionId >= 1 && data.revisionId <= 999999 && frameReady && !refreshing) {
          viewing = data.revisionId;
          const next = new URL(${serializeForInlineScript(previewPath)}, window.location.origin);
          next.searchParams.set("revision", String(data.revisionId));
          showFrame(next);
          return;
        }
        if (hasExactKeys(data, ["channel", "version", "action"]) && data.channel === channel && data.version === 1 && data.action === "view-current" && viewing !== null) {
          viewing = null;
          const next = new URL(${serializeForInlineScript(previewPath)}, window.location.origin);
          if (newestVersion) next.searchParams.set("v", newestVersion);
          showFrame(next);
          return;
        }
        const operation = feedbackOperation(data);
        if (!operation) return;
        const operationEpoch = readyEpoch;
        const resultCommand = operation.workspace ? "workspace-result" : "comments-result";
        const url = new URL(commentsUrl, window.location.origin);
        url.pathname = operation.path;
        for (const [key, value] of Object.entries(operation.query || {})) url.searchParams.set(key, String(value));
        fetch(url, { method: operation.method, credentials: "same-origin", cache: "no-store",
          ...(operation.body === undefined ? {} : { headers: { "Content-Type": "application/json", ...(data.mutationId ? { "X-Feedback-Mutation": data.mutationId } : {}) }, body: JSON.stringify(operation.body) }),
        }).then(async (response) => {
          const result = await response.json();
          if (operationEpoch !== readyEpoch) return;
          if (!response.ok && response.status === 409 && (operation.workspace || operation.path === "/comments/submit")) {
            await withReadDeadline((signal) => pollComments(signal, operationEpoch));
            if (operationEpoch !== readyEpoch) return;
            const conflicts = Array.isArray(result.conflicts) && result.conflicts.length <= 32 && result.conflicts.every((item) => hasExactKeys(item, ["id", "label"])
              && typeof item.id === "string" && item.id.length <= 160 && typeof item.label === "string" && item.label.length <= 400) ? result.conflicts : null;
            sendToPreview({ command: resultCommand, requestId: data.requestId, ok: false, conflict: true,
              ...(["editor-conflict", "revision-unavailable"].includes(result.errorCode) ? { errorCode: result.errorCode } : {}),
              ...(conflicts ? { conflicts } : {}) });
            return;
          }
          sendToPreview(response.ok ? { command: resultCommand, requestId: data.requestId, ok: true, ...(operation.workspace && operation.method === "GET" ? { result } : { snapshot: result }) }
            : { command: resultCommand, requestId: data.requestId, ok: false, ...(response.status === 429 ? { errorCode: "capacity" } : {}), error: result.error || "Feedback request failed." });
        }).catch(() => {
          if (operationEpoch === readyEpoch) sendToPreview({ command: resultCommand, requestId: data.requestId, ok: false, error: "Feedback is unavailable. Keep your note and try again." });
        });
      });

      window.addEventListener("message", (message) => {
        if (message.source !== frame.contentWindow || !validSelectionMessage(message.data)) return;
        const event = message.data.event;
        const reportSelectionStatus = (status) => frame.contentWindow.postMessage({
          channel,
          version: 1,
          command: "selection-status",
          screen: event.screen,
          type: event.type,
          choice: event.choice,
          status,
        }, "*");
        fetch(eventsUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(event),
          credentials: "same-origin",
        }).then((response) => {
          reportSelectionStatus(response.ok ? "saved" : "failed");
        }).catch(() => reportSelectionStatus("failed"));
      });

      setInterval(async () => {
        if (polling) return;
        polling = true;
        try {
          await withReadDeadline(async (signal) => {
            const response = await fetch(versionUrl, { credentials: "same-origin", cache: "no-store", signal });
            if (!response.ok) throw new Error("preview unavailable");
            const version = await response.text();
            if (version) newestVersion = version;
            if (version && version !== lastVersion) {
              pendingVersion = version;
              if (frameReady && viewing === null) {
                sendToPreview({ command: "update-available", screen: version });
                if (!feedbackBusy) refreshPreview();
              }
            }
            await pollComments(signal);
            markConnected();
          });
        } catch { markDisconnected(); }
        finally { polling = false; }
      }, 2000);
    })();
  </script>
</body>
</html>`;
}

function shellCsp(nonce, parentOrigin) {
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
    `frame-ancestors ${parentOrigin || "'none'"}`,
  ].join("; ");
}

function previewCsp(nonce, parentOrigin) {
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
    `frame-ancestors 'self'${parentOrigin ? ` ${parentOrigin}` : ""}`,
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

// Only a parent process with a private IPC channel can bind canvas delivery.
// Nothing in a browser request can enable or call this capability.
async function runPreview() {
let recovered = false;
if (workspacePath) {
  workspaceStore = new WorkspaceStore({ projectDir, workspacePath, create: workspaceCreate === "true", title: workspaceTitle, validateState: validWorkspaceState });
  recovered = workspaceStore.load() !== null;
}
const feedback = new FeedbackStore(stateDir, { canvas: canvasMode, persistence: workspaceStore,
  initialWorkspace: workspaceStore ? { id: crypto.randomBytes(12).toString("hex"), title: workspaceTitle || path.basename(workspacePath), version: 0, revisions: [] } : null });
if (workspaceStore) workspaceState = new WorkspaceState(feedback, workspaceStore, { path: workspacePath, recovered });
const canvasState = canvasMode ? new CanvasState(feedback) : null;
const mutationReceipts = new FeedbackMutationReceipts();
let accessToken = crypto.randomBytes(32).toString("base64url");
let tokenBuffer = Buffer.from(accessToken);
let authority = null;
let embedding = null, viewGeneration = 0;
function revokeView() { viewGeneration += 1; embedding?.revoke(); authority = null; }
function currentRequest(req) { return req.viewGeneration === viewGeneration && authority !== null && (!embedding || embedding.active); }
let eventCount = 0;
let lastActivity = Date.now();
let activeSessionRemoved = false;
let activeScreen = null;
let listeningUntil = 0;

function feedbackSnapshot() { return { ...feedback.snapshot(), listeningUntil, ...(workspaceState ? { workspace: workspaceState.summary() } : {}) }; }

function activateScreen(newest) {
  const nextScreen = newest ? newest.screen : "";
  if (activeScreen === nextScreen) return;
  if (newest) feedback.knowScreen(newest.screen, newest.filename, newest.design);
  activeScreen = nextScreen;
  eventCount = 0;
  const eventPath = path.join(stateDir, "events.jsonl");
  if (fs.existsSync(eventPath)) {
    const stat = fs.lstatSync(eventPath);
    if (stat.isSymbolicLink() || !stat.isFile()) {
      throw new Error("Refusing unsafe event state while activating a screen.");
    }
    fs.unlinkSync(eventPath);
  }
  lastActivity = Date.now();
}

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
    keys.length === 3 &&
    keys[0] === "choice" &&
    keys[1] === "screen" &&
    keys[2] === "type" &&
    (value.type === "click" || value.type === "deselect") &&
    typeof value.choice === "string" &&
    /^choice-[1-9][0-9]{0,3}$/.test(value.choice) &&
    typeof value.screen === "string" &&
    /^[a-f0-9]{32}$/.test(value.screen)
  );
}

function appendEvent(event) {
  if (eventCount >= MAX_EVENTS) return false;
  feedback.assertDirectory();
  const eventPath = path.join(stateDir, "events.jsonl");
  const line = `${JSON.stringify({
    type: event.type,
    choice: event.choice,
    screen: event.screen,
    timestamp: Date.now(),
  })}\n`;
  const descriptor = fs.openSync(
    eventPath,
    fs.constants.O_WRONLY |
      fs.constants.O_CREAT |
      fs.constants.O_APPEND |
      fs.constants.O_NOFOLLOW |
      fs.constants.O_NONBLOCK,
    0o600,
  );
  try {
    feedback.assertDirectory();
    const stat = fs.fstatSync(descriptor);
    const linked = fs.lstatSync(eventPath);
    assertOwnedByCurrentUser(stat, eventPath);
    if (!stat.isFile() || stat.nlink !== 1 || (stat.mode & 0o077) ||
        linked.isSymbolicLink() || stat.dev !== linked.dev || stat.ino !== linked.ino) {
      throw new Error("Unsafe selection state file.");
    }
    if (stat.size + Buffer.byteLength(line) > MAX_EVENT_FILE_BYTES) return false;
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
  req.on("error", () => { rejected = true; chunks = []; });
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
    if (!currentRequest(req)) { sendJson(res, 410, { error: "The proposal view has expired." }); return; }
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
    if (event.screen !== activeScreen) {
      res.writeHead(409, { "Content-Type": "application/json; charset=utf-8" });
      res.end('{"error":"event belongs to a stale screen"}');
      return;
    }
    try {
      if (!appendEvent(event)) {
        sendJson(res, 429, { error: "event limit reached" });
        return;
      }
    } catch {
      // Selection storage is optional. A failed write must never terminate
      // the session and remove unrelated comments.
      sendJson(res, 500, { error: "Selection storage is unavailable." });
      return;
    }
    lastActivity = Date.now();
    res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
    res.end('{"ok":true}');
  });
}

function sendJson(res, status, value) {
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(value));
}
function requestErrorStatus(error) {
  return Number.isInteger(error?.status) && error.status >= 400 && error.status <= 599 ? error.status : 500;
}

function readFeedbackBody(req, res, operation, pathname, maximumBytes = MAX_BODY_BYTES) {
  let chunks = [];
  let size = 0;
  let rejected = false;
  req.on("error", () => { rejected = true; chunks = []; });
  req.on("data", (chunk) => {
    if (rejected) return;
    size += chunk.length;
    if (size > maximumBytes) {
      rejected = true;
      chunks = [];
      sendJson(res, 413, { error: "Feedback payload too large." });
      return;
    }
    chunks.push(chunk);
  });
  req.on("end", () => {
    if (rejected || res.writableEnded) return;
    if (!currentRequest(req)) { sendJson(res, 410, { error: "The proposal view has expired." }); return; }
    let value;
    try { value = JSON.parse(Buffer.concat(chunks).toString("utf8")); }
    catch { sendJson(res, 400, { error: "Invalid JSON." }); return; }
    const previousSubmission = feedback.state.submission;
    try {
      mutationReceipts.run(req.headers["x-feedback-mutation"], req.method, pathname, value, operation);
      const snapshot = feedbackSnapshot();
      lastActivity = Date.now();
      sendJson(res, 200, snapshot);
    } catch (error) {
      sendJson(res, requestErrorStatus(error), {
        error: error instanceof FeedbackError || error?.expose === true ? error.message : "Feedback storage is unavailable.",
        ...(["editor-conflict", "revision-unavailable"].includes(error.errorCode) ? { errorCode: error.errorCode } : {}),
        ...(error.errorCode === "editor-conflict" && Array.isArray(error.conflicts) ? { conflicts: error.conflicts } : {}),
      });
    } finally {
      // A post-rename error can follow a committed round. Notify that transition
      // once even when its HTTP result failed; a receipt retry has no transition.
      if (canvasMode && feedback.state.submission > previousSubmission) {
        canvasEvent({ event: "submitted", submission: feedback.state.submission });
      }
    }
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
  req.viewGeneration = viewGeneration;
  if (embedding && requestUrl.pathname === "/embedded") {
    try {
      if (req.method !== "GET" || requestUrl.searchParams.size !== 1) throw new FeedbackError(400, "Invalid proposal view.");
      const candidate = embedding.candidate(requestUrl.searchParams.get("invitation"));
      res.setHeader("Content-Security-Policy", shellCsp(candidate.nonce, embedding.parentOrigin));
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end(renderEmbeddingBootstrap({ ...candidate, parentOrigin: embedding.parentOrigin, leaseId: embedding.leaseId }));
    } catch (error) { sendJson(res, requestErrorStatus(error), { error: "Open the proposal from the workshop." }); }
    return;
  }
  if (embedding && requestUrl.pathname === "/embedded/activate") {
    if (req.method !== "POST" || req.headers.origin !== `http://${authority}` || requestUrl.search || !/^application\/json(?:\s*;\s*charset=utf-8)?$/i.test(String(req.headers["content-type"] || ""))) {
      sendJson(res, 403, { error: "Proposal activation is unavailable." }); return;
    }
    const bound = embedding; let chunks = [], size = 0, rejected = false;
    req.on("error", () => { rejected = true; chunks = []; });
    req.on("data", chunk => { if (rejected) return; size += chunk.length; if (size > 2048) { rejected = true; chunks = []; sendJson(res, 413, { error: "Proposal activation is too large." }); } else chunks.push(chunk); });
    req.on("end", () => {
      if (rejected || res.writableEnded) return;
      try {
        if (req.viewGeneration !== viewGeneration || bound !== embedding || authority === null) throw new FeedbackError(410, "The proposal view has expired.");
        let input; try { input = JSON.parse(Buffer.concat(chunks).toString("utf8")); } catch { throw new FeedbackError(400, "Invalid proposal activation."); }
        const { nonce } = bound.activate(input), newest = newestContent(); activateScreen(newest);
        res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
        res.end(renderShellPage(nonce, accessToken, newest?.filename || "proposal", newest?.screen, bound));
      } catch (error) { sendJson(res, requestErrorStatus(error), { error: "Proposal activation is unavailable." }); }
    });
    return;
  }
  if (embedding && (!embedding.active || requestUrl.pathname === "/")) {
    sendJson(res, 410, { error: "Open the proposal from the workshop." }); return;
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

  if (requestUrl.pathname.startsWith("/workspace/")) {
    if (!workspaceState) { sendJson(res, 409, { error: "This preview has no saved project workspace." }); return; }
    if (req.method === "GET" && requestUrl.pathname === "/workspace/editor") {
      try {
        if ([...requestUrl.searchParams.keys()].some(key => key !== "token" || requestUrl.searchParams.getAll(key).length !== 1)) throw new FeedbackError(400, "Invalid editor request.");
        sendJson(res, 200, workspaceState.editorRead({}));
      } catch (error) { sendJson(res, requestErrorStatus(error), { error: "Workspace editor is unavailable." }); }
      return;
    }
    if (req.method === "GET" && requestUrl.pathname === "/workspace/history") {
      try {
        const after = requestUrl.searchParams.get("after") ?? "0";
        const limit = requestUrl.searchParams.get("limit") ?? "20";
        if (!/^(0|[1-9][0-9]*)$/.test(after) || !/^[1-9][0-9]*$/.test(limit) ||
            [...requestUrl.searchParams.keys()].some(key => !["token", "after", "limit"].includes(key) || requestUrl.searchParams.getAll(key).length !== 1)) throw new FeedbackError(400, "Invalid history request.");
        sendJson(res, 200, workspaceState.history({ after: Number(after), limit: Number(limit) }));
      } catch (error) { sendJson(res, requestErrorStatus(error), { error: "Workspace history is unavailable." }); }
      return;
    }
    const operation = requestUrl.pathname === "/workspace/restore" ? value => workspaceState.restore(value)
      : requestUrl.pathname === "/workspace/editor/save" ? value => workspaceState.editorSave(value)
      : requestUrl.pathname === "/workspace/editor/release" ? value => workspaceState.editorRelease(value) : null;
    if (req.method !== "POST" || !operation) { sendJson(res, 405, { error: "Unsupported workspace operation." }); return; }
    if (req.headers.origin !== expectedOrigin) { sendJson(res, 403, { error: "Workspace writes require the exact server origin." }); return; }
    if (!/^application\/json(?:\s*;\s*charset=utf-8)?$/i.test(String(req.headers["content-type"] || ""))) { sendJson(res, 415, { error: "application/json required." }); return; }
    readFeedbackBody(req, res, operation, requestUrl.pathname, 64 * 1024);
    return;
  }

  // Existing feedback stays readable and writable even when a newer source
  // cannot be registered. Its own screen IDs were validated on preview load.
  if (requestUrl.pathname === "/comments" || requestUrl.pathname.startsWith("/comments/")) {
    const commentId = /^\/comments\/([a-f0-9]{24})$/.exec(requestUrl.pathname)?.[1];
    if (req.method === "GET" && requestUrl.pathname === "/comments/submissions") {
      try {
        const after = requestUrl.searchParams.get("after");
        if (!/^(0|[1-9][0-9]*)$/.test(after || "") || !Number.isSafeInteger(Number(after)) ||
            [...requestUrl.searchParams.keys()].some((key) => !["token", "after", "waiter"].includes(key) || requestUrl.searchParams.getAll(key).length !== 1) ||
            (requestUrl.searchParams.has("waiter") && requestUrl.searchParams.get("waiter") !== "1")) throw new FeedbackError(400, "Invalid feedback round cursor.");
        const snapshot = feedback.nextSubmission(Number(after));
        if (requestUrl.searchParams.get("waiter") === "1") listeningUntil = Date.now() + 2000;
        sendJson(res, 200, snapshot);
      } catch (error) {
        sendJson(res, error instanceof FeedbackError ? error.status : 500, { error: error instanceof FeedbackError ? error.message : "Feedback history is unavailable." });
      }
      return;
    }
    if (req.method === "GET" && requestUrl.pathname === "/comments") {
      if (requestUrl.searchParams.get("waiter") === "1") listeningUntil = Date.now() + 2000;
      // An open canvas polls continuously; a closed one cannot reach the server.
      if (canvasMode) lastActivity = Date.now();
      sendJson(res, 200, feedbackSnapshot());
      return;
    }
    const operation = req.method === "POST" && requestUrl.pathname === "/comments" ? (value) => feedback.create(value)
      : req.method === "POST" && requestUrl.pathname === "/comments/submit" ? (value) => feedback.submit(value)
      : req.method === "PATCH" && commentId ? (value) => feedback.patch(commentId, value)
      : req.method === "DELETE" && commentId ? (value) => feedback.delete(commentId, value) : null;
    if (!operation) {
      sendJson(res, 405, { error: "Unsupported feedback operation." });
      return;
    }
    if (req.headers.origin !== expectedOrigin) {
      sendJson(res, 403, { error: "Feedback writes require the exact server origin." });
      return;
    }
    if (!/^application\/json(?:\s*;\s*charset=utf-8)?$/i.test(String(req.headers["content-type"] || ""))) {
      sendJson(res, 415, { error: "application/json required." });
      return;
    }
    readFeedbackBody(req, res, operation, requestUrl.pathname);
    return;
  }

  let newest;
  try {
    newest = newestContent();
    activateScreen(newest);
  } catch (error) {
    res.writeHead(error instanceof FeedbackError ? error.status : 500, { "Content-Type": "text/plain; charset=utf-8" });
    res.end(error instanceof FeedbackError ? error.message : "Preview state is unavailable.");
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

  if (requestUrl.pathname === "/version") {
    if (canvasMode) lastActivity = Date.now();
    res.writeHead(200, { "Content-Type": "text/plain; charset=utf-8" });
    res.end(newest ? newest.screen : "");
    return;
  }

  if (requestUrl.pathname === "/") {
    lastActivity = Date.now();
    const nonce = crypto.randomBytes(18).toString("base64url");
    res.setHeader("Content-Security-Policy", shellCsp(nonce));
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(renderShellPage(nonce, accessToken, newest?.filename || "prototype", newest?.screen));
    return;
  }

  if (requestUrl.pathname === "/preview") {
    lastActivity = Date.now();
    const nonce = crypto.randomBytes(18).toString("base64url");
    res.setHeader("Content-Security-Policy", previewCsp(nonce, embedding?.parentOrigin));
    const revisions = requestUrl.searchParams.getAll("revision");
    if (revisions.length) {
      // A stored version is shown read-only: it is hash-verified and sanitized
      // like the current sketch, and viewing it never changes the room.
      const revisionId = revisions.length === 1 && /^[1-9][0-9]{0,5}$/.test(revisions[0]) ? Number(revisions[0]) : 0;
      let view = null, status = 200;
      try {
        if (!workspaceState) throw new FeedbackError(409, "This preview has no saved project workspace.");
        if (!revisionId) throw new FeedbackError(400, "Invalid sketch version.");
        view = workspaceState.view(revisionId);
      } catch (error) { status = requestErrorStatus(error); }
      res.writeHead(status, { "Content-Type": "text/html; charset=utf-8" });
      res.end(view
        ? wrapInFrame(view.html, view.filename, view.screen, nonce, view.design, false, { revisionId: view.revisionId }, Boolean(embedding))
        : wrapInFrame(`<div style="display:flex;align-items:center;justify-content:center;min-height:60vh"><div style="text-align:center"><h2>Versjonen kan ikke vises</h2><p class="subtitle">${status === 409 && workspaceState ? "En lagret fil for denne versjonen er endret eller mangler. Ingen filer er endret." : "Versjonen finnes ikke i dette arbeidet."}</p></div></div>`,
          "unavailable", "00000000000000000000000000000000", nonce, null, false, { revisionId, unavailable: true }, Boolean(embedding)));
      return;
    }
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    const content = newest
      ? newest.content
      : `<div style="display:flex;align-items:center;justify-content:center;min-height:60vh">
          <div style="text-align:center">
            <h2>Venter på innhold …</h2>
            <p class="subtitle">Agenten skriver en skisse. Siden oppdateres automatisk.</p>
          </div>
        </div>`;
    res.end(
      wrapInFrame(
        content,
        newest?.filename || "waiting",
        newest?.screen || "00000000000000000000000000000000",
        nonce,
        newest?.design,
        newest?.designError,
        null, Boolean(embedding),
      ),
    );
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
  try { workspaceStore?.close(); } catch { /* Keep saved work even when transport cleanup fails. */ }
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
  if (Date.now() - lastActivity > idleTimeoutMs) shutdown("inactivity");
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

function serverInfo() {
  const address = server.address();
  const port = typeof address === "object" && address ? address.port : 0;
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
    idle_timeout_ms: idleTimeoutMs,
  };
  writePrivateJson(path.join(stateDir, "server-info.json"), info);
  return info;
}

const CANVAS_CHANNEL = "visual-companion-canvas";
function canvasEvent(value) {
  if (canvasMode && process.connected) {
    try { process.send({ channel: CANVAS_CHANNEL, version: 1, ...value }, () => {}); }
    catch { /* A lost parent must not turn a committed HTTP write into a retry. */ }
  }
}
// A declared control can only change the sketch through a style rule that names
// one of its values. Name the controls without one, so the sketch can be fixed
// before review. Values written into markup by the editor do not count.
function inertControls(newest) {
  if (!newest?.design) return [];
  const css = (String(newest.content).match(/<style\b[^>]*>[\s\S]*?<\/style>/gi) || []).join("\n");
  const inert = [];
  for (const target of newest.design.targets) for (const control of target.controls) {
    const values = control.options.map(option => option.value).join("|");
    const rule = new RegExp(`data-vc-setting-${control.id}\\s*[~|^$*]?=\\s*["']?(?:${values})(?![a-z0-9-])`);
    if (!rule.test(css)) inert.push({ variant: target.variant, target: target.key, control: control.id, label: control.label });
  }
  return inert;
}
function canvasReadState() {
  const newest = newestContent();
  activateScreen(newest);
  const inert = inertControls(newest);
  return { ...canvasState.summary(), screen: newest?.screen || "", filename: newest?.filename || "", styles: styleReceipt,
    ...(inert.length ? { inertControls: inert } : {}),
    ...(workspaceState ? { workspace: workspaceState.summary() } : {}) };
}
function publishCanvasRevision(input) {
  if (!keys(input, ["expectedScreen", "filename", "html"], ["design"]) || typeof input.expectedScreen !== "string" ||
      !/^(?:[a-f0-9]{32})?$/.test(input.expectedScreen) || typeof input.filename !== "string" ||
      !/^[a-z0-9][a-z0-9-]{0,95}\.html$/.test(input.filename) || typeof input.html !== "string" ||
      !input.html.trim() || Buffer.byteLength(input.html) > MAX_CONTENT_BYTES ||
      (Object.hasOwn(input, "design") && (!validDesign(input.design) || Buffer.byteLength(JSON.stringify(input.design)) > MAX_DESIGN_BYTES))) {
    throw new FeedbackError(400, "Invalid sketch revision.");
  }
  const before = newestContent();
  if (input.design?.version === 2) validateEditorBindings(input.html, input.design);
  if (input.expectedScreen !== (before?.screen || "")) throw new FeedbackError(409, "The sketch changed. Read the current screen before publishing.");
  if (workspaceState) {
    workspaceState.publish(input);
    return canvasReadState();
  }
  const filename = path.join(contentDir, input.filename);
  const descriptor = path.join(contentDir, input.filename.slice(0, -5) + ".design.json");
  if (fs.existsSync(filename) || fs.existsSync(descriptor)) throw new FeedbackError(409, "Use a new filename for each sketch revision.");
  const written = [];
  const write = (target, content) => {
    const fd = fs.openSync(target, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_NOFOLLOW, 0o600);
    const stat = fs.fstatSync(fd);
    written.push({ target, stat });
    try { fs.writeFileSync(fd, content); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
  };
  try {
    if (Object.hasOwn(input, "design")) write(descriptor, JSON.stringify(input.design));
    write(filename, input.html);
    // Deterministic ordering even when two small revisions share an mtime tick.
    const modified = before ? fs.statSync(path.join(contentDir, before.filename)).mtimeMs : 0;
    const time = new Date(Math.max(Date.now(), modified + 1));
    fs.utimesSync(filename, time, time);
    return canvasReadState();
  } catch (error) {
    for (const { target, stat } of written.reverse()) {
      try { const current = fs.lstatSync(target); if (current.dev === stat.dev && current.ino === stat.ino) fs.unlinkSync(target); } catch { /* Do not follow replacement paths. */ }
    }
    throw error;
  }
}
let savedWorkspaceRequest = null, savedWorkspaceDurabilityPending = false;
function saveCanvasWorkspace(input) {
  if (!keys(input, ["workspacePath", "workspaceId", "title", "expectedScreen", "expectedRevision"]) || !validWorkspacePath(input.workspacePath) ||
      typeof input.workspaceId !== "string" || !/^[a-f0-9]{24}$/.test(input.workspaceId) || typeof input.title !== "string" || !input.title.trim() || Buffer.byteLength(input.title) > 200 ||
      /[\u0000-\u001f\u007f]/.test(input.title) || typeof input.expectedScreen !== "string" || !/^[a-f0-9]{32}$/.test(input.expectedScreen) ||
      !Number.isSafeInteger(input.expectedRevision) || input.expectedRevision < 0) throw new FeedbackError(400, "Invalid proposal storage request.");
  if (workspaceState) {
    // An acknowledged or uncertain first save is never copied again. Reopened
    // recovery also verifies every registered pair before completing the link.
    try {
      const summary = workspaceState.summary();
      if (summary.id !== input.workspaceId || summary.path !== input.workspacePath || savedWorkspaceRequest && JSON.stringify(savedWorkspaceRequest) !== JSON.stringify(input)) throw new Error("Different save.");
      workspaceStore.assertOpen(); workspaceStore.assertUnchanged();
      for (const revision of feedback.state.workspace.revisions) {
        const pair = workspaceStore.readRevision(revision);
        if (screenIdentity(revision.filename, pair.html, pair.design) !== revision.screen) throw new Error("Changed saved pair.");
      }
      if (savedWorkspaceDurabilityPending || workspaceState.recovered && !savedWorkspaceRequest) {
        workspaceStore.persist(feedback.state); savedWorkspaceDurabilityPending = false;
        savedWorkspaceRequest = JSON.parse(JSON.stringify(input));
      }
      return canvasReadState();
    } catch { throw new FeedbackError(503, "Det lagrede forslaget kunne ikke bekreftes. Behold den samme lagringshandlingen og kontroller prosjektfilene før et nytt forsøk."); }
  }
  let promoted;
  try {
    promoted = promoteTemporaryWorkspace({ feedback, projectDir, ...input, currentScreen: newestContent()?.screen || "", readPair(record) {
      const bytes = readRegularFile(path.join(contentDir, record.filename), contentDir, MAX_CONTENT_BYTES, true);
      const html = bytes.toString("utf8");
      if (!Buffer.from(html).equals(bytes)) throw new Error("Invalid source encoding.");
      const declaration = readDesign(record.filename);
      if (declaration.designError) throw new Error("Unavailable design controls.");
      return { html, design: declaration.design };
    } });
  } catch (error) {
    throw new FeedbackError([400, 409, 413, 429].includes(error?.status) ? error.status : 409,
      "Forslaget ble ikke lagret. Skissen, innspillene eller målmappen kunne ikke verifiseres. Det midlertidige arbeidet er beholdt.");
  }
  workspaceStore = promoted.store; workspaceState = promoted.workspaceState;
  savedWorkspaceRequest = JSON.parse(JSON.stringify(input)); savedWorkspaceDurabilityPending = Boolean(promoted.committedError);
  if (savedWorkspaceDurabilityPending) throw new FeedbackError(503, "Forslaget er skrevet, men varig lagring er ikke bekreftet. Gjenta samme lagringshandling.");
  try { return canvasReadState(); }
  catch { throw new FeedbackError(503, "Forslaget er skrevet, men gjeldende status kunne ikke bekreftes. Behold samme lagringshandling; ikke opprett et nytt forslag."); }
}
async function canvasCommand(method, params) {
  lastActivity = Date.now();
  if (method === "readSubmission") return canvasState.read(params);
  if (method === "publishRevision") return publishCanvasRevision(params);
  if (method === "saveWorkspace") return saveCanvasWorkspace(params);
  if (method === "reviewSubmission") { canvasState.review(params); return canvasReadState(); }
  if (method === "updateComment") { canvasState.updateComment(params); return canvasReadState(); }
  if (method === "markDelivery") { canvasState.delivery(params); return canvasReadState(); }
  if (["listHistory", "readRevision", "restoreRevision"].includes(method)) {
    if (!workspaceState) throw new FeedbackError(409, "This sketch is temporary. Open a project workspace to keep version history.");
    if (method === "listHistory") return workspaceState.history(params);
    if (method === "readRevision") return workspaceState.read(params);
    workspaceState.restore(params); return canvasReadState();
  }
  if (method === "openView" && Object.hasOwn(params, "embedding")) {
    if (!keys(params, ["embedding"])) throw new FeedbackError(400, "Invalid embedding options.");
    const next = createHtmlEmbedding(params.embedding);
    embedding?.revoke(); embedding = next; viewGeneration += 1;
    accessToken = crypto.randomBytes(32).toString("base64url"); tokenBuffer = Buffer.from(accessToken);
  } else if (!keys(params, [])) throw new FeedbackError(400, "No arguments expected.");
  if (method === "readState") return canvasReadState();
  if (method === "readPreview") throw new FeedbackError(409, "read_preview observes running apps only. For HTML sketches use read_state and the available visual inspection tools.");
  if (method === "closeView") {
    revokeView();
    if (server.listening) await new Promise(resolve => { server.close(resolve); server.closeAllConnections?.(); });
    return { closed: true };
  }
  if (method === "openView") {
    const openingGeneration = viewGeneration;
    if (!server.listening) {
      accessToken = crypto.randomBytes(32).toString("base64url"); tokenBuffer = Buffer.from(accessToken);
      await new Promise((resolve, reject) => {
        const error = value => { server.off("listening", ready); reject(value); };
        const ready = () => { server.off("error", error); resolve(); };
        server.once("error", error); server.once("listening", ready); server.listen(0, normalizeHost(host));
      });
    }
    if (openingGeneration !== viewGeneration) {
      revokeView();
      if (server.listening) await new Promise(resolve => { server.close(resolve); server.closeAllConnections?.(); });
      throw new FeedbackError(410, "The proposal was closed while opening.");
    }
    const info = serverInfo();
    if (embedding) return { url: `http://${authority}/embedded?invitation=${embedding.invitation}`, origin: `http://${authority}`, activationKey: embedding.activationKey, leaseId: embedding.leaseId, title: workspaceState?.summary().title || "Forslag", status: "Forslag i verkstedet." };
    return { url: info.url, title: workspaceState?.summary().title || "Midlertidig skisse", status: workspaceState ? "Arbeidet lagres i prosjektet. Send innspill når runden er klar." : "Midlertidig skisse. Den og innspillene forsvinner når samtalen avsluttes eller etter fire timer uten bruk." };
  }
  if (method === "retire") return { retired: true };
  throw new FeedbackError(400, "Unknown canvas operation.");
}
if (canvasMode) {
  let commands = Promise.resolve();
  process.on("message", message => {
    if (message?.channel !== CANVAS_CHANNEL || message?.version !== 1 || !Number.isSafeInteger(message.id) || message.id < 1) return;
    if (keys(message, ["channel", "version", "id", "method", "params"]) && ["closeView", "retire"].includes(message.method) && keys(message.params, [])) revokeView();
    const requestedGeneration = viewGeneration;
    commands = commands.then(async () => {
      try {
        if (message.method === "openView" && requestedGeneration !== viewGeneration) throw new FeedbackError(410, "The proposal was closed before opening.");
        if (!keys(message, ["channel", "version", "id", "method", "params"]) || typeof message.method !== "string" ||
            Buffer.byteLength(JSON.stringify(message)) > MAX_CONTENT_BYTES + MAX_DESIGN_BYTES + 64 * 1024) throw new FeedbackError(400, "Invalid canvas request.");
        const result = await canvasCommand(message.method, message.params);
        const reply = { channel: CANVAS_CHANNEL, version: 1, id: message.id, ok: true, result };
        if (message.method === "retire") process.send(reply, () => shutdown("canvas-retired"));
        else canvasEvent({ id: message.id, ok: true, result });
      } catch (error) {
        canvasEvent({ id: message.id, ok: false, status: requestErrorStatus(error),
          error: error instanceof FeedbackError || error?.expose === true ? error.message : error.errorCode === "invalid-editor-bindings"
            ? editorBindingErrorMessage(error) : "Canvas state is unavailable." });
      }
    });
  });
  process.once("disconnect", () => shutdown("canvas-disconnected"));
}

server.listen(requestedPort, normalizeHost(host), () => {
  const info = serverInfo();
  console.log(JSON.stringify(info));
  canvasEvent({ event: "ready", info });
});
}

void runPreview().catch(error => {
  try { workspaceStore?.close(); } catch { /* Only release this process's claim. */ }
  try { removeOwnedSession(sessionId); } catch { /* Never touch project artifacts on failed startup. */ }
  const status = Number.isInteger(error.status) && error.status >= 400 && error.status <= 599 ? error.status : 500;
  const detail = String(error?.message || "");
  const file = /[a-z0-9][a-z0-9-]{0,95}\.(?:design\.json|html)/.exec(detail)?.[0];
  const holder = /already open in process ([0-9]+)/.exec(detail)?.[1], lockFile = /remove (\/\S+\.json)\.$/.exec(detail)?.[1];
  const message = status === 409 && holder && lockFile
    ? `Arbeidsrommet er åpent i en annen økt (prosess ${holder}). Lukk den andre økten før du prøver igjen. Kjører ingen slik økt, kan låsfilen slettes: ${lockFile}`
    : status === 409 && /already open|still acquiring|simultaneous workspace open/.test(detail)
    ? "Arbeidsrommet er åpent i en annen økt. Lukk den andre økten før du prøver igjen."
    : status === 409 && /revisions but no workspace\.json/.test(detail) ? "Mappen har skisseversjoner, men mangler workspace.json. Ingen filer er endret. Hent workspace.json tilbake fra versjonskontroll, eller flytt revisions-mappen til side for å starte på nytt."
    : status === 409 && /requires an empty/.test(detail) ? "Mappen for det nye arbeidsrommet er ikke tom. Ingen filer er endret. Velg en annen mappe, eller åpne det eksisterende arbeidet."
    : status === 409 && file ? `Arbeidsrommet kan ikke åpnes fordi den lagrede filen ${file} ikke stemmer med registeret. Ingen filer er endret. Hent filen tilbake fra versjonskontroll, og hold rommappen utenfor formatering.`
    : status === 409 ? "Arbeidsrommet ble endret utenfra eller har filer som ikke stemmer med registeret. Ingen filer er endret. Kontroller prosjektfilene før du prøver igjen."
    : status === 404 ? "Arbeidsrommet finnes ikke. Opprett det uttrykkelig eller velg et eksisterende arbeid."
    : status === 501 ? "Prosjektlagrede designrom støttes foreløpig bare på Unix-verter som macOS og Linux."
      : "Arbeidsrommet kunne ikke åpnes. Kontroller stien og de lagrede filene.";
  if (canvasMode && process.connected) {
    const timeout = setTimeout(() => process.exit(2), 1000);
    process.send({ channel: "visual-companion-canvas", version: 1, event: "startup-error", status, error: message }, () => { clearTimeout(timeout); process.exit(2); });
  } else { console.error(JSON.stringify({ type: "error", message })); process.exitCode = 2; }
});
