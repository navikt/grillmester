#!/usr/bin/env python3
"""Probe an OpenAI-compatible local model before trusting it with agents.

The probe is deliberately provider-neutral. It verifies model discovery,
server-sent-event streaming, and one forced tool call without changing files
or invoking a tool. Non-loopback endpoints require an explicit opt-in.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable, Sequence


NONCE = "grillmester-local-probe"
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


class ProbeError(RuntimeError):
    """Raised when the endpoint does not meet the agent-runtime contract."""


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Fail closed before urllib can copy credentials to a redirect target."""

    def redirect_request(  # type: ignore[no-untyped-def]
        self, request, response, code, message, headers, redirect_url
    ):
        raise urllib.error.HTTPError(
            request.full_url,
            code,
            "redirect responses are not allowed",
            headers,
            response,
        )


def build_http_opener() -> urllib.request.OpenerDirector:
    """Build direct HTTP transport with redirects disabled."""

    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        RejectRedirects(),
    )


NO_REDIRECT_OPENER = build_http_opener()


@dataclass(frozen=True)
class ProbeResult:
    endpoint: str
    model: str
    advertised_models: int
    stream_events: int
    tool_name: str


def normalize_base_url(value: str, *, allow_remote: bool) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ProbeError("base URL must be an absolute http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProbeError("base URL must not contain credentials, query, or fragment")
    if not allow_remote and parsed.hostname.lower() not in LOOPBACK_HOSTS:
        raise ProbeError(
            "refusing a non-loopback endpoint; pass --allow-remote explicitly"
        )
    return value.rstrip("/")


def auth_headers(api_key_env: str | None) -> dict[str, str]:
    if api_key_env is None:
        return {}
    if ENV_NAME.fullmatch(api_key_env) is None:
        raise ProbeError("--api-key-env must be an environment variable name")
    value = os.environ.get(api_key_env)
    if not value:
        raise ProbeError(f"environment variable {api_key_env} is empty or missing")
    return {"Authorization": f"Bearer {value}"}


def open_request(
    request: urllib.request.Request, *, timeout: float
) -> urllib.response.addinfourl:
    try:
        return NO_REDIRECT_OPENER.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", errors="replace").strip()
        authorization = request.get_header("Authorization")
        if authorization:
            detail = detail.replace(authorization, "<redacted>")
            scheme, separator, credential = authorization.partition(" ")
            if separator and scheme.lower() == "bearer" and credential:
                detail = detail.replace(credential, "<redacted>")
        suffix = f": {detail}" if detail else ""
        raise ProbeError(f"HTTP {exc.code} from {request.full_url}{suffix}") from exc
    except urllib.error.URLError as exc:
        raise ProbeError(f"cannot reach {request.full_url}: {exc.reason}") from exc


def read_json(response: urllib.response.addinfourl, *, label: str) -> Any:
    try:
        return json.loads(response.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProbeError(f"{label} did not return valid UTF-8 JSON") from exc


def probe_models(
    base_url: str,
    model: str,
    *,
    headers: dict[str, str],
    timeout: float,
) -> int:
    request = urllib.request.Request(
        f"{base_url}/models",
        headers={"Accept": "application/json", **headers},
    )
    with open_request(request, timeout=timeout) as response:
        value = read_json(response, label="GET /models")
    data = value.get("data") if isinstance(value, dict) else None
    if not isinstance(data, list):
        raise ProbeError("GET /models response has no data array")
    ids = {
        entry.get("id")
        for entry in data
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }
    if model not in ids:
        visible = ", ".join(sorted(ids)[:8]) or "none"
        raise ProbeError(f"model {model!r} is not advertised; visible models: {visible}")
    return len(ids)


def sse_payloads(lines: Iterable[bytes]) -> Iterable[dict[str, Any]]:
    for raw_line in lines:
        try:
            line = raw_line.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise ProbeError("stream contained non-UTF-8 data") from exc
        if not line or line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:").strip()
        if data == "[DONE]":
            return
        try:
            value = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ProbeError("stream contained an invalid JSON event") from exc
        if not isinstance(value, dict):
            raise ProbeError("stream event must be a JSON object")
        yield value


def probe_streaming_tool_call(
    base_url: str,
    model: str,
    *,
    headers: dict[str, str],
    timeout: float,
) -> tuple[int, str]:
    tool_name = "grillmester_capability_probe"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": (
                    f"Call {tool_name} exactly once with nonce {NONCE!r}. "
                    "Do not answer in prose."
                ),
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": "Reports that the local agent capability probe passed.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "nonce": {"type": "string", "const": NONCE}
                        },
                        "required": ["nonce"],
                        "additionalProperties": False,
                    },
                },
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": tool_name}},
        "stream": True,
        "temperature": 0,
        "max_tokens": 512,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            **headers,
        },
    )
    with open_request(request, timeout=timeout) as response:
        content_type = response.headers.get_content_type()
        if content_type != "text/event-stream":
            raise ProbeError(
                "streaming request did not return text/event-stream "
                f"(got {content_type})"
            )
        names: dict[int, str] = {}
        arguments: dict[int, str] = {}
        events = 0
        for event in sse_payloads(response):
            events += 1
            choices = event.get("choices")
            if not isinstance(choices, list):
                continue
            for choice in choices:
                delta = choice.get("delta") if isinstance(choice, dict) else None
                calls = delta.get("tool_calls") if isinstance(delta, dict) else None
                if not isinstance(calls, list):
                    continue
                for call in calls:
                    if not isinstance(call, dict):
                        continue
                    index = call.get("index", 0)
                    if not isinstance(index, int):
                        raise ProbeError("tool-call stream index must be an integer")
                    function = call.get("function")
                    if not isinstance(function, dict):
                        continue
                    name_fragment = function.get("name", "")
                    args_fragment = function.get("arguments", "")
                    if isinstance(name_fragment, str):
                        names[index] = names.get(index, "") + name_fragment
                    if isinstance(args_fragment, str):
                        arguments[index] = arguments.get(index, "") + args_fragment

    if events < 1:
        raise ProbeError("stream returned no JSON events")
    matching = [index for index, name in names.items() if name == tool_name]
    if not matching:
        visible = ", ".join(names.values()) or "none"
        raise ProbeError(f"model did not call {tool_name}; observed tools: {visible}")
    try:
        args = json.loads(arguments.get(matching[0], ""))
    except json.JSONDecodeError as exc:
        raise ProbeError("tool call arguments were not valid JSON") from exc
    if not isinstance(args, dict) or args.get("nonce") != NONCE:
        raise ProbeError("tool call did not preserve the required probe nonce")
    return events, tool_name


def probe(
    base_url: str,
    model: str,
    *,
    api_key_env: str | None,
    allow_remote: bool,
    timeout: float,
) -> ProbeResult:
    endpoint = normalize_base_url(base_url, allow_remote=allow_remote)
    headers = auth_headers(api_key_env)
    advertised = probe_models(endpoint, model, headers=headers, timeout=timeout)
    events, tool_name = probe_streaming_tool_call(
        endpoint, model, headers=headers, timeout=timeout
    )
    return ProbeResult(
        endpoint=endpoint,
        model=model,
        advertised_models=advertised,
        stream_events=events,
        tool_name=tool_name,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:1234/v1",
        help="OpenAI-compatible API root (default: LM Studio localhost)",
    )
    parser.add_argument("--model", required=True, help="exact model ID from /models")
    parser.add_argument(
        "--api-key-env",
        help="read a bearer token from this environment variable; never printed",
    )
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="allow a non-loopback endpoint",
    )
    parser.add_argument("--timeout", type=float, default=180.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.timeout <= 0:
        print("Local model probe failed: --timeout must be positive", file=sys.stderr)
        return 2
    try:
        result = probe(
            args.base_url,
            args.model,
            api_key_env=args.api_key_env,
            allow_remote=args.allow_remote,
            timeout=args.timeout,
        )
    except ProbeError as exc:
        print(f"Local model probe failed: {exc}", file=sys.stderr)
        return 1
    print("LOCAL_MODEL_PROBE: PASS")
    print(f"Endpoint: {result.endpoint}")
    print(f"Model: {result.model}")
    print(f"Models advertised: {result.advertised_models}")
    print(f"Streaming events: {result.stream_events}")
    print(f"Tool call: {result.tool_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
