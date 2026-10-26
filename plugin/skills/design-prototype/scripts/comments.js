#!/usr/bin/env node
"use strict";

// All mutations go through the preview server, the sole feedback-state writer.
const path = require("node:path");
const { readPrivateJson, MAX_STORE_BYTES, ID, validPatch } = require("./feedback-store.js");
const MAX_RESPONSE_BYTES = MAX_STORE_BYTES + 64 * 1024;

function parseArguments(argv) {
  const [command, ...args] = argv;
  if (!["list", "wait", "resolve", "reopen", "delete"].includes(command)) throw new Error("Use list, wait, resolve, reopen, or delete with --state-dir DIRECTORY.");
  const options = {};
  for (let index = 0; index < args.length; index += 2) {
    const key = args[index];
    if (!["--state-dir", "--id", "--reply", "--after", "--timeout", "--submission"].includes(key) || Object.hasOwn(options, key) || index + 1 >= args.length) throw new Error("Invalid or repeated option.");
    options[key] = args[index + 1];
  }
  if (!options["--state-dir"]) throw new Error("--state-dir is required.");
  const mutation = ["resolve", "reopen", "delete"].includes(command);
  if (mutation && !ID.test(options["--id"] || "")) throw new Error("--id must identify one comment.");
  if (!mutation && options["--id"] !== undefined) throw new Error("--id is only used with resolve, reopen, or delete.");
  if (options["--reply"] !== undefined && (!["resolve", "reopen"].includes(command) || !validPatch({ reply: options["--reply"] }))) throw new Error("--reply must be at most 2000 UTF-8 bytes and accompany resolve or reopen.");
  if (options["--submission"] !== undefined && (!["resolve", "reopen"].includes(command) || !/^(0|[1-9][0-9]*)$/.test(options["--submission"]) || !Number.isSafeInteger(Number(options["--submission"])))) throw new Error("--submission must be a nonnegative round number and accompany resolve or reopen.");
  if (command !== "wait" && (options["--after"] !== undefined || options["--timeout"] !== undefined)) throw new Error("--after and --timeout are only used with wait.");
  const after = Number(options["--after"] || "0");
  const timeout = Number(options["--timeout"] || "55");
  if (!/^(0|[1-9][0-9]*)$/.test(options["--after"] || "0") || !Number.isSafeInteger(after)) throw new Error("--after must be a nonnegative submission integer.");
  if (!/^(0|[1-9][0-9]*)$/.test(options["--timeout"] || "55") || !Number.isInteger(timeout) || timeout < 0 || timeout > 60) throw new Error("--timeout must be an integer from 0 through 60 seconds.");
  return { command, options, after, timeout };
}
function serverAddress(directory) {
  const info = readPrivateJson(path.resolve(directory), "server-info.json", 16 * 1024);
  const url = new URL(info.url);
  const host = url.hostname.replace(/^\[|\]$/g, "");
  const ipv4 = host.split(".");
  const loopback = host === "localhost" || host === "::1" || (ipv4.length === 4 && ipv4[0] === "127" && ipv4.every((part) => /^\d+$/.test(part) && Number(part) <= 255));
  if (info.type !== "server-started" || !loopback || url.protocol !== "http:" || url.username || url.password || !url.port || url.pathname !== "/" || url.hash || !/^[A-Za-z0-9_-]{43}$/.test(url.searchParams.get("token") || "") || [...url.searchParams.keys()].length !== 1) throw new Error("Invalid local preview connection information.");
  return url;
}
async function request(baseUrl, pathname, method = "GET", body, waiter = false, after) {
  const url = new URL(baseUrl);
  url.pathname = pathname;
  if (waiter) url.searchParams.set("waiter", "1");
  if (after !== undefined) url.searchParams.set("after", String(after));
  let response;
  try {
    response = await fetch(url, {
      method, redirect: "error", signal: AbortSignal.timeout(2000),
      headers: { Origin: url.origin, ...(method === "GET" ? {} : { "Content-Type": "application/json" }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch { throw new Error("The local preview is unavailable. Start or reconnect the preview session."); }
  let bytes = 0;
  const chunks = [];
  for await (const chunk of response.body) {
    bytes += chunk.length;
    if (bytes > MAX_RESPONSE_BYTES) throw new Error("Feedback response exceeded its size limit.");
    chunks.push(chunk);
  }
  let result;
  try { result = JSON.parse(Buffer.concat(chunks).toString("utf8")); }
  catch { throw new Error(`Preview request failed (${response.status}).`); }
  if (!response.ok && pathname === "/comments/submissions" && [404, 405].includes(response.status)) throw new Error("This preview does not support preserved feedback rounds. Start a new preview session with the current scripts.");
  if (!response.ok) throw new Error(typeof result.error === "string" ? result.error : `Preview request failed (${response.status}).`);
  return result;
}
async function main() {
  const { command, options, after, timeout } = parseArguments(process.argv.slice(2));
  const baseUrl = serverAddress(options["--state-dir"]);
  if (command === "list") return request(baseUrl, "/comments");
  if (command === "wait") {
    const deadline = Date.now() + timeout * 1000;
    do {
      const snapshot = await request(baseUrl, "/comments/submissions", "GET", undefined, true, after);
      if (snapshot.submission > after) return { type: "feedback-submission", ...snapshot };
      if (Date.now() >= deadline) return { type: "feedback-timeout", ...snapshot };
      await new Promise((resolve) => setTimeout(resolve, Math.min(500, Math.max(0, deadline - Date.now()))));
    } while (true);
  }
  const pathname = `/comments/${options["--id"]}`;
  if (command === "delete") return request(baseUrl, pathname, "DELETE", {});
  const patch = { status: command === "resolve" ? "fixed" : "open" };
  if (options["--submission"] !== undefined) patch.expectedSubmission = Number(options["--submission"]);
  if (options["--reply"] !== undefined) patch.reply = options["--reply"];
  return request(baseUrl, pathname, "PATCH", patch);
}
main().then((result) => console.log(JSON.stringify(result))).catch((error) => {
  console.error(JSON.stringify({ type: "error", message: error.message }));
  process.exitCode = 2;
});
