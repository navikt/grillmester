#!/usr/bin/env python3
"""Build a deterministic, manifest-verified Grillmester terminal bundle."""

from __future__ import annotations

import argparse
import ast
import errno
import gzip
import hashlib
import io
import json
import os
import re
import stat
import sys
import tarfile
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


ARCHIVE_ROOT = PurePosixPath("grillmester-terminal-v1")
DISTRIBUTION_NAME = ARCHIVE_ROOT.as_posix()
TARGET_NAME = "opencode-v1"
TARGET_DIRECTORY = PurePosixPath("targets/opencode-v1")
FOCUSED_OPENCODE_TARGET_NAME = "opencode-v1-focused"
FOCUSED_OPENCODE_DIRECTORY = PurePosixPath("targets/opencode-v1-focused")
FOCUSED_COPILOT_TARGET_NAME = "copilot-cli-focused-v1"
FOCUSED_COPILOT_DIRECTORY = PurePosixPath("targets/copilot-cli-focused-v1")
PLUGIN_DIRECTORY = PurePosixPath("plugin")
COPILOT_FULL_MANIFEST_PATH = PLUGIN_DIRECTORY / "manifest.json"
COPILOT_FULL_TARGET_NAME = "copilot-full-v1"
COPILOT_MANIFEST_GENERATOR_PATH = PurePosixPath(
    "scripts/generate_copilot_manifest.py"
)
LAUNCHER_PATH = PurePosixPath("scripts/grillmester.py")
LOCAL_LAUNCHER_PATH = PurePosixPath("scripts/grillmester_local.py")
PROJECTION_GENERATOR_PATH = PurePosixPath("scripts/generate_context_projections.py")
FOCUSED_POLICY_PATH = PurePosixPath("policy/focused-context-v1.json")
CONTENT_LOCK_PATH = PurePosixPath("policy/content-lock.json")
RELEASE_TEST_BASELINE_PATH = PurePosixPath("scripts/release_test_baseline.py")
LICENSE_PATH = PurePosixPath("LICENSE")
PROVENANCE_PATH = PurePosixPath("PROVENANCE.md")
THIRD_PARTY_NOTICES_SOURCE = PurePosixPath("THIRD_PARTY_NOTICES.md")
THIRD_PARTY_NOTICES_PATH = PurePosixPath("THIRD_PARTY_NOTICES.md")
OUTER_MANIFEST = PurePosixPath("DISTRIBUTION-MANIFEST.json")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
FILE_MODE = re.compile(r"^0[0-7]{3}$")
ALLOWED_FILE_MODES = frozenset({0o644, 0o755})
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_JSON_DEPTH = 40
MAX_FILE_BYTES = 5_000_000
MAX_DISTRIBUTION_BYTES = 50_000_000
MAX_ARCHIVE_MEMBERS = 10_000
OPENCODE_OVERLAY_SKILL_IDS = frozenset(
    {"grillmester-create-a-skill", "grillmester-doctor"}
)
FOCUSED_AGENT_IDS = ("barista", "grill-inspektor")
FOCUSED_SKILL_IDS = (
    "grillmester-diagnosing-bugs",
    "grillmester-integration-tests",
    "grillmester-issue-management",
    "grillmester-pull-request",
    "grillmester-review",
    "grillmester-security-review",
    "grillmester-tdd",
)


class BundleBuildError(RuntimeError):
    """Raised when source input cannot produce a trustworthy bundle."""


@dataclass(frozen=True)
class BundleFile:
    path: PurePosixPath
    content: bytes
    mode: int


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_relative_path(value: object, *, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise BundleBuildError(f"{label} must be a non-empty string")
    if "\\" in value or any(
        ord(character) < 32 or ord(character) == 127 for character in value
    ):
        raise BundleBuildError(f"{label} is not a safe portable path: {value!r}")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise BundleBuildError(f"{label} is not a normalized relative path: {value!r}")
    return path


def _portable_collision_key(path: PurePosixPath) -> str:
    return unicodedata.normalize("NFC", path.as_posix()).casefold()


def _require_ustar_path(path: PurePosixPath) -> None:
    """Reject names that would require non-deterministic archive extensions."""

    try:
        tarfile.TarInfo(path.as_posix()).tobuf(
            format=tarfile.USTAR_FORMAT, encoding="utf-8", errors="strict"
        )
    except (UnicodeEncodeError, ValueError) as exc:
        raise BundleBuildError(f"archive path is not portable USTAR: {path}") from exc


def _require_directory(path: Path, *, label: str) -> None:
    try:
        observed = path.lstat()
    except FileNotFoundError as exc:
        raise BundleBuildError(f"missing {label}: {path}") from exc
    except OSError as exc:
        raise BundleBuildError(f"could not inspect {label} {path}: {exc}") from exc
    if stat.S_ISLNK(observed.st_mode):
        raise BundleBuildError(f"refusing symlinked {label}: {path}")
    if not stat.S_ISDIR(observed.st_mode):
        raise BundleBuildError(f"{label} is not a directory: {path}")


def _read_regular(
    path: Path, *, label: str, max_bytes: int = MAX_FILE_BYTES
) -> tuple[bytes, int]:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as exc:
        raise BundleBuildError(f"missing {label}: {path}") from exc
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise BundleBuildError(f"refusing symlinked {label}: {path}") from exc
        raise BundleBuildError(f"could not open {label} {path}: {exc}") from exc
    try:
        observed = os.fstat(descriptor)
    except OSError as exc:
        os.close(descriptor)
        raise BundleBuildError(f"could not inspect {label} {path}: {exc}") from exc
    if not stat.S_ISREG(observed.st_mode):
        os.close(descriptor)
        raise BundleBuildError(f"{label} is not a regular file: {path}")
    if observed.st_size > max_bytes:
        os.close(descriptor)
        raise BundleBuildError(
            f"{label} exceeds the {max_bytes}-byte safety limit: {path}"
        )
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as source:
            content = source.read(max_bytes + 1)
            try:
                after_read = os.fstat(source.fileno())
            except OSError as exc:
                raise BundleBuildError(
                    f"could not inspect {label} after reading {path}: {exc}"
                ) from exc
            if len(content) > max_bytes:
                raise BundleBuildError(
                    f"{label} exceeds the {max_bytes}-byte safety limit: {path}"
                )
            stable_metadata = (
                "st_dev",
                "st_ino",
                "st_mode",
                "st_nlink",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
            )
            if len(content) != observed.st_size or any(
                getattr(observed, field) != getattr(after_read, field)
                for field in stable_metadata
            ):
                raise BundleBuildError(f"{label} changed while being read: {path}")
            return content, stat.S_IMODE(observed.st_mode)
    except OSError as exc:
        raise BundleBuildError(f"could not read {label} {path}: {exc}") from exc


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BundleBuildError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_nonstandard_json_constant(value: str) -> None:
    raise BundleBuildError(f"non-standard JSON constant is forbidden: {value}")


def _parse_json_object(content: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except UnicodeDecodeError as exc:
        raise BundleBuildError(f"{label} is not UTF-8") from exc
    except RecursionError as exc:
        raise BundleBuildError(f"{label} exceeds the JSON nesting limit") from exc
    except json.JSONDecodeError as exc:
        raise BundleBuildError(
            f"{label} is not valid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    if not isinstance(value, dict):
        raise BundleBuildError(f"{label} must contain a JSON object")
    pending: list[tuple[object, int]] = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > MAX_JSON_DEPTH:
            raise BundleBuildError(f"{label} exceeds the JSON nesting limit")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    return value


def _require_exact_fields(
    value: object, expected: set[str], *, label: str
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise BundleBuildError(
            f"{label} must contain exactly: {', '.join(sorted(expected))}"
        )
    return value


def _require_digest(
    value: object, pattern: re.Pattern[str], *, algorithm: str, label: str
) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise BundleBuildError(f"{label} must be a lowercase {algorithm} digest")
    return value


def _distribution_support_files(source_root: Path) -> list[BundleFile]:
    content_lock_content, content_lock_mode = _read_regular(
        source_root.joinpath(*CONTENT_LOCK_PATH.parts),
        label="content lock",
        max_bytes=MAX_JSON_BYTES,
    )
    if content_lock_mode != 0o644:
        raise BundleBuildError(
            f"content lock mode must be 0644; observed {content_lock_mode:04o}"
        )
    content_lock = _parse_json_object(content_lock_content, label="content lock")
    if (
        set(content_lock) != {"schemaVersion", "sources", "agents", "skills"}
        or type(content_lock.get("schemaVersion")) is not int
        or content_lock["schemaVersion"] != 1
        or not isinstance(content_lock.get("sources"), dict)
        or not isinstance(content_lock.get("agents"), dict)
        or len(content_lock["agents"]) != 7
        or not isinstance(content_lock.get("skills"), dict)
        or len(content_lock["skills"]) != 43
    ):
        raise BundleBuildError("content lock must be the complete 7-agent/43-skill BOM")

    result = [BundleFile(CONTENT_LOCK_PATH, content_lock_content, 0o644)]
    for source_path, distribution_path, label in (
        (LICENSE_PATH, LICENSE_PATH, "license"),
        (PROVENANCE_PATH, PROVENANCE_PATH, "provenance record"),
        (
            THIRD_PARTY_NOTICES_SOURCE,
            THIRD_PARTY_NOTICES_PATH,
            "third-party notices",
        ),
    ):
        content, mode = _read_regular(
            source_root.joinpath(*source_path.parts), label=label
        )
        if mode != 0o644:
            raise BundleBuildError(
                f"{label} mode must be 0644; observed {mode:04o}"
            )
        if not content.strip():
            raise BundleBuildError(f"{label} must not be empty")
        result.append(BundleFile(distribution_path, content, 0o644))
    return result


def _target_inventory(root: Path) -> set[PurePosixPath]:
    inventory: set[PurePosixPath] = set()
    portable_nodes: dict[str, PurePosixPath] = {}
    node_count = 1

    def walk_error(error: OSError) -> None:
        raise BundleBuildError(f"could not inventory OpenCode target {root}: {error}")

    for current, directories, files in os.walk(
        root, followlinks=False, onerror=walk_error
    ):
        node_count += len(directories) + len(files)
        if node_count > MAX_ARCHIVE_MEMBERS:
            raise BundleBuildError(
                f"OpenCode target exceeds the {MAX_ARCHIVE_MEMBERS}-member safety limit"
            )
        current_path = Path(current)
        directories.sort()
        files.sort()
        for name in directories:
            child = current_path / name
            try:
                observed = child.lstat()
            except OSError as exc:
                raise BundleBuildError(
                    f"could not inspect target directory {child}: {exc}"
                ) from exc
            if stat.S_ISLNK(observed.st_mode):
                raise BundleBuildError(f"target contains a symlinked directory: {child}")
            if not stat.S_ISDIR(observed.st_mode):
                raise BundleBuildError(f"target contains a non-directory node: {child}")
            relative = _safe_relative_path(
                child.relative_to(root).as_posix(), label="target inventory path"
            )
            collision_key = _portable_collision_key(relative)
            previous = portable_nodes.get(collision_key)
            if previous is not None and previous != relative:
                raise BundleBuildError(
                    f"target contains a portable path collision: {previous}, {relative}"
                )
            portable_nodes[collision_key] = relative
        for name in files:
            child = current_path / name
            try:
                observed = child.lstat()
            except OSError as exc:
                raise BundleBuildError(f"could not inspect target file {child}: {exc}") from exc
            if stat.S_ISLNK(observed.st_mode):
                raise BundleBuildError(f"target contains a symlink: {child}")
            if not stat.S_ISREG(observed.st_mode):
                raise BundleBuildError(f"target contains a non-regular file: {child}")
            relative = _safe_relative_path(
                child.relative_to(root).as_posix(), label="target inventory path"
            )
            collision_key = _portable_collision_key(relative)
            previous = portable_nodes.get(collision_key)
            if previous is not None and previous != relative:
                raise BundleBuildError(
                    f"target contains a portable path collision: {previous}, {relative}"
                )
            portable_nodes[collision_key] = relative
            if relative != PurePosixPath("manifest.json"):
                inventory.add(relative)
    return inventory


def _target_files(
    source_root: Path,
    *,
    expected_agents: frozenset[str],
    expected_skills: frozenset[str],
) -> tuple[list[BundleFile], bytes]:
    _require_directory(source_root / "targets", label="targets directory")
    target = source_root.joinpath(*TARGET_DIRECTORY.parts)
    _require_directory(target, label="OpenCode target directory")
    manifest_bytes, manifest_mode = _read_regular(
        target / "manifest.json",
        label="OpenCode target manifest",
        max_bytes=MAX_JSON_BYTES,
    )
    if manifest_mode != 0o644:
        raise BundleBuildError(
            "OpenCode target manifest mode must be 0644; "
            f"observed {manifest_mode:04o}"
        )
    manifest = _parse_json_object(manifest_bytes, label="OpenCode target manifest")
    if type(manifest.get("schemaVersion")) is not int or manifest["schemaVersion"] != 1:
        raise BundleBuildError("OpenCode target manifest schemaVersion must be 1")
    if manifest.get("target") != TARGET_NAME:
        raise BundleBuildError(f"OpenCode target manifest must name {TARGET_NAME!r}")
    raw_files = manifest.get("files")
    if not isinstance(raw_files, dict) or not raw_files:
        raise BundleBuildError("OpenCode target manifest files must be a non-empty object")
    if len(raw_files) + 2 > MAX_ARCHIVE_MEMBERS:
        raise BundleBuildError(
            "OpenCode target manifest exceeds the "
            f"{MAX_ARCHIVE_MEMBERS}-member safety limit"
        )

    declared: dict[PurePosixPath, tuple[str, int]] = {}
    portable_paths: dict[str, PurePosixPath] = {}
    for raw_path, raw_entry in raw_files.items():
        relative = _safe_relative_path(raw_path, label="target manifest path")
        if relative == PurePosixPath("manifest.json"):
            raise BundleBuildError("target manifest must not describe itself")
        if relative in declared:
            raise BundleBuildError(f"duplicate target manifest path: {relative}")
        collision_key = _portable_collision_key(relative)
        previous = portable_paths.get(collision_key)
        if previous is not None:
            raise BundleBuildError(
                f"portable target manifest path collision: {previous}, {relative}"
            )
        portable_paths[collision_key] = relative
        if not isinstance(raw_entry, dict) or set(raw_entry) != {"sha256", "mode"}:
            raise BundleBuildError(
                f"target manifest entry for {relative} must contain only sha256 and mode"
            )
        digest = raw_entry.get("sha256")
        raw_mode = raw_entry.get("mode")
        if not isinstance(digest, str) or DIGEST.fullmatch(digest) is None:
            raise BundleBuildError(f"invalid sha256 for target manifest entry {relative}")
        if not isinstance(raw_mode, str) or FILE_MODE.fullmatch(raw_mode) is None:
            raise BundleBuildError(f"invalid mode for target manifest entry {relative}")
        mode = int(raw_mode, 8)
        if mode not in ALLOWED_FILE_MODES:
            raise BundleBuildError(
                f"unsupported mode for target manifest entry {relative}: {raw_mode}"
            )
        declared[relative] = (digest, mode)

    expected_agent_paths = {
        PurePosixPath("agents") / f"{agent_id}.md"
        for agent_id in expected_agents
    }
    observed_agent_paths = {
        path for path in declared if path.parts[:1] == ("agents",)
    }
    if observed_agent_paths != expected_agent_paths:
        raise BundleBuildError(
            "OpenCode target agent roster differs from policy/content-lock.json"
        )
    expected_skill_paths = {
        PurePosixPath("skills") / skill_id / "SKILL.md"
        for skill_id in expected_skills
    }
    observed_skill_paths = {
        path
        for path in declared
        if len(path.parts) == 3
        and path.parts[0] == "skills"
        and path.name == "SKILL.md"
    }
    observed_skill_ids = {
        path.parts[1]
        for path in declared
        if len(path.parts) >= 2 and path.parts[0] == "skills"
    }
    if observed_skill_paths != expected_skill_paths or observed_skill_ids != expected_skills:
        raise BundleBuildError(
            "OpenCode target skill roster differs from policy/content-lock.json"
        )
    expected_command_paths = {
        PurePosixPath("commands") / f"{skill_id}.md"
        for skill_id in expected_skills
    }
    observed_command_paths = {
        path for path in declared if path.parts[:1] == ("commands",)
    }
    if observed_command_paths != expected_command_paths:
        raise BundleBuildError(
            "OpenCode target command roster differs from policy/content-lock.json"
        )
    expected_counts = {
        "agents": 7,
        "primaryAgents": 4,
        "subagents": 3,
        "skills": 43,
        "commands": 43,
    }
    if manifest.get("counts") != expected_counts:
        raise BundleBuildError("OpenCode target manifest has the wrong 7/43/43 counts")
    capabilities = manifest.get("skillCapabilities")
    expected_capabilities = {
        skill_id: (
            "overlay" if skill_id in OPENCODE_OVERLAY_SKILL_IDS else "native"
        )
        for skill_id in expected_skills
    }
    if capabilities != expected_capabilities:
        raise BundleBuildError(
            "OpenCode target skillCapabilities differ from the reviewed classification"
        )

    actual = _target_inventory(target)
    expected = set(declared)
    missing = sorted(expected - actual, key=str)
    extras = sorted(actual - expected, key=str)
    if missing:
        raise BundleBuildError(
            "OpenCode target is missing manifest files: " + ", ".join(map(str, missing))
        )
    if extras:
        raise BundleBuildError(
            "OpenCode target contains unmanifested files: " + ", ".join(map(str, extras))
        )

    result: list[BundleFile] = []
    for relative in sorted(declared, key=str):
        expected_digest, expected_mode = declared[relative]
        content, observed_mode = _read_regular(
            target.joinpath(*relative.parts), label=f"OpenCode target file {relative}"
        )
        observed_digest = _sha256(content)
        if observed_digest != expected_digest:
            raise BundleBuildError(
                f"checksum mismatch for OpenCode target file {relative}: "
                f"expected {expected_digest}, observed {observed_digest}"
            )
        if observed_mode != expected_mode:
            raise BundleBuildError(
                f"mode mismatch for OpenCode target file {relative}: "
                f"expected {expected_mode:04o}, observed {observed_mode:04o}"
            )
        result.append(
            BundleFile(TARGET_DIRECTORY / relative, content, expected_mode)
        )
    result.append(
        BundleFile(TARGET_DIRECTORY / "manifest.json", manifest_bytes, 0o644)
    )
    return result, manifest_bytes


def _focused_target_files(
    source_root: Path,
    *,
    directory: PurePosixPath,
    target_name: str,
    client: str,
    policy_sha256: str,
    canonical_source_sha256: str,
) -> tuple[list[BundleFile], bytes]:
    """Verify one generated focused projection before it enters the bundle."""

    target = source_root.joinpath(*directory.parts)
    _require_directory(target, label=f"{target_name} directory")
    manifest_bytes, manifest_mode = _read_regular(
        target / "manifest.json",
        label=f"{target_name} manifest",
        max_bytes=MAX_JSON_BYTES,
    )
    if manifest_mode != 0o644:
        raise BundleBuildError(
            f"{target_name} manifest mode must be 0644; observed {manifest_mode:04o}"
        )
    manifest = _parse_json_object(
        manifest_bytes, label=f"{target_name} manifest"
    )
    common_fields = {
        "schemaVersion",
        "target",
        "projection",
        "generator",
        "source",
        "modelSelection",
        "transformations",
        "counts",
        "agents",
        "skills",
        "files",
    }
    expected_fields = common_fields | ({"distribution"} if client == "copilot" else set())
    if set(manifest) != expected_fields:
        raise BundleBuildError(
            f"{target_name} manifest has unexpected or missing fields"
        )
    if (
        type(manifest.get("schemaVersion")) is not int
        or manifest["schemaVersion"] != 1
        or manifest.get("target") != target_name
        or manifest.get("projection") != "focused-context-v1"
        or manifest.get("modelSelection") != "inherit-provider-or-session"
    ):
        raise BundleBuildError(f"{target_name} manifest identity is invalid")
    if manifest.get("generator") != {
        "path": PROJECTION_GENERATOR_PATH.as_posix(),
        "version": 1,
    }:
        raise BundleBuildError(f"{target_name} generator contract is invalid")
    if manifest.get("agents") != list(FOCUSED_AGENT_IDS) or manifest.get(
        "skills"
    ) != list(FOCUSED_SKILL_IDS):
        raise BundleBuildError(f"{target_name} roster differs from focused policy")

    source = manifest.get("source")
    if not isinstance(source, dict):
        raise BundleBuildError(f"{target_name} source contract must be an object")
    if client == "opencode":
        expected_source = {
            "target": TARGET_DIRECTORY.as_posix(),
            "targetManifestSha256": canonical_source_sha256,
            "policy": FOCUSED_POLICY_PATH.as_posix(),
            "policySha256": policy_sha256,
        }
        expected_counts = {
            "agents": len(FOCUSED_AGENT_IDS),
            "skills": len(FOCUSED_SKILL_IDS),
            "commands": len(FOCUSED_SKILL_IDS),
        }
        expected_transformations = {
            "agentEscalation": "full-context-handoff",
            "excludedSkillReferences": "full-context-guidance",
            "skillPermissionEntriesRemoved": [
                "grillmester-doctor",
                "grillmester-grill-me",
                "grillmester-grill-with-docs",
                "grillmester-guided-review",
                "grillmester-handoff",
            ],
        }
    elif client == "copilot":
        expected_source = {
            "plugin": PLUGIN_DIRECTORY.as_posix(),
            "payloadManifest": COPILOT_FULL_MANIFEST_PATH.as_posix(),
            "payloadManifestSha256": canonical_source_sha256,
            "policy": FOCUSED_POLICY_PATH.as_posix(),
            "policySha256": policy_sha256,
        }
        expected_counts = {
            "agents": len(FOCUSED_AGENT_IDS),
            "skills": len(FOCUSED_SKILL_IDS),
        }
        expected_transformations = {
            "agentFrontmatterRemoved": ["model"],
            "agentEscalation": "full-context-handoff",
            "excludedSkillReferences": "full-context-guidance",
        }
        if manifest.get("distribution") != "private-cli-only":
            raise BundleBuildError(
                "focused Copilot target must remain private-cli-only"
            )
    else:  # pragma: no cover - fixed internal callers
        raise BundleBuildError(f"unsupported focused client {client!r}")
    if source != expected_source:
        raise BundleBuildError(f"{target_name} source hashes are stale")
    if manifest.get("counts") != expected_counts:
        raise BundleBuildError(f"{target_name} counts are invalid")
    if manifest.get("transformations") != expected_transformations:
        raise BundleBuildError(f"{target_name} transformations are invalid")

    raw_files = manifest.get("files")
    if not isinstance(raw_files, dict) or not raw_files:
        raise BundleBuildError(f"{target_name} files must be a non-empty object")
    if len(raw_files) + 2 > MAX_ARCHIVE_MEMBERS:
        raise BundleBuildError(
            f"{target_name} exceeds the {MAX_ARCHIVE_MEMBERS}-member safety limit"
        )
    declared: dict[PurePosixPath, tuple[str, int]] = {}
    portable_paths: dict[str, PurePosixPath] = {}
    for raw_path, raw_entry in raw_files.items():
        relative = _safe_relative_path(
            raw_path, label=f"{target_name} manifest path"
        )
        if relative == PurePosixPath("manifest.json"):
            raise BundleBuildError(f"{target_name} manifest must not describe itself")
        collision_key = _portable_collision_key(relative)
        previous = portable_paths.get(collision_key)
        if previous is not None:
            raise BundleBuildError(
                f"portable {target_name} path collision: {previous}, {relative}"
            )
        portable_paths[collision_key] = relative
        if not isinstance(raw_entry, dict) or set(raw_entry) != {"sha256", "mode"}:
            raise BundleBuildError(
                f"{target_name} entry {relative} must contain only sha256 and mode"
            )
        digest = raw_entry.get("sha256")
        raw_mode = raw_entry.get("mode")
        if not isinstance(digest, str) or DIGEST.fullmatch(digest) is None:
            raise BundleBuildError(f"invalid {target_name} sha256 for {relative}")
        if not isinstance(raw_mode, str) or FILE_MODE.fullmatch(raw_mode) is None:
            raise BundleBuildError(f"invalid {target_name} mode for {relative}")
        mode = int(raw_mode, 8)
        if mode not in ALLOWED_FILE_MODES:
            raise BundleBuildError(
                f"unsupported {target_name} mode for {relative}: {raw_mode}"
            )
        declared[relative] = (digest, mode)

    expected_agents = {
        PurePosixPath("agents")
        / (f"{agent}.md" if client == "opencode" else f"{agent}.agent.md")
        for agent in FOCUSED_AGENT_IDS
    }
    observed_agents = {
        path for path in declared if path.parts[:1] == ("agents",)
    }
    expected_skill_manifests = {
        PurePosixPath("skills") / skill / "SKILL.md"
        for skill in FOCUSED_SKILL_IDS
    }
    observed_skill_ids = {
        path.parts[1]
        for path in declared
        if len(path.parts) >= 2 and path.parts[0] == "skills"
    }
    observed_skill_manifests = {
        path
        for path in declared
        if len(path.parts) == 3
        and path.parts[0] == "skills"
        and path.name == "SKILL.md"
    }
    if observed_agents != expected_agents or (
        observed_skill_ids != set(FOCUSED_SKILL_IDS)
        or observed_skill_manifests != expected_skill_manifests
    ):
        raise BundleBuildError(f"{target_name} component inventory is invalid")
    observed_commands = {
        path for path in declared if path.parts[:1] == ("commands",)
    }
    expected_commands = (
        {
            PurePosixPath("commands") / f"{skill}.md"
            for skill in FOCUSED_SKILL_IDS
        }
        if client == "opencode"
        else set()
    )
    if observed_commands != expected_commands:
        raise BundleBuildError(f"{target_name} command inventory is invalid")

    actual = _target_inventory(target)
    if actual != set(declared):
        missing = sorted(set(declared) - actual, key=str)
        extras = sorted(actual - set(declared), key=str)
        detail = "; ".join(
            f"{label}: {', '.join(map(str, paths[:5]))}"
            for label, paths in (("missing", missing), ("extra", extras))
            if paths
        )
        raise BundleBuildError(
            f"{target_name} differs from its manifest" + (f"; {detail}" if detail else "")
        )

    result: list[BundleFile] = []
    for relative in sorted(declared, key=str):
        expected_digest, expected_mode = declared[relative]
        content, observed_mode = _read_regular(
            target.joinpath(*relative.parts), label=f"{target_name} file {relative}"
        )
        if _sha256(content) != expected_digest or observed_mode != expected_mode:
            raise BundleBuildError(
                f"{target_name} file differs from its manifest: {relative}"
            )
        result.append(BundleFile(directory / relative, content, expected_mode))
    result.append(BundleFile(directory / "manifest.json", manifest_bytes, 0o644))
    return result, manifest_bytes


def _portable_tree_files(root: Path, *, destination: PurePosixPath, label: str) -> list[BundleFile]:
    """Read one symlink-free portable tree without following directory aliases."""

    _require_directory(root, label=label)
    result: list[BundleFile] = []
    stack: list[tuple[Path, PurePosixPath]] = [(root, PurePosixPath())]
    portable_paths: dict[str, PurePosixPath] = {}
    while stack:
        directory, relative_directory = stack.pop()
        try:
            children = sorted(directory.iterdir(), key=lambda path: path.name, reverse=True)
        except OSError as exc:
            raise BundleBuildError(f"could not list {label} {directory}: {exc}") from exc
        for child in children:
            relative_name = _safe_relative_path(child.name, label=f"{label} path")
            relative = relative_directory / relative_name
            collision_key = _portable_collision_key(relative)
            previous = portable_paths.get(collision_key)
            if previous is not None and previous != relative:
                raise BundleBuildError(
                    f"portable {label} path collision: {previous}, {relative}"
                )
            portable_paths[collision_key] = relative
            try:
                observed = child.lstat()
            except OSError as exc:
                raise BundleBuildError(f"could not inspect {label} entry {child}: {exc}") from exc
            if stat.S_ISLNK(observed.st_mode):
                raise BundleBuildError(f"refusing symlinked {label} entry: {child}")
            if stat.S_ISDIR(observed.st_mode):
                stack.append((child, relative))
                continue
            if not stat.S_ISREG(observed.st_mode):
                raise BundleBuildError(f"{label} entry is not a regular file: {child}")
            content, mode = _read_regular(child, label=f"{label} file {relative}")
            if mode not in ALLOWED_FILE_MODES:
                raise BundleBuildError(
                    f"{label} file {relative} has unsupported mode {mode:04o}"
                )
            result.append(BundleFile(destination / relative, content, mode))
    result.sort(key=lambda entry: entry.path.as_posix())
    return result


def _plugin_files(
    source_root: Path,
    *,
    expected_agents: frozenset[str],
    expected_skills: frozenset[str],
) -> tuple[list[BundleFile], bytes]:
    files = _portable_tree_files(
        source_root.joinpath(*PLUGIN_DIRECTORY.parts),
        destination=PLUGIN_DIRECTORY,
        label="Copilot plugin",
    )
    relative_files = {
        entry.path.relative_to(PLUGIN_DIRECTORY): entry for entry in files
    }
    payload_manifest_entry = relative_files.get(PurePosixPath("manifest.json"))
    if payload_manifest_entry is None:
        raise BundleBuildError("Copilot full payload has no manifest.json")
    if payload_manifest_entry.mode != 0o644:
        raise BundleBuildError("Copilot full payload manifest mode must be 0644")
    payload_manifest = _parse_json_object(
        payload_manifest_entry.content, label="Copilot full payload manifest"
    )
    _require_exact_fields(
        payload_manifest,
        {
            "schemaVersion",
            "target",
            "generator",
            "counts",
            "agents",
            "skills",
            "files",
        },
        label="Copilot full payload manifest",
    )
    if (
        type(payload_manifest.get("schemaVersion")) is not int
        or payload_manifest["schemaVersion"] != 1
        or payload_manifest.get("target") != COPILOT_FULL_TARGET_NAME
        or payload_manifest.get("generator")
        != {
            "path": COPILOT_MANIFEST_GENERATOR_PATH.as_posix(),
            "version": 1,
        }
    ):
        raise BundleBuildError("Copilot full payload manifest identity is invalid")
    manifest_entry = relative_files.get(PurePosixPath("plugin.json"))
    if manifest_entry is None:
        raise BundleBuildError("Copilot plugin has no plugin.json")
    manifest = _parse_json_object(
        manifest_entry.content, label="Copilot plugin manifest"
    )
    if manifest.get("name") != "grillmester":
        raise BundleBuildError("Copilot plugin manifest must name grillmester")
    if not isinstance(manifest.get("version"), str) or not manifest["version"].strip():
        raise BundleBuildError("Copilot plugin manifest needs a version")
    observed_agents = {
        path.name.removesuffix(".agent.md")
        for path in relative_files
        if len(path.parts) == 2
        and path.parts[0] == "agents"
        and path.name.endswith(".agent.md")
    }
    observed_agent_entries = {
        path for path in relative_files if path.parts[:1] == ("agents",)
    }
    expected_agent_entries = {
        PurePosixPath("agents") / f"{agent_id}.agent.md"
        for agent_id in expected_agents
    }
    if observed_agents != expected_agents or observed_agent_entries != expected_agent_entries:
        raise BundleBuildError(
            "Copilot plugin agent roster differs from policy/content-lock.json"
        )
    observed_skill_ids = {
        path.parts[1]
        for path in relative_files
        if len(path.parts) >= 2 and path.parts[0] == "skills"
    }
    observed_skill_manifests = {
        path
        for path in relative_files
        if len(path.parts) == 3
        and path.parts[0] == "skills"
        and path.name == "SKILL.md"
    }
    expected_skill_manifests = {
        PurePosixPath("skills") / skill_id / "SKILL.md"
        for skill_id in expected_skills
    }
    if (
        observed_skill_ids != expected_skills
        or observed_skill_manifests != expected_skill_manifests
    ):
        raise BundleBuildError(
            "Copilot plugin skill roster differs from policy/content-lock.json"
        )
    if payload_manifest.get("agents") != sorted(expected_agents) or (
        payload_manifest.get("skills") != sorted(expected_skills)
    ):
        raise BundleBuildError(
            "Copilot full payload manifest roster differs from policy/content-lock.json"
        )
    if payload_manifest.get("counts") != {
        "agents": len(expected_agents),
        "skills": len(expected_skills),
    }:
        raise BundleBuildError("Copilot full payload manifest counts are invalid")
    declared_files = payload_manifest.get("files")
    if not isinstance(declared_files, dict) or not declared_files:
        raise BundleBuildError("Copilot full payload manifest files are invalid")
    actual_payload_paths = set(relative_files) - {PurePosixPath("manifest.json")}
    declared_paths: set[PurePosixPath] = set()
    portable_paths: set[str] = set()
    for raw_relative, raw_contract in declared_files.items():
        relative = _safe_relative_path(
            raw_relative, label="Copilot full payload manifest path"
        )
        if relative == PurePosixPath("manifest.json"):
            raise BundleBuildError("Copilot full payload manifest must not describe itself")
        portable = _portable_collision_key(relative)
        if portable in portable_paths:
            raise BundleBuildError(
                f"portable Copilot full payload manifest path collision: {relative}"
            )
        portable_paths.add(portable)
        contract = _require_exact_fields(
            raw_contract,
            {"sha256", "mode"},
            label=f"Copilot full payload contract {relative}",
        )
        digest = _require_digest(
            contract["sha256"],
            DIGEST,
            algorithm="SHA-256",
            label=f"Copilot full payload digest {relative}",
        )
        raw_mode = contract["mode"]
        if not isinstance(raw_mode, str) or FILE_MODE.fullmatch(raw_mode) is None:
            raise BundleBuildError(
                f"Copilot full payload mode is invalid for {relative}"
            )
        mode = int(raw_mode, 8)
        if mode not in ALLOWED_FILE_MODES:
            raise BundleBuildError(
                f"Copilot full payload mode is unsupported for {relative}"
            )
        entry = relative_files.get(relative)
        if entry is None or _sha256(entry.content) != digest or entry.mode != mode:
            raise BundleBuildError(
                f"Copilot full payload differs from its manifest: {relative}"
            )
        declared_paths.add(relative)
    if actual_payload_paths != declared_paths:
        missing = sorted(actual_payload_paths - declared_paths, key=str)
        extra = sorted(declared_paths - actual_payload_paths, key=str)
        details = []
        if missing:
            details.append("unmanifested " + ", ".join(map(str, missing[:5])))
        if extra:
            details.append("missing " + ", ".join(map(str, extra[:5])))
        raise BundleBuildError(
            "Copilot full payload tree differs from its manifest: "
            + "; ".join(details)
        )
    return files, payload_manifest_entry.content


def _validate_python_literals(
    content: bytes,
    *,
    path: PurePosixPath,
    label: str,
    expected: dict[str, object],
) -> None:
    try:
        tree = ast.parse(content.decode("utf-8"), filename=path.as_posix())
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise BundleBuildError(f"{label} is not valid UTF-8 Python: {exc}") from exc
    observed: dict[str, list[object]] = {name: [] for name in expected}
    for statement in tree.body:
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id in observed
        ):
            try:
                observed[statement.targets[0].id].append(ast.literal_eval(statement.value))
            except (ValueError, TypeError) as exc:
                raise BundleBuildError(
                    f"{label} {statement.targets[0].id} must be a literal"
                ) from exc
    for name, expected_value in expected.items():
        if observed[name] != [expected_value]:
            raise BundleBuildError(
                f"{label} must pin {name}={expected_value!r}"
            )


def _release_test_contract(source_root: Path) -> dict[str, Any]:
    content, mode = _read_regular(
        source_root.joinpath(*RELEASE_TEST_BASELINE_PATH.parts),
        label="release-test baseline contract",
        max_bytes=MAX_JSON_BYTES,
    )
    if mode != 0o644:
        raise BundleBuildError(
            "release-test baseline contract source mode must be 0644; "
            f"observed {mode:04o}"
        )
    try:
        tree = ast.parse(
            content.decode("utf-8"), filename=RELEASE_TEST_BASELINE_PATH.as_posix()
        )
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise BundleBuildError(
            f"release-test baseline contract is not valid UTF-8 Python: {exc}"
        ) from exc
    assignments: list[object] = []
    for statement in tree.body:
        if (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == "CONTRACT"
            and statement.value is not None
        ):
            try:
                assignments.append(ast.literal_eval(statement.value))
            except (ValueError, TypeError) as exc:
                raise BundleBuildError(
                    "release-test baseline CONTRACT must be one literal"
                ) from exc
    if len(assignments) != 1 or not isinstance(assignments[0], dict):
        raise BundleBuildError(
            "release-test baseline must define exactly one literal CONTRACT"
        )
    contract = assignments[0]
    if set(contract) != {"schemaVersion", "standardSupport", "releaseTest", "artifacts"}:
        raise BundleBuildError("release-test baseline contract fields differ")
    if type(contract.get("schemaVersion")) is not int or contract["schemaVersion"] != 1:
        raise BundleBuildError("release-test baseline schemaVersion must be 1")
    standard = contract.get("standardSupport")
    tested = contract.get("releaseTest")
    artifacts = contract.get("artifacts")
    if not isinstance(standard, dict) or set(standard) != {
        "opencodeMinimum",
        "copilotMinimum",
        "cpltMinimum",
    }:
        raise BundleBuildError("release-test standard support fields differ")
    if not isinstance(tested, dict) or set(tested) != {
        "opencodeVersion",
        "copilotVersion",
        "cpltRelease",
    }:
        raise BundleBuildError("release-test client baseline fields differ")
    if not isinstance(artifacts, dict) or not artifacts:
        raise BundleBuildError("release-test artifact roster must not be empty")
    values = (*standard.values(), *tested.values())
    if any(not isinstance(value, str) or not value for value in values):
        raise BundleBuildError("release-test client versions must be non-empty strings")
    return contract


def _launcher_file(
    source_root: Path, *, standard_support: Mapping[str, str]
) -> BundleFile:
    content, mode = _read_regular(
        source_root.joinpath(*LAUNCHER_PATH.parts), label="Grillmester launcher"
    )
    if mode != 0o644:
        raise BundleBuildError(
            f"Grillmester launcher source mode must be 0644; observed {mode:04o}"
        )
    _validate_python_literals(
        content,
        path=LAUNCHER_PATH,
        label="Grillmester launcher",
        expected={
            "MINIMUM_OPENCODE_VERSION_TEXT": standard_support["opencodeMinimum"],
            "MINIMUM_COPILOT_VERSION": tuple(
                int(part) for part in standard_support["copilotMinimum"].split(".")
            ),
            "SUPPORTED_CPLT_RELEASE": standard_support["cpltMinimum"],
        },
    )
    return BundleFile(LAUNCHER_PATH, content, 0o755)


def _python_support_file(
    source_root: Path,
    path: PurePosixPath,
    *,
    label: str,
    expected_literals: dict[str, object] | None = None,
) -> BundleFile:
    content, mode = _read_regular(source_root.joinpath(*path.parts), label=label)
    if mode != 0o644:
        raise BundleBuildError(f"{label} source mode must be 0644; observed {mode:04o}")
    _validate_python_literals(
        content,
        path=path,
        label=label,
        expected={} if expected_literals is None else expected_literals,
    )
    return BundleFile(path, content, 0o644)


def _validate_archive_path_collisions(files: list[BundleFile]) -> None:
    portable_nodes: dict[str, PurePosixPath] = {}
    for entry in files:
        current = ARCHIVE_ROOT / entry.path
        while current != PurePosixPath("."):
            key = _portable_collision_key(current)
            previous = portable_nodes.get(key)
            if previous is not None and previous != current:
                raise BundleBuildError(
                    f"portable archive path collision: {previous}, {current}"
                )
            portable_nodes[key] = current
            current = current.parent


def collect_bundle_files(source_root: Path, source_sha: str) -> list[BundleFile]:
    """Validate all source inputs and return the complete canonical file set."""

    if FULL_SHA.fullmatch(source_sha) is None:
        raise BundleBuildError("source SHA must be exactly 40 lowercase hex digits")
    source_root = source_root.expanduser().absolute()
    _require_directory(source_root, label="source root")
    _require_directory(source_root / "scripts", label="scripts directory")

    release_test_contract = _release_test_contract(source_root)
    standard_support = release_test_contract["standardSupport"]
    release_test = release_test_contract["releaseTest"]

    support_files = _distribution_support_files(source_root)
    content_lock_file = next(
        entry for entry in support_files if entry.path == CONTENT_LOCK_PATH
    )
    content_lock = _parse_json_object(
        content_lock_file.content, label="content lock"
    )
    expected_agents = frozenset(content_lock["agents"])
    expected_skills = frozenset(content_lock["skills"])
    if any(not isinstance(value, str) or not value for value in expected_agents):
        raise BundleBuildError("content lock contains an invalid agent ID")
    if any(not isinstance(value, str) or not value for value in expected_skills):
        raise BundleBuildError("content lock contains an invalid skill ID")
    target_files, target_manifest = _target_files(
        source_root,
        expected_agents=expected_agents,
        expected_skills=expected_skills,
    )
    focused_policy_content, focused_policy_mode = _read_regular(
        source_root.joinpath(*FOCUSED_POLICY_PATH.parts),
        label="focused context policy",
        max_bytes=MAX_JSON_BYTES,
    )
    if focused_policy_mode != 0o644:
        raise BundleBuildError(
            "focused context policy mode must be 0644; "
            f"observed {focused_policy_mode:04o}"
        )
    focused_policy = _parse_json_object(
        focused_policy_content, label="focused context policy"
    )
    expected_focused_policy = {
        "schemaVersion": 1,
        "projection": "focused-context-v1",
        "sources": {
            "plugin": PLUGIN_DIRECTORY.as_posix(),
            "opencode": TARGET_DIRECTORY.as_posix(),
        },
        "outputs": {
            "opencode": FOCUSED_OPENCODE_DIRECTORY.as_posix(),
            "copilotCli": FOCUSED_COPILOT_DIRECTORY.as_posix(),
        },
        "agents": list(FOCUSED_AGENT_IDS),
        "skills": list(FOCUSED_SKILL_IDS),
        "fullContextHandoff": {
            "status": "NEEDS_FULL_CONTEXT",
            "command": "grillmester local --full",
        },
        "copilotCli": {"removeAgentFrontmatterFields": ["model"]},
    }
    if focused_policy != expected_focused_policy:
        raise BundleBuildError("focused context policy differs from the reviewed v1 contract")
    policy_sha256 = _sha256(focused_policy_content)
    plugin_files, copilot_full_manifest = _plugin_files(
        source_root,
        expected_agents=expected_agents,
        expected_skills=expected_skills,
    )
    focused_opencode_files, focused_opencode_manifest = _focused_target_files(
        source_root,
        directory=FOCUSED_OPENCODE_DIRECTORY,
        target_name=FOCUSED_OPENCODE_TARGET_NAME,
        client="opencode",
        policy_sha256=policy_sha256,
        canonical_source_sha256=_sha256(target_manifest),
    )
    focused_copilot_files, focused_copilot_manifest = _focused_target_files(
        source_root,
        directory=FOCUSED_COPILOT_DIRECTORY,
        target_name=FOCUSED_COPILOT_TARGET_NAME,
        client="copilot",
        policy_sha256=policy_sha256,
        canonical_source_sha256=_sha256(copilot_full_manifest),
    )
    files = [
        _launcher_file(source_root, standard_support=standard_support),
        _python_support_file(
            source_root, LOCAL_LAUNCHER_PATH, label="Grillmester local launcher"
        ),
        BundleFile(FOCUSED_POLICY_PATH, focused_policy_content, 0o644),
    ]
    files.extend(support_files)
    files.extend(plugin_files)
    files.extend(target_files)
    files.extend(focused_opencode_files)
    files.extend(focused_copilot_files)
    files.sort(key=lambda entry: entry.path.as_posix())
    aggregate_size = sum(len(entry.content) for entry in files)
    if aggregate_size > MAX_DISTRIBUTION_BYTES:
        raise BundleBuildError(
            f"bundle inputs exceed the {MAX_DISTRIBUTION_BYTES}-byte safety limit"
        )

    paths = [entry.path for entry in files]
    if len(paths) != len(set(paths)):  # pragma: no cover - fixed namespaces
        raise BundleBuildError("bundle inputs produce duplicate archive paths")
    file_manifest = {
        entry.path.as_posix(): {
            "sha256": _sha256(entry.content),
            "mode": f"{entry.mode:04o}",
        }
        for entry in files
    }
    distribution_manifest = {
        "schemaVersion": 1,
        "sourceSha": source_sha,
        "distribution": DISTRIBUTION_NAME,
        "releaseTest": {
            "opencodeVersion": release_test["opencodeVersion"],
            "copilotVersion": release_test["copilotVersion"],
            "cpltRelease": release_test["cpltRelease"],
        },
        "targetManifestSha256": _sha256(target_manifest),
        "copilotFullManifestSha256": _sha256(copilot_full_manifest),
        "focusedOpenCodeManifestSha256": _sha256(focused_opencode_manifest),
        "focusedCopilotManifestSha256": _sha256(focused_copilot_manifest),
        "focusedContextPolicySha256": policy_sha256,
        "files": file_manifest,
    }
    manifest_bytes = (
        json.dumps(distribution_manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if len(manifest_bytes) > MAX_JSON_BYTES:
        raise BundleBuildError(
            "distribution manifest exceeds the "
            f"{MAX_JSON_BYTES}-byte JSON safety limit"
        )
    if aggregate_size + len(manifest_bytes) > MAX_DISTRIBUTION_BYTES:
        raise BundleBuildError(
            "bundle plus distribution manifest exceeds the "
            f"{MAX_DISTRIBUTION_BYTES}-byte safety limit"
        )
    files.append(BundleFile(OUTER_MANIFEST, manifest_bytes, 0o644))
    files.sort(key=lambda entry: entry.path.as_posix())
    _validate_archive_path_collisions(files)
    for entry in files:
        _require_ustar_path(ARCHIVE_ROOT / entry.path)
    return files


def _tar_info(name: str, *, mode: int, directory: bool, size: int = 0) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name + ("/" if directory else ""))
    info.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
    info.mode = mode
    info.size = 0 if directory else size
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.devmajor = 0
    info.devminor = 0
    return info


def _write_archive(output: io.BufferedWriter, files: list[BundleFile]) -> None:
    members: dict[PurePosixPath, BundleFile | None] = {ARCHIVE_ROOT: None}
    for entry in files:
        archive_path = ARCHIVE_ROOT / entry.path
        parent = archive_path.parent
        while parent != PurePosixPath("."):
            members.setdefault(parent, None)
            parent = parent.parent
        members[archive_path] = entry
    if len(members) > MAX_ARCHIVE_MEMBERS:
        raise BundleBuildError(
            f"archive exceeds the {MAX_ARCHIVE_MEMBERS}-member safety limit"
        )

    with gzip.GzipFile(
        filename="", mode="wb", compresslevel=9, fileobj=output, mtime=0
    ) as compressed:
        with tarfile.open(
            fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT
        ) as archive:
            for path in sorted(members, key=lambda item: item.as_posix()):
                entry = members[path]
                if entry is None:
                    archive.addfile(
                        _tar_info(path.as_posix(), mode=0o755, directory=True)
                    )
                else:
                    archive.addfile(
                        _tar_info(
                            path.as_posix(),
                            mode=entry.mode,
                            directory=False,
                            size=len(entry.content),
                        ),
                        io.BytesIO(entry.content),
                    )


def _canonical_future_path(path: Path) -> Path:
    absolute = path.expanduser().absolute()
    missing: list[str] = []
    ancestor = absolute
    while not ancestor.exists() and not ancestor.is_symlink():
        missing.append(ancestor.name)
        parent = ancestor.parent
        if parent == ancestor:  # pragma: no cover - root always exists
            break
        ancestor = parent
    try:
        resolved = ancestor.resolve(strict=True)
    except OSError as exc:
        raise BundleBuildError(f"could not resolve output path {path}: {exc}") from exc
    for part in reversed(missing):
        resolved /= part
    return resolved


def _portable_absolute_path_key(path: Path) -> tuple[str, ...]:
    """Match path aliases on case-insensitive, Unicode-normalizing filesystems."""

    return tuple(
        unicodedata.normalize("NFC", part).casefold() for part in path.parts
    )


def _is_within(path: Path, parent: Path) -> bool:
    path_key = _portable_absolute_path_key(path)
    parent_key = _portable_absolute_path_key(parent)
    return (
        len(path_key) >= len(parent_key)
        and path_key[: len(parent_key)] == parent_key
    )


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise BundleBuildError(f"could not durably sync output directory {path}: {exc}") from exc


def build_bundle(source_root: Path, source_sha: str, output: Path) -> None:
    """Build one byte-reproducible tar.gz, replacing only the requested output."""

    raw_source_root = source_root.expanduser().absolute()
    _require_directory(raw_source_root, label="source root")
    try:
        source_root = raw_source_root.resolve(strict=True)
    except OSError as exc:
        raise BundleBuildError(f"could not resolve source root {raw_source_root}: {exc}") from exc
    files = collect_bundle_files(source_root, source_sha)
    output = output.expanduser().absolute()
    if output.is_symlink():
        raise BundleBuildError(f"refusing to replace symlinked output: {output}")
    output = _canonical_future_path(output)
    if _is_within(output, source_root):
        raise BundleBuildError("output must be outside the immutable source root")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output = _canonical_future_path(output)
        if _is_within(output, source_root):
            raise BundleBuildError("output must be outside the immutable source root")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                os.fchmod(stream.fileno(), 0o644)
                _write_archive(stream, files)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, output)
            _fsync_directory(output.parent)
        finally:
            temporary.unlink(missing_ok=True)
    except BundleBuildError:
        raise
    except OSError as exc:
        raise BundleBuildError(f"could not write bundle {output}: {exc}") from exc


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    options = parse_arguments(arguments)
    try:
        build_bundle(options.source_root, options.source_sha, options.output)
    except BundleBuildError as exc:
        print(f"Terminal bundle build failed: {exc}", file=sys.stderr)
        return 2
    print(options.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
