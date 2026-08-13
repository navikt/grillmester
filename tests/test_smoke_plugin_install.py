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
    def test_release_semver_is_strict_and_linear(self) -> None:
        for version in ("0.3.0-poc.2", "1.2.3", "1.2.3-rc.0"):
            with self.subTest(version=version):
                self.assertTrue(SMOKE.is_strict_semver(version))
        for version in (
            "01.2.3",
            "1.2.3+rebuilt",
            "1.2.3-rc.01",
            "0.0.0-0." + "--." * 2_000,
        ):
            with self.subTest(version=version):
                self.assertFalse(SMOKE.is_strict_semver(version))

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
                (plugin / "LICENSE").write_text("fixture license\n", encoding="utf-8")
                (plugin / "THIRD_PARTY_NOTICES.md").write_text(
                    "fixture notices\n", encoding="utf-8"
                )
                skill_ids = [
                    *(f"fixture-skill-{index}" for index in range(34)),
                    *SMOKE.LEGACY_ADD_ON_SKILLS,
                ]
                for skill_id in skill_ids:
                    skill = plugin / "skills" / skill_id / "SKILL.md"
                    skill.parent.mkdir(parents=True)
                    skill.write_text(f"---\nname: {skill_id}\n---\n", encoding="utf-8")
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
                SMOKE.prepare_upgrade_marketplace(
                    root / ".github/plugin/marketplace.json", root, staged
                )
            )

            self.assertEqual(
                [package.name for package in SMOKE.PREVIOUS_PACKAGES],
                [entry["name"] for entry in previous_catalog["plugins"]],
            )
            self.assertEqual(
                [SMOKE.PLUGIN_NAME],
                [entry["name"] for entry in current_catalog["plugins"]],
            )
            for package, previous_entry in zip(
                SMOKE.PREVIOUS_PACKAGES, previous_catalog["plugins"], strict=True
            ):
                previous_plugin = previous_plugins[package.name]
                self.assertEqual(
                    SMOKE.PREVIOUS_VERSION,
                    SMOKE.plugin_version(previous_plugin),
                )
                self.assertEqual(f"previous-{package.path}", previous_entry["source"])
                self.assertEqual(SMOKE.PREVIOUS_VERSION, previous_entry["version"])
                self.assertEqual(
                    package.skills,
                    len(list((previous_plugin / "skills").glob("*/SKILL.md"))),
                )
            self.assertTrue(
                (previous_plugins[SMOKE.PLUGIN_NAME] / SMOKE.UPGRADE_SENTINEL).is_file()
            )
            self.assertEqual("plugin", current_catalog["plugins"][0]["source"])
            self.assertEqual("1.2.3", current_catalog["plugins"][0]["version"])
            self.assertEqual(
                SMOKE.tree_manifest(root / "plugin"),
                SMOKE.tree_manifest(staged / "plugin"),
            )
            core_skills = previous_plugins[SMOKE.LEGACY_CORE.name] / "skills"
            add_on_skills = previous_plugins[SMOKE.LEGACY_ADD_ON.name] / "skills"
            for skill_id in SMOKE.LEGACY_ADD_ON_SKILLS:
                self.assertFalse((core_skills / skill_id).exists())
                self.assertTrue((add_on_skills / skill_id / "SKILL.md").is_file())

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

    def test_release_source_rejects_noncanonical_plugin_path(self) -> None:
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
        sources["grillmester"] = {**sources["grillmester"], "path": "."}

        with self.assertRaisesRegex(RuntimeError, "pinned source shape"):
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

    def test_remote_install_uses_reviewed_release_tag_and_cleans_up(self) -> None:
        tag = "v1.2.3"
        copilot_home = Path("/tmp/copilot-home")
        installed = copilot_home / "installed-plugins" / SMOKE.MARKETPLACE_NAME
        with mock.patch.object(
            SMOKE,
            "run",
            side_effect=[
                "",
                "",
                "\n".join(package.qualified_name for package in SMOKE.PACKAGES),
                "",
            ],
        ) as run, mock.patch.object(
            SMOKE,
            "verify_installed_package",
            return_value=(7, 44),
        ) as verify, mock.patch.object(
            SMOKE, "enabled_setting", return_value=True
        ), mock.patch.object(SMOKE, "verify_uninstalled") as uninstalled:
            result = SMOKE.remote_install_smoke(
                copilot="copilot",
                env={"CI": "true"},
                cwd=Path("/tmp/work"),
                copilot_home=copilot_home,
                marketplace_ref=f"navikt/grillmester#{tag}",
                expected_tag=tag,
                source_root=Path("/tmp/source"),
            )

        self.assertEqual((7, 44), result)
        self.assertEqual(
            [
                "copilot",
                "plugin",
                "marketplace",
                "add",
                f"navikt/grillmester#{tag}",
            ],
            run.call_args_list[0].args[0],
        )
        self.assertEqual(1, verify.call_count)
        self.assertEqual(1, uninstalled.call_count)
        verify.assert_called_once_with(
            Path("/tmp/source/plugin"), installed / "grillmester", SMOKE.PACKAGES[0]
        )
        uninstalled.assert_called_once_with(
            copilot_home,
            installed / "grillmester",
            SMOKE.PACKAGES[0],
        )

    def test_remote_install_rejects_raw_sha_and_moving_main_ref(self) -> None:
        raw_sha = "0123456789abcdef0123456789abcdef01234567"
        for ref in (raw_sha, "main"):
            with self.subTest(ref=ref), self.assertRaisesRegex(
                RuntimeError, "reviewed release tag v1.2.3"
            ):
                SMOKE.remote_install_smoke(
                    copilot="copilot",
                    env={},
                    cwd=Path("/tmp"),
                    copilot_home=Path("/tmp/home"),
                    marketplace_ref=f"navikt/grillmester#{ref}",
                    expected_tag="v1.2.3",
                    source_root=Path("/tmp"),
                )


if __name__ == "__main__":
    unittest.main()
