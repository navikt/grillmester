"""Shared encoding and filesystem path comparisons."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import rules


class SetupError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def schema_error() -> SetupError:
    return SetupError(3, "Schema/policy mismatch; nothing written. Use guide for the manual click guide.")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def display(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    return re.sub(r"[\x7f-\x9f]", lambda match: f"\\u{ord(match[0]):04x}", text)


def home_relative(path: Path, home: Path) -> str:
    try:
        return "~/" + str(path.relative_to(home))
    except ValueError:
        return str(path)


def has_control(value: str) -> bool:
    return any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in value)


def same_path(left: Path, right: Path) -> bool:
    try:
        if left.exists() and right.exists() and left.samefile(right):
            return True
    except OSError:
        pass
    return str(left.resolve()).casefold() == str(right.resolve()).casefold()


def under(path: Path, parent: Path) -> bool:
    return any(same_path(part, parent) for part in (path, *path.parents))


def safe_code_root(path: Path, home: Path, parent: bool = False) -> bool:
    if under(home, path):
        return False
    if any(same_path(path, Path(root)) for root in ("/", "/Users", "/Volumes")):
        return False
    if under(path, home / ".copilot"):
        return False
    if any(under(home / denied, path) for denied in rules.DENIED_PATHS):
        return False
    if parent and (under(path, home / "Library") or any(
        same_path(path, home / folder) for folder in ("Downloads", "Desktop", "Documents")
    )):
        return False
    for area in rules.SYSTEM_AREAS:
        for system in (Path(area), Path(area).resolve()):
            if under(path, system):
                return False
    return True


def changed_projects(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [project for project in plan["projects"] if project["before"] != project["after"]]
