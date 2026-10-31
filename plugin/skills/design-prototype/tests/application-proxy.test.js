"use strict";

const assert = require("node:assert/strict");
const http = require("node:http");
const net = require("node:net");
const crypto = require("node:crypto");
const zlib = require("node:zlib");
const vm = require("node:vm");
const { test } = require("node:test");
const { parseApplication } = require("../scripts/application-contract.js");
const { createApplicationProxy, proxyTarget, appCookiesForUpstream, rewriteAppCookie, proxyRequestHeaders, contentSecurityPolicy, instrumentHtml, decodeBody, browserCompatibility, workerCompatibility } = require("../scripts/application-proxy.js");

const UPSTREAM = "http://127.0.0.1:3000";
const PREVIEW = "http://127.0.0.1:4000";
const SHELL = "http://127.0.0.1:5000";
const PREFIX = "dv_app_1234567890abcdef12345678_";
const INSPECTOR = PREVIEW + "/.designverksted/1234567890abcdef12345678/inspect.js";

test("proxy requests cannot select an upstream or reinterpret an absolute target", () => {
  assert.equal(proxyTarget("/syk/demo?mode=detail", UPSTREAM).href, UPSTREAM + "/syk/demo?mode=detail");
  // Dev-server transport tokens are not persisted evidence and must remain usable.
  assert.equal(proxyTarget("/@vite/client?token=transport-only", UPSTREAM).search, "?token=transport-only");
  for (const value of ["//external.test/path", "http://external.test/", "http://127.0.0.1:3001/", "/\\external.test/", "/bad\npath", "/hash#fragment", "", "/" + "x".repeat(17000)]) {
    assert.throws(() => proxyTarget(value, UPSTREAM), /request path is invalid/);
  }
});

test("upstream cookies are allowlisted to one application namespace", () => {
  const incoming = [
    "session=ambient", "dv_preview_own_auth=private", "agentic_ui_shell_other=private",
    "dv_app_other_session=other-app", `${PREFIX}theme=dark`, `${PREFIX}__Host-session=synthetic`,
  ].join("; ");
  assert.equal(appCookiesForUpstream(incoming, PREFIX), "theme=dark; __Host-session=synthetic");
  assert.equal(appCookiesForUpstream("dv_preview_own_auth=private; session=ambient", PREFIX), "");
});

test("application Set-Cookie cannot create a privileged or another instance cookie", () => {
  assert.equal(rewriteAppCookie("__Host-session=synthetic; Secure; HttpOnly; Domain=localhost; Path=/; SameSite=None", PREFIX),
    `${PREFIX}__Host-session=synthetic; HttpOnly; Path=/; SameSite=Strict`);
  assert.equal(rewriteAppCookie("dv_preview_other_auth=forged; Path=/", PREFIX), `${PREFIX}dv_preview_other_auth=forged; Path=/; SameSite=Strict`);
  assert.equal(rewriteAppCookie("theme=light; Max-Age=0; Path=/syk", PREFIX), `${PREFIX}theme=light; Max-Age=0; Path=/syk; SameSite=Strict`);
  assert.equal(rewriteAppCookie("theme=dark; Domain=localhost; SameSite=Strict; Secure; Partitioned; Path=/", PREFIX), `${PREFIX}theme=dark; Path=/; SameSite=Strict`);
  assert.equal(rewriteAppCookie("bad cookie=value", PREFIX), null);
  assert.equal(rewriteAppCookie("ok=x\r\nSet-Cookie: another=y", PREFIX), null);
});

test("request forwarding removes private capabilities and rewrites origin exactly", () => {
  const result = proxyRequestHeaders({
    host: "arbitrary", cookie: `ambient=x; dv_preview_a_auth=x; ${PREFIX}theme=dark`,
    origin: PREVIEW, referer: PREVIEW + "/syk/demo?mode=detail", authorization: "Bearer synthetic-app-token",
    "x-designverksted-token": "private", "x-feedback-mutation": "private", "x-visual-companion-session": "private",
    "x-forwarded-for": "elsewhere", "proxy-authorization": "private", connection: "keep-alive, x-private-hop", "x-private-hop": "private",
    "content-type": "application/json", "accept-encoding": "gzip",
  }, new URL(UPSTREAM), PREVIEW, PREFIX);
  assert.deepEqual(result, {
    host: "127.0.0.1:3000", cookie: "theme=dark", origin: UPSTREAM,
    referer: UPSTREAM + "/syk/demo?mode=detail", authorization: "Bearer synthetic-app-token",
    "content-type": "application/json", "accept-encoding": "identity",
  });
  const spoofed = proxyRequestHeaders({ origin: PREVIEW + ".attacker.test", referer: PREVIEW + ".attacker.test/path" }, new URL(UPSTREAM), PREVIEW, PREFIX);
  assert.equal(spoofed.origin, undefined);
  assert.equal(spoofed.referer, undefined);
});

test("inspector CSP does not broadly enable arbitrary application scripts", () => {
  const policy = contentSecurityPolicy("default-src 'none'; script-src 'sha256-example' 'strict-dynamic'; script-src-elem 'nonce-existing'; connect-src 'self'; frame-ancestors 'none'; upgrade-insecure-requests", SHELL, "inspector-nonce");
  assert.match(policy, /script-src 'sha256-example' 'strict-dynamic';/);
  assert.match(policy, /script-src-elem 'nonce-existing' 'nonce-inspector-nonce'/);
  assert.match(policy, /connect-src 'self'/);
  assert.match(policy, /frame-ancestors http:\/\/127\.0\.0\.1:5000/);
  assert.doesNotMatch(policy, /unsafe-inline|unsafe-eval|upgrade-insecure-requests/);
  assert.equal(contentSecurityPolicy(undefined, SHELL, "n"), `frame-ancestors ${SHELL}`);
  assert.match(contentSecurityPolicy("default-src 'self'", SHELL, "n"), /script-src-elem 'self' 'nonce-n'/);
  assert.throws(() => contentSecurityPolicy("script-src 'none', script-src 'self'", SHELL, "n"), /Multiple application security policies/);
});

test("effective unsafe-inline survives inspector permission without a new nonce source", () => {
  for (const policy of [
    "script-src 'self' 'unsafe-inline'",
    "script-src 'unsafe-inline'",
    "default-src 'self' 'unsafe-inline'",
    "script-src 'none'; script-src-elem 'self' 'unsafe-inline'",
    "script-src 'UNSAFE-INLINE'",
  ]) {
    const result = contentSecurityPolicy(policy, SHELL, "n", INSPECTOR);
    for (const directive of policy.split(";").map(value => value.trim()).filter(value => !value.startsWith("script-src-elem "))) {
      assert.ok(result.split(";").map(value => value.trim()).includes(directive), "Non-element directives remain unchanged");
    }
    assert.doesNotMatch(result, /nonce-n/);
    const elements = result.split(";").find(value => value.trim().startsWith("script-src-elem "));
    assert.ok(elements.includes(INSPECTOR));
    assert.match(elements, /'unsafe-inline'/i);
  }
  assert.throws(() => contentSecurityPolicy("script-src 'unsafe-inline'", SHELL, "n"), /inspector address is invalid/);
  assert.throws(() => contentSecurityPolicy("script-src 'unsafe-inline'", SHELL, "n", INSPECTOR + " 'unsafe-eval'"), /inspector address is invalid/);
});

test("nonce, hash and strict-dynamic policies continue blocking unapproved inline scripts", () => {
  for (const source of ["'nonce-existing'", "'sha256-YWJjZA=='", "'sha384-YWJjZA=='", "'sha512-YWJjZA=='", "'strict-dynamic'"]) {
    const original = `script-src 'self' 'unsafe-inline' ${source}`;
    const result = contentSecurityPolicy(original, SHELL, "n", INSPECTOR);
    assert.ok(result.startsWith(original + ";"));
    assert.ok(result.includes(`script-src-elem 'self' 'unsafe-inline' ${source} 'nonce-n'`));
    assert.ok(!result.includes(INSPECTOR));
  }
});

test("script-src-elem is evaluated independently and script handlers keep their original policy", () => {
  const inlineElements = contentSecurityPolicy("script-src 'nonce-existing'; script-src-elem 'unsafe-inline'; script-src-attr 'none'", SHELL, "n", INSPECTOR);
  assert.ok(inlineElements.includes("script-src 'nonce-existing';"));
  assert.ok(inlineElements.includes(`script-src-elem 'unsafe-inline' ${INSPECTOR}`));
  assert.ok(inlineElements.includes("script-src-attr 'none'"));
  assert.doesNotMatch(inlineElements, /nonce-n/);
  const restrictedElements = contentSecurityPolicy("script-src 'unsafe-inline'; script-src-elem 'none'", SHELL, "n", INSPECTOR);
  assert.ok(restrictedElements.includes("script-src 'unsafe-inline';"));
  assert.ok(restrictedElements.includes("script-src-elem 'nonce-n'"));
  assert.ok(!restrictedElements.includes(INSPECTOR));
});

test("HTML instrumentation preserves application code and adds no control capability", () => {
  const html = `<!doctype html><html lang="nb"><head><meta http-equiv="content-security-policy" content="script-src 'self'"><script src="${UPSTREAM}/assets/main.js"></script></head><body><a href="${UPSTREAM}/syk/demo?view=detail">Prøv</a><script>window.applicationWorks=true</script><a href="${UPSTREAM}.invalid/">Ekstern</a></body></html>`;
  const result = instrumentHtml(html, { upstreamOrigin: UPSTREAM, previewOrigin: PREVIEW, inspectorPath: "/.designverksted/test/inspect.js", nonce: "test-nonce" });
  assert.ok(result.startsWith('<!doctype html><script nonce="test-nonce" src="/.designverksted/test/inspect.js"></script>'));
  assert.match(result, /<html lang="nb">/);
  assert.match(result, /window\.applicationWorks=true/);
  assert.ok(result.includes(PREVIEW + "/assets/main.js"));
  assert.ok(result.includes(PREVIEW + "/syk/demo?view=detail"));
  assert.ok(result.includes(UPSTREAM + ".invalid/"));
  assert.doesNotMatch(result, /dv_preview|dv_app|\/open\/|control-token/);
});

test("compressed documents decode with a hard decompressed limit", async () => {
  const source = Buffer.from("<html lang=nb><body>Ærlig skisse</body></html>");
  for (const [encoding, encode] of [["gzip", zlib.gzipSync], ["deflate", zlib.deflateSync], ["br", zlib.brotliCompressSync]]) {
    assert.deepEqual(await decodeBody(encode(source), encoding), source);
    await assert.rejects(decodeBody(encode(Buffer.alloc(9 * 1024 * 1024, 97)), encoding));
  }
  assert.deepEqual(await decodeBody(zlib.gzipSync(zlib.brotliCompressSync(source)), "br, gzip"), source);
  await assert.rejects(decodeBody(source, "unknown"), /unsupported document encoding/);
});

test("browser transport adapters preserve fetch, API, HMR and logical app cookies", async () => {
  const calls = [], events = {};
  class Document {
    constructor() { this.rawCookie = `${PREFIX}theme=dark; ambient=hidden; dv_preview_secret_auth=hidden`; }
    get cookie() { return this.rawCookie; }
    set cookie(value) { this.lastSetCookie = value; }
    addEventListener(name, listener) { events[name] = listener; }
  }
  class XMLHttpRequest { open(...args) { this.openArguments = args; } }
  class NativeSocket { constructor(...args) { this.arguments = args; } }
  class ServiceWorker { constructor(url) { this.address = url; } get scriptURL() { return this.address; } }
  NativeSocket.OPEN = 1;
  const document = new Document();
  const window = { fetch: (input, init) => { calls.push([input, init]); return Promise.resolve(); }, WebSocket: NativeSocket, EventSource: NativeSocket };
  const history = { pushState(...args) { calls.push(args); }, replaceState(...args) { calls.push(args); } };
  const navigator = { serviceWorker: { register(...args) { calls.push(args); return Promise.resolve({ registered: true }); } } };
  const context = vm.createContext({ Document, XMLHttpRequest, ServiceWorker, document, window, Request, URL, location: new URL(PREVIEW + "/syk/demo"), history, navigator, HTMLAnchorElement: class {}, HTMLFormElement: class {} });
  vm.runInContext(`(${browserCompatibility.toString()})(${JSON.stringify({ upstreamOrigin: UPSTREAM, previewOrigin: PREVIEW, cookiePrefix: PREFIX, workerKey: "synthetic-worker-key" })})`, context);
  await window.fetch(UPSTREAM + "/api/demo", { method: "POST" });
  assert.equal(calls.at(-1)[0], PREVIEW + "/api/demo");
  const source = new Request(UPSTREAM + "/api/form", { method: "POST", body: "synthetic-body", headers: { "content-type": "text/plain" } });
  await window.fetch(source);
  assert.equal(calls.at(-1)[0].url, PREVIEW + "/api/form");
  assert.equal(await calls.at(-1)[0].text(), "synthetic-body");
  await window.fetch("https://public.example.invalid/font");
  assert.equal(calls.at(-1)[0], "https://public.example.invalid/font");
  const xhr = new XMLHttpRequest(); xhr.open("GET", UPSTREAM + "/api/choices", true);
  assert.deepEqual(xhr.openArguments, ["GET", PREVIEW + "/api/choices", true]);
  const socket = new window.WebSocket(UPSTREAM.replace("http:", "ws:") + "/hmr", ["vite-hmr"]);
  assert.equal(socket.arguments[0], PREVIEW.replace("http:", "ws:") + "/hmr");
  assert.deepEqual(socket.arguments[1], ["vite-hmr"]); assert.equal(window.WebSocket.OPEN, 1);
  assert.equal(new window.EventSource(UPSTREAM + "/events").arguments[0], PREVIEW + "/events");
  assert.equal(document.cookie, "theme=dark");
  document.cookie = "theme=light; Path=/; Domain=localhost; Secure; SameSite=None";
  assert.equal(document.lastSetCookie, PREFIX + "theme=light; Path=/; SameSite=Strict");
  history.pushState({}, "", UPSTREAM + "/syk/next");
  assert.equal(calls.at(-1)[2], PREVIEW + "/syk/next");
  await navigator.serviceWorker.register(UPSTREAM + "/sw.js", { scope: UPSTREAM + "/syk/", type: "module" });
  assert.equal(calls.at(-1)[0], PREVIEW + "/sw.js?__designverksted_worker=synthetic-worker-key");
  assert.equal(calls.at(-1)[1].scope, PREVIEW + "/syk/");
  assert.equal(calls.at(-1)[1].type, "module");
  await navigator.serviceWorker.register("/sw.js?version=space%20value");
  assert.equal(calls.at(-1)[0], PREVIEW + "/sw.js?version=space%20value&__designverksted_worker=synthetic-worker-key");
  assert.equal(new ServiceWorker(calls.at(-1)[0]).scriptURL, PREVIEW + "/sw.js?version=space%20value");
  await assert.rejects(navigator.serviceWorker.register("/sw.js?__designverksted_worker=existing"), /reserved preview parameter/);
});

test("invalid configuration fails before opening a listener", async () => {
  for (const options of [
    { application: { name: "Demo", url: "https://external.test" } },
    { application: { name: "Demo", url: UPSTREAM, origin: "http://127.0.0.1:3001" } },
    { application: { name: "Demo", url: UPSTREAM, startPath: "/wrong" } },
    { application: { name: "Demo", url: UPSTREAM }, shellOrigin: "https://external.test" },
    { application: { name: "Demo", url: UPSTREAM }, shellOrigin: "http://localhost:5000" },
    { application: { name: "Demo", url: UPSTREAM }, shellOrigin: "http://127.0.0.2:5000" },
  ]) {
    await assert.rejects(createApplicationProxy({ shellOrigin: SHELL, inspectorSource: "", ...options }), /address is invalid/);
  }
  await assert.rejects(createApplicationProxy({ application: { name: "Demo", url: UPSTREAM }, shellOrigin: SHELL, inspectorSource: "x".repeat(300000) }), /inspector configuration is invalid/);
  await assert.rejects(createApplicationProxy({ application: { name: "Demo", url: UPSTREAM }, shellOrigin: SHELL, inspectorSource: "", onStatus: "wrong" }), /inspector configuration is invalid/);
  await assert.rejects(createApplicationProxy({ application: { name: "Demo", url: UPSTREAM }, shellOrigin: SHELL, inspectorSource: "", diagnosticEpoch: "untrusted-script" }), /inspector configuration is invalid/);
});

test("worker passthrough adds its capability only to its own origin and preserves request bodies", async () => {
  const calls = [];
  const self = { location: new URL(PREVIEW + "/worker.js"), fetch: (...args) => { calls.push(args); return Promise.resolve(); } };
  const context = vm.createContext({ self, Request, Headers, URL });
  vm.runInContext(`(${workerCompatibility.toString()})(${JSON.stringify({ previewOrigin: PREVIEW, workerTransportKey: "worker-only" })})`, context);
  await self.fetch(new Request(PREVIEW + "/api/demo", { method: "POST", body: "synthetic-body", headers: { "content-type": "text/plain", "x-designverksted-worker-navigation": "forged" } }));
  assert.equal(calls[0][0].headers.get("x-designverksted-worker"), "worker-only");
  assert.equal(calls[0][0].headers.get("x-designverksted-worker-navigation"), null);
  assert.equal(calls[0][0].method, "POST"); assert.equal(await calls[0][0].text(), "synthetic-body");
  const external = new Request("https://external.invalid/demo", { method: "POST", body: "outside" });
  await self.fetch(external);
  assert.equal(calls[1][0], external); assert.equal(external.bodyUsed, false);
  assert.equal(external.headers.get("x-designverksted-worker"), null);
});

async function fixture(t, handler, startPath = "/syk/demo?mode=detail", options = {}) {
  const { listenHost = "127.0.0.1", applicationHost = listenHost, ...proxyOptions } = options;
  const sockets = new Set();
  const server = http.createServer(handler);
  server.on("connection", socket => { sockets.add(socket); socket.on("close", () => sockets.delete(socket)); });
  await new Promise((resolve, reject) => { server.once("error", reject); server.listen(0, listenHost, resolve); });
  t.after(async () => { for (const socket of sockets) socket.destroy(); await new Promise(resolve => server.close(resolve)); });
  const upstreamOrigin = `http://${net.isIP(applicationHost) === 6 ? `[${applicationHost}]` : applicationHost}:${server.address().port}`;
  const proxy = await createApplicationProxy({ application: parseApplication({ name: "Syntetisk demo", url: upstreamOrigin + startPath }), shellOrigin: SHELL, inspectorSource: "window.inspectorLoaded = true;", ...proxyOptions });
  t.after(() => proxy.close());
  const bootstrap = await request(proxy.url);
  assert.equal(bootstrap.status, 303);
  const cookie = bootstrap.headers["set-cookie"][0].split(";")[0];
  return { server, proxy, upstreamOrigin, bootstrap, cookie,
    request: (path, options = {}) => request(proxy.origin + path, { ...options, headers: { cookie, ...options.headers } }),
  };
}
function request(url, { method = "GET", headers = {}, body, rawPath } = {}) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const outgoing = http.request({ hostname: "127.0.0.1", port: parsed.port, path: rawPath || parsed.pathname + parsed.search, method, headers: { host: parsed.host, ...headers }, agent: false }, response => {
      const chunks = [];
      response.on("data", chunk => chunks.push(chunk));
      response.on("end", () => resolve({ status: response.statusCode, headers: response.headers, body: Buffer.concat(chunks).toString("utf8") }));
      response.on("error", reject);
    });
    outgoing.setTimeout(5000, () => outgoing.destroy(new Error("test request timed out")));
    outgoing.on("error", reject); outgoing.end(body);
  });
}

test("owned server: bootstrap preserves basepath/query and serves actual app code", async t => {
  const seen = [];
  const f = await fixture(t, (req, res) => {
    seen.push(req.url);
    if (req.url === "/assets/main.js") { res.writeHead(200, { "Content-Type": "text/javascript" }); res.end("window.realApplication=true;"); return; }
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": "default-src 'self'; script-src 'self'" });
    res.end('<!doctype html><html><head><script src="/assets/main.js"></script></head><body>Demo</body></html>');
  });
  assert.equal(f.bootstrap.headers.location, "/syk/demo?mode=detail");
  assert.equal(new URL(f.proxy.origin).hostname, "127.0.0.1");
  assert.match(f.bootstrap.headers["set-cookie"][0], /HttpOnly; SameSite=Strict; Path=\/$/);
  const invitation = new URL(f.proxy.url).pathname.split("/").at(-1);
  assert.notEqual(f.cookie.split("=")[1], invitation, "The invitation is never stored as the browser credential");
  assert.equal((await request(f.proxy.origin + "/", { headers: { cookie: f.cookie.split("=")[0] + "=" + invitation } })).status, 403);
  const result = await f.request(f.bootstrap.headers.location);
  assert.equal(result.status, 200);
  assert.deepEqual(seen, ["/syk/demo?mode=detail"]);
  assert.match(result.body, /<script src="\/assets\/main\.js"><\/script>/);
  const inspectorPath = /src="([^\"]+\/inspect\.js)"/.exec(result.body)[1];
  const inspector = await f.request(inspectorPath);
  assert.equal(inspector.status, 200);
  assert.match(inspector.body, /window\.inspectorLoaded = true/);
  assert.ok(!inspector.body.includes(f.cookie.split("=")[1]));
  assert.ok(!inspector.body.includes(f.proxy.url));
  assert.equal((await f.request("/assets/main.js")).body, "window.realApplication=true;");
  assert.match(result.headers["content-security-policy"], /frame-ancestors http:\/\/127\.0\.0\.1:5000/);
});

test("owned server: localhost works with an upstream bound only to IPv4", async t => {
  const f = await fixture(t, (_req, res) => res.end("IPv4 application"), "/", { applicationHost: "localhost" });
  assert.equal((await f.request("/")).body, "IPv4 application");
});

test("owned server: localhost works with an upstream bound only to IPv6", async t => {
  let f;
  try { f = await fixture(t, (_req, res) => res.end("IPv6 application"), "/", { listenHost: "::1", applicationHost: "localhost" }); }
  catch (error) {
    if (["EAFNOSUPPORT", "EADDRNOTAVAIL"].includes(error.code)) { t.skip("IPv6 loopback is unavailable on this host"); return; }
    throw error;
  }
  assert.equal((await f.request("/")).body, "IPv6 application");
});

test("owned server: wrong Host/Origin and forged transport cannot touch upstream", async t => {
  let touched = 0;
  const f = await fixture(t, (_req, res) => { touched += 1; res.end("application"); });
  assert.equal((await request(f.proxy.origin + "/")).status, 403);
  assert.equal((await f.request("/", { headers: { host: "external.test" } })).status, 403);
  assert.equal((await f.request("/", { headers: { origin: "http://127.0.0.1:9999" } })).status, 403);
  assert.equal((await f.request("/", { method: "POST" })).status, 403);
  assert.equal((await f.request("/", { method: "POST", headers: { origin: "null" } })).status, 403);
  assert.equal((await f.request("/", { rawPath: "http://external.test/" })).status, 400);
  assert.equal((await f.request("/", { rawPath: "//external.test/" })).status, 400);
  assert.equal((await request(f.proxy.origin + "/worker.js", { headers: { "service-worker": "script" } })).status, 403);
  assert.equal(touched, 0);
  assert.equal((await f.request("/", { method: "POST", headers: { origin: f.proxy.origin } })).status, 200);
  assert.equal(touched, 1);
});

test("owned server: application workers keep their code and cannot claim an external scope", async t => {
  const source = "self.addEventListener('fetch', () => {});";
  const f = await fixture(t, (req, res) => {
    res.writeHead(200, { "Content-Type": "text/javascript", "Service-Worker-Allowed": req.url === "/external.js" ? "https://external.invalid/" : "../" });
    res.end(source);
  });
  const result = await f.request("/syk/mockServiceWorker.js", { headers: { "service-worker": "script", "sec-fetch-dest": "serviceworker" } });
  assert.equal(result.status, 200);
  assert.equal(result.body, source);
  assert.equal(result.headers["service-worker-allowed"], f.proxy.origin + "/");
  assert.equal((await f.request("/external.js", { headers: { "service-worker": "script" } })).status, 502);
});

test("owned server: cookie-free worker capability grants only a same-origin JavaScript retrieval", async t => {
  const seen = [], receivedHeaders = [];
  const f = await fixture(t, (req, res) => {
    seen.push(req.url);
    receivedHeaders.push(req.headers);
    if (req.url === "/" || req.url === "/html.js") { res.writeHead(200, { "Content-Type": "text/html" }); res.end("<!doctype html><p>Demo</p>"); return; }
    res.writeHead(200, { "Content-Type": "text/javascript", "Service-Worker-Allowed": req.url === "/external.js" ? "https://external.invalid/" : "/" });
    res.end("self.addEventListener('fetch', () => {});");
  });
  const document = await f.request("/");
  const inspectorPath = /src="([^\"]+\/inspect\.js)"/.exec(document.body)[1];
  const inspector = await f.request(inspectorPath);
  const key = /"workerKey":"([a-zA-Z0-9_-]+)"/.exec(inspector.body)[1];
  assert.ok(!f.cookie.includes(key) && !f.proxy.url.includes(key), "Worker and transport capabilities are separate");
  const headers = { "service-worker": "script", "sec-fetch-dest": "serviceworker", "sec-fetch-mode": "same-origin", "sec-fetch-site": "same-origin" };
  const address = path => f.proxy.origin + path + "?__designverksted_worker=" + key;
  assert.equal((await request(f.proxy.origin + "/worker.js", { headers })).status, 403);
  assert.equal((await request(f.proxy.origin + "/worker.js?__designverksted_worker=wrong", { headers })).status, 403);
  assert.equal((await request(address("/worker.js"))).status, 403);
  assert.equal((await request(address("/worker.js"), { headers: { cookie: f.cookie } })).status, 403);
  assert.equal((await request(address("/worker.js"), { method: "POST", headers })).status, 403);
  assert.equal((await request(address("/worker.js"), { headers: { ...headers, origin: SHELL } })).status, 403);
  assert.equal((await request(address("/worker.js"), { headers: { ...headers, host: new URL(f.proxy.origin).host.replace("127.0.0.1", "localhost") } })).status, 403);
  assert.equal((await request(address("/worker.js") + "&__designverksted_worker=" + key, { headers })).status, 403);
  assert.equal((await request(address(inspectorPath), { headers })).status, 403);
  assert.deepEqual(seen, ["/"]);
  const allowed = await request(address("/worker.js"), { headers });
  assert.equal(allowed.status, 200); assert.ok(allowed.body.endsWith("self.addEventListener('fetch', () => {});"));
  assert.equal(seen.at(-1), "/worker.js", "The capability never reaches upstream");
  const transportKey = /"workerTransportKey":"([a-zA-Z0-9_-]+)"/.exec(allowed.body)[1];
  assert.ok(!inspector.body.includes(transportKey) && transportKey !== key && !f.cookie.includes(transportKey));
  const transportHeaders = { "x-designverksted-worker": transportKey, "sec-fetch-site": "same-origin", origin: f.proxy.origin };
  assert.equal((await request(f.proxy.origin + "/api/demo", { method: "POST", headers: transportHeaders, body: "synthetic" })).status, 200);
  assert.equal(receivedHeaders.at(-1)["x-designverksted-worker"], undefined);
  assert.equal(receivedHeaders.at(-1).origin, f.upstreamOrigin);
  assert.equal((await request(f.proxy.origin + "/api/demo", { headers: { ...transportHeaders, "x-designverksted-worker": key } })).status, 403);
  assert.equal((await request(f.proxy.origin + "/api/demo", { headers: { ...transportHeaders, "sec-fetch-site": "cross-site" } })).status, 403);
  assert.equal((await request(f.proxy.origin + "/api/demo", { headers: { ...transportHeaders, origin: SHELL } })).status, 403);
  assert.equal((await request(f.proxy.origin + inspectorPath, { headers: transportHeaders })).status, 403);
  assert.equal((await request(address("/worker.js") + "&version=space%20value", { headers })).status, 200);
  assert.equal(seen.at(-1), "/worker.js?version=space%20value");
  assert.equal((await request(address("/html.js"), { headers })).status, 502);
  assert.equal((await request(address("/external.js"), { headers })).status, 502);
});

test("owned server: inline app bootstrap remains unchanged under effective unsafe-inline", async t => {
  const source = '<!doctype html><script id="_R_">self.__next_r="synthetic-request"</script><button onclick="window.clicked=true">Demo</button>';
  const f = await fixture(t, (_req, res) => {
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; script-src-elem 'self' 'unsafe-inline'" });
    res.end(source);
  });
  const result = await f.request("/");
  assert.equal(result.status, 200);
  assert.ok(result.body.includes('<script id="_R_">self.__next_r="synthetic-request"</script>'));
  assert.ok(result.body.includes('<button onclick="window.clicked=true">Demo</button>'));
  assert.equal((result.body.match(/nonce=/g) || []).length, 1, "Only the inspector is nonced");
  const inspectorPath = /src="([^\"]+\/inspect\.js)"/.exec(result.body)[1];
  assert.ok(result.headers["content-security-policy"].includes(f.proxy.origin + inspectorPath));
  assert.doesNotMatch(result.headers["content-security-policy"], /'nonce-/);
  assert.equal((await f.request(inspectorPath)).status, 200);
});

test("owned server: POST body, API status and own app cookies survive the proxy", async t => {
  const seen = [];
  const f = await fixture(t, async (req, res) => {
    let body = ""; for await (const chunk of req) body += chunk;
    seen.push({ url: req.url, method: req.method, body, headers: req.headers });
    res.writeHead(201, { "Content-Type": "application/json", "Set-Cookie": ["theme=dark; Path=/", "__Host-session=synthetic; Secure; HttpOnly; Path=/"] });
    res.end(JSON.stringify({ saved: true }));
  });
  const first = await f.request("/api/demo", { method: "POST", body: '{"choice":"phone"}', headers: { origin: f.proxy.origin, "content-type": "application/json", "x-designverksted-token": "private-shell", "x-feedback-mutation": "private-round" } });
  assert.equal(first.status, 201); assert.equal(first.body, '{"saved":true}');
  assert.equal(seen[0].body, '{"choice":"phone"}'); assert.equal(seen[0].method, "POST");
  assert.equal(seen[0].headers.origin, f.upstreamOrigin);
  assert.equal(seen[0].headers.cookie, undefined);
  assert.equal(seen[0].headers["x-designverksted-token"], undefined);
  assert.equal(seen[0].headers["x-feedback-mutation"], undefined);
  const appCookie = first.headers["set-cookie"].map(value => value.split(";")[0]).join("; ");
  await f.request("/api/demo", { headers: { cookie: f.cookie + "; " + appCookie + "; unrelated=ambient; dv_preview_other_auth=secret; dv_app_other_session=other" } });
  assert.equal(seen[1].headers.cookie, "theme=dark; __Host-session=synthetic");
  assert.ok(!seen[1].headers.cookie.includes(f.cookie.split("=")[1]));
});

test("owned server: compressed HTML is bounded, statuses and relative redirects survive", async t => {
  const f = await fixture(t, (req, res) => {
    if (req.url === "/syk/redirect") { res.writeHead(307, { Location: "next?view=detail" }); res.end(); return; }
    if (req.url === "/external") { res.writeHead(302, { Location: "https://example.invalid/login?token=should-not-leak" }); res.end(); return; }
    const content = req.url === "/too-big" ? "x".repeat(9 * 1024 * 1024) : "<!doctype html><html><body>Compressed demo</body></html>";
    res.writeHead(202, { "Content-Type": "text/html; charset=utf-8", "Content-Encoding": "gzip" }); res.end(zlib.gzipSync(content));
  });
  const page = await f.request("/compressed");
  assert.equal(page.status, 202); assert.match(page.body, /Compressed demo/); assert.match(page.body, /\/inspect\.js/);
  assert.equal(page.headers["content-encoding"], undefined);
  const redirect = await f.request("/syk/redirect");
  assert.equal(redirect.status, 307); assert.equal(redirect.headers.location, f.proxy.origin + "/syk/next?view=detail");
  const outside = await f.request("/external");
  assert.equal(outside.status, 502); assert.match(outside.body, /outside its local address/); assert.doesNotMatch(outside.body, /should-not-leak|example\.invalid/);
  const tooBig = await f.request("/too-big"); assert.equal(tooBig.status, 502); assert.doesNotMatch(tooBig.body, /x{30}/);
});

test("owned server: parallel previews isolate cookies and close only their own transport", async t => {
  const seen = [];
  const f = await fixture(t, (req, res) => { seen.push(req.headers.cookie); res.writeHead(200, { "Set-Cookie": "theme=dark; Path=/" }); res.end("ok"); });
  let closed = 0;
  const second = await createApplicationProxy({ application: { name: "Second", url: f.upstreamOrigin }, shellOrigin: SHELL, inspectorSource: "", onClose: () => { closed += 1; } });
  t.after(() => second.close());
  const first = await f.request("/");
  const secondOpen = await request(second.url);
  const secondCookie = secondOpen.headers["set-cookie"][0].split(";")[0];
  await request(second.origin + "/", { headers: { cookie: secondCookie + "; " + first.headers["set-cookie"][0].split(";")[0] + "; " + f.cookie } });
  assert.equal(seen.at(-1), undefined);
  assert.equal((await request(second.origin + "/", { headers: { cookie: f.cookie } })).status, 403);
  await second.close(); await second.close(); assert.equal(closed, 1);
  assert.equal((await f.request("/")).status, 200);
  assert.equal((await request(f.upstreamOrigin)).status, 200);
  await assert.rejects(request(second.origin + "/"));
});

const DOCUMENT_HEADERS = { "sec-fetch-dest": "iframe", "sec-fetch-mode": "navigate", accept: "text/html,application/xhtml+xml" };

test("owned server: stopped upstream gives a shell-readable fixed document and recovers on reload", async t => {
  const statuses = [];
  const f = await fixture(t, (_req, res) => { res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" }); res.end("<!doctype html><body>Demo</body>"); }, "/demo", { onStatus: value => statuses.push(value) });
  assert.deepEqual(statuses, []);
  const first = await f.request("/demo", { headers: DOCUMENT_HEADERS });
  assert.equal(first.status, 200);
  assert.deepEqual(statuses, [{ state: "loading" }, { state: "ready", httpStatus: 200 }]);
  const port = f.server.address().port;
  await new Promise(resolve => { f.server.close(resolve); f.server.closeAllConnections(); });
  await request(f.proxy.url);
  const unavailable = await f.request("/demo", { headers: DOCUMENT_HEADERS });
  assert.equal(unavailable.status, 502);
  assert.match(unavailable.headers["content-type"], /^text\/html/);
  assert.match(unavailable.body, /<html lang="nb">/);
  assert.match(unavailable.body, /Appen kunne ikke vises/);
  assert.doesNotMatch(unavailable.body, /private-test-value|http:|inspect\.js|<script/);
  assert.equal(unavailable.headers["content-security-policy"], `default-src 'none'; frame-ancestors ${SHELL} ${f.proxy.origin}; base-uri 'none'; form-action 'none'`);
  assert.deepEqual(statuses.slice(-2), [{ state: "loading" }, { state: "unavailable", httpStatus: 502, reason: "application-unavailable" }]);
  const count = statuses.length;
  const denied = await request(f.proxy.origin + "/demo", { headers: DOCUMENT_HEADERS });
  assert.equal(denied.status, 403);
  assert.match(denied.headers["content-security-policy"], /frame-ancestors 'none'/);
  assert.equal(statuses.length, count);
  await new Promise((resolve, reject) => { f.server.once("error", reject); f.server.listen(port, "127.0.0.1", resolve); });
  await request(f.proxy.url);
  assert.equal((await f.request("/demo", { headers: DOCUMENT_HEADERS })).status, 200);
  assert.deepEqual(statuses.slice(-2), [{ state: "loading" }, { state: "ready", httpStatus: 200 }]);
  assert(statuses.every(value => Object.isFrozen(value) && Object.keys(value).every(key => ["state", "httpStatus", "reason"].includes(key))));
});

test("owned server: API errors and HTML fetches never change document status", async t => {
  const statuses = [];
  const f = await fixture(t, (req, res) => {
    const status = req.url === "/demo" ? 200 : 404;
    res.writeHead(status, { "Content-Type": req.url === "/api" ? "application/json" : "text/html; charset=utf-8" });
    res.end(req.url === "/api" ? '{"error":"missing"}' : "<!doctype html><body>Demo</body>");
  }, "/demo", { onStatus: value => { statuses.push(value); if (value.state === "loading") throw new Error("observer unavailable"); return Promise.reject(new Error("observer unavailable")); } });
  assert.equal((await f.request("/demo", { headers: DOCUMENT_HEADERS })).status, 200);
  const count = statuses.length;
  assert.equal((await f.request("/api")).status, 404);
  assert.equal((await f.request("/fragment", { headers: { accept: "text/html", "sec-fetch-dest": "empty", "sec-fetch-mode": "same-origin" } })).status, 404);
  assert.equal(statuses.length, count);
  assert.equal((await f.request("/missing-page", { headers: DOCUMENT_HEADERS })).status, 404);
  assert.equal(statuses.length, count, "Unclassified nested documents cannot replace the main view status");
  await request(f.proxy.url);
  assert.equal((await f.request("/demo", { headers: { accept: "text/html" } })).status, 200);
  assert.deepEqual(statuses.slice(-2), [{ state: "loading" }, { state: "ready", httpStatus: 200 }]);
});

test("denied document diagnostics answer only the owning view challenge without changing transport", async t => {
  const statuses = [], epoch = "e".repeat(32);
  const f = await fixture(t, (_req, res) => { res.writeHead(200, { "Content-Type": "text/html" }); res.end("<body>Demo</body>"); }, "/demo", {
    diagnosticEpoch: epoch, onStatus: value => statuses.push(value),
  });
  await f.request("/demo", { headers: DOCUMENT_HEADERS });
  const before = structuredClone(statuses);
  for (const [reason, headers] of [
    ["preview-cookie-unavailable", { ...DOCUMENT_HEADERS }],
    ["preview-origin-rejected", { ...DOCUMENT_HEADERS, cookie: f.cookie, origin: "http://localhost:9999" }],
  ]) {
    const denied = await request(f.proxy.origin + "/demo?private-test-value=omitted", { headers });
    assert.equal(denied.status, 403);
    assert.match(denied.headers["content-type"], /^text\/html/);
    assert.doesNotMatch(denied.body, /private-test-value|inspect\.js|design-view-ready|dv_preview_|dv_app_/);
    const script = /<script nonce="([^"]+)">([\s\S]*?)<\/script>/.exec(denied.body);
    assert.ok(script, "A denied document can explain failure to its current owner");
    assert.ok(denied.headers["content-security-policy"].includes(`script-src 'nonce-${script[1]}'`));
    const sent = [], listeners = {}, parent = { postMessage: (value, origin) => sent.push({ value, origin }) };
    vm.runInNewContext(script[2], { window: { parent, addEventListener: (name, listener) => { listeners[name] = listener; } } });
    assert.deepEqual(sent, [], "The error document never reports an unsolicited failure");
    const challenge = { type: "check-view", epoch, view: "a".repeat(32) };
    for (const event of [
      { source: {}, origin: SHELL, data: challenge },
      { source: parent, origin: f.proxy.origin, data: challenge },
      { source: parent, origin: SHELL, data: { ...challenge, epoch: "b".repeat(32) } },
      { source: parent, origin: SHELL, data: { ...challenge, view: "invalid" } },
      { source: parent, origin: SHELL, data: { ...challenge, extra: true } },
    ]) listeners.message(event);
    assert.equal(sent.length, 0);
    listeners.message({ source: parent, origin: SHELL, data: challenge });
    assert.deepEqual(JSON.parse(JSON.stringify(sent)), [{ origin: SHELL, value: { type: "design-view-error", epoch, view: challenge.view, reason, httpStatus: 403 } }]);
    assert.deepEqual(statuses, before, "A nested or background denial cannot poison the active app status");
  }
  const background = await request(f.proxy.origin + "/demo", { headers: { accept: "text/html", "sec-fetch-dest": "empty", "sec-fetch-mode": "same-origin" } });
  assert.equal(background.status, 403); assert.doesNotMatch(background.body, /<script/);
  assert.deepEqual(statuses, before);
});

test("document error categories retain fixed diagnostics and ignore nested failures", async t => {
  const statuses = [], epoch = "e".repeat(32);
  const f = await fixture(t, (req, res) => {
    if (req.url === "/invalid") { res.writeHead(200, { "Content-Type": "text/html; charset=unsupported" }); res.end("private-test-value"); return; }
    res.writeHead(req.url === "/demo" ? 200 : 404, { "Content-Type": "text/html" }); res.end("private-test-value");
  }, "/demo", { diagnosticEpoch: epoch, onStatus: value => statuses.push(value) });
  await f.request("/demo", { headers: DOCUMENT_HEADERS });
  const before = structuredClone(statuses);
  for (const [pathname, reason, status] of [["/missing", "application-http-error", 404], ["/invalid", "application-response-rejected", 502]]) {
    const failed = await f.request(pathname, { headers: DOCUMENT_HEADERS });
    assert.equal(failed.status, status);
    assert.ok(failed.body.includes(`"reason":"${reason}","httpStatus":${status}`));
    assert.doesNotMatch(failed.body, /private-test-value|design-view-ready|inspect\.js/);
    assert.deepEqual(statuses, before, "Only the owning shell can correlate this later document failure");
  }
});

test("owned server: nested documents keep their own errors without replacing the app status", async t => {
  const statuses = [];
  const f = await fixture(t, (req, res) => {
    if (req.url === "/attachment") { res.writeHead(200, { "Content-Type": "application/json" }); res.end('{"synthetic":"attachment"}'); return; }
    res.writeHead(req.url === "/missing" ? 404 : 200, { "Content-Type": "text/html; charset=utf-8" });
    res.end("<!doctype html><body>Nested demo</body>");
  }, "/demo", { onStatus: value => statuses.push(value) });
  await f.request("/demo", { headers: DOCUMENT_HEADERS });
  const mainStatus = structuredClone(statuses);
  for (const route of ["/nested", "/attachment", "/missing"]) {
    const nested = await f.request(route, { headers: { ...DOCUMENT_HEADERS, referer: f.proxy.origin + "/demo" } });
    assert.match(nested.headers["content-security-policy"], new RegExp(`frame-ancestors ${SHELL.replaceAll(".", "\\.")} ${f.proxy.origin}`));
    if (route === "/missing") {
      assert.equal(nested.status, 404);
      assert.match(nested.body, /Appen kunne ikke vises/);
      assert.doesNotMatch(nested.body, /inspect\.js|<script/, "Failed main or nested documents cannot claim inspector readiness");
    }
  }
  assert.deepEqual(statuses, mainStatus);
});

test("owned server: bootstrap redirects retain status until the selected document is complete", async t => {
  const statuses = [];
  const f = await fixture(t, (req, res) => {
    if (req.url === "/start") { res.writeHead(302, { Location: "/demo" }); res.end(); return; }
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" }); res.end("<!doctype html><body>Demo</body>");
  }, "/start", { onStatus: value => statuses.push(value) });
  const redirect = await f.request("/start", { headers: DOCUMENT_HEADERS });
  assert.equal(redirect.status, 302); assert.deepEqual(statuses, [{ state: "loading" }]);
  await f.request("/nested", { headers: DOCUMENT_HEADERS });
  assert.deepEqual(statuses, [{ state: "loading" }]);
  await f.request(new URL(redirect.headers.location).pathname, { headers: DOCUMENT_HEADERS });
  assert.deepEqual(statuses, [{ state: "loading" }, { state: "ready", httpStatus: 200 }]);
});

test("owned server: an older bootstrap document cannot replace the latest view status", async t => {
  const statuses = [];
  let release, started, first = true;
  const pending = new Promise(resolve => { started = resolve; });
  const f = await fixture(t, (req, res) => {
    if (first) { first = false; release = () => { res.writeHead(503, { "Content-Type": "text/html; charset=utf-8" }); res.end("<body>Old response</body>"); }; started(); return; }
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" }); res.end("<body>Current response</body>");
  }, "/demo", { onStatus: value => statuses.push(value) });
  const old = f.request("/demo", { headers: DOCUMENT_HEADERS });
  await pending;
  await request(f.proxy.url);
  assert.equal((await f.request("/demo", { headers: DOCUMENT_HEADERS })).status, 200);
  release(); assert.equal((await old).status, 503);
  assert.deepEqual(statuses, [{ state: "loading" }, { state: "ready", httpStatus: 200 }]);
});

function upgrade(url, headers) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url), socket = net.connect(Number(parsed.port), "127.0.0.1");
    const timer = setTimeout(() => { socket.destroy(); reject(new Error("upgrade test timed out")); }, 5000);
    let result = "";
    socket.once("connect", () => socket.write(`GET ${parsed.pathname} HTTP/1.1\r\nHost: ${parsed.host}\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n${Object.entries(headers).map(([name, value]) => `${name}: ${value}\r\n`).join("")}\r\n`));
    socket.on("data", chunk => { result += chunk.toString("utf8"); if (result.includes("\r\n\r\n")) { clearTimeout(timer); resolve({ result, socket }); } });
    socket.once("error", error => { clearTimeout(timer); reject(error); });
    socket.once("end", () => { if (!result.includes("\r\n\r\n")) { clearTimeout(timer); reject(new Error("upgrade ended without headers")); } });
  });
}

test("owned server: WebSocket HMR uses the same bound origin and strips private cookies", async t => {
  const f = await fixture(t, (_req, res) => res.end("ok"));
  const seen = [];
  f.server.on("upgrade", (req, socket) => {
    seen.push(req.headers);
    const accept = crypto.createHash("sha1").update(req.headers["sec-websocket-key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest("base64");
    socket.write(`HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ${accept}\r\n\r\n`);
  });
  const denied = await upgrade(f.proxy.origin + "/hmr", { Cookie: f.cookie, Origin: "http://127.0.0.1:9999" });
  denied.socket.destroy(); assert.match(denied.result, /^HTTP\/1\.1 403/); assert.equal(seen.length, 0);
  const allowed = await upgrade(f.proxy.origin + "/hmr", { Cookie: f.cookie + "; ambient=private", Origin: f.proxy.origin });
  assert.match(allowed.result, /^HTTP\/1\.1 101/); assert.equal(seen.length, 1);
  assert.equal(seen[0].cookie, undefined); assert.equal(seen[0].origin, f.upstreamOrigin);
  const closed = new Promise(resolve => allowed.socket.once("close", resolve));
  await f.proxy.close(); await closed;
});

test("owned server: aborted pending and denied upgrades leave the transport available", async t => {
  const f = await fixture(t, (_req, res) => res.end("still available"));
  let waiting = 0, sequence = 0;
  const pending = new Map();
  f.server.on("upgrade", (req, socket) => {
    waiting += 1;
    pending.get(req.headers["x-test-handshake"])?.();
    socket.on("error", () => socket.destroy());
    const timer = setTimeout(() => socket.end("HTTP/1.1 503 Unavailable\r\nConnection: close\r\n\r\n"), 50);
    socket.once("close", () => clearTimeout(timer));
  });
  async function abortHandshake(allowed) {
    const url = new URL(f.proxy.origin);
    await new Promise((resolve, reject) => {
      const id = String(++sequence), socket = net.connect(Number(url.port), "127.0.0.1");
      const timer = setTimeout(() => { socket.destroy(); reject(new Error("Upstream handshake was not reached")); }, 5000);
      if (allowed) pending.set(id, () => { if (!socket.destroyed) socket.resetAndDestroy(); });
      socket.on("error", () => socket.destroy());
      socket.once("close", () => { clearTimeout(timer); pending.delete(id); resolve(); });
      socket.once("connect", () => {
        socket.write(`GET /hmr HTTP/1.1\r\nHost: ${url.host}\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\nX-Test-Handshake: ${id}\r\nCookie: ${f.cookie}\r\nOrigin: ${allowed ? f.proxy.origin : "http://127.0.0.1:9999"}\r\n\r\n`, () => {
          // Authorized resets wait for the actual upstream upgrade event;
          // scheduling speed must not turn this into only denied requests.
          if (!allowed && !socket.destroyed) socket.resetAndDestroy();
        });
      });
    });
  }
  for (let batch = 0; batch < 10; batch += 1) await Promise.all(Array.from({ length: 20 }, (_, index) => abortHandshake(index % 2 === 0)));
  assert.equal(waiting, 100, "Every authorized reset reached a real pending upstream handshake");
  assert.equal((await f.request("/health")).body, "still available");
});
