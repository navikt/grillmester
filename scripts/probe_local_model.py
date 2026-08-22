#!/usr/bin/env python3
"""Probe an OpenAI-compatible local model before trusting it with agents.

The probe is deliberately provider-neutral. It verifies model discovery,
server-sent-event streaming, and exactly one forced tool call without prose,
without changing files or invoking a tool. Non-loopback endpoints require an
explicit opt-in, and bearer authentication to them requires HTTPS.
"""

from __future__ import annotations

import argparse
import http.client
import ipaddress
import json
import math
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
LOOPBACK_HOSTNAMES = {"localhost"}
MAX_JSON_RESPONSE_BYTES = 2_000_000
MAX_SSE_LINE_BYTES = 1_000_000
MAX_SSE_RESPONSE_BYTES = 5_000_000
MAX_SSE_EVENTS = 10_000
MAX_TOOL_CALL_TEXT_CHARS = 1_000_000
MAX_TOOL_CALL_ID_CHARS = 512
MAX_BASE_URL_CHARS = 4_096
MAX_MODEL_ID_CHARS = 512


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


def is_loopback_host(hostname: str) -> bool:
    """Classify explicit loopback literals and the conventional localhost name."""

    if hostname.lower() in LOOPBACK_HOSTNAMES:
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def normalize_base_url(value: str, *, allow_remote: bool) -> str:
    if not value or len(value) > MAX_BASE_URL_CHARS:
        raise ProbeError(
            f"base URL must contain between 1 and {MAX_BASE_URL_CHARS} characters"
        )
    if any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in value
    ):
        raise ProbeError(
            "base URL must not contain whitespace or control characters"
        )
    if any(ord(character) > 126 for character in value):
        raise ProbeError("base URL must contain only visible ASCII")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ProbeError("base URL must be an absolute http(s) URL")
    try:
        parsed.port
    except ValueError as exc:
        raise ProbeError("base URL contains an invalid port") from exc
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProbeError("base URL must not contain credentials, query, or fragment")
    if not allow_remote and not is_loopback_host(parsed.hostname):
        raise ProbeError(
            "refusing a non-loopback endpoint; pass --allow-remote explicitly"
        )
    return value.rstrip("/")


def normalize_model_id(value: str) -> str:
    """Reject empty, oversized, or terminal-active model identifiers."""

    if not value or len(value) > MAX_MODEL_ID_CHARS:
        raise ProbeError(
            f"model ID must contain between 1 and {MAX_MODEL_ID_CHARS} characters"
        )
    if any(not 33 <= ord(character) <= 126 for character in value):
        raise ProbeError("model ID must contain only visible ASCII")
    return value


def auth_headers(api_key_env: str | None) -> dict[str, str]:
    if api_key_env is None:
        return {}
    if ENV_NAME.fullmatch(api_key_env) is None:
        raise ProbeError("--api-key-env must be an environment variable name")
    value = os.environ.get(api_key_env)
    if not value:
        raise ProbeError(f"environment variable {api_key_env} is empty or missing")
    if any(not 33 <= ord(character) <= 126 for character in value):
        raise ProbeError(
            f"environment variable {api_key_env} must contain only visible ASCII"
        )
    return {"Authorization": f"Bearer {value}"}


def require_secure_bearer_transport(
    base_url: str, *, api_key_env: str | None
) -> None:
    if api_key_env is None:
        return
    parsed = urllib.parse.urlsplit(base_url)
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if not is_loopback_host(hostname) and parsed.scheme != "https":
        raise ProbeError(
            "bearer authentication to a non-loopback endpoint requires HTTPS"
        )


def open_request(
    request: urllib.request.Request, *, timeout: float
) -> urllib.response.addinfourl:
    try:
        return NO_REDIRECT_OPENER.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        # A provider controls its error body and can reflect, transform, or
        # encode an Authorization header in ways that ad-hoc replacement will
        # miss. Keep diagnostics value-opaque instead of echoing provider data.
        exc.close()
        raise ProbeError(f"provider returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ProbeError("cannot reach the configured provider endpoint") from exc
    except (http.client.HTTPException, OSError, ValueError) as exc:
        raise ProbeError("cannot reach the configured provider endpoint") from exc


def read_json(response: urllib.response.addinfourl, *, label: str) -> Any:
    content = response.read(MAX_JSON_RESPONSE_BYTES + 1)
    if len(content) > MAX_JSON_RESPONSE_BYTES:
        raise ProbeError(
            f"{label} exceeded the {MAX_JSON_RESPONSE_BYTES}-byte response limit"
        )
    try:
        return json.loads(content.decode("utf-8"))
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
        raise ProbeError("the requested model is not advertised")
    return len(ids)


def sse_payloads(lines: Any) -> Iterable[dict[str, Any]]:
    total_bytes = 0
    events = 0
    while True:
        raw_line = lines.readline(MAX_SSE_LINE_BYTES + 1)
        if not raw_line:
            break
        if len(raw_line) > MAX_SSE_LINE_BYTES:
            raise ProbeError(
                f"stream line exceeded the {MAX_SSE_LINE_BYTES}-byte limit"
            )
        total_bytes += len(raw_line)
        if total_bytes > MAX_SSE_RESPONSE_BYTES:
            raise ProbeError(
                "stream exceeded the "
                f"{MAX_SSE_RESPONSE_BYTES}-byte response limit"
            )
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
        events += 1
        if events > MAX_SSE_EVENTS:
            raise ProbeError(
                f"stream exceeded the {MAX_SSE_EVENTS}-event limit"
            )
        yield value
    raise ProbeError("stream ended before the required [DONE] marker")


def reject_duplicate_json_fields(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ProbeError("tool call arguments contain a duplicate field")
        value[key] = item
    return value


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
        "parallel_tool_calls": False,
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
            raise ProbeError("streaming request did not return text/event-stream")
        names: dict[int, str] = {}
        arguments: dict[int, str] = {}
        call_ids: dict[int, str] = {}
        call_types: dict[int, str] = {}
        seen_indexes: set[int] = set()
        finish_reasons: list[str] = []
        finished = False
        events = 0
        for event in sse_payloads(response):
            events += 1
            choices = event.get("choices")
            if not isinstance(choices, list):
                continue
            for choice in choices:
                finish_reason: str | None = None
                if isinstance(choice, dict):
                    finish_reason = choice.get("finish_reason")
                    if finish_reason is not None:
                        if not isinstance(finish_reason, str):
                            raise ProbeError("finish_reason must be a string or null")
                        finish_reasons.append(finish_reason)
                delta = choice.get("delta") if isinstance(choice, dict) else None
                if isinstance(delta, dict) and delta.get("content") not in (None, ""):
                    raise ProbeError(
                        "model returned prose instead of only the forced tool call"
                    )
                calls = delta.get("tool_calls") if isinstance(delta, dict) else None
                if not isinstance(calls, list):
                    if finish_reason is not None:
                        finished = True
                    continue
                if calls and finished:
                    raise ProbeError("stream returned tool-call data after finish")
                for call in calls:
                    if not isinstance(call, dict):
                        raise ProbeError("tool-call stream entry must be an object")
                    index = call.get("index")
                    if type(index) is not int or index < 0:
                        raise ProbeError(
                            "tool-call stream index must be a non-negative integer"
                        )
                    first_fragment = index not in seen_indexes
                    seen_indexes.add(index)

                    call_id = call.get("id")
                    if first_fragment:
                        if not isinstance(call_id, str):
                            raise ProbeError(
                                "the first tool-call fragment must contain a string id"
                            )
                        if (
                            not call_id
                            or len(call_id) > MAX_TOOL_CALL_ID_CHARS
                            or any(not 33 <= ord(character) <= 126 for character in call_id)
                        ):
                            raise ProbeError(
                                "tool-call id must be bounded non-empty visible ASCII"
                            )
                        call_ids[index] = call_id
                    elif call_id is not None:
                        if not isinstance(call_id, str):
                            raise ProbeError("tool-call id must be a string when present")
                        if call_id != call_ids[index]:
                            raise ProbeError(
                                "tool-call id changed for an existing stream index"
                            )

                    call_type = call.get("type")
                    if first_fragment:
                        if call_type != "function":
                            raise ProbeError(
                                "the first tool-call fragment must have type 'function'"
                            )
                        call_types[index] = call_type
                    elif call_type is not None:
                        if not isinstance(call_type, str):
                            raise ProbeError(
                                "tool-call type must be a string when present"
                            )
                        if call_type != call_types[index]:
                            raise ProbeError(
                                "tool-call type changed for an existing stream index"
                            )

                    function = call.get("function")
                    if not isinstance(function, dict):
                        raise ProbeError(
                            "tool-call stream entry must contain a function object"
                        )
                    name_fragment = function.get("name", "")
                    args_fragment = function.get("arguments", "")
                    if not isinstance(name_fragment, str):
                        raise ProbeError("tool-call name fragment must be a string")
                    if not isinstance(args_fragment, str):
                        raise ProbeError("tool-call argument fragment must be a string")
                    names[index] = names.get(index, "") + name_fragment
                    if len(names[index]) > MAX_TOOL_CALL_TEXT_CHARS:
                        raise ProbeError("tool-call name exceeded the size limit")
                    arguments[index] = arguments.get(index, "") + args_fragment
                    if len(arguments[index]) > MAX_TOOL_CALL_TEXT_CHARS:
                        raise ProbeError(
                            "tool-call arguments exceeded the size limit"
                        )
                if finish_reason is not None:
                    finished = True

    if events < 1:
        raise ProbeError("stream returned no JSON events")
    if len(seen_indexes) != 1:
        raise ProbeError(
            "model must return exactly one tool call; "
            f"observed {len(seen_indexes)}"
        )
    if seen_indexes != {0}:
        raise ProbeError("the single tool call must use stream index 0")
    matching = [index for index, name in names.items() if name == tool_name]
    if not matching:
        raise ProbeError(f"model did not call the required {tool_name} tool")
    try:
        args = json.loads(
            arguments.get(matching[0], ""),
            object_pairs_hook=reject_duplicate_json_fields,
        )
    except json.JSONDecodeError as exc:
        raise ProbeError("tool call arguments were not valid JSON") from exc
    if args != {"nonce": NONCE}:
        raise ProbeError(
            "tool call arguments must be exactly the required probe nonce object"
        )
    if finish_reasons != ["tool_calls"]:
        raise ProbeError(
            "stream must finish exactly once with finish_reason 'tool_calls'"
        )
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
    selected_model = normalize_model_id(model)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ProbeError("timeout must be a positive finite number")
    require_secure_bearer_transport(endpoint, api_key_env=api_key_env)
    headers = auth_headers(api_key_env)
    advertised = probe_models(
        endpoint, selected_model, headers=headers, timeout=timeout
    )
    events, tool_name = probe_streaming_tool_call(
        endpoint, selected_model, headers=headers, timeout=timeout
    )
    return ProbeResult(
        endpoint=endpoint,
        model=selected_model,
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
        help="allow a non-loopback endpoint; remote bearer auth still requires HTTPS",
    )
    parser.add_argument("--timeout", type=float, default=180.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
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
