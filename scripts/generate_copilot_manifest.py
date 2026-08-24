#!/usr/bin/env python3
"""Generate the deterministic manifest for the full Copilot plugin payload."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIRECTORY = Path("plugin")
MANIFEST_NAME = "manifest.json"
TARGET_NAME = "copilot-full-v1"
GENERATOR_VERSION = 1
ALLOWED_FILE_MODES = frozenset({0o644, 0o755})
MAX_FILE_BYTES = 5_000_000
MAX_PAYLOAD_FILES = 10_000
COMPONENT_ID = re.compile(r"^[a-z][a-z0-9-]*$")


class CopilotManifestError(ValueError):
    """Raised when the canonical Copilot payload cannot be manifested safely."""


PayloadFile = tuple[bytes, int]


def _portable_collision_key(path: PurePosixPath) -> str:
    return unicodedata.normalize("NFC", path.as_posix()).casefold()


def _read_regular(path: Path, *, label: str) -> PayloadFile:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as exc:
        raise CopilotManifestError(f"missing {label}: {path}") from exc
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise CopilotManifestError(f"refusing symlinked {label}: {path}") from exc
        raise CopilotManifestError(f"could not open {label} {path}: {exc}") from exc
    try:
        observed = os.fstat(descriptor)
        if not stat.S_ISREG(observed.st_mode):
            raise CopilotManifestError(f"{label} is not a regular file: {path}")
        if observed.st_size > MAX_FILE_BYTES:
            raise CopilotManifestError(
                f"{label} exceeds the {MAX_FILE_BYTES}-byte safety limit: {path}"
            )
        with os.fdopen(descriptor, "rb", closefd=True) as source:
            descriptor = -1
            content = source.read(MAX_FILE_BYTES + 1)
            after_read = os.fstat(source.fileno())
        if len(content) > MAX_FILE_BYTES:
            raise CopilotManifestError(
                f"{label} exceeds the {MAX_FILE_BYTES}-byte safety limit: {path}"
            )
        stable_fields = (
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
            for field in stable_fields
        ):
            raise CopilotManifestError(f"{label} changed while being read: {path}")
        mode = stat.S_IMODE(observed.st_mode)
        if mode not in ALLOWED_FILE_MODES:
            raise CopilotManifestError(
                f"{label} has unsupported mode {mode:04o}: {path}"
            )
        return content, mode
    except OSError as exc:
        raise CopilotManifestError(f"could not read {label} {path}: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def collect_payload_files(plugin_root: Path) -> dict[str, PayloadFile]:
    try:
        root_stat = plugin_root.lstat()
    except FileNotFoundError as exc:
        raise CopilotManifestError(
            f"Copilot plugin directory does not exist: {plugin_root}"
        ) from exc
    except OSError as exc:
        raise CopilotManifestError(
            f"could not inspect Copilot plugin directory {plugin_root}: {exc}"
        ) from exc
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise CopilotManifestError(
            f"Copilot plugin path is not a regular directory: {plugin_root}"
        )

    files: dict[str, PayloadFile] = {}
    portable_paths: dict[str, str] = {}
    pending = [plugin_root]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise CopilotManifestError(
                f"could not list Copilot plugin directory {directory}: {exc}"
            ) from exc
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(plugin_root).as_posix()
            portable = PurePosixPath(relative)
            if (
                portable.is_absolute()
                or portable.as_posix() != relative
                or any(part in ("", ".", "..") for part in portable.parts)
            ):
                raise CopilotManifestError(
                    f"Copilot payload path is not normalized: {relative!r}"
                )
            collision_key = _portable_collision_key(portable)
            previous = portable_paths.get(collision_key)
            if previous is not None and previous != relative:
                raise CopilotManifestError(
                    f"portable Copilot payload path collision: {previous}, {relative}"
                )
            portable_paths[collision_key] = relative
            if entry.is_symlink():
                raise CopilotManifestError(
                    f"Copilot payload contains symlink: {relative}"
                )
            if entry.is_dir(follow_symlinks=False):
                pending.append(path)
                continue
            if not entry.is_file(follow_symlinks=False):
                raise CopilotManifestError(
                    f"Copilot payload contains non-regular node: {relative}"
                )
            if relative == MANIFEST_NAME:
                # The manifest cannot bind its own digest. It is validated separately.
                continue
            files[relative] = _read_regular(
                path, label=f"Copilot payload file {relative}"
            )
            if len(files) > MAX_PAYLOAD_FILES:
                raise CopilotManifestError(
                    f"Copilot payload exceeds the {MAX_PAYLOAD_FILES}-file safety limit"
                )
    if not files:
        raise CopilotManifestError("Copilot payload contains no files")
    return dict(sorted(files.items()))


def _parse_plugin_manifest(content: bytes) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise CopilotManifestError(
                    f"plugin/plugin.json contains duplicate key {key!r}"
                )
            value[key] = item
        return value

    def reject_nonstandard_constant(value: str) -> None:
        raise CopilotManifestError(
            f"plugin/plugin.json contains non-standard JSON constant {value!r}"
        )

    try:
        value = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonstandard_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CopilotManifestError("plugin/plugin.json is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict) or value.get("name") != "grillmester":
        raise CopilotManifestError("plugin/plugin.json must name grillmester")
    if not isinstance(value.get("version"), str) or not value["version"].strip():
        raise CopilotManifestError("plugin/plugin.json must contain a version")
    return value


def build_manifest(root: Path) -> bytes:
    plugin_root = root.resolve() / PLUGIN_DIRECTORY
    files = collect_payload_files(plugin_root)
    plugin_json = files.get("plugin.json")
    if plugin_json is None:
        raise CopilotManifestError("Copilot payload is missing plugin.json")
    _parse_plugin_manifest(plugin_json[0])

    agents = sorted(
        PurePosixPath(path).name.removesuffix(".agent.md")
        for path in files
        if len(PurePosixPath(path).parts) == 2
        and PurePosixPath(path).parts[0] == "agents"
        and path.endswith(".agent.md")
    )
    skills = sorted(
        {
            PurePosixPath(path).parts[1]
            for path in files
            if len(PurePosixPath(path).parts) >= 3
            and PurePosixPath(path).parts[0] == "skills"
        }
    )
    if (
        not agents
        or not skills
        or any(COMPONENT_ID.fullmatch(component) is None for component in (*agents, *skills))
    ):
        raise CopilotManifestError("Copilot payload has an invalid agent or skill roster")
    expected_agent_paths = {f"agents/{agent}.agent.md" for agent in agents}
    actual_agent_paths = {path for path in files if path.startswith("agents/")}
    if actual_agent_paths != expected_agent_paths:
        raise CopilotManifestError(
            "Copilot agents directory may contain only <agent-id>.agent.md files"
        )
    missing_skill_manifests = [
        skill for skill in skills if f"skills/{skill}/SKILL.md" not in files
    ]
    if missing_skill_manifests:
        raise CopilotManifestError(
            "Copilot skills are missing SKILL.md: "
            + ", ".join(missing_skill_manifests)
        )

    manifest = {
        "schemaVersion": 1,
        "target": TARGET_NAME,
        "generator": {
            "path": "scripts/generate_copilot_manifest.py",
            "version": GENERATOR_VERSION,
        },
        "counts": {"agents": len(agents), "skills": len(skills)},
        "agents": agents,
        "skills": skills,
        "files": {
            path: {
                "sha256": hashlib.sha256(content).hexdigest(),
                "mode": f"{mode:04o}",
            }
            for path, (content, mode) in files.items()
        },
    }
    return (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def compare_manifest(root: Path, expected: bytes) -> list[str]:
    manifest_path = root.resolve() / PLUGIN_DIRECTORY / MANIFEST_NAME
    try:
        observed = manifest_path.lstat()
    except FileNotFoundError:
        return [f"missing generated file: {PLUGIN_DIRECTORY / MANIFEST_NAME}"]
    except OSError as exc:
        return [f"could not inspect generated Copilot manifest: {exc}"]
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
        return [f"generated Copilot manifest is not a regular file: {manifest_path}"]
    differences: list[str] = []
    try:
        actual = manifest_path.read_bytes()
    except OSError as exc:
        return [f"could not read generated Copilot manifest: {exc}"]
    if actual != expected:
        differences.append("generated Copilot full payload manifest is stale")
    mode = stat.S_IMODE(observed.st_mode)
    if mode != 0o644:
        differences.append(
            f"generated Copilot manifest mode differs: actual={mode:04o}, expected=0644"
        )
    return differences


def update_manifest(root: Path, expected: bytes) -> bool:
    plugin_root = root.resolve() / PLUGIN_DIRECTORY
    manifest_path = plugin_root / MANIFEST_NAME
    differences = compare_manifest(root, expected)
    if not differences:
        return False
    if manifest_path.exists() and (
        manifest_path.is_symlink() or not manifest_path.is_file()
    ):
        raise CopilotManifestError(
            f"generated Copilot manifest is not a regular file: {manifest_path}"
        )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".copilot-manifest-", dir=plugin_root
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            os.fchmod(output.fileno(), 0o644)
            output.write(expected)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, manifest_path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return True


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the manifest is stale")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    try:
        expected = build_manifest(root)
        differences = compare_manifest(root, expected)
        if args.check:
            if differences:
                raise CopilotManifestError("; ".join(differences))
            print(f"Copilot full payload manifest is current: {root / PLUGIN_DIRECTORY / MANIFEST_NAME}")
        else:
            changed = update_manifest(root, expected)
            state = "Generated" if changed else "Already current"
            print(f"{state} Copilot full payload manifest: {root / PLUGIN_DIRECTORY / MANIFEST_NAME}")
    except (OSError, CopilotManifestError, ValueError) as exc:
        print(f"Copilot manifest generation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
