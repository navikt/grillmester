"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { afterEach, test } = require("node:test");

const SERVER = path.resolve(__dirname, "../scripts/server.js");
const temporaryRoots = new Set();
const children = new Set();

function makeProject() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "grillmester-vc-test-"));
  temporaryRoots.add(root);
  return root;
}

function runCli(projectDir, extraArgs = []) {
  return new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [SERVER, "--project-dir", projectDir, ...extraArgs],
      { stdio: ["ignore", "pipe", "pipe"] },
    );
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("error", reject);
    child.on("close", (code, signal) =>
      resolve({ code, signal, stdout, stderr }),
    );
  });
}

function startServer(projectDir, extraArgs = [], environment = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        SERVER,
        "--project-dir",
        projectDir,
        "--host",
        "127.0.0.1",
        ...extraArgs,
      ],
      {
        stdio: ["ignore", "pipe", "pipe"],
        env: { ...process.env, ...environment },
      },
    );
    children.add(child);
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    let stdout = "";
    let stderr = "";
    const timeout = setTimeout(() => {
      child.kill("SIGKILL");
      reject(new Error(`server startup timed out; stderr=${stderr}`));
    }, 5_000);

    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
      const newline = stdout.indexOf("\n");
      if (newline === -1) return;
      const firstLine = stdout.slice(0, newline).trim();
      let info;
      try {
        info = JSON.parse(firstLine);
      } catch (error) {
        clearTimeout(timeout);
        reject(
          new Error(`invalid startup JSON ${JSON.stringify(firstLine)}: ${error}`),
        );
        return;
      }
      if (info.type !== "server-started") {
        clearTimeout(timeout);
        reject(new Error(`unexpected startup response: ${firstLine}`));
        return;
      }
      clearTimeout(timeout);
      resolve({ child, info, getStderr: () => stderr });
    });
    child.on("error", (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    child.on("close", (code, signal) => {
      if (!stdout.includes('"type":"server-started"')) {
        clearTimeout(timeout);
        reject(
          new Error(
            `server exited before startup (code=${code}, signal=${signal}); stderr=${stderr}`,
          ),
        );
      }
    });
  });
}

function stopServer(running, signal = "SIGTERM") {
  return new Promise((resolve) => {
    const { child } = running;
    if (child.exitCode !== null || child.signalCode !== null) {
      children.delete(child);
      resolve();
      return;
    }
    child.once("close", () => {
      children.delete(child);
      resolve();
    });
    child.kill(signal);
  });
}

function snapshotTree(root) {
  const result = {};
  function visit(directory, prefix = "") {
    for (const entry of fs
      .readdirSync(directory, { withFileTypes: true })
      .sort((a, b) => a.name.localeCompare(b.name))) {
      const relative = path.join(prefix, entry.name);
      const absolute = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        result[relative] = { type: "directory" };
        visit(absolute, relative);
      } else if (entry.isSymbolicLink()) {
        result[relative] = { type: "symlink", target: fs.readlinkSync(absolute) };
      } else {
        result[relative] = {
          type: "file",
          content: fs.readFileSync(absolute, "utf8"),
        };
      }
    }
  }
  visit(root);
  return result;
}

function endpoint(startupUrl, pathname) {
  const url = new URL(startupUrl);
  url.pathname = pathname;
  return url;
}

function mode(target) {
  return fs.statSync(target).mode & 0o777;
}

async function postEvent(startupUrl, value) {
  const url = endpoint(startupUrl, "/events");
  let body = value;
  if (value && typeof value === "object" && !Array.isArray(value) && !("screen" in value)) {
    const version = await fetch(endpoint(startupUrl, "/version"));
    body = { ...value, screen: await version.text() };
  }
  return fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Origin: url.origin,
    },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

afterEach(() => {
  for (const child of children) {
    if (child.exitCode === null && child.signalCode === null) {
      child.kill("SIGKILL");
    }
  }
  children.clear();
  for (const root of temporaryRoots) {
    fs.rmSync(root, { recursive: true, force: true });
  }
  temporaryRoots.clear();
});

test("remote mode is rejected before any consumer-repository mutation", async () => {
  const projectDir = makeProject();

  const result = await runCli(projectDir, ["--allow-remote"]);

  assert.notEqual(result.code, 0);
  assert.match(
    `${result.stdout}\n${result.stderr}`,
    /unknown option: --allow-remote/i,
  );
  assert.deepEqual(fs.readdirSync(projectDir), []);
});

test("a non-loopback bind host is rejected before startup", async () => {
  const projectDir = makeProject();

  const result = await runCli(projectDir, ["--host", "0.0.0.0"]);

  assert.notEqual(result.code, 0);
  assert.match(`${result.stdout}\n${result.stderr}`, /refusing non-local bind/i);
  assert.deepEqual(fs.readdirSync(projectDir), []);
});

test("idle timeout is explicit, bounded, and reported at startup", async () => {
  const projectDir = makeProject();

  const invalid = await runCli(projectDir, ["--idle-timeout-minutes", "0"]);
  assert.notEqual(invalid.code, 0);
  assert.match(`${invalid.stdout}\n${invalid.stderr}`, /integer from 1 through 480/i);
  assert.deepEqual(fs.readdirSync(projectDir), []);

  const running = await startServer(projectDir, ["--idle-timeout-minutes", "1"]);
  try {
    assert.equal(running.info.idle_timeout_ms, 60_000);
  } finally {
    await stopServer(running);
  }
});

test("a symlinked project directory is rejected before runtime access", async () => {
  const projectDir = makeProject();
  const linkParent = makeProject();
  const projectLink = path.join(linkParent, "project-link");
  fs.symlinkSync(projectDir, projectLink);

  const result = await runCli(projectLink, [
    "--cleanup",
    "0123456789abcdef01234567",
  ]);

  assert.notEqual(result.code, 0);
  assert.match(`${result.stdout}\n${result.stderr}`, /non-symlink directory/i);
});

test("starting a preview does not mutate the consumer worktree", async () => {
  const projectDir = makeProject();
  fs.writeFileSync(path.join(projectDir, "package.json"), '{"private":true}\n');
  fs.writeFileSync(path.join(projectDir, "pnpm-lock.yaml"), "lockfileVersion: 9\n");
  fs.writeFileSync(path.join(projectDir, ".gitignore"), "dist/\n");
  const before = snapshotTree(projectDir);

  const running = await startServer(projectDir);
  try {
    assert.equal(
      path.relative(projectDir, running.info.screen_dir).startsWith(".."),
      true,
      "screen_dir must live outside the consumer repository",
    );
    assert.deepEqual(snapshotTree(projectDir), before);
  } finally {
    await stopServer(running);
  }
  assert.deepEqual(snapshotTree(projectDir), before);
});

test("agent HTML is isolated in a sandbox with a no-external-network CSP", async () => {
  const projectDir = makeProject();
  const running = await startServer(projectDir);
  const rasterDataUrl =
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";
  try {
    fs.writeFileSync(
      path.join(running.info.screen_dir, "unsafe.html"),
      '<h2 data-choice="choice-1">Konsept</h2>' +
        '<script<script src="https://example.com/script">fetch("https://example.com/leak")</script\t\n ignored>' +
        '<iframe<iframe src="https://example.com/frame"></iframe>' +
        '<a href="https://example.com/link" onclick="fetch(1)">lenke</a>' +
        '<img src="https://example.com/pixel" onerror="fetch(2)">' +
        `<img id="safe-raster" src="${rasterDataUrl}" srcset="${rasterDataUrl} 2x">` +
        '<img id="active-svg" src="data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=">',
    );

    const shellResponse = await fetch(running.info.url);
    const shell = await shellResponse.text();
    assert.equal(shellResponse.status, 200);
    assert.match(
      shellResponse.headers.get("content-security-policy") || "",
      /frame-src 'self'/,
    );
    assert.match(shell, /<iframe[^>]+sandbox="allow-scripts"/);
    assert.doesNotMatch(shell, /allow-same-origin/);
    assert.match(shell, /id="vc-paused"/);
    assert.match(shell, /id="vc-status"/);
    assert.match(shell, /Kobler til …/);
    assert.match(shell, /status\.textContent = "Tilkoblet"/);
    assert.match(shell, /Forhåndsvisningen er satt på pause/);
    assert.match(shell, /command: "selection-status"/);
    assert.match(shell, /choice: event\.choice/);
    assert.match(shell, /type: event\.type/);
    assert.match(shell, /response\.ok \? "saved" : "failed"/);
    assert.doesNotMatch(shell, /\.catch\(\(\) => \{\}\)/);

    const previewResponse = await fetch(
      endpoint(running.info.url, "/preview"),
    );
    const preview = await previewResponse.text();
    const csp = previewResponse.headers.get("content-security-policy") || "";
    assert.equal(previewResponse.status, 200);
    assert.match(csp, /default-src 'none'/);
    assert.match(csp, /connect-src 'none'/);
    assert.match(csp, /img-src data: blob:/);
    assert.match(csp, /frame-src 'none'/);
    assert.match(csp, /script-src[^;]*'nonce-[^']+'/);
    assert.doesNotMatch(csp, /https?:/);
    const forbiddenExternalHost = ["example", "com"].join(".");
    assert.equal(preview.includes(forbiddenExternalHost), false);
    assert.equal(preview.toLowerCase().includes("script<script"), false);
    assert.equal(preview.toLowerCase().includes("iframe<iframe"), false);
    assert.equal(preview.toLowerCase().includes("onclick="), false);
    assert.equal(preview.toLowerCase().includes("onerror="), false);
    assert.equal(
      preview.includes(
        `<img id="safe-raster" src="${rasterDataUrl}" srcset="${rasterDataUrl} 2x">`,
      ),
      true,
    );
    assert.equal(preview.includes("data:image/svg+xml"), false);
    assert.match(preview, /parent\.postMessage/);
    assert.match(preview, /ikke lagret — si valget i chatten/);
  } finally {
    await stopServer(running);
  }
});

test("parser-state markup cannot swallow the trusted preview helper", async () => {
  const projectDir = makeProject();
  const running = await startServer(projectDir);
  try {
    fs.writeFileSync(
      path.join(running.info.screen_dir, "parser-state.html"),
      '<textarea id="balanced-textarea">Begrunnelse</textarea>' +
        '<svg><title id="balanced-title">Søk</title></svg>' +
        '<style id="balanced-style">.safe-marker { color: inherit; }</style>' +
        '<!--balanced-comment-->' +
        '<!--unclosed-comment-marker' +
        '<plaintext id="unclosed-plaintext">plaintext-marker' +
        '<textarea id="unclosed-textarea">textarea-marker' +
        '<title id="unclosed-title">title-marker' +
        '<xmp id="unclosed-xmp">xmp-marker' +
        '<template id="unclosed-template">template-marker' +
        '<noscript id="unclosed-noscript">noscript-marker' +
        '<style id="unclosed-style">style-marker' +
        '<noembed id="unclosed-noembed">noembed-marker' +
        '<noframes id="unclosed-noframes">noframes-marker',
    );

    const response = await fetch(endpoint(running.info.url, "/preview"));
    const preview = await response.text();
    assert.equal(response.status, 200);

    assert.match(preview, /<textarea id="balanced-textarea">/);
    assert.match(preview, /<title id="balanced-title">/);
    assert.match(preview, /<style id="balanced-style">/);
    assert.match(preview, /<!--balanced-comment-->/);
    assert.equal(preview.includes("<!--unclosed-comment-marker"), false);
    assert.match(preview, /&lt;!--unclosed-comment-marker/);
    for (const element of [
      "plaintext",
      "textarea",
      "title",
      "xmp",
      "template",
      "noscript",
      "style",
      "noembed",
      "noframes",
    ]) {
      assert.equal(
        preview.includes(`<${element} id="unclosed-${element}">`),
        false,
        `unclosed ${element} tag must be flattened`,
      );
    }
    for (const marker of [
      "unclosed-comment-marker",
      "plaintext-marker",
      "textarea-marker",
      "title-marker",
      "xmp-marker",
      "template-marker",
      "noscript-marker",
      "style-marker",
      "noembed-marker",
      "noframes-marker",
    ]) {
      assert.match(preview, new RegExp(marker));
    }
    const helperStart = preview.indexOf(
      "window.__grillmesterVisualCompanionScreen=",
    );
    assert.ok(helperStart > preview.indexOf("noframes-marker"));
    assert.match(preview.slice(helperStart), /parent\.postMessage/);
  } finally {
    await stopServer(running);
  }
});

test("a new screen clears prior opaque selection events", async () => {
  const projectDir = makeProject();
  const running = await startServer(projectDir);
  try {
    const firstPath = path.join(running.info.screen_dir, "concept-a.html");
    fs.writeFileSync(firstPath, '<div class="option"><h3>A</h3></div>');
    const firstVersionResponse = await fetch(endpoint(running.info.url, "/version"));
    const firstScreen = await firstVersionResponse.text();
    assert.equal(
      (await postEvent(running.info.url, { type: "click", choice: "choice-1" })).status,
      200,
    );

    const eventPath = path.join(running.info.state_dir, "events.jsonl");
    assert.match(fs.readFileSync(eventPath, "utf8"), /"choice":"choice-1"/);

    const secondPath = path.join(running.info.screen_dir, "concept-b.html");
    fs.writeFileSync(secondPath, '<div class="option"><h3>B</h3></div>');
    const newer = new Date(Date.now() + 2_000);
    fs.utimesSync(secondPath, newer, newer);
    await fetch(endpoint(running.info.url, "/version"));
    assert.equal(fs.existsSync(eventPath), false);

    const stale = await postEvent(running.info.url, {
      type: "click",
      choice: "choice-1",
      screen: firstScreen,
    });
    assert.equal(stale.status, 409);

    assert.equal(
      (await postEvent(running.info.url, { type: "click", choice: "choice-2" })).status,
      200,
    );
    const currentEvents = fs.readFileSync(eventPath, "utf8");
    assert.doesNotMatch(currentEvents, /"choice":"choice-1"/);
    assert.match(currentEvents, /"choice":"choice-2"/);
  } finally {
    await stopServer(running);
  }
});

test("symlinked preview and CSS files cannot escape their allowed roots", async () => {
  const projectDir = makeProject();
  const outsideSecret = path.join(makeProject(), "secret.html");
  fs.writeFileSync(outsideSecret, "TOP-SECRET-SYMLINK-PROOF");
  const cssDirectory = path.join(
    projectDir,
    "node_modules/@navikt/ds-css/dist",
  );
  fs.mkdirSync(cssDirectory, { recursive: true });
  fs.symlinkSync(outsideSecret, path.join(cssDirectory, "index.css"));

  const running = await startServer(projectDir);
  try {
    fs.symlinkSync(
      outsideSecret,
      path.join(running.info.screen_dir, "latest.html"),
    );
    fs.writeFileSync(
      path.join(running.info.screen_dir, "oversized.html"),
      Buffer.alloc(2 * 1024 * 1024 + 1, "x"),
    );

    const response = await fetch(endpoint(running.info.url, "/preview"));
    const preview = await response.text();
    assert.equal(response.status, 200);
    assert.doesNotMatch(preview, /TOP-SECRET-SYMLINK-PROOF/);
    assert.match(preview, /Venter på innhold/);
    assert.match(running.getStderr(), /Aksel CSS was rejected/);
  } finally {
    await stopServer(running);
  }
});

for (const replacement of ["symlink", "fifo", "missing"]) {
  test(`a file replaced with ${replacement} immediately before opening is rejected`, {
    skip: process.platform === "win32" ? "requires POSIX file opening semantics" : false,
  }, async () => {
    const projectDir = makeProject();
    const cssDirectory = path.join(projectDir, "node_modules/@navikt/ds-css/dist");
    fs.mkdirSync(cssDirectory, { recursive: true });
    const cssPath = path.join(cssDirectory, "index.min.css");
    fs.writeFileSync(cssPath, "body { color: green; }");
    const outsidePath = path.join(makeProject(), "outside.css");
    const outsideContent = "OUTSIDE-FILE-MUST-NOT-BE-OPENED";
    fs.writeFileSync(outsidePath, outsideContent);
    const probePath = path.join(projectDir, "open-probe.json");
    const preloadPath = path.join(projectDir, "replace-before-open.js");
    fs.writeFileSync(preloadPath, `"use strict";
const fs = require("node:fs");
const { execFileSync } = require("node:child_process");
const target = fs.realpathSync(process.env.GRILLMESTER_TEST_OPEN_TARGET);
const originalOpen = fs.openSync;
let replaced = false;
fs.openSync = function patchedOpen(filename, ...args) {
  if (filename !== target || replaced) return originalOpen.call(fs, filename, ...args);
  replaced = true;
  fs.unlinkSync(target);
  if (process.env.GRILLMESTER_TEST_OPEN_REPLACEMENT === "symlink") {
    fs.symlinkSync(process.env.GRILLMESTER_TEST_OPEN_OUTSIDE, target);
  } else if (process.env.GRILLMESTER_TEST_OPEN_REPLACEMENT === "fifo") {
    execFileSync("mkfifo", [target]);
  }
  try {
    const descriptor = originalOpen.call(fs, filename, ...args);
    fs.writeFileSync(process.env.GRILLMESTER_TEST_OPEN_PROBE, JSON.stringify({ opened: true }));
    return descriptor;
  } catch (error) {
    fs.writeFileSync(process.env.GRILLMESTER_TEST_OPEN_PROBE, JSON.stringify({ opened: false, code: error.code }));
    throw error;
  }
};
`);

    const running = await startServer(projectDir, [], {
      GRILLMESTER_TEST_OPEN_TARGET: cssPath,
      GRILLMESTER_TEST_OPEN_REPLACEMENT: replacement,
      GRILLMESTER_TEST_OPEN_OUTSIDE: outsidePath,
      GRILLMESTER_TEST_OPEN_PROBE: probePath,
      NODE_OPTIONS: `--require=${preloadPath}`,
    });
    try {
      const probe = JSON.parse(fs.readFileSync(probePath, "utf8"));
      assert.match(running.getStderr(), /Aksel CSS was rejected/);
      if (replacement === "fifo") {
        assert.deepEqual(probe, { opened: true });
        assert.ok(fs.lstatSync(cssPath).isFIFO());
        assert.match(running.getStderr(), /Refusing non-regular file/);
      } else {
        assert.deepEqual(probe, {
          opened: false,
          code: replacement === "symlink" ? "ELOOP" : "ENOENT",
        });
        if (replacement === "missing") assert.equal(fs.existsSync(cssPath), false);
      }
      assert.equal(fs.readFileSync(outsidePath, "utf8"), outsideContent);
      const response = await fetch(endpoint(running.info.url, "/preview"));
      assert.equal(response.status, 200);
      assert.doesNotMatch(await response.text(), /OUTSIDE-FILE-MUST-NOT-BE-OPENED/);
    } finally {
      await stopServer(running);
    }
  });
}

test("a file changed in place during a bounded read is rejected", async () => {
  const projectDir = makeProject();
  const cssDirectory = path.join(
    projectDir,
    "node_modules/@navikt/ds-css/dist",
  );
  fs.mkdirSync(cssDirectory, { recursive: true });
  const cssPath = path.join(cssDirectory, "index.min.css");
  fs.writeFileSync(cssPath, Buffer.alloc(128 * 1024, "a"));

  const preloadPath = path.join(projectDir, "mutate-read.js");
  fs.writeFileSync(
    preloadPath,
    `"use strict";
const fs = require("node:fs");
const target = process.env.GRILLMESTER_TEST_MUTATE_READ;
const expected = fs.statSync(target);
const originalRead = fs.readSync;
let mutated = false;
fs.readSync = function patchedRead(descriptor, ...args) {
  const count = originalRead.call(fs, descriptor, ...args);
  const observed = fs.fstatSync(descriptor);
  if (!mutated && count > 0 && observed.dev === expected.dev && observed.ino === expected.ino) {
    mutated = true;
    fs.writeFileSync(target, Buffer.alloc(expected.size, "b"));
  }
  return count;
};
`,
  );

  const running = await startServer(projectDir, [], {
    GRILLMESTER_TEST_MUTATE_READ: cssPath,
    NODE_OPTIONS: `--require=${preloadPath}`,
  });
  try {
    fs.writeFileSync(
      path.join(running.info.screen_dir, "stable.html"),
      '<div class="option"><h3>Stabil</h3></div>',
    );
    const response = await fetch(endpoint(running.info.url, "/preview"));
    const preview = await response.text();
    assert.equal(response.status, 200);
    assert.match(preview, /Aksel CSS mangler/);
    assert.match(running.getStderr(), /File changed while it was being read/);
  } finally {
    await stopServer(running);
  }
});

test("selection state is private, schema-bound, opaque, and capped", async () => {
  const projectDir = makeProject();
  const running = await startServer(projectDir);
  try {
    fs.writeFileSync(
      path.join(running.info.screen_dir, "selection-test.html"),
      '<div class="option"><h3>A</h3></div>',
    );
    await fetch(endpoint(running.info.url, "/version"));

    assert.equal(mode(running.info.screen_dir), 0o700);
    assert.equal(mode(running.info.state_dir), 0o700);
    assert.equal(mode(path.dirname(running.info.state_dir)), 0o700);
    assert.equal(mode(path.join(running.info.state_dir, "server-info.json")), 0o600);

    const accepted = await postEvent(running.info.url, {
      type: "click",
      choice: "choice-1",
    });
    assert.equal(accepted.status, 200);

    const eventPath = path.join(running.info.state_dir, "events.jsonl");
    assert.equal(mode(eventPath), 0o600);
    const firstEvent = JSON.parse(fs.readFileSync(eventPath, "utf8").trim());
    assert.deepEqual(Object.keys(firstEvent).sort(), [
      "choice",
      "screen",
      "timestamp",
      "type",
    ]);
    assert.equal(firstEvent.choice, "choice-1");
    assert.equal("text" in firstEvent, false);

    const withVisibleText = await postEvent(running.info.url, {
      type: "click",
      choice: "choice-2",
      text: "Sensitive visible label",
    });
    assert.equal(withVisibleText.status, 400);

    const getEvents = await fetch(endpoint(running.info.url, "/events"));
    assert.equal(getEvents.status, 405);

    const oversized = await postEvent(
      running.info.url,
      JSON.stringify({ type: "click", choice: `choice-${"1".repeat(2000)}` }),
    );
    assert.equal(oversized.status, 413);

    const remaining = await Promise.all(
      Array.from({ length: 99 }, (_, index) =>
        postEvent(running.info.url, {
          type: index % 2 === 0 ? "click" : "deselect",
          choice: `choice-${(index % 9) + 1}`,
        }),
      ),
    );
    assert.equal(remaining.every((response) => response.status === 200), true);
    const overLimit = await postEvent(running.info.url, {
      type: "click",
      choice: "choice-1",
    });
    assert.equal(overLimit.status, 429);
    assert.ok(fs.statSync(eventPath).size <= 64 * 1024);
  } finally {
    await stopServer(running);
  }
});

test("session token, exact Host, and exact Origin block rebinding and cross-origin writes", async () => {
  const projectDir = makeProject();
  const running = await startServer(projectDir);
  try {
    const startupUrl = new URL(running.info.url);
    const withoutToken = new URL(startupUrl);
    withoutToken.search = "";
    assert.equal((await fetch(withoutToken)).status, 403);

    const reboundHost = `attacker.invalid:${startupUrl.port}`;
    const rebound = await fetch(startupUrl, {
      headers: {
        Host: reboundHost,
        Origin: `http://${reboundHost}`,
      },
    });
    assert.equal(rebound.status, 403);

    const wrongOrigin = await fetch(startupUrl, {
      headers: { Origin: "https://attacker.invalid" },
    });
    assert.equal(wrongOrigin.status, 403);

    const eventUrl = endpoint(running.info.url, "/events");
    const noOriginEvent = await fetch(eventUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "click", choice: "choice-1" }),
    });
    assert.equal(noOriginEvent.status, 403);
  } finally {
    await stopServer(running);
  }
});

test("cleanup is marker-bound to one exact session and never broad-deletes", async () => {
  const projectDir = makeProject();
  const first = await startServer(projectDir);
  const second = await startServer(projectDir);
  const firstSessionRoot = path.dirname(first.info.state_dir);
  const secondSessionRoot = path.dirname(second.info.state_dir);

  await stopServer(first, "SIGKILL");
  await stopServer(second, "SIGKILL");
  assert.equal(fs.existsSync(firstSessionRoot), true);
  assert.equal(fs.existsSync(secondSessionRoot), true);

  const cleanupFirst = await runCli(projectDir, [
    "--cleanup",
    first.info.session_id,
  ]);
  assert.equal(cleanupFirst.code, 0, cleanupFirst.stderr);
  assert.equal(fs.existsSync(firstSessionRoot), false);
  assert.equal(fs.existsSync(secondSessionRoot), true);

  const broadCleanup = await runCli(projectDir, ["--cleanup-all"]);
  assert.notEqual(broadCleanup.code, 0);
  assert.match(
    `${broadCleanup.stdout}\n${broadCleanup.stderr}`,
    /broad cleanup is not supported/i,
  );
  assert.equal(fs.existsSync(secondSessionRoot), true);

  const cleanupSecond = await runCli(projectDir, [
    "--cleanup",
    second.info.session_id,
  ]);
  assert.equal(cleanupSecond.code, 0, cleanupSecond.stderr);
  assert.equal(fs.existsSync(secondSessionRoot), false);

  const graceful = await startServer(projectDir);
  const gracefulSessionRoot = path.dirname(graceful.info.state_dir);
  await stopServer(graceful);
  assert.equal(fs.existsSync(gracefulSessionRoot), false);
});

const COMMENTS = path.resolve(__dirname, "../scripts/comments.js");
function runComments(args) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [COMMENTS, ...args], { stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "", stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", (code) => resolve({ code, stdout, stderr }));
  });
}
async function feedbackRequest(url, pathname, method = "GET", body) {
  return fetch(endpoint(url, pathname), {
    method,
    headers: { Origin: new URL(url).origin, ...(method === "GET" ? {} : { "Content-Type": "application/json" }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
}
async function previewScreen(running, content = "<h1>Prototype</h1>") {
  fs.writeFileSync(path.join(running.info.screen_dir, "test.html"), content);
  return (await fetch(endpoint(running.info.url, "/version"))).text();
}
function commentFor(screen, overrides = {}) {
  return {
    screen, kind: "point", text: "Make the primary action clearer.",
    anchor: { path: "main:nth-of-type(1) > button:nth-of-type(1)", role: "button", rect: { x: 20, y: 40, width: 100, height: 30 }, viewport: { width: 1200, height: 800 } },
    ...overrides,
  };
}

test("feedback persists privately across screen versions, with deliberate batches and replies", async () => {
  const projectDir = makeProject();
  const running = await startServer(projectDir);
  try {
    const screen = await previewScreen(running);
    const created = await feedbackRequest(running.info.url, "/comments", "POST", commentFor(screen));
    assert.equal(created.status, 200);
    const snapshot = await created.json();
    assert.equal(snapshot.comments.length, 1);
    assert.equal(snapshot.comments[0].submission, 0);
    assert.equal(snapshot.screens[0].filename, "test.html");
    const id = snapshot.comments[0].id;
    assert.match(id, /^[a-f0-9]{24}$/);
    const filename = path.join(running.info.state_dir, "comments.json");
    assert.equal(mode(filename), 0o600);
    assert.equal(fs.existsSync(path.join(running.info.state_dir, "events.jsonl")), false);
    const nextScreen = await previewScreen(running, "<h1>Updated prototype</h1>");
    assert.notEqual(screen, nextScreen);
    const stale = await feedbackRequest(running.info.url, "/comments", "POST", commentFor(screen, { text: "My frozen tab still shows the prior screen." }));
    assert.equal(stale.status, 200);
    const submitted = await feedbackRequest(running.info.url, "/comments/submit", "POST", { screen });
    const batch = await submitted.json();
    assert.equal(batch.submission, 1);
    assert.deepEqual(batch.comments.map((item) => item.submission), [1, 1]);
    assert.equal((await feedbackRequest(running.info.url, "/comments/submit", "POST", { screen })).status, 409);
    const resolved = await feedbackRequest(running.info.url, `/comments/${id}`, "PATCH", { status: "fixed", reply: "The primary action now has a stronger label." });
    assert.equal(resolved.status, 200);
    const after = (await resolved.json()).comments[0];
    assert.equal(after.status, "fixed");
    assert.match(after.reply, /stronger label/);
    assert.equal(after.submission, 1);
    assert.equal((await feedbackRequest(running.info.url, `/comments/${id}`, "DELETE", {})).status, 200);
    const persisted = JSON.parse(fs.readFileSync(filename, "utf8"));
    assert.equal(persisted.comments.length, 1);
    assert.equal(persisted.screens.length, 2);
    assert.deepEqual(fs.readdirSync(projectDir), []);
  } finally { await stopServer(running); }
});

test("feedback rejects unknown fields, DOM data, unsafe geometry, and forged write origins", async () => {
  const running = await startServer(makeProject());
  try {
    const screen = await previewScreen(running);
    const valid = commentFor(screen);
    const badValues = [
      { ...valid, html: "<input value='secret'>" },
      { ...valid, anchor: { ...valid.anchor, text: "captured content" } },
      { ...valid, anchor: { ...valid.anchor, path: "#customer-name" } },
      { ...valid, anchor: { ...valid.anchor, role: "customer account" } },
      { ...valid, anchor: { ...valid.anchor, rect: { ...valid.anchor.rect, x: -1 } } },
      { ...valid, anchor: { ...valid.anchor, rect: { ...valid.anchor.rect, height: 1e100 } } },
      { ...valid, text: "ø".repeat(1001) },
      { ...valid, text: "" },
      { ...valid, text: "null\0character" },
      { ...valid, kind: "script" },
      { ...valid, proposal: { property: "text", value: "unannounced edit" } },
      { ...valid, kind: "edit", proposal: { property: "innerHTML", value: "<b>wrong</b>" } },
      { ...valid, kind: "edit", proposal: { property: "text", value: "fine", original: "captured content" } },
    ];
    for (const value of badValues) assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", value)).status, 400, JSON.stringify(value));
    assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", { ...valid, screen: "a".repeat(32) })).status, 409);
    assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", { ...valid, text: "x".repeat(20000) })).status, 413);
    const url = endpoint(running.info.url, "/comments");
    for (const origin of [undefined, "null", "https://attacker.invalid"]) {
      assert.equal((await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", ...(origin === undefined ? {} : { Origin: origin }) }, body: JSON.stringify(valid) })).status, 403);
    }
    assert.equal((await fetch(url, { method: "POST", headers: { "Content-Type": "application/jsonp", Origin: url.origin }, body: JSON.stringify(valid) })).status, 415);
    const missingToken = new URL(url); missingToken.search = "";
    assert.equal((await fetch(missingToken)).status, 403);
    const edit = await feedbackRequest(running.info.url, "/comments", "POST", { ...valid, kind: "edit", text: "", proposal: { property: "text", value: "Continue" } });
    assert.equal(edit.status, 200);
    const id = (await edit.json()).comments[0].id;
    for (const patch of [{}, { text: "changed" }, { status: "done" }, { reply: "x".repeat(2001) }]) assert.equal((await feedbackRequest(running.info.url, `/comments/${id}`, "PATCH", patch)).status, 400);
    assert.equal((await feedbackRequest(running.info.url, `/comments/${id}`, "DELETE", { force: true })).status, 400);
  } finally { await stopServer(running); }
});

test("feedback mutations refuse symlinked and hard-linked state without writing outside the session", async () => {
  const running = await startServer(makeProject());
  const outside = makeProject();
  const protectedFile = path.join(outside, "protected.json");
  fs.writeFileSync(protectedFile, "untouched", { mode: 0o600 });
  try {
    const screen = await previewScreen(running);
    const stateFile = path.join(running.info.state_dir, "comments.json");
    const saved = fs.readFileSync(stateFile);
    for (const link of ["symbolic", "hard"]) {
      fs.unlinkSync(stateFile);
      if (link === "symbolic") fs.symlinkSync(protectedFile, stateFile);
      else fs.linkSync(protectedFile, stateFile);
      assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", commentFor(screen))).status, 500);
      assert.equal(fs.readFileSync(protectedFile, "utf8"), "untouched");
      fs.unlinkSync(stateFile);
      fs.writeFileSync(stateFile, saved, { mode: 0o600 });
    }
    const result = await feedbackRequest(running.info.url, "/comments", "POST", commentFor(screen));
    assert.equal(result.status, 200);
    assert.equal((await result.json()).comments.length, 1);
    assert.equal(fs.readdirSync(running.info.state_dir).some((name) => name.endsWith(".tmp")), false);
  } finally { await stopServer(running); }
});

test("feedback count is capped and concurrent requests do not lose accepted comments", async () => {
  const running = await startServer(makeProject());
  try {
    const screen = await previewScreen(running);
    for (let start = 0; start < 200; start += 20) {
      const replies = await Promise.all(Array.from({ length: 20 }, (_, offset) => feedbackRequest(running.info.url, "/comments", "POST", commentFor(screen, { text: `Comment ${start + offset}` }))));
      assert.equal(replies.every((reply) => reply.status === 200), true);
    }
    assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", commentFor(screen))).status, 429);
    const snapshot = await (await feedbackRequest(running.info.url, "/comments")).json();
    assert.equal(snapshot.comments.length, 200);
    assert.equal(new Set(snapshot.comments.map((item) => item.id)).size, 200);
    assert.ok(fs.statSync(path.join(running.info.state_dir, "comments.json")).size < 2 * 1024 * 1024);
  } finally { await stopServer(running); }
});

test("feedback CLI waits for a submitted batch, bounds its wait, and resolves through the server", async () => {
  const running = await startServer(makeProject());
  try {
    const screen = await previewScreen(running);
    const stateArgs = ["--state-dir", running.info.state_dir];
    const initial = await runComments(["list", ...stateArgs]);
    assert.equal(initial.code, 0, initial.stderr);
    assert.equal(JSON.parse(initial.stdout).submission, 0);
    const timedOut = await runComments(["wait", ...stateArgs, "--after", "0", "--timeout", "0"]);
    assert.equal(timedOut.code, 0, timedOut.stderr);
    assert.equal(JSON.parse(timedOut.stdout).type, "feedback-timeout");
    assert.equal((await runComments(["wait", ...stateArgs, "--timeout", "61"])).code, 2);
    assert.equal((await runComments(["wait", ...stateArgs, "--after", "-1"])).code, 2);
    const waiting = runComments(["wait", ...stateArgs, "--after", "0", "--timeout", "4"]);
    await new Promise((resolve) => setTimeout(resolve, 150));
    const lease = await (await feedbackRequest(running.info.url, "/comments")).json();
    assert.ok(lease.listeningUntil > Date.now());
    const created = await (await feedbackRequest(running.info.url, "/comments", "POST", commentFor(screen))).json();
    await feedbackRequest(running.info.url, "/comments/submit", "POST", { screen });
    const batch = await waiting;
    assert.equal(batch.code, 0, batch.stderr);
    assert.equal(JSON.parse(batch.stdout).type, "feedback-submission");
    assert.equal(JSON.parse(batch.stdout).comments[0].submission, 1);
    const id = created.comments[0].id;
    const resolved = await runComments(["resolve", ...stateArgs, "--id", id, "--reply", "Adjusted and checked."]);
    assert.equal(resolved.code, 0, resolved.stderr);
    assert.equal(JSON.parse(resolved.stdout).comments[0].status, "fixed");
    assert.equal(JSON.parse(resolved.stdout).comments[0].reply, "Adjusted and checked.");
    const reopened = await runComments(["reopen", ...stateArgs, "--id", id]);
    assert.equal(JSON.parse(reopened.stdout).comments[0].status, "open");
    const deleted = await runComments(["delete", ...stateArgs, "--id", id]);
    assert.equal(JSON.parse(deleted.stdout).comments.length, 0);
    const token = new URL(running.info.url).searchParams.get("token");
    for (const result of [initial, timedOut, batch, resolved, reopened, deleted]) assert.equal(`${result.stdout}${result.stderr}`.includes(token), false);
  } finally { await stopServer(running); }
});

test("the fixed shell validates feedback messages and defers refresh while a note is busy", async () => {
  const running = await startServer(makeProject());
  try {
    const screen = await previewScreen(running);
    const html = await (await fetch(running.info.url)).text();
    const script = html.match(/<script nonce="[^"]+">([\s\S]*?)<\/script>/)[1];
    const vm = require("node:vm");
    const callbacks = [], intervals = [], requests = [], messages = [];
    const frameWindow = { postMessage: (value) => messages.push(value) };
    const frame = { contentWindow: frameWindow, src: "unchanged" };
    const status = { textContent: "", classList: { remove() {}, add() {} } };
    const newer = "f".repeat(32);
    const newest = "e".repeat(32);
    let pollVersion = newer;
    vm.runInNewContext(script, {
      document: { getElementById: (id) => id === "vc-preview" ? frame : status },
      window: { location: { origin: new URL(running.info.url).origin }, addEventListener: (_, callback) => callbacks.push(callback) },
      setInterval: (callback) => intervals.push(callback), setTimeout: (callback) => callback(),
      URL, TextEncoder, Date,
      fetch: async (url, options) => { requests.push({ url: String(url), options }); return { ok: true, text: async () => pollVersion, json: async () => ({ revision: 1, submission: 0, screens: [{ screen, filename: "test.html" }, { screen: newer, filename: "test.html" }, { screen: newest, filename: "test.html" }], comments: [], listeningUntil: 0 }) }; },
    });
    const send = (data, source = frameWindow) => callbacks.forEach((callback) => callback({ data, source }));
    const base = { channel: "grillmester-visual-companion", version: 1 };
    send({ ...base, action: "comment-create", requestId: 1, payload: { ...commentFor(screen), html: "hidden" } });
    send({ ...base, action: "comment-create", requestId: 1, payload: commentFor(screen) }, {});
    assert.equal(requests.length, 0);
    send({ ...base, action: "comment-create", requestId: 1, payload: commentFor(screen) });
    await new Promise(setImmediate);
    assert.equal(requests.length, 1);
    assert.equal(new URL(requests[0].url).pathname, "/comments");
    assert.equal(messages.at(-1).command, "comments-result");
    // The iframe loaded a newer version than the parent shell was rendered for.
    send({ ...base, action: "feedback-ready", screen: newer });
    send({ ...base, action: "feedback-busy", screen: newer, busy: true });
    await new Promise(setImmediate);
    intervals[0]();
    await new Promise(setImmediate);
    assert.equal(frame.src, "unchanged");
    assert.equal(messages.some((message) => message.command === "update-available"), false);
    pollVersion = newest;
    intervals[0]();
    await new Promise(setImmediate);
    assert.equal(frame.src, "unchanged");
    assert.ok(messages.some((message) => message.command === "update-available"));
    send({ ...base, action: "refresh-now", screen: newer });
    assert.match(frame.src, /v=eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee/);
    frame.src = "newer-frame-loaded";
    send({ ...base, action: "feedback-ready", screen: newest });
    send({ ...base, action: "feedback-busy", screen: newest, busy: true });
    await new Promise(setImmediate);
    intervals[0]();
    await new Promise(setImmediate);
    assert.equal(frame.src, "newer-frame-loaded");
  } finally { await stopServer(running); }
});

test("feedback refuses a state-directory swap during temporary open before writing bytes", () => {
  const { FeedbackStore } = require("../scripts/feedback-store.js");
  const root = fs.realpathSync(makeProject());
  const state = path.join(root, "state");
  const moved = path.join(root, "original-state");
  const outside = path.join(root, "outside");
  fs.mkdirSync(state, { mode: 0o700 });
  fs.mkdirSync(outside, { mode: 0o700 });
  const outsideFile = path.join(outside, "comments.json");
  fs.writeFileSync(outsideFile, "protected", { mode: 0o600 });
  const store = new FeedbackStore(state);
  const before = store.snapshot();
  const originalOpen = fs.openSync;
  let swapped = false;
  fs.openSync = function (filename, ...args) {
    if (!swapped && String(filename).startsWith(path.join(state, ".comments-"))) {
      swapped = true;
      fs.renameSync(state, moved);
      fs.symlinkSync(outside, state);
    }
    return originalOpen.call(fs, filename, ...args);
  };
  try {
    assert.throws(() => store.knowScreen("a".repeat(32), "private-prototype.html"), /unsafe feedback state directory/i);
  } finally { fs.openSync = originalOpen; }
  assert.equal(swapped, true);
  assert.deepEqual(store.snapshot(), before);
  assert.equal(fs.readFileSync(outsideFile, "utf8"), "protected");
  for (const filename of fs.readdirSync(outside).filter((name) => name !== "comments.json")) {
    assert.equal(fs.statSync(path.join(outside, filename)).size, 0, "refused open must not write feedback into the replacement directory");
  }
  fs.unlinkSync(state);
  fs.renameSync(moved, state);
  store.knowScreen("b".repeat(32), "safe-prototype.html");
  assert.equal(store.snapshot().screens.length, 1);
});

test("feedback CLI malformed private state errors never echo file contents", async () => {
  const root = fs.realpathSync(makeProject());
  fs.chmodSync(root, 0o700);
  const marker = "private-credential-do-not-print";
  fs.writeFileSync(path.join(root, "server-info.json"), `{"url":"${marker}`, { mode: 0o600 });
  const result = await runComments(["list", "--state-dir", root]);
  assert.equal(result.code, 2);
  assert.match(result.stderr, /invalid private preview state json/i);
  assert.equal(`${result.stdout}${result.stderr}`.includes(marker), false);
});

test("a batch can submit pending notes from both current and previous screen versions", async () => {
  const running = await startServer(makeProject());
  try {
    const first = await previewScreen(running, "<h1>First version</h1>");
    await feedbackRequest(running.info.url, "/comments", "POST", commentFor(first));
    const second = await previewScreen(running, "<h1>Second version</h1>");
    await feedbackRequest(running.info.url, "/comments", "POST", commentFor(second));
    const response = await feedbackRequest(running.info.url, "/comments/submit", "POST", {});
    assert.equal(response.status, 200);
    const snapshot = await response.json();
    assert.deepEqual(snapshot.comments.map((item) => item.submission), [1, 1]);
    assert.equal(snapshot.comments.some((item) => item.screen === first), true);
    assert.equal(snapshot.comments.some((item) => item.screen === second), true);
    assert.equal((await feedbackRequest(running.info.url, "/comments/submit", "POST", { all: true })).status, 400);
  } finally { await stopServer(running); }
});
