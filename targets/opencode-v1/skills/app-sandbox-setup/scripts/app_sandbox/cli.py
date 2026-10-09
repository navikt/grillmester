"""Plan and confirm portable GitHub Copilot desktop sandbox settings."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

from . import backups, discovery, instructions, optional_cli, policy, probes, rules, store
from .facts import Options
from .paths import SetupError, changed_projects, display


class UsageParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SetupError(1, "Usage error; see --help. apply requires --confirm DIGEST.")


def compute_plan(connection: sqlite3.Connection, home: Path, mask: Optional[bool],
                 no_docker: bool = False, no_instructions: bool = False,
                 move_backups: bool = False) -> dict[str, Any]:
    projects = store.project_rows(connection)
    if not projects:
        raise SetupError(1, "No projects: add a project in the app first, then rerun plan.")
    existing = store.policy_rows(connection, projects)
    warnings: list[str] = []
    paths = store.code_path_rows(connection, warnings)
    facts = discovery.gather(home, projects, paths, existing, warnings, no_docker=no_docker,
                             no_instructions=no_instructions, move_backups=move_backups)
    return policy.compute_plan(rules.snapshot(), facts, existing,
                               Options(mask, no_docker, no_instructions, move_backups))


def profile_paths(home: Path, mask: Optional[bool], warnings: list[str],
                  no_docker: bool = False) -> dict[str, list[str]]:
    facts = discovery.gather(home, (), (), {}, profile_only=True, no_docker=no_docker)
    return policy.profile_paths(rules.snapshot(), facts, Options(mask, no_docker), warnings)


def rollback_plan(connection: sqlite3.Connection, snapshot: dict[str, Any],
                  no_instructions: bool = False) -> dict[str, Any]:
    return policy.rollback_plan(store.rollback_rows(connection), snapshot, no_instructions)


def public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    projects = []
    for project in plan["projects"]:
        before, after = project["before"], project["after"]
        if before == after:
            continue
        diff = {}
        if before["sandbox_enabled"] != after["sandbox_enabled"]:
            diff["sandbox_enabled"] = {"before": before["sandbox_enabled"], "after": after["sandbox_enabled"]}
        for field in rules.PATH_FIELDS:
            old, new = (before["policy"] or {}).get(field, []), (after["policy"] or {}).get(field, [])
            diff[field] = {
                "added": [path for path in new if path not in old],
                "removed": [path for path in old if path not in new],
            }
        for field in rules.BOOL_FIELDS:
            old, new = (before["policy"] or {}).get(field), (after["policy"] or {}).get(field)
            if old != new:
                diff[field] = {"before": old, "after": new}
        if before.get("instructions") != after.get("instructions"):
            diff["instructions"] = instructions_diff(before["instructions"], after["instructions"])
        projects.append({"name": project["name"], "diff": diff, "changed": before != after,
                         "toolchain": project.get("toolchain", [])})
        projects[-1]["manual_instructions"] = project.get("manual_instructions", "")
        projects[-1]["policy_json_rewritten"] = rewritten_keys(before, after)
    result = {
        "projects": projects, "digest": plan["digest"], "warnings": plan["warnings"],
        "placeholder_removals": plan.get("placeholder_removals", []),
        "backup_moves": plan.get("backup_moves", []),
        "changed": bool(changed_projects(plan) or plan.get("placeholder_removals") or plan.get("backup_moves")),
    }
    result["unchanged_projects"] = len(plan["projects"]) - len(projects)
    result["toolchain_decisions"] = [{"name": project["name"], "decisions": project.get("toolchain", [])}
                                    for project in changed_projects(plan)]
    result["instructions_changes"] = [project["name"] for project in changed_projects(plan)
                                      if project["before"].get("instructions") != project["after"].get("instructions")]
    result["manual_instructions"] = [{"name": project["name"], "block": project["manual_instructions"]}
                                     for project in plan["projects"] if project.get("manual_instructions")]
    return result


def instructions_diff(before: str, after: str) -> dict[str, str]:
    result = {}
    for key, text in (("removed", before), ("added", after)):
        try:
            result[key] = instructions.display_block(text)
        except ValueError:
            result[key] = "(malformed managed block; contents not displayed)"
    return result


def rewritten_keys(before: dict[str, Any], after: dict[str, Any]) -> Optional[str]:
    if before["policy"] == after["policy"] and before.get("policy_json") == after.get("policy_json"):
        return None
    old, new = before["policy"] or {}, after["policy"] or {}
    keys = sorted((set(old) | set(new)) - set(rules.PATH_FIELDS + rules.BOOL_FIELDS))
    changed = [key for key in keys if (key in old) != (key in new) or old.get(key) != new.get(key)]
    return ", ".join(display(key) for key in changed) if changed else "formatting only"


def print_plan(plan: dict[str, Any], json_mode: bool = False, summary: Optional[str] = None) -> None:
    if json_mode:
        result = public_plan(plan)
        if summary is not None:
            result["summary"] = summary
            result["projects"] = [{"name": project["name"], "changed": True} for project in result["projects"]]
            result.update(projects_updated=len(changed_projects(plan)),
                          backup_path=plan.get("backup_path"),
                          placeholders_removed=plan.get("placeholders_removed", 0),
                          backups_moved=plan.get("backups_moved", 0))
        print(display(result))
        return
    projects = changed_projects(plan)
    for project in projects if summary is None else []:
        print(f'Project: {display(project["name"])}')
        before, after = project["before"], project["after"]
        if before["sandbox_enabled"] != after["sandbox_enabled"]:
            print(f'  sandbox_enabled: {before["sandbox_enabled"]} -> {after["sandbox_enabled"]}')
        for field in rules.PATH_FIELDS:
            old = (before["policy"] or {}).get(field, [])
            new = (after["policy"] or {}).get(field, [])
            for path in old:
                if path not in new:
                    print(f"  - {field}: {display(path)}")
            for path in new:
                if path not in old:
                    print(f"  + {field}: {display(path)}")
        for field in rules.BOOL_FIELDS:
            old, new = (before["policy"] or {}).get(field), (after["policy"] or {}).get(field)
            if old != new:
                print(f"  {field}: {json.dumps(old)} -> {json.dumps(new)}")
        rewritten = rewritten_keys(before, after)
        if rewritten:
            print("  policy JSON rewritten: " + rewritten)
        if before.get("instructions") != after.get("instructions"):
            for key, prefix in (("removed", "-"), ("added", "+")):
                for line in instructions_diff(before["instructions"], after["instructions"])[key].splitlines():
                    print(f"  {prefix} instructions: {line}")
    print(f'{len(plan["projects"]) - len(projects)} projects unchanged')
    if summary is None:
        for entry in plan.get("backup_moves", []):
            print(f'  move backup: {display(entry["source"])} -> {display(entry["destination"])}')
        for project in plan["projects"]:
            if project.get("manual_instructions"):
                print(f'Manual block for .github/github-app.yml ({display(project["name"])}):')
                print(project["manual_instructions"])
    for warning in plan["warnings"]:
        print("Warning: " + warning)
    if not changed_projects(plan) and not plan.get("placeholder_removals") and not plan.get("backup_moves"):
        print("no changes")
    if summary is not None:
        print(summary)
    print(f'Plan digest: {plan["digest"]}')


def print_guide(db: Path, home: Path, mask: Optional[bool], no_docker: bool = False) -> int:
    warnings: list[str] = []
    paths = None
    projects = []
    connection = None
    status = 0
    try:
        connection = store.open_db(db)
        connection.execute("BEGIN")
        store.validate_schema(connection)
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
        status = store.db_error(error).code
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
        policy_data = project["after"]["policy"]
        for field in rules.PATH_FIELDS:
            print(f"{labels[field]} (diagnostic: {field}):")
            for path in policy_data[field]:
                print("  " + display(path))
        print("Outbound internet: ON; Local network: ON")
        for label, field in (("Git credentials", "allowGitCredentials"), ("GitHub CLI credentials", "allowGhCredentials")):
            value = policy_data.get(field, mask)
            print(f"{label}: {'preserve existing (new policies OFF)' if value is None else 'ON' if value else 'OFF'} (credential masking)")
    print("Add your code folders; never grant HOME itself or system areas.")
    print("Remove the retired rw grants: "
          + ", ".join(display("~/" + path) for path in rules.RETIRED_GRANTS["readwritePaths"])
          + "; also remove rw entries exactly equal to readonly/denied paths; a narrower readonly/deny wins.")
    for warning in dict.fromkeys(warnings):
        print("Warning: " + warning)
    print("Policy changes apply to NEW sessions or after /restart-session. /sandbox off persists for this session even after restart: use /sandbox on + /restart-session, or a new session. Enterprise managed settings may override.")
    return status


def run(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("profile", "gradle-toolchains"):
        return optional_cli.run(argv)
    parser = UsageParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "apply", "guide", "rollback", "verify"])
    parser.add_argument("--confirm")
    parser.add_argument("--db", type=Path)
    parser.add_argument("--home", type=Path)
    masking = parser.add_mutually_exclusive_group()
    masking.add_argument("--mask-credentials", dest="mask_credentials", action="store_const", const=True, default=None)
    masking.add_argument("--no-mask-credentials", dest="mask_credentials", action="store_const", const=False)
    parser.add_argument("--no-docker", action="store_true")
    parser.add_argument("--no-instructions", action="store_true")
    parser.add_argument("--move-backups", action="store_true")
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
        return probes.verify(home, db, bool(args.mask_credentials))
    if args.command == "guide":
        return print_guide(db, home, args.mask_credentials, args.no_docker)
    snapshot = store.rollback_snapshot(args.backup) if args.command == "rollback" else None
    writing = args.command == "apply" or (args.command == "rollback" and args.confirm is not None)
    connection = store.open_db(db, writing)
    try:
        connection.execute("BEGIN IMMEDIATE" if writing else "BEGIN")
        store.validate_schema(connection)
        plan = (rollback_plan(connection, snapshot, args.no_instructions) if snapshot is not None
                else compute_plan(connection, home, args.mask_credentials, args.no_docker,
                                  args.no_instructions, args.move_backups))
        summary = None
        if writing:
            if args.confirm != plan["digest"]:
                print("Digest mismatch; rerun plan and confirm the new digest.")
                return 4
            summary = store.write_changes(connection, plan, db, home) or "Updated 0 projects. Backup: none."
            if args.command == "apply":
                connection.commit()
                removed = store.remove_placeholders(plan, home)
                plan["placeholders_removed"] = removed
                summary += f' Placeholder removals: {removed}/{len(plan.get("placeholder_removals", []))}.'
                moved = backups.move(plan, home)
                plan["backups_moved"] = moved
                summary += f' Moved backups: {moved}.'
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
            failure = store.db_error(error)
            print(str(failure))
            return failure.code
        print("Setup failed; any uncommitted transaction was rolled back. Inspect a fresh plan or use guide.")
        return 1
    except (sqlite3.Error, OSError, ValueError, RuntimeError, RecursionError):
        print("Setup failed; any uncommitted transaction was rolled back. Inspect a fresh plan or use guide.")
        return 1
