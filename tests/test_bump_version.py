from __future__ import annotations

import datetime as dt
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_bump_version", ROOT / "scripts/bump_version.py"
)
assert SPEC and SPEC.loader
BUMP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BUMP
SPEC.loader.exec_module(BUMP)


class BumpVersionTest(unittest.TestCase):
    def test_semver_bumps(self) -> None:
        for current, bump, expected in (
            ("0.4.1", "patch", "0.4.2"),
            ("0.4.1", "minor", "0.5.0"),
            ("0.4.1", "major", "1.0.0"),
            ("0.5.0-rc.1", "patch", "0.5.0"),
            ("0.5.0-rc.1", "minor", "0.5.0"),
            ("0.5.1-rc.1", "minor", "0.6.0"),
            ("1.0.0-rc.1", "major", "1.0.0"),
            ("1.1.0-rc.1", "major", "2.0.0"),
            ("0.4.1", "0.5.0-rc.1", "0.5.0-rc.1"),
            ("0.5.0-rc.2", "0.5.0-rc.10", "0.5.0-rc.10"),
        ):
            with self.subTest(current=current, bump=bump):
                self.assertEqual(expected, BUMP.next_version(current, bump))

    def test_rejects_versions_that_do_not_move_forward(self) -> None:
        for current, bump in (
            ("0.4.1", "0.4.1"),
            ("0.4.1", "0.4.0"),
            ("0.5.0", "0.5.0-rc.1"),
            ("0.5.0-rc.10", "0.5.0-rc.2"),
        ):
            with self.subTest(current=current, bump=bump):
                with self.assertRaises(BUMP.BumpError):
                    BUMP.next_version(current, bump)
        with self.assertRaises(BUMP.CONTRACT.ReleaseContractError):
            BUMP.next_version("0.4.1", "0.5.0+build")

    def test_rewrites_only_the_version_field(self) -> None:
        manifest = '{\n  "name": "grillmester",\n  "version": "0.4.1"\n}\n'
        self.assertEqual(
            '{\n  "name": "grillmester",\n  "version": "0.4.2"\n}\n',
            BUMP.rewrite_version(manifest, "0.4.1", "0.4.2"),
        )
        with self.assertRaises(BUMP.BumpError):
            BUMP.rewrite_version(manifest, "0.4.0", "0.4.2")

    def test_rebinds_rights_under_a_named_review(self) -> None:
        approval = json.loads(
            (ROOT / BUMP.CONTRACT.STABLE_RIGHTS_APPROVAL_PATH).read_text(encoding="utf-8")
        )
        scope = BUMP.CONTRACT.current_rights_scope(ROOT)
        rebound = BUMP.rebind_rights(
            approval, scope, "navikt/grillmester#99", dt.date(2026, 9, 23)
        )
        self.assertEqual(scope, rebound["scope"])
        for decision in rebound["decisions"].values():
            self.assertEqual(
                "underlying decision: navikt/grillmester#56; "
                "current-content review: navikt/grillmester#99",
                decision["decisionReference"],
            )
            self.assertEqual("2026-09-23", decision["date"])
        self.assertNotEqual(approval, rebound)
        for invalid in ("#99", "grillmester 99", "navikt/grillmester#56"):
            with self.subTest(review=invalid):
                with self.assertRaises(BUMP.BumpError):
                    BUMP.rebind_rights(approval, scope, invalid, dt.date(2026, 9, 23))

    def _fixture(self, root: Path) -> Path:
        manifest = root / "plugin/plugin.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text('{\n  "name": "grillmester",\n  "version": "0.4.1"\n}\n')
        return manifest

    def test_refuses_before_writing_when_rights_scope_changed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self._fixture(root)
            before = manifest.read_text()
            stderr = io.StringIO()
            with mock.patch.object(BUMP, "_rights_are_current", return_value=False), \
                    mock.patch.object(BUMP.subprocess, "run") as run, \
                    redirect_stderr(stderr):
                status = BUMP.main(["patch", "--root", str(root)])
            self.assertEqual(2, status)
            self.assertIn("--rights-review", stderr.getvalue())
            self.assertEqual(before, manifest.read_text())
            run.assert_not_called()

    def test_bumps_then_regenerates_in_contract_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self._fixture(root)
            with mock.patch.object(BUMP, "_rights_are_current", return_value=True), \
                    mock.patch.object(BUMP.subprocess, "run") as run, \
                    redirect_stdout(io.StringIO()):
                status = BUMP.main(["minor", "--root", str(root)])
            self.assertEqual(0, status)
            self.assertIn('"version": "0.5.0"', manifest.read_text())
            self.assertEqual(
                [call.args[0][1] for call in run.call_args_list],
                [
                    "scripts/generate_copilot_manifest.py",
                    "scripts/generate_opencode.py",
                    "scripts/generate_context_projections.py",
                    "scripts/generate_agentpakke_manifest.py",
                    "scripts/generate_marketplace.py",
                ],
            )
            for call in run.call_args_list:
                self.assertEqual(root, call.kwargs["cwd"])

    def test_reports_a_failed_generator_without_a_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            stderr = io.StringIO()
            failure = subprocess.CalledProcessError(1, ["generate"])
            with mock.patch.object(BUMP, "_rights_are_current", return_value=True), \
                    mock.patch.object(BUMP.subprocess, "run", side_effect=failure), \
                    redirect_stderr(stderr):
                status = BUMP.main(["patch", "--root", str(root)])
            self.assertEqual(1, status)
            self.assertIn("revert the partial bump", stderr.getvalue())

    def test_live_rights_scope_matches_the_committed_journal(self) -> None:
        approval = json.loads(
            (ROOT / BUMP.CONTRACT.STABLE_RIGHTS_APPROVAL_PATH).read_text(encoding="utf-8")
        )
        self.assertEqual(approval["scope"], BUMP.CONTRACT.current_rights_scope(ROOT))


if __name__ == "__main__":
    unittest.main()
