#!/usr/bin/env python3
"""Prove that the launcher runs Grillmester's OpenCode target on OpenCode 2.

The smoke contacts no real model. A loopback provider scripts the tool calls,
and each session starts through the public launcher: directly, and also inside
cplt when --cplt is given.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "targets/opencode-v1"
LAUNCHER = ROOT / "scripts/grillmester.py"
POLICY = ROOT / "policy/opencode-v1.json"


def _release_test_opencode_version() -> str:
    name = "grillmester_release_test_baseline_for_opencode_smoke"
    specification = importlib.util.spec_from_file_location(
        name, ROOT / "scripts/release_test_baseline.py"
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("could not load the release-test baseline")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module.CONTRACT["releaseTest"]["opencodeVersion"]


EXPECTED_VERSION = _release_test_opencode_version()
PROVIDER_ID = "probe"
MODEL_ID = "grillmester-smoke"
PROMPT = "Run the Grillmester OpenCode smoke."
FINAL_TEXT = "GRILLMESTER_OPENCODE_SMOKE_OK"
CONSUMER_MARKER = "GRILLMESTER_OPENCODE_SMOKE_CONSUMER_GUIDANCE"
OUTSIDE_MARKER = "GRILLMESTER_OPENCODE_SMOKE_OUTSIDE_FILE"
ENV_MARKER = "GRILLMESTER_OPENCODE_SMOKE_ENV_FILE"
SUBAGENT_TEXT = "GRILLMESTER_OPENCODE_SMOKE_SUBAGENT_OK"
SUBAGENT_HEADING = "# Grill-inspektor"
SKILL_ID = "create-a-skill"
SKILL_REFERENCE = "references/opencode-validation.md"
SKILL_BASE_DIRECTORY = re.compile(r"^Base directory for this skill: (.+)$", re.MULTILINE)
REVIEWED_TOOLS = frozenset(
    {
        "edit",
        "glob",
        "grep",
        # OpenCode gates this one with the `edit` permission.
        "opencode_worktree_remove",
        "question",
        "read",
        "shell",
        "skill",
        "subagent",
        "webfetch",
        "websearch",
        "write",
    }
)
SESSION_TIMEOUT_SECONDS = 120
SYSTEM_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


Arguments = Mapping[str, Any] | Callable[[Mapping[str, Any]], Mapping[str, Any]]
TEXT_REPLY = "text"


class SmokeError(RuntimeError):
    """Raised when OpenCode does not honor the reviewed target."""


def _stream(chunks: Sequence[Mapping[str, Any]]) -> bytes:
    events = b"".join(f"data: {json.dumps(chunk)}\n\n".encode() for chunk in chunks)
    return events + b"data: [DONE]\n\n"


def _chunk(delta: Mapping[str, Any], finish_reason: str | None = None) -> dict[str, Any]:
    return {
        "id": "grillmester-smoke",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": MODEL_ID,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def _text_stream(text: str) -> bytes:
    return _stream(
        (_chunk({"role": "assistant", "content": text}), _chunk({}, "stop"))
    )


def _tool_stream(index: int, name: str, arguments: Mapping[str, Any]) -> bytes:
    call = {
        "index": 0,
        "id": call_id(index),
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }
    return _stream(
        (_chunk({"role": "assistant", "tool_calls": [call]}), _chunk({}, "tool_calls"))
    )


def call_id(index: int) -> str:
    return f"call_smoke_{index}"


class ProbeProvider(ThreadingHTTPServer):
    """Answer agent requests from a script; title requests carry no tools."""

    daemon_threads = True

    def __init__(self, steps: Sequence[tuple[str, Arguments]]) -> None:
        super().__init__(("127.0.0.1", 0), _ProbeHandler)
        self.steps = tuple(steps)
        self.requests: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    @property
    def port(self) -> int:
        return self.server_address[1]

    def respond(self, request: dict[str, Any]) -> bytes:
        if not request.get("tools"):
            return _text_stream("Grillmester smoke")
        with self._lock:
            index = len(self.requests)
            self.requests.append(request)
        if index < len(self.steps):
            name, arguments = self.steps[index]
            if name == TEXT_REPLY:
                return _text_stream(arguments["text"])
            if callable(arguments):
                arguments = arguments(request)
            return _tool_stream(index, name, arguments)
        return _text_stream(FINAL_TEXT)


class _ProbeHandler(BaseHTTPRequestHandler):
    server: ProbeProvider

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _send(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        models = {"object": "list", "data": [{"id": MODEL_ID, "object": "model"}]}
        self._send(json.dumps(models).encode(), "application/json")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length))
        self._send(self.server.respond(request), "text/event-stream")


def tree_digest(root: Path) -> str:
    """Hash names and contents, ignoring Git's own bookkeeping."""

    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts[0] == ".git" or not path.is_file():
            continue
        digest.update(str(relative).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _isolated_environment(root: Path, client_bin: Path) -> dict[str, str]:
    directories = {
        "HOME": root / "home",
        "TMPDIR": root / "tmp",
        "XDG_CACHE_HOME": root / "xdg/cache",
        "XDG_CONFIG_HOME": root / "xdg/config",
        "XDG_DATA_HOME": root / "xdg/data",
        "XDG_STATE_HOME": root / "xdg/state",
    }
    for directory in directories.values():
        directory.mkdir(parents=True, mode=0o700)
    return {
        **{name: str(path) for name, path in directories.items()},
        "CI": "true",
        "DO_NOT_TRACK": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "NO_COLOR": "1",
        "NO_PROXY": "127.0.0.1,localhost,::1",
        "OPENCODE_DISABLE_AUTOUPDATE": "true",
        "OPENCODE_DISABLE_FREE_MODELS": "true",
        "OPENCODE_DISABLE_MODELS_FETCH": "true",
        "PATH": f"{client_bin}:{SYSTEM_PATH}",
        # A stale PWD must not beat --project-dir.
        "PWD": str(root),
        "TERM": "dumb",
    }


def _provider_config(port: int) -> str:
    return json.dumps(
        {
            "model": f"{PROVIDER_ID}/{MODEL_ID}",
            "providers": {
                PROVIDER_ID: {
                    "package": "aisdk:@ai-sdk/openai-compatible",
                    "settings": {
                        "apiKey": "not-a-secret",
                        "baseURL": f"http://127.0.0.1:{port}/v1",
                    },
                    "models": {
                        MODEL_ID: {"name": MODEL_ID, "capabilities": {"tools": True}}
                    },
                }
            },
        }
    )


def _run(
    command: Sequence[str], *, cwd: Path, environment: Mapping[str, str]
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            cwd=cwd,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=SESSION_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SmokeError(f"timed out: {shlex.join(command)[:200]}") from exc


def verify_version(opencode: Path, sandbox: Path, client_bin: Path) -> None:
    root = sandbox / "version"
    root.mkdir()
    result = _run(
        (str(opencode), "--version"),
        cwd=root,
        environment=_isolated_environment(root, client_bin),
    )
    expected = f"opencode v{EXPECTED_VERSION}"
    if result.returncode != 0 or result.stdout.strip() != expected:
        raise SmokeError(
            f"expected {expected!r} from {opencode}, found {result.stdout.strip()!r} "
            f"(exit {result.returncode})"
        )


def _effect(rules: Sequence[Mapping[str, str]], action: str) -> str | None:
    """Return the effect of the last rule that covers every resource of an action."""

    matching = [
        rule["effect"]
        for rule in rules
        if rule["action"] == action and rule["resource"] == "*"
    ]
    return matching[-1] if matching else None


def validate_agents(
    agents: Sequence[Mapping[str, Any]],
    *,
    policy: Mapping[str, Mapping[str, Any]],
    target: Path,
) -> None:
    observed = {agent.get("id"): agent for agent in agents}
    for agent_id, expected in policy.items():
        agent = observed.get(agent_id)
        if agent is None:
            raise SmokeError(f"OpenCode did not load agent {agent_id!r}")
        if bool(agent.get("hidden")) != expected["hidden"]:
            raise SmokeError(f"{agent_id} has the wrong hidden flag")
        if agent.get("mode") != expected["mode"]:
            raise SmokeError(f"{agent_id} has mode {agent.get('mode')!r}")
        rules = agent.get("permissions")
        if not isinstance(rules, list):
            raise SmokeError(f"{agent_id} exposes no permission rules")
        if _effect(rules, "external_directory") != "ask":
            raise SmokeError(f"{agent_id} does not ask before leaving the project")
        skills = {
            "action": "external_directory",
            "resource": f"{target}/skills/*",
            "effect": "allow",
        }
        if skills not in rules:
            raise SmokeError(f"{agent_id} cannot read the bundled skills")
        if _effect(rules, "execute") != "deny":
            raise SmokeError(f"{agent_id} keeps Code Mode")
        if _effect(rules, "opencode_*") != "deny":
            raise SmokeError(f"{agent_id} keeps OpenCode's own tools")
        for tool, action in (("bash", "shell"), ("task", "subagent")):
            if expected["permission"].get(tool) == "deny":
                if _effect(rules, action) != "deny":
                    raise SmokeError(f"{agent_id} lost its {action} deny")


def _check_agents(opencode: Path, sandbox: Path, client_bin: Path) -> None:
    root = sandbox / "agents"
    consumer = root / "consumer"
    consumer.mkdir(parents=True)
    environment = _isolated_environment(root, client_bin)
    environment["OPENCODE_CONFIG_DIR"] = str(TARGET)
    result = _run(
        (str(opencode), "--standalone", "debug", "agents"),
        cwd=consumer,
        environment=environment,
    )
    if result.returncode != 0:
        raise SmokeError(f"debug agents failed: {result.stderr[-2000:]}")
    policy = json.loads(POLICY.read_text(encoding="utf-8"))["agents"]
    validate_agents(json.loads(result.stdout), policy=policy, target=TARGET)


def _tool_results(request: Mapping[str, Any]) -> dict[str, str]:
    results: dict[str, str] = {}
    for message in request.get("messages", []):
        if message.get("role") == "tool":
            content = message.get("content")
            results[message.get("tool_call_id")] = (
                content if isinstance(content, str) else json.dumps(content)
            )
    return results


def _skill_reference(request: Mapping[str, Any]) -> dict[str, str]:
    """Read where the skill says it lives, as a model does; cplt relocates it."""

    skill = _tool_results(request).get(call_id(0), "")
    base = SKILL_BASE_DIRECTORY.search(skill)
    return {"path": f"{base.group(1) if base else ''}/{SKILL_REFERENCE}"}


def _system_text(request: Mapping[str, Any]) -> str:
    return "\n".join(
        message["content"]
        if isinstance(message.get("content"), str)
        else json.dumps(message.get("content"))
        for message in request.get("messages", [])
        if message.get("role") == "system"
    )


def validate_session(
    requests: Sequence[Mapping[str, Any]],
    *,
    steps: int,
    skills: Sequence[str],
    reference_line: str,
) -> None:
    if len(requests) != steps + 1:
        raise SmokeError(f"expected {steps + 1} agent requests, saw {len(requests)}")
    first = requests[0]
    system = _system_text(first)
    if "# Grillmester" not in system:
        raise SmokeError("the request did not carry the Grillmester prompt")
    if CONSUMER_MARKER not in system:
        raise SmokeError("the request did not carry the consumer's AGENTS.md")
    missing = [skill for skill in skills if skill not in system]
    if missing:
        raise SmokeError(f"the skill catalog lacks: {', '.join(missing)}")
    tools = {tool["function"]["name"] for tool in first.get("tools", [])}
    if tools != REVIEWED_TOOLS:
        raise SmokeError(
            f"the tools differ from the reviewed set: {sorted(tools ^ REVIEWED_TOOLS)}"
        )

    if SUBAGENT_HEADING not in _system_text(requests[-2]):
        raise SmokeError("the delegated request did not run as Grill-inspektor")
    results = _tool_results(requests[-1])
    skill, reference, outside, env_file, write, subagent = (
        results.get(call_id(index), "") for index in range(6)
    )
    if f'<skill_content name="{SKILL_ID}">' not in skill:
        raise SmokeError(f"skill {SKILL_ID!r} did not load: {skill[:300]}")
    if reference_line not in reference:
        raise SmokeError(f"the bundled reference was not read: {reference[:300]}")
    if OUTSIDE_MARKER in outside or "permission.rejected" not in outside:
        raise SmokeError(f"a read outside the project went through: {outside[:300]}")
    if ENV_MARKER in env_file or "permission.rejected" not in env_file:
        raise SmokeError(f"a read of .env went through: {env_file[:300]}")
    if "permission.rejected" not in write:
        raise SmokeError(f"a write without approval went through: {write[:300]}")
    if SUBAGENT_TEXT not in subagent:
        raise SmokeError(f"the delegation did not return: {subagent[:300]}")


def _install_provider(environment: dict[str, str], *, mode: str, port: int) -> None:
    """Prove the user's own config in a direct session; cplt does not load it."""

    config = _provider_config(port)
    if mode == "cplt":
        environment["OPENCODE_CONFIG_CONTENT"] = config
        return
    user_config = Path(environment["XDG_CONFIG_HOME"]) / "opencode/opencode.json"
    user_config.parent.mkdir(mode=0o700)
    user_config.write_text(config, encoding="utf-8")


def _check_session(
    mode: str,
    launch_arguments: Sequence[str],
    *,
    sandbox: Path,
    client_bin: Path,
) -> None:
    root = sandbox / mode
    consumer = root / "consumer"
    consumer.mkdir(parents=True)
    subprocess.run(
        ("git", "init", "--quiet", str(consumer)),
        check=True,
        env={"PATH": SYSTEM_PATH, "GIT_CONFIG_GLOBAL": os.devnull},
    )
    (consumer / "AGENTS.md").write_text(f"{CONSUMER_MARKER}\n", encoding="utf-8")
    env_file = consumer / ".env"
    env_file.write_text(f"SMOKE={ENV_MARKER}\n", encoding="utf-8")
    outside = root / "outside.txt"
    outside.write_text(f"{OUTSIDE_MARKER}\n", encoding="utf-8")
    written = consumer / "written-without-approval.txt"
    before = tree_digest(consumer)
    steps = (
        ("skill", {"id": SKILL_ID}),
        ("read", _skill_reference),
        ("read", {"path": str(outside)}),
        ("read", {"path": str(env_file)}),
        ("write", {"path": str(written), "content": "must not exist\n"}),
        (
            "subagent",
            {
                "agent": "grill-inspektor",
                "description": "Smoke delegation",
                "prompt": "Return the smoke sentinel.",
            },
        ),
        (TEXT_REPLY, {"text": SUBAGENT_TEXT}),
    )
    environment = _isolated_environment(root, client_bin)
    with ProbeProvider(steps) as provider:
        threading.Thread(target=provider.serve_forever, daemon=True).start()
        _install_provider(environment, mode=mode, port=provider.port)
        arguments = [
            argument.replace("{port}", str(provider.port))
            for argument in launch_arguments
        ]
        result = _run(
            (
                sys.executable,
                "-I",
                "-S",
                str(LAUNCHER),
                "--client",
                "opencode",
                "--agent",
                "grillmester",
                "--project-dir",
                str(consumer),
                *arguments,
                "--",
                "run",
                "--model",
                f"{PROVIDER_ID}/{MODEL_ID}",
                PROMPT,
            ),
            cwd=root,
            environment=environment,
        )
        provider.shutdown()
    if result.returncode != 0 or FINAL_TEXT not in result.stdout:
        raise SmokeError(
            f"{mode} session failed with exit {result.returncode}: "
            f"{result.stdout[-1500:]}\n{result.stderr[-2500:]}"
        )
    try:
        validate_session(
            provider.requests,
            steps=len(steps),
            skills=sorted(path.name for path in (TARGET / "skills").iterdir()),
            reference_line=(TARGET / "skills" / SKILL_ID / SKILL_REFERENCE)
            .read_text(encoding="utf-8")
            .splitlines()[0],
        )
    except SmokeError as exc:
        raise SmokeError(f"{mode} session: {exc}") from exc
    if written.exists() or tree_digest(consumer) != before:
        raise SmokeError(f"{mode} session changed the consumer repository")


def smoke(opencode: Path, cplt: Path | None) -> None:
    before = tree_digest(TARGET)
    with tempfile.TemporaryDirectory(prefix="grillmester-opencode-smoke-") as temp:
        sandbox = Path(temp).resolve()
        client_bin = sandbox / "client-bin"
        client_bin.mkdir()
        (client_bin / "opencode").symlink_to(opencode)
        verify_version(opencode, sandbox, client_bin)
        _check_agents(opencode, sandbox, client_bin)
        _check_session(
            "direct", ("--no-cplt",), sandbox=sandbox, client_bin=client_bin
        )
        if cplt is not None:
            (client_bin / "cplt").symlink_to(cplt)
            _check_session(
                "cplt",
                ("--yes", "--allow-localhost", "{port}"),
                sandbox=sandbox,
                client_bin=client_bin,
            )
    if tree_digest(TARGET) != before:
        raise SmokeError("a session wrote into the distributed target")


def _resolve(value: str | None, name: str) -> Path | None:
    found = shutil.which(value or name)
    return None if found is None else Path(found).resolve()


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--opencode", help="path to the exact OpenCode binary")
    parser.add_argument("--cplt", help="also run a session through this cplt")
    parser.add_argument(
        "--require-binary",
        action="store_true",
        help="fail instead of skipping when OpenCode is missing",
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    options = parse_arguments(arguments)
    opencode = _resolve(options.opencode, "opencode")
    if opencode is None:
        if options.require_binary:
            print("OpenCode smoke failed: opencode was not found", file=sys.stderr)
            return 1
        print("Skipped OpenCode smoke: opencode was not found")
        return 0
    cplt = None
    if options.cplt is not None:
        cplt = _resolve(options.cplt, "cplt")
        if cplt is None:
            print(f"OpenCode smoke failed: {options.cplt} not found", file=sys.stderr)
            return 1
    try:
        smoke(opencode, cplt)
    except (SmokeError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"OpenCode smoke failed: {exc}", file=sys.stderr)
        return 1
    modes = "directly and through cplt" if cplt is not None else "directly"
    print(f"OpenCode smoke passed {modes} on {EXPECTED_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
