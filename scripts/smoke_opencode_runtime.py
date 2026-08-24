#!/usr/bin/env python3
"""Exercise Grillmester permissions and delegation through a real OpenCode runtime.

The smoke uses a deterministic loopback-only OpenAI-compatible provider. It does
not contact a model or execute any provider-requested command outside a disposable
consumer repository. Unlike ``smoke_opencode.py``, this script drives native
``task``, ``skill``, ``read``, and ``write`` tool calls end to end.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = ROOT / "targets/opencode-v1"
_BASELINE_SPEC = importlib.util.spec_from_file_location(
    "grillmester_release_test_baseline_for_runtime_smoke",
    ROOT / "scripts/release_test_baseline.py",
)
if _BASELINE_SPEC is None or _BASELINE_SPEC.loader is None:
    raise RuntimeError("could not load release-test baseline contract")
_BASELINE_MODULE = importlib.util.module_from_spec(_BASELINE_SPEC)
sys.modules[_BASELINE_SPEC.name] = _BASELINE_MODULE
_BASELINE_SPEC.loader.exec_module(_BASELINE_MODULE)
_RELEASE_TEST = _BASELINE_MODULE.CONTRACT["releaseTest"]
EXPECTED_OPENCODE_VERSION = _RELEASE_TEST["opencodeVersion"]
EXPECTED_CPLT_RELEASE = _RELEASE_TEST["cpltRelease"]
MODEL_ID = "permission-probe"
MODEL_REF = f"probe/{MODEL_ID}"
SERVER_HOST = "127.0.0.1"
ENV_SENTINEL = "GRILLMESTER_RUNTIME_SMOKE_SECRET"
SKILL_MARKER = "# OpenCode v1 Skill Validation"
WRITE_CONTENT = "grillmester-runtime-smoke\n"
PLUGIN_CANARY_CONTENT = "grillmester-project-plugin-executed\n"
CONSUMER_INSTRUCTION_MARKER = "GRILLMESTER_RUNTIME_CONSUMER_INSTRUCTION_7D4A"
HOSTILE_PROJECT_MARKER = "GRILLMESTER_RUNTIME_HOSTILE_PROJECT_CONFIG_91BC"
CPLT_PASSTHROUGH_ENV = (
    "OPENCODE_CONFIG_CONTENT",
    "OPENCODE_CONFIG_DIR",
    "OPENCODE_DISABLE_AUTOUPDATE",
    "OPENCODE_PURE",
    "OPENCODE_DISABLE_CLAUDE_CODE",
    "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT",
    "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS",
    "OPENCODE_DISABLE_DEFAULT_PLUGINS",
    "OPENCODE_DISABLE_EXTERNAL_SKILLS",
    "OPENCODE_DISABLE_LSP_DOWNLOAD",
    "OPENCODE_DISABLE_MODELS_FETCH",
    "OPENCODE_DISABLE_PROJECT_CONFIG",
    "OPENCODE_DB",
    "OPENCODE_AUTO_SHARE",
    "PWD",
)


class RuntimeSmokeError(RuntimeError):
    """Raised when real OpenCode behavior violates the target contract."""


@dataclass(frozen=True)
class Scenario:
    name: str
    subagent: str
    action: str
    target: Path
    auto: bool = False


@dataclass
class ProviderState:
    scenario: Scenario
    requests: list[dict[str, Any]] = field(default_factory=list)
    requested_tools: list[str] = field(default_factory=list)
    runtime_output: str = ""
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, request: dict[str, Any]) -> None:
        with self.lock:
            self.requests.append(request)

    def record_requested_tool(self, tool: str) -> None:
        """Record a fake-provider request separately from runtime execution evidence."""

        with self.lock:
            self.requested_tools.append(tool)

    def requested_tool_names(self) -> set[str]:
        with self.lock:
            return set(self.requested_tools)

    def tool_results(self) -> list[str]:
        results: list[str] = []
        with self.lock:
            requests = list(self.requests)
        for request in requests:
            for message in request.get("messages", []):
                if isinstance(message, dict) and message.get("role") == "tool":
                    results.append(json.dumps(message.get("content"), ensure_ascii=False))
        return results

    def called_tools(self) -> set[str]:
        called: set[str] = set()
        with self.lock:
            requests = list(self.requests)
        for request in requests:
            for message in request.get("messages", []):
                if not isinstance(message, dict):
                    continue
                for call in message.get("tool_calls", []):
                    if not isinstance(call, dict):
                        continue
                    function = call.get("function")
                    if isinstance(function, dict) and isinstance(function.get("name"), str):
                        called.add(function["name"])
        return called


def system_text(request: Mapping[str, Any]) -> str:
    messages = request.get("messages")
    if not isinstance(messages, list) or not messages:
        return ""
    first = messages[0]
    if not isinstance(first, dict):
        return ""
    content = first.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        )
    return ""


def message_tool_names(request: Mapping[str, Any]) -> set[str]:
    names: set[str] = set()
    messages = request.get("messages")
    if not isinstance(messages, list):
        return names
    for message in messages:
        if not isinstance(message, dict):
            continue
        calls = message.get("tool_calls")
        if not isinstance(calls, list):
            continue
        for call in calls:
            function = call.get("function") if isinstance(call, dict) else None
            name = function.get("name") if isinstance(function, dict) else None
            if isinstance(name, str):
                names.add(name)
    return names


def completion_chunks(*, tool: str | None = None, arguments: dict[str, Any] | None = None) -> bytes:
    if tool is None:
        chunks = [
            {
                "id": "runtime-smoke-final",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": MODEL_ID,
                "choices": [
                    {"index": 0, "delta": {"content": "runtime smoke complete"}, "finish_reason": None}
                ],
            },
            {
                "id": "runtime-smoke-final",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": MODEL_ID,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            },
        ]
    else:
        chunks = [
            {
                "id": f"runtime-smoke-{tool}",
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
                                    "id": f"call_{tool}",
                                    "type": "function",
                                    "function": {
                                        "name": tool,
                                        "arguments": json.dumps(arguments or {}, separators=(",", ":")),
                                    },
                                }
                            ],
                        },
                        "finish_reason": None,
                    }
                ],
            },
            {
                "id": f"runtime-smoke-{tool}",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": MODEL_ID,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
            },
        ]
    return b"".join(
        f"data: {json.dumps(chunk, separators=(',', ':'))}\n\n".encode("utf-8")
        for chunk in chunks
    ) + b"data: [DONE]\n\n"


def provider_response(state: ProviderState, request: dict[str, Any]) -> bytes:
    tools = request.get("tools")
    if not isinstance(tools, list) or not tools:
        return completion_chunks()

    prompt = system_text(request)
    called = message_tool_names(request)
    requested = state.requested_tool_names()
    is_primary = "# Grillmester" in prompt
    is_subagent = "# Kokk" in prompt or "# Grill-inspekt" in prompt

    if is_primary:
        if "task" not in called and "task" not in requested:
            state.record_requested_tool("task")
            return completion_chunks(
                tool="task",
                arguments={
                    "description": f"Run {state.scenario.name}",
                    "prompt": f"Execute the single deterministic {state.scenario.name} probe.",
                    "subagent_type": state.scenario.subagent,
                },
            )
        return completion_chunks()

    if not is_subagent:
        return completion_chunks()

    action = state.scenario.action
    if action == "read-env" and "read" not in called:
        if "read" not in requested:
            state.record_requested_tool("read")
            return completion_chunks(
                tool="read",
                arguments={
                    "filePath": str(state.scenario.target),
                    "offset": 1,
                    "limit": 20,
                },
            )
        return completion_chunks()
    if action == "skill-reference":
        if "skill" not in called:
            if "skill" not in requested:
                state.record_requested_tool("skill")
                return completion_chunks(
                    tool="skill", arguments={"name": "grillmester-create-a-skill"}
                )
            return completion_chunks()
        if "read" not in called:
            if "read" not in requested:
                state.record_requested_tool("read")
                return completion_chunks(
                    tool="read",
                    arguments={
                        "filePath": str(state.scenario.target),
                        "offset": 1,
                        "limit": 40,
                    },
                )
            return completion_chunks()
    if action in {"deny-write", "allow-write"} and "write" not in called:
        if "write" not in requested:
            state.record_requested_tool("write")
            return completion_chunks(
                tool="write",
                arguments={
                    "filePath": str(state.scenario.target),
                    "content": WRITE_CONTENT,
                },
            )
        return completion_chunks()
    return completion_chunks()


class ProbeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, state: ProviderState):
        super().__init__((SERVER_HOST, 0), ProbeHandler)
        self.state = state


class ProbeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: ProbeServer

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def send_payload(self, body: bytes, *, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        body = json.dumps(
            {"object": "list", "data": [{"id": MODEL_ID, "object": "model"}]}
        ).encode("utf-8")
        self.send_payload(body, content_type="application/json")

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        try:
            size = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(size))
        except (ValueError, json.JSONDecodeError):
            self.send_error(400)
            return
        if not isinstance(request, dict):
            self.send_error(400)
            return
        self.server.state.record(request)
        body = provider_response(self.server.state, request)
        self.send_payload(body, content_type="text/event-stream")


def find_binary(value: str | None) -> Path | None:
    candidate = Path(value).expanduser() if value else None
    if candidate is None or (len(candidate.parts) == 1 and not candidate.exists()):
        found = shutil.which(value or "opencode")
        candidate = Path(found) if found else None
    if candidate is None or not candidate.is_file() or not os.access(candidate, os.X_OK):
        return None
    return candidate.resolve()


def isolated_environment(
    *, sandbox: Path, config_dir: Path, consumer: Path | None = None
) -> dict[str, str]:
    passthrough = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if key in os.environ}
    xdg = sandbox / "xdg"
    temp_dir = sandbox / "tmp"
    environment = {
        **passthrough,
        "CI": "true",
        "DO_NOT_TRACK": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(sandbox / "home"),
        "NO_COLOR": "1",
        "NO_PROXY": "127.0.0.1,localhost,::1",
        "OPENCODE_CONFIG_DIR": str(config_dir),
        "OPENCODE_CONFIG_CONTENT": json.dumps(
            {
                "autoupdate": False,
                "share": "disabled",
                **(
                    {"instructions": [str((consumer / "AGENTS.md").resolve())]}
                    if consumer is not None
                    else {}
                ),
            },
            separators=(",", ":"),
        ),
        "OPENCODE_AUTO_SHARE": "false",
        "OPENCODE_DISABLE_AUTOUPDATE": "true",
        "OPENCODE_DISABLE_CLAUDE_CODE": "true",
        "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT": "true",
        "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "true",
        "OPENCODE_DISABLE_DEFAULT_PLUGINS": "true",
        "OPENCODE_DISABLE_EXTERNAL_SKILLS": "true",
        "OPENCODE_DISABLE_LSP_DOWNLOAD": "true",
        "OPENCODE_DISABLE_MODELS_FETCH": "true",
        "OPENCODE_DISABLE_PROJECT_CONFIG": "true",
        "OPENCODE_DB": ":memory:",
        "OPENCODE_PURE": "true",
        "PWD": str((consumer or sandbox).resolve()),
        "TEMP": str(temp_dir),
        "TERM": "dumb",
        "TMP": str(temp_dir),
        "TMPDIR": str(temp_dir),
        "XDG_CACHE_HOME": str(xdg / "cache"),
        "XDG_CONFIG_HOME": str(xdg / "config"),
        "XDG_DATA_HOME": str(xdg / "data"),
        "XDG_STATE_HOME": str(xdg / "state"),
    }
    for directory in (
        Path(environment["HOME"]),
        temp_dir,
        Path(environment["XDG_CACHE_HOME"]),
        Path(environment["XDG_CONFIG_HOME"]),
        Path(environment["XDG_DATA_HOME"]),
        Path(environment["XDG_STATE_HOME"]),
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return environment


def write_provider_config(environment: Mapping[str, str], *, port: int) -> None:
    destination = Path(environment["XDG_CONFIG_HOME"]) / "opencode/opencode.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "probe": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Grillmester runtime smoke",
                "options": {"baseURL": f"http://127.0.0.1:{port}/v1"},
                "models": {
                    MODEL_ID: {
                        "name": "Deterministic permission probe",
                        "tool_call": True,
                        "limit": {"context": 32768, "output": 8192},
                    }
                },
            }
        },
    }
    destination.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def write_project_plugin_canary(consumer: Path) -> Path:
    """Install a harmless canary for the stock project's import-time surface."""

    marker = consumer / "project-plugin-executed.txt"
    plugin = consumer / ".opencode/plugins/grillmester-runtime-canary.js"
    plugin.parent.mkdir(parents=True, exist_ok=True)
    plugin.write_text(
        "import { writeFileSync } from 'node:fs'\n"
        f"writeFileSync({json.dumps(str(marker))}, "
        f"{json.dumps(PLUGIN_CANARY_CONTENT)}, {{ flag: 'wx' }})\n"
        "export default async () => ({})\n",
        encoding="utf-8",
    )
    return marker


def cplt_command(
    *,
    cplt: Path,
    opencode_command: Sequence[str],
    consumer: Path,
    config_dir: Path,
    local_port: int,
) -> list[str]:
    """Wrap an OpenCode command in the exact audited cplt contract."""

    if not opencode_command:
        raise RuntimeSmokeError("cannot wrap an empty OpenCode command")
    command = [
        str(cplt),
        "--agent",
        "opencode",
        "--preset",
        "strict",
        "--yes",
        "--scratch-dir",
        "--deny-clipboard",
        "--no-audit",
        "--no-quiet",
        "--project-dir",
        str(consumer),
        "--allow-read",
        str(config_dir),
        "--allow-localhost",
        str(local_port),
    ]
    for name in CPLT_PASSTHROUGH_ENV:
        command.extend(["--pass-env", name])
    command.extend(["--", *opencode_command[1:]])
    return command


def make_tree_immutable(root: Path) -> None:
    """Make the staged target read-only before exposing it to OpenCode."""

    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_symlink():
            raise RuntimeSmokeError(f"OpenCode target contains a symlink: {path}")
        if path.is_dir():
            path.chmod(0o555)
        elif path.is_file():
            executable = bool(path.stat().st_mode & stat.S_IXUSR)
            path.chmod(0o555 if executable else 0o444)
    root.chmod(0o555)


def make_tree_writable(root: Path) -> None:
    """Restore owner write access so the disposable tree can be removed."""

    if not root.exists():
        return
    root.chmod(0o755)
    for path in root.rglob("*"):
        if path.is_dir():
            path.chmod(0o755)
        elif path.is_file():
            executable = bool(path.stat().st_mode & stat.S_IXUSR)
            path.chmod(0o755 if executable else 0o644)


def run_scenario(
    *,
    binary: Path,
    cplt: Path | None,
    target: Path,
    sandbox: Path,
    scenario: Scenario,
) -> ProviderState:
    state = ProviderState(scenario=scenario)
    server = ProbeServer(state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        environment = isolated_environment(
            sandbox=sandbox,
            config_dir=target,
            consumer=sandbox / "consumer",
        )
        write_provider_config(environment, port=server.server_port)
        command = [
            str(binary),
            "run",
            "--agent",
            "grillmester",
            "--model",
            MODEL_REF,
            "--format",
            "json",
        ]
        if scenario.auto:
            command.append("--auto")
        command.append(f"Run the deterministic {scenario.name} runtime contract probe.")
        if cplt is not None:
            command = cplt_command(
                cplt=cplt,
                opencode_command=command,
                consumer=sandbox / "consumer",
                config_dir=target,
                local_port=server.server_port,
            )
        result = subprocess.run(
            command,
            cwd=sandbox / "consumer",
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=45,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    if result.returncode != 0:
        raise RuntimeSmokeError(
            f"{scenario.name} failed with exit {result.returncode}: {result.stdout[-4000:]}"
        )
    state.runtime_output = result.stdout
    if "task" not in state.called_tools():
        raise RuntimeSmokeError(f"{scenario.name} did not exercise native task delegation")
    return state


def smoke(*, binary: Path, source_target: Path, cplt: Path | None = None) -> None:
    version = subprocess.run(
        [str(binary), "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=15,
        check=False,
    ).stdout.strip()
    if version != EXPECTED_OPENCODE_VERSION:
        raise RuntimeSmokeError(
            f"expected OpenCode {EXPECTED_OPENCODE_VERSION}, found {version!r}"
        )
    if cplt is not None:
        cplt_version = subprocess.run(
            [str(cplt), "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
            check=False,
        )
        if cplt_version.returncode != 0 or cplt_version.stdout.strip() != (
            f"cplt {EXPECTED_CPLT_RELEASE}"
        ):
            raise RuntimeSmokeError(
                f"expected cplt {EXPECTED_CPLT_RELEASE}, found "
                f"{cplt_version.stdout.strip()!r}"
            )
        discovered = shutil.which("opencode")
        if discovered is None or Path(discovered).resolve() != binary:
            raise RuntimeSmokeError(
                "cplt smoke requires PATH's opencode to resolve to the pinned "
                "--opencode binary"
            )
    if not source_target.is_dir():
        raise RuntimeSmokeError(f"OpenCode target does not exist: {source_target}")

    with tempfile.TemporaryDirectory(prefix="grillmester-opencode-runtime-") as temp:
        sandbox = Path(temp)
        target = sandbox / "target"
        consumer = sandbox / "consumer"
        shutil.copytree(source_target, target)
        make_tree_immutable(target)
        consumer.mkdir()
        (consumer / ".git").mkdir()
        (consumer / ".git/HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (consumer / "AGENTS.md").write_text(
            "# Runtime smoke consumer\n\n"
            f"{CONSUMER_INSTRUCTION_MARKER}\n\nNever expose secrets.\n",
            encoding="utf-8",
        )
        hostile_instruction = consumer / "hostile-project-instruction.md"
        hostile_instruction.write_text(HOSTILE_PROJECT_MARKER + "\n", encoding="utf-8")
        (consumer / "opencode.json").write_text(
            json.dumps({"instructions": [str(hostile_instruction.resolve())]}) + "\n",
            encoding="utf-8",
        )
        plugin_marker = write_project_plugin_canary(consumer)

        try:
            env_path = consumer / ".env"
            env_path.write_text(f"SYNTHETIC_SECRET={ENV_SENTINEL}\n", encoding="utf-8")
            env_state = run_scenario(
                binary=binary,
                cplt=cplt,
                target=target,
                sandbox=sandbox,
                scenario=Scenario("env-deny", "kokk", "read-env", env_path),
            )
            env_results = "\n".join(env_state.tool_results())
            if "read" not in env_state.requested_tool_names():
                raise RuntimeSmokeError(
                    ".env scenario did not request the native read tool; "
                    f"requested={sorted(env_state.requested_tool_names())}; "
                    f"output={env_state.runtime_output[-2000:]}"
                )
            if "read" in env_state.called_tools():
                raise RuntimeSmokeError("OpenCode executed the rejected .env read")
            if "user rejected permission" not in env_state.runtime_output:
                raise RuntimeSmokeError(".env read lacked explicit permission rejection evidence")
            if ENV_SENTINEL in env_results:
                raise RuntimeSmokeError("Kokk read .env contents without approval")
            primary_prompts = [
                system_text(request)
                for request in env_state.requests
                if "# Grillmester" in system_text(request)
            ]
            if not primary_prompts or not all(
                CONSUMER_INSTRUCTION_MARKER in prompt for prompt in primary_prompts
            ):
                raise RuntimeSmokeError(
                    "managed runtime did not inject the fingerprinted consumer AGENTS.md"
                )
            if any(HOSTILE_PROJECT_MARKER in prompt for prompt in primary_prompts):
                raise RuntimeSmokeError(
                    "disabled project config injected an unreviewed instruction"
                )

            reference = (
                target
                / "skills/grillmester-create-a-skill/references/opencode-validation.md"
            )
            skill_state = run_scenario(
                binary=binary,
                cplt=cplt,
                target=target,
                sandbox=sandbox,
                scenario=Scenario(
                    "skill-reference", "kokk", "skill-reference", reference
                ),
            )
            skill_results = "\n".join(skill_state.tool_results())
            if not {"skill", "read"}.issubset(skill_state.called_tools()):
                raise RuntimeSmokeError("skill scenario did not exercise skill then read")
            if SKILL_MARKER not in skill_results:
                raise RuntimeSmokeError("Kokk could not read a bundled skill reference")

            denied_path = consumer / "inspector-must-not-write.txt"
            denied_state = run_scenario(
                binary=binary,
                cplt=cplt,
                target=target,
                sandbox=sandbox,
                scenario=Scenario(
                    "denied-write", "grill-inspektor", "deny-write", denied_path
                ),
            )
            if "write" not in denied_state.called_tools():
                if "write" not in denied_state.requested_tool_names():
                    raise RuntimeSmokeError(
                        "denied-write scenario did not request native write"
                    )
            else:
                raise RuntimeSmokeError("OpenCode executed Grill-inspektor's denied write")
            denied_results = "\n".join(denied_state.tool_results())
            if "unavailable tool 'write'" not in denied_results:
                raise RuntimeSmokeError(
                    "denied write lacked explicit unavailable-tool evidence; "
                    f"requested={sorted(denied_state.requested_tool_names())}; "
                    f"called={sorted(denied_state.called_tools())}; "
                    f"results={denied_state.tool_results()[-3:]}; "
                    f"output={denied_state.runtime_output[-2000:]}"
                )
            if denied_path.exists():
                raise RuntimeSmokeError("Grill-inspektor bypassed edit: deny")

            allowed_path = consumer / "kokk-approved-write.txt"
            allowed_state = run_scenario(
                binary=binary,
                cplt=cplt,
                target=target,
                sandbox=sandbox,
                scenario=Scenario(
                    "approved-write", "kokk", "allow-write", allowed_path, auto=True
                ),
            )
            if "write" not in allowed_state.called_tools():
                raise RuntimeSmokeError("approved-write scenario did not request native write")
            if not allowed_path.is_file() or allowed_path.read_text() != WRITE_CONTENT:
                raise RuntimeSmokeError("Kokk's approved write did not complete")
            if not plugin_marker.exists():
                raise RuntimeSmokeError(
                    "pinned OpenCode no longer reproduced the project-plugin "
                    "import surface covered by the release compatibility test"
                )
        finally:
            make_tree_writable(target)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opencode", help="path to the pinned OpenCode binary")
    parser.add_argument("--cplt", help="wrap every scenario in the pinned cplt binary")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--require-binary", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    binary = find_binary(args.opencode)
    if binary is None:
        message = (
            f"OpenCode {EXPECTED_OPENCODE_VERSION} is required; install "
            f"opencode-ai@{EXPECTED_OPENCODE_VERSION} or pass --opencode PATH"
        )
        if args.require_binary:
            print(f"ERROR: {message}", file=sys.stderr)
            return 1
        print(f"SKIP: {message}")
        return 0
    cplt = find_binary(args.cplt) if args.cplt else None
    if args.cplt and cplt is None:
        print(
            f"ERROR: cplt {EXPECTED_CPLT_RELEASE} is required; "
            "pass --cplt PATH",
            file=sys.stderr,
        )
        return 1
    try:
        smoke(binary=binary, source_target=args.target.resolve(), cplt=cplt)
    except (OSError, RuntimeSmokeError, subprocess.TimeoutExpired) as exc:
        print(f"OpenCode runtime smoke failed: {exc}", file=sys.stderr)
        return 1
    print(
        "OpenCode runtime smoke passed: delegation, .env deny, bundled skill read, "
        "stock project-plugin import hazard, denied write, and approved write"
        + (" through pinned cplt." if cplt is not None else " directly.")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
