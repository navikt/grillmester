#!/usr/bin/env python3
"""Take a skill in unchanged from its owner's repository, or prove the copy is.

A ported skill is owned elsewhere. Every file of the skill, except the source's
catalog files, is byte-identical to the source repository at the commit the
content lock names, and the lock binds the files with `contentSha256`. Nothing
is fetched: the source is read from a local checkout through its Git objects,
so the checkout's branch and working tree do not matter. The commit must be on
a branch fetched from the repository the lock names. See ADR 0038.

    python3 scripts/port_skill.py aksel-builder --source ../copilot --check
    python3 scripts/port_skill.py aksel-builder --source ../copilot --revision <sha>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
CONTENT_LOCK = Path("policy/content-lock.json")
SKILLS = Path("plugin/skills")
PORTED = "ported"
SKILL_FILE = "SKILL.md"
# Files at the skill's root that describe it in the source's own catalog. They
# stay with the source; everything else comes along, so nothing a skill points
# at is dropped.
CATALOG_FILES = frozenset({"README.md", "metadata.json"})
REVISION_RECORDS = (
    Path("PROVENANCE.md"),
    Path("THIRD_PARTY_NOTICES.md"),
    Path("plugin/THIRD_PARTY_NOTICES.md"),
)
FULL_SHA = re.compile(r"[0-9a-f]{40}")
REGULAR_FILE = "100644"


class PortError(ValueError):
    """Raised when a skill cannot be ported or proven unchanged."""


def content_digest(files: dict[str, bytes]) -> str:
    """Bind the complete file roster the same way the rights journal binds a component."""

    manifest = {path: hashlib.sha256(data).hexdigest() for path, data in files.items()}
    canonical = json.dumps(
        manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def local_files(skill_root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in sorted(skill_root.rglob("*")):
        if path.is_symlink():
            raise PortError(f"ported skill contains a symlink: {path}")
        if path.is_file():
            files[path.relative_to(skill_root).as_posix()] = path.read_bytes()
    return files


def _git(source: Path, *arguments: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-C", str(source), *arguments], check=True, capture_output=True
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", b"") or str(exc).encode()
        raise PortError(
            f"git {arguments[0]} failed in {source}: {detail.decode(errors='replace').strip()}"
        ) from exc


def verify_origin(source: Path, repository: str, revision: str) -> None:
    """Refuse a checkout of another repository and a commit its remote does not have.

    Without this, "identical to the source" would hold for any repository that
    has the path, and for a local commit nobody else can look up.
    """

    if not FULL_SHA.fullmatch(revision):
        raise PortError("the revision must be a full 40-character commit SHA")
    _git(source, "cat-file", "-e", f"{revision}^{{commit}}")
    names_repository = re.compile(r"[:/]" + re.escape(repository) + r"(?:\.git)?/?$", re.I)
    remotes = set()
    for line in _git(source, "remote", "-v").decode().splitlines():
        name, _, rest = line.partition("\t")
        if names_repository.search(rest.rsplit(" ", 1)[0]):
            remotes.add(name)
    if not remotes:
        raise PortError(f"{source} has no remote for {repository}")
    branches = _git(
        source, "branch", "-r", "--contains", revision, "--format=%(refname:short)"
    ).decode().split()
    if not any(branch.split("/", 1)[0] in remotes for branch in branches):
        raise PortError(
            f"{revision} is not on a branch fetched from {repository}; fetch the "
            "repository, or wait until the commit is pushed there"
        )


def source_files(source: Path, revision: str, source_path: str) -> dict[str, bytes]:
    """Read the skill's files from the source's Git objects."""

    prefix = source_path.strip("/") + "/"
    listing = _git(source, "ls-tree", "-r", "-z", revision, "--", prefix)
    files: dict[str, bytes] = {}
    for entry in filter(None, listing.split(b"\0")):
        metadata, _, name = entry.partition(b"\t")
        mode, kind, _ = metadata.decode().split(" ")
        relative = name.decode("utf-8")[len(prefix):]
        if relative in CATALOG_FILES:
            continue
        if kind != "blob" or mode != REGULAR_FILE:
            raise PortError(f"{prefix}{relative} is not a regular file in the source")
        files[relative] = _git(source, "cat-file", "blob", f"{revision}:{prefix}{relative}")
    if SKILL_FILE not in files:
        raise PortError(f"{prefix}{SKILL_FILE} does not exist at {revision}")
    return files


def _named_sources(contract: dict[str, Any]) -> list[Any]:
    own = contract.get("source")
    lineage = contract.get("lineage") or []
    return [*(own if isinstance(own, list) else [own]), *(item.get("source") for item in lineage)]


def read_contract(root: Path, skill: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    try:
        lock = json.loads((root / CONTENT_LOCK).read_text(encoding="utf-8"))
        contract = lock["skills"][skill]
        source_id = contract["source"]
        source = lock["sources"][source_id]
        repository, revision = source["repository"], source["revision"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise PortError(f"{CONTENT_LOCK} has no usable contract for {skill}: {exc}") from exc
    if contract.get("disposition") != PORTED:
        raise PortError(f"{skill} is not a ported skill in {CONTENT_LOCK}")
    if not isinstance(repository, str) or not isinstance(revision, str):
        raise PortError(f"source {source_id} needs a repository and a revision")
    users = sorted(
        component_id
        for kind in ("agents", "skills")
        for component_id, other in lock.get(kind, {}).items()
        if (kind, component_id) != ("skills", skill) and source_id in _named_sources(other)
    )
    if users:
        raise PortError(
            f"source {source_id} is shared with {', '.join(users)}; "
            "a ported skill needs a source of its own, because its revision moves"
        )
    return source_id, source, contract


def differences(expected: dict[str, bytes], actual: dict[str, bytes]) -> list[str]:
    found = [f"missing: {path}" for path in sorted(expected.keys() - actual.keys())]
    found += [f"not in the source: {path}" for path in sorted(actual.keys() - expected.keys())]
    found += [
        f"changed: {path}"
        for path in sorted(expected.keys() & actual.keys())
        if expected[path] != actual[path]
    ]
    return found


def check(root: Path, skill: str, source: Path) -> list[str]:
    _, source_entry, contract = read_contract(root, skill)
    verify_origin(source, source_entry["repository"], source_entry["revision"])
    expected = source_files(source, source_entry["revision"], contract["sourcePath"])
    found = differences(expected, local_files(root / SKILLS / skill))
    if content_digest(expected) != contract.get("contentSha256"):
        found.append("contentSha256 in the content lock does not match the source")
    return found


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PortError(f"{label} must contain {old} exactly once")
    return text.replace(old, new)


def port(
    root: Path, skill: str, source: Path, revision: str | None
) -> tuple[str, list[Path]]:
    """Take the skill in. Return the revision and the records left to update by hand."""

    source_id, source_entry, contract = read_contract(root, skill)
    old_revision = source_entry["revision"]
    revision = revision or old_revision
    verify_origin(source, source_entry["repository"], revision)
    files = source_files(source, revision, contract["sourcePath"])
    digest = content_digest(files)
    skill_root = root / SKILLS / skill
    if skill_root.is_symlink():
        raise PortError(f"{skill_root} is a symlink")

    # Work out every new text before the first write, so a refusal changes nothing.
    writes: dict[Path, str] = {}
    by_hand: list[Path] = []
    lock_text = (root / CONTENT_LOCK).read_text(encoding="utf-8")
    shared = any(
        other_id != source_id and other.get("revision") == old_revision
        for other_id, other in json.loads(lock_text)["sources"].items()
    )
    old_digest = contract.get("contentSha256")
    if digest != old_digest:
        if not isinstance(old_digest, str):
            raise PortError(f"{CONTENT_LOCK} needs a contentSha256 for {skill} to replace")
        lock_text = _replace_once(lock_text, old_digest, digest, label=str(CONTENT_LOCK))
    if revision != old_revision:
        block = re.search(r'"' + re.escape(source_id) + r'": \{[^{}]*\}', lock_text, re.S)
        if block is None or block.group().count(old_revision) != 1:
            raise PortError(f"could not find the revision of source {source_id}")
        lock_text = (
            lock_text[: block.start()]
            + block.group().replace(old_revision, revision)
            + lock_text[block.end() :]
        )
        for record in REVISION_RECORDS:
            if not (root / record).is_file():
                continue
            text = (root / record).read_text(encoding="utf-8")
            if old_revision not in text:
                continue
            if shared or text.count(old_revision) != 1:
                # More than one mention, or another source pinned to the same
                # commit: prose about history cannot be told from the pin.
                by_hand.append(record)
            else:
                writes[root / record] = text.replace(old_revision, revision)
    # The lock goes last: until it is written, validation rejects the half-way state.
    writes[root / CONTENT_LOCK] = lock_text

    try:
        if skill_root.exists():
            shutil.rmtree(skill_root)
        for relative, data in files.items():
            target = skill_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(0o644)
        for path, text in writes.items():
            path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise PortError(
            f"writing stopped part-way: {exc}. Fix the cause and run the same "
            "command again; the content lock is written last, so it completes the port"
        ) from exc
    return revision, by_hand


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("skill", help="ID of a skill the content lock records as ported")
    parser.add_argument(
        "--source", type=Path, required=True, help="local checkout of the source repository"
    )
    parser.add_argument("--revision", help="full commit SHA to move the pin to")
    parser.add_argument(
        "--check", action="store_true", help="prove the copy equals the source; change nothing"
    )
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.check:
            if args.revision:
                raise PortError("--check proves the locked revision; drop --revision")
            found = check(args.root, args.skill, args.source)
            for line in found:
                print(f"port_skill: {args.skill}: {line}", file=sys.stderr)
            if not found:
                print(f"{args.skill} is byte-identical to its source at the locked revision.")
            return 1 if found else 0
        revision, by_hand = port(args.root, args.skill, args.source, args.revision)
    except PortError as exc:
        print(f"port_skill: {exc}", file=sys.stderr)
        return 2
    for record in by_hand:
        print(f"port_skill: update the revision of {args.skill} in {record} by hand")
    print(
        f"Ported {args.skill} at {revision}. Regenerate the targets, measure its "
        "references, review the change, and rebind the rights journal when "
        "PROVENANCE.md or the content lock changed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
