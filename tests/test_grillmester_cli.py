from __future__ import annotations

import importlib.util
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
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


class TtyBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


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
                "--agent",
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

    def test_opencode_runtime_support_is_preseeded_without_a_write_grant(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_home = Path(directory) / "config"
            support = CLI.ensure_opencode_runtime_support(
                self.distribution, {"XDG_CONFIG_HOME": str(config_home)}
            )

            self.assertEqual(
                CLI.OPENCODE_RUNTIME_GITIGNORE,
                support.read_bytes(),
            )
            self.assertEqual(0o600, support.stat().st_mode & 0o777)
            self.assertEqual(
                CLI.OPENCODE_RUNTIME_GITIGNORE,
                (self.distribution.opencode_target / ".gitignore").read_bytes(),
            )

    def test_existing_opencode_runtime_support_is_never_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_home = Path(directory) / "config"
            support = config_home / "opencode/.gitignore"
            support.parent.mkdir(parents=True)
            support.write_text("user-owned\n", encoding="utf-8")

            resolved = CLI.ensure_opencode_runtime_support(
                self.distribution, {"XDG_CONFIG_HOME": str(config_home)}
            )

            self.assertEqual(support, resolved)
            self.assertEqual("user-owned\n", support.read_text(encoding="utf-8"))

    def test_symlinked_opencode_runtime_support_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_home = Path(directory) / "config"
            support = config_home / "opencode/.gitignore"
            support.parent.mkdir(parents=True)
            target = config_home / "other"
            target.write_text("untouched\n", encoding="utf-8")
            support.symlink_to(target)

            with self.assertRaisesRegex(CLI.LauncherError, "non-symlink"):
                CLI.ensure_opencode_runtime_support(
                    self.distribution, {"XDG_CONFIG_HOME": str(config_home)}
                )
            self.assertEqual("untouched\n", target.read_text(encoding="utf-8"))

    def test_failed_runtime_support_write_removes_its_partial_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_home = Path(directory) / "config"
            support = config_home / "opencode/.gitignore"

            with mock.patch.object(
                CLI.os, "fsync", side_effect=OSError("simulated write failure")
            ), self.assertRaisesRegex(CLI.LauncherError, "could not write"):
                CLI.ensure_opencode_runtime_support(
                    self.distribution, {"XDG_CONFIG_HOME": str(config_home)}
                )

            self.assertFalse(support.exists())

    def test_positional_client_is_supported(self) -> None:
        invocation = CLI.parse_invocation(["opencode"], cwd=ROOT)
        self.assertEqual("opencode", invocation.client)

    def test_saved_defaults_are_used_when_flags_are_omitted(self) -> None:
        invocation = CLI.parse_invocation(
            [], cwd=ROOT, defaults=CLI.Preferences("opencode", "designer")
        )
        self.assertEqual(("opencode", "designer"), (invocation.client, invocation.agent))

    def test_explicit_selection_overrides_saved_defaults_for_one_launch(self) -> None:
        invocation = CLI.parse_invocation(
            ["--client", "copilot", "--agent", "barista"],
            cwd=ROOT,
            defaults=CLI.Preferences("opencode", "designer"),
        )
        self.assertEqual(("copilot", "barista"), (invocation.client, invocation.agent))

    def test_agent_is_the_canonical_public_selector(self) -> None:
        invocation = CLI.parse_invocation(
            ["--client", "opencode", "--agent", "barista"], cwd=ROOT
        )
        self.assertEqual(("opencode", "barista"), (invocation.client, invocation.agent))

    def test_role_remains_a_compatible_agent_alias(self) -> None:
        invocation = CLI.parse_invocation(
            ["--client", "opencode", "--role", "designer"], cwd=ROOT
        )
        self.assertEqual("designer", invocation.agent)

    def test_interactive_picker_selects_and_saves_client_and_agent(self) -> None:
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
                    "--agent",
                    "barista",
                    "--print-command",
                    "--project-dir",
                    str(ROOT),
                ]
            )

        self.assertEqual(0, result)
        load.assert_not_called()

    def test_print_command_does_not_seed_opencode_runtime_support(self) -> None:
        checks = [
            ("cplt", f"/trusted/cplt (cplt {CLI.SUPPORTED_CPLT_RELEASE})"),
            ("opencode", f"/trusted/opencode ({CLI.SUPPORTED_OPENCODE_VERSION})"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            config_home = Path(directory) / "config"
            with mock.patch.dict(
                os.environ, {"XDG_CONFIG_HOME": str(config_home)}
            ), mock.patch.object(
                CLI, "check_client", return_value=checks
            ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result = CLI.main(
                    [
                        "--client",
                        "opencode",
                        "--agent",
                        "grillmester",
                        "--print-command",
                        "--project-dir",
                        str(ROOT),
                    ]
                )

            self.assertEqual(0, result)
            self.assertFalse((config_home / "opencode/.gitignore").exists())

    def test_opencode_launch_seeds_runtime_support_before_exec(self) -> None:
        checks = [
            ("cplt", f"/trusted/cplt (cplt {CLI.SUPPORTED_CPLT_RELEASE})"),
            ("opencode", f"/trusted/opencode ({CLI.SUPPORTED_OPENCODE_VERSION})"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            config_home = Path(directory) / "config"

            def execute(_binary: str, _command: list[str], _environment: dict[str, str]) -> None:
                self.assertEqual(
                    CLI.OPENCODE_RUNTIME_GITIGNORE,
                    (config_home / "opencode/.gitignore").read_bytes(),
                )

            with mock.patch.dict(
                os.environ, {"XDG_CONFIG_HOME": str(config_home)}
            ), mock.patch.object(
                CLI, "check_client", return_value=checks
            ), mock.patch.object(
                CLI.os, "execvpe", side_effect=execute
            ) as execvpe, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result = CLI.main(
                    [
                        "--client",
                        "opencode",
                        "--agent",
                        "grillmester",
                        "--project-dir",
                        str(ROOT),
                    ]
                )

            self.assertEqual(0, result)
            execvpe.assert_called_once()

    def test_help_does_not_require_saved_preferences(self) -> None:
        stdout = io.StringIO()
        with mock.patch.object(CLI, "load_preferences") as load, redirect_stdout(
            stdout
        ), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as stopped:
                CLI.main(["--help"])

        self.assertEqual(0, stopped.exception.code)
        self.assertIn("usage: grillmester", stdout.getvalue())
        self.assertIn("--agent", stdout.getvalue())
        self.assertIn("--print-command", stdout.getvalue())
        self.assertIn("choose    change and save", stdout.getvalue())
        self.assertIn("doctor    verify", stdout.getvalue())
        self.assertIn("update    update", stdout.getvalue())
        self.assertIn("version   show", stdout.getvalue())
        self.assertIn("Examples:", stdout.getvalue())
        load.assert_not_called()

    def test_help_subcommand_does_not_require_saved_preferences(self) -> None:
        stdout = io.StringIO()
        with mock.patch.object(CLI, "load_preferences") as load, redirect_stdout(
            stdout
        ), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as stopped:
                CLI.main(["help"])

        self.assertEqual(0, stopped.exception.code)
        self.assertIn("usage: grillmester", stdout.getvalue())
        load.assert_not_called()

    def test_update_commands_run_homebrew_without_launching_a_client(self) -> None:
        for command in ("update", "upgrade"):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as directory:
                brew = Path(directory) / "brew"
                brew.write_text("fixture\n", encoding="utf-8")
                brew.chmod(0o700)
                refreshed = CLI.subprocess.CompletedProcess([str(brew), "update"], 0)
                with mock.patch.object(
                    CLI.shutil, "which", return_value=str(brew)
                ), mock.patch.object(
                    CLI.subprocess, "run", return_value=refreshed
                ) as run, mock.patch.object(
                    CLI.os, "execv"
                ) as execute, mock.patch.object(
                    CLI, "load_preferences"
                ) as load, mock.patch.object(
                    CLI, "check_client"
                ) as check_client, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    result = CLI.main([command])

                self.assertEqual(0, result)
                resolved_brew = str(brew.resolve(strict=True))
                run.assert_called_once_with([resolved_brew, "update"], check=False)
                execute.assert_called_once_with(
                    resolved_brew, [resolved_brew, "upgrade", "grillmester"]
                )
                load.assert_not_called()
                check_client.assert_not_called()

    def test_failed_homebrew_refresh_never_attempts_the_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            brew = Path(directory) / "brew"
            brew.write_text("fixture\n", encoding="utf-8")
            brew.chmod(0o700)
            refreshed = CLI.subprocess.CompletedProcess([str(brew), "update"], 1)
            stderr = io.StringIO()
            with mock.patch.object(
                CLI.shutil, "which", return_value=str(brew)
            ), mock.patch.object(
                CLI.subprocess, "run", return_value=refreshed
            ), mock.patch.object(
                CLI.os, "execv"
            ) as execute, redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                result = CLI.main(["update"])

        self.assertEqual(2, result)
        self.assertIn("was not upgraded", stderr.getvalue())
        execute.assert_not_called()

    def test_update_without_homebrew_has_an_actionable_error(self) -> None:
        stderr = io.StringIO()
        with mock.patch.object(
            CLI.shutil, "which", return_value=None
        ), redirect_stdout(io.StringIO()), redirect_stderr(stderr):
            result = CLI.main(["update"])

        self.assertEqual(2, result)
        self.assertIn("https://brew.sh/", stderr.getvalue())

    def test_arguments_without_selection_require_a_saved_default_noninteractively(
        self,
    ) -> None:
        checks = [
            ("cplt", f"/trusted/cplt (cplt {CLI.SUPPORTED_CPLT_RELEASE})"),
            ("copilot", "/trusted/copilot (GitHub Copilot CLI 1.0.80.)"),
        ]
        stderr = io.StringIO()
        with mock.patch.object(CLI, "load_preferences", return_value=None), mock.patch.object(
            CLI.sys.stdin, "isatty", return_value=False
        ), mock.patch.object(
            CLI.sys.stdout, "isatty", return_value=False
        ), mock.patch.object(
            CLI, "check_client", return_value=checks
        ) as check_client, redirect_stdout(io.StringIO()), redirect_stderr(stderr):
            result = CLI.main(
                [
                    "--allow-localhost",
                    "1234",
                    "--print-command",
                    "--",
                    "--model",
                    "lmstudio/example",
                ]
            )

        self.assertEqual(2, result)
        self.assertIn("no saved default", stderr.getvalue())
        self.assertIn("--client and --agent", stderr.getvalue())
        check_client.assert_not_called()

    def test_arguments_without_selection_open_picker_interactively(self) -> None:
        checks = [
            ("cplt", f"/trusted/cplt (cplt {CLI.SUPPORTED_CPLT_RELEASE})"),
            ("opencode", f"/trusted/opencode ({CLI.SUPPORTED_OPENCODE_VERSION})"),
        ]
        saved_path = Path("/tmp/preferences.json")
        stdout = TtyBuffer()
        with mock.patch.object(CLI, "load_preferences", return_value=None), mock.patch.object(
            CLI.sys, "stdin", TtyBuffer()
        ), mock.patch.object(
            CLI.sys, "stdout", stdout
        ), mock.patch.object(
            CLI, "input", side_effect=["2", "3"], create=True
        ), mock.patch.object(
            CLI, "save_preferences", return_value=saved_path
        ), mock.patch.object(
            CLI, "check_client", return_value=checks
        ) as check_client, redirect_stderr(io.StringIO()):
            result = CLI.main(
                [
                    "--allow-localhost",
                    "1234",
                    "--print-command",
                    "--",
                    "--model",
                    "lmstudio/example",
                ]
            )

        self.assertEqual(0, result)
        check_client.assert_called_once_with("opencode")
        self.assertIn("--agent opencode", stdout.getvalue())

    def test_first_launch_with_client_only_prompts_for_and_saves_agent(self) -> None:
        checks = [
            ("cplt", f"/trusted/cplt (cplt {CLI.SUPPORTED_CPLT_RELEASE})"),
            ("opencode", f"/trusted/opencode ({CLI.SUPPORTED_OPENCODE_VERSION})"),
        ]
        saved_path = Path("/tmp/preferences.json")
        stdout = TtyBuffer()
        with mock.patch.object(CLI, "load_preferences", return_value=None), mock.patch.object(
            CLI.sys, "stdin", TtyBuffer()
        ), mock.patch.object(
            CLI.sys, "stdout", stdout
        ), mock.patch.object(
            CLI, "input", side_effect=["3"], create=True
        ), mock.patch.object(
            CLI, "save_preferences", return_value=saved_path
        ) as save, mock.patch.object(
            CLI, "check_client", return_value=checks
        ), redirect_stderr(io.StringIO()):
            result = CLI.main(
                [
                    "--client",
                    "opencode",
                    "--print-command",
                    "--project-dir",
                    str(ROOT),
                ]
            )

        selected = CLI.Preferences("opencode", "designer")
        self.assertEqual(0, result)
        save.assert_called_once_with(selected)
        self.assertIn("OpenCode (fra kommandoen)", stdout.getvalue())
        self.assertIn("--agent opencode", stdout.getvalue())

    def test_first_launch_with_agent_only_prompts_for_and_saves_client(self) -> None:
        checks = [
            ("cplt", f"/trusted/cplt (cplt {CLI.SUPPORTED_CPLT_RELEASE})"),
            ("opencode", f"/trusted/opencode ({CLI.SUPPORTED_OPENCODE_VERSION})"),
        ]
        saved_path = Path("/tmp/preferences.json")
        stdout = TtyBuffer()
        with mock.patch.object(CLI, "load_preferences", return_value=None), mock.patch.object(
            CLI.sys, "stdin", TtyBuffer()
        ), mock.patch.object(
            CLI.sys, "stdout", stdout
        ), mock.patch.object(
            CLI, "input", side_effect=["2"], create=True
        ), mock.patch.object(
            CLI, "save_preferences", return_value=saved_path
        ) as save, mock.patch.object(
            CLI, "check_client", return_value=checks
        ), redirect_stderr(io.StringIO()):
            result = CLI.main(
                [
                    "--agent",
                    "barista",
                    "--print-command",
                    "--project-dir",
                    str(ROOT),
                ]
            )

        selected = CLI.Preferences("opencode", "barista")
        self.assertEqual(0, result)
        save.assert_called_once_with(selected)
        self.assertIn("Barista – tydelige utviklingsoppgaver (fra kommandoen)", stdout.getvalue())
        self.assertIn("--agent opencode", stdout.getvalue())

    def test_choose_repairs_invalid_preferences_without_starting_a_client(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_home = Path(directory) / "config"
            preferences = config_home / "grillmester/preferences.json"
            preferences.parent.mkdir(parents=True)
            preferences.write_text("{broken\n", encoding="utf-8")
            with mock.patch.dict(
                os.environ, {"XDG_CONFIG_HOME": str(config_home)}
            ), mock.patch.object(
                CLI.sys, "stdin", TtyBuffer()
            ), mock.patch.object(
                CLI.sys, "stdout", TtyBuffer()
            ), mock.patch.object(
                CLI, "input", side_effect=["2", "3"], create=True
            ), mock.patch.object(
                CLI, "check_client"
            ) as check_client, mock.patch.object(
                CLI.os, "execvpe"
            ) as execvpe, redirect_stderr(io.StringIO()):
                result = CLI.main(["choose"])

            self.assertEqual(0, result)
            self.assertEqual(
                CLI.Preferences("opencode", "designer"),
                CLI.load_preferences(preferences),
            )
            check_client.assert_not_called()
            execvpe.assert_not_called()

    def test_choose_repairs_preferences_with_unexpected_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_home = Path(directory) / "config"
            preferences = config_home / "grillmester/preferences.json"
            preferences.parent.mkdir(parents=True)
            preferences.write_text(
                '{"schemaVersion":1,"client":"copilot","agent":"barista",'
                '"unexpected":true}\n',
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ, {"XDG_CONFIG_HOME": str(config_home)}
            ), mock.patch.object(
                CLI.sys, "stdin", TtyBuffer()
            ), mock.patch.object(
                CLI.sys, "stdout", TtyBuffer()
            ), mock.patch.object(
                CLI, "input", side_effect=["2", "4"], create=True
            ), redirect_stderr(io.StringIO()):
                result = CLI.main(["choose"])

            self.assertEqual(0, result)
            self.assertEqual(
                CLI.Preferences("opencode", "doctor-who"),
                CLI.load_preferences(preferences),
            )

    def test_invalid_preferences_error_points_to_choose_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_home = Path(directory) / "config"
            preferences = config_home / "grillmester/preferences.json"
            preferences.parent.mkdir(parents=True)
            preferences.write_text("{broken\n", encoding="utf-8")
            stderr = io.StringIO()
            with mock.patch.dict(
                os.environ, {"XDG_CONFIG_HOME": str(config_home)}
            ), redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                result = CLI.main([])

        self.assertEqual(2, result)
        self.assertIn("grillmester choose", stderr.getvalue())

    def test_preferences_round_trip_with_private_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config/grillmester/preferences.json"
            preferences = CLI.Preferences("opencode", "doctor-who")
            self.assertEqual(path, CLI.save_preferences(preferences, path))
            self.assertEqual(preferences, CLI.load_preferences(path))
            content = path.read_text(encoding="utf-8")
            self.assertIn('"agent": "doctor-who"', content)
            self.assertNotIn('"role"', content)
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

    def test_cplt_client_cannot_be_selected_as_a_public_agent(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
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

    def test_reserved_client_agent_cannot_replace_selected_agent(self) -> None:
        with self.assertRaisesRegex(CLI.LauncherError, "put --agent before"):
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

    def test_doctor_skips_an_absent_optional_client_and_checks_cplt_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            binaries = Path(directory)
            for name in ("cplt", "opencode"):
                path = binaries / name
                path.write_text("fixture\n", encoding="utf-8")
                path.chmod(0o700)

            def which(name: str) -> str | None:
                return None if name == "copilot" else str(binaries / name)

            def version(binary: str) -> str:
                return (
                    f"cplt {CLI.SUPPORTED_CPLT_RELEASE}"
                    if Path(binary).name == "cplt"
                    else CLI.SUPPORTED_OPENCODE_VERSION
                )

            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch.object(CLI.shutil, "which", side_effect=which), mock.patch.object(
                CLI, "_version_output", side_effect=version
            ), redirect_stdout(stdout), redirect_stderr(stderr):
                result = CLI.doctor(None, root=ROOT)

        self.assertEqual(0, result)
        self.assertEqual("", stderr.getvalue())
        self.assertEqual(1, stdout.getvalue().count("ok  cplt "))
        self.assertIn("skip  copilot", stdout.getvalue())
        self.assertIn("ok  opencode", stdout.getvalue())

    def test_doctor_requires_an_explicitly_selected_client(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cplt = Path(directory) / "cplt"
            cplt.write_text("fixture\n", encoding="utf-8")
            cplt.chmod(0o700)

            def which(name: str) -> str | None:
                return str(cplt) if name == "cplt" else None

            with mock.patch.object(CLI.shutil, "which", side_effect=which), mock.patch.object(
                CLI, "_version_output", return_value=f"cplt {CLI.SUPPORTED_CPLT_RELEASE}"
            ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result = CLI.doctor("copilot", root=ROOT)

        self.assertEqual(1, result)


if __name__ == "__main__":
    unittest.main()
