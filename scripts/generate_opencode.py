#!/usr/bin/env python3
"""Generate the native OpenCode v1 target from canonical Grillmester sources."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = Path("policy/opencode-v1.json")
TARGET_ID = "opencode-v1"
GENERATOR_VERSION = 1
COMPONENT_ID = re.compile(r"^[a-z][a-z0-9-]*$")
QUALIFIED_AGENT_ID = re.compile(r"(?<![a-z0-9-])grillmester:([a-z][a-z0-9-]*)")
SLASH_SKILL_REFERENCE = re.compile(r"`?/((?:grillmester)-[a-z0-9-]+)\b`?")
ALLOWED_ACTIONS = {"allow", "ask", "deny"}
ALLOWED_CAPABILITIES = {"native", "overlay", "degraded", "unsupported"}
ALLOWED_SKILL_ACCESS = {"allow-with-manual-ask", "deny"}
TARGET_GITIGNORE = """# OpenCode may bootstrap runtime dependencies in this config directory.
node_modules/
package.json
bun.lock
bun.lockb
"""
TARGET_CONFIG = {"$schema": "https://opencode.ai/config.json"}
RUNTIME_ARTIFACT_FILES = {"package.json", "bun.lock", "bun.lockb"}
RUNTIME_ARTIFACT_DIRECTORIES = {"node_modules"}
TARGET_INVOCATION_NOTE = (
    "> **OpenCode v1:** Backticked `grillmester-*` names below are skill IDs, "
    "not slash commands. Load them with the native `skill` tool. Slash commands "
    "are direct user entry points only."
)


class ProjectionError(ValueError):
    """Raised when canonical sources cannot produce a safe native target."""


GeneratedFile = tuple[bytes, int]


def load_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProjectionError(f"{label} does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ProjectionError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ProjectionError(f"{label} must contain a JSON object")
    return value


def relative_path(value: Any, *, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ProjectionError(f"{label} must be a non-empty repository-relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ProjectionError(f"{label} must be a normalized repository-relative path")
    return path


def split_frontmatter(text: str, *, path: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise ProjectionError(f"{path} must start with YAML frontmatter")
    closing = text.find("\n---\n", 4)
    if closing < 0:
        raise ProjectionError(f"{path} has unterminated YAML frontmatter")
    block = text[4:closing]
    body = text[closing + len("\n---\n") :]
    values: dict[str, Any] = {}
    for number, line in enumerate(block.splitlines(), start=2):
        if not line or line[0].isspace() or line.startswith("-"):
            continue
        if ":" not in line:
            raise ProjectionError(f"{path}:{number} is not a frontmatter field")
        key, raw = line.split(":", 1)
        raw = raw.strip()
        if key in values:
            raise ProjectionError(f"{path} repeats frontmatter field {key!r}")
        if not raw:
            values[key] = None
        elif raw.startswith('"'):
            try:
                values[key] = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ProjectionError(
                    f"{path}:{number} has an invalid quoted value: {exc}"
                ) from exc
        elif raw == "true":
            values[key] = True
        elif raw == "false":
            values[key] = False
        else:
            values[key] = raw
    return values, body


def required_component(frontmatter: Mapping[str, Any], *, path: str) -> tuple[str, str]:
    name = frontmatter.get("name")
    description = frontmatter.get("description")
    if not isinstance(name, str) or not COMPONENT_ID.fullmatch(name):
        raise ProjectionError(f"{path} needs a valid kebab-case name")
    if not isinstance(description, str) or not description.strip():
        raise ProjectionError(f"{path} needs a non-empty description")
    return name, description.strip()


def validate_action(value: Any, *, label: str) -> None:
    if isinstance(value, str):
        if value not in ALLOWED_ACTIONS:
            raise ProjectionError(f"{label} has unsupported action {value!r}")
        return
    if not isinstance(value, dict) or not value:
        raise ProjectionError(f"{label} must be an action or non-empty pattern map")
    for pattern, action in value.items():
        if not isinstance(pattern, str) or not pattern:
            raise ProjectionError(f"{label} contains an invalid pattern")
        validate_action(action, label=f"{label}.{pattern}")


def load_policy(root: Path, policy_path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    resolved = policy_path if policy_path.is_absolute() else root / policy_path
    policy = load_object(resolved, label="OpenCode target policy")
    if policy.get("schemaVersion") != 1 or policy.get("target") != TARGET_ID:
        raise ProjectionError("OpenCode target policy must declare schemaVersion 1 and opencode-v1")
    output = relative_path(policy.get("output"), label="policy output")
    if output.parts != ("targets", TARGET_ID):
        raise ProjectionError(f"policy output must be targets/{TARGET_ID}")
    source = policy.get("source")
    if not isinstance(source, dict) or set(source) != {
        "pluginManifest",
        "agents",
        "skills",
    }:
        raise ProjectionError("policy source must name pluginManifest, agents, and skills")
    for key, value in source.items():
        relative_path(value, label=f"policy source.{key}")

    agents = policy.get("agents")
    if not isinstance(agents, dict) or not agents:
        raise ProjectionError("policy agents must be a non-empty object")
    for agent_id, config in agents.items():
        if not COMPONENT_ID.fullmatch(agent_id) or not isinstance(config, dict):
            raise ProjectionError(f"policy agent {agent_id!r} is invalid")
        if set(config) != {"mode", "hidden", "skillAccess", "permission"}:
            raise ProjectionError(
                f"policy agent {agent_id} must define mode, hidden, skillAccess, and permission"
            )
        if config["mode"] not in {"primary", "subagent"}:
            raise ProjectionError(f"policy agent {agent_id} has invalid mode")
        if not isinstance(config["hidden"], bool):
            raise ProjectionError(f"policy agent {agent_id} hidden must be boolean")
        if config["mode"] == "primary" and config["hidden"]:
            raise ProjectionError(f"primary policy agent {agent_id} cannot be hidden")
        if config["skillAccess"] not in ALLOWED_SKILL_ACCESS:
            raise ProjectionError(f"policy agent {agent_id} has invalid skillAccess")
        permissions = config["permission"]
        if not isinstance(permissions, dict) or not permissions:
            raise ProjectionError(f"policy agent {agent_id} needs permissions")
        if "model" in permissions:
            raise ProjectionError(f"policy agent {agent_id} must not pin a model")
        for tool, action in permissions.items():
            if not isinstance(tool, str) or not tool:
                raise ProjectionError(f"policy agent {agent_id} has an invalid tool key")
            validate_action(action, label=f"policy agent {agent_id} permission.{tool}")

    for key in ("runtimeTextReplacements", "remove", "forbiddenRuntimeTokens"):
        if not isinstance(policy.get(key), list):
            raise ProjectionError(f"policy {key} must be a list")
    for replacement in policy["runtimeTextReplacements"]:
        validate_replacement(replacement, label="runtimeTextReplacements")
    path_replacements = policy.get("pathTextReplacements")
    if not isinstance(path_replacements, dict):
        raise ProjectionError("policy pathTextReplacements must be an object")
    for target, replacements in path_replacements.items():
        relative_path(target, label="pathTextReplacements target")
        if not isinstance(replacements, list) or not replacements:
            raise ProjectionError(f"pathTextReplacements {target} must be a non-empty list")
        for replacement in replacements:
            validate_replacement(replacement, label=f"pathTextReplacements {target}")

    overlays = policy.get("overlays")
    if not isinstance(overlays, dict):
        raise ProjectionError("policy overlays must be an object")
    for target, source_path in overlays.items():
        relative_path(target, label="overlay target")
        relative_path(source_path, label="overlay source")
    for target in policy["remove"]:
        relative_path(target, label="remove target")

    capabilities = policy.get("skillCapabilities")
    if not isinstance(capabilities, dict) or set(capabilities) != {"default", "overrides"}:
        raise ProjectionError("skillCapabilities must define default and overrides")
    if capabilities["default"] not in ALLOWED_CAPABILITIES:
        raise ProjectionError("skillCapabilities default is invalid")
    if not isinstance(capabilities["overrides"], dict):
        raise ProjectionError("skillCapabilities overrides must be an object")
    for skill_id, capability in capabilities["overrides"].items():
        if not COMPONENT_ID.fullmatch(skill_id) or capability not in ALLOWED_CAPABILITIES:
            raise ProjectionError(f"invalid skill capability for {skill_id!r}")

    forbidden_by_prefix = policy.get("forbiddenByPrefix")
    if not isinstance(forbidden_by_prefix, dict):
        raise ProjectionError("forbiddenByPrefix must be an object")
    for prefix, tokens in forbidden_by_prefix.items():
        relative_path(prefix.rstrip("/"), label="forbiddenByPrefix path")
        if not isinstance(tokens, list) or not all(
            isinstance(token, str) and token for token in tokens
        ):
            raise ProjectionError(f"forbiddenByPrefix {prefix} must list tokens")
    return policy


def validate_replacement(value: Any, *, label: str) -> None:
    if not isinstance(value, dict) or set(value) != {"from", "to"}:
        raise ProjectionError(f"{label} entries must contain from and to")
    if not isinstance(value["from"], str) or not value["from"]:
        raise ProjectionError(f"{label} replacement source must be non-empty")
    if not isinstance(value["to"], str):
        raise ProjectionError(f"{label} replacement target must be text")


def add_file(
    files: dict[str, GeneratedFile],
    casefolded: dict[str, str],
    relative: str,
    data: bytes,
    *,
    executable: bool = False,
) -> None:
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts or str(posix) != relative:
        raise ProjectionError(f"generated path is unsafe: {relative!r}")
    folded = relative.casefold()
    previous = casefolded.get(folded)
    if previous is not None:
        raise ProjectionError(f"generated path collision: {previous!r} and {relative!r}")
    casefolded[folded] = relative
    files[relative] = (data, 0o755 if executable else 0o644)


def apply_text_adapter(
    text: str,
    *,
    target_path: str,
    policy: Mapping[str, Any],
    agent_ids: set[str],
    replacement_hits: dict[str, int],
    check_prefix_residue: bool = True,
) -> str:
    def replace_qualified(match: re.Match[str]) -> str:
        agent_id = match.group(1)
        if agent_id not in agent_ids:
            raise ProjectionError(
                f"{target_path} references unknown qualified agent {match.group(0)!r}"
            )
        replacement_hits["qualified-agent"] = replacement_hits.get("qualified-agent", 0) + 1
        return agent_id

    adapted = QUALIFIED_AGENT_ID.sub(replace_qualified, text)
    for index, replacement in enumerate(policy["runtimeTextReplacements"]):
        source = replacement["from"]
        count = adapted.count(source)
        if count:
            adapted = adapted.replace(source, replacement["to"])
            key = f"runtime:{index}:{source}"
            replacement_hits[key] = replacement_hits.get(key, 0) + count

    for index, replacement in enumerate(policy["pathTextReplacements"].get(target_path, [])):
        source = replacement["from"]
        count = adapted.count(source)
        if count:
            adapted = adapted.replace(source, replacement["to"])
            key = f"path:{target_path}:{index}"
            replacement_hits[key] = replacement_hits.get(key, 0) + count

    def replace_slash_skill(match: re.Match[str]) -> str:
        skill_id = match.group(1)
        replacement_hits["slash-skill"] = replacement_hits.get("slash-skill", 0) + 1
        return f"`{skill_id}`"

    adapted = SLASH_SKILL_REFERENCE.sub(replace_slash_skill, adapted)

    residue = QUALIFIED_AGENT_ID.search(adapted)
    if residue:
        raise ProjectionError(f"{target_path} retains qualified agent ID {residue.group(0)!r}")
    slash_residue = SLASH_SKILL_REFERENCE.search(adapted)
    if slash_residue:
        raise ProjectionError(
            f"{target_path} retains internal slash skill reference {slash_residue.group(0)!r}"
        )
    for token in policy["forbiddenRuntimeTokens"]:
        if token in adapted:
            raise ProjectionError(f"{target_path} retains target-specific token {token!r}")
    for prefix, tokens in policy["forbiddenByPrefix"].items():
        if check_prefix_residue and target_path.startswith(prefix):
            for token in tokens:
                if token in adapted:
                    raise ProjectionError(f"{target_path} retains forbidden token {token!r}")
    return adapted


def render_yaml_key(key: str) -> str:
    if COMPONENT_ID.fullmatch(key) or key in {
        "read",
        "edit",
        "glob",
        "grep",
        "list",
        "bash",
        "task",
        "lsp",
        "skill",
        "question",
        "webfetch",
        "websearch",
        "external_directory",
        "todowrite",
    }:
        return key
    return json.dumps(key, ensure_ascii=False)


def render_mapping(value: Mapping[str, Any], *, indent: int) -> list[str]:
    lines: list[str] = []
    padding = " " * indent
    for key, child in value.items():
        rendered_key = render_yaml_key(key)
        if isinstance(child, dict):
            lines.append(f"{padding}{rendered_key}:")
            lines.extend(render_mapping(child, indent=indent + 2))
        elif isinstance(child, str) and child in ALLOWED_ACTIONS:
            lines.append(f"{padding}{rendered_key}: {child}")
        else:
            raise ProjectionError(f"cannot render permission value for {key!r}")
    return lines


def permission_with_skill_policy(
    base: Mapping[str, Any], *, skill_access: str, manual_only: Sequence[str]
) -> dict[str, Any]:
    permissions: dict[str, Any] = {}
    inserted = False
    for tool, action in base.items():
        if tool == "task" and not inserted:
            permissions["skill"] = skill_permission(skill_access, manual_only)
            inserted = True
        permissions[tool] = action
    if not inserted:
        permissions["skill"] = skill_permission(skill_access, manual_only)
    return permissions


def skill_permission(skill_access: str, manual_only: Sequence[str]) -> Any:
    if skill_access == "deny":
        return "deny"
    rules: dict[str, str] = {"*": "allow"}
    for skill_id in sorted(manual_only):
        rules[skill_id] = "ask"
    if list(rules)[0] != "*":
        raise ProjectionError("manual-only skill policy must put the broad rule first")
    return rules


def render_agent(
    description: str,
    body: str,
    *,
    config: Mapping[str, Any],
    manual_only: Sequence[str],
) -> str:
    permissions = permission_with_skill_policy(
        config["permission"],
        skill_access=config["skillAccess"],
        manual_only=manual_only,
    )
    lines = [
        "---",
        f"description: {json.dumps(description, ensure_ascii=False)}",
        f"mode: {config['mode']}",
        f"hidden: {'true' if config['hidden'] else 'false'}",
        "permission:",
        *render_mapping(permissions, indent=2),
        "---",
    ]
    return "\n".join(lines) + "\n" + add_invocation_note(body).rstrip() + "\n"


def render_skill(name: str, description: str, body: str) -> str:
    return (
        "---\n"
        f"name: {name}\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        "---\n"
        + add_invocation_note(body).rstrip()
        + "\n"
    )


def add_invocation_note(body: str) -> str:
    stripped = body.lstrip("\n")
    if not stripped.startswith("# "):
        return TARGET_INVOCATION_NOTE + "\n\n" + stripped
    heading_end = stripped.find("\n")
    if heading_end < 0:
        return stripped + "\n\n" + TARGET_INVOCATION_NOTE + "\n"
    return (
        stripped[:heading_end]
        + "\n\n"
        + TARGET_INVOCATION_NOTE
        + "\n\n"
        + stripped[heading_end + 1 :].lstrip("\n")
    )


def render_command(name: str, description: str) -> str:
    return (
        "---\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        "---\n\n"
        f"Use the `skill` tool to load `{name}`, then follow that skill for this request.\n\n"
        "Treat the following as the user's arguments to the skill:\n\n"
        "$ARGUMENTS\n"
    )


def discover_source_skills(
    root: Path, source_dir: Path
) -> tuple[dict[str, tuple[Path, str]], list[str]]:
    skills: dict[str, tuple[Path, str]] = {}
    manual_only: list[str] = []
    if not source_dir.is_dir():
        raise ProjectionError(f"skill source directory does not exist: {source_dir}")
    for skill_dir in sorted(source_dir.iterdir(), key=lambda path: path.name):
        if skill_dir.is_symlink():
            raise ProjectionError(f"skill source must not be a symlink: {skill_dir}")
        if not skill_dir.is_dir():
            raise ProjectionError(f"unexpected entry in skill source: {skill_dir}")
        source_skill = skill_dir / "SKILL.md"
        frontmatter, _ = split_frontmatter(
            source_skill.read_text(encoding="utf-8"),
            path=source_skill.relative_to(root).as_posix(),
        )
        skill_id, description = required_component(
            frontmatter, path=source_skill.relative_to(root).as_posix()
        )
        if skill_id != skill_dir.name:
            raise ProjectionError(
                f"skill {source_skill} name {skill_id!r} must match its directory"
            )
        folded = skill_id.casefold()
        if any(existing.casefold() == folded for existing in skills):
            raise ProjectionError(f"case-insensitive skill ID collision: {skill_id}")
        skills[skill_id] = (skill_dir, description)
        if frontmatter.get("disable-model-invocation") is True:
            manual_only.append(skill_id)
    return skills, sorted(manual_only)


def source_files(skill_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(skill_dir.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise ProjectionError(f"skill trees must not contain symlinks: {path}")
        if path.is_file():
            files.append(path)
    return files


def capability_map(policy: Mapping[str, Any], skill_ids: set[str]) -> dict[str, str]:
    contract = policy["skillCapabilities"]
    overrides = contract["overrides"]
    unknown = set(overrides) - skill_ids
    if unknown:
        raise ProjectionError(f"skillCapabilities names unknown skills: {sorted(unknown)}")
    capabilities = {
        skill_id: overrides.get(skill_id, contract["default"])
        for skill_id in sorted(skill_ids)
    }
    unsupported = [
        skill_id for skill_id, capability in capabilities.items() if capability == "unsupported"
    ]
    if unsupported:
        raise ProjectionError(f"OpenCode target has unsupported skills: {unsupported}")
    overlay_skills = {
        PurePosixPath(target).parts[1]
        for target in policy["overlays"]
        if PurePosixPath(target).parts[:1] == ("skills",)
    }
    classified_overlays = {
        skill_id for skill_id, capability in capabilities.items() if capability == "overlay"
    }
    if overlay_skills != classified_overlays:
        raise ProjectionError(
            "overlay skill classification must exactly match target-owned skill overlays"
        )
    return capabilities


def build_projection(
    root: Path = ROOT, policy_path: Path = DEFAULT_POLICY
) -> tuple[dict[str, GeneratedFile], dict[str, Any]]:
    root = root.resolve()
    policy = load_policy(root, policy_path)
    source = policy["source"]
    plugin_manifest_path = root / relative_path(
        source["pluginManifest"], label="plugin manifest source"
    )
    plugin_manifest = load_object(plugin_manifest_path, label="plugin manifest")
    agents_dir = root / relative_path(source["agents"], label="agent source")
    skills_dir = root / relative_path(source["skills"], label="skill source")
    skills, manual_only = discover_source_skills(root, skills_dir)
    capabilities = capability_map(policy, set(skills))

    agent_sources = sorted(agents_dir.glob("*.agent.md"), key=lambda path: path.name)
    if not agent_sources:
        raise ProjectionError(f"agent source directory contains no agents: {agents_dir}")
    source_agent_ids: set[str] = set()
    parsed_agents: list[tuple[str, str, str, Path]] = []
    for source_agent in agent_sources:
        frontmatter, body = split_frontmatter(
            source_agent.read_text(encoding="utf-8"),
            path=source_agent.relative_to(root).as_posix(),
        )
        agent_id, description = required_component(
            frontmatter, path=source_agent.relative_to(root).as_posix()
        )
        expected_filename = f"{agent_id}.agent.md"
        if source_agent.name != expected_filename:
            raise ProjectionError(
                f"agent {source_agent} name {agent_id!r} must match {expected_filename}"
            )
        if agent_id.casefold() in {item.casefold() for item in source_agent_ids}:
            raise ProjectionError(f"case-insensitive agent ID collision: {agent_id}")
        source_agent_ids.add(agent_id)
        parsed_agents.append((agent_id, description, body, source_agent))
    if source_agent_ids != set(policy["agents"]):
        raise ProjectionError(
            "policy agent IDs must exactly match canonical source agents: "
            f"source={sorted(source_agent_ids)}, policy={sorted(policy['agents'])}"
        )

    for agent_id, config in policy["agents"].items():
        task = config["permission"].get("task")
        if isinstance(task, dict):
            if list(task)[0] != "*":
                raise ProjectionError(f"agent {agent_id} task wildcard must be first")
            unknown = {
                pattern
                for pattern in task
                if pattern != "*" and pattern not in source_agent_ids
            }
            if unknown:
                raise ProjectionError(f"agent {agent_id} task policy names unknown agents")

    files: dict[str, GeneratedFile] = {}
    casefolded: dict[str, str] = {}
    replacement_hits: dict[str, int] = {}
    add_file(files, casefolded, ".gitignore", TARGET_GITIGNORE.encode("utf-8"))
    add_file(
        files,
        casefolded,
        "opencode.json",
        (json.dumps(TARGET_CONFIG, indent=2) + "\n").encode("utf-8"),
    )

    for agent_id, description, body, _ in parsed_agents:
        target = f"agents/{agent_id}.md"
        adapted_description = apply_text_adapter(
            description,
            target_path=target,
            policy=policy,
            agent_ids=source_agent_ids,
            replacement_hits=replacement_hits,
        )
        adapted_body = apply_text_adapter(
            body,
            target_path=target,
            policy=policy,
            agent_ids=source_agent_ids,
            replacement_hits=replacement_hits,
        )
        rendered = render_agent(
            adapted_description,
            adapted_body,
            config=policy["agents"][agent_id],
            manual_only=manual_only,
        )
        if re.search(r"(?m)^model\s*:", rendered):
            raise ProjectionError(f"generated agent {agent_id} unexpectedly pins a model")
        add_file(files, casefolded, target, rendered.encode("utf-8"))

    for skill_id, (skill_dir, _) in skills.items():
        for source_file in source_files(skill_dir):
            relative_in_skill = source_file.relative_to(skill_dir).as_posix()
            target = f"skills/{skill_id}/{relative_in_skill}"
            executable = bool(source_file.stat().st_mode & 0o111)
            if source_file.suffix.lower() == ".md":
                text = source_file.read_text(encoding="utf-8")
                check_prefix_residue = (
                    target not in policy["overlays"] and target not in policy["remove"]
                )
                if relative_in_skill == "SKILL.md":
                    frontmatter, body = split_frontmatter(
                        text, path=source_file.relative_to(root).as_posix()
                    )
                    name, description = required_component(
                        frontmatter, path=source_file.relative_to(root).as_posix()
                    )
                    adapted_description = apply_text_adapter(
                        description,
                        target_path=target,
                        policy=policy,
                        agent_ids=source_agent_ids,
                        replacement_hits=replacement_hits,
                        check_prefix_residue=check_prefix_residue,
                    )
                    adapted_body = apply_text_adapter(
                        body,
                        target_path=target,
                        policy=policy,
                        agent_ids=source_agent_ids,
                        replacement_hits=replacement_hits,
                        check_prefix_residue=check_prefix_residue,
                    )
                    data = render_skill(name, adapted_description, adapted_body).encode("utf-8")
                else:
                    adapted = apply_text_adapter(
                        text,
                        target_path=target,
                        policy=policy,
                        agent_ids=source_agent_ids,
                        replacement_hits=replacement_hits,
                        check_prefix_residue=check_prefix_residue,
                    )
                    data = adapted.encode("utf-8")
            else:
                data = source_file.read_bytes()
            add_file(files, casefolded, target, data, executable=executable)

    for target in policy["remove"]:
        if target not in files:
            raise ProjectionError(f"remove target does not exist in projection: {target}")
        del files[target]
        del casefolded[target.casefold()]

    for target, overlay_source in policy["overlays"].items():
        path = root / relative_path(overlay_source, label=f"overlay source for {target}")
        if path.is_symlink() or not path.is_file():
            raise ProjectionError(f"overlay source must be a regular file: {path}")
        if target in files:
            del files[target]
            del casefolded[target.casefold()]
        if path.suffix.lower() == ".md":
            text = path.read_text(encoding="utf-8")
            if PurePosixPath(target).name == "SKILL.md":
                frontmatter, body = split_frontmatter(
                    text, path=path.relative_to(root).as_posix()
                )
                name, description = required_component(
                    frontmatter, path=path.relative_to(root).as_posix()
                )
                expected_name = PurePosixPath(target).parts[1]
                if name != expected_name:
                    raise ProjectionError(
                        f"overlay {path} name {name!r} must match {expected_name!r}"
                    )
                adapted_description = apply_text_adapter(
                    description,
                    target_path=target,
                    policy=policy,
                    agent_ids=source_agent_ids,
                    replacement_hits=replacement_hits,
                )
                adapted_body = apply_text_adapter(
                    body,
                    target_path=target,
                    policy=policy,
                    agent_ids=source_agent_ids,
                    replacement_hits=replacement_hits,
                )
                data = render_skill(name, adapted_description, adapted_body).encode("utf-8")
            else:
                data = apply_text_adapter(
                    text,
                    target_path=target,
                    policy=policy,
                    agent_ids=source_agent_ids,
                    replacement_hits=replacement_hits,
                ).encode("utf-8")
        else:
            data = path.read_bytes()
        add_file(
            files,
            casefolded,
            target,
            data,
            executable=bool(path.stat().st_mode & 0o111),
        )

    for skill_id in sorted(skills):
        target_skill = f"skills/{skill_id}/SKILL.md"
        if target_skill not in files:
            raise ProjectionError(f"projected skill is missing: {target_skill}")
        frontmatter, _ = split_frontmatter(
            files[target_skill][0].decode("utf-8"), path=target_skill
        )
        name, description = required_component(frontmatter, path=target_skill)
        if name != skill_id:
            raise ProjectionError(f"projected skill name drift for {skill_id}")
        command = f"commands/{skill_id}.md"
        add_file(
            files,
            casefolded,
            command,
            render_command(name, description).encode("utf-8"),
        )

    for index, replacement in enumerate(policy["runtimeTextReplacements"]):
        key = f"runtime:{index}:{replacement['from']}"
        if replacement_hits.get(key, 0) == 0:
            raise ProjectionError(
                "runtime replacement no longer matches canonical sources: "
                f"{replacement['from']!r}"
            )
    for target, replacements in policy["pathTextReplacements"].items():
        for index, replacement in enumerate(replacements):
            key = f"path:{target}:{index}"
            if replacement_hits.get(key, 0) == 0:
                raise ProjectionError(
                    f"path replacement no longer matches {target}: "
                    f"{replacement['from']!r}"
                )
    if replacement_hits.get("qualified-agent", 0) == 0:
        raise ProjectionError("canonical sources no longer exercise qualified agent adaptation")
    if replacement_hits.get("slash-skill", 0) == 0:
        raise ProjectionError("canonical sources no longer exercise slash skill adaptation")

    policy_resolved = (
        policy_path if policy_path.is_absolute() else root / policy_path
    ).resolve()
    file_contract = {
        path: {
            "sha256": hashlib.sha256(data).hexdigest(),
            "mode": f"{mode:04o}",
        }
        for path, (data, mode) in sorted(files.items())
    }
    manifest = {
        "schemaVersion": 1,
        "target": TARGET_ID,
        "generator": {
            "path": "scripts/generate_opencode.py",
            "version": GENERATOR_VERSION,
        },
        "source": {
            "plugin": plugin_manifest.get("name"),
            "pluginManifest": source["pluginManifest"],
            "policy": policy_resolved.relative_to(root).as_posix(),
            "policySha256": hashlib.sha256(policy_resolved.read_bytes()).hexdigest(),
        },
        "modelSelection": "inherit-provider-or-session",
        "skillInvocation": {
            "internal": "native-skill-tool",
            "user": "commands/<skill-id>.md",
        },
        "counts": {
            "agents": len(source_agent_ids),
            "primaryAgents": sum(
                config["mode"] == "primary" for config in policy["agents"].values()
            ),
            "subagents": sum(
                config["mode"] == "subagent" for config in policy["agents"].values()
            ),
            "skills": len(skills),
            "commands": len(skills),
        },
        "skillCapabilities": capabilities,
        "manualOnlyApproximation": {
            "sourceField": "disable-model-invocation: true",
            "targetRule": "permission.skill: ask",
            "lastMatchWins": True,
            "explicitCommandWrapper": True,
            "skills": manual_only,
        },
        "files": file_contract,
    }
    add_file(
        files,
        casefolded,
        "manifest.json",
        (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
    )
    return files, policy


def compare_projection(output: Path, expected: Mapping[str, GeneratedFile]) -> list[str]:
    differences: list[str] = []
    if output.exists():
        if output.is_symlink() or not output.is_dir():
            return [f"target output is not a regular directory: {output}"]
    actual_paths, symlinks, _ = scan_output(output)
    for path in symlinks:
        differences.append(f"generated target contains symlink: {path}")
    expected_paths = set(expected)
    for relative in sorted(expected_paths - set(actual_paths)):
        differences.append(f"missing generated file: {relative}")
    for relative in sorted(set(actual_paths) - expected_paths):
        differences.append(f"unexpected generated file: {relative}")
    for relative in sorted(expected_paths & set(actual_paths)):
        expected_data, expected_mode = expected[relative]
        actual_path = actual_paths[relative]
        actual_data = actual_path.read_bytes()
        if actual_data != expected_data:
            try:
                old = actual_data.decode("utf-8")
                new = expected_data.decode("utf-8")
            except UnicodeDecodeError:
                differences.append(f"generated binary file differs: {relative}")
            else:
                diff = difflib.unified_diff(
                    old.splitlines(keepends=True),
                    new.splitlines(keepends=True),
                    fromfile=relative,
                    tofile=f"{relative} (generated)",
                    n=2,
                )
                differences.append("".join(diff).rstrip())
        actual_executable = bool(actual_path.stat().st_mode & 0o111)
        expected_executable = bool(expected_mode & 0o111)
        if actual_executable != expected_executable:
            differences.append(
                f"generated mode differs for {relative}: executable={actual_executable}, "
                f"expected={expected_executable}"
            )
    return differences


def is_runtime_artifact(relative: str) -> bool:
    path = PurePosixPath(relative)
    return (
        len(path.parts) == 1 and relative in RUNTIME_ARTIFACT_FILES
    ) or (bool(path.parts) and path.parts[0] in RUNTIME_ARTIFACT_DIRECTORIES)


def scan_output(output: Path) -> tuple[dict[str, Path], list[Path], list[Path]]:
    files: dict[str, Path] = {}
    symlinks: list[Path] = []
    directories: list[Path] = []
    if not output.is_dir() or output.is_symlink():
        return files, symlinks, directories
    pending = [output]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                relative = path.relative_to(output).as_posix()
                if is_runtime_artifact(relative):
                    continue
                if entry.is_symlink():
                    symlinks.append(path)
                elif entry.is_dir(follow_symlinks=False):
                    directories.append(path)
                    pending.append(path)
                elif entry.is_file(follow_symlinks=False):
                    files[relative] = path
    return files, symlinks, directories


def update_projection(output: Path, expected: Mapping[str, GeneratedFile]) -> bool:
    if output.exists() and (output.is_symlink() or not output.is_dir()):
        raise ProjectionError(f"target output is not a regular directory: {output}")
    changed = bool(compare_projection(output, expected))
    output.mkdir(parents=True, exist_ok=True)
    actual_files, symlinks, directories = scan_output(output)
    actual_files.update(
        (path.relative_to(output).as_posix(), path) for path in symlinks
    )
    for relative in sorted(set(actual_files) - set(expected), reverse=True):
        actual_files[relative].unlink()
    for relative, (data, mode) in sorted(expected.items()):
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink():
            destination.unlink()
        if not destination.is_file() or destination.read_bytes() != data:
            destination.write_bytes(data)
        os.chmod(destination, mode)
    for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    return changed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if generated output is stale")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    try:
        expected, policy = build_projection(root, args.policy)
        output = root / relative_path(policy["output"], label="policy output")
        if args.check:
            differences = compare_projection(output, expected)
            if differences:
                print("OpenCode v1 target is not generated from canonical sources:", file=sys.stderr)
                for difference in differences[:20]:
                    print(difference, file=sys.stderr)
                if len(differences) > 20:
                    print(f"... and {len(differences) - 20} more differences", file=sys.stderr)
                raise ProjectionError("OpenCode v1 target is stale")
            print(f"OpenCode v1 target is current: {output}")
        else:
            changed = update_projection(output, expected)
            if changed:
                print(f"Generated OpenCode v1 target: {output}")
            else:
                print(f"OpenCode v1 target was already current: {output}")
    except (OSError, ProjectionError) as exc:
        print(f"OpenCode generation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
