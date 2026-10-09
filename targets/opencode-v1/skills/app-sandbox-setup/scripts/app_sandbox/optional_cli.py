"""Separately confirmed profile and Gradle file operations."""

import hashlib
import json
import os
import shutil
from pathlib import Path

from . import discovery, gradle_repair, policy, profile, profile_discovery, profile_store, rules, store, toolchain_discovery
from .facts import Facts
from .paths import SetupError, canonical, display

RESTART = ("Quit and restart the GitHub Copilot app completely (not just /restart-session): "
           "the app captures the shell environment at startup.")


def java_choice(choice, home, connection):
    if choice != "auto":
        if not Path(choice).is_absolute():
            raise SetupError(1, "--java-home requires an absolute validated JDK path or auto.")
        found = toolchain_discovery.validated_jdk(choice)
        if not found:
            raise SetupError(1, "--java-home is not a validated JDK (bin/java and matching release required).")
        return found["home"]
    majors = set()
    for row in store.project_rows(connection):
        raw = row["main_repo_path"]
        if isinstance(raw, str) and Path(raw).is_absolute():
            observation = toolchain_discovery.observe(Path(raw), home, capture_session=False)
            pin = observation["pins"].get("java")
            if pin:
                majors.add(pin["major"])
    if len(majors) > 1:
        raise SetupError(1, "--java-home auto refused: projects pin different Java majors; "
                         "per-project instructions handle them.")
    if not majors:
        raise SetupError(1, "--java-home auto requires a Java pin in a project; no default java is chosen.")
    found = next((jdk for jdk in toolchain_discovery.jdks(home) if jdk["major"] in majors), None)
    if not found:
        raise SetupError(1, "No validated JDK matches the project Java pin; install outside the sandbox.")
    return found["home"]


def policy_plan(connection, home, readonly):
    rows = store.project_rows(connection)
    existing = store.policy_rows(connection, rows)
    candidates = {Path(p) for p in readonly}
    for raw in existing.values():
        before = policy.read_policy(raw) if raw is not None else {}
        candidates.update(Path(p) for p in before.get("readwritePaths", []))
    candidates.update(parent for path in tuple(candidates) for parent in path.parents)
    facts = Facts(str(home), paths={str(p): discovery.path_fact(p) for p in candidates},
                  profile_readonly=tuple(readonly))
    readonly = policy.profile_opt_in_paths(rules.snapshot(), facts)
    # Only the opt-in policy hardening; do not absorb the default setup plan.
    changes = []
    for row in rows:
        raw = existing[row["id"]]
        before = policy.read_policy(raw) if raw is not None else None
        after = dict(before or {})
        after["readonlyPaths"] = list(dict.fromkeys(after.get("readonlyPaths", []) + list(readonly)))
        after["readwritePaths"] = [p for p in after.get("readwritePaths", [])
                                   if not any(facts.same(Path(p), Path(ro)) for ro in readonly)]
        changes.append({"id": row["id"], "name": row["name"],
                        "before": {"sandbox_enabled": row["sandbox_enabled"], "policy": before},
                        "after": {"sandbox_enabled": 1, "policy": after}})
    if not rows and readonly:
        raise SetupError(1, "No projects: add a project before activating the profile.")
    return {"projects": changes, "warnings": [], "digest": "", "skipped": []}


def profile_plan(args, home, connection):
    kind, path, state, old = profile_discovery.observe(home, args.shell)
    warnings = []
    selected = sorted(set(args.tool or ("java", "node", "pnpm")))
    new = old
    if args.action == "remove":
        new = None
    elif path:
        env = dict(os.environ)
        if args.shell:
            env["SHELL"] = args.shell
        session, warning = toolchain_discovery.session_environment(home, env)
        if session is None:
            raise SetupError(1, warning)
        java_home = java_choice(args.java_home, home, connection) if args.java_home else None
        resolved = {tool: shutil.which(tool, path=session["PATH"]) for tool in selected}
        failing = [tool for tool in selected if (
            tool == "java" and resolved[tool] == "/usr/bin/java" and not session.get("JAVA_HOME")
            or tool != "java" and not resolved[tool])]
        if failing:
            shims, readonly, mise = profile_discovery.mise_paths(home, {**env, **session})
            if not mise:
                shims, readonly = None, []
                failing = ["java"] if "java" in failing and java_home else []
                if not failing:
                    warnings.append("No mise found; Java profile guidance requires --java-home PATH or auto. "
                                    "Use per-project instructions for other missing tools.")
            new = {"shell": kind, "tools": failing, "shims": shims,
                   "java_home": java_home if not mise else None,
                   "readonly": list(dict.fromkeys(readonly + [str(path)]))} if failing else old
    else:
        warnings.append("Unsupported login shell: instructions only; no file or DB writes. "
                        "Add validated tool directories to your login PATH manually; never overwrite "
                        "JAVA_HOME. Use per-project toolchain instructions; no profile activation.")
    text = profile.merge(state["text"], profile.block(new) if new else "") if path else state["text"]
    readonly = new["readonly"] if new else []
    db_plan = policy_plan(connection, home, readonly) if readonly else {
        "projects": [], "warnings": [], "digest": "", "skipped": []}
    public = {"operation": "profile " + ("remove" if args.action == "remove" else "apply"),
              "target": str(path) if path else None, "tools": new["tools"] if new else [],
              "block": profile.block(new) if new else "", "readonly": readonly,
              "warnings": warnings, "changed": text != state["text"] or any(
                  p["before"] != p["after"] for p in db_plan["projects"])}
    public["policy_changes"] = [
        {"name": p["name"], "sandbox_enabled": p["after"]["sandbox_enabled"],
         "readonly_added": [path for path in p["after"]["policy"].get("readonlyPaths", [])
                            if path not in (p["before"]["policy"] or {}).get("readonlyPaths", [])],
         "readwrite_removed": [path for path in (p["before"]["policy"] or {}).get("readwritePaths", [])
                               if path not in p["after"]["policy"].get("readwritePaths", [])]}
        for p in db_plan["projects"] if p["before"] != p["after"]]
    public["digest"] = hashlib.sha256(canonical({
        "public": public, "file": profile_store.fingerprint(state),
        "db": [{k: p[k] for k in ("id", "before", "after")} for p in db_plan["projects"]],
    }).encode()).hexdigest()
    return public, path, state, text, db_plan


def run(argv):
    from .cli import UsageParser
    parser = UsageParser(description=__doc__)
    parser.add_argument("group", choices=("profile", "gradle-toolchains"))
    parser.add_argument("action", choices=("plan", "apply", "remove"))
    parser.add_argument("--confirm")
    parser.add_argument("--home", type=Path)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--shell")
    parser.add_argument("--tool", action="append", choices=("java", "node", "pnpm"))
    parser.add_argument("--java-home")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.action == "apply" and not args.confirm:
        raise SetupError(1, "apply requires --confirm DIGEST.")
    home = (args.home or Path.home()).resolve()
    db = args.db or home / ".copilot/data.db"
    writing = args.action == "apply" or args.action == "remove" and args.confirm is not None
    unsupported = args.group == "profile" and Path(args.shell or os.environ.get("SHELL", "")).name not in (
        "zsh", "bash", "fish")
    connection = None if unsupported else store.open_db(db, writing)
    try:
        if connection is not None:
            connection.execute("BEGIN IMMEDIATE" if writing else "BEGIN")
            store.validate_schema(connection)
        planner = profile_plan if args.group == "profile" else gradle_repair.plan
        public, path, state, text, db_plan = planner(args, home, connection)
        if writing:
            if args.confirm != public["digest"]:
                print("Digest mismatch; rerun plan and confirm the new digest.")
                return 4
            summary = store.write_changes(connection, db_plan, db, home)
            if connection is not None:
                connection.commit()
            try:
                backup = profile_store.write(path, state, text, home) if path else None
            except (OSError, ValueError, SetupError):
                if args.group != "profile":
                    raise SetupError(1, "Gradle properties write failed; inspect a fresh plan. "
                                     "No sandbox policy changes were requested.") from None
                raise SetupError(1, "Profile write failed AFTER DB commit; readonly shims stay committed. "
                                 "Profile state may be unchanged or already updated; inspect a fresh plan.") from None
            public.update(summary=summary or "Updated 0 projects.", backup_path=backup)
            if args.group == "profile" and args.action != "remove" and path and text:
                public["restart"] = RESTART
        if args.json:
            print(display(public))
        else:
            print("Target: " + display(public["target"]))
            if public.get("block"):
                print(public["block"])
            for change in public.get("policy_changes", []):
                print("Sandbox policy: " + display(change))
            for key in ("added", "removed"):
                for item in public.get(key, []):
                    print(key + ": " + display(item))
            for project in public.get("projects", []):
                print("Project: " + display(project["name"]))
                print("  " + project["reason"])
            if args.group == "gradle-toolchains" and not public["repair_needed"] and args.action != "remove":
                print("no repair needed")
            for warning in public["warnings"]:
                print("Warning: " + warning)
            if not public["changed"]:
                print("no changes")
            if writing:
                print(public["summary"])
                if public.get("restart"):
                    print(public["restart"])
            print("Plan digest: " + public["digest"])
    finally:
        if connection is not None:
            connection.close()
    return 0
