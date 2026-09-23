from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
import unittest
from pathlib import Path


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

    def test_live_rights_scope_matches_the_committed_journal(self) -> None:
        approval = json.loads(
            (ROOT / BUMP.CONTRACT.STABLE_RIGHTS_APPROVAL_PATH).read_text(encoding="utf-8")
        )
        self.assertEqual(approval["scope"], BUMP.CONTRACT.current_rights_scope(ROOT))


if __name__ == "__main__":
    unittest.main()
