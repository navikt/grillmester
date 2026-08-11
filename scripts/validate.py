#!/usr/bin/env python3
"""Deterministic validation for the Grillmester plugin package."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


PLUGIN_NAME = "grillmester"
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
COMPONENT_ID = re.compile(r"`(grillmester(?:-[a-z0-9-]+)?)`")
QUALIFIED_COMPONENT_ID = re.compile(r"`grillmester:(grillmester(?:-[a-z0-9-]+)?)`")
REALISTIC_NATIONAL_ID = re.compile(r"(?<!\d)\d{11}(?!\d)")
LEGACY_IDS = re.compile(
    r"\b(?:hovmester|kokk|barista|souschef|konditor|grill-inspektor)\b",
    re.IGNORECASE,
)
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

AGENT_CONTRACTS = {
    "grillmester": {
        "model": "gpt-5.6-sol",
        "user-invocable": True,
        "disable-model-invocation": True,
        "tools": {"read", "search", "execute", "agent", "skill", "web", "ask_user"},
    },
    "grillmester-implementer": {
        "model": "gpt-5.6-terra",
        "user-invocable": False,
        "disable-model-invocation": False,
        "tools": {"read", "search", "edit", "execute", "skill"},
    },
    "grillmester-reviewer": {
        "model": "claude-opus-5",
        "user-invocable": False,
        "disable-model-invocation": False,
        "tools": {"read", "search", "skill"},
    },
}

SKILL_CONTRACTS = {
    "grillmester-grilling": {
        "user-invocable": False,
        "disable-model-invocation": False,
    },
    "grillmester-review": {
        "user-invocable": True,
        "disable-model-invocation": False,
    },
    "grillmester-security-review": {
        "user-invocable": True,
        "disable-model-invocation": False,
    },
}


class FrontmatterError(ValueError):
    pass


def load_json(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing required file: {path}")
        return {}
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON in {path}: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"expected a JSON object in {path}")
        return {}
    return value


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith(('"', "'")):
        try:
            return json.loads(value) if value.startswith('"') else value[1:-1]
        except json.JSONDecodeError as exc:
            raise FrontmatterError(f"invalid quoted scalar: {value}") from exc
    return value


def parse_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise FrontmatterError("file must start with ---")
    try:
        closing = lines.index("---", 1)
    except ValueError as exc:
        raise FrontmatterError("frontmatter has no closing ---") from exc

    data: dict[str, Any] = {}
    current_list: str | None = None
    for number, line in enumerate(lines[1:closing], start=2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - "):
            if current_list is None:
                raise FrontmatterError(f"line {number}: list item without a key")
            data[current_list].append(parse_scalar(line[4:]))
            continue
        match = re.fullmatch(r"([a-z][a-z0-9-]*):(?:\s*(.*))?", line)
        if not match:
            raise FrontmatterError(f"line {number}: unsupported frontmatter syntax")
        key, raw_value = match.groups()
        if key in data:
            raise FrontmatterError(f"line {number}: duplicate key {key}")
        if raw_value:
            data[key] = parse_scalar(raw_value)
            current_list = None
        else:
            data[key] = []
            current_list = key

    return data, "\n".join(lines[closing + 1 :]).strip()


def validate_manifests(root: Path, errors: list[str]) -> str | None:
    plugin_path = root / "plugin.json"
    marketplace_path = root / ".github/plugin/marketplace.json"
    plugin = load_json(plugin_path, errors)
    marketplace = load_json(marketplace_path, errors)
    if not plugin or not marketplace:
        return None

    if "$schema" in plugin:
        errors.append(
            "plugin.json must use native Copilot semantics and must not declare Agent Plugins $schema"
        )
    if plugin.get("name") != PLUGIN_NAME:
        errors.append(f"plugin.json name must be {PLUGIN_NAME!r}")
    version = plugin.get("version")
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        errors.append("plugin.json version must be SemVer, optionally with a prerelease suffix")
        version = None
    if plugin.get("agents") != "agents/" or plugin.get("skills") != "skills/":
        errors.append("plugin.json must point to canonical agents/ and skills/ directories")
    for key in ("description", "author", "repository", "license"):
        if not plugin.get(key):
            errors.append(f"plugin.json is missing {key}")

    if marketplace.get("name") != PLUGIN_NAME:
        errors.append(f"marketplace name must be {PLUGIN_NAME!r}")
    owner = marketplace.get("owner")
    if not isinstance(owner, dict) or not isinstance(owner.get("name"), str) or not owner["name"].strip():
        errors.append("marketplace owner must be an object with a non-empty name")
    metadata = marketplace.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("version") != version:
        errors.append("marketplace metadata version must equal plugin.json version")
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != 1 or not isinstance(plugins[0], dict):
        errors.append("marketplace must contain exactly one plugin entry")
    else:
        entry = plugins[0]
        if entry.get("name") != PLUGIN_NAME:
            errors.append(f"marketplace plugin name must be {PLUGIN_NAME!r}")
        if entry.get("version") != version:
            errors.append("marketplace plugin version must equal plugin.json version")
        if entry.get("source") != ".":
            errors.append('marketplace plugin source must be "."')
        if not entry.get("description"):
            errors.append("marketplace plugin needs a description")
    return version


def validate_agents(root: Path, errors: list[str]) -> set[str]:
    agents_dir = root / "agents"
    found: dict[str, Path] = {}
    if not agents_dir.is_dir():
        errors.append("missing agents/ directory")
        return set()

    for path in sorted(agents_dir.glob("*.agent.md")):
        agent_id = path.name.removesuffix(".agent.md")
        if agent_id in found:
            errors.append(f"duplicate agent ID {agent_id}: {path} and {found[agent_id]}")
        found[agent_id] = path
        try:
            frontmatter, body = parse_frontmatter(path)
        except FrontmatterError as exc:
            errors.append(f"invalid frontmatter in {path}: {exc}")
            continue
        if frontmatter.get("name") != agent_id:
            errors.append(f"{path}: frontmatter name must equal filename ID {agent_id!r}")
        if not frontmatter.get("description"):
            errors.append(f"{path}: description is required")
        if not body:
            errors.append(f"{path}: agent body is empty")

        expected = AGENT_CONTRACTS.get(agent_id)
        if expected is None:
            errors.append(f"unexpected agent {agent_id}; update the reviewed agent contract first")
            continue
        for key in ("model", "user-invocable", "disable-model-invocation"):
            if frontmatter.get(key) != expected[key]:
                errors.append(f"{path}: {key} must be {expected[key]!r}")
        tools = frontmatter.get("tools")
        if not isinstance(tools, list) or set(tools) != expected["tools"]:
            errors.append(f"{path}: tools must be exactly {sorted(expected['tools'])}")

    missing = set(AGENT_CONTRACTS) - set(found)
    for agent_id in sorted(missing):
        errors.append(f"missing required agent: {agent_id}")
    return set(found)


def validate_skill_links(path: Path, body: str, errors: list[str]) -> None:
    skill_root = path.parent.resolve()
    for target in MARKDOWN_LINK.findall(body):
        target = target.strip().split("#", 1)[0]
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        resolved = (path.parent / target).resolve()
        try:
            resolved.relative_to(skill_root)
        except ValueError:
            errors.append(f"{path}: link escapes the skill directory: {target}")
            continue
        if not resolved.is_file():
            errors.append(f"{path}: linked file does not exist: {target}")


def validate_skills(root: Path, errors: list[str]) -> set[str]:
    skills_dir = root / "skills"
    found: dict[str, Path] = {}
    if not skills_dir.is_dir():
        errors.append("missing skills/ directory")
        return set()

    for path in sorted(skills_dir.glob("*/SKILL.md")):
        directory_name = path.parent.name
        try:
            frontmatter, body = parse_frontmatter(path)
        except FrontmatterError as exc:
            errors.append(f"invalid frontmatter in {path}: {exc}")
            continue
        skill_id = frontmatter.get("name")
        if skill_id != directory_name:
            errors.append(f"{path}: skill name must equal directory {directory_name!r}")
            skill_id = directory_name
        if skill_id in found:
            errors.append(f"duplicate skill ID {skill_id}: {path} and {found[skill_id]}")
        found[skill_id] = path
        if not frontmatter.get("description"):
            errors.append(f"{path}: description is required")
        if not body:
            errors.append(f"{path}: skill body is empty")
        expected = SKILL_CONTRACTS.get(skill_id)
        if expected is None:
            errors.append(f"unexpected skill {skill_id}; update the reviewed skill contract first")
        else:
            for key, expected_value in expected.items():
                if frontmatter.get(key) != expected_value:
                    errors.append(f"{path}: {key} must be {expected_value!r}")
        validate_skill_links(path, body, errors)

    missing = set(SKILL_CONTRACTS) - set(found)
    for skill_id in sorted(missing):
        errors.append(f"missing required skill: {skill_id}")
    return set(found)


def runtime_markdown(root: Path) -> list[Path]:
    paths: list[Path] = []
    for directory in (root / "agents", root / "skills"):
        if directory.exists():
            paths.extend(path for path in directory.rglob("*.md") if path.is_file())
    return sorted(paths)


def validate_content(
    root: Path, agent_ids: set[str], skill_ids: set[str], errors: list[str]
) -> None:
    known_ids = agent_ids | skill_ids
    for path in runtime_markdown(root):
        text = path.read_text(encoding="utf-8")
        legacy = LEGACY_IDS.search(text)
        if legacy:
            errors.append(f"{path}: legacy runtime ID is not allowed: {legacy.group(0)}")
        for component_id in COMPONENT_ID.findall(text):
            if component_id not in known_ids and component_id != PLUGIN_NAME:
                errors.append(f"{path}: dangling Grillmester component reference: {component_id}")
        for component_id in QUALIFIED_COMPONENT_ID.findall(text):
            if component_id not in known_ids:
                errors.append(f"{path}: dangling qualified component reference: {component_id}")

    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if REALISTIC_NATIONAL_ID.search(text):
            errors.append(f"{path}: contains an 11-digit value that looks like a national ID")


def validate_layout(root: Path, errors: list[str]) -> None:
    forbidden = [
        root / ".github/agents",
        root / ".github/skills",
        root / ".plugin/plugin.json",
        root / "marketplace.json",
        root / "dist",
    ]
    for path in forbidden:
        if path.exists():
            errors.append(f"forbidden alternate or generated path: {path}")


def validate_repo(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    validate_layout(root, errors)
    validate_manifests(root, errors)
    agent_ids = validate_agents(root, errors)
    skill_ids = validate_skills(root, errors)
    validate_content(root, agent_ids, skill_ids, errors)
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = validate_repo(root)
    if errors:
        print("Grillmester package validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Grillmester package validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
