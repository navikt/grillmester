"""Targeted Gradle repair through separately confirmed commands."""

import json
import os
import unittest
from unittest import mock

import test_app_sandbox_setup_profile as profile_fixtures


class GradleTest(unittest.TestCase):
    setUp = profile_fixtures.ProfileTest.setUp
    run_cli = profile_fixtures.ProfileTest.run_cli
    jdk = profile_fixtures.ProfileTest.jdk

    def test_mise_launcher_matching_toolchain_needs_no_repair(self):
        repo = self.home / "code/repository"
        (repo / ".mise.toml").write_text('[tools]\njava = "25"\n')
        (repo / "build.gradle.kts").write_text("jvmToolchain(25)")
        self.jdk("25", ".local/share/mise/installs/java/25")
        code, output = self.run_cli("gradle-toolchains", "plan", "--json")
        self.assertEqual(0, code, output)
        plan = json.loads(output)
        self.assertFalse(plan["repair_needed"])
        self.assertFalse(plan["changed"])
        self.assertEqual([], plan["added"])
        self.assertFalse((self.home / ".gradle").exists())
        code, output = self.run_cli("gradle-toolchains", "plan")
        self.assertEqual(0, code, output)
        self.assertIn("example", output)
        self.assertIn("launching JVM", output)
        self.assertIn("no repair needed", output)

    def test_java_home_launcher_matching_toolchain_needs_no_repair(self):
        repo = self.home / "code/repository"
        (repo / ".java-version").write_text("25")
        (repo / "build.gradle.kts").write_text("jvmToolchain(25)")
        self.jdk("25", "Library/Java/JavaVirtualMachines/25/Contents/Home")
        code, output = self.run_cli("gradle-toolchains", "plan", "--json", managers={})
        self.assertEqual(0, code, output)
        plan = json.loads(output)
        self.assertFalse(plan["repair_needed"])
        self.assertFalse(plan["changed"])
        self.assertIn("JAVA_HOME", plan["projects"][0]["reason"])
        self.assertIn("launching JVM", plan["projects"][0]["reason"])
        self.assertFalse((self.home / ".gradle").exists())

    def test_without_a_java_instruction_decision_discovery_missing_is_not_proven(self):
        repo = self.home / "code/repository"
        (repo / ".java-version").write_text("25")
        (repo / "build.gradle.kts").write_text("jvmToolchain(21)")
        self.jdk("21", ".local/share/mise/installs/java/21")
        code, output = self.run_cli("gradle-toolchains", "plan", "--json", managers={})
        self.assertEqual(0, code, output)
        plan = json.loads(output)
        self.assertFalse(plan["repair_needed"])
        self.assertFalse(plan["changed"])
        self.assertIn("no per-project Java instruction decision", plan["projects"][0]["reason"])
        code, output = self.run_cli("gradle-toolchains", "apply",
                                    "--confirm", plan["digest"], managers={})
        self.assertEqual(0, code, output)
        self.assertFalse((self.home / ".gradle").exists())
        self.assertFalse((self.home / ".copilot/app-sandbox-setup-backups").exists())

    def test_mise_launcher_differing_from_toolchain_repairs_requested_major(self):
        repo = self.home / "code/repository"
        (repo / ".mise.toml").write_text('[tools]\njava = "25"\n')
        (repo / "build.gradle.kts").write_text("jvmToolchain(21)")
        self.jdk("25", ".local/share/mise/installs/java/25")
        requested = self.jdk("21", ".local/share/mise/installs/java/21")
        code, output = self.run_cli("gradle-toolchains", "plan", "--json")
        self.assertEqual(0, code, output)
        plan = json.loads(output)
        self.assertEqual([str(requested)], plan["added"])
        project = plan["projects"][0]
        self.assertEqual("25", project["launching_major"])
        self.assertEqual("21", project["requested_major"])
        self.assertTrue(project["repair_needed"])
        self.assertIn("differs", project["reason"])
        # Ambient JAVA_HOME is not the command-local environment of mise exec.
        code, output = self.run_cli("gradle-toolchains", "plan", "--json",
                                    environment={"JAVA_HOME": str(requested)})
        self.assertEqual(0, code, output)
        self.assertEqual([str(requested)], json.loads(output)["added"])
        (repo / ".mise.toml").write_text('[tools]\njava = "17"\n')
        code, output = self.run_cli("gradle-toolchains", "apply", "--confirm", plan["digest"])
        self.assertEqual(4, code, output)
        self.assertFalse((self.home / ".gradle").exists())

    def test_requested_jdk_selection_prefers_roots_then_numeric_version(self):
        from app_sandbox import toolchain_discovery
        repo = self.home / "code/repository"
        (repo / ".mise.toml").write_text('[tools]\njava = "25"\n')
        (repo / "build.gradle.kts").write_text("jvmToolchain(21)")
        self.jdk("25", ".local/share/mise/installs/java/25")
        older = self.jdk("21", ".local/share/mise/installs/java/temurin-21.0.9")
        newer = self.jdk("21", ".local/share/mise/installs/java/temurin-21.0.10")
        user = self.jdk("21", "Library/Java/JavaVirtualMachines/21/Contents/Home")
        system = toolchain_discovery.SYSTEM_JDK_ROOT / "21/Contents/Home"
        (system / "bin").mkdir(parents=True)
        (system / "bin/java").touch()
        (system / "bin/java").chmod(0o700)
        for path, version in ((older, "21.0.9+99"), (newer, "21.0.10+7"),
                              (user, "21.0.99+100"), (system, "21.0.999+100")):
            (path / "release").write_text('JAVA_VERSION="' + version + '"\n')
        for expected, remove in ((newer, (newer, older)), (user, (user,)), (system, ())):
            code, output = self.run_cli("gradle-toolchains", "plan", "--json")
            self.assertEqual(0, code, output)
            plan = json.loads(output)
            self.assertEqual([str(expected)], plan["added"])
            code, output = self.run_cli("gradle-toolchains", "plan", "--json")
            self.assertEqual(0, code, output)
            self.assertEqual(plan["digest"], json.loads(output)["digest"])
            if expected == newer:
                (newer / "release").write_text('JAVA_VERSION="21.0.10+8"\n')
                code, output = self.run_cli("gradle-toolchains", "apply", "--confirm", plan["digest"])
                self.assertEqual(4, code, output)
                self.assertFalse((self.home / ".gradle").exists())
            for path in remove:
                (path / "release").unlink()

    def test_existing_matching_paths_prevent_unnecessary_repair_even_with_a_preferred_jdk(self):
        repo = self.home / "code/repository"
        (repo / ".mise.toml").write_text('[tools]\njava = "25"\n')
        (repo / "build.gradle.kts").write_text("jvmToolchain(21)")
        existing = self.jdk("21", "Library/Java/JavaVirtualMachines/21/Contents/Home")
        self.jdk("21", ".local/share/mise/installs/java/21")
        properties = self.home / ".gradle/gradle.properties"
        properties.parent.mkdir()
        original = "# keep\norg.gradle.java.installations.paths=" + str(existing) + "\n"
        properties.write_text(original)
        code, output = self.run_cli("gradle-toolchains", "plan", "--json")
        self.assertEqual(0, code, output)
        plan = json.loads(output)
        self.assertFalse(plan["changed"])
        self.assertFalse(plan["repair_needed"])
        self.assertIn("already configured", plan["projects"][0]["reason"])
        code, output = self.run_cli("gradle-toolchains", "apply", "--confirm", plan["digest"])
        self.assertEqual(0, code, output)
        self.assertEqual(original, properties.read_text())
        self.assertFalse((self.home / ".copilot/app-sandbox-setup-backups").exists())

    def test_configured_mise_root_and_sdkman_symlink_are_discovered(self):
        repo = self.home / "code/repository"
        (repo / ".mise.toml").write_text('[tools]\njava = "21"\n')
        (repo / "build.gradle.kts").write_text("jvmToolchain(25)")
        path = self.jdk("25", "configured-mise/installs/java/25")
        env = {"MISE_DATA_DIR": str(self.home / "configured-mise")}
        code, output = self.run_cli("gradle-toolchains", "plan", "--json", environment=env)
        self.assertEqual(0, code, output)
        self.assertEqual([str(path)], json.loads(output)["added"])
        sdkman = self.home / ".sdkman/candidates/java"
        sdkman.mkdir(parents=True)
        (sdkman / "25").symlink_to(path, target_is_directory=True)
        code, output = self.run_cli("gradle-toolchains", "plan", "--json", environment=env)
        self.assertEqual(0, code, output)
        self.assertFalse(json.loads(output)["repair_needed"])

    def test_repair_only_with_gradle_pin_and_matching_non_detected_jdk(self):
        repo = self.home / "code/repository"
        (repo / ".mise.toml").write_text('[tools]\njava = "21"\n')
        for relative, expected in ((".sdkman/candidates/java/25", False),
                                   (".asdf/installs/java/25", False),
                                   ("Library/Java/JavaVirtualMachines/25/Contents/Home", True),
                                   (".local/share/mise/installs/java/25", True)):
            with self.subTest(relative=relative):
                path = self.jdk("25", relative)
                (repo / "build.gradle").write_text("JavaLanguageVersion.of(25)")
                code, output = self.run_cli("gradle-toolchains", "plan", "--json")
                self.assertEqual(0, code, output)
                plan = json.loads(output)
                self.assertEqual(expected, plan["changed"])
                if expected:
                    self.assertEqual([str(path)], plan["added"])
                else:
                    self.assertFalse(plan["repair_needed"])
                # No writes from a plan, whether repair is needed or not.
                self.assertFalse((self.home / ".gradle").exists())
                (path / "release").unlink()
        (repo / "build.gradle").write_text("jvmToolchain(21)")
        path = self.jdk("25", ".local/share/mise/installs/java/another25")
        code, output = self.run_cli("gradle-toolchains", "plan")
        self.assertEqual(0, code, output)
        self.assertIn("no repair needed", output)
        (repo / "build.gradle").unlink()
        (repo / ".java-version").write_text("25")
        code, output = self.run_cli("gradle-toolchains", "plan")
        self.assertEqual(0, code, output)
        self.assertIn("no repair needed", output)
        (repo / "build.gradle.kts").write_text("jvmToolchain(25)")
        (repo / ".mise.toml").unlink()
        code, output = self.run_cli("gradle-toolchains", "plan", environment={"JAVA_HOME": str(path)})
        self.assertEqual(0, code, output)
        self.assertIn("no repair needed", output)

    def test_existing_paths_are_not_owned_and_concurrent_edits_invalidate_digest(self):
        (self.home / "code/repository/.mise.toml").write_text('[tools]\njava = "21"\n')
        path = self.jdk("25", ".local/share/mise/installs/java/25")
        (self.home / "code/repository/build.gradle").write_text("jvmToolchain(25)")
        file = self.home / ".gradle/gradle.properties"
        file.parent.mkdir()
        file.write_text("# keep\norg.gradle.java.installations.paths=" + str(path) + "\n")
        before = file.read_text()
        code, output = self.run_cli("gradle-toolchains", "plan", "--json")
        self.assertEqual(0, code, output)
        self.assertFalse(json.loads(output)["changed"])
        code, output = self.run_cli("gradle-toolchains", "remove", "--json")
        self.assertEqual(0, code, output)
        code, output = self.run_cli("gradle-toolchains", "remove", "--confirm", json.loads(output)["digest"])
        self.assertEqual(0, code, output)
        self.assertEqual(before, file.read_text())
        file.write_text("# keep\n")
        code, output = self.run_cli("gradle-toolchains", "plan", "--json")
        digest = json.loads(output)["digest"]
        file.write_text("# concurrent\n")
        code, output = self.run_cli("gradle-toolchains", "apply", "--confirm", digest)
        self.assertEqual(4, code, output)
        self.assertEqual("# concurrent\n", file.read_text())
        self.assertFalse((self.home / ".copilot/app-sandbox-setup-backups").exists())

    def test_gradle_missing_key_escape_dedup_and_refuse_ambiguous_or_symlinked_properties(self):
        from app_sandbox import gradle_repair
        paths = [str(self.home / "jdk with spaces")]
        merged, added, _ = gradle_repair.merge("# keep\nother=private fixture\n", paths)
        self.assertEqual(paths, added)
        self.assertIn("jdk\\ with\\ spaces", merged)
        self.assertEqual(merged, gradle_repair.merge(merged, paths)[0])
        removed = gradle_repair.merge(merged, [], True)[0]
        self.assertIn("# keep\nother=private fixture\n", removed)
        self.assertNotIn("jdk", removed)
        file = self.home / ".gradle/gradle.properties"
        file.parent.mkdir()
        for text in ("org.gradle.java.installations.paths=/a\norg.gradle.java.installations.paths=/b\n",
                     "org.gradle.java.installations.paths=/a,\\\n/b\n",
                     "other=continued\\\norg.gradle.java.installations.paths=/a\n",
                     "# app-sandbox-setup:gradle-toolchains malformed fixture\n"):
            file.write_text(text)
            code, output = self.run_cli("gradle-toolchains", "plan")
            self.assertEqual(1, code, output)
            self.assertNotIn("malformed fixture", output)
            self.assertEqual(text, file.read_text())
        file.unlink()
        target = self.home / "props"
        target.write_text("fixture untouched")
        file.symlink_to(target)
        code, output = self.run_cli("gradle-toolchains", "plan")
        self.assertEqual(1, code, output)
        self.assertEqual("fixture untouched", target.read_text())

    def test_mise_jdk_needs_repair_merges_and_removes_only_ours(self):
        (self.home / "code/repository/.mise.toml").write_text('[tools]\njava = "21"\n')
        jdk = self.jdk("25", ".local/share/mise/installs/java/25")
        (self.home / "code/repository/build.gradle.kts").write_text("jvmToolchain(25)")
        properties = self.home / ".gradle/gradle.properties"
        properties.parent.mkdir()
        original = "# user comment\norg.gradle.java.installations.paths=/user/jdk\nother=fixture\n"
        properties.write_text(original)
        properties.chmod(0o640)
        code, output = self.run_cli("gradle-toolchains", "plan", "--json")
        self.assertEqual(0, code, output)
        plan = json.loads(output)
        self.assertEqual([str(jdk)], plan["added"])
        self.assertNotIn("other=fixture", output)
        code, output = self.run_cli("gradle-toolchains", "apply", "--confirm", plan["digest"])
        self.assertEqual(0, code, output)
        self.assertIn("/user/jdk," + str(jdk), properties.read_text())
        self.assertIn("does NOT give the wrapper a java to start with", output)
        self.assertEqual(0o640, properties.stat().st_mode & 0o777)
        backup = next((self.home / ".copilot/app-sandbox-setup-backups").glob("gradle.properties.*"))
        self.assertEqual(original, backup.read_text())
        self.assertEqual(0o600, backup.stat().st_mode & 0o777)
        code, output = self.run_cli("gradle-toolchains", "plan")
        self.assertEqual(0, code, output)
        self.assertIn("no changes", output)
        code, output = self.run_cli("gradle-toolchains", "remove", "--json")
        self.assertEqual(0, code, output)
        code, output = self.run_cli("gradle-toolchains", "remove", "--confirm", json.loads(output)["digest"])
        self.assertEqual(0, code, output)
        self.assertEqual(original, properties.read_text())


if __name__ == "__main__":
    unittest.main()
