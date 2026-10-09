"""Opt-in profile flow; every filesystem and shell boundary is a fixture."""

import json
import os
import sqlite3
import unittest
from unittest import mock

import test_app_sandbox_setup as fixtures


class ProfileTest(unittest.TestCase):
    policies = fixtures.AppSandboxSetupTest.policies

    def setUp(self):
        fixtures.AppSandboxSetupTest.setUp(self)
        self.session_bin = self.home / ".nvm/versions/node/24/bin"
        self.session_bin.mkdir(parents=True)
        for tool in ("node", "pnpm"):
            path = self.session_bin / tool
            path.touch()
            path.chmod(0o700)

    def run_cli(self, group, action, *options, session=None, managers=None, environment=None):
        import contextlib
        import io
        from app_sandbox import cli, toolchain_discovery
        output = io.StringIO()
        env = {"HOME": str(self.home), "SHELL": "/bin/zsh",
               "ZDOTDIR": "", "MISE_DATA_DIR": "", "XDG_DATA_HOME": "",
               "JAVA_HOME": "", "ASDF_DATA_DIR": "", "SDKMAN_CANDIDATES_DIR": ""}
        env.update(environment or {})
        session = session if session is not None else {"PATH": str(self.session_bin) + ":/usr/bin",
                                                       "JAVA_HOME": ""}
        original_which = toolchain_discovery.shutil.which
        def which(tool, **kwargs):
            if tool == "java":
                local = self.session_bin / "java"
                if str(self.session_bin) in kwargs.get("path", "").split(os.pathsep) and local.exists():
                    return str(local)
                return "/usr/bin/java" if "/usr/bin" in kwargs.get("path", "").split(os.pathsep) else None
            return original_which(tool, **kwargs)
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(toolchain_discovery.shutil, "which", side_effect=which), \
                mock.patch.object(toolchain_discovery, "session_environment",
                                  return_value=(session, None)), \
                mock.patch.object(toolchain_discovery, "managers",
                                  return_value=managers if managers is not None else
                                  {"mise": str(self.home / ".local/bin/mise")}), \
                contextlib.redirect_stdout(output):
            code = cli.main([group, action, "--home", str(self.home), "--db", str(self.db), *options])
        return code, output.getvalue()

    def test_profile_plan_apply_preserves_text_and_protects_shims_before_activation(self):
        repo2 = self.home / "code/second"
        repo2.mkdir()
        with sqlite3.connect(str(self.db)) as db:
            db.execute("INSERT INTO projects(id,name,main_repo_path) VALUES (?,?,?)",
                       ("p2", "second", str(repo2)))
        path = self.home / ".zprofile"
        path.write_text("# user\n")
        path.chmod(0o640)
        code, output = self.run_cli("profile", "plan", "--json")
        self.assertEqual(0, code, output)
        plan = json.loads(output)
        self.assertEqual(["java"], plan["tools"])
        self.assertFalse((self.home / ".copilot/app-sandbox-setup-backups").exists())
        code, output = self.run_cli("profile", "apply", "--confirm", plan["digest"])
        self.assertEqual(0, code, output)
        self.assertTrue(path.read_text().startswith("# user\n"))
        self.assertIn("case", path.read_text())
        self.assertIn(str(self.home / ".local/share/mise/shims"), self.policies()[0]["readonlyPaths"])
        self.assertIn(str(self.home / ".local/bin"), self.policies()[0]["readonlyPaths"])
        self.assertIn(str(path), self.policies()[0]["readonlyPaths"])
        self.assertEqual(2, len(self.policies()))
        self.assertTrue(all(str(self.home / ".local/share/mise/shims") in p["readonlyPaths"]
                            for p in self.policies()))
        with sqlite3.connect(str(self.db)) as db:
            self.assertEqual(0, db.execute("SELECT sandbox_enabled FROM projects").fetchone()[0])
        self.assertEqual(0o640, path.stat().st_mode & 0o777)
        backup = next((self.home / ".copilot/app-sandbox-setup-backups").glob(".zprofile.*"))
        self.assertEqual("# user\n", backup.read_text())
        self.assertEqual(0o600, backup.stat().st_mode & 0o777)
        self.assertIn("Quit and restart the GitHub Copilot app completely", output)
        code, output = self.run_cli("profile", "plan")
        self.assertEqual(0, code, output)
        self.assertIn("no changes", output)

    def jdk(self, major, relative=None):
        path = self.home / (relative or ".sdkman/candidates/java/" + major)
        (path / "bin").mkdir(parents=True)
        (path / "bin/java").touch()
        (path / "bin/java").chmod(0o700)
        (path / "release").write_text('JAVA_VERSION="' + major + '.0.2"\n')
        return path

    def test_java_home_requires_explicit_validated_choice_without_mise(self):
        path = self.jdk("25")
        for flags, expected in (((), False), (("--java-home", str(path)), True),
                                (("--java-home", "auto"), True)):
            (self.home / "code/repository/.java-version").write_text("25")
            code, output = self.run_cli("profile", "plan", *flags, "--json", managers={})
            self.assertEqual(0, code, output)
            block = json.loads(output)["block"]
            self.assertEqual(expected, 'export JAVA_HOME=' in block)
            if expected:
                self.assertIn('[ -z "$JAVA_HOME" ] && export JAVA_HOME=', block)
                self.assertIn(str(path), block)
        code, output = self.run_cli("profile", "plan", "--java-home", str(path / "missing"), managers={})
        self.assertEqual(1, code, output)
        self.assertIn("validated JDK", output)
        code, output = self.run_cli("profile", "plan", "--shell", "/usr/bin/fish",
                                    "--java-home", str(path), "--json", managers={})
        self.assertEqual(0, code, output)
        block = json.loads(output)["block"]
        self.assertIn("if not set -q JAVA_HOME", block)
        self.assertIn("set -gx JAVA_HOME " + str(path), block)
        self.assertNotIn("export JAVA_HOME", block)

    def test_shell_targets_zdotdir_bash_precedence_fish_and_unknown(self):
        from app_sandbox import profile
        dotdir = self.home / "z-dot"
        cases = [("/bin/zsh", {}, self.home / ".zprofile"),
                 ("/bin/zsh", {"ZDOTDIR": str(dotdir)}, dotdir / ".zprofile"),
                 ("/bin/bash", {}, self.home / ".bash_profile"),
                 ("/usr/bin/fish", {}, self.home / ".config/fish/conf.d/app-sandbox-setup.fish")]
        for shell, env, target in cases:
            with self.subTest(shell=shell, env=env):
                code, output = self.run_cli("profile", "plan", "--shell", shell, "--json", environment=env)
                self.assertEqual(0, code, output)
                plan = json.loads(output)
                self.assertEqual(str(target), plan["target"])
                code, output = self.run_cli("profile", "apply", "--shell", shell,
                                            "--confirm", plan["digest"], environment=env)
                self.assertEqual(0, code, output)
                if shell.endswith("fish"):
                    self.assertIn("if not contains --", target.read_text())
                    self.assertIn("set -gx PATH", target.read_text())
                    self.assertNotIn("export", target.read_text())
                target.unlink()
        for first in (".profile", ".bash_login", ".bash_profile"):
            (self.home / first).write_text("# fixture")
            code, output = self.run_cli("profile", "plan", "--shell", "/bin/bash", "--json")
            self.assertEqual(0, code, output)
            self.assertEqual(str(self.home / first), json.loads(output)["target"])
        before = self.db.read_bytes()
        code, output = self.run_cli("profile", "plan", "--shell", "/bin/other", "--json")
        self.assertEqual(0, code, output)
        plan = json.loads(output)
        self.assertFalse(plan["changed"])
        self.assertIsNone(plan["target"])
        self.assertIn("instructions only", output)
        code, output = self.run_cli("profile", "apply", "--shell", "/bin/other", "--confirm", plan["digest"])
        self.assertEqual(0, code, output)
        self.assertEqual(before, self.db.read_bytes())
        self.assertFalse((self.home / ".zshenv").exists())
        self.db.unlink()
        code, output = self.run_cli("profile", "plan", "--shell", "/bin/other")
        self.assertEqual(0, code, output)
        self.assertIn("instructions only", output)
        old = profile.BEGIN + "\nold\n" + profile.END
        new = profile.BEGIN + "\nnew\n" + profile.END
        for user in ("", "user", "user\n", "user\n\n"):
            merged = profile.merge(user, new)
            self.assertEqual(merged, profile.merge(merged, new))
            self.assertEqual(user, profile.merge(merged, ""))
        self.assertEqual("before\n" + new + "\nafter",
                         profile.merge("before\n" + old + "\nafter", new))

    def test_malformed_markers_symlinked_file_and_parents_refused_before_db_write(self):
        from app_sandbox import profile
        path = self.home / ".zprofile"
        for text in (profile.BEGIN, profile.END, profile.BEGIN + "\n" + profile.END + "\n" + profile.BEGIN,
                     profile.END + "\n" + profile.BEGIN, profile.BEGIN.replace("v1", "v2"),
                     profile.BEGIN + "\nprivate fixture text\n" + profile.END):
            path.write_text(text)
            before = self.db.read_bytes()
            code, output = self.run_cli("profile", "plan")
            self.assertEqual(1, code, output)
            self.assertNotIn("private fixture text", output)
            self.assertEqual(before, self.db.read_bytes())
        path.unlink()
        target = self.home / "target"
        target.write_text("# target")
        path.symlink_to(target)
        code, output = self.run_cli("profile", "plan")
        self.assertEqual(1, code, output)
        self.assertIn("symlink", output)
        self.assertEqual("# target", target.read_text())
        with mock.patch.dict(os.environ, {"SHELL": "/bin/zsh", "ZDOTDIR": ""}):
            code, output = fixtures.AppSandboxSetupTest.run_cli(self, "plan")
        self.assertEqual(0, code, output)
        self.assertIn("Profile opt-in state unavailable", output)
        path.unlink()
        directory = self.home / "real"
        directory.mkdir()
        linked = self.home / "linked"
        linked.symlink_to(directory, target_is_directory=True)
        code, output = self.run_cli("profile", "plan", environment={"ZDOTDIR": str(linked)})
        self.assertEqual(1, code, output)
        self.assertFalse((directory / ".zprofile").exists())

    def test_remove_preserves_user_text_and_next_policy_plan_drops_shims(self):
        from app_sandbox import cli, toolchain_discovery
        path = self.home / ".zprofile"
        path.write_text("# keep")
        code, output = self.run_cli("profile", "plan", "--json")
        self.assertEqual(0, code, output)
        code, output = self.run_cli("profile", "apply", "--confirm", json.loads(output)["digest"])
        self.assertEqual(0, code, output)
        with mock.patch.dict(os.environ, {"SHELL": "/bin/zsh", "ZDOTDIR": "", "MISE_DATA_DIR": "",
                                         "XDG_DATA_HOME": ""}), \
                mock.patch.object(toolchain_discovery, "managers", return_value={}):
            # Default plan sees the discovery fact without performing shell activation.
            connection = cli.store.open_db(self.db)
            try:
                policy_plan = cli.compute_plan(connection, self.home, None)
            finally:
                connection.close()
            self.assertIn(str(self.home / ".local/share/mise/shims"),
                          policy_plan["projects"][0]["after"]["policy"]["readonlyPaths"])
        code, output = self.run_cli("profile", "remove", "--json")
        self.assertEqual(0, code, output)
        plan = json.loads(output)
        self.assertNotEqual("", plan["digest"])
        self.assertNotEqual("# keep", path.read_text())
        code, output = self.run_cli("profile", "remove", "--confirm", plan["digest"])
        self.assertEqual(0, code, output)
        self.assertEqual("# keep", path.read_text())
        with mock.patch.dict(os.environ, {"SHELL": "/bin/zsh", "ZDOTDIR": "", "MISE_DATA_DIR": "",
                                         "XDG_DATA_HOME": ""}):
            connection = cli.store.open_db(self.db)
            try:
                policy_plan = cli.compute_plan(connection, self.home, None)
            finally:
                connection.close()
        self.assertNotIn(str(self.home / ".local/share/mise/shims"),
                         policy_plan["projects"][0]["after"]["policy"]["readonlyPaths"])

    def test_nothing_failing_and_existing_java_home_never_moved(self):
        java = self.session_bin / "java"
        java.touch()
        java.chmod(0o700)
        for session in ({"PATH": str(self.session_bin), "JAVA_HOME": ""},
                        {"PATH": str(self.session_bin) + ":/usr/bin", "JAVA_HOME": "/fixture/jdk"}):
            code, output = self.run_cli("profile", "plan", "--json", session=session)
            self.assertEqual(0, code, output)
            plan = json.loads(output)
            self.assertFalse(plan["changed"])
            self.assertEqual("", plan["block"])
        java.unlink()
        code, output = self.run_cli("profile", "plan", "--json",
                                    session={"PATH": "/usr/bin", "JAVA_HOME": "/existing/jdk"})
        self.assertEqual(0, code, output)
        self.assertEqual(["node", "pnpm"], json.loads(output)["tools"])
        self.assertNotIn("export JAVA_HOME=", output)

    def test_conflicting_auto_majors_refused_with_per_project_explanation(self):
        self.jdk("25")
        repo = self.home / "code/repository"
        (repo / ".java-version").write_text("25")
        other = self.home / "code/other"
        other.mkdir()
        (other / ".java-version").write_text("21")
        with sqlite3.connect(str(self.db)) as db:
            db.execute("INSERT INTO projects(id,name,main_repo_path) VALUES (?,?,?)",
                       ("p2", "other", str(other)))
        code, output = self.run_cli("profile", "plan", "--java-home", "auto", managers={})
        self.assertEqual(1, code, output)
        self.assertIn("different Java majors", output)
        self.assertIn("per-project instructions", output)
        self.assertFalse((self.home / ".zprofile").exists())

    def test_digest_binds_file_mode_policy_and_target_and_failure_keeps_committed_readonly(self):
        from app_sandbox import profile_store
        code, output = self.run_cli("profile", "plan", "--json")
        self.assertEqual(0, code, output)
        digest = json.loads(output)["digest"]
        path = self.home / ".zprofile"
        path.write_text("# concurrent")
        code, output = self.run_cli("profile", "apply", "--confirm", digest)
        self.assertEqual(4, code, output)
        code, output = self.run_cli("profile", "plan", "--json")
        digest = json.loads(output)["digest"]
        path.chmod(0o640)
        code, output = self.run_cli("profile", "apply", "--confirm", digest)
        self.assertEqual(4, code, output)
        code, output = self.run_cli("profile", "plan", "--json")
        digest = json.loads(output)["digest"]
        with sqlite3.connect(str(self.db)) as db:
            db.execute("INSERT INTO project_sandbox_policies VALUES (?,?)",
                       ("p1", '{"readonlyPaths":["/fixture/new"]}'))
        code, output = self.run_cli("profile", "apply", "--confirm", digest)
        self.assertEqual(4, code, output)
        code, output = self.run_cli("profile", "plan", "--json")
        digest = json.loads(output)["digest"]
        other = self.home / "other-zdot"
        code, output = self.run_cli("profile", "apply", "--confirm", digest,
                                    environment={"ZDOTDIR": str(other)})
        self.assertEqual(4, code, output)
        def failing_write(*args):
            self.assertIn(str(self.home / ".local/share/mise/shims"),
                          self.policies()[0]["readonlyPaths"])
            raise OSError("private fixture error")
        with mock.patch.object(profile_store, "write", side_effect=failing_write):
            code, output = self.run_cli("profile", "apply", "--confirm", digest)
        self.assertEqual(1, code, output)
        self.assertIn("AFTER DB commit", output)
        self.assertIn("readonly shims stay committed", output)
        self.assertNotIn("private fixture error", output)
        self.assertEqual("# concurrent", path.read_text())
        self.assertIn(str(self.home / ".local/share/mise/shims"), self.policies()[0]["readonlyPaths"])

    def test_post_replace_sync_failure_reports_uncertain_profile_state_not_false_rollback(self):
        import stat
        from app_sandbox import profile, profile_store
        code, output = self.run_cli("profile", "plan", "--json")
        self.assertEqual(0, code, output)
        digest = json.loads(output)["digest"]
        fsync = os.fsync
        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("private fixture error")
            return fsync(fd)
        with mock.patch.object(profile_store.os, "fsync", side_effect=fail_directory):
            code, output = self.run_cli("profile", "apply", "--confirm", digest)
        self.assertEqual(1, code, output)
        self.assertIn(profile.BEGIN, (self.home / ".zprofile").read_text())
        self.assertIn("readonly shims stay committed", output)
        self.assertNotIn("Profile not activated", output)
        self.assertNotIn("private fixture error", output)

    def test_session_environment_runner_is_injectable_bounded_and_preserves_toolchain_settings(self):
        import subprocess
        from app_sandbox import toolchain_discovery
        env = {"SHELL": "/bin/zsh", "HOME": "/not-used", "ZDOTDIR": str(self.home / "dot"),
               "JAVA_HOME": str(self.home / "jdk"), "MISE_DATA_DIR": str(self.home / "mise-data"),
               "TOKEN": "private fixture value"}
        keys = ("PATH", "JAVA_HOME", "MISE_DATA_DIR", "XDG_DATA_HOME",
                "ASDF_DATA_DIR", "SDKMAN_CANDIDATES_DIR", "ZDOTDIR")
        response = {key: env.get(key, "") for key in keys}
        response["PATH"] = str(self.session_bin)
        encoded = response["PATH"] + "\0" + response["ZDOTDIR"] + "\0" + json.dumps(response)
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, encoded, ""))
        result, warning = self._session_environment(self.home, env, runner)
        self.assertEqual(response, result)
        self.assertIsNone(warning)
        call = runner.call_args
        self.assertEqual(10, call.kwargs["timeout"])
        self.assertEqual(subprocess.DEVNULL, call.kwargs["stdin"])
        self.assertEqual(str(self.home), call.kwargs["env"]["HOME"])
        self.assertEqual(env["ZDOTDIR"], call.kwargs["env"]["ZDOTDIR"])
        self.assertEqual(env["JAVA_HOME"], call.kwargs["env"]["JAVA_HOME"])
        self.assertEqual(env["MISE_DATA_DIR"], call.kwargs["env"]["MISE_DATA_DIR"])
        self.assertNotIn("TOKEN", call.kwargs["env"])
        for failure in (subprocess.CompletedProcess([], 1, "private fixture value", ""),
                        subprocess.CompletedProcess([], 0, '{"PATH": "private fixture value"}', ""),
                        subprocess.TimeoutExpired("private fixture value", 10)):
            runner = mock.Mock(side_effect=failure if isinstance(failure, Exception) else None,
                               return_value=failure)
            result, warning = self._session_environment(self.home, env, runner)
            self.assertIsNone(result)
            self.assertNotIn("private fixture value", warning)

    def test_custom_mise_data_shim_alias_and_tool_filter_are_digest_bound(self):
        data = self.home / "custom-mise"
        data.mkdir()
        real = self.home / "real-shims"
        real.mkdir()
        (data / "shims").symlink_to(real, target_is_directory=True)
        env = {"MISE_DATA_DIR": str(data)}
        code, output = self.run_cli("profile", "plan", "--tool", "java", "--json", environment=env)
        self.assertEqual(0, code, output)
        plan = json.loads(output)
        self.assertEqual(["java"], plan["tools"])
        self.assertIn(str(data / "shims"), plan["readonly"])
        self.assertIn(str(real), plan["readonly"])
        self.assertNotIn("mise activate", plan["block"])
        code, output = self.run_cli("profile", "apply", "--tool", "java", "--confirm", plan["digest"])
        self.assertEqual(4, code, output)
        code, output = self.run_cli("profile", "apply", "--tool", "java",
                                    "--confirm", plan["digest"], environment=env)
        self.assertEqual(0, code, output)
        self.assertIn(str(real), self.policies()[0]["readonlyPaths"])
        (self.home / ".zprofile").unlink()
        (data / "shims").unlink()
        (data / "shims").symlink_to(self.home, target_is_directory=True)
        code, output = self.run_cli("profile", "plan", "--tool", "java", environment=env)
        self.assertEqual(1, code, output)


if __name__ == "__main__":
    unittest.main()
