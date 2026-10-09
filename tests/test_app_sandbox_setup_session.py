"""Login-shell observations use injected runners and a disposable HOME only."""

import contextlib
import io
import json
import os
import subprocess
import unittest
from unittest import mock

import test_app_sandbox_setup as fixtures


class SessionTest(unittest.TestCase):
    setUp = fixtures.AppSandboxSetupTest.setUp

    def test_one_login_run_captures_unexported_zdotdir_and_selects_that_profile(self):
        from app_sandbox import cli, toolchain_discovery
        dot = self.home / "from-zshenv"
        dot.mkdir()
        env = {"SHELL": "/fixture/zsh", "HOME": str(self.home), "ZDOTDIR": ""}
        values = {key: "" for key in ("PATH", "JAVA_HOME", "ZDOTDIR", "MISE_DATA_DIR",
                                      "XDG_DATA_HOME", "ASDF_DATA_DIR", "SDKMAN_CANDIDATES_DIR")}
        # Python sees an unset/unexported ZDOTDIR; the shell's printf knows it.
        values["PATH"] = "/usr/bin"
        stdout = "/usr/bin\0" + str(dot) + "\0" + json.dumps(values)
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, stdout, ""))
        captured, warning = self._session_environment(self.home, env, runner)
        self.assertIsNone(warning)
        self.assertEqual(str(dot), captured["ZDOTDIR"])
        self.assertEqual(1, runner.call_count)
        original = toolchain_discovery.shutil.which
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(toolchain_discovery, "session_environment", return_value=(captured, None)) as capture, \
                mock.patch.object(toolchain_discovery, "managers", return_value={"mise": "/fixture/mise"}), \
                mock.patch.object(toolchain_discovery.shutil, "which", side_effect=lambda tool, **kw:
                                  "/usr/bin/java" if tool == "java" else original(tool, **kw)):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = cli.main(["profile", "plan", "--home", str(self.home), "--db", str(self.db),
                                 "--shell", "/fixture/zsh", "--tool", "java", "--json"])
        self.assertEqual(0, code, output.getvalue())
        self.assertEqual(str(dot / ".zprofile"), json.loads(output.getvalue())["target"])
        self.assertEqual(1, capture.call_count)

    def test_default_plan_reuses_capture_for_projects_and_profile_hardening(self):
        from app_sandbox import profile, toolchain_discovery
        repo = self.home / "code/repository"
        (repo / ".mise.toml").write_text('[tools]\nnode = "24"\n')
        other = self.home / "code/other"
        other.mkdir()
        (other / ".mise.toml").write_text('[tools]\nnode = "24"\n')
        import sqlite3
        with sqlite3.connect(str(self.db)) as db:
            db.execute("INSERT INTO projects(id,name,main_repo_path) VALUES (?,?,?)",
                       ("p2", "second", str(other)))
        dot = self.home / "zshenv-dot"
        dot.mkdir()
        shims = str(self.home / ".local/share/mise/shims")
        config = {"shell": "zsh", "tools": ["java"], "shims": shims, "java_home": None,
                  "readonly": [shims, str(dot / ".zprofile")]}
        (dot / ".zprofile").write_text(profile.block(config))
        snapshot = {"PATH": "", "ZDOTDIR": str(dot)}
        with mock.patch.dict(os.environ, {"SHELL": "/fixture/zsh", "ZDOTDIR": ""}), \
                mock.patch.object(toolchain_discovery, "session_environment", return_value=(snapshot, None)) as capture:
            code, output = fixtures.AppSandboxSetupTest.run_cli(self, "plan", "--json")
        self.assertEqual(0, code, output)
        self.assertEqual(1, capture.call_count)
        self.assertTrue(all(shims in item["diff"]["readonlyPaths"]["added"]
                            for item in json.loads(output)["projects"]))

    def test_relative_or_invalid_login_zdotdir_refuses_profile_write_clearly(self):
        from app_sandbox import cli, toolchain_discovery
        for dot in ("relative", "bad\nvalue", str(self.home / "child/../elsewhere")):
            with self.subTest(dot=dot), \
                    mock.patch.object(toolchain_discovery, "session_environment",
                                      return_value=({"PATH": "/usr/bin", "JAVA_HOME": "", "ZDOTDIR": dot}, None)):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = cli.main(["profile", "plan", "--home", str(self.home), "--db", str(self.db),
                                     "--shell", "/fixture/zsh"])
                self.assertEqual(1, code, output.getvalue())
                self.assertIn("Invalid ZDOTDIR", output.getvalue())
                self.assertNotIn("Traceback", output.getvalue())
                self.assertFalse((self.home / ".zprofile").exists())
                self.assertFalse((self.home / ".copilot/app-sandbox-setup-backups").exists())
