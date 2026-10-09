"""Value-only discovery snapshot and pure path relations.

Discovery records resolved identities for paths and their lexical ancestors.
Synthetic facts can use lexical identities without touching the filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence


@dataclass(frozen=True)
class PathFact:
    resolved: str
    inode: Optional[tuple[int, int]] = None
    exists: bool = False
    file: bool = False
    directory: bool = False
    symlink: bool = False
    empty: bool = False
    resolution_failed: bool = False


@dataclass(frozen=True)
class Options:
    mask: Optional[bool] = None
    no_docker: bool = False
    no_instructions: bool = False
    move_backups: bool = False


@dataclass(frozen=True)
class Facts:
    home: str
    projects: Sequence[dict[str, Any]] = ()
    paths: dict[str, PathFact] = field(default_factory=dict)
    docker: Sequence[str] = ()
    roots: Sequence[str] = ()
    git_paths: Sequence[str] = ()
    hardened_caches: Sequence[str] = ()
    writable_caches: Sequence[str] = ()
    profile_warnings: Sequence[str] = ()
    backup_warnings: Sequence[str] = ()
    git_warnings: Sequence[str] = ()
    root_warnings: Sequence[str] = ()
    toolchains: dict[str, Any] = field(default_factory=dict)
    backup_moves: Sequence[dict[str, Any]] = ()

    def path(self, path: Path) -> PathFact:
        return self.paths.get(str(path), PathFact(str(path).casefold()))

    def same(self, left: Path, right: Path) -> bool:
        a, b = self.path(left), self.path(right)
        if a.inode is not None and a.inode == b.inode:
            return True
        if a.resolution_failed or b.resolution_failed:
            raise RuntimeError("path resolution unavailable")
        return a.resolved == b.resolved

    def under(self, path: Path, parent: Path) -> bool:
        return any(self.same(part, parent) for part in (path, *path.parents))

    def parent_writable(self, path: Path, readwrite: Sequence[str]) -> bool:
        return any(self.under(path.parent, Path(grant)) for grant in readwrite)

    def placeholder(self, rules: dict[str, Any], relative: str, readwrite: Sequence[str]) -> bool:
        home = Path(self.home)
        path = home / relative
        if (relative == rules["BACKUP_DIRECTORY"] or self.path(path.parent).symlink
                or self.parent_writable(path, readwrite)):
            return False
        return (relative in rules["FILE_DENIED_PATHS"] or self.same(path.parent, home)
                or self.same(path.parent, home / ".copilot")) and self.path(path).empty

    def required_denies(self, rules: dict[str, Any], readwrite: Sequence[str]) -> list[str]:
        denied = []
        for relative in rules["DENIED_PATHS"]:
            path = Path(self.home) / relative
            state = self.path(path)
            if relative == rules["BACKUP_DIRECTORY"]:
                denied.append(str(path))
            elif relative in rules["FILE_DENIED_PATHS"]:
                if state.file:
                    denied.append(str(path))
            elif state.directory and not self.placeholder(rules, relative, readwrite):
                denied.append(str(path))
            elif not state.exists and not state.symlink and self.parent_writable(path, readwrite):
                denied.append(str(path))
        return denied
