#!/usr/bin/env python3
"""Validate and describe Grillmester's immutable release chain.

The public release tag identifies a catalog-only commit. The catalog then
identifies both package payloads with one exact GitHub commit SHA. Stable
releases are new, stable-versioned catalogs whose payloads are identical to a
named RC apart from each manifest's version; an RC tag is never moved or
re-used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


PLUGIN_NAMES = ("grillmester", "grillmester-nav")
PLUGIN_PATHS = {
    "grillmester": "plugin",
    "grillmester-nav": "plugin-nav",
}
PLUGIN_REPOSITORY = "navikt/grillmester"
CATALOG_PATH = ".github/plugin/marketplace.json"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
SEMVER = re.compile(
    r"^(?P<major>0|[1-9][0-9]*)\."
    r"(?P<minor>0|[1-9][0-9]*)\."
    r"(?P<patch>0|[1-9][0-9]*)"
    r"(?:-(?P<prerelease>"
    r"(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*"
    r"))?$"
)


class ReleaseContractError(ValueError):
    """Raised when a candidate cannot be promoted safely."""


@dataclass(frozen=True)
class Version:
    text: str
    core: tuple[int, int, int]
    prerelease: str | None

    @property
    def tag(self) -> str:
        return f"v{self.text}"


@dataclass(frozen=True)
class Catalog:
    version: Version
    source_sha: str


def parse_version(value: object) -> Version:
    if not isinstance(value, str):
        raise ReleaseContractError("version must be a SemVer string")
    match = SEMVER.fullmatch(value)
    if match is None:
        raise ReleaseContractError(
            "version must be strict SemVer without build metadata"
        )
    return Version(
        text=value,
        core=tuple(int(match.group(name)) for name in ("major", "minor", "patch")),
        prerelease=match.group("prerelease"),
    )


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReleaseContractError(f"required file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReleaseContractError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReleaseContractError(f"expected a JSON object in {path}")
    return value


def inspect_catalog(path: Path, *, channel: str) -> Catalog:
    value = read_object(path)
    if value.get("name") != "grillmester":
        raise ReleaseContractError("catalog has the wrong marketplace name")

    metadata = value.get("metadata")
    plugins = value.get("plugins")
    if not isinstance(metadata, dict):
        raise ReleaseContractError("catalog metadata must be an object")
    if not isinstance(plugins, list) or len(plugins) != len(PLUGIN_NAMES):
        raise ReleaseContractError("catalog must contain both Grillmester packages")
    entries = {
        entry.get("name"): entry
        for entry in plugins
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }
    if tuple(entries) != PLUGIN_NAMES:
        raise ReleaseContractError("catalog package order or names have drifted")

    version = parse_version(entries[PLUGIN_NAMES[0]].get("version"))
    if any(entry.get("version") != version.text for entry in entries.values()):
        raise ReleaseContractError("catalog package versions differ")
    if metadata.get("version") != version.text:
        raise ReleaseContractError("catalog metadata and plugin versions differ")
    if channel == "rc" and version.prerelease is None:
        raise ReleaseContractError("RC promotion requires a prerelease version")
    if channel == "stable" and version.prerelease is not None:
        raise ReleaseContractError("stable promotion requires a stable version")

    sources = {name: entry.get("source") for name, entry in entries.items()}
    if any(not isinstance(source, dict) for source in sources.values()):
        raise ReleaseContractError("release catalog must use immutable sources")
    source_sha = sources[PLUGIN_NAMES[0]].get("sha")  # type: ignore[union-attr]
    for name, source in sources.items():
        expected_source = {
            "source": "github",
            "repo": PLUGIN_REPOSITORY,
            "path": PLUGIN_PATHS[name],
            "sha": source_sha,
        }
        if source != expected_source:
            raise ReleaseContractError(
                "catalog packages must pin their canonical paths at one exact SHA"
            )
    if not isinstance(source_sha, str) or FULL_SHA.fullmatch(source_sha) is None:
        raise ReleaseContractError("catalog source SHA must be 40 lowercase hex digits")
    return Catalog(version=version, source_sha=source_sha)


def git_output(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseContractError(
            f"git {' '.join(arguments)} failed in {repo}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def validate_catalog_checkout(repo: Path, expected_sha: str) -> None:
    if FULL_SHA.fullmatch(expected_sha) is None:
        raise ReleaseContractError("catalog SHA must be 40 lowercase hex digits")
    actual_sha = git_output(repo, "rev-parse", "HEAD")
    if actual_sha != expected_sha:
        raise ReleaseContractError(
            f"catalog checkout is {actual_sha}; expected {expected_sha}"
        )
    entries = git_output(repo, "ls-tree", "-r", "HEAD").splitlines()
    expected_entry = f"100644 blob {git_output(repo, 'rev-parse', f'HEAD:{CATALOG_PATH}')}\t{CATALOG_PATH}"
    if entries != [expected_entry]:
        raise ReleaseContractError(
            "release tag target must be a catalog-only commit containing exactly "
            f"one regular {CATALOG_PATH} blob"
        )


def bind_catalog_bytes(catalog_path: Path, catalog_repo: Path) -> None:
    checkout_catalog = catalog_repo / CATALOG_PATH
    if catalog_path.read_bytes() != checkout_catalog.read_bytes():
        raise ReleaseContractError(
            "inspected catalog bytes differ from the catalog commit"
        )


def validate_source_checkout(
    repo: Path, catalog: Catalog
) -> dict[str, dict[str, Any]]:
    actual_sha = git_output(repo, "rev-parse", "HEAD")
    if actual_sha != catalog.source_sha:
        raise ReleaseContractError(
            f"source checkout is {actual_sha}; catalog pins {catalog.source_sha}"
        )
    manifests: dict[str, dict[str, Any]] = {}
    for name in PLUGIN_NAMES:
        manifest = read_object(repo / PLUGIN_PATHS[name] / "plugin.json")
        if manifest.get("name") != name:
            raise ReleaseContractError(f"source manifest has the wrong name for {name}")
        if manifest.get("version") != catalog.version.text:
            raise ReleaseContractError(
                f"source manifest version does not match the catalog for {name}"
            )
        if manifest.get("repository") != f"https://github.com/{PLUGIN_REPOSITORY}":
            raise ReleaseContractError(f"source manifest has the wrong repository for {name}")
        manifests[name] = manifest
    return manifests


def validate_regenerated_catalog(
    *, catalog_path: Path, source_repo: Path, source_sha: str
) -> None:
    generator = source_repo / "scripts/generate_marketplace.py"
    if not generator.is_file():
        raise ReleaseContractError("source checkout has no marketplace generator")
    with tempfile.TemporaryDirectory(prefix="grillmester-release-contract-") as temp:
        generated = Path(temp) / "marketplace.json"
        result = subprocess.run(
            [
                sys.executable,
                str(generator),
                "--mode",
                "release",
                "--sha",
                source_sha,
                "--output",
                str(generated),
            ],
            cwd=source_repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if result.returncode != 0:
            raise ReleaseContractError(
                "failed to regenerate catalog from the source checkout: "
                + result.stdout.strip()
            )
        if generated.read_bytes() != catalog_path.read_bytes():
            raise ReleaseContractError(
                "catalog commit is not byte-identical to regeneration from source.sha"
            )


def payload_manifest(plugin: Path, *, exclude_manifest: bool = False) -> dict[str, str]:
    if not plugin.is_dir():
        raise ReleaseContractError(f"plugin payload is missing: {plugin}")
    result: dict[str, str] = {}
    for path in sorted(plugin.rglob("*")):
        if path.is_symlink():
            raise ReleaseContractError(f"plugin payload contains a symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(plugin).as_posix()
        if exclude_manifest and relative == "plugin.json":
            continue
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not result:
        raise ReleaseContractError(f"plugin payload contains no files: {plugin}")
    return result


def validate_stable_promotion(
    stable: Catalog,
    stable_source: Path,
    rc_tag: str,
    rc: Catalog,
    rc_source: Path,
) -> None:
    if rc_tag != rc.version.tag:
        raise ReleaseContractError(
            f"RC tag {rc_tag!r} must equal catalog version tag {rc.version.tag!r}"
        )
    if stable.version.core != rc.version.core:
        raise ReleaseContractError(
            "stable and RC versions must have the same major.minor.patch"
        )
    stable_package_manifest = stable_source / "package-manifest.json"
    rc_package_manifest = rc_source / "package-manifest.json"
    try:
        package_manifest_matches = (
            stable_package_manifest.read_bytes() == rc_package_manifest.read_bytes()
        )
    except FileNotFoundError as exc:
        raise ReleaseContractError(
            "stable and RC sources must both contain package-manifest.json"
        ) from exc
    if not package_manifest_matches:
        raise ReleaseContractError(
            "stable package-manifest.json differs from the reviewed RC"
        )

    for name in PLUGIN_NAMES:
        stable_package = stable_source / PLUGIN_PATHS[name]
        rc_package = rc_source / PLUGIN_PATHS[name]
        stable_manifest_path = stable_package / "plugin.json"
        rc_manifest_path = rc_package / "plugin.json"
        stable_manifest = read_object(stable_manifest_path)
        rc_manifest = read_object(rc_manifest_path)
        stable_manifest.pop("version", None)
        rc_manifest.pop("version", None)
        if stable_manifest != rc_manifest:
            raise ReleaseContractError(
                f"stable {name} manifest differs from the RC beyond its version"
            )
        stable_manifest_bytes = stable_manifest_path.read_bytes()
        stable_version = json.dumps(stable.version.text).encode("utf-8")
        rc_version = json.dumps(rc.version.text).encode("utf-8")
        version_field = re.compile(rb'("version"\s*:\s*)' + re.escape(stable_version))
        normalized_manifest, substitutions = version_field.subn(
            rb"\g<1>" + rc_version, stable_manifest_bytes
        )
        if substitutions != 1 or normalized_manifest != rc_manifest_path.read_bytes():
            raise ReleaseContractError(
                f"stable {name}/plugin.json differs byte-for-byte from the RC beyond its version value"
            )

        stable_payload = payload_manifest(stable_package, exclude_manifest=True)
        rc_payload = payload_manifest(rc_package, exclude_manifest=True)
        if stable_payload != rc_payload:
            missing = sorted(rc_payload.keys() - stable_payload.keys())
            added = sorted(stable_payload.keys() - rc_payload.keys())
            changed = sorted(
                path
                for path in stable_payload.keys() & rc_payload.keys()
                if stable_payload[path] != rc_payload[path]
            )
            detail = "; ".join(
                f"{label}: {', '.join(paths[:5])}"
                for label, paths in (("missing", missing), ("added", added), ("changed", changed))
                if paths
            )
            raise ReleaseContractError(
                f"stable {name} payload differs from the reviewed RC beyond plugin.json version"
                + (f"; {detail}" if detail else "")
            )


def write_outputs(path: Path, values: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as output:
        for key, value in values.items():
            if "\n" in value:
                raise ReleaseContractError(f"output {key!r} must be one line")
            output.write(f"{key}={value}\n")


def render_notes(
    *,
    channel: str,
    tag: str,
    catalog_sha: str,
    source_sha: str,
    rc_tag: str | None,
) -> str:
    if channel not in {"rc", "stable"}:
        raise ReleaseContractError(f"unsupported release channel: {channel!r}")
    if not tag.startswith("v"):
        raise ReleaseContractError("release notes need a version tag")
    version = parse_version(tag.removeprefix("v"))
    if tag != version.tag:
        raise ReleaseContractError("release tag must be canonical v<semver>")
    if channel == "rc" and (version.prerelease is None or rc_tag is not None):
        raise ReleaseContractError(
            "RC release notes require a prerelease tag and no RC parent"
        )
    if channel == "stable":
        if version.prerelease is not None or rc_tag is None:
            raise ReleaseContractError(
                "stable release notes require a stable tag and an RC parent"
            )
        rc_version = parse_version(rc_tag.removeprefix("v"))
        if rc_tag != rc_version.tag or rc_version.prerelease is None:
            raise ReleaseContractError("RC parent must be a canonical prerelease tag")
        if version.core != rc_version.core:
            raise ReleaseContractError("stable and RC note tags need the same base version")
    if FULL_SHA.fullmatch(catalog_sha) is None:
        raise ReleaseContractError("release notes need a version tag and catalog SHA")
    if FULL_SHA.fullmatch(source_sha) is None:
        raise ReleaseContractError("release notes need an exact source SHA")

    status = "release candidate" if channel == "rc" else "stable release"
    promoted = (
        f"\nThis stable release promotes the tested `{rc_tag}` payloads. The only "
        "permitted payload changes are the two `plugin.json.version` values.\n"
        if rc_tag
        else ""
    )
    return f"""## Grillmester {tag}

This is a **{status}** with an immutable, two-step provenance chain.{promoted}
| Layer | Immutable identity |
| --- | --- |
| Release tag | `{tag}` → catalog commit `{catalog_sha}` |
| Package payloads | both catalog sources → `{source_sha}` |

The tag points to a catalog-only commit. It never points at `main` and is never
moved after publication.

### Install with Copilot CLI

```bash
copilot plugin marketplace add navikt/grillmester#{tag}
copilot plugin install grillmester@grillmester
copilot --agent=grillmester:grillmester
```

For the optional NAV specialist pack, also run:

```bash
copilot plugin install grillmester-nav@grillmester
```

### Verify

```bash
copilot plugin list
```

### Roll back

For a repository activation, revert its marketplace `ref` to the previously
reviewed tag. For a personal installation, uninstall every installed
Grillmester package, add/update the marketplace at the previous tag, and
reinstall the same package set. Tags are immutable; never retag an older or
newer catalog.
"""


def add_common_inspect_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--channel", choices=("rc", "stable"), required=True)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    inspect = commands.add_parser("inspect", help="inspect one release catalog")
    add_common_inspect_arguments(inspect)
    inspect.add_argument("--github-output", type=Path)

    validate = commands.add_parser("validate", help="validate a promotion")
    add_common_inspect_arguments(validate)
    validate.add_argument("--catalog-repo", type=Path, required=True)
    validate.add_argument("--catalog-sha", required=True)
    validate.add_argument("--source-repo", type=Path, required=True)
    validate.add_argument("--rc-tag")
    validate.add_argument("--rc-catalog", type=Path)
    validate.add_argument("--rc-catalog-repo", type=Path)
    validate.add_argument("--rc-catalog-sha")
    validate.add_argument("--rc-source-repo", type=Path)

    notes = commands.add_parser("notes", help="render deterministic release notes")
    notes.add_argument("--channel", choices=("rc", "stable"), required=True)
    notes.add_argument("--tag", required=True)
    notes.add_argument("--catalog-sha", required=True)
    notes.add_argument("--source-sha", required=True)
    notes.add_argument("--rc-tag")
    notes.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "inspect":
            catalog = inspect_catalog(args.catalog, channel=args.channel)
            values = {
                "version": catalog.version.text,
                "tag": catalog.version.tag,
                "source_sha": catalog.source_sha,
            }
            if args.github_output:
                write_outputs(args.github_output, values)
            print(
                f"{args.channel} catalog is {catalog.version.tag} -> "
                f"{catalog.source_sha}"
            )
            return 0

        if args.command == "validate":
            catalog = inspect_catalog(args.catalog, channel=args.channel)
            validate_catalog_checkout(args.catalog_repo, args.catalog_sha)
            bind_catalog_bytes(args.catalog, args.catalog_repo)
            validate_source_checkout(args.source_repo, catalog)
            validate_regenerated_catalog(
                catalog_path=args.catalog,
                source_repo=args.source_repo,
                source_sha=catalog.source_sha,
            )

            rc_values = (
                args.rc_tag,
                args.rc_catalog,
                args.rc_catalog_repo,
                args.rc_catalog_sha,
                args.rc_source_repo,
            )
            if args.channel == "rc":
                if any(value is not None for value in rc_values):
                    raise ReleaseContractError("RC promotion must not specify an RC parent")
            else:
                if any(value is None for value in rc_values):
                    raise ReleaseContractError(
                        "stable promotion requires --rc-tag, --rc-catalog, "
                        "--rc-catalog-repo, --rc-catalog-sha, and --rc-source-repo"
                    )
                assert args.rc_tag is not None
                assert args.rc_catalog is not None
                assert args.rc_catalog_repo is not None
                assert args.rc_catalog_sha is not None
                assert args.rc_source_repo is not None
                rc = inspect_catalog(args.rc_catalog, channel="rc")
                validate_catalog_checkout(
                    args.rc_catalog_repo,
                    args.rc_catalog_sha,
                )
                bind_catalog_bytes(args.rc_catalog, args.rc_catalog_repo)
                validate_source_checkout(args.rc_source_repo, rc)
                validate_regenerated_catalog(
                    catalog_path=args.rc_catalog,
                    source_repo=args.rc_source_repo,
                    source_sha=rc.source_sha,
                )
                validate_stable_promotion(
                    catalog,
                    args.source_repo,
                    args.rc_tag,
                    rc,
                    args.rc_source_repo,
                )
            print(
                f"Validated {args.channel} chain: {catalog.version.tag} -> "
                f"{args.catalog_sha} -> {catalog.source_sha}"
            )
            return 0

        notes = render_notes(
            channel=args.channel,
            tag=args.tag,
            catalog_sha=args.catalog_sha,
            source_sha=args.source_sha,
            rc_tag=args.rc_tag,
        )
        args.output.write_text(notes, encoding="utf-8")
        print(f"Wrote release notes: {args.output}")
        return 0
    except ReleaseContractError as exc:
        print(f"Release contract failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
