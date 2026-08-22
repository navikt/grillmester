from __future__ import annotations

import importlib.util
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_cli", ROOT / "scripts/grillmester.py"
)
assert SPEC is not None and SPEC.loader is not None
CLI = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CLI
SPEC.loader.exec_module(CLI)


class GrillmesterCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.distribution = CLI.load_distribution(ROOT)

    def test_default_is_copilot_through_cplt_with_reviewed_plugin(self) -> None:
        invocation = CLI.parse_invocation([], cwd=ROOT)
        command, environment = CLI.build_launch_command(
            invocation, self.distribution, cplt="/trusted/cplt"
        )

        self.assertEqual("copilot", invocation.client)
        self.assertEqual(
            command,
            [
                "/trusted/cplt",
                "--agent",
                "copilot",
                "--project-dir",
                str(ROOT),
                "--allow-read",
                str(ROOT / "plugin"),
                "--",
                "--plugin-dir",
                str(ROOT / "plugin"),
                "--agent",
                "grillmester:grillmester",
            ],
        )
        self.assertEqual(os.environ.get("OPENCODE_CONFIG_DIR"), environment.get("OPENCODE_CONFIG_DIR"))

    def test_opencode_binds_target_and_forwards_both_argument_layers(self) -> None:
        invocation = CLI.parse_invocation(
            [
                "--client",
                "opencode",
                "--role",
                "barista",
                "--allow-localhost",
                "1234",
                "--pass-env",
                "LOCAL_MODEL_KEY",
                "--",
                "--model",
                "lmstudio/qwen",
            ],
            cwd=ROOT,
        )
        command, environment = CLI.build_launch_command(
            invocation, self.distribution, cplt="/trusted/cplt"
        )

        separator = command.index("--")
        self.assertEqual(command[1:3], ["--agent", "opencode"])
        self.assertEqual(
            command[separator + 1 :],
            ["--agent", "barista", "--model", "lmstudio/qwen"],
        )
        self.assertIn("--allow-localhost", command[:separator])
        self.assertIn("LOCAL_MODEL_KEY", command[:separator])
        self.assertEqual(
            str(ROOT / "targets/opencode-v1"),
            environment["OPENCODE_CONFIG_DIR"],
        )
        self.assertIn("OPENCODE_CONFIG_DIR", command[:separator])

    def test_positional_client_is_supported(self) -> None:
        invocation = CLI.parse_invocation(["opencode"], cwd=ROOT)
        self.assertEqual("opencode", invocation.client)

    def test_saved_defaults_are_used_when_flags_are_omitted(self) -> None:
        invocation = CLI.parse_invocation(
            [], cwd=ROOT, defaults=CLI.Preferences("opencode", "designer")
        )
        self.assertEqual(("opencode", "designer"), (invocation.client, invocation.role))

    def test_explicit_selection_overrides_saved_defaults_for_one_launch(self) -> None:
        invocation = CLI.parse_invocation(
            ["--client", "copilot", "--role", "barista"],
            cwd=ROOT,
            defaults=CLI.Preferences("opencode", "designer"),
        )
        self.assertEqual(("copilot", "barista"), (invocation.client, invocation.role))

    def test_interactive_picker_selects_and_saves_client_and_role(self) -> None:
        saved_path = Path("/tmp/preferences.json")
        with mock.patch.object(CLI.sys.stdin, "isatty", return_value=True), mock.patch.object(
            CLI.sys.stdout, "isatty", return_value=True
        ), mock.patch.object(
            CLI, "input", side_effect=["2", "3"], create=True
        ), mock.patch.object(
            CLI, "save_preferences", return_value=saved_path
        ) as save, mock.patch.object(CLI, "print", create=True):
            selected = CLI.choose_preferences()

        self.assertEqual(CLI.Preferences("opencode", "designer"), selected)
        save.assert_called_once_with(selected)

    def test_bare_command_uses_saved_default_on_enter(self) -> None:
        current = CLI.Preferences("opencode", "doctor-who")
        with mock.patch.object(CLI, "load_preferences", return_value=current), mock.patch.object(
            CLI.sys.stdin, "isatty", return_value=True
        ), mock.patch.object(
            CLI.sys.stdout, "isatty", return_value=True
        ), mock.patch.object(CLI, "input", return_value="", create=True):
            self.assertEqual(current, CLI.interactive_defaults())

    def test_fully_explicit_launch_does_not_read_saved_preferences(self) -> None:
        checks = [
            (
                "cplt",
                f"/trusted/cplt (cplt {CLI.SUPPORTED_CPLT_RELEASE})",
            ),
            ("opencode", f"/trusted/opencode ({CLI.SUPPORTED_OPENCODE_VERSION})"),
        ]
        with mock.patch.object(CLI, "load_preferences") as load, mock.patch.object(
            CLI, "check_client", return_value=checks
        ), mock.patch.object(CLI.sys, "stdout"):
            result = CLI.main(
                [
                    "--client",
                    "opencode",
                    "--role",
                    "barista",
                    "--print-command",
                    "--project-dir",
                    str(ROOT),
                ]
            )

        self.assertEqual(0, result)
        load.assert_not_called()

    def test_preferences_round_trip_with_private_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config/grillmester/preferences.json"
            preferences = CLI.Preferences("opencode", "doctor-who")
            self.assertEqual(path, CLI.save_preferences(preferences, path))
            self.assertEqual(preferences, CLI.load_preferences(path))
            self.assertEqual(0o600, path.stat().st_mode & 0o777)
            self.assertEqual(0o700, path.parent.stat().st_mode & 0o777)

    def test_relative_xdg_config_home_is_rejected(self) -> None:
        with self.assertRaisesRegex(CLI.LauncherError, "must be an absolute path"):
            CLI.preference_path({"XDG_CONFIG_HOME": "relative"})

    def test_symlinked_preferences_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "real.json"
            target.write_text("{}\n")
            link = root / "preferences.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(CLI.LauncherError, "non-symlink"):
                CLI.load_preferences(link)

    def test_conflicting_client_selectors_are_rejected(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            CLI.parse_invocation(["copilot", "--client", "opencode"], cwd=ROOT)

    def test_reserved_cplt_agent_cannot_replace_selected_client(self) -> None:
        with self.assertRaisesRegex(CLI.LauncherError, "owned by Grillmester"):
            CLI.parse_invocation(
                ["--client", "opencode", "--agent", "copilot"], cwd=ROOT
            )

    def test_short_cplt_project_dir_cannot_replace_selected_project(self) -> None:
        with self.assertRaisesRegex(CLI.LauncherError, "cplt -d is owned"):
            CLI.parse_invocation(
                ["--client", "opencode", "-d", "/tmp/other"], cwd=ROOT
            )

    def test_cplt_subcommand_cannot_replace_the_client_launch(self) -> None:
        with self.assertRaisesRegex(CLI.LauncherError, "subcommands"):
            CLI.parse_invocation(
                ["--client", "opencode", "exec", "sh"], cwd=ROOT
            )

    def test_reserved_client_agent_cannot_replace_selected_role(self) -> None:
        with self.assertRaisesRegex(CLI.LauncherError, "use --role"):
            CLI.parse_invocation(
                ["--client", "opencode", "--", "--agent", "build"], cwd=ROOT
            )

    def test_client_project_dir_cannot_replace_selected_project(self) -> None:
        with self.assertRaisesRegex(CLI.LauncherError, "client --project-dir"):
            CLI.parse_invocation(
                ["--client", "opencode", "--", "--project-dir", "/tmp/other"],
                cwd=ROOT,
            )

    def test_copilot_plugin_dir_cannot_be_replaced(self) -> None:
        with self.assertRaisesRegex(CLI.LauncherError, "reviewed distribution"):
            CLI.parse_invocation(
                ["--client", "copilot", "--", "--plugin-dir", "/tmp/other"],
                cwd=ROOT,
            )

    def test_distribution_requires_both_client_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(CLI.LauncherError, "plugin directory"):
                CLI.load_distribution(Path(directory))

    def test_exact_cplt_and_opencode_versions_are_required(self) -> None:
        outputs = {
            "/bin/cplt": f"cplt {CLI.SUPPORTED_CPLT_RELEASE}",
            "/bin/opencode": CLI.SUPPORTED_OPENCODE_VERSION,
        }
        with mock.patch.object(CLI, "_resolve_binary", side_effect=lambda name: f"/bin/{name}"), mock.patch.object(
            CLI, "_version_output", side_effect=lambda binary: outputs[binary]
        ):
            checks = CLI.check_client("opencode")
        self.assertEqual(["cplt", "opencode"], [label for label, _ in checks])

    def test_wrong_cplt_version_fails_before_client_probe(self) -> None:
        with mock.patch.object(CLI, "_resolve_binary", return_value="/bin/cplt"), mock.patch.object(
            CLI, "_version_output", return_value="cplt future"
        ) as version:
            with self.assertRaisesRegex(CLI.LauncherError, "must be exactly"):
                CLI.check_client("copilot")
        version.assert_called_once_with("/bin/cplt")

    def test_supported_copilot_semver_range_accepts_newer_patch(self) -> None:
        outputs = {
            "/bin/cplt": f"cplt {CLI.SUPPORTED_CPLT_RELEASE}",
            "/bin/copilot": "GitHub Copilot CLI 1.0.80.",
        }
        with mock.patch.object(CLI, "_resolve_binary", side_effect=lambda name: f"/bin/{name}"), mock.patch.object(
            CLI, "_version_output", side_effect=lambda binary: outputs[binary]
        ):
            checks = CLI.check_client("copilot")
        self.assertEqual(["cplt", "copilot"], [label for label, _ in checks])

    def test_old_copilot_cli_is_rejected(self) -> None:
        outputs = {
            "/bin/cplt": f"cplt {CLI.SUPPORTED_CPLT_RELEASE}",
            "/bin/copilot": "0.0.410",
        }
        with mock.patch.object(CLI, "_resolve_binary", side_effect=lambda name: f"/bin/{name}"), mock.patch.object(
            CLI, "_version_output", side_effect=lambda binary: outputs[binary]
        ):
            with self.assertRaisesRegex(CLI.LauncherError, "at least"):
                CLI.check_client("copilot")


if __name__ == "__main__":
    unittest.main()
