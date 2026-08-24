#!/usr/bin/env python3
"""Smoke-test the generated OpenCode v1 target without contacting a model."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = ROOT / "targets/opencode-v1"
_BASELINE_SPEC = importlib.util.spec_from_file_location(
    "grillmester_release_test_baseline_for_opencode_smoke",
    ROOT / "scripts/release_test_baseline.py",
)
if _BASELINE_SPEC is None or _BASELINE_SPEC.loader is None:
    raise RuntimeError("could not load release-test baseline contract")
_BASELINE_MODULE = importlib.util.module_from_spec(_BASELINE_SPEC)
sys.modules[_BASELINE_SPEC.name] = _BASELINE_MODULE
_BASELINE_SPEC.loader.exec_module(_BASELINE_MODULE)
EXPECTED_OPENCODE_VERSION = _BASELINE_MODULE.CONTRACT["releaseTest"][
    "opencodeVersion"
]
PRIMARY_AGENTS = frozenset({"grillmester", "barista", "designer", "doctor-who"})
SUBAGENTS = frozenset({"kokk", "grill-inspektor", "researcher"})
EXPECTED_AGENTS = PRIMARY_AGENTS | SUBAGENTS
EXPECTED_SKILLS = 42
EXPECTED_COMMANDS = 42
HYBRID_PROVIDER_ID = "lmstudio"
HYBRID_MODEL_ID = "grillmester-smoke"
USER_DENIED_READ_PATTERN = "*.user-denied"
USER_DENIED_READ_SAMPLE = "consumer.user-denied"
SKILL_DEBUG_BATCH_BYTES = 28 * 1024
CONSUMER_CONTEXT_MARKER = "GRILLMESTER_OPENCODE_SMOKE_CONSUMER_CONTEXT"
AGENT_LIST_ENTRY = re.compile(
    r"^([a-z0-9][a-z0-9-]*) \((primary|subagent)\)\s*$", re.MULTILINE
)
NATIVE_PERMISSION_KEYS = frozenset(
    {
        "*",
        "bash",
        "doom_loop",
        "edit",
        "external_directory",
        "glob",
        "grep",
        "list",
        "lsp",
        "question",
        "read",
        "skill",
        "task",
        "todowrite",
        "webfetch",
        "websearch",
    }
)
PERMISSION_ACTIONS = frozenset({"allow", "ask", "deny"})
PROTECTED_ENV_PATHS = (
    ".env",
    ".env.local",
    "service.env",
    "service.env.local",
)
ENV_EXAMPLE_PATHS = (".env.example", "service.env.example")
SAFE_ENV_PASSTHROUGH = frozenset(
    {
        "COMSPEC",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
    }
)


class SmokeError(RuntimeError):
    """Raised when the OpenCode target is not discovered as reviewed."""


class TargetInventory(NamedTuple):
    agents: frozenset[str]
    commands: frozenset[str]
    skills: frozenset[str]


class SmokeReport(NamedTuple):
    version: str
    primary_agents: int
    subagents: int
    skills: int
    commands: int


def resolve_binary(value: str | None, base: Mapping[str, str]) -> Path | None:
    """Resolve a caller-selected binary before replacing HOME and XDG paths."""

    if value:
        expanded = Path(value).expanduser()
        if expanded.is_absolute() or expanded.parent != Path("."):
            candidate = expanded
        else:
            found = shutil.which(value, path=base.get("PATH"))
            candidate = Path(found) if found else expanded
    else:
        found = shutil.which("opencode", path=base.get("PATH"))
        if not found:
            return None
        candidate = Path(found)

    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        return None
    return candidate.resolve()


def isolated_environment(
    base: Mapping[str, str], *, sandbox: Path, config_dir: Path
) -> dict[str, str]:
    """Build an offline environment without ambient credentials or config."""

    env = {key: value for key, value in base.items() if key in SAFE_ENV_PASSTHROUGH}
    xdg = sandbox / "xdg"
    temp_files = sandbox / "tmp"
    env.update(
        {
            "CI": "true",
            "DO_NOT_TRACK": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "HOME": str(sandbox / "home"),
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "127.0.0.1,localhost,::1",
            "NO_COLOR": "1",
            "OPENCODE_CONFIG_DIR": str(config_dir),
            "OPENCODE_DISABLE_AUTOUPDATE": "true",
            "OPENCODE_DISABLE_CLAUDE_CODE": "true",
            "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT": "true",
            "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "true",
            "OPENCODE_DISABLE_DEFAULT_PLUGINS": "true",
            "OPENCODE_DISABLE_EXTERNAL_SKILLS": "true",
            "OPENCODE_DISABLE_LSP_DOWNLOAD": "true",
            "OPENCODE_DISABLE_MODELS_FETCH": "true",
            "OPENCODE_DISABLE_SHARE": "true",
            "OPENCODE_PURE": "1",
            "TEMP": str(temp_files),
            "TERM": "dumb",
            "TMP": str(temp_files),
            "TMPDIR": str(temp_files),
            "XDG_CACHE_HOME": str(xdg / "cache"),
            "XDG_CONFIG_HOME": str(xdg / "config"),
            "XDG_DATA_HOME": str(xdg / "data"),
            "XDG_STATE_HOME": str(xdg / "state"),
            "http_proxy": "http://127.0.0.1:9",
            "https_proxy": "http://127.0.0.1:9",
            "all_proxy": "http://127.0.0.1:9",
            "no_proxy": "127.0.0.1,localhost,::1",
        }
    )
    return env


def execute(
    command: Sequence[str],
    *,
    env: Mapping[str, str],
    cwd: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            cwd=cwd,
            env=dict(env),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise SmokeError(
            f"command timed out after {timeout_seconds}s: {shlex.join(command)}"
        ) from exc
    except OSError as exc:
        raise SmokeError(f"could not execute {shlex.join(command)}: {exc}") from exc


def run(
    command: Sequence[str],
    *,
    env: Mapping[str, str],
    cwd: Path,
    timeout_seconds: int,
) -> str:
    result = execute(command, env=env, cwd=cwd, timeout_seconds=timeout_seconds)
    if result.returncode != 0:
        raise SmokeError(
            f"command failed with exit code {result.returncode}: "
            f"{shlex.join(command)}\n{result.stdout}"
        )
    return result.stdout


def run_json(
    command: Sequence[str],
    *,
    env: Mapping[str, str],
    cwd: Path,
    timeout_seconds: int,
) -> Any:
    output = run(command, env=env, cwd=cwd, timeout_seconds=timeout_seconds)
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        preview = output[:2_000]
        raise SmokeError(
            f"command did not return JSON: {shlex.join(command)}\n{preview}"
        ) from exc


def target_inventory(target: Path) -> TargetInventory:
    if not target.is_dir():
        raise SmokeError(f"OpenCode target is missing: {target}")

    agents = frozenset(path.stem for path in (target / "agents").glob("*.md"))
    commands = frozenset(path.stem for path in (target / "commands").glob("*.md"))
    skills = frozenset(
        path.parent.name for path in (target / "skills").glob("*/SKILL.md")
    )

    if agents != EXPECTED_AGENTS:
        raise SmokeError(
            "OpenCode target agent roster differs from the reviewed seven roles: "
            f"{sorted(agents)}"
        )
    if len(skills) != EXPECTED_SKILLS:
        raise SmokeError(
            f"OpenCode target must contain {EXPECTED_SKILLS} skills, found {len(skills)}"
        )
    if len(commands) != EXPECTED_COMMANDS:
        raise SmokeError(
            "OpenCode target must contain "
            f"{EXPECTED_COMMANDS} commands, found {len(commands)}"
        )
    if commands != skills:
        raise SmokeError("OpenCode command IDs must exactly match the skill IDs")
    return TargetInventory(agents=agents, commands=commands, skills=skills)


def make_tree_writable(root: Path) -> None:
    for path in [root, *root.rglob("*")]:
        path.chmod(path.stat().st_mode | stat.S_IWUSR)


def prepare_debug_config_probe(source: Path, destination: Path) -> None:
    """Preserve frontmatter below pinned 1.18.20/Bun's pipe-flush boundary."""

    shutil.copytree(source, destination)
    make_tree_writable(destination)
    for agent in (destination / "agents").glob("*.md"):
        text = agent.read_text(encoding="utf-8")
        end = text.find("\n---\n", 4)
        if not text.startswith("---\n") or end < 0:
            raise SmokeError(f"cannot isolate frontmatter for debug config: {agent}")
        agent.write_text(
            text[: end + len("\n---\n")]
            + f"\nOpenCode config discovery probe for {agent.stem}.\n",
            encoding="utf-8",
        )


def prepare_agent_list_probe(source: Path, destination: Path) -> None:
    """Stage only agent metadata for bounded human-formatted list output."""

    destination.mkdir()
    opencode_config = source / "opencode.json"
    if opencode_config.is_file():
        shutil.copy2(opencode_config, destination / "opencode.json")
    shutil.copytree(source / "agents", destination / "agents")
    make_tree_writable(destination)
    for agent in (destination / "agents").glob("*.md"):
        text = agent.read_text(encoding="utf-8")
        end = text.find("\n---\n", 4)
        if not text.startswith("---\n") or end < 0:
            raise SmokeError(f"cannot isolate frontmatter for agent list: {agent}")
        agent.write_text(
            text[: end + len("\n---\n")]
            + f"\nOpenCode agent list probe for {agent.stem}.\n",
            encoding="utf-8",
        )


def prepare_skill_debug_probes(
    source: Path, destination: Path
) -> list[tuple[Path, frozenset[str]]]:
    """Create byte-exact skill batches small enough for OpenCode's debug output."""

    batches: list[list[Path]] = []
    current: list[Path] = []
    current_bytes = 0
    for skill_file in sorted((source / "skills").glob("*/SKILL.md")):
        size = skill_file.stat().st_size
        if current and current_bytes + size > SKILL_DEBUG_BATCH_BYTES:
            batches.append(current)
            current = []
            current_bytes = 0
        current.append(skill_file)
        current_bytes += size
    if current:
        batches.append(current)

    probes: list[tuple[Path, frozenset[str]]] = []
    for index, batch in enumerate(batches):
        probe = destination / f"skill-batch-{index:02d}"
        probe.mkdir(parents=True)
        for optional_file in (".gitignore", "opencode.json"):
            source_file = source / optional_file
            if source_file.is_file():
                shutil.copy2(source_file, probe / optional_file)
        skill_ids = frozenset(path.parent.name for path in batch)
        for skill_id in skill_ids:
            shutil.copytree(source / "skills" / skill_id, probe / "skills" / skill_id)
        make_tree_writable(probe)
        probes.append((probe, skill_ids))
    return probes


def nested_key_paths(value: Any, key: str, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            path = f"{prefix}.{child_key}" if prefix else str(child_key)
            if child_key == key:
                paths.append(path)
            paths.extend(nested_key_paths(child_value, key, path))
    elif isinstance(value, list):
        for index, child_value in enumerate(value):
            paths.extend(nested_key_paths(child_value, key, f"{prefix}[{index}]"))
    return paths


def declared_permission_rules(permission: Any) -> list[tuple[str, str, str]]:
    if not isinstance(permission, dict) or not permission:
        raise SmokeError("each OpenCode agent needs a non-empty permission object")
    rules: list[tuple[str, str, str]] = []
    unknown = set(permission) - NATIVE_PERMISSION_KEYS
    if unknown:
        raise SmokeError(f"agent uses unknown permission keys: {sorted(unknown)}")
    for permission_name, value in permission.items():
        if isinstance(value, str):
            if value not in PERMISSION_ACTIONS:
                raise SmokeError(
                    f"invalid {permission_name} permission action: {value!r}"
                )
            rules.append((permission_name, "*", value))
            continue
        if not isinstance(value, dict) or not value:
            raise SmokeError(
                f"permission {permission_name!r} must be an action or pattern map"
            )
        for pattern, action in value.items():
            if not isinstance(pattern, str) or action not in PERMISSION_ACTIONS:
                raise SmokeError(
                    f"invalid {permission_name} permission rule: {pattern!r}: {action!r}"
                )
            rules.append((permission_name, pattern, action))
    return rules


def wildcard_matches(value: str, pattern: str) -> bool:
    """Match one OpenCode v1 permission wildcard exactly."""

    normalized = value.replace("\\", "/")
    source = pattern.replace("\\", "/")
    special = frozenset(".+^${}()|[]\\")
    escaped = "".join(f"\\{char}" if char in special else char for char in source)
    escaped = escaped.replace("*", ".*").replace("?", ".")
    if escaped.endswith(" .*"):
        escaped = escaped[:-3] + "( .*)?"
    return re.fullmatch(f"^{escaped}$", normalized, flags=re.DOTALL) is not None


def effective_permission_action(
    rules: Sequence[tuple[str, str, str]], permission: str, pattern: str
) -> str:
    matching = [
        action
        for rule_permission, rule_pattern, action in rules
        if wildcard_matches(permission, rule_permission)
        and wildcard_matches(pattern, rule_pattern)
    ]
    return matching[-1] if matching else "ask"


def resolved_permission_rules(
    value: Any, *, label: str
) -> list[tuple[str, str, str]]:
    permissions = value.get("permission") if isinstance(value, dict) else None
    if not isinstance(permissions, list) or not permissions:
        raise SmokeError(f"{label} has no resolved permissions")
    rules: list[tuple[str, str, str]] = []
    for rule in permissions:
        if not isinstance(rule, dict):
            raise SmokeError(f"{label} has an invalid resolved permission")
        permission_name = rule.get("permission")
        pattern = rule.get("pattern")
        action = rule.get("action")
        if not all(isinstance(item, str) for item in (permission_name, pattern, action)):
            raise SmokeError(f"{label} has an invalid resolved permission")
        rules.append((permission_name, pattern, action))
    return rules


def validate_resolved_config(
    value: Any, inventory: TargetInventory
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise SmokeError("opencode debug config must return a JSON object")
    agents = value.get("agent")
    commands = value.get("command")
    if not isinstance(agents, dict) or set(agents) != inventory.agents:
        raise SmokeError("resolved config did not discover exactly seven Grillmester agents")
    if not isinstance(commands, dict) or set(commands) != inventory.commands:
        raise SmokeError("resolved config did not discover exactly 42 Grillmester commands")
    if value.get("plugin") != []:
        raise SmokeError("external plugins were not disabled for the OpenCode smoke")
    if value.get("share") != "disabled":
        raise SmokeError("resolved OpenCode config must disable session sharing")
    if value.get("autoupdate") is not False:
        raise SmokeError("resolved OpenCode config must disable automatic updates")

    model_paths = nested_key_paths({"agent": agents, "command": commands}, "model")
    if model_paths:
        raise SmokeError(
            "OpenCode target must inherit the selected model; hardcoded model found at "
            + ", ".join(model_paths)
        )

    for agent_id, agent in agents.items():
        if not isinstance(agent, dict):
            raise SmokeError(f"resolved agent {agent_id} is not an object")
        expected_mode = "primary" if agent_id in PRIMARY_AGENTS else "subagent"
        if agent.get("mode") != expected_mode:
            raise SmokeError(
                f"resolved agent {agent_id} has mode {agent.get('mode')!r}, "
                f"expected {expected_mode!r}"
            )
        if agent.get("hidden") is not (expected_mode == "subagent"):
            raise SmokeError(f"resolved agent {agent_id} has the wrong hidden state")
        if not isinstance(agent.get("description"), str) or not agent["description"].strip():
            raise SmokeError(f"resolved agent {agent_id} has no description")
        if not isinstance(agent.get("prompt"), str) or not agent["prompt"].strip():
            raise SmokeError(f"resolved agent {agent_id} has no prompt")
        if agent.get("options") not in (None, {}):
            raise SmokeError(
                f"resolved agent {agent_id} contains unrecognized frontmatter options"
            )
        declared_permission_rules(agent.get("permission"))

    for command_id, command in commands.items():
        if not isinstance(command, dict):
            raise SmokeError(f"resolved command {command_id} is not an object")
        template = command.get("template")
        if not isinstance(template, str) or not template.strip():
            raise SmokeError(f"resolved command {command_id} has no template")
        if command_id not in template or "$ARGUMENTS" not in template:
            raise SmokeError(
                f"resolved command {command_id} does not route its skill and arguments"
            )
    return agents


def validate_agent_list(output: str) -> None:
    discovered: dict[str, list[str]] = {}
    for agent_id, mode in AGENT_LIST_ENTRY.findall(output):
        discovered.setdefault(agent_id, []).append(mode)
    for agent_id in EXPECTED_AGENTS:
        expected_mode = "primary" if agent_id in PRIMARY_AGENTS else "subagent"
        if discovered.get(agent_id) != [expected_mode]:
            raise SmokeError(
                f"agent list did not expose {agent_id!r} exactly once as {expected_mode}"
            )


def validate_agent_detail(
    value: Any,
    *,
    agent_id: str,
    config_agent: dict[str, Any],
    config_dir: Path | None = None,
    skill_ids: frozenset[str] | None = None,
) -> None:
    if not isinstance(value, dict) or value.get("name") != agent_id:
        raise SmokeError(f"debug agent returned the wrong payload for {agent_id}")
    expected_mode = "primary" if agent_id in PRIMARY_AGENTS else "subagent"
    if value.get("mode") != expected_mode:
        raise SmokeError(f"debug agent returned the wrong mode for {agent_id}")
    if value.get("native") is not False:
        raise SmokeError(f"debug agent did not resolve {agent_id} as a custom agent")
    if nested_key_paths(value, "model"):
        raise SmokeError(f"debug agent resolved a hardcoded model for {agent_id}")
    resolved_rules = resolved_permission_rules(value, label=f"debug agent {agent_id}")

    declared = declared_permission_rules(config_agent.get("permission"))
    cursor = 0
    for declared_rule in declared:
        try:
            index = resolved_rules.index(declared_rule, cursor)
        except ValueError as exc:
            raise SmokeError(
                "debug agent did not preserve declared native permission order for "
                f"{agent_id}: missing {declared_rule!r} after rule {cursor}"
            ) from exc
        cursor = index + 1

    unsafe_env = [
        path
        for path in PROTECTED_ENV_PATHS
        if effective_permission_action(resolved_rules, "read", path) == "allow"
    ]
    if unsafe_env:
        raise SmokeError(
            f"resolved agent {agent_id} must not allow environment files: "
            + ", ".join(unsafe_env)
        )

    blocked_examples = [
        path
        for path in ENV_EXAMPLE_PATHS
        if effective_permission_action(resolved_rules, "read", path) != "allow"
    ]
    if blocked_examples:
        raise SmokeError(
            f"resolved agent {agent_id} must allow environment examples: "
            + ", ".join(blocked_examples)
        )

    if agent_id in SUBAGENTS and config_dir is not None and skill_ids is not None:
        blocked_skill_paths = []
        for skill_id in sorted(skill_ids):
            bundled_reference_glob = str(
                config_dir / f"skills/{skill_id}/references/*"
            )
            external_action = effective_permission_action(
                resolved_rules, "external_directory", bundled_reference_glob
            )
            if external_action != "allow":
                blocked_skill_paths.append((bundled_reference_glob, external_action))
        if blocked_skill_paths:
            bundled_reference_glob, external_action = blocked_skill_paths[0]
            raise SmokeError(
                f"resolved agent {agent_id} must allow bundled skill paths; "
                f"got {external_action!r} for {bundled_reference_glob}"
            )


def validate_skills(
    value: Any, *, expected: frozenset[str], config_dir: Path
) -> frozenset[str]:
    if not isinstance(value, list):
        raise SmokeError("opencode debug skill must return a JSON array")
    discovered: dict[str, list[dict[str, Any]]] = {}
    external: list[str] = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise SmokeError("opencode debug skill returned an invalid entry")
        name = item["name"]
        location = item.get("location")
        if location == "<built-in>":
            continue
        if name not in expected:
            external.append(name)
            continue
        discovered.setdefault(name, []).append(item)

    if external:
        raise SmokeError(f"unexpected non-built-in skills leaked into smoke: {external}")
    if set(discovered) != expected or any(
        len(entries) != 1 for entries in discovered.values()
    ):
        raise SmokeError(
            "debug skill did not discover exactly its byte-exact Grillmester batch"
        )

    resolved_config = config_dir.resolve()
    for skill_id, entries in discovered.items():
        item = entries[0]
        description = item.get("description")
        location = item.get("location")
        if not isinstance(description, str) or not description.strip():
            raise SmokeError(f"discovered skill {skill_id} has no description")
        if not isinstance(location, str):
            raise SmokeError(f"discovered skill {skill_id} has no source location")
        try:
            Path(location).resolve().relative_to(resolved_config)
        except ValueError as exc:
            raise SmokeError(
                f"discovered skill {skill_id} did not come from the staged target"
            ) from exc
    return frozenset(discovered)


def validate_consumer_context(value: Any, consumer: Path) -> None:
    if not isinstance(value, dict) or value.get("tool") != "read":
        raise SmokeError("debug agent did not execute the native read tool")
    result = value.get("result")
    output = result.get("output") if isinstance(result, dict) else None
    if not isinstance(output, str) or CONSUMER_CONTEXT_MARKER not in output:
        raise SmokeError("Grillmester could not read the consumer-owned AGENTS.md")
    if str((consumer / "AGENTS.md").resolve()) not in output:
        raise SmokeError("native read did not resolve AGENTS.md from the consumer repo")


def hybrid_user_config() -> dict[str, Any]:
    """Return a provider/agent overlay that never needs to contact its endpoint."""

    return {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            HYBRID_PROVIDER_ID: {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Grillmester smoke provider",
                "options": {"baseURL": "http://127.0.0.1:9/v1"},
                "models": {
                    HYBRID_MODEL_ID: {
                        "name": "Grillmester smoke model",
                        "tool_call": True,
                        "modalities": {"input": ["text"], "output": ["text"]},
                        "limit": {"context": 32768, "output": 8192},
                    }
                },
            }
        },
        "agent": {
            "kokk": {"model": f"{HYBRID_PROVIDER_ID}/{HYBRID_MODEL_ID}"}
        },
        "permission": {"read": {USER_DENIED_READ_PATTERN: "deny"}},
    }


def validate_hybrid_override(kokk: Any, grillmester: Any) -> None:
    if not isinstance(kokk, dict) or kokk.get("model") != {
        "providerID": HYBRID_PROVIDER_ID,
        "modelID": HYBRID_MODEL_ID,
    }:
        raise SmokeError("user config did not apply the local model override to Kokk")
    if nested_key_paths(grillmester, "model"):
        raise SmokeError("Kokk's user-owned model override leaked into Grillmester")
    for agent_id, value in (("kokk", kokk), ("grillmester", grillmester)):
        rules = resolved_permission_rules(value, label=f"hybrid agent {agent_id}")
        if (
            effective_permission_action(
                rules, "read", USER_DENIED_READ_SAMPLE
            )
            != "deny"
        ):
            raise SmokeError(
                f"top-level read deny was expanded by resolved agent {agent_id}"
            )


def smoke(
    *,
    binary: Path,
    target: Path = DEFAULT_TARGET,
    base_env: Mapping[str, str] = os.environ,
    timeout_seconds: int = 30,
) -> SmokeReport:
    inventory = target_inventory(target)
    with tempfile.TemporaryDirectory(prefix="grillmester-opencode-smoke-") as temp:
        sandbox = Path(temp)
        config_dir = sandbox / "config"
        config_probe = sandbox / "config-probe"
        agent_list_probe = sandbox / "agent-list-probe"
        skill_probe_root = sandbox / "skill-probes"
        consumer = sandbox / "consumer"
        shutil.copytree(target, config_dir)
        make_tree_writable(config_dir)
        prepare_debug_config_probe(config_dir, config_probe)
        prepare_agent_list_probe(config_dir, agent_list_probe)
        skill_probes = prepare_skill_debug_probes(config_dir, skill_probe_root)
        consumer.mkdir()
        (consumer / "AGENTS.md").write_text(
            "# Disposable consumer contract\n\n"
            f"{CONSUMER_CONTEXT_MARKER}\n",
            encoding="utf-8",
        )
        for path in (
            sandbox / "home",
            sandbox / "tmp",
            sandbox / "xdg/cache",
            sandbox / "xdg/config",
            sandbox / "xdg/data",
            sandbox / "xdg/state",
        ):
            path.mkdir(parents=True, exist_ok=True)

        env = isolated_environment(base_env, sandbox=sandbox, config_dir=config_dir)
        git = shutil.which("git", path=env.get("PATH"))
        if not git:
            raise SmokeError("git is required to create the disposable consumer repo")
        run(
            [git, "init", "--quiet"],
            env=env,
            cwd=consumer,
            timeout_seconds=timeout_seconds,
        )

        version = run(
            [str(binary), "--version"],
            env=env,
            cwd=consumer,
            timeout_seconds=timeout_seconds,
        ).strip()
        if version != EXPECTED_OPENCODE_VERSION:
            raise SmokeError(
                f"expected OpenCode {EXPECTED_OPENCODE_VERSION}, found {version!r}"
            )

        probe_env = dict(env)
        probe_env["OPENCODE_CONFIG_DIR"] = str(config_probe)
        config = run_json(
            [str(binary), "debug", "config", "--pure"],
            env=probe_env,
            cwd=consumer,
            timeout_seconds=timeout_seconds,
        )
        config_agents = validate_resolved_config(config, inventory)

        agent_list_env = dict(env)
        agent_list_env["OPENCODE_CONFIG_DIR"] = str(agent_list_probe)
        agent_list = run(
            [str(binary), "agent", "list", "--pure"],
            env=agent_list_env,
            cwd=consumer,
            timeout_seconds=timeout_seconds,
        )
        validate_agent_list(agent_list)

        for agent_id in sorted(EXPECTED_AGENTS):
            detail = run_json(
                [str(binary), "debug", "agent", agent_id, "--pure"],
                env=env,
                cwd=consumer,
                timeout_seconds=timeout_seconds,
            )
            validate_agent_detail(
                detail,
                agent_id=agent_id,
                config_agent=config_agents[agent_id],
                config_dir=config_dir,
                skill_ids=inventory.skills,
            )

        discovered_skills: set[str] = set()
        for skill_probe, expected_batch in skill_probes:
            skill_env = dict(env)
            skill_env["OPENCODE_CONFIG_DIR"] = str(skill_probe)
            skills = run_json(
                [str(binary), "debug", "skill", "--pure"],
                env=skill_env,
                cwd=consumer,
                timeout_seconds=timeout_seconds,
            )
            overlap = discovered_skills & expected_batch
            if overlap:
                raise SmokeError(f"skill debug batches overlap: {sorted(overlap)}")
            discovered_skills.update(
                validate_skills(
                    skills, expected=expected_batch, config_dir=skill_probe
                )
            )
        if discovered_skills != inventory.skills:
            raise SmokeError("debug skill did not discover all 42 Grillmester skills")

        consumer_context = run_json(
            [
                str(binary),
                "debug",
                "agent",
                "grillmester",
                "--tool",
                "read",
                "--params",
                json.dumps({"filePath": "AGENTS.md", "offset": 1, "limit": 20}),
                "--pure",
            ],
            env=env,
            cwd=consumer,
            timeout_seconds=timeout_seconds,
        )
        validate_consumer_context(consumer_context, consumer)

        # Prove the documented hybrid profile without making a model request.
        user_config = sandbox / "xdg/config/opencode/opencode.json"
        user_config.parent.mkdir(parents=True, exist_ok=True)
        user_config.write_text(
            json.dumps(hybrid_user_config(), indent=2) + "\n", encoding="utf-8"
        )
        hybrid_kokk = run_json(
            [str(binary), "debug", "agent", "kokk", "--pure"],
            env=env,
            cwd=consumer,
            timeout_seconds=timeout_seconds,
        )
        hybrid_grillmester = run_json(
            [str(binary), "debug", "agent", "grillmester", "--pure"],
            env=env,
            cwd=consumer,
            timeout_seconds=timeout_seconds,
        )
        validate_hybrid_override(hybrid_kokk, hybrid_grillmester)

    return SmokeReport(
        version=version,
        primary_agents=len(PRIMARY_AGENTS),
        subagents=len(SUBAGENTS),
        skills=len(inventory.skills),
        commands=len(inventory.commands),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--opencode",
        help="OpenCode executable name or path (default: resolve opencode from PATH)",
    )
    parser.add_argument(
        "--require-binary",
        action="store_true",
        help="fail instead of skipping when the OpenCode binary is unavailable",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_TARGET,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="per-command timeout (default: 30)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    binary = resolve_binary(args.opencode, os.environ)
    if binary is None:
        message = (
            "OpenCode binary not found; install "
            f"opencode-ai@{EXPECTED_OPENCODE_VERSION} or pass --opencode PATH"
        )
        if args.require_binary:
            print(f"ERROR: {message}", file=sys.stderr)
            return 1
        print(f"SKIP: {message}")
        return 0
    if args.timeout_seconds <= 0:
        print("ERROR: --timeout-seconds must be positive", file=sys.stderr)
        return 1

    try:
        report = smoke(
            binary=binary,
            target=args.target.resolve(),
            timeout_seconds=args.timeout_seconds,
        )
    except SmokeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        f"OpenCode {report.version} smoke passed: "
        f"{report.primary_agents} primary agents, "
        f"{report.subagents} subagents, {report.skills} skills, "
        f"{report.commands} commands, inherited model, native permissions, "
        "native consumer AGENTS.md resolution, and an isolated hybrid Kokk "
        "model override"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
