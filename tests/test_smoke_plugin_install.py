from __future__ import annotations

import importlib.util
import shutil
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
    def test_expected_inventory_matches_the_plugin_source(self) -> None:
        package = SMOKE.PACKAGES[0]
        self.assertEqual(
            len(list((ROOT / "plugin" / "agents").glob("*.agent.md"))),
            package.agents,
        )
        self.assertEqual(
            len([p for p in (ROOT / "plugin" / "skills").iterdir() if p.is_dir()]),
            package.skills,
        )
        # Upgrade fixtures are copied from the current source and keep its agents.
        self.assertEqual(package.agents, SMOKE.PREVIOUS_UNIFIED_PACKAGE.agents)
        self.assertEqual(package.agents, SMOKE.LEGACY_CORE.agents)

    def test_local_help_requires_the_complete_minimum_copilot_flag_roster(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with mock.patch.object(
                SMOKE,
                "run",
                return_value="\n".join(
                    (
                        "--plugin-dir",
                        "--agent",
                        "--model",
                        "--no-auto-update",
                        "--no-experimental",
                        "--no-remote",
                        "--no-remote-export",
                        "--disable-builtin-mcps",
                        "--secret-env-vars",
                        "--prompt",
                        "--allow-all-tools",
                        "--allow-all-paths",
                        "--allow-all-urls",
                        "--no-ask-user",
                        "--deny-tool",
                    )
                ),
            ) as run:
                SMOKE.verify_local_cli_help_surface(
                    "copilot",
                    {"HOME": str(root / "home")},
                    root,
                )

        command, environment, cwd = run.call_args.args
        self.assertEqual(["copilot", "--help"], command)
        self.assertEqual({"HOME": str(root / "home")}, environment)
        self.assertEqual(root, cwd)

    def test_local_help_fails_when_required_option_disappears(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            plugin = Path(temp)
            with mock.patch.object(SMOKE, "run", return_value="--plugin-dir\n"):
                with self.assertRaisesRegex(
                    RuntimeError, "omitted required local-run option"
                ):
                    SMOKE.verify_local_cli_help_surface("copilot", {}, plugin)

    def test_local_help_requires_exact_option_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            plugin = Path(temp)
            deceptive = "\n".join(
                (
                    "--plugin-dir",
                    "--agent",
                    "--model",
                    "--no-auto-update",
                    "--no-experimental",
                    "--no-remote-export",
                    "--disable-builtin-mcps",
                    "--secret-env-vars",
                    "--prompt",
                    "--allow-all-tools",
                    "--allow-all-paths",
                    "--allow-all-urls",
                    "--no-ask-user",
                    "--deny-tool",
                )
            )
            with mock.patch.object(SMOKE, "run", return_value=deceptive):
                with self.assertRaisesRegex(RuntimeError, "--no-remote"):
                    SMOKE.verify_local_cli_help_surface("copilot", {}, plugin)

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
                    *(
                        f"fixture-skill-{index}"
                        for index in range(
                            SMOKE.LEGACY_CORE.skills
                            - len(SMOKE.SAME_PACKAGE_REMOVED_SKILLS)
                        )
                    ),
                    *(
                        skill_id
                        for skill_id in SMOKE.LEGACY_ADD_ON_SKILLS
                        if skill_id not in SMOKE.HISTORICAL_REMOVED_SKILLS
                    ),
                    *SMOKE.CURRENT_ONLY_SKILLS,
                ]
                self.assertEqual(package.skills, len(skill_ids))
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

            (
                previous_plugins,
                previous_catalog,
                previous_unified_plugin,
                previous_unified_catalog,
                current_catalog,
            ) = (
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
            self.assertEqual(
                SMOKE.PREVIOUS_UNIFIED_VERSION,
                previous_unified_catalog["metadata"]["version"],
            )
            self.assertEqual(
                SMOKE.PREVIOUS_UNIFIED_VERSION,
                SMOKE.plugin_version(previous_unified_plugin),
            )
            self.assertEqual(
                SMOKE.PREVIOUS_UNIFIED_PACKAGE.skills,
                len(list((previous_unified_plugin / "skills").glob("*/SKILL.md"))),
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
            for skill_id in SMOKE.REMOVED_SKILLS:
                self.assertFalse((root / "plugin/skills" / skill_id).exists())
                self.assertFalse((staged / "plugin/skills" / skill_id).exists())
            for skill_id in SMOKE.SAME_PACKAGE_REMOVED_SKILLS:
                self.assertTrue(
                    (previous_unified_plugin / "skills" / skill_id / "SKILL.md").is_file()
                )
                self.assertTrue((core_skills / skill_id / "SKILL.md").is_file())
            for skill_id in SMOKE.HISTORICAL_REMOVED_SKILLS:
                self.assertFalse((previous_unified_plugin / "skills" / skill_id).exists())
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

    def test_removed_skills_are_rejected_from_current_installation(self) -> None:
        for skill_id in SMOKE.REMOVED_SKILLS:
            with self.subTest(skill_id=skill_id), tempfile.TemporaryDirectory() as temp:
                installed = Path(temp)
                removed = installed / "skills" / skill_id / "SKILL.md"
                removed.parent.mkdir(parents=True)
                removed.write_text("legacy\n", encoding="utf-8")

                with self.assertRaisesRegex(RuntimeError, "retained removed skill"):
                    SMOKE.assert_removed_skills_absent(installed)

    def test_removed_skill_check_only_applies_to_current_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            installed = Path(temp)
            SMOKE.write_json_object(
                installed / "plugin.json",
                {"name": SMOKE.PLUGIN_NAME},
            )
            for index in range(SMOKE.PACKAGES[0].agents):
                (installed / "agents").mkdir(exist_ok=True)
                (installed / "agents" / f"agent-{index}.agent.md").touch()
            for index in range(SMOKE.PREVIOUS_UNIFIED_PACKAGE.skills):
                skill = installed / "skills" / f"skill-{index}" / "SKILL.md"
                skill.parent.mkdir(parents=True)
                skill.touch()
            (installed / "LICENSE").touch()
            (installed / "THIRD_PARTY_NOTICES.md").touch()

            with mock.patch.object(
                SMOKE, "assert_payload_matches"
            ), mock.patch.object(SMOKE, "assert_removed_skills_absent") as removed:
                SMOKE.verify_installed_package(
                    installed,
                    installed,
                    SMOKE.PREVIOUS_UNIFIED_PACKAGE,
                )
                removed.assert_not_called()

                for index in range(SMOKE.PREVIOUS_UNIFIED_PACKAGE.skills, SMOKE.PACKAGES[0].skills):
                    skill = installed / "skills" / f"skill-{index}" / "SKILL.md"
                    skill.parent.mkdir(parents=True)
                    skill.touch()
                SMOKE.verify_installed_package(
                    installed,
                    installed,
                    SMOKE.PACKAGES[0],
                )
                removed.assert_called_once_with(installed)

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

    def test_toggle_retries_only_the_removed_plugin_selector(self) -> None:
        unsupported = subprocess.CompletedProcess([], 1, "error: unexpected argument '--plugin' found")
        success = subprocess.CompletedProcess([], 0, "")
        with mock.patch.object(SMOKE, "execute", side_effect=[unsupported, success]) as execute, \
             mock.patch.object(SMOKE, "enabled_setting", side_effect=[False, True]), \
             mock.patch.object(SMOKE, "run", side_effect=[
                 "grillmester@grillmester [disabled]", "", "grillmester@grillmester",
             ]) as run, redirect_stdout(StringIO()):
            self.assertTrue(SMOKE.try_toggle_lifecycle("copilot", {}, Path("/tmp"), Path("/tmp/home")))
        self.assertEqual(["copilot", "plugins", "disable", SMOKE.PLUGIN_SPEC], execute.call_args_list[-1].args[0])
        self.assertEqual(["copilot", "plugins", "enable", SMOKE.PLUGIN_SPEC], run.call_args_list[1].args[0])

    def test_toggle_listing_supports_both_formats_without_using_another_plugin_state(self) -> None:
        for marker in ("[disabled]", "(disabled)"):
            listing = f"  • {SMOKE.PLUGIN_SPEC} (v1.2.3) {marker}\n"
            SMOKE.assert_plugin_listing_state(listing, SMOKE.PACKAGES[0], enabled=False)
            with self.assertRaisesRegex(RuntimeError, "as enabled"):
                SMOKE.assert_plugin_listing_state(listing, SMOKE.PACKAGES[0], enabled=True)
            SMOKE.assert_plugin_listing_state(
                f"{SMOKE.PLUGIN_SPEC} (v1.2.3)\nother@grillmester {marker}",
                SMOKE.PACKAGES[0], enabled=True,
            )
        with self.assertRaises(RuntimeError):
            SMOKE.assert_plugin_listing_state(
                f"{SMOKE.PLUGIN_SPEC}-other (disabled)", SMOKE.PACKAGES[0], enabled=False,
            )

    def test_toggle_does_not_hide_an_unrelated_failure(self) -> None:
        failure = subprocess.CompletedProcess([], 1, "permission denied")
        with mock.patch.object(SMOKE, "execute", return_value=failure) as execute:
            with self.assertRaisesRegex(RuntimeError, "permission denied"):
                SMOKE.try_toggle_lifecycle("copilot", {}, Path("/tmp"), Path("/tmp/home"))
        self.assertEqual(1, execute.call_count)

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
            return_value=(8, 44),
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

        self.assertEqual((8, 44), result)
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

    def test_remote_install_allows_floating_marketplace_only_when_explicit(self) -> None:
        with mock.patch.object(
            SMOKE,
            "run",
            side_effect=["", "", "grillmester@grillmester", ""],
        ), mock.patch.object(
            SMOKE, "verify_installed_package", return_value=(8, 44)
        ), mock.patch.object(
            SMOKE, "enabled_setting", return_value=True
        ), mock.patch.object(SMOKE, "verify_uninstalled"):
            result = SMOKE.remote_install_smoke(
                copilot="copilot",
                env={"CI": "true"},
                cwd=Path("/tmp/work"),
                copilot_home=Path("/tmp/copilot-home"),
                marketplace_ref="navikt/grillmester#marketplace",
                expected_tag="v1.2.3",
                source_root=Path("/tmp/source"),
                allow_floating_marketplace=True,
            )

        self.assertEqual((8, 44), result)

    def test_remote_install_rejects_floating_marketplace_without_explicit_opt_in(
        self,
    ) -> None:
        with self.assertRaisesRegex(RuntimeError, "explicitly allowed floating"):
            SMOKE.remote_install_smoke(
                copilot="copilot",
                env={},
                cwd=Path("/tmp"),
                copilot_home=Path("/tmp/home"),
                marketplace_ref="navikt/grillmester#marketplace",
                expected_tag="v1.2.3",
                source_root=Path("/tmp"),
            )

    def test_cli_rejects_floating_marketplace_opt_in_without_remote_ref(self) -> None:
        with mock.patch.object(SMOKE.shutil, "which") as which:
            with mock.patch("sys.stderr", new_callable=StringIO) as error:
                self.assertEqual(
                    2,
                    SMOKE.main(["--allow-floating-marketplace"]),
                )
            which.assert_not_called()

        self.assertIn(
            "--allow-floating-marketplace requires --remote-marketplace-ref",
            error.getvalue(),
        )


class LocalInstallChecksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.marketplace = self.root / "marketplace"
        self.home = self.root / "copilot-home"
        self.package = SMOKE.PackageSpec("grillmester", "plugin", 0, 1, False)
        SMOKE.write_json_object(self.source / "plugin.json", {
            "name": self.package.name, "version": "1.2.3",
        })
        for name in ("LICENSE", "THIRD_PARTY_NOTICES.md", "skills/example/SKILL.md"):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture\n", encoding="utf-8")
        self.live = self.marketplace / "plugin"
        shutil.copytree(self.source, self.live)
        self.catalog("plugin")
        self.settings(True)
        self.checks = SMOKE.LocalInstallChecks(
            "copilot", {}, self.root, self.home, self.marketplace, [self.source],
        )
        self.row = {"name": self.package.name, "marketplace": SMOKE.MARKETPLACE_NAME,
                    "source": "live", "installedFrom": str(self.marketplace),
                    "version": "1.2.3", "enabled": True}
        self.skill = {"source": "plugin", "path": str(self.live / "skills/example"),
                      "name": "example", "enabled": True}

    def catalog(self, source: str) -> None:
        SMOKE.write_json_object(self.marketplace / ".github/plugin/marketplace.json", {
            "plugins": [{"name": self.package.name, "source": source}],
        })

    def settings(self, enabled: bool) -> None:
        SMOKE.write_json_object(self.home / "settings.json", {
            "enabledPlugins": {self.package.qualified_name: enabled},
        })

    def verify_live(self) -> None:
        with mock.patch.object(self.checks, "listing", side_effect=[[self.row], [self.skill]]):
            self.assertEqual((0, 1), self.checks.verify(self.source, self.package))

    def test_live_install_and_uninstall_verify_discovery_and_preserve_source(self) -> None:
        self.verify_live()
        before = SMOKE.tree_manifest(self.live)
        self.settings(False)
        with mock.patch.object(self.checks, "listing", side_effect=[[
            {**self.row, "enabled": False}], []
        ]):
            self.checks.uninstalled(self.package)
        self.assertEqual(before, SMOKE.tree_manifest(self.live))
        self.assertEqual({}, self.checks.active)
        # A removed marketplace entry may disappear completely; no skills may remain.
        with mock.patch.object(self.checks, "listing", side_effect=[[], []]):
            self.checks.uninstalled(self.package)

    def test_copied_install_keeps_byte_checks_without_requiring_json_cli(self) -> None:
        copied = self.checks.copied_path(self.package)
        shutil.copytree(self.source, copied)
        with mock.patch.object(self.checks, "listing") as listing:
            self.assertEqual((0, 1), self.checks.verify(self.source, self.package))
            listing.assert_not_called()
            (copied / "LICENSE").write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "changed: LICENSE"):
                self.checks.verify(self.source, self.package)
        self.assertEqual({}, self.checks.live)

    def test_copied_uninstall_still_requires_payload_and_settings_removal(self) -> None:
        copied = self.checks.copied_path(self.package)
        shutil.copytree(self.source, copied)
        with self.assertRaisesRegex(RuntimeError, "payload behind"):
            self.checks.uninstalled(self.package)
        shutil.rmtree(copied)
        SMOKE.write_json_object(self.home / "config.json", {"installedPlugins": []})
        with self.assertRaisesRegex(RuntimeError, "enabledPlugins"):
            self.checks.uninstalled(self.package)
        SMOKE.write_json_object(self.home / "settings.json", {"enabledPlugins": {}})
        self.checks.uninstalled(self.package)

    def test_copied_update_after_live_fixture_keeps_copied_uninstall_semantics(self) -> None:
        self.verify_live()
        copied = self.checks.copied_path(self.package)
        shutil.copytree(self.source, copied)
        with mock.patch.object(self.checks, "listing", return_value=[
            {**self.skill, "path": str(copied / "skills/example")}
        ]):
            self.checks.verify(self.source, self.package)
        self.assertNotIn(self.package.name, self.checks.live_mode)
        with mock.patch.object(SMOKE, "verify_uninstalled") as uninstalled, \
             mock.patch.object(self.checks, "listing", return_value=[]):
            self.checks.uninstalled(self.package)
        uninstalled.assert_called_once_with(self.home, copied, self.package)

    def test_live_registration_must_be_unique_enabled_and_from_isolated_marketplace(self) -> None:
        for rows, error in (
            ([], "did not enable"),
            ([{**self.row, "enabled": False}], "did not enable"),
            ([{**self.row, "version": "0.1.0"}], "wrong version"),
            ([{**self.row, "installedFrom": str(self.root)}], "registration source"),
            ([{**self.row, "installedFrom": "marketplace"}], "registration source"),
            ([{**self.row, "source": "other"}], "registration source"),
            ([self.row, self.row], "duplicate registration"),
        ):
            with self.subTest(rows=rows), mock.patch.object(self.checks, "listing", return_value=rows):
                with self.assertRaisesRegex(RuntimeError, error):
                    self.checks.verify(self.source, self.package)

    def test_live_source_must_stay_inside_marketplace(self) -> None:
        for path, error in (("../source", "escapes"), (".", "escapes"),
                            (str(self.source), "relative local")):
            self.catalog(path)
            with self.subTest(path=path), mock.patch.object(self.checks, "listing", return_value=[self.row]):
                with self.assertRaisesRegex(RuntimeError, error):
                    self.checks.verify(self.source, self.package)

    def test_live_payload_is_compared_with_snapshot_taken_before_install(self) -> None:
        # Even when the expected and live source are the same directory.
        checks = SMOKE.LocalInstallChecks(
            "copilot", {}, self.root, self.home, self.marketplace, [self.live],
        )
        (self.live / "LICENSE").write_text("client mutation", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "changed the source fixture"):
            checks.verify(self.live, self.package)

    def test_live_discovery_rejects_missing_stale_extra_disabled_and_renamed_skills(self) -> None:
        for rows in (
            [],
            [{**self.skill, "path": str(self.source / "skills/example")}],
            [self.skill, {**self.skill, "path": str(self.live / "skills/removed")}],
            [{**self.skill, "enabled": False}],
            [{**self.skill, "name": "wrong-name"}],
            [self.skill, self.skill],
        ):
            with self.subTest(rows=rows), mock.patch.object(self.checks, "listing", side_effect=[[self.row], rows]):
                with self.assertRaises(RuntimeError):
                    self.checks.verify(self.source, self.package)

    def test_live_uninstall_rejects_enabled_registration_or_remaining_skill(self) -> None:
        self.verify_live()
        self.settings(False)
        with mock.patch.object(self.checks, "listing", return_value=[self.row]):
            with self.assertRaisesRegex(RuntimeError, "live and enabled"):
                self.checks.uninstalled(self.package)
        with mock.patch.object(self.checks, "listing", side_effect=[[
            {**self.row, "enabled": False}], [self.skill]
        ]):
            with self.assertRaisesRegex(RuntimeError, "available plugin skills"):
                self.checks.uninstalled(self.package)

    def test_live_uninstall_rejects_changed_source(self) -> None:
        self.verify_live()
        self.settings(False)
        (self.live / "LICENSE").unlink()
        with mock.patch.object(self.checks, "listing", return_value=[{**self.row, "enabled": False}]):
            with self.assertRaisesRegex(RuntimeError, "changed the source fixture"):
                self.checks.uninstalled(self.package)

    def test_live_update_checks_actual_new_paths_instead_of_previous_directory(self) -> None:
        self.verify_live()
        updated = self.marketplace / "updated"
        shutil.copytree(self.live, updated)
        self.catalog("updated")
        with mock.patch.object(self.checks, "listing", side_effect=[[self.row], [self.skill]]):
            with self.assertRaisesRegex(RuntimeError, "available plugin skills"):
                self.checks.verify(self.source, self.package)
        with mock.patch.object(self.checks, "listing", side_effect=[[self.row], [
            {**self.skill, "path": str(updated / "skills/example")}
        ]]):
            self.checks.verify(self.source, self.package)
        self.assertEqual(updated.resolve(), self.checks.active[self.package.name])


if __name__ == "__main__":
    unittest.main()
