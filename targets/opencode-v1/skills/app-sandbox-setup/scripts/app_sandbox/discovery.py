"""Host observations only; never select policy grants or write settings."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

from . import backups, rules, toolchain_discovery
from .facts import Facts, PathFact
from .paths import SetupError, display, has_control, home_relative, safe_code_root, same_path, under
from .policy import read_policy


def empty_directory(path: Path) -> bool:
    try:
        return not path.is_symlink() and path.is_dir() and next(path.iterdir(), None) is None
    except OSError:
        return False


def code_roots(paths: Sequence[tuple[Any, bool]], home: Path, warnings: list[str]) -> list[str]:
    roots = []
    for raw, worktree in paths:
        if not isinstance(raw, str) or has_control(raw):
            warnings.append("Code path skipped: invalid string or control characters.")
            continue
        if not Path(raw).is_absolute():
            warnings.append("Code path skipped: non-absolute path.")
            continue
        try:
            if under(Path(raw), home / ".copilot"):
                warnings.append("Code path under ~/.copilot skipped; never a code root.")
                continue
            specific = Path(raw).resolve()
        except (OSError, RuntimeError):
            warnings.append("Code path skipped: cannot resolve symlinks.")
            continue
        if has_control(str(specific)):
            warnings.append("Resolved code path skipped: control characters.")
            continue
        if under(specific, home / ".copilot"):
            warnings.append("Code path under ~/.copilot skipped; never a code root.")
            continue
        if not specific.exists() and not under(specific, Path("/Volumes")):
            warnings.append(f"Code path missing; skipped: {display(str(specific))}")
            continue
        candidate = specific.parent.parent if worktree else specific.parent
        if not safe_code_root(candidate, home, parent=True):
            warnings.append(f"unsafe code root {display(str(candidate))}; trying specific path.")
            candidate = specific
        if not safe_code_root(candidate, home):
            warnings.append(f"unsafe specific code path {display(str(candidate))}; skipped.")
            continue
        roots.append(str(candidate))
    return list(dict.fromkeys(roots))


def docker_parent(home: Path) -> Optional[str]:
    host = os.environ.get("DOCKER_HOST")
    if not host:
        try:
            host = subprocess.run(
                ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
                env={**os.environ, "HOME": str(home)}, capture_output=True, text=True,
                timeout=3, check=True,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
    if host.startswith("unix://") and not has_control(host):
        path = Path(host[7:]).parent
        if path.is_absolute() and under(path.resolve(), home) and not same_path(path.resolve(), home):
            return str(path)
    return None


def docker_grants(home: Path) -> list[str]:
    parent = docker_parent(home)
    return [str(home / path) for path in rules.DOCKER_PATHS] + ([parent] if parent else [])


def git_environment(home: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_CONFIG") and key not in ("XDG_CONFIG_HOME", "GIT_DIR", "GIT_WORK_TREE")}
    env.update(HOME=str(home), GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
    return env


def git_discovery(home: Path, warnings: list[str], projects: Sequence[Any] = ()) -> list[str]:
    git = shutil.which("git")
    if not git:
        warnings.append("Git discovery skipped: git is unavailable.")
        return []
    env = git_environment(home)
    try:
        if sys.platform == "darwin" and str(Path(git).resolve()) == "/usr/bin/git":
            result = subprocess.run(["/usr/bin/xcode-select", "-p"], env=env, capture_output=True, timeout=3)
            if result.returncode:
                warnings.append("Git discovery skipped: stock /usr/bin/git needs Xcode Command Line Tools and could open an install dialog.")
                return []
        result = subprocess.run(
            [git, "config", "--global", "--list", "--show-origin", "--includes", "--null"],
            env=env, cwd=str(home), capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        warnings.append("Git discovery unavailable; add global config paths manually.")
        return []
    paths = []
    if result.returncode == 0:
        records = result.stdout.split("\0")
        for index in range(0, len(records) - 1, 2):
            origin, entry = records[index:index + 2]
            if not origin.startswith("file:") or has_control(origin):
                continue
            file = Path(origin[5:])
            if not file.is_absolute():
                file = home / file
            paths.append(file)
            key, _, value = entry.partition("\n")
            key = key.lower()
            if key == "commit.gpgsign" and value.strip().lower() in ("true", "yes", "on", "1"):
                warnings.append("commit.gpgsign=true: signing needs ~/.gnupg or ~/.ssh, both denied.")
            include = key == "include.path" or (key.startswith("includeif.") and key.endswith(".path"))
            if include or key in ("core.excludesfile", "commit.template", "core.hookspath"):
                if value and not has_control(value):
                    if value == "~" or value.startswith("~/"):
                        path = home / value[2:] if value != "~" else home
                    else:
                        path = Path(value)
                    if not path.is_absolute():
                        path = (file.parent if include else home) / path
                    paths.append(path)
    elif (home / ".gitconfig").exists():
        warnings.append("Git global discovery failed; config contents are never printed.")
    for project in projects:
        if not isinstance(project["main_repo_path"], str):
            continue
        repo = Path(project["main_repo_path"])
        if not repo.is_absolute() or has_control(str(repo)) or not repo.is_dir():
            continue
        try:
            remotes = subprocess.run(
                [git, "-C", str(repo), "config", "--get-regexp", r"^remote\..*\.url$"],
                env=env, capture_output=True, text=True, timeout=3,
            )
            if remotes.returncode == 0 and any(re.match(r"(?:[^\s/@]+@[^\s/:]+:|ssh://)", line.partition(" ")[2])
                                              for line in remotes.stdout.splitlines()):
                warnings.append(f'{display(project["name"])}: SSH remote blocked (~/.ssh denied); use HTTPS or run outside the sandbox.')
        except (OSError, subprocess.SubprocessError):
            warnings.append(f'{display(project["name"])}: SSH remote discovery unavailable.')
    return list(dict.fromkeys(str(path.resolve()) for path in paths if path.exists() and not has_control(str(path))))


def jdk_warning(home: Path, warnings: list[str]) -> None:
    homes = sorted(
        (path for root in ("Library/Java/JavaVirtualMachines", "/Library/Java/JavaVirtualMachines")
         for path in (home / root).glob("*/Contents/Home") if path.is_dir()),
        key=lambda path: (path.parent.parent.name, str(path)), reverse=True,
    )
    if homes:
        warnings.append(
            "JDK info: " + ", ".join(display(home_relative(path, home)) for path in homes)
            + ". In the sandbox, /usr/bin/java and java_home cannot discover JDKs "
            "(Spotlight lookup unavailable). JDK directories are readable: set JAVA_HOME "
            "or use any version manager (mise, sdkman, asdf, jenv, etc.). "
            "Choose the first listed home (newest by directory name order), "
            "e.g. export JAVA_HOME=…/Contents/Home."
        )


def credential_file_warnings(home: Path, warnings: list[str]) -> None:
    hosts = home / ".config/gh/hosts.yml"
    config = home / ".docker/config.json"
    try:
        if hosts.is_file() and any(
            match.group(1).split("#", 1)[0].strip().strip("'\"")
            for match in re.finditer(r"^[ \t]*oauth_token:[ \t]*([^\r\n]*)", hosts.read_text(encoding="utf-8"), re.MULTILINE)
        ):
            warnings.append("~/.config/gh/hosts.yml contains an inline token; readonly still permits reading it, and masking does not cover it.")
    except (OSError, UnicodeError):
        warnings.append("Could not check hosts.yml for inline credentials; contents are never printed.")
    try:
        if config.is_file():
            data = json.loads(config.read_text(encoding="utf-8"))
            auths = data.get("auths", {}) if isinstance(data, dict) else {}
            if isinstance(auths, dict) and any(isinstance(entry, dict) and entry.get("auth") for entry in auths.values()):
                warnings.append("~/.docker/config.json contains inline auth; readonly still permits reading it, and masking does not cover it.")
    except (OSError, ValueError, UnicodeError):
        warnings.append("Could not check config.json for inline credentials; contents are never printed.")


def hardened_cache_paths(home: Path) -> list[Path]:
    cache = home / "Library/Caches"
    copilot = cache / "copilot"
    result = [copilot] if copilot.is_dir() else []
    result += [child for child in copilot.glob("*")
               if child.is_dir() and child.name not in rules.APP_CACHE_WRITABLE]
    for pattern in ("github-copilot*", "copilot-desktop-*"):
        result += [child for child in cache.glob(pattern) if child.is_dir()]
    return sorted(result)


def backup_warnings(home: Path) -> list[str]:
    return backups.observe(home)[0]


def path_fact(path: Path) -> PathFact:
    exists = file = directory = symlink = False
    inode = None
    try:
        exists = path.exists()
    except OSError:
        pass
    else:
        if exists:
            try:
                info = path.stat()
                inode = (info.st_dev, info.st_ino)
            except OSError:
                # Preserve existence and allow resolved/casefold comparison.
                pass
        try:
            file = path.is_file()
        except OSError:
            pass
        try:
            directory = path.is_dir()
        except OSError:
            pass
        try:
            symlink = path.is_symlink()
        except OSError:
            pass
    failed = False
    try:
        resolved = str(path.resolve()).casefold()
    except (OSError, RuntimeError):
        resolved = str(path).casefold()
        failed = True
    return PathFact(resolved, inode, exists, file, directory,
                    symlink, empty_directory(path), failed)


def capture_paths(home: Path, candidates: Sequence[str], existing: dict[str, Any],
                  docker: Sequence[str] = (), no_docker: bool = False) -> dict[str, PathFact]:
    # Preserve the oracle's unguarded profile/deny checks, but not for arbitrary
    # policy entries or their ancestors. The backup rule is unconditional, and
    # --no-docker skips profile checks beneath Docker grants.
    for relative in rules.RW_PATHS + rules.RO_PATHS + rules.HARDENING_READONLY:
        path = home / relative
        if no_docker and any(under(path, Path(parent)) for parent in docker):
            continue
        path.exists()
    if not no_docker:
        for raw in docker:
            Path(raw).exists()
    for relative in rules.DENIED_PATHS:
        path = home / relative
        if relative == rules.BACKUP_DIRECTORY:
            continue
        if relative in rules.FILE_DENIED_PATHS:
            path.is_file()
        else:
            path.is_dir()

    paths = {home, home / ".copilot", Path("/Users")}
    paths.update(Path(area) for area in rules.SYSTEM_AREAS)
    paths.update(home / relative for relative in
                 rules.RW_PATHS + rules.RO_PATHS + rules.HARDENING_READONLY + rules.DENIED_PATHS)
    paths.update(Path(path) for path in candidates)
    for raw in existing.values():
        try:
            policy = read_policy(raw) if raw is not None else {}
        except SetupError:
            continue
        paths.update(Path(path) for field in rules.PATH_FIELDS for path in policy.get(field, [])
                     if Path(path).is_absolute() and not has_control(path))
    paths.update(parent for path in tuple(paths) for parent in path.parents)
    return {str(path): path_fact(path) for path in sorted(paths)}


def gather(home: Path, projects: Sequence[dict[str, Any]], code_paths: Sequence[tuple[Any, bool]],
           existing: dict[str, Any], root_warnings: Sequence[str] = (),
           profile_only: bool = False, no_docker: bool = False,
           no_instructions: bool = False, move_backups: bool = False) -> Facts:
    docker = docker_grants(home)
    profile_warnings: list[str] = []
    credential_file_warnings(home, profile_warnings)
    jdk_warning(home, profile_warnings)
    backup_messages, moves = backups.observe(home, move_backups)
    hardened = [str(path) for path in hardened_cache_paths(home)]
    writable = [str(child) for child in sorted((home / "Library/Caches/copilot").glob("*"))
                if child.is_dir() and child.name in rules.APP_CACHE_WRITABLE]
    git_warnings: list[str] = []
    git_paths = [] if profile_only else git_discovery(home, git_warnings, projects)
    warnings = list(root_warnings)
    roots = [] if profile_only else code_roots(code_paths, home, warnings)
    paths = capture_paths(home, docker + hardened + writable + git_paths + roots, existing,
                          docker, no_docker)
    toolchains = {}
    if not profile_only and not no_instructions:
        for project in projects:
            raw = project["main_repo_path"]
            if isinstance(raw, str) and Path(raw).is_absolute() and not has_control(raw):
                toolchains[project["id"]] = toolchain_discovery.observe(Path(raw), home)
    return Facts(str(home), projects, paths, docker, roots, git_paths, hardened, writable,
                 profile_warnings, backup_messages, git_warnings, warnings, toolchains, moves)
