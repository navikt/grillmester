#!/usr/bin/env python3
"""Generate the Grillmester marketplace catalog from canonical package manifests."""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE_MANIFEST = Path("package-manifest.json")
DEFAULT_OUTPUT = Path(".github/plugin/marketplace.json")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


class MarketplaceError(ValueError):
    """Raised when canonical metadata cannot produce a safe catalog."""


@dataclass(frozen=True)
class Package:
    name: str
    path: str
    manifest: dict[str, Any]


def load_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MarketplaceError(f"{label} does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise MarketplaceError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise MarketplaceError(f"{label} must contain a JSON object")
    return value


def required_text(value: dict[str, Any], key: str, *, label: str) -> str:
    field = value.get(key)
    if not isinstance(field, str) or not field.strip():
        raise MarketplaceError(f"{label} needs a non-empty {key!r}")
    return field.strip()


def author_name(manifest: dict[str, Any]) -> str:
    author = manifest.get("author")
    if not isinstance(author, dict):
        raise MarketplaceError("plugin manifest author must be an object")
    return required_text(author, "name", label="plugin manifest author")


def github_repository(manifest: dict[str, Any]) -> str:
    repository = required_text(manifest, "repository", label="plugin manifest")
    parsed = urlparse(repository)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise MarketplaceError(
            "plugin manifest repository must be an https://github.com URL"
        )
    parts = [part for part in parsed.path.removesuffix(".git").split("/") if part]
    if len(parts) != 2:
        raise MarketplaceError(
            "plugin manifest repository must identify one GitHub owner/repository"
        )
    return "/".join(parts)


def load_packages(package_manifest_path: Path) -> tuple[dict[str, Any], list[Package]]:
    package_manifest = load_object(package_manifest_path, label="package manifest")
    if package_manifest.get("schemaVersion") != 1:
        raise MarketplaceError("package manifest schemaVersion must be 1")
    definitions = package_manifest.get("packages")
    if not isinstance(definitions, list) or not definitions:
        raise MarketplaceError("package manifest must contain packages")

    packages: list[Package] = []
    names: set[str] = set()
    paths: set[str] = set()
    for index, definition in enumerate(definitions):
        if not isinstance(definition, dict):
            raise MarketplaceError(f"package definition {index} must be an object")
        name = required_text(definition, "name", label=f"package definition {index}")
        path = required_text(definition, "path", label=f"package definition {index}")
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != path:
            raise MarketplaceError(f"package path must be repository-relative: {path}")
        if name in names or path in paths:
            raise MarketplaceError("package names and paths must be unique")
        manifest = load_object(ROOT / relative / "plugin.json", label="plugin manifest")
        if manifest.get("name") != name:
            raise MarketplaceError(
                f"package {name!r} does not match {path}/plugin.json name"
            )
        names.add(name)
        paths.add(path)
        packages.append(Package(name=name, path=path, manifest=manifest))
    return package_manifest, packages


def build_marketplace(
    package_manifest: dict[str, Any],
    packages: list[Package],
    *,
    mode: str,
    sha: str | None = None,
) -> dict[str, Any]:
    marketplace = package_manifest.get("marketplace")
    if not isinstance(marketplace, dict):
        raise MarketplaceError("package manifest marketplace must be an object")
    name = required_text(marketplace, "name", label="marketplace")
    description = required_text(marketplace, "description", label="marketplace")
    owner = required_text(marketplace, "owner", label="marketplace")

    repositories = {github_repository(package.manifest) for package in packages}
    versions = {
        required_text(package.manifest, "version", label="plugin manifest")
        for package in packages
    }
    authors = {author_name(package.manifest) for package in packages}
    if len(repositories) != 1:
        raise MarketplaceError("all packages must use the same GitHub repository")
    if len(versions) != 1:
        raise MarketplaceError("all packages must use the same version")
    if authors != {owner}:
        raise MarketplaceError("marketplace owner must match every package author")

    if mode == "development":
        if sha is not None:
            raise MarketplaceError("--sha is only valid in release mode")
    elif mode == "release":
        if sha is None or not FULL_SHA.fullmatch(sha):
            raise MarketplaceError("release mode requires a lowercase 40-character SHA")
    else:
        raise MarketplaceError(f"unsupported marketplace mode: {mode!r}")

    repository = next(iter(repositories))
    version = next(iter(versions))
    entries: list[dict[str, Any]] = []
    for package in packages:
        source: str | dict[str, str]
        if mode == "development":
            source = package.path
        else:
            assert sha is not None
            source = {
                "source": "github",
                "repo": repository,
                "path": package.path,
                "sha": sha,
            }
        entries.append(
            {
                "name": package.name,
                "description": required_text(
                    package.manifest, "description", label="plugin manifest"
                ),
                "version": version,
                "source": source,
            }
        )

    return {
        "name": name,
        "owner": {"name": owner},
        "metadata": {"description": description, "version": version},
        "plugins": entries,
    }


def render_marketplace(marketplace: dict[str, Any]) -> str:
    return json.dumps(marketplace, indent=2, ensure_ascii=False) + "\n"


def update_catalog(output: Path, expected: str, *, check: bool) -> bool:
    current = output.read_text(encoding="utf-8") if output.is_file() else ""
    if check:
        if current == expected:
            return False
        diff = difflib.unified_diff(
            current.splitlines(keepends=True),
            expected.splitlines(keepends=True),
            fromfile=str(output),
            tofile=f"{output} (generated)",
        )
        print("marketplace catalog is not generated from package-manifest.json", file=sys.stderr)
        print("".join(diff), file=sys.stderr, end="")
        raise MarketplaceError("marketplace catalog is stale")
    if current == expected:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(expected, encoding="utf-8")
    return True


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("development", "release"), default="development"
    )
    parser.add_argument("--sha", help="exact plugin commit SHA for release mode")
    parser.add_argument(
        "--package-manifest",
        type=Path,
        default=DEFAULT_PACKAGE_MANIFEST,
        help="package manifest path relative to the repository root",
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help="catalog path relative to the repository root",
    )
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def resolve_from_root(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        package_manifest, packages = load_packages(
            resolve_from_root(args.package_manifest)
        )
        marketplace = build_marketplace(
            package_manifest, packages, mode=args.mode, sha=args.sha
        )
        output = resolve_from_root(args.output)
        changed = update_catalog(
            output, render_marketplace(marketplace), check=args.check
        )
    except MarketplaceError as exc:
        print(f"Marketplace generation failed: {exc}", file=sys.stderr)
        return 1
    if args.check:
        print(f"Marketplace catalog is current: {output}")
    elif changed:
        print(f"Generated marketplace catalog: {output}")
    else:
        print(f"Marketplace catalog was already current: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
