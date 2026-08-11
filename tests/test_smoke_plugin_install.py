from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_smoke_plugin_install", ROOT / "scripts/smoke_plugin_install.py"
)
assert SPEC and SPEC.loader
SMOKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SMOKE)


class PluginLifecycleSmokeTest(unittest.TestCase):
    def test_isolated_environment_drops_ambient_credentials(self) -> None:
        root = Path("/tmp/grillmester-smoke-env")
        env = SMOKE.isolated_cli_environment(
            {
                "PATH": "/usr/bin",
                "HTTPS_PROXY": "http://proxy.invalid",
                "GH_TOKEN": "secret-gh",
                "GITHUB_TOKEN": "secret-github",
                "COPILOT_GITHUB_TOKEN": "secret-copilot",
                "AWS_SECRET_ACCESS_KEY": "secret-aws",
                "COPILOT_CLI_ENABLED_FEATURE_FLAGS": "private-feature",
            },
            home=root / "home",
            copilot_home=root / "copilot",
            cache_home=root / "cache",
            xdg_home=root / "xdg",
            temp_files=root / "tmp",
        )

        self.assertEqual("/usr/bin", env["PATH"])
        self.assertEqual("http://proxy.invalid", env["HTTPS_PROXY"])
        for key in (
            "GH_TOKEN",
            "GITHUB_TOKEN",
            "COPILOT_GITHUB_TOKEN",
            "AWS_SECRET_ACCESS_KEY",
            "COPILOT_CLI_ENABLED_FEATURE_FLAGS",
        ):
            self.assertNotIn(key, env)

    def test_upgrade_fixture_uses_distinct_versions_and_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            plugin = root / "plugin"
            plugin.mkdir(parents=True)
            SMOKE.write_json_object(
                plugin / "plugin.json",
                {"name": SMOKE.PLUGIN_NAME, "version": "1.2.3"},
            )
            (plugin / "payload.txt").write_text("current\n", encoding="utf-8")
            SMOKE.write_json_object(
                root / ".github/plugin/marketplace.json",
                {
                    "name": SMOKE.MARKETPLACE_NAME,
                    "metadata": {"version": "1.2.3"},
                    "plugins": [
                        {
                            "name": SMOKE.PLUGIN_NAME,
                            "version": "1.2.3",
                            "source": "plugin",
                        }
                    ],
                },
            )
            staged = Path(temp) / "staged"

            previous_plugin, previous_catalog, current_catalog = (
                SMOKE.prepare_upgrade_marketplace(root, plugin, staged)
            )

            self.assertEqual(
                SMOKE.PREVIOUS_VERSION,
                SMOKE.plugin_version(previous_plugin),
            )
            self.assertEqual(
                SMOKE.PREVIOUS_SOURCE,
                previous_catalog["plugins"][0]["source"],
            )
            self.assertEqual(
                SMOKE.PREVIOUS_VERSION,
                previous_catalog["plugins"][0]["version"],
            )
            self.assertEqual("plugin", current_catalog["plugins"][0]["source"])
            self.assertEqual("1.2.3", current_catalog["plugins"][0]["version"])
            self.assertTrue((previous_plugin / SMOKE.UPGRADE_SENTINEL).is_file())
            self.assertEqual(
                SMOKE.tree_manifest(plugin),
                SMOKE.tree_manifest(staged / "plugin"),
            )

    def test_catalog_activation_uses_public_marketplace_update_command(self) -> None:
        catalog = {
            "name": SMOKE.MARKETPLACE_NAME,
            "plugins": [{"name": SMOKE.PLUGIN_NAME, "source": "plugin"}],
        }
        env = {"CI": "true"}
        cwd = Path("/tmp/work")
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(
            SMOKE, "run"
        ) as run:
            staged = Path(temp)
            SMOKE.activate_marketplace_catalog(
                catalog,
                staged,
                "copilot",
                env,
                cwd,
            )

            self.assertEqual(
                catalog,
                SMOKE.load_json_object(
                    staged / ".github/plugin/marketplace.json"
                ),
            )
            run.assert_called_once_with(
                [
                    "copilot",
                    "plugin",
                    "marketplace",
                    "update",
                    SMOKE.MARKETPLACE_NAME,
                ],
                env,
                cwd,
            )

    def test_release_source_must_pin_expected_checkout_sha(self) -> None:
        sha = "0123456789abcdef0123456789abcdef01234567"
        source = {
            "source": "github",
            "repo": "navikt/grillmester",
            "path": "plugin",
            "sha": sha,
        }

        self.assertEqual(
            sha,
            SMOKE.validate_catalog_source(
                source,
                expected_release_sha=sha,
                checkout_sha=sha,
            ),
        )

    def test_release_source_rejects_a_different_checkout(self) -> None:
        source_sha = "0123456789abcdef0123456789abcdef01234567"
        checkout_sha = "89abcdef0123456789abcdef0123456789abcdef"
        source = {
            "source": "github",
            "repo": "navikt/grillmester",
            "path": "plugin",
            "sha": source_sha,
        }

        with self.assertRaisesRegex(RuntimeError, "checkout HEAD"):
            SMOKE.validate_catalog_source(
                source,
                expected_release_sha=source_sha,
                checkout_sha=checkout_sha,
            )

    def test_release_expectation_rejects_development_source(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "immutable GitHub source"):
            SMOKE.validate_catalog_source(
                "plugin",
                expected_release_sha="0123456789abcdef0123456789abcdef01234567",
                checkout_sha="0123456789abcdef0123456789abcdef01234567",
            )

    def test_payload_comparison_detects_changed_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            expected = root / "expected"
            actual = root / "actual"
            expected.mkdir()
            actual.mkdir()
            (expected / "plugin.json").write_text("expected", encoding="utf-8")
            (actual / "plugin.json").write_text("changed", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "changed: plugin.json"):
                SMOKE.assert_payload_matches(expected, actual)

    def test_unavailable_documented_toggle_is_an_explicit_skip(self) -> None:
        unavailable = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="The plugins command is not available.\n",
        )
        with mock.patch.object(SMOKE, "execute", side_effect=[unavailable, unavailable]):
            output = StringIO()
            with redirect_stdout(output):
                tested = SMOKE.try_toggle_lifecycle(
                    "copilot",
                    {},
                    Path("/tmp"),
                    Path("/tmp/not-read-on-skip"),
                )

        self.assertFalse(tested)
        self.assertIn("SKIP enable/disable", output.getvalue())


if __name__ == "__main__":
    unittest.main()
