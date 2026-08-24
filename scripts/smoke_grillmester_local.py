#!/usr/bin/env python3
"""Gate local-model launches through real cplt and installed terminal clients.

The smoke never contacts a model. A deterministic OpenAI-compatible provider
binds to loopback, returns one fixed streamed response, and captures the exact
request made by each client for contract validation.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import selectors
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
EXPECTED_CPLT_RELEASE = "2026.08.17-062831-1008a92"
EXPECTED_OPENCODE_VERSION = "1.18.20"
EXPECTED_COPILOT_VERSION = "1.0.80"
MODEL_ID = "grillmester-local-smoke-v1"
PROVIDER_ID = "smoke"
SERVER_HOST = "127.0.0.1"
PROMPT = "Return the deterministic Grillmester local smoke sentinel only."
SUBAGENT_PROMPT = "Return SUBAGENT_LOCAL_ONLY and do not use tools."
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
DEFAULT_TIMEOUT = 45.0
CREDENTIAL_CANARY_PREFIX = "GRILLMESTER_LOCAL_SMOKE_CREDENTIAL_"
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
    "NPM_TOKEN",
    "OPENAI_API_KEY",
)


class LocalSmokeError(RuntimeError):
    """Raised when a local-model smoke contract cannot be proven."""


def _load_local_launcher() -> Any:
    name = "grillmester_local_for_local_smoke"
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/grillmester_local.py")
    if spec is None or spec.loader is None:
        raise LocalSmokeError("could not load scripts/grillmester_local.py")
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
    model_requests: list[Mapping[str, str]] = field(default_factory=list)
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


def _stream_body(state: ProviderState) -> bytes:
    request_number = len(state.completions)
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
        if self.path != "/v1/models":
            self._reject(404, f"unsupported GET {self.path}")
            return
        self.server.state.record_models(
            {name.lower(): value for name, value in self.headers.items()}
        )
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

    def __init__(self, scenario: Scenario):
        self.state = ProviderState(scenario)
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


def validate_provider_state(state: ProviderState) -> None:
    if state.violations:
        raise LocalSmokeError(
            f"{state.scenario.name} provider protocol violation: "
            + "; ".join(state.violations)
        )
    expected_completions = 3 if state.scenario.client == "copilot" else 1
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
            entries.append((relative, "file", mode, str(observed.st_size)))
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
    # Prove the sanitizer with synthetic values without ever reading or passing
    # a caller's real ambient credentials to the child.
    environment.update(
        {
            name: f"{CREDENTIAL_CANARY_PREFIX}{name}"
            for name in CREDENTIAL_ENVIRONMENT
        }
    )
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
            "PATH": os.pathsep.join(dict.fromkeys(path_entries)),
            "LANG": environment.get("LANG", "en_US.UTF-8"),
            "TERM": "dumb",
        }
    )
    return environment


def _scenario_client_arguments(scenario: Scenario) -> tuple[str, ...]:
    if scenario.client == "opencode":
        return (
            "run",
            "--format",
            "json",
            "--title",
            f"Grillmester local smoke {scenario.context}",
            PROMPT,
        )
    return ("--output-format", "json", "--stream", "on", "-p", PROMPT)


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
    before = _tree_snapshot(consumer)
    scenario_environment = _scenario_environment(
        environment,
        scenario_root,
        cplt=cplt,
        client=client,
        client_name=scenario.client,
        ripgrep=ripgrep,
    )
    canaries = _credential_values(scenario_environment)
    with LoopbackProvider(scenario) as provider:
        config = LOCAL.LocalConfig(
            client=scenario.client,
            agent="barista",
            context=scenario.context,
            provider_id=PROVIDER_ID,
            base_url=provider.base_url,
            model_id=MODEL_ID,
        )
        LOCAL.probe_model(config, environment=scenario_environment, timeout=5)
        launch = LOCAL.build_local_launch(
            config,
            distribution_root=distribution_root,
            project_dir=consumer,
            cplt=cplt,
            client=client,
            client_arguments=_scenario_client_arguments(scenario),
            environment=scenario_environment,
            platform="darwin",
        )
        expected_payload = (distribution_root / scenario.relative_payload).resolve(
            strict=True
        )
        if launch.payload != expected_payload:
            raise LocalSmokeError(
                f"{scenario.name} selected {launch.payload}, expected {expected_payload}"
            )
        staged_ripgrep = (
            Path(launch.environment["XDG_CACHE_HOME"]) / "opencode/bin/rg"
        )
        if scenario.client == "opencode":
            try:
                staged_mode = stat.S_IMODE(staged_ripgrep.stat().st_mode)
                staged_content = staged_ripgrep.read_bytes()
                source_content = ripgrep.read_bytes()
            except OSError as exc:
                raise LocalSmokeError(
                    f"{scenario.name} did not stage ripgrep for offline Glob/Grep: {exc}"
                ) from exc
            if staged_mode != 0o500 or staged_content != source_content:
                raise LocalSmokeError(
                    f"{scenario.name} staged ripgrep with the wrong identity or mode"
                )
        elif staged_ripgrep.exists():
            raise LocalSmokeError(
                f"{scenario.name} unexpectedly staged OpenCode-only ripgrep"
            )
        result = run_process(
            tuple(launch.command), consumer, dict(launch.environment), timeout
        )
    if result.returncode != 0:
        raise LocalSmokeError(
            f"{scenario.name} exited {result.returncode}: {result.output[-4000:]}"
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
    environment_text = json.dumps(dict(launch.environment), ensure_ascii=False, sort_keys=True)
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
        lines = tuple(line.strip() for line in version.output.splitlines() if line.strip())
        observed = lines[0] if lines else ""
        if version.returncode != 0 or observed != expected[name]:
            problems.append(
                f"expected {name} version {expected[name]!r}, found {observed!r} "
                f"(exit {version.returncode})"
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
    parser.add_argument("--ripgrep", help="path to ripgrep staged for OpenCode tools")
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
    arguments = parse_args(argv)
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
        "scenarios through exact cplt; ripgrep staged for OpenCode; consumer "
        "clean; credentials scrubbed."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main tests
    raise SystemExit(main())
