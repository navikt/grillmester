"""SQLite validation, snapshots, writes, and bounded filesystem cleanup."""

from __future__ import annotations

import errno
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .paths import SetupError, canonical, changed_projects, display, home_relative, schema_error


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


def validate_schema(connection: sqlite3.Connection) -> None:
    required = {
        "projects": {"id": "TEXT", "name": "TEXT", "main_repo_path": "TEXT",
                     "sandbox_enabled": "INTEGER", "instructions": "TEXT"},
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
            if found["instructions"]["notnull"] != 1:
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
            # Only these project columns are written; unrelated UPDATE OF cannot fire.
            if columns is None or any(
                sql_identifier_name(column) in ("sandbox_enabled", "instructions")
                for column in re.findall(SQL_IDENTIFIER, columns, re.IGNORECASE | re.ASCII)
            ):
                raise schema_error()


def project_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    has_trust = any(row["name"] == "trusted_config_sha256"
                    for row in connection.execute("PRAGMA table_info(projects)"))
    trust = "trusted_config_sha256 IS NOT NULL" if has_trust else "0"
    return [dict(row) for row in connection.execute(
        "SELECT id, name, main_repo_path, sandbox_enabled, instructions, "
        + trust + " AS trusted_config FROM projects ORDER BY id"
    )]


def policy_rows(connection: sqlite3.Connection, projects: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for project in projects:
        row = connection.execute(
            "SELECT policy_json FROM project_sandbox_policies WHERE project_id = ?", (project["id"],)
        ).fetchone()
        result[project["id"]] = row["policy_json"] if row else None
    return result


def code_path_rows(connection: sqlite3.Connection, warnings: list[str]) -> list[tuple[Any, bool]]:
    paths = [(row[0], False) for row in connection.execute(
        "SELECT main_repo_path FROM projects ORDER BY id"
    )]
    try:
        paths += [(row[0], True) for row in connection.execute("SELECT path FROM worktrees ORDER BY id")]
    except sqlite3.Error:
        warnings.append("Worktree paths unavailable; add your code folders manually where needed.")
    return paths


def remove_placeholders(plan: dict[str, Any], home: Path) -> int:
    removed = 0
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
            os.rmdir(path.name, dir_fd=parent_fd)
            removed += 1
        except (OSError, ValueError, NotImplementedError):
            plan["warnings"].append("policy update succeeded but could not remove empty placeholder directory: "
                                    + display(home_relative(path, home))
                                    + "; left untouched, inspect a fresh plan.")
        finally:
            for descriptor in (child_fd, parent_fd, home_fd):
                if descriptor is not None:
                    os.close(descriptor)
    return removed


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
        # The writer's BEGIN IMMEDIATE prevents concurrent writes.
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
            if project["before"].get("instructions") != project["after"].get("instructions"):
                connection.execute("UPDATE projects SET instructions = ? WHERE id = ?",
                                   (project["after"]["instructions"], project["id"]))
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
    plan["backup_path"] = str(backup)
    return f"Updated {len(changes)} projects. Backup: {json.dumps(str(backup), ensure_ascii=False)}"


def rollback_snapshot(path: Path) -> dict[str, Any]:
    connection = open_db(path)
    try:
        connection.execute("BEGIN")
        validate_schema(connection)
        return {row["id"]: dict(row) for row in connection.execute(
            "SELECT p.id, p.sandbox_enabled, p.instructions, s.policy_json FROM projects p "
            "LEFT JOIN project_sandbox_policies s ON s.project_id = p.id ORDER BY p.id"
        )}
    finally:
        connection.close()


def rollback_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(
        "SELECT p.id, p.name, p.sandbox_enabled, p.instructions, s.policy_json FROM projects p "
        "LEFT JOIN project_sandbox_policies s ON s.project_id = p.id ORDER BY p.id"
    )]
