"""Inspector regressions through fixture-only public command boundaries."""

import json
import os
import sqlite3
import subprocess
import unittest
from unittest import mock

import test_app_sandbox_setup as fixtures


class InspectorTest(unittest.TestCase):
    setUp = fixtures.AppSandboxSetupTest.setUp
    run_cli = fixtures.AppSandboxSetupTest.run_cli
    digest = fixtures.AppSandboxSetupTest.digest
    policies = fixtures.AppSandboxSetupTest.policies

    def test_rollback_preserves_user_edits_and_binds_the_actual_block_only_change(self):
        from app_sandbox import instructions, toolchain_discovery
        (self.home / "code/repository/.mise.toml").write_text('[tools]\njava = "25"\n')
        with sqlite3.connect(str(self.db)) as db:
            db.execute("UPDATE projects SET instructions = 'before apply'")
        with mock.patch.object(toolchain_discovery, "managers", return_value={"mise": "/fixture/mise"}):
            code, output = self.run_cli("apply", "--confirm", self.digest())
        self.assertEqual(0, code, output)
        backup = next((self.db.parent / "app-sandbox-setup-backups").glob("data.db.*"))
        with sqlite3.connect(str(self.db)) as db:
            text = db.execute("SELECT instructions FROM projects").fetchone()[0]
            current = "edited after apply\n" + instructions.managed(text) + "\nnew user suffix"
            db.execute("UPDATE projects SET instructions = ?", (current,))
        code, output = self.run_cli("rollback", "--from", str(backup), "--json")
        self.assertEqual(0, code, output)
        preview = json.loads(output)
        self.assertIn("mise exec -- ./gradlew", output)
        self.assertNotIn("edited after apply", output)
        with sqlite3.connect(str(self.db)) as db:
            db.execute("UPDATE projects SET instructions = ?", ("another edit\n" + current,))
        code, output = self.run_cli("rollback", "--from", str(backup), "--confirm", preview["digest"])
        self.assertEqual(4, code, output)
        code, output = self.run_cli("rollback", "--from", str(backup), "--json")
        preview = json.loads(output)
        code, output = self.run_cli("rollback", "--from", str(backup), "--confirm", preview["digest"])
        self.assertEqual(0, code, output)
        with sqlite3.connect(str(self.db)) as db:
            restored = db.execute("SELECT instructions FROM projects").fetchone()[0]
        self.assertEqual("another edit\nedited after apply\n\nnew user suffix", restored)

    def test_malformed_instructions_do_not_skip_sandbox_policy_updates(self):
        from app_sandbox import instructions
        with sqlite3.connect(str(self.db)) as db:
            db.execute("UPDATE projects SET instructions = ?", (instructions.BEGIN,))
        code, output = self.run_cli("plan", "--json")
        self.assertEqual(0, code, output)
        plan = json.loads(output)
        self.assertEqual(1, len(plan["projects"]))
        self.assertNotIn("instructions", plan["projects"][0]["diff"])
        self.assertIn("instructions left untouched", output)
        code, output = self.run_cli("apply", "--confirm", plan["digest"])
        self.assertEqual(0, code, output)
        with sqlite3.connect(str(self.db)) as db:
            flag, text = db.execute("SELECT sandbox_enabled,instructions FROM projects").fetchone()
        self.assertEqual(1, flag)
        self.assertEqual(instructions.BEGIN, text)

    def test_npm_only_and_gradle_tooling_packages_do_not_gate_missing_pnpm_or_unpinned_node(self):
        from app_sandbox import probes, project_probes
        repo = self.home / "code/repository"
        expected = {"HOME write": "denied", "DB open": "denied", "loopback": "OK",
                    "cache write": "OK", "readonly write": "denied"}
        def command(args, **kwargs):
            if args[0] in ("node", "pnpm"):
                raise FileNotFoundError()
            output = 'openjdk version "25.0.2"' if args[0] == "java" else "Launcher JVM: 25.0.2"
            return subprocess.CompletedProcess(args, 0, output, "")
        for gradle in (False, True):
            (repo / "package.json").write_text('{"packageManager":"npm@10.0.0","private":true}')
            if gradle:
                (repo / "gradlew").touch()
            with self.subTest(gradle=gradle), \
                    mock.patch.object(probes, "behavioral_probes", return_value=expected, create=True), \
                    mock.patch.object(probes.Path, "cwd", return_value=repo), \
                    mock.patch.object(project_probes.subprocess, "run", side_effect=command) as runner:
                code, output = self.run_cli("verify")
            self.assertEqual(0, code, output)
            self.assertIn("node | info", output)
            self.assertFalse(any("pnpm" in call.args[0] for call in runner.call_args_list))

    def test_repo_toolchain_reads_refuse_symlinks_fifos_and_oversized_files(self):
        from app_sandbox import toolchain_discovery
        repo = self.home / "code/repository"
        file = repo / ".mise.toml"
        outside = self.root / "outside.toml"
        outside.write_text('[tools]\njava = "25"\n# private fixture text\n')
        file.symlink_to(outside)
        observation = toolchain_discovery.observe(repo, self.home, capture_session=False)
        self.assertNotIn("java", observation["pins"])
        self.assertTrue(observation["warnings"])
        file.unlink()
        file.write_text('[tools]\njava = "25"\n' + "#" * (64 * 1024))
        observation = toolchain_discovery.observe(repo, self.home, capture_session=False)
        self.assertNotIn("java", observation["pins"])
        file.unlink()
        os.mkfifo(str(file))
        observation = toolchain_discovery.observe(repo, self.home, capture_session=False)
        self.assertNotIn("java", observation["pins"])
        self.assertNotIn("private fixture text", str(observation))
        file.unlink()
        external = self.root / "external-config"
        external.mkdir()
        (external / "github-app.yml").write_text("instructions: private fixture text\n")
        (repo / ".github").symlink_to(external, target_is_directory=True)
        observation = toolchain_discovery.observe(repo, self.home, capture_session=False)
        self.assertTrue(observation["repo_instructions"])
        self.assertNotIn("private fixture text", str(observation))

    def test_default_plan_captures_login_session_once_for_all_projects(self):
        from app_sandbox import toolchain_discovery
        repo = self.home / "code/repository"
        (repo / ".mise.toml").write_text('[tools]\nnode = "24"\n')
        other = self.home / "code/other"
        other.mkdir()
        (other / ".mise.toml").write_text('[tools]\nnode = "24"\n')
        with sqlite3.connect(str(self.db)) as db:
            db.execute("INSERT INTO projects(id,name,main_repo_path) VALUES (?,?,?)",
                       ("p2", "second", str(other)))
        with mock.patch.object(toolchain_discovery, "session_environment",
                               return_value=({"PATH": "", "ZDOTDIR": ""}, None)) as capture:
            code, output = self.run_cli("plan")
        self.assertEqual(0, code, output)
        self.assertEqual(1, capture.call_count)

    def test_session_path_does_not_execute_an_unknown_login_shell(self):
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, "/fixture/bin", ""))
        path, warning = self._session_path(self.home, {"SHELL": "/fixture/other"}, runner)
        self.assertIsNone(path)
        self.assertIn("unknown, no guidance", warning)
        runner.assert_not_called()

    def test_readonly_opt_in_remains_active_in_other_shell_profile_candidates(self):
        from app_sandbox import profile
        shims = str(self.home / ".local/share/mise/shims")
        for relative, shell in ((".bash_profile", "bash"), (".bash_login", "bash"),
                                (".profile", "bash"), (".config/fish/conf.d/app-sandbox-setup.fish", "fish")):
            with self.subTest(relative=relative):
                path = self.home / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(profile.block({"shell": shell, "tools": ["java"], "shims": shims,
                                               "java_home": None, "readonly": [shims, str(path)]}))
                code, output = self.run_cli("plan", "--json")
                self.assertEqual(0, code, output)
                self.assertIn(shims, json.loads(output)["projects"][0]["diff"]["readonlyPaths"]["added"])
                path.unlink()

    def test_gradle_remove_deletes_only_our_created_empty_key_and_keeps_a_bare_user_key(self):
        from app_sandbox import gradle_repair
        path = str(self.home / "jdk")
        original = "# keep\nother=value\n"
        merged, _, _ = gradle_repair.merge(original, [path])
        removed, _, _ = gradle_repair.merge(merged, [], True)
        self.assertEqual(original, removed)
        cleared = merged.replace(gradle_repair.KEY + "=" + path + "\n", gradle_repair.KEY + "=\n")
        removed, _, _ = gradle_repair.merge(cleared, [], True)
        self.assertEqual(original, removed)
        bare = "# keep\n" + gradle_repair.KEY + "\n"
        merged, _, _ = gradle_repair.merge(bare, [path])
        self.assertEqual(1, sum(line.startswith(gradle_repair.KEY) for line in merged.splitlines()))
        removed, _, _ = gradle_repair.merge(merged, [], True)
        self.assertEqual(1, sum(line.startswith(gradle_repair.KEY) for line in removed.splitlines()))
        legacy = (gradle_repair.KEY + "=" + path + "\n"
                  + gradle_repair.MARKER + json.dumps([path]) + "\n")
        removed, _, _ = gradle_repair.merge(legacy, [], True)
        self.assertEqual(gradle_repair.KEY + "=\n", removed)

    def test_gradle_repair_honours_gradle_user_home(self):
        from app_sandbox import toolchain_discovery
        repo = self.home / "code/repository"
        (repo / ".mise.toml").write_text('[tools]\njava = "25"\n')
        (repo / "build.gradle.kts").write_text("jvmToolchain(21)")
        jdk = self.home / "Library/Java/JavaVirtualMachines/21/Contents/Home"
        (jdk / "bin").mkdir(parents=True)
        (jdk / "bin/java").touch()
        (jdk / "bin/java").chmod(0o700)
        (jdk / "release").write_text('JAVA_VERSION="21.0.2"\n')
        directory = self.home / "custom-gradle"
        directory.mkdir()
        file = directory / "gradle.properties"
        file.write_text("# keep\n")
        with mock.patch.dict(os.environ, {"GRADLE_USER_HOME": str(directory)}), \
                mock.patch.object(toolchain_discovery, "managers", return_value={"mise": "/fixture/mise"}):
            code, output = self.run_cli("gradle-toolchains", "plan", "--json")
            self.assertEqual(0, code, output)
            plan = json.loads(output)
            self.assertEqual(str(file), plan["target"])
            code, output = self.run_cli("gradle-toolchains", "apply", "--confirm", plan["digest"])
        self.assertEqual(0, code, output)
        self.assertIn(str(jdk), file.read_text())
        self.assertTrue(file.read_text().startswith("# keep\n"))
        self.assertFalse((self.home / ".gradle/gradle.properties").exists())

    def test_profile_policy_changes_only_readonly_entries(self):
        from app_sandbox import toolchain_discovery
        shims = str(self.home / ".local/share/mise/shims")
        original = {"readonlyPaths": ["/fixture/user-ro"], "readwritePaths": [shims, "/fixture/user-rw"],
                    "allowOutbound": False, "userChoice": 3}
        with sqlite3.connect(str(self.db)) as db:
            db.execute("UPDATE projects SET sandbox_enabled=1")
            db.execute("INSERT INTO project_sandbox_policies VALUES (?,?)", ("p1", json.dumps(original)))
        with mock.patch.object(toolchain_discovery, "session_environment",
                               return_value=({"PATH": "/usr/bin", "JAVA_HOME": "", "ZDOTDIR": ""}, None)), \
                mock.patch.object(toolchain_discovery, "managers", return_value={"mise": "/fixture/mise"}), \
                mock.patch.object(toolchain_discovery.shutil, "which", return_value="/usr/bin/java"):
            code, output = self.run_cli("profile", "plan", "--shell", "/fixture/zsh", "--tool", "java", "--json")
            self.assertEqual(0, code, output)
            code, output = self.run_cli("profile", "apply", "--shell", "/fixture/zsh", "--tool", "java",
                                        "--confirm", json.loads(output)["digest"])
        self.assertEqual(0, code, output)
        policy = self.policies()[0]
        self.assertEqual(original["readwritePaths"], policy["readwritePaths"])
        self.assertFalse(policy["allowOutbound"])
        self.assertEqual(3, policy["userChoice"])
        self.assertIn("/fixture/user-ro", policy["readonlyPaths"])
        self.assertIn(shims, policy["readonlyPaths"])
        with sqlite3.connect(str(self.db)) as db:
            self.assertEqual(1, db.execute("SELECT sandbox_enabled FROM projects").fetchone()[0])

    def test_rollback_replaces_only_managed_block_and_refuses_malformed_current_markers(self):
        from app_sandbox import instructions, policy
        def block(major):
            return instructions.block([{"tool": "java", "command": "mise",
                                        "pin": {"major": major, "source": ".mise.toml"}}])
        current = "edited user prefix\n" + block("25") + "\nuser suffix"
        rows = [{"id": "p1", "name": "example", "sandbox_enabled": 1,
                 "policy_json": None, "instructions": current}]
        backup = {"p1": {"sandbox_enabled": 0, "policy_json": None,
                         "instructions": "old user prefix\n" + block("21")}}
        plan = policy.rollback_plan(rows, backup)
        self.assertEqual("edited user prefix\n" + block("21") + "\nuser suffix",
                         plan["projects"][0]["after"]["instructions"])
        rows[0]["instructions"] = instructions.BEGIN
        plan = policy.rollback_plan(rows, backup)
        self.assertEqual([], plan["projects"])
        self.assertIn("p1", plan["skipped"])
        self.assertTrue(any("malformed" in warning for warning in plan["warnings"]))

    def test_engines_node_and_pnpm_lock_or_pin_are_the_only_additional_frontend_gates(self):
        from app_sandbox import project_probes
        repo = self.home / "code/repository"
        package = repo / "package.json"
        package.write_text('{"engines":{"node":">=20"}}')
        results = project_probes.run(repo, self.home, runner=mock.Mock(side_effect=FileNotFoundError()))
        self.assertEqual(["node"], [item["name"] for item in results])
        self.assertTrue(results[0]["gate"])
        package.write_text("{}")
        for marker, contents in (("pnpm-lock.yaml", "lockfileVersion: 9"), (".tool-versions", "pnpm 9.7.0")):
            (repo / marker).write_text(contents)
            results = project_probes.run(repo, self.home, runner=mock.Mock(side_effect=FileNotFoundError()))
            self.assertTrue(any(item["name"] in ("pnpm", "managed pnpm") and item["gate"] for item in results))
            (repo / marker).unlink()
        (repo / ".nvmrc").write_text("lts/*")
        results = project_probes.run(repo, self.home, runner=mock.Mock(side_effect=FileNotFoundError()))
        self.assertTrue(next(item for item in results if item["name"] == "node")["gate"])
        (repo / ".nvmrc").write_text("x" * (64 * 1024 + 1))
        results = project_probes.run(repo, self.home, runner=mock.Mock(side_effect=FileNotFoundError()))
        self.assertTrue(next(item for item in results if item["name"] == "node")["gate"])
