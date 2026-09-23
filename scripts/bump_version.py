#!/usr/bin/env python3
"""Bump the Grillmester package version and regenerate every derived target.

Merging the resulting change to main starts the Release workflow. When
rights-scoped imported content changed, pass the pull request that reviews it
with --rights-review so the stable rights journal is rebound in the same step.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_MANIFEST = Path("plugin/plugin.json")
GENERATORS = (
    ("scripts/generate_copilot_manifest.py",),
    ("scripts/generate_opencode.py",),
    ("scripts/generate_context_projections.py",),
    ("scripts/generate_agentpakke_manifest.py",),
    ("scripts/generate_marketplace.py", "--mode", "development"),
)
UNDERLYING_DECISION = "navikt/grillmester#56"
REVIEW_REFERENCE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[1-9][0-9]*$")

_CONTRACT_SPEC = importlib.util.spec_from_file_location(
    "grillmester_release_contract_for_bump",
    Path(__file__).resolve().with_name("release_contract.py"),
)
if _CONTRACT_SPEC is None or _CONTRACT_SPEC.loader is None:
    raise RuntimeError("could not load the release contract")
CONTRACT = importlib.util.module_from_spec(_CONTRACT_SPEC)
sys.modules[_CONTRACT_SPEC.name] = CONTRACT
_CONTRACT_SPEC.loader.exec_module(CONTRACT)


class BumpError(ValueError):
    """Raised when a version bump cannot be applied safely."""


def next_version(current: str, bump: str) -> str:
    """Return the version after a patch/minor/major bump or an explicit version."""

    version = CONTRACT.parse_version(current)
    if bump in ("patch", "minor", "major"):
        major, minor, patch = version.core
        if bump == "major":
            candidate = f"{major + 1}.0.0"
        elif bump == "minor":
            candidate = f"{major}.{minor + 1}.0"
        elif version.prerelease is not None:
            # A prerelease precedes its own core version.
            candidate = f"{major}.{minor}.{patch}"
        else:
            candidate = f"{major}.{minor}.{patch + 1}"
    else:
        candidate = bump
    target = CONTRACT.parse_version(candidate)
    if _precedence(target) <= _precedence(version):
        raise BumpError(f"{candidate} does not follow the current version {current}")
    return candidate


def _precedence(version: Any) -> tuple[Any, ...]:
    """SemVer precedence: a prerelease sorts before its core release."""

    if version.prerelease is None:
        return (version.core, 1, ())
    identifiers = tuple(
        (0, int(part), "") if part.isdigit() else (1, 0, part)
        for part in version.prerelease.split(".")
    )
    return (version.core, 0, identifiers)


def rewrite_version(manifest_text: str, current: str, target: str) -> str:
    old = f'"version": "{current}"'
    if manifest_text.count(old) != 1:
        raise BumpError(f"{PLUGIN_MANIFEST} must contain exactly one {old}")
    return manifest_text.replace(old, f'"version": "{target}"')


def rebind_rights(
    approval: dict[str, Any], scope: dict[str, Any], review: str, today: dt.date
) -> dict[str, Any]:
    """Bind the rights record to the current content under a named review."""

    if REVIEW_REFERENCE.fullmatch(review) is None:
        raise BumpError("--rights-review must look like navikt/grillmester#123")
    if review == UNDERLYING_DECISION:
        raise BumpError("the current-content review must differ from the underlying decision")
    rebound = json.loads(json.dumps(approval))
    rebound["scope"] = scope
    for decision in rebound["decisions"].values():
        decision["decisionReference"] = (
            f"underlying decision: {UNDERLYING_DECISION}; "
            f"current-content review: {review}"
        )
        decision["date"] = today.isoformat()
    return rebound


def _rights_are_current(root: Path) -> bool:
    try:
        CONTRACT.validate_stable_rights_approval(root)
    except CONTRACT.ReleaseContractError:
        return False
    return True


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "bump",
        help="patch, minor, major, or an explicit strict SemVer such as 0.5.0-rc.1",
    )
    parser.add_argument(
        "--rights-review",
        metavar="OWNER/REPO#PR",
        help="pull request that reviews changed rights-scoped imported content",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = ROOT
    manifest_path = root / PLUGIN_MANIFEST
    try:
        manifest_text = manifest_path.read_text(encoding="utf-8")
        current = json.loads(manifest_text)["version"]
        target = next_version(current, args.bump)

        rights_path = root / CONTRACT.STABLE_RIGHTS_APPROVAL_PATH
        if args.rights_review:
            approval = json.loads(rights_path.read_text(encoding="utf-8"))
            rebound = rebind_rights(
                approval,
                CONTRACT.current_rights_scope(root),
                args.rights_review,
                dt.date.today(),
            )
            rights_path.write_text(
                json.dumps(rebound, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            CONTRACT.validate_stable_rights_approval(root)
        elif not _rights_are_current(root):
            raise BumpError(
                "rights-scoped imported content changed since the rights journal was "
                "bound; rerun with --rights-review OWNER/REPO#PR naming the pull "
                "request that reviews that content"
            )

        manifest_path.write_text(
            rewrite_version(manifest_text, current, target), encoding="utf-8"
        )
    except (BumpError, CONTRACT.ReleaseContractError, KeyError, json.JSONDecodeError) as exc:
        print(f"bump_version: {exc}", file=sys.stderr)
        return 2

    for generator in GENERATORS:
        subprocess.run([sys.executable, *generator], cwd=root, check=True)
    print(f"Bumped Grillmester {current} -> {target}. Merging to main releases v{target}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
