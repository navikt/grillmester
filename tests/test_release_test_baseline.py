from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import stat
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_release_test_baseline",
    ROOT / "scripts/release_test_baseline.py",
)
assert SPEC and SPEC.loader
BASELINE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BASELINE
SPEC.loader.exec_module(BASELINE)


def archive_fixture(executable: bytes) -> tuple[bytes, dict[str, object]]:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz", format=tarfile.USTAR_FORMAT) as archive:
        info = tarfile.TarInfo("client")
        info.size = len(executable)
        info.mode = 0o755
        archive.addfile(info, io.BytesIO(executable))
    content = stream.getvalue()
    return content, {
        "url": "https://example.invalid/client.tar.gz",
        "archiveSize": len(content),
        "archiveDigest": f"sha256:{hashlib.sha256(content).hexdigest()}",
        "roster": ["client"],
        "executablePath": "client",
        "executableSize": len(executable),
        "executableSha256": hashlib.sha256(executable).hexdigest(),
    }


class ReleaseTestBaselineTest(unittest.TestCase):
    def test_contract_separates_runtime_support_from_exact_test_clients(self) -> None:
        contract = BASELINE.CONTRACT
        self.assertEqual(1, contract["schemaVersion"])
        self.assertEqual("1.18.20", contract["standardSupport"]["opencodeMinimum"])
        self.assertEqual("1.0.79", contract["standardSupport"]["copilotMinimum"])
        self.assertEqual("1.18.20", contract["releaseTest"]["opencodeVersion"])
        self.assertEqual("1.0.80", contract["releaseTest"]["copilotVersion"])
        for client in ("opencode", "copilot", "cplt"):
            self.assertTrue(
                any(key.startswith(f"{client}:") for key in contract["artifacts"]),
                client,
            )

    def test_github_env_is_machine_readable_and_json_is_complete(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, BASELINE.main(["github-env"]))
        values = dict(line.split("=", 1) for line in output.getvalue().splitlines())
        self.assertEqual("1.18.20", values["RELEASE_TEST_OPENCODE_VERSION"])
        self.assertEqual("1.0.79", values["RELEASE_TEST_COPILOT_MINIMUM"])

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, BASELINE.main(["json"]))
        self.assertEqual(BASELINE.CONTRACT, json.loads(output.getvalue()))

    def test_verify_extracts_only_the_digest_bound_executable(self) -> None:
        executable = b"#!/bin/sh\necho ok\n"
        archive, record = archive_fixture(executable)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "client.tar.gz"
            output = root / "bin/client"
            source.write_bytes(archive)
            BASELINE.verify_and_extract(record, source, output)
            self.assertEqual(executable, output.read_bytes())
            self.assertEqual(0o555, stat.S_IMODE(output.stat().st_mode))

    def test_verify_rejects_digest_roster_and_existing_output(self) -> None:
        archive, record = archive_fixture(b"client")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "client.tar.gz"
            source.write_bytes(archive)

            changed_digest = dict(record, archiveDigest="sha256:" + "0" * 64)
            with self.assertRaisesRegex(BASELINE.BaselineError, "archive digest"):
                BASELINE.verify_and_extract(changed_digest, source, root / "digest")

            changed_roster = dict(record, roster=["other"])
            with self.assertRaisesRegex(BASELINE.BaselineError, "archive roster"):
                BASELINE.verify_and_extract(changed_roster, source, root / "roster")

            existing = root / "existing"
            existing.write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                BASELINE.verify_and_extract(record, source, existing)
            self.assertEqual("keep", existing.read_text(encoding="utf-8"))

    def test_download_ignores_ambient_curl_configuration_then_verifies(self) -> None:
        archive, record = archive_fixture(b"client")

        def fake_curl(command: list[str], *, check: bool) -> object:
            self.assertFalse(check)
            self.assertEqual("curl", command[0])
            self.assertEqual(["--config", "/dev/null"], command[1:3])
            Path(command[command.index("--output") + 1]).write_bytes(archive)
            return type("Result", (), {"returncode": 0})()

        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            BASELINE.subprocess, "run", side_effect=fake_curl
        ):
            output = Path(temporary) / "bin/client"
            BASELINE.download_and_install(record, output)
            self.assertEqual(b"client", output.read_bytes())


if __name__ == "__main__":
    unittest.main()
