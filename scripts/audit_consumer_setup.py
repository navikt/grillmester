#!/usr/bin/env python3
"""Inventory obsolete consumer setup and exact migration candidates without writes.

Local source repositories are optional evidence, never fetched or executed. This
is an audit, not an installer, deletion command, or synchronization lifecycle.
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
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ".github/.hovmester-manifest.json"
AGENT_ROOTS = (".github/agents", ".claude/agents", ".opencode/agents")
SKILL_ROOTS = (".github/skills", ".agents/skills", ".claude/skills", ".opencode/skills")
REFERENCE = re.compile(r"\bhovmester\b|\bgrillmester-[a-z][a-z0-9-]*\b", re.I)
SHA = re.compile(r"[0-9a-f]{40}")
# Reviewed historical reader: raw dist files, with TEAM_REPO substitution or
# removal of placeholder-containing lines in Markdown. Never execute this file.
REVIEWED_HOVMESTER_SYNC_BLOB = "29660e9ccaa7706330553003468da01a7235af59"
REVIEWED_HOVMESTER_WORKFLOW_BLOB = "90fbed816ba08c58ca6480f70bff522f955d3132"
HOVMESTER_CALLER = re.compile(
    r"^(?P<indent> *)uses:\s*[\"']?navikt/hovmester/\.github/workflows/"
    r"(?P<workflow>hovmester-sync\.ya?ml)@[^\s\"']+[\"']?\s*(?:#.*)?$", re.I,
)


class AuditError(RuntimeError):
    pass


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def object_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AuditError(f"expected JSON object: {path}")
    return data


def safe_relative(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and path.as_posix() == value and ".." not in path.parts


def files_under(path: Path) -> list[Path]:
    """Never descend through a symlink; retain it as a visible unknown entry."""
    if path.is_symlink() or path.is_file():
        return [path]
    if not path.is_dir():
        return []
    result = []
    for parent, dirs, files in os.walk(path, followlinks=False):
        dirs.sort()
        for name in list(dirs):
            child = Path(parent) / name
            if child.is_symlink():
                result.append(child)
                dirs.remove(name)
        result.extend(Path(parent) / name for name in sorted(files))
    return sorted(result)


def inventory(path: Path) -> dict[str, str | None]:
    return {
        (item.name if item == path else item.relative_to(path).as_posix()):
        None if item.is_symlink() else digest(item.read_bytes())
        for item in files_under(path)
    }


def skill_name(path: Path) -> str | None:
    if path.is_symlink():
        return None
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    frontmatter = text.split("\n---", 1)[0]
    match = re.search(r"^name:\s*([^\n]+)$", frontmatter, re.M)
    return match.group(1).strip().strip("\"'") if match else None


def git(repository: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", *arguments],
        cwd=repository, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
    )
    if result.returncode:
        raise AuditError(f"cannot read local source revision in {repository}: {result.stderr.decode().strip()}")
    return result.stdout


def source_inventory(repository: Path, revision: str, path: str, *, team_repo: str | None = None, distribution: bool = False) -> dict[str, str | None]:
    if not SHA.fullmatch(revision) or not safe_relative(path):
        raise AuditError("source evidence requires a full commit SHA and a safe relative path")
    result = {}
    for record in git(repository, "ls-tree", "-rz", revision, "--", path).split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        name = raw_path.decode()
        relative = PurePosixPath(name).name if name == path else name[len(path) + 1:]
        if kind != "blob" or mode == "120000":
            result[relative] = None
            continue
        content = git(repository, "cat-file", "blob", oid)
        if distribution and name.endswith(".md") and b"${TEAM_REPO}" in content:
            if team_repo is None:
                # Preserve the component when caller input is unobservable.
                result[relative] = None
                continue
            text = content.decode("utf-8")
            content = (text.replace("${TEAM_REPO}", team_repo) if team_repo else re.sub(r"^.*\$\{TEAM_REPO\}.*\n?", "", text, flags=re.M)).encode("utf-8")
        result[relative] = digest(content)
    return result


def caller_team_repo(consumer: Path) -> dict[str, Any]:
    """Recognize only one simple reusable caller and its literal TEAM_REPO input."""
    callers = []
    workflows = consumer / ".github/workflows"
    if any(path.is_symlink() for path in (consumer / ".github", workflows)):
        return {"status": "UNVERIFIED", "reason": "workflow root is a symlink"}
    for path in sorted(workflows.glob("*")):
        if path.is_symlink() or path.suffix not in (".yml", ".yaml"):
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            match = HOVMESTER_CALLER.fullmatch(line)
            if match:
                callers.append((path, lines, index, len(match["indent"]), match["workflow"]))
    if len(callers) != 1:
        return {"status": "UNVERIFIED", "reason": "expected one observable reusable sync caller"}
    path, lines, index, indent, workflow = callers[0]
    begin, end = index, index + 1
    while begin and (not lines[begin - 1].strip() or len(lines[begin - 1]) - len(lines[begin - 1].lstrip()) >= indent):
        begin -= 1
    while end < len(lines) and (not lines[end].strip() or len(lines[end]) - len(lines[end].lstrip()) >= indent):
        end += 1
    job = lines[begin:end]
    with_lines = [i for i, line in enumerate(job) if re.match(rf"^ {{{indent}}}with:", line)]
    team_repo = ""
    if len(with_lines) > 1 or any(not re.fullmatch(rf" {{{indent}}}with:\s*(?:#.*)?", job[i]) for i in with_lines):
        return {"status": "UNVERIFIED", "reason": "unrecognized caller inputs"}
    inputs = []
    if with_lines:
        for line in job[with_lines[0] + 1:]:
            if line.strip() and len(line) - len(line.lstrip()) <= indent:
                break
            if line.strip() and not line.lstrip().startswith("#"):
                inputs.append(line)
        # YAML merges, nested mappings and dynamic input maps require review.
        if any(not re.match(rf"^ {{{indent + 2}}}[A-Za-z_][A-Za-z0-9_]*:", line) for line in inputs):
            return {"status": "UNVERIFIED", "reason": "unrecognized caller input structure"}
        values = [line.split(":", 1)[1].strip() for line in inputs if line.lstrip().startswith("team_repo:")]
        if len(values) > 1:
            return {"status": "UNVERIFIED", "reason": "duplicate team_repo input"}
        if values:
            match = re.fullmatch(r"(?:\"(?P<double>[^\"]*)\"|'(?P<single>[^']*)'|(?P<bare>[^\s#]+))\s*(?:#.*)?", values[0])
            if not match:
                return {"status": "UNVERIFIED", "reason": "team_repo is not a literal string"}
            team_repo = next(value for value in match.groups() if value is not None)
            if team_repo and not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", team_repo):
                return {"status": "UNVERIFIED", "reason": "team_repo is not a literal repository name"}
    return {"status": "VERIFIED", "value": team_repo, "sourceWorkflow": f".github/workflows/{workflow}", "path": path.relative_to(consumer).as_posix(), "sha256": digest(path.read_bytes())}


def distribution_candidates(consumer: Path, manifest: dict[str, Any], owned: set[str], source_roots: dict[str, Path], lock: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source = source_roots.get("hovmester")
    if source is None or manifest["status"] != "OWNERSHIP_ONLY":
        return [], {"status": "UNVERIFIED", "reason": "manifest ownership and an explicit local Hovmester source are required"}
    if lock["sources"].get("hovmester", {}).get("repository") != "navikt/hovmester":
        return [], {"status": "UNVERIFIED", "reason": "content lock does not declare Hovmester provenance"}
    revision = manifest["sourceSha"]
    script = git(source, "ls-tree", "-z", revision, "--", "scripts/sync.py").split(b"\0")[0]
    if not script or script.split(b"\t", 1)[0].decode().split() != ["100644", "blob", REVIEWED_HOVMESTER_SYNC_BLOB]:
        return [], {"status": "UNVERIFIED", "reason": "historical sync reader differs from the reviewed transform", "revision": revision}
    caller = caller_team_repo(consumer)
    if caller["status"] == "VERIFIED":
        wrapper = git(source, "ls-tree", "-z", revision, "--", caller["sourceWorkflow"]).split(b"\0")[0]
        if not wrapper or wrapper.split(b"\t", 1)[0].decode().split() != ["100644", "blob", REVIEWED_HOVMESTER_WORKFLOW_BLOB]:
            return [], {"status": "UNVERIFIED", "reason": "historical workflow defaults or argument pass-through differ from the reviewed wrapper", "revision": revision}
    candidates = []
    components = set()
    for path in owned:
        parts = PurePosixPath(path).parts
        if len(parts) >= 3 and parts[:2] == (".github", "skills"):
            components.add(("skills", "/".join(parts[:3])))
        elif len(parts) == 3 and parts[:2] == (".github", "agents") and path.endswith(".md"):
            components.add(("agents", path))
    for kind, path in sorted(components):
        source_path = path.replace(".github/", "dist/", 1)
        fingerprints = source_inventory(source, revision, source_path, team_repo=caller.get("value"), distribution=True)
        if not fingerprints:
            continue
        name = PurePosixPath(path).name.removesuffix(".md").removesuffix(".agent")
        candidates.append({"kind": kind, "replacement": name if name in lock[kind] else None, "source": "hovmester-distribution", "sourcePath": source_path, "consumerPath": path, "revision": revision, "teamRepoTransform": caller, "files": fingerprints})
    return candidates, {"status": "VERIFIED", "revision": revision, "readerBlob": REVIEWED_HOVMESTER_SYNC_BLOB, "workflowBlob": REVIEWED_HOVMESTER_WORKFLOW_BLOB if caller["status"] == "VERIFIED" else None, "teamRepoTransform": caller}


def source_candidates(plugin: Path, lock: dict[str, Any], source_roots: dict[str, Path], retired_ref: str | None) -> list[dict[str, Any]]:
    candidates = []
    for kind in ("agents", "skills"):
        for runtime_id, entry in sorted(lock[kind].items()):
            current = plugin / "plugin" / kind / (f"{runtime_id}.agent.md" if kind == "agents" else runtime_id)
            if current.exists():
                candidates.append({"kind": kind, "replacement": runtime_id, "source": "current-plugin", "sourcePath": current.relative_to(plugin).as_posix(), "files": inventory(current)})
            for origin in [entry, *entry.get("lineage", [])]:
                sources = origin["source"] if isinstance(origin["source"], list) else [origin["source"]]
                source_path = origin["sourcePath"]
                # An instruction file used as inspiration does not own a component.
                if f"/{kind}/" not in f"/{source_path}":
                    continue
                for source in sources:
                    if source not in source_roots:
                        continue
                    revision = lock["sources"][source]["revision"]
                    fingerprints = source_inventory(source_roots[source], revision, source_path)
                    if fingerprints:
                        candidates.append({"kind": kind, "replacement": runtime_id, "source": source, "sourcePath": source_path, "revision": revision, "files": fingerprints})
            if retired_ref:
                source_path = f"plugin/{kind}/" + (f"{runtime_id}.agent.md" if kind == "agents" else f"grillmester-{runtime_id}")
                fingerprints = source_inventory(plugin, retired_ref, source_path)
                if fingerprints:
                    candidates.append({"kind": kind, "replacement": runtime_id, "source": "retired-plugin", "sourcePath": source_path, "revision": retired_ref, "files": fingerprints})
    return candidates


def read_manifest(consumer: Path) -> tuple[dict[str, Any], set[str]]:
    path = consumer / MANIFEST
    if not path.exists() and not path.is_symlink():
        return {"path": None, "status": "ABSENT"}, set()
    if path.is_symlink() or path.parent.is_symlink():
        return {"path": MANIFEST, "status": "UNVERIFIED", "reason": "symlink"}, set()
    value = object_json(path)
    listed = value.get("files", [])
    valid = isinstance(listed, list) and all(isinstance(item, str) and safe_relative(item) for item in listed)
    owned = valid and value.get("source") == "navikt/hovmester" and bool(SHA.fullmatch(str(value.get("source_sha", ""))))
    return {
        "path": MANIFEST, "sha256": digest(path.read_bytes()),
        "status": "OWNERSHIP_ONLY" if owned else "UNVERIFIED",
        "sourceSha": value.get("source_sha"),
        "reason": "Manifest ownership does not prove unchanged content.",
    }, set(listed) if owned else set()


def discover_components(root: Path, user_scope: bool) -> list[tuple[str, Path]]:
    result = []
    for kind, roots in (("agents", AGENT_ROOTS), ("skills", SKILL_ROOTS)):
        locations = (*roots, kind) if user_scope else roots
        for relative in locations:
            location = root / relative
            # A parent link can escape the requested root even when the final file is regular.
            if any(parent.is_symlink() for parent in [location, *location.parents] if parent != root and root in parent.parents):
                result.append((kind, location))
                continue
            for path in files_under(location):
                if path.is_symlink() or (kind == "agents" and path.suffix == ".md"):
                    result.append((kind, path))
                elif kind == "skills" and path.name == "SKILL.md":
                    result.append((kind, path.parent))
    return sorted(set(result), key=lambda item: (item[0], item[1]))


def audit(consumer: Path, plugin: Path = ROOT, source_roots: dict[str, Path] | None = None, user_roots: list[Path] | None = None, retired_ref: str | None = None) -> dict[str, Any]:
    consumer, plugin = consumer.resolve(), plugin.resolve()
    if not consumer.is_dir():
        raise AuditError(f"consumer directory is missing: {consumer}")
    lock_path = plugin / "policy/content-lock.json"
    lock = object_json(lock_path)
    candidates = source_candidates(plugin, lock, source_roots or {}, retired_ref)
    manifest, owned = read_manifest(consumer)
    distribution, source_evidence = distribution_candidates(consumer, manifest, owned, source_roots or {}, lock)
    candidates.extend(distribution)
    report: dict[str, Any] = {
        "schemaVersion": 1, "readOnly": True, "consumer": str(consumer),
        "contentLockSha256": digest(lock_path.read_bytes()), "manifest": manifest,
        "distributionEvidence": source_evidence,
        "runtimeResolution": "UNVERIFIED", "components": [], "references": [], "plan": [],
        "limits": ["Filesystem collisions do not prove the active runtime winner.", "No source repository is fetched and no historical sync is run.", "Exact file hashes are review evidence, not authorization to remove files."],
    }
    scopes = [("repository", consumer), *(("user", path.resolve()) for path in user_roots or [])]
    for scope, root in scopes:
        for kind, path in discover_components(root, scope == "user"):
            relative = path.relative_to(root).as_posix()
            linked = path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != root and root in parent.parents)
            hashes = {"<symlink>": None} if linked else inventory(path)
            name = None if linked else (path.name.removesuffix(".md").removesuffix(".agent") if kind == "agents" else skill_name(path / "SKILL.md"))
            hinted = name or path.name
            short = hinted.removeprefix("grillmester-")
            same_id = name in lock[kind] if name else False
            old_prefix = hinted.startswith("grillmester-") and short in lock[kind]
            manifest_owned = scope == "repository" and any(item == relative or item.startswith(relative + "/") for item in owned)
            known = [candidate for candidate in candidates if candidate["kind"] == kind]
            matches = [candidate for candidate in known if None not in hashes.values() and hashes == candidate["files"]]
            related = [candidate for candidate in known if candidate["source"] != "current-plugin" and None not in candidate["files"].values() and (candidate["replacement"] == short or PurePosixPath(candidate["sourcePath"]).name in (path.name, hinted))]
            if linked or None in hashes.values():
                classification = "UNKNOWN_SYMLINK"
            elif matches:
                classification = "OBSOLETE_UNMODIFIED"
            elif manifest_owned and related:
                classification = "OWNED_CUSTOMIZED_OR_TRANSFORMED"
            elif manifest_owned:
                classification = "OWNED_CONTENT_UNVERIFIED"
            elif old_prefix:
                classification = "LEGACY_ID_CONTENT_UNVERIFIED"
            else:
                classification = "LOCAL_OR_UNKNOWN"
            entry = {
                "scope": scope, "root": str(root), "path": relative, "kind": kind,
                "name": name, "classification": classification, "idCollision": same_id,
                "legacyPrefixedId": old_prefix, "manifestOwned": manifest_owned,
                "files": hashes, "matches": [{key: value for key, value in match.items() if key != "files"} for match in matches],
                "replacementIds": sorted({match["replacement"] for match in matches if match["replacement"]}) or ([short] if short in lock[kind] else []),
            }
            report["components"].append(entry)
            relevant = linked or None in hashes.values() or bool(matches) or manifest_owned or old_prefix or same_id or "hovmester" in hinted.lower()
            if relevant:
                report["plan"].append({
                    "scope": scope, "root": str(root), "path": relative,
                    "action": "REVIEW_REMOVE_EXACT_COPY" if matches and classification == "OBSOLETE_UNMODIFIED" else "PRESERVE_AND_RECONCILE",
                    "expectedFiles": hashes,
                    "reason": "Byte-identical complete component; verify replacement in the selected runtime before removal." if matches else "Preserve local changes; review ownership, domain rules, and active runtime identity before choosing a change.",
                })
        reference_paths = []
        for top in ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "README.md", ".github", ".agents", ".claude", ".opencode", "docs"):
            path = root / top
            if path.is_symlink():
                continue
            reference_paths.extend(files_under(path))
        for path in sorted(set(reference_paths)):
            if path.is_symlink() or path.suffix.lower() not in (".md", ".yml", ".yaml", ".json", ".jsonc"):
                continue
            relative = path.relative_to(root).as_posix()
            # Runtime components already carry full hashes and their own review plan.
            if any(relative == part["path"] or relative.startswith(part["path"] + "/") for part in report["components"] if part["root"] == str(root)):
                continue
            matches = [{"line": index, "terms": sorted(set(REFERENCE.findall(line)))} for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if REFERENCE.search(line)]
            if matches:
                category = "LEGACY_WORKFLOW" if relative.startswith(".github/workflows/") else "REFERENCE_REVIEW"
                report["references"].append({"scope": scope, "root": str(root), "path": relative, "category": category, "sha256": digest(path.read_bytes()), "matches": matches, "action": "REVIEW_EDIT_PRESERVE_LOCAL_RULES"})
    report["summary"] = {
        "components": len(report["components"]),
        "exactCopies": sum(item["classification"] == "OBSOLETE_UNMODIFIED" for item in report["components"]),
        "idCollisions": sum(item["idCollision"] for item in report["components"]),
        "legacyPrefixedIds": sum(item["legacyPrefixedId"] for item in report["components"]),
        "references": len(report["references"]),
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("consumer", type=Path)
    parser.add_argument("--plugin-root", type=Path, default=ROOT)
    parser.add_argument("--source-root", action="append", default=[], metavar="SOURCE=PATH", help="Optional local Git repository for a source in content-lock.json; reads its locked revision.")
    parser.add_argument("--retired-plugin-ref", help="Optional full commit SHA in the plugin repository for byte comparison with prefixed copies.")
    parser.add_argument("--user-root", type=Path, action="append", default=[], help="Explicit user configuration root to audit as well; never inferred from HOME.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        source_roots = {}
        for value in args.source_root:
            source, separator, path = value.partition("=")
            if not separator or not source or not path:
                raise AuditError("--source-root must be SOURCE=PATH")
            if source not in object_json(args.plugin_root / "policy/content-lock.json")["sources"]:
                raise AuditError(f"unknown content-lock source: {source}")
            source_roots[source] = Path(path).resolve()
        report = audit(args.consumer, args.plugin_root, source_roots, args.user_root, args.retired_plugin_ref)
    except (AuditError, OSError, ValueError) as exc:
        print(f"CONSUMER_SETUP_AUDIT: ERROR — {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("CONSUMER_SETUP_AUDIT: REVIEW_REQUIRED" if report["plan"] or report["references"] else "CONSUMER_SETUP_AUDIT: NO_CONFLICTS_OBSERVED")
        for item in report["plan"]:
            print(f'{item["action"]}: {item["root"]}/{item["path"]}')
        for item in report["references"]:
            print(f'{item["category"]}: {item["root"]}/{item["path"]}')
        print("Read-only filesystem audit; active skill resolution remains UNVERIFIED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
