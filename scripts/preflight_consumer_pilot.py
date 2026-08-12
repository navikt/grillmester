#!/usr/bin/env python3
"""Create or verify the read-only contract for a Grillmester consumer pilot.

The only supported write is an explicit baseline JSON path outside the consumer
repository. Neither the consumer nor the Grillmester checkout is ever modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SCHEMA_VERSION = 3
PLUGIN_NAME = "grillmester"
MARKETPLACE_NAME = "grillmester"
PLUGIN_SPEC = f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"
PLUGIN_REPOSITORY = "navikt/grillmester"
HOVMESTER_REPOSITORY = "navikt/hovmester"
CATALOG_PATH = ".github/plugin/marketplace.json"
MANIFEST_PATH = ".github/.hovmester-manifest.json"
SETTINGS_PATH = ".github/copilot/settings.json"
AGENT_ROOTS = (".github/agents", ".claude/agents")
SKILL_ROOTS = (".github/skills", ".agents/skills", ".claude/skills")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
RELEASE_TAG = re.compile(
    r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*)?$"
)
HOVMESTER_CALLER = re.compile(
    r"^(?P<indent>\s*)uses:\s*(?P<quote>[\"']?)"
    r"navikt/hovmester/\.github/workflows/hovmester-sync\.ya?ml@"
    r"(?P<ref>[^\s\"'#]+)(?P=quote)\s*$",
    flags=re.MULTILINE | re.IGNORECASE,
)
ALLOWED_MANAGED_EXACT = {
    ".github/copilot-instructions.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
}
ALLOWED_MANAGED_PREFIXES = (
    ".github/agents/",
    ".github/skills/",
    ".github/instructions/",
    ".github/ISSUE_TEMPLATE/",
    ".github/PULL_REQUEST_TEMPLATE/",
)


class PreflightError(RuntimeError):
    """Raised when the requested audit cannot be completed safely."""


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PreflightError(f"required JSON file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PreflightError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PreflightError(f"expected a JSON object in {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def frontmatter_name(path: Path) -> str:
    """Return a skill's explicit ID without adding a YAML dependency."""

    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise PreflightError(f"missing frontmatter in {path}")
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.fullmatch(r"name:\s*(.+?)\s*", line)
        if match:
            value = match.group(1).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if value:
                return value
    raise PreflightError(f"frontmatter has no name in {path}")


def agent_id(path: Path) -> str:
    """Return Copilot's filename-derived agent ID."""

    if path.name.endswith(".agent.md"):
        return path.name[: -len(".agent.md")]
    if path.name.endswith(".md"):
        return path.name[: -len(".md")]
    raise PreflightError(f"unsupported agent filename: {path}")


def agent_files(root: Path) -> list[Path]:
    if root.is_symlink():
        raise PreflightError(f"agent root is a symlink: {root}")
    paths = list(root.glob("**/*.md"))
    symlinks = [path for path in paths if path.is_symlink()]
    if symlinks:
        raise PreflightError(f"agent path is a symlink: {symlinks[0]}")
    return [path for path in paths if path.is_file()]


def agent_roster(paths: Iterable[Path], root: Path) -> dict[str, list[str]]:
    roster: dict[str, list[str]] = {}
    for path in sorted(set(paths)):
        roster.setdefault(agent_id(path), []).append(path.relative_to(root).as_posix())
    return dict(sorted(roster.items()))


def skill_roster(paths: Iterable[Path], root: Path) -> dict[str, list[str]]:
    roster: dict[str, list[str]] = {}
    for path in sorted(set(paths)):
        if path.is_symlink():
            raise PreflightError(f"skill path is a symlink: {path}")
        roster.setdefault(frontmatter_name(path), []).append(
            path.relative_to(root).as_posix()
        )
    return dict(sorted(roster.items()))


def plugin_rosters(plugin_root: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    agents = agent_roster(agent_files(plugin_root / "plugin/agents"), plugin_root)
    skills = skill_roster(
        (plugin_root / "plugin/skills").glob("*/SKILL.md"), plugin_root
    )
    if not agents or not skills:
        raise PreflightError("plugin agent or skill roster is empty")
    return agents, skills


def consumer_rosters(
    consumer: Path,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    agent_paths: list[Path] = []
    for relative in AGENT_ROOTS:
        agent_paths.extend(agent_files(consumer / relative))
    skill_paths: list[Path] = []
    for relative in SKILL_ROOTS:
        skill_root = consumer / relative
        if skill_root.is_symlink():
            raise PreflightError(f"skill root is a symlink: {skill_root}")
        candidates = list(skill_root.glob("**/SKILL.md"))
        symlinks = [path for path in candidates if path.is_symlink()]
        if symlinks:
            raise PreflightError(f"skill path is a symlink: {symlinks[0]}")
        skill_paths.extend(path for path in candidates if path.is_file())
    return agent_roster(agent_paths, consumer), skill_roster(skill_paths, consumer)


def git_run(
    repository: Path, arguments: list[str], *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    result = subprocess.run(
        ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", *arguments],
        cwd=repository,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise PreflightError(
            f"git {' '.join(arguments)} failed in {repository}: {result.stderr.strip()}"
        )
    return result


def git_state(repository: Path) -> dict[str, Any]:
    top = git_run(repository, ["rev-parse", "--show-toplevel"], check=False)
    if top.returncode != 0:
        return {"repository": False, "clean": None, "head": None, "changes": []}
    if Path(top.stdout.strip()).resolve() != repository.resolve():
        raise PreflightError(f"path is not the Git root: {repository}")

    status = git_run(
        repository,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
    )
    head = git_run(repository, ["rev-parse", "HEAD"], check=False)
    changes = [item for item in status.stdout.split("\0") if item]
    return {
        "repository": True,
        "clean": not changes,
        "head": head.stdout.strip() if head.returncode == 0 else None,
        "changes": changes,
    }


def git_tracked_files(repository: Path) -> set[str]:
    result = git_run(repository, ["ls-tree", "-r", "--name-only", "-z", "HEAD"])
    return {path for path in result.stdout.split("\0") if path}


def git_diff(
    repository: Path, baseline_head: str
) -> dict[str, Any]:
    if FULL_SHA.fullmatch(baseline_head) is None:
        raise PreflightError("baseline consumer HEAD is not a full Git SHA")
    ancestor = git_run(
        repository,
        ["merge-base", "--is-ancestor", baseline_head, "HEAD"],
        check=False,
    )
    if ancestor.returncode != 0:
        return {
            "baselineHead": baseline_head,
            "ancestor": False,
            "changes": {},
            "problems": ["baseline HEAD is not an ancestor of the pilot HEAD"],
        }
    result = git_run(
        repository,
        ["diff", "--name-status", "-z", "--no-renames", baseline_head, "HEAD", "--"],
    )
    fields = [field for field in result.stdout.split("\0") if field]
    if len(fields) % 2:
        raise PreflightError("could not parse git diff --name-status output")
    changes: dict[str, str] = {}
    for index in range(0, len(fields), 2):
        status, path = fields[index], fields[index + 1]
        if path in changes:
            raise PreflightError(f"Git diff contains duplicate path: {path}")
        changes[path] = status
    return {
        "baselineHead": baseline_head,
        "ancestor": True,
        "changes": dict(sorted(changes.items())),
        "problems": [],
    }


def release_binding(
    plugin_root: Path, catalog_path: Path, expected_ref: str
) -> dict[str, Any]:
    """Bind the audited roster to an exact, clean release payload checkout."""

    if RELEASE_TAG.fullmatch(expected_ref) is None:
        raise PreflightError("expected ref must be a strict v-prefixed release tag")
    catalog_path = catalog_path.resolve()
    catalog_top = git_run(
        catalog_path.parent, ["rev-parse", "--show-toplevel"], check=False
    )
    if catalog_top.returncode != 0:
        raise PreflightError("release catalog must come from a Git checkout")
    catalog_root = Path(catalog_top.stdout.strip()).resolve()
    try:
        catalog_relative = catalog_path.relative_to(catalog_root).as_posix()
    except ValueError as exc:
        raise PreflightError("release catalog is outside its Git checkout") from exc
    if catalog_relative != CATALOG_PATH:
        raise PreflightError(
            f"release catalog must be the checkout's {CATALOG_PATH}"
        )
    catalog_git = git_state(catalog_root)
    if not catalog_git["repository"] or not catalog_git["head"]:
        raise PreflightError("release catalog checkout is not a Git repository")
    if not catalog_git["clean"]:
        raise PreflightError("release catalog checkout is dirty")
    catalog_sha = catalog_git["head"]
    tag = git_run(
        catalog_root,
        ["rev-parse", "--verify", f"refs/tags/{expected_ref}^{{commit}}"],
        check=False,
    )
    if tag.returncode != 0 or tag.stdout.strip() != catalog_sha:
        raise PreflightError(
            "expected release tag does not identify the catalog checkout HEAD"
        )
    catalog_blob = git_run(
        catalog_root, ["rev-parse", f"HEAD:{CATALOG_PATH}"]
    ).stdout.strip()
    expected_tree = f"100644 blob {catalog_blob}\t{CATALOG_PATH}"
    actual_tree = git_run(catalog_root, ["ls-tree", "-r", "HEAD"]).stdout.strip()
    if actual_tree != expected_tree:
        raise PreflightError(
            "release tag must identify a catalog-only commit with one regular catalog"
        )
    if git_run(catalog_root, ["hash-object", CATALOG_PATH]).stdout.strip() != catalog_blob:
        raise PreflightError("release catalog bytes differ from the tagged commit")

    catalog = load_json_object(catalog_path)
    if catalog.get("name") != MARKETPLACE_NAME:
        raise PreflightError("release catalog has the wrong marketplace name")
    plugins = catalog.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != 1:
        raise PreflightError("release catalog must contain exactly one plugin")
    plugin = plugins[0]
    if not isinstance(plugin, dict) or plugin.get("name") != PLUGIN_NAME:
        raise PreflightError("release catalog does not contain Grillmester")
    version = plugin.get("version")
    metadata = catalog.get("metadata")
    if not isinstance(version, str) or expected_ref != f"v{version}":
        raise PreflightError("expected ref does not match the release catalog version")
    if not isinstance(metadata, dict) or metadata.get("version") != version:
        raise PreflightError("release catalog metadata and plugin versions differ")

    source = plugin.get("source")
    source_sha = source.get("sha") if isinstance(source, dict) else None
    if source != {
        "source": "github",
        "repo": PLUGIN_REPOSITORY,
        "path": "plugin",
        "sha": source_sha,
    }:
        raise PreflightError("release catalog has an unexpected source shape")
    if not isinstance(source_sha, str) or FULL_SHA.fullmatch(source_sha) is None:
        raise PreflightError("release catalog does not pin a full source SHA")

    manifest = load_json_object(plugin_root / "plugin/plugin.json")
    if manifest.get("name") != PLUGIN_NAME or manifest.get("version") != version:
        raise PreflightError("plugin checkout manifest does not match the release catalog")
    if manifest.get("repository") != f"https://github.com/{PLUGIN_REPOSITORY}":
        raise PreflightError("plugin checkout manifest has the wrong repository")

    plugin_git = git_state(plugin_root)
    problems: list[str] = []
    if not plugin_git["repository"]:
        problems.append("plugin root is not a Git repository")
    elif plugin_git["head"] != source_sha:
        problems.append("plugin checkout HEAD does not equal catalog source.sha")
    elif not plugin_git["clean"]:
        problems.append("plugin checkout is dirty")
    return {
        "catalogPath": str(catalog_path),
        "catalogRepo": str(catalog_root),
        "catalogSha": catalog_sha,
        "catalogSha256": sha256(catalog_path),
        "catalogGit": catalog_git,
        "expectedRef": expected_ref,
        "version": version,
        "sourceSha": source_sha,
        "pluginGit": plugin_git,
        "problems": problems,
    }


def validate_managed_path(consumer: Path, value: str) -> str:
    if not value or "\\" in value or "\0" in value:
        raise PreflightError(f"unsafe Hovmester manifest path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or pure.as_posix() != value or any(
        part in {"", ".", ".."} for part in pure.parts
    ):
        raise PreflightError(f"unsafe Hovmester manifest path: {value!r}")
    if value not in ALLOWED_MANAGED_EXACT and not value.startswith(
        ALLOWED_MANAGED_PREFIXES
    ):
        raise PreflightError(
            f"Hovmester manifest path is outside the owned roots: {value}"
        )
    current = consumer
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise PreflightError(f"Hovmester manifest path traverses a symlink: {value}")
    return value


def unquote_yaml_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def caller_inputs_after(text: str, match: re.Match[str]) -> dict[str, str]:
    lines = text.splitlines()
    line_index = text[: match.start()].count("\n")
    parent_indent = len(match.group("indent"))
    in_with = False
    result: dict[str, str] = {}
    for line in lines[line_index + 1 :]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if not in_with:
            if indent == parent_indent and stripped == "with:":
                in_with = True
                continue
            if indent <= parent_indent:
                break
            continue
        if indent <= parent_indent:
            break
        field = re.fullmatch(r"([A-Za-z0-9_-]+):\s*(.*?)\s*", stripped)
        if field:
            result[field.group(1)] = unquote_yaml_scalar(field.group(2))
    return result


def csv_value(value: str | None) -> list[str]:
    if value is None:
        return []
    return sorted({item.strip() for item in value.split(",") if item.strip()})


def scan_hovmester_callers(consumer: Path) -> list[dict[str, Any]]:
    callers: list[dict[str, Any]] = []
    workflows_root = consumer / ".github/workflows"
    workflow_paths = sorted(
        set(workflows_root.glob("**/*.yml")) | set(workflows_root.glob("**/*.yaml"))
    )
    for workflow_path in workflow_paths:
        if workflow_path.is_symlink():
            raise PreflightError(f"workflow path is a symlink: {workflow_path}")
        if not workflow_path.is_file():
            continue
        workflow_text = workflow_path.read_text(encoding="utf-8")
        matches = list(HOVMESTER_CALLER.finditer(workflow_text))
        marker_count = len(
            re.findall(
                r"navikt/hovmester/\.github/workflows/hovmester-sync",
                workflow_text,
                flags=re.IGNORECASE,
            )
        )
        if marker_count != len(matches):
            raise PreflightError(
                f"unsupported or ambiguous Hovmester caller syntax in {workflow_path}"
            )
        for match in matches:
            inputs = caller_inputs_after(workflow_text, match)
            problems = [
                f"workflow input {name} is an expression"
                for name, value in inputs.items()
                if "${{" in value
            ]
            callers.append(
                {
                    "path": workflow_path.relative_to(consumer).as_posix(),
                    "sha256": sha256(workflow_path),
                    "ref": match.group("ref"),
                    "inputs": inputs,
                    "collections": csv_value(inputs.get("collections")),
                    "exclude": csv_value(inputs.get("exclude")),
                    "githubProject": inputs.get("github_project", ""),
                    "teamRepo": inputs.get("team_repo", ""),
                    "prAppId": inputs.get("pr_app_id", ""),
                    "problems": problems,
                }
            )
    return callers


def hovmester_state(consumer: Path) -> dict[str, Any]:
    callers = scan_hovmester_callers(consumer)
    manifest_path = consumer / MANIFEST_PATH
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return {
            "manifest": None,
            "manifestSha256": None,
            "source": None,
            "sourceSha": None,
            "managedFiles": [],
            "missingManagedFiles": [],
            "syncWorkflows": callers,
            "manifestProblems": ["required Hovmester manifest is missing"],
        }

    manifest = load_json_object(manifest_path)
    files = manifest.get("files")
    if not isinstance(files, list) or any(not isinstance(item, str) for item in files):
        raise PreflightError(f"invalid files list in {manifest_path}")
    if len(files) != len(set(files)):
        raise PreflightError(f"duplicate paths in {manifest_path}")
    managed_files = sorted(validate_managed_path(consumer, item) for item in files)
    missing = sorted(path for path in managed_files if not (consumer / path).is_file())
    source = manifest.get("source")
    source_sha = manifest.get("source_sha")
    manifest_problems: list[str] = []
    if source != HOVMESTER_REPOSITORY:
        manifest_problems.append("Hovmester manifest has an unexpected source")
    if not isinstance(source_sha, str) or FULL_SHA.fullmatch(source_sha) is None:
        manifest_problems.append("Hovmester manifest source_sha must be a full SHA")

    return {
        "manifest": MANIFEST_PATH,
        "manifestSha256": sha256(manifest_path),
        "source": source,
        "sourceSha": source_sha,
        "managedFiles": managed_files,
        "missingManagedFiles": missing,
        "syncWorkflows": callers,
        "manifestProblems": manifest_problems,
    }


def activation_state(consumer: Path, expected_ref: str) -> dict[str, Any]:
    settings_path = consumer / SETTINGS_PATH
    if not settings_path.is_file() or settings_path.is_symlink():
        return {
            "path": SETTINGS_PATH,
            "exists": False,
            "sha256": None,
            "status": "NOT_CONFIGURED",
            "ref": None,
            "problems": ["repository activation file is missing"],
        }
    try:
        settings = load_json_object(settings_path)
    except PreflightError as exc:
        return {
            "path": SETTINGS_PATH,
            "exists": True,
            "sha256": sha256(settings_path),
            "status": "INVALID",
            "ref": None,
            "problems": [str(exc)],
        }

    problems: list[str] = []
    marketplaces = settings.get("extraKnownMarketplaces")
    marketplace = (
        marketplaces.get(MARKETPLACE_NAME) if isinstance(marketplaces, dict) else None
    )
    source = marketplace.get("source") if isinstance(marketplace, dict) else None
    if not isinstance(source, dict):
        problems.append(f"extraKnownMarketplaces.{MARKETPLACE_NAME}.source is missing")
        source = {}
    if source.get("source") != "github":
        problems.append("marketplace source must be github")
    if source.get("repo") != PLUGIN_REPOSITORY:
        problems.append(f"marketplace repo must be {PLUGIN_REPOSITORY}")
    ref = source.get("ref")
    if ref != expected_ref:
        problems.append(f"marketplace ref must equal expected ref {expected_ref}")
    enabled = settings.get("enabledPlugins")
    if not isinstance(enabled, dict) or enabled.get(PLUGIN_SPEC) is not True:
        problems.append(f"enabledPlugins.{PLUGIN_SPEC} must be true")
    return {
        "path": SETTINGS_PATH,
        "exists": True,
        "sha256": sha256(settings_path),
        "status": "CONFIGURED" if not problems else "INVALID",
        "ref": ref if isinstance(ref, str) else None,
        "problems": problems,
    }


def protected_files(consumer: Path, managed: set[str]) -> dict[str, list[dict[str, Any]]]:
    instructions: set[Path] = set()
    for relative in ("AGENTS.md", "CLAUDE.md", ".github/copilot-instructions.md"):
        candidate = consumer / relative
        if candidate.is_symlink():
            raise PreflightError(f"protected instruction is a symlink: {candidate}")
        if candidate.is_file():
            instructions.add(candidate)
    instructions_root = consumer / ".github/instructions"
    if instructions_root.is_symlink():
        raise PreflightError(f"protected instruction root is a symlink: {instructions_root}")
    instruction_candidates = list(instructions_root.glob("**/*.instructions.md"))
    instruction_symlinks = [path for path in instruction_candidates if path.is_symlink()]
    if instruction_symlinks:
        raise PreflightError(
            f"protected instruction is a symlink: {instruction_symlinks[0]}"
        )
    instructions.update(path for path in instruction_candidates if path.is_file())

    templates: set[Path] = set()
    pull_request_template = consumer / ".github/PULL_REQUEST_TEMPLATE.md"
    if pull_request_template.is_symlink():
        raise PreflightError(f"protected template is a symlink: {pull_request_template}")
    if pull_request_template.is_file():
        templates.add(pull_request_template)
    for relative in (".github/PULL_REQUEST_TEMPLATE", ".github/ISSUE_TEMPLATE"):
        template_root = consumer / relative
        if template_root.is_symlink():
            raise PreflightError(f"protected template root is a symlink: {template_root}")
        candidates = list(template_root.glob("**/*"))
        symlinks = [path for path in candidates if path.is_symlink()]
        if symlinks:
            raise PreflightError(f"protected template is a symlink: {symlinks[0]}")
        templates.update(path for path in candidates if path.is_file())

    def entries(paths: set[Path]) -> list[dict[str, Any]]:
        return [
            {
                "path": path.relative_to(consumer).as_posix(),
                "sha256": sha256(path),
                "hovmesterManaged": path.relative_to(consumer).as_posix() in managed,
            }
            for path in sorted(paths)
        ]

    return {"instructions": entries(instructions), "templates": entries(templates)}


def collisions(
    plugin: dict[str, list[str]],
    local: dict[str, list[str]],
    managed: set[str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for component_id in sorted(set(plugin) & set(local)):
        for local_path in local[component_id]:
            result.append(
                {
                    "id": component_id,
                    "localPath": local_path,
                    "pluginPaths": plugin[component_id],
                    "hovmesterManaged": local_path in managed,
                }
            )
    return result


def remove_roster_paths(
    roster: dict[str, list[str]], removed: set[str]
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for component_id, paths in sorted(roster.items()):
        kept = [path for path in paths if path not in removed]
        if kept:
            result[component_id] = kept
    return result


def protected_pairs(snapshot: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    for group in ("instructions", "templates"):
        values = snapshot.get(group)
        if not isinstance(values, list):
            raise PreflightError("baseline protected-file snapshot is invalid")
        pairs: list[dict[str, str]] = []
        for item in values:
            if not isinstance(item, dict):
                raise PreflightError("baseline protected-file entry is invalid")
            path, digest = item.get("path"), item.get("sha256")
            if not isinstance(path, str) or not isinstance(digest, str):
                raise PreflightError("baseline protected-file entry is invalid")
            pairs.append({"path": path, "sha256": digest})
        result[group] = sorted(pairs, key=lambda item: item["path"])
    return result


def approved_removals(
    managed_files: list[str],
    agent_collisions: list[dict[str, Any]],
    skill_collisions: list[dict[str, Any]],
) -> list[str]:
    removals = {item["localPath"] for item in agent_collisions}
    for item in skill_collisions:
        skill_root = PurePosixPath(item["localPath"]).parent.as_posix()
        removals.update(
            path
            for path in managed_files
            if path == skill_root or path.startswith(f"{skill_root}/")
        )
    return sorted(removals)


def relevant_tracked_paths(report: dict[str, Any]) -> set[str]:
    paths = set(report["hovmester"]["managedFiles"])
    paths.update(item["path"] for item in report["hovmester"]["syncWorkflows"])
    paths.update(
        item["path"]
        for values in report["preserve"].values()
        for item in values
    )
    paths.update(
        path
        for roster in report["localComponents"].values()
        for values in roster.values()
        for path in values
    )
    if report["hovmester"]["manifest"]:
        paths.add(report["hovmester"]["manifest"])
    if report["activation"]["exists"]:
        paths.add(report["activation"]["path"])
    return paths


def snapshot(
    plugin_root: Path,
    consumer: Path,
    release_catalog: Path,
    expected_ref: str,
) -> dict[str, Any]:
    plugin_root = plugin_root.resolve()
    consumer = consumer.resolve()
    if not consumer.is_dir():
        raise PreflightError(f"consumer directory does not exist: {consumer}")
    release = release_binding(plugin_root, release_catalog.resolve(), expected_ref)
    plugin_agents, plugin_skills = plugin_rosters(plugin_root)
    local_agents, local_skills = consumer_rosters(consumer)
    hovmester = hovmester_state(consumer)
    managed = set(hovmester["managedFiles"])
    return {
        "release": release,
        "consumer": {"path": str(consumer), "git": git_state(consumer)},
        "plugin": {
            "path": str(plugin_root),
            "name": PLUGIN_NAME,
            "agentCount": len(plugin_agents),
            "skillCount": len(plugin_skills),
            "agentIds": sorted(plugin_agents),
            "skillIds": sorted(plugin_skills),
        },
        "activation": activation_state(consumer, expected_ref),
        "hovmester": hovmester,
        "localComponents": {"agentIds": local_agents, "skillIds": local_skills},
        "collisions": {
            "agents": collisions(plugin_agents, local_agents, managed),
            "skills": collisions(plugin_skills, local_skills, managed),
        },
        "preserve": protected_files(consumer, managed),
    }


def baseline_contract(report: dict[str, Any]) -> dict[str, Any] | None:
    callers = report["hovmester"]["syncWorkflows"]
    if len(callers) != 1:
        return None
    collision_entries = report["collisions"]["agents"] + report["collisions"]["skills"]
    collision_paths = sorted(item["localPath"] for item in collision_entries)
    collision_ids = sorted({item["id"] for item in collision_entries})
    removals = approved_removals(
        report["hovmester"]["managedFiles"],
        report["collisions"]["agents"],
        report["collisions"]["skills"],
    )
    caller = callers[0]
    return {
        "baselineHead": report["consumer"]["git"]["head"],
        "callerWorkflowPaths": [caller["path"]],
        "collisionComponentPaths": collision_paths,
        "collisionIds": collision_ids,
        "approvedManagedRemovals": removals,
        "expectedManifestFiles": sorted(
            set(report["hovmester"]["managedFiles"]) - set(removals)
        ),
        "expectedLocalComponents": {
            "agentIds": remove_roster_paths(
                report["localComponents"]["agentIds"], set(collision_paths)
            ),
            "skillIds": remove_roster_paths(
                report["localComponents"]["skillIds"], set(collision_paths)
            ),
        },
        "syncInputs": {
            "collections": caller["collections"],
            "exclude": sorted(set(caller["exclude"]) | set(collision_ids)),
            "githubProject": caller["githubProject"],
            "teamRepo": caller["teamRepo"],
            "prAppId": caller["prAppId"],
        },
    }


def build_baseline_report(
    plugin_root: Path,
    consumer: Path,
    release_catalog: Path,
    expected_ref: str,
) -> dict[str, Any]:
    report = snapshot(plugin_root, consumer, release_catalog, expected_ref)
    blockers: list[str] = list(report["release"]["problems"])
    consumer_git = report["consumer"]["git"]
    hovmester = report["hovmester"]
    callers = hovmester["syncWorkflows"]
    if not consumer_git["repository"]:
        blockers.append("consumer is not a Git repository")
    elif not consumer_git["clean"]:
        blockers.append("consumer worktree is dirty; use a clean disposable worktree")
    blockers.extend(hovmester["manifestProblems"])
    if hovmester["missingManagedFiles"]:
        blockers.append("Hovmester manifest references missing managed files")
    if len(callers) != 1:
        blockers.append("baseline requires exactly one unambiguous Hovmester caller")
    elif not callers[0]["collections"]:
        blockers.append("Hovmester caller must declare a literal collections input")
    elif callers[0]["problems"]:
        blockers.extend(callers[0]["problems"])
    collision_entries = report["collisions"]["agents"] + report["collisions"]["skills"]
    if any(not item["hovmesterManaged"] for item in collision_entries):
        blockers.append("a colliding local component is not Hovmester-managed")

    if consumer_git["repository"] and consumer_git["clean"]:
        tracked = git_tracked_files(consumer.resolve())
        missing_tracked = sorted(relevant_tracked_paths(report) - tracked)
    else:
        missing_tracked = []
    if missing_tracked:
        blockers.append("baseline-relevant files are not tracked at consumer HEAD")

    contract = baseline_contract(report)
    report.update(
        {
            "schemaVersion": SCHEMA_VERSION,
            "mode": "baseline",
            "verdict": "BLOCKED",
            "baselineWritable": not blockers,
            "blockers": blockers
            + (["baseline captured; migration has not been verified"] if not blockers else []),
            "migrationContract": contract,
            "trackedProblems": missing_tracked,
        }
    )
    return report


def validate_baseline_artifact(baseline: dict[str, Any]) -> dict[str, Any]:
    if baseline.get("schemaVersion") != SCHEMA_VERSION or baseline.get("mode") != "baseline":
        raise PreflightError("baseline artifact has an unsupported schema or mode")
    if baseline.get("verdict") != "BLOCKED" or baseline.get("baselineWritable") is not True:
        raise PreflightError("baseline artifact was not eligible for migration")
    contract = baseline.get("migrationContract")
    if not isinstance(contract, dict):
        raise PreflightError("baseline artifact has no migration contract")
    required_objects = (
        "release",
        "consumer",
        "plugin",
        "activation",
        "hovmester",
        "localComponents",
        "collisions",
        "preserve",
    )
    if any(not isinstance(baseline.get(key), dict) for key in required_objects):
        raise PreflightError("baseline artifact is incomplete")
    release = baseline["release"]
    if (
        RELEASE_TAG.fullmatch(release.get("expectedRef", "")) is None
        or FULL_SHA.fullmatch(release.get("catalogSha", "")) is None
        or re.fullmatch(r"[0-9a-f]{64}", release.get("catalogSha256", "")) is None
        or FULL_SHA.fullmatch(release.get("sourceSha", "")) is None
    ):
        raise PreflightError("baseline release identity is incomplete")

    expected = baseline_contract(baseline)
    if expected is None or contract != expected:
        raise PreflightError("baseline migration contract is internally inconsistent")
    if baseline["blockers"] != ["baseline captured; migration has not been verified"]:
        raise PreflightError("baseline artifact contains unresolved capture blockers")
    protected_pairs(baseline["preserve"])
    return contract


def add_comparison(
    comparisons: dict[str, dict[str, Any]],
    name: str,
    expected: Any,
    actual: Any,
) -> None:
    comparisons[name] = {"matches": expected == actual, "expected": expected, "actual": actual}


def expected_git_diff(
    baseline: dict[str, Any], current: dict[str, Any], contract: dict[str, Any]
) -> dict[str, str]:
    expected: dict[str, str] = {}
    for path in contract["callerWorkflowPaths"]:
        expected[path] = "D"
    for path in contract["approvedManagedRemovals"]:
        expected[path] = "D"

    baseline_activation = baseline["activation"]
    current_activation = current["activation"]
    if not baseline_activation["exists"]:
        expected[SETTINGS_PATH] = "A"
    elif baseline_activation["sha256"] != current_activation["sha256"]:
        expected[SETTINGS_PATH] = "M"

    if baseline["hovmester"]["manifestSha256"] != current["hovmester"]["manifestSha256"]:
        expected[MANIFEST_PATH] = "M"
    return dict(sorted(expected.items()))


def build_postflight_report(
    plugin_root: Path,
    consumer: Path,
    release_catalog: Path,
    expected_ref: str,
    baseline_path: Path,
) -> dict[str, Any]:
    baseline_path = baseline_path.resolve()
    consumer = consumer.resolve()
    try:
        baseline_path.relative_to(consumer)
    except ValueError:
        pass
    else:
        raise PreflightError("baseline artifact must live outside the consumer repository")
    baseline = load_json_object(baseline_path)
    contract = validate_baseline_artifact(baseline)
    report = snapshot(plugin_root, consumer, release_catalog, expected_ref)
    blockers: list[str] = list(report["release"]["problems"])
    comparisons: dict[str, dict[str, Any]] = {}

    add_comparison(
        comparisons,
        "releaseTag",
        baseline["release"]["expectedRef"],
        report["release"]["expectedRef"],
    )
    add_comparison(
        comparisons,
        "releaseSourceSha",
        baseline["release"]["sourceSha"],
        report["release"]["sourceSha"],
    )
    add_comparison(
        comparisons,
        "releaseCatalogSha",
        baseline["release"]["catalogSha"],
        report["release"]["catalogSha"],
    )
    add_comparison(
        comparisons,
        "releaseCatalogSha256",
        baseline["release"]["catalogSha256"],
        report["release"]["catalogSha256"],
    )
    add_comparison(
        comparisons,
        "pluginAgentIds",
        baseline["plugin"]["agentIds"],
        report["plugin"]["agentIds"],
    )
    add_comparison(
        comparisons,
        "pluginSkillIds",
        baseline["plugin"]["skillIds"],
        report["plugin"]["skillIds"],
    )
    add_comparison(
        comparisons,
        "protectedFiles",
        protected_pairs(baseline["preserve"]),
        protected_pairs(report["preserve"]),
    )
    add_comparison(
        comparisons,
        "localComponents",
        contract["expectedLocalComponents"],
        report["localComponents"],
    )
    add_comparison(
        comparisons,
        "manifestFiles",
        contract["expectedManifestFiles"],
        report["hovmester"]["managedFiles"],
    )
    add_comparison(
        comparisons,
        "hovmesterSource",
        {
            "source": baseline["hovmester"]["source"],
            "sourceSha": baseline["hovmester"]["sourceSha"],
        },
        {
            "source": report["hovmester"]["source"],
            "sourceSha": report["hovmester"]["sourceSha"],
        },
    )
    add_comparison(
        comparisons,
        "callerWorkflowsRemoved",
        [],
        report["hovmester"]["syncWorkflows"],
    )
    add_comparison(
        comparisons,
        "collisionsRemoved",
        {"agents": [], "skills": []},
        report["collisions"],
    )
    add_comparison(
        comparisons,
        "approvedPathsRemoved",
        [],
        sorted(
            path
            for path in contract["approvedManagedRemovals"]
            if (consumer / path).exists() or (consumer / path).is_symlink()
        ),
    )

    consumer_git = report["consumer"]["git"]
    if not consumer_git["repository"]:
        blockers.append("consumer is not a Git repository")
        diff = {
            "baselineHead": contract["baselineHead"],
            "ancestor": False,
            "changes": {},
            "problems": ["consumer is not a Git repository"],
        }
    else:
        if not consumer_git["clean"]:
            blockers.append("consumer worktree is dirty; verify a clean pilot commit")
        diff = git_diff(consumer, contract["baselineHead"])
    expected_diff = expected_git_diff(baseline, report, contract)
    add_comparison(comparisons, "gitDiff", expected_diff, diff["changes"])
    if diff["problems"]:
        blockers.extend(diff["problems"])

    if report["activation"]["status"] != "CONFIGURED":
        blockers.append("repository activation does not use the exact release tag")
    blockers.extend(report["hovmester"]["manifestProblems"])
    if report["hovmester"]["missingManagedFiles"]:
        blockers.append("postflight manifest references missing managed files")

    if consumer_git["repository"] and consumer_git["clean"]:
        tracked = git_tracked_files(consumer)
        missing_tracked = sorted(relevant_tracked_paths(report) - tracked)
    else:
        missing_tracked = []
    if missing_tracked:
        blockers.append("postflight-relevant files are not tracked at pilot HEAD")
    for name, comparison in comparisons.items():
        if not comparison["matches"]:
            blockers.append(f"baseline comparison failed: {name}")

    report.update(
        {
            "schemaVersion": SCHEMA_VERSION,
            "mode": "postflight",
            "verdict": "MIGRATION_PREFLIGHT_PASSED" if not blockers else "BLOCKED",
            "blockers": blockers,
            "baselinePath": str(baseline_path),
            "migrationContract": contract,
            "comparisons": comparisons,
            "gitDiff": diff,
            "trackedProblems": missing_tracked,
        }
    )
    return report


def git_metadata_roots(repository: Path) -> set[Path]:
    """Return Git metadata directories, including a linked worktree common dir."""

    roots: set[Path] = set()
    for argument in ("--absolute-git-dir", "--git-common-dir"):
        result = git_run(repository, ["rev-parse", argument], check=False)
        if result.returncode != 0:
            continue
        value = Path(result.stdout.strip())
        roots.add((value if value.is_absolute() else repository / value).resolve())
    return roots


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def write_baseline(
    report: dict[str, Any],
    output: Path,
    consumer: Path,
    plugin_root: Path,
) -> Path:
    if report.get("baselineWritable") is not True:
        raise PreflightError("baseline has blockers and will not be written")
    output = output.resolve()
    consumer = consumer.resolve()
    plugin_root = plugin_root.resolve()
    release = report.get("release")
    catalog_repo_value = release.get("catalogRepo") if isinstance(release, dict) else None
    if not isinstance(catalog_repo_value, str) or not catalog_repo_value:
        raise PreflightError("baseline report has no bound release catalog checkout")
    catalog_repo = Path(catalog_repo_value).resolve()
    protected_roots = {consumer, plugin_root, catalog_repo}
    protected_roots.update(git_metadata_roots(consumer))
    protected_roots.update(git_metadata_roots(plugin_root))
    protected_roots.update(git_metadata_roots(catalog_repo))
    protected_roots = {root.resolve() for root in protected_roots}
    if any(path_is_within(output, root) for root in protected_roots):
        raise PreflightError(
            "baseline output must live outside the consumer, plugin source, "
            "release catalog checkout, and their Git metadata"
        )
    if not output.parent.is_dir():
        raise PreflightError(f"baseline output parent does not exist: {output.parent}")
    try:
        with output.open("x", encoding="utf-8") as target:
            json.dump(report, target, indent=2, sort_keys=True, ensure_ascii=False)
            target.write("\n")
    except FileExistsError as exc:
        raise PreflightError(f"refusing to overwrite baseline: {output}") from exc
    return output


def print_human(report: dict[str, Any]) -> None:
    print(f"GRILLMESTER_CONSUMER_PILOT: {report['verdict']}")
    print(f"Mode: {report['mode']}")
    print(f"Consumer: {report['consumer']['path']}")
    print(f"Release: {report['release']['expectedRef']} ({report['release']['sourceSha']})")
    print(f"Activation: {report['activation']['status']}")
    print(f"Hovmester source SHA: {report['hovmester']['sourceSha'] or 'none'}")
    print(f"Hovmester caller count: {len(report['hovmester']['syncWorkflows'])}")
    print(
        "Collisions: "
        f"{len(report['collisions']['agents'])} agent(s), "
        f"{len(report['collisions']['skills'])} skill(s)"
    )
    if report["blockers"]:
        print("Blockers/status:")
        for blocker in report["blockers"]:
            print(f"- {blocker}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "consumer", type=Path, help="Path to the consumer repository Git root"
    )
    parser.add_argument(
        "--plugin-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Clean Grillmester source checkout pinned by the release catalog",
    )
    parser.add_argument(
        "--release-catalog",
        type=Path,
        required=True,
        help="Exact release marketplace.json used by the reviewed tag",
    )
    parser.add_argument(
        "--expected-ref",
        required=True,
        help="Exact reviewed v-prefixed release tag",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--write-baseline",
        type=Path,
        help="Create a new baseline JSON outside the consumer repository",
    )
    mode.add_argument(
        "--baseline",
        type=Path,
        help="Verify the pilot commit against an existing baseline JSON",
    )
    parser.add_argument("--json", action="store_true", help="Print deterministic JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        if args.write_baseline is not None:
            report = build_baseline_report(
                args.plugin_root,
                args.consumer,
                args.release_catalog,
                args.expected_ref,
            )
            if report["baselineWritable"]:
                write_baseline(
                    report,
                    args.write_baseline,
                    args.consumer,
                    args.plugin_root,
                )
        else:
            report = build_postflight_report(
                args.plugin_root,
                args.consumer,
                args.release_catalog,
                args.expected_ref,
                args.baseline,
            )
    except PreflightError as exc:
        print(f"preflight error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print_human(report)
    return 0 if report["verdict"] == "MIGRATION_PREFLIGHT_PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
