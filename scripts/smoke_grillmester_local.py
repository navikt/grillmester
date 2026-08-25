#!/usr/bin/env python3
"""Gate local-model launches through real cplt and installed terminal clients.

The smoke never contacts a model. A deterministic OpenAI-compatible provider
binds to loopback, returns one fixed streamed response, and captures the exact
request made by each client for contract validation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import selectors
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]


def _load_release_test_contract() -> Mapping[str, Any]:
    name = "grillmester_release_test_baseline_for_local_smoke"
    path = ROOT / "scripts/release_test_baseline.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load release-test baseline contract: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module.CONTRACT["releaseTest"]


_RELEASE_TEST = _load_release_test_contract()
EXPECTED_CPLT_RELEASE = _RELEASE_TEST["cpltRelease"]
EXPECTED_OPENCODE_VERSION = _RELEASE_TEST["opencodeVersion"]
EXPECTED_COPILOT_VERSION = _RELEASE_TEST["copilotVersion"]
MODEL_ID = "grillmester-local-smoke-v1"
PROVIDER_ID = "smoke"
SERVER_HOST = "127.0.0.1"
PROMPT = "Return the deterministic Grillmester local smoke sentinel only."
SUBAGENT_PROMPT = "Return SUBAGENT_LOCAL_ONLY and do not use tools."
TOOL_SENTINEL = "GRILLMESTER_LOCAL_TOOL_OK"
NPM_ACCESS_SENTINEL = "GRILLMESTER_LOCAL_NPM_ACCESS_OK"
NPM_ACCESS_ENVIRONMENT = "NODE_AUTH_TOKEN"
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
DEFAULT_TIMEOUT = 45.0
CREDENTIAL_CANARY_PREFIX = "GRILLMESTER_LOCAL_SMOKE_CREDENTIAL_"
AMBIENT_GITHUB_TOKEN_CANARY = "GRILLMESTER_LOCAL_SMOKE_AMBIENT_GITHUB_TOKEN"
GITHUB_GUARD_TOKEN = "GRILLMESTER_LOCAL_SMOKE_EXPLICIT_TOKEN"
GITHUB_GUARD_SENTINEL = "GRILLMESTER_LOCAL_GITHUB_GUARD_OK"
CREDENTIAL_ENVIRONMENT = (
    "ANTHROPIC_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AZURE_OPENAI_API_KEY",
    "COPILOT_PROVIDER_API_KEY",
    "COPILOT_GITHUB_TOKEN",
    "GEMINI_API_KEY",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GOOGLE_API_KEY",
    "GRILLMESTER_LOCAL_API_KEY",
    "HF_TOKEN",
    "NPM_AUTH_TOKEN",
    "NODE_AUTH_TOKEN",
    "NPM_TOKEN",
    "OPENAI_API_KEY",
)
GITHUB_CREDENTIAL_ENVIRONMENT = (
    "COPILOT_GITHUB_TOKEN",
    "GH_TOKEN",
    "GITHUB_TOKEN",
)
PARENT_TOOL_CANARIES = ("git", "which", "sandbox-exec", "uname", "mise", "asdf")


class LocalSmokeError(RuntimeError):
    """Raised when a local-model smoke contract cannot be proven."""


def _load_local_launcher(distribution_root: Path = ROOT) -> Any:
    name = "grillmester_local_for_local_smoke"
    path = distribution_root / "scripts/grillmester_local.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise LocalSmokeError(f"could not load extracted local launcher: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


LOCAL = _load_local_launcher()


@dataclass(frozen=True)
class Scenario:
    client: str
    context: str

    def __post_init__(self) -> None:
        if self.client not in {"opencode", "copilot"}:
            raise ValueError(f"unsupported client: {self.client}")
        if self.context not in {"focused", "full"}:
            raise ValueError(f"unsupported context: {self.context}")

    @property
    def name(self) -> str:
        return f"{self.client}-{self.context}"

    @property
    def relative_payload(self) -> Path:
        return {
            ("opencode", "focused"): Path("targets/opencode-v1-focused"),
            ("opencode", "full"): Path("targets/opencode-v1"),
            ("copilot", "focused"): Path("targets/copilot-cli-focused-v1"),
            ("copilot", "full"): Path("plugin"),
        }[(self.client, self.context)]


SCENARIOS = tuple(
    Scenario(client, context)
    for client in ("opencode", "copilot")
    for context in ("focused", "full")
)


def sentinel_for(scenario: Scenario) -> str:
    return f"GRILLMESTER_LOCAL_SMOKE_OK_{scenario.client.upper()}_{scenario.context.upper()}"


@dataclass(frozen=True)
class CompletionRecord:
    path: str
    headers: Mapping[str, str]
    payload: Mapping[str, Any]


@dataclass
class ProviderState:
    scenario: Scenario
    tool_command: str | None = None
    final_content: str | None = None
    model_requests: list[Mapping[str, str]] = field(default_factory=list)
    npm_requests: list[Mapping[str, str]] = field(default_factory=list)
    completions: list[CompletionRecord] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    last_content_type: str = ""
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_completion(self, record: CompletionRecord) -> None:
        with self.lock:
            self.completions.append(record)

    def record_models(self, headers: Mapping[str, str]) -> None:
        with self.lock:
            self.model_requests.append(headers)

    def record_npm(self, headers: Mapping[str, str]) -> None:
        with self.lock:
            self.npm_requests.append(headers)

    def violate(self, message: str) -> None:
        with self.lock:
            self.violations.append(message)


class _ProviderHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, state: ProviderState):
        super().__init__((SERVER_HOST, 0), _ProviderHandler)
        self.state = state


def _content_stream_body(scenario: Scenario, content: str, *, suffix: str) -> bytes:
    chunks = (
        {
            "id": f"chatcmpl-{scenario.name}-{suffix}",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": MODEL_ID,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": content},
                    "finish_reason": None,
                }
            ],
        },
        {
            "id": f"chatcmpl-{scenario.name}-{suffix}",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": MODEL_ID,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        },
    )
    return b"".join(
        f"data: {json.dumps(chunk, sort_keys=True, separators=(',', ':'))}\n\n".encode(
            "utf-8"
        )
        for chunk in chunks
    ) + b"data: [DONE]\n\n"


def _task_stream_body(scenario: Scenario) -> bytes:
    arguments = json.dumps(
        {
            "name": "local-precedence-probe",
            "description": "Probe model inheritance",
            "prompt": SUBAGENT_PROMPT,
            "agent_type": "grillmester:grill-inspektor",
            "mode": "sync",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    chunks = (
        {
            "id": f"chatcmpl-{scenario.name}-delegate",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": MODEL_ID,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_local_precedence_probe",
                                "type": "function",
                                "function": {"name": "task", "arguments": arguments},
                            }
                        ],
                    },
                    "finish_reason": None,
                }
            ],
        },
        {
            "id": f"chatcmpl-{scenario.name}-delegate",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": MODEL_ID,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "tool_calls",
                }
            ],
        },
    )
    return b"".join(
        f"data: {json.dumps(chunk, sort_keys=True, separators=(',', ':'))}\n\n".encode(
            "utf-8"
        )
        for chunk in chunks
    ) + b"data: [DONE]\n\n"


def _bash_stream_body(scenario: Scenario, command: str | None = None) -> bytes:
    arguments = json.dumps(
        {"command": command or f"/usr/bin/printf {TOOL_SENTINEL}"},
        sort_keys=True,
        separators=(",", ":"),
    )
    chunks = (
        {
            "id": f"chatcmpl-{scenario.name}-tool",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": MODEL_ID,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_local_tool_probe",
                                "type": "function",
                                "function": {"name": "bash", "arguments": arguments},
                            }
                        ],
                    },
                    "finish_reason": None,
                }
            ],
        },
        {
            "id": f"chatcmpl-{scenario.name}-tool",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": MODEL_ID,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "tool_calls",
                }
            ],
        },
    )
    return b"".join(
        f"data: {json.dumps(chunk, sort_keys=True, separators=(',', ':'))}\n\n".encode(
            "utf-8"
        )
        for chunk in chunks
    ) + b"data: [DONE]\n\n"


def _function_tool_names(record: CompletionRecord) -> tuple[str, ...]:
    tools = record.payload.get("tools")
    if not isinstance(tools, list):
        return ()
    return tuple(
        name
        for tool in tools
        if isinstance(tool, dict)
        and isinstance(tool.get("function"), dict)
        and isinstance((name := tool["function"].get("name")), str)
    )


def _exposes_function_tool(record: CompletionRecord, name: str) -> bool:
    return name in _function_tool_names(record)


def _stream_body(state: ProviderState) -> bytes:
    request_number = len(state.completions)
    if state.tool_command is not None:
        if request_number == 1 and _exposes_function_tool(
            state.completions[0], "bash"
        ):
            return _bash_stream_body(state.scenario, state.tool_command)
        return _content_stream_body(
            state.scenario,
            state.final_content or sentinel_for(state.scenario),
            suffix="npm-final",
        )
    if (
        state.scenario == Scenario("opencode", "focused")
        and request_number == 1
        and _exposes_function_tool(state.completions[0], "bash")
    ):
        return _bash_stream_body(state.scenario)
    if state.scenario.client == "copilot":
        if request_number == 1:
            return _task_stream_body(state.scenario)
        if request_number == 2:
            return _content_stream_body(
                state.scenario, "SUBAGENT_LOCAL_ONLY", suffix="subagent"
            )
    return _content_stream_body(
        state.scenario, sentinel_for(state.scenario), suffix="final"
    )


class _ProviderHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: _ProviderHTTPServer

    def log_message(self, _format: str, *_arguments: object) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.server.state.last_content_type = content_type
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _reject(self, status: int, message: str) -> None:
        self.server.state.violate(message)
        body = json.dumps({"error": message}, sort_keys=True).encode("utf-8")
        self._send(status, body, "application/json")

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        headers = {name.lower(): value for name, value in self.headers.items()}
        if self.path.startswith("/npm/"):
            self.server.state.record_npm(headers)
            self._send(200, b'{"ok":true}\n', "application/json")
            return
        if self.path != "/v1/models":
            self._reject(404, f"unsupported GET {self.path}")
            return
        self.server.state.record_models(headers)
        body = json.dumps(
            {"object": "list", "data": [{"id": MODEL_ID, "object": "model"}]},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self._send(200, body, "application/json")

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        if self.path != "/v1/chat/completions":
            self._reject(404, f"unsupported POST {self.path}")
            return
        try:
            size = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._reject(400, "completion request has an invalid Content-Length")
            return
        if size <= 0 or size > MAX_REQUEST_BYTES:
            self._reject(
                413,
                f"completion request size must be in [1, {MAX_REQUEST_BYTES}] bytes",
            )
            return
        raw = self.rfile.read(size)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._reject(400, "completion request is not valid UTF-8 JSON")
            return
        if not isinstance(payload, dict):
            self._reject(400, "completion request must be a JSON object")
            return
        record = CompletionRecord(
            path=self.path,
            headers={name.lower(): value for name, value in self.headers.items()},
            payload=payload,
        )
        self.server.state.record_completion(record)
        problems: list[str] = []
        if payload.get("model") != MODEL_ID:
            problems.append(f"completion request did not use exact model {MODEL_ID!r}")
        if payload.get("stream") is not True:
            problems.append("completion request did not set stream=true")
        if not isinstance(payload.get("messages"), list):
            problems.append("completion request did not contain a messages array")
        if problems:
            for problem in problems:
                self.server.state.violate(problem)
            body = json.dumps({"error": "; ".join(problems)}, sort_keys=True).encode(
                "utf-8"
            )
            self._send(400, body, "application/json")
            return
        self._send(200, _stream_body(self.server.state), "text/event-stream")


class LoopbackProvider:
    """A bounded local provider for one scenario."""

    def __init__(
        self,
        scenario: Scenario,
        *,
        tool_command: str | None = None,
        final_content: str | None = None,
    ):
        self.state = ProviderState(
            scenario,
            tool_command=tool_command,
            final_content=final_content,
        )
        self.server = _ProviderHTTPServer(self.state)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://{SERVER_HOST}:{self.server.server_port}/v1"

    @property
    def last_content_type(self) -> str:
        return self.state.last_content_type

    def __enter__(self) -> "LoopbackProvider":
        self.thread.start()
        return self

    def __exit__(self, *_arguments: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    output: str


@dataclass(frozen=True)
class ScenarioReport:
    scenario: Scenario
    payload: Path
    requests: int
    consumer_clean: bool
    credentials_scrubbed: bool


@dataclass(frozen=True)
class PrerequisiteResult:
    cplt: Path | None
    opencode: Path | None
    copilot: Path | None
    ripgrep: Path | None
    problems: tuple[str, ...]


def _terminate(process: subprocess.Popen[bytes], *, grace: float = 2.0) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=grace)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    process.wait(timeout=grace)


def run_command(
    command: Sequence[str],
    cwd: Path,
    environment: Mapping[str, str],
    timeout: float,
    *,
    max_output_bytes: int = MAX_OUTPUT_BYTES,
) -> CommandResult:
    """Run one bounded child in its own process group."""

    if not math.isfinite(timeout) or timeout <= 0 or timeout > 300:
        raise LocalSmokeError("process timeout must be in (0, 300] seconds")
    if max_output_bytes <= 0:
        raise LocalSmokeError("process output limit must be positive")
    try:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as exc:
        raise LocalSmokeError(f"could not start {Path(command[0]).name}: {exc}") from exc
    assert process.stdout is not None
    descriptor = process.stdout.fileno()
    selector = selectors.DefaultSelector()
    selector.register(descriptor, selectors.EVENT_READ)
    output = bytearray()
    deadline = time.monotonic() + timeout
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _terminate(process)
                raise LocalSmokeError(
                    f"{Path(command[0]).name} exceeded the {timeout:g}s timeout"
                )
            for key, _mask in selector.select(min(remaining, 0.2)):
                chunk = os.read(key.fd, 64 * 1024)
                if not chunk:
                    selector.unregister(key.fd)
                    continue
                output.extend(chunk)
                if len(output) > max_output_bytes:
                    _terminate(process)
                    raise LocalSmokeError(
                        f"{Path(command[0]).name} exceeded the "
                        f"{max_output_bytes}-byte output limit"
                    )
        returncode = process.wait(timeout=max(0.1, deadline - time.monotonic()))
    except subprocess.TimeoutExpired as exc:
        _terminate(process)
        raise LocalSmokeError(
            f"{Path(command[0]).name} did not exit before timeout"
        ) from exc
    finally:
        selector.close()
        process.stdout.close()
        if process.poll() is None:
            _terminate(process)
    return CommandResult(returncode, output.decode("utf-8", errors="replace"))


def _request_text(payload: Mapping[str, Any]) -> str:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return ""
    found: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, str):
            found.append(value)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, dict):
            for item in value.values():
                collect(item)

    collect(messages)
    return "\n".join(found)


def _tool_result_text(payload: Mapping[str, Any]) -> str:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return ""
    contents = [
        message.get("content")
        for message in messages
        if isinstance(message, dict) and message.get("role") == "tool"
    ]
    return _request_text({"messages": contents})


def validate_provider_state(state: ProviderState) -> None:
    if state.violations:
        raise LocalSmokeError(
            f"{state.scenario.name} provider protocol violation: "
            + "; ".join(state.violations)
        )
    if (
        state.scenario == Scenario("opencode", "focused")
        and state.completions
        and not _exposes_function_tool(state.completions[0], "bash")
    ):
        advertised = ", ".join(_function_tool_names(state.completions[0])) or "none"
        raise LocalSmokeError(
            f"{state.scenario.name} did not expose the required 'bash' tool; "
            f"advertised function tools: {advertised}"
        )
    expected_completions = (
        3
        if state.scenario.client == "copilot"
        else 2
        if state.scenario == Scenario("opencode", "focused")
        else 1
    )
    if len(state.completions) != expected_completions:
        raise LocalSmokeError(
            f"{state.scenario.name} made {len(state.completions)} completion requests; "
            f"expected exactly {expected_completions} request(s)"
        )
    if len(state.model_requests) != 1:
        raise LocalSmokeError(
            f"{state.scenario.name} made {len(state.model_requests)} model-discovery "
            "requests; expected exactly the launcher's single loopback probe"
        )
    record = state.completions[0]
    if record.path != "/v1/chat/completions":
        raise LocalSmokeError(f"{state.scenario.name} used the wrong completion path")
    if record.payload.get("model") != MODEL_ID or record.payload.get("stream") is not True:
        raise LocalSmokeError(
            f"{state.scenario.name} did not preserve the exact streamed model request"
        )
    tools = record.payload.get("tools")
    if not isinstance(tools, list) or not tools:
        raise LocalSmokeError(
            f"{state.scenario.name} request did not expose the agent tool surface"
        )
    for index, completion in enumerate(state.completions, start=1):
        if completion.payload.get("model") != MODEL_ID:
            raise LocalSmokeError(
                f"{state.scenario.name} request {index} escaped exact model {MODEL_ID!r}"
            )
    if state.scenario.client == "copilot":
        delegated_text = _request_text(state.completions[1].payload)
        if SUBAGENT_PROMPT not in delegated_text:
            raise LocalSmokeError(
                f"{state.scenario.name} did not dispatch the Grill-inspektor probe"
            )
    elif state.scenario.context == "focused":
        tool_text = _tool_result_text(state.completions[1].payload)
        if TOOL_SENTINEL not in tool_text:
            raise LocalSmokeError(
                f"{state.scenario.name} did not execute its auto-approved bash probe"
            )
    text = _request_text(record.payload)
    if "# Barista" not in text:
        raise LocalSmokeError(f"{state.scenario.name} did not load the Barista agent")
    if state.scenario.client == "copilot":
        leaked_builtin = next(
            (
                name
                for name in LOCAL.COPILOT_DISABLED_BUILTIN_SKILLS
                if name in text
            ),
            None,
        )
        if leaked_builtin is not None:
            raise LocalSmokeError(
                f"{state.scenario.name} loaded disabled built-in skill {leaked_builtin!r}"
            )
    handoff = "Status: NEEDS_FULL_CONTEXT" in text and "grillmester local --full" in text
    full_marker = (
        "grillmester:grillmester"
        if state.scenario.client == "copilot"
        else "Grillmester (`grillmester`)"
    )
    full_reference = full_marker in text
    if state.scenario.context == "focused":
        if not handoff:
            raise LocalSmokeError(
                f"{state.scenario.name} did not load the focused handoff contract"
            )
        if full_reference:
            raise LocalSmokeError(
                f"{state.scenario.name} retained the unavailable full agent reference"
            )
    else:
        if handoff:
            raise LocalSmokeError(
                f"{state.scenario.name} unexpectedly loaded the focused handoff contract"
            )
        if not full_reference:
            raise LocalSmokeError(
                f"{state.scenario.name} did not load the full Barista projection"
            )


def validate_npm_provider_state(
    state: ProviderState, *, expected_environment_value: str | None
) -> None:
    """Validate one synthetic package-token tool round trip."""

    if state.violations:
        raise LocalSmokeError(
            f"{state.scenario.name} npm provider protocol violation: "
            + "; ".join(state.violations)
        )
    if len(state.completions) != 2:
        raise LocalSmokeError(
            f"{state.scenario.name} npm probe made {len(state.completions)} "
            "completion requests; expected exactly two"
        )
    if not _exposes_function_tool(state.completions[0], "bash"):
        raise LocalSmokeError(
            f"{state.scenario.name} npm probe did not expose the bash tool"
        )
    if not state.npm_requests:
        raise LocalSmokeError(
            f"{state.scenario.name} npm probe made no registry request"
        )
    authorizations = tuple(
        request.get("authorization") for request in state.npm_requests
    )
    unresolved_authorization = f"Bearer ${{{NPM_ACCESS_ENVIRONMENT}}}"
    if expected_environment_value is None and any(
        value not in {None, unresolved_authorization} for value in authorizations
    ):
        raise LocalSmokeError(
            f"{state.scenario.name} npm probe sent an unexpected authorization "
            "value without opt-in"
        )
    if expected_environment_value is not None:
        expected_authorization = f"Bearer {expected_environment_value}"
        if expected_authorization not in authorizations or any(
            value not in {None, expected_authorization} for value in authorizations
        ):
            raise LocalSmokeError(
                f"{state.scenario.name} npm probe did not send the selected token"
            )
    if len(state.model_requests) != 1:
        raise LocalSmokeError(
            f"{state.scenario.name} npm probe did not use exactly one model probe"
        )


def _tree_snapshot(root: Path) -> tuple[tuple[str, str, int, str], ...]:
    entries: list[tuple[str, str, int, str]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        observed = path.lstat()
        mode = stat.S_IMODE(observed.st_mode)
        if stat.S_ISLNK(observed.st_mode):
            entries.append((relative, "symlink", mode, os.readlink(path)))
        elif stat.S_ISDIR(observed.st_mode):
            entries.append((relative, "directory", mode, ""))
        elif stat.S_ISREG(observed.st_mode):
            digest = hashlib.sha256()
            try:
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
            except OSError as exc:
                raise LocalSmokeError(
                    f"could not hash consumer file {path}: {exc}"
                ) from exc
            entries.append((relative, "file", mode, digest.hexdigest()))
        else:
            entries.append((relative, "other", mode, ""))
    return tuple(entries)


def _credential_values(environment: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(
        environment[name]
        for name in CREDENTIAL_ENVIRONMENT
        if name in environment and environment[name]
    )


def _record_text(state: ProviderState) -> str:
    return json.dumps(
        {
            "models": [dict(headers) for headers in state.model_requests],
            "completions": [
                {
                    "path": record.path,
                    "headers": dict(record.headers),
                    "payload": dict(record.payload),
                }
                for record in state.completions
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


RunCommand = Callable[
    [tuple[str, ...], Path, dict[str, str], float], CommandResult
]


def _scenario_environment(
    source: Mapping[str, str],
    scenario_root: Path,
    *,
    cplt: Path,
    client: Path,
    client_name: str,
    ripgrep: Path,
) -> dict[str, str]:
    environment = dict(source)
    # The release gate must exercise cplt's reviewed defaults rather than an
    # ambient user or runner policy file.
    environment.pop("CPLT_CONFIG", None)
    # Prove the sanitizer with synthetic values without ever reading or passing
    # a caller's real ambient credentials to the child.
    environment.update(
        {
            name: f"{CREDENTIAL_CANARY_PREFIX}{name}"
            for name in CREDENTIAL_ENVIRONMENT
            if name not in GITHUB_CREDENTIAL_ENVIRONMENT
        }
    )
    # Leave every GitHub token variable absent so cplt must consult `gh` if
    # either the top-level preflight or actual launch sees caller PATH state.
    for name in GITHUB_CREDENTIAL_ENVIRONMENT:
        environment.pop(name, None)
    home = scenario_root / "home"
    xdg = scenario_root / "xdg"
    for directory in (home, xdg / "config", xdg / "cache", xdg / "data", xdg / "state"):
        directory.mkdir(parents=True, mode=0o700)
    client_bin = scenario_root / "client-bin"
    client_bin.mkdir(mode=0o700)
    aliases = [("cplt", cplt), (client_name, client)]
    if client_name == "opencode":
        aliases.append(("rg", ripgrep))
    for name, binary in aliases:
        alias = client_bin / name
        alias.symlink_to(binary)
        if alias.resolve(strict=True) != binary:
            raise LocalSmokeError(f"could not stage exact {name} binary for cplt")
    # Simulate an ambient gh account without consulting the runner's real gh
    # config or Keychain. The fixture yields a token only if cplt sees the
    # ambient config. A correct launcher replaces it with a private session
    # config before cplt can mediate native Copilot authentication.
    ambient_github_config = scenario_root / "ambient-github-config"
    ambient_github_config.mkdir(mode=0o700)
    (ambient_github_config / "hosts.yml").write_text(
        "github.com:\n  user: smoke-only\n", encoding="utf-8"
    )
    gh_invocations = scenario_root / "gh-invocations.log"
    guarded_gh = client_bin / "gh"
    guarded_gh.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"${{GH_CONFIG_DIR-}}\" >> "
        f"{shlex.quote(str(gh_invocations))}\n"
        f"if [ \"${{GH_CONFIG_DIR-}}\" = "
        f"{shlex.quote(str(ambient_github_config))} ]; then\n"
        f"  printf '%s\\n' {shlex.quote(AMBIENT_GITHUB_TOKEN_CANARY)}\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    guarded_gh.chmod(0o500)
    parent_tool_invocations = scenario_root / "parent-tool-invocations.log"
    for name in PARENT_TOOL_CANARIES:
        canary = client_bin / name
        canary.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' {shlex.quote(name)} >> "
            f"{shlex.quote(str(parent_tool_invocations))}\n"
            "exit 97\n",
            encoding="utf-8",
        )
        canary.chmod(0o500)
    path_entries: list[str] = [str(client_bin)]
    for binary in (cplt, client):
        parent = str(binary.parent)
        if parent not in path_entries:
            path_entries.append(parent)
    path_entries.extend(("/usr/bin", "/bin", "/usr/sbin", "/sbin"))
    environment.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(xdg / "config"),
            "XDG_CACHE_HOME": str(xdg / "cache"),
            "XDG_DATA_HOME": str(xdg / "data"),
            "XDG_STATE_HOME": str(xdg / "state"),
            "GH_CONFIG_DIR": str(ambient_github_config),
            "PATH": os.pathsep.join(dict.fromkeys(path_entries)),
            "LANG": environment.get("LANG", "en_US.UTF-8"),
            "TERM": "dumb",
        }
    )
    return environment


def _run_scenario(
    *,
    scenario: Scenario,
    scenario_root: Path,
    distribution_root: Path,
    cplt: Path,
    client: Path,
    ripgrep: Path,
    environment: Mapping[str, str],
    timeout: float,
    run_process: RunCommand,
) -> ScenarioReport:
    consumer = scenario_root / "consumer"
    consumer.mkdir(mode=0o700)
    audit_marker = scenario_root / "cplt-audit-escaped"
    git = Path("/usr/bin/git")
    try:
        subprocess.run(
            (str(git), "init", "-q"),
            cwd=consumer,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=10,
            check=True,
        )
        subprocess.run(
            (
                str(git),
                "config",
                "core.fsmonitor",
                f"/usr/bin/touch {audit_marker}",
            ),
            cwd=consumer,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LocalSmokeError(
            f"{scenario.name} could not seed the cplt audit escape regression: {exc}"
        ) from exc
    if scenario.client == "opencode":
        (consumer / "AGENTS.md").write_text(
            "# Disposable project guidance\n",
            encoding="utf-8",
        )
        project_config = consumer / ".opencode"
        project_config.mkdir(mode=0o700)
        (project_config / ".gitignore").write_text(
            "node_modules\npackage.json\npackage-lock.json\nbun.lock\n.gitignore\n",
            encoding="utf-8",
        )
        (project_config / "AGENTS.md").write_text(
            "# Inert OpenCode-local metadata fixture\n",
            encoding="utf-8",
        )
        (project_config / "package.json").write_text("{}\n", encoding="utf-8")
    before = _tree_snapshot(consumer)
    scenario_environment = _scenario_environment(
        environment,
        scenario_root,
        cplt=cplt,
        client=client,
        client_name=scenario.client,
        ripgrep=ripgrep,
    )
    canaries = (
        *_credential_values(scenario_environment),
        AMBIENT_GITHUB_TOKEN_CANARY,
    )
    with LoopbackProvider(scenario) as provider:
        config = LOCAL.LocalConfig(
            client=scenario.client,
            agent="barista",
            context=scenario.context,
            provider_id=PROVIDER_ID,
            base_url=provider.base_url,
            model_id=MODEL_ID,
        )
        LOCAL.save_config(config, environment=scenario_environment)
        # Keep a side-effect-free preview for payload/env assertions, but run
        # the actual gate through the public top-level CLI below.
        launch = LOCAL.build_local_launch(
            config,
            distribution_root=distribution_root,
            project_dir=consumer,
            cplt=cplt,
            client=client,
            client_arguments=(),
            run_prompt=PROMPT,
            environment=scenario_environment,
            resolve_credentials=False,
            prepare_state=False,
            platform="darwin",
        )
        expected_payload = (distribution_root / scenario.relative_payload).resolve(
            strict=True
        )
        if launch.payload != expected_payload:
            raise LocalSmokeError(
                f"{scenario.name} selected {launch.payload}, expected {expected_payload}"
            )
        public_command = [
            sys.executable,
            "-I",
            "-S",
            str(distribution_root / "scripts/grillmester.py"),
            "local",
            "run",
            "--client",
            scenario.client,
            "--agent",
            "barista",
            "--project-dir",
            str(consumer),
        ]
        if scenario.context == "full":
            public_command.append("--full")
        public_command.append(PROMPT)
        result = run_process(
            tuple(public_command), consumer, dict(scenario_environment), timeout
        )
    if audit_marker.exists():
        raise LocalSmokeError(
            f"{scenario.name} let cplt execute repository core.fsmonitor "
            "outside the sandbox"
        )
    if result.returncode != 0:
        raise LocalSmokeError(
            f"{scenario.name} exited {result.returncode}: {result.output[-4000:]}"
        )
    gh_invocations = scenario_root / "gh-invocations.log"
    if gh_invocations.exists():
        raise LocalSmokeError(
            f"{scenario.name} let cplt or the client execute caller-PATH gh outside "
            "the explicit GitHub opt-in"
        )
    if (scenario_root / "parent-tool-invocations.log").exists():
        raise LocalSmokeError(
            f"{scenario.name} let cplt or the client execute a caller-PATH "
            "parent tool"
        )
    if sentinel_for(scenario) not in result.output:
        raise LocalSmokeError(
            f"{scenario.name} output did not contain its provider sentinel: "
            f"{result.output[-2000:]}"
        )
    validate_provider_state(provider.state)
    after = _tree_snapshot(consumer)
    if after != before:
        raise LocalSmokeError(
            f"{scenario.name} changed the consumer tree: before={before!r}, after={after!r}"
        )
    command_text = json.dumps(list(launch.command), ensure_ascii=False)
    environment_text = json.dumps(
        launch.environment, ensure_ascii=False, sort_keys=True
    )
    provider_text = _record_text(provider.state)
    for canary in canaries:
        if any(
            canary in value
            for value in (command_text, environment_text, provider_text, result.output)
        ):
            raise LocalSmokeError(
                f"{scenario.name} exposed an ambient credential canary"
            )
    return ScenarioReport(
        scenario=scenario,
        payload=launch.payload,
        requests=len(provider.state.completions),
        consumer_clean=True,
        credentials_scrubbed=True,
    )


def run_matrix(
    *,
    distribution_root: Path,
    cplt: Path,
    opencode: Path,
    copilot: Path,
    ripgrep: Path,
    environment: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    run_command: RunCommand = run_command,
    platform: str | None = None,
) -> tuple[ScenarioReport, ...]:
    platform = sys.platform if platform is None else platform
    if platform != "darwin":
        raise LocalSmokeError("the local-model cplt smoke is supported only on macOS")
    source = os.environ if environment is None else environment
    home_value = source.get("HOME")
    if not home_value:
        raise LocalSmokeError("HOME is required for an isolated cplt smoke root")
    try:
        home = Path(home_value).expanduser().resolve(strict=True)
    except OSError as exc:
        raise LocalSmokeError(f"could not resolve HOME for the smoke: {exc}") from exc
    if not home.is_dir():
        raise LocalSmokeError("HOME must be a directory")
    reports: list[ScenarioReport] = []
    with tempfile.TemporaryDirectory(
        prefix=".grillmester-local-smoke-", dir=home
    ) as directory:
        sandbox = Path(directory).resolve(strict=True)
        for scenario in SCENARIOS:
            scenario_root = sandbox / scenario.name
            scenario_root.mkdir(mode=0o700)
            reports.append(
                _run_scenario(
                    scenario=scenario,
                    scenario_root=scenario_root,
                    distribution_root=distribution_root.resolve(strict=True),
                    cplt=cplt.resolve(strict=True),
                    client=(opencode if scenario.client == "opencode" else copilot).resolve(
                        strict=True
                    ),
                    ripgrep=ripgrep.resolve(strict=True),
                    environment=source,
                    timeout=timeout,
                    run_process=run_command,
                )
            )
    return tuple(reports)


def verify_release_payloads_unchanged(distribution_root: Path) -> None:
    """Recheck immutable inputs after clients have completed runtime work."""

    seen: set[tuple[Path, str]] = set()
    for relative, target in LOCAL.PAYLOADS.values():
        record = (relative, target)
        if record in seen:
            continue
        seen.add(record)
        LOCAL._verify_manifested_payload(
            (distribution_root / relative).resolve(strict=True),
            expected_target=target,
        )


def run_npm_access_matrix(
    *,
    distribution_root: Path,
    cplt: Path,
    opencode: Path,
    copilot: Path,
    ripgrep: Path,
    environment: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    run_process: RunCommand = run_command,
    platform: str | None = None,
) -> None:
    """Prove tool-subprocess token absence and explicit access in both clients."""

    platform = sys.platform if platform is None else platform
    if platform != "darwin":
        raise LocalSmokeError("the npm access smoke is supported only on macOS")
    source = os.environ if environment is None else environment
    home_value = source.get("HOME")
    if not home_value:
        raise LocalSmokeError("HOME is required for the npm access smoke")
    home = Path(home_value).expanduser().resolve(strict=True)
    distribution_root = distribution_root.resolve(strict=True)
    cplt = cplt.resolve(strict=True)
    opencode = opencode.resolve(strict=True)
    copilot = copilot.resolve(strict=True)
    ripgrep = ripgrep.resolve(strict=True)
    npm_raw = shutil.which("npm", path=source.get("PATH"))
    if npm_raw is None:
        raise LocalSmokeError("npm is required for the package-access smoke")
    npm_entry = Path(npm_raw).expanduser()
    npm = npm_entry.resolve(strict=True)
    if not npm.is_file() or not os.access(npm, os.X_OK):
        raise LocalSmokeError("npm must resolve to an executable regular file")
    with tempfile.TemporaryDirectory(
        prefix=".grillmester-npm-access-smoke-", dir=home
    ) as directory:
        root = Path(directory).resolve(strict=True)
        for client_name, client in (("opencode", opencode), ("copilot", copilot)):
            for npm_access in (False, True):
                label = "allowed" if npm_access else "denied"
                scenario = Scenario(client_name, "focused")
                scenario_root = root / f"{client_name}-{label}"
                scenario_root.mkdir(mode=0o700)
                consumer = scenario_root / "consumer"
                consumer.mkdir(mode=0o700)
                scenario_environment = _scenario_environment(
                    source,
                    scenario_root,
                    cplt=cplt,
                    client=client,
                    client_name=client_name,
                    ripgrep=ripgrep,
                )
                scenario_environment["PATH"] = os.pathsep.join(
                    dict.fromkeys(
                        (
                            str(npm_entry.parent),
                            *scenario_environment["PATH"].split(os.pathsep),
                        )
                    )
                )
                scenario_environment[NPM_ACCESS_ENVIRONMENT] = (
                    f"{CREDENTIAL_CANARY_PREFIX}{NPM_ACCESS_ENVIRONMENT}"
                )
                tool_command = "npm ping"
                final_content = f"{NPM_ACCESS_SENTINEL}_{client_name}_{label}"
                with LoopbackProvider(
                    scenario,
                    tool_command=tool_command,
                    final_content=final_content,
                ) as provider:
                    registry = provider.base_url.removesuffix("/v1") + "/npm/"
                    registry_authority = registry.removeprefix("http:")
                    (consumer / ".npmrc").write_text(
                        f"registry={registry}\n"
                        f"{registry_authority}:_authToken="
                        f"${{{NPM_ACCESS_ENVIRONMENT}}}\n",
                        encoding="utf-8",
                    )
                    before = _tree_snapshot(consumer)
                    config = LOCAL.LocalConfig(
                        client=client_name,
                        agent="barista",
                        context="focused",
                        provider_id=PROVIDER_ID,
                        base_url=provider.base_url,
                        model_id=MODEL_ID,
                    )
                    LOCAL.save_config(config, environment=scenario_environment)
                    preview = LOCAL.build_local_launch(
                        config,
                        distribution_root=distribution_root,
                        project_dir=consumer,
                        cplt=cplt,
                        client=client,
                        run_prompt=PROMPT,
                        environment=scenario_environment,
                        npm_access=npm_access,
                        resolve_credentials=False,
                        prepare_state=False,
                        platform="darwin",
                    )
                    if npm_access:
                        if (
                            preview.redacted_environment.get(NPM_ACCESS_ENVIRONMENT)
                            != "<redacted>"
                            or NPM_ACCESS_ENVIRONMENT
                            not in preview.secret_environment
                        ):
                            raise LocalSmokeError(
                                f"{client_name} npm preview did not redact selected token"
                            )
                    elif NPM_ACCESS_ENVIRONMENT in preview.environment:
                        raise LocalSmokeError(
                            f"{client_name} npm preview exposed token without opt-in"
                        )
                    public_command = [
                        sys.executable,
                        "-I",
                        "-S",
                        str(distribution_root / "scripts/grillmester.py"),
                        "local",
                        "run",
                        "--client",
                        client_name,
                        "--agent",
                        "barista",
                        "--project-dir",
                        str(consumer),
                    ]
                    if npm_access:
                        public_command.append("--npm-access")
                    public_command.append(PROMPT)
                    result = run_process(
                        tuple(public_command),
                        consumer,
                        dict(scenario_environment),
                        timeout,
                    )
                if result.returncode != 0 or final_content not in result.output:
                    raise LocalSmokeError(
                        f"{client_name} npm {label} probe failed: "
                        f"{result.output[-3000:]}"
                    )
                try:
                    validate_npm_provider_state(
                        provider.state,
                        expected_environment_value=(
                            scenario_environment[NPM_ACCESS_ENVIRONMENT]
                            if npm_access
                            else None
                        ),
                    )
                except LocalSmokeError as exc:
                    raise LocalSmokeError(
                        f"{client_name} npm {label} provider validation failed: {exc}; "
                        f"client output: {result.output[-2000:]}"
                    ) from exc
                if _tree_snapshot(consumer) != before:
                    raise LocalSmokeError(
                        f"{client_name} npm {label} probe changed the consumer"
                    )
                token = scenario_environment[NPM_ACCESS_ENVIRONMENT]
                if token in result.output or token in _record_text(provider.state):
                    raise LocalSmokeError(
                        f"{client_name} npm {label} probe leaked the synthetic token "
                        "to the client transcript or model"
                    )


def run_github_guard_matrix(
    *,
    distribution_root: Path,
    cplt: Path,
    opencode: Path,
    environment: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    run_process: RunCommand = run_command,
    platform: str | None = None,
) -> None:
    """Prove explicit-token issue creation and cplt's blocking decisions locally."""

    platform = sys.platform if platform is None else platform
    if platform != "darwin":
        raise LocalSmokeError("the GitHub guard smoke is supported only on macOS")
    source = os.environ if environment is None else environment
    home_value = source.get("HOME")
    if not home_value:
        raise LocalSmokeError("HOME is required for the GitHub guard smoke")
    home = Path(home_value).expanduser().resolve(strict=True)
    with tempfile.TemporaryDirectory(
        prefix=".grillmester-github-guard-smoke-", dir=home
    ) as directory:
        root = Path(directory).resolve(strict=True)
        consumer = root / "consumer"
        fake_bin = root / "fake-bin"
        isolated_home = root / "home"
        xdg = root / "xdg"
        for path in (
            consumer,
            fake_bin,
            isolated_home,
            xdg / "config",
            xdg / "cache",
            xdg / "data",
            xdg / "state",
        ):
            path.mkdir(parents=True, mode=0o700)
        git = Path("/usr/bin/git")
        try:
            subprocess.run(
                (str(git), "init", "-q"),
                cwd=consumer,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=10,
                check=True,
            )
            subprocess.run(
                (
                    str(git),
                    "remote",
                    "add",
                    "origin",
                    "https://github.com/navikt/grillmester-local-smoke.git",
                ),
                cwd=consumer,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=10,
                check=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise LocalSmokeError(f"could not prepare GitHub guard fixture: {exc}") from exc

        fake_gh = fake_bin / "gh"
        fake_gh.write_text(
            "#!/bin/sh\n"
            f"[ \"${{GH_TOKEN-}}\" = {shlex.quote(GITHUB_GUARD_TOKEN)} ] || exit 96\n"
            f"printf '%s:%s\\n' {shlex.quote(GITHUB_GUARD_SENTINEL)} \"$*\"\n",
            encoding="utf-8",
        )
        fake_gh.chmod(0o500)
        (fake_bin / "opencode").symlink_to(opencode)
        scenario_environment = dict(source)
        scenario_environment.pop("CPLT_CONFIG", None)
        scenario_environment.update(
            {
                "HOME": str(isolated_home),
                "XDG_CONFIG_HOME": str(xdg / "config"),
                "XDG_CACHE_HOME": str(xdg / "cache"),
                "XDG_DATA_HOME": str(xdg / "data"),
                "XDG_STATE_HOME": str(xdg / "state"),
                "GH_TOKEN": GITHUB_GUARD_TOKEN,
                "PATH": os.pathsep.join(
                    dict.fromkeys(
                        (
                            str(fake_bin),
                            str(cplt.parent),
                            str(opencode.parent),
                            "/usr/bin",
                            "/bin",
                            "/usr/sbin",
                            "/sbin",
                        )
                    )
                ),
                "LANG": source.get("LANG", "en_US.UTF-8"),
                "TERM": "dumb",
            }
        )
        config = LOCAL.LocalConfig(
            client="opencode",
            agent="barista",
            context="focused",
            provider_id=PROVIDER_ID,
            base_url="http://127.0.0.1:9/v1",
            model_id=MODEL_ID,
        )
        launch = LOCAL.build_local_launch(
            config,
            distribution_root=distribution_root,
            project_dir=consumer,
            cplt=cplt,
            client=opencode,
            environment=scenario_environment,
            github_access=True,
            platform="darwin",
        )
        prefix = list(launch.command[: launch.command.index("--")])
        agent_index = prefix.index("--agent")
        del prefix[agent_index : agent_index + 2]

        def guarded(*arguments: str) -> CommandResult:
            # cplt resolves `exec -- gh ...` to an absolute binary before it
            # installs the sandbox PATH wrappers. Resolve through the shell
            # inside the sandbox instead; this is the same PATH lookup used
            # when OpenCode or Copilot invokes gh.
            return run_process(
                tuple((*prefix, "exec", "-c", shlex.join(("gh", *arguments)))),
                consumer,
                dict(launch.environment),
                timeout,
            )

        allowed = guarded(
            "issue",
            "create",
            "--title",
            "Smoke only",
            "--body",
            "No GitHub request is made",
        )
        if (
            allowed.returncode != 0
            or f"{GITHUB_GUARD_SENTINEL}:issue create" not in allowed.output
        ):
            raise LocalSmokeError(
                "cplt did not allow the current-repository fake issue creation: "
                f"{allowed.output[-2000:]}"
            )

        for label, arguments in (
            (
                "cross-repo issue",
                (
                    "issue",
                    "create",
                    "--repo",
                    "other-org/other-repo",
                    "--title",
                    "blocked",
                    "--body",
                    "blocked",
                ),
            ),
            ("destructive issue", ("issue", "delete", "1")),
            ("token extraction", ("auth", "token")),
        ):
            blocked = guarded(*arguments)
            if blocked.returncode == 0:
                raise LocalSmokeError(
                    f"cplt unexpectedly allowed {label}: {blocked.output[-2000:]}"
                )
            if GITHUB_GUARD_SENTINEL in blocked.output:
                raise LocalSmokeError(f"cplt forwarded blocked {label} to fake gh")


def _regular_executable(
    value: Path | None,
    *,
    name: str,
    environment: Mapping[str, str],
) -> tuple[Path | None, str | None]:
    if value is None:
        return None, f"{name} was not found"
    try:
        resolved = value.expanduser().resolve(strict=True)
        observed = resolved.stat()
    except OSError as exc:
        return None, f"{name} is unavailable: {exc}"
    if not stat.S_ISREG(observed.st_mode) or not os.access(resolved, os.X_OK):
        return None, f"{name} is not an executable regular file: {resolved}"
    if resolved.name != name:
        alias = shutil.which(name, path=environment.get("PATH"))
        try:
            alias_resolves = alias is not None and Path(alias).resolve(strict=True) == resolved
        except OSError:
            alias_resolves = False
        if name == "cplt" or not alias_resolves:
            return (
                None,
                f"{name} binary resolves to {resolved}, but PATH has no trusted "
                f"{name!r} alias for cplt",
            )
    return resolved, None


def _version_environment(
    *, state: Path, binary: Path, environment: Mapping[str, str]
) -> dict[str, str]:
    home = state / binary.name
    home.mkdir(mode=0o700)
    path = os.pathsep.join(
        dict.fromkeys((str(binary.parent), "/usr/bin", "/bin", "/usr/sbin", "/sbin"))
    )
    return {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / "config"),
        "XDG_CACHE_HOME": str(home / "cache"),
        "XDG_DATA_HOME": str(home / "data"),
        "XDG_STATE_HOME": str(home / "state"),
        "PATH": path,
        "LANG": environment.get("LANG", "en_US.UTF-8"),
        "TERM": "dumb",
        "COPILOT_AUTO_UPDATE": "false",
        "COPILOT_OTEL_ENABLED": "false",
    }


def inspect_prerequisites(
    *,
    cplt: Path | None,
    opencode: Path | None,
    copilot: Path | None,
    ripgrep: Path | None,
    state: Path,
    environment: Mapping[str, str] | None = None,
    platform: str | None = None,
) -> PrerequisiteResult:
    source = os.environ if environment is None else environment
    platform = sys.platform if platform is None else platform
    problems: list[str] = []
    if platform != "darwin":
        problems.append("macOS is required for the forced-proxy cplt gate")
    resolved: dict[str, Path | None] = {}
    for name, candidate in (
        ("cplt", cplt),
        ("opencode", opencode),
        ("copilot", copilot),
        ("rg", ripgrep),
    ):
        binary, problem = _regular_executable(
            candidate, name=name, environment=source
        )
        resolved[name] = binary
        if problem is not None:
            problems.append(problem)
    expected = {
        "cplt": f"cplt {EXPECTED_CPLT_RELEASE}",
        "opencode": EXPECTED_OPENCODE_VERSION,
        "copilot": f"GitHub Copilot CLI {EXPECTED_COPILOT_VERSION}.",
    }
    for name in ("cplt", "opencode", "copilot"):
        binary = resolved[name]
        if binary is None:
            continue
        try:
            version = run_command(
                (str(binary), "--version"),
                state,
                _version_environment(state=state, binary=binary, environment=source),
                20,
                max_output_bytes=64 * 1024,
            )
        except LocalSmokeError as exc:
            problems.append(f"could not inspect {name} version: {exc}")
            continue
        lines = tuple(
            line.strip() for line in version.output.splitlines() if line.strip()
        )
        matches = tuple(line for line in lines if line == expected[name])
        if version.returncode != 0 or len(matches) != 1:
            preview = " | ".join(lines[:3]) if lines else "<no output>"
            problems.append(
                f"expected exactly one {name} version line {expected[name]!r}, "
                f"found {len(matches)} in {preview!r} (exit {version.returncode})"
            )
    return PrerequisiteResult(
        resolved["cplt"],
        resolved["opencode"],
        resolved["copilot"],
        resolved["rg"],
        tuple(problems),
    )


def _resolve_binary(value: str | None, *, name: str, environment: Mapping[str, str]) -> Path | None:
    if value is not None:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute() and candidate.parent == Path("."):
            # A bare command name selects the PATH entry, matching the
            # documented `--cplt cplt` invocation; explicit paths stay paths.
            found = shutil.which(value, path=environment.get("PATH"))
            if found is not None:
                candidate = Path(found)
    else:
        found = shutil.which(name, path=environment.get("PATH"))
        candidate = Path(found) if found else None
    return candidate


def resolve_and_inspect_prerequisites(
    *,
    cplt: str | None,
    opencode: str | None,
    copilot: str | None,
    ripgrep: str | None,
    environment: Mapping[str, str] | None = None,
    platform: str | None = None,
) -> PrerequisiteResult:
    source = os.environ if environment is None else environment
    home_value = source.get("HOME")
    if not home_value:
        return PrerequisiteResult(None, None, None, None, ("HOME is not set",))
    try:
        home = Path(home_value).expanduser().resolve(strict=True)
    except OSError as exc:
        return PrerequisiteResult(
            None, None, None, None, (f"could not resolve HOME: {exc}",)
        )
    if not home.is_dir():
        return PrerequisiteResult(
            None, None, None, None, ("HOME must be a directory",)
        )
    try:
        with tempfile.TemporaryDirectory(
            prefix=".grillmester-local-prereq-", dir=home
        ) as directory:
            return inspect_prerequisites(
                cplt=_resolve_binary(cplt, name="cplt", environment=source),
                opencode=_resolve_binary(opencode, name="opencode", environment=source),
                copilot=_resolve_binary(copilot, name="copilot", environment=source),
                ripgrep=_resolve_binary(ripgrep, name="rg", environment=source),
                state=Path(directory),
                environment=source,
                platform=platform,
            )
    except OSError as exc:
        return PrerequisiteResult(
            None,
            None,
            None,
            None,
            (f"could not create isolated prerequisite state: {exc}",),
        )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--cplt", help="path to exact gated cplt")
    parser.add_argument("--opencode", help="path to exact gated OpenCode")
    parser.add_argument("--copilot", help="path to exact gated Copilot CLI")
    parser.add_argument("--ripgrep", help="path to ripgrep exposed to OpenCode tools")
    parser.add_argument(
        "--distribution-root",
        type=Path,
        help="extracted Grillmester bundle root to exercise",
    )
    parser.add_argument(
        "--require-binaries",
        action="store_true",
        help="fail instead of skip when the complete pinned matrix is unavailable",
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    distribution_root: Path = ROOT,
    environment: Mapping[str, str] | None = None,
    platform: str | None = None,
) -> int:
    global LOCAL
    arguments = parse_args(argv)
    if arguments.distribution_root is not None:
        distribution_root = arguments.distribution_root
    try:
        distribution_root = distribution_root.expanduser().resolve(strict=True)
        LOCAL = _load_local_launcher(distribution_root)
    except (LocalSmokeError, OSError) as exc:
        print(f"Grillmester local smoke failed: {exc}", file=sys.stderr)
        return 1
    source = os.environ if environment is None else environment
    prerequisites = resolve_and_inspect_prerequisites(
        cplt=arguments.cplt,
        opencode=arguments.opencode,
        copilot=arguments.copilot,
        ripgrep=arguments.ripgrep,
        environment=source,
        platform=platform,
    )
    if prerequisites.problems:
        message = "; ".join(prerequisites.problems) + ". No scenario was executed."
        if arguments.require_binaries:
            print(f"ERROR: {message}", file=sys.stderr)
            return 1
        print(f"SKIP: {message}")
        return 0
    assert prerequisites.cplt is not None
    assert prerequisites.opencode is not None
    assert prerequisites.copilot is not None
    assert prerequisites.ripgrep is not None
    try:
        reports = run_matrix(
            distribution_root=distribution_root,
            cplt=prerequisites.cplt,
            opencode=prerequisites.opencode,
            copilot=prerequisites.copilot,
            ripgrep=prerequisites.ripgrep,
            environment=source,
            timeout=arguments.timeout,
            platform=platform,
        )
        run_npm_access_matrix(
            distribution_root=distribution_root,
            cplt=prerequisites.cplt,
            opencode=prerequisites.opencode,
            copilot=prerequisites.copilot,
            ripgrep=prerequisites.ripgrep,
            environment=source,
            timeout=arguments.timeout,
            platform=platform,
        )
        run_github_guard_matrix(
            distribution_root=distribution_root,
            cplt=prerequisites.cplt,
            opencode=prerequisites.opencode,
            environment=source,
            timeout=arguments.timeout,
            platform=platform,
        )
        verify_release_payloads_unchanged(distribution_root)
    except (LocalSmokeError, LOCAL.LocalModeError, OSError) as exc:
        print(f"Grillmester local smoke failed: {exc}", file=sys.stderr)
        return 1
    for report in reports:
        print(
            f"PASS: {report.scenario.name} model={MODEL_ID} "
            f"payload={report.payload} requests={report.requests}"
        )
    print(
        "Grillmester local smoke passed: 4/4 focused/full OpenCode/Copilot "
        "scenarios through the release-test cplt baseline; ripgrep available on "
        "PATH; cplt audit escape and caller-PATH parent tools blocked; explicit "
        "fake-gh current-repo issue allowed while cross-repo, destructive and "
        "token-extraction calls were blocked; npm token absent by default and "
        "available only by explicit project-bound opt-in in both clients; consumer "
        "clean; release payloads unchanged; credentials scrubbed."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main tests
    raise SystemExit(main())
