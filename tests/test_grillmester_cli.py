from __future__ import annotations

import importlib.util
import io
import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time
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
        self.local_normalize = (
            CLI._load_local_mode_module().normalize_cli_arguments
        )

    @staticmethod
    def _write_version_binary(directory: Path, name: str, version: str) -> Path:
        binary = directory / name
        binary.write_text(
            f"#!/bin/sh\nprintf '%s\\n' '{version}'\n",
            encoding="utf-8",
        )
        binary.chmod(0o700)
        return binary

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
                "--no-audit",
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
        self.assertEqual(command[1:4], ["--no-audit", "--agent", "opencode"])
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

    def test_opencode_run_places_the_selected_agent_after_the_subcommand(self) -> None:
        invocation = CLI.parse_invocation(
            [
                "--client",
                "opencode",
                "--agent",
                "barista",
                "--",
                "run",
                "inspect this repository",
            ],
            cwd=ROOT,
        )

        command, _ = CLI.build_launch_command(
            invocation, self.distribution, cplt="/trusted/cplt"
        )

        separator = command.index("--")
        self.assertEqual(
            ["run", "--agent", "barista", "inspect this repository"],
            command[separator + 1 :],
        )

    def test_opencode_administrative_subcommand_is_not_given_an_agent_flag(self) -> None:
        invocation = CLI.parse_invocation(
            [
                "--client",
                "opencode",
                "--agent",
                "barista",
                "--",
                "models",
                "llamacpp",
            ],
            cwd=ROOT,
        )

        command, _ = CLI.build_launch_command(
            invocation, self.distribution, cplt="/trusted/cplt"
        )

        separator = command.index("--")
        self.assertEqual(["models", "llamacpp"], command[separator + 1 :])

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
        ) as save, mock.patch.object(
            CLI, "check_client_runtime", return_value=("opencode", "/bin/opencode (1.18.20)")
        ) as runtime, mock.patch.object(CLI, "print", create=True):
            selected = CLI.choose_preferences(available_clients=CLI.CLIENTS)

        self.assertEqual(CLI.Preferences("opencode", "designer"), selected)
        save.assert_called_once_with(selected)
        runtime.assert_called_once_with("opencode")

    def test_interactive_picker_never_saves_before_sandboxed_validation(self) -> None:
        with mock.patch.object(
            CLI.sys, "stdin", TtyBuffer()
        ), mock.patch.object(
            CLI.sys, "stdout", TtyBuffer()
        ), mock.patch.object(
            CLI, "input", side_effect=["2"], create=True
        ), mock.patch.object(
            CLI,
            "check_client_runtime",
            side_effect=CLI.LauncherError("sandboxed probe failed"),
        ), mock.patch.object(CLI, "save_preferences") as save:
            with self.assertRaisesRegex(CLI.LauncherError, "sandboxed probe failed"):
                CLI.choose_preferences(
                    fixed_agent="barista", available_clients=CLI.CLIENTS
                )

        save.assert_not_called()

    def test_first_run_uses_the_only_installed_client_and_only_asks_for_agent(self) -> None:
        saved_path = Path("/tmp/preferences.json")
        stdout = TtyBuffer()

        def resolve(client: str) -> str:
            if client == "opencode":
                raise CLI.MissingBinaryError(
                    "OpenCode was not found on PATH; install it with: brew install opencode"
                )
            return "/opt/homebrew/bin/copilot"

        with mock.patch.object(CLI, "load_preferences", return_value=None), mock.patch.object(
            CLI.sys, "stdin", TtyBuffer()
        ), mock.patch.object(CLI.sys, "stdout", stdout), mock.patch.object(
            CLI, "_resolve_binary", side_effect=resolve
        ), mock.patch.object(
            CLI, "input", side_effect=["2"], create=True
        ), mock.patch.object(
            CLI, "save_preferences", return_value=saved_path
        ) as save, mock.patch.object(CLI, "check_client_runtime") as runtime:
            runtime.return_value = (
                "copilot",
                "/opt/homebrew/bin/copilot (GitHub Copilot CLI 1.0.80.)",
            )
            selected = CLI.interactive_defaults()

        expected = CLI.Preferences("copilot", "barista")
        self.assertEqual(expected, selected)
        save.assert_called_once_with(expected)
        runtime.assert_called_once_with("copilot")
        self.assertIn("OpenCode was not found on PATH", stdout.getvalue())
        self.assertIn("eneste tilgjengelige", stdout.getvalue())

    def test_first_interactive_launch_reuses_the_validated_client_check(self) -> None:
        checks = CLI.LaunchChecks(
            CLI.CheckedBinary(
                "cplt", "/trusted/cplt", f"cplt {CLI.SUPPORTED_CPLT_RELEASE}"
            ),
            CLI.CheckedBinary(
                "opencode",
                "/trusted/opencode",
                CLI.MINIMUM_OPENCODE_VERSION_TEXT,
            ),
        )
        validation_cache: dict[str, CLI.LaunchChecks] = {}
        with mock.patch.object(CLI.sys, "stdin", TtyBuffer()), mock.patch.object(
            CLI.sys, "stdout", TtyBuffer()
        ), mock.patch.object(
            CLI, "input", side_effect=["", ""], create=True
        ), mock.patch.object(
            CLI, "discover_clients", return_value=("opencode",)
        ), mock.patch.object(
            CLI, "check_client", return_value=checks
        ) as check_client, mock.patch.object(
            CLI, "save_preferences", return_value=Path("/tmp/preferences.json")
        ):
            selected = CLI.choose_preferences(validation_cache=validation_cache)

        self.assertEqual(CLI.Preferences("opencode", "grillmester"), selected)
        self.assertIs(checks, validation_cache["opencode"])
        check_client.assert_called_once_with("opencode")

    def test_client_discovery_never_executes_ambient_clients(self) -> None:
        with mock.patch.object(
            CLI, "_resolve_binary", side_effect=lambda name: f"/bin/{name}"
        ), mock.patch.object(CLI, "check_client_runtime") as runtime:
            available = CLI.discover_clients()

        self.assertEqual(CLI.CLIENTS, available)
        runtime.assert_not_called()

    def test_bare_command_uses_saved_default_on_enter(self) -> None:
        current = CLI.Preferences("opencode", "doctor-who")
        with mock.patch.object(CLI, "load_preferences", return_value=current), mock.patch.object(
            CLI.sys.stdin, "isatty", return_value=True
        ), mock.patch.object(
            CLI.sys.stdout, "isatty", return_value=True
        ), mock.patch.object(CLI, "input", return_value="", create=True):
            self.assertEqual(current, CLI.interactive_defaults())

    def test_change_flow_filters_a_missing_saved_client_before_saving(self) -> None:
        current = CLI.Preferences("opencode", "designer")
        saved_path = Path("/tmp/preferences.json")

        def resolve(client: str) -> str:
            if client == "opencode":
                raise CLI.MissingBinaryError(
                    "OpenCode was not found on PATH; install it with: brew install opencode"
                )
            return "/opt/homebrew/bin/copilot"

        with mock.patch.object(
            CLI, "load_preferences", return_value=current
        ), mock.patch.object(
            CLI.sys, "stdin", TtyBuffer()
        ), mock.patch.object(
            CLI.sys, "stdout", TtyBuffer()
        ), mock.patch.object(
            CLI, "_resolve_binary", side_effect=resolve
        ), mock.patch.object(
            CLI,
            "check_client_runtime",
            return_value=(
                "copilot",
                "/opt/homebrew/bin/copilot (GitHub Copilot CLI 1.0.80.)",
            ),
        ), mock.patch.object(
            CLI, "input", side_effect=["c", ""], create=True
        ), mock.patch.object(
            CLI, "save_preferences", return_value=saved_path
        ) as save:
            selected = CLI.interactive_defaults()

        expected = CLI.Preferences("copilot", "designer")
        self.assertEqual(expected, selected)
        save.assert_called_once_with(expected)

    def test_fully_explicit_launch_does_not_read_saved_preferences(self) -> None:
        with mock.patch.object(CLI, "load_preferences") as load, mock.patch.object(
            CLI,
            "_resolve_binary",
            side_effect=lambda name: f"/trusted/{name}",
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
        with tempfile.TemporaryDirectory() as directory:
            config_home = Path(directory) / "config"
            with mock.patch.dict(
                os.environ, {"XDG_CONFIG_HOME": str(config_home)}
            ), mock.patch.object(
                CLI,
                "_resolve_binary",
                side_effect=lambda name: f"/trusted/{name}",
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

    def test_print_command_never_executes_cplt_or_the_selected_client(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binaries = root / "bin"
            binaries.mkdir()
            cplt_marker = root / "cplt-executed"
            client_marker = root / "client-executed"
            cplt = binaries / "cplt"
            cplt.write_text(
                "#!/bin/sh\n"
                f"touch '{cplt_marker}'\n"
                f"printf '%s\\n' 'cplt {CLI.SUPPORTED_CPLT_RELEASE}'\n",
                encoding="utf-8",
            )
            cplt.chmod(0o700)
            opencode = binaries / "opencode"
            opencode.write_text(
                "#!/bin/sh\n"
                f"touch '{client_marker}'\n"
                f"printf '%s\\n' '{CLI.MINIMUM_OPENCODE_VERSION_TEXT}'\n",
                encoding="utf-8",
            )
            opencode.chmod(0o700)
            environment = {
                **os.environ,
                "HOME": str(root / "home"),
                "PATH": f"{binaries}:/usr/bin:/bin",
                "XDG_CONFIG_HOME": str(root / "config"),
            }

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/grillmester.py"),
                    "--client",
                    "opencode",
                    "--agent",
                    "barista",
                    "--project-dir",
                    str(ROOT),
                    "--print-command",
                ],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertFalse(cplt_marker.exists())
            self.assertFalse(client_marker.exists())

    def test_print_command_preserves_a_cplt_path_containing_parenthesis(self) -> None:
        with tempfile.TemporaryDirectory(prefix="grillmester (qa) ") as directory:
            root = Path(directory)
            binaries = root / "bin"
            binaries.mkdir()
            cplt = self._write_version_binary(
                binaries, "cplt", f"cplt {CLI.SUPPORTED_CPLT_RELEASE}"
            )
            self._write_version_binary(
                binaries, "opencode", CLI.MINIMUM_OPENCODE_VERSION_TEXT
            )
            environment = {
                **os.environ,
                "HOME": str(root / "home"),
                "PATH": f"{binaries}:/usr/bin:/bin",
                "XDG_CONFIG_HOME": str(root / "config"),
            }

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/grillmester.py"),
                    "--client",
                    "opencode",
                    "--agent",
                    "barista",
                    "--project-dir",
                    str(ROOT),
                    "--print-command",
                ],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(str(cplt.resolve(strict=True)), shlex.split(result.stdout)[0])

    @unittest.skipUnless(hasattr(os, "fork"), "requires POSIX process groups")
    def test_probe_timeout_kills_child_after_the_group_leader_exits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            child_pid_path = Path(directory) / "child.pid"
            script = (
                "import os, pathlib, sys, time\n"
                "child = os.fork()\n"
                "if child == 0:\n"
                "    time.sleep(60)\n"
                "else:\n"
                "    pathlib.Path(sys.argv[1]).write_text(str(child))\n"
                "    os._exit(0)\n"
            )

            with self.assertRaisesRegex(CLI.LauncherError, "timed out"):
                CLI._bounded_command_output(
                    [sys.executable, "-c", script, str(child_pid_path)],
                    environment=os.environ,
                    timeout=0.2,
                )

            child_pid = int(child_pid_path.read_text(encoding="utf-8"))
            deadline = time.monotonic() + 2
            while True:
                try:
                    os.kill(child_pid, 0)
                except ProcessLookupError:
                    break
                if time.monotonic() >= deadline:
                    try:
                        os.kill(child_pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    self.fail("probe descendant survived process-group timeout cleanup")
                time.sleep(0.02)

    def test_probe_leader_that_closes_pipes_without_exiting_times_out(self) -> None:
        script = "import os, time\nos.close(1)\nos.close(2)\ntime.sleep(30)\n"

        started = time.monotonic()
        with self.assertRaisesRegex(CLI.LauncherError, "timed out"):
            CLI._bounded_command_output(
                [sys.executable, "-c", script],
                environment=os.environ,
                timeout=0.2,
            )
        self.assertLess(time.monotonic() - started, 5)

    @unittest.skipUnless(hasattr(os, "fork"), "requires POSIX process groups")
    def test_successful_probe_kills_a_closed_pipe_daemon_child(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            child_pid_path = Path(directory) / "child.pid"
            script = (
                "import os, pathlib, sys, time\n"
                "child = os.fork()\n"
                "if child == 0:\n"
                "    os.close(1); os.close(2); time.sleep(60)\n"
                "else:\n"
                "    pathlib.Path(sys.argv[1]).write_text(str(child))\n"
                "    print('1.18.20', flush=True)\n"
                "    os._exit(0)\n"
            )

            result = CLI._bounded_command_output(
                [sys.executable, "-c", script, str(child_pid_path)],
                environment=os.environ,
            )

            self.assertEqual((0, "1.18.20\n", ""), result)
            child_pid = int(child_pid_path.read_text(encoding="utf-8"))
            deadline = time.monotonic() + 2
            while True:
                try:
                    os.kill(child_pid, 0)
                except ProcessLookupError:
                    break
                if time.monotonic() >= deadline:
                    try:
                        os.kill(child_pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    self.fail("probe descendant survived successful cleanup")
                time.sleep(0.02)

    def test_opencode_launch_seeds_runtime_support_before_exec(self) -> None:
        checks = CLI.LaunchChecks(
            CLI.CheckedBinary(
                "cplt", "/trusted/cplt", f"cplt {CLI.SUPPORTED_CPLT_RELEASE}"
            ),
            CLI.CheckedBinary(
                "opencode",
                "/trusted/opencode",
                CLI.MINIMUM_OPENCODE_VERSION_TEXT,
            ),
        )
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
        self.assertIn("version   show", stdout.getvalue())
        self.assertIn("Examples:", stdout.getvalue())
        self.assertIn("grillmester local setup", stdout.getvalue())
        self.assertNotIn("--allow-localhost", stdout.getvalue())
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

    def test_help_with_launch_options_never_reads_or_writes_preferences(self) -> None:
        stdout = io.StringIO()
        with mock.patch.object(CLI, "load_preferences") as load, mock.patch.object(
            CLI, "save_preferences"
        ) as save, mock.patch.object(
            CLI, "check_client_runtime"
        ) as runtime, redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as stopped:
                CLI.main(["--client", "opencode", "--help"])

        self.assertEqual(0, stopped.exception.code)
        self.assertIn("usage: grillmester", stdout.getvalue())
        load.assert_not_called()
        save.assert_not_called()
        runtime.assert_not_called()

    def test_help_after_separator_remains_a_client_argument(self) -> None:
        invocation = CLI.parse_invocation(
            ["--client", "opencode", "--agent", "barista", "--", "--help"],
            cwd=ROOT,
        )
        self.assertEqual(("--help",), invocation.client_args)

    def test_abbreviated_print_flag_is_rejected_before_prompt_or_save(self) -> None:
        stderr = io.StringIO()
        with mock.patch.object(
            CLI.sys, "stdin", TtyBuffer()
        ), mock.patch.object(
            CLI.sys, "stdout", TtyBuffer()
        ), mock.patch.object(CLI, "input", create=True) as prompt, mock.patch.object(
            CLI, "save_preferences"
        ) as save, mock.patch.object(
            CLI, "check_client_runtime"
        ) as runtime, redirect_stderr(stderr):
            result = CLI.main(["--client", "opencode", "--print-c"])

        self.assertEqual(2, result)
        self.assertIn("abbreviated launcher option", stderr.getvalue())
        prompt.assert_not_called()
        save.assert_not_called()
        runtime.assert_not_called()

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
        ) as save, mock.patch.object(
            CLI, "discover_clients", return_value=CLI.CLIENTS
        ), mock.patch.object(
            CLI, "check_client_runtime"
        ) as runtime, mock.patch.object(
            CLI, "_resolve_binary", side_effect=lambda name: f"/trusted/{name}"
        ), redirect_stderr(io.StringIO()):
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
        runtime.assert_not_called()
        save.assert_not_called()
        self.assertIn("ble ikke lagret", stdout.getvalue())
        self.assertIn("--agent opencode", stdout.getvalue())

    def test_print_command_with_client_only_prompts_without_saving(self) -> None:
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
            CLI, "_resolve_binary", return_value="/bin/opencode"
        ), mock.patch.object(
            CLI, "check_client_runtime"
        ) as runtime, mock.patch.object(
            CLI, "_resolve_binary", side_effect=lambda name: f"/bin/{name}"
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

        self.assertEqual(0, result)
        save.assert_not_called()
        runtime.assert_not_called()
        self.assertIn("OpenCode (fra kommandoen)", stdout.getvalue())
        self.assertIn("ble ikke lagret", stdout.getvalue())
        self.assertIn("--agent opencode", stdout.getvalue())

    def test_first_launch_with_missing_fixed_client_fails_before_prompt_or_save(
        self,
    ) -> None:
        stderr = io.StringIO()
        with mock.patch.object(CLI, "load_preferences", return_value=None), mock.patch.object(
            CLI.sys, "stdin", TtyBuffer()
        ), mock.patch.object(
            CLI.sys, "stdout", TtyBuffer()
        ), mock.patch.object(
            CLI, "discover_clients", return_value=("copilot",)
        ), mock.patch.object(
            CLI,
            "_resolve_binary",
            side_effect=CLI.MissingBinaryError(
                "OpenCode was not found on PATH; install it with: brew install opencode"
            ),
        ), mock.patch.object(
            CLI, "input", create=True
        ) as prompt, mock.patch.object(
            CLI, "save_preferences"
        ) as save, redirect_stderr(stderr):
            result = CLI.main(
                [
                    "--client",
                    "opencode",
                    "--print-command",
                    "--project-dir",
                    str(ROOT),
                ]
            )

        self.assertEqual(2, result)
        self.assertIn("OpenCode was not found on PATH", stderr.getvalue())
        prompt.assert_not_called()
        save.assert_not_called()

    def test_print_command_with_agent_only_prompts_without_saving(self) -> None:
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
            CLI, "discover_clients", return_value=CLI.CLIENTS
        ), mock.patch.object(
            CLI, "check_client_runtime"
        ) as runtime, mock.patch.object(
            CLI, "_resolve_binary", side_effect=lambda name: f"/trusted/{name}"
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

        self.assertEqual(0, result)
        save.assert_not_called()
        runtime.assert_not_called()
        self.assertIn("Barista – tydelige utviklingsoppgaver (fra kommandoen)", stdout.getvalue())
        self.assertIn("ble ikke lagret", stdout.getvalue())
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
                CLI, "input", side_effect=["2"], create=True
            ), mock.patch.object(
                CLI, "discover_clients", return_value=("copilot",)
            ), mock.patch.object(
                CLI,
                "check_client_runtime",
                return_value=("copilot", "/bin/copilot (GitHub Copilot CLI 1.0.80.)"),
            ), mock.patch.object(
                CLI, "check_client"
            ) as check_client, mock.patch.object(
                CLI.os, "execvpe"
            ) as execvpe, redirect_stderr(io.StringIO()):
                result = CLI.main(["choose"])

            self.assertEqual(0, result)
            self.assertEqual(
                CLI.Preferences("copilot", "barista"),
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
            ), mock.patch.object(
                CLI, "discover_clients", return_value=CLI.CLIENTS
            ), mock.patch.object(
                CLI,
                "check_client_runtime",
                return_value=("opencode", "/bin/opencode (1.18.20)"),
            ), redirect_stderr(io.StringIO()):
                result = CLI.main(["choose"])

            self.assertEqual(0, result)
            self.assertEqual(
                CLI.Preferences("opencode", "doctor-who"),
                CLI.load_preferences(preferences),
            )

    def test_choose_replaces_unshipped_role_preferences_with_agent_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_home = Path(directory) / "config"
            preferences = config_home / "grillmester/preferences.json"
            preferences.parent.mkdir(parents=True)
            preferences.write_text(
                '{"schemaVersion":1,"client":"copilot","role":"barista"}\n',
                encoding="utf-8",
            )
            stderr = io.StringIO()
            with mock.patch.dict(
                os.environ, {"XDG_CONFIG_HOME": str(config_home)}
            ), mock.patch.object(
                CLI.sys, "stdin", TtyBuffer()
            ), mock.patch.object(
                CLI.sys, "stdout", TtyBuffer()
            ), mock.patch.object(
                CLI, "input", side_effect=["2", "3"], create=True
            ), mock.patch.object(
                CLI, "discover_clients", return_value=CLI.CLIENTS
            ), mock.patch.object(
                CLI,
                "check_client_runtime",
                return_value=("opencode", "/bin/opencode (1.18.20)"),
            ), redirect_stderr(stderr):
                result = CLI.main(["choose"])

            self.assertEqual(0, result)
            self.assertIn("unexpected or missing fields", stderr.getvalue())
            self.assertEqual(
                {
                    "schemaVersion": 1,
                    "client": "opencode",
                    "agent": "designer",
                },
                json.loads(preferences.read_text(encoding="utf-8")),
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
            self.assertEqual(
                {
                    "schemaVersion": 1,
                    "client": "opencode",
                    "agent": "doctor-who",
                },
                json.loads(path.read_text(encoding="utf-8")),
            )
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

    def test_launcher_owned_no_audit_cannot_be_duplicated(self) -> None:
        with self.assertRaisesRegex(CLI.LauncherError, "already enforced"):
            CLI.parse_invocation(
                ["--client", "opencode", "--no-audit"], cwd=ROOT
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

    def test_client_version_is_observed_only_through_the_cplt_agent_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            argv_path = root / "probe-argv"
            client_marker = root / "client-executed-directly"
            cplt = root / "cplt"
            cplt.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = --version ]; then\n"
                f"  printf '%s\\n' 'cplt {CLI.SUPPORTED_CPLT_RELEASE}'\n"
                "  exit 0\n"
                "fi\n"
                f"printf '%s\\n' \"$@\" > '{argv_path}'\n"
                f"printf '%s\\n' '{CLI.MINIMUM_OPENCODE_VERSION_TEXT}'\n",
                encoding="utf-8",
            )
            cplt.chmod(0o700)
            opencode = root / "opencode"
            opencode.write_text(
                "#!/bin/sh\n"
                f"touch '{client_marker}'\n"
                f"printf '%s\\n' '{CLI.MINIMUM_OPENCODE_VERSION_TEXT}'\n",
                encoding="utf-8",
            )
            opencode.chmod(0o700)

            def resolve(name: str) -> str:
                return str({"cplt": cplt, "opencode": opencode}[name])

            with mock.patch.object(CLI, "_resolve_binary", side_effect=resolve):
                checks = CLI.check_client(
                    "opencode", distribution=self.distribution
                )

            self.assertEqual(CLI.MINIMUM_OPENCODE_VERSION_TEXT, checks.client.version)
            self.assertFalse(client_marker.exists())
            probe_argv = argv_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(["--yes", "--quiet", "--no-audit"], probe_argv[:3])
            self.assertEqual("opencode", probe_argv[probe_argv.index("--agent") + 1])
            probe_dir = Path(probe_argv[probe_argv.index("--project-dir") + 1])
            self.assertNotEqual(ROOT, probe_dir)
            self.assertFalse(probe_dir.exists())
            separator = probe_argv.index("--")
            self.assertEqual(
                ["--agent", "grillmester", "--version"],
                probe_argv[separator + 1 :],
            )

    def test_sandboxed_probe_rejects_extra_stdout_lines(self) -> None:
        cplt = CLI.CheckedBinary(
            "cplt", "/bin/cplt", f"cplt {CLI.SUPPORTED_CPLT_RELEASE}"
        )
        with mock.patch.object(
            CLI,
            "_bounded_command_output",
            return_value=(0, "cplt summary\n1.18.20\n", ""),
        ):
            with self.assertRaisesRegex(CLI.LauncherError, "unexpected stdout"):
                CLI._sandboxed_client_version(
                    "opencode",
                    cplt=cplt,
                    distribution=self.distribution,
                )

    def test_sandboxed_copilot_probe_accepts_the_exact_update_hint(self) -> None:
        cplt = CLI.CheckedBinary(
            "cplt", "/bin/cplt", f"cplt {CLI.SUPPORTED_CPLT_RELEASE}"
        )
        output = (
            "GitHub Copilot CLI 1.0.80.\n"
            "Run 'copilot update' to check for updates.\n"
        )
        with mock.patch.object(
            CLI, "_bounded_command_output", return_value=(0, output, "")
        ):
            self.assertEqual(
                "GitHub Copilot CLI 1.0.80.",
                CLI._sandboxed_client_version(
                    "copilot", cplt=cplt, distribution=self.distribution
                ),
            )

    def test_sandboxed_copilot_probe_rejects_unknown_extra_stdout(self) -> None:
        cplt = CLI.CheckedBinary(
            "cplt", "/bin/cplt", f"cplt {CLI.SUPPORTED_CPLT_RELEASE}"
        )
        output = "GitHub Copilot CLI 1.0.80.\nunexpected banner\n"
        with mock.patch.object(
            CLI, "_bounded_command_output", return_value=(0, output, "")
        ):
            with self.assertRaisesRegex(CLI.LauncherError, "unexpected stdout"):
                CLI._sandboxed_client_version(
                    "copilot", cplt=cplt, distribution=self.distribution
                )

    def test_sandboxed_probe_has_a_hard_output_limit(self) -> None:
        with self.assertRaisesRegex(CLI.LauncherError, "output limit"):
            CLI._bounded_command_output(
                [sys.executable, "-c", "import sys; sys.stdout.write('x' * 8192)"],
                environment=os.environ,
                max_output_bytes=1024,
            )

    def test_tested_cplt_and_opencode_baselines_are_accepted(self) -> None:
        with mock.patch.object(
            CLI, "_resolve_binary", side_effect=lambda name: f"/bin/{name}"
        ), mock.patch.object(
            CLI,
            "_trusted_cplt_version_output",
            return_value=f"cplt {CLI.SUPPORTED_CPLT_RELEASE}",
        ), mock.patch.object(
            CLI,
            "_sandboxed_client_version",
            return_value=CLI.MINIMUM_OPENCODE_VERSION_TEXT,
        ) as probe:
            checks = CLI.check_client("opencode")
        self.assertEqual("cplt", checks.cplt.label)
        self.assertEqual("opencode", checks.client.label)
        probe.assert_called_once()

    def test_supported_opencode_v1_range_accepts_newer_minor(self) -> None:
        cplt = CLI.CheckedBinary(
            "cplt", "/bin/cplt", f"cplt {CLI.SUPPORTED_CPLT_RELEASE}"
        )
        with mock.patch.object(
            CLI, "_resolve_binary", return_value="/bin/opencode"
        ), mock.patch.object(
            CLI, "_sandboxed_client_version", return_value="1.19.3"
        ):
            checked = CLI.check_client_runtime(
                "opencode", cplt=cplt, distribution=self.distribution
            )

        self.assertEqual("opencode", checked.label)
        self.assertIn("1.19.3", checked.detail)

    def test_supported_opencode_v1_range_rejects_next_major(self) -> None:
        cplt = CLI.CheckedBinary(
            "cplt", "/bin/cplt", f"cplt {CLI.SUPPORTED_CPLT_RELEASE}"
        )
        with mock.patch.object(
            CLI, "_resolve_binary", return_value="/bin/opencode"
        ), mock.patch.object(
            CLI, "_sandboxed_client_version", return_value="2.0.0"
        ):
            with self.assertRaisesRegex(CLI.LauncherError, "supported 1.x range"):
                CLI.check_client_runtime(
                    "opencode",
                    cplt=cplt,
                    distribution=self.distribution,
                )

    def test_supported_opencode_v1_range_rejects_older_version(self) -> None:
        cplt = CLI.CheckedBinary(
            "cplt", "/bin/cplt", f"cplt {CLI.SUPPORTED_CPLT_RELEASE}"
        )
        with mock.patch.object(
            CLI, "_resolve_binary", return_value="/bin/opencode"
        ), mock.patch.object(
            CLI, "_sandboxed_client_version", return_value="1.18.19"
        ):
            with self.assertRaisesRegex(CLI.LauncherError, "starting at 1.18.20"):
                CLI.check_client_runtime(
                    "opencode",
                    cplt=cplt,
                    distribution=self.distribution,
                )

    def test_opencode_version_parser_rejects_prereleases(self) -> None:
        cplt = CLI.CheckedBinary(
            "cplt", "/bin/cplt", f"cplt {CLI.SUPPORTED_CPLT_RELEASE}"
        )
        with mock.patch.object(
            CLI, "_resolve_binary", return_value="/bin/opencode"
        ), mock.patch.object(
            CLI, "_sandboxed_client_version", return_value="1.18.20-beta.1"
        ):
            with self.assertRaisesRegex(CLI.LauncherError, "prerelease"):
                CLI.check_client_runtime(
                    "opencode",
                    cplt=cplt,
                    distribution=self.distribution,
                )

    def test_opencode_version_parser_rejects_misleading_tool_output(self) -> None:
        cplt = CLI.CheckedBinary(
            "cplt", "/bin/cplt", f"cplt {CLI.SUPPORTED_CPLT_RELEASE}"
        )
        with mock.patch.object(
            CLI, "_resolve_binary", return_value="/bin/opencode"
        ), mock.patch.object(
            CLI,
            "_sandboxed_client_version",
            return_value="bun 1.19.3 opencode 1.17.0",
        ):
            with self.assertRaisesRegex(CLI.LauncherError, "could not parse OpenCode"):
                CLI.check_client_runtime(
                    "opencode",
                    cplt=cplt,
                    distribution=self.distribution,
                )

    def test_wrong_cplt_version_fails_before_client_probe(self) -> None:
        with mock.patch.object(CLI, "_resolve_binary", return_value="/bin/cplt"), mock.patch.object(
            CLI,
            "_trusted_cplt_version_output",
            return_value="cplt 2026.08.16-235959-deadbee",
        ) as version:
            with self.assertRaisesRegex(CLI.LauncherError, "baseline.*or a newer"):
                CLI.check_client("copilot")
        version.assert_called_once_with("/bin/cplt")

    def test_supported_cplt_range_accepts_newer_release(self) -> None:
        newer = "cplt 2026.08.24-120000-deadbee"
        with mock.patch.object(
            CLI, "_resolve_binary", return_value="/bin/cplt"
        ), mock.patch.object(CLI, "_trusted_cplt_version_output", return_value=newer):
            checked = CLI.check_cplt()

        self.assertEqual("cplt", checked.label)
        self.assertIn(newer, checked.detail)

    def test_cplt_same_timestamp_with_different_hash_is_rejected(self) -> None:
        same_stamp = "cplt 2026.08.17-062831-deadbee"
        with mock.patch.object(
            CLI, "_resolve_binary", return_value="/bin/cplt"
        ), mock.patch.object(
            CLI, "_trusted_cplt_version_output", return_value=same_stamp
        ):
            with self.assertRaisesRegex(CLI.LauncherError, "baseline.*or a newer"):
                CLI.check_cplt()

    def test_supported_copilot_semver_range_accepts_newer_patch(self) -> None:
        with mock.patch.object(
            CLI, "_resolve_binary", side_effect=lambda name: f"/bin/{name}"
        ), mock.patch.object(
            CLI,
            "_trusted_cplt_version_output",
            return_value=f"cplt {CLI.SUPPORTED_CPLT_RELEASE}",
        ), mock.patch.object(
            CLI,
            "_sandboxed_client_version",
            return_value="GitHub Copilot CLI 1.0.80.",
        ):
            checks = CLI.check_client("copilot")
        self.assertEqual("cplt", checks.cplt.label)
        self.assertEqual("copilot", checks.client.label)

    def test_supported_copilot_v1_range_accepts_newer_minor(self) -> None:
        cplt = CLI.CheckedBinary(
            "cplt", "/bin/cplt", f"cplt {CLI.SUPPORTED_CPLT_RELEASE}"
        )
        with mock.patch.object(
            CLI, "_resolve_binary", return_value="/bin/copilot"
        ), mock.patch.object(
            CLI,
            "_sandboxed_client_version",
            return_value="GitHub Copilot CLI 1.7.3.",
        ):
            checked = CLI.check_client_runtime(
                "copilot", cplt=cplt, distribution=self.distribution
            )

        self.assertEqual("copilot", checked.label)
        self.assertIn("1.7.3", checked.detail)

    def test_supported_copilot_v1_range_rejects_next_major(self) -> None:
        cplt = CLI.CheckedBinary(
            "cplt", "/bin/cplt", f"cplt {CLI.SUPPORTED_CPLT_RELEASE}"
        )
        with mock.patch.object(
            CLI, "_resolve_binary", return_value="/bin/copilot"
        ), mock.patch.object(
            CLI,
            "_sandboxed_client_version",
            return_value="GitHub Copilot CLI 2.0.0.",
        ):
            with self.assertRaisesRegex(CLI.LauncherError, "supported 1.x range"):
                CLI.check_client_runtime(
                    "copilot", cplt=cplt, distribution=self.distribution
                )

    def test_copilot_version_parser_rejects_prereleases(self) -> None:
        cplt = CLI.CheckedBinary(
            "cplt", "/bin/cplt", f"cplt {CLI.SUPPORTED_CPLT_RELEASE}"
        )
        with mock.patch.object(
            CLI, "_resolve_binary", return_value="/bin/copilot"
        ), mock.patch.object(
            CLI,
            "_sandboxed_client_version",
            return_value="GitHub Copilot CLI 1.0.80-beta.1",
        ):
            with self.assertRaisesRegex(CLI.LauncherError, "prerelease"):
                CLI.check_client_runtime(
                    "copilot",
                    cplt=cplt,
                    distribution=self.distribution,
                )

    def test_old_copilot_cli_is_rejected(self) -> None:
        with mock.patch.object(
            CLI, "_resolve_binary", side_effect=lambda name: f"/bin/{name}"
        ), mock.patch.object(
            CLI,
            "_trusted_cplt_version_output",
            return_value=f"cplt {CLI.SUPPORTED_CPLT_RELEASE}",
        ), mock.patch.object(
            CLI, "_sandboxed_client_version", return_value="0.0.410"
        ):
            with self.assertRaisesRegex(CLI.LauncherError, "starting at 1.0.79"):
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

            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch.object(CLI.shutil, "which", side_effect=which), mock.patch.object(
                CLI,
                "_trusted_cplt_version_output",
                return_value=f"cplt {CLI.SUPPORTED_CPLT_RELEASE}",
            ) as cplt_version, mock.patch.object(
                CLI,
                "_sandboxed_client_version",
                return_value=CLI.MINIMUM_OPENCODE_VERSION_TEXT,
            ), redirect_stdout(stdout), redirect_stderr(stderr):
                result = CLI.doctor(None, root=ROOT)

        self.assertEqual(0, result)
        self.assertEqual("", stderr.getvalue())
        self.assertEqual(1, stdout.getvalue().count("ok  cplt "))
        self.assertIn("skip  copilot", stdout.getvalue())
        self.assertIn("ok  opencode", stdout.getvalue())
        cplt_version.assert_called_once()

    def test_doctor_requires_an_explicitly_selected_client(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cplt = Path(directory) / "cplt"
            cplt.write_text("fixture\n", encoding="utf-8")
            cplt.chmod(0o700)

            def which(name: str) -> str | None:
                return str(cplt) if name == "cplt" else None

            with mock.patch.object(CLI.shutil, "which", side_effect=which), mock.patch.object(
                CLI,
                "_trusted_cplt_version_output",
                return_value=f"cplt {CLI.SUPPORTED_CPLT_RELEASE}",
            ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result = CLI.doctor("copilot", root=ROOT)

        self.assertEqual(1, result)

    def test_doctor_fails_when_no_supported_terminal_client_is_installed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cplt = Path(directory) / "cplt"
            cplt.write_text("fixture\n", encoding="utf-8")
            cplt.chmod(0o700)

            def which(name: str) -> str | None:
                return str(cplt) if name == "cplt" else None

            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch.object(
                CLI.shutil, "which", side_effect=which
            ), mock.patch.object(
                CLI,
                "_trusted_cplt_version_output",
                return_value=f"cplt {CLI.SUPPORTED_CPLT_RELEASE}",
            ), redirect_stdout(stdout), redirect_stderr(stderr):
                result = CLI.doctor(None, root=ROOT)

        self.assertEqual(1, result)
        self.assertIn("skip  copilot", stdout.getvalue())
        self.assertIn("skip  opencode", stdout.getvalue())
        self.assertIn("no supported terminal client", stderr.getvalue())

    def test_explicit_opencode_launch_reports_actionable_error_when_not_installed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binaries = root / "bin"
            binaries.mkdir()
            self._write_version_binary(
                binaries, "cplt", f"cplt {CLI.SUPPORTED_CPLT_RELEASE}"
            )
            environment = {
                **os.environ,
                "HOME": str(root / "home"),
                "PATH": str(binaries),
                "XDG_CONFIG_HOME": str(root / "config"),
            }
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/grillmester.py"),
                    "--client",
                    "opencode",
                    "--agent",
                    "barista",
                    "--project-dir",
                    str(ROOT),
                    "--print-command",
                ],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertIn("OpenCode was not found on PATH", result.stderr)
        self.assertIn("brew install opencode", result.stderr)

    def test_installed_copilot_cli_works_without_opencode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binaries = root / "bin"
            binaries.mkdir()
            cplt = self._write_version_binary(
                binaries, "cplt", f"cplt {CLI.SUPPORTED_CPLT_RELEASE}"
            )
            resolved_cplt = str(cplt.resolve(strict=True))
            self._write_version_binary(
                binaries, "copilot", "GitHub Copilot CLI 1.0.80."
            )
            environment = {
                **os.environ,
                "HOME": str(root / "home"),
                "PATH": str(binaries),
                "XDG_CONFIG_HOME": str(root / "config"),
            }
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/grillmester.py"),
                    "--client",
                    "copilot",
                    "--agent",
                    "barista",
                    "--project-dir",
                    str(ROOT),
                    "--print-command",
                ],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        self.assertIn(resolved_cplt, result.stdout)
        self.assertIn("--agent copilot", result.stdout)
        self.assertIn("--agent grillmester:barista", result.stdout)
        self.assertNotIn("opencode", shlex.split(result.stdout))

    def test_local_print_command_locates_binaries_without_executing_version_probes(self) -> None:
        observed: dict[str, object] = {}

        def local_main(arguments, *, distribution_root, binary_resolver):
            observed["arguments"] = list(arguments)
            observed["root"] = distribution_root
            observed["binaries"] = binary_resolver("opencode", False, ROOT)
            return 0

        local_module = mock.Mock()
        local_module.main = local_main
        local_module.normalize_cli_arguments = self.local_normalize
        with (
            mock.patch.object(CLI, "_load_local_mode_module", return_value=local_module),
            mock.patch.object(CLI, "load_distribution", return_value=self.distribution),
            mock.patch.object(
                CLI,
                "_resolve_binary",
                side_effect=lambda name: f"/resolved/{name}",
            ) as locate,
            mock.patch.object(
                CLI,
                "check_client",
                side_effect=AssertionError("print must not execute a client probe"),
            ) as checked,
        ):
            result = CLI._run_local_mode(["--client", "opencode", "--print-command"])

        self.assertEqual(0, result)
        self.assertEqual(
            ["launch", "--client", "opencode", "--print-command"],
            observed["arguments"],
        )
        self.assertEqual(self.distribution.root, observed["root"])
        cplt, client = observed["binaries"]
        self.assertEqual("/resolved/cplt", cplt.path)
        self.assertEqual("/resolved/opencode", client.path)
        self.assertEqual([mock.call("cplt"), mock.call("opencode")], locate.call_args_list)
        checked.assert_not_called()

    def test_local_help_alias_uses_the_local_help_surface_without_runtime_checks(
        self,
    ) -> None:
        observed: dict[str, object] = {}

        def local_main(arguments, *, distribution_root, binary_resolver):
            observed["arguments"] = list(arguments)
            observed["root"] = distribution_root
            observed["resolver"] = binary_resolver
            return 0

        local_module = mock.Mock()
        local_module.main = local_main
        local_module.normalize_cli_arguments = self.local_normalize
        with (
            mock.patch.object(CLI, "_load_local_mode_module", return_value=local_module),
            mock.patch.object(
                CLI,
                "load_distribution",
                side_effect=AssertionError("help must not load the distribution"),
            ),
        ):
            result = CLI._run_local_mode(["help"])

        self.assertEqual(0, result)
        self.assertEqual(["--help"], observed["arguments"])
        self.assertIsNone(observed["root"])
        self.assertIsNone(observed["resolver"])

    def test_local_run_preview_uses_distribution_binaries_without_version_probes(
        self,
    ) -> None:
        observed: dict[str, object] = {}

        def local_main(arguments, *, distribution_root, binary_resolver):
            observed["arguments"] = list(arguments)
            observed["root"] = distribution_root
            observed["binaries"] = binary_resolver("opencode", False, ROOT)
            return 0

        local_module = mock.Mock()
        local_module.main = local_main
        local_module.normalize_cli_arguments = self.local_normalize
        with (
            mock.patch.object(CLI, "_load_local_mode_module", return_value=local_module),
            mock.patch.object(CLI, "load_distribution", return_value=self.distribution),
            mock.patch.object(
                CLI,
                "_resolve_binary",
                side_effect=lambda name: f"/resolved/{name}",
            ) as locate,
            mock.patch.object(
                CLI,
                "check_client",
                side_effect=AssertionError("preview must not execute a client probe"),
            ) as checked,
        ):
            result = CLI._run_local_mode(
                [
                    "run",
                    "--client",
                    "opencode",
                    "--print-command",
                    "Fix the failing test",
                ]
            )

        self.assertEqual(0, result)
        self.assertEqual(
            [
                "run",
                "--client",
                "opencode",
                "--print-command",
                "Fix the failing test",
            ],
            observed["arguments"],
        )
        self.assertEqual(self.distribution.root, observed["root"])
        cplt, client = observed["binaries"]
        self.assertEqual("/resolved/cplt", cplt.path)
        self.assertEqual("/resolved/opencode", client.path)
        self.assertEqual([mock.call("cplt"), mock.call("opencode")], locate.call_args_list)
        checked.assert_not_called()

    def test_local_run_accepts_one_shot_options_before_the_subcommand(self) -> None:
        observed: dict[str, object] = {}

        def local_main(arguments, *, distribution_root, binary_resolver):
            observed["arguments"] = list(arguments)
            return 0

        local_module = mock.Mock()
        local_module.main = local_main
        local_module.normalize_cli_arguments = self.local_normalize
        with (
            mock.patch.object(CLI, "_load_local_mode_module", return_value=local_module),
            mock.patch.object(CLI, "load_distribution", return_value=self.distribution),
        ):
            result = CLI._run_local_mode(
                ["--client", "opencode", "--full", "run", "Fix the failing test"]
            )

        self.assertEqual(0, result)
        self.assertEqual(
            ["run", "--client", "opencode", "--full", "Fix the failing test"],
            observed["arguments"],
        )

    def test_local_launch_uses_the_standard_compatible_client_gate(self) -> None:
        observed: dict[str, object] = {}
        checks = CLI.LaunchChecks(
            CLI.CheckedBinary("cplt", "/checked/cplt", "cplt newer"),
            CLI.CheckedBinary("opencode", "/checked/opencode", "1.99.0"),
        )

        def local_main(arguments, *, distribution_root, binary_resolver):
            observed["arguments"] = list(arguments)
            observed["binaries"] = binary_resolver("opencode", True, ROOT)
            return 0

        local_module = mock.Mock()
        local_module.main = local_main
        local_module.normalize_cli_arguments = self.local_normalize
        probe = mock.Mock(environment={}, cplt_arguments=())
        local_module.prepare_client_version_probe = mock.Mock(return_value=probe)
        local_module.cleanup_client_version_probe = mock.Mock()
        with (
            mock.patch.object(CLI, "_load_local_mode_module", return_value=local_module),
            mock.patch.object(CLI, "load_distribution", return_value=self.distribution),
            mock.patch.object(
                CLI,
                "_resolve_binary",
                side_effect=lambda name: f"/checked/{name}",
            ),
            mock.patch.object(CLI, "check_cplt", return_value=checks.cplt),
            mock.patch.object(
                CLI, "check_client_runtime", return_value=checks.client
            ) as check_runtime,
        ):
            result = CLI._run_local_mode(["--client", "opencode"])

        self.assertEqual(0, result)
        self.assertEqual(["launch", "--client", "opencode"], observed["arguments"])
        self.assertEqual((checks.cplt, checks.client), observed["binaries"])
        self.assertEqual("/checked/cplt", local_module.prepare_client_version_probe.call_args.kwargs["cplt"])
        check_runtime.assert_called_once()
        self.assertEqual("opencode", check_runtime.call_args.args[0])
        local_module.cleanup_client_version_probe.assert_called_once_with(probe)

    def test_local_run_uses_the_standard_compatible_client_gate(self) -> None:
        observed: dict[str, object] = {}
        checks = CLI.LaunchChecks(
            CLI.CheckedBinary("cplt", "/checked/cplt", "cplt newer"),
            CLI.CheckedBinary("opencode", "/checked/opencode", "1.99.0"),
        )

        def local_main(arguments, *, distribution_root, binary_resolver):
            observed["arguments"] = list(arguments)
            observed["binaries"] = binary_resolver("opencode", True, ROOT)
            return 0

        local_module = mock.Mock()
        local_module.main = local_main
        local_module.normalize_cli_arguments = self.local_normalize
        probe = mock.Mock(environment={}, cplt_arguments=())
        local_module.prepare_client_version_probe = mock.Mock(return_value=probe)
        local_module.cleanup_client_version_probe = mock.Mock()
        with (
            mock.patch.object(CLI, "_load_local_mode_module", return_value=local_module),
            mock.patch.object(CLI, "load_distribution", return_value=self.distribution),
            mock.patch.object(
                CLI,
                "_resolve_binary",
                side_effect=lambda name: f"/checked/{name}",
            ),
            mock.patch.object(CLI, "check_cplt", return_value=checks.cplt),
            mock.patch.object(
                CLI, "check_client_runtime", return_value=checks.client
            ) as check_runtime,
        ):
            result = CLI._run_local_mode(
                ["run", "--client", "opencode", "Fix the failing test"]
            )

        self.assertEqual(0, result)
        self.assertEqual(
            ["run", "--client", "opencode", "Fix the failing test"],
            observed["arguments"],
        )
        self.assertEqual((checks.cplt, checks.client), observed["binaries"])
        check_runtime.assert_called_once()
        self.assertEqual("opencode", check_runtime.call_args.args[0])
        local_module.cleanup_client_version_probe.assert_called_once_with(probe)


if __name__ == "__main__":
    unittest.main()
