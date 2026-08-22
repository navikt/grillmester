from __future__ import annotations

import ast
import base64
import hashlib
import importlib.util
import io
import json
import os
import stat
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_verify_client_artifact",
    ROOT / "scripts/verify_client_artifact.py",
)
assert SPEC and SPEC.loader
VERIFIER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFIER
SPEC.loader.exec_module(VERIFIER)


class VerifyClientArtifactTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.output = self.root / "trusted-bin"
        self.output.mkdir(mode=0o700)
        self.output.chmod(0o700)
        self.marker = self.root / "must-not-exist"
        self.binary = (
            b"#!/bin/sh\n"
            + f"touch {str(self.marker)!r}\n".encode("utf-8")
            + b"exit 0\n"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_archive(
        self,
        name: str,
        members: list[tuple[str, bytes, str]],
        *,
        pax: bool = False,
    ) -> Path:
        path = self.root / name
        archive_format = tarfile.PAX_FORMAT if pax else tarfile.USTAR_FORMAT
        with tarfile.open(path, "w:gz", format=archive_format) as archive:
            for member_name, content, kind in members:
                info = tarfile.TarInfo(member_name)
                info.mtime = 0
                info.uid = 0
                info.gid = 0
                if kind == "file":
                    info.size = len(content)
                    if pax:
                        info.pax_headers = {"comment": "hidden metadata"}
                    archive.addfile(info, io.BytesIO(content))
                elif kind == "symlink":
                    info.type = tarfile.SYMTYPE
                    info.linkname = "package/package.json"
                    archive.addfile(info)
                else:  # pragma: no cover - fixture contract
                    self.fail(f"unsupported fixture member kind: {kind}")
        return path

    def opencode_lock(
        self,
        archive: Path,
        *,
        roster: list[str] | None = None,
        executable_digest: str | None = None,
    ) -> dict[str, object]:
        archive_bytes = archive.read_bytes()
        archive_digest = hashlib.sha512(archive_bytes).digest()
        record = {
            "platform": "darwin",
            "architecture": "arm64",
            "libc": "none",
            "variant": "default",
            "package": "fixture",
            "url": "https://example.invalid/fixture.tgz",
            "archive": {
                "size": len(archive_bytes),
                "sha512": archive_digest.hex(),
                "integrity": "sha512-"
                + base64.b64encode(archive_digest).decode("ascii"),
                "roster": roster
                or ["package/package.json", "package/bin/opencode"],
            },
            "executable": {
                "path": "package/bin/opencode",
                "size": len(self.binary),
                "sha256": executable_digest or hashlib.sha256(self.binary).hexdigest(),
            },
        }
        return {
            "schemaVersion": 1,
            "opencode": {"version": "fixture", "artifacts": [record]},
            "cplt": {"release": "fixture", "artifacts": []},
        }

    def cplt_lock(self, archive: Path) -> dict[str, object]:
        archive_bytes = archive.read_bytes()
        archive_digest = hashlib.sha256(archive_bytes).hexdigest()
        return {
            "schemaVersion": 1,
            "opencode": {"version": "fixture", "artifacts": []},
            "cplt": {
                "release": "fixture",
                "artifacts": [
                    {
                        "platform": "linux",
                        "architecture": "x86_64",
                        "libc": "glibc",
                        "variant": "default",
                        "asset": "fixture.tar.gz",
                        "url": "https://example.invalid/fixture.tar.gz",
                        "archive": {
                            "size": len(archive_bytes),
                            "sha256": archive_digest,
                            "digestEvidence": {
                                "reportedDigest": f"sha256:{archive_digest}"
                            },
                            "roster": ["cplt"],
                        },
                        "executable": {
                            "path": "cplt",
                            "size": len(self.binary),
                            "sha256": hashlib.sha256(self.binary).hexdigest(),
                        },
                    }
                ],
            },
        }

    def write_lock(self, name: str, value: dict[str, object]) -> Path:
        path = self.root / name
        path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def test_artifact_lock_rejects_excessive_json_nesting(self) -> None:
        nested: object = "leaf"
        for _ in range(VERIFIER.MAX_JSON_DEPTH + 2):
            nested = {"child": nested}
        lock_path = self.write_lock(
            "deep-client-artifacts.json",
            {"schemaVersion": 1, "nested": nested},
        )

        with self.assertRaisesRegex(
            VERIFIER.ArtifactVerificationError, "nesting limit"
        ):
            VERIFIER.load_artifact_lock(lock_path)

    def verify_opencode(
        self, archive: Path, lock: dict[str, object], *, output: Path | None = None
    ) -> dict[str, object]:
        lock_path = self.write_lock("client-artifacts.json", lock)
        return VERIFIER.verify_and_extract(
            lock_path=lock_path,
            client="opencode",
            os_name="darwin",
            architecture="arm64",
            libc="none",
            variant="default",
            archive_path=archive,
            output_directory=output or self.output,
        )

    def test_verifier_is_stdlib_only_and_has_no_network_or_execution_surface(
        self,
    ) -> None:
        source = (ROOT / "scripts/verify_client_artifact.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])
        self.assertEqual(
            imported_roots,
            {
                "__future__",
                "argparse",
                "base64",
                "binascii",
                "contextlib",
                "hashlib",
                "json",
                "os",
                "pathlib",
                "secrets",
                "stat",
                "sys",
                "tarfile",
                "typing",
            },
        )
        forbidden_call_names = {
            "exec",
            "eval",
            "compile",
            "system",
            "popen",
            "startfile",
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, forbidden_call_names)
            elif isinstance(node.func, ast.Attribute):
                self.assertFalse(
                    node.func.attr in forbidden_call_names
                    or node.func.attr.startswith("exec")
                    or node.func.attr.startswith("spawn"),
                    node.func.attr,
                )

    def test_print_url_selects_one_official_lock_row_without_extraction(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = VERIFIER.main(
                [
                    "--client",
                    "opencode",
                    "--os",
                    "darwin",
                    "--arch",
                    "arm64",
                    "--libc",
                    "none",
                    "--variant",
                    "default",
                    "--print-url",
                ]
            )
        self.assertEqual(0, result)
        self.assertEqual(
            "https://registry.npmjs.org/opencode-darwin-arm64/-/"
            "opencode-darwin-arm64-1.18.20.tgz",
            output.getvalue().strip(),
        )
        self.assertEqual([], list(self.output.iterdir()))

    def test_verifies_extracts_and_never_executes_the_pinned_opencode_binary(
        self,
    ) -> None:
        archive = self.make_archive(
            "opencode.tgz",
            [
                ("package/package.json", b"{}\n", "file"),
                ("package/bin/opencode", self.binary, "file"),
            ],
        )

        result = self.verify_opencode(archive, self.opencode_lock(archive))

        output = self.output / "opencode"
        self.assertEqual(output.read_bytes(), self.binary)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o755)
        self.assertEqual(result["path"], str(output.resolve()))
        self.assertEqual(result["executed"], False)
        self.assertFalse(self.marker.exists(), "verified bytes must never be executed")
        self.assertEqual(["opencode"], [path.name for path in self.output.iterdir()])

    def test_cplt_uses_the_same_exact_selector_and_verification_path(self) -> None:
        archive = self.make_archive(
            "cplt.tar.gz", [("cplt", self.binary, "file")]
        )
        lock_path = self.write_lock("cplt-artifacts.json", self.cplt_lock(archive))

        result = VERIFIER.verify_and_extract(
            lock_path=lock_path,
            client="cplt",
            os_name="linux",
            architecture="x86_64",
            libc="glibc",
            variant="default",
            archive_path=archive,
            output_directory=self.output,
        )

        self.assertEqual((self.output / "cplt").read_bytes(), self.binary)
        self.assertEqual(result["client"], "cplt")
        self.assertFalse(self.marker.exists())

    def test_rejects_wrong_selector_archive_size_digest_and_existing_output(self) -> None:
        archive = self.make_archive(
            "opencode.tgz",
            [
                ("package/package.json", b"{}\n", "file"),
                ("package/bin/opencode", self.binary, "file"),
            ],
        )
        lock = self.opencode_lock(archive)
        lock_path = self.write_lock("selector.json", lock)
        with self.assertRaisesRegex(
            VERIFIER.ArtifactVerificationError, "no exact record"
        ):
            VERIFIER.verify_and_extract(
                lock_path=lock_path,
                client="opencode",
                os_name="darwin",
                architecture="x86_64",
                libc="none",
                variant="default",
                archive_path=archive,
                output_directory=self.output,
            )

        wrong_size = self.opencode_lock(archive)
        wrong_size["opencode"]["artifacts"][0]["archive"]["size"] += 1
        with self.assertRaisesRegex(
            VERIFIER.ArtifactVerificationError, "archive size mismatch"
        ):
            self.verify_opencode(archive, wrong_size)

        wrong_digest = self.opencode_lock(archive)
        zero_digest = bytes(64)
        wrong_digest["opencode"]["artifacts"][0]["archive"].update(
            {
                "sha512": zero_digest.hex(),
                "integrity": "sha512-"
                + base64.b64encode(zero_digest).decode("ascii"),
            }
        )
        with self.assertRaisesRegex(
            VERIFIER.ArtifactVerificationError, "archive SHA512 mismatch"
        ):
            self.verify_opencode(archive, wrong_digest)

        (self.output / "opencode").write_bytes(b"keep me")
        with self.assertRaisesRegex(
            VERIFIER.ArtifactVerificationError, "refusing to overwrite"
        ):
            self.verify_opencode(archive, self.opencode_lock(archive))
        self.assertEqual((self.output / "opencode").read_bytes(), b"keep me")
        self.assertEqual(["opencode"], [path.name for path in self.output.iterdir()])

    def test_rejects_symlinked_inputs_and_output_directory(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks are unavailable")
        archive = self.make_archive(
            "opencode.tgz",
            [
                ("package/package.json", b"{}\n", "file"),
                ("package/bin/opencode", self.binary, "file"),
            ],
        )
        lock = self.opencode_lock(archive)
        archive_link = self.root / "archive-link.tgz"
        archive_link.symlink_to(archive)
        with self.assertRaisesRegex(
            VERIFIER.ArtifactVerificationError, "symlinked client archive"
        ):
            self.verify_opencode(archive_link, lock)

        output_link = self.root / "output-link"
        output_link.symlink_to(self.output, target_is_directory=True)
        with self.assertRaisesRegex(
            VERIFIER.ArtifactVerificationError, "symlinked output directory"
        ):
            self.verify_opencode(archive, lock, output=output_link)
        self.assertEqual([], list(self.output.iterdir()))

    def test_rejects_unsafe_extra_duplicate_link_and_extension_members(self) -> None:
        unsafe = self.make_archive(
            "unsafe.tgz",
            [
                ("../package.json", b"{}\n", "file"),
                ("package/bin/opencode", self.binary, "file"),
            ],
        )
        with self.assertRaisesRegex(
            VERIFIER.ArtifactVerificationError, "not a normalized relative path"
        ):
            self.verify_opencode(
                unsafe,
                self.opencode_lock(
                    unsafe,
                    roster=["../package.json", "package/bin/opencode"],
                ),
            )

        extra = self.make_archive(
            "extra.tgz",
            [
                ("package/package.json", b"{}\n", "file"),
                ("package/bin/opencode", self.binary, "file"),
                ("package/extra", b"extra", "file"),
            ],
        )
        with self.assertRaisesRegex(
            VERIFIER.ArtifactVerificationError, "outside the roster"
        ):
            self.verify_opencode(extra, self.opencode_lock(extra))

        duplicate = self.make_archive(
            "duplicate.tgz",
            [
                ("package/package.json", b"{}\n", "file"),
                ("package/package.json", b"again\n", "file"),
                ("package/bin/opencode", self.binary, "file"),
            ],
        )
        with self.assertRaisesRegex(
            VERIFIER.ArtifactVerificationError,
            "outside the roster|duplicate member paths",
        ):
            self.verify_opencode(duplicate, self.opencode_lock(duplicate))

        linked = self.make_archive(
            "linked.tgz",
            [
                ("package/package.json", b"{}\n", "file"),
                ("package/bin/opencode", b"", "symlink"),
            ],
        )
        with self.assertRaisesRegex(
            VERIFIER.ArtifactVerificationError, "not a plain regular file"
        ):
            self.verify_opencode(linked, self.opencode_lock(linked))

        extended = self.make_archive(
            "extended.tgz",
            [
                ("package/package.json", b"{}\n", "file"),
                ("package/bin/opencode", self.binary, "file"),
            ],
            pax=True,
        )
        with self.assertRaisesRegex(
            VERIFIER.ArtifactVerificationError, "hidden extension headers"
        ):
            self.verify_opencode(extended, self.opencode_lock(extended))

        self.assertEqual([], list(self.output.iterdir()))

    def test_bad_executable_digest_publishes_nothing_and_cleans_temp_files(self) -> None:
        archive = self.make_archive(
            "opencode.tgz",
            [
                ("package/package.json", b"{}\n", "file"),
                ("package/bin/opencode", self.binary, "file"),
            ],
        )
        with self.assertRaisesRegex(
            VERIFIER.ArtifactVerificationError, "executable SHA-256 mismatch"
        ):
            self.verify_opencode(
                archive,
                self.opencode_lock(archive, executable_digest="0" * 64),
            )
        self.assertEqual([], list(self.output.iterdir()))
        self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main()
