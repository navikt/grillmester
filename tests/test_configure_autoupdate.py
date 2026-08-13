from __future__ import annotations

import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_configure_autoupdate",
    ROOT / "scripts/configure_autoupdate.py",
)
assert SPEC and SPEC.loader
AUTUPDATE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUTUPDATE
SPEC.loader.exec_module(AUTUPDATE)


class ConfigureAutoupdateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "copilot-home"
        self.settings = self.home / "settings.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_settings(self, content: str, mode: int = 0o600) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(content, encoding="utf-8")
        self.settings.chmod(mode)

    def read_settings(self) -> dict[str, object]:
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def test_creates_private_settings_with_the_floating_update_channel(self) -> None:
        result = AUTUPDATE.configure(self.home)

        self.assertTrue(result.changed)
        self.assertIsNone(result.backup_path)
        self.assertEqual(
            self.read_settings(),
            {
                "extraKnownMarketplaces": {
                    "grillmester": {
                        "source": AUTUPDATE.EXPECTED_SOURCE,
                        "autoUpdate": True,
                    }
                },
                "enabledPlugins": {"grillmester@grillmester": True},
            },
        )
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o600)

    def test_merges_unknown_settings_and_backs_up_the_original_bytes(self) -> None:
        original = json.dumps(
            {
                "theme": "dark",
                "extraKnownMarketplaces": {
                    "another": {"source": {"source": "github", "repo": "x/y"}},
                    "grillmester": {
                        "source": AUTUPDATE.EXPECTED_SOURCE,
                        "autoUpdate": False,
                        "futureField": "preserve me",
                    },
                },
                "enabledPlugins": {
                    "another@another": True,
                    "grillmester@grillmester": False,
                },
            },
            separators=(",", ":"),
        ) + "\n"
        self.write_settings(original, mode=0o644)

        result = AUTUPDATE.configure(self.home)

        self.assertEqual(
            result.backup_path, self.settings.with_name("settings.json.bak")
        )
        assert result.backup_path is not None
        self.assertEqual(result.backup_path.read_bytes(), original.encode("utf-8"))
        self.assertEqual(stat.S_IMODE(result.backup_path.stat().st_mode), 0o600)
        updated = self.read_settings()
        self.assertEqual(updated["theme"], "dark")
        self.assertIn("another", updated["extraKnownMarketplaces"])
        self.assertEqual(
            updated["extraKnownMarketplaces"]["grillmester"]["futureField"],
            "preserve me",
        )
        self.assertTrue(
            updated["extraKnownMarketplaces"]["grillmester"]["autoUpdate"]
        )
        self.assertTrue(updated["enabledPlugins"]["grillmester@grillmester"])
        self.assertTrue(updated["enabledPlugins"]["another@another"])
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o600)

    def test_second_run_is_a_noop_without_another_backup(self) -> None:
        AUTUPDATE.configure(self.home)
        first_bytes = self.settings.read_bytes()
        first_stat = self.settings.stat()

        result = AUTUPDATE.configure(self.home)

        self.assertFalse(result.changed)
        self.assertEqual(self.settings.read_bytes(), first_bytes)
        self.assertEqual(self.settings.stat().st_ino, first_stat.st_ino)
        self.assertEqual(list(self.home.glob("settings.json.bak*")), [])

    def test_existing_backup_is_never_overwritten(self) -> None:
        self.write_settings("{}\n")
        first_backup = self.settings.with_name("settings.json.bak")
        first_backup.write_text("keep this backup\n", encoding="utf-8")

        result = AUTUPDATE.configure(self.home)

        self.assertEqual(first_backup.read_text(encoding="utf-8"), "keep this backup\n")
        self.assertEqual(
            result.backup_path, self.settings.with_name("settings.json.bak.1")
        )
        assert result.backup_path is not None
        self.assertEqual(result.backup_path.read_text(encoding="utf-8"), "{}\n")

    def test_dry_run_does_not_create_a_home_or_settings(self) -> None:
        result = AUTUPDATE.configure(self.home, dry_run=True)

        self.assertTrue(result.changed)
        self.assertTrue(result.dry_run)
        self.assertFalse(self.home.exists())

    def test_jsonc_fails_without_modifying_or_backing_up_the_file(self) -> None:
        original = '{\n  // keep this comment\n  "enabledPlugins": {}\n}\n'
        self.write_settings(original)

        with self.assertRaisesRegex(AUTUPDATE.ConfigurationError, "not strict JSON"):
            AUTUPDATE.configure(self.home)

        self.assertEqual(self.settings.read_text(encoding="utf-8"), original)
        self.assertEqual(list(self.home.glob("settings.json.bak*")), [])

    def test_non_object_and_wrong_nested_types_fail_without_writes(self) -> None:
        for value in ([], {"enabledPlugins": []}, {"extraKnownMarketplaces": []}):
            with self.subTest(value=value):
                original = json.dumps(value) + "\n"
                self.write_settings(original)
                with self.assertRaises(AUTUPDATE.ConfigurationError):
                    AUTUPDATE.configure(self.home)
                self.assertEqual(self.settings.read_text(encoding="utf-8"), original)
                self.assertEqual(list(self.home.glob("settings.json.bak*")), [])

    def test_pinned_marketplace_requires_explicit_replacement(self) -> None:
        pinned = {
            "extraKnownMarketplaces": {
                "grillmester": {
                    "source": {
                        "source": "github",
                        "repo": "navikt/grillmester",
                        "ref": "v0.3.0-poc.2",
                    }
                }
            }
        }
        original = json.dumps(pinned, indent=2) + "\n"
        self.write_settings(original)

        with self.assertRaisesRegex(
            AUTUPDATE.ConfigurationError, "--replace-existing-marketplace"
        ):
            AUTUPDATE.configure(self.home)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), original)

        result = AUTUPDATE.configure(
            self.home, replace_existing_marketplace=True
        )

        self.assertTrue(result.changed)
        self.assertEqual(
            self.read_settings()["extraKnownMarketplaces"]["grillmester"]["source"],
            AUTUPDATE.EXPECTED_SOURCE,
        )
        self.assertTrue(
            self.read_settings()["extraKnownMarketplaces"]["grillmester"]["autoUpdate"]
        )

    def test_different_marketplace_shape_requires_replacement_flag(self) -> None:
        original = {
            "extraKnownMarketplaces": {
                "grillmester": {"source": "https://example.test/catalog.json"}
            }
        }
        self.write_settings(json.dumps(original) + "\n")

        with self.assertRaises(AUTUPDATE.ConfigurationError):
            AUTUPDATE.configure(self.home, dry_run=True)

        self.assertEqual(self.read_settings(), original)

    def test_explicit_global_auto_update_false_requires_explicit_override(self) -> None:
        original = {"autoUpdate": False, "telemetry": "keep"}
        encoded = json.dumps(original, indent=2) + "\n"
        self.write_settings(encoded)

        with self.assertRaisesRegex(
            AUTUPDATE.ConfigurationError, "--enable-global-auto-update"
        ) as rejected:
            AUTUPDATE.configure(self.home)

        self.assertIn("Copilot CLI itself and all plugins", str(rejected.exception))

        self.assertEqual(self.settings.read_text(encoding="utf-8"), encoded)
        self.assertEqual(list(self.home.glob("settings.json.bak*")), [])

        preview = AUTUPDATE.configure(
            self.home,
            dry_run=True,
            enable_global_auto_update=True,
        )
        self.assertTrue(preview.changed)
        self.assertIn(
            "enable automatic updates for Copilot CLI itself and all plugins",
            preview.actions,
        )
        self.assertEqual(self.settings.read_text(encoding="utf-8"), encoded)

        applied = AUTUPDATE.configure(
            self.home,
            enable_global_auto_update=True,
        )
        self.assertTrue(applied.changed)
        self.assertIs(self.read_settings()["autoUpdate"], True)
        self.assertEqual(self.read_settings()["telemetry"], "keep")

        help_text = " ".join(AUTUPDATE.build_parser().format_help().split())
        self.assertIn("Copilot CLI itself and all plugins", help_text)

    def test_invalid_global_auto_update_type_is_not_rewritten(self) -> None:
        original = '{"autoUpdate": "sometimes"}\n'
        self.write_settings(original)

        with self.assertRaisesRegex(AUTUPDATE.ConfigurationError, "JSON boolean"):
            AUTUPDATE.configure(
                self.home,
                enable_global_auto_update=True,
            )

        self.assertEqual(self.settings.read_text(encoding="utf-8"), original)

    def test_symlinked_settings_file_is_refused(self) -> None:
        self.home.mkdir(parents=True)
        target = self.home / "real-settings.json"
        target.write_text("{}\n", encoding="utf-8")
        self.settings.symlink_to(target.name)

        with self.assertRaisesRegex(AUTUPDATE.ConfigurationError, "symlinked"):
            AUTUPDATE.configure(self.home)

        self.assertEqual(target.read_text(encoding="utf-8"), "{}\n")

    def test_symlinked_copilot_home_is_refused(self) -> None:
        real_home = Path(self.temp.name) / "real-copilot-home"
        real_home.mkdir()
        real_settings = real_home / "settings.json"
        real_settings.write_text("{}\n", encoding="utf-8")
        self.home.symlink_to(real_home, target_is_directory=True)

        with self.assertRaisesRegex(
            AUTUPDATE.ConfigurationError, "symlinked Copilot home"
        ):
            AUTUPDATE.configure(self.home, dry_run=True)

        self.assertEqual(real_settings.read_text(encoding="utf-8"), "{}\n")

    def test_copilot_home_owned_by_another_user_is_refused(self) -> None:
        self.home.mkdir(parents=True)
        actual_owner = self.home.stat().st_uid

        with mock.patch.object(AUTUPDATE.os, "geteuid", return_value=actual_owner + 1):
            with self.assertRaisesRegex(
                AUTUPDATE.ConfigurationError, "Copilot home is not owned"
            ):
                AUTUPDATE.configure(self.home, dry_run=True)

    def test_atomic_replace_failure_keeps_original_and_removes_temp(self) -> None:
        original = "{}\n"
        self.write_settings(original)

        with mock.patch.object(AUTUPDATE.os, "replace", side_effect=OSError("boom")):
            with self.assertRaisesRegex(AUTUPDATE.ConfigurationError, "atomically"):
                AUTUPDATE.configure(self.home)

        self.assertEqual(self.settings.read_text(encoding="utf-8"), original)
        self.assertEqual(list(self.home.glob(".settings.json.*.tmp")), [])
        self.assertEqual(
            self.settings.with_name("settings.json.bak").read_text(encoding="utf-8"),
            original,
        )

    def test_permission_only_change_is_idempotent_without_backup(self) -> None:
        desired, _ = AUTUPDATE.merge_settings({})
        self.write_settings(json.dumps(desired, indent=2) + "\n", mode=0o644)

        first = AUTUPDATE.configure(self.home)
        second = AUTUPDATE.configure(self.home)

        self.assertTrue(first.changed)
        self.assertFalse(second.changed)
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o600)
        self.assertEqual(list(self.home.glob("settings.json.bak*")), [])

    def test_cli_uses_copilot_home_environment_and_reports_conflicts(self) -> None:
        pinned = {
            "extraKnownMarketplaces": {
                "grillmester": {
                    "source": {"source": "github", "repo": "navikt/grillmester"}
                }
            }
        }
        self.write_settings(json.dumps(pinned) + "\n")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with mock.patch.dict(os.environ, {"COPILOT_HOME": str(self.home)}):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = AUTUPDATE.main([])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("--replace-existing-marketplace", stderr.getvalue())

    def test_cli_previews_by_default_and_requires_apply_to_write(self) -> None:
        preview_stdout = io.StringIO()
        with redirect_stdout(preview_stdout):
            preview_exit = AUTUPDATE.main(["--copilot-home", str(self.home)])

        self.assertEqual(preview_exit, 0)
        self.assertIn("Would update", preview_stdout.getvalue())
        self.assertFalse(self.settings.exists())

        apply_stdout = io.StringIO()
        with redirect_stdout(apply_stdout):
            apply_exit = AUTUPDATE.main(
                ["--copilot-home", str(self.home), "--apply"]
            )

        self.assertEqual(apply_exit, 0)
        self.assertIn("Updated", apply_stdout.getvalue())
        self.assertTrue(self.settings.exists())

    def test_disabled_environment_warns_on_preview_apply_and_noop(self) -> None:
        stages = (
            ([], "Would update"),
            (["--apply"], "Updated"),
            (["--apply"], "already configured"),
        )

        for arguments, expected_status in stages:
            with self.subTest(stage=expected_status):
                stdout = io.StringIO()
                stderr = io.StringIO()
                with mock.patch.dict(
                    os.environ,
                    {"COPILOT_AUTO_UPDATE": "false"},
                ):
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        exit_code = AUTUPDATE.main(
                            ["--copilot-home", str(self.home), *arguments]
                        )
                    self.assertEqual(os.environ["COPILOT_AUTO_UPDATE"], "false")

                self.assertEqual(exit_code, 0)
                self.assertIn(expected_status, stdout.getvalue())
                self.assertTrue(
                    stderr.getvalue().startswith(
                        "WARNING: COPILOT_AUTO_UPDATE=false"
                    ),
                    stderr.getvalue(),
                )
                self.assertIn("Unset COPILOT_AUTO_UPDATE", stderr.getvalue())

    def test_only_documented_exact_false_environment_value_warns(self) -> None:
        warning = AUTUPDATE.environment_warnings(
            {"COPILOT_AUTO_UPDATE": "false"}
        )
        self.assertEqual(len(warning), 1)

        for value in ("", "0", "off", "False", "FALSE", " false "):
            with self.subTest(value=value):
                self.assertEqual(
                    AUTUPDATE.environment_warnings(
                        {"COPILOT_AUTO_UPDATE": value}
                    ),
                    (),
                )
        self.assertEqual(AUTUPDATE.environment_warnings({}), ())


if __name__ == "__main__":
    unittest.main()
