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
            for package in SMOKE.PACKAGES:
                plugin = root / package.path
                plugin.mkdir(parents=True)
                SMOKE.write_json_object(
                    plugin / "plugin.json",
                    {"name": package.name, "version": "1.2.3"},
                )
                (plugin / "payload.txt").write_text("current\n", encoding="utf-8")
            SMOKE.write_json_object(
                root / ".github/plugin/marketplace.json",
                {
                    "name": SMOKE.MARKETPLACE_NAME,
                    "metadata": {"version": "1.2.3"},
                    "plugins": [
                        {
                            "name": package.name,
                            "version": "1.2.3",
                            "source": package.path,
                        }
                        for package in SMOKE.PACKAGES
                    ],
                },
            )
            staged = Path(temp) / "staged"

            previous_plugins, previous_catalog, current_catalog = (
                SMOKE.prepare_upgrade_marketplace(root, root, staged)
            )

            for package, previous_entry, current_entry in zip(
                SMOKE.PACKAGES,
                previous_catalog["plugins"],
                current_catalog["plugins"],
                strict=True,
            ):
                previous_plugin = previous_plugins[package.name]
                self.assertEqual(
                    SMOKE.PREVIOUS_VERSION,
                    SMOKE.plugin_version(previous_plugin),
                )
                self.assertEqual(f"previous-{package.path}", previous_entry["source"])
                self.assertEqual(SMOKE.PREVIOUS_VERSION, previous_entry["version"])
                self.assertEqual(package.path, current_entry["source"])
                self.assertEqual("1.2.3", current_entry["version"])
                self.assertTrue((previous_plugin / SMOKE.UPGRADE_SENTINEL).is_file())
                self.assertEqual(
                    SMOKE.tree_manifest(root / package.path),
                    SMOKE.tree_manifest(staged / package.path),
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

    def test_release_sources_reject_cross_package_path_or_sha_drift(self) -> None:
        sha = "0123456789abcdef0123456789abcdef01234567"
        sources = {
            package.name: {
                "source": "github",
                "repo": SMOKE.PLUGIN_REPOSITORY,
                "path": package.path,
                "sha": sha,
            }
            for package in SMOKE.PACKAGES
        }
        sources["grillmester-nav"] = {
            **sources["grillmester-nav"],
            "path": "plugin",
        }

        with self.assertRaisesRegex(RuntimeError, "pinned shapes"):
            SMOKE.validate_catalog_sources(
                sources,
                expected_release_sha=sha,
                checkout_sha=sha,
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

    def test_remote_install_uses_exact_catalog_ref_and_cleans_up(self) -> None:
        sha = "0123456789abcdef0123456789abcdef01234567"
        copilot_home = Path("/tmp/copilot-home")
        installed = copilot_home / "installed-plugins" / SMOKE.MARKETPLACE_NAME
        with mock.patch.object(
            SMOKE,
            "run",
            side_effect=[
                "",
                "",
                "",
                "\n".join(package.qualified_name for package in SMOKE.PACKAGES),
                "",
                "",
            ],
        ) as run, mock.patch.object(
            SMOKE,
            "verify_installed_package",
            side_effect=[(7, 34), (0, 10)],
        ) as verify, mock.patch.object(
            SMOKE, "enabled_setting", return_value=True
        ), mock.patch.object(SMOKE, "verify_uninstalled") as uninstalled:
            result = SMOKE.remote_install_smoke(
                copilot="copilot",
                env={"CI": "true"},
                cwd=Path("/tmp/work"),
                copilot_home=copilot_home,
                marketplace_ref=f"navikt/grillmester#{sha}",
                source_root=Path("/tmp/source"),
            )

        self.assertEqual((7, 44), result)
        self.assertEqual(
            [
                "copilot",
                "plugin",
                "marketplace",
                "add",
                f"navikt/grillmester#{sha}",
            ],
            run.call_args_list[0].args[0],
        )
        self.assertEqual(2, verify.call_count)
        self.assertEqual(2, uninstalled.call_count)
        verify.assert_any_call(
            Path("/tmp/source/plugin"), installed / "grillmester", SMOKE.PACKAGES[0]
        )
        verify.assert_any_call(
            Path("/tmp/source/plugin-nav"),
            installed / "grillmester-nav",
            SMOKE.PACKAGES[1],
        )
        uninstalled.assert_any_call(
            copilot_home,
            installed / "grillmester-nav",
            SMOKE.PACKAGES[1],
        )
        uninstalled.assert_any_call(
            copilot_home,
            installed / "grillmester",
            SMOKE.PACKAGES[0],
        )

    def test_remote_install_rejects_a_moving_ref(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "full catalog SHA"):
            SMOKE.remote_install_smoke(
                copilot="copilot",
                env={},
                cwd=Path("/tmp"),
                copilot_home=Path("/tmp/home"),
                marketplace_ref="navikt/grillmester#main",
                source_root=Path("/tmp"),
            )


if __name__ == "__main__":
    unittest.main()
