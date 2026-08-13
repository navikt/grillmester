from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_generate_marketplace", ROOT / "scripts/generate_marketplace.py"
)
assert SPEC and SPEC.loader
GENERATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GENERATOR
SPEC.loader.exec_module(GENERATOR)


class MarketplaceGenerationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.package_manifest = {
            "schemaVersion": 1,
            "marketplace": {
                "name": "grillmester",
                "description": "Canonical marketplace description.",
                "owner": "Team eSyfo",
            },
        }
        self.packages = [
            GENERATOR.Package(
                name="grillmester",
                path="plugin",
                manifest={
                    "name": "grillmester",
                    "version": "2.3.4",
                    "description": "Agent team.",
                    "author": {"name": "Team eSyfo"},
                    "repository": "https://github.com/navikt/grillmester",
                },
            ),
            GENERATOR.Package(
                name="grillmester-nav",
                path="plugin-nav",
                manifest={
                    "name": "grillmester-nav",
                    "version": "2.3.4",
                    "description": "NAV add-on.",
                    "author": {"name": "Team eSyfo"},
                    "repository": "https://github.com/navikt/grillmester",
                },
            ),
        ]

    def test_development_catalog_has_two_local_disjoint_packages(self) -> None:
        actual = GENERATOR.build_marketplace(
            self.package_manifest, self.packages, mode="development"
        )
        self.assertEqual("grillmester", actual["name"])
        self.assertEqual({"name": "Team eSyfo"}, actual["owner"])
        self.assertEqual("2.3.4", actual["metadata"]["version"])
        self.assertEqual(
            [
                {
                    "name": "grillmester",
                    "description": "Agent team.",
                    "version": "2.3.4",
                    "source": "plugin",
                },
                {
                    "name": "grillmester-nav",
                    "description": "NAV add-on.",
                    "version": "2.3.4",
                    "source": "plugin-nav",
                },
            ],
            actual["plugins"],
        )

    def test_release_catalog_pins_both_paths_to_one_exact_sha(self) -> None:
        sha = "0123456789abcdef0123456789abcdef01234567"
        actual = GENERATOR.build_marketplace(
            self.package_manifest, self.packages, mode="release", sha=sha
        )
        self.assertEqual(
            [
                {
                    "source": "github",
                    "repo": "navikt/grillmester",
                    "path": "plugin",
                    "sha": sha,
                },
                {
                    "source": "github",
                    "repo": "navikt/grillmester",
                    "path": "plugin-nav",
                    "sha": sha,
                },
            ],
            [entry["source"] for entry in actual["plugins"]],
        )

    def test_release_catalog_rejects_a_moving_ref(self) -> None:
        with self.assertRaisesRegex(GENERATOR.MarketplaceError, "40-character SHA"):
            GENERATOR.build_marketplace(
                self.package_manifest,
                self.packages,
                mode="release",
                sha="main",
            )

    def test_packages_must_share_one_version(self) -> None:
        self.packages[1].manifest["version"] = "2.3.5"
        with self.assertRaisesRegex(GENERATOR.MarketplaceError, "same version"):
            GENERATOR.build_marketplace(
                self.package_manifest, self.packages, mode="development"
            )

    def test_check_detects_drift_without_rewriting_catalog(self) -> None:
        expected = GENERATOR.render_marketplace(
            GENERATOR.build_marketplace(
                self.package_manifest, self.packages, mode="development"
            )
        )
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "marketplace.json"
            output.write_text('{"stale": true}\n', encoding="utf-8")
            before = output.read_bytes()
            with redirect_stderr(StringIO()):
                with self.assertRaisesRegex(
                    GENERATOR.MarketplaceError, "catalog is stale"
                ):
                    GENERATOR.update_catalog(output, expected, check=True)
            self.assertEqual(before, output.read_bytes())

    def test_repository_must_be_a_canonical_github_repository_url(self) -> None:
        self.packages[1].manifest["repository"] = "https://example.com/grillmester"
        with self.assertRaisesRegex(GENERATOR.MarketplaceError, "github.com"):
            GENERATOR.build_marketplace(
                self.package_manifest, self.packages, mode="release", sha="0" * 40
            )

    def test_rendered_catalog_is_deterministic_json_with_final_newline(self) -> None:
        catalog = GENERATOR.build_marketplace(
            self.package_manifest, self.packages, mode="development"
        )
        rendered = GENERATOR.render_marketplace(catalog)
        self.assertTrue(rendered.endswith("\n"))
        self.assertEqual(catalog, json.loads(rendered))


if __name__ == "__main__":
    unittest.main()
