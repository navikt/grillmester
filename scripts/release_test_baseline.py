#!/usr/bin/env python3
"""Select, download, and verify Grillmester's exact release-test clients.

This is the single executable contract for the client versions and native
artifacts exercised by release CI. It is deliberately not part of the runtime
bundle: installed launchers accept the wider compatible ranges recorded in
``STANDARD_SUPPORT`` and resolve user-installed clients from ``PATH``.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


CONTRACT: dict[str, Any] = {
    "schemaVersion": 1,
    "standardSupport": {
        "opencodeMinimum": "2.2.5",
        "copilotMinimum": "1.0.100",
        "cpltMinimum": "2026.11.02-225238-10a2882",
    },
    "releaseTest": {
        "opencodeVersion": "2.2.5",
        "copilotVersion": "1.0.100",
        "cpltRelease": "2026.11.02-225238-10a2882",
    },
    "artifacts": {
        "opencode:darwin:arm64": {
            "url": "https://registry.npmjs.org/@opencode/cli-darwin-arm64/-/cli-darwin-arm64-2.2.5.tgz",
            "archiveSize": 105814595,
            "archiveDigest": "sha512:53019bd8c209a8b4a1e307eb92fa8d880a211b559fe6df7a371ef5d7742f9ad0a7e4b1a29a65d83744dbd5c843d2631145d3ef9d482e7af291770334b71658d5",
            "roster": [
                "package",
                "package/bin",
                "package/package.json",
                "package/bin/opencode",
            ],
            "executablePath": "package/bin/opencode",
            "executableSize": 226703008,
            "executableSha256": "abe4d88594bffb12b364375b8a6732d2d1f7a977195ed1a35c5c76f8e89c9e0e",
        },
        "opencode:darwin:x86_64": {
            "url": "https://registry.npmjs.org/@opencode/cli-darwin-x64/-/cli-darwin-x64-2.2.5.tgz",
            "archiveSize": 111044366,
            "archiveDigest": "sha512:cfec2a2015e4e435705d57724091cec309e73a514ec742df025c773f3b9b26313fddaf78f0a3c1909aee179ce6eb2ca09491b33604778e2ee80ff07f1ce303fb",
            "roster": [
                "package",
                "package/bin",
                "package/package.json",
                "package/bin/opencode",
            ],
            "executablePath": "package/bin/opencode",
            "executableSize": 240617312,
            "executableSha256": "5e0cf9c94ee0fd4a4635807534e9ca4bf51ffe1c83260ada3510bf60e7333173",
        },
        "opencode:linux:x86_64": {
            "url": "https://registry.npmjs.org/@opencode/cli-linux-x64/-/cli-linux-x64-2.2.5.tgz",
            "archiveSize": 118637290,
            "archiveDigest": "sha512:0641c07d3a8db20feaa61c8736b9c7f831a43b166c1a36a63693390efc2812fcfb6403cdc3c9846cc5c64c20ce007fbffb8d04a9e89ee8a359059650c0f0a368",
            "roster": ["package/package.json", "package/bin/opencode"],
            "executablePath": "package/bin/opencode",
            "executableSize": 252713136,
            "executableSha256": "8d060e1d2fbb9bb44cf09ae6ed1f3f6a7cff070b5227e2f90970132b23a92050",
        },
        "copilot:darwin:arm64": {
            "url": "https://github.com/github/copilot-cli/releases/download/v1.0.100/copilot-darwin-arm64.tar.gz",
            "archiveSize": 114270894,
            "archiveDigest": "sha256:4af0815e798158641bdd8e76e622fee0975e24ef91c5f0daf9ada4d9e0eac5a0",
            "roster": ["copilot"],
            "executablePath": "copilot",
            "executableSize": 176496976,
            "executableSha256": "371be36eac9b322cf01898a05b10f63dab7843f58358732123c9371815ae6388",
        },
        "copilot:darwin:x86_64": {
            "url": "https://github.com/github/copilot-cli/releases/download/v1.0.100/copilot-darwin-x64.tar.gz",
            "archiveSize": 120513190,
            "archiveDigest": "sha256:dedf0a0b57ef845067d28195ac1ba9668269de45d521a72bb81f74a3f13a5a7b",
            "roster": ["copilot"],
            "executablePath": "copilot",
            "executableSize": 183691504,
            "executableSha256": "7febb1274d53b6b2b9d9aa76af02c9780c5fbf9973cd3874397e51e648ee136c",
        },
        "cplt:darwin:arm64": {
            "url": "https://github.com/navikt/cplt/releases/download/2026.11.02-225238-10a2882/cplt-aarch64-apple-darwin.tar.gz",
            "archiveSize": 3459234,
            "archiveDigest": "sha256:023a19657110fa382a447fef683c1b6966700b75bcccf94440f701a85671a607",
            "roster": ["cplt"],
            "executablePath": "cplt",
            "executableSize": 7028784,
            "executableSha256": "b975395752f8185c2bf4800d4c41eb17d55091c5c43908ff40836925009fb0a3",
        },
        "cplt:darwin:x86_64": {
            "url": "https://github.com/navikt/cplt/releases/download/2026.11.02-225238-10a2882/cplt-x86_64-apple-darwin.tar.gz",
            "archiveSize": 3772457,
            "archiveDigest": "sha256:e578f27ba9a6eb318606a50c60d55e5a022a867792647e6878f76d42e0096689",
            "roster": ["cplt"],
            "executablePath": "cplt",
            "executableSize": 8146536,
            "executableSha256": "8fefc0b45667978da9b6d2c52e95b048cec248718f98651577a0a3929efff515",
        },
        "cplt:linux:x86_64": {
            "url": "https://github.com/navikt/cplt/releases/download/2026.11.02-225238-10a2882/cplt-x86_64-unknown-linux-gnu.tar.gz",
            "archiveSize": 3960152,
            "archiveDigest": "sha256:65c4e2d39c1f49a7e0018002c8bb0bcfef08965aee85676759b591ee84fdbc46",
            "roster": ["cplt"],
            "executablePath": "cplt",
            "executableSize": 8823232,
            "executableSha256": "9d473289d1e74c8519ce47cadf986b3cbc97db4a09ec5383e3bd696d713fe59e",
        },
    },
}

MAX_ARCHIVE_MEMBERS = 8
COPY_CHUNK_BYTES = 1024 * 1024


class BaselineError(RuntimeError):
    """Raised when a release-test artifact differs from the reviewed baseline."""


def _validate_contract() -> None:
    expected_artifacts = {
        f"{client}:{platform}:{architecture}"
        for client, platforms in {
            "opencode": (("darwin", "arm64"), ("darwin", "x86_64"), ("linux", "x86_64")),
            "copilot": (("darwin", "arm64"), ("darwin", "x86_64")),
            "cplt": (("darwin", "arm64"), ("darwin", "x86_64"), ("linux", "x86_64")),
        }.items()
        for platform, architecture in platforms
    }
    if set(CONTRACT) != {"schemaVersion", "standardSupport", "releaseTest", "artifacts"}:
        raise BaselineError("release-test baseline contract fields differ")
    if CONTRACT["schemaVersion"] != 1:
        raise BaselineError("release-test baseline schemaVersion must be 1")
    standard = CONTRACT["standardSupport"]
    tested = CONTRACT["releaseTest"]
    if set(standard) != {"opencodeMinimum", "copilotMinimum", "cpltMinimum"}:
        raise BaselineError("standard support fields differ")
    if set(tested) != {"opencodeVersion", "copilotVersion", "cpltRelease"}:
        raise BaselineError("release-test version fields differ")
    semantic_version = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
    for key in ("opencodeMinimum", "copilotMinimum"):
        if not isinstance(standard[key], str) or semantic_version.fullmatch(standard[key]) is None:
            raise BaselineError(f"standard support {key} is not a semantic version")
    for key in ("opencodeVersion", "copilotVersion"):
        if not isinstance(tested[key], str) or semantic_version.fullmatch(tested[key]) is None:
            raise BaselineError(f"release-test {key} is not a semantic version")
    if tuple(map(int, tested["opencodeVersion"].split("."))) < tuple(
        map(int, standard["opencodeMinimum"].split("."))
    ):
        raise BaselineError("release-test OpenCode predates the standard minimum")
    if tuple(map(int, tested["copilotVersion"].split("."))) < tuple(
        map(int, standard["copilotMinimum"].split("."))
    ):
        raise BaselineError("release-test Copilot predates the standard minimum")
    if standard["cpltMinimum"] != tested["cpltRelease"]:
        raise BaselineError("cplt standard minimum and release-test baseline differ")
    artifacts = CONTRACT["artifacts"]
    if not isinstance(artifacts, dict) or set(artifacts) != expected_artifacts:
        raise BaselineError("release-test artifact roster differs")
    expected_fields = {
        "url",
        "archiveSize",
        "archiveDigest",
        "roster",
        "executablePath",
        "executableSize",
        "executableSha256",
    }
    for key, record in artifacts.items():
        if not isinstance(record, dict) or set(record) != expected_fields:
            raise BaselineError(f"release-test artifact fields differ for {key}")
        if not isinstance(record["url"], str) or not record["url"].startswith("https://"):
            raise BaselineError(f"release-test artifact URL is invalid for {key}")
        client = key.split(":", 1)[0]
        version = {
            "opencode": tested["opencodeVersion"],
            "copilot": tested["copilotVersion"],
            "cplt": tested["cpltRelease"],
        }[client]
        if version not in record["url"]:
            raise BaselineError(f"release-test artifact URL has the wrong version for {key}")
        if type(record["archiveSize"]) is not int or record["archiveSize"] <= 0:
            raise BaselineError(f"release-test archive size is invalid for {key}")
        if type(record["executableSize"]) is not int or record["executableSize"] <= 0:
            raise BaselineError(f"release-test executable size is invalid for {key}")
        algorithm, separator, digest = record["archiveDigest"].partition(":")
        if separator != ":" or algorithm not in {"sha256", "sha512"} or re.fullmatch(
            r"[0-9a-f]+", digest
        ) is None or len(digest) != {"sha256": 64, "sha512": 128}[algorithm]:
            raise BaselineError(f"release-test archive digest is invalid for {key}")
        if not isinstance(record["executableSha256"], str) or re.fullmatch(
            r"[0-9a-f]{64}", record["executableSha256"]
        ) is None:
            raise BaselineError(f"release-test executable digest is invalid for {key}")
        roster = record["roster"]
        if not isinstance(roster, list) or not roster or len(roster) != len(set(roster)):
            raise BaselineError(f"release-test archive roster is invalid for {key}")
        for value in roster:
            path = PurePosixPath(value) if isinstance(value, str) else PurePosixPath("/")
            if path.is_absolute() or path.as_posix() != value or any(
                part in {"", ".", ".."} for part in path.parts
            ):
                raise BaselineError(f"release-test archive path is invalid for {key}")
        if record["executablePath"] not in roster:
            raise BaselineError(f"release-test executable is absent from roster for {key}")


_validate_contract()


def artifact(client: str, platform: str, architecture: str) -> Mapping[str, Any]:
    key = f"{client}:{platform}:{architecture}"
    value = CONTRACT["artifacts"].get(key)
    if not isinstance(value, dict):
        raise BaselineError(f"unsupported release-test artifact: {key}")
    return value


def _read_exact(path: Path, expected_size: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        observed = os.fstat(descriptor)
        if not stat.S_ISREG(observed.st_mode) or observed.st_size != expected_size:
            raise BaselineError("archive size or type differs from the baseline")
        chunks: list[bytes] = []
        remaining = expected_size + 1
        while remaining:
            chunk = os.read(descriptor, min(COPY_CHUNK_BYTES, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after = os.fstat(descriptor)
        if len(content) != expected_size or (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) != (
            observed.st_size,
            observed.st_mtime_ns,
            observed.st_ctime_ns,
        ):
            raise BaselineError("archive changed while it was read")
        return content
    finally:
        os.close(descriptor)


def verify_and_extract(record: Mapping[str, Any], archive: Path, output: Path) -> None:
    """Verify one pinned tarball and atomically publish its executable."""

    expected_size = record["archiveSize"]
    content = _read_exact(archive, expected_size)
    algorithm, expected_digest = record["archiveDigest"].split(":", 1)
    if algorithm not in {"sha256", "sha512"}:
        raise BaselineError(f"unsupported archive digest: {algorithm}")
    if hashlib.new(algorithm, content).hexdigest() != expected_digest:
        raise BaselineError("archive digest differs from the baseline")

    with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as package:
        if package.pax_headers:
            raise BaselineError("archive has global PAX headers")
        members = package.getmembers()
        if len(members) > MAX_ARCHIVE_MEMBERS or [item.name for item in members] != record["roster"]:
            raise BaselineError("archive roster differs from the baseline")
        selected = None
        for member in members:
            if (
                member.type not in {tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE}
                or member.pax_headers
                or member.linkname
                or member.devmajor != 0
                or member.devminor != 0
                or member.sparse is not None
            ):
                raise BaselineError("archive contains a link or special member")
            if member.name == record["executablePath"]:
                selected = member
        if (
            selected is None
            or not selected.isfile()
            or selected.size != record["executableSize"]
        ):
            raise BaselineError("executable size differs from the baseline")
        extracted = package.extractfile(selected)
        if extracted is None:
            raise BaselineError("could not read executable from archive")
        executable = extracted.read(record["executableSize"] + 1)
    if len(executable) != record["executableSize"]:
        raise BaselineError("executable changed while it was read")
    if hashlib.sha256(executable).hexdigest() != record["executableSha256"]:
        raise BaselineError("executable digest differs from the baseline")

    output = output.expanduser().absolute()
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(output, flags, 0o500)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as destination:
            destination.write(executable)
            destination.flush()
            os.fsync(descriptor)
        os.fchmod(descriptor, 0o555)
    except BaseException:
        try:
            output.unlink()
        except OSError:
            pass
        raise
    finally:
        os.close(descriptor)


def download_and_install(record: Mapping[str, Any], output: Path) -> None:
    output = output.expanduser().absolute()
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tar.gz", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        result = subprocess.run(
            [
                "curl",
                "--config",
                "/dev/null",
                "--fail-with-body",
                "--silent",
                "--show-error",
                "--location",
                "--proto",
                "=https",
                "--tlsv1.2",
                "--proto-redir",
                "=https",
                "--max-filesize",
                str(record["archiveSize"]),
                "--output",
                str(temporary),
                record["url"],
            ],
            check=False,
        )
        if result.returncode != 0:
            raise BaselineError(f"curl failed with exit status {result.returncode}")
        verify_and_extract(record, temporary, output)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("json", help="print the complete baseline contract")
    env_parser = subparsers.add_parser("github-env", help="print stable CI variables")
    env_parser.add_argument("--prefix", default="RELEASE_TEST_")
    for command in ("field", "verify", "install"):
        candidate = subparsers.add_parser(command)
        candidate.add_argument("--client", choices=("opencode", "copilot", "cplt"), required=True)
        candidate.add_argument("--platform", choices=("darwin", "linux"), required=True)
        candidate.add_argument("--architecture", choices=("arm64", "x86_64"), required=True)
        if command == "field":
            candidate.add_argument("--name", choices=("url", "executableSha256"), required=True)
        elif command == "verify":
            candidate.add_argument("--archive", type=Path, required=True)
            candidate.add_argument("--output", type=Path, required=True)
        else:
            candidate.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    options = parse_args(argv)
    try:
        if options.command == "json":
            print(json.dumps(CONTRACT, indent=2, sort_keys=True))
            return 0
        if options.command == "github-env":
            prefix = options.prefix
            if not prefix or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for character in prefix):
                raise BaselineError("environment prefix must contain only A-Z, 0-9, and underscore")
            standard = CONTRACT["standardSupport"]
            tested = CONTRACT["releaseTest"]
            for name, value in (
                ("OPENCODE_MINIMUM", standard["opencodeMinimum"]),
                ("COPILOT_MINIMUM", standard["copilotMinimum"]),
                ("CPLT_MINIMUM", standard["cpltMinimum"]),
                ("OPENCODE_VERSION", tested["opencodeVersion"]),
                ("COPILOT_VERSION", tested["copilotVersion"]),
                ("CPLT_RELEASE", tested["cpltRelease"]),
            ):
                print(f"{prefix}{name}={value}")
            return 0
        selected = artifact(options.client, options.platform, options.architecture)
        if options.command == "field":
            print(selected[options.name])
        elif options.command == "verify":
            verify_and_extract(selected, options.archive, options.output)
        else:
            download_and_install(selected, options.output)
        return 0
    except (BaselineError, OSError, tarfile.TarError) as exc:
        print(f"Release-test baseline failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
