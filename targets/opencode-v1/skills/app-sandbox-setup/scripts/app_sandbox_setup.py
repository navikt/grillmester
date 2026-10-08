#!/usr/bin/env python3
"""Plan and confirm portable GitHub Copilot desktop sandbox settings."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence


RW_PATHS = (
    ".gradle", ".m2", ".npm", ".cache", ".config", ".local/share", ".local/state",
    "Library/Caches", "Library/pnpm", ".bun", ".nvm", ".rd", ".docker",
    ".copilot/session-state", "/tmp", "/private/tmp",
)
RO_PATHS = (
    ".copilot/installed-plugins", ".copilot/agents", ".copilot/extensions",
    ".copilot/marketplace-cache", ".agents", ".claude/skills", ".gitconfig",
)
DENIED_PATHS = (
    ".ssh", ".aws", ".gnupg", ".kube", ".config/gcloud", "Library/Keychains",
    ".netrc", ".copilot/data.db", ".copilot/data.db-wal", ".copilot/data.db-shm",
    ".copilot/app-sandbox-setup-backups", ".copilot/settings.json",
    ".copilot/config.json", ".copilot/mcp-oauth-config",
)
PATH_FIELDS = ("readwritePaths", "readonlyPaths", "deniedPaths")
BOOL_FIELDS = ("allowOutbound", "allowLocalNetwork", "allowGitCredentials", "allowGhCredentials")
CREDENTIAL_WARNING = (
    "Credential masking is OFF: sandboxed processes see the real GH_TOKEN / git credentials. "
    "With outbound allowed, any build script or dependency could exfiltrate them. "
    "Use --mask-credentials to mask them instead; the proxy forces loopback deny, "
    "breaking Gradle daemon, Testcontainers, dev servers and Playwright even with allowLocalNetwork=true."
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


def open_db(path: Path, writable: bool = False) -> sqlite3.Connection:
    connection = None
    try:
        connection = sqlite3.connect(
            path.resolve().as_uri() + ("?mode=rw" if writable else "?mode=ro"),
            uri=True, timeout=5,
        )
        connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except (sqlite3.Error, OSError, ValueError, RuntimeError):
        if connection is not None:
            connection.close()
        raise SetupError(
            2, "DB missing/unreadable: the sandbox is probably ON in this session, "
            "or the app was never started. Run with sandbox OFF or in a normal terminal."
        ) from None
    connection.row_factory = sqlite3.Row
    return connection


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


def safe_code_root(path: Path, home: Path) -> bool:
    if path == Path("/") or path == home or path in home.parents:
        return False
    if path in (Path("/Users"), Path("/Volumes")):
        return False
    for area in SYSTEM_AREAS:
        # Resolve system aliases too (e.g. /etc -> /private/etc on macOS).
        for system in (Path(area), Path(area).resolve()):
            if path == system or system in path.parents:
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
            specific = Path(raw).resolve()
        except (OSError, RuntimeError):
            warnings.append("Code path skipped: cannot resolve symlinks.")
            continue
        if has_control(str(specific)):
            warnings.append("Resolved code path skipped: control characters.")
            continue
        candidate = specific.parent.parent if worktree else specific.parent
        if not safe_code_root(candidate, home):
            warnings.append(f"unsafe code root {json.dumps(str(candidate))}; trying specific path.")
            candidate = specific
        if not safe_code_root(candidate, home):
            warnings.append(f"unsafe specific code path {json.dumps(str(candidate))}; skipped.")
            continue
        roots.append(str(candidate))
    return list(dict.fromkeys(roots))


def profile_paths(home: Path, mask: bool, warnings: list[str]) -> dict[str, list[str]]:
    warnings.extend([] if mask else [CREDENTIAL_WARNING])
    if mask:
        warnings.append("Credential masking is ON: its proxy forces loopback deny even with allowLocalNetwork=true.")
    for sibling in sorted((home / ".copilot").glob("data.db.*")):
        if sibling.is_file():
            warnings.append(
                f"Legacy sibling file {json.dumps(str(sibling))}: recommend deleting backup files "
                "because they are not covered by the deny list (never delete live WAL/SHM files)."
            )
    grants = {}
    for field, relatives in (("readwritePaths", RW_PATHS), ("readonlyPaths", RO_PATHS)):
        grants[field] = []
        for relative in relatives:
            path = str(home / relative)
            if Path(path).exists():
                grants[field].append(path)
            else:
                warnings.append(f"{json.dumps(path)}: skipped (missing; rerun after installing)")
    grants["deniedPaths"] = [str(home / relative) for relative in DENIED_PATHS]
    return grants


def compute_plan(connection: sqlite3.Connection, home: Path, mask: bool) -> dict[str, Any]:
    projects = connection.execute(
        "SELECT id, name, main_repo_path, sandbox_enabled FROM projects ORDER BY id"
    ).fetchall()
    warnings: list[str] = []
    grants = profile_paths(home, mask, warnings)
    roots = code_roots(connection, home, warnings)
    denied = grants["deniedPaths"]
    changes = []
    for row in projects:
        policy = connection.execute(
            "SELECT policy_json FROM project_sandbox_policies WHERE project_id = ?", (row["id"],)
        ).fetchone()
        before = read_policy(policy["policy_json"]) if policy else None
        after = dict(before or {})
        for field in PATH_FIELDS:
            existing = list(dict.fromkeys(after.get(field, [])))
            if field != "deniedPaths":
                for path in existing:
                    if path in denied:
                        warnings.append(f"removed {field} entry equal to denied path: {json.dumps(path)}")
                existing = [path for path in existing if path not in denied]
            additions = denied if field == "deniedPaths" else grants[field]
            if field == "readwritePaths":
                additions = roots + additions
            after[field] = list(dict.fromkeys(existing + additions))
        after.update(
            allowOutbound=True, allowLocalNetwork=True,
            allowGitCredentials=mask, allowGhCredentials=mask,
        )
        changes.append({
            "id": row["id"], "name": row["name"],
            "before": {"sandbox_enabled": row["sandbox_enabled"], "policy": before},
            "after": {"sandbox_enabled": 1, "policy": after},
        })
    full_change_set = [
        {"id": project["id"], "before": project["before"], "after": project["after"]}
        for project in changes
    ]
    digest = hashlib.sha256(canonical(full_change_set).encode()).hexdigest()
    return {"projects": changes, "digest": digest, "warnings": list(dict.fromkeys(warnings))}


def public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    projects = []
    for project in plan["projects"]:
        before, after = project["before"], project["after"]
        diff = {}
        if before["sandbox_enabled"] != after["sandbox_enabled"]:
            diff["sandbox_enabled"] = {"before": before["sandbox_enabled"], "after": after["sandbox_enabled"]}
        for field in PATH_FIELDS:
            old, new = (before["policy"] or {}).get(field, []), after["policy"][field]
            diff[field] = {
                "added": [path for path in new if path not in old],
                "removed": [path for path in old if path not in new],
            }
        for field in BOOL_FIELDS:
            old, new = (before["policy"] or {}).get(field), after["policy"][field]
            if old != new:
                diff[field] = {"before": old, "after": new}
        projects.append({"name": project["name"], "diff": diff, "changed": before != after})
    return {
        "projects": projects, "digest": plan["digest"], "warnings": plan["warnings"],
        "changed": bool(changed_projects(plan)),
    }


def print_plan(plan: dict[str, Any], json_mode: bool = False, summary: Optional[str] = None) -> None:
    if json_mode:
        result = public_plan(plan)
        if summary is not None:
            result["summary"] = summary
        print(canonical(result))
        return
    for project in plan["projects"]:
        print(f'Project: {json.dumps(project["name"])}')
        before, after = project["before"], project["after"]
        if before["sandbox_enabled"] != after["sandbox_enabled"]:
            print(f'  sandbox_enabled: {before["sandbox_enabled"]} -> {after["sandbox_enabled"]}')
        for field in PATH_FIELDS:
            old = (before["policy"] or {}).get(field, [])
            new = after["policy"][field]
            for path in old:
                if path not in new:
                    print(f"  - {field}: {json.dumps(path)}")
            for path in new:
                if path not in old:
                    print(f"  + {field}: {json.dumps(path)}")
        for field in BOOL_FIELDS:
            old = (before["policy"] or {}).get(field)
            new = after["policy"][field]
            if old != new:
                print(f"  {field}: {json.dumps(old)} -> {json.dumps(new)}")
    for warning in plan["warnings"]:
        print("Warning: " + warning)
    if not changed_projects(plan):
        print("no changes")
    if summary is not None:
        print(summary)
    print(f'Plan digest: {plan["digest"]}')


def changed_projects(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [project for project in plan["projects"] if project["before"] != project["after"]]


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
        target = sqlite3.connect(str(path))
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
    except Exception:
        path.unlink()
        raise
    return path


def print_guide(db: Path, home: Path, mask: bool) -> None:
    warnings: list[str] = []
    paths = profile_paths(home, mask, warnings)
    projects = []
    connection = None
    try:
        connection = open_db(db)
        connection.execute("BEGIN")
        projects = [row[0] for row in connection.execute("SELECT name FROM projects ORDER BY id")]
        paths["readwritePaths"] = code_roots(connection, home, warnings) + paths["readwritePaths"]
    except (SetupError, sqlite3.Error):
        warnings.append("DB paths unavailable; add your code folders manually.")
    finally:
        if connection is not None:
            connection.close()
    if not projects:
        print("Settings → Projects → <project> → Sandbox")
        print("For every project, add your code folders; never grant HOME itself or system areas.")
    for name in projects:
        print(f"Settings → Projects → {json.dumps(name)} → Sandbox")
    print("Enable Sandbox. Merge these paths with existing values; keep user additions.")
    for field in PATH_FIELDS:
        print(f"{field}:")
        for path in paths[field]:
            print("  " + json.dumps(path))
    print("Remove rw/ro entries exactly equal to denied paths; a narrower deny wins.")
    print(f"allowOutbound=true, allowLocalNetwork=true, allowGitCredentials={str(mask).lower()}, "
          f"allowGhCredentials={str(mask).lower()} (the last two control credential masking).")
    for warning in dict.fromkeys(warnings):
        print("Warning: " + warning)
    print("Start new sessions or /restart-session; the current session stays unsandboxed until restarted.")


def run(argv: Optional[Sequence[str]] = None) -> int:
    parser = UsageParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "apply", "guide"])
    parser.add_argument("--confirm")
    parser.add_argument("--db", type=Path)
    parser.add_argument("--home", type=Path)
    parser.add_argument("--mask-credentials", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "apply" and not args.confirm:
        parser.error("apply requires --confirm DIGEST")
    home = (args.home if args.home is not None else Path.home()).resolve()
    db = args.db if args.db is not None else home / ".copilot/data.db"
    if args.command == "guide":
        print_guide(db, home, args.mask_credentials)
        return 0
    connection = open_db(db, args.command == "apply")
    try:
        connection.execute("BEGIN IMMEDIATE" if args.command == "apply" else "BEGIN")
        validate_schema(connection)
        plan = compute_plan(connection, home, args.mask_credentials)
        summary = None
        if args.command == "apply":
            if args.confirm != plan["digest"]:
                print("Digest mismatch; rerun plan and confirm the new digest.")
                return 4
            changes = changed_projects(plan)
            if changes:
                backup = backup_db(db, home)
                for project in changes:
                    connection.execute(
                        "UPDATE projects SET sandbox_enabled = ? WHERE id = ?",
                        (project["after"]["sandbox_enabled"], project["id"]),
                    )
                    connection.execute(
                        "INSERT INTO project_sandbox_policies(project_id, policy_json) VALUES (?, ?) "
                        "ON CONFLICT(project_id) DO UPDATE SET policy_json = excluded.policy_json",
                        (project["id"], canonical(project["after"]["policy"])),
                    )
                connection.commit()
                summary = f"Updated {len(changes)} projects. Backup: {json.dumps(str(backup))}"
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
    except (sqlite3.Error, OSError, ValueError, RuntimeError, RecursionError):
        print("Setup failed; any uncommitted transaction was rolled back. Inspect a fresh plan or use guide.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
