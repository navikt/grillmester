"""Fixture-only toolchain/instructions contract through plan/apply."""

import json
import sqlite3
import unittest
from unittest import mock

import test_app_sandbox_setup as fixtures


class ToolchainTest(unittest.TestCase):
    setUp = fixtures.AppSandboxSetupTest.setUp
    run_cli = fixtures.AppSandboxSetupTest.run_cli
    digest = fixtures.AppSandboxSetupTest.digest
    policies = fixtures.AppSandboxSetupTest.policies

    def test_gradle_without_java_pin_warns_once_without_default_or_instructions(self):
        repo = self.home / "code/repository"
        (repo / "gradlew").touch()
        (repo / ".mise.toml").write_text('[tools]\nnode = "24"\n')
        for major in ("21", "25"):
            path = self.home / ".sdkman/candidates/java" / major
            (path / "bin").mkdir(parents=True)
            (path / "bin/java").touch()
            (path / "bin/java").chmod(0o700)
            (path / "release").write_text('JAVA_VERSION="' + major + '"')
        code, output = self.run_cli("plan", "--json")
        self.assertEqual(0, code, output)
        warnings = [w for w in json.loads(output)["warnings"] if "Gradle project without a Java version pin" in w]
        self.assertEqual(1, len(warnings))
        self.assertIn('java = "25"', warnings[0])
        self.assertIn("jvmToolchain(25)", warnings[0])
        self.assertEqual([], json.loads(output)["projects"][0]["toolchain"])
        self.assertNotIn("instructions", json.loads(output)["projects"][0]["diff"])
        (repo / ".java-version").write_text("21")
        code, output = self.run_cli("plan", "--json")
        self.assertEqual(0, code, output)
        self.assertNotIn("Gradle project without", output)

    def test_mise_java_pin_writes_only_a_managed_block_and_is_idempotent(self):
        from app_sandbox import toolchain_discovery
        repo = self.home / "code/repository"
        (repo / ".mise.toml").write_text('[tools]\njava = "25"\n')
        with sqlite3.connect(str(self.db)) as db:
            db.execute("UPDATE projects SET instructions = ?", ("User-owned text\n",))
        with mock.patch.object(toolchain_discovery, "managers", return_value={"mise": "/fixture/mise"}):
            code, output = self.run_cli("plan", "--json")
            self.assertEqual(0, code, output)
            plan = json.loads(output)
            added = plan["projects"][0]["diff"]["instructions"]["added"]
            self.assertIn("mise exec -- ./gradlew", added)
            self.assertIn("macOS /usr/bin/java stub", added)
            self.assertNotIn("User-owned", output)
            code, output = self.run_cli("apply", "--confirm", plan["digest"])
            self.assertEqual(0, code, output)
            with sqlite3.connect(str(self.db)) as db:
                text = db.execute("SELECT instructions FROM projects").fetchone()[0]
            self.assertTrue(text.startswith("User-owned text\n\n\n"))
            self.assertIn("<!-- app-sandbox-setup:toolchain:begin v1 -->", text)
            code, output = self.run_cli("plan")
            self.assertEqual(0, code, output)
            self.assertIn("no changes", output)

    def test_merge_preserves_user_text_around_block_and_refuses_malformed_markers(self):
        from app_sandbox import instructions
        old = instructions.BEGIN + "\nold\n" + instructions.END
        new = instructions.BEGIN + "\nnew\n" + instructions.END
        for before, after in (("", ""), ("before\n", ""), ("", "\nafter"),
                              ("before\n", "\nafter")):
            with self.subTest(before=before, after=after):
                text = before + old + after
                replaced = instructions.merge(text, new)
                self.assertEqual(before + new + after, replaced)
                self.assertEqual(replaced, instructions.merge(replaced, new))
                self.assertEqual(before + after, instructions.merge(text, ""))
        for user in ("", "user", "user\n", "user\n\n"):
            self.assertEqual(user, instructions.merge(instructions.merge(user, new), ""))
        for text in (instructions.BEGIN, instructions.END, old + old,
                     instructions.END + instructions.BEGIN, old.replace("v1", "v2")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                instructions.merge(text, new)

    def test_gradle_pin_chooses_only_a_valid_matching_jdk_without_executing_java(self):
        from app_sandbox import toolchain_discovery
        repo = self.home / "code/repository"
        (repo / "build.gradle.kts").write_text("kotlin { jvmToolchain(25) }")
        for version in ("21", "25"):
            jdk = self.home / ".sdkman/candidates/java" / version
            (jdk / "bin").mkdir(parents=True)
            (jdk / "bin/java").write_text("not executable code")
            (jdk / "bin/java").chmod(0o700)
            (jdk / "release").write_text('JAVA_VERSION="' + version + '.0.2"\n')
        with mock.patch.object(toolchain_discovery, "managers", return_value={}), \
                mock.patch.object(toolchain_discovery, "session_path", side_effect=AssertionError("no shell for java")):
            code, output = self.run_cli("plan", "--json")
        self.assertEqual(0, code, output)
        plan = json.loads(output)
        block = plan["projects"][0]["diff"]["instructions"]["added"]
        self.assertIn("JAVA_HOME=", block)
        self.assertIn(".sdkman/candidates/java/25", block)
        self.assertNotIn("candidates/java/21", block)
        (self.home / ".sdkman/candidates/java/25/release").unlink()
        with mock.patch.object(toolchain_discovery, "managers", return_value={}):
            code, output = self.run_cli("plan", "--json")
        self.assertEqual(0, code, output)
        self.assertIn("no matching JDK found for Java 25", output)
        self.assertNotIn("instructions", json.loads(output)["projects"][0]["diff"])

    def test_pin_sources_are_pure_and_java_stub_is_never_a_success(self):
        from app_sandbox import toolchain
        samples = {
            ".mise.toml": '[tools]\njava = "25"\nnode = "24"\npnpm = "11.3.0"',
            "mise.toml": '[tools]\njava = "25"',
            ".tool-versions": "java temurin-25.0.2\nnodejs 24.1\npnpm 11.3.0\n",
            ".java-version": "25.0.2\n",
            ".sdkmanrc": "java=25.0.2-tem\n",
            "build.gradle": "java { toolchain { languageVersion = JavaLanguageVersion.of(25) } }",
            "settings.gradle.kts": "jvmToolchain(25)",
        }
        for source, text in samples.items():
            with self.subTest(source=source):
                pins = toolchain.detect({source: text})
                self.assertEqual("25", pins["java"]["major"])
                observation = {"pins": pins, "managers": {}, "jdks": [],
                               "session_path": "/usr/bin", "resolved": {"java": "/usr/bin/java"}}
                java = toolchain.decide(observation)[0]
                self.assertIsNone(java["command"])
                self.assertIn("no matching JDK", java["warning"])
        for source in (".nvmrc", ".node-version"):
            self.assertEqual("24", toolchain.detect({source: "v24.1.0"})["node"]["major"])
        pins = toolchain.detect({"package.json": '{"packageManager":"pnpm@11.3.0"}'})
        self.assertEqual("11.3.0", pins["pnpm"]["version"])
        pins = toolchain.detect({".tool-versions": "java temurin-25"})
        self.assertEqual("mise", toolchain.decide({"pins": pins, "managers": {"mise": "/bin/mise"}})[0]["command"])

    def test_frontend_guidance_only_for_missing_tools_on_known_session_path(self):
        from app_sandbox import toolchain_discovery
        repo = self.home / "code/repository"
        (repo / ".mise.toml").write_text('[tools]\nnode = "24"\npnpm = "11.3.0"\n')
        (repo / "package.json").write_text('{"packageManager":"pnpm@11.3.0"}')
        bin_dir = self.home / "session-bin"
        bin_dir.mkdir()
        for tool in ("node", "pnpm"):
            (bin_dir / tool).touch()
            (bin_dir / tool).chmod(0o700)
        with mock.patch.object(toolchain_discovery, "managers", return_value={"mise": "/fixture/mise"}):
            for path, warning, expected in ((str(bin_dir), None, False), ("", None, True),
                                             (None, "Session PATH discovery failed; node/pnpm unknown, no guidance.", False)):
                with self.subTest(path=path), \
                        mock.patch.object(toolchain_discovery, "session_path", return_value=(path, warning)):
                    code, output = self.run_cli("plan", "--json")
                    self.assertEqual(0, code, output)
                    diff = json.loads(output)["projects"][0]["diff"]
                    self.assertEqual(expected, "instructions" in diff)
                    if expected:
                        self.assertIn("mise exec -- pnpm …", diff["instructions"]["added"])
                        self.assertIn("mise exec -- node …", diff["instructions"]["added"])
                    if warning:
                        self.assertIn("unknown, no guidance", output)

    def test_no_instructions_preserves_even_malformed_user_text_and_digest_ignores_it(self):
        from app_sandbox import toolchain_discovery, instructions
        with sqlite3.connect(str(self.db)) as db:
            db.execute("UPDATE projects SET instructions = ?", (instructions.BEGIN,))
        with mock.patch.object(toolchain_discovery, "observe", side_effect=AssertionError("opt-out")):
            digest = self.digest("--no-instructions")
            code, output = self.run_cli("apply", "--no-instructions", "--confirm", digest)
        self.assertEqual(0, code, output)
        with sqlite3.connect(str(self.db)) as db:
            self.assertEqual(instructions.BEGIN, db.execute("SELECT instructions FROM projects").fetchone()[0])
        code, output = self.run_cli("plan")
        self.assertEqual(0, code, output)
        self.assertIn("malformed toolchain markers; project skipped", output)

    def test_rollback_restores_instructions_and_digest_binds_concurrent_edits(self):
        from app_sandbox import toolchain_discovery
        (self.home / "code/repository/.mise.toml").write_text('[tools]\njava = "25"\n')
        with sqlite3.connect(str(self.db)) as db:
            db.execute("UPDATE projects SET instructions = 'original user text'")
        with mock.patch.object(toolchain_discovery, "managers", return_value={"mise": "/fixture/mise"}):
            digest = self.digest()
            with sqlite3.connect(str(self.db)) as db:
                db.execute("UPDATE projects SET instructions = 'changed user text'")
            code, output = self.run_cli("apply", "--confirm", digest)
            self.assertEqual(4, code, output)
            code, output = self.run_cli("apply", "--confirm", self.digest())
            self.assertEqual(0, code, output)
        backup = next((self.db.parent / "app-sandbox-setup-backups").iterdir())
        code, output = self.run_cli("rollback", "--from", str(backup), "--json")
        self.assertEqual(0, code, output)
        preview = json.loads(output)
        self.assertIn("mise exec -- ./gradlew", preview["projects"][0]["diff"]["instructions"]["removed"])
        self.assertNotIn("changed user text", output)
        code, output = self.run_cli("rollback", "--from", str(backup), "--confirm", preview["digest"])
        self.assertEqual(0, code, output)
        with sqlite3.connect(str(self.db)) as db:
            self.assertEqual("changed user text", db.execute("SELECT instructions FROM projects").fetchone()[0])

    def test_repo_config_instructions_skip_db_and_print_manual_block_with_trust_state(self):
        from app_sandbox import toolchain_discovery
        repo = self.home / "code/repository"
        (repo / ".mise.toml").write_text('[tools]\njava = "25"')
        (repo / ".github").mkdir()
        config = repo / ".github/github-app.yml"
        config.write_text("other:\n  instructions: nested\ninstructions: |\n  user config\n")
        with mock.patch.object(toolchain_discovery, "managers", return_value={"mise": "/fixture/mise"}):
            for trusted in (False, True):
                with self.subTest(trusted=trusted):
                    if trusted:
                        with sqlite3.connect(str(self.db)) as db:
                            db.execute("ALTER TABLE projects ADD COLUMN trusted_config_sha256 TEXT")
                            db.execute("UPDATE projects SET trusted_config_sha256 = 'fixture-hash'")
                    code, output = self.run_cli("plan", "--json")
                    self.assertEqual(0, code, output)
                    plan = json.loads(output)
                    self.assertTrue(all("instructions" not in p["diff"] for p in plan["projects"]))
                    self.assertIn("mise exec -- ./gradlew", output)
                    self.assertIn("precedence unverified", output)
                    self.assertIn("trusted config: " + ("yes" if trusted else "no"), output)
                    self.assertNotIn("fixture-hash", output)
                    self.assertNotIn("user config", output)
                    code, output = self.run_cli("apply", "--confirm", plan["digest"])
                    self.assertEqual(0, code, output)
                    with sqlite3.connect(str(self.db)) as db:
                        self.assertEqual("", db.execute("SELECT instructions FROM projects").fetchone()[0])

    def test_plan_is_changed_only_and_apply_is_summary_only(self):
        code, output = self.run_cli("apply", "--confirm", self.digest())
        self.assertEqual(0, code, output)
        self.assertNotIn("Project:", output)
        self.assertNotIn("+ readwritePaths", output)
        self.assertIn("Updated 1 projects.", output)
        code, output = self.run_cli("plan")
        self.assertEqual(0, code, output)
        self.assertNotIn("Project:", output)
        self.assertIn("1 projects unchanged", output)
        code, output = self.run_cli("plan", "--json")
        plan = json.loads(output)
        self.assertEqual([], plan["projects"])
        self.assertEqual(1, plan["unchanged_projects"])

    def test_move_backups_is_digest_bound_collision_safe_and_never_deletes_sidecars(self):
        loose = self.db.parent / "data.db.before-fixture"
        loose.write_bytes(b"fixture backup")
        directory = self.db.parent / "app-sandbox-setup-backups"
        directory.mkdir()
        (directory / loose.name).write_bytes(b"existing fixture")
        symlink = self.db.parent / "data.db.symlink"
        symlink.symlink_to(loose)
        (self.db.parent / "data.db.directory").mkdir()
        for suffix in (".open-lock", "-wal", "-shm", "-journal"):
            # WAL/SHM used by SQLite are tested elsewhere; don't fabricate them here.
            if suffix in (".open-lock", "-journal"):
                (self.db.parent / ("data.db" + suffix)).touch()
        code, output = self.run_cli("plan")
        self.assertEqual(0, code, output)
        self.assertIn("--move-backups", output)
        self.assertIn(str(symlink), output)
        old_digest = self.digest()
        code, output = self.run_cli("plan", "--move-backups", "--json")
        self.assertEqual(0, code, output)
        plan = json.loads(output)
        self.assertNotEqual(old_digest, plan["digest"])
        moves = plan["backup_moves"]
        self.assertEqual(1, len(moves))
        self.assertTrue(moves[0]["destination"].endswith(".1"))
        self.assertIn("symlink", output)
        code, output = self.run_cli("apply", "--move-backups", "--confirm", old_digest)
        self.assertEqual(4, code, output)
        code, output = self.run_cli("apply", "--move-backups", "--confirm", plan["digest"])
        self.assertEqual(0, code, output)
        self.assertFalse(loose.exists())
        self.assertEqual(b"fixture backup", (directory / (loose.name + ".1")).read_bytes())
        self.assertEqual(b"existing fixture", (directory / loose.name).read_bytes())
        self.assertTrue(symlink.is_symlink())
        self.assertTrue((self.db.parent / "data.db.directory").is_dir())
        self.assertTrue((self.db.parent / "data.db.open-lock").exists())
        self.assertEqual(0o700, directory.stat().st_mode & 0o777)
        self.assertIn("Moved backups: 1", output)

    def test_instructions_schema_and_update_triggers_fail_closed(self):
        for header in ("AFTER UPDATE OF instructions ON projects",
                       "BEFORE UPDATE OF name, [instructions] ON projects"):
            with sqlite3.connect(str(self.db)) as db:
                db.execute("CREATE TRIGGER fixture " + header + " BEGIN SELECT RAISE(ABORT, 'private'); END")
            before = self.db.read_bytes()
            for command, options in (("plan", ()), ("apply", ("--confirm", "wrong"))):
                code, output = self.run_cli(command, *options)
                self.assertEqual(3, code, output)
                self.assertEqual(before, self.db.read_bytes())
            with sqlite3.connect(str(self.db)) as db:
                db.execute("DROP TRIGGER fixture")
        for clause in ("", ", instructions TEXT", ", instructions INTEGER NOT NULL DEFAULT 0"):
            with sqlite3.connect(str(self.db)) as db:
                db.executescript("DROP TABLE projects; CREATE TABLE projects(id TEXT PRIMARY KEY, "
                                 "name TEXT, main_repo_path TEXT UNIQUE, "
                                 "sandbox_enabled INTEGER NOT NULL DEFAULT 0" + clause + ");")
            code, output = self.run_cli("plan")
            self.assertEqual(3, code, output)
        self.assertFalse((self.db.parent / "app-sandbox-setup-backups").exists())

    def test_instructions_are_removed_when_pins_disappear(self):
        from app_sandbox import toolchain_discovery
        pin = self.home / "code/repository/.mise.toml"
        pin.write_text('[tools]\njava = "25"')
        with sqlite3.connect(str(self.db)) as db:
            db.execute("UPDATE projects SET instructions = 'keep user text'")
        with mock.patch.object(toolchain_discovery, "managers", return_value={"mise": "/fixture/mise"}):
            code, output = self.run_cli("apply", "--confirm", self.digest())
            self.assertEqual(0, code, output)
            pin.unlink()
            code, output = self.run_cli("plan")
            self.assertEqual(0, code, output)
            self.assertIn("- instructions: <!-- app-sandbox-setup:toolchain:begin v1 -->", output)
            code, output = self.run_cli("apply", "--confirm", self.digest())
            self.assertEqual(0, code, output)
        with sqlite3.connect(str(self.db)) as db:
            self.assertEqual("keep user text", db.execute("SELECT instructions FROM projects").fetchone()[0])

    def test_session_path_uses_only_injected_environment_and_suppresses_failed_output(self):
        from app_sandbox import toolchain_discovery
        import subprocess
        env = {"HOME": "/not-used", "USER": "fixture", "SHELL": "/fixture/shell",
               "LANG": "C", "TOKEN": "fixture-private-value", "PATH": "/not-inherited"}
        for result in (subprocess.CompletedProcess([], 0, "/fixture/bin", ""),
                       subprocess.CompletedProcess([], 1, "fixture-private-value", ""),
                       subprocess.TimeoutExpired("fixture-private-value", 10)):
            runner = mock.Mock(side_effect=result if isinstance(result, Exception) else None,
                               return_value=result)
            # Call the actual function beneath setUp's protective shell stub.
            path, warning = self._session_path(self.home, env, runner)
            call = runner.call_args
            self.assertEqual(["/fixture/shell", "-l", "-i", "-c", 'printf %s "$PATH"'], call.args[0])
            self.assertEqual(10, call.kwargs["timeout"])
            self.assertEqual(subprocess.DEVNULL, call.kwargs["stdin"])
            self.assertEqual(str(self.home), call.kwargs["cwd"])
            self.assertEqual({"HOME": str(self.home), "USER": "fixture", "SHELL": "/fixture/shell",
                              "TERM": "dumb", "LANG": "C"}, call.kwargs["env"])
            self.assertEqual(isinstance(result, subprocess.CompletedProcess) and result.returncode == 0,
                             path is not None)
            self.assertNotIn("fixture-private-value", warning or "")

    def test_untrusted_pin_content_cannot_become_instructions_or_json_diagnostics(self):
        from app_sandbox import toolchain
        pins = toolchain.detect({".mise.toml": '[tools]\nnode = "24 fixture-private-value"\n'
                                              'pnpm = "11; echo fixture-private-value"\n'
                                              'java = "25 fixture-private-value"\n'})
        self.assertNotIn("node", pins)
        self.assertNotIn("pnpm", pins)
        self.assertNotIn("fixture-private-value", json.dumps(pins))


if __name__ == "__main__":
    unittest.main()
