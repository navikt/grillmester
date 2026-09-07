#!/usr/bin/env python3
"""Validate and describe Grillmester's immutable release chain.

The public release tag identifies a catalog-only commit. The catalog then
identifies every target payload with one exact GitHub commit SHA. Stable
releases are new, stable-versioned catalogs whose Copilot and OpenCode
payloads are identical to a named RC apart from the Copilot manifest version
and its mechanically derived payload hashes; an RC tag is never moved or
re-used.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import re
import stat
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Sequence


PLUGIN_NAMES = ("grillmester",)
PLUGIN_PATHS = {"grillmester": "plugin"}
NATIVE_TARGET_PATHS = ("targets/opencode-v1",)
OPENCODE_DISTRIBUTION_DIRECTORIES = (
    "targets/opencode-v1",
    "targets/opencode-v1-focused",
)
FOCUSED_COPILOT_DIRECTORY = "targets/copilot-cli-focused-v1"
OPENCODE_DISTRIBUTION_FILES = (
    "LICENSE",
    "PROVENANCE.md",
    "THIRD_PARTY_NOTICES.md",
    "policy/content-lock.json",
    "policy/focused-context-v1.json",
    "scripts/build_opencode_bundle.py",
    "scripts/generate_copilot_manifest.py",
    "scripts/generate_context_projections.py",
    "scripts/grillmester.py",
    "scripts/grillmester_local.py",
    "scripts/release_contract.py",
    "scripts/smoke_grillmester_local.py",
)
STABLE_GATE_HARNESS_FILES = (
    "scripts/release_test_baseline.py",
    "scripts/smoke_grillmester_tui.py",
    "scripts/smoke_plugin_install.py",
    "scripts/smoke_opencode.py",
    "scripts/smoke_opencode_runtime.py",
)
_BASELINE_SPEC = importlib.util.spec_from_file_location(
    "grillmester_release_test_baseline_for_release_contract",
    Path(__file__).with_name("release_test_baseline.py"),
)
if _BASELINE_SPEC is None or _BASELINE_SPEC.loader is None:
    raise RuntimeError("could not load release-test baseline contract")
_BASELINE_MODULE = importlib.util.module_from_spec(_BASELINE_SPEC)
sys.modules[_BASELINE_SPEC.name] = _BASELINE_MODULE
_BASELINE_SPEC.loader.exec_module(_BASELINE_MODULE)
_STANDARD_SUPPORT = _BASELINE_MODULE.CONTRACT["standardSupport"]
_RELEASE_TEST = _BASELINE_MODULE.CONTRACT["releaseTest"]

SUPPORTED_OPENCODE_VERSION = _STANDARD_SUPPORT["opencodeMinimum"]
SUPPORTED_OPENCODE_RANGE = f">={SUPPORTED_OPENCODE_VERSION},<2.0.0"
SUPPORTED_COPILOT_VERSION = _STANDARD_SUPPORT["copilotMinimum"]
SUPPORTED_COPILOT_RANGE = f">={SUPPORTED_COPILOT_VERSION},<2.0.0"
SUPPORTED_CPLT_RELEASE = _STANDARD_SUPPORT["cpltMinimum"]
RELEASE_TEST_OPENCODE_VERSION = _RELEASE_TEST["opencodeVersion"]
RELEASE_TEST_COPILOT_VERSION = _RELEASE_TEST["copilotVersion"]
RELEASE_TEST_CPLT_RELEASE = _RELEASE_TEST["cpltRelease"]
PLUGIN_REPOSITORY = "navikt/grillmester"
CATALOG_PATH = ".github/plugin/marketplace.json"
CONTENT_LOCK_PATH = "policy/content-lock.json"
PROVENANCE_PATH = "PROVENANCE.md"
STABLE_RIGHTS_APPROVAL_PATH = "policy/stable-rights-approval.json"
HOVMESTER_REPOSITORY = "navikt/hovmester"
HOVMESTER_REVISION = "48483bf32c2b6f89c31e7d50e25b5fe6fac45ca2"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
APPROVAL_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
PLACEHOLDER_APPROVAL_TEXT = re.compile(
    r"(?:unverified|unknown|pending|placeholder|example|todo|tbd|replace[-_ ]?me)",
    re.IGNORECASE,
)
SEMVER = re.compile(
    r"^(?P<major>0|[1-9][0-9]*)\."
    r"(?P<minor>0|[1-9][0-9]*)\."
    r"(?P<patch>0|[1-9][0-9]*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
MAX_VERSION_LENGTH = 64
MAX_JSON_DEPTH = 40


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
    if len(value) > MAX_VERSION_LENGTH:
        raise ReleaseContractError(
            f"version must not exceed {MAX_VERSION_LENGTH} characters"
        )
    match = SEMVER.fullmatch(value)
    if match is None:
        raise ReleaseContractError(
            "version must be strict SemVer without build metadata"
        )
    prerelease = match.group("prerelease")
    if prerelease is not None and any(
        identifier != "0"
        and identifier.isdigit()
        and identifier.startswith("0")
        for identifier in prerelease.split(".")
    ):
        raise ReleaseContractError(
            "version must be strict SemVer without leading prerelease zeroes"
        )
    return Version(
        text=value,
        core=tuple(int(match.group(name)) for name in ("major", "minor", "patch")),
        prerelease=prerelease,
    )


def read_object(path: Path) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ReleaseContractError(f"duplicate JSON key in {path}: {key!r}")
            result[key] = value
        return result

    def reject_nonstandard_constant(value: str) -> None:
        raise ReleaseContractError(
            f"non-standard JSON constant in {path}: {value}"
        )

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonstandard_constant,
        )
    except FileNotFoundError as exc:
        raise ReleaseContractError(f"required file is missing: {path}") from exc
    except UnicodeDecodeError as exc:
        raise ReleaseContractError(f"JSON file is not UTF-8: {path}") from exc
    except RecursionError as exc:
        raise ReleaseContractError(f"JSON in {path} exceeds the nesting limit") from exc
    except json.JSONDecodeError as exc:
        raise ReleaseContractError(f"invalid JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise ReleaseContractError(f"could not read JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReleaseContractError(f"expected a JSON object in {path}")
    pending: list[tuple[object, int]] = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > MAX_JSON_DEPTH:
            raise ReleaseContractError(f"JSON in {path} exceeds the nesting limit")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
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
        raise ReleaseContractError("catalog must contain exactly one Grillmester package")
    entries = {
        entry.get("name"): entry
        for entry in plugins
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }
    if tuple(entries) != PLUGIN_NAMES:
        raise ReleaseContractError("catalog package order or names have drifted")

    version = parse_version(entries[PLUGIN_NAMES[0]].get("version"))
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
                "catalog must pin the canonical plugin path at one exact SHA"
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
    for directory in OPENCODE_DISTRIBUTION_DIRECTORIES:
        payload_manifest(repo / directory)
    payload_manifest(repo / FOCUSED_COPILOT_DIRECTORY)
    for relative in OPENCODE_DISTRIBUTION_FILES:
        distribution_file_digest(repo / relative)
    return manifests


def validate_regenerated_catalog(
    *, catalog_path: Path, source_repo: Path, source_sha: str
) -> None:
    def required_text(value: object, *, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ReleaseContractError(f"{label} must be a non-empty string")
        return value.strip()

    if FULL_SHA.fullmatch(source_sha) is None:
        raise ReleaseContractError("catalog regeneration needs an exact source SHA")
    package_manifest = read_object(source_repo / "package-manifest.json")
    marketplace = package_manifest.get("marketplace")
    packages = package_manifest.get("packages")
    if package_manifest.get("schemaVersion") != 1 or not isinstance(marketplace, dict):
        raise ReleaseContractError("package manifest identity is invalid")
    if (
        not isinstance(packages, list)
        or len(packages) != len(PLUGIN_NAMES)
        or not all(isinstance(entry, dict) for entry in packages)
        or [(entry.get("name"), entry.get("path")) for entry in packages]
        != list(zip(PLUGIN_NAMES, (PLUGIN_PATHS[name] for name in PLUGIN_NAMES)))
    ):
        raise ReleaseContractError("package manifest has the wrong package roster")

    owner = required_text(marketplace.get("owner"), label="marketplace owner")
    plugin_entries: list[dict[str, Any]] = []
    versions: set[str] = set()
    for name in PLUGIN_NAMES:
        path = PLUGIN_PATHS[name]
        manifest = read_object(source_repo / path / "plugin.json")
        author = manifest.get("author")
        if not isinstance(author, dict) or required_text(
            author.get("name"), label="plugin author"
        ) != owner:
            raise ReleaseContractError("plugin author must match marketplace owner")
        if manifest.get("repository") != f"https://github.com/{PLUGIN_REPOSITORY}":
            raise ReleaseContractError("plugin repository is not canonical")
        version = required_text(manifest.get("version"), label="plugin version")
        versions.add(version)
        plugin_entries.append(
            {
                "name": name,
                "description": required_text(
                    manifest.get("description"), label="plugin description"
                ),
                "version": version,
                "source": {
                    "source": "github",
                    "repo": PLUGIN_REPOSITORY,
                    "path": path,
                    "sha": source_sha,
                },
            }
        )
    if len(versions) != 1:
        raise ReleaseContractError("plugin versions differ")
    version = next(iter(versions))
    expected = {
        "name": required_text(marketplace.get("name"), label="marketplace name"),
        "owner": {"name": owner},
        "metadata": {
            "description": required_text(
                marketplace.get("description"), label="marketplace description"
            ),
            "version": version,
        },
        "plugins": plugin_entries,
    }
    generated = (json.dumps(expected, indent=2, ensure_ascii=False) + "\n").encode()
    if generated != catalog_path.read_bytes():
        raise ReleaseContractError(
            "catalog commit is not byte-identical to trusted regeneration from source.sha"
        )


def payload_manifest(plugin: Path, *, exclude_manifest: bool = False) -> dict[str, str]:
    if plugin.is_symlink() or not plugin.is_dir():
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


def distribution_file_digest(path: Path) -> str:
    """Hash one required regular distribution input without following symlinks."""

    if path.is_symlink() or not path.is_file():
        raise ReleaseContractError(
            f"OpenCode distribution input is not a regular file: {path}"
        )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _exact_keys(value: object, expected: set[str], *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ReleaseContractError(
            f"{label} must be an object with exactly {sorted(expected)}"
        )
    return value


def _component_digest(path: Path) -> str:
    """Bind one imported component, including its complete regular-file roster."""

    if path.is_symlink():
        raise ReleaseContractError(f"rights-scoped component is a symlink: {path}")
    if path.is_file():
        return distribution_file_digest(path)
    manifest = payload_manifest(path)
    canonical = json.dumps(
        manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _hovmester_component_digests(source_repo: Path) -> dict[str, dict[str, str]]:
    content_lock = read_object(source_repo / CONTENT_LOCK_PATH)
    sources = content_lock.get("sources")
    if not isinstance(sources, dict):
        raise ReleaseContractError("content-lock sources must be an object")
    hovmester = _exact_keys(
        sources.get("hovmester"),
        {"repository", "revision"},
        label="content-lock Hovmester source",
    )
    if hovmester["repository"] != HOVMESTER_REPOSITORY:
        raise ReleaseContractError("content lock has no canonical Hovmester source")
    if hovmester["revision"] != HOVMESTER_REVISION:
        raise ReleaseContractError("content lock Hovmester revision is not release-approved")

    result: dict[str, dict[str, str]] = {"agents": {}, "skills": {}}
    for kind in ("agents", "skills"):
        contracts = content_lock.get(kind)
        if not isinstance(contracts, dict):
            raise ReleaseContractError(f"content lock {kind} must be an object")
        for component_id, contract in sorted(contracts.items()):
            if not isinstance(component_id, str) or not isinstance(contract, dict):
                raise ReleaseContractError(f"content lock {kind} entry is invalid")
            raw_source_ids = contract.get("source")
            if isinstance(raw_source_ids, str):
                source_ids = {raw_source_ids}
            elif (
                isinstance(raw_source_ids, list)
                and raw_source_ids
                and all(isinstance(source_id, str) for source_id in raw_source_ids)
            ):
                source_ids = set(raw_source_ids)
            else:
                raise ReleaseContractError(
                    f"content lock {kind} {component_id} source must name one or more sources"
                )
            lineage = contract.get("lineage", [])
            if not isinstance(lineage, list) or not all(
                isinstance(entry, dict) and isinstance(entry.get("source"), str)
                for entry in lineage
            ):
                raise ReleaseContractError(
                    f"content lock {kind} {component_id} lineage must contain source objects"
                )
            source_ids.update(entry["source"] for entry in lineage)
            if "hovmester" not in source_ids:
                continue
            component_path = (
                source_repo / "plugin/agents" / f"{component_id}.agent.md"
                if kind == "agents"
                else source_repo / "plugin/skills" / component_id
            )
            result[kind][component_id] = _component_digest(component_path)
    if set(result["agents"]) != {"designer", "doctor-who"}:
        raise ReleaseContractError(
            "rights scope must contain exactly the imported Designer and Doctor Who agents"
        )
    if not result["skills"]:
        raise ReleaseContractError("rights scope contains no Hovmester-imported skills")
    return result


def _validate_approval_decision(
    value: object, *, label: str, allowed_statuses: set[str]
) -> str:
    decision = _exact_keys(
        value,
        {"status", "decisionReference", "authority", "date"},
        label=label,
    )
    status = decision["status"]
    if status not in allowed_statuses:
        raise ReleaseContractError(
            f"{label}.status must be one of {sorted(allowed_statuses)}"
        )
    authority = _exact_keys(
        decision["authority"], {"role", "team"}, label=f"{label}.authority"
    )
    for field, text in (
        ("decisionReference", decision["decisionReference"]),
        ("authority.role", authority["role"]),
        ("authority.team", authority["team"]),
    ):
        if (
            not isinstance(text, str)
            or not text.strip()
            or len(text) > 256
            or PLACEHOLDER_APPROVAL_TEXT.search(text)
        ):
            raise ReleaseContractError(f"{label}.{field} is missing or a placeholder")
    date_text = decision["date"]
    if not isinstance(date_text, str) or APPROVAL_DATE.fullmatch(date_text) is None:
        raise ReleaseContractError(f"{label}.date must be an ISO calendar date")
    try:
        decision_date = dt.date.fromisoformat(date_text)
    except ValueError as exc:
        raise ReleaseContractError(f"{label}.date is not a real calendar date") from exc
    if decision_date > dt.date.today():
        raise ReleaseContractError(f"{label}.date must not be in the future")
    return status


def validate_stable_rights_approval(source_repo: Path) -> None:
    """Require a reviewed, content-bound legal/rights record for stable only."""

    approval_path = source_repo / STABLE_RIGHTS_APPROVAL_PATH
    approval = read_object(approval_path)
    approval = _exact_keys(
        approval, {"schemaVersion", "scope", "decisions"}, label="stable rights approval"
    )
    if approval["schemaVersion"] != 1:
        raise ReleaseContractError("stable rights approval schemaVersion must be 1")

    scope = _exact_keys(
        approval["scope"],
        {"hovmester", "contentLockSha256", "provenanceSha256", "components"},
        label="stable rights approval scope",
    )
    hovmester = _exact_keys(
        scope["hovmester"], {"repository", "revision"}, label="approval Hovmester scope"
    )
    if hovmester != {
        "repository": HOVMESTER_REPOSITORY,
        "revision": HOVMESTER_REVISION,
    }:
        raise ReleaseContractError("stable rights approval has the wrong Hovmester scope")

    expected_content_lock = distribution_file_digest(source_repo / CONTENT_LOCK_PATH)
    expected_provenance = distribution_file_digest(source_repo / PROVENANCE_PATH)
    if scope["contentLockSha256"] != expected_content_lock:
        raise ReleaseContractError("stable rights approval does not bind content-lock.json")
    if scope["provenanceSha256"] != expected_provenance:
        raise ReleaseContractError("stable rights approval does not bind PROVENANCE.md")
    for field in ("contentLockSha256", "provenanceSha256"):
        if not isinstance(scope[field], str) or SHA256.fullmatch(scope[field]) is None:
            raise ReleaseContractError(f"stable rights approval {field} is not SHA-256")

    components = _exact_keys(
        scope["components"], {"agents", "skills"}, label="stable rights component scope"
    )
    expected_components = _hovmester_component_digests(source_repo)
    if components != expected_components:
        raise ReleaseContractError(
            "stable rights approval does not bind the exact imported component IDs and digests"
        )

    decisions = _exact_keys(
        approval["decisions"],
        {"organizationalRights", "doctorWhoBrand"},
        label="stable rights decisions",
    )
    _validate_approval_decision(
        decisions["organizationalRights"],
        label="organizationalRights",
        allowed_statuses={"approved"},
    )
    brand_status = _validate_approval_decision(
        decisions["doctorWhoBrand"],
        label="doctorWhoBrand",
        allowed_statuses={"approved", "renamed"},
    )
    if brand_status == "renamed" and "doctor-who" in expected_components["agents"]:
        raise ReleaseContractError(
            "doctorWhoBrand cannot be 'renamed' while the Doctor Who agent remains in scope"
        )


def _validate_focused_copilot_stable_promotion(
    stable_source: Path,
    rc_source: Path,
    *,
    stable_version: Version,
    rc_version: Version,
) -> None:
    """Allow only the mechanically regenerated hashes caused by a version bump."""

    stable_target = stable_source / FOCUSED_COPILOT_DIRECTORY
    rc_target = rc_source / FOCUSED_COPILOT_DIRECTORY
    stable_plugin = stable_target / "plugin.json"
    rc_plugin = rc_target / "plugin.json"
    canonical_stable = stable_source / "plugin/plugin.json"
    canonical_rc = rc_source / "plugin/plugin.json"
    if stable_plugin.read_bytes() != canonical_stable.read_bytes() or (
        rc_plugin.read_bytes() != canonical_rc.read_bytes()
    ):
        raise ReleaseContractError(
            "focused Copilot plugin.json must be byte-identical to its canonical plugin"
        )

    stable_plugin_bytes = stable_plugin.read_bytes()
    rc_plugin_bytes = rc_plugin.read_bytes()
    stable_version_bytes = json.dumps(stable_version.text).encode("utf-8")
    rc_version_bytes = json.dumps(rc_version.text).encode("utf-8")
    version_field = re.compile(
        rb'("version"\s*:\s*)' + re.escape(stable_version_bytes)
    )
    normalized_plugin, substitutions = version_field.subn(
        rb"\g<1>" + rc_version_bytes, stable_plugin_bytes
    )
    if substitutions != 1 or normalized_plugin != rc_plugin_bytes:
        raise ReleaseContractError(
            "focused Copilot plugin.json differs from the RC beyond its version value"
        )

    stable_full_manifest = _validate_copilot_full_payload_manifest(
        stable_source, label="stable"
    )
    rc_full_manifest = _validate_copilot_full_payload_manifest(
        rc_source, label="RC"
    )
    stable_full_digest = hashlib.sha256(stable_full_manifest).hexdigest()
    rc_full_digest = hashlib.sha256(rc_full_manifest).hexdigest()

    stable_manifest_path = stable_target / "manifest.json"
    rc_manifest_path = rc_target / "manifest.json"
    stable_manifest = read_object(stable_manifest_path)
    rc_manifest = read_object(rc_manifest_path)
    stable_plugin_digest = hashlib.sha256(stable_plugin_bytes).hexdigest()
    rc_plugin_digest = hashlib.sha256(rc_plugin_bytes).hexdigest()
    for label, manifest, plugin_digest, full_digest in (
        ("stable", stable_manifest, stable_plugin_digest, stable_full_digest),
        ("RC", rc_manifest, rc_plugin_digest, rc_full_digest),
    ):
        source = manifest.get("source")
        files = manifest.get("files")
        if (
            not isinstance(source, dict)
            or source.get("payloadManifest") != "plugin/manifest.json"
            or source.get("payloadManifestSha256") != full_digest
            or not isinstance(files, dict)
            or not isinstance(files.get("plugin.json"), dict)
            or files["plugin.json"].get("sha256") != plugin_digest
        ):
            raise ReleaseContractError(
                f"{label} focused Copilot manifest does not bind its full source payload"
            )
    stable_manifest_bytes = stable_manifest_path.read_bytes()
    if (
        stable_manifest_bytes.count(stable_plugin_digest.encode("ascii")) != 1
        or stable_manifest_bytes.count(stable_full_digest.encode("ascii")) != 1
    ):
        raise ReleaseContractError(
            "stable focused Copilot manifest must contain exactly one derived plugin "
            "and full-payload hash"
        )
    normalized_manifest = stable_manifest_bytes.replace(
        stable_plugin_digest.encode("ascii"), rc_plugin_digest.encode("ascii")
    ).replace(
        stable_full_digest.encode("ascii"), rc_full_digest.encode("ascii")
    )
    if normalized_manifest != rc_manifest_path.read_bytes():
        raise ReleaseContractError(
            "focused Copilot manifest differs from the RC beyond derived plugin hashes"
        )

    stable_payload = payload_manifest(stable_target)
    rc_payload = payload_manifest(rc_target)
    for derived in ("plugin.json", "manifest.json"):
        stable_payload.pop(derived, None)
        rc_payload.pop(derived, None)
    if stable_payload != rc_payload:
        raise ReleaseContractError(
            "focused Copilot payload differs from the reviewed RC"
        )


def _validate_copilot_full_payload_manifest(source: Path, *, label: str) -> bytes:
    plugin_root = source / "plugin"
    manifest_path = plugin_root / "manifest.json"
    try:
        root_mode = plugin_root.lstat().st_mode
        manifest_mode = manifest_path.lstat().st_mode
    except OSError as exc:
        raise ReleaseContractError(
            f"{label} Copilot full payload or manifest is missing: {exc}"
        ) from exc
    if stat.S_ISLNK(root_mode) or not stat.S_ISDIR(root_mode):
        raise ReleaseContractError(
            f"{label} Copilot full payload root is not a regular directory"
        )
    if stat.S_ISLNK(manifest_mode) or not stat.S_ISREG(manifest_mode) or (
        stat.S_IMODE(manifest_mode) != 0o644
    ):
        raise ReleaseContractError(
            f"{label} Copilot full payload manifest is not a mode-0644 regular file"
        )
    manifest_bytes = manifest_path.read_bytes()
    manifest = read_object(manifest_path)
    expected_fields = {
        "schemaVersion",
        "target",
        "generator",
        "counts",
        "agents",
        "skills",
        "files",
    }
    if set(manifest) != expected_fields or (
        manifest.get("schemaVersion") != 1
        or manifest.get("target") != "copilot-full-v1"
        or manifest.get("generator")
        != {"path": "scripts/generate_copilot_manifest.py", "version": 1}
    ):
        raise ReleaseContractError(
            f"{label} Copilot full payload manifest identity is invalid"
        )
    contracts = manifest.get("files")
    if not isinstance(contracts, dict) or not contracts:
        raise ReleaseContractError(
            f"{label} Copilot full payload manifest has no file contracts"
        )
    actual: dict[str, dict[str, str]] = {}
    portable_paths: dict[str, str] = {}
    for path in sorted(plugin_root.rglob("*")):
        observed = path.lstat()
        if stat.S_ISLNK(observed.st_mode):
            raise ReleaseContractError(
                f"{label} Copilot full payload contains a symlink: {path}"
            )
        if stat.S_ISDIR(observed.st_mode):
            continue
        if not stat.S_ISREG(observed.st_mode):
            raise ReleaseContractError(
                f"{label} Copilot full payload contains a special node: {path}"
            )
        if path == manifest_path:
            continue
        relative = path.relative_to(plugin_root).as_posix()
        portable = unicodedata.normalize("NFC", relative).casefold()
        previous = portable_paths.get(portable)
        if previous is not None and previous != relative:
            raise ReleaseContractError(
                f"{label} Copilot full payload has a portable path collision: "
                f"{previous}, {relative}"
            )
        portable_paths[portable] = relative
        mode = stat.S_IMODE(observed.st_mode)
        if mode not in (0o644, 0o755):
            raise ReleaseContractError(
                f"{label} Copilot full payload has unsupported mode {mode:04o}: "
                f"{relative}"
            )
        actual[relative] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "mode": f"{mode:04o}",
        }
    for raw_path, contract in contracts.items():
        if not isinstance(raw_path, str):
            raise ReleaseContractError(
                f"{label} Copilot full payload manifest contains a non-text path"
            )
        relative = PurePosixPath(raw_path)
        if (
            relative.is_absolute()
            or relative.as_posix() != raw_path
            or any(part in ("", ".", "..") for part in relative.parts)
            or raw_path == "manifest.json"
            or not isinstance(contract, dict)
            or set(contract) != {"sha256", "mode"}
            or not isinstance(contract.get("sha256"), str)
            or SHA256.fullmatch(contract["sha256"]) is None
            or contract.get("mode") not in {"0644", "0755"}
        ):
            raise ReleaseContractError(
                f"{label} Copilot full payload manifest contract is invalid: "
                f"{raw_path!r}"
            )
    if actual != contracts:
        raise ReleaseContractError(
            f"{label} Copilot full payload differs from its manifest"
        )
    agents = manifest.get("agents")
    skills = manifest.get("skills")
    component_id = re.compile(r"^[a-z][a-z0-9-]*$")
    observed_agent_files = {path for path in actual if path.startswith("agents/")}
    observed_agents = sorted(
        path.removeprefix("agents/").removesuffix(".agent.md")
        for path in observed_agent_files
        if path.endswith(".agent.md") and path.count("/") == 1
    )
    observed_skills = sorted(
        {
            path.split("/", 2)[1]
            for path in actual
            if path.startswith("skills/") and path.count("/") >= 2
        }
    )
    if (
        agents != observed_agents
        or skills != observed_skills
        or any(component_id.fullmatch(item) is None for item in (*observed_agents, *observed_skills))
        or observed_agent_files
        != {f"agents/{agent}.agent.md" for agent in observed_agents}
        or any(f"skills/{skill}/SKILL.md" not in actual for skill in observed_skills)
        or manifest.get("counts")
        != {"agents": len(observed_agents), "skills": len(observed_skills)}
    ):
        raise ReleaseContractError(
            f"{label} Copilot full payload roster differs from its manifest"
        )
    return manifest_bytes


def _validate_copilot_full_stable_promotion(
    stable_source: Path, rc_source: Path
) -> None:
    stable_manifest = _validate_copilot_full_payload_manifest(
        stable_source, label="stable"
    )
    rc_manifest = _validate_copilot_full_payload_manifest(rc_source, label="RC")
    stable_plugin = (stable_source / "plugin/plugin.json").read_bytes()
    rc_plugin = (rc_source / "plugin/plugin.json").read_bytes()
    stable_digest = hashlib.sha256(stable_plugin).hexdigest()
    rc_digest = hashlib.sha256(rc_plugin).hexdigest()
    if stable_manifest.count(stable_digest.encode("ascii")) != 1:
        raise ReleaseContractError(
            "stable Copilot full payload manifest must bind plugin.json exactly once"
        )
    normalized = stable_manifest.replace(
        stable_digest.encode("ascii"), rc_digest.encode("ascii")
    )
    if normalized != rc_manifest:
        raise ReleaseContractError(
            "stable Copilot full payload manifest differs from the RC beyond the "
            "derived plugin.json hash"
        )


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
        stable_payload.pop("manifest.json", None)
        rc_payload.pop("manifest.json", None)
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

    _validate_copilot_full_stable_promotion(stable_source, rc_source)

    for directory in OPENCODE_DISTRIBUTION_DIRECTORIES:
        stable_payload = payload_manifest(stable_source / directory)
        rc_payload = payload_manifest(rc_source / directory)
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
                f"stable {directory} payload differs from the reviewed RC"
                + (f"; {detail}" if detail else "")
            )

    _validate_focused_copilot_stable_promotion(
        stable_source,
        rc_source,
        stable_version=stable.version,
        rc_version=rc.version,
    )

    for relative in OPENCODE_DISTRIBUTION_FILES:
        stable_digest = distribution_file_digest(stable_source / relative)
        rc_digest = distribution_file_digest(rc_source / relative)
        if stable_digest != rc_digest:
            raise ReleaseContractError(
                f"stable {relative} differs from the reviewed RC"
            )

    for relative in STABLE_GATE_HARNESS_FILES:
        stable_digest = distribution_file_digest(stable_source / relative)
        rc_digest = distribution_file_digest(rc_source / relative)
        if stable_digest != rc_digest:
            raise ReleaseContractError(
                f"stable release-gate harness {relative} differs from the reviewed RC"
            )

    validate_stable_rights_approval(stable_source)


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
        f"\nThis stable release promotes the tested `{rc_tag}` payload. The only "
        "permitted semantic payload change is the `plugin.json.version` value; "
        "the full and focused Copilot manifest hashes are regenerated "
        "mechanically from it.\n"
        if rc_tag
        else ""
    )
    terminal_install = f"""### Install the terminal launcher

Download the bundle and its detached checksum from this release, verify the
checksum, then extract the archive:

```bash
shasum -a 256 -c grillmester-terminal-{tag}.tar.gz.sha256
tar -xzf grillmester-terminal-{tag}.tar.gz
```

The extracted `scripts/grillmester.py` is the launcher. Put it on `PATH` as
`grillmester`, or invoke it by path. It uses the OpenCode and GitHub Copilot CLI
executables from `PATH` and does not package either client binary. cplt is
installed and updated separately.
"""
    update_commands = """Grillmester, cplt, OpenCode, and GitHub Copilot CLI keep
separate update lifecycles. Replace the extracted bundle with a newer release to
update Grillmester, and update each client with its own installer:

```bash
brew upgrade navikt/tap/cplt
brew upgrade opencode
brew upgrade --cask copilot-cli
```"""
    return f"""## Grillmester {tag}

This is a **{status}** with an immutable, two-step provenance chain.{promoted}
| Layer | Immutable identity |
| --- | --- |
| Release tag | `{tag}` → catalog commit `{catalog_sha}` |
| Source payloads | catalog source → `{source_sha}` |
| Grillmester terminal bundle (no client binaries) | release asset built from `{source_sha}` |

The tag points to a catalog-only commit. It never points at `main` and is never
moved after publication.

{terminal_install}

The bundle manifest identifies the outer distribution as
`grillmester-terminal-v1`; its exact client versions are release-test metadata,
not runtime pins. The inner native OpenCode target remains `opencode-v1`.
Install only the client or clients you want to use:

```bash
brew install opencode
brew install --cask copilot-cli
```

{update_commands}

The standard launcher accepts OpenCode `{SUPPORTED_OPENCODE_RANGE}`, GitHub
Copilot CLI `{SUPPORTED_COPILOT_RANGE}`, and the tested cplt baseline
`{SUPPORTED_CPLT_RELEASE}` or a newer release. The release gate exercises exact
OpenCode `{RELEASE_TEST_OPENCODE_VERSION}`, Copilot CLI
`{RELEASE_TEST_COPILOT_VERSION}`, and cplt `{RELEASE_TEST_CPLT_RELEASE}`. Newer
compatible clients are not the exact bytes covered by the release gate.

### Run with Copilot CLI from PATH

```bash
grillmester doctor --client copilot
grillmester --client copilot --agent grillmester
```

The launcher supplies the reviewed plugin directory and starts the installed
GitHub Copilot CLI through cplt.

### Install directly in Copilot CLI

This alternative registers the immutable marketplace tag in Copilot CLI's own
plugin store. It is separate from the launcher path above.

```bash
copilot plugin marketplace add navikt/grillmester#{tag}
copilot plugin install grillmester@grillmester
copilot --agent=grillmester:grillmester
```

### Run with OpenCode from PATH

```bash
grillmester doctor --client opencode
grillmester --client opencode --agent grillmester \\
  --allow-localhost 1234 -- --model lmstudio/replace-with-local-model-id
```

The launcher binds the installed Grillmester target and starts the PATH-resolved
OpenCode through cplt. Declare the provider and model in the user's normal
OpenCode config before launch. This source-pinned
[local-provider example](https://github.com/navikt/grillmester/blob/{source_sha}/docs/local-models.md#avansert-manuell-opencode-binding)
shows the complete OpenAI-compatible shape; OpenCode's built-in GitHub Copilot
provider instead uses its normal `/connect` flow. The source-pinned
[native cplt notes](https://github.com/navikt/grillmester/blob/{source_sha}/docs/opencode.md#kom-i-gang)
describe the tested launcher boundary and any client-provider network access
that must be admitted by the user's cplt policy.

The exact OpenCode, Copilot CLI, and cplt versions named above are release-test
inputs, not client binaries shipped in the bundle. The executable release-test
baseline is used only by the release gate to authenticate those test inputs.
Users remain in control of the compatible client versions installed on their
machines.

### Verify Copilot

```bash
copilot plugin list
```

### Verify OpenCode

`doctor` validates the PATH-selected clients and the reviewed target without
starting an interactive session or contacting a model. `--print-command` then
previews the exact cplt invocation; it is a rendering aid and performs no
client or version validation of its own:

```bash
grillmester doctor --client opencode
grillmester --client opencode --agent grillmester --print-command
```

### Roll back

For a repository activation, revert its marketplace `ref` to the previously
reviewed tag. For a personal installation, uninstall Grillmester, add/update
the marketplace at the previous tag, and reinstall the plugin. Tags are
immutable; never retag an older or
newer catalog.

For the terminal launcher, stop the active session and extract the previously
reviewed release bundle in place of the current one. Grillmester does not create
a separate lifecycle installation or copy client binaries into its bundle.
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

    validate_source = commands.add_parser(
        "validate-source-promotion",
        help="validate a prospective catalog and its source before catalog publication",
    )
    add_common_inspect_arguments(validate_source)
    validate_source.add_argument("--source-repo", type=Path, required=True)
    validate_source.add_argument("--rc-tag")
    validate_source.add_argument("--rc-catalog", type=Path)
    validate_source.add_argument("--rc-source-repo", type=Path)

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

        if args.command == "validate-source-promotion":
            catalog = inspect_catalog(args.catalog, channel=args.channel)
            validate_source_checkout(args.source_repo, catalog)
            validate_regenerated_catalog(
                catalog_path=args.catalog,
                source_repo=args.source_repo,
                source_sha=catalog.source_sha,
            )
            rc_values = (args.rc_tag, args.rc_catalog, args.rc_source_repo)
            if args.channel == "rc":
                if any(value is not None for value in rc_values):
                    raise ReleaseContractError(
                        "RC source promotion must not specify an RC parent"
                    )
            else:
                if any(value is None for value in rc_values):
                    raise ReleaseContractError(
                        "stable source promotion requires --rc-tag, --rc-catalog, "
                        "and --rc-source-repo"
                    )
                assert args.rc_tag is not None
                assert args.rc_catalog is not None
                assert args.rc_source_repo is not None
                rc = inspect_catalog(args.rc_catalog, channel="rc")
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
                f"Validated prospective {args.channel} source: "
                f"{catalog.version.tag} -> {catalog.source_sha}"
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
