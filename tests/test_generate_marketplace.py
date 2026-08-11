from __future__ import annotations

import importlib.util
import json
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
SPEC.loader.exec_module(GENERATOR)


class MarketplaceGenerationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = {
            "name": "grillmester",
            "version": "2.3.4",
            "description": "Canonical plugin description.",
            "author": {"name": "Team eSyfo"},
            "repository": "https://github.com/navikt/grillmester",
        }

    def test_development_catalog_uses_manifest_metadata_and_local_source(self) -> None:
        actual = GENERATOR.build_marketplace(
            self.manifest,
            mode="development",
        )

        self.assertEqual("grillmester", actual["name"])
        self.assertEqual({"name": "Team eSyfo"}, actual["owner"])
        self.assertEqual(
            {
                "description": "Canonical plugin description.",
                "version": "2.3.4",
            },
            actual["metadata"],
        )
        self.assertEqual(
            {
                "name": "grillmester",
                "description": "Canonical plugin description.",
                "version": "2.3.4",
                "source": "plugin",
            },
            actual["plugins"][0],
        )

    def test_release_catalog_pins_exact_github_sha_and_plugin_path(self) -> None:
        sha = "0123456789abcdef0123456789abcdef01234567"

        actual = GENERATOR.build_marketplace(
            self.manifest,
            mode="release",
            sha=sha,
        )

        self.assertEqual(
            {
                "source": "github",
                "repo": "navikt/grillmester",
                "path": "plugin",
                "sha": sha,
            },
            actual["plugins"][0]["source"],
        )
        self.assertNotIn("ref", actual["plugins"][0]["source"])

    def test_release_catalog_rejects_a_moving_ref(self) -> None:
        with self.assertRaisesRegex(
            GENERATOR.MarketplaceError,
            "40-character SHA",
        ):
            GENERATOR.build_marketplace(
                self.manifest,
                mode="release",
                sha="main",
            )

    def test_check_detects_drift_without_rewriting_the_catalog(self) -> None:
        expected = GENERATOR.render_marketplace(
            GENERATOR.build_marketplace(self.manifest, mode="development")
        )
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "marketplace.json"
            output.write_text('{"stale": true}\n', encoding="utf-8")
            before = output.read_bytes()

            with redirect_stderr(StringIO()):
                with self.assertRaisesRegex(
                    GENERATOR.MarketplaceError,
                    "catalog is stale",
                ):
                    GENERATOR.update_catalog(output, expected, check=True)

            self.assertEqual(before, output.read_bytes())

    def test_repository_must_be_a_canonical_github_repository_url(self) -> None:
        self.manifest["repository"] = "https://example.com/navikt/grillmester"

        with self.assertRaisesRegex(
            GENERATOR.MarketplaceError,
            "github.com",
        ):
            GENERATOR.build_marketplace(
                self.manifest,
                mode="release",
                sha="0123456789abcdef0123456789abcdef01234567",
            )

    def test_rendered_catalog_is_deterministic_json_with_a_final_newline(self) -> None:
        catalog = GENERATOR.build_marketplace(self.manifest, mode="development")

        rendered = GENERATOR.render_marketplace(catalog)

        self.assertTrue(rendered.endswith("\n"))
        self.assertEqual(catalog, json.loads(rendered))


if __name__ == "__main__":
    unittest.main()
