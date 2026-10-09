"""Pure policy construction: all host observations arrive as Facts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .facts import Facts, Options
from .paths import SetupError, canonical, display, has_control, home_relative, schema_error
from .rules import BOOL_FIELDS, CREDENTIAL_WARNING, MASKING_SCOPE_WARNING, PATH_FIELDS
from . import instructions, toolchain


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


def profile_opt_in_paths(rules: dict[str, Any], facts: Facts) -> list[str]:
    """The same conditional rule applies to observed and pending activation."""
    return list(facts.profile_readonly) if rules.get("PROFILE_OPT_IN") else []


def profile_paths(rules: dict[str, Any], facts: Facts, options: Options,
                  warnings: list[str]) -> dict[str, list[str]]:
    home = Path(facts.home)
    warnings.append(MASKING_SCOPE_WARNING)
    warnings.extend(facts.profile_warnings)
    # Discovery separates the backup diagnostics so masking retains its position.
    if options.mask:
        warnings.append("Credential masking is ON: its proxy forces loopback deny even with allowLocalNetwork=true.")
    warnings.extend(facts.backup_warnings)
    grants = {}
    missing = []
    docker = facts.docker
    if options.no_docker:
        warnings.append("--no-docker removes exact Docker rw grants; Testcontainers/docker will not work in the sandbox.")
    else:
        warnings.append("Docker socket = effectively unsandboxed host access: it can mount HOME, read ~/.ssh and write LaunchAgents. Use --no-docker to omit Docker grants.")
    warnings.append("Writable tool installs can persist changes that later execute outside the sandbox; they remain writable so agents can install tools.")
    for field, relatives in (("readwritePaths", rules["RW_PATHS"]), ("readonlyPaths", rules["RO_PATHS"])):
        grants[field] = []
        for relative in relatives:
            path = str(home / relative)
            if options.no_docker and any(facts.under(Path(path), Path(parent)) for parent in docker):
                continue
            if facts.path(Path(path)).exists:
                grants[field].append(path)
            else:
                missing.append(display(home_relative(Path(path), home)))
    missing_hardening = []
    for relative in rules["HARDENING_READONLY"]:
        path = home / relative
        if options.no_docker and any(facts.under(path, Path(parent)) for parent in docker):
            continue
        grants["readonlyPaths"].append(str(path))
        if not facts.path(path).exists:
            missing_hardening.append(display(home_relative(path, home)))
    if not options.no_docker:
        grants["readwritePaths"] += [path for path in docker if facts.path(Path(path)).exists
                                    and path not in grants["readwritePaths"]]
    if missing:
        warnings.append("Tools not installed (grants skipped; rerun after installing): " + ", ".join(missing))
    warnings.append("Hardening (missing paths listed as readonly; the app cannot block their creation, "
                    "so readonly applies only once the path exists): "
                    + ", ".join(missing_hardening))
    grants["deniedPaths"] = facts.required_denies(rules, grants["readwritePaths"])
    grants["readonlyPaths"] += list(facts.hardened_caches)
    grants["readonlyPaths"] += profile_opt_in_paths(rules, facts)
    grants["readwritePaths"] += list(facts.writable_caches)
    warnings.append("After an app update, rerun this skill: new version-named app cache directories need readonly hardening.")
    return grants


def clean_paths(rules: dict[str, Any], facts: Facts, row: dict[str, Any],
                after: dict[str, Any], owned_paths: set[str], warnings: list[str]) -> None:
    home = Path(facts.home)
    for field in PATH_FIELDS:
        clean = []
        for path in after.get(field, []):
            if has_control(path) or not Path(path).is_absolute():
                warnings.append(f'{display(row["name"])}: removed invalid {field} entry (relative path or control characters).')
                continue
            if field != "deniedPaths" and path not in owned_paths and (
                facts.under(home, Path(path)) or facts.same(Path(path), Path("/Users"))
                or facts.same(Path(path), home / ".copilot")
                or any(facts.under(Path(path), Path(area)) for area in rules["SYSTEM_AREAS"])
            ):
                warnings.append(f'{display(row["name"])}: broad existing {field} grant: {display(path)} (retained).')
            clean.append(path)
        after[field] = clean


def merge_paths(rules: dict[str, Any], facts: Facts, options: Options, row: dict[str, Any],
                after: dict[str, Any], grants: dict[str, list[str]], warnings: list[str]) -> None:
    home = Path(facts.home)
    denied = grants["deniedPaths"]
    retired_denies = {str(home / path): reason
                      for path, reason in rules["RETIRED_GRANTS"].get("deniedPaths", {}).items()}
    retired_denies.update({
        str(home / path): "path no longer qualifies for deny: expected type absent or empty "
                         "placeholder outside writable parents; no app-created directory needed"
        for path in rules["DENIED_PATHS"] if str(home / path) not in denied
    })
    user_denied = [path for path in after["deniedPaths"] if path not in retired_denies]
    for field in PATH_FIELDS:
        existing = list(dict.fromkeys(after.get(field, [])))
        retired = {str(home / path): reason
                   for path, reason in rules["RETIRED_GRANTS"].get(field, {}).items()}
        if field == "deniedPaths":
            retired.update(retired_denies)
        if field == "readonlyPaths" and rules.get("PROFILE_OPT_IN"):
            retired.update({path: "profile opt-in inactive" for path in facts.profile_candidates
                            if path not in facts.profile_readonly})
        if options.no_docker and field == "readwritePaths":
            retired.update({path: "--no-docker removes this exact grant" for path in facts.docker})
        for path in existing:
            if path in retired:
                warnings.append(f'{display(row["name"])}: removed retired {field} grant: {display(path)}; {retired[path]}.')
        existing = [path for path in existing if path not in retired]
        if field != "deniedPaths":
            blocked = denied + (grants["readonlyPaths"] if field == "readwritePaths" else [])
            for path in existing:
                if any(facts.same(Path(path), Path(block)) for block in blocked):
                    warnings.append(f'{display(row["name"])}: removed {field} entry equal to denied/readonly path: {display(path)}')
            existing = [path for path in existing
                        if not any(facts.same(Path(path), Path(block)) for block in blocked)]
        additions = denied if field == "deniedPaths" else grants[field]
        if field == "readwritePaths":
            additions = list(facts.roots) + additions
        if field != "deniedPaths":
            filtered = []
            for path in additions:
                if any(facts.under(Path(path), Path(block)) for block in user_denied + denied):
                    warnings.append(f'{display(row["name"])}: addition skipped under existing/required denied path: {display(path)}')
                elif field == "readwritePaths" and any(facts.same(Path(path), Path(ro)) for ro in grants["readonlyPaths"]):
                    continue
                else:
                    filtered.append(path)
            additions = filtered
        after[field] = list(dict.fromkeys(existing + additions))


def merge_booleans(row: dict[str, Any], after: dict[str, Any], options: Options,
                   warnings: list[str]) -> None:
    for field in ("allowOutbound", "allowLocalNetwork"):
        if after.get(field) is False:
            warnings.append(f'{display(row["name"])}: {field}=true overrides existing false.')
        after[field] = True
    for field in ("allowGitCredentials", "allowGhCredentials"):
        if options.mask is not None:
            if field in after and after[field] != options.mask:
                warnings.append(f'{display(row["name"])}: {field} credential value overridden by flag.')
            after[field] = options.mask
        else:
            after.setdefault(field, False)


def compute_plan(rules: dict[str, Any], facts: Facts, existing: dict[str, Any],
                 options: Options) -> dict[str, Any]:
    if not facts.projects:
        raise SetupError(1, "No projects: add a project in the app first, then rerun plan.")
    home = Path(facts.home)
    warnings: list[str] = []
    grants = profile_paths(rules, facts, options, warnings)
    grants["readonlyPaths"] += list(facts.git_paths)
    warnings.extend(facts.git_warnings)
    warnings.extend(facts.root_warnings)
    readwrite = list(facts.roots) + grants["readwritePaths"]
    grants["deniedPaths"] = facts.required_denies(rules, readwrite)
    placeholder_removals = [
        {"path": str(home / relative),
         "reason": "the app created a directory for a deny path; its parent is not writable "
                   "in the sandbox, so deny is unnecessary and the directory can break tools"}
        for relative in rules["DENIED_PATHS"] if facts.placeholder(rules, relative, readwrite)
    ]
    for entry in placeholder_removals:
        warnings.append(f'will remove empty placeholder directory: {display(entry["path"])}; {entry["reason"]}.')
    owned_paths = {path for paths in grants.values() for path in paths} | set(facts.roots)
    owned_paths.update(str(home / path) for path in rules["RW_PATHS"] + rules["RO_PATHS"] if Path(path).is_absolute())
    denied = grants["deniedPaths"]
    missing_denies = [
        display(home_relative(home / path, home))
        for path in rules["DENIED_PATHS"] if str(home / path) not in denied
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
    for row in facts.projects:
        raw = existing.get(row["id"])
        try:
            before = read_policy(raw) if raw is not None else None
        except SetupError:
            skipped.append(row["id"])
            warnings.append(f'{display(row["name"])}: corrupt policy skipped; repair this project manually with guide.')
            continue
        after = dict(before or {})
        old_text = row.get("instructions", "")
        new_text = old_text
        decisions = []
        manual_block = ""
        if not options.no_instructions:
            observation = facts.toolchains.get(row["id"], {})
            unpinned_gradle = observation.get("gradlew") and "java" not in observation.get("pins", {})
            if unpinned_gradle:
                example = max((jdk["major"] for jdk in observation.get("jdks", [])),
                              key=int, default="<major>")
                warnings.append(
                    f'{display(row["name"])[1:-1]}: Gradle project without a Java version pin; '
                    'the sandbox has no default java. Add a pin in the repository '
                    f'(e.g. `java = "{example}"` in .mise.toml, or jvmToolchain({example})).')
            warnings.extend(f'{display(row["name"])}: {warning}' for warning in observation.get("warnings", []))
            decisions = [] if unpinned_gradle else toolchain.decide(observation)
            warnings.extend(f'{display(row["name"])}: {item["warning"]}'
                            for item in decisions if item["warning"])
            try:
                # Validate markers even when repo config prevents a DB edit.
                instructions.bounds(old_text)
                if observation.get("repo_instructions"):
                    manual_block = instructions.block(decisions)
                    warnings.append(f'{display(row["name"])}: .github/github-app.yml instructions may overlay '
                                    'DB instructions (precedence unverified); DB instructions left untouched. '
                                    f'trusted config: {"yes" if row.get("trusted_config") else "no"}. '
                                    'Add the displayed block to that file manually.')
                else:
                    new_text = instructions.merge(old_text, instructions.block(decisions))
            except ValueError:
                skipped.append(row["id"])
                warnings.append(f'{display(row["name"])}: malformed toolchain markers; project skipped.')
                continue
        clean_paths(rules, facts, row, after, owned_paths, warnings)
        merge_paths(rules, facts, options, row, after, grants, warnings)
        merge_booleans(row, after, options, warnings)
        changes.append({
            "id": row["id"], "name": row["name"],
            "before": {"sandbox_enabled": row["sandbox_enabled"], "policy": before},
            "after": {"sandbox_enabled": 1, "policy": after},
            "toolchain": decisions,
            "manual_instructions": manual_block,
        })
        if not options.no_instructions:
            changes[-1]["before"]["instructions"] = old_text
            changes[-1]["after"]["instructions"] = new_text
    if any(not project["after"]["policy"][field] for project in changes
           for field in ("allowGitCredentials", "allowGhCredentials")):
        warnings.append(CREDENTIAL_WARNING)
    full_change_set = [
        {key: project[key] for key in ("id", "before", "after", "toolchain", "manual_instructions")}
        for project in changes
    ]
    digest_input = {"changes": full_change_set, "skipped": skipped,
                    "placeholder_removals": placeholder_removals, "backup_moves": list(facts.backup_moves)}
    digest = hashlib.sha256(canonical(digest_input).encode()).hexdigest()
    return {"projects": changes, "skipped": skipped, "digest": digest,
            "placeholder_removals": placeholder_removals, "warnings": list(dict.fromkeys(warnings)),
            "backup_moves": list(facts.backup_moves)}


def rollback_plan(projects: list[dict[str, Any]], snapshot: dict[str, Any],
                  no_instructions: bool = False) -> dict[str, Any]:
    changes, warnings, skipped = [], [], []
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
                if not no_instructions:
                    states[-1]["instructions"] = state.get("instructions", "")
        except SetupError:
            skipped.append(row["id"])
            warnings.append(f'{display(row["name"])}: corrupt current/backup policy skipped.')
            continue
        changes.append({"id": row["id"], "name": row["name"], "before": states[0], "after": states[1]})
    digest = hashlib.sha256(canonical({
        "operation": "rollback", "projects": [{key: value for key, value in project.items() if key != "name"}
                                             for project in changes], "skipped": skipped,
    }).encode()).hexdigest()
    warnings.append("Rollback restores only shared projects' sandbox settings and project instructions unless opted out, never the whole DB. A fresh backup makes rollback reversible.")
    return {"operation": "rollback", "projects": changes, "skipped": skipped,
            "warnings": warnings, "digest": digest}
