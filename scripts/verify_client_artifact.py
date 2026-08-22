#!/usr/bin/env python3
"""Verify and extract one pinned OpenCode or cplt client without executing it."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import secrets
import stat
import sys
import tarfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterator, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = REPOSITORY_ROOT / "policy/client-artifacts.json"
MAX_LOCK_BYTES = 2 * 1024 * 1024
MAX_JSON_DEPTH = 40
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
COPY_CHUNK_BYTES = 1024 * 1024
ALLOWED_CLIENTS = frozenset({"opencode", "cplt"})
HEX_DIGEST_LENGTH = {"sha256": 64, "sha512": 128}


class ArtifactVerificationError(RuntimeError):
    """Raised before a client can be published when verification fails."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactVerificationError(f"duplicate JSON key in artifact lock: {key!r}")
        result[key] = value
    return result


def _reject_nonstandard_json_constant(value: str) -> None:
    raise ArtifactVerificationError(
        f"non-standard JSON constant in artifact lock: {value}"
    )


def _absolute_existing_path(path: Path) -> Path:
    try:
        return path.expanduser().absolute()
    except OSError as exc:  # pragma: no cover - platform-specific Path failure
        raise ArtifactVerificationError(f"could not resolve path {path}: {exc}") from exc


@contextmanager
def _open_regular_file(
    path: Path, *, label: str, maximum_bytes: int
) -> Iterator[tuple[int, os.stat_result]]:
    path = _absolute_existing_path(path)
    try:
        before = path.lstat()
    except FileNotFoundError as exc:
        raise ArtifactVerificationError(f"missing {label}: {path}") from exc
    except OSError as exc:
        raise ArtifactVerificationError(f"could not inspect {label} {path}: {exc}") from exc
    if stat.S_ISLNK(before.st_mode):
        raise ArtifactVerificationError(f"refusing symlinked {label}: {path}")
    if not stat.S_ISREG(before.st_mode):
        raise ArtifactVerificationError(f"{label} is not a regular file: {path}")
    if before.st_size > maximum_bytes:
        raise ArtifactVerificationError(
            f"{label} exceeds the {maximum_bytes}-byte safety limit: {path}"
        )

    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ArtifactVerificationError(f"could not safely open {label} {path}: {exc}") from exc
    try:
        observed = os.fstat(descriptor)
        if not stat.S_ISREG(observed.st_mode):
            raise ArtifactVerificationError(f"{label} is not a regular file: {path}")
        if (observed.st_dev, observed.st_ino) != (before.st_dev, before.st_ino):
            raise ArtifactVerificationError(f"{label} changed while it was opened: {path}")
        if observed.st_size > maximum_bytes:
            raise ArtifactVerificationError(
                f"{label} exceeds the {maximum_bytes}-byte safety limit: {path}"
            )
        yield descriptor, observed
    finally:
        os.close(descriptor)


def _read_bounded_file(
    path: Path, *, label: str, maximum_bytes: int
) -> bytes:
    with _open_regular_file(
        path, label=label, maximum_bytes=maximum_bytes
    ) as (descriptor, observed):
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(COPY_CHUNK_BYTES, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > maximum_bytes:
            raise ArtifactVerificationError(
                f"{label} exceeds the {maximum_bytes}-byte safety limit: {path}"
            )
        after = os.fstat(descriptor)
        if len(content) != observed.st_size or (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) != (
            observed.st_size,
            observed.st_mtime_ns,
            observed.st_ctime_ns,
        ):
            raise ArtifactVerificationError(f"{label} changed while it was read: {path}")
        return content


def load_artifact_lock(path: Path) -> dict[str, Any]:
    content = _read_bounded_file(
        path, label="client artifact lock", maximum_bytes=MAX_LOCK_BYTES
    )
    try:
        value = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except UnicodeDecodeError as exc:
        raise ArtifactVerificationError("client artifact lock is not UTF-8") from exc
    except RecursionError as exc:
        raise ArtifactVerificationError(
            "client artifact lock exceeds the JSON nesting limit"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ArtifactVerificationError(
            "client artifact lock is not valid JSON at "
            f"line {exc.lineno}, column {exc.colno}"
        ) from exc
    if (
        not isinstance(value, dict)
        or type(value.get("schemaVersion")) is not int
        or value["schemaVersion"] != 1
    ):
        raise ArtifactVerificationError("client artifact lock schemaVersion must be 1")
    pending: list[tuple[object, int]] = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > MAX_JSON_DEPTH:
            raise ArtifactVerificationError(
                "client artifact lock exceeds the JSON nesting limit"
            )
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    return value


def _safe_archive_path(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ArtifactVerificationError(f"{label} must be a non-empty string")
    if "\\" in value or any(
        ord(character) < 32 or ord(character) == 127 for character in value
    ):
        raise ArtifactVerificationError(f"{label} is not a safe portable path: {value!r}")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise ArtifactVerificationError(f"{label} is not a normalized relative path")
    return value


def _positive_integer(value: object, *, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ArtifactVerificationError(f"{label} must be a positive integer")
    return value


def _hex_digest(value: object, *, algorithm: str, label: str) -> str:
    expected_length = HEX_DIGEST_LENGTH[algorithm]
    if (
        not isinstance(value, str)
        or len(value) != expected_length
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ArtifactVerificationError(
            f"{label} must be a {expected_length}-character lowercase {algorithm} digest"
        )
    return value


def select_artifact(
    lock: dict[str, Any],
    *,
    client: str,
    os_name: str,
    architecture: str,
    libc: str,
    variant: str,
) -> dict[str, Any]:
    if client not in ALLOWED_CLIENTS:
        raise ArtifactVerificationError(f"unsupported client: {client!r}")
    client_policy = lock.get(client)
    if not isinstance(client_policy, dict):
        raise ArtifactVerificationError(f"artifact lock is missing client {client!r}")
    records = client_policy.get("artifacts")
    if not isinstance(records, list):
        raise ArtifactVerificationError(f"artifact lock {client} records must be an array")
    selector = (os_name, architecture, libc, variant)
    matches: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            raise ArtifactVerificationError(f"artifact lock {client} record must be an object")
        if (
            record.get("platform"),
            record.get("architecture"),
            record.get("libc"),
            record.get("variant"),
        ) == selector:
            matches.append(record)
    if not matches:
        raise ArtifactVerificationError(
            "artifact lock has no exact record for "
            f"client={client}, os={os_name}, arch={architecture}, "
            f"libc={libc}, variant={variant}"
        )
    if len(matches) != 1:
        raise ArtifactVerificationError(
            "artifact lock has duplicate records for the requested client selector"
        )
    return matches[0]


def _record_contract(
    client: str, record: dict[str, Any]
) -> tuple[int, str, str, list[str], str, int, str]:
    archive = record.get("archive")
    executable = record.get("executable")
    if not isinstance(archive, dict) or not isinstance(executable, dict):
        raise ArtifactVerificationError("selected artifact record is incomplete")
    archive_size = _positive_integer(archive.get("size"), label="archive size")
    if client == "opencode":
        algorithm = "sha512"
        archive_digest = _hex_digest(
            archive.get("sha512"), algorithm=algorithm, label="archive digest"
        )
        integrity = archive.get("integrity")
        if not isinstance(integrity, str) or not integrity.startswith("sha512-"):
            raise ArtifactVerificationError("OpenCode archive needs npm SHA-512 integrity")
        try:
            integrity_digest = base64.b64decode(
                integrity.removeprefix("sha512-"), validate=True
            ).hex()
        except (binascii.Error, ValueError) as exc:
            raise ArtifactVerificationError("OpenCode archive integrity is invalid") from exc
        if integrity_digest != archive_digest:
            raise ArtifactVerificationError(
                "OpenCode archive integrity does not match its SHA-512 digest"
            )
    else:
        algorithm = "sha256"
        archive_digest = _hex_digest(
            archive.get("sha256"), algorithm=algorithm, label="archive digest"
        )
        evidence = archive.get("digestEvidence")
        if not isinstance(evidence, dict) or evidence.get(
            "reportedDigest"
        ) != f"sha256:{archive_digest}":
            raise ArtifactVerificationError(
                "cplt archive digest does not match its GitHub asset evidence"
            )

    raw_roster = archive.get("roster")
    if not isinstance(raw_roster, list) or not raw_roster:
        raise ArtifactVerificationError("archive roster must be a non-empty array")
    roster = [
        _safe_archive_path(path, label="archive roster path") for path in raw_roster
    ]
    if len(roster) != len(set(roster)):
        raise ArtifactVerificationError("archive roster contains duplicate paths")

    executable_path = _safe_archive_path(
        executable.get("path"), label="executable path"
    )
    if executable_path not in roster:
        raise ArtifactVerificationError("executable path is missing from archive roster")
    executable_size = _positive_integer(
        executable.get("size"), label="executable size"
    )
    executable_digest = _hex_digest(
        executable.get("sha256"),
        algorithm="sha256",
        label="executable digest",
    )
    return (
        archive_size,
        algorithm,
        archive_digest,
        roster,
        executable_path,
        executable_size,
        executable_digest,
    )


def _hash_descriptor(descriptor: int, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        chunk = os.read(descriptor, COPY_CHUNK_BYTES)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def _validate_tar_members(
    archive: tarfile.TarFile, *, roster: list[str], executable_path: str
) -> tarfile.TarInfo:
    if archive.pax_headers:
        raise ArtifactVerificationError("archive contains unsupported global PAX metadata")
    members: list[tarfile.TarInfo] = []
    for member in archive:
        members.append(member)
        if len(members) > len(roster):
            raise ArtifactVerificationError("archive contains members outside the roster")
    names = [member.name for member in members]
    if len(names) != len(set(names)):
        raise ArtifactVerificationError("archive contains duplicate member paths")
    for name in names:
        _safe_archive_path(name, label="archive member path")
    if names != roster:
        raise ArtifactVerificationError(
            f"archive roster mismatch: expected {roster!r}, observed {names!r}"
        )

    expected_offset = 0
    executable_member: tarfile.TarInfo | None = None
    for member in members:
        if member.offset != expected_offset or member.offset_data != member.offset + 512:
            raise ArtifactVerificationError(
                f"archive member {member.name!r} uses hidden extension headers"
            )
        if (
            not member.isfile()
            or member.issym()
            or member.islnk()
            or member.type not in {tarfile.REGTYPE, tarfile.AREGTYPE}
            or member.linkname
            or member.pax_headers
            or getattr(member, "sparse", None)
        ):
            raise ArtifactVerificationError(
                f"archive member {member.name!r} is not a plain regular file"
            )
        expected_offset = member.offset_data + ((member.size + 511) // 512) * 512
        if member.name == executable_path:
            executable_member = member
    if executable_member is None:  # pragma: no cover - roster check establishes this
        raise ArtifactVerificationError("archive does not contain the selected executable")
    return executable_member


@contextmanager
def _open_private_output_directory(path: Path) -> Iterator[tuple[Path, int]]:
    raw_path = _absolute_existing_path(path)
    try:
        raw = raw_path.lstat()
        if stat.S_ISLNK(raw.st_mode):
            raise ArtifactVerificationError(
                f"refusing symlinked output directory: {raw_path}"
            )
        canonical = raw_path.resolve(strict=True)
        before = canonical.lstat()
    except ArtifactVerificationError:
        raise
    except (FileNotFoundError, OSError) as exc:
        raise ArtifactVerificationError(f"could not resolve output directory {path}: {exc}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
        raise ArtifactVerificationError(f"output path is not a real directory: {canonical}")
    if stat.S_IMODE(before.st_mode) & 0o022:
        raise ArtifactVerificationError(
            f"output directory must not be group/world writable: {canonical}"
        )
    if hasattr(os, "geteuid") and before.st_uid != os.geteuid():
        raise ArtifactVerificationError(
            f"output directory must be owned by the current user: {canonical}"
        )

    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        directory_descriptor = os.open(canonical, flags)
    except OSError as exc:
        raise ArtifactVerificationError(
            f"could not safely open output directory {canonical}: {exc}"
        ) from exc
    try:
        observed = os.fstat(directory_descriptor)
        if not stat.S_ISDIR(observed.st_mode) or (
            observed.st_dev,
            observed.st_ino,
        ) != (before.st_dev, before.st_ino):
            raise ArtifactVerificationError(
                f"output directory changed while it was opened: {canonical}"
            )
        yield canonical, directory_descriptor
    finally:
        os.close(directory_descriptor)


def _create_private_temp_file(directory_descriptor: int, binary_name: str) -> tuple[str, int]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    for _ in range(128):
        name = f".{binary_name}.verify-{secrets.token_hex(12)}"
        try:
            return name, os.open(name, flags, 0o600, dir_fd=directory_descriptor)
        except FileExistsError:
            continue
        except OSError as exc:
            raise ArtifactVerificationError(
                f"could not create private output file: {exc}"
            ) from exc
    raise ArtifactVerificationError("could not allocate a unique private output file")


def _write_all(descriptor: int, content: bytes) -> None:
    view = memoryview(content)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:  # pragma: no cover - os.write raises instead
            raise ArtifactVerificationError("could not write the verified executable")
        view = view[written:]


def _recheck_output(
    directory_descriptor: int,
    binary_name: str,
    *,
    expected_size: int,
    expected_digest: str,
) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(binary_name, flags, dir_fd=directory_descriptor)
    try:
        observed = os.fstat(descriptor)
        if not stat.S_ISREG(observed.st_mode) or observed.st_size != expected_size:
            raise ArtifactVerificationError("published executable changed before chmod")
        if _hash_descriptor(descriptor, "sha256") != expected_digest:
            raise ArtifactVerificationError("published executable digest changed before chmod")
        os.fchmod(descriptor, 0o755)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_executable(
    archive: tarfile.TarFile,
    member: tarfile.TarInfo,
    *,
    output_directory: Path,
    executable_path: str,
    expected_size: int,
    expected_digest: str,
    pre_publish: Callable[[], None],
) -> Path:
    if member.size != expected_size:
        raise ArtifactVerificationError(
            f"executable size mismatch: expected {expected_size}, observed {member.size}"
        )
    binary_name = PurePosixPath(executable_path).name
    if not binary_name or binary_name in (".", ".."):
        raise ArtifactVerificationError("executable path has no safe output filename")

    extracted = archive.extractfile(member)
    if extracted is None:
        raise ArtifactVerificationError("could not read executable from archive")
    with extracted, _open_private_output_directory(output_directory) as (
        canonical_output,
        directory_descriptor,
    ):
        temporary_name, temporary_descriptor = _create_private_temp_file(
            directory_descriptor, binary_name
        )
        published = False
        try:
            digest = hashlib.sha256()
            observed_size = 0
            while True:
                chunk = extracted.read(COPY_CHUNK_BYTES)
                if not chunk:
                    break
                observed_size += len(chunk)
                if observed_size > expected_size:
                    raise ArtifactVerificationError(
                        "extracted executable exceeds its pinned size"
                    )
                digest.update(chunk)
                _write_all(temporary_descriptor, chunk)
            if observed_size != expected_size:
                raise ArtifactVerificationError(
                    f"executable size mismatch: expected {expected_size}, "
                    f"observed {observed_size}"
                )
            if digest.hexdigest() != expected_digest:
                raise ArtifactVerificationError("executable SHA-256 mismatch")
            os.fsync(temporary_descriptor)
            observed = os.fstat(temporary_descriptor)
            if (
                not stat.S_ISREG(observed.st_mode)
                or observed.st_size != expected_size
                or stat.S_IMODE(observed.st_mode) != 0o600
            ):
                raise ArtifactVerificationError(
                    "private executable output changed before publication"
                )
            pre_publish()
            os.close(temporary_descriptor)
            temporary_descriptor = -1
            try:
                os.link(
                    temporary_name,
                    binary_name,
                    src_dir_fd=directory_descriptor,
                    dst_dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise ArtifactVerificationError(
                    f"refusing to overwrite existing output: {canonical_output / binary_name}"
                ) from exc
            published = True
            os.unlink(temporary_name, dir_fd=directory_descriptor)
            temporary_name = ""
            _recheck_output(
                directory_descriptor,
                binary_name,
                expected_size=expected_size,
                expected_digest=expected_digest,
            )
            os.fsync(directory_descriptor)
            return canonical_output / binary_name
        except BaseException:
            if published:
                try:
                    os.unlink(binary_name, dir_fd=directory_descriptor)
                except FileNotFoundError:
                    pass
            raise
        finally:
            if temporary_descriptor >= 0:
                os.close(temporary_descriptor)
            if temporary_name:
                try:
                    os.unlink(temporary_name, dir_fd=directory_descriptor)
                except FileNotFoundError:
                    pass


def verify_and_extract(
    *,
    lock_path: Path,
    client: str,
    os_name: str,
    architecture: str,
    libc: str,
    variant: str,
    archive_path: Path,
    output_directory: Path,
) -> dict[str, object]:
    lock = load_artifact_lock(lock_path)
    record = select_artifact(
        lock,
        client=client,
        os_name=os_name,
        architecture=architecture,
        libc=libc,
        variant=variant,
    )
    (
        archive_size,
        archive_algorithm,
        archive_digest,
        roster,
        executable_path,
        executable_size,
        executable_digest,
    ) = _record_contract(client, record)
    if archive_size > MAX_ARCHIVE_BYTES:
        raise ArtifactVerificationError(
            f"pinned archive exceeds the {MAX_ARCHIVE_BYTES}-byte safety limit"
        )

    with _open_regular_file(
        archive_path, label="client archive", maximum_bytes=MAX_ARCHIVE_BYTES
    ) as (archive_descriptor, observed):
        if observed.st_size != archive_size:
            raise ArtifactVerificationError(
                f"archive size mismatch: expected {archive_size}, observed {observed.st_size}"
            )
        if _hash_descriptor(archive_descriptor, archive_algorithm) != archive_digest:
            raise ArtifactVerificationError(
                f"archive {archive_algorithm.upper()} mismatch"
            )
        os.lseek(archive_descriptor, 0, os.SEEK_SET)

        def require_unchanged_archive() -> None:
            after = os.fstat(archive_descriptor)
            if (
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ) != (
                observed.st_size,
                observed.st_mtime_ns,
                observed.st_ctime_ns,
            ) or _hash_descriptor(archive_descriptor, archive_algorithm) != archive_digest:
                raise ArtifactVerificationError("client archive changed during extraction")

        with os.fdopen(os.dup(archive_descriptor), "rb") as archive_stream:
            try:
                with tarfile.open(fileobj=archive_stream, mode="r:gz") as archive:
                    member = _validate_tar_members(
                        archive, roster=roster, executable_path=executable_path
                    )
                    output_path = _publish_executable(
                        archive,
                        member,
                        output_directory=output_directory,
                        executable_path=executable_path,
                        expected_size=executable_size,
                        expected_digest=executable_digest,
                        pre_publish=require_unchanged_archive,
                    )
            except (tarfile.TarError, EOFError, OSError) as exc:
                raise ArtifactVerificationError(
                    f"could not safely read client archive: {exc}"
                ) from exc
    return {
        "client": client,
        "platform": os_name,
        "architecture": architecture,
        "libc": libc,
        "variant": variant,
        "archiveDigest": f"{archive_algorithm}:{archive_digest}",
        "path": str(output_path),
        "size": executable_size,
        "sha256": executable_digest,
        "executed": False,
    }


def selected_download_url(
    *,
    lock_path: Path,
    client: str,
    os_name: str,
    architecture: str,
    libc: str,
    variant: str,
) -> str:
    """Return the authenticated lock's exact HTTPS URL without networking."""

    record = select_artifact(
        load_artifact_lock(lock_path),
        client=client,
        os_name=os_name,
        architecture=architecture,
        libc=libc,
        variant=variant,
    )
    # Validate the complete digest/roster contract before publishing even its
    # download location to a bootstrap command.
    _record_contract(client, record)
    url = record.get("url")
    expected_prefix = {
        "opencode": "https://registry.npmjs.org/",
        "cplt": "https://github.com/navikt/cplt/releases/download/",
    }[client]
    if (
        not isinstance(url, str)
        or not url.startswith(expected_prefix)
        or any(character.isspace() or ord(character) < 32 for character in url)
        or "#" in url
        or "?" in url
    ):
        raise ArtifactVerificationError(
            f"selected {client} artifact has an invalid official HTTPS URL"
        )
    return url


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify and extract one already-downloaded client from the immutable "
            "artifact lock. This command performs no network access and executes nothing."
        )
    )
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--client", choices=sorted(ALLOWED_CLIENTS), required=True)
    parser.add_argument("--os", dest="os_name", required=True)
    parser.add_argument("--arch", dest="architecture", required=True)
    parser.add_argument("--libc", required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--print-url",
        action="store_true",
        help="print the exact authenticated download URL and perform no extraction",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.print_url:
            if arguments.archive is not None or arguments.output_dir is not None:
                raise ArtifactVerificationError(
                    "--print-url cannot be combined with --archive or --output-dir"
                )
            print(
                selected_download_url(
                    lock_path=arguments.lock,
                    client=arguments.client,
                    os_name=arguments.os_name,
                    architecture=arguments.architecture,
                    libc=arguments.libc,
                    variant=arguments.variant,
                )
            )
            return 0
        if arguments.archive is None or arguments.output_dir is None:
            raise ArtifactVerificationError(
                "verification requires both --archive and --output-dir"
            )
        result = verify_and_extract(
            lock_path=arguments.lock,
            client=arguments.client,
            os_name=arguments.os_name,
            architecture=arguments.architecture,
            libc=arguments.libc,
            variant=arguments.variant,
            archive_path=arguments.archive,
            output_directory=arguments.output_dir,
        )
    except ArtifactVerificationError as exc:
        print(f"client artifact verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
