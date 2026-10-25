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
    // A malformed "<script<script" is an unknown element in the browser, so its
    // body is inert text. No tag or attribute may reference the external host.
    assert.equal(new RegExp(`<[^>]*${forbiddenExternalHost.replace(".", "\\.")}`).test(preview), false);
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

test("preview keeps only strict same-document anchor fragments", async () => {
  const running = await startServer(makeProject());
  try {
    const allowed = ["#steps-fare", "#field.name:part_1", `#a${"b".repeat(127)}`];
    const rejected = ["#", "", "#%73teps-fare", "&#35;steps-fare", "#steps&#45;fare", "#field name", " #field", "#1field", `#a${"b".repeat(128)}`, "https://example.invalid/#field", "/#field", "javascript:alert(1)"];
    const content = allowed.map((href, index) => `<a id="allowed-${index}" href="${href}">Allowed</a>`).join("")
      + rejected.map((href, index) => `<a id="rejected-${index}" href="${href}">Blocked</a>`).join("")
      + '<area id="blocked-area" href="#steps-fare"><svg><use id="blocked-use" href="#steps-fare"></use></svg><input id="steps-fare">';
    await previewScreen(running, content);
    const response = await fetch(endpoint(running.info.url, "/preview"));
    const html = await response.text();
    for (let index = 0; index < allowed.length; index += 1) assert(html.includes(`<a id="allowed-${index}" href="${allowed[index]}">`));
    for (let index = 0; index < rejected.length; index += 1) assert(html.includes(`<a id="rejected-${index}">`), rejected[index]);
    assert(html.includes('<area id="blocked-area">'));
    assert(html.includes('<use id="blocked-use">'));
    const policy = response.headers.get("content-security-policy");
    assert.match(policy, /connect-src 'none'/);
    assert.match(policy, /form-action 'none'/);
    assert.match(policy, /navigate-to 'none'/);
  } finally { await stopServer(running); }
});

test("fragment focus rejects ambiguous, hidden, out-of-sketch, disabled, and busy targets", () => {
  const source = fs.readFileSync(path.resolve(__dirname, "../scripts/helper.js"), "utf8");
  const handler = source.match(/  function followLocalFragment\(link\) \{[\s\S]*?\n  \}/)?.[0];
  assert(handler, "The actual browser helper must expose its fragment handler to this isolated contract check.");
  let focused = 0, scrolled = 0, lookups = 0;
  const target = {
    inside: true, blocked: false, disabled: false, visible: true, visibility: "visible",
    getAttribute: name => name === "id" ? "field.name:part_1" : null,
    closest() { return this.blocked ? {} : null; },
    matches() { return this.disabled; },
    getClientRects() { return this.visible ? [{}] : []; },
    scrollIntoView: () => { scrolled += 1; },
  };
  const ids = [target];
  const link = {
    localName: "a", href: "#field.name:part_1", blocked: false, disabled: false,
    getAttribute(name) { return name === "href" ? this.href : null; },
    hasAttribute() { return this.disabled; }, closest() { return this.blocked ? {} : null; },
  };
  const context = {
    mode: "browse", draft: null, preview: null, busy: false,
    saving: () => context.busy,
    document: {
      getElementById(id) { lookups += 1; assert.equal(id, "field.name:part_1"); return target; },
      body: { querySelector(selector) { assert.equal(selector, ":scope > .vc-content"); return { contains: item => item === target && target.inside }; } },
      querySelectorAll(selector) { assert.equal(selector, "[id]", "Fragments must never become CSS selectors."); return ids; },
    },
    getComputedStyle: item => ({ visibility: item.visibility }),
    focusPrototype: item => { assert.equal(item, target); focused += 1; },
  };
  require("node:vm").runInNewContext(handler, context);
  assert.equal(context.followLocalFragment(link), true);
  assert.equal(focused, 1); assert.equal(scrolled, 1);
  ids.push({ getAttribute: () => "field.name:part_1" });
  assert.equal(context.followLocalFragment(link), false, "Duplicate targets cannot be chosen by document order.");
  ids.pop();
  for (const [property, value] of [["inside", false], ["blocked", true], ["disabled", true], ["visible", false], ["visibility", "hidden"]]) {
    const previous = target[property]; target[property] = value;
    assert.equal(context.followLocalFragment(link), false, property); target[property] = previous;
  }
  const previousLookups = lookups;
  for (const href of ["", "#", "#%66ield.name:part_1", "https://example.invalid/#field.name:part_1", "#field name"])
    { link.href = href; assert.equal(context.followLocalFragment(link), false); }
  link.href = "#field.name:part_1";
  for (const [object, property, value] of [[context, "mode", "comment"], [context, "draft", {}], [context, "preview", {}], [context, "busy", true], [link, "blocked", true], [link, "disabled", true], [link, "localName", "area"]]) {
    const previous = object[property]; object[property] = value;
    assert.equal(context.followLocalFragment(link), false, property); object[property] = previous;
  }
  assert.equal(lookups, previousLookups, "Invalid links and busy states must not resolve a target.");
  assert.equal(focused, 1); assert.equal(scrolled, 1);
});

test("raw-text elements inside SVG and MathML are sanitized as markup", async () => {
  const projectDir = makeProject();
  const running = await startServer(projectDir);
  try {
    fs.writeFileSync(
      path.join(running.info.screen_dir, "foreign.html"),
      '<svg><style><p></p><textarea id="swallow"></style></svg>' +
        '<svg><title>Graf<meta http-equiv="refresh" content="0;url=https://example.invalid/"><iframe src="https://example.invalid/"></iframe></title></svg>' +
        '<math><mi><style><img src="https://example.invalid/x.png"></style></mi></math>' +
        '<svg role="img"><title id="kept-title">Søknader per måned</title></svg>',
    );
    const preview = await (await fetch(endpoint(running.info.url, "/preview"))).text();
    assert.equal(preview.includes('id="swallow"'), false);
    assert.equal(/<meta http-equiv/i.test(preview), false);
    assert.equal(preview.includes("<iframe"), false);
    assert.equal(preview.includes("https://example.invalid"), false);
    assert.match(preview, /<title id="kept-title">Søknader per måned<\/title>/);
  } finally {
    await stopServer(running);
  }
});

test("foreign content stays sanitized after nested, misleading or ignored SVG end markup", async () => {
  const projectDir = makeProject();
  const running = await startServer(projectDir);
  try {
    // Each case leaves Chrome inside SVG, where a raw-text-looking element is
    // markup and a breakout textarea/xmp would swallow the trusted helper.
    fs.writeFileSync(
      path.join(running.info.screen_dir, "foreign-tricks.html"),
      '<svg><style><g><textarea><p></p><xmp id="nested"></textarea></g></style></svg>' +
        '<svg></math><style><p></p><textarea id="math-end"></style></svg>' +
        '<svg x=/><style><p></p><textarea id="unquoted-slash"></style></svg>' +
        '<svg><foreignObject><div></svg></div></foreignObject><style><p></p><textarea id="ignored-end"></style></svg>' +
        '<svg viewBox="0 0 1 1"><path d="M0 0h1v1z"/></svg><style>.chart > rect { fill: currentColor; }</style>' +
        '<textarea id="kept-text">a > b</textarea>',
    );
    const preview = await (await fetch(endpoint(running.info.url, "/preview"))).text();
    for (const id of ["nested", "math-end", "unquoted-slash", "ignored-end"]) assert.equal(preview.includes(`id="${id}"`), false, id);
    assert.match(preview, /<style nonce="[^"]+">\.chart > rect \{ fill: currentColor; \}<\/style>/);
    assert.match(preview, /<textarea id="kept-text">a > b<\/textarea>/);
  } finally {
    await stopServer(running);
  }
});

test("tag scanning follows the browser tokenizer for quotes, end tags and comments", () => {
  const source = fs.readFileSync(path.resolve(__dirname, "../scripts/server.js"), "utf8");
  const start = source.indexOf("const FORBIDDEN_PREVIEW_ELEMENTS"), end = source.indexOf("function readDesign(", start);
  assert(start >= 0 && end > start, "The sanitizer must stay in one contiguous, isolated block.");
  const strip = require("node:vm").runInNewContext(`${source.slice(start, end)}; stripActivePreviewMarkup`, { Buffer, MAX_INLINE_IMAGE_URL_BYTES: 64 * 1024 });
  for (const [input, expected] of [
    // Only tab, newline, form feed, carriage return, space, "/" or ">" end raw text.
    ["<style>.a{}</style\u000b><p>x</p>", ".a{}<p>x</p>"],
    ["<style>.a{}</ style><p>x</p>", ".a{}<p>x</p>"],
    ["<title>x</ title><p>y</p>", "x<p>y</p>"],
    // Raw text ends at the first matching end tag, even inside apparent quotes.
    ['<style>a<b title="</style><textarea>">c</style><p>x</p>', '<style nonce="N">a<b title="</style>">c</style><p>x</p>'],
    // Quotes delimit attribute values only; end tags are written without attributes.
    ["<style>x</style a'b><textarea><p>y</p>", '<style nonce="N">x</style><p>y</p>'],
    ["<p>z</p a'b><textarea><p>y</p>", "<p>z</p><p>y</p>"],
    ["<p a'b class=ok>t</p>", '<p class="ok">t</p>'],
    // Every comment ending is recognized, and comments are dropped.
    ["<!--><textarea>-->", "-->"],
    ["<!-- x --!><textarea> -->", " -->"],
    // A tag cut off by the end of the fragment is not closed here.
    ['<p title="abc', ""],
    // A slash in an unquoted value does not self-close a foreign element.
    ["<svg x=/><style><p></p><textarea></style></svg>", '<svg x="/"><style nonce="N"><p></p></style></svg>'],
    // Legitimate CSS and text survive unchanged.
    ['<style>@media (width < 600px) { .a { content: "it\'s"; } }</style>', '<style nonce="N">@media (width < 600px) { .a { content: "it\'s"; } }</style>'],
    ["<textarea>if a < b then 1 / 2</textarea>", "<textarea>if a < b then 1 / 2</textarea>"],
    ['<img src="https://example.invalid/a.png" src="data:image/png;base64,iVBORw0KGgo=">', "<img>"],
  ]) assert.equal(strip(input, "N"), expected, JSON.stringify(input));
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
    assert.equal(preview.includes("balanced-comment"), false, "Comments are dropped instead of copied.");
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
    // The trusted helpers load in <head>, before the sketch, so no sketch markup
    // can consume them; they start once the document is parsed.
    assert.ok(helperStart >= 0 && helperStart < preview.indexOf('<main class="vc-content'));
    assert.ok(preview.indexOf("noframes-marker") > preview.indexOf('<main class="vc-content'));
    assert.match(preview.slice(helperStart, preview.indexOf("</head>")), /parent\.postMessage/);
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

test("style subproject CLI selectors reject absolute, traversal and ambiguous paths before startup", async () => {
  const projectDir = makeProject();
  for (const selected of ["/tmp/app", "../app", "apps/../app", "./app", "apps//app", "apps\\app", "apps/.hidden", "apps/node_modules"]) {
    const result = await runCli(projectDir, ["--style-project-path", selected]);
    assert.equal(result.code, 2);
    assert.match(result.stderr, /bounded project-relative directory/);
    assert.equal(result.stdout, "");
  }
  assert.deepEqual(fs.readdirSync(projectDir), []);
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
async function feedbackRequest(url, pathname, method = "GET", body, headers = {}) {
  return fetch(endpoint(url, pathname), {
    method,
    headers: { Origin: new URL(url).origin, ...(method === "GET" ? {} : { "Content-Type": "application/json" }), ...headers },
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

test("feedback retry receipts commit once, preserve newer state, and reject changed intent", async () => {
  const running = await startServer(makeProject());
  try {
    const screen = await previewScreen(running);
    const value = commentFor(screen);
    const headers = { "X-Feedback-Mutation": "a".repeat(32) };
    const replies = await Promise.all(Array.from({ length: 4 }, () => feedbackRequest(running.info.url, "/comments", "POST", value, headers)));
    assert(replies.every((response) => response.status === 200));
    const snapshots = await Promise.all(replies.map((response) => response.json()));
    assert(snapshots.every((snapshot) => snapshot.comments.length === 1 && snapshot.revision === snapshots[0].revision));
    const id = snapshots[0].comments[0].id;
    const reordered = { text: value.text, anchor: { viewport: value.anchor.viewport, rect: value.anchor.rect, role: value.anchor.role, path: value.anchor.path }, kind: value.kind, screen };
    assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", reordered, headers)).status, 200);
    assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", { ...value, text: "A different intent." }, headers)).status, 409);
    assert.equal((await feedbackRequest(running.info.url, `/comments/${id}`, "PATCH", { status: "fixed" }, headers)).status, 409);
    assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", value, { "X-Feedback-Mutation": "invalid" })).status, 400);
    const beforeSubmit = await (await feedbackRequest(running.info.url, "/comments")).json();
    const submitHeaders = { "X-Feedback-Mutation": "b".repeat(32) };
    assert.equal((await feedbackRequest(running.info.url, "/comments/submit", "POST", { revision: beforeSubmit.revision }, submitHeaders)).status, 200);
    const deleted = await (await feedbackRequest(running.info.url, `/comments/${id}`, "DELETE", {}, { "X-Feedback-Mutation": "c".repeat(32) })).json();
    const replay = await (await feedbackRequest(running.info.url, "/comments", "POST", value, headers)).json();
    assert.deepEqual(replay, deleted, "Replaying a committed create must not resurrect deleted feedback or return an old snapshot.");
    const resubmitted = await (await feedbackRequest(running.info.url, "/comments/submit", "POST", { revision: beforeSubmit.revision }, submitHeaders)).json();
    assert.deepEqual(resubmitted, deleted, "A submit retry must succeed without creating another batch, despite its old revision.");
    assert.equal(JSON.stringify(replay).includes(headers["X-Feedback-Mutation"]), false);
    assert.equal(fs.readFileSync(path.join(running.info.state_dir, "comments.json"), "utf8").includes(headers["X-Feedback-Mutation"]), false);
    assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", value)).status, 200, "Legacy clients without a retry identifier remain supported.");
  } finally { await stopServer(running); }
});

test("feedback receipt capacity fails closed without evicting old retries or recording failed commits", () => {
  const { FeedbackMutationReceipts, FeedbackError } = require("../scripts/feedback-store.js");
  const receipts = new FeedbackMutationReceipts(2);
  let writes = 0;
  const operation = () => { writes += 1; };
  const a = "a".repeat(32), b = "b".repeat(32), c = "c".repeat(32);
  assert.throws(() => receipts.run(a, "POST", "/comments", {}, () => { throw new Error("commit failed"); }), /commit failed/);
  receipts.run(a, "POST", "/comments", {}, operation);
  receipts.run(b, "PATCH", "/comments/1", {}, operation);
  assert.equal(writes, 2);
  assert.throws(() => receipts.run(c, "POST", "/comments", {}, operation), (error) => error instanceof FeedbackError && error.status === 429);
  receipts.run(a, "POST", "/comments", {}, operation);
  assert.equal(writes, 2, "The oldest accepted retry still resolves without another write.");
  assert.throws(() => receipts.run(a, "POST", "/decisions", {}, operation), (error) => error.status === 409);
  assert.throws(() => receipts.run(b, "DELETE", "/comments/1", {}, operation), (error) => error.status === 409);
  assert.equal(writes, 2);
});

function privateFeedbackStore() {
  const { FeedbackStore } = require("../scripts/feedback-store.js");
  const directory = fs.realpathSync(makeProject());
  fs.chmodSync(directory, 0o700);
  return new FeedbackStore(directory);
}

test("submission history keeps both original rounds after resubmission, replies and deletion", () => {
  const store = privateFeedbackStore();
  const screen = "a".repeat(32);
  store.knowScreen(screen, "original.html", sampleDesign());
  const context = { variant: "", target: "header", values: { density: "compact" } };
  const created = store.create(commentFor(screen, { kind: "edit", text: "Clarify this heading.", proposal: { property: "text", value: "Prepare for the meeting" }, context }));
  const id = created.comments[0].id;
  assert.equal(created.comments[0].lastSubmission, 0);
  const first = store.submit({ revision: created.revision });
  const original = clone(first.comments[0]);
  assert.equal(original.lastSubmission, 1);
  store.patch(id, { status: "fixed", reply: "The wording is clearer.", expectedSubmission: 1 });
  let delivered = store.nextSubmission(0);
  assert.deepEqual(delivered.comments, [original]);
  assert.equal(delivered.currentComments[0].status, "fixed");
  assert.equal(delivered.currentComments[0].reply, "The wording is clearer.");
  const pending = store.patch(id, { status: "open", resubmit: true });
  assert.equal(pending.comments[0].submission, 0);
  assert.equal(pending.comments[0].lastSubmission, 1);
  assert.deepEqual(store.nextSubmission(0).comments, [original], "An unsent reopening must not erase the first round.");
  const second = store.submit({});
  const secondOriginal = clone(second.comments[0]);
  store.delete(id, {});
  delivered = store.nextSubmission(0);
  assert.equal(delivered.revision, first.revision);
  assert.equal(delivered.submission, 1);
  assert.equal(delivered.latestSubmission, 2);
  assert.equal(delivered.hasMore, true);
  assert.equal(Number.isNaN(Date.parse(delivered.submittedAt)), false);
  assert.deepEqual(delivered.comments, [original]);
  assert.deepEqual(delivered.currentComments, [{ id, present: false }]);
  delivered.comments[0].context.values.density = "spacious";
  delivered.screens[0].filename = "changed.html";
  assert.deepEqual(store.nextSubmission(0).comments, [original], "Returned nested data cannot mutate the journal.");
  assert.equal(store.nextSubmission(0).screens[0].filename, "original.html");
  assert.deepEqual(store.nextSubmission(1).comments, [secondOriginal]);
  assert.equal(store.nextSubmission(1).hasMore, false);
  assert.deepEqual(store.nextSubmission(2).comments, []);
  assert.equal(store.nextSubmission(2).submittedAt, null);
  assert.deepEqual(store.snapshot().comments, []);
  assert.equal(Object.hasOwn(store.snapshot(), "submissions"), false, "Ordinary browser snapshots must not include the delivery journal.");
  const saved = JSON.parse(fs.readFileSync(store.filename, "utf8"));
  assert.deepEqual(saved.submissions.map((batch) => batch.comments[0]), [original, secondOriginal]);
});

test("submission history reconstructs constraints at each cursor and preserves scoped screens", () => {
  const store = privateFeedbackStore();
  const firstScreen = "a".repeat(32), secondScreen = "b".repeat(32), unrelatedScreen = "c".repeat(32);
  for (const [screen, filename] of [[firstScreen, "first.html"], [secondScreen, "second.html"], [unrelatedScreen, "unrelated.html"]]) store.knowScreen(screen, filename, sampleDesign());
  store.create(commentFor(firstScreen));
  store.create(commentFor(secondScreen, { text: "This belongs to the second version." }));
  const keep = store.keep(keepFor(firstScreen));
  const decisionId = keep.decisions[0].id;
  store.submit({ screen: firstScreen });
  store.keep(keepFor(secondScreen, { values: { density: "spacious" } }));
  store.submit({ screen: secondScreen });
  store.release(decisionId, {});
  store.submit({});
  store.keep(keepFor(unrelatedScreen));
  const first = store.nextSubmission(0), second = store.nextSubmission(1), released = store.nextSubmission(2);
  assert.equal(first.comments.length, 1);
  assert.equal(first.comments[0].screen, firstScreen);
  assert.deepEqual(first.decisions[0].values, { density: "compact" });
  assert.deepEqual(first.screens.map((item) => item.screen), [firstScreen]);
  assert.equal(second.comments.length, 1);
  assert.equal(second.comments[0].screen, secondScreen);
  assert.deepEqual(second.decisions[0].values, { density: "spacious" });
  assert.deepEqual(second.screens.map((item) => item.screen), [secondScreen]);
  assert.deepEqual(released.comments, []);
  assert.equal(released.decisions[0].state, "released");
  assert.equal(released.decisions[0].submission, 3);
  assert.deepEqual(store.nextSubmission(3).decisions, [], "A newer unsent hold is not an accepted constraint.");
  for (const cursor of [-1, 0.5, "0", null, Number.MAX_SAFE_INTEGER + 1]) assert.throws(() => store.nextSubmission(cursor), (error) => error.status === 400);
  assert.throws(() => store.nextSubmission(4), (error) => error.status === 409);
});

test("submission guards prevent an old reply from resolving a pending or newer round", () => {
  const { validPatch } = require("../scripts/feedback-store.js");
  const store = privateFeedbackStore(), screen = "a".repeat(32);
  store.knowScreen(screen, "test.html");
  const id = store.create(commentFor(screen)).comments[0].id;
  store.submit({});
  store.patch(id, { status: "open", resubmit: true });
  const pending = store.snapshot();
  assert.throws(() => store.patch(id, { status: "fixed", expectedSubmission: 1 }), (error) => error.status === 409);
  assert.deepEqual(store.snapshot(), pending);
  store.submit({});
  const sent = store.snapshot();
  assert.throws(() => store.patch(id, { status: "fixed", reply: "Outdated reply", expectedSubmission: 1 }), (error) => error.status === 409);
  assert.deepEqual(store.snapshot(), sent);
  const resolved = store.patch(id, { status: "fixed", reply: "Current reply", expectedSubmission: 2 });
  assert.equal(resolved.comments[0].reply, "Current reply");
  assert.equal(Object.hasOwn(resolved.comments[0], "expectedSubmission"), false);
  assert.equal(store.patch(id, { status: "open" }).comments[0].status, "open", "Existing clients can still update current status.");
  for (const expectedSubmission of [-1, 1.5, "1", null, Number.MAX_SAFE_INTEGER + 1]) assert.equal(validPatch({ status: "fixed", expectedSubmission }), false);
  assert.equal(validPatch({ expectedSubmission: 2 }), false);
});

test("submission journal refuses its count limit without evicting earlier rounds", () => {
  const { MAX_SUBMISSIONS } = require("../scripts/feedback-store.js");
  const store = privateFeedbackStore(), screen = "a".repeat(32);
  store.knowScreen(screen, "test.html");
  const id = store.create(commentFor(screen)).comments[0].id;
  for (let count = 0; count < MAX_SUBMISSIONS; count += 1) {
    store.submit({});
    store.patch(id, { status: "open", resubmit: true });
  }
  const before = store.snapshot(), fileBefore = fs.readFileSync(store.filename, "utf8");
  assert.equal(MAX_SUBMISSIONS, 200);
  assert.throws(() => store.submit({}), (error) => error.status === 429 && /Submission limit/.test(error.message));
  assert.deepEqual(store.snapshot(), before);
  assert.equal(fs.readFileSync(store.filename, "utf8"), fileBefore);
  assert.equal(store.nextSubmission(0).submission, 1);
  assert.equal(store.nextSubmission(MAX_SUBMISSIONS - 1).submission, MAX_SUBMISSIONS);
});

test("submission journal size failure leaves the original round and pending feedback intact", () => {
  const { MAX_COMMENTS, MAX_STORE_BYTES } = require("../scripts/feedback-store.js");
  const store = privateFeedbackStore(), screen = "a".repeat(32);
  store.knowScreen(screen, "test.html");
  const large = store.create(commentFor(screen, { kind: "edit", text: "x".repeat(2000), proposal: { property: "text", value: "y".repeat(2000) } })).comments[0];
  // Build a valid, full live queue without hundreds of unrelated disk commits.
  store.change((state) => { state.comments = Array.from({ length: MAX_COMMENTS }, (_, index) => ({ ...clone(large), id: index.toString(16).padStart(24, "0") })); });
  store.submit({});
  store.change((state) => { for (const item of state.comments) item.submission = 0; });
  const before = store.snapshot(), fileBefore = fs.readFileSync(store.filename, "utf8");
  assert(Buffer.byteLength(fileBefore) < MAX_STORE_BYTES);
  assert.throws(() => store.submit({}), (error) => error.status === 429 && /storage limit/.test(error.message));
  assert.deepEqual(store.snapshot(), before);
  assert.equal(fs.readFileSync(store.filename, "utf8"), fileBefore);
  assert.equal(store.nextSubmission(0).comments.length, MAX_COMMENTS);
  assert.equal(store.nextSubmission(0).latestSubmission, 1);
});

test("large submission reads remain bounded, complete and read-only without exporting the journal", () => {
  const { MAX_COMMENTS, MAX_STORE_BYTES } = require("../scripts/feedback-store.js");
  const store = privateFeedbackStore(), screen = "a".repeat(32);
  store.knowScreen(screen, "test.html");
  const text = "ø".repeat(1000), proposed = "å".repeat(1000);
  const comment = store.create(commentFor(screen, { kind: "edit", text, proposal: { property: "text", value: proposed } })).comments[0];
  store.change((state) => { state.comments = Array.from({ length: MAX_COMMENTS }, (_, index) => ({ ...clone(comment), id: index.toString(16).padStart(24, "0") })); });
  store.submit({});
  store.change((state) => { for (const current of state.comments) { current.status = "fixed"; current.reply = "Senere svar med æ, ø og å."; } });
  const saved = fs.readFileSync(store.filename, "utf8");
  const batch = store.nextSubmission(0);
  const bytes = Buffer.byteLength(JSON.stringify(batch));
  assert(bytes > 800 * 1024, "The fixture must exercise a large UTF-8 response.");
  assert(bytes <= MAX_STORE_BYTES + 64 * 1024, "The full response, including current status, must fit the CLI read bound.");
  assert.equal(batch.comments.length, MAX_COMMENTS);
  assert(batch.comments.every((item) => item.text === text && item.proposal.value === proposed && item.reply === ""));
  assert(batch.currentComments.every((item) => item.status === "fixed" && item.reply === "Senere svar med æ, ø og å."));
  assert.equal(Object.hasOwn(batch, "submissions"), false);
  assert.equal(Object.hasOwn(batch, "batches"), false);
  const timeout = store.nextSubmission(1);
  assert.deepEqual(timeout.comments, []);
  assert(Buffer.byteLength(JSON.stringify(timeout)) < 1024, "An exhausted cursor must not repeat the delivered large payload.");
  assert.deepEqual(store.nextSubmission(0), batch, "Reading a cursor does not acknowledge or change it.");
  assert.equal(fs.readFileSync(store.filename, "utf8"), saved);
});

test("submission commit failure is atomic and a receipt retries exactly once", () => {
  const { FeedbackMutationReceipts } = require("../scripts/feedback-store.js");
  const store = privateFeedbackStore(), screen = "a".repeat(32);
  store.knowScreen(screen, "test.html");
  store.create(commentFor(screen));
  const receipts = new FeedbackMutationReceipts(), mutationId = "a".repeat(32);
  const value = { revision: store.snapshot().revision };
  const send = () => receipts.run(mutationId, "POST", "/comments/submit", value, (body) => store.submit(body));
  const before = store.snapshot(), fileBefore = fs.readFileSync(store.filename, "utf8");
  const rename = fs.renameSync;
  fs.renameSync = (...args) => { if (args[1] === store.filename) throw new Error("simulated commit failure"); return rename(...args); };
  try { assert.throws(send, /simulated commit failure/); } finally { fs.renameSync = rename; }
  assert.deepEqual(store.snapshot(), before);
  assert.equal(fs.readFileSync(store.filename, "utf8"), fileBefore);
  assert.deepEqual(store.nextSubmission(0).comments, []);
  assert.equal(fs.readdirSync(store.directory).some((filename) => filename.endsWith(".tmp")), false);
  send();
  const saved = fs.readFileSync(store.filename, "utf8");
  send();
  assert.equal(fs.readFileSync(store.filename, "utf8"), saved);
  assert.equal(store.nextSubmission(0).submission, 1);
  assert.equal(store.nextSubmission(0).latestSubmission, 1);
});

test("submission history HTTP reads validate cursors, parameters and the session boundary", async () => {
  const running = await startServer(makeProject());
  try {
    const url = endpoint(running.info.url, "/comments/submissions");
    assert.equal((await fetch(url)).status, 400);
    for (const after of ["", "-1", "1.5", "01", "9007199254740992", "x"]) {
      url.searchParams.set("after", after);
      assert.equal((await fetch(url)).status, 400, after);
    }
    url.searchParams.set("after", "1");
    assert.equal((await fetch(url)).status, 409, "A cursor from another or newer session must fail explicitly.");
    url.searchParams.set("after", "0");
    const initial = await (await fetch(url)).json();
    assert.equal(initial.submission, 0);
    assert.equal(initial.latestSubmission, 0);
    assert.equal(initial.hasMore, false);
    assert.equal(initial.submittedAt, null);
    assert.deepEqual(initial.comments, []);
    for (const [key, value] of [["unknown", "1"], ["after", "0"], ["waiter", "0"]]) {
      const invalid = new URL(url); invalid.searchParams.append(key, value);
      assert.equal((await fetch(invalid)).status, 400, key);
    }
    const noToken = new URL(url); noToken.searchParams.delete("token");
    assert.equal((await fetch(noToken)).status, 403);
    assert.equal((await fetch(url, { headers: { Origin: "https://unrelated.invalid" } })).status, 403);
    assert.equal((await fetch(url, { method: "POST", headers: { Origin: url.origin, "Content-Type": "application/json" }, body: "{}" })).status, 405);
    url.searchParams.set("waiter", "1");
    assert.equal((await fetch(url)).status, 200);
    const live = await (await feedbackRequest(running.info.url, "/comments")).json();
    assert(live.listeningUntil > Date.now());
    assert.equal(Object.hasOwn(live, "submissions"), false);
    assert.equal(Object.hasOwn(live, "currentComments"), false);
  } finally { await stopServer(running); }
});

test("feedback CLI drains immutable rounds and guards replies against a later resubmission", async () => {
  const running = await startServer(makeProject());
  try {
    const screen = await previewScreen(running);
    const created = await (await feedbackRequest(running.info.url, "/comments", "POST", commentFor(screen, { text: "Keep the first note available." }))).json();
    const removedId = created.comments[0].id;
    const both = await (await feedbackRequest(running.info.url, "/comments", "POST", commentFor(screen, { text: "Reconsider this note." }))).json();
    const resentId = both.comments[1].id;
    const stateArgs = ["--state-dir", running.info.state_dir];
    await feedbackRequest(running.info.url, "/comments/submit", "POST", { revision: both.revision });
    await feedbackRequest(running.info.url, `/comments/${removedId}`, "DELETE", {});
    await feedbackRequest(running.info.url, `/comments/${resentId}`, "PATCH", { status: "open", resubmit: true });
    const beforeResend = JSON.parse((await runComments(["wait", ...stateArgs, "--after", "0", "--timeout", "0"])).stdout);
    assert.equal(beforeResend.submission, 1);
    assert.equal(beforeResend.comments.length, 2);
    assert.deepEqual(beforeResend.currentComments.find((item) => item.id === removedId), { id: removedId, present: false });
    assert.equal(beforeResend.currentComments.find((item) => item.id === resentId).submission, 0);
    await feedbackRequest(running.info.url, "/comments/submit", "POST", {});
    await previewScreen(running, "<h1>A newer screen</h1>");
    const first = JSON.parse((await runComments(["wait", ...stateArgs, "--after", "0", "--timeout", "0"])).stdout);
    assert.equal(first.type, "feedback-submission");
    assert.equal(first.submission, 1);
    assert.equal(first.latestSubmission, 2);
    assert.equal(first.hasMore, true);
    assert.equal(first.comments[0].text, "Keep the first note available.");
    assert(first.comments.every((item) => item.screen === screen && item.submission === 1));
    assert.equal(first.currentComments.find((item) => item.id === resentId).submission, 2);
    const lateReply = await runComments(["resolve", ...stateArgs, "--id", resentId, "--submission", "1", "--reply", "An outdated response."]);
    assert.equal(lateReply.code, 2);
    assert.match(lateReply.stderr, /different submission/);
    const resolved = await runComments(["resolve", ...stateArgs, "--id", resentId, "--submission", "2", "--reply", "A current response."]);
    assert.equal(resolved.code, 0, resolved.stderr);
    const second = JSON.parse((await runComments(["wait", ...stateArgs, "--after", "1", "--timeout", "0"])).stdout);
    assert.equal(second.submission, 2);
    assert.equal(second.hasMore, false);
    assert.equal(second.comments.length, 1);
    assert.equal(second.comments[0].id, resentId);
    assert.equal(second.comments[0].status, "open");
    assert.equal(second.comments[0].reply, "");
    assert.equal(second.currentComments[0].status, "fixed");
    assert.equal(second.currentComments[0].reply, "A current response.");
    assert.equal((await runComments(["reopen", ...stateArgs, "--id", resentId, "--submission", "1"])).code, 2);
    assert.equal((await runComments(["reopen", ...stateArgs, "--id", resentId, "--submission", "2"])).code, 0);
    const timeout = JSON.parse((await runComments(["wait", ...stateArgs, "--after", "2", "--timeout", "0"])).stdout);
    assert.equal(timeout.type, "feedback-timeout");
    assert.deepEqual(timeout.comments, []);
    assert.deepEqual(timeout.currentComments, []);
    assert.equal((await runComments(["wait", ...stateArgs, "--after", "3", "--timeout", "0"])).code, 2);
    for (const command of ["delete", "release", "list", "wait"]) assert.equal((await runComments([command, ...stateArgs, ...(["delete", "release"].includes(command) ? ["--id", resentId] : []), "--submission", "2"])).code, 2);
    assert.equal(JSON.stringify(first).includes(new URL(running.info.url).searchParams.get("token")), false);
  } finally { await stopServer(running); }
});

test("feedback CLI reports each round's accepted constraints before later changes and releases", async () => {
  const running = await startServer(makeProject());
  try {
    const screen = await workshopScreen(running);
    const created = await (await feedbackRequest(running.info.url, "/decisions", "POST", keepFor(screen))).json();
    const id = created.decisions[0].id;
    await feedbackRequest(running.info.url, "/comments/submit", "POST", {});
    await feedbackRequest(running.info.url, "/decisions", "POST", keepFor(screen, { values: { density: "spacious" } }));
    await feedbackRequest(running.info.url, "/comments/submit", "POST", {});
    await feedbackRequest(running.info.url, `/decisions/${id}`, "PATCH", {});
    await feedbackRequest(running.info.url, "/comments/submit", "POST", {});
    const stateArgs = ["--state-dir", running.info.state_dir, "--timeout", "0"];
    const first = JSON.parse((await runComments(["wait", ...stateArgs, "--after", "0"])).stdout);
    const second = JSON.parse((await runComments(["wait", ...stateArgs, "--after", "1"])).stdout);
    const third = JSON.parse((await runComments(["wait", ...stateArgs, "--after", "2"])).stdout);
    const timeout = JSON.parse((await runComments(["wait", ...stateArgs, "--after", "3"])).stdout);
    assert.equal(first.submission, 1);
    assert.deepEqual(first.decisions[0].values, { density: "compact" });
    assert.equal(first.decisions[0].state, "active");
    assert.deepEqual(second.decisions[0].values, { density: "spacious" });
    assert.equal(second.decisions[0].state, "active");
    assert.equal(third.decisions[0].state, "released");
    assert.equal(third.decisions[0].submission, 3);
    assert.deepEqual(timeout.decisions, []);
  } finally { await stopServer(running); }
});

test("feedback retry identifiers are not consumed by a failed disk commit", async () => {
  const running = await startServer(makeProject());
  const outside = makeProject();
  try {
    const screen = await previewScreen(running);
    const filename = path.join(running.info.state_dir, "comments.json");
    const saved = fs.readFileSync(filename);
    const protectedFile = path.join(outside, "protected.json");
    fs.writeFileSync(protectedFile, "untouched", { mode: 0o600 });
    fs.unlinkSync(filename); fs.symlinkSync(protectedFile, filename);
    const headers = { "X-Feedback-Mutation": "d".repeat(32) };
    const value = commentFor(screen);
    assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", value, headers)).status, 500);
    assert.equal(fs.readFileSync(protectedFile, "utf8"), "untouched");
    fs.unlinkSync(filename); fs.writeFileSync(filename, saved, { mode: 0o600 });
    const recovered = await feedbackRequest(running.info.url, "/comments", "POST", value, headers);
    assert.equal(recovered.status, 200);
    assert.equal((await recovered.json()).comments.length, 1);
    assert.equal((await (await feedbackRequest(running.info.url, "/comments", "POST", value, headers)).json()).comments.length, 1);
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
    const status = { textContent: "", classList: { remove() {}, add() {} }, addEventListener() {}, focus() {} };
    const newer = "f".repeat(32);
    const newest = "e".repeat(32);
    let pollVersion = newer;
    let feedbackStatus = 200;
    vm.runInNewContext(script, {
      document: { getElementById: (id) => id === "vc-preview" ? frame : status },
      window: { location: { origin: new URL(running.info.url).origin }, addEventListener: (_, callback) => callbacks.push(callback) },
      setInterval: (callback) => intervals.push(callback), setTimeout: (callback) => callback(), clearTimeout() {},
      URL, TextEncoder, Date, AbortController,
      fetch: async (url, options) => { requests.push({ url: String(url), options }); return { ok: feedbackStatus === 200, status: feedbackStatus, text: async () => pollVersion, json: async () => feedbackStatus === 200 ? ({ revision: 1, submission: 0, screens: [{ screen, filename: "test.html" }, { screen: newer, filename: "test.html" }, { screen: newest, filename: "test.html" }], comments: [], listeningUntil: 0 }) : ({ error: "RAW_SERVER_DETAIL_NOT_FOR_UI", errorCode: "capacity" }) }; },
    });
    const send = (data, source = frameWindow) => callbacks.forEach((callback) => callback({ data, source }));
    const base = { channel: "grillmester-visual-companion", version: 1 };
    send({ ...base, action: "comment-create", requestId: 1, payload: { ...commentFor(screen), html: "hidden" } });
    send({ ...base, action: "comment-create", requestId: 1, payload: commentFor(screen) }, {});
    assert.equal(requests.length, 0);
    send({ ...base, action: "comment-create", requestId: 1, mutationId: "not-an-id", payload: commentFor(screen) });
    assert.equal(requests.length, 0);
    send({ ...base, action: "comment-create", requestId: 1, mutationId: "a".repeat(32), payload: commentFor(screen) });
    await new Promise(setImmediate);
    assert.equal(requests.length, 1);
    assert.equal(new URL(requests[0].url).pathname, "/comments");
    assert.equal(requests[0].options.headers["X-Feedback-Mutation"], "a".repeat(32));
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
    send({ ...base, action: "comments-list", requestId: 2, mutationId: "b".repeat(32), payload: {} });
    await new Promise(setImmediate);
    assert.equal(requests.at(-1).options.headers, undefined, "Read requests must not forward a mutation identifier.");
    const context = { variant: "", target: "summary", values: { stage: "details" } };
    const beforeInvalid = requests.length;
    send({ ...base, action: "comment-create", requestId: 3, payload: commentFor(screen, { context: { ...context, text: "untrusted DOM text" } }) });
    assert.equal(requests.length, beforeInvalid, "The shell rejects undeclared context metadata before HTTP.");
    send({ ...base, action: "comment-create", requestId: 4, payload: commentFor(screen, { context }) });
    await new Promise(setImmediate);
    assert.deepEqual(JSON.parse(requests.at(-1).options.body).context, context);
    const beforeNull = requests.length;
    for (const action of ["decision-keep", "decision-release"]) send({ ...base, action, requestId: 5, payload: null });
    assert.equal(requests.length, beforeNull, "Null decision payloads must be rejected before property access or HTTP.");
    for (const status of [429, 400, 500]) {
      feedbackStatus = status;
      send({ ...base, action: "comment-create", requestId: status, payload: commentFor(screen) });
      await new Promise(setImmediate);
      const result = messages.at(-1);
      assert.equal(result.ok, false);
      assert.equal(result.errorCode, status === 429 ? "capacity" : undefined, "Only the HTTP capacity status selects the bounded UI code.");
    }
    const helper = fs.readFileSync(path.resolve(__dirname, "../scripts/helper.js"), "utf8");
    const resultStart = helper.indexOf('    if (data.command === "comments-result" || data.command === "workspace-result") {');
    const resultEnd = helper.indexOf('    if (data.command !== "selection-status"', resultStart);
    assert(resultStart >= 0 && resultEnd > resultStart);
    const pending = new Map();
    let stored = false;
    const receive = vm.runInNewContext(`(data) => { ${helper.slice(resultStart, resultEnd)} }`, { requests: pending, window: { clearTimeout() {} }, applySnapshot() {}, updateBusy() {}, workspaceStored: () => stored });
    for (const errorCode of ["capacity", "unknown", undefined]) {
      let failure;
      pending.set(1, { action: "comment-create", timer: 1, reject: (error) => { failure = error; } });
      receive({ command: "comments-result", requestId: 1, ok: false, errorCode, error: "RAW_SERVER_DETAIL_NOT_FOR_UI" });
      assert(failure);
      assert.equal(failure.message.includes("RAW_SERVER_DETAIL_NOT_FOR_UI"), false);
      if (errorCode === "capacity") { assert.match(failure.message, /lagringsgrense/); assert.doesNotMatch(failure.message, /prøv samme innspill igjen/i); }
      else assert.match(failure.message, /prøv samme innspill igjen/i);
    }
    // A saved room reopens with the same full journal, so a new session is no way out.
    stored = true;
    let roomFailure;
    pending.set(1, { action: "comment-create", timer: 1, reject: (error) => { roomFailure = error; } });
    receive({ command: "comments-result", requestId: 1, ok: false, errorCode: "capacity" });
    assert.match(roomFailure.message, /lagringsgrense/);
    assert.match(roomFailure.message, /opprette et nytt arbeid/);
    assert.doesNotMatch(roomFailure.message, /før du starter en ny økt/);
  } finally { await stopServer(running); }
});

test("restore distinguishes preserved-field conflicts from stale history without retrying or claiming success", async () => {
  const source = fs.readFileSync(path.resolve(__dirname, "../scripts/helper.js"), "utf8");
  const excerpt = (start, end) => {
    const from = source.indexOf(start), to = source.indexOf(end, from);
    assert(from >= 0 && to > from);
    return source.slice(from, to);
  };
  const summary = excerpt("  function workspaceStored()", "  function closeWorkspace(");
  const restore = excerpt("  async function restoreWorkspace()", "  function renderCanvasRounds()");
  const result = excerpt('    if (data.command === "comments-result" || data.command === "workspace-result") {', '    if (data.command !== "selection-status"');
  for (const errorCode of ["editor-conflict", undefined, "unknown"]) {
    const nodes = new Map(), requests = new Map(), calls = [], announcements = [];
    const el = selector => {
      if (!nodes.has(selector)) nodes.set(selector, { textContent: "", hidden: false, disabled: false, dataset: {}, setAttribute() {} });
      return nodes.get(selector);
    };
    const snapshot = { revision: 7, workspace: { storage: "project", title: "Test", path: "designs/test", version: 3 } };
    const confirmation = { entry: { revisionId: 1 }, expectedRevision: snapshot.revision, retry: {} };
    const context = {
      el, all: () => [el('[data-action="workspace-restore"]')], snapshot, requests,
      workspaceButton: {}, workspaceConfirmation: confirmation, workspaceRestoring: false,
      workspaceLoading: false, workspaceNextAfter: null, workspaceRestoreOpen: false,
      draft: null, drag: null, preview: null, workshop: null, editor: null,
      connectionLost: false, savingDraft: false, updateAvailable: false,
      canvasRounds: () => [], window: { clearTimeout() {} },
      errorAt: (selector, text) => { el(selector).textContent = text; },
      announce: text => announcements.push(text),
      refreshNow: () => assert.fail("A rejected restore must not refresh the sketch."),
      applySnapshot: () => assert.fail("A rejected restore must not apply a snapshot."),
      request: (action, payload, retry) => {
        calls.push({ action, payload, retry });
        return new Promise((resolve, reject) => requests.set(1, { action, resolve, reject, timer: 1 }));
      },
    };
    const browser = require("node:vm").runInNewContext(`${summary}\n${restore}\nfunction updateBusy() { renderWorkspaceSummary(); }\nrenderWorkspaceSummary();\n({ restore: restoreWorkspace, receive: (data) => { ${result} } })`, context);
    const running = browser.restore();
    assert.equal(calls.length, 1);
    assert.equal(calls[0].action, "workspace-restore");
    assert.deepEqual(JSON.parse(JSON.stringify(calls[0].payload)), { revisionId: 1, expectedRevision: 7 });
    assert.equal(calls[0].retry, confirmation.retry);
    browser.receive({ command: "workspace-result", requestId: 1, ok: false, conflict: true, errorCode, error: "PRIVATE_SERVER_DETAIL" });
    await running;
    const message = el(".workspace-error").textContent;
    if (errorCode === "editor-conflict") {
      assert.match(message, /^Versjon 1 endrer felt du har lagret\./);
      assert.match(message, /Tillat senere endring av feltene i «Rediger skissen»/);
      assert.doesNotMatch(message, /^Arbeidet er endret/);
    } else assert.equal(message, "Arbeidet er endret. Oppdater historikken og velg versjonen på nytt.");
    assert.doesNotMatch(message, /PRIVATE_SERVER_DETAIL/);
    assert.equal(context.workspaceConfirmation, confirmation);
    assert.equal(confirmation.conflict, true);
    assert.equal(context.workspaceRestoring, false);
    assert.equal(el('[data-action="workspace-restore"]').disabled, true);
    assert.equal(snapshot.workspace.version, 3);
    assert.equal(snapshot.revision, 7);
    assert.equal(context.workspaceRestoreOpen, false);
    assert.deepEqual(announcements, []);
    assert.equal(requests.size, 0);
    await browser.restore();
    assert.equal(calls.length, 1, "A blocked restore cannot silently retry the rejected write.");
  }
});


test("a restore blocked by named preserved fields offers one release-and-restore action", async () => {
  const source = fs.readFileSync(path.resolve(__dirname, "../scripts/helper.js"), "utf8");
  const excerpt = (start, end) => {
    const from = source.indexOf(start), to = source.indexOf(end, from);
    assert(from >= 0 && to > from);
    return source.slice(from, to);
  };
  const summary = excerpt("  function workspaceStored()", "  function closeWorkspace(");
  const restore = excerpt("  async function restoreWorkspace()", "  function renderCanvasRounds()");
  const result = excerpt('    if (data.command === "comments-result" || data.command === "workspace-result") {', '    if (data.command !== "selection-status"');
  const nodes = new Map(), requests = new Map(), calls = [];
  const el = selector => {
    if (!nodes.has(selector)) nodes.set(selector, { textContent: "", hidden: false, disabled: false, dataset: {}, setAttribute() {} });
    return nodes.get(selector);
  };
  const snapshot = { revision: 7, workspace: { storage: "project", title: "Test", path: "designs/test", version: 3 } };
  const confirmation = { entry: { revisionId: 1 }, expectedRevision: snapshot.revision, retry: {} };
  let sequence = 0;
  const context = {
    el, all: () => [el('[data-action="workspace-restore"]'), el('[data-action="workspace-release-restore"]')], snapshot, requests,
    workspaceButton: {}, workspaceConfirmation: confirmation, workspaceRestoring: false,
    workspaceLoading: false, workspaceNextAfter: null, workspaceRestoreOpen: false,
    draft: null, drag: null, preview: null, workshop: null, editor: null, screen: "c".repeat(32),
    connectionLost: false, savingDraft: false, updateAvailable: false,
    canvasRounds: () => [], window: { clearTimeout() {} },
    errorAt: (selector, text) => { el(selector).textContent = text; },
    announce() {}, refreshNow() {}, applySnapshot() {},
    request: (action, payload, retry) => {
      calls.push({ action, payload: JSON.parse(JSON.stringify(payload)), retry });
      const id = ++sequence;
      return new Promise((resolve, reject) => requests.set(id, { action, resolve, reject, timer: 1 }));
    },
  };
  const browser = require("node:vm").runInNewContext(`${summary}\n${restore}\nfunction updateBusy() { renderWorkspaceSummary(); }\nrenderWorkspaceSummary();\n({ restore: restoreWorkspace, release: releaseAndRestore, receive: (data) => { ${result} }, confirmation: () => workspaceConfirmation })`, context);
  const running = browser.restore();
  browser.receive({ command: "workspace-result", requestId: 1, ok: false, conflict: true, errorCode: "editor-conflict",
    conflicts: [{ id: "text:heading", label: "Overskrift" }, { id: "control:/card/density", label: "Luft · Oppsummering" }] });
  await running;
  assert.match(el(".workspace-error").textContent, /Versjon 1 endrer felt du har lagret: «Overskrift», «Luft · Oppsummering»\./);
  const action = el('[data-action="workspace-release-restore"]');
  assert.equal(action.hidden, false);
  assert.equal(action.disabled, false);
  assert.equal(action.textContent, "Tillat endring og bruk versjon 1");
  assert.equal(el('[data-action="workspace-restore"]').disabled, true, "The plain restore stays blocked.");
  const releasing = browser.release();
  assert.deepEqual(calls[1], { action: "workspace-editor-release", payload: { screen: "c".repeat(32), expectedRevision: 7, ids: ["text:heading", "control:/card/density"] }, retry: calls[1].retry });
  snapshot.revision = 8;
  browser.receive({ command: "workspace-result", requestId: 2, ok: true, snapshot: { ...snapshot } });
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(calls[2].payload, { revisionId: 1, expectedRevision: 8 });
  browser.receive({ command: "workspace-result", requestId: 3, ok: true, snapshot: { ...snapshot } });
  await releasing;
  assert.equal(browser.confirmation(), null);
  assert.equal(calls.length, 3, "Exactly one release and one restore are written.");
});

test("feedback results and conflict refreshes stay with their originating preview document", async () => {
  const running = await startServer(makeProject());
  try {
    const screen = await previewScreen(running);
    const html = await (await fetch(running.info.url)).text();
    const script = html.match(/<script nonce="[^"]+">([\s\S]*?)<\/script>/)[1];
    const vm = require("node:vm");
    const callbacks = [], messages = [];
    const frameWindow = { postMessage: value => messages.push(value) };
    const frame = { contentWindow: frameWindow, src: "unchanged" };
    const status = { textContent: "", classList: { remove() {}, add() {} }, addEventListener() {}, focus() {} };
    const snapshot = { revision: 1, submission: 0, screens: [{ screen, filename: "test.html" }], comments: [], listeningUntil: 0 };
    const response = (statusCode, value) => ({ ok: statusCode === 200, status: statusCode, json: async () => value });
    let write = async () => response(200, snapshot), read = async () => response(200, snapshot);
    vm.runInNewContext(script, {
      document: { getElementById: id => id === "vc-preview" ? frame : status },
      window: { location: { origin: new URL(running.info.url).origin }, addEventListener: (_, callback) => callbacks.push(callback) },
      setInterval() {}, setTimeout() { return 1; }, clearTimeout() {}, URL, TextEncoder, Date, AbortController,
      fetch: (url, options) => options?.method === "POST" ? write() : read(),
    });
    const base = { channel: "grillmester-visual-companion", version: 1 };
    const send = data => callbacks.forEach(callback => callback({ data: { ...base, ...data }, source: frameWindow }));
    const tick = () => new Promise(setImmediate);
    const ready = async () => { send({ action: "feedback-ready", screen }); await tick(); };
    await ready();
    for (const kind of ["success", "http-failure", "transport-failure", "body-decoding"]) {
      let resolve, reject;
      const pending = new Promise((done, fail) => { resolve = done; reject = fail; });
      write = kind === "body-decoding" ? async () => ({ ok: true, status: 200, json: () => pending }) : () => pending;
      send({ action: "comment-create", requestId: 2, payload: commentFor(screen) });
      await tick();
      await ready(); // A reload of even the same screen starts a new document.
      const before = messages.length;
      if (kind === "transport-failure") reject(new Error("Controlled old transport failure."));
      else resolve(kind === "body-decoding" ? snapshot : response(kind === "success" ? 200 : 503, snapshot));
      await tick();
      assert.equal(messages.slice(before).some(message => message.command === "comments-result"), false, `An old ${kind} must not settle a new document's reused request number.`);
    }
    let releaseRead, readStarted = false;
    const delayedRead = new Promise(resolve => { releaseRead = resolve; });
    read = () => { readStarted = true; return delayedRead; };
    write = async () => response(409, { error: "Controlled conflict." });
    send({ action: "comments-submit", requestId: 3, payload: { revision: 1 } });
    await tick();
    assert.equal(readStarted, true, "The conflict must actually enter its follow-up read before the document changes.");
    read = async () => response(200, snapshot);
    await ready();
    const before = messages.length;
    releaseRead(response(200, { ...snapshot, revision: 77 }));
    await tick();
    assert.equal(messages.slice(before).some(message => message.command === "comments-result" || message.snapshot?.revision === 77), false, "An old conflict read must not refresh or reject the next document.");
    write = async () => response(200, snapshot);
    send({ action: "comment-create", requestId: 2, payload: commentFor(screen) });
    await tick();
    assert.equal(messages.at(-1).command, "comments-result");
    assert.equal(messages.at(-1).requestId, 2);
    assert.equal(messages.at(-1).ok, true, "A current document's own response must still be delivered.");
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

test("comment context includes only declared settings from its own screen", async () => {
  const running = await startServer(makeProject());
  try {
    const screen = await workshopScreen(running);
    const context = { variant: "", target: "header", values: { density: "compact", description: "hidden" } };
    for (const kind of ["point", "area", "edit"]) {
      const value = commentFor(screen, { kind, context, ...(kind === "edit" ? { proposal: { property: "text", value: "A clearer heading." } } : {}) });
      const response = await feedbackRequest(running.info.url, "/comments", "POST", value);
      assert.equal(response.status, 200);
      assert.deepEqual((await response.json()).comments.at(-1).context, context);
    }
    assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", commentFor(screen, { context: { ...context, values: {} } }))).status, 200);
    const invalid = [
      null,
      { ...context, text: "DOM content must not be collected" },
      { ...context, values: { density: "a raw form value" } },
      { ...context, values: { density: "undeclared" } },
      { ...context, values: { unknown: "compact" } },
      { ...context, target: "unknown" },
      { ...context, variant: "compact" },
      { ...context, values: [] },
    ];
    for (const value of invalid) assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", commentFor(screen, { context: value }))).status, 400, JSON.stringify(value));
    assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", commentFor(screen, { kind: "adjustment", adjustment: context, context }))).status, 400);
    assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", commentFor(screen, { kind: "variant", variant: "compact", context }))).status, 400);
    const nextDesign = sampleDesign(); nextDesign.targets[0].controls[0].options.shift();
    const next = await workshopScreen(running, nextDesign);
    assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", commentFor(next, { context }))).status, 400);
    assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", commentFor(screen, { context }))).status, 200, "An older draft remains bound to its original declaration.");
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

test("a saved workspace at its journal limits points to a new workspace, not a new session", () => {
  const { FeedbackStore, MAX_COMMENTS } = require("../scripts/feedback-store.js");
  const root = fs.realpathSync(makeProject());
  fs.chmodSync(root, 0o700);
  const store = new FeedbackStore(root, { canvas: true, persistence: { load: () => null, persist() {} },
    initialWorkspace: { id: "d".repeat(24), title: "Lagret rom", version: 0, revisions: [] } });
  const screen = "c".repeat(32);
  store.knowScreen(screen, "test.html", sampleDesign());
  const savedLimit = (pattern) => (error) => error.status === 429 && pattern.test(error.message) &&
    /saved workspace/.test(error.message) && /new workspace/.test(error.message) && /keeps the same limit/.test(error.message) &&
    !/start a new (?:preview )?session/.test(error.message);
  for (let index = 0; index < 200; index += 1) {
    const snapshot = store.keep(keepFor(screen));
    store.release(snapshot.decisions.at(-1).id, {});
    store.submit({});
    // Only an acknowledged delivery admits the next canvas round.
    store.change((state) => { state.canvas.rounds.at(-1).delivery = "queued"; });
  }
  assert.throws(() => store.keep(keepFor(screen)), savedLimit(/Decision limit reached/));
  const id = store.create(commentFor(screen)).comments[0].id;
  assert.throws(() => store.submit({}), savedLimit(/Submission limit reached/));
  store.delete(id, {});
  for (let index = 0; index < MAX_COMMENTS; index += 1) store.create(commentFor(screen));
  assert.throws(() => store.create(commentFor(screen)), savedLimit(/Comment limit reached/));
});

test("decision revision guards preserve another tab's pending choice on the same or a newer screen", () => {
  for (const crossScreen of [false, true]) {
    const store = privateFeedbackStore();
    const firstScreen = "a".repeat(32), laterScreen = crossScreen ? "b".repeat(32) : firstScreen;
    store.knowScreen(firstScreen, "first.html", sampleDesign());
    if (crossScreen) store.knowScreen(laterScreen, "later.html", sampleDesign());
    const staleDraft = keepFor(firstScreen, { expectedRevision: 0, text: "An older local note." });
    const created = store.keep(keepFor(laterScreen, { expectedRevision: 0, values: { density: "spacious" }, text: "A newer pending choice." }));
    const first = created.decisions[0];
    assert.equal(first.revision, created.revision);
    assert.equal(Object.hasOwn(first, "expectedRevision"), false);
    const saved = fs.readFileSync(store.filename, "utf8");
    assert.throws(() => store.keep(staleDraft), (error) => error.status === 409);
    assert.deepEqual(store.snapshot(), created);
    assert.equal(fs.readFileSync(store.filename, "utf8"), saved);
    const accepted = store.submit({});
    const updated = store.keep(keepFor(laterScreen, { expectedRevision: first.revision, text: "The latest pending note." }));
    const current = updated.decisions[0];
    assert(current.revision > first.revision);
    assert.equal(current.revision, updated.revision);
    assert.deepEqual(updated.submittedDecisions, accepted.submittedDecisions, "Guarded edits do not publish or replace accepted constraints.");
    for (const expectedRevision of [0, first.revision]) {
      assert.throws(() => store.keep(keepFor(firstScreen, { expectedRevision })), (error) => error.status === 409);
      assert.throws(() => store.release(first.id, { expectedRevision }), (error) => error.status === 409);
    }
    assert.deepEqual(store.snapshot(), updated);
    const released = store.release(first.id, { expectedRevision: current.revision });
    assert.equal(released.decisions[0].revision, released.revision);
    assert.deepEqual(released.submittedDecisions, accepted.submittedDecisions);
    assert.throws(() => store.keep(keepFor(firstScreen, { expectedRevision: current.revision })), (error) => error.status === 409);
    const restored = store.keep(keepFor(firstScreen, { expectedRevision: released.decisions[0].revision }));
    assert.equal(restored.decisions[0].id, first.id, "Re-keeping a pending release must guard and reuse that same decision.");
    assert.equal(restored.decisions.length, 1);
    store.release(first.id, { expectedRevision: restored.decisions[0].revision });
    store.submit({});
    const newHold = store.keep(keepFor(firstScreen, { expectedRevision: 0 }));
    assert.equal(newHold.decisions.length, 2);
    assert.notEqual(newHold.decisions[1].id, first.id, "A published release permits an explicitly new hold.");
  }
});

test("decision revision guards reject invalid metadata without changing live or accepted state", () => {
  const store = privateFeedbackStore(), screen = "a".repeat(32);
  store.knowScreen(screen, "test.html", sampleDesign());
  const created = store.keep(keepFor(screen, { expectedRevision: 0 }));
  const { id, revision } = created.decisions[0];
  const before = store.submit({});
  for (const expectedRevision of [-1, 1.5, "1", null, Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(() => store.keep(keepFor(screen, { expectedRevision })), (error) => error.status === 400);
    assert.throws(() => store.release(id, { expectedRevision }), (error) => error.status === 400);
  }
  for (const metadata of [{ revision }, { expectedRevision: revision, extra: true }]) {
    assert.throws(() => store.keep(keepFor(screen, metadata)), (error) => error.status === 400);
    assert.throws(() => store.release(id, metadata), (error) => error.status === 400);
  }
  assert.deepEqual(store.snapshot(), before);
  const legacy = store.keep(keepFor(screen));
  assert(legacy.decisions[0].revision > revision, "Legacy callers remain supported and still advance the decision revision.");
  assert.equal(store.release(id, {}).decisions[0].state, "released");
});

test("failed guarded decision commits preserve their revision and can retry with the same receipt", () => {
  const { FeedbackMutationReceipts } = require("../scripts/feedback-store.js");
  const store = privateFeedbackStore(), screen = "a".repeat(32);
  store.knowScreen(screen, "test.html", sampleDesign());
  const receipts = new FeedbackMutationReceipts();
  const payload = keepFor(screen, { expectedRevision: 0 });
  const keep = () => receipts.run("a".repeat(32), "POST", "/decisions", payload, (body) => store.keep(body));
  const failCommit = (operation) => {
    const before = store.snapshot(), saved = fs.readFileSync(store.filename, "utf8");
    const rename = fs.renameSync;
    fs.renameSync = (...args) => { if (args[1] === store.filename) throw new Error("decision commit failed"); return rename(...args); };
    try { assert.throws(operation, /decision commit failed/); } finally { fs.renameSync = rename; }
    assert.deepEqual(store.snapshot(), before);
    assert.equal(fs.readFileSync(store.filename, "utf8"), saved);
    operation();
    const committed = store.snapshot();
    operation();
    assert.deepEqual(store.snapshot(), committed);
  };
  failCommit(keep);
  const { id, revision } = store.snapshot().decisions[0];
  const releasePayload = { expectedRevision: revision };
  failCommit(() => receipts.run("b".repeat(32), "PATCH", `/decisions/${id}`, releasePayload, (body) => store.release(id, body)));
});

test("guarded decision retries recover an accepted write without overwriting a newer choice", async () => {
  const running = await startServer(makeProject());
  try {
    const screen = await workshopScreen(running);
    const keep = keepFor(screen, { expectedRevision: 0, text: "The original intent." });
    const keepHeaders = { "X-Feedback-Mutation": "d".repeat(32) };
    const firstResponse = await feedbackRequest(running.info.url, "/decisions", "POST", keep, keepHeaders);
    assert.equal(firstResponse.status, 200);
    const first = (await firstResponse.json()).decisions[0];
    const second = await (await feedbackRequest(running.info.url, "/decisions", "POST", keepFor(screen, { expectedRevision: first.revision, text: "A newer local choice." }))).json();
    assert.equal((await feedbackRequest(running.info.url, "/decisions", "POST", keep)).status, 409);
    const retry = await feedbackRequest(running.info.url, "/decisions", "POST", keep, keepHeaders);
    assert.equal(retry.status, 200);
    assert.deepEqual(await retry.json(), second, "A lost-response retry returns current state without restoring its older content.");
    const release = { expectedRevision: second.decisions[0].revision };
    const releaseHeaders = { "X-Feedback-Mutation": "e".repeat(32) };
    const released = await (await feedbackRequest(running.info.url, `/decisions/${first.id}`, "PATCH", release, releaseHeaders)).json();
    const restored = await (await feedbackRequest(running.info.url, "/decisions", "POST", keepFor(screen, { expectedRevision: released.decisions[0].revision, text: "Keep this after reconsidering." }))).json();
    assert.equal((await feedbackRequest(running.info.url, `/decisions/${first.id}`, "PATCH", release)).status, 409);
    const releaseRetry = await feedbackRequest(running.info.url, `/decisions/${first.id}`, "PATCH", release, releaseHeaders);
    assert.equal(releaseRetry.status, 200);
    assert.deepEqual(await releaseRetry.json(), restored);
    assert.equal(restored.decisions[0].state, "active");
  } finally { await stopServer(running); }
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

test("selection storage failures preserve the session and never alter linked files", async () => {
  for (const replacement of ["symlink", "hardlink", "directory"]) {
    const running = await startServer(makeProject());
    try {
      const screen = await previewScreen(running);
      await feedbackRequest(running.info.url, "/comments", "POST", commentFor(screen));
      const outside = path.join(makeProject(), "outside.txt");
      fs.writeFileSync(outside, "OUTSIDE-CONTENT-MUST-STAY-PRIVATE", { mode: 0o600 });
      const eventPath = path.join(running.info.state_dir, "events.jsonl");
      if (replacement === "symlink") fs.symlinkSync(outside, eventPath);
      else if (replacement === "hardlink") fs.linkSync(outside, eventPath);
      else fs.mkdirSync(eventPath);
      const response = await postEvent(running.info.url, { type: "click", choice: "choice-1", screen });
      assert.equal(response.status, 500, replacement);
      const error = await response.json();
      assert.deepEqual(error, { error: "Selection storage is unavailable." });
      assert.equal(fs.readFileSync(outside, "utf8"), "OUTSIDE-CONTENT-MUST-STAY-PRIVATE");
      const snapshot = await (await feedbackRequest(running.info.url, "/comments")).json();
      assert.equal(snapshot.comments.length, 1, "a selection failure must not remove saved feedback");
      fs.rmSync(eventPath, { recursive: true });
      assert.equal((await postEvent(running.info.url, { type: "click", choice: "choice-1", screen })).status, 200);
    } finally { await stopServer(running); }
  }
});

test("existing feedback remains available when a new version reaches the screen limit", async () => {
  const running = await startServer(makeProject());
  try {
    const first = await previewScreen(running, "<h1>Version 0</h1>");
    const created = await (await feedbackRequest(running.info.url, "/comments", "POST", commentFor(first))).json();
    for (let index = 1; index < 100; index += 1) {
      const screen = await previewScreen(running, `<h1>Version ${index}</h1>`);
      assert.match(screen, /^[a-f0-9]{32}$/);
    }
    fs.writeFileSync(path.join(running.info.screen_dir, "test.html"), "<h1>One version too many</h1>");
    const rejected = await fetch(endpoint(running.info.url, "/version"));
    assert.equal(rejected.status, 429);
    assert.match(await rejected.text(), /Screen limit reached/);
    const response = await feedbackRequest(running.info.url, "/comments");
    assert.equal(response.status, 200, "the content limit must not block access to existing feedback");
    const snapshot = await response.json();
    assert.equal(snapshot.screens.length, 100);
    assert.equal(snapshot.comments[0].id, created.comments[0].id);
    assert.equal((await feedbackRequest(running.info.url, "/comments/submit", "POST", {})).status, 200);
    const listed = await runComments(["list", "--state-dir", running.info.state_dir]);
    assert.equal(listed.code, 0, listed.stderr);
    assert.equal(JSON.parse(listed.stdout).comments[0].submission, 1);
  } finally { await stopServer(running); }
});

test("feedback can be read and deleted when design history fills its byte budget", async () => {
  const { validDesign } = require("../scripts/design-contract.js");
  const design = {
    version: 1,
    variants: [],
    targets: Array.from({ length: 24 }, (_, index) => ({
      key: `target-${index}`, variant: "", label: `Target ${index}`,
      controls: [{ id: "density", label: "Density", type: "select", initial: "option-0",
        options: Array.from({ length: 8 }, (_, option) => ({ value: `option-${option}`, label: String(option).padEnd(100, "x") })) }],
    })),
  };
  assert.equal(validDesign(design), true);
  const running = await startServer(makeProject());
  try {
    fs.writeFileSync(path.join(running.info.screen_dir, "test.design.json"), JSON.stringify(design));
    const first = await previewScreen(running, "<h1>Version 0</h1>");
    const created = await (await feedbackRequest(running.info.url, "/comments", "POST", commentFor(first, { text: "x".repeat(2000) }))).json();
    let full = false;
    for (let index = 1; index < 100; index += 1) {
      fs.writeFileSync(path.join(running.info.screen_dir, "test.html"), `<h1>Version ${index}</h1>`);
      const response = await fetch(endpoint(running.info.url, "/version"));
      if (response.status === 429) {
        assert.match(await response.text(), /storage limit reached/);
        full = true;
        break;
      }
      assert.equal(response.status, 200);
    }
    assert.equal(full, true, "the real byte limit must be reached before the screen count limit");
    const snapshot = await (await feedbackRequest(running.info.url, "/comments")).json();
    assert.equal(snapshot.comments[0].id, created.comments[0].id);
    assert.equal((await feedbackRequest(running.info.url, `/comments/${created.comments[0].id}`, "DELETE", {})).status, 200);
    assert.equal((await feedbackRequest(running.info.url, "/comments", "POST", commentFor(first))).status, 200);
  } finally { await stopServer(running); }
});

test("an interrupted selection request does not stop the preview or erase feedback", async () => {
  const http = require("node:http");
  const running = await startServer(makeProject());
  try {
    const screen = await previewScreen(running);
    await feedbackRequest(running.info.url, "/comments", "POST", commentFor(screen));
    const url = endpoint(running.info.url, "/events");
    await new Promise((resolve, reject) => {
      const request = http.request(url, { method: "POST", headers: { Origin: url.origin, "Content-Type": "application/json", "Content-Length": "1000" } });
      request.on("error", (error) => error.code === "ECONNRESET" ? resolve() : reject(error));
      request.write('{"type":"click"');
      request.once("socket", (socket) => socket.once("connect", () => setTimeout(() => request.destroy(), 50)));
    });
    const response = await feedbackRequest(running.info.url, "/comments");
    assert.equal(response.status, 200);
    assert.equal((await response.json()).comments.length, 1);
    assert.equal((await postEvent(running.info.url, { type: "click", choice: "choice-1", screen })).status, 200);
  } finally { await stopServer(running); }
});

test("a participant reopening feedback creates a new deliberate batch without looping on replies", async () => {
  const running = await startServer(makeProject());
  try {
    const screen = await previewScreen(running);
    const created = await (await feedbackRequest(running.info.url, "/comments", "POST", commentFor(screen))).json();
    const id = created.comments[0].id;
    const args = ["--state-dir", running.info.state_dir];
    await feedbackRequest(running.info.url, "/comments/submit", "POST", { revision: created.revision });
    await runComments(["resolve", ...args, "--id", id, "--reply", "Checked the new wording."]);
    const reopened = await runComments(["reopen", ...args, "--id", id]);
    assert.equal(reopened.code, 0, reopened.stderr);
    assert.equal(JSON.parse(reopened.stdout).comments[0].submission, 1, "a working status update must not create a new participant batch");
    await runComments(["resolve", ...args, "--id", id]);
    const pending = await (await feedbackRequest(running.info.url, `/comments/${id}`, "PATCH", { status: "open", resubmit: true })).json();
    assert.equal(pending.comments[0].submission, 0);
    assert.equal(pending.comments[0].reply, "Checked the new wording.");
    assert.equal(Object.hasOwn(pending.comments[0], "resubmit"), false, "the command flag is not stored as comment data");
    const beforeSend = JSON.parse((await runComments(["wait", ...args, "--after", "1", "--timeout", "0"])).stdout);
    assert.equal(beforeSend.type, "feedback-timeout");
    await feedbackRequest(running.info.url, "/comments/submit", "POST", { revision: pending.revision });
    const next = JSON.parse((await runComments(["wait", ...args, "--after", "1", "--timeout", "0"])).stdout);
    assert.equal(next.type, "feedback-submission");
    assert.equal(next.submission, 2);
    assert.equal(next.comments[0].id, id);
    assert.equal(next.comments[0].status, "open");
    assert.equal(next.comments.length, 1);
    for (const patch of [{ resubmit: true }, { status: "fixed", resubmit: true }, { status: "open", resubmit: false }, { status: "open", submission: 0 }]) {
      assert.equal((await feedbackRequest(running.info.url, `/comments/${id}`, "PATCH", patch)).status, 400);
    }
  } finally { await stopServer(running); }
});

test("a reviewed batch refuses unseen comments and changed decisions until the list is refreshed", async () => {
  const running = await startServer(makeProject());
  try {
    const screen = await workshopScreen(running);
    const reviewed = await (await feedbackRequest(running.info.url, "/comments", "POST", commentFor(screen))).json();
    const unseen = await (await feedbackRequest(running.info.url, "/comments", "POST", commentFor(screen, { text: "Added in another tab." }))).json();
    const stale = await feedbackRequest(running.info.url, "/comments/submit", "POST", { revision: reviewed.revision });
    assert.equal(stale.status, 409);
    assert.match((await stale.json()).error, /Review the current feedback/);
    const afterReject = await (await feedbackRequest(running.info.url, "/comments")).json();
    assert.equal(afterReject.submission, 0);
    assert.equal(afterReject.comments.length, 2);
    assert(afterReject.comments.every((item) => item.submission === 0));
    assert.equal((await feedbackRequest(running.info.url, "/comments/submit", "POST", { revision: unseen.revision })).status, 200);
    const kept = await (await feedbackRequest(running.info.url, "/decisions", "POST", keepFor(screen))).json();
    const released = await (await feedbackRequest(running.info.url, `/decisions/${kept.decisions[0].id}`, "PATCH", {})).json();
    assert.equal((await feedbackRequest(running.info.url, "/comments/submit", "POST", { revision: kept.revision })).status, 409);
    assert.equal((await feedbackRequest(running.info.url, "/comments/submit", "POST", { revision: released.revision })).status, 200);
    for (const revision of [-1, 1.5, "1", null, Number.MAX_SAFE_INTEGER + 1]) {
      assert.equal((await feedbackRequest(running.info.url, "/comments/submit", "POST", { revision })).status, 400);
    }
  } finally { await stopServer(running); }
});


test("a hanging feedback poll stays bounded and permits recovery after connection loss", async () => {
  const running = await startServer(makeProject());
  try {
    const screen = await previewScreen(running);
    const html = await (await fetch(running.info.url)).text();
    const script = html.match(/<script nonce="[^"]+">([\s\S]*?)<\/script>/)[1];
    const vm = require("node:vm");
    let now = 0, nextTimer = 0, mode = "healthy", pendingReads = 0, maxPendingReads = 0, abortedReads = 0;
    const timers = new Map(), messages = [], callbacks = new Map();
    function element(id) {
      const classes = new Set();
      return {
        textContent: "", inert: false, src: "unchanged",
        classList: { add: (name) => classes.add(name), remove: (name) => classes.delete(name), contains: (name) => classes.has(name) },
        addEventListener: (event, callback) => callbacks.set(`${id}:${event}`, callback),
        focus() { focused = id; },
      };
    }
    let focused = null;
    const frame = element("vc-preview"), paused = element("vc-paused"), status = element("vc-status"), recover = element("vc-recover");
    frame.contentWindow = { postMessage: (message) => messages.push({ ...message, at: now }) };
    const elements = { "vc-preview": frame, "vc-paused": paused, "vc-status": status, "vc-recover": recover };
    function schedule(callback, delay, repeat = false) {
      const id = ++nextTimer;
      timers.set(id, { callback, at: now + delay, delay, repeat });
      return id;
    }
    async function advance(milliseconds) {
      const end = now + milliseconds;
      for (;;) {
        const next = [...timers.entries()].filter(([, timer]) => timer.at <= end).sort((a, b) => a[1].at - b[1].at || a[0] - b[0])[0];
        if (!next) break;
        const [id, timer] = next;
        now = timer.at;
        if (timer.repeat) timer.at += timer.delay;
        else timers.delete(id);
        timer.callback();
        await new Promise(setImmediate);
      }
      now = end;
      await new Promise(setImmediate);
    }
    vm.runInNewContext(script, {
      document: { getElementById: (id) => elements[id] },
      window: { location: { origin: new URL(running.info.url).origin }, addEventListener() {} },
      setTimeout: (callback, delay) => schedule(callback, delay), clearTimeout: (id) => timers.delete(id),
      setInterval: (callback, delay) => schedule(callback, delay, true), clearInterval: (id) => timers.delete(id),
      URL, TextEncoder, AbortController, Date: { now: () => now },
      fetch: async (url, options = {}) => {
        if (new URL(url, running.info.url).pathname !== "/comments") return { ok: true, text: async () => screen };
        if (mode === "healthy") return { ok: true, json: async () => ({ revision: 0, submission: 0, screens: [{ screen, filename: "test.html" }], comments: [], decisions: [], submittedDecisions: [] }) };
        // Headers arrive, but the response body never completes. The deadline
        // must cover reading the body, not only obtaining a Response object.
        return { ok: true, json: () => new Promise((resolve, reject) => {
          pendingReads += 1;
          maxPendingReads = Math.max(maxPendingReads, pendingReads);
          const abort = () => {
            pendingReads -= 1;
            abortedReads += 1;
            reject(Object.assign(new Error("Read aborted"), { name: "AbortError" }));
          };
          if (options.signal?.aborted) abort();
          else options.signal?.addEventListener("abort", abort, { once: true });
        }) };
      },
    });
    await advance(2000);
    assert.equal(status.textContent, "Tilkoblet");
    const lastCompletePoll = now;
    mode = "hanging";
    await advance(14000);
    assert.equal(messages.filter((message) => message.command === "connection-lost").length, 0, "short interruptions should not show the recovery dialog");
    await advance(12000);
    const disconnected = messages.filter((message) => message.command === "connection-lost");
    assert.equal(disconnected.length, 1, "a response body that never finishes must be detected as connection loss");
    assert(disconnected[0].at - lastCompletePoll >= 15000);
    assert.equal(maxPendingReads, 1, "periodic polls must not accumulate while a previous read is pending");
    assert(abortedReads > 0, "the blocked response body must be aborted");
    assert.equal(status.textContent, "Pauset");
    assert.equal(paused.classList.contains("visible"), true);
    assert.equal(frame.inert, true);
    assert.equal(focused, "vc-recover");
    callbacks.get("vc-recover:click")();
    assert.equal(paused.classList.contains("visible"), false);
    assert.equal(frame.inert, false);
    assert.equal(focused, "vc-preview");
    await advance(6000);
    assert.equal(paused.classList.contains("visible"), false, "copying the surviving draft must not be interrupted by repeated failures");
    mode = "healthy";
    await advance(8000);
    assert.equal(pendingReads, 0);
    assert.equal(status.textContent, "Tilkoblet");
    assert.equal(messages.filter((message) => message.command === "connection-restored").length, 1);
    assert.equal(paused.classList.contains("visible"), false);
    assert.equal(frame.inert, false);
    assert.equal(frame.src, "unchanged", "recovery must preserve the loaded preview rather than reload its drafts");
  } finally { await stopServer(running); }
});
