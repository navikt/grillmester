#!/usr/bin/env python3
"""Generate the nav-pilot agentpakke contract from canonical Grillmester data."""

from __future__ import annotations

import argparse
import ast
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence


OUTPUT = Path(".nav-pilot/agentpakke.json")
MAX_JSON_BYTES = 4 * 1024 * 1024
EXPECTED_PAYLOAD_TARGETS = {
    "plugin": "copilot-full-v1",
    "targets/copilot-cli-focused-v1": "copilot-cli-focused-v1",
    "targets/opencode-v1": "opencode-v1",
    "targets/opencode-v1-focused": "opencode-v1-focused",
}


class AgentpakkeManifestError(RuntimeError):
    """Raised when canonical inputs cannot produce a trustworthy manifest."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AgentpakkeManifestError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise AgentpakkeManifestError(f"non-standard JSON constant: {value}")


def _read_regular_bytes(path: Path, *, maximum: int = MAX_JSON_BYTES) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise AgentpakkeManifestError(
            f"cannot open regular file {path}: {error}"
        ) from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise AgentpakkeManifestError(f"expected a regular file: {path}")
        if before.st_size > maximum:
            raise AgentpakkeManifestError(f"file exceeds {maximum} bytes: {path}")
        data = bytearray()
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > maximum:
                raise AgentpakkeManifestError(f"file exceeds {maximum} bytes: {path}")
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise AgentpakkeManifestError(f"file changed while it was read: {path}")
        return bytes(data)
    finally:
        os.close(descriptor)


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            _read_regular_bytes(path).decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AgentpakkeManifestError(f"invalid UTF-8 JSON in {path}: {error}") from error
    if not isinstance(value, dict):
        raise AgentpakkeManifestError(f"expected a JSON object: {path}")
    return value


def _literal_assignment(path: Path, name: str) -> Any:
    try:
        tree = ast.parse(
            _read_regular_bytes(path).decode("utf-8"), filename=str(path)
        )
    except (UnicodeDecodeError, SyntaxError) as error:
        raise AgentpakkeManifestError(f"cannot parse {path}: {error}") from error
    for node in tree.body:
        target_name: str | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                target_name = target.id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
        if target_name == name:
            value_node = node.value
            if value_node is None:
                break
            try:
                return ast.literal_eval(value_node)
            except (TypeError, ValueError) as error:
                raise AgentpakkeManifestError(
                    f"{name} in {path} must remain a literal"
                ) from error
    raise AgentpakkeManifestError(f"missing literal assignment {name} in {path}")


def _public_agents(root: Path) -> list[str]:
    launcher_agents = _literal_assignment(
        root / "scripts/grillmester.py", "PUBLIC_AGENTS"
    )
    if not isinstance(launcher_agents, tuple) or not all(
        isinstance(agent, str) and agent for agent in launcher_agents
    ):
        raise AgentpakkeManifestError(
            "PUBLIC_AGENTS must be a non-empty tuple of strings"
        )
    if len(set(launcher_agents)) != len(launcher_agents):
        raise AgentpakkeManifestError("PUBLIC_AGENTS must not contain duplicates")
    content_lock = _load_json_object(root / "policy/content-lock.json")
    locked_agents = content_lock.get("agents")
    if not isinstance(locked_agents, dict):
        raise AgentpakkeManifestError("content-lock agents must be an object")
    invocable = {
        agent_id
        for agent_id, metadata in locked_agents.items()
        if isinstance(agent_id, str)
        and isinstance(metadata, dict)
        and metadata.get("user-invocable") is True
    }
    if set(launcher_agents) != invocable:
        raise AgentpakkeManifestError(
            "PUBLIC_AGENTS differs from user-invocable agents in policy/content-lock.json"
        )
    return list(launcher_agents)


def _compatibility_ranges(root: Path) -> tuple[str, str]:
    contract = _literal_assignment(root / "scripts/release_test_baseline.py", "CONTRACT")
    if not isinstance(contract, dict):
        raise AgentpakkeManifestError("release-test CONTRACT must be an object literal")
    support = contract.get("standardSupport")
    if not isinstance(support, dict):
        raise AgentpakkeManifestError("release-test standardSupport must be an object")
    opencode_minimum = support.get("opencodeMinimum")
    copilot_minimum = support.get("copilotMinimum")
    for label, value in (
        ("opencodeMinimum", opencode_minimum),
        ("copilotMinimum", copilot_minimum),
    ):
        if (
            not isinstance(value, str)
            or len(value.split(".")) != 3
            or not all(
                part.isdigit() and (part == "0" or not part.startswith("0"))
                for part in value.split(".")
            )
        ):
            raise AgentpakkeManifestError(
                f"standardSupport.{label} must be a semantic version"
            )
        parts = tuple(int(part) for part in value.split("."))
        if parts[0] != 1:
            raise AgentpakkeManifestError(
                f"standardSupport.{label} must stay within reviewed major version 1"
            )
    return f">={copilot_minimum},<2", f">={opencode_minimum},<2"


def _validate_payloads(root: Path) -> None:
    for relative, expected_target in EXPECTED_PAYLOAD_TARGETS.items():
        payload_path = root / relative
        current = root
        for component in Path(relative).parts:
            current /= component
            try:
                current_stat = current.lstat()
            except OSError as error:
                raise AgentpakkeManifestError(
                    f"missing payload path {current}"
                ) from error
            if stat.S_ISLNK(current_stat.st_mode):
                raise AgentpakkeManifestError(
                    f"payload path contains a symlink: {current}"
                )
        if not stat.S_ISDIR(payload_path.lstat().st_mode):
            raise AgentpakkeManifestError(f"payload must be a directory: {payload_path}")
        manifest = _load_json_object(payload_path / "manifest.json")
        if manifest.get("target") != expected_target:
            raise AgentpakkeManifestError(
                f"{relative}/manifest.json target must be {expected_target!r}"
            )


def build_manifest(root: Path) -> dict[str, Any]:
    root = root.resolve()
    public_agents = _public_agents(root)
    copilot_compatibility, opencode_compatibility = _compatibility_ranges(root)
    _validate_payloads(root)
    plugin_metadata = _load_json_object(root / "plugin/plugin.json")
    description = plugin_metadata.get("description")
    if (
        plugin_metadata.get("name") != "grillmester"
        or not isinstance(description, str)
        or not description.strip()
    ):
        raise AgentpakkeManifestError(
            "plugin/plugin.json identity differs from Grillmester"
        )
    return {
        "contractVersion": "1",
        "name": "grillmester",
        "description": description,
        "owner": {"repo": "navikt/grillmester", "team": "Team eSyfo"},
        "clients": {
            "copilot": {
                "primaryAgents": public_agents,
                "compatibility": copilot_compatibility,
                "defaultModel": "inherit",
                "defaultContext": "full",
                "payloads": {
                    "full": {"path": "plugin"},
                    "focused": {"path": "targets/copilot-cli-focused-v1"},
                },
            },
            "opencode": {
                "primaryAgents": public_agents,
                "compatibility": opencode_compatibility,
                "defaultModel": "inherit",
                "defaultContext": "full",
                "payloads": {
                    "full": {"path": "targets/opencode-v1"},
                    "focused": {"path": "targets/opencode-v1-focused"},
                },
            },
        },
    }


def render_manifest(manifest: Mapping[str, Any]) -> bytes:
    return (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _write_atomic(path: Path, content: bytes) -> None:
    parent = path.parent
    if parent.exists():
        parent_stat = parent.lstat()
        if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
            raise AgentpakkeManifestError(
                f"output parent must be a real directory: {parent}"
            )
    else:
        parent.mkdir(mode=0o755)
    if path.exists() or path.is_symlink():
        existing = path.lstat()
        if stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode):
            raise AgentpakkeManifestError(f"output must be a regular file: {path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise


def update_manifest(root: Path) -> bool:
    output = root.resolve() / OUTPUT
    expected = render_manifest(build_manifest(root))
    current = (
        _read_regular_bytes(output)
        if output.exists() and not output.is_symlink()
        else None
    )
    if current == expected:
        return False
    _write_atomic(output, expected)
    return True


def check_manifest(root: Path) -> None:
    output = root.resolve() / OUTPUT
    expected = render_manifest(build_manifest(root))
    if not output.exists():
        raise AgentpakkeManifestError(
            f"missing {OUTPUT}; run scripts/generate_agentpakke_manifest.py"
        )
    actual = _read_regular_bytes(output)
    if actual != expected:
        raise AgentpakkeManifestError(
            f"stale {OUTPUT}; run scripts/generate_agentpakke_manifest.py"
        )


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail unless the committed manifest is current",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if arguments.check:
            check_manifest(arguments.root)
            print(f"ok: {OUTPUT} is current")
        else:
            changed = update_manifest(arguments.root)
            print(f"{'updated' if changed else 'unchanged'}: {OUTPUT}")
    except AgentpakkeManifestError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
