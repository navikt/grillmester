"""Project probes execute only injected subprocesses in disposable fixtures."""

import errno
import os
import subprocess
import unittest
from unittest import mock

import test_app_sandbox_setup as fixtures


class ProjectProbesTest(unittest.TestCase):
    setUp = fixtures.AppSandboxSetupTest.setUp
    run_cli = fixtures.AppSandboxSetupTest.run_cli

    def test_verify_managed_java_gates_while_bare_stub_is_informational(self):
        from app_sandbox import project_probes, probes, toolchain_discovery
        repo = self.home / "code/repository"
        (repo / "gradlew").touch()
        (repo / ".mise.toml").write_text('[tools]\njava = "25"')
        behaviors = {"HOME write": "denied", "DB open": "denied", "loopback": "OK",
                     "cache write": "OK", "readonly write": "denied"}
        with mock.patch.object(probes, "behavioral_probes", return_value=behaviors, create=True), \
                mock.patch.object(toolchain_discovery, "managers", return_value={"mise": "/fixture/mise"}), \
                mock.patch.object(project_probes.subprocess, "run", side_effect=[
                    subprocess.CompletedProcess([], 1, "", "Unable to locate a Java Runtime"),
                    subprocess.CompletedProcess([], 0, "", 'openjdk version "25.0.2"'),
                    subprocess.CompletedProcess([], 0, "Launcher JVM: 25.0.2", ""),
                ]) as runner, \
                mock.patch.object(probes.Path, "cwd", return_value=repo):
            code, output = self.run_cli("verify")
        self.assertEqual(0, code, output)
        self.assertIn("info (bare java; agents use mise exec -- java)", output)
        self.assertIn("managed java | gate", output)
        self.assertIn("gradlew | gate", output)
        self.assertEqual(["mise", "exec", "--", "java", "-version"], runner.call_args_list[1].args[0])

    def test_verify_mise_frontend_decisions_gate_managed_forms(self):
        from app_sandbox import project_probes, probes, toolchain_discovery
        repo = self.home / "code/repository"
        (repo / "package.json").write_text('{"packageManager":"pnpm@11.3.0"}')
        (repo / ".mise.toml").write_text('[tools]\nnode = "24"\npnpm = "11.3.0"')
        behaviors = {"HOME write": "denied", "DB open": "denied", "loopback": "OK",
                     "cache write": "OK", "readonly write": "denied"}
        for failed_tool in (None, "node", "pnpm"):
            with self.subTest(failed_tool=failed_tool), \
                    mock.patch.dict(os.environ, {"PATH": str(self.root / "empty-bin")}), \
                    mock.patch.object(toolchain_discovery, "managers", return_value={"mise": "/fixture/mise"}), \
                    mock.patch.object(probes, "behavioral_probes", return_value=behaviors, create=True), \
                    mock.patch.object(project_probes.subprocess, "run", side_effect=[
                        FileNotFoundError(),
                        subprocess.CompletedProcess([], int(failed_tool == "node"), "v24.1.0\n", ""),
                        FileNotFoundError(),
                        subprocess.CompletedProcess([], int(failed_tool == "pnpm"), "11.3.0\n", ""),
                    ]) as runner, \
                    mock.patch.object(probes.Path, "cwd", return_value=repo):
                code, output = self.run_cli("verify")
                self.assertEqual(0 if failed_tool is None else 7, code, output)
                for tool, index in (("node", 0), ("pnpm", 2)):
                    self.assertEqual([tool, "-v"], runner.call_args_list[index].args[0])
                    self.assertEqual(["mise", "exec", "--", tool, "-v"], runner.call_args_list[index + 1].args[0])
                    self.assertIn(f"info (bare {tool}; agents use mise exec -- {tool})", output)
                    self.assertIn(f"managed {tool} | gate", output)

    def test_verify_java_managed_and_gradle_failures_gate_without_leaking_environment(self):
        from app_sandbox import project_probes, probes, toolchain_discovery
        repo = self.home / "code/repository"
        (repo / "gradlew").touch()
        (repo / ".mise.toml").write_text('[tools]\njava = "25"')
        jdk = str(self.home / "fixture-private-value/jdk")
        behaviors = {"HOME write": "denied", "DB open": "denied", "loopback": "OK",
                     "cache write": "OK", "readonly write": "denied"}
        for command in ("mise", "JAVA_HOME"):
            for failure in (None, "java", "gradlew", "behavior"):
                actual = dict(behaviors)
                if failure == "behavior":
                    actual["HOME write"] = "OK"
                with self.subTest(command=command, failure=failure), \
                        mock.patch.object(toolchain_discovery, "managers",
                                          return_value={"mise": "/fixture/mise" if command == "mise" else None}), \
                        mock.patch.object(toolchain_discovery, "jdks", return_value=[{"home": jdk, "major": "25"}]), \
                        mock.patch.dict(os.environ, {
                            "GRADLE_OPTS": "fixture-private-value", "JAVA_HOME": "fixture-private-value",
                            "GH_TOKEN": "fixture-private-value",
                            "HTTP_PROXY": "http://fixture-private-value@127.0.0.1:8080",
                        }), \
                        mock.patch.object(probes, "behavioral_probes", return_value=actual, create=True), \
                        mock.patch.object(project_probes.subprocess, "run", side_effect=[
                            subprocess.CompletedProcess([], 1, "", "EPERM fixture-private-value"),
                            subprocess.CompletedProcess([], int(failure == "java"),
                                                        'openjdk version "25.0.2"', "fixture-private-value"),
                            subprocess.CompletedProcess([], int(failure == "gradlew"),
                                                        "Launcher JVM: 25.0.2", "fixture-private-value"),
                        ]) as runner, \
                        mock.patch.object(probes.Path, "cwd", return_value=repo):
                    code, output = self.run_cli("verify")
                    self.assertEqual(0 if failure is None else 7, code, output)
                    form = "mise exec -- java" if command == "mise" else "JAVA_HOME=… java"
                    self.assertIn(f"info (bare java; agents use {form})", output)
                    self.assertNotIn("fixture-private-value", output)
                    if command == "JAVA_HOME":
                        self.assertEqual(["java", "-version"], runner.call_args_list[1].args[0])
                        self.assertEqual(jdk, runner.call_args_list[1].kwargs["env"]["JAVA_HOME"])
                        self.assertEqual(jdk, runner.call_args_list[2].kwargs["env"]["JAVA_HOME"])
                    else:
                        self.assertEqual(["mise", "exec", "--", "./gradlew", "--version",
                                          "-Dorg.gradle.java.installations.auto-download=false"],
                                         runner.call_args_list[2].args[0])

    def test_verify_no_java_pin_uses_bare_gate_and_missing_jdk_still_gates(self):
        from app_sandbox import project_probes, probes, toolchain_discovery
        repo = self.home / "code/repository"
        (repo / "gradlew").touch()
        behaviors = {"HOME write": "denied", "DB open": "denied", "loopback": "OK",
                     "cache write": "OK", "readonly write": "denied"}
        for pin, bare_fails, expected in ((False, True, 7), (False, False, 0), (True, False, 7)):
            if pin:
                (repo / ".java-version").write_text("25")
            with self.subTest(pin=pin, bare_fails=bare_fails), \
                    mock.patch.object(toolchain_discovery, "jdks", return_value=[]), \
                    mock.patch.object(probes, "behavioral_probes", return_value=behaviors, create=True), \
                    mock.patch.object(project_probes.subprocess, "run", side_effect=[
                        subprocess.CompletedProcess([], int(bare_fails), 'openjdk version "25.0.2"', ""),
                        subprocess.CompletedProcess([], 0, "Launcher JVM: 25.0.2", ""),
                    ]) as runner, \
                    mock.patch.object(probes.Path, "cwd", return_value=repo):
                code, output = self.run_cli("verify")
                self.assertEqual(expected, code, output)
                self.assertIn("java | gate", output)
                self.assertNotIn("info (bare java", output)
                self.assertEqual(2, runner.call_count)
                if pin:
                    self.assertIn("managed java | gate | ok (version 25) | not-installed", output)

    def test_backend_probes_are_bounded_no_download_and_classified_separately(self):
        from app_sandbox import project_probes, toolchain_discovery
        repo = self.home / "code/repository"
        (repo / "gradlew").touch()
        (repo / ".mise.toml").write_text('[tools]\njava = "25"')
        runner = mock.Mock(side_effect=[
            subprocess.CompletedProcess([], 1, "", "Unable to locate a Java Runtime"),
            subprocess.CompletedProcess([], 0, "", 'openjdk version "25.0.2"'),
            subprocess.CompletedProcess([], 0, "Gradle 9\nLauncher JVM: 25.0.2", ""),
        ])
        with mock.patch.object(toolchain_discovery, "managers", return_value={"mise": "/fixture/mise"}), \
                mock.patch.dict(os.environ, {"GRADLE_OPTS": "fixture-private-value"}):
            results = project_probes.run(repo, self.home, runner=runner)
        self.assertEqual(["environment", "ok", "ok"], [result["category"] for result in results])
        self.assertEqual([False, True, True], [result["gate"] for result in results])
        self.assertEqual("bare java; agents use mise exec -- java", results[0]["info"])
        self.assertEqual(["25", "25", "25"], [result["expected"] for result in results])
        self.assertEqual([20, 20, 120], [call.kwargs["timeout"] for call in runner.call_args_list])
        self.assertEqual(["java", "-version"], runner.call_args_list[0].args[0])
        self.assertEqual(["mise", "exec", "--", "java", "-version"], runner.call_args_list[1].args[0])
        self.assertIn("-Dorg.gradle.java.installations.auto-download=false", runner.call_args_list[2].args[0])
        for call in runner.call_args_list:
            self.assertEqual(str(repo), call.kwargs["cwd"])
            self.assertEqual("false", call.kwargs["env"]["MISE_EXEC_AUTO_INSTALL"])
            self.assertEqual("0", call.kwargs["env"]["COREPACK_ENABLE_DOWNLOAD_PROMPT"])
            self.assertEqual("0", call.kwargs["env"]["COREPACK_ENABLE_NETWORK"])
            self.assertEqual("false", call.kwargs["env"]["npm_config_manage_package_manager_versions"])
            self.assertEqual("fixture-private-value", call.kwargs["env"]["GRADLE_OPTS"])

    def test_verify_frontend_categories_timeouts_and_no_output_or_environment_values(self):
        from app_sandbox import project_probes, probes
        repo = self.home / "code/repository"
        (repo / "package.json").write_text('{"packageManager":"pnpm@11.3.0"}')
        (repo / ".node-version").write_text("24")
        behaviors = {"HOME write": "denied", "DB open": "denied", "loopback": "OK",
                     "cache write": "OK", "readonly write": "denied"}
        cases = (
            (subprocess.CompletedProcess([], 0, "v24.1.0\n", ""),
             subprocess.CompletedProcess([], 0, "11.3.0\n", ""), 0, "ok"),
            (subprocess.CompletedProcess([], 0, "v23.1.0\n", "fixture-private-value"),
             FileNotFoundError(), 7, "environment"),
            (subprocess.CompletedProcess([], 0, "v24.1.0\n", ""),
             subprocess.CompletedProcess([], 0, "11.3.1\n", ""), 7, "environment"),
            (OSError(errno.EPERM, "fixture-private-value"),
             subprocess.CompletedProcess([], 1, "", "Operation not permitted fixture-private-value"), 7, "seatbelt"),
            (subprocess.CompletedProcess([], 1, "", "mise: node not installed fixture-private-value"),
             subprocess.TimeoutExpired("fixture-private-value", 20, output="fixture-private-value"), 7, "not-installed"),
        )
        for node, pnpm, expected, category in cases:
            with self.subTest(category=category), \
                    mock.patch.object(probes, "behavioral_probes", return_value=behaviors, create=True), \
                    mock.patch.object(project_probes.subprocess, "run", side_effect=[node, pnpm]) as runner, \
                    mock.patch.object(probes.Path, "cwd", return_value=repo):
                code, output = self.run_cli("verify")
                self.assertEqual(expected, code, output)
                self.assertIn(category, output)
                self.assertIn("11.3.0", output)
                self.assertNotIn("fixture-private-value", output)
                self.assertIn("node | gate", output)
                self.assertIn("pnpm | gate", output)
                self.assertNotIn("info (bare", output)
                self.assertEqual(2, runner.call_count)
                self.assertEqual([["node", "-v"], ["pnpm", "-v"]],
                                 [call.args[0] for call in runner.call_args_list])
                self.assertTrue(all(call.kwargs["timeout"] == 20 for call in runner.call_args_list))

    def test_java_home_probes_and_java_gradle_timeouts_do_not_leak_outputs(self):
        from app_sandbox import project_probes, toolchain_discovery
        repo = self.home / "code/repository"
        (repo / "gradlew").touch()
        (repo / ".java-version").write_text("25")
        jdk = self.home / "Library/Java/JavaVirtualMachines/fixture/Contents/Home"
        (jdk / "bin").mkdir(parents=True)
        (jdk / "bin/java").touch()
        (jdk / "bin/java").chmod(0o700)
        (jdk / "release").write_text('JAVA_VERSION="25.0.2"')
        runner = mock.Mock(side_effect=[
            subprocess.TimeoutExpired("java", 20, output="fixture-private-value"),
            subprocess.CompletedProcess([], 1, "", "EPERM fixture-private-value"),
            subprocess.TimeoutExpired("gradle", 120, output="fixture-private-value"),
        ])
        with mock.patch.object(toolchain_discovery, "session_path", side_effect=AssertionError("no login shell")):
            results = project_probes.run(repo, self.home, runner=runner)
        self.assertEqual(["environment", "seatbelt", "environment"], [r["category"] for r in results])
        self.assertEqual([False, True, True], [r["gate"] for r in results])
        self.assertEqual("bare java; agents use JAVA_HOME=… java", results[0]["info"])
        self.assertEqual("timeout", results[0]["actual"])
        self.assertEqual(str(jdk), runner.call_args_list[1].kwargs["env"]["JAVA_HOME"])
        self.assertEqual(str(jdk), runner.call_args_list[2].kwargs["env"]["JAVA_HOME"])
        self.assertNotIn("fixture-private-value", str(results))


if __name__ == "__main__":
    unittest.main()
