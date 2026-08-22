#!/usr/bin/env python3
"""Compose fail-closed Grillmester permissions for one OpenCode session.

OpenCode v1 evaluates the last matching permission rule.  Its config loader
merges user/project agent policy before config-directory agent frontmatter,
which means a portable agent's later ``allow`` or ``ask`` can otherwise weaken
an earlier user restriction.  This module composes caller ``ask``/``deny``
rules monotonically, resets every staged per-agent permission key, and emits
the final agent maps through last-loaded ``OPENCODE_CONFIG_CONTENT``.

The module deliberately contains no subprocess or cplt integration.  The
lifecycle manager owns the pinned, sandboxed probes and passes their JSON here.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence


SCHEMA_VERSION = 1
NORMAL_FALLBACK = "ask"
RESEARCHER_FALLBACK = "deny"
RESEARCHER_ID = "researcher"
PERMISSION_ACTIONS = frozenset({"allow", "ask", "deny"})
SAFE_DISCOVERY_PERMISSIONS = ("glob", "grep", "list")
READ_GUARD = {
    "*": "allow",
    "*.env": "ask",
    "*.env.*": "ask",
    "*.env.example": "allow",
}
AGENT_ID = re.compile(r"^[a-z][a-z0-9-]*$")
YAML_KEY = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_-]*$")
JSON_MAX_DEPTH = 40
SAFE_PROVIDER_NPM = "@ai-sdk/openai-compatible"
OPENCODE_SKILL_PROBE_MARKER = "Managed OpenCode skill probe"
PINNED_BUILTIN_SKILL_ID = "customize-opencode"
PINNED_BUILTIN_SKILL_LOCATION = "<built-in>"
# OpenCode 1.18.20 applies built-in provider-specific loaders to these exact
# IDs independently of config ``npm`` and the default-plugin disable flag.
# Managed sessions reserve them so every accepted provider uses only the
# reviewed OpenAI-compatible SDK path.
RESERVED_PROVIDER_IDS = frozenset(
    {
        "amazon-bedrock",
        "anthropic",
        "azure",
        "azure-cognitive-services",
        "cerebras",
        "cloudflare-ai-gateway",
        "cloudflare-workers-ai",
        "github-copilot",
        "gitlab",
        "google-vertex",
        "google-vertex-anthropic",
        "kilo",
        "llmgateway",
        "meta",
        "nvidia",
        "opencode",
        "openai",
        "openrouter",
        "sap-ai-core",
        "snowflake-cortex",
        "vercel",
        "xai",
        "zenmux",
    }
)
DISABLED_NATIVE_AGENTS = ("build", "explore", "general", "plan")
HIDDEN_NATIVE_AGENTS = ("compaction", "summary", "title")
DESIGNER_REVIEWED_SERVER_PATTERNS = (
    "node scripts/server.js --project-dir *",
    "node *grillmester-design-prototype/scripts/server.js --project-dir *",
)
# OpenCode 1.18.20 registers these tools even when its native ``plan`` and
# ``build`` agents are disabled. ``plan_exit`` queues a synthetic next user
# message for the native ``build`` agent, so exposing either tool would break
# the one-selected-primary invariant after the otherwise safe preflight.
DISABLED_PLAN_TOOLS = ("plan_enter", "plan_exit")


class PermissionCompositionError(RuntimeError):
    """Raised when a session policy cannot be composed or proved safely."""


PermissionRule = str | dict[str, str]
PermissionMap = dict[str, PermissionRule]


@dataclass(frozen=True)
class GeneratedAgent:
    agent_id: str
    description: str
    mode: str
    hidden: bool
    prompt: str
    permission: PermissionMap
    source: Path


@dataclass(frozen=True)
class ComposedPolicy:
    config_content: str
    agents: Mapping[str, PermissionMap]
    agent_contracts: Mapping[str, Mapping[str, Any]]
    command_contracts: Mapping[str, Mapping[str, Any]]
    instruction_paths: tuple[str, ...]
    reset_keys: Mapping[str, tuple[str, ...]]
    imported_denies: Mapping[str, tuple[tuple[str, str], ...]]
    runtime_agent: str
    enabled_agent_ids: tuple[str, ...]
    disabled_agent_ids: tuple[str, ...]
    hidden_native_agent_ids: tuple[str, ...]
    provider_contract: Mapping[str, Any]


def _json_depth(value: object, *, depth: int = 0) -> int:
    if depth > JSON_MAX_DEPTH:
        raise PermissionCompositionError("resolved OpenCode config is too deeply nested")
    if isinstance(value, dict):
        return max((_json_depth(item, depth=depth + 1) for item in value.values()), default=depth)
    if isinstance(value, list):
        return max((_json_depth(item, depth=depth + 1) for item in value), default=depth)
    return depth


def parse_resolved_config(content: str | bytes) -> dict[str, Any]:
    """Parse one bounded ``opencode debug config`` JSON object."""

    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PermissionCompositionError("resolved OpenCode config is not UTF-8") from exc
    try:
        value = json.loads(content, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, RecursionError) as exc:
        if isinstance(exc, RecursionError):
            raise PermissionCompositionError(
                "resolved OpenCode config exceeds the JSON nesting limit"
            ) from exc
        raise PermissionCompositionError(
            f"resolved OpenCode config is not JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    if not isinstance(value, dict):
        raise PermissionCompositionError("resolved OpenCode config must be an object")
    _json_depth(value)
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PermissionCompositionError("duplicate JSON key in OpenCode output")
        result[key] = value
    return result


def require_no_external_extensions(
    config: Mapping[str, Any],
    expected_instructions: Sequence[str] = (),
) -> None:
    """Reject extension surfaces that can add tools or execute code.

    This check operates on resolved config as a second line of defence.  The
    lifecycle manager must statically reject plugin files/config before asking
    OpenCode to resolve config, because OpenCode 1.18.20 can import an
    auto-discovered project plugin even in pure mode.
    """

    if config.get("share") != "disabled":
        raise PermissionCompositionError(
            "managed Grillmester sessions require effective OpenCode share=disabled"
        )
    if config.get("autoupdate") is not False:
        raise PermissionCompositionError(
            "managed Grillmester sessions require effective OpenCode autoupdate=false"
        )

    plugins = config.get("plugin", [])
    origins = config.get("plugin_origins", [])
    if plugins not in (None, []) or origins not in (None, []):
        raise PermissionCompositionError(
            "managed Grillmester sessions forbid external OpenCode plugins"
        )
    mcp = config.get("mcp", {})
    if mcp not in (None, {}):
        if not isinstance(mcp, dict):
            raise PermissionCompositionError("resolved OpenCode mcp config must be an object")
        enabled: list[str] = []
        for name, entry in mcp.items():
            if not isinstance(name, str) or not name:
                raise PermissionCompositionError(
                    "resolved OpenCode mcp IDs must be non-empty strings"
                )
            if not isinstance(entry, dict):
                raise PermissionCompositionError("resolved MCP entry must be an object")
            if entry.get("enabled") is not False:
                enabled.append(name)
        if enabled:
            raise PermissionCompositionError(
                "managed Grillmester sessions forbid enabled OpenCode MCP servers"
            )

    skills = config.get("skills", {})
    if skills not in (None, {}):
        if not isinstance(skills, dict):
            raise PermissionCompositionError("resolved OpenCode skills config must be an object")
        for field in ("paths", "urls"):
            value = skills.get(field)
            if value not in (None, []):
                raise PermissionCompositionError(
                    "managed Grillmester sessions forbid external OpenCode "
                    f"skills.{field}"
                )

    instructions = config.get("instructions")
    normalized_instructions = [] if instructions is None else instructions
    if (
        not isinstance(normalized_instructions, list)
        or normalized_instructions != list(expected_instructions)
    ):
        raise PermissionCompositionError(
            "managed Grillmester sessions allow only the fingerprinted project "
            "instruction chain"
        )
    if config.get("shell") not in (None, ""):
        raise PermissionCompositionError(
            "managed Grillmester sessions forbid a custom OpenCode shell"
        )
    for field in ("references", "reference"):
        if config.get(field) not in (None, {}):
            raise PermissionCompositionError(
                f"managed Grillmester sessions forbid OpenCode {field}"
            )
    server = config.get("server")
    if server not in (None, {}):
        if not isinstance(server, dict):
            raise PermissionCompositionError("resolved OpenCode server must be an object")
        if server.get("hostname") not in (None, "127.0.0.1", "localhost"):
            raise PermissionCompositionError(
                "managed Grillmester sessions require a loopback OpenCode server"
            )
        if server.get("mdns") not in (None, False) or server.get("mdnsDomain") is not None:
            raise PermissionCompositionError(
                "managed Grillmester sessions forbid OpenCode mDNS"
            )
        if server.get("cors") not in (None, []):
            raise PermissionCompositionError(
                "managed Grillmester sessions forbid OpenCode CORS origins"
            )
    experimental = config.get("experimental")
    if experimental not in (None, {}):
        if not isinstance(experimental, dict):
            raise PermissionCompositionError(
                "resolved OpenCode experimental config must be an object"
            )
        if experimental.get("openTelemetry") is True:
            raise PermissionCompositionError(
                "managed Grillmester sessions forbid OpenCode telemetry export"
            )

    _require_safe_provider_npm(config.get("provider"), label="resolved provider")
    _require_no_executable_commands(config.get("lsp"), label="resolved lsp")
    _require_no_executable_commands(config.get("formatter"), label="resolved formatter")


def _require_no_executable_commands(value: object, *, label: str) -> None:
    """Allow only absent/false or explicitly disabled command entries."""

    if value in (None, False, {}):
        return
    if not isinstance(value, dict):
        raise PermissionCompositionError(
            f"{label} must be absent, false, or contain disabled-only entries"
        )
    for entry_id, entry in value.items():
        if (
            not isinstance(entry_id, str)
            or not entry_id
            or not isinstance(entry, dict)
            or entry.get("disabled") is not True
            or "command" in entry
        ):
            raise PermissionCompositionError(
                f"{label} contains an executable or non-disabled entry"
            )


def _require_safe_npm(value: object, *, label: str) -> None:
    if value is None:
        return
    if value != SAFE_PROVIDER_NPM:
        raise PermissionCompositionError(
            f"{label} must be omitted or exactly {SAFE_PROVIDER_NPM!r} in a "
            "managed Grillmester session"
        )


def _require_safe_provider_npm(value: object, *, label: str) -> None:
    """Forbid provider SDK specs that make OpenCode install/import code.

    OpenCode 1.18.20 bundles ``@ai-sdk/openai-compatible``.  Every unknown
    package spec (including ``file://``) reaches ``Npm.add`` or a direct
    dynamic import when a model is used.  Omitting ``npm`` also safely selects
    the bundled OpenAI-compatible fallback for custom local/cloud providers.
    """

    if value in (None, {}):
        return
    if not isinstance(value, dict):
        raise PermissionCompositionError(f"{label} must be an object")
    for provider_id, provider in value.items():
        if not isinstance(provider_id, str) or not provider_id:
            raise PermissionCompositionError(f"{label} contains an invalid provider ID")
        if provider_id in RESERVED_PROVIDER_IDS:
            raise PermissionCompositionError(
                f"{label} uses a provider ID with built-in "
                "OpenCode 1.18.20 loader behavior"
            )
        if not isinstance(provider, dict):
            raise PermissionCompositionError(f"{label} entry must be an object")
        provider_npm = provider.get("npm")
        _require_safe_npm(provider_npm, label=f"{label} SDK")
        models = provider.get("models")
        if models in (None, {}):
            continue
        if not isinstance(models, dict):
            raise PermissionCompositionError(
                f"{label} models must be an object"
            )
        for model_id, model in models.items():
            if not isinstance(model_id, str) or not model_id or not isinstance(model, dict):
                raise PermissionCompositionError(
                    f"{label} models contain an invalid model"
                )
            model_provider = model.get("provider")
            if model_provider is None:
                model_provider = {}
            if not isinstance(model_provider, dict):
                raise PermissionCompositionError(
                    f"{label} model provider must be an object"
                )
            model_npm = model_provider.get("npm")
            _require_safe_npm(
                model_npm,
                label=f"{label} model provider SDK",
            )
            if model_npm is None and provider_npm != SAFE_PROVIDER_NPM:
                raise PermissionCompositionError(
                    f"{label} model must resolve through "
                    f"exactly {SAFE_PROVIDER_NPM!r}"
                )


def _parse_yaml_key(raw: str, *, label: str) -> str:
    if raw.startswith('"'):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PermissionCompositionError(f"{label} has an invalid quoted key") from exc
        if not isinstance(value, str) or not value:
            raise PermissionCompositionError(f"{label} has an invalid key")
        return value
    if not YAML_KEY.fullmatch(raw):
        raise PermissionCompositionError(f"{label} has an unsupported YAML key {raw!r}")
    return raw


def _parse_frontmatter_string(raw: str, *, label: str) -> str:
    if raw.startswith('"'):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PermissionCompositionError(f"{label} has an invalid quoted value") from exc
        if not isinstance(value, str):
            raise PermissionCompositionError(f"{label} must be a string")
        return value
    if not raw or raw != raw.strip() or any(character in raw for character in "{}[]"):
        raise PermissionCompositionError(f"{label} has an unsupported YAML scalar")
    return raw


def _parse_permission_block(lines: Sequence[str], *, label: str) -> PermissionMap:
    result: PermissionMap = {}
    current: str | None = None
    for line in lines:
        if line.startswith("  ") and not line.startswith("    "):
            raw = line[2:]
            if ":" not in raw:
                raise PermissionCompositionError(f"{label} contains malformed permission YAML")
            raw_key, raw_value = raw.split(":", 1)
            key = _parse_yaml_key(raw_key, label=label)
            if key in result:
                raise PermissionCompositionError(f"{label} repeats permission key {key!r}")
            value = raw_value.strip()
            if value:
                if value not in PERMISSION_ACTIONS:
                    raise PermissionCompositionError(f"{label} has unsupported action {value!r}")
                result[key] = value
                current = None
            else:
                result[key] = {}
                current = key
            continue
        if line.startswith("    ") and current is not None:
            raw = line[4:]
            if ":" not in raw:
                raise PermissionCompositionError(f"{label} contains malformed pattern YAML")
            raw_pattern, raw_action = raw.split(":", 1)
            pattern = _parse_yaml_key(raw_pattern, label=label)
            action = raw_action.strip()
            if action not in PERMISSION_ACTIONS:
                raise PermissionCompositionError(f"{label} has unsupported action {action!r}")
            patterns = result[current]
            assert isinstance(patterns, dict)
            if pattern in patterns:
                raise PermissionCompositionError(
                    f"{label} repeats permission pattern {current}.{pattern}"
                )
            patterns[pattern] = action
            continue
        raise PermissionCompositionError(f"{label} has unsupported permission YAML: {line!r}")
    if not result:
        raise PermissionCompositionError(f"{label} has no permission rules")
    return result


def parse_generated_agent(path: Path) -> GeneratedAgent:
    """Parse the deterministic YAML subset emitted by ``generate_opencode.py``."""

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PermissionCompositionError(f"could not read generated agent {path}: {exc}") from exc
    if not text.startswith("---\n"):
        raise PermissionCompositionError(f"generated agent lacks frontmatter: {path}")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise PermissionCompositionError(f"generated agent has unterminated frontmatter: {path}")
    lines = text[4:end].splitlines()
    values: dict[str, str] = {}
    permission_start: int | None = None
    for index, line in enumerate(lines):
        if line == "permission:":
            permission_start = index + 1
            break
        if line.startswith(" ") or ":" not in line:
            raise PermissionCompositionError(f"generated agent frontmatter is not canonical: {path}")
        key, value = line.split(":", 1)
        values[key] = value.strip()
    if permission_start is None:
        raise PermissionCompositionError(f"generated agent has no permission block: {path}")
    permission_lines = lines[permission_start:]
    if any(line and not line.startswith("  ") for line in permission_lines):
        raise PermissionCompositionError(
            f"permission must be the last generated frontmatter field: {path}"
        )
    mode = values.get("mode")
    hidden_raw = values.get("hidden")
    if mode not in {"primary", "subagent"} or hidden_raw not in {"true", "false"}:
        raise PermissionCompositionError(f"generated agent has invalid mode/hidden fields: {path}")
    agent_id = path.stem
    if not AGENT_ID.fullmatch(agent_id):
        raise PermissionCompositionError(f"generated agent has invalid ID: {agent_id!r}")
    return GeneratedAgent(
        agent_id=agent_id,
        description=_parse_frontmatter_string(
            values.get("description", ""), label=f"{path} description"
        ),
        mode=mode,
        hidden=hidden_raw == "true",
        prompt=text[end + len("\n---\n") :].strip(),
        permission=_parse_permission_block(permission_lines, label=str(path)),
        source=path,
    )


def load_generated_agents(config_dir: Path) -> dict[str, GeneratedAgent]:
    agents_dir = config_dir / "agents"
    try:
        paths = sorted(agents_dir.glob("*.md"), key=lambda path: path.name)
    except OSError as exc:
        raise PermissionCompositionError(f"could not list generated agents: {exc}") from exc
    agents = {agent.agent_id: agent for agent in map(parse_generated_agent, paths)}
    if not agents:
        raise PermissionCompositionError("generated OpenCode config has no agents")
    if len(agents) != len(paths):
        raise PermissionCompositionError("generated OpenCode agent IDs collide")
    return agents


def _parse_frontmatter_document(path: Path) -> tuple[dict[str, Any], str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PermissionCompositionError(f"could not read generated component {path}: {exc}") from exc
    if not text.startswith("---\n"):
        raise PermissionCompositionError(f"generated component lacks frontmatter: {path}")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise PermissionCompositionError(f"generated component has unterminated frontmatter: {path}")
    values: dict[str, Any] = {}
    for line in text[4:end].splitlines():
        if line.startswith(" ") or ":" not in line:
            raise PermissionCompositionError(
                f"generated component frontmatter is not canonical: {path}"
            )
        key, raw = line.split(":", 1)
        if not YAML_KEY.fullmatch(key) or key in values:
            raise PermissionCompositionError(
                f"generated component has an invalid/repeated field: {path}"
            )
        raw = raw.strip()
        if key == "subtask":
            if raw not in {"true", "false"}:
                raise PermissionCompositionError(f"{path} subtask must be boolean")
            values[key] = raw == "true"
        else:
            values[key] = _parse_frontmatter_string(raw, label=f"{path} {key}")
    return values, text[end + len("\n---\n") :].strip()


def load_generated_commands(config_dir: Path) -> dict[str, Mapping[str, Any]]:
    commands_dir = config_dir / "commands"
    try:
        paths = sorted(commands_dir.glob("*.md"), key=lambda path: path.name)
    except OSError as exc:
        raise PermissionCompositionError(f"could not list generated commands: {exc}") from exc
    if not paths:
        raise PermissionCompositionError("generated OpenCode config has no commands")
    commands: dict[str, Mapping[str, Any]] = {}
    allowed = {"description", "agent", "model", "variant", "subtask"}
    for path in paths:
        command_id = path.stem
        if not AGENT_ID.fullmatch(command_id):
            raise PermissionCompositionError(f"generated command has invalid ID: {command_id!r}")
        fields, template = _parse_frontmatter_document(path)
        unexpected = sorted(set(fields) - allowed)
        if unexpected:
            raise PermissionCompositionError(
                f"generated command {command_id!r} has unsupported fields: "
                + ", ".join(unexpected)
            )
        if not template:
            raise PermissionCompositionError(f"generated command {command_id!r} has no template")
        commands[command_id] = {"template": template, **fields}
    if len(commands) != len(paths):
        raise PermissionCompositionError("generated OpenCode command IDs collide")
    return commands


def _validate_permission(value: object, *, label: str) -> PermissionMap:
    if value is None:
        return {}
    if isinstance(value, str):
        if value not in PERMISSION_ACTIONS:
            raise PermissionCompositionError(f"{label} has unsupported action {value!r}")
        return {"*": value}
    if not isinstance(value, dict):
        raise PermissionCompositionError(f"{label} must be an action or object")
    result: PermissionMap = {}
    for key, rule in value.items():
        if not isinstance(key, str) or not key:
            raise PermissionCompositionError(f"{label} contains an invalid permission key")
        if isinstance(rule, str):
            if rule not in PERMISSION_ACTIONS:
                raise PermissionCompositionError(f"{label}.{key} has unsupported action")
            result[key] = rule
            continue
        if not isinstance(rule, dict) or not rule:
            raise PermissionCompositionError(f"{label}.{key} must be an action or non-empty object")
        patterns: dict[str, str] = {}
        for pattern, action in rule.items():
            if not isinstance(pattern, str) or not pattern or action not in PERMISSION_ACTIONS:
                raise PermissionCompositionError(f"{label}.{key} contains an invalid pattern/action")
            patterns[pattern] = action
        result[key] = patterns
    return result


def _constraint_rules(permission: PermissionMap) -> list[tuple[str, str, str]]:
    """Return explicit ask/deny constraints; caller allows are never imported."""

    result: list[tuple[str, str, str]] = []
    for key, rule in permission.items():
        if isinstance(rule, str):
            if rule in {"ask", "deny"}:
                result.append((key, "*", rule))
            continue
        result.extend(
            (key, pattern, action)
            for pattern, action in rule.items()
            if action in {"ask", "deny"}
        )
    return result


def _resolved_agent_permissions(config: Mapping[str, Any], agent_id: str) -> PermissionMap:
    raw_agents = config.get("agent", {})
    if raw_agents in (None, {}):
        return {}
    if not isinstance(raw_agents, dict):
        raise PermissionCompositionError("resolved OpenCode agent config must be an object")
    raw_agent = raw_agents.get(agent_id)
    if raw_agent is None:
        return {}
    if not isinstance(raw_agent, dict):
        raise PermissionCompositionError(f"resolved agent {agent_id!r} must be an object")
    return _validate_permission(
        raw_agent.get("permission"), label=f"resolved agent {agent_id}.permission"
    )


def _require_safe_baseline_agents_and_commands(
    config: Mapping[str, Any], generated_agent_ids: Iterable[str]
) -> None:
    """Reject ambient entry points while preserving audited user restrictions.

    OpenCode command templates expand ``!`` shell snippets before model tool
    permission is consulted.  Ambient commands therefore cannot be made safe by
    the composed tool policy.  Ambient agents are likewise selectable by ID, so
    only restriction/model metadata for generated agent IDs is accepted.
    """

    commands = config.get("command")
    if commands not in (None, {}):
        raise PermissionCompositionError(
            "managed Grillmester sessions forbid ambient OpenCode commands"
        )

    raw_agents = config.get("agent")
    if raw_agents in (None, {}):
        return
    if not isinstance(raw_agents, dict):
        raise PermissionCompositionError("resolved OpenCode agent config must be an object")
    expected = set(generated_agent_ids)
    unknown = sorted(set(raw_agents) - expected)
    if unknown:
        raise PermissionCompositionError(
            "resolved OpenCode config contains unknown ambient agents"
        )
    allowed_fields = {"permission", "model", "variant"}
    for agent_id, entry in raw_agents.items():
        if not isinstance(entry, dict):
            raise PermissionCompositionError("resolved generated agent must be an object")
        unsupported = sorted(set(entry) - allowed_fields)
        if unsupported:
            raise PermissionCompositionError(
                "resolved generated agent has unsupported ambient agent fields"
            )
        for field in ("model", "variant"):
            value = entry.get(field)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise PermissionCompositionError(
                    "resolved generated agent model metadata must be a non-empty string"
                )


def _target_skills(config_dir: Path) -> tuple[tuple[str, str], ...]:
    skills = config_dir / "skills"
    try:
        paths = sorted(
            (path for path in skills.iterdir() if path.is_dir() and not path.is_symlink()),
            key=lambda path: path.name,
        )
    except OSError as exc:
        raise PermissionCompositionError(f"could not enumerate generated skills: {exc}") from exc
    if not paths:
        raise PermissionCompositionError("generated OpenCode config has no skills")
    return tuple(
        (path.name, str(path.resolve(strict=True) / "*")) for path in paths
    )


def _copy_rule(rule: PermissionRule) -> PermissionRule:
    return dict(rule) if isinstance(rule, dict) else rule


def _restrict_allows(rule: PermissionRule) -> PermissionRule:
    if isinstance(rule, str):
        return "ask" if rule == "allow" else rule
    return {
        pattern: "ask" if action == "allow" else action
        for pattern, action in rule.items()
    }


def _is_literal_pattern(pattern: str) -> bool:
    return "*" not in pattern and "?" not in pattern


def _patterns_may_overlap(left: str, right: str) -> bool:
    """Conservatively decide whether two OpenCode wildcard patterns overlap."""

    if _is_literal_pattern(left):
        return wildcard_match(left, right)
    if _is_literal_pattern(right):
        return wildcard_match(right, left)
    # Proving two arbitrary glob languages disjoint is unnecessary here.  A
    # false positive only changes an allow to ask; a false negative could
    # bypass a caller restriction.
    return True


def _downgrade_matching_allows(
    permission: PermissionMap, key: str, resource_pattern: str
) -> None:
    current = permission[key]
    if resource_pattern == "*":
        permission[key] = _restrict_allows(current)
        return
    if isinstance(current, str):
        if current == "allow":
            permission[key] = {"*": "allow", resource_pattern: "ask"}
        return

    # With a non-deny catch-all, a terminal patterned ask is an exact safe
    # intersection: every matching resource was already allow/ask.  Moving an
    # existing pattern to the end is required by OpenCode's last-match-wins
    # evaluation.
    if "deny" not in current.values() and current.get("*") in {"allow", "ask"}:
        current.pop(resource_pattern, None)
        current[resource_pattern] = "ask"
        return

    # A broad ask appended after a role deny would weaken that deny.  Instead,
    # downgrade each possibly intersecting allow rule.  Wildcard/wildcard
    # overlap is deliberately conservative.
    for existing_pattern, existing_action in tuple(current.items()):
        if existing_action == "allow" and _patterns_may_overlap(
            existing_pattern, resource_pattern
        ):
            current[existing_pattern] = "ask"


def _append_deny_rule(
    permission: PermissionMap, key: str, resource_pattern: str
) -> None:
    current = permission.get(key)
    if resource_pattern == "*":
        permission[key] = "deny"
        return
    if current == "deny":
        return
    if isinstance(current, str):
        permission[key] = {"*": current, resource_pattern: "deny"}
        return
    if current is None:
        permission[key] = {resource_pattern: "deny"}
        return
    # Reinsert an existing rule so the caller deny is terminal for this tool.
    current.pop(resource_pattern, None)
    current[resource_pattern] = "deny"


def _permission_rules(permission: PermissionMap) -> list[dict[str, str]]:
    return _rules_from_permission(permission)


def _append_constraints(
    permission: PermissionMap,
    constraints: Iterable[tuple[str, str, str]],
    *,
    fallback: str,
) -> None:
    ordered_constraints = tuple(constraints)
    unsupported_generated_globs = sorted(
        key for key in permission if key != "*" and not _is_literal_pattern(key)
    )
    if unsupported_generated_globs:
        raise PermissionCompositionError(
            "generated permission tool keys must be exact literals or '*'"
        )

    # Exact caller tool keys need an explicit role fallback after the staged
    # reset.  Patterned keys are rendered only as constraint rules: attaching
    # an ask fallback to overlapping globs can override an earlier role deny.
    for key, _pattern, _action in ordered_constraints:
        if key != "*" and _is_literal_pattern(key) and key not in permission:
            permission[key] = fallback
    exact_keys = tuple(key for key in permission if _is_literal_pattern(key))

    wildcard_fallback = permission.get("*")
    if wildcard_fallback is not None and next(iter(permission)) != "*":
        raise PermissionCompositionError(
            "generated wildcard tool fallback must be the first managed rule"
        )
    if (
        wildcard_fallback == "allow"
        or isinstance(wildcard_fallback, dict)
        and "allow" in wildcard_fallback.values()
    ):
        raise PermissionCompositionError(
            "generated wildcard tool fallback must not allow managed operations"
        )

    for key, pattern, action in ordered_constraints:
        if key == "*" and pattern == "*" and action == "deny":
            permission.clear()
            permission["*"] = "deny"
            return
        matching_exact_keys = tuple(
            existing for existing in exact_keys if wildcard_match(existing, key)
        )
        if action == "ask":
            for existing in matching_exact_keys:
                _downgrade_matching_allows(permission, existing, pattern)
            continue
        for existing in matching_exact_keys:
            _append_deny_rule(permission, existing, pattern)
        if not _is_literal_pattern(key):
            # Known exact tools were constrained above.  This terminal glob
            # covers matching future/unknown tools without adding a fallback
            # that could weaken another exact or wildcard deny.
            _append_deny_rule(permission, key, pattern)


def _legacy_tool_permissions(config: Mapping[str, Any], *, label: str) -> PermissionMap:
    tools = config.get("tools")
    if tools in (None, {}):
        return {}
    if not isinstance(tools, dict):
        raise PermissionCompositionError(f"{label}.tools must be an object")
    result: PermissionMap = {}
    for tool, enabled in tools.items():
        if not isinstance(tool, str) or not tool or not isinstance(enabled, bool):
            raise PermissionCompositionError(f"{label}.tools contains an invalid entry")
        key = "edit" if tool in {"write", "edit", "patch"} else tool
        result[key] = "allow" if enabled else "deny"
    return result


def compose_policy(
    config_dir: Path,
    resolved_config: Mapping[str, Any],
    restriction_configs: Sequence[Mapping[str, Any]] = (),
    expected_instructions: Sequence[str] = (),
    runtime_agent: str = "grillmester",
) -> ComposedPolicy:
    """Build deterministic role policy plus monotone caller restrictions."""

    agents = load_generated_agents(config_dir)
    command_contracts = load_generated_commands(config_dir)
    selected = agents.get(runtime_agent)
    if selected is None or selected.mode != "primary" or selected.hidden:
        raise PermissionCompositionError(
            f"managed runtime agent {runtime_agent!r} must be a visible generated primary"
        )
    require_no_external_extensions(resolved_config)
    _require_safe_baseline_agents_and_commands(resolved_config, agents)
    # The baseline debug output is already variable-substituted by OpenCode.
    # Copying its permission keys/patterns would move arbitrary strings (and
    # potentially {file:...}/{env:...} contents) into OPENCODE_CONFIG_CONTENT.
    # Managed role policy is authoritative; only raw, manager-read project
    # overlays below may contribute conservative ask/deny constraints.
    top_sources: list[PermissionMap] = []
    for index, overlay in enumerate(restriction_configs):
        if not isinstance(overlay, Mapping):
            raise PermissionCompositionError(
                f"project permission overlay {index} must be an object"
            )
        top_sources.extend(
            (
                _validate_permission(
                    overlay.get("permission"),
                    label=f"project permission overlay {index}.permission",
                ),
                _legacy_tool_permissions(
                    overlay, label=f"project permission overlay {index}"
                ),
            )
        )
    top_constraints = [
        constraint
        for source in top_sources
        for constraint in _constraint_rules(source)
    ]
    target_skills = _target_skills(config_dir)
    skill_paths = tuple(pattern for _skill_id, pattern in target_skills)
    composed: dict[str, PermissionMap] = {}
    contracts: dict[str, Mapping[str, Any]] = {}
    resets: dict[str, tuple[str, ...]] = {}
    imported: dict[str, tuple[tuple[str, str], ...]] = {}

    for agent_id, agent in agents.items():
        fallback = RESEARCHER_FALLBACK if agent_id == RESEARCHER_ID else NORMAL_FALLBACK
        user_agent_sources = [
            _resolved_agent_permissions(overlay, agent_id)
            for overlay in restriction_configs
        ]
        user_agent = user_agent_sources[0] if user_agent_sources else {}
        wildcard_rule = user_agent.get("*")
        if wildcard_rule is not None and not any(
            action in {"ask", "deny"}
            for key, _pattern, action in _constraint_rules(user_agent)
            if key == "*"
        ):
            raise PermissionCompositionError(
                f"resolved agent {agent_id!r} defines an allow-only wildcard; "
                "OpenCode cannot reorder it safely for managed composition"
            )

        permission: PermissionMap = {}
        if agent_id == RESEARCHER_ID:
            permission["*"] = "deny"
        permission["read"] = dict(READ_GUARD)
        permission["external_directory"] = {
            "*": "ask",
            **{pattern: "allow" for pattern in skill_paths},
        }
        for key in SAFE_DISCOVERY_PERMISSIONS:
            permission[key] = "allow"
        if agent_id == RESEARCHER_ID:
            permission["webfetch"] = "allow"
            permission["websearch"] = "allow"
        for key, rule in agent.permission.items():
            permission[key] = _copy_rule(rule)
        if agent_id == "designer":
            bash = permission.get("bash")
            if not isinstance(bash, dict) or any(
                bash.get(pattern) != "ask"
                for pattern in DESIGNER_REVIEWED_SERVER_PATTERNS
            ):
                raise PermissionCompositionError(
                    "generated Designer server contract changed unexpectedly"
                )
            # Do not pre-authorize either portable shape. Both can resolve to a
            # consumer-controlled script, and the trailing project wildcard can
            # contain shell metacharacters. A deliberate Allow-once prompt is
            # the stock-client boundary; later cleanup-all shapes remain deny.
        if agent_id != RESEARCHER_ID:
            original_skill = agent.permission.get("skill")
            manual_only = {
                skill_id
                for skill_id, action in (
                    original_skill.items()
                    if isinstance(original_skill, dict)
                    else ()
                )
                if action == "ask"
            }
            permission["skill"] = {
                "*": "ask",
                **{
                    skill_id: "ask" if skill_id in manual_only else "allow"
                    for skill_id, _pattern in target_skills
                },
            }

        # These are managed-runtime constraints, not portable target policy.
        # Keep the scalar denies after the generated role map so they also win
        # if a role starts allowing a future OpenCode plan tool.
        for key in DISABLED_PLAN_TOOLS:
            permission[key] = "deny"

        # Every user-defined, non-role permission is explicitly brought back to
        # the role fallback after the staged per-key reset.  This prevents a
        # plugin/MCP-like tool name from inheriting OpenCode's built-in allow.
        for key in (
            *(key for source in top_sources for key in source),
            *(key for source in user_agent_sources for key in source),
        ):
            if (
                key != "*"
                and _is_literal_pattern(key)
                and key not in permission
            ):
                permission[key] = fallback

        constraints = [
            *top_constraints,
            *(
                constraint
                for source in user_agent_sources
                for constraint in _constraint_rules(source)
            ),
        ]
        _append_constraints(permission, constraints, fallback=fallback)
        composed[agent_id] = permission
        contracts[agent_id] = {
            "description": agent.description,
            "mode": agent.mode,
            "hidden": agent.hidden,
            "prompt": agent.prompt,
        }
        imported[agent_id] = tuple(
            (key, pattern) for key, pattern, _action in constraints
        )
        # Match the final map's insertion order so OpenCode's deep merge keeps
        # the composed rule sequence as an exact, verifiable suffix.
        resets[agent_id] = tuple(permission)

    content = {
        "autoupdate": False,
        "share": "disabled",
        # This global fallback executes before every composed agent map.  It
        # covers future/unknown tool names for normal roles without inserting a
        # per-agent wildcard that could be reordered by a same-name user agent.
        "permission": {"*": NORMAL_FALLBACK},
        "agent": {
            **{
                agent_id: {"disable": True}
                for agent_id in DISABLED_NATIVE_AGENTS
            },
            **{
                agent_id: {"permission": {"*": "deny"}}
                for agent_id in HIDDEN_NATIVE_AGENTS
            },
            **{
                agent_id: {
                    "permission": permission,
                    **(
                        {"disable": True}
                        if contracts[agent_id]["mode"] == "primary"
                        and agent_id != runtime_agent
                        else {}
                    ),
                }
                for agent_id, permission in sorted(composed.items())
            },
        },
    }
    # The manager isolates XDG_CONFIG_HOME after this resolved baseline is
    # reviewed, so preserve only the statically admitted provider definitions
    # and the supported model/variant overrides for known generated agents.
    # Do not carry the rest of ambient config into the managed process.
    providers = resolved_config.get("provider")
    if providers is None:
        providers = {}
    if not isinstance(providers, Mapping):  # validated above
        raise PermissionCompositionError("resolved provider config must be an object")
    provider_contract = dict(providers)
    content["provider"] = provider_contract
    content["enabled_providers"] = sorted(provider_contract)
    content["disabled_providers"] = []
    baseline_agents = resolved_config.get("agent")
    if isinstance(baseline_agents, Mapping):
        for agent_id, entry in baseline_agents.items():
            if not isinstance(entry, Mapping):  # validated above
                continue
            for field in ("model", "variant"):
                value = entry.get(field)
                if value is not None:
                    content["agent"][agent_id][field] = value
                    contracts[agent_id] = {
                        **contracts[agent_id],
                        field: value,
                    }
    if expected_instructions:
        content["instructions"] = list(expected_instructions)
    return ComposedPolicy(
        config_content=json.dumps(content, ensure_ascii=False, separators=(",", ":")),
        agents=composed,
        agent_contracts=contracts,
        command_contracts=command_contracts,
        instruction_paths=tuple(expected_instructions),
        reset_keys=resets,
        imported_denies=imported,
        runtime_agent=runtime_agent,
        enabled_agent_ids=tuple(
            sorted(
                agent_id
                for agent_id, contract in contracts.items()
                if contract["mode"] == "subagent" or agent_id == runtime_agent
            )
        ),
        disabled_agent_ids=tuple(
            sorted(
                {
                    *DISABLED_NATIVE_AGENTS,
                    *(
                        agent_id
                        for agent_id, contract in contracts.items()
                        if contract["mode"] == "primary" and agent_id != runtime_agent
                    ),
                }
            )
        ),
        hidden_native_agent_ids=HIDDEN_NATIVE_AGENTS,
        provider_contract=provider_contract,
    )


def build_bounded_config_probe_content(composed: ComposedPolicy) -> str:
    """Drop generated-agent permission bulk that is verified by per-agent probes."""

    try:
        content = json.loads(
            composed.config_content, object_pairs_hook=_reject_duplicate_keys
        )
    except (json.JSONDecodeError, RecursionError) as exc:  # pragma: no cover
        raise PermissionCompositionError(
            "composed OpenCode config content is not valid JSON"
        ) from exc
    agents = content.get("agent")
    if not isinstance(agents, dict):
        raise PermissionCompositionError("composed OpenCode config has no agent map")
    for agent_id, permission in composed.agents.items():
        entry = agents.get(agent_id)
        if not isinstance(entry, dict) or entry.get("permission") != permission:
            raise PermissionCompositionError(
                f"composed generated agent {agent_id!r} permission drifted"
            )
        unexpected = set(entry) - {"permission", "disable", "model", "variant"}
        if unexpected:
            raise PermissionCompositionError(
                f"composed generated agent {agent_id!r} has unexpected probe fields"
            )
        agents[agent_id] = {
            field: entry[field]
            for field in ("disable", "model", "variant")
            if field in entry
        }
    return json.dumps(content, ensure_ascii=False, separators=(",", ":"))


def _render_yaml_key(value: str) -> str:
    return value if YAML_KEY.fullmatch(value) else json.dumps(value, ensure_ascii=False)


def rewrite_agent_permissions(path: Path, reset_keys: Sequence[str]) -> None:
    """Replace a staged agent policy with per-key scalar resets.

    The target has already been manifest-verified before this function runs.
    Resetting each key to a scalar is necessary because OpenCode deep-merges
    nested permission maps.  The final maps are supplied in config content.
    """

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PermissionCompositionError(f"could not read staged agent {path}: {exc}") from exc
    start = text.find("\npermission:\n")
    end = text.find("\n---\n", start + 1)
    if start < 0 or end < 0:
        raise PermissionCompositionError(f"staged agent has non-canonical frontmatter: {path}")
    keys = tuple(dict.fromkeys(reset_keys))
    if not keys:
        raise PermissionCompositionError(f"staged agent reset has no keys: {path}")
    block = "\npermission:\n" + "".join(
        f"  {_render_yaml_key(key)}: deny\n" for key in keys
    )
    rendered = text[:start] + block + text[end:]
    try:
        path.write_text(rendered, encoding="utf-8")
    except OSError as exc:
        raise PermissionCompositionError(f"could not rewrite staged agent {path}: {exc}") from exc


def rewrite_staged_agents(config_dir: Path, policy: ComposedPolicy) -> None:
    for agent_id, keys in policy.reset_keys.items():
        rewrite_agent_permissions(config_dir / "agents" / f"{agent_id}.md", keys)


def wildcard_match(value: str, pattern: str, *, case_insensitive: bool = False) -> bool:
    """Match OpenCode v1's reviewed ``Wildcard.match`` semantics."""

    normalized = value.replace("\\", "/")
    normalized_pattern = pattern.replace("\\", "/")
    escaped = "".join(
        ".*"
        if character == "*"
        else "."
        if character == "?"
        else "\\" + character
        if character in ".+^${}()|[]\\"
        else character
        for character in normalized_pattern
    )
    if escaped.endswith(" .*"):
        escaped = escaped[:-3] + r"(?: .*)?"
    flags = re.DOTALL | (re.IGNORECASE if case_insensitive else 0)
    return re.fullmatch(escaped, normalized, flags=flags) is not None


def evaluate_rules(rules: Sequence[Mapping[str, Any]], permission: str, pattern: str) -> str:
    action = "ask"
    for rule in rules:
        rule_permission = rule.get("permission")
        rule_pattern = rule.get("pattern")
        rule_action = rule.get("action")
        if not all(isinstance(item, str) for item in (rule_permission, rule_pattern, rule_action)):
            raise PermissionCompositionError("resolved agent contains a malformed permission rule")
        if rule_action not in PERMISSION_ACTIONS:
            raise PermissionCompositionError("resolved agent contains an unsupported permission action")
        if wildcard_match(permission, rule_permission) and wildcard_match(pattern, rule_pattern):
            action = rule_action
    return action


def _rules_from_permission(permission: PermissionMap) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for key, rule in permission.items():
        if isinstance(rule, str):
            result.append({"permission": key, "pattern": "*", "action": rule})
        else:
            result.extend(
                {"permission": key, "pattern": pattern, "action": action}
                for pattern, action in rule.items()
            )
    return result


def _probe_value(pattern: str) -> str:
    value = pattern.replace("\\", "/")
    value = value.replace("*", "grillmester-probe").replace("?", "x")
    return value or "grillmester-probe"


def _validated_ordered_rules(
    raw_rules: object, *, agent_id: str
) -> list[dict[str, str]]:
    """Validate the exact ordered-rule schema returned by pinned OpenCode."""

    if not isinstance(raw_rules, list) or not raw_rules:
        raise PermissionCompositionError(
            f"resolved agent {agent_id!r} has no ordered rules"
        )
    rules: list[dict[str, str]] = []
    for raw in raw_rules:
        if (
            not isinstance(raw, dict)
            or set(raw) != {"permission", "pattern", "action"}
            or not isinstance(raw.get("permission"), str)
            or not raw["permission"]
            or not isinstance(raw.get("pattern"), str)
            or not raw["pattern"]
            or not isinstance(raw.get("action"), str)
            or raw.get("action") not in PERMISSION_ACTIONS
        ):
            raise PermissionCompositionError(
                f"resolved agent {agent_id!r} has malformed rules"
            )
        rules.append(
            {
                "permission": raw["permission"],
                "pattern": raw["pattern"],
                "action": raw["action"],
            }
        )
    return rules


def _split_managed_tool_output_rule(
    rules: Sequence[dict[str, str]],
    expected_pattern: str,
) -> tuple[list[dict[str, str]], bool]:
    """Remove the exact pinned-client tool-output exception."""

    if not rules:
        return [], False
    last = rules[-1]
    expected = expected_pattern
    prefix = expected.removesuffix("/tool-output/*")
    if (
        expected == prefix
        or not prefix.startswith("/")
        or "\\" in expected
        or any(character in prefix for character in "*?[")
        or any(segment in {"", ".", ".."} for segment in prefix.split("/")[1:])
    ):
        raise PermissionCompositionError(
            "expected OpenCode tool-output permission has an unsafe path"
        )
    if not (
        last["permission"] == "external_directory"
        and last["action"] == "allow"
        and last["pattern"] == expected
    ):
        return list(rules), False
    return list(rules[:-1]), True


def _normalize_cplt_scratch_pattern(pattern: str) -> str:
    """Normalize only cplt's per-probe 32-hex scratch-session component."""

    if "\\" in pattern:
        return pattern
    match = re.fullmatch(
        r"(?P<base>/.+/(?:Library/Caches|\.cache)/cplt/tmp/)"
        r"[0-9a-f]{32}(?P<tail>/opencode/\*)",
        pattern,
    )
    if match is None:
        return pattern
    base = match.group("base")
    if any(
        segment in {"", ".", ".."}
        or any(character in segment for character in "*?[")
        for segment in base.split("/")[1:-1]
    ):
        raise PermissionCompositionError("resolved cplt scratch permission is unsafe")
    return f"{base}<managed-cplt-session>{match.group('tail')}"


def _canonicalize_external_allow_runs(
    rules: Sequence[dict[str, str]],
) -> list[dict[str, str]]:
    """Sort only adjacent ``external_directory`` allow rules.

    These equal-action rules commute under OpenCode's last-match evaluator.
    Deny order remains significant to its separate tool-visibility check and
    is never canonicalized.
    """

    canonical: list[dict[str, str]] = []
    start = 0
    while start < len(rules):
        key = (rules[start]["permission"], rules[start]["action"])
        end = start + 1
        while end < len(rules) and (
            rules[end]["permission"], rules[end]["action"]
        ) == key:
            end += 1
        run = [dict(rule) for rule in rules[start:end]]
        if key == ("external_directory", "allow"):
            for rule in run:
                rule["pattern"] = _normalize_cplt_scratch_pattern(rule["pattern"])
            run.sort(key=lambda rule: rule["pattern"])
        canonical.extend(run)
        start = end
    return canonical


def _canonical_resolved_agent(
    resolved_agent: Mapping[str, Any],
    prefix: Sequence[dict[str, str]],
    exact_suffix: Sequence[dict[str, str]],
    expected_tool_output_pattern: str,
) -> str:
    normalized = dict(resolved_agent)
    normalized_rules = [
        *_canonicalize_external_allow_runs(prefix),
        *(dict(rule) for rule in exact_suffix),
        {
            "permission": "external_directory",
            "pattern": expected_tool_output_pattern,
            "action": "allow",
        },
    ]
    normalized["permission"] = normalized_rules
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def validate_effective_agent(
    agent_id: str,
    resolved_agent: Mapping[str, Any],
    intended: PermissionMap,
    expected_contract: Mapping[str, Any],
    expected_tool_output_pattern: str,
) -> str:
    """Prove key policy decisions against ``debug agent`` ordered output.

    Returns a SHA-256-ready canonical JSON string used by the manager's
    same-stage TOCTOU check.
    """

    import hashlib

    if resolved_agent.get("name") != agent_id:
        raise PermissionCompositionError(f"resolved agent name mismatch for {agent_id!r}")
    for field in ("description", "mode", "hidden", "prompt", "model", "variant"):
        if resolved_agent.get(field) != expected_contract.get(field):
            raise PermissionCompositionError(
                f"resolved agent {agent_id!r} changed generated {field}"
            )
    if resolved_agent.get("native") not in (None, False):
        raise PermissionCompositionError(
            f"resolved agent {agent_id!r} has an external native override"
        )
    for field in ("color", "steps"):
        if resolved_agent.get(field) is not None:
            raise PermissionCompositionError(
                f"resolved agent {agent_id!r} has an external {field} override"
            )
    rules = _validated_ordered_rules(
        resolved_agent.get("permission"), agent_id=agent_id
    )

    intended_rules = [
        {"permission": "*", "pattern": "*", "action": NORMAL_FALLBACK},
        *_rules_from_permission(intended),
    ]
    expected_agent_rules = _rules_from_permission(intended)
    observed_core, has_tool_output_rule = _split_managed_tool_output_rule(
        rules, expected_tool_output_pattern
    )
    if not has_tool_output_rule:
        raise PermissionCompositionError(
            f"resolved agent {agent_id!r} lacks the exact managed tool-output rule"
        )
    if (
        len(observed_core) < len(expected_agent_rules)
        or observed_core[-len(expected_agent_rules) :] != expected_agent_rules
    ):
        raise PermissionCompositionError(
            f"resolved agent {agent_id!r} does not end with the exact composed rule map"
        )

    suffix_start = len(observed_core) - len(expected_agent_rules)
    prefix = observed_core[:suffix_start]
    intended_wildcards = {
        rule["permission"]
        for rule in expected_agent_rules
        if rule["pattern"] == "*"
    }
    for index, rule in enumerate(prefix):
        if rule.get("action") != "allow":
            continue
        permission_pattern = rule.get("permission")
        if permission_pattern == "*":
            if not any(
                later.get("permission") == "*"
                and later.get("pattern") == "*"
                and later.get("action") in {"ask", "deny"}
                for later in observed_core[index + 1 :]
            ):
                raise PermissionCompositionError(
                    f"resolved agent {agent_id!r} has an unbounded earlier allow"
                )
            continue
        if permission_pattern not in intended_wildcards:
            raise PermissionCompositionError(
                f"resolved agent {agent_id!r} has unexpected allow rule "
                f"{permission_pattern!r}"
            )
    probes: set[tuple[str, str]] = {
        ("grillmester_unknown_tool", "*"),
        ("read", "README.md"),
        ("read", ".env"),
        ("read", ".env.local"),
        ("read", ".env.example"),
    }
    for rule in intended_rules:
        probes.add((_probe_value(rule["permission"]), _probe_value(rule["pattern"])))

    failures: list[str] = []
    for permission, pattern in sorted(probes):
        expected = evaluate_rules(intended_rules, permission, pattern)
        observed = evaluate_rules(rules, permission, pattern)
        if observed != expected:
            failures.append(f"{permission}:{pattern} expected {expected}, observed {observed}")
    if failures:
        raise PermissionCompositionError(
            f"resolved agent {agent_id!r} does not preserve composed policy: "
            + "; ".join(failures[:8])
        )

    canonical = _canonical_resolved_agent(
        resolved_agent,
        prefix,
        observed_core[suffix_start:],
        expected_tool_output_pattern,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_hidden_native_agent(
    agent_id: str,
    resolved_agent: Mapping[str, Any],
    expected_tool_output_pattern: str,
) -> str:
    """Prove required OpenCode housekeeping agents remain hidden and terminally denied."""

    import hashlib

    if agent_id not in HIDDEN_NATIVE_AGENTS:
        raise PermissionCompositionError(f"unexpected hidden native agent {agent_id!r}")
    if (
        resolved_agent.get("name") != agent_id
        or resolved_agent.get("native") is not True
        or resolved_agent.get("hidden") is not True
    ):
        raise PermissionCompositionError(
            f"hidden native OpenCode agent {agent_id!r} changed identity or visibility"
        )
    tools = resolved_agent.get("tools")
    if tools not in (None, {}) and (
        not isinstance(tools, dict)
        or any(value is not False for value in tools.values())
    ):
        raise PermissionCompositionError(
            f"hidden native OpenCode agent {agent_id!r} enables tools"
        )
    rules = _validated_ordered_rules(
        resolved_agent.get("permission"), agent_id=agent_id
    )
    observed_core, has_tool_output_rule = _split_managed_tool_output_rule(
        rules, expected_tool_output_pattern
    )
    if not has_tool_output_rule:
        raise PermissionCompositionError(
            f"hidden native OpenCode agent {agent_id!r} lacks the exact managed "
            "tool-output rule"
        )
    if not observed_core or observed_core[-1] != {
        "permission": "*",
        "pattern": "*",
        "action": "deny",
    }:
        raise PermissionCompositionError(
            f"hidden native OpenCode agent {agent_id!r} is not terminally denied"
        )
    if evaluate_rules(rules, "grillmester_unknown_tool", "*") != "deny":
        raise PermissionCompositionError(
            f"hidden native OpenCode agent {agent_id!r} is not terminally denied"
        )
    canonical = _canonical_resolved_agent(
        resolved_agent,
        observed_core[:-1],
        observed_core[-1:],
        expected_tool_output_pattern,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_target_agent_ids(
    resolved_config: Mapping[str, Any],
    expected_agents: Mapping[str, object],
    expected_contracts: Mapping[str, Mapping[str, Any]],
    runtime_agent: str,
) -> str:
    """Require only the selected primary and generated subagents to be enabled."""

    import hashlib

    raw_agents = resolved_config.get("agent")
    if not isinstance(raw_agents, dict):
        raise PermissionCompositionError("resolved OpenCode config has no agent map")
    expected = set(expected_agents) | set(DISABLED_NATIVE_AGENTS) | set(HIDDEN_NATIVE_AGENTS)
    observed = set(raw_agents)
    unexpected = sorted(observed - expected)
    missing = sorted(expected - observed)
    if unexpected:
        raise PermissionCompositionError("resolved OpenCode config contains unexpected agents")
    if missing:
        raise PermissionCompositionError(
            "resolved OpenCode config omits generated agents: " + ", ".join(missing)
        )
    for agent_id in DISABLED_NATIVE_AGENTS:
        entry = raw_agents[agent_id]
        if not isinstance(entry, dict) or entry.get("disable") is not True:
            raise PermissionCompositionError(
                f"native OpenCode agent {agent_id!r} is not disabled"
            )
    for agent_id in HIDDEN_NATIVE_AGENTS:
        entry = raw_agents[agent_id]
        permission = entry.get("permission") if isinstance(entry, dict) else None
        if not isinstance(permission, dict) or permission.get("*") != "deny":
            raise PermissionCompositionError(
                f"hidden native OpenCode agent {agent_id!r} lacks terminal deny"
            )
    for agent_id, contract in expected_contracts.items():
        entry = raw_agents[agent_id]
        if not isinstance(entry, dict):
            raise PermissionCompositionError(
                f"resolved generated agent {agent_id!r} must be an object"
            )
        should_disable = contract.get("mode") == "primary" and agent_id != runtime_agent
        if entry.get("disable") is not (True if should_disable else None):
            raise PermissionCompositionError(
                f"resolved generated agent {agent_id!r} has unsafe selectability"
            )
        for field in ("model", "variant"):
            if entry.get(field) != contract.get(field):
                raise PermissionCompositionError(
                    f"resolved generated agent {agent_id!r} changed {field}"
                )
    canonical = json.dumps(raw_agents, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_target_commands(
    resolved_config: Mapping[str, Any],
    expected_commands: Mapping[str, Mapping[str, Any]],
) -> str:
    """Prove that post-content managed config did not replace target commands."""

    import hashlib

    raw_commands = resolved_config.get("command")
    if not isinstance(raw_commands, dict):
        raise PermissionCompositionError("resolved OpenCode config has no command map")
    unexpected = sorted(set(raw_commands) - set(expected_commands))
    if unexpected:
        raise PermissionCompositionError("resolved OpenCode config contains unexpected commands")
    for command_id, expected in expected_commands.items():
        actual = raw_commands.get(command_id)
        if not isinstance(actual, dict) or actual != expected:
            raise PermissionCompositionError(
                f"resolved OpenCode command {command_id!r} does not match the generated target"
            )
    canonical = json.dumps(
        {key: raw_commands[key] for key in sorted(expected_commands)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_provider_contract(
    resolved_config: Mapping[str, Any], expected: Mapping[str, Any]
) -> str:
    """Prove late managed/MDM config did not widen selected providers."""

    import hashlib

    providers = resolved_config.get("provider")
    if providers is None:
        providers = {}
    if providers != expected:
        raise PermissionCompositionError(
            "final resolved provider map differs from the exact selected provider set"
        )
    enabled = resolved_config.get("enabled_providers")
    if enabled != sorted(expected):
        raise PermissionCompositionError(
            "final enabled_providers differs from the exact selected provider IDs"
        )
    if resolved_config.get("disabled_providers") not in (None, []):
        raise PermissionCompositionError(
            "final disabled_providers must be absent or empty in managed mode"
        )
    canonical = json.dumps(
        {
            "provider": providers,
            "enabled_providers": enabled,
            "disabled_providers": resolved_config.get("disabled_providers", []),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_skill_origins(skills: object, config_dir: Path) -> str:
    """Validate the exact projected skill roster and every target origin."""

    import hashlib

    if not isinstance(skills, list):
        raise PermissionCompositionError("OpenCode debug skill output must be an array")
    expected_paths = {
        skill_id: Path(pattern.removesuffix("/*")) / "SKILL.md"
        for skill_id, pattern in _target_skills(config_dir)
    }
    expected_descriptions: dict[str, str] = {}
    for skill_id, path in expected_paths.items():
        fields, _body = _parse_frontmatter_document(path)
        if fields.get("name") != skill_id or not isinstance(
            fields.get("description"), str
        ):
            raise PermissionCompositionError(
                f"projected target skill {skill_id!r} changed frontmatter identity"
            )
        expected_descriptions[skill_id] = fields["description"]
    expected_ids = {*expected_paths, PINNED_BUILTIN_SKILL_ID}
    observed: dict[str, Mapping[str, Any]] = {}
    for raw in skills:
        if not isinstance(raw, dict):
            raise PermissionCompositionError("OpenCode debug skill entry must be an object")
        name = raw.get("name")
        location = raw.get("location")
        description = raw.get("description")
        content = raw.get("content")
        if (
            set(raw) != {"name", "description", "location", "content"}
            or not isinstance(name, str)
            or not isinstance(location, str)
            or not isinstance(description, str)
            or not isinstance(content, str)
        ):
            raise PermissionCompositionError(
                "OpenCode debug skill entry has an unexpected schema"
            )
        if name not in expected_ids:
            raise PermissionCompositionError(
                "OpenCode resolved an unexpected skill in managed mode"
            )
        if name in observed:
            raise PermissionCompositionError(f"OpenCode resolved duplicate target skill {name!r}")
        observed[name] = raw
    missing = sorted(expected_ids - set(observed))
    if missing:
        raise PermissionCompositionError(
            "OpenCode did not resolve the exact managed skill roster: "
            + ", ".join(missing)
        )
    builtin = observed[PINNED_BUILTIN_SKILL_ID]
    if (
        builtin["location"] != PINNED_BUILTIN_SKILL_LOCATION
        or not builtin["description"]
        or not builtin["content"]
    ):
        raise PermissionCompositionError(
            "pinned OpenCode built-in skill changed identity or origin"
        )
    for name, expected_path in expected_paths.items():
        raw = observed[name]
        try:
            actual = Path(raw["location"]).resolve(strict=True)
            wanted = expected_path.resolve(strict=True)
        except OSError as exc:
            raise PermissionCompositionError(
                f"OpenCode target skill {name!r} has an unreadable origin"
            ) from exc
        if actual != wanted:
            raise PermissionCompositionError(
                f"OpenCode target skill {name!r} is shadowed by {actual}"
            )
        if raw["description"] != expected_descriptions[name]:
            raise PermissionCompositionError(
                f"OpenCode target skill {name!r} changed description"
            )
        expected_content = f"{OPENCODE_SKILL_PROBE_MARKER} for {name}.\n"
        if raw["content"] != expected_content:
            raise PermissionCompositionError(
                f"OpenCode target skill {name!r} changed projected content"
            )
    canonical = json.dumps(
        sorted(skills, key=lambda entry: (entry["name"], entry["location"])),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
