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
        '<style id="balanced-style" nonce="untrusted" NONCE="duplicate">.safe-marker { color: inherit; }</style>' +
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
    const styleNonce = /style-src-elem 'nonce-([^']+)'/.exec(response.headers.get("content-security-policy"))[1];
    assert(preview.includes(`<style nonce="${styleNonce}" id="balanced-style">`));
    assert.equal(preview.includes('nonce="untrusted"'), false);
    assert.equal(preview.includes('NONCE="duplicate"'), false);
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

function sampleDesign() {
  return {
    version: 1,
    variants: [{ key: "compact", label: "Compact" }, { key: "spacious", label: "Spacious" }],
    targets: [
      { key: "header", variant: "", label: "Header", controls: [
        { id: "density", label: "Density", type: "range", initial: "comfortable", options: [{ value: "compact", label: "Compact" }, { value: "comfortable", label: "Comfortable" }, { value: "spacious", label: "Spacious" }] },
        { id: "description", label: "Description", type: "toggle", initial: "shown", options: [{ value: "shown", label: "Shown" }, { value: "hidden", label: "Hidden" }] },
      ] },
      { key: "card", variant: "compact", label: "Card", controls: [
        { id: "emphasis", label: "Emphasis", type: "select", initial: "quiet", options: [{ value: "quiet", label: "Quiet" }, { value: "strong", label: "Strong" }] },
      ] },
      { key: "card", variant: "spacious", label: "Card", controls: [] },
    ],
  };
}
function clone(value) { return JSON.parse(JSON.stringify(value)); }
async function workshopScreen(running, design = sampleDesign(), html = '<h1 data-vc-key="header">Design workshop</h1>') {
  fs.writeFileSync(path.join(running.info.screen_dir, "test.design.json"), JSON.stringify(design));
  return previewScreen(running, html);
}
function keepFor(screen, overrides = {}) {
  return { screen, variant: "", target: "header", values: { density: "compact" }, text: "Keep this spacing.", ...overrides };
}

test("design declarations accept only bounded finite options and closed structural metadata", () => {
  const { validDesign, MAX_DESIGN_BYTES } = require("../scripts/design-contract.js");
  const design = sampleDesign();
  assert.equal(validDesign(design), true);
  assert.equal(MAX_DESIGN_BYTES, 32768);
  assert.equal(validDesign({ version: 1, variants: [], targets: [] }), true);
  const mutations = [
    (d) => { d.css = "body { color:red }"; },
    (d) => { d.version = 2; },
    (d) => { d.variants.pop(); },
    (d) => { d.variants[1].key = d.variants[0].key; },
    (d) => { d.variants[0].selector = "#private"; },
    (d) => { d.variants[0].label = "ø".repeat(61); },
    (d) => { d.variants[0].key = "#compact"; },
    (d) => { d.variants[0].label = "line\nbreak"; },
    (d) => { d.targets[0].variant = "unknown"; },
    (d) => { d.targets[0].key = "customer[name]"; },
    (d) => { d.targets.push(clone(d.targets[0])); },
    (d) => { d.targets = Array.from({ length: 25 }, (_, index) => ({ ...clone(d.targets[0]), key: `target-${index}` })); },
    (d) => { d.targets[0].controls.push(clone(d.targets[0].controls[0])); },
    (d) => { d.targets[0].controls[0].initial = "not-declared"; },
    (d) => { d.targets[0].controls[0].type = "css"; },
    (d) => { d.targets[0].controls[0].min = 0; },
    (d) => { d.targets[0].controls[0].initial = 1; },
    (d) => { d.targets[0].controls[0].options[0].value = "12px"; },
    (d) => { d.targets[0].controls[0].options[0].css = "padding:2rem"; },
    (d) => { d.targets[0].controls[0].options[1].value = "compact"; },
    (d) => { d.targets[0].controls[0].options = []; },
    (d) => { d.targets[0].controls[0].options = Array.from({ length: 9 }, (_, index) => ({ value: `choice-${index}`, label: "Choice" })); },
    (d) => { d.targets[0].controls[1].options.push({ value: "sometimes", label: "Sometimes" }); },
  ];
  for (const mutate of mutations) { const invalid = clone(design); mutate(invalid); assert.equal(validDesign(invalid), false, JSON.stringify(invalid)); }
  for (const invalid of [null, [], {}, { version: 1, variants: null, targets: [] }]) assert.equal(validDesign(invalid), false);
});

test("a design sidecar is optional, changes screen identity, and safely disables invalid controls", async () => {
  const crypto = require("node:crypto");
  const running = await startServer(makeProject());
  try {
    const html = '<h1 data-vc-key="header">A stable prototype</h1>';
    const original = await previewScreen(running, html);
    assert.equal(original, crypto.createHash("sha256").update("test.html").update("\0").update(html).digest("hex").slice(0, 32));
    const designed = await workshopScreen(running, sampleDesign(), html);
    assert.notEqual(designed, original);
    let snapshot = await (await feedbackRequest(running.info.url, "/comments")).json();
    assert.deepEqual(snapshot.screens.find((item) => item.screen === designed).design, sampleDesign());
    assert.equal(Object.hasOwn(snapshot.screens.find((item) => item.screen === original), "design"), false);
    const preview = await (await fetch(endpoint(running.info.url, "/preview"))).text();
    assert.match(preview, /window\.__grillmesterVisualCompanionDesign=\{"version":1/);
    const changed = sampleDesign(); changed.targets[0].controls[0].initial = "spacious";
    const edited = await workshopScreen(running, changed, html);
    assert.notEqual(edited, designed);
    const file = path.join(running.info.screen_dir, "test.design.json");
    fs.writeFileSync(file, '{"private-invalid-metadata":');
    const invalid = await (await fetch(endpoint(running.info.url, "/preview"))).text();
    assert.match(invalid, /Justeringspanelet er utilgjengelig/);
    assert.match(invalid, /window\.__grillmesterVisualCompanionDesign=null;/);
    assert.equal(invalid.includes("private-invalid-metadata"), false);
    assert.match(invalid, /A stable prototype/);
    const invalidScreen = await (await fetch(endpoint(running.info.url, "/version"))).text();
    assert.equal((await feedbackRequest(running.info.url, "/decisions", "POST", keepFor(invalidScreen))).status, 409);
    fs.writeFileSync(file, " ".repeat(32769));
    const oversized = await (await fetch(endpoint(running.info.url, "/preview"))).text();
    assert.match(oversized, /window\.__grillmesterVisualCompanionDesign=null;/);
    fs.unlinkSync(file);
    const outside = path.join(makeProject(), "outside-design.json");
    fs.writeFileSync(outside, JSON.stringify(sampleDesign()));
    fs.symlinkSync(outside, file);
    const linked = await (await fetch(endpoint(running.info.url, "/preview"))).text();
    assert.match(linked, /window\.__grillmesterVisualCompanionDesign=null;/);
    fs.unlinkSync(file);
    assert.equal(await (await fetch(endpoint(running.info.url, "/version"))).text(), original);
  } finally { await stopServer(running); }
});

test("structured adjustment and preference feedback is validated against its own screen declaration", async () => {
  const running = await startServer(makeProject());
  try {
    const screen = await workshopScreen(running);
    const adjustment = commentFor(screen, { kind: "adjustment", text: "", adjustment: { variant: "", target: "header", values: { density: "spacious", description: "hidden" } } });
    assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", adjustment)).status, 200);
    assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", commentFor(screen, { kind: "variant", text: "", variant: "compact" }))).status, 200);
    const invalid = [
      { ...adjustment, adjustment: { ...adjustment.adjustment, values: {} } },
      { ...adjustment, adjustment: { ...adjustment.adjustment, values: { color: "red" } } },
      { ...adjustment, adjustment: { ...adjustment.adjustment, values: { density: "100px" } } },
      { ...adjustment, adjustment: { ...adjustment.adjustment, target: "unknown" } },
      { ...adjustment, adjustment: { ...adjustment.adjustment, variant: "compact" } },
      { ...adjustment, adjustment: { ...adjustment.adjustment, selector: "body" } },
      { ...adjustment, proposal: { property: "text", value: "extra" } },
      { ...adjustment, variant: "compact" },
      commentFor(screen, { kind: "variant", variant: "unknown" }),
      commentFor(screen, { kind: "variant", variant: "compact", adjustment: adjustment.adjustment }),
    ];
    for (const value of invalid) assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", value)).status, 400, JSON.stringify(value));
    const nextDesign = sampleDesign(); nextDesign.targets[0].controls[0].options.shift();
    const next = await workshopScreen(running, nextDesign);
    assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", { ...adjustment, screen: next, adjustment: { variant: "", target: "header", values: { density: "compact" } } })).status, 400);
    assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", { ...adjustment, adjustment: { variant: "", target: "header", values: { density: "compact" } } })).status, 200);
  } finally { await stopServer(running); }
});

test("kept decisions survive versions, retain active IDs, and batch explicit releases", async () => {
  const running = await startServer(makeProject());
  try {
    const screen = await workshopScreen(running);
    const kept = await feedbackRequest(running.info.url, "/decisions", "POST", keepFor(screen));
    assert.equal(kept.status, 200);
    const first = (await kept.json()).decisions[0];
    assert.match(first.id, /^[a-f0-9]{24}$/);
    assert.equal(first.state, "active");
    assert.equal(first.submission, 0);
    const draftWait = await runComments(["wait", "--state-dir", running.info.state_dir, "--after", "0", "--timeout", "0"]);
    assert.equal(draftWait.code, 0, draftWait.stderr);
    assert.deepEqual(JSON.parse(draftWait.stdout).decisions, [], "unsubmitted decisions must stay behind the explicit Send boundary");
    const firstBatch = await (await feedbackRequest(running.info.url, "/comments/submit", "POST", {})).json();
    assert.equal(firstBatch.submission, 1);
    assert.equal(firstBatch.decisions[0].submission, 1);
    const next = await workshopScreen(running, sampleDesign(), '<h1 data-vc-key="header">Next version</h1>');
    const maintained = await (await feedbackRequest(running.info.url, "/comments")).json();
    assert.equal(maintained.decisions[0].id, first.id);
    assert.equal(maintained.decisions[0].screen, screen, "new screens must not rewrite a kept decision without explicit input");
    const updated = await (await feedbackRequest(running.info.url, "/decisions", "POST", keepFor(next, { values: {}, text: "Keep the whole header." }))).json();
    assert.equal(updated.decisions.length, 1);
    assert.equal(updated.decisions[0].id, first.id);
    assert.equal(updated.decisions[0].screen, next);
    assert.equal(updated.decisions[0].submission, 0);
    assert.deepEqual(updated.decisions[0].values, {});
    const pendingUpdate = JSON.parse((await runComments(["wait", "--state-dir", running.info.state_dir, "--after", "1", "--timeout", "0"])).stdout);
    assert.equal(pendingUpdate.type, "feedback-timeout");
    assert.equal(pendingUpdate.decisions[0].screen, screen);
    assert.deepEqual(pendingUpdate.decisions[0].values, { density: "compact" }, "pending updates must preserve the last submitted constraint");
    assert.equal((await feedbackRequest(running.info.url, "/comments/submit", "POST", { screen })).status, 409);
    const secondBatch = await (await feedbackRequest(running.info.url, "/comments/submit", "POST", {})).json();
    assert.equal(secondBatch.submission, 2);
    await feedbackRequest(running.info.url, "/comments", "POST", commentFor(next));
    await feedbackRequest(running.info.url, "/comments/submit", "POST", {});
    const stateArgs = ["--state-dir", running.info.state_dir];
    const waited = await runComments(["wait", ...stateArgs, "--after", "2", "--timeout", "0"]);
    assert.equal(waited.code, 0, waited.stderr);
    const received = JSON.parse(waited.stdout);
    assert.equal(received.comments.length, 1);
    assert.equal(received.decisions[0].id, first.id, "older active holds must accompany later batches");
    const released = await runComments(["release", ...stateArgs, "--id", first.id]);
    assert.equal(released.code, 0, released.stderr);
    assert.equal(JSON.parse(released.stdout).decisions[0].state, "released");
    assert.equal(JSON.parse(released.stdout).decisions[0].submission, 0);
    const pendingRelease = JSON.parse((await runComments(["wait", ...stateArgs, "--after", "3", "--timeout", "0"])).stdout);
    assert.equal(pendingRelease.type, "feedback-timeout");
    assert.equal(pendingRelease.decisions[0].state, "active", "a pending release must not remove the submitted constraint");
    assert.deepEqual(pendingRelease.decisions[0].values, {});
    assert.equal((await feedbackRequest(running.info.url, `/decisions/${first.id}`, "PATCH", {})).status, 409);
    await feedbackRequest(running.info.url, "/comments/submit", "POST", {});
    const releaseBatch = JSON.parse((await runComments(["wait", ...stateArgs, "--after", "3", "--timeout", "0"])).stdout);
    assert.equal(releaseBatch.decisions[0].state, "released");
    assert.equal(releaseBatch.decisions[0].submission, 4);
    const timeout = JSON.parse((await runComments(["wait", ...stateArgs, "--after", "4", "--timeout", "0"])).stdout);
    assert.equal(timeout.decisions.length, 0);
    const token = new URL(running.info.url).searchParams.get("token");
    assert.equal(`${waited.stdout}${released.stdout}`.includes(token), false);
  } finally { await stopServer(running); }
});

test("design decisions reject undeclared controls, extra fields, wrong origins, and unbounded text", async () => {
  const running = await startServer(makeProject());
  try {
    const screen = await workshopScreen(running);
    const valid = keepFor(screen);
    const invalid = [
      { ...valid, values: { density: "arbitrary" } },
      { ...valid, values: { onclick: "run" } },
      { ...valid, values: [] },
      { ...valid, values: { density: 2 } },
      { ...valid, values: {}, target: "unknown" },
      { ...valid, selector: "#header" },
      { ...valid, state: "active" },
      { ...valid, text: "ø".repeat(1001) },
      { ...valid, variant: "compact" },
    ];
    for (const value of invalid) assert.equal((await feedbackRequest(running.info.url, "/decisions", "POST", value)).status, 400, JSON.stringify(value));
    const url = endpoint(running.info.url, "/decisions");
    assert.equal((await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(valid) })).status, 403);
    assert.equal((await fetch(url, { method: "POST", headers: { "Content-Type": "text/plain", Origin: url.origin }, body: JSON.stringify(valid) })).status, 415);
    const created = await (await feedbackRequest(running.info.url, "/decisions", "POST", valid)).json();
    const id = created.decisions[0].id;
    assert.equal((await feedbackRequest(running.info.url, `/decisions/${id}`, "PATCH", { state: "released" })).status, 400);
    assert.equal((await feedbackRequest(running.info.url, "/decisions/aaaaaaaaaaaaaaaaaaaaaaaa", "PATCH", {})).status, 404);
  } finally { await stopServer(running); }
});

test("decision history has its own fixed count limit", () => {
  const { FeedbackStore, MAX_DECISIONS } = require("../scripts/feedback-store.js");
  const root = fs.realpathSync(makeProject());
  fs.chmodSync(root, 0o700);
  const store = new FeedbackStore(root);
  const screen = "c".repeat(32);
  store.knowScreen(screen, "test.html", sampleDesign());
  for (let index = 0; index < MAX_DECISIONS; index += 1) {
    const snapshot = store.keep(keepFor(screen));
    store.release(snapshot.decisions.at(-1).id, {});
    store.submit({});
  }
  assert.equal(store.snapshot().decisions.length, 200);
  assert.throws(() => store.keep(keepFor(screen)), /Decision limit reached/);
});


test("re-keeping a pending release preserves one accepted hold during a scoped version submission", async () => {
  const running = await startServer(makeProject());
  try {
    const firstScreen = await workshopScreen(running);
    const kept = await (await feedbackRequest(running.info.url, "/decisions", "POST", keepFor(firstScreen))).json();
    const id = kept.decisions[0].id;
    await feedbackRequest(running.info.url, "/comments/submit", "POST", {});
    await feedbackRequest(running.info.url, `/decisions/${id}`, "PATCH", {});
    const nextScreen = await workshopScreen(running, sampleDesign(), '<h1 data-vc-key="header">Revised header</h1>');
    const renewed = await (await feedbackRequest(running.info.url, "/decisions", "POST", keepFor(nextScreen, { values: { density: "spacious" } }))).json();
    assert.equal(renewed.decisions.length, 1);
    assert.equal(renewed.decisions[0].id, id);
    assert.equal(renewed.decisions[0].state, "active");
    const submitted = await (await feedbackRequest(running.info.url, "/comments/submit", "POST", { screen: nextScreen })).json();
    assert.equal(submitted.submittedDecisions.filter((item) => item.state === "active").length, 1);
    assert.equal(submitted.submittedDecisions[0].id, id);
    assert.deepEqual(submitted.submittedDecisions[0].values, { density: "spacious" });
    assert.equal((await feedbackRequest(running.info.url, "/comments/submit", "POST", { screen: firstScreen })).status, 409);
  } finally { await stopServer(running); }
});
