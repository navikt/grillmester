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
        "opencodeMinimum": "1.18.20",
        "copilotMinimum": "1.0.79",
        "cpltMinimum": "2026.08.17-062831-1008a92",
    },
    "releaseTest": {
        "opencodeVersion": "1.18.20",
        "copilotVersion": "1.0.80",
        "cpltRelease": "2026.08.17-062831-1008a92",
    },
    "artifacts": {
        "opencode:darwin:arm64": {
            "url": "https://registry.npmjs.org/opencode-darwin-arm64/-/opencode-darwin-arm64-1.18.20.tgz",
            "archiveSize": 45912069,
            "archiveDigest": "sha512:7e010126cc31f75380b44989cbb8934f6da262c69d0b29f8629eeb574f60fae7f9968c995e49f238b62620b6080ebbc43fa16b50bacf6160635a65aa22beae80",
            "roster": ["package/package.json", "package/bin/opencode"],
            "executablePath": "package/bin/opencode",
            "executableSize": 143925602,
            "executableSha256": "9598c27bda0e2d88ce4db5f853e25504c20ac6152e10205785a1cf8f45559952",
        },
        "opencode:darwin:x86_64": {
            "url": "https://registry.npmjs.org/opencode-darwin-x64/-/opencode-darwin-x64-1.18.20.tgz",
            "archiveSize": 48089366,
            "archiveDigest": "sha512:cbade5db7d9d2cf3175a66155aba13c5b77bc1f602b1178f05a5ec8bb9f77983cd7bb29ea3aacc97170db266c187173c3a609eaf4c83f4391a492e7230b83dc1",
            "roster": ["package/package.json", "package/bin/opencode"],
            "executablePath": "package/bin/opencode",
            "executableSize": 149405776,
            "executableSha256": "96e4a9ecd931a059515fb2126cf59a4a3b56d9a66f9d4dbdf1361d1b4cd5ef60",
        },
        "opencode:linux:x86_64": {
            "url": "https://registry.npmjs.org/opencode-linux-x64/-/opencode-linux-x64-1.18.20.tgz",
            "archiveSize": 60135211,
            "archiveDigest": "sha512:1fe5e153b35b7d306df98135cdab1876e9637ef79941b6adc3bda00d485629f9c4f3781df4a67cbb96e209fed364472c8bd40979b1606b6513ade6ec8afcd0ba",
            "roster": ["package/package.json", "package/bin/opencode"],
            "executablePath": "package/bin/opencode",
            "executableSize": 184490112,
            "executableSha256": "5dce99ea079d925736e332b20f5bf869fe9a1fa67dc0a09027156b0ed8e41b16",
        },
        "copilot:darwin:arm64": {
            "url": "https://github.com/github/copilot-cli/releases/download/v1.0.80/copilot-darwin-arm64.tar.gz",
            "archiveSize": 99168802,
            "archiveDigest": "sha256:2346bb691981c2997d65c1c5bc3cef1aeddc9edd37dcb2f970b911aa597e59f6",
            "roster": ["copilot"],
            "executablePath": "copilot",
            "executableSize": 160804656,
            "executableSha256": "fe779da7dd2342c1d23f0744873fa27d0251eaaee4dc6637fa53093639c0f3c9",
        },
        "copilot:darwin:x86_64": {
            "url": "https://github.com/github/copilot-cli/releases/download/v1.0.80/copilot-darwin-x64.tar.gz",
            "archiveSize": 110675243,
            "archiveDigest": "sha256:a1a9c1f25740f9a27b34eb14b70b5d3175794dc8bb410875531aa198b3abc18f",
            "roster": ["copilot"],
            "executablePath": "copilot",
            "executableSize": 173286208,
            "executableSha256": "15a2576566635fdd2dc0c84137ec7481e41a6982281391c62e58883aa5f39f41",
        },
        "cplt:darwin:arm64": {
            "url": "https://github.com/navikt/cplt/releases/download/2026.08.17-062831-1008a92/cplt-aarch64-apple-darwin.tar.gz",
            "archiveSize": 1480572,
            "archiveDigest": "sha256:fb1fd69f5ff42deb1cf2e510d97a58ff5f7ddf913e1cd4f7533815a16588eeda",
            "roster": ["cplt"],
            "executablePath": "cplt",
            "executableSize": 3122208,
            "executableSha256": "423af2ce6166b0ddc1939d2e4d1340837daa23a29ccc58024ec0a849051becb2",
        },
        "cplt:darwin:x86_64": {
            "url": "https://github.com/navikt/cplt/releases/download/2026.08.17-062831-1008a92/cplt-x86_64-apple-darwin.tar.gz",
            "archiveSize": 1613282,
            "archiveDigest": "sha256:e60687724df8a2fdb6f99654cc80f1a0dccb215263c2d984c222ff99ce56f8ea",
            "roster": ["cplt"],
            "executablePath": "cplt",
            "executableSize": 3546896,
            "executableSha256": "36592c1b2bcfd7ab2d9083842b0aa7f51737cdf12ec1752d351bd9467dab5c02",
        },
        "cplt:linux:x86_64": {
            "url": "https://github.com/navikt/cplt/releases/download/2026.08.17-062831-1008a92/cplt-x86_64-unknown-linux-gnu.tar.gz",
            "archiveSize": 1680011,
            "archiveDigest": "sha256:3e6607db8ed2f361bb4e8a43246d38acc7e63e5d956de96c3319fffbd3be3eb4",
            "roster": ["cplt"],
            "executablePath": "cplt",
            "executableSize": 3807496,
            "executableSha256": "115fff00248f0c170388e11f2a05cc9914f5ba589f2ca87817ed96de2c6eedb5",
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
                member.type not in {tarfile.REGTYPE, tarfile.AREGTYPE}
                or member.pax_headers
                or member.linkname
                or member.devmajor != 0
                or member.devminor != 0
                or member.sparse is not None
            ):
                raise BaselineError("archive contains a link or special member")
            if member.name == record["executablePath"]:
                selected = member
        if selected is None or selected.size != record["executableSize"]:
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
