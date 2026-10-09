#!/usr/bin/env python3
"""Plan and confirm portable GitHub Copilot desktop sandbox settings."""
# Frozen pre-refactor oracle from e69e97b.
# Used by tests/test_app_sandbox_setup_equivalence.py.
# Must never be edited.

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence
from urllib.parse import urlsplit


RW_PATHS = (
    ".gradle", ".m2", ".npm", ".cache", ".config", ".local/share", ".local/state",
    "Library/Caches", "Library/pnpm", ".bun", ".nvm", ".rd", ".docker",
    "/tmp", "/private/tmp",
    "Library/Application Support/kotlin", ".konan", ".testcontainers.properties",
    ".colima", ".orbstack", ".lima", "go", ".cargo", ".yarn",
)
RO_PATHS = (
    ".copilot/installed-plugins", ".copilot/agents", ".copilot/extensions",
    ".copilot/marketplace-cache", ".agents", ".claude/skills", ".gitconfig",
    "Library/Java/JavaVirtualMachines", "/Library/Java/JavaVirtualMachines",
    ".sdkman", ".asdf", ".jenv", ".volta", ".pyenv", ".rustup", ".local/bin",
    "Library/Application Support/fnm", ".npmrc", ".yarnrc.yml",
    ".config/gh/hosts.yml",
)
HARDENING_READONLY = (
    ".config/git", ".config/fish", ".config/mise", ".config/direnv",
    ".config/gh/config.yml", ".gradle/init.d", ".gradle/init.gradle",
    ".gradle/init.gradle.kts", ".gradle/gradle.properties",
    ".docker/cli-plugins", ".docker/config.json", "Library/Caches/copilot",
)
DOCKER_PATHS = (".docker", ".rd", ".colima", ".orbstack", ".lima", ".testcontainers.properties")
APP_CACHE_WRITABLE: set[str] = set()
RETIRED_GRANTS = {
    "readwritePaths": {
        ".copilot/session-state": "the app grants its own session files",
        "Library/Application Support/Google/Chrome for Testing":
            "Chromium needs denied macOS IPC; no path grant helps",
    },
    "deniedPaths": {
        ".copilot/data.db-wal":
            "~/.copilot is not readable in the sandbox; a deny placeholder could break the app's SQLite WAL",
        ".copilot/data.db-shm":
            "~/.copilot is not readable in the sandbox; a deny placeholder could break the app's SQLite WAL",
    },
}
DENIED_PATHS = (
    ".ssh", ".aws", ".gnupg", ".kube", ".config/gcloud", "Library/Keychains",
    ".netrc", ".copilot/data.db",
    ".copilot/app-sandbox-setup-backups", ".copilot/settings.json",
    ".copilot/config.json", ".copilot/mcp-oauth-config",
    ".config/github-copilot", ".config/configstore", ".config/op", ".azure",
)
FILE_DENIED_PATHS = frozenset((
    ".netrc", ".copilot/data.db", ".copilot/settings.json", ".copilot/config.json",
))
BACKUP_DIRECTORY = ".copilot/app-sandbox-setup-backups"
APP_OWNED_DB_SUFFIXES = (".open-lock", "-wal", "-shm", "-journal")
PATH_FIELDS = ("readwritePaths", "readonlyPaths", "deniedPaths")
BOOL_FIELDS = ("allowOutbound", "allowLocalNetwork", "allowGitCredentials", "allowGhCredentials")
CREDENTIAL_WARNING = (
    "When credential masking is OFF: sandboxed processes see the real GH_TOKEN / git credentials. "
    "With outbound allowed, any build script or dependency could exfiltrate them. "
    "Use --mask-credentials to mask them instead; the proxy forces loopback deny, "
    "breaking Gradle daemon, Testcontainers, dev servers and Playwright even with allowLocalNetwork=true."
)
MASKING_SCOPE_WARNING = (
    "Credential masking covers only app-injected GH_TOKEN / git credential helper, NOT files "
    "on disk such as ~/.npmrc, gradle.properties or hosts.yml. Existing credential choices are preserved."
)
SYSTEM_AREAS = (
    "/System", "/Library", "/usr", "/bin", "/sbin", "/etc", "/var",
    "/private", "/opt", "/Applications",
)
SQL_IDENTIFIER = r"""(?:"(?:[^"]|"")*"|`(?:[^`]|``)*`|\[[^\]]*\]|'(?:[^']|'')*'|[a-z_][a-z0-9_$]*)"""
TRIGGER_HEADER = re.compile(
    rf"\A\s*CREATE\s+(?:TEMP(?:ORARY)?\s+)?TRIGGER\s+"
    rf"(?:IF\s+NOT\s+EXISTS\s+)?{SQL_IDENTIFIER}(?:\s*\.\s*{SQL_IDENTIFIER})?\s+"
    r"(?:(?:BEFORE|AFTER)\s+|INSTEAD\s+OF\s+)?"
    rf"(?P<event>INSERT|DELETE|UPDATE)"
    rf"(?:\s+OF\s+(?P<columns>{SQL_IDENTIFIER}(?:\s*,\s*{SQL_IDENTIFIER})*))?"
    rf"\s+ON\s+(?:{SQL_IDENTIFIER}\s*\.\s*)?(?P<table>{SQL_IDENTIFIER})"
    r"(?=\s+(?:FOR\s+EACH\s+ROW|WHEN|BEGIN)\b)",
    re.IGNORECASE | re.ASCII,
)


def sql_identifier_name(identifier: str) -> str:
    if identifier[0] in ('"', "'", "`", "["):
        quote = identifier[0]
        identifier = identifier[1:-1]
        if quote != "[":
            identifier = identifier.replace(quote * 2, quote)
    return identifier.lower()


class SetupError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


class UsageParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SetupError(1, "Usage error; see --help. apply requires --confirm DIGEST.")


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


def open_db(path: Path, writable: bool = False) -> sqlite3.Connection:
    connection = None
    try:
        path.stat()
        if not os.access(str(path), os.R_OK | os.W_OK):
            raise PermissionError()
        connection = sqlite3.connect(
            path.resolve().as_uri() + "?mode=rw",
            uri=True, timeout=30,
        )
        if not writable:
            connection.execute("PRAGMA query_only=ON")
        connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except (sqlite3.Error, OSError, ValueError, RuntimeError) as error:
        if connection is not None:
            connection.close()
        if isinstance(error, FileNotFoundError):
            raise SetupError(2, "DB not found: app never started or wrong --db.") from None
        if isinstance(error, PermissionError) or getattr(error, "errno", None) in (errno.EPERM, errno.EACCES):
            raise SetupError(2, "DB access denied: sandbox is ON in this session: approve "
                             "'Run outside the sandbox' once, or /sandbox off, or use a normal terminal.") from None
        raise db_error(error) from None
    connection.row_factory = sqlite3.Row
    return connection


def db_error(error: Exception) -> SetupError:
    # Never echo SQLite/OS errors: they can contain data from the store.
    if isinstance(error, sqlite3.Error) and (
        "locked" in str(error).lower() or "busy" in str(error).lower()
    ):
        return SetupError(5, "DB busy/locked after waiting up to 30 seconds; close competing operations and retry.")
    return SetupError(2, "DB unreadable or access denied: sandbox is ON in this session: approve "
                      "'Run outside the sandbox' once, or /sandbox off, or use a normal terminal.")


def schema_error() -> SetupError:
    return SetupError(3, "Schema/policy mismatch; nothing written. Use guide for the manual click guide.")


def validate_schema(connection: sqlite3.Connection) -> None:
    required = {
        "projects": {"id": "TEXT", "name": "TEXT", "main_repo_path": "TEXT", "sandbox_enabled": "INTEGER"},
        "project_sandbox_policies": {"project_id": "TEXT", "policy_json": "TEXT"},
        "worktrees": {"id": "TEXT", "project_id": "TEXT", "path": "TEXT", "branch": "TEXT"},
    }
    queries = {
        "projects": "PRAGMA table_info(projects)",
        "project_sandbox_policies": "PRAGMA table_info(project_sandbox_policies)",
        "worktrees": "PRAGMA table_info(worktrees)",
    }
    for table, columns in required.items():
        kind = connection.execute(
            "SELECT type FROM sqlite_master WHERE name = ?", (table,)
        ).fetchone()
        found = {row["name"]: row for row in connection.execute(queries[table])}
        if not kind or kind[0] != "table" or any(
            name not in found or found[name]["type"].upper() != sql_type
            for name, sql_type in columns.items()
        ):
            raise schema_error()
        key = "project_id" if table == "project_sandbox_policies" else "id"
        if found[key]["pk"] != 1 or sum(row["pk"] > 0 for row in found.values()) != 1:
            raise schema_error()
        if table == "projects":
            flag = found["sandbox_enabled"]
            if flag["notnull"] != 1 or str(flag["dflt_value"]).strip("() ") != "0":
                raise schema_error()
        if table == "project_sandbox_policies" and found["policy_json"]["notnull"] != 1:
            raise schema_error()
        if table == "project_sandbox_policies" and any(
            name not in columns and info["notnull"] and info["dflt_value"] is None
            for name, info in found.items()
        ):
            raise schema_error()
    unique_repo = connection.execute(
        "SELECT 1 FROM pragma_index_list('projects') AS indexes "
        "JOIN pragma_index_info(indexes.name) AS columns "
        "WHERE indexes.[unique] = 1 AND indexes.partial = 0 AND columns.name = 'main_repo_path' "
        "AND (SELECT count(*) FROM pragma_index_info(indexes.name)) = 1"
    ).fetchone()
    foreign_keys = connection.execute("PRAGMA foreign_key_list(project_sandbox_policies)").fetchall()
    if not unique_repo or not any(
        row["table"] == "projects" and row["from"] == "project_id"
        and row["to"] == "id" and row["on_delete"].upper() == "CASCADE"
        for row in foreign_keys
    ):
        raise schema_error()
    for trigger in connection.execute(
        "SELECT tbl_name, sql FROM sqlite_master WHERE type = 'trigger' "
        "AND tbl_name IN ('projects', 'project_sandbox_policies', 'worktrees')"
    ):
        if trigger["tbl_name"] == "project_sandbox_policies":
            # The policy UPSERT can fire both INSERT and UPDATE triggers.
            raise schema_error()
        header = TRIGGER_HEADER.match(trigger["sql"] or "")
        if not header or sql_identifier_name(header["table"]) != trigger["tbl_name"]:
            raise schema_error()
        columns = header["columns"]
        event = header["event"].upper()
        if columns is not None and event != "UPDATE":
            raise schema_error()
        if trigger["tbl_name"] == "projects" and event == "UPDATE":
            # Only sandbox_enabled is written; unrelated UPDATE OF triggers cannot fire.
            if columns is None or any(
                sql_identifier_name(column) == "sandbox_enabled"
                for column in re.findall(SQL_IDENTIFIER, columns, re.IGNORECASE | re.ASCII)
            ):
                raise schema_error()


def read_policy(raw: str) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError("non-finite JSON")

    try:
        policy = json.loads(raw, parse_constant=reject_constant)
        if not isinstance(policy, dict):
            raise ValueError("not an object")
        for field in PATH_FIELDS:
            if field in policy and (
                not isinstance(policy[field], list)
                or any(not isinstance(path, str) for path in policy[field])
            ):
                raise ValueError("invalid paths")
        for field in BOOL_FIELDS:
            if field in policy and type(policy[field]) is not bool:
                raise ValueError("invalid boolean")
        canonical(policy)
        return policy
    except (ValueError, TypeError, RecursionError):
        raise schema_error() from None


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


def empty_directory(path: Path) -> bool:
    try:
        return not path.is_symlink() and path.is_dir() and next(path.iterdir(), None) is None
    except OSError:
        return False


def parent_writable(path: Path, readwrite: Sequence[str]) -> bool:
    return any(under(path.parent, Path(grant)) for grant in readwrite)


def placeholder_directory(home: Path, relative: str, readwrite: Sequence[str]) -> bool:
    path = home / relative
    if relative == BACKUP_DIRECTORY or path.parent.is_symlink() or parent_writable(path, readwrite):
        return False
    return (relative in FILE_DENIED_PATHS or same_path(path.parent, home)
            or same_path(path.parent, home / ".copilot")) and empty_directory(path)


def required_denies(home: Path, readwrite: Sequence[str]) -> list[str]:
    denied = []
    for relative in DENIED_PATHS:
        path = home / relative
        if relative == BACKUP_DIRECTORY:
            # Apply creates backups before policy commit; an empty placeholder here is harmless.
            denied.append(str(path))
        elif relative in FILE_DENIED_PATHS:
            if path.is_file():
                denied.append(str(path))
        elif path.is_dir() and not placeholder_directory(home, relative, readwrite):
            denied.append(str(path))
        elif not path.exists() and not path.is_symlink() and parent_writable(path, readwrite):
            denied.append(str(path))
    return denied


def safe_code_root(path: Path, home: Path, parent: bool = False) -> bool:
    if under(home, path):
        return False
    if any(same_path(path, Path(root)) for root in ("/", "/Users", "/Volumes")):
        return False
    if under(path, home / ".copilot"):
        return False
    if any(under(home / denied, path) for denied in DENIED_PATHS):
        return False
    if parent and (under(path, home / "Library") or any(
        same_path(path, home / folder) for folder in ("Downloads", "Desktop", "Documents")
    )):
        return False
    for area in SYSTEM_AREAS:
        # Resolve system aliases too (e.g. /etc -> /private/etc on macOS).
        for system in (Path(area), Path(area).resolve()):
            if under(path, system):
                return False
    return True


def code_roots(connection: sqlite3.Connection, home: Path, warnings: list[str]) -> list[str]:
    paths = [(row[0], False) for row in connection.execute(
        "SELECT main_repo_path FROM projects ORDER BY id"
    )]
    try:
        paths += [(row[0], True) for row in connection.execute("SELECT path FROM worktrees ORDER BY id")]
    except sqlite3.Error:
        # guide can still discover projects on an upgraded/incomplete schema.
        warnings.append("Worktree paths unavailable; add your code folders manually where needed.")
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
    return [str(home / path) for path in DOCKER_PATHS] + ([parent] if parent else [])


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


def profile_paths(home: Path, mask: Optional[bool], warnings: list[str],
                  no_docker: bool = False, docker_paths: Optional[list[str]] = None) -> dict[str, list[str]]:
    warnings.append(MASKING_SCOPE_WARNING)
    credential_file_warnings(home, warnings)
    jdk_warning(home, warnings)
    if mask:
        warnings.append("Credential masking is ON: its proxy forces loopback deny even with allowLocalNetwork=true.")
    for sibling in sorted((home / ".copilot").glob("data.db*")):
        name = sibling.name
        # The app owns its lock and SQLite sidecars; never suggest touching them.
        if name == "data.db" or not sibling.is_file() or name.endswith(APP_OWNED_DB_SUFFIXES):
            continue
        warnings.append(
            f"Backup copy {display(str(sibling))} is not covered by the deny list; "
            "suggest moving it (do not delete it) into ~/.copilot/app-sandbox-setup-backups, which is denied."
        )
    grants = {}
    missing = []
    docker = docker_grants(home) if docker_paths is None else docker_paths
    if no_docker:
        warnings.append("--no-docker removes exact Docker rw grants; Testcontainers/docker will not work in the sandbox.")
    else:
        warnings.append("Docker socket = effectively unsandboxed host access: it can mount HOME, read ~/.ssh and write LaunchAgents. Use --no-docker to omit Docker grants.")
    warnings.append("Writable tool installs can persist changes that later execute outside the sandbox; they remain writable so agents can install tools.")
    for field, relatives in (("readwritePaths", RW_PATHS), ("readonlyPaths", RO_PATHS)):
        grants[field] = []
        for relative in relatives:
            path = str(home / relative)
            if no_docker and any(under(Path(path), Path(parent)) for parent in docker):
                continue
            if Path(path).exists():
                grants[field].append(path)
            else:
                missing.append(display(home_relative(Path(path), home)))
    # Missing hardening paths stay readonly without pre-creation: creation is a residual risk.
    missing_hardening = []
    for relative in HARDENING_READONLY:
        path = home / relative
        if no_docker and any(under(path, Path(parent)) for parent in docker):
            continue
        grants["readonlyPaths"].append(str(path))
        if not path.exists():
            missing_hardening.append(display(home_relative(path, home)))
    if not no_docker:
        grants["readwritePaths"] += [path for path in docker if Path(path).exists()
                                    and path not in grants["readwritePaths"]]
    if missing:
        warnings.append("Tools not installed (grants skipped; rerun after installing): " + ", ".join(missing))
    warnings.append("Hardening (missing paths listed as readonly; the app cannot block their creation, "
                    "so readonly applies only once the path exists): "
                    + ", ".join(missing_hardening))
    grants["deniedPaths"] = required_denies(home, grants["readwritePaths"])
    grants["readonlyPaths"] += [str(path) for path in hardened_cache_paths(home)]
    # Narrower rw under broader ro has not yet been verified live.
    grants["readwritePaths"] += [str(child) for child in sorted((home / "Library/Caches/copilot").glob("*"))
                               if child.is_dir() and child.name in APP_CACHE_WRITABLE]
    warnings.append("After an app update, rerun this skill: new version-named app cache directories need readonly hardening.")
    return grants


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


def compute_plan(connection: sqlite3.Connection, home: Path, mask: Optional[bool],
                 no_docker: bool = False) -> dict[str, Any]:
    projects = connection.execute(
        "SELECT id, name, main_repo_path, sandbox_enabled FROM projects ORDER BY id"
    ).fetchall()
    if not projects:
        raise SetupError(1, "No projects: add a project in the app first, then rerun plan.")
    warnings: list[str] = []
    docker = docker_grants(home)
    grants = profile_paths(home, mask, warnings, no_docker, docker)
    grants["readonlyPaths"] += git_discovery(home, warnings, projects)
    roots = code_roots(connection, home, warnings)
    readwrite = roots + grants["readwritePaths"]
    grants["deniedPaths"] = required_denies(home, readwrite)
    placeholder_removals = [
        {"path": str(home / relative),
         "reason": "the app created a directory for a deny path; its parent is not writable "
                   "in the sandbox, so deny is unnecessary and the directory can break tools"}
        for relative in DENIED_PATHS if placeholder_directory(home, relative, readwrite)
    ]
    for entry in placeholder_removals:
        warnings.append(f'will remove empty placeholder directory: {display(entry["path"])}; {entry["reason"]}.')
    owned_paths = {path for paths in grants.values() for path in paths} | set(roots)
    owned_paths.update(str(home / path) for path in RW_PATHS + RO_PATHS if Path(path).is_absolute())
    denied = grants["deniedPaths"]
    missing_denies = [
        display(home_relative(home / path, home))
        for path in DENIED_PATHS if str(home / path) not in denied
    ]
    if missing_denies:
        warnings.append(
            "Missing/non-qualifying secret paths (deny entries skipped or removed): "
            + ", ".join(missing_denies)
            + ". The sandbox cannot read $HOME by default; these paths are only readable "
            "if you added a broader grant. Rerun after first creating or logging in to "
            "these credential paths (including MCP OAuth at ~/.copilot/mcp-oauth-config) "
            "so denies are added as defense in depth."
        )
    changes = []
    skipped = []
    for row in projects:
        policy = connection.execute(
            "SELECT policy_json FROM project_sandbox_policies WHERE project_id = ?", (row["id"],)
        ).fetchone()
        try:
            before = read_policy(policy["policy_json"]) if policy else None
        except SetupError:
            skipped.append(row["id"])
            warnings.append(f'{display(row["name"])}: corrupt policy skipped; repair this project manually with guide.')
            continue
        after = dict(before or {})
        for field in PATH_FIELDS:
            clean = []
            for path in after.get(field, []):
                if has_control(path) or not Path(path).is_absolute():
                    warnings.append(f'{display(row["name"])}: removed invalid {field} entry (relative path or control characters).')
                    continue
                if field != "deniedPaths" and path not in owned_paths and (
                    under(home, Path(path)) or same_path(Path(path), Path("/Users"))
                    or same_path(Path(path), home / ".copilot")
                    or any(under(Path(path), Path(area)) for area in SYSTEM_AREAS)
                ):
                    warnings.append(f'{display(row["name"])}: broad existing {field} grant: {display(path)} (retained).')
                clean.append(path)
            after[field] = clean
        retired_denies = {str(home / path): reason
                          for path, reason in RETIRED_GRANTS.get("deniedPaths", {}).items()}
        retired_denies.update({
            str(home / path): "path no longer qualifies for deny: expected type absent or empty "
                             "placeholder outside writable parents; no app-created directory needed"
            for path in DENIED_PATHS if str(home / path) not in denied
        })
        user_denied = [path for path in after["deniedPaths"] if path not in retired_denies]
        for field in PATH_FIELDS:
            existing = list(dict.fromkeys(after.get(field, [])))
            retired = {str(home / path): reason
                       for path, reason in RETIRED_GRANTS.get(field, {}).items()}
            if field == "deniedPaths":
                retired.update(retired_denies)
            if no_docker and field == "readwritePaths":
                retired.update({path: "--no-docker removes this exact grant" for path in docker})
            for path in existing:
                if path in retired:
                    warnings.append(f'{display(row["name"])}: removed retired {field} grant: {display(path)}; {retired[path]}.')
            existing = [path for path in existing if path not in retired]
            if field != "deniedPaths":
                blocked = denied + (grants["readonlyPaths"] if field == "readwritePaths" else [])
                for path in existing:
                    if any(same_path(Path(path), Path(block)) for block in blocked):
                        warnings.append(f'{display(row["name"])}: removed {field} entry equal to denied/readonly path: {display(path)}')
                existing = [path for path in existing
                            if not any(same_path(Path(path), Path(block)) for block in blocked)]
            additions = denied if field == "deniedPaths" else grants[field]
            if field == "readwritePaths":
                additions = roots + additions
            if field != "deniedPaths":
                filtered = []
                for path in additions:
                    if any(under(Path(path), Path(block)) for block in user_denied + denied):
                        warnings.append(f'{display(row["name"])}: addition skipped under existing/required denied path: {display(path)}')
                    elif field == "readwritePaths" and any(same_path(Path(path), Path(ro)) for ro in grants["readonlyPaths"]):
                        continue
                    else:
                        filtered.append(path)
                additions = filtered
            after[field] = list(dict.fromkeys(existing + additions))
        for field in ("allowOutbound", "allowLocalNetwork"):
            if after.get(field) is False:
                warnings.append(f'{display(row["name"])}: {field}=true overrides existing false.')
            after[field] = True
        for field in ("allowGitCredentials", "allowGhCredentials"):
            if mask is not None:
                if field in after and after[field] != mask:
                    warnings.append(f'{display(row["name"])}: {field} credential value overridden by flag.')
                after[field] = mask
            else:
                after.setdefault(field, False)
        changes.append({
            "id": row["id"], "name": row["name"],
            "before": {"sandbox_enabled": row["sandbox_enabled"], "policy": before},
            "after": {"sandbox_enabled": 1, "policy": after},
        })
    if any(not project["after"]["policy"][field] for project in changes
           for field in ("allowGitCredentials", "allowGhCredentials")):
        warnings.append(CREDENTIAL_WARNING)
    full_change_set = [
        {"id": project["id"], "before": project["before"], "after": project["after"]}
        for project in changes
    ]
    digest_input = {"changes": full_change_set, "skipped": skipped,
                    "placeholder_removals": placeholder_removals}
    digest = hashlib.sha256(canonical(digest_input).encode()).hexdigest()
    return {"projects": changes, "skipped": skipped, "digest": digest,
            "placeholder_removals": placeholder_removals, "warnings": list(dict.fromkeys(warnings))}


def public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    projects = []
    for project in plan["projects"]:
        before, after = project["before"], project["after"]
        if plan.get("operation") == "rollback" and before == after:
            continue
        diff = {}
        if before["sandbox_enabled"] != after["sandbox_enabled"]:
            diff["sandbox_enabled"] = {"before": before["sandbox_enabled"], "after": after["sandbox_enabled"]}
        for field in PATH_FIELDS:
            old, new = (before["policy"] or {}).get(field, []), (after["policy"] or {}).get(field, [])
            diff[field] = {
                "added": [path for path in new if path not in old],
                "removed": [path for path in old if path not in new],
            }
        for field in BOOL_FIELDS:
            old, new = (before["policy"] or {}).get(field), (after["policy"] or {}).get(field)
            if old != new:
                diff[field] = {"before": old, "after": new}
        projects.append({"name": project["name"], "diff": diff, "changed": before != after})
    result = {
        "projects": projects, "digest": plan["digest"], "warnings": plan["warnings"],
        "placeholder_removals": plan.get("placeholder_removals", []),
        "changed": bool(changed_projects(plan) or plan.get("placeholder_removals")),
    }
    if plan.get("operation") == "rollback":
        result["unchanged_projects"] = len(plan["projects"]) - len(projects)
    return result


def print_plan(plan: dict[str, Any], json_mode: bool = False, summary: Optional[str] = None) -> None:
    if json_mode:
        result = public_plan(plan)
        if summary is not None:
            result["summary"] = summary
        print(display(result))
        return
    projects = changed_projects(plan) if plan.get("operation") == "rollback" else plan["projects"]
    for project in projects:
        print(f'Project: {display(project["name"])}')
        before, after = project["before"], project["after"]
        if before["sandbox_enabled"] != after["sandbox_enabled"]:
            print(f'  sandbox_enabled: {before["sandbox_enabled"]} -> {after["sandbox_enabled"]}')
        for field in PATH_FIELDS:
            old = (before["policy"] or {}).get(field, [])
            new = (after["policy"] or {}).get(field, [])
            for path in old:
                if path not in new:
                    print(f"  - {field}: {display(path)}")
            for path in new:
                if path not in old:
                    print(f"  + {field}: {display(path)}")
        for field in BOOL_FIELDS:
            old = (before["policy"] or {}).get(field)
            new = (after["policy"] or {}).get(field)
            if old != new:
                print(f"  {field}: {json.dumps(old)} -> {json.dumps(new)}")
        if before["policy"] != after["policy"] or before.get("policy_json") != after.get("policy_json"):
            print("  policy row changed (unknown fields are not displayed).")
    if plan.get("operation") == "rollback":
        print(f'Unchanged projects: {len(plan["projects"]) - len(projects)}')
    for warning in plan["warnings"]:
        print("Warning: " + warning)
    if not changed_projects(plan) and not plan.get("placeholder_removals"):
        print("no changes")
    if summary is not None:
        print(summary)
    print(f'Plan digest: {plan["digest"]}')


def changed_projects(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [project for project in plan["projects"] if project["before"] != project["after"]]


def remove_placeholders(plan: dict[str, Any], home: Path) -> None:
    for entry in plan.get("placeholder_removals", []):
        path = Path(entry["path"])
        home_fd = parent_fd = child_fd = None
        try:
            # Anchor removal to HOME and refuse symlinked parents or final directories.
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            home_fd = os.open(str(home), flags)
            parent_fd = os.open(str(path.parent.relative_to(home)), flags, dir_fd=home_fd)
            child_fd = os.open(path.name, flags, dir_fd=parent_fd)
            if os.listdir(child_fd):
                raise OSError("directory is no longer empty")
            opened = os.fstat(child_fd)
            current = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
            if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                raise OSError("directory changed")
            # rmdir itself atomically refuses non-empty directories and symlinks.
            os.rmdir(path.name, dir_fd=parent_fd)
        except (OSError, ValueError, NotImplementedError):
            plan["warnings"].append("policy update succeeded but could not remove empty placeholder directory: "
                                    + display(home_relative(path, home))
                                    + "; left untouched, inspect a fresh plan.")
        finally:
            for descriptor in (child_fd, parent_fd, home_fd):
                if descriptor is not None:
                    os.close(descriptor)


def backup_db(db: Path, home: Path) -> Path:
    directory = home / ".copilot/app-sandbox-setup-backups"
    if directory.is_symlink() or directory.parent.is_symlink():
        raise SetupError(1, "Backup directory must not be a symlink; nothing written.")
    directory.mkdir(mode=0o700, exist_ok=True)
    directory.chmod(0o700)
    path = directory / ("data.db." + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ"))
    descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)
    try:
        # A separate read-only source avoids backing up an active write
        # transaction. BEGIN IMMEDIATE on the writer prevents concurrent writes.
        source = open_db(db)
        try:
            target = sqlite3.connect(str(path))
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()
    except Exception:
        path.unlink()
        raise
    return path


def prune_backups(home: Path) -> None:
    directory = home / ".copilot/app-sandbox-setup-backups"
    pattern = re.compile(r"data\.db\.\d{8}T\d{6}\.\d{6}Z\Z")
    backups = sorted((path for path in directory.iterdir()
                      if pattern.fullmatch(path.name) and path.is_file() and not path.is_symlink()),
                     key=lambda path: path.name, reverse=True)
    for path in backups[10:]:
        path.unlink()


def write_changes(connection: sqlite3.Connection, plan: dict[str, Any], db: Path, home: Path) -> Optional[str]:
    changes = changed_projects(plan)
    if not changes:
        return None
    backup = backup_db(db, home)
    try:
        for project in changes:
            if project["before"]["sandbox_enabled"] != project["after"]["sandbox_enabled"]:
                connection.execute(
                    "UPDATE projects SET sandbox_enabled = ? WHERE id = ?",
                    (project["after"]["sandbox_enabled"], project["id"]),
                )
            if (project["before"]["policy"] != project["after"]["policy"]
                    or project["before"].get("policy_json") != project["after"].get("policy_json")):
                policy = project["after"]["policy"]
                if policy is None:
                    connection.execute("DELETE FROM project_sandbox_policies WHERE project_id = ?", (project["id"],))
                else:
                    connection.execute(
                        "INSERT INTO project_sandbox_policies(project_id, policy_json) VALUES (?, ?) "
                        "ON CONFLICT(project_id) DO UPDATE SET policy_json = excluded.policy_json",
                        (project["id"], project["after"].get("policy_json", canonical(policy))),
                    )
        connection.commit()
    except Exception:
        try:
            connection.execute("ROLLBACK")
        finally:
            connection.close()
            backup.unlink()
        raise
    try:
        prune_backups(home)
    except OSError:
        print("Warning: update succeeded but backup retention failed; remove only old app-sandbox-setup backups manually.")
    return f"Updated {len(changes)} projects. Backup: {json.dumps(str(backup), ensure_ascii=False)}"


def rollback_snapshot(path: Path) -> dict[str, Any]:
    connection = open_db(path)
    try:
        connection.execute("BEGIN")
        validate_schema(connection)
        return {row["id"]: dict(row) for row in connection.execute(
            "SELECT p.id, p.sandbox_enabled, s.policy_json FROM projects p "
            "LEFT JOIN project_sandbox_policies s ON s.project_id = p.id ORDER BY p.id"
        )}
    finally:
        connection.close()


def rollback_plan(connection: sqlite3.Connection, snapshot: dict[str, Any]) -> dict[str, Any]:
    changes, warnings, skipped = [], [], []
    projects = connection.execute(
        "SELECT p.id, p.name, p.sandbox_enabled, s.policy_json FROM projects p "
        "LEFT JOIN project_sandbox_policies s ON s.project_id = p.id ORDER BY p.id"
    ).fetchall()
    if not projects:
        raise SetupError(1, "No projects: add a project in the app first.")
    for row in projects:
        if row["id"] not in snapshot:
            skipped.append(row["id"])
            warnings.append(f'{display(row["name"])}: missing from backup; left untouched.')
            continue
        target = snapshot[row["id"]]
        states = []
        try:
            for state in (row, target):
                raw = state["policy_json"]
                states.append({"sandbox_enabled": state["sandbox_enabled"],
                               "policy": read_policy(raw) if raw is not None else None,
                               "policy_json": raw})
        except SetupError:
            skipped.append(row["id"])
            warnings.append(f'{display(row["name"])}: corrupt current/backup policy skipped.')
            continue
        changes.append({"id": row["id"], "name": row["name"], "before": states[0], "after": states[1]})
    digest = hashlib.sha256(canonical({
        "operation": "rollback", "projects": [{key: value for key, value in project.items() if key != "name"}
                                             for project in changes], "skipped": skipped,
    }).encode()).hexdigest()
    warnings.append("Rollback restores only shared projects' sandbox settings, never the whole DB. A fresh backup makes rollback reversible.")
    return {"operation": "rollback", "projects": changes, "skipped": skipped,
            "warnings": warnings, "digest": digest}


def probe_result(action: Any) -> str:
    try:
        action()
        return "OK"
    except OSError as error:
        return "denied" if error.errno in (errno.EPERM, errno.EACCES) else "error"


def probe_write(directory: Path) -> str:
    def action() -> None:
        descriptor, name = tempfile.mkstemp(prefix=".app-sandbox-verify-", dir=str(directory))
        try:
            os.write(descriptor, b"probe")
        finally:
            try:
                os.close(descriptor)
            finally:
                os.unlink(name)
    return probe_result(action)


def probe_db_open(db: Path) -> str:
    def action() -> None:
        # Opening is the entire probe; never read even one byte or query SQLite.
        with db.open("rb"):
            pass
    return probe_result(action)


def probe_loopback() -> str:
    def action() -> None:
        errors = []
        with socket.socket() as server:
            server.settimeout(1)
            server.bind(("127.0.0.1", 0))
            server.listen(1)

            def exchange() -> None:
                try:
                    peer, _ = server.accept()
                    with peer:
                        peer.settimeout(1)
                        if peer.recv(1) != b"x":
                            raise OSError("probe exchange failed")
                        peer.sendall(b"y")
                except OSError as error:
                    errors.append(error)

            thread = threading.Thread(target=exchange, daemon=True)
            thread.start()
            try:
                with socket.create_connection(server.getsockname(), timeout=1) as client:
                    client.sendall(b"x")
                    if client.recv(1) != b"y":
                        raise OSError("probe exchange failed")
            finally:
                thread.join(timeout=2)
            if errors:
                raise errors[0]
    return probe_result(action)


def hardened_cache_paths(home: Path) -> list[Path]:
    cache = home / "Library/Caches"
    copilot = cache / "copilot"
    result = [copilot] if copilot.is_dir() else []
    result += [child for child in copilot.glob("*")
               if child.is_dir() and child.name not in APP_CACHE_WRITABLE]
    for pattern in ("github-copilot*", "copilot-desktop-*"):
        result += [child for child in cache.glob(pattern) if child.is_dir()]
    return sorted(result)


def behavioral_probes(home: Path, db: Path) -> dict[str, str]:
    cache = next((path for path in (home / ".gradle", home / ".m2", home / "Library/Caches", Path("/tmp"))
                  if path.is_dir()), None)
    hardened = next((path for path in [home / ".config/git", *hardened_cache_paths(home),
                                       *(home / relative for relative in HARDENING_READONLY),
                                       *(home / relative for relative in RO_PATHS)]
                     if under(path, home) and path.is_dir()), None)
    return {
        "HOME write": probe_write(home), "DB open": probe_db_open(db), "loopback": probe_loopback(),
        "cache write": probe_write(cache) if cache else "unavailable",
        "readonly write": probe_write(hardened) if hardened else "unavailable",
    }


def verify(home: Path, db: Path, mask: bool) -> int:
    expected = {"HOME write": "denied", "DB open": "denied",
                "loopback": "denied" if mask else "OK", "cache write": "OK", "readonly write": "denied"}
    actual = behavioral_probes(home, db)
    print(f"Masking expectation: {'ON' if mask else 'OFF'}")
    print("probe | expected | actual")
    for name, value in expected.items():
        print(f"{name} | {value} | {actual[name]}")
    loopback_proxy = False
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        try:
            loopback_proxy |= urlsplit(os.environ.get(key, "")).hostname == "127.0.0.1"
        except ValueError:
            pass
    print("proxy env points to 127.0.0.1: " + ("yes" if loopback_proxy else "no"))
    print("GH_TOKEN set: " + ("yes" if os.environ.get("GH_TOKEN") else "no"))
    if actual["HOME write"] == "OK":
        print("this session is not sandboxed: start a new session or use /sandbox on.")
    print("Differences can be caused by enterprise managed settings. Verify in a NEW sandboxed session; unavailable/error probes do not prove protection.")
    return 0 if actual == expected else 7


def print_guide(db: Path, home: Path, mask: Optional[bool], no_docker: bool = False) -> int:
    warnings: list[str] = []
    paths = None
    projects = []
    connection = None
    status = 0
    try:
        connection = open_db(db)
        connection.execute("BEGIN")
        validate_schema(connection)
        plan = compute_plan(connection, home, mask, no_docker)
        projects = plan["projects"]
        warnings.extend(plan["warnings"])
    except SetupError as error:
        if error.code == 1:
            raise
        status = error.code
        warnings.append(str(error))
        warnings.append("DB paths unavailable; add your code folders manually.")
    except sqlite3.Error as error:
        status = db_error(error).code
        warnings.append("DB paths unavailable; add your code folders manually.")
    finally:
        if connection is not None:
            connection.close()
    if not projects:
        paths = profile_paths(home, mask, warnings, no_docker)
        projects = [{"name": "<project>", "after": {"policy": paths}}]
    labels = {"readwritePaths": "Additional read/write (Add folder)",
              "readonlyPaths": "Additional read-only", "deniedPaths": "Denied"}
    for project in projects:
        print(f'Settings → Projects → {display(project["name"])} → Sandbox')
        print("Sandbox new sessions: ON. Merge these paths; keep valid user additions.")
        policy = project["after"]["policy"]
        for field in PATH_FIELDS:
            print(f"{labels[field]} (diagnostic: {field}):")
            for path in policy[field]:
                print("  " + display(path))
        print("Outbound internet: ON; Local network: ON")
        for label, field in (("Git credentials", "allowGitCredentials"), ("GitHub CLI credentials", "allowGhCredentials")):
            value = policy.get(field, mask)
            print(f"{label}: {'preserve existing (new policies OFF)' if value is None else 'ON' if value else 'OFF'} (credential masking)")
    print("Add your code folders; never grant HOME itself or system areas.")
    print("Remove the retired rw grants: "
          + ", ".join(display("~/" + path) for path in RETIRED_GRANTS["readwritePaths"])
          + "; also remove rw entries exactly equal to readonly/denied paths; a narrower readonly/deny wins.")
    for warning in dict.fromkeys(warnings):
        print("Warning: " + warning)
    print("Policy changes apply to NEW sessions or after /restart-session. /sandbox off persists for this session even after restart: use /sandbox on + /restart-session, or a new session. Enterprise managed settings may override.")
    return status


def run(argv: Optional[Sequence[str]] = None) -> int:
    parser = UsageParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "apply", "guide", "rollback", "verify"])
    parser.add_argument("--confirm")
    parser.add_argument("--db", type=Path)
    parser.add_argument("--home", type=Path)
    masking = parser.add_mutually_exclusive_group()
    masking.add_argument("--mask-credentials", dest="mask_credentials", action="store_const", const=True, default=None)
    masking.add_argument("--no-mask-credentials", dest="mask_credentials", action="store_const", const=False)
    parser.add_argument("--no-docker", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--from", dest="backup", type=Path)
    args = parser.parse_args(argv)
    if args.command == "apply" and not args.confirm:
        parser.error("apply requires --confirm DIGEST")
    if args.command == "rollback" and args.backup is None:
        parser.error("rollback requires --from")
    home = (args.home if args.home is not None else Path.home()).resolve()
    db = args.db if args.db is not None else home / ".copilot/data.db"
    if args.command == "verify":
        return verify(home, db, bool(args.mask_credentials))
    if args.command == "guide":
        return print_guide(db, home, args.mask_credentials, args.no_docker)
    snapshot = rollback_snapshot(args.backup) if args.command == "rollback" else None
    writing = args.command == "apply" or (args.command == "rollback" and args.confirm is not None)
    connection = open_db(db, writing)
    try:
        connection.execute("BEGIN IMMEDIATE" if writing else "BEGIN")
        validate_schema(connection)
        plan = (rollback_plan(connection, snapshot) if snapshot is not None
                else compute_plan(connection, home, args.mask_credentials, args.no_docker))
        summary = None
        if writing:
            if args.confirm != plan["digest"]:
                print("Digest mismatch; rerun plan and confirm the new digest.")
                return 4
            summary = write_changes(connection, plan, db, home)
            if args.command == "apply":
                # Cleanup-only plans also need a successful transaction before removing anything.
                connection.commit()
                remove_placeholders(plan, home)
        print_plan(plan, args.json, summary)
    finally:
        connection.close()
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        return run(argv)
    except SetupError as error:
        print(str(error))
        return error.code
    except sqlite3.OperationalError as error:
        if "locked" in str(error).lower() or "busy" in str(error).lower():
            failure = db_error(error)
            print(str(failure))
            return failure.code
        print("Setup failed; any uncommitted transaction was rolled back. Inspect a fresh plan or use guide.")
        return 1
    except (sqlite3.Error, OSError, ValueError, RuntimeError, RecursionError):
        print("Setup failed; any uncommitted transaction was rolled back. Inspect a fresh plan or use guide.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
