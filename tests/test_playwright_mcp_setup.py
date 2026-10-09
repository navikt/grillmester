import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "plugin/skills/app-sandbox-setup/scripts"


class PlaywrightSetupTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve() / "home"
        self.home.mkdir()
        spec = importlib.util.spec_from_file_location("playwright_mcp_setup", SCRIPTS / "playwright_mcp_setup.py")
        self.setup = importlib.util.module_from_spec(spec)
        with mock.patch.object(sys, "dont_write_bytecode", True):
            spec.loader.exec_module(self.setup)
        self.config = self.home / ".copilot/mcp-config.json"
        self.docker_config = self.home / ".config/playwright-mcp/docker.json"
        self.environment = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.image_patch = mock.patch.object(self.setup, "image_warning", return_value="Docker unavailable.")
        self.image_patch.start()
        self.addCleanup(self.image_patch.stop)

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = self.setup.main([*args, "--home", str(self.home),
                                    "--mcp-config", str(self.config)])
        return code, output.getvalue()

    def plan(self):
        code, output = self.cli("plan", "--json")
        self.assertEqual(0, code, output)
        return json.loads(output)

    def apply(self):
        code, output = self.cli("apply", "--confirm", self.plan()["digest"])
        self.assertEqual(0, code, output)
        return output

    def test_fresh_install_through_confirmed_cli(self):
        plan = self.plan()
        self.assertEqual(5, len(plan["changes"]))
        self.assertIn("rerun /app-sandbox-setup", " ".join(plan["warnings"]))
        self.apply()
        for name in ("playwright-mcp-docker", "playwright-mcp-headed"):
            wrapper = self.home / ".local/bin" / name
            self.assertEqual(0o755, wrapper.stat().st_mode & 0o777)
            self.assertEqual((SCRIPTS / name).read_bytes(), wrapper.read_bytes())
        self.assertEqual(0o600, self.docker_config.stat().st_mode & 0o777)
        remote = json.loads(self.docker_config.read_text())["browser"]["remoteEndpoint"]
        self.assertRegex(remote["endpoint"], r"^ws://127\.0\.0\.1:53333/[A-Za-z0-9_-]{32,}$")
        self.assertEqual("chromium", remote["browserName"])
        self.assertEqual("<loopback>", remote["exposeNetwork"])
        servers = json.loads(self.config.read_text())["mcpServers"]
        self.assertEqual([], servers["playwright-sandbox"]["args"])
        self.assertEqual(["--isolated", "--browser", "chromium"],
                         servers["com.microsoft/playwright-mcp"]["args"])
        self.assertFalse((self.home / ".copilot/app-sandbox-setup-backups").exists())

    def test_preservation_backup_and_idempotency(self):
        entry = {"command": "old", "type": "stdio", "tools": ["browser"],
                 "args": ["--blocked-origins", "https://example.invalid", "--auth", "fixture-secret"],
                 "env": {"TOKEN": "fixture-env-secret"}, "extra": {"keep": True}}
        original = {"mcpServers": {"playwright-sandbox": entry,
                                  "com.microsoft/playwright-mcp": entry,
                                  "other": {"command": "unrelated"}}, "keep": 42}
        self.config.parent.mkdir()
        self.config.write_text(json.dumps(original))
        self.config.chmod(0o640)
        self.docker_config.parent.mkdir(parents=True)
        self.docker_config.write_text(json.dumps({"browser": {"channel": "keep"},
                                                "network": {"keep": True}}))
        before = self.config.read_bytes()
        code, output = self.cli("plan")
        self.assertEqual(0, code, output)
        self.assertNotIn("fixture-secret", output)
        self.assertNotIn("fixture-env-secret", output)
        self.assertIn("<4 args preserved>", output)
        self.apply()
        updated = json.loads(self.config.read_text())
        for key, name in (("playwright-sandbox", "docker"), ("com.microsoft/playwright-mcp", "headed")):
            expected = dict(entry, command=str(self.home / ".local/bin" / ("playwright-mcp-" + name)))
            self.assertEqual(expected, updated["mcpServers"][key])
        self.assertEqual(original["mcpServers"]["other"], updated["mcpServers"]["other"])
        self.assertEqual(42, updated["keep"])
        self.assertEqual(0o640, self.config.stat().st_mode & 0o777)
        directory = self.home / ".copilot/app-sandbox-setup-backups"
        backups = list(directory.iterdir())
        self.assertEqual(1, len(backups))
        self.assertEqual(before, backups[0].read_bytes())
        self.assertEqual(0o700, directory.stat().st_mode & 0o777)
        self.assertEqual(0o600, backups[0].stat().st_mode & 0o777)
        docker = json.loads(self.docker_config.read_text())
        self.assertEqual("keep", docker["browser"]["channel"])
        self.assertEqual({"keep": True}, docker["network"])
        token = docker["browser"]["remoteEndpoint"]["endpoint"].rsplit("/", 1)[1]
        code, output = self.cli("plan")
        self.assertEqual(0, code, output)
        self.assertIn("No changes.", output)
        self.assertNotIn(token, output)
        self.assertNotIn(token, json.dumps(self.plan()))
        self.apply()
        self.assertEqual(docker, json.loads(self.docker_config.read_text()))
        self.assertEqual(backups, list(directory.iterdir()))

    def test_symlinks_nonregular_files_and_outside_bin_are_refused_without_writes(self):
        external = self.home.parent / "outside"
        external.mkdir()
        bin_dir = self.home / ".local/bin"
        bin_dir.parent.mkdir()
        bin_dir.symlink_to(external, target_is_directory=True)
        code, _ = self.cli("plan")
        self.assertEqual(1, code)
        bin_dir.unlink()
        bin_dir.mkdir()
        wrapper = bin_dir / "playwright-mcp-docker"
        target = external / "wrapper"
        target.write_text("untouched")
        wrapper.symlink_to(target)
        code, _ = self.cli("plan")
        self.assertEqual(1, code)
        self.assertEqual("untouched", target.read_text())
        wrapper.unlink()
        wrapper.mkdir()
        self.assertEqual(1, self.cli("plan")[0])
        wrapper.rmdir()
        self.assertEqual(1, self.cli("plan", "--bin-dir", str(external))[0])
        # Do not follow symlinked parents of config or backups either.
        (self.home / ".config").symlink_to(external, target_is_directory=True)
        self.assertEqual(1, self.cli("plan")[0])
        self.assertFalse(self.config.exists())
        self.assertFalse(list(external.glob("*.json")))

    def test_invalid_config_and_stale_confirmation_fail_without_writes(self):
        self.config.parent.mkdir()
        for value in ("invalid-json", "[]", '{"mcpServers": []}',
                      '{"mcpServers": {"playwright-sandbox": null}}',
                      '{"mcpServers": {"com.microsoft/playwright-mcp": "bad"}}'):
            self.config.write_text(value)
            code, output = self.cli("plan")
            self.assertEqual(3, code, output)
            self.assertEqual(value, self.config.read_text())
            self.assertFalse(self.docker_config.exists())
        self.config.write_text('{"mcpServers": {}}')
        digest = self.plan()["digest"]
        self.config.write_text('{"mcpServers": {}, "changed": true}')
        code, output = self.cli("apply", "--confirm", digest)
        self.assertEqual(4, code, output)
        self.assertFalse(self.docker_config.exists())
        self.assertFalse((self.home / ".local/bin").exists())
        self.assertFalse((self.config.parent / "app-sandbox-setup-backups").exists())

    def test_image_checks_are_bounded_and_do_not_print_subprocess_data(self):
        self.image_patch.stop()
        with mock.patch.object(self.setup, "find_docker", return_value=None):
            self.assertIn("unavailable", " ".join(self.plan()["warnings"]))
        with mock.patch.object(self.setup, "find_docker", return_value="/fixture/docker"):
            with mock.patch.object(self.setup.subprocess, "run") as run:
                run.side_effect = [mock.Mock(returncode=1), mock.Mock(returncode=0)]
                output = " ".join(self.plan()["warnings"])
                self.assertIn("docker pull " + self.setup.IMAGE, output)
                self.assertIn("OUTSIDE the sandbox", output)
                self.assertEqual(["/fixture/docker", "image", "inspect", self.setup.IMAGE],
                                 run.call_args_list[0].args[0])
                self.assertLessEqual(run.call_args_list[0].kwargs["timeout"], 5)
                self.assertIs(run.call_args_list[0].kwargs["stdout"], self.setup.subprocess.DEVNULL)
                run.side_effect = [mock.Mock(returncode=1), mock.Mock(returncode=1)]
                self.assertIn("not running", " ".join(self.plan()["warnings"]))
                run.side_effect = self.setup.subprocess.TimeoutExpired("fixture", 3)
                self.assertIn("timed out", " ".join(self.plan()["warnings"]))

    def test_remote_options_are_preserved_and_token_is_only_generated_at_apply(self):
        self.docker_config.parent.mkdir(parents=True)
        self.docker_config.write_text(json.dumps({"browser": {"remoteEndpoint": {
            "headers": {"Authorization": "fixture-sensitive-header"},
            "timeout": 1000, "endpoint": "invalid"}}}))
        before = self.docker_config.read_bytes()
        first = self.plan()
        self.assertEqual(first["digest"], self.plan()["digest"])
        self.assertEqual(before, self.docker_config.read_bytes())
        self.assertNotIn("fixture-sensitive-header", json.dumps(first))
        self.apply()
        remote = json.loads(self.docker_config.read_text())["browser"]["remoteEndpoint"]
        self.assertEqual({"Authorization": "fixture-sensitive-header"}, remote["headers"])
        self.assertEqual(1000, remote["timeout"])
        endpoint = remote["endpoint"]
        self.assertTrue(self.setup.valid_endpoint(endpoint))
        self.assertEqual([], self.plan()["changes"])
        self.docker_config.chmod(0o644)
        self.assertTrue(self.plan()["changes"])
        self.apply()
        self.assertEqual(0o600, self.docker_config.stat().st_mode & 0o777)
        self.assertTrue(endpoint == json.loads(self.docker_config.read_text())["browser"]["remoteEndpoint"]["endpoint"])

    def test_usage_error_does_not_echo_unknown_secret_arguments(self):
        code, output = self.cli("plan", "--unknown-secret", "fixture-private-value")
        self.assertEqual(1, code)
        self.assertNotIn("fixture-private-value", output)
        self.assertEqual(1, self.cli("apply")[0])

    def test_target_swapped_to_symlink_after_preflight_is_not_read(self):
        directory = self.home / ".local/bin"
        directory.mkdir(parents=True)
        wrapper = directory / "playwright-mcp-docker"
        wrapper.write_text("old")
        target = self.home / "unrelated"
        target.write_text("private fixture content")
        check = self.setup.check_path
        swapped = False

        def swap(path, directory=False):
            nonlocal swapped
            check(path, directory)
            if path == wrapper and not swapped:
                path.unlink()
                path.symlink_to(target)
                swapped = True

        with mock.patch.object(self.setup, "check_path", side_effect=swap):
            code, output = self.cli("plan")
        self.assertEqual(1, code, output)
        self.assertNotIn("private fixture content", output)
        self.assertFalse(self.config.exists())

    def test_config_only_format_change_is_visible_and_failed_replace_keeps_original(self):
        self.apply()
        self.config.write_text(json.dumps(json.loads(self.config.read_text())))
        plan = self.plan()
        self.assertTrue(any(change.get("file") == str(self.config) for change in plan["changes"]))
        before = self.config.read_bytes()
        replace = self.setup.os.replace

        def fail_config_replace(source, target):
            if target == self.config:
                raise OSError("fixture-private-error")
            return replace(source, target)

        with mock.patch.object(self.setup.os, "replace", side_effect=fail_config_replace):
            code, output = self.cli("apply", "--confirm", plan["digest"])
        self.assertEqual(1, code, output)
        self.assertNotIn("fixture-private-error", output)
        self.assertEqual(before, self.config.read_bytes())
        self.assertEqual([], list(self.config.parent.glob(".mcp-config.json.*")))
        backup = next((self.config.parent / "app-sandbox-setup-backups").iterdir())
        self.assertEqual(before, backup.read_bytes())


class PlaywrightWrapperTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "argv.jsonl"
        self.config = self.home / "docker.json"
        self.token = "fixture-only-not-a-real-secret-path-123456"
        self.config.write_text(json.dumps({"browser": {"remoteEndpoint": {
            "endpoint": "ws://127.0.0.1:54444/" + self.token}}}))
        self.env = {"HOME": str(self.home), "PATH": str(self.bin),
                    "PW_MCP_CONFIG": str(self.config), "PW_READY_TIMEOUT": "1",
                    "FIXTURE_LOG": str(self.log), "PYTHONDONTWRITEBYTECODE": "1"}
        for name, source in (("python3", sys.executable), ("rm", "/bin/rm"),
                             ("mktemp", "/usr/bin/mktemp"), ("sleep", "/bin/sleep")):
            (self.bin / name).symlink_to(source)
        self.fake("docker", """
if args[:2] == ['image', 'inspect']:
    sys.exit(int(os.environ.get('IMAGE_MISSING', '0')))
if args[0] == 'inspect':
    print(os.environ.get('CONTAINER_JSON', '[]'))
if args[0] == 'run':
    print('fixture-container')
""")
        self.fake("curl", "sys.exit(int(os.environ.get('NOT_READY', '0')))")
        self.fake("pnpm", "")
        self.fake("npx", "")

    def fake(self, name, body):
        path = self.bin / name
        path.write_text("#!" + sys.executable + "\n"
                        "import json, os, sys\nargs = sys.argv[1:]\n"
                        "with open(os.environ['FIXTURE_LOG'], 'a') as log:\n"
                        "    log.write(json.dumps([os.path.basename(sys.argv[0]), args]) + '\\n')\n"
                        + body + "\n")
        path.chmod(0o755)

    def run_wrapper(self, name="docker", *args):
        return subprocess.run(["/bin/bash", str(SCRIPTS / ("playwright-mcp-" + name)), *args],
                              env=self.env, text=True, capture_output=True, timeout=10)

    def calls(self, executable):
        return [args for name, args in (json.loads(line) for line in self.log.read_text().splitlines())
                if name == executable]

    def test_container_start_and_mcp_passthrough_use_pinned_safe_defaults(self):
        result = self.run_wrapper("docker", "--block-service-workers")
        self.assertEqual(0, result.returncode, result.stderr)
        run = next(args for args in self.calls("docker") if args[0] == "run")
        for flag in ("--rm", "--init"):
            self.assertIn(flag, run)
        for flag, value in (("-p", "127.0.0.1:54444:3333"), ("--user", "pwuser"),
                            ("--workdir", "/home/pwuser"), ("--path", "/" + self.token)):
            self.assertTrue(run[run.index(flag) + 1] == value)
        self.assertIn("mcr.microsoft.com/playwright:v1.63.0-noble", run)
        self.assertIn("playwright@1.63.0", run)
        self.assertNotIn("--unsafe", run)
        self.assertNotIn("--no-sandbox", run)
        self.assertEqual([["dlx", "@playwright/mcp@0.0.80", "--config", str(self.config),
                           "--block-service-workers"]], self.calls("pnpm"))
        self.assertNotIn(self.token, result.stdout + result.stderr)

    def test_image_missing_exits_with_outside_pull_advice_without_starting_container(self):
        self.env["IMAGE_MISSING"] = "1"
        result = self.run_wrapper()
        self.assertEqual(1, result.returncode)
        self.assertIn("outside the sandbox: docker pull mcr.microsoft.com/playwright:v1.63.0-noble", result.stderr)
        self.assertFalse(any(args[0] == "run" for args in self.calls("docker")))
        self.assertFalse(self.calls("pnpm"))

    def test_npx_and_mise_fallbacks_and_explicit_missing_runner_error(self):
        (self.bin / "pnpm").unlink()
        result = self.run_wrapper("docker", "--block-service-workers")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([["-y", "@playwright/mcp@0.0.80", "--config", str(self.config),
                          "--block-service-workers"]], self.calls("npx"))
        (self.bin / "npx").unlink()
        result = self.run_wrapper()
        self.assertEqual(1, result.returncode)
        self.assertIn("Install pnpm or npx", result.stderr)
        shims = self.home / ".local/share/mise/shims"
        shims.mkdir(parents=True)
        self.fake("pnpm", "")
        (self.bin / "pnpm").rename(shims / "pnpm")
        result = self.run_wrapper("headed", "--isolated")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["dlx", "@playwright/mcp@0.0.80", "--isolated"], self.calls("pnpm")[-1])
        self.assertEqual([], list(self.home.glob(".playwright-mcp-sandbox-probe.*")))

    def test_readiness_timeout_is_bounded_and_does_not_exec_mcp(self):
        self.env["NOT_READY"] = "1"
        result = self.run_wrapper()
        self.assertEqual(1, result.returncode)
        self.assertIn("Readiness timed out", result.stderr)
        self.assertFalse(self.calls("pnpm"))

    def test_existing_container_is_reused_only_with_matching_path_port_and_hardening(self):
        container = {"State": {"Running": True}, "Config": {
            "Cmd": ["npx", "-y", "playwright@1.63.0", "run-server", "--path", "/" + self.token],
            "Image": "mcr.microsoft.com/playwright:v1.63.0-noble",
            "User": "pwuser", "WorkingDir": "/home/pwuser"},
            "HostConfig": {"PortBindings": {"3333/tcp": [{"HostIp": "127.0.0.1", "HostPort": "54444"}]}}}
        self.env["CONTAINER_JSON"] = json.dumps([container])
        result = self.run_wrapper()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(any(args[0] == "run" for args in self.calls("docker")))
        for change in ("path", "port", "unsafe"):
            with self.subTest(change=change):
                altered = json.loads(json.dumps(container))
                if change == "path":
                    altered["Config"]["Cmd"][-1] = "/old-fixture-path"
                elif change == "port":
                    altered["HostConfig"]["PortBindings"]["3333/tcp"][0]["HostPort"] = "54445"
                else:
                    altered["Config"]["Cmd"].append("--unsafe")
                self.env["CONTAINER_JSON"] = json.dumps([altered])
                self.log.unlink()
                result = self.run_wrapper()
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertTrue(any(args[0] == "rm" for args in self.calls("docker")))
                self.assertTrue(any(args[0] == "run" for args in self.calls("docker")))

    def test_bash_syntax_and_headed_sandbox_refusal(self):
        for name in ("docker", "headed"):
            result = subprocess.run(["/bin/bash", "-n", str(SCRIPTS / ("playwright-mcp-" + name))],
                                    env=self.env, capture_output=True)
            self.assertEqual(0, result.returncode)
        if os.geteuid() == 0:
            self.skipTest("root bypasses readonly HOME")
        self.home.chmod(0o500)
        try:
            result = self.run_wrapper("headed")
            self.assertEqual(1, result.returncode)
            self.assertIn("running inside the Copilot sandbox; use the playwright-sandbox", result.stderr)
            self.assertFalse(self.log.exists())
        finally:
            self.home.chmod(0o700)

    def test_invalid_overrides_are_rejected_without_invoking_docker(self):
        self.env["PW_IMAGE"] = "--help"
        result = self.run_wrapper()
        self.assertEqual(1, result.returncode)
        self.assertIn("Invalid PW_IMAGE", result.stderr)
        self.assertFalse(self.log.exists())
        self.env.pop("PW_IMAGE")
        self.env["PW_DOCKER_PORT"] = "54445"
        self.env["PYTHONOPTIMIZE"] = "1"
        result = self.run_wrapper()
        self.assertEqual(1, result.returncode)
        self.assertIn("conflicting port/path override", result.stderr)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
