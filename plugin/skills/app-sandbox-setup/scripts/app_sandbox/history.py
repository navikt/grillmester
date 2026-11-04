"""Change only the shared session-history grant, with the normal write safeguards."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any, Optional, Sequence

from . import discovery, policy, rules, store
from .facts import Facts, Options
from .paths import Info, SetupError, canonical, display, has_control, same_path, schema_error


def plan(connection: sqlite3.Connection, home: Path, project: Optional[Path],
         no_session_history: bool) -> dict[str, Any]:
    projects = store.project_rows(connection)
    if project is not None:
        projects = [row for row in projects if isinstance(row["main_repo_path"], str)
                    and Path(row["main_repo_path"]).is_absolute()
                    and same_path(Path(row["main_repo_path"]), project)]
    if not projects or project is not None and len(projects) != 1:
        raise SetupError(1, "Choose existing app projects; --project requires the exact project directory.")
    existing = store.policy_rows(connection, projects)
    target = home / rules.SESSION_HISTORY_PATH
    paths = {target, home / ".copilot"}
    for raw in existing.values():
        try:
            parsed = policy.read_policy(raw) if raw is not None else {}
        except SetupError:
            continue
        paths.update(Path(path) for field in rules.PATH_FIELDS for path in parsed.get(field, [])
                     if Path(path).is_absolute() and not has_control(path))
    paths.update(parent for path in tuple(paths) for parent in path.parents)
    facts = Facts(str(home), projects=projects,
                  paths={str(path): discovery.path_fact(path) for path in paths})
    warnings: list[str] = []
    grants = policy.session_history_paths(rules.snapshot(), facts, Options(no_session_history=no_session_history),
                                         warnings)
    changes, skipped = [], []
    for row in projects:
        raw = existing[row["id"]]
        try:
            before = policy.read_policy(raw) if raw is not None else None
            if any(not Path(path).is_absolute() or has_control(path)
                   for field in rules.PATH_FIELDS for path in (before or {}).get(field, [])):
                raise schema_error()
        except SetupError:
            skipped.append(row["id"])
            warnings.append(f'{display(row["name"])}: corrupt policy skipped; repair it with guide.')
            continue
        after = dict(before or {})
        if grants and any(facts.under(target, Path(path)) for path in after.get("deniedPaths", [])):
            skipped.append(row["id"])
            warnings.append(f'{display(row["name"])}: history grant skipped under an existing denied path.')
            continue
        for field in ("readwritePaths", "readonlyPaths"):
            if field in after and (field == "readwritePaths" or no_session_history):
                after[field] = [path for path in after[field] if not facts.same(Path(path), target)]
        if grants:
            readonly = after.get("readonlyPaths", [])
            after["readonlyPaths"] = readonly + [path for path in grants if path not in readonly]
        if before is None and not after:
            after = None
        changes.append({
            "id": row["id"], "name": row["name"],
            "before": {"sandbox_enabled": row["sandbox_enabled"], "policy": before},
            "after": {"sandbox_enabled": row["sandbox_enabled"], "policy": after},
        })
    warnings.append(Info("History-only update: network, credential masking, Docker, instructions, "
                         "sandbox defaults and all other path entries are preserved. No history contents are read."))
    digest = hashlib.sha256(canonical({
        "operation": "history", "no_session_history": no_session_history,
        "directory": str(target), "identity": facts.path(target).inode,
        "projects": [{key: change[key] for key in ("id", "before", "after")} for change in changes],
        "skipped": skipped,
    }).encode()).hexdigest()
    return {"operation": "history", "projects": changes, "warnings": warnings,
            "digest": digest, "skipped": skipped}


def run(argv: Sequence[str]) -> int:
    from .cli import UsageParser, print_plan

    parser = UsageParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "apply"))
    parser.add_argument("--project", type=Path)
    parser.add_argument("--no-session-history", action="store_true")
    parser.add_argument("--confirm")
    parser.add_argument("--home", type=Path)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.project is not None and (not args.project.is_absolute() or has_control(str(args.project))):
        raise SetupError(1, "--project requires the exact absolute project directory.")
    if args.action == "apply" and not args.confirm:
        parser.error("apply requires --confirm DIGEST")
    home = (args.home or Path.home()).resolve()
    db = args.db or home / ".copilot/data.db"
    writing = args.action == "apply"
    connection = store.open_db(db, writing)
    try:
        connection.execute("BEGIN IMMEDIATE" if writing else "BEGIN")
        store.validate_schema(connection)
        proposed = plan(connection, home, args.project, args.no_session_history)
        summary = None
        if writing:
            if args.confirm != proposed["digest"]:
                print("Digest mismatch; rerun plan and confirm the new digest.")
                return 4
            summary = store.write_changes(connection, proposed, db, home) or "Updated 0 projects. Backup: none."
        print_plan(proposed, args.json, summary)
    finally:
        connection.close()
    return 0
