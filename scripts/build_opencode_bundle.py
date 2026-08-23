#!/usr/bin/env python3
"""Build a deterministic, manifest-verified Grillmester OpenCode bundle."""

from __future__ import annotations

import argparse
import ast
import base64
import binascii
import errno
import gzip
import hashlib
import io
import json
import os
import re
import stat
import sys
import tarfile
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Sequence


ARCHIVE_ROOT = PurePosixPath("grillmester-opencode-v1")
TARGET_NAME = "opencode-v1"
TARGET_DIRECTORY = PurePosixPath("targets/opencode-v1")
PLUGIN_DIRECTORY = PurePosixPath("plugin")
LAUNCHER_PATH = PurePosixPath("scripts/grillmester.py")
MANAGER_PATH = PurePosixPath("scripts/manage_opencode.py")
PERMISSION_COMPOSER_PATH = PurePosixPath("scripts/compose_opencode_permissions.py")
ARTIFACT_VERIFIER_PATH = PurePosixPath("scripts/verify_client_artifact.py")
PROFILE_DIRECTORY = PurePosixPath("profiles/opencode")
CLIENT_ARTIFACTS_PATH = PurePosixPath("policy/client-artifacts.json")
CONTENT_LOCK_PATH = PurePosixPath("policy/content-lock.json")
LICENSE_PATH = PurePosixPath("LICENSE")
PROVENANCE_PATH = PurePosixPath("PROVENANCE.md")
THIRD_PARTY_NOTICES_SOURCE = PurePosixPath("THIRD_PARTY_NOTICES.md")
THIRD_PARTY_NOTICES_PATH = PurePosixPath("THIRD_PARTY_NOTICES.md")
OUTER_MANIFEST = PurePosixPath("DISTRIBUTION-MANIFEST.json")
OPENCODE_VERSION = "1.18.20"
CPLT_RELEASE = "2026.08.17-062831-1008a92"
CPLT_TARGET_COMMIT = "1008a92188cc39fb17e0c9afc098f68050aff19a"
CPLT_RELEASE_ID = 371561671
CPLT_CHECKSUMS_ASSET_ID = 517725071
CPLT_CHECKSUMS_SHA256 = (
    "ec1f96427a90230afc1df685c237750b1f4d98c5ce5abcb18ec097c8e706b3fd"
)
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
SHA512_DIGEST = re.compile(r"^[0-9a-f]{128}$")
FILE_MODE = re.compile(r"^0[0-7]{3}$")
ALLOWED_FILE_MODES = frozenset({0o644, 0o755})
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_JSON_DEPTH = 40
MAX_FILE_BYTES = 5_000_000
MAX_DISTRIBUTION_BYTES = 50_000_000
MAX_ARCHIVE_MEMBERS = 10_000
REQUIRED_PROFILES = frozenset(
    {"local", "cloud-open-weight", "hybrid", "local-only"}
)
OPENCODE_OVERLAY_SKILL_IDS = frozenset(
    {"grillmester-create-a-skill", "grillmester-doctor"}
)
BASE_PROFILE_ENVIRONMENT = {
    "OPENCODE_CONFIG_CONTENT": '{"autoupdate":false,"share":"disabled"}',
    "OPENCODE_DISABLE_AUTOUPDATE": "true",
    "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "true",
    "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT": "true",
    "OPENCODE_DISABLE_DEFAULT_PLUGINS": "true",
    "OPENCODE_DISABLE_EXTERNAL_SKILLS": "true",
    "OPENCODE_DISABLE_SHARE": "true",
    "OPENCODE_DISABLE_MODELS_FETCH": "true",
    "OPENCODE_DISABLE_LSP_DOWNLOAD": "true",
    "OPENCODE_DISABLE_PROJECT_CONFIG": "true",
    "OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER": "true",
    "OPENCODE_EXPERIMENTAL": "false",
    "OPENCODE_EXPERIMENTAL_CODE_MODE": "false",
    "OPENCODE_PURE": "true",
    "OPENCODE_DB": ":memory:",
}
LOCAL_ONLY_ENVIRONMENT = {
    **BASE_PROFILE_ENVIRONMENT,
    "OPENCODE_DISABLE_MODELS_FETCH": "true",
    "OPENCODE_DISABLE_LSP_DOWNLOAD": "true",
    "OPENCODE_AUTO_SHARE": "false",
    "OPENCODE_ENABLE_EXA": "false",
}
LOCAL_ONLY_ALLOWED_DOMAIN = "grillmester-local-only.invalid"
LOCAL_ONLY_BLOCKED_DOMAINS = frozenset(
    {
        "registry.npmjs.org",
        "registry.yarnpkg.com",
        "repo.maven.apache.org",
        "plugins.gradle.org",
        "crates.io",
        "static.crates.io",
        "pypi.org",
        "files.pythonhosted.org",
        "opencode.ai",
        "models.dev",
    }
)
OPENCODE_ARTIFACT_PACKAGES = {
    ("darwin", "arm64", "none", "default"): "opencode-darwin-arm64",
    ("darwin", "x86_64", "none", "default"): "opencode-darwin-x64",
    ("darwin", "x86_64", "none", "baseline"): "opencode-darwin-x64-baseline",
    ("linux", "arm64", "glibc", "default"): "opencode-linux-arm64",
    ("linux", "arm64", "musl", "default"): "opencode-linux-arm64-musl",
    ("linux", "x86_64", "glibc", "default"): "opencode-linux-x64",
    ("linux", "x86_64", "glibc", "baseline"): "opencode-linux-x64-baseline",
    ("linux", "x86_64", "musl", "default"): "opencode-linux-x64-musl",
    (
        "linux",
        "x86_64",
        "musl",
        "baseline",
    ): "opencode-linux-x64-baseline-musl",
}
CPLT_ARTIFACT_ASSETS = {
    ("darwin", "arm64"): ("cplt-aarch64-apple-darwin.tar.gz", 517725074),
    ("darwin", "x86_64"): ("cplt-x86_64-apple-darwin.tar.gz", 517725073),
    ("linux", "arm64"): ("cplt-aarch64-unknown-linux-gnu.tar.gz", 517725072),
    ("linux", "x86_64"): ("cplt-x86_64-unknown-linux-gnu.tar.gz", 517725077),
}


class BundleBuildError(RuntimeError):
    """Raised when source input cannot produce a trustworthy bundle."""


@dataclass(frozen=True)
class BundleFile:
    path: PurePosixPath
    content: bytes
    mode: int


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_relative_path(value: object, *, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise BundleBuildError(f"{label} must be a non-empty string")
    if "\\" in value or any(
        ord(character) < 32 or ord(character) == 127 for character in value
    ):
        raise BundleBuildError(f"{label} is not a safe portable path: {value!r}")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise BundleBuildError(f"{label} is not a normalized relative path: {value!r}")
    return path


def _portable_collision_key(path: PurePosixPath) -> str:
    return unicodedata.normalize("NFC", path.as_posix()).casefold()


def _require_ustar_path(path: PurePosixPath) -> None:
    """Reject names that would require non-deterministic archive extensions."""

    try:
        tarfile.TarInfo(path.as_posix()).tobuf(
            format=tarfile.USTAR_FORMAT, encoding="utf-8", errors="strict"
        )
    except (UnicodeEncodeError, ValueError) as exc:
        raise BundleBuildError(f"archive path is not portable USTAR: {path}") from exc


def _require_directory(path: Path, *, label: str) -> None:
    try:
        observed = path.lstat()
    except FileNotFoundError as exc:
        raise BundleBuildError(f"missing {label}: {path}") from exc
    except OSError as exc:
        raise BundleBuildError(f"could not inspect {label} {path}: {exc}") from exc
    if stat.S_ISLNK(observed.st_mode):
        raise BundleBuildError(f"refusing symlinked {label}: {path}")
    if not stat.S_ISDIR(observed.st_mode):
        raise BundleBuildError(f"{label} is not a directory: {path}")


def _read_regular(
    path: Path, *, label: str, max_bytes: int = MAX_FILE_BYTES
) -> tuple[bytes, int]:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as exc:
        raise BundleBuildError(f"missing {label}: {path}") from exc
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise BundleBuildError(f"refusing symlinked {label}: {path}") from exc
        raise BundleBuildError(f"could not open {label} {path}: {exc}") from exc
    try:
        observed = os.fstat(descriptor)
    except OSError as exc:
        os.close(descriptor)
        raise BundleBuildError(f"could not inspect {label} {path}: {exc}") from exc
    if not stat.S_ISREG(observed.st_mode):
        os.close(descriptor)
        raise BundleBuildError(f"{label} is not a regular file: {path}")
    if observed.st_size > max_bytes:
        os.close(descriptor)
        raise BundleBuildError(
            f"{label} exceeds the {max_bytes}-byte safety limit: {path}"
        )
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as source:
            content = source.read(max_bytes + 1)
            try:
                after_read = os.fstat(source.fileno())
            except OSError as exc:
                raise BundleBuildError(
                    f"could not inspect {label} after reading {path}: {exc}"
                ) from exc
            if len(content) > max_bytes:
                raise BundleBuildError(
                    f"{label} exceeds the {max_bytes}-byte safety limit: {path}"
                )
            stable_metadata = (
                "st_dev",
                "st_ino",
                "st_mode",
                "st_nlink",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
            )
            if len(content) != observed.st_size or any(
                getattr(observed, field) != getattr(after_read, field)
                for field in stable_metadata
            ):
                raise BundleBuildError(f"{label} changed while being read: {path}")
            return content, stat.S_IMODE(observed.st_mode)
    except OSError as exc:
        raise BundleBuildError(f"could not read {label} {path}: {exc}") from exc


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BundleBuildError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_nonstandard_json_constant(value: str) -> None:
    raise BundleBuildError(f"non-standard JSON constant is forbidden: {value}")


def _parse_json_object(content: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except UnicodeDecodeError as exc:
        raise BundleBuildError(f"{label} is not UTF-8") from exc
    except RecursionError as exc:
        raise BundleBuildError(f"{label} exceeds the JSON nesting limit") from exc
    except json.JSONDecodeError as exc:
        raise BundleBuildError(
            f"{label} is not valid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    if not isinstance(value, dict):
        raise BundleBuildError(f"{label} must contain a JSON object")
    pending: list[tuple[object, int]] = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > MAX_JSON_DEPTH:
            raise BundleBuildError(f"{label} exceeds the JSON nesting limit")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    return value


def _require_exact_fields(
    value: object, expected: set[str], *, label: str
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise BundleBuildError(
            f"{label} must contain exactly: {', '.join(sorted(expected))}"
        )
    return value


def _require_positive_integer(value: object, *, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise BundleBuildError(f"{label} must be a positive integer")
    return value


def _require_digest(
    value: object, pattern: re.Pattern[str], *, algorithm: str, label: str
) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise BundleBuildError(f"{label} must be a lowercase {algorithm} digest")
    return value


def _validate_executable_record(value: object, *, path: str, label: str) -> None:
    executable = _require_exact_fields(
        value, {"path", "size", "sha256"}, label=label
    )
    if executable["path"] != path:
        raise BundleBuildError(f"{label} must name {path!r}")
    _require_positive_integer(executable["size"], label=f"{label} size")
    _require_digest(
        executable["sha256"], DIGEST, algorithm="SHA-256", label=f"{label} sha256"
    )


def _validate_opencode_artifacts(value: object) -> None:
    opencode = _require_exact_fields(
        value, {"version", "registry", "artifacts"}, label="OpenCode artifact lock"
    )
    if opencode["version"] != OPENCODE_VERSION:
        raise BundleBuildError(
            f"client artifact lock must pin OpenCode {OPENCODE_VERSION}"
        )
    if opencode["registry"] != "https://registry.npmjs.org":
        raise BundleBuildError("OpenCode artifact registry must be the npm registry")
    artifacts = opencode["artifacts"]
    if not isinstance(artifacts, list):
        raise BundleBuildError("OpenCode artifact records must be an array")

    observed: dict[tuple[str, str, str, str], str] = {}
    for index, raw_artifact in enumerate(artifacts):
        label = f"OpenCode artifact record {index}"
        artifact = _require_exact_fields(
            raw_artifact,
            {
                "platform",
                "architecture",
                "libc",
                "variant",
                "package",
                "url",
                "archive",
                "executable",
            },
            label=label,
        )
        key = (
            artifact["platform"],
            artifact["architecture"],
            artifact["libc"],
            artifact["variant"],
        )
        if not all(isinstance(part, str) for part in key):
            raise BundleBuildError(f"{label} platform selector must contain strings")
        package = OPENCODE_ARTIFACT_PACKAGES.get(key)
        if package is None or artifact["package"] != package:
            raise BundleBuildError(f"{label} has an unsupported platform package")
        if key in observed:
            raise BundleBuildError(f"duplicate OpenCode artifact platform selector: {key}")
        observed[key] = package
        expected_url = (
            f"https://registry.npmjs.org/{package}/-/{package}-{OPENCODE_VERSION}.tgz"
        )
        if artifact["url"] != expected_url:
            raise BundleBuildError(f"{label} has an invalid immutable tarball URL")

        archive_fields = {
            "size",
            "sha512",
            "integrity",
            "integrityEvidence",
            "roster",
        }
        if key[0] == "darwin" and key[3] == "default":
            archive_fields.add("sha256")
        archive = _require_exact_fields(
            artifact["archive"], archive_fields, label=f"{label} archive"
        )
        _require_positive_integer(archive["size"], label=f"{label} archive size")
        if "sha256" in archive:
            _require_digest(
                archive["sha256"],
                DIGEST,
                algorithm="SHA-256",
                label=f"{label} archive sha256",
            )
        sha512 = _require_digest(
            archive["sha512"],
            SHA512_DIGEST,
            algorithm="SHA-512",
            label=f"{label} archive sha512",
        )
        integrity = archive["integrity"]
        if not isinstance(integrity, str) or not integrity.startswith("sha512-"):
            raise BundleBuildError(f"{label} archive needs npm SHA-512 integrity")
        try:
            integrity_digest = base64.b64decode(
                integrity.removeprefix("sha512-"), validate=True
            ).hex()
        except (binascii.Error, ValueError) as exc:
            raise BundleBuildError(
                f"{label} archive has invalid npm SHA-512 integrity"
            ) from exc
        if integrity_digest != sha512:
            raise BundleBuildError(
                f"{label} archive integrity does not match its SHA-512 digest"
            )
        evidence = _require_exact_fields(
            archive["integrityEvidence"],
            {"type", "metadataUrl"},
            label=f"{label} integrity evidence",
        )
        if evidence != {
            "type": "npm-registry-dist-integrity",
            "metadataUrl": f"https://registry.npmjs.org/{package}/{OPENCODE_VERSION}",
        }:
            raise BundleBuildError(f"{label} has invalid registry integrity evidence")
        if archive["roster"] != ["package/package.json", "package/bin/opencode"]:
            raise BundleBuildError(f"{label} archive roster must be exact")
        _validate_executable_record(
            artifact["executable"], path="package/bin/opencode", label=f"{label} executable"
        )

    if observed != OPENCODE_ARTIFACT_PACKAGES:
        raise BundleBuildError(
            "client artifact lock must cover the exact supported OpenCode packages"
        )


def _validate_cplt_artifacts(value: object) -> None:
    cplt = _require_exact_fields(
        value,
        {
            "release",
            "targetCommit",
            "releaseUrl",
            "releaseApiUrl",
            "upstreamReleaseImmutable",
            "checksumManifest",
            "artifacts",
        },
        label="cplt artifact lock",
    )
    expected_release_url = f"https://github.com/navikt/cplt/releases/tag/{CPLT_RELEASE}"
    expected_api_url = (
        f"https://api.github.com/repos/navikt/cplt/releases/{CPLT_RELEASE_ID}"
    )
    if (
        cplt["release"] != CPLT_RELEASE
        or cplt["targetCommit"] != CPLT_TARGET_COMMIT
        or cplt["releaseUrl"] != expected_release_url
        or cplt["releaseApiUrl"] != expected_api_url
        or cplt["upstreamReleaseImmutable"] is not False
    ):
        raise BundleBuildError("cplt artifact lock has an invalid release identity")

    checksum = _require_exact_fields(
        cplt["checksumManifest"],
        {"asset", "url", "assetApiUrl", "size", "sha256", "content"},
        label="cplt checksum manifest",
    )
    expected_download_root = (
        f"https://github.com/navikt/cplt/releases/download/{CPLT_RELEASE}"
    )
    checksum_identity = {key: value for key, value in checksum.items() if key != "content"}
    if checksum_identity != {
        "asset": "SHA256SUMS",
        "url": f"{expected_download_root}/SHA256SUMS",
        "assetApiUrl": (
            "https://api.github.com/repos/navikt/cplt/releases/assets/"
            f"{CPLT_CHECKSUMS_ASSET_ID}"
        ),
        "size": 404,
        "sha256": CPLT_CHECKSUMS_SHA256,
    }:
        raise BundleBuildError("cplt checksum manifest identity is invalid")
    checksum_content = checksum["content"]
    if not isinstance(checksum_content, str):
        raise BundleBuildError("cplt checksum manifest content must be text")
    checksum_bytes = checksum_content.encode("utf-8")
    if (
        len(checksum_bytes) != checksum["size"]
        or _sha256(checksum_bytes) != checksum["sha256"]
    ):
        raise BundleBuildError(
            "cplt checksum manifest content does not match its size and SHA-256"
        )
    if not checksum_content.endswith("\n"):
        raise BundleBuildError("cplt checksum manifest must end with one newline")
    checksum_entries: dict[str, str] = {}
    for line in checksum_content[:-1].split("\n"):
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+)", line)
        if match is None or match.group(2) in checksum_entries:
            raise BundleBuildError("cplt checksum manifest has an invalid or duplicate row")
        checksum_entries[match.group(2)] = match.group(1)

    artifacts = cplt["artifacts"]
    if not isinstance(artifacts, list):
        raise BundleBuildError("cplt artifact records must be an array")
    observed: dict[tuple[str, str], str] = {}
    observed_archive_digests: dict[str, str] = {}
    for index, raw_artifact in enumerate(artifacts):
        label = f"cplt artifact record {index}"
        artifact = _require_exact_fields(
            raw_artifact,
            {
                "platform",
                "architecture",
                "libc",
                "variant",
                "asset",
                "url",
                "archive",
                "executable",
            },
            label=label,
        )
        key = (artifact["platform"], artifact["architecture"])
        if not all(isinstance(part, str) for part in key):
            raise BundleBuildError(f"{label} platform selector must contain strings")
        expected = CPLT_ARTIFACT_ASSETS.get(key)
        if expected is None or artifact["asset"] != expected[0]:
            raise BundleBuildError(f"{label} has an unsupported platform asset")
        if key in observed:
            raise BundleBuildError(f"duplicate cplt artifact platform selector: {key}")
        asset, asset_id = expected
        observed[key] = asset
        expected_libc = "none" if artifact["platform"] == "darwin" else "glibc"
        if artifact["libc"] != expected_libc or artifact["variant"] != "default":
            raise BundleBuildError(f"{label} has an invalid runtime variant")
        if artifact["url"] != f"{expected_download_root}/{asset}":
            raise BundleBuildError(f"{label} has an invalid immutable asset URL")

        archive = _require_exact_fields(
            artifact["archive"],
            {"size", "sha256", "digestEvidence", "roster"},
            label=f"{label} archive",
        )
        _require_positive_integer(archive["size"], label=f"{label} archive size")
        archive_digest = _require_digest(
            archive["sha256"],
            DIGEST,
            algorithm="SHA-256",
            label=f"{label} archive sha256",
        )
        observed_archive_digests[asset] = archive_digest
        evidence = _require_exact_fields(
            archive["digestEvidence"],
            {"type", "assetApiUrl", "reportedDigest"},
            label=f"{label} digest evidence",
        )
        if evidence != {
            "type": "github-release-api-asset-digest",
            "assetApiUrl": (
                "https://api.github.com/repos/navikt/cplt/releases/assets/"
                f"{asset_id}"
            ),
            "reportedDigest": f"sha256:{archive_digest}",
        }:
            raise BundleBuildError(f"{label} has invalid GitHub asset digest evidence")
        if archive["roster"] != ["cplt"]:
            raise BundleBuildError(f"{label} archive roster must be exactly ['cplt']")
        _validate_executable_record(
            artifact["executable"], path="cplt", label=f"{label} executable"
        )

    if observed != {
        selector: asset for selector, (asset, _) in CPLT_ARTIFACT_ASSETS.items()
    }:
        raise BundleBuildError(
            "client artifact lock must cover the exact supported cplt assets"
        )
    if checksum_entries != observed_archive_digests:
        raise BundleBuildError(
            "cplt SHA256SUMS rows must bind the exact supported archive digests"
        )


def _distribution_support_files(source_root: Path) -> list[BundleFile]:
    artifact_content, artifact_mode = _read_regular(
        source_root.joinpath(*CLIENT_ARTIFACTS_PATH.parts),
        label="client artifact lock",
        max_bytes=MAX_JSON_BYTES,
    )
    if artifact_mode != 0o644:
        raise BundleBuildError(
            "client artifact lock mode must be 0644; "
            f"observed {artifact_mode:04o}"
        )
    artifact_lock = _parse_json_object(
        artifact_content, label="client artifact lock"
    )
    if set(artifact_lock) != {"schemaVersion", "opencode", "cplt"}:
        raise BundleBuildError("client artifact lock has unexpected or missing fields")
    if type(artifact_lock["schemaVersion"]) is not int or artifact_lock[
        "schemaVersion"
    ] != 1:
        raise BundleBuildError("client artifact lock schemaVersion must be 1")
    _validate_opencode_artifacts(artifact_lock["opencode"])
    _validate_cplt_artifacts(artifact_lock["cplt"])

    content_lock_content, content_lock_mode = _read_regular(
        source_root.joinpath(*CONTENT_LOCK_PATH.parts),
        label="content lock",
        max_bytes=MAX_JSON_BYTES,
    )
    if content_lock_mode != 0o644:
        raise BundleBuildError(
            f"content lock mode must be 0644; observed {content_lock_mode:04o}"
        )
    content_lock = _parse_json_object(content_lock_content, label="content lock")
    if (
        set(content_lock) != {"schemaVersion", "sources", "agents", "skills"}
        or type(content_lock.get("schemaVersion")) is not int
        or content_lock["schemaVersion"] != 1
        or not isinstance(content_lock.get("sources"), dict)
        or not isinstance(content_lock.get("agents"), dict)
        or len(content_lock["agents"]) != 7
        or not isinstance(content_lock.get("skills"), dict)
        or len(content_lock["skills"]) != 42
    ):
        raise BundleBuildError("content lock must be the complete 7-agent/42-skill BOM")

    result = [
        BundleFile(CLIENT_ARTIFACTS_PATH, artifact_content, 0o644),
        BundleFile(CONTENT_LOCK_PATH, content_lock_content, 0o644),
    ]
    for source_path, distribution_path, label in (
        (LICENSE_PATH, LICENSE_PATH, "license"),
        (PROVENANCE_PATH, PROVENANCE_PATH, "provenance record"),
        (
            THIRD_PARTY_NOTICES_SOURCE,
            THIRD_PARTY_NOTICES_PATH,
            "third-party notices",
        ),
    ):
        content, mode = _read_regular(
            source_root.joinpath(*source_path.parts), label=label
        )
        if mode != 0o644:
            raise BundleBuildError(
                f"{label} mode must be 0644; observed {mode:04o}"
            )
        if not content.strip():
            raise BundleBuildError(f"{label} must not be empty")
        result.append(BundleFile(distribution_path, content, 0o644))
    return result


def _target_inventory(root: Path) -> set[PurePosixPath]:
    inventory: set[PurePosixPath] = set()
    portable_nodes: dict[str, PurePosixPath] = {}
    node_count = 1

    def walk_error(error: OSError) -> None:
        raise BundleBuildError(f"could not inventory OpenCode target {root}: {error}")

    for current, directories, files in os.walk(
        root, followlinks=False, onerror=walk_error
    ):
        node_count += len(directories) + len(files)
        if node_count > MAX_ARCHIVE_MEMBERS:
            raise BundleBuildError(
                f"OpenCode target exceeds the {MAX_ARCHIVE_MEMBERS}-member safety limit"
            )
        current_path = Path(current)
        directories.sort()
        files.sort()
        for name in directories:
            child = current_path / name
            try:
                observed = child.lstat()
            except OSError as exc:
                raise BundleBuildError(
                    f"could not inspect target directory {child}: {exc}"
                ) from exc
            if stat.S_ISLNK(observed.st_mode):
                raise BundleBuildError(f"target contains a symlinked directory: {child}")
            if not stat.S_ISDIR(observed.st_mode):
                raise BundleBuildError(f"target contains a non-directory node: {child}")
            relative = _safe_relative_path(
                child.relative_to(root).as_posix(), label="target inventory path"
            )
            collision_key = _portable_collision_key(relative)
            previous = portable_nodes.get(collision_key)
            if previous is not None and previous != relative:
                raise BundleBuildError(
                    f"target contains a portable path collision: {previous}, {relative}"
                )
            portable_nodes[collision_key] = relative
        for name in files:
            child = current_path / name
            try:
                observed = child.lstat()
            except OSError as exc:
                raise BundleBuildError(f"could not inspect target file {child}: {exc}") from exc
            if stat.S_ISLNK(observed.st_mode):
                raise BundleBuildError(f"target contains a symlink: {child}")
            if not stat.S_ISREG(observed.st_mode):
                raise BundleBuildError(f"target contains a non-regular file: {child}")
            relative = _safe_relative_path(
                child.relative_to(root).as_posix(), label="target inventory path"
            )
            collision_key = _portable_collision_key(relative)
            previous = portable_nodes.get(collision_key)
            if previous is not None and previous != relative:
                raise BundleBuildError(
                    f"target contains a portable path collision: {previous}, {relative}"
                )
            portable_nodes[collision_key] = relative
            if relative != PurePosixPath("manifest.json"):
                inventory.add(relative)
    return inventory


def _target_files(
    source_root: Path,
    *,
    expected_agents: frozenset[str],
    expected_skills: frozenset[str],
) -> tuple[list[BundleFile], bytes]:
    _require_directory(source_root / "targets", label="targets directory")
    target = source_root.joinpath(*TARGET_DIRECTORY.parts)
    _require_directory(target, label="OpenCode target directory")
    manifest_bytes, manifest_mode = _read_regular(
        target / "manifest.json",
        label="OpenCode target manifest",
        max_bytes=MAX_JSON_BYTES,
    )
    if manifest_mode != 0o644:
        raise BundleBuildError(
            "OpenCode target manifest mode must be 0644; "
            f"observed {manifest_mode:04o}"
        )
    manifest = _parse_json_object(manifest_bytes, label="OpenCode target manifest")
    if type(manifest.get("schemaVersion")) is not int or manifest["schemaVersion"] != 1:
        raise BundleBuildError("OpenCode target manifest schemaVersion must be 1")
    if manifest.get("target") != TARGET_NAME:
        raise BundleBuildError(f"OpenCode target manifest must name {TARGET_NAME!r}")
    raw_files = manifest.get("files")
    if not isinstance(raw_files, dict) or not raw_files:
        raise BundleBuildError("OpenCode target manifest files must be a non-empty object")
    if len(raw_files) + 2 > MAX_ARCHIVE_MEMBERS:
        raise BundleBuildError(
            "OpenCode target manifest exceeds the "
            f"{MAX_ARCHIVE_MEMBERS}-member safety limit"
        )

    declared: dict[PurePosixPath, tuple[str, int]] = {}
    portable_paths: dict[str, PurePosixPath] = {}
    for raw_path, raw_entry in raw_files.items():
        relative = _safe_relative_path(raw_path, label="target manifest path")
        if relative == PurePosixPath("manifest.json"):
            raise BundleBuildError("target manifest must not describe itself")
        if relative in declared:
            raise BundleBuildError(f"duplicate target manifest path: {relative}")
        collision_key = _portable_collision_key(relative)
        previous = portable_paths.get(collision_key)
        if previous is not None:
            raise BundleBuildError(
                f"portable target manifest path collision: {previous}, {relative}"
            )
        portable_paths[collision_key] = relative
        if not isinstance(raw_entry, dict) or set(raw_entry) != {"sha256", "mode"}:
            raise BundleBuildError(
                f"target manifest entry for {relative} must contain only sha256 and mode"
            )
        digest = raw_entry.get("sha256")
        raw_mode = raw_entry.get("mode")
        if not isinstance(digest, str) or DIGEST.fullmatch(digest) is None:
            raise BundleBuildError(f"invalid sha256 for target manifest entry {relative}")
        if not isinstance(raw_mode, str) or FILE_MODE.fullmatch(raw_mode) is None:
            raise BundleBuildError(f"invalid mode for target manifest entry {relative}")
        mode = int(raw_mode, 8)
        if mode not in ALLOWED_FILE_MODES:
            raise BundleBuildError(
                f"unsupported mode for target manifest entry {relative}: {raw_mode}"
            )
        declared[relative] = (digest, mode)

    expected_agent_paths = {
        PurePosixPath("agents") / f"{agent_id}.md"
        for agent_id in expected_agents
    }
    observed_agent_paths = {
        path for path in declared if path.parts[:1] == ("agents",)
    }
    if observed_agent_paths != expected_agent_paths:
        raise BundleBuildError(
            "OpenCode target agent roster differs from policy/content-lock.json"
        )
    expected_skill_paths = {
        PurePosixPath("skills") / skill_id / "SKILL.md"
        for skill_id in expected_skills
    }
    observed_skill_paths = {
        path
        for path in declared
        if len(path.parts) == 3
        and path.parts[0] == "skills"
        and path.name == "SKILL.md"
    }
    observed_skill_ids = {
        path.parts[1]
        for path in declared
        if len(path.parts) >= 2 and path.parts[0] == "skills"
    }
    if observed_skill_paths != expected_skill_paths or observed_skill_ids != expected_skills:
        raise BundleBuildError(
            "OpenCode target skill roster differs from policy/content-lock.json"
        )
    expected_command_paths = {
        PurePosixPath("commands") / f"{skill_id}.md"
        for skill_id in expected_skills
    }
    observed_command_paths = {
        path for path in declared if path.parts[:1] == ("commands",)
    }
    if observed_command_paths != expected_command_paths:
        raise BundleBuildError(
            "OpenCode target command roster differs from policy/content-lock.json"
        )
    expected_counts = {
        "agents": 7,
        "primaryAgents": 4,
        "subagents": 3,
        "skills": 42,
        "commands": 42,
    }
    if manifest.get("counts") != expected_counts:
        raise BundleBuildError("OpenCode target manifest has the wrong 7/42/42 counts")
    capabilities = manifest.get("skillCapabilities")
    expected_capabilities = {
        skill_id: (
            "overlay" if skill_id in OPENCODE_OVERLAY_SKILL_IDS else "native"
        )
        for skill_id in expected_skills
    }
    if capabilities != expected_capabilities:
        raise BundleBuildError(
            "OpenCode target skillCapabilities differ from the reviewed classification"
        )

    actual = _target_inventory(target)
    expected = set(declared)
    missing = sorted(expected - actual, key=str)
    extras = sorted(actual - expected, key=str)
    if missing:
        raise BundleBuildError(
            "OpenCode target is missing manifest files: " + ", ".join(map(str, missing))
        )
    if extras:
        raise BundleBuildError(
            "OpenCode target contains unmanifested files: " + ", ".join(map(str, extras))
        )

    result: list[BundleFile] = []
    for relative in sorted(declared, key=str):
        expected_digest, expected_mode = declared[relative]
        content, observed_mode = _read_regular(
            target.joinpath(*relative.parts), label=f"OpenCode target file {relative}"
        )
        observed_digest = _sha256(content)
        if observed_digest != expected_digest:
            raise BundleBuildError(
                f"checksum mismatch for OpenCode target file {relative}: "
                f"expected {expected_digest}, observed {observed_digest}"
            )
        if observed_mode != expected_mode:
            raise BundleBuildError(
                f"mode mismatch for OpenCode target file {relative}: "
                f"expected {expected_mode:04o}, observed {observed_mode:04o}"
            )
        result.append(
            BundleFile(TARGET_DIRECTORY / relative, content, expected_mode)
        )
    result.append(
        BundleFile(TARGET_DIRECTORY / "manifest.json", manifest_bytes, 0o644)
    )
    return result, manifest_bytes


def _validate_profile(profile: dict[str, Any], *, profile_id: str) -> None:
    common_fields = {
        "schemaVersion",
        "id",
        "description",
        "cpltPolicy",
        "cpltRelease",
        "localPorts",
        "providerDomains",
        "environment",
    }
    is_local_only = profile_id == "local-only"
    expected_fields = (
        common_fields | {"allowedDomain", "blockedDomains"}
        if is_local_only
        else common_fields
    )
    if set(profile) != expected_fields:
        raise BundleBuildError(
            f"OpenCode profile {profile_id} has unexpected or missing fields"
        )
    if (
        type(profile.get("schemaVersion")) is not int
        or profile["schemaVersion"] != 1
        or profile.get("id") != profile_id
    ):
        raise BundleBuildError(
            f"OpenCode profile {profile_id} has an invalid schema or id"
        )
    if not isinstance(profile.get("description"), str) or not profile[
        "description"
    ].strip():
        raise BundleBuildError(f"OpenCode profile {profile_id} needs a description")
    if profile.get("cpltRelease") != CPLT_RELEASE:
        raise BundleBuildError(
            f"OpenCode profile {profile_id} must pin cplt {CPLT_RELEASE}"
        )

    expected_shape = {
        "local": ("strict", "required", "forbidden"),
        "cloud-open-weight": ("strict", "forbidden", "required"),
        "hybrid": ("strict", "required", "required"),
        "local-only": ("local-only", "required", "forbidden"),
    }[profile_id]
    observed_shape = (
        profile.get("cpltPolicy"),
        profile.get("localPorts"),
        profile.get("providerDomains"),
    )
    if observed_shape != expected_shape:
        raise BundleBuildError(
            f"OpenCode profile {profile_id} has an invalid runtime policy shape"
        )
    expected_environment = (
        LOCAL_ONLY_ENVIRONMENT if is_local_only else BASE_PROFILE_ENVIRONMENT
    )
    if profile.get("environment") != expected_environment:
        raise BundleBuildError(
            f"OpenCode profile {profile_id} has an invalid immutable environment overlay"
        )
    if is_local_only:
        if profile.get("allowedDomain") != LOCAL_ONLY_ALLOWED_DOMAIN:
            raise BundleBuildError(
                "local-only profile has an invalid fail-closed allowed domain"
            )
        blocked = profile.get("blockedDomains")
        if (
            not isinstance(blocked, list)
            or len(blocked) != len(LOCAL_ONLY_BLOCKED_DOMAINS)
            or any(not isinstance(domain, str) for domain in blocked)
            or set(blocked) != LOCAL_ONLY_BLOCKED_DOMAINS
        ):
            raise BundleBuildError(
                "local-only profile must block the exact audited cplt domain set"
            )


def _profile_files(source_root: Path) -> list[BundleFile]:
    _require_directory(source_root / "profiles", label="profiles directory")
    profiles = source_root.joinpath(*PROFILE_DIRECTORY.parts)
    _require_directory(profiles, label="OpenCode profiles directory")
    result: list[BundleFile] = []
    try:
        children = sorted(profiles.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise BundleBuildError(f"could not list OpenCode profiles {profiles}: {exc}") from exc
    validated_children: list[tuple[Path, PurePosixPath]] = []
    for child in children:
        relative = _safe_relative_path(child.name, label="OpenCode profile path")
        if len(relative.parts) != 1 or child.suffix != ".json":
            raise BundleBuildError(f"unexpected OpenCode profile entry: {child}")
        validated_children.append((child, relative))
    observed_profile_ids = {
        child.stem
        for child, _ in validated_children
        if child.suffix == ".json" and not child.name.startswith(".")
    }
    if (
        observed_profile_ids != REQUIRED_PROFILES
        or len(children) != len(REQUIRED_PROFILES)
    ):
        raise BundleBuildError(
            "OpenCode profiles must be exactly: "
            + ", ".join(sorted(REQUIRED_PROFILES))
        )
    for child, relative in validated_children:
        content, mode = _read_regular(
            child,
            label=f"OpenCode profile {child.name}",
            max_bytes=MAX_JSON_BYTES,
        )
        if mode != 0o644:
            raise BundleBuildError(
                f"OpenCode profile {child.name} mode must be 0644; observed {mode:04o}"
            )
        profile = _parse_json_object(content, label=f"OpenCode profile {child.name}")
        _validate_profile(profile, profile_id=child.stem)
        result.append(BundleFile(PROFILE_DIRECTORY / relative, content, 0o644))
    return result


def _portable_tree_files(root: Path, *, destination: PurePosixPath, label: str) -> list[BundleFile]:
    """Read one symlink-free portable tree without following directory aliases."""

    _require_directory(root, label=label)
    result: list[BundleFile] = []
    stack: list[tuple[Path, PurePosixPath]] = [(root, PurePosixPath())]
    portable_paths: dict[str, PurePosixPath] = {}
    while stack:
        directory, relative_directory = stack.pop()
        try:
            children = sorted(directory.iterdir(), key=lambda path: path.name, reverse=True)
        except OSError as exc:
            raise BundleBuildError(f"could not list {label} {directory}: {exc}") from exc
        for child in children:
            relative_name = _safe_relative_path(child.name, label=f"{label} path")
            relative = relative_directory / relative_name
            collision_key = _portable_collision_key(relative)
            previous = portable_paths.get(collision_key)
            if previous is not None and previous != relative:
                raise BundleBuildError(
                    f"portable {label} path collision: {previous}, {relative}"
                )
            portable_paths[collision_key] = relative
            try:
                observed = child.lstat()
            except OSError as exc:
                raise BundleBuildError(f"could not inspect {label} entry {child}: {exc}") from exc
            if stat.S_ISLNK(observed.st_mode):
                raise BundleBuildError(f"refusing symlinked {label} entry: {child}")
            if stat.S_ISDIR(observed.st_mode):
                stack.append((child, relative))
                continue
            if not stat.S_ISREG(observed.st_mode):
                raise BundleBuildError(f"{label} entry is not a regular file: {child}")
            content, mode = _read_regular(child, label=f"{label} file {relative}")
            if mode not in ALLOWED_FILE_MODES:
                raise BundleBuildError(
                    f"{label} file {relative} has unsupported mode {mode:04o}"
                )
            result.append(BundleFile(destination / relative, content, mode))
    result.sort(key=lambda entry: entry.path.as_posix())
    return result


def _plugin_files(
    source_root: Path,
    *,
    expected_agents: frozenset[str],
    expected_skills: frozenset[str],
) -> list[BundleFile]:
    files = _portable_tree_files(
        source_root.joinpath(*PLUGIN_DIRECTORY.parts),
        destination=PLUGIN_DIRECTORY,
        label="Copilot plugin",
    )
    relative_files = {
        entry.path.relative_to(PLUGIN_DIRECTORY): entry for entry in files
    }
    manifest_entry = relative_files.get(PurePosixPath("plugin.json"))
    if manifest_entry is None:
        raise BundleBuildError("Copilot plugin has no plugin.json")
    manifest = _parse_json_object(
        manifest_entry.content, label="Copilot plugin manifest"
    )
    if manifest.get("name") != "grillmester":
        raise BundleBuildError("Copilot plugin manifest must name grillmester")
    if not isinstance(manifest.get("version"), str) or not manifest["version"].strip():
        raise BundleBuildError("Copilot plugin manifest needs a version")
    observed_agents = {
        path.name.removesuffix(".agent.md")
        for path in relative_files
        if len(path.parts) == 2
        and path.parts[0] == "agents"
        and path.name.endswith(".agent.md")
    }
    observed_agent_entries = {
        path for path in relative_files if path.parts[:1] == ("agents",)
    }
    expected_agent_entries = {
        PurePosixPath("agents") / f"{agent_id}.agent.md"
        for agent_id in expected_agents
    }
    if observed_agents != expected_agents or observed_agent_entries != expected_agent_entries:
        raise BundleBuildError(
            "Copilot plugin agent roster differs from policy/content-lock.json"
        )
    observed_skill_ids = {
        path.parts[1]
        for path in relative_files
        if len(path.parts) >= 2 and path.parts[0] == "skills"
    }
    observed_skill_manifests = {
        path
        for path in relative_files
        if len(path.parts) == 3
        and path.parts[0] == "skills"
        and path.name == "SKILL.md"
    }
    expected_skill_manifests = {
        PurePosixPath("skills") / skill_id / "SKILL.md"
        for skill_id in expected_skills
    }
    if (
        observed_skill_ids != expected_skills
        or observed_skill_manifests != expected_skill_manifests
    ):
        raise BundleBuildError(
            "Copilot plugin skill roster differs from policy/content-lock.json"
        )
    return files


def _launcher_file(source_root: Path) -> BundleFile:
    content, mode = _read_regular(
        source_root.joinpath(*LAUNCHER_PATH.parts), label="Grillmester launcher"
    )
    if mode != 0o644:
        raise BundleBuildError(
            f"Grillmester launcher source mode must be 0644; observed {mode:04o}"
        )
    try:
        tree = ast.parse(content.decode("utf-8"), filename=LAUNCHER_PATH.as_posix())
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise BundleBuildError(f"Grillmester launcher is not valid UTF-8 Python: {exc}") from exc
    observed: dict[str, list[object]] = {
        "SUPPORTED_OPENCODE_VERSION": [],
        "SUPPORTED_CPLT_RELEASE": [],
    }
    for statement in tree.body:
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id in observed
        ):
            try:
                observed[statement.targets[0].id].append(ast.literal_eval(statement.value))
            except (ValueError, TypeError) as exc:
                raise BundleBuildError(
                    f"Grillmester launcher {statement.targets[0].id} must be a literal"
                ) from exc
    expected = {
        "SUPPORTED_OPENCODE_VERSION": OPENCODE_VERSION,
        "SUPPORTED_CPLT_RELEASE": CPLT_RELEASE,
    }
    for name, expected_value in expected.items():
        if observed[name] != [expected_value]:
            raise BundleBuildError(
                f"Grillmester launcher must pin {name}={expected_value!r}"
            )
    return BundleFile(LAUNCHER_PATH, content, 0o755)


def _artifact_binary_digest_maps(
    artifact_lock: dict[str, Any],
) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str, str], str]]:
    cplt_digests = {
        (record["platform"], record["architecture"]): record["executable"][
            "sha256"
        ]
        for record in artifact_lock["cplt"]["artifacts"]
    }
    opencode_digest_sets: dict[tuple[str, str, str], set[str]] = {}
    for record in artifact_lock["opencode"]["artifacts"]:
        platform = record["platform"]
        architecture = record["architecture"]
        binary_variant = "default" if platform == "darwin" else record["libc"]
        opencode_digest_sets.setdefault(
            (platform, architecture, binary_variant), set()
        ).add(record["executable"]["sha256"])
    divergent = {
        selector: digests
        for selector, digests in opencode_digest_sets.items()
        if len(digests) != 1
    }
    if divergent:  # pragma: no cover - rejected by the committed lock contract
        raise BundleBuildError(
            "OpenCode baseline/default artifact variants have divergent executable bytes"
        )
    return cplt_digests, {
        selector: next(iter(digests))
        for selector, digests in opencode_digest_sets.items()
    }


def _manager_architecture(platform: str, architecture: str) -> str:
    if platform == "linux" and architecture == "arm64":
        return "aarch64"
    return architecture


def _validate_manager_contract(
    content: bytes,
    *,
    composer_sha256: str,
    artifact_lock: dict[str, Any],
) -> None:
    try:
        source = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BundleBuildError("OpenCode lifecycle manager is not UTF-8") from exc
    try:
        tree = ast.parse(source, filename=MANAGER_PATH.as_posix())
    except SyntaxError as exc:
        raise BundleBuildError(f"OpenCode lifecycle manager is not valid Python: {exc}") from exc

    observed: dict[str, list[object]] = {
        "SUPPORTED_OPENCODE_VERSION": [],
        "SUPPORTED_CPLT_RELEASE": [],
        "PERMISSION_COMPOSER_SHA256": [],
        "PINNED_CPLT_BINARY_SHA256": [],
        "PINNED_OPENCODE_BINARY_SHA256": [],
    }
    for statement in tree.body:
        name: str | None = None
        value: ast.expr | None = None
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
        ):
            name = statement.targets[0].id
            value = statement.value
        elif isinstance(statement, ast.AnnAssign) and isinstance(
            statement.target, ast.Name
        ):
            name = statement.target.id
            value = statement.value
        if name in observed and value is not None:
            try:
                observed[name].append(ast.literal_eval(value))
            except (ValueError, TypeError) as exc:
                raise BundleBuildError(
                    f"OpenCode lifecycle manager {name} must be a literal"
                ) from exc

    expected = {
        "SUPPORTED_OPENCODE_VERSION": OPENCODE_VERSION,
        "SUPPORTED_CPLT_RELEASE": CPLT_RELEASE,
        "PERMISSION_COMPOSER_SHA256": composer_sha256,
    }
    for name, expected_value in expected.items():
        if observed[name] != [expected_value]:
            raise BundleBuildError(
                f"OpenCode lifecycle manager must pin {name}={expected_value!r}"
            )

    cplt_digests, opencode_digests = _artifact_binary_digest_maps(artifact_lock)
    expected_cplt = {
        (platform, _manager_architecture(platform, architecture)): digest
        for (platform, architecture), digest in cplt_digests.items()
    }
    expected_opencode = {
        (
            platform,
            _manager_architecture(platform, architecture),
            variant,
        ): digest
        for (platform, architecture, variant), digest in opencode_digests.items()
    }
    if observed["PINNED_CPLT_BINARY_SHA256"] != [expected_cplt]:
        raise BundleBuildError(
            "OpenCode lifecycle manager PINNED_CPLT_BINARY_SHA256 must match "
            "policy/client-artifacts.json"
        )
    if observed["PINNED_OPENCODE_BINARY_SHA256"] != [expected_opencode]:
        raise BundleBuildError(
            "OpenCode lifecycle manager PINNED_OPENCODE_BINARY_SHA256 must match "
            "policy/client-artifacts.json"
        )


def _validate_archive_path_collisions(files: list[BundleFile]) -> None:
    portable_nodes: dict[str, PurePosixPath] = {}
    for entry in files:
        current = ARCHIVE_ROOT / entry.path
        while current != PurePosixPath("."):
            key = _portable_collision_key(current)
            previous = portable_nodes.get(key)
            if previous is not None and previous != current:
                raise BundleBuildError(
                    f"portable archive path collision: {previous}, {current}"
                )
            portable_nodes[key] = current
            current = current.parent


def collect_bundle_files(source_root: Path, source_sha: str) -> list[BundleFile]:
    """Validate all source inputs and return the complete canonical file set."""

    if FULL_SHA.fullmatch(source_sha) is None:
        raise BundleBuildError("source SHA must be exactly 40 lowercase hex digits")
    source_root = source_root.expanduser().absolute()
    _require_directory(source_root, label="source root")
    _require_directory(source_root / "scripts", label="scripts directory")

    manager_content, _ = _read_regular(
        source_root.joinpath(*MANAGER_PATH.parts), label="OpenCode lifecycle manager"
    )
    composer_content, composer_mode = _read_regular(
        source_root.joinpath(*PERMISSION_COMPOSER_PATH.parts),
        label="OpenCode permission composer",
    )
    if composer_mode != 0o644:
        raise BundleBuildError(
            "OpenCode permission composer mode must be 0644; "
            f"observed {composer_mode:04o}"
        )
    try:
        ast.parse(
            composer_content.decode("utf-8"),
            filename=PERMISSION_COMPOSER_PATH.as_posix(),
        )
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise BundleBuildError(
            f"OpenCode permission composer is not valid UTF-8 Python: {exc}"
        ) from exc
    verifier_content, verifier_mode = _read_regular(
        source_root.joinpath(*ARTIFACT_VERIFIER_PATH.parts),
        label="client artifact verifier",
    )
    if verifier_mode != 0o644:
        raise BundleBuildError(
            "client artifact verifier mode must be 0644; "
            f"observed {verifier_mode:04o}"
        )
    try:
        ast.parse(
            verifier_content.decode("utf-8"),
            filename=ARTIFACT_VERIFIER_PATH.as_posix(),
        )
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise BundleBuildError(
            f"client artifact verifier is not valid UTF-8 Python: {exc}"
        ) from exc
    support_files = _distribution_support_files(source_root)
    artifact_lock_file = next(
        entry for entry in support_files if entry.path == CLIENT_ARTIFACTS_PATH
    )
    artifact_lock = _parse_json_object(
        artifact_lock_file.content, label="client artifact lock"
    )
    _validate_manager_contract(
        manager_content,
        composer_sha256=_sha256(composer_content),
        artifact_lock=artifact_lock,
    )
    content_lock_file = next(
        entry for entry in support_files if entry.path == CONTENT_LOCK_PATH
    )
    content_lock = _parse_json_object(
        content_lock_file.content, label="content lock"
    )
    expected_agents = frozenset(content_lock["agents"])
    expected_skills = frozenset(content_lock["skills"])
    if any(not isinstance(value, str) or not value for value in expected_agents):
        raise BundleBuildError("content lock contains an invalid agent ID")
    if any(not isinstance(value, str) or not value for value in expected_skills):
        raise BundleBuildError("content lock contains an invalid skill ID")
    target_files, target_manifest = _target_files(
        source_root,
        expected_agents=expected_agents,
        expected_skills=expected_skills,
    )
    files = [
        _launcher_file(source_root),
        BundleFile(MANAGER_PATH, manager_content, 0o755),
        BundleFile(PERMISSION_COMPOSER_PATH, composer_content, 0o644),
        BundleFile(ARTIFACT_VERIFIER_PATH, verifier_content, 0o755),
    ]
    files.extend(support_files)
    files.extend(_profile_files(source_root))
    files.extend(
        _plugin_files(
            source_root,
            expected_agents=expected_agents,
            expected_skills=expected_skills,
        )
    )
    files.extend(target_files)
    files.sort(key=lambda entry: entry.path.as_posix())
    aggregate_size = sum(len(entry.content) for entry in files)
    if aggregate_size > MAX_DISTRIBUTION_BYTES:
        raise BundleBuildError(
            f"bundle inputs exceed the {MAX_DISTRIBUTION_BYTES}-byte safety limit"
        )

    paths = [entry.path for entry in files]
    if len(paths) != len(set(paths)):  # pragma: no cover - fixed namespaces
        raise BundleBuildError("bundle inputs produce duplicate archive paths")
    file_manifest = {
        entry.path.as_posix(): {
            "sha256": _sha256(entry.content),
            "mode": f"{entry.mode:04o}",
        }
        for entry in files
    }
    distribution_manifest = {
        "schemaVersion": 1,
        "sourceSha": source_sha,
        "target": TARGET_NAME,
        "opencodeVersion": OPENCODE_VERSION,
        "cpltRelease": CPLT_RELEASE,
        "targetManifestSha256": _sha256(target_manifest),
        "files": file_manifest,
    }
    manifest_bytes = (
        json.dumps(distribution_manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if len(manifest_bytes) > MAX_JSON_BYTES:
        raise BundleBuildError(
            "distribution manifest exceeds the "
            f"{MAX_JSON_BYTES}-byte JSON safety limit"
        )
    if aggregate_size + len(manifest_bytes) > MAX_DISTRIBUTION_BYTES:
        raise BundleBuildError(
            "bundle plus distribution manifest exceeds the "
            f"{MAX_DISTRIBUTION_BYTES}-byte safety limit"
        )
    files.append(BundleFile(OUTER_MANIFEST, manifest_bytes, 0o644))
    files.sort(key=lambda entry: entry.path.as_posix())
    _validate_archive_path_collisions(files)
    for entry in files:
        _require_ustar_path(ARCHIVE_ROOT / entry.path)
    return files


def _tar_info(name: str, *, mode: int, directory: bool, size: int = 0) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name + ("/" if directory else ""))
    info.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
    info.mode = mode
    info.size = 0 if directory else size
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.devmajor = 0
    info.devminor = 0
    return info


def _write_archive(output: io.BufferedWriter, files: list[BundleFile]) -> None:
    members: dict[PurePosixPath, BundleFile | None] = {ARCHIVE_ROOT: None}
    for entry in files:
        archive_path = ARCHIVE_ROOT / entry.path
        parent = archive_path.parent
        while parent != PurePosixPath("."):
            members.setdefault(parent, None)
            parent = parent.parent
        members[archive_path] = entry
    if len(members) > MAX_ARCHIVE_MEMBERS:
        raise BundleBuildError(
            f"archive exceeds the {MAX_ARCHIVE_MEMBERS}-member safety limit"
        )

    with gzip.GzipFile(
        filename="", mode="wb", compresslevel=9, fileobj=output, mtime=0
    ) as compressed:
        with tarfile.open(
            fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT
        ) as archive:
            for path in sorted(members, key=lambda item: item.as_posix()):
                entry = members[path]
                if entry is None:
                    archive.addfile(
                        _tar_info(path.as_posix(), mode=0o755, directory=True)
                    )
                else:
                    archive.addfile(
                        _tar_info(
                            path.as_posix(),
                            mode=entry.mode,
                            directory=False,
                            size=len(entry.content),
                        ),
                        io.BytesIO(entry.content),
                    )


def _canonical_future_path(path: Path) -> Path:
    absolute = path.expanduser().absolute()
    missing: list[str] = []
    ancestor = absolute
    while not ancestor.exists() and not ancestor.is_symlink():
        missing.append(ancestor.name)
        parent = ancestor.parent
        if parent == ancestor:  # pragma: no cover - root always exists
            break
        ancestor = parent
    try:
        resolved = ancestor.resolve(strict=True)
    except OSError as exc:
        raise BundleBuildError(f"could not resolve output path {path}: {exc}") from exc
    for part in reversed(missing):
        resolved /= part
    return resolved


def _portable_absolute_path_key(path: Path) -> tuple[str, ...]:
    """Match path aliases on case-insensitive, Unicode-normalizing filesystems."""

    return tuple(
        unicodedata.normalize("NFC", part).casefold() for part in path.parts
    )


def _is_within(path: Path, parent: Path) -> bool:
    path_key = _portable_absolute_path_key(path)
    parent_key = _portable_absolute_path_key(parent)
    return (
        len(path_key) >= len(parent_key)
        and path_key[: len(parent_key)] == parent_key
    )


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise BundleBuildError(f"could not durably sync output directory {path}: {exc}") from exc


def build_bundle(source_root: Path, source_sha: str, output: Path) -> None:
    """Build one byte-reproducible tar.gz, replacing only the requested output."""

    raw_source_root = source_root.expanduser().absolute()
    _require_directory(raw_source_root, label="source root")
    try:
        source_root = raw_source_root.resolve(strict=True)
    except OSError as exc:
        raise BundleBuildError(f"could not resolve source root {raw_source_root}: {exc}") from exc
    files = collect_bundle_files(source_root, source_sha)
    output = output.expanduser().absolute()
    if output.is_symlink():
        raise BundleBuildError(f"refusing to replace symlinked output: {output}")
    output = _canonical_future_path(output)
    if _is_within(output, source_root):
        raise BundleBuildError("output must be outside the immutable source root")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output = _canonical_future_path(output)
        if _is_within(output, source_root):
            raise BundleBuildError("output must be outside the immutable source root")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                os.fchmod(stream.fileno(), 0o644)
                _write_archive(stream, files)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, output)
            _fsync_directory(output.parent)
        finally:
            temporary.unlink(missing_ok=True)
    except BundleBuildError:
        raise
    except OSError as exc:
        raise BundleBuildError(f"could not write bundle {output}: {exc}") from exc


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    options = parse_arguments(arguments)
    try:
        build_bundle(options.source_root, options.source_sha, options.output)
    except BundleBuildError as exc:
        print(f"OpenCode bundle build failed: {exc}", file=sys.stderr)
        return 2
    print(options.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
