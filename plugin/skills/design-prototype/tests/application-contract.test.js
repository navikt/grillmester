"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { parseApplication, normalizeApplicationRoute, normalizeResourceQueryKeys, validApplicationRoute, validApplicationScreen, validApplicationContext, screenIdentity } = require("../scripts/application-contract.js");

const checkpoint = "a".repeat(64);
const parse = url => parseApplication({ name: "Møtevalg", url });
const reject = error => error.status === 400;
const context = () => ({ route: "/syk/dialogmoter?view=kort", target: { tag: "button", role: "button", name: "Neste", text: "Neste", path: "main:nth-of-type(1) > button:nth-of-type(2)" }, viewport: { width: 375, height: 812, scrollX: 0, scrollY: 120 } });

test("application input preserves local start routes and normalizes benign query encoding", () => {
  assert.deepEqual(parseApplication({ name: "  Møtevalg  ", url: "HTTP://LOCALHOST:3000/syk/dialogmoter?view=kort&q=to%20ord" }), {
    name: "Møtevalg", url: "http://localhost:3000/syk/dialogmoter?view=kort&q=to+ord", origin: "http://localhost:3000", startPath: "/syk/dialogmoter?view=kort&q=to+ord",
  });
  assert.equal(parse("https://localhost:443").url, "https://localhost/");
  assert.equal(parse("http://127.0.0.1:8080/?").startPath, "/");
  assert.equal(parse("http://localhost/søknad?q=æøå").startPath, "/s%C3%B8knad?q=%C3%A6%C3%B8%C3%A5");
});

test("only canonical loopback authorities and valid ports are accepted", () => {
  for (const host of ["localhost", "127.0.0.1", "127.12.34.56", "[::1]", "[0:0:0:0:0:0:0:1]"]) assert.equal(parse(`http://${host}:3000/`).startPath, "/", host);
  assert.equal(parse("https://[0:0:0:0:0:0:0:1]:8443/app").origin, "https://[::1]:8443");
  for (const url of ["file:///tmp/demo", "ftp://localhost/demo", "http://example.org", "http://localhost.example.org", "http://localhost.", "http://0.0.0.0", "http://192.168.1.1", "http://[::]", "http://[::ffff:127.0.0.1]", "http://127.1", "http://2130706433", "http://0x7f000001", "http://127.000.0.1", "http://127.0.0.256", "http://%6cocalhost", "http://localhost:", "http://localhost:0", "http://localhost:00080", "http://localhost:65536", "http://localhost:abc", "http://user@localhost", "http://user:pass@localhost", "http://localhost#", "http://localhost/#section", "http://localhost\\@example.org/", " http://localhost", "http://localhost\n"]) assert.throws(() => parse(url), reject, url);
});

test("URL and name shape, control characters and UTF-8 byte bounds are enforced", () => {
  for (const value of [null, [], {}, { name: "Demo" }, { name: "Demo", url: "http://localhost", origin: "http://example.org" }, { name: " ", url: "http://localhost" }, { name: "x\n", url: "http://localhost" }, { name: "x\u202e", url: "http://localhost" }, { name: "\ud800", url: "http://localhost" }, { name: "ø".repeat(101), url: "http://localhost" }]) assert.throws(() => parseApplication(value), reject);
  assert.equal(parseApplication({ name: "ø".repeat(100), url: "http://localhost" }).name.length, 100);
  assert.throws(() => parse(`http://localhost/${"x".repeat(4096)}`), reject);
  assert.throws(() => parse("http://localhost/\u0085"), reject);
});

test("routes reject traversal, repaired authorities, invalid UTF-8 and nested escapes", () => {
  for (const route of ["", "app", "http://localhost/app", "//localhost/app", "/\\example.org", "/a/../b", "/a/./b", "/a/%2e%2e/b", "/a/.%2e/b", "/a/%252e%252e/b", "/a%2fb", "/%5cfoo", "/a#b", "/a%3fb", "/%00", "/%0a", "/%7f", "/%C0%AE", "/%E0%A4%A", "/bad%", "/\ud800", "/a?q=%E0%A4%A", "/a?q=%", `/${"a".repeat(2048)}`]) {
    assert.equal(validApplicationRoute(route), false, route);
    if (route) assert.throws(() => parse(`http://localhost${route}`), reject, route);
  }
  for (const route of ["/", "/a/b/", "/.well-known/example", "/søknad", "/app?view=kort&step=2&lang=nb-NO", "/app?q=to+ord", "/app?q=", "/app?"]) assert.equal(validApplicationRoute(route), true, route);
});

test("sensitive and ambiguous query names are rejected without including their values in errors", () => {
  const secret = "private-example-value";
  for (const name of ["token", "access_token", "Id-Token", "refresh.token", "auth", "authorization", "password", "client_secret", "sessionId", "csrf", "xsrf", "code", "state", "apiKey", "key", "sig", "nonce", "jwt", "SAMLResponse", "redirect_uri", "returnUrl", "email", "fnr", "personident", "fodselsnummer", "%74oken", "%2574oken"]) {
    assert.throws(() => parse(`http://localhost/app?${name}=${secret}`), error => {
      assert.equal(error.status, 400); assert(!error.message.includes(secret)); assert(!error.message.includes("http://")); assert(!error.message.includes("token=")); return true;
    }, name);
  }
  for (const query of ["view=kort&view=lang", "view=kort&VIEW=lang", "=kort", "view[]=kort", "1view=kort", Array.from({ length: 17 }, (_, i) => `p${i}=x`).join("&")]) assert.equal(validApplicationRoute(`/app?${query}`), false, query);
});

test("opaque credentials, identifying values and nested URL payloads cannot enter saved routes", () => {
  const values = ["Bearer example", "Basic dXNlcjpwYXNz", "eyJhbGciOiJIUzI1NiJ9.e30.signature", "123e4567-e89b-12d3-a456-426614174000", "abcdefghijklmnopqrstuvwxyz", "ghp_example", "github_pat_example", "sk_example", "0".repeat(11), "someone@example.test", "https://example.test", "//example.test", "%74oken", "[private]", "<script>", "{\"x\":1}", "x\n", "x\u0085", "ø".repeat(101)];
  for (const value of values) assert.equal(validApplicationRoute(`/app?view=${encodeURIComponent(value)}`), false, value);
  assert.equal(validApplicationRoute("/app?q=sammenlign+kort+og+lang+forklaring"), true);
});

test("application screen identity is deterministic, normalized, source-bound and independent of origin", () => {
  const route = "/app?q=to%20ord";
  const screen = screenIdentity(checkpoint, route);
  assert.match(screen, /^[a-f0-9]{32}$/);
  assert.equal(screen, screenIdentity(checkpoint, "/app?q=to+ord"));
  assert.equal(normalizeApplicationRoute("/app?q=to%20ord"), normalizeApplicationRoute("/app?q=to+ord"));
  assert.equal(normalizeApplicationRoute("/søknad?q=æøå"), normalizeApplicationRoute("/s%C3%B8knad?q=%C3%A6%C3%B8%C3%A5"));
  assert.notEqual(screen, screenIdentity("b".repeat(64), route));
  assert.notEqual(screen, screenIdentity(checkpoint, "/next"));
  assert.equal(screenIdentity(checkpoint, parse("http://localhost:3000/app").startPath), screenIdentity(checkpoint, parse("http://127.0.0.1:4000/app").startPath));
  for (const hash of [null, "A".repeat(64), "a".repeat(63), "a".repeat(65), "x".repeat(64)]) assert.throws(() => screenIdentity(hash, "/"), reject);
  assert.throws(() => screenIdentity(checkpoint, "/?token=private"), reject);
});

test("application screens have a closed source union and a matching identity", () => {
  const good = { screen: screenIdentity(checkpoint, "/app"), source: { kind: "application", checkpoint, route: "/app" } };
  assert.equal(validApplicationScreen(good), true);
  for (const value of [null, {}, { ...good, filename: "app.html" }, { ...good, screen: "0".repeat(32) }, { ...good, source: { ...good.source, url: "http://localhost" } }, { ...good, source: { ...good.source, kind: "html" } }, { ...good, source: { ...good.source, checkpoint: "x".repeat(64) } }, { ...good, source: { ...good.source, route: "/?token=private" } }]) assert.equal(validApplicationScreen(value), false);
});

test("bounded target evidence describes elements without accepting selectors, source paths or write authority", () => {
  assert.equal(validApplicationContext(context()), true);
  const changes = [
    value => { value.extra = true; }, value => { value.route = "https://example.org"; }, value => { value.route = "/?token=private"; },
    value => { value.target.selector = "#main"; }, value => { value.target.file = "src/main.tsx"; }, value => { value.target.value = "private"; },
    value => { value.target.tag = "BUTTON"; }, value => { value.target.tag = "a b"; }, value => { value.target.role = "arbitrary"; },
    value => { value.target.path = "button:nth-of-type(0)"; }, value => { value.target.path = "button:nth-of-type(1000000)"; }, value => { value.target.path = "#submit"; },
    value => { value.target.path = "button:nth-of-type(1)[onclick]"; }, value => { value.target.path = "a:nth-of-type(1), button:nth-of-type(1)"; },
    value => { value.target.name = "ø".repeat(121); }, value => { value.target.text = "ø".repeat(501); }, value => { value.target.name = "\ud800"; },
    value => { value.target.text = "x\u202e"; }, value => { value.viewport.scale = 2; }, value => { value.viewport.width = "375"; },
    value => { value.viewport.width = 0; }, value => { value.viewport.height = 20001; }, value => { value.viewport.scrollY = -1; },
    value => { value.viewport.scrollX = Infinity; }, value => { value.viewport.scrollY = NaN; }, value => { value.viewport.scrollY = 1000001; },
  ];
  for (const change of changes) { const value = context(); change(value); assert.equal(validApplicationContext(value), false, change.toString()); }
  const maximum = context(); maximum.target.name = "ø".repeat(120); maximum.target.text = "ø".repeat(500); maximum.viewport.scrollY = 1000000;
  assert.equal(validApplicationContext(maximum), true);
});

test("field labels may be collected but input and editable values are excluded", () => {
  for (const target of [{ tag: "input", role: "textbox" }, { tag: "textarea", role: "" }, { tag: "select", role: "combobox" }, { tag: "option", role: "option" }, { tag: "div", role: "textbox" }, { tag: "div", role: "slider" }]) {
    const value = context(); Object.assign(value.target, target, { name: "Velg tidspunkt", text: "" });
    assert.equal(validApplicationContext(value), true);
    value.target.text = "a selected value"; assert.equal(validApplicationContext(value), false);
    value.target.text = ""; value.target.value = "a selected value"; assert.equal(validApplicationContext(value), false);
  }
});

test("validation is pure and never repairs the caller's evidence", () => {
  const value = context(); Object.freeze(value.target); Object.freeze(value.viewport); Object.freeze(value);
  const before = JSON.stringify(value); assert.equal(validApplicationContext(value), true); assert.equal(JSON.stringify(value), before);
  const configuration = Object.freeze({ name: "Demo", url: "http://LOCALHOST/app?q=two%20words" });
  const result = parseApplication(configuration);
  assert.equal(configuration.url, "http://LOCALHOST/app?q=two%20words"); assert.equal(result.url, "http://localhost/app?q=two+words");
});

test("resource UUID queries require an explicit matching public key and preserve legacy defaults", () => {
  const uuid = "123e4567-e89b-12d3-a456-426614174000";
  const route = `/items?itemId=${uuid}&view=kort`;
  assert.equal(validApplicationRoute(route), false);
  assert.equal(validApplicationRoute(route, ["otherId"]), false);
  assert.equal(validApplicationRoute(route, ["itemId"]), true);
  assert.equal(normalizeApplicationRoute(route, ["ITEMID"]), route);
  assert.throws(() => parseApplication({ name: "Demo", url: `http://localhost:3000${route}` }), reject);
  assert.equal(parseApplication({ name: "Demo", url: `http://localhost:3000${route}`, resourceQueryKeys: ["itemId"] }).startPath, route);
  assert.equal(validApplicationRoute(`/items?otherId=${uuid}`, ["itemId"]), false);
  assert.equal(validApplicationRoute(`/items?itemId=${uuid}&ITEMID=${uuid}`, ["itemId"]), false);
  assert.equal(validApplicationRoute(`/items?itemId=${uuid}&otherId=${uuid}`, ["itemId"]), false);
  assert.equal(validApplicationRoute("/items?itemId=ordinary-short-label", ["itemId"]), true);
  assert.deepEqual(parseApplication({ name: "Demo", url: "http://localhost/", resourceQueryKeys: [] }), parseApplication({ name: "Demo", url: "http://localhost/" }));
});

test("resource query opt-in adds UUIDs only and never bypasses credential or identifying-value checks", () => {
  const uuid = "123e4567-e89b-12d3-a456-426614174000";
  for (const value of ["a".repeat(32), "a".repeat(64), "123e4567e89b12d3a456426614174000", `{${uuid}}`, `${uuid}-extra`, "ghp_example", "github_pat_example", "Bearer example", "header.payload.signature", "0".repeat(11), "person@example.test", "https://example.test", `%${uuid}`, "\u202e" + uuid]) {
    const route = `/items?itemId=${encodeURIComponent(value)}`;
    assert.equal(validApplicationRoute(route, ["itemId"]), false, value);
    assert.throws(() => parseApplication({ name: "Demo", url: `http://localhost${route}`, resourceQueryKeys: ["itemId"] }), error => {
      assert.equal(error.status, 400); assert(!error.message.includes(value)); assert(!error.message.includes("http://")); return true;
    });
  }
  for (const name of ["token", "access_token", "AUTH", "sessionId", "session_id", "cookie", "code", "state", "nonce", "key", "api-key", "client.secret", "returnUrl", "email", "personident", "fnr"]) {
    assert.throws(() => normalizeResourceQueryKeys([name]), reject, name);
    assert.equal(validApplicationRoute(`/items?${name}=${uuid}`, ["itemId"]), false, name);
    assert.equal(validApplicationRoute(`/items?${name}=${uuid}`, [name]), false, name);
  }
});

test("resource query policy is bounded, canonical and detached from caller-owned arrays", () => {
  const input = Object.freeze(["ResultId", "itemId"]);
  assert.deepEqual(normalizeResourceQueryKeys(input), ["itemid", "resultid"]);
  assert.deepEqual(input, ["ResultId", "itemId"]);
  const mutable = ["ResultId", "itemId"];
  const configuration = { name: "Demo", url: "http://localhost/", resourceQueryKeys: mutable };
  const parsed = parseApplication(configuration);
  mutable.push("otherId");
  assert.deepEqual(parsed.resourceQueryKeys, ["itemid", "resultid"]);
  parsed.resourceQueryKeys.push("anotherId");
  assert.deepEqual(configuration.resourceQueryKeys, ["ResultId", "itemId", "otherId"]);
  for (const value of [null, "itemId", {}, [null], [1], [""], [" itemId"], ["itemId\n"], ["itemId", "ITEMID"], ["item[]"], ["item/id"], ["item%49d"], ["øId"], ["a".repeat(65)], Array.from({ length: 9 }, (_, i) => `item${i}`)]) {
    assert.throws(() => normalizeResourceQueryKeys(value), reject, JSON.stringify(value));
    assert.throws(() => parseApplication({ name: "Demo", url: "http://localhost/", resourceQueryKeys: value }), reject);
  }
  assert.equal(normalizeResourceQueryKeys(Array.from({ length: 8 }, (_, i) => `item${i}`)).length, 8);
});

test("structural UUID evidence stays deterministic but grants no navigation policy", () => {
  const route = "/items?itemId=123e4567-e89b-12d3-a456-426614174000";
  const record = { screen: screenIdentity(checkpoint, route), source: { kind: "application", checkpoint, route } };
  assert.equal(validApplicationScreen(record), true);
  const evidence = { ...context(), route };
  assert.equal(validApplicationContext(evidence), true);
  assert.equal(validApplicationRoute(route), false);
  assert.equal(validApplicationScreen({ ...record, resourceQueryKeys: ["itemId"] }), false);
  assert.equal(validApplicationContext({ ...evidence, resourceQueryKeys: ["itemId"] }), false);
  const forbidden = route.replace("itemId=", "sessionId=");
  assert.throws(() => screenIdentity(checkpoint, forbidden), reject);
  assert.equal(validApplicationContext({ ...evidence, route: forbidden }), false);
});

test("resource query policy rejects sparse arrays instead of returning a non-JSON policy", () => {
  for (const value of [new Array(1), [, "itemId"]]) {
    assert.throws(() => normalizeResourceQueryKeys(value), reject);
    assert.throws(() => parseApplication({ name: "Demo", url: "http://localhost/", resourceQueryKeys: value }), reject);
  }
});


test("route privacy covers separated identifiers and sensitive query aliases without changing the route", () => {
  const identifier = "1".repeat(6) + "-" + "1".repeat(5);
  for (const value of [identifier, identifier.replace("-", "."), identifier.replace("-", " "), identifier.replace("-", "+"), "１".repeat(11), "prefix" + "1".repeat(11)]) {
    assert.equal(validApplicationRoute(`/demo?itemId=${encodeURIComponent(value)}`, ["itemId"]), false);
    assert.equal(validApplicationRoute(`/person/${encodeURIComponent(value)}`), false);
  }
  for (const name of ["foedselsnummer", "personnummer", "ident", "pnr", "dnr", "otp", "pin", "passcode", "telefon", "phone", "tlf", "navn", "name", "adresse", "address"]) {
    assert.equal(validApplicationRoute(`/demo?${name}=synthetic`), false, name);
    assert.throws(() => normalizeResourceQueryKeys([name]), reject, name);
    assert.equal(validApplicationContext({ ...context(), route: `/demo?${name}=123e4567-e89b-12d3-a456-426614174000` }), false, name);
  }
});

test("private path segments receive the same conservative checks as query evidence", () => {
  const segments = ["1".repeat(11), "person@example.test", "ghp_" + "A".repeat(30), "header.payload.signature", "a".repeat(30), "123e4567-e89b-12d3-a456-426614174000"];
  for (const segment of segments) {
    const route = `/demo/${encodeURIComponent(segment)}/details`;
    assert.equal(validApplicationRoute(route, ["itemId"]), false);
    assert.throws(() => normalizeApplicationRoute(route), error => error.status === 400 && !error.message.includes(segment));
    assert.throws(() => parseApplication({ name: "Demo", url: `http://localhost${route}` }), reject);
    assert.equal(validApplicationContext({ ...context(), route }), false);
  }
  assert.equal(normalizeApplicationRoute("/demo/motevalg-2?view=kort"), "/demo/motevalg-2?view=kort");
});

test("preview observations are bounded untrusted data, with no fields, private identifiers or extra capabilities", () => {
  const { parseInspection, validRuntimeHealth } = require("../scripts/application-contract.js");
  const base = { viewport: { width: 800, height: 600 }, elements: [{ tag: "h1", role: "heading", name: "Dialogmøter", text: "Dialogmøter" }], health: { script: 0, module: 0, rejection: 0 }, truncated: false };
  assert.equal(parseInspection(base).evidence, "untrusted-page-content");
  const privateLabel = { ...base, elements: [{ ...base.elements[0], name: "test@example.invalid", text: "1".repeat(11) }] };
  assert.equal(parseInspection(privateLabel).elements[0].name, "[omitted]");
  assert.equal(parseInspection(privateLabel).elements[0].text, "[omitted]");
  for (const changes of [{ health: { ...base.health, stack: "private" } }, { viewport: { width: 0, height: 600 } }, { elements: Array(81).fill(base.elements[0]) },
    { elements: [{ tag: ["h1"], role: "heading", name: "Heading", text: "Heading" }] },
    { elements: [{ tag: "input", role: "textbox", name: "Felt", text: "VALUE" }] }, { evaluate: "document.cookie" }]) {
    assert.throws(() => parseInspection({ ...base, ...changes }));
  }
  assert.equal(validRuntimeHealth({ script: 101, module: 0, rejection: 0 }), false);
});
