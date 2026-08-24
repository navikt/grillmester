#!/usr/bin/env python3
"""Generate focused local-model targets from reviewed full Grillmester targets."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = Path("policy/focused-context-v1.json")
GENERATOR_VERSION = 1
MAX_JSON_DEPTH = 40
COMPONENT_ID = re.compile(r"^[a-z][a-z0-9-]*$")
POLICY_FIELDS = frozenset(
    {
        "schemaVersion",
        "projection",
        "sources",
        "outputs",
        "agents",
        "skills",
        "fullContextHandoff",
        "copilotCli",
    }
)
EXPECTED_AGENTS = ("barista", "grill-inspektor")
EXPECTED_SKILLS = (
    "grillmester-diagnosing-bugs",
    "grillmester-integration-tests",
    "grillmester-pull-request",
    "grillmester-review",
    "grillmester-security-review",
    "grillmester-tdd",
)
EXPECTED_SOURCES = {
    "plugin": "plugin",
    "opencode": "targets/opencode-v1",
}
EXPECTED_OUTPUTS = {
    "opencode": "targets/opencode-v1-focused",
    "copilotCli": "targets/copilot-cli-focused-v1",
}
EXCLUDED_SKILL_REPLACEMENTS = {
    "grillmester-e2e-tests": "the repository's full-system test workflow",
}
OPENCODE_ABSENT_PERMISSION_SKILLS = (
    "grillmester-doctor",
    "grillmester-grill-me",
    "grillmester-grill-with-docs",
    "grillmester-handoff",
)
QUALIFIED_AGENT_REFERENCE = re.compile(
    r"(?<![a-z0-9-])grillmester:([a-z][a-z0-9-]*)"
)
SKILL_REFERENCE = re.compile(r"(?<![a-z0-9-])(grillmester-[a-z][a-z0-9-]*)")


class ProjectionError(ValueError):
    """Raised when reviewed sources cannot produce safe focused targets."""


GeneratedFile = tuple[bytes, int]


def reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProjectionError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def reject_nonstandard_json_constant(value: str) -> None:
    raise ProjectionError(f"non-standard JSON constant is forbidden: {value}")


def parse_object(data: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=reject_duplicate_json_keys,
            parse_constant=reject_nonstandard_json_constant,
        )
    except UnicodeDecodeError as exc:
        raise ProjectionError(f"{label} is not UTF-8") from exc
    except RecursionError as exc:
        raise ProjectionError(f"{label} exceeds the JSON nesting limit") from exc
    except json.JSONDecodeError as exc:
        raise ProjectionError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ProjectionError(f"{label} must contain a JSON object")
    pending: list[tuple[object, int]] = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > MAX_JSON_DEPTH:
            raise ProjectionError(f"{label} exceeds the JSON nesting limit")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    return value


def load_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise ProjectionError(f"{label} does not exist: {path}") from exc
    except OSError as exc:
        raise ProjectionError(f"could not read {label} {path}: {exc}") from exc
    return parse_object(data, label=label)


def relative_path(value: Any, *, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ProjectionError(f"{label} must be a non-empty repository-relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ProjectionError(f"{label} must be a normalized repository-relative path")
    return path


def require_exact_fields(
    value: Mapping[str, Any], *, expected: frozenset[str], label: str
) -> None:
    missing = sorted(expected - set(value))
    unexpected = sorted(set(value) - expected)
    if missing or unexpected:
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unexpected:
            details.append("unexpected " + ", ".join(unexpected))
        raise ProjectionError(f"{label} fields are invalid: {'; '.join(details)}")


def string_list(value: Any, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ProjectionError(f"{label} must be a non-empty array")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not COMPONENT_ID.fullmatch(item):
            raise ProjectionError(f"{label} contains an invalid component ID")
        if item in result:
            raise ProjectionError(f"{label} contains duplicate ID {item!r}")
        result.append(item)
    return tuple(result)


def load_policy(root: Path, policy_path: Path) -> tuple[dict[str, Any], str]:
    resolved = policy_path if policy_path.is_absolute() else root / policy_path
    if resolved.is_symlink() or not resolved.is_file():
        raise ProjectionError(
            f"focused-context policy is not a regular file: {resolved}"
        )
    try:
        policy_bytes = resolved.read_bytes()
    except OSError as exc:
        raise ProjectionError(
            f"could not read focused-context policy {resolved}: {exc}"
        ) from exc
    policy = parse_object(policy_bytes, label="focused-context policy")
    require_exact_fields(policy, expected=POLICY_FIELDS, label="focused-context policy")
    if policy["schemaVersion"] != 1:
        raise ProjectionError("focused-context policy schemaVersion must be 1")
    if policy["projection"] != "focused-context-v1":
        raise ProjectionError("focused-context policy names an unsupported projection")
    if string_list(policy["agents"], label="policy agents") != EXPECTED_AGENTS:
        raise ProjectionError("focused-context policy must use the reviewed agent roster")
    if string_list(policy["skills"], label="policy skills") != EXPECTED_SKILLS:
        raise ProjectionError("focused-context policy must use the reviewed skill roster")
    sources = policy["sources"]
    outputs = policy["outputs"]
    copilot = policy["copilotCli"]
    handoff = policy["fullContextHandoff"]
    if not isinstance(sources, dict):
        raise ProjectionError("policy sources must be an object")
    if not isinstance(outputs, dict):
        raise ProjectionError("policy outputs must be an object")
    if not isinstance(copilot, dict):
        raise ProjectionError("policy copilotCli must be an object")
    if not isinstance(handoff, dict):
        raise ProjectionError("policy fullContextHandoff must be an object")
    require_exact_fields(
        sources, expected=frozenset({"plugin", "opencode"}), label="policy sources"
    )
    require_exact_fields(
        outputs,
        expected=frozenset({"opencode", "copilotCli"}),
        label="policy outputs",
    )
    require_exact_fields(
        copilot,
        expected=frozenset({"removeAgentFrontmatterFields"}),
        label="policy copilotCli",
    )
    require_exact_fields(
        handoff,
        expected=frozenset({"status", "command"}),
        label="policy fullContextHandoff",
    )
    for key, value in sources.items():
        relative_path(value, label=f"policy sources.{key}")
    for key, value in outputs.items():
        relative_path(value, label=f"policy outputs.{key}")
    if sources != EXPECTED_SOURCES:
        raise ProjectionError("policy sources must name the reviewed canonical targets")
    if outputs != EXPECTED_OUTPUTS:
        raise ProjectionError(
            "policy outputs must name the reviewed focused target paths"
        )
    if copilot["removeAgentFrontmatterFields"] != ["model"]:
        raise ProjectionError("focused Copilot agents must remove only the model field")
    if handoff != {
        "status": "NEEDS_FULL_CONTEXT",
        "command": "grillmester local --full",
    }:
        raise ProjectionError("focused full-context handoff is not the reviewed contract")
    return policy, hashlib.sha256(policy_bytes).hexdigest()


def read_regular_file(path: Path, *, label: str) -> GeneratedFile:
    if path.is_symlink() or not path.is_file():
        raise ProjectionError(f"{label} is not a regular file: {path}")
    try:
        return path.read_bytes(), path.stat().st_mode & 0o7777
    except OSError as exc:
        raise ProjectionError(f"could not read {label} {path}: {exc}") from exc


def add_file(
    files: dict[str, GeneratedFile], relative: str, generated: GeneratedFile
) -> None:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != relative:
        raise ProjectionError(f"generated path is not normalized: {relative}")
    folded = relative.casefold()
    if any(existing.casefold() == folded for existing in files):
        raise ProjectionError(f"generated path collides case-insensitively: {relative}")
    files[relative] = generated


def copy_tree(
    files: dict[str, GeneratedFile], *, source: Path, destination: str, label: str
) -> None:
    if source.is_symlink() or not source.is_dir():
        raise ProjectionError(f"{label} is not a regular directory: {source}")
    found = False
    for candidate in sorted(source.rglob("*")):
        if candidate.is_symlink():
            raise ProjectionError(f"{label} contains symlink: {candidate}")
        if candidate.is_dir():
            continue
        if not candidate.is_file():
            raise ProjectionError(f"{label} contains non-regular node: {candidate}")
        found = True
        relative = candidate.relative_to(source).as_posix()
        add_file(
            files,
            f"{destination}/{relative}",
            read_regular_file(candidate, label=label),
        )
    if not found:
        raise ProjectionError(f"{label} contains no files: {source}")


def remove_frontmatter_field(data: bytes, *, field: str, path: str) -> bytes:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProjectionError(f"{path} is not UTF-8") from exc
    if not text.startswith("---\n"):
        raise ProjectionError(f"{path} has no YAML frontmatter")
    closing = text.find("\n---\n", 4)
    if closing < 0:
        raise ProjectionError(f"{path} has unterminated YAML frontmatter")
    block = text[4:closing]
    lines = block.splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if line.startswith(f"{field}:")]
    if len(matches) != 1:
        raise ProjectionError(f"{path} must contain exactly one {field!r} field")
    del lines[matches[0]]
    return ("---\n" + "".join(lines) + text[closing:]).encode("utf-8")


def replace_once(text: str, old: str, new: str, *, path: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ProjectionError(
            f"focused overlay expected one reviewed match in {path}, found {count}"
        )
    return text.replace(old, new, 1)


def strip_opencode_absent_skill_permissions(text: str, *, path: str) -> str:
    if not path.startswith("agents/"):
        return text
    for skill in OPENCODE_ABSENT_PERMISSION_SKILLS:
        text = replace_once(text, f"    {skill}: ask\n", "", path=path)
    return text


def replace_excluded_skill_references(text: str) -> str:
    for skill, replacement in EXCLUDED_SKILL_REPLACEMENTS.items():
        for reference in (
            f"`/{skill}`",
            f"/{skill}",
            f"`{skill}`",
            skill,
        ):
            text = text.replace(reference, replacement)
    return text


def replace_section(
    text: str, *, start: str, end: str | None, new: str, path: str
) -> str:
    if text.count(start) != 1:
        raise ProjectionError(
            f"focused overlay expected one section start in {path}: {start!r}"
        )
    begin = text.index(start)
    if end is None:
        finish = len(text)
    else:
        if text.count(end, begin + len(start)) != 1:
            raise ProjectionError(
                f"focused overlay expected one section end in {path}: {end!r}"
            )
        finish = text.index(end, begin + len(start))
    return text[:begin] + new + text[finish:]


def apply_diagnosing_focused_overlay(text: str, *, path: str) -> str:
    text = replace_section(
        text,
        start="If the symptom is a runtime/platform problem in production,",
        end="\n\n## Phase 1 — Build a feedback loop",
        new=(
            "If the symptom is a runtime/platform problem in production, use the "
            "platform's\n"
            "approved diagnostic tooling to establish the failing boundary, then return "
            "here\n"
            "for the reproduction and fix discipline. Use repository evidence where it "
            "is\n"
            "sufficient. If the necessary Nav-specific diagnostic tree is unavailable in\n"
            "focused mode, do not invent it; return `Status: NEEDS_FULL_CONTEXT` as\n"
            "defined in the Full-context boundary section."
        ),
        path=path,
    )
    text = replace_section(
        text,
        start="**Then ask: what would have prevented this bug?**",
        end="\n\n## Runtime/platform symptoms",
        new=(
            "**Then ask: what would have prevented this bug?** Record the smallest useful\n"
            "follow-up after the fix, when the evidence is strongest. If the follow-up\n"
            "requires specialist architecture, domain, design-stress, identity, or Nav\n"
            "platform guidance outside this roster, return `Status: NEEDS_FULL_CONTEXT`\n"
            "as defined in the Full-context boundary section."
        ),
        path=path,
    )
    text = replace_section(
        text,
        start="## Runtime/platform symptoms",
        end="\n\n## Related skills",
        new=(
            "## Runtime/platform symptoms\n\n"
            "For a production-only failure, identify the layer before changing code:\n"
            "deployment/startup, identity or authorization, messaging, database, or\n"
            "observability. Use only repository-approved platform tools, keep the pass\n"
            "read-only until the boundary is known, and then return to phases 5–6 here.\n"
            "Always propose the least invasive fix first. Production configuration changes,\n"
            "workload restarts and managed-resource changes require explicit approval.\n\n"
            "If deeper Nav-specific diagnostic or identity guidance is required but absent\n"
            "from the repository, return `Status: NEEDS_FULL_CONTEXT` as defined in the\n"
            "Full-context boundary section."
        ),
        path=path,
    )
    return replace_section(
        text,
        start="## Related skills",
        end=None,
        new=(
            "## Full-context boundary\n\n"
            "This focused skill deliberately omits specialist architecture, domain, identity,\n"
            "design-stress, and Nav platform skills. When the task requires one, stop with:\n\n"
            "```text\n"
            "Status: NEEDS_FULL_CONTEXT\n"
            "Resume with: grillmester local --full\n"
            "```\n"
        ),
        path=path,
    )


def apply_focused_text_overlay(
    files: Mapping[str, GeneratedFile], *, client: str
) -> dict[str, GeneratedFile]:
    transformed: dict[str, GeneratedFile] = {}
    for relative, (data, mode) in files.items():
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            transformed[relative] = (data, mode)
            continue
        if client == "opencode":
            text = strip_opencode_absent_skill_permissions(text, path=relative)
        if relative == "skills/grillmester-diagnosing-bugs/SKILL.md":
            text = apply_diagnosing_focused_overlay(text, path=relative)
        text = replace_excluded_skill_references(text)
        if relative in {"agents/barista.md", "agents/barista.agent.md"}:
            qualified = (
                "`grillmester`" if client == "opencode" else "`grillmester:grillmester`"
            )
            old = (
                "- When repository exploration still leaves coupled product or architecture\n"
                "  decisions with material user-owned trade-offs, or a repository-defined\n"
                "  high-risk signal, stop before editing. Recommend that the user select\n"
                f"  Grillmester ({qualified}) and summarize the outcome, criteria,\n"
                "  facts, open choices, risk, verified state, and next step. Never invoke\n"
                "  Grillmester or Kokk.\n"
            )
            new = (
                "- When repository exploration still leaves coupled product or architecture\n"
                "  decisions with material user-owned trade-offs, or a repository-defined\n"
                "  high-risk signal, stop before editing and return a full-context handoff:\n"
                "  `Status: NEEDS_FULL_CONTEXT`. Summarize the outcome, criteria, facts, open\n"
                "  choices, risk, verified state, and next step, then state\n"
                "  `Resume with: grillmester local --full`. Do not continue in focused mode.\n"
            )
            text = replace_once(text, old, new, path=relative)
            text = replace_once(
                text,
                "Security relevance alone does not change the solo route;\n"
                "recommend Grillmester when the review exposes unresolved user-owned "
                "trade-offs\n"
                "or risk outside a bounded solo change.",
                "Security relevance alone does not change the solo route. If review exposes\n"
                "unresolved user-owned trade-offs or risk outside a bounded solo change,\n"
                "return `Status: NEEDS_FULL_CONTEXT` with the full-context handoff\n"
                "defined in the Route step.",
                path=relative,
            )
            text = replace_once(
                text,
                "Task size and file count alone do not change the route. If later evidence\n"
                "crosses the solo boundary, stop at a safe point, report what changed and "
                "what\n"
                "remains verified, and recommend Grillmester.",
                "Task size and file count alone do not change the route. If later evidence\n"
                "crosses the solo boundary, stop at a safe point, report what changed and "
                "what\n"
                "remains verified, then return `Status: NEEDS_FULL_CONTEXT` with the\n"
                "full-context handoff defined in the Route step.",
                path=relative,
            )
        if relative in {
            "agents/grill-inspektor.md",
            "agents/grill-inspektor.agent.md",
        }:
            text = replace_once(
                text,
                "the Kokk brief",
                "the implementer's brief",
                path=relative,
            )
        if relative == "skills/grillmester-review/SKILL.md":
            delegated = (
                "`kokk`" if client == "opencode" else "`grillmester:kokk`"
            )
            text = replace_once(
                text,
                "If the active caller is the writer, fix in-scope findings before "
                "returning. If\n"
                f"Grillmester is reviewing work from {delegated}, do not edit the\n"
                "implementation in the orchestration context; send Kokk the smallest "
                "bounded\n"
                "correction instead.",
                "If the active caller is the writer, fix in-scope findings before "
                "returning. When\n"
                "reviewing delegated work, do not edit the implementation in the "
                "review\n"
                "context; return the smallest bounded correction to the active writer "
                "instead.",
                path=relative,
            )
        transformed[relative] = (text.encode("utf-8"), mode)
    validate_focused_references(transformed, client=client)
    return transformed


def validate_focused_references(
    files: Mapping[str, GeneratedFile], *, client: str
) -> None:
    allowed_agents = set(EXPECTED_AGENTS)
    allowed_skills = set(EXPECTED_SKILLS)
    for relative, (data, _) in files.items():
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        missing_agents = set(QUALIFIED_AGENT_REFERENCE.findall(text)) - allowed_agents
        missing_skills = set(SKILL_REFERENCE.findall(text)) - allowed_skills
        if missing_agents:
            raise ProjectionError(
                f"focused {client} file references absent agents in {relative}: "
                + ", ".join(sorted(missing_agents))
            )
        if missing_skills:
            raise ProjectionError(
                f"focused {client} file references absent skills in {relative}: "
                + ", ".join(sorted(missing_skills))
            )
        if re.search(r"\bKokk\b|`kokk`", text):
            raise ProjectionError(
                f"focused {client} file references absent Kokk in {relative}"
            )


def file_contract(files: Mapping[str, GeneratedFile]) -> dict[str, dict[str, str]]:
    return {
        path: {
            "sha256": hashlib.sha256(data).hexdigest(),
            "mode": f"{mode:04o}",
        }
        for path, (data, mode) in sorted(files.items())
    }


def validate_source_files(
    files: Mapping[str, GeneratedFile],
    contracts: Any,
    *,
    label: str,
) -> None:
    if not isinstance(contracts, dict):
        raise ProjectionError(f"{label} manifest has no file contracts")
    for relative, (data, mode) in sorted(files.items()):
        contract = contracts.get(relative)
        if not isinstance(contract, dict):
            raise ProjectionError(
                f"{label} source differs from its manifest: missing {relative}"
            )
        digest = contract.get("sha256")
        expected_mode = contract.get("mode")
        if digest != hashlib.sha256(data).hexdigest() or expected_mode != f"{mode:04o}":
            raise ProjectionError(
                f"{label} source differs from its manifest: {relative}"
            )


def build_opencode_projection(
    root: Path, policy: Mapping[str, Any], policy_path: Path, policy_sha256: str
) -> dict[str, GeneratedFile]:
    source_relative = relative_path(
        policy["sources"]["opencode"], label="policy sources.opencode"
    )
    source = root / source_relative
    if source.is_symlink() or not source.is_dir():
        raise ProjectionError(
            f"focused OpenCode source is not a regular directory: {source}"
        )
    manifest_bytes, _ = read_regular_file(
        source / "manifest.json", label="OpenCode manifest"
    )
    source_manifest = parse_object(manifest_bytes, label="OpenCode manifest")
    if source_manifest.get("target") != "opencode-v1":
        raise ProjectionError("focused OpenCode source must be target opencode-v1")
    counts = source_manifest.get("counts")
    if not isinstance(counts, dict) or counts.get("agents") != 7 or counts.get(
        "skills"
    ) != 42 or counts.get("commands") != 42:
        raise ProjectionError("focused OpenCode source is not the complete 7/42 target")
    files: dict[str, GeneratedFile] = {}
    for relative in (".gitignore", "opencode.json"):
        add_file(
            files,
            relative,
            read_regular_file(source / relative, label=f"OpenCode {relative}"),
        )
    for agent in EXPECTED_AGENTS:
        relative = f"agents/{agent}.md"
        add_file(
            files,
            relative,
            read_regular_file(source / relative, label=f"OpenCode agent {agent}"),
        )
    for skill in EXPECTED_SKILLS:
        copy_tree(
            files,
            source=source / "skills" / skill,
            destination=f"skills/{skill}",
            label=f"OpenCode skill {skill}",
        )
        relative = f"commands/{skill}.md"
        add_file(
            files,
            relative,
            read_regular_file(source / relative, label=f"OpenCode command {skill}"),
        )
    validate_source_files(
        files, source_manifest.get("files"), label="OpenCode"
    )
    files = apply_focused_text_overlay(files, client="opencode")
    manifest = {
        "schemaVersion": 1,
        "target": "opencode-v1-focused",
        "projection": "focused-context-v1",
        "generator": {
            "path": "scripts/generate_context_projections.py",
            "version": GENERATOR_VERSION,
        },
        "source": {
            "target": source_relative.as_posix(),
            "targetManifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "policy": policy_path.as_posix(),
            "policySha256": policy_sha256,
        },
        "modelSelection": "inherit-provider-or-session",
        "transformations": {
            "agentEscalation": "full-context-handoff",
            "excludedSkillReferences": "full-context-guidance",
            "skillPermissionEntriesRemoved": list(
                OPENCODE_ABSENT_PERMISSION_SKILLS
            ),
        },
        "counts": {"agents": 2, "skills": 6, "commands": 6},
        "agents": list(EXPECTED_AGENTS),
        "skills": list(EXPECTED_SKILLS),
        "files": file_contract(files),
    }
    add_file(
        files,
        "manifest.json",
        (
            (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode(
                "utf-8"
            ),
            0o644,
        ),
    )
    return files


def build_copilot_projection(
    root: Path, policy: Mapping[str, Any], policy_path: Path, policy_sha256: str
) -> dict[str, GeneratedFile]:
    source_relative = relative_path(
        policy["sources"]["plugin"], label="policy sources.plugin"
    )
    source = root / source_relative
    if source.is_symlink() or not source.is_dir():
        raise ProjectionError(
            f"focused Copilot source is not a regular directory: {source}"
        )
    plugin_bytes, plugin_mode = read_regular_file(
        source / "plugin.json", label="Copilot manifest"
    )
    plugin_manifest = parse_object(plugin_bytes, label="Copilot manifest")
    if plugin_manifest.get("name") != "grillmester":
        raise ProjectionError("focused Copilot source must be the Grillmester plugin")
    files: dict[str, GeneratedFile] = {}
    add_file(files, "plugin.json", (plugin_bytes, plugin_mode))
    for relative in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        add_file(
            files,
            relative,
            read_regular_file(source / relative, label=f"Copilot {relative}"),
        )
    for agent in EXPECTED_AGENTS:
        relative = f"agents/{agent}.agent.md"
        data, mode = read_regular_file(
            source / relative, label=f"Copilot agent {agent}"
        )
        add_file(
            files,
            relative,
            (remove_frontmatter_field(data, field="model", path=relative), mode),
        )
    for skill in EXPECTED_SKILLS:
        copy_tree(
            files,
            source=source / "skills" / skill,
            destination=f"skills/{skill}",
            label=f"Copilot skill {skill}",
        )
    files = apply_focused_text_overlay(files, client="copilotCli")
    manifest = {
        "schemaVersion": 1,
        "target": "copilot-cli-focused-v1",
        "projection": "focused-context-v1",
        "distribution": "private-cli-only",
        "generator": {
            "path": "scripts/generate_context_projections.py",
            "version": GENERATOR_VERSION,
        },
        "source": {
            "plugin": source_relative.as_posix(),
            "pluginManifestSha256": hashlib.sha256(plugin_bytes).hexdigest(),
            "policy": policy_path.as_posix(),
            "policySha256": policy_sha256,
        },
        "modelSelection": "inherit-provider-or-session",
        "transformations": {
            "agentFrontmatterRemoved": ["model"],
            "agentEscalation": "full-context-handoff",
            "excludedSkillReferences": "full-context-guidance",
        },
        "counts": {"agents": 2, "skills": 6},
        "agents": list(EXPECTED_AGENTS),
        "skills": list(EXPECTED_SKILLS),
        "files": file_contract(files),
    }
    add_file(
        files,
        "manifest.json",
        (
            (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode(
                "utf-8"
            ),
            0o644,
        ),
    )
    return files


def build_projections(
    root: Path, policy_path: Path = DEFAULT_POLICY
) -> tuple[dict[str, dict[str, GeneratedFile]], dict[str, Any]]:
    root = root.resolve()
    policy, policy_sha256 = load_policy(root, policy_path)
    if policy_path.is_absolute():
        try:
            normalized_policy = policy_path.relative_to(root)
        except ValueError as exc:
            raise ProjectionError(
                "focused-context policy must be inside the repository root"
            ) from exc
    else:
        normalized_policy = policy_path
    return {
        "opencode": build_opencode_projection(
            root, policy, normalized_policy, policy_sha256
        ),
        "copilotCli": build_copilot_projection(
            root, policy, normalized_policy, policy_sha256
        ),
    }, policy


def scan_output(output: Path) -> tuple[dict[str, Path], list[Path], list[Path], list[Path]]:
    files: dict[str, Path] = {}
    symlinks: list[Path] = []
    directories: list[Path] = []
    special_nodes: list[Path] = []
    if not output.is_dir() or output.is_symlink():
        return files, symlinks, directories, special_nodes
    pending = [output]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                relative = path.relative_to(output).as_posix()
                if entry.is_symlink():
                    symlinks.append(path)
                elif entry.is_dir(follow_symlinks=False):
                    directories.append(path)
                    pending.append(path)
                elif entry.is_file(follow_symlinks=False):
                    files[relative] = path
                else:
                    special_nodes.append(path)
    return files, symlinks, directories, special_nodes


def compare_projection(
    output: Path, expected: Mapping[str, GeneratedFile]
) -> list[str]:
    differences: list[str] = []
    if output.exists() and (output.is_symlink() or not output.is_dir()):
        return [f"target output is not a regular directory: {output}"]
    actual, symlinks, _, special = scan_output(output)
    differences.extend(f"generated target contains symlink: {path}" for path in symlinks)
    differences.extend(
        f"generated target contains non-regular node: {path}" for path in special
    )
    for relative in sorted(set(expected) - set(actual)):
        differences.append(f"missing generated file: {relative}")
    for relative in sorted(set(actual) - set(expected)):
        differences.append(f"unexpected generated file: {relative}")
    for relative in sorted(set(expected) & set(actual)):
        expected_data, expected_mode = expected[relative]
        actual_data = actual[relative].read_bytes()
        if actual_data != expected_data:
            try:
                old = actual_data.decode("utf-8")
                new = expected_data.decode("utf-8")
            except UnicodeDecodeError:
                differences.append(f"generated binary file differs: {relative}")
            else:
                differences.append(
                    "".join(
                        difflib.unified_diff(
                            old.splitlines(keepends=True),
                            new.splitlines(keepends=True),
                            fromfile=relative,
                            tofile=f"{relative} (generated)",
                            n=2,
                        )
                    ).rstrip()
                )
        actual_mode = actual[relative].stat().st_mode & 0o7777
        if actual_mode != expected_mode:
            differences.append(
                f"generated mode differs for {relative}: actual={actual_mode:04o}, "
                f"expected={expected_mode:04o}"
            )
    return differences


def update_projection(output: Path, expected: Mapping[str, GeneratedFile]) -> bool:
    if output.exists() and (output.is_symlink() or not output.is_dir()):
        raise ProjectionError(f"target output is not a regular directory: {output}")
    changed = False
    output.mkdir(parents=True, exist_ok=True)
    actual, symlinks, directories, special = scan_output(output)
    if special:
        raise ProjectionError(
            "generated target contains non-regular nodes: "
            + ", ".join(str(path) for path in sorted(special))
        )
    actual.update((path.relative_to(output).as_posix(), path) for path in symlinks)
    for relative in sorted(set(actual) - set(expected), reverse=True):
        actual[relative].unlink()
        changed = True
    for relative, (data, mode) in sorted(expected.items()):
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink():
            destination.unlink()
            changed = True
        if not destination.is_file() or destination.read_bytes() != data:
            destination.write_bytes(data)
            changed = True
        if stat.S_IMODE(destination.stat().st_mode) != mode:
            os.chmod(destination, mode)
            changed = True
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
        projections, policy = build_projections(root, args.policy)
        for key in ("opencode", "copilotCli"):
            output = root / relative_path(
                policy["outputs"][key], label=f"policy outputs.{key}"
            )
            differences = compare_projection(output, projections[key])
            if args.check:
                if differences:
                    for difference in differences[:20]:
                        print(difference, file=sys.stderr)
                    if len(differences) > 20:
                        print(
                            f"... and {len(differences) - 20} more differences",
                            file=sys.stderr,
                        )
                    raise ProjectionError(f"{key} focused target is stale")
                print(f"Focused {key} target is current: {output}")
            else:
                changed = update_projection(output, projections[key])
                state = "Generated" if changed else "Already current"
                print(f"{state} focused {key} target: {output}")
    except (OSError, ProjectionError, ValueError) as exc:
        print(f"Focused context generation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
