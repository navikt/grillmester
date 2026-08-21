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

function startServer(projectDir, extraArgs = []) {
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
      { stdio: ["ignore", "pipe", "pipe"] },
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
  try {
    fs.writeFileSync(
      path.join(running.info.screen_dir, "unsafe.html"),
      '<h2>Konsept</h2><script>fetch("https://example.com/leak")</script><img src="https://example.com/pixel">',
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
    assert.doesNotMatch(preview, /fetch\("https:\/\/example\.com\/leak"\)/);
    assert.doesNotMatch(preview, /https:\/\/example\.com\/pixel/);
    assert.match(preview, /parent\.postMessage/);
    assert.match(preview, /ikke lagret — si valget i chatten/);
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
