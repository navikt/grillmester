#!/usr/bin/env python3
"""Generate the Grillmester marketplace catalog from plugin/plugin.json."""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path("plugin/plugin.json")
DEFAULT_OUTPUT = Path(".github/plugin/marketplace.json")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


class MarketplaceError(ValueError):
    """Raised when the canonical manifest cannot produce a safe catalog."""


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MarketplaceError(f"plugin manifest does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise MarketplaceError(f"plugin manifest is not valid JSON: {exc}") from exc

    if not isinstance(value, dict):
        raise MarketplaceError("plugin manifest must contain a JSON object")
    return value


def required_text(manifest: dict[str, Any], key: str) -> str:
    value = manifest.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MarketplaceError(f"plugin manifest needs a non-empty {key!r}")
    return value.strip()


def author_name(manifest: dict[str, Any]) -> str:
    author = manifest.get("author")
    if not isinstance(author, dict):
        raise MarketplaceError("plugin manifest author must be an object")
    name = author.get("name")
    if not isinstance(name, str) or not name.strip():
        raise MarketplaceError("plugin manifest author needs a non-empty name")
    return name.strip()


def github_repository(manifest: dict[str, Any]) -> str:
    repository = required_text(manifest, "repository")
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


def build_marketplace(
    manifest: dict[str, Any], *, mode: str, sha: str | None = None
) -> dict[str, Any]:
    name = required_text(manifest, "name")
    version = required_text(manifest, "version")
    description = required_text(manifest, "description")
    owner = author_name(manifest)

    if mode == "development":
        if sha is not None:
            raise MarketplaceError("--sha is only valid in release mode")
        source: str | dict[str, str] = "plugin"
    elif mode == "release":
        if sha is None or not FULL_SHA.fullmatch(sha):
            raise MarketplaceError("release mode requires a lowercase 40-character SHA")
        source = {
            "source": "github",
            "repo": github_repository(manifest),
            "path": "plugin",
            "sha": sha,
        }
    else:
        raise MarketplaceError(f"unsupported marketplace mode: {mode!r}")

    return {
        "name": name,
        "owner": {"name": owner},
        "metadata": {
            "description": description,
            "version": version,
        },
        "plugins": [
            {
                "name": name,
                "description": description,
                "version": version,
                "source": source,
            }
        ],
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
        print("marketplace catalog is not generated from plugin/plugin.json", file=sys.stderr)
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
        "--mode",
        choices=("development", "release"),
        default="development",
        help="use a local plugin path or an immutable GitHub source",
    )
    parser.add_argument("--sha", help="exact plugin commit SHA for release mode")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="manifest path relative to the repository root",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="catalog path relative to the repository root",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail instead of writing when the catalog differs",
    )
    return parser.parse_args(argv)


def resolve_from_root(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = load_manifest(resolve_from_root(args.manifest))
        marketplace = build_marketplace(manifest, mode=args.mode, sha=args.sha)
        output = resolve_from_root(args.output)
        changed = update_catalog(
            output,
            render_marketplace(marketplace),
            check=args.check,
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
