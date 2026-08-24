from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_local", ROOT / "scripts/grillmester_local.py"
)
assert SPEC is not None and SPEC.loader is not None
LOCAL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = LOCAL
SPEC.loader.exec_module(LOCAL)


class ProbeHandler(BaseHTTPRequestHandler):
    models = ["qwen3.8-local"]
    authorization: str | None = None
    redirect: str | None = None

    def do_GET(self) -> None:  # noqa: N802
        type(self).authorization = self.headers.get("Authorization")
        if self.path != "/v1/models":
            self.send_response(404)
            self.end_headers()
            return
        if type(self).redirect is not None:
            self.send_response(302)
            self.send_header("Location", type(self).redirect)
            self.end_headers()
            return
        payload = json.dumps(
            {"object": "list", "data": [{"id": item} for item in type(self).models]}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_arguments: object) -> None:
        return


class ProbeServer:
    def __init__(self) -> None:
        ProbeHandler.models = ["qwen3.8-local"]
        ProbeHandler.authorization = None
        ProbeHandler.redirect = None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ProbeHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "ProbeServer":
        self.thread.start()
        return self

    def __exit__(self, *_arguments: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/v1"


class LocalModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.distribution = self.root / "distribution"
        for payload in (
            "plugin",
            "targets/opencode-v1",
            "targets/opencode-v1-focused",
            "targets/copilot-cli-focused-v1",
        ):
            (self.distribution / payload).mkdir(parents=True)
        (self.distribution / "plugin/plugin.json").write_text(
            json.dumps({"name": "grillmester"}), encoding="utf-8"
        )
        for payload, target in (
            ("targets/opencode-v1", "opencode-v1"),
            ("targets/opencode-v1-focused", "opencode-v1-focused"),
            ("targets/copilot-cli-focused-v1", "copilot-cli-focused-v1"),
        ):
            (self.distribution / payload / "manifest.json").write_text(
                json.dumps({"schemaVersion": 1, "target": target, "files": {}}),
                encoding="utf-8",
            )
        self.project = self.root / "consumer"
        self.project.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.cplt = self._binary("cplt")
        self.opencode = self._binary("opencode")
        self.copilot = self._binary("copilot")
        self.ripgrep = self._binary("rg")
        self.gh = self._binary("gh")
        self.environment = {
            "PATH": str(self.bin),
            "HOME": str(self.root / "home"),
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_STATE_HOME": str(self.root / "state"),
            "LANG": "en_US.UTF-8",
            "GH_TOKEN": "must-not-cross",
            "GITHUB_TOKEN": "must-not-cross",
            "OPENAI_API_KEY": "must-not-cross",
            "AWS_SECRET_ACCESS_KEY": "must-not-cross",
        }
        Path(self.environment["HOME"]).mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _binary(self, name: str) -> Path:
        path = self.bin / name
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o700)
        return path

    @staticmethod
    def _config(**overrides: object) -> LOCAL.LocalConfig:
        values: dict[str, object] = {
            "client": "opencode",
            "agent": "barista",
            "context": "focused",
            "provider_id": "llamacpp",
            "base_url": "http://127.0.0.1:8080/v1",
            "model_id": "qwen3.8-local",
        }
        values.update(overrides)
        return LOCAL.LocalConfig(**values)

    def _launch(
        self,
        config: LOCAL.LocalConfig | None = None,
        *,
        arguments: tuple[str, ...] = (),
        github_access: bool = False,
    ) -> LOCAL.LocalLaunch:
        config = config or self._config()
        client = self.opencode if config.client == "opencode" else self.copilot
        return LOCAL.build_local_launch(
            config,
            distribution_root=self.distribution,
            project_dir=self.project,
            cplt=SimpleNamespace(path=str(self.cplt), version="reviewed"),
            client=SimpleNamespace(path=str(client), version="reviewed"),
            client_arguments=arguments,
            github_access=github_access,
            environment=self.environment,
            platform="darwin",
        )

    def test_config_round_trip_is_atomic_private_and_contains_no_credential(self) -> None:
        self.environment["LOCAL_MODEL_TOKEN"] = "super-secret-value"
        config = self._config(client="copilot", api_key_env="LOCAL_MODEL_TOKEN")

        path = LOCAL.save_config(config, environment=self.environment)
        loaded = LOCAL.load_config(environment=self.environment)

        self.assertEqual(config, loaded)
        self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))
        self.assertEqual(0o700, stat.S_IMODE(path.parent.stat().st_mode))
        self.assertNotIn("super-secret-value", path.read_text(encoding="utf-8"))
        self.assertFalse(list(path.parent.glob(f".{path.name}.*")))

    def test_config_rejects_symlink_and_group_readable_file(self) -> None:
        path = LOCAL.config_path(self.environment)
        path.parent.mkdir(parents=True)
        target = self.root / "target.json"
        target.write_text("{}", encoding="utf-8")
        target.chmod(0o600)
        path.symlink_to(target)
        with self.assertRaisesRegex(LOCAL.LocalModeError, "non-symlink"):
            LOCAL.load_config(environment=self.environment)

        path.unlink()
        path.write_text("{}", encoding="utf-8")
        path.chmod(0o640)
        with self.assertRaisesRegex(LOCAL.LocalModeError, "group or others"):
            LOCAL.load_config(environment=self.environment)

    def test_save_refuses_to_replace_symlink(self) -> None:
        path = LOCAL.config_path(self.environment)
        path.parent.mkdir(parents=True)
        victim = self.root / "victim"
        victim.write_text("untouched", encoding="utf-8")
        path.symlink_to(victim)

        with self.assertRaisesRegex(LOCAL.LocalModeError, "non-regular"):
            LOCAL.save_config(self._config(), environment=self.environment)
        self.assertEqual("untouched", victim.read_text(encoding="utf-8"))

    def test_config_schema_is_exact(self) -> None:
        path = LOCAL.save_config(self._config(), environment=self.environment)
        value = json.loads(path.read_text(encoding="utf-8"))
        value["credential"] = "forbidden"
        path.write_text(json.dumps(value), encoding="utf-8")
        path.chmod(0o600)
        with self.assertRaisesRegex(LOCAL.LocalModeError, "unexpected"):
            LOCAL.load_config(environment=self.environment)

    def test_focused_context_is_barista_only_but_full_keeps_public_agents(self) -> None:
        with self.assertRaisesRegex(LOCAL.LocalModeError, "only the barista"):
            LOCAL.validate_config(self._config(agent="grillmester"))
        observed = LOCAL.validate_config(
            self._config(agent="doctor-who", context="full")
        )
        self.assertEqual("doctor-who", observed.agent)

    def test_base_url_requires_http_loopback_explicit_port_and_exact_v1(self) -> None:
        invalid = (
            "https://127.0.0.1:8080/v1",
            "http://example.com:8080/v1",
            "http://10.0.0.1:8080/v1",
            "http://127.0.0.1/v1",
            "http://127.0.0.1:8080/v1/",
            "http://user:secret@127.0.0.1:8080/v1",
            "http://127.0.0.1:8080/v1?q=1",
        )
        for base_url in invalid:
            with self.subTest(base_url=base_url), self.assertRaises(LOCAL.LocalModeError):
                LOCAL.validate_config(self._config(base_url=base_url))

        for base_url in (
            "http://localhost:8080/v1",
            "http://127.0.0.2:8080/v1",
            "http://[::1]:8080/v1",
        ):
            with self.subTest(base_url=base_url):
                self.assertEqual(8080, LOCAL.validate_config(self._config(base_url=base_url)).port)

    def test_provider_model_and_key_selector_are_strict(self) -> None:
        with self.assertRaisesRegex(LOCAL.LocalModeError, "providerId"):
            LOCAL.validate_config(self._config(provider_id="Bad Provider"))
        with self.assertRaisesRegex(LOCAL.LocalModeError, "modelId"):
            LOCAL.validate_config(self._config(model_id="--cloud"))
        with self.assertRaisesRegex(LOCAL.LocalModeError, "at most one"):
            LOCAL.validate_config(
                self._config(
                    client="copilot",
                    api_key_env="LOCAL_KEY",
                    api_key_file=Path("/tmp/key"),
                ),
                check_key_file=False,
            )
        for name in LOCAL.SAFE_HOST_ENVIRONMENT:
            with self.subTest(api_key_env=name), self.assertRaisesRegex(
                LOCAL.LocalModeError, "host environment variable"
            ):
                LOCAL.validate_config(
                    self._config(client="copilot", api_key_env=name)
                )

    def test_api_key_file_must_be_absolute_regular_and_private(self) -> None:
        key = self.root / "key"
        key.write_text("secret\n", encoding="utf-8")
        key.chmod(0o644)
        with self.assertRaisesRegex(LOCAL.LocalModeError, "group or others"):
            LOCAL.validate_config(self._config(client="copilot", api_key_file=key))
        key.chmod(0o600)
        self.assertEqual(
            key.resolve(strict=True),
            LOCAL.validate_config(
                self._config(client="copilot", api_key_file=key)
            ).api_key_file,
        )
        linked = self.root / "key-hardlink"
        os.link(key, linked)
        with self.assertRaisesRegex(LOCAL.LocalModeError, "hard links"):
            LOCAL.validate_config(self._config(client="copilot", api_key_file=key))
        linked.unlink()

        real_parent = self.root / "real-key-parent"
        real_parent.mkdir()
        canonical_key = real_parent / "provider.key"
        canonical_key.write_text("secret\n", encoding="utf-8")
        canonical_key.chmod(0o600)
        parent_alias = self.root / "key-parent-alias"
        parent_alias.symlink_to(real_parent, target_is_directory=True)
        self.assertEqual(
            canonical_key.resolve(strict=True),
            LOCAL.validate_config(
                self._config(
                    client="copilot",
                    api_key_file=parent_alias / "provider.key",
                )
            ).api_key_file,
        )
        with self.assertRaisesRegex(LOCAL.LocalModeError, "absolute"):
            LOCAL.validate_config(
                self._config(client="copilot", api_key_file=Path("relative-key")),
                check_key_file=False,
            )

    def test_probe_disables_ambient_proxy_and_verifies_exact_model(self) -> None:
        with ProbeServer() as server:
            config = self._config(base_url=server.base_url)
            environment = {**self.environment, "HTTP_PROXY": "http://127.0.0.1:9"}
            result = LOCAL.probe_model(config, environment=environment)
            self.assertEqual("qwen3.8-local", result.model_id)
            self.assertEqual(("qwen3.8-local",), result.advertised_models)

            ProbeHandler.models = ["a-different-model"]
            with self.assertRaisesRegex(LOCAL.LocalModeError, "exact modelId"):
                LOCAL.probe_model(config, environment=environment)

    def test_probe_passes_only_explicit_auth_and_refuses_redirect(self) -> None:
        with ProbeServer() as server:
            config = self._config(
                client="copilot",
                base_url=server.base_url,
                api_key_env="LOCAL_MODEL_TOKEN",
            )
            environment = {**self.environment, "LOCAL_MODEL_TOKEN": "private-token"}
            LOCAL.probe_model(config, environment=environment)
            self.assertEqual("Bearer private-token", ProbeHandler.authorization)

            ProbeHandler.redirect = "https://example.com/v1/models"
            with self.assertRaisesRegex(LOCAL.LocalModeError, "redirect"):
                LOCAL.probe_model(config, environment=environment)

    def test_probe_never_mentions_secret_in_error(self) -> None:
        config = self._config(
            client="copilot",
            base_url="http://127.0.0.1:1/v1",
            api_key_env="LOCAL_MODEL_TOKEN",
        )
        with self.assertRaises(LOCAL.LocalModeError) as raised:
            LOCAL.probe_model(
                config,
                environment={**self.environment, "LOCAL_MODEL_TOKEN": "do-not-print"},
                timeout=0.1,
            )
        self.assertNotIn("do-not-print", str(raised.exception))

    def test_opencode_launch_uses_cplt_connected_policy_and_focused_payload(self) -> None:
        launch = self._launch()
        command = list(launch.command)
        separator = command.index("--")

        self.assertEqual(str(self.cplt.resolve(strict=True)), command[0])
        self.assertEqual(str(self.bin.resolve(strict=True)), launch.environment["PATH"].split(os.pathsep)[0])
        self.assertEqual(
            self.opencode.resolve(strict=True),
            Path(shutil.which("opencode", path=launch.environment["PATH"])).resolve(strict=True),
        )
        self.assertEqual(
            self.gh.resolve(strict=True),
            Path(shutil.which("gh", path=launch.environment["PATH"])).resolve(strict=True),
        )
        self.assertEqual(["--agent", "opencode"], command[command.index("--agent") : command.index("--agent") + 2])
        for flag in (
            "--proxy-forced",
            "--gh-guard",
            "--git-guard",
            "--no-audit",
            "--deny-clipboard",
        ):
            self.assertIn(flag, command[:separator])
        for forbidden in (
            "exec",
            "shell",
            "--allow-all-domains",
            "--default-allowlist",
            "--inherit-env",
        ):
            self.assertNotIn(forbidden, command[:separator])
        self.assertEqual("8080", command[command.index("--allow-localhost") + 1])
        self.assertEqual(
            ["--agent", "barista", "--model", "llamacpp/qwen3.8-local"],
            command[separator + 1 :],
        )
        self.assertEqual(
            (self.distribution / "targets/opencode-v1-focused").resolve(strict=True),
            launch.payload,
        )

    def test_network_and_sandbox_policy_are_delegated_to_cplt(self) -> None:
        launch = self._launch()
        command = list(launch.command)
        self.assertIn("--proxy-forced", command)
        self.assertIn("--gh-guard", command)
        self.assertIn("--git-guard", command)
        self.assertNotIn("--allow-all-domains", command)
        self.assertNotIn("--preset", command)
        self.assertNotIn("--allowed-domains", command)
        self.assertNotIn("--blocked-domains", command)
        writable = {
            command[index + 1]
            for index, value in enumerate(command)
            if value == "--allow-write"
        }
        self.assertNotIn(str(launch.runtime.root), writable)
        self.assertNotIn(str(launch.runtime.root), writable)

    def test_caller_cplt_policy_is_preserved_without_being_passed_to_child(self) -> None:
        policy = self.root / "managed-cplt.toml"
        policy.write_text(
            '[proxy]\nallowed_domains = "/managed/allowlist.txt"\n',
            encoding="utf-8",
        )
        self.environment["CPLT_CONFIG"] = str(policy)

        launch = self._launch()

        self.assertEqual(str(policy), launch.environment["CPLT_CONFIG"])
        command = list(launch.command)
        passed = {
            command[index + 1]
            for index, value in enumerate(command)
            if value == "--pass-env"
        }
        self.assertNotIn("CPLT_CONFIG", passed)
        self.assertNotIn("--allow-all-domains", command)

    def test_repository_cplt_proposals_are_left_to_cplt(self) -> None:
        (self.project / ".cplt.toml").write_text(
            "[propose.allow]\nlocalhost = [9999]\n", encoding="utf-8"
        )

        launch = self._launch()

        self.assertNotIn("--accept-repo-config", launch.command)

    def test_each_launch_gets_a_private_isolated_session_root(self) -> None:
        first = self._launch()
        second = self._launch()

        self.assertNotEqual(first.runtime.root, second.runtime.root)
        self.assertEqual(0o700, stat.S_IMODE(first.runtime.root.stat().st_mode))
        self.assertEqual(0o700, stat.S_IMODE(second.runtime.root.stat().st_mode))
        self.assertEqual(first.runtime.root.parent, second.runtime.root.parent)

    def test_concurrent_session_creation_never_prunes_an_ownerless_peer(self) -> None:
        runtimes: list[LOCAL.RuntimePaths] = []
        failures: list[BaseException] = []
        start = threading.Barrier(8)

        def create() -> None:
            try:
                start.wait(timeout=5)
                runtimes.append(LOCAL._prepare_runtime(self.environment, "opencode"))
            except BaseException as exc:  # captured for assertion in main thread
                failures.append(exc)

        threads = [threading.Thread(target=create) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual([], failures)
        self.assertEqual(8, len(runtimes))
        self.assertEqual(8, len({runtime.root for runtime in runtimes}))
        self.assertTrue(all(runtime.root.is_dir() for runtime in runtimes))
        self.assertTrue(
            all(
                (runtime.root / LOCAL.SESSION_OWNER_FILE)
                .read_text(encoding="ascii")
                .split()[0]
                == str(os.getpid())
                for runtime in runtimes
            )
        )

    def test_session_liveness_rejects_pid_reuse_by_process_birth_identity(self) -> None:
        session = self.root / "opencode-owner"
        session.mkdir()
        owner = session / LOCAL.SESSION_OWNER_FILE
        owner.write_text(f"{os.getpid()} {'a' * 32}\n", encoding="ascii")
        owner.chmod(0o600)

        with mock.patch.object(
            LOCAL, "_process_start_identity", return_value="b" * 32
        ):
            self.assertFalse(LOCAL._session_owner_is_alive(session))
        with mock.patch.object(
            LOCAL, "_process_start_identity", return_value="a" * 32
        ):
            self.assertTrue(LOCAL._session_owner_is_alive(session))
        with mock.patch.object(LOCAL, "_process_start_identity", return_value=None):
            self.assertTrue(LOCAL._session_owner_is_alive(session))

    def test_inactive_session_retention_is_bounded_without_touching_live_state(self) -> None:
        parent = LOCAL.state_root(self.environment) / "sessions"
        parent.mkdir(parents=True)
        parent.chmod(0o700)
        stale: list[Path] = []
        for index in range(5):
            session = parent / f"opencode-stale{index}"
            session.mkdir(mode=0o700)
            owner = session / LOCAL.SESSION_OWNER_FILE
            owner.write_text("999999999\n", encoding="ascii")
            owner.chmod(0o600)
            os.utime(session, ns=(index + 1, index + 1))
            stale.append(session)
        live = parent / "copilot-live"
        live.mkdir(mode=0o700)
        owner = live / LOCAL.SESSION_OWNER_FILE
        owner.write_text(f"{os.getpid()}\n", encoding="ascii")
        owner.chmod(0o600)

        runtime = LOCAL._prepare_runtime(self.environment, "opencode")

        self.assertTrue(live.is_dir())
        self.assertTrue(runtime.root.is_dir())
        retained_stale = [path for path in stale if path.exists()]
        self.assertEqual(LOCAL.RETAINED_INACTIVE_SESSIONS - 1, len(retained_stale))
        self.assertEqual(stale[-1:], retained_stale)

    def test_sequential_completed_sessions_leave_at_most_two_roots(self) -> None:
        parent = LOCAL.state_root(self.environment) / "sessions"
        for _ in range(4):
            runtime = LOCAL._prepare_runtime(self.environment, "opencode")
            owner = runtime.root / LOCAL.SESSION_OWNER_FILE
            owner.write_text("999999999\n", encoding="ascii")
            owner.chmod(0o600)

        sessions = [
            path
            for path in parent.iterdir()
            if path.is_dir() and path.name.startswith("opencode-")
        ]
        self.assertEqual(LOCAL.RETAINED_INACTIVE_SESSIONS, len(sessions))

    def test_pruning_migrates_legacy_sealed_binary_session_without_following_links(self) -> None:
        parent = LOCAL.state_root(self.environment) / "sessions"
        parent.mkdir(parents=True)
        parent.chmod(0o700)
        stale = parent / "opencode-legacy"
        trusted_bin = stale / "trusted-bin"
        trusted_bin.mkdir(parents=True, mode=0o700)
        (stale / LOCAL.SESSION_OWNER_FILE).write_text(
            "999999999\n", encoding="ascii"
        )
        staged = trusted_bin / "cplt"
        staged.write_bytes(b"legacy staged binary")
        staged.chmod(0o500)
        outside = self.root / "outside"
        outside.write_text("keep", encoding="ascii")
        (trusted_bin / "outside-link").symlink_to(outside)
        trusted_bin.chmod(0o500)
        stale.chmod(0o500)

        LOCAL._prune_inactive_sessions(parent, retain=0)

        self.assertFalse(stale.exists())
        self.assertEqual("keep", outside.read_text(encoding="ascii"))

    def test_concurrent_session_pruning_tolerates_the_same_victim_disappearing(self) -> None:
        parent = LOCAL.state_root(self.environment) / "sessions"
        parent.mkdir(parents=True)
        parent.chmod(0o700)
        stale: list[Path] = []
        for index in range(5):
            session = parent / f"opencode-race{index}"
            session.mkdir(mode=0o700)
            owner = session / LOCAL.SESSION_OWNER_FILE
            owner.write_text("999999999\n", encoding="ascii")
            owner.chmod(0o600)
            os.utime(session, ns=(index + 1, index + 1))
            stale.append(session)

        original_rmtree = LOCAL.shutil.rmtree
        barrier = threading.Barrier(2)
        failures: list[BaseException] = []

        def racing_rmtree(path: Path, *args: object, **kwargs: object) -> None:
            barrier.wait(timeout=5)
            original_rmtree(path, *args, **kwargs)

        def prune() -> None:
            try:
                LOCAL._prune_inactive_sessions(parent)
            except BaseException as exc:  # captured for assertion in main thread
                failures.append(exc)

        with mock.patch.object(LOCAL.shutil, "rmtree", side_effect=racing_rmtree):
            threads = [threading.Thread(target=prune) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual([], failures)
        self.assertLessEqual(
            len([session for session in stale if session.exists()]),
            LOCAL.RETAINED_INACTIVE_SESSIONS,
        )

    def test_opencode_sessions_keep_path_ripgrep_available(self) -> None:
        launch = self._launch()
        self.assertEqual(
            self.ripgrep.resolve(strict=True),
            Path(shutil.which("rg", path=launch.environment["PATH"])).resolve(strict=True),
        )

    def test_install_hints_match_the_parent_launcher(self) -> None:
        cli_spec = importlib.util.spec_from_file_location(
            "grillmester_cli_hint_check", ROOT / "scripts/grillmester.py"
        )
        assert cli_spec is not None and cli_spec.loader is not None
        cli = importlib.util.module_from_spec(cli_spec)
        sys.modules[cli_spec.name] = cli
        try:
            cli_spec.loader.exec_module(cli)
            self.assertEqual(cli.CLIENT_INSTALL_HINTS, LOCAL.CLIENT_INSTALL_HINTS)
        finally:
            sys.modules.pop(cli_spec.name, None)

    def test_interactive_prompt_eof_becomes_a_clean_local_error(self) -> None:
        for interrupt in (EOFError, KeyboardInterrupt):
            with self.subTest(interrupt=interrupt):
                with mock.patch("builtins.input", side_effect=interrupt):
                    with redirect_stdout(io.StringIO()):
                        with self.assertRaisesRegex(
                            LOCAL.LocalModeError, "selection cancelled"
                        ):
                            LOCAL._prompt("Klient [1-2]: ")

    def test_foreign_or_irregular_session_entries_never_block_pruning(self) -> None:
        parent = LOCAL.state_root(self.environment) / "sessions"
        parent.mkdir(parents=True)
        parent.chmod(0o700)
        kept = parent / "opencode-owned"
        kept.mkdir(mode=0o700)
        symlinked = parent / "opencode-symlinked"
        symlinked.symlink_to(kept)
        irregular = parent / "opencode-notadir"
        irregular.write_text("", encoding="ascii")

        LOCAL._prune_inactive_sessions(parent)
        with mock.patch.object(LOCAL.os, "geteuid", return_value=os.geteuid() + 1):
            LOCAL._prune_inactive_sessions(parent)

        self.assertTrue(kept.is_dir())
        self.assertTrue(symlinked.is_symlink())
        self.assertTrue(irregular.is_file())

    def test_host_environment_is_sanitized_and_source_key_is_renamed(self) -> None:
        launch = self._launch()
        for name in (
            "GH_TOKEN",
            "GITHUB_TOKEN",
            "OPENAI_API_KEY",
            "AWS_SECRET_ACCESS_KEY",
        ):
            self.assertNotIn(name, launch.environment)
        config_content = json.loads(launch.environment["OPENCODE_CONFIG_CONTENT"])
        provider = config_content["provider"]["llamacpp"]
        self.assertEqual("@ai-sdk/openai-compatible", provider["npm"])
        self.assertNotIn("apiKey", provider["options"])
        self.assertEqual("{}", launch.environment["OPENCODE_AUTH_CONTENT"])
        self.assertEqual("true", launch.environment["OPENCODE_ENABLE_EXA"])

    def test_opencode_never_executes_ambient_gh_outside_cplt(self) -> None:
        marker = self.root / "ambient-gh-executed"
        self.gh.write_text(
            f"#!/bin/sh\ntouch {marker}\nprintf '%s\\n' github_pat_test_secret\n",
            encoding="utf-8",
        )
        self.gh.chmod(0o700)

        launch = self._launch()

        self.assertFalse(marker.exists())
        self.assertNotIn("GH_TOKEN", launch.environment)
        self.assertNotIn("GH_TOKEN", launch.secret_environment)

    def test_clients_deny_every_existing_host_gh_config_directory(self) -> None:
        custom = self.root / "work-gh-config"
        custom.mkdir()
        xdg = Path(self.environment["XDG_CONFIG_HOME"]) / "gh"
        xdg.mkdir(parents=True)
        default = Path(self.environment["HOME"]) / ".config" / "gh"
        default.mkdir(parents=True)
        self.environment["GH_CONFIG_DIR"] = str(custom)

        for client in ("opencode", "copilot"):
            with self.subTest(client=client):
                launch = self._launch(self._config(client=client))
                command = list(launch.command)
                denied = {
                    command[index + 1]
                    for index, value in enumerate(command)
                    if value == "--deny-path"
                }
                passed = {
                    command[index + 1]
                    for index, value in enumerate(command)
                    if value == "--pass-env"
                }

                self.assertEqual(
                    str(custom.resolve(strict=True)),
                    launch.environment["GH_CONFIG_DIR"],
                )
                self.assertTrue(
                    {
                        str(custom.resolve(strict=True)),
                        str(xdg.resolve(strict=True)),
                        str(default.resolve(strict=True)),
                    }.issubset(denied)
                )
                self.assertNotIn("GH_CONFIG_DIR", passed)

    def test_github_access_requires_explicit_environment_capability_for_each_client(self) -> None:
        without_token = {**self.environment}
        without_token.pop("GH_TOKEN")
        for client, binary in (("opencode", self.opencode), ("copilot", self.copilot)):
            with self.subTest(client=client), self.assertRaisesRegex(
                LOCAL.LocalModeError, "GH_TOKEN"
            ):
                LOCAL.build_local_launch(
                    self._config(client=client),
                    distribution_root=self.distribution,
                    project_dir=self.project,
                    cplt=self.cplt,
                    client=binary,
                    environment=without_token,
                    github_access=True,
                    platform="darwin",
                )

            launch = LOCAL.build_local_launch(
                self._config(client=client),
                distribution_root=self.distribution,
                project_dir=self.project,
                cplt=self.cplt,
                client=binary,
                environment=self.environment,
                github_access=True,
                platform="darwin",
            )

            self.assertEqual("must-not-cross", launch.environment["GH_TOKEN"])
            self.assertEqual("<redacted>", launch.redacted_environment["GH_TOKEN"])
            self.assertIn("GH_TOKEN", launch.secret_environment)
            self.assertIn("GH_TOKEN", launch.command)
            self.assertNotIn("must-not-cross", repr(launch))
            if client == "copilot":
                command = list(launch.command)
                passed = {
                    command[index + 1]
                    for index, value in enumerate(command)
                    if value == "--pass-env"
                }
                child = command[command.index("--") + 1 :]
                self.assertIn("GH_TOKEN", passed)
                self.assertIn(
                    "--secret-env-vars=COPILOT_PROVIDER_API_KEY", child
                )
                self.assertNotIn(
                    "--secret-env-vars=COPILOT_PROVIDER_API_KEY,GH_TOKEN", child
                )

    def test_opencode_rejects_provider_credentials_before_state_is_created(self) -> None:
        for config in (
            self._config(api_key_env="LOCAL_MODEL_TOKEN"),
            self._config(api_key_file=self.root / "key"),
        ):
            with self.subTest(config=config), self.assertRaisesRegex(
                LOCAL.LocalModeError, "tool subprocesses inherit provider environment"
            ):
                LOCAL.validate_config(config, check_key_file=False)
        self.assertFalse((self.root / "state").exists())

    def test_open_code_full_projection_and_subcommand_classification(self) -> None:
        config = self._config(context="full", agent="grillmester")
        full = self._launch(config)
        command = list(full.command)
        self.assertEqual(
            (self.distribution / "targets/opencode-v1").resolve(strict=True), full.payload
        )
        self.assertEqual(
            ["--agent", "grillmester", "--model", "llamacpp/qwen3.8-local"],
            command[command.index("--") + 1 :],
        )

        run = self._launch(arguments=("run", "fix the test"))
        command = list(run.command)
        self.assertEqual(
            [
                "run",
                "--agent",
                "barista",
                "--model",
                "llamacpp/qwen3.8-local",
                "fix the test",
            ],
            command[command.index("--") + 1 :],
        )

        for arguments in (("--help",), ("-v",)):
            with self.subTest(arguments=arguments):
                meta = self._launch(arguments=arguments)
                self.assertEqual(
                    list(arguments), list(meta.command[meta.command.index("--") + 1 :])
                )

        for arguments in (("models", "llamacpp"), ("subdir",), ("plugin", "list")):
            with self.subTest(arguments=arguments), self.assertRaisesRegex(
                LOCAL.LocalModeError, "accepts the TUI, 'run'"
            ):
                self._launch(arguments=arguments)

    def test_copilot_launch_binds_local_inference_and_keeps_tools_connected(self) -> None:
        self.environment["LOCAL_MODEL_TOKEN"] = "private-token"
        config = self._config(
            client="copilot", api_key_env="LOCAL_MODEL_TOKEN"
        )
        launch = self._launch(config, arguments=("-p", "fix the test"))
        command = list(launch.command)
        client = command[command.index("--") + 1 :]
        self.assertEqual(
            (self.distribution / "targets/copilot-cli-focused-v1").resolve(strict=True),
            launch.payload,
        )
        self.assertIn("--plugin-dir", client)
        self.assertIn("grillmester:barista", client)
        self.assertIn("--no-auto-update", client)
        self.assertIn("--no-experimental", client)
        self.assertIn("--no-remote", client)
        self.assertIn("--no-remote-export", client)
        self.assertIn("--disable-builtin-mcps", client)
        self.assertIn("--secret-env-vars=COPILOT_PROVIDER_API_KEY", client)
        self.assertNotIn("COPILOT_OFFLINE", launch.environment)
        self.assertEqual("false", launch.environment["COPILOT_AUTO_UPDATE"])
        self.assertEqual("false", launch.environment["COPILOT_OTEL_ENABLED"])
        self.assertEqual("private-token", launch.environment["COPILOT_PROVIDER_API_KEY"])
        self.assertEqual("<redacted>", launch.redacted_environment["COPILOT_PROVIDER_API_KEY"])
        settings = json.loads((launch.runtime.copilot_home / "settings.json").read_text())
        self.assertIs(settings["disableAllHooks"], True)
        self.assertEqual(
            list(LOCAL.COPILOT_DISABLED_BUILTIN_SKILLS), settings["disabledSkills"]
        )
        self.assertIs(settings["autoUpdate"], False)
        self.assertIs(settings["memory"], False)
        self.assertIs(settings["experimental"], False)
        self.assertEqual({"autoConnect": False}, settings["ide"])
        self.assertNotIn("customAgents", settings)
        self.assertEqual(
            set(LOCAL.COPILOT_INHERIT_AGENTS),
            set(settings["subagents"]["agents"]),
        )
        self.assertTrue(
            all(
                item == {"model": "inherit"}
                for item in settings["subagents"]["agents"].values()
            )
        )

    def test_copilot_without_auth_uses_only_redacted_local_placeholder(self) -> None:
        launch = self._launch(self._config(client="copilot"))
        self.assertEqual("local", launch.environment["COPILOT_PROVIDER_API_KEY"])
        self.assertEqual("<redacted>", launch.redacted_environment["COPILOT_PROVIDER_API_KEY"])
        self.assertNotIn("'COPILOT_PROVIDER_API_KEY': 'local'", repr(launch))

    def test_project_opencode_config_and_extension_surfaces_fail_closed(self) -> None:
        candidates = (
            self.project / "opencode.json",
            self.project / "opencode.jsonc",
            self.project / ".opencode" / "plugins" / "evil.js",
            self.project / ".opencode" / "mcp.json",
            self.project / ".opencode" / "skills" / "evil" / "SKILL.md",
            self.project / ".claude" / "skills" / "evil" / "SKILL.md",
            self.project / ".agents" / "skills" / "evil" / "SKILL.md",
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.write_text("{}", encoding="utf-8")
                with self.assertRaisesRegex(
                    LOCAL.LocalModeError, "auto-discovered project OpenCode"
                ):
                    self._launch()
                if (self.project / ".opencode").exists():
                    import shutil

                    shutil.rmtree(self.project / ".opencode")
                import shutil

                for root in (self.project / ".claude", self.project / ".agents"):
                    if root.exists():
                        shutil.rmtree(root)
                for name in ("opencode.json", "opencode.jsonc"):
                    try:
                        (self.project / name).unlink()
                    except FileNotFoundError:
                        pass

    def test_opencode_alternate_project_cannot_bypass_extension_scan(self) -> None:
        alternate = self.project / "subdir"
        plugin = alternate / ".opencode/plugins/evil.js"
        plugin.parent.mkdir(parents=True)
        plugin.write_text("throw new Error('executed')", encoding="utf-8")

        with self.assertRaisesRegex(LOCAL.LocalModeError, "accepts the TUI, 'run'"):
            self._launch(arguments=("subdir",))

    def test_project_copilot_hook_and_settings_surfaces_fail_closed(self) -> None:
        candidates = (
            self.project / ".mcp.json",
            self.project / ".github/mcp.json",
            self.project / ".github/lsp.json",
            self.project / ".github/extensions/evil/extension.mjs",
            self.project / ".github/hooks/session.json",
            self.project / ".github/agents/barista.agent.md",
            self.project / ".claude/agents/barista.md",
            self.project / ".github/skills/grillmester-tdd/SKILL.md",
            self.project / ".agents/skills/grillmester-tdd/SKILL.md",
            self.project / ".claude/skills/grillmester-tdd/SKILL.md",
            self.project / ".github/copilot/settings.json",
            self.project / ".github/copilot/settings.local.json",
            self.project / ".claude/settings.json",
            self.project / ".claude/settings.local.json",
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.write_text("{}", encoding="utf-8")
                with self.assertRaisesRegex(
                    LOCAL.LocalModeError, "auto-discovered project Copilot"
                ):
                    self._launch(self._config(client="copilot"))
                import shutil

                for root in (
                    self.project / ".github",
                    self.project / ".claude",
                    self.project / ".agents",
                ):
                    if root.exists():
                        shutil.rmtree(root)

    def test_nested_copilot_project_cannot_bypass_repository_hook_scan(self) -> None:
        subprocess.run(("git", "init", "-q"), cwd=self.project, check=True)
        nested = self.project / "nested/project"
        nested.mkdir(parents=True)
        hook = self.project / ".github/hooks/session.json"
        hook.parent.mkdir(parents=True)
        hook.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(
            LOCAL.LocalModeError, "auto-discovered project Copilot hook"
        ):
            LOCAL.build_local_launch(
                self._config(client="copilot"),
                distribution_root=self.distribution,
                project_dir=nested,
                cplt=self.cplt,
                client=self.copilot,
                environment=self.environment,
                platform="darwin",
            )

    def test_nested_copilot_project_cannot_bypass_repository_mcp_scan(self) -> None:
        subprocess.run(("git", "init", "-q"), cwd=self.project, check=True)
        nested = self.project / "nested/project"
        nested.mkdir(parents=True)
        mcp = self.project / ".github/mcp.json"
        mcp.parent.mkdir(parents=True)
        mcp.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(
            LOCAL.LocalModeError, "auto-discovered project Copilot executable config"
        ):
            LOCAL.build_local_launch(
                self._config(client="copilot"),
                distribution_root=self.distribution,
                project_dir=nested,
                cplt=self.cplt,
                client=self.copilot,
                environment=self.environment,
                platform="darwin",
            )

    def test_cplt_post_session_audit_is_disabled_for_untrusted_repository_config(self) -> None:
        marker = self.root / "fsmonitor-executed"
        subprocess.run(("git", "init", "-q"), cwd=self.project, check=True)
        subprocess.run(
            ("git", "config", "core.fsmonitor", f"touch {marker}"),
            cwd=self.project,
            check=True,
        )
        launch = self._launch()
        separator = launch.command.index("--")
        self.assertIn("--no-audit", launch.command[:separator])
        self.assertFalse(marker.exists())

    def test_print_shape_does_not_read_api_key_environment_or_file(self) -> None:
        missing_file = self.root / "does-not-exist.key"
        for config in (
            self._config(client="copilot", api_key_env="MISSING_LOCAL_KEY"),
            self._config(client="copilot", api_key_file=missing_file),
        ):
            client = self.copilot
            with self.subTest(config=config), mock.patch.object(
                LOCAL, "_read_secret", side_effect=AssertionError("credential read")
            ) as read_secret:
                launch = LOCAL.build_local_launch(
                    config,
                    distribution_root=self.distribution,
                    project_dir=self.project,
                    cplt=self.cplt,
                    client=client,
                    environment=self.environment,
                    resolve_credentials=False,
                    prepare_state=False,
                    platform="darwin",
                )
            read_secret.assert_not_called()
            self.assertIn("--pass-env", launch.command)
            self.assertFalse((self.root / "state").exists())

    def test_opencode_print_shape_redacts_explicit_github_credential(self) -> None:
        launch = LOCAL.build_local_launch(
            self._config(),
            distribution_root=self.distribution,
            project_dir=self.project,
            cplt=self.cplt,
            client=self.opencode,
            environment=self.environment,
            github_access=True,
            resolve_credentials=False,
            prepare_state=False,
            platform="darwin",
        )

        self.assertEqual("<redacted>", launch.environment["GH_TOKEN"])
        self.assertIn("GH_TOKEN", launch.secret_environment)

    def test_reserved_client_arguments_cannot_override_local_binding(self) -> None:
        for client, option in (
            ("opencode", "--model=cloud/model"),
            ("opencode", "--agent"),
            ("opencode", "--auto"),
            ("opencode", "--yolo"),
            ("opencode", "--yolo=true"),
            ("opencode", "--dangerously-skip-permissions"),
            ("opencode", "--dangerously-skip-permissions=true"),
            ("opencode", "--share"),
            ("opencode", "--attach=http://example.com"),
            ("opencode", "-mcloud/model"),
            ("opencode", "-vmcloud/model"),
            ("opencode", "-cimcloud/model"),
            ("opencode", "-c"),
            ("opencode", "-sresume"),
            ("opencode", "-psecret"),
            ("opencode", "-uuser"),
            ("copilot", "--remote"),
            ("copilot", "--acp"),
            ("copilot", "-C/tmp/elsewhere"),
            ("copilot", "-sC/tmp/elsewhere"),
            ("copilot", "-smcloud/model"),
            ("copilot", "-rprevious-session"),
            ("copilot", "-srprevious-session"),
            ("copilot", "--plugin-dir=/tmp/evil"),
            ("copilot", "--config-dir"),
            ("copilot", "--config-dir=/tmp/evil"),
            ("copilot", "--continue"),
            ("copilot", "--resume=previous-session"),
            ("copilot", "--session-id=00000000-0000-0000-0000-000000000000"),
            ("copilot", "--log-dir=/tmp/evil"),
            ("copilot", "--share=conversation.md"),
            ("copilot", "--enable-memory"),
            ("copilot", "--server"),
            ("copilot", "--headless"),
            ("copilot", "--embedded-host"),
            ("copilot", "--mode=autopilot"),
            ("copilot", "--max-autopilot-continues=99"),
            ("copilot", "--enable-builtin-mcps"),
            ("copilot", "--experimental"),
            ("copilot", "--no-experimental"),
            ("copilot", "--secret-env-vars=TOKEN"),
            ("copilot", "--allow-all"),
            ("copilot", "--additional-mcp-config={}"),
            ("copilot", "--share-gist"),
            ("copilot", "--yolo"),
        ):
            with self.subTest(client=client, option=option), self.assertRaisesRegex(
                LOCAL.LocalModeError, "owned by local mode"
            ):
                self._launch(self._config(client=client), arguments=(option,))

    def test_copilot_admin_commands_are_rejected_after_global_options(self) -> None:
        for arguments in (
            ("login",),
            ("mcp", "list"),
            ("plugin", "install", "evil"),
            ("plugins",),
            ("skill", "list"),
            ("update",),
            ("init",),
            ("--no-color", "plugin", "list"),
        ):
            with self.subTest(arguments=arguments), self.assertRaisesRegex(
                LOCAL.LocalModeError, "command-mode positional"
            ):
                self._launch(self._config(client="copilot"), arguments=arguments)

    def test_opencode_hidden_auto_aliases_are_rejected_in_tui_and_run(self) -> None:
        for arguments in (
            ("--yolo",),
            ("--dangerously-skip-permissions=true",),
            ("run", "--yolo=true", "review"),
            ("run", "--dangerously-skip-permissions", "review"),
        ):
            with self.subTest(arguments=arguments), self.assertRaisesRegex(
                LOCAL.LocalModeError, "owned by local mode"
            ):
                self._launch(arguments=arguments)

    def test_opencode_unknown_long_options_fail_closed(self) -> None:
        for arguments in (("--future-mode",), ("run", "--future-mode=true", "review")):
            with self.subTest(arguments=arguments), self.assertRaisesRegex(
                LOCAL.LocalModeError, "not supported by local mode"
            ):
                self._launch(arguments=arguments)

    def test_opencode_positionals_cannot_bypass_local_command_gate(self) -> None:
        for arguments in (
            ("--print-logs", "serve"),
            ("--print-logs", "upgrade"),
            ("--mini", "../outside"),
            ("--",),
            ("--", "serve"),
            ("--replay-limit", "10", "acp"),
        ):
            with self.subTest(arguments=arguments), self.assertRaisesRegex(
                LOCAL.LocalModeError, "accepts the TUI, 'run'"
            ):
                self._launch(arguments=arguments)

    def test_opencode_short_value_options_do_not_leave_positional_residue(
        self,
    ) -> None:
        for arguments in (
            ("-f", "notes.txt"),
            ("-if", "notes.txt"),
            ("-fnotes.txt",),
        ):
            with self.subTest(arguments=arguments):
                launch = self._launch(arguments=arguments)
                self.assertTrue(set(arguments).issubset(set(launch.command)))

    def test_opencode_reviewed_tui_and_run_options_remain_available(self) -> None:
        for arguments in (
            ("--mini", "--no-replay", "--replay-limit", "10"),
            (
                "run",
                "--format",
                "json",
                "--title=local-review",
                "--variant",
                "high",
                "--thinking",
                "-i",
                "-f",
                "fixture.txt",
                "review",
            ),
        ):
            with self.subTest(arguments=arguments):
                launch = self._launch(arguments=arguments)
                self.assertTrue(set(arguments).issubset(set(launch.command)))

    def test_copilot_prompt_values_and_safe_metadata_are_not_command_mode(self) -> None:
        for arguments in (
            ("-p", "plugin"),
            ("-sp", "update"),
            ("--prompt", "login"),
            ("--interactive", "plugin"),
            ("--name", "mcp", "-p", "hello"),
            ("help",),
            ("version",),
        ):
            with self.subTest(arguments=arguments):
                launch = self._launch(
                    self._config(client="copilot"), arguments=arguments
                )
                self.assertTrue(set(arguments).issubset(set(launch.command)))

    def test_copilot_unknown_and_hidden_long_modes_fail_closed(self) -> None:
        for option in (
            "--ui-server",
            "--managed-server",
            "--stdio",
            "--host=0.0.0.0",
            "--port=12345",
            "--auth-token-env=TOKEN",
            "--session-idle-timeout=60",
            "--cloud",
            "--worktree=branch",
            "--prefer-version=9.9.9",
            "--relay",
            "--environment-id=remote",
            "--save-trajectory-output=trace.json",
            "--log-interactive-shells",
            "--collect-debug-logs",
            "--collect-debug-logs-output=debug.zip",
            "--dynamic-retrieval",
            "--sandbox",
            "--no-sandbox",
        ):
            with self.subTest(option=option), self.assertRaisesRegex(
                LOCAL.LocalModeError, "not supported by local mode"
            ):
                self._launch(self._config(client="copilot"), arguments=(option,))

    def test_copilot_reviewed_restrictive_and_ui_options_remain_available(self) -> None:
        arguments = (
            "--attachment",
            "fixture.png",
            "--context=default",
            "--disable-mcp-server",
            "unused",
            "--available-tools=read",
            "--excluded-tools=write",
            "--deny-tool=shell",
            "--deny-url=example.com",
            "--no-custom-instructions",
            "--screen-reader",
            "--log-level",
            "warning",
            "--output-format",
            "json",
            "--stream",
            "on",
            "-p",
            "review",
        )
        launch = self._launch(
            self._config(client="copilot"), arguments=arguments
        )
        self.assertTrue(set(arguments).issubset(set(launch.command)))

    def test_value_taking_short_options_do_not_parse_their_values_as_clusters(self) -> None:
        for client, arguments in (
            ("opencode", ("run", "-fVALUE-with-m-and-C", "hello")),
            ("copilot", ("-pVALUE-with-m-and-C",)),
            ("copilot", ("-iVALUE-with-m-and-C",)),
        ):
            with self.subTest(client=client, arguments=arguments):
                launch = self._launch(self._config(client=client), arguments=arguments)
                self.assertTrue(set(arguments).issubset(set(launch.command)))

    def test_unknown_short_option_clusters_fail_closed(self) -> None:
        for client, option in (
            ("opencode", "-x"),
            ("opencode", "-vx"),
            ("copilot", "-x"),
            ("copilot", "-sx"),
        ):
            with self.subTest(client=client, option=option), self.assertRaisesRegex(
                LOCAL.LocalModeError, "unknown short option"
            ):
                self._launch(self._config(client=client), arguments=(option,))

    def test_copilot_worktree_short_option_is_owned_by_local_mode(self) -> None:
        for option in ("-w", "-wfeature", "-sw", "-swfeature"):
            with self.subTest(option=option), self.assertRaisesRegex(
                LOCAL.LocalModeError, "option -w is owned"
            ):
                self._launch(self._config(client="copilot"), arguments=(option,))

    def test_value_taking_short_options_require_a_value(self) -> None:
        for client, option in (
            ("opencode", "-f"),
            ("opencode", "-vf"),
            ("copilot", "-p"),
            ("copilot", "-sp"),
        ):
            with self.subTest(client=client, option=option), self.assertRaisesRegex(
                LOCAL.LocalModeError, "needs a value"
            ):
                self._launch(self._config(client=client), arguments=(option,))

    def test_manifested_payload_tampering_fails_closed(self) -> None:
        payload = self.distribution / "targets/opencode-v1-focused"
        injected = payload / "agents/barista.md"
        injected.parent.mkdir()
        injected.write_text("tampered", encoding="utf-8")
        manifest = json.loads((payload / "manifest.json").read_text(encoding="utf-8"))
        manifest["files"] = {
            "agents/barista.md": {"sha256": "0" * 64, "mode": "0644"}
        }
        (payload / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(LOCAL.LocalModeError, "digest mismatch"):
            self._launch()

    def test_copilot_preserves_host_home_but_denies_raw_gh_state(self) -> None:
        account_home = Path(self.environment["HOME"])
        sensitive = (
            account_home / ".copilot",
            account_home / ".agents",
            account_home / ".claude",
        )
        for path in sensitive:
            path.mkdir(parents=True)
        expected_gh_config = Path(self.environment["XDG_CONFIG_HOME"]) / "gh"
        expected_gh_config.mkdir(parents=True)
        launch = self._launch(self._config(client="copilot"))
        command = list(launch.command)
        self.assertEqual("copilot", command[command.index("--allow-cache-exec") + 1])
        denied = {
            command[index + 1]
            for index, value in enumerate(command)
            if value == "--deny-path"
        }
        self.assertEqual(
            {str(path.resolve(strict=True)) for path in sensitive}
            | {str(expected_gh_config.resolve(strict=False))},
            denied,
        )
        self.assertEqual(str(account_home), launch.environment["HOME"])
        self.assertEqual(
            str(expected_gh_config.resolve(strict=False)),
            launch.environment["GH_CONFIG_DIR"],
        )
        command = list(launch.command)
        passed = {
            command[index + 1]
            for index, value in enumerate(command)
            if value == "--pass-env"
        }
        self.assertNotIn("GH_CONFIG_DIR", passed)
        self.assertNotIn(str(account_home / "Library" / "Keychains"), denied)
        self.assertEqual(
            str(launch.runtime.copilot_home), launch.environment["COPILOT_HOME"]
        )

    def test_copilot_denies_external_key_file_and_rejects_project_key_or_alias(self) -> None:
        key = self.root / "provider.key"
        key.write_text("private-token\n", encoding="utf-8")
        key.chmod(0o600)
        launch = self._launch(
            self._config(client="copilot", api_key_file=key)
        )
        command = list(launch.command)
        denied = {
            command[index + 1]
            for index, value in enumerate(command)
            if value == "--deny-path"
        }
        self.assertIn(str(key.resolve(strict=True)), denied)

        project_key = self.project / "provider.key"
        project_key.write_text("private-token\n", encoding="utf-8")
        project_key.chmod(0o600)
        with self.assertRaisesRegex(LOCAL.LocalModeError, "outside the consumer project"):
            self._launch(
                self._config(client="copilot", api_key_file=project_key)
            )

        project_key.unlink()
        os.link(key, self.project / "provider-key-alias")
        with self.assertRaisesRegex(LOCAL.LocalModeError, "hard links"):
            self._launch(
                self._config(client="copilot", api_key_file=key)
            )

    def test_execute_probes_before_calling_injected_exec(self) -> None:
        calls: list[tuple[str, tuple[str, ...], dict[str, str]]] = []

        def execute(
            executable: str, command: object, environment: Mapping[str, str]
        ) -> int:
            calls.append((executable, tuple(command), dict(environment)))  # type: ignore[arg-type]
            return 73

        with ProbeServer() as server:
            result = LOCAL.execute_local(
                self._config(base_url=server.base_url),
                distribution_root=self.distribution,
                project_dir=self.project,
                cplt=self.cplt,
                client=self.opencode,
                environment=self.environment,
                exec_callback=execute,
                platform="darwin",
            )
        self.assertEqual(73, result)
        self.assertEqual(1, len(calls))
        executable = Path(calls[0][0])
        self.assertEqual("cplt", executable.name)
        self.assertEqual(self.cplt.resolve(strict=True), executable.resolve(strict=True))
        self.assertEqual("qwen3.8-local", ProbeHandler.models[0])

    def test_execute_binds_one_secret_value_to_probe_and_launch(self) -> None:
        calls: list[dict[str, str]] = []

        def execute(
            _executable: str, _command: object, environment: Mapping[str, str]
        ) -> int:
            calls.append(dict(environment))
            return 0

        with ProbeServer() as server, mock.patch.object(
            LOCAL, "_read_secret", return_value="one-reviewed-secret"
        ) as read_secret:
            result = LOCAL.execute_local(
                self._config(
                    client="copilot",
                    base_url=server.base_url,
                    api_key_env="LOCAL_MODEL_TOKEN",
                ),
                distribution_root=self.distribution,
                project_dir=self.project,
                cplt=self.cplt,
                client=self.copilot,
                environment={**self.environment, "LOCAL_MODEL_TOKEN": "ambient-secret"},
                exec_callback=execute,
                platform="darwin",
            )

        self.assertEqual(0, result)
        read_secret.assert_called_once()
        self.assertEqual(
            "one-reviewed-secret", calls[0]["COPILOT_PROVIDER_API_KEY"]
        )

    def test_execute_validates_config_before_reading_a_secret(self) -> None:
        with mock.patch.object(
            LOCAL, "_read_secret", side_effect=AssertionError("credential read")
        ) as read_secret, self.assertRaisesRegex(
            LOCAL.LocalModeError, "not supported with OpenCode"
        ):
            LOCAL.execute_local(
                self._config(client="opencode", api_key_env="LOCAL_MODEL_TOKEN"),
                distribution_root=self.distribution,
                project_dir=self.project,
                cplt=self.cplt,
                client=self.opencode,
                environment={**self.environment, "LOCAL_MODEL_TOKEN": "secret"},
                exec_callback=lambda *_arguments: 0,
                platform="darwin",
            )

        read_secret.assert_not_called()

    def test_local_launch_fails_closed_off_macos(self) -> None:
        with self.assertRaisesRegex(LOCAL.LocalModeError, "only on macOS"):
            LOCAL.build_local_launch(
                self._config(),
                distribution_root=self.distribution,
                project_dir=self.project,
                cplt=self.cplt,
                client=self.opencode,
                environment=self.environment,
                platform="linux",
            )

    def test_missing_key_fails_before_launch_is_built(self) -> None:
        with self.assertRaisesRegex(LOCAL.LocalModeError, "is not set"):
            self._launch(
                self._config(client="copilot", api_key_env="MISSING_LOCAL_KEY")
            )
        self.assertFalse((self.root / "state").exists() and any((self.root / "state").rglob("settings.json")))

    def test_setup_and_status_cli_never_print_a_secret(self) -> None:
        environment = {
            **self.environment,
            "PATH": str(self.bin),
            "LOCAL_MODEL_TOKEN": "never-print-this-value",
        }
        stdout = io.StringIO()
        with ProbeServer() as server, mock.patch.dict(
            os.environ, environment, clear=True
        ), redirect_stdout(stdout):
            self.assertEqual(
                0,
                LOCAL.main(
                    [
                        "setup",
                        "--client",
                        "copilot",
                        "--provider-id",
                        "llamacpp",
                        "--base-url",
                        server.base_url,
                        "--model-id",
                        "qwen3.8-local",
                        "--api-key-env",
                        "LOCAL_MODEL_TOKEN",
                    ]
                ),
            )
            self.assertEqual(0, LOCAL.main(["status"]))
        self.assertIn("environment LOCAL_MODEL_TOKEN", stdout.getvalue())
        self.assertNotIn("never-print-this-value", stdout.getvalue())

    def test_bare_setup_detects_one_client_and_one_local_model(self) -> None:
        only_bin = self.root / "only-opencode"
        only_bin.mkdir()
        binary = only_bin / "opencode"
        binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        binary.chmod(0o700)
        environment = {**self.environment, "PATH": str(only_bin)}

        with ProbeServer() as server, redirect_stdout(io.StringIO()):
            result = LOCAL.main(
                ["setup", "--base-url", server.base_url],
                environment=environment,
            )

        self.assertEqual(0, result)
        config = LOCAL.load_config(environment=environment)
        self.assertEqual("opencode", config.client)
        self.assertEqual("local", config.provider_id)
        self.assertEqual("qwen3.8-local", config.model_id)
        self.assertEqual("focused", config.context)
        self.assertEqual("barista", config.agent)

    def test_explicit_setup_requires_present_client_and_advertised_model(self) -> None:
        opencode_only = self.root / "explicit-opencode"
        opencode_only.mkdir()
        binary = opencode_only / "opencode"
        binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        binary.chmod(0o700)
        environment = {**self.environment, "PATH": str(opencode_only)}

        missing_stderr = io.StringIO()
        with redirect_stderr(missing_stderr):
            missing = LOCAL.main(
                [
                    "setup",
                    "--client",
                    "copilot",
                    "--base-url",
                    "http://127.0.0.1:1/v1",
                    "--model-id",
                    "ghost-model",
                ],
                environment=environment,
            )
        self.assertEqual(2, missing)
        self.assertIn("copilot was not found on PATH", missing_stderr.getvalue())
        self.assertFalse(LOCAL.config_path(environment).exists())

        wrong_model_stderr = io.StringIO()
        with ProbeServer() as server, redirect_stderr(wrong_model_stderr):
            wrong_model = LOCAL.main(
                [
                    "setup",
                    "--client",
                    "opencode",
                    "--base-url",
                    server.base_url,
                    "--model-id",
                    "ghost-model",
                ],
                environment=environment,
            )
        self.assertEqual(2, wrong_model)
        self.assertIn("does not advertise exact modelId", wrong_model_stderr.getvalue())
        self.assertFalse(LOCAL.config_path(environment).exists())

    def test_explicit_setup_with_model_still_requires_reachable_endpoint(self) -> None:
        environment = {**self.environment, "PATH": str(self.bin)}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = LOCAL.main(
                [
                    "setup",
                    "--client",
                    "opencode",
                    "--base-url",
                    "http://127.0.0.1:1/v1",
                    "--model-id",
                    "ghost-model",
                ],
                environment=environment,
            )
        self.assertEqual(2, result)
        self.assertIn("could not reach local model endpoint", stderr.getvalue())
        self.assertFalse(LOCAL.config_path(environment).exists())

    def test_setup_requires_explicit_client_when_both_are_installed_noninteractively(self) -> None:
        environment = {**self.environment, "PATH": str(self.bin)}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = LOCAL.main(
                ["setup", "--base-url", "http://127.0.0.1:1/v1"],
                environment=environment,
            )

        self.assertEqual(2, result)
        self.assertIn("multiple client choices", stderr.getvalue())
        self.assertFalse(LOCAL.config_path(environment).exists())

    @mock.patch.object(LOCAL.sys, "platform", "darwin")
    def test_embedded_main_accepts_checked_binaries_and_full_one_shot(self) -> None:
        LOCAL.save_config(self._config(), environment=self.environment)
        resolutions: list[str] = []

        def resolve(client: str, checked: bool) -> tuple[object, object]:
            resolutions.append(f"{client}:{checked}")
            return (
                SimpleNamespace(path=str(self.cplt), version="reviewed"),
                SimpleNamespace(
                    path=str(self.opencode if client == "opencode" else self.copilot),
                    version="reviewed",
                ),
            )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = LOCAL.main(
                [
                    "launch",
                    "--project-dir",
                    str(self.project),
                    "--full",
                    "--client",
                    "copilot",
                    "--agent",
                    "designer",
                    "--print-command",
                ],
                distribution_root=self.distribution,
                binary_resolver=resolve,
                environment=self.environment,
            )
        self.assertEqual(0, result)
        self.assertEqual(["copilot:False"], resolutions)
        self.assertIn(str((self.distribution / "plugin").resolve()), stdout.getvalue())
        self.assertIn("grillmester:designer", stdout.getvalue())
        self.assertFalse((self.root / "state").exists())
        persisted = LOCAL.load_config(environment=self.environment)
        self.assertEqual("focused", persisted.context)
        self.assertEqual("opencode", persisted.client)
        self.assertEqual("barista", persisted.agent)

    @mock.patch.object(LOCAL.sys, "platform", "darwin")
    def test_doctor_reports_the_exact_checked_runtime_and_selection(self) -> None:
        with ProbeServer() as server:
            LOCAL.save_config(
                self._config(base_url=server.base_url), environment=self.environment
            )

            def resolve(client: str, checked: bool) -> tuple[object, object]:
                self.assertEqual("opencode", client)
                self.assertTrue(checked)
                return (
                    SimpleNamespace(path=str(self.cplt), version="cplt reviewed"),
                    SimpleNamespace(path=str(self.opencode), version="1.18.20"),
                )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = LOCAL.main(
                    ["doctor", "--project-dir", str(self.project)],
                    distribution_root=self.distribution,
                    binary_resolver=resolve,
                    environment=self.environment,
                )

        self.assertEqual(0, result)
        output = stdout.getvalue()
        self.assertIn(f"ok  cplt {self.cplt.resolve()} (cplt reviewed)", output)
        self.assertIn(
            f"ok  client opencode {self.opencode.resolve()} (1.18.20)", output
        )
        self.assertIn(f"ok  project {self.project.resolve()}", output)
        self.assertIn("ok  agent barista", output)
        self.assertIn("ok  context focused", output)
        self.assertIn(f"ok  endpoint {server.base_url}", output)
        self.assertIn("ok  model qwen3.8-local", output)
        self.assertIn("targets/opencode-v1-focused", output)
        self.assertFalse((self.root / "state").exists())

    @mock.patch.object(LOCAL.sys, "platform", "darwin")
    def test_remainder_print_token_cannot_disable_checked_binary_resolution(self) -> None:
        with ProbeServer() as server:
            LOCAL.save_config(
                self._config(base_url=server.base_url), environment=self.environment
            )
            resolutions: list[tuple[str, bool]] = []
            executions: list[tuple[str, ...]] = []

            def resolve(client: str, checked: bool) -> tuple[object, object]:
                resolutions.append((client, checked))
                return (
                    SimpleNamespace(path=str(self.cplt), version="reviewed"),
                    SimpleNamespace(path=str(self.opencode), version="reviewed"),
                )

            def execute(
                _executable: str,
                command: Sequence[str],
                _environment: Mapping[str, str],
            ) -> int:
                executions.append(tuple(command))
                return 0

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                result = LOCAL.main(
                    [
                        "launch",
                        "--project-dir",
                        str(self.project),
                        "--client",
                        "opencode",
                        "run",
                        "--print-command",
                    ],
                    distribution_root=self.distribution,
                    binary_resolver=resolve,
                    environment=self.environment,
                    exec_callback=execute,
                )

        self.assertEqual(2, result)
        self.assertIn("not supported by local mode", stderr.getvalue())
        self.assertEqual([("opencode", True)], resolutions)
        self.assertEqual([], executions)

    def test_missing_local_config_points_directly_to_setup(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = LOCAL.main(["status"], environment=self.environment)

        self.assertEqual(2, result)
        self.assertIn("grillmester local setup", stderr.getvalue())

    def test_internal_module_cannot_bypass_parent_binary_verification(self) -> None:
        LOCAL.save_config(self._config(), environment=self.environment)
        for command in ("doctor", "launch"):
            with self.subTest(command=command):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    result = LOCAL.main(
                        [command, "--project-dir", str(self.project)],
                        distribution_root=self.distribution,
                        environment={**self.environment, "PATH": str(self.bin)},
                    )
                self.assertEqual(2, result)
                self.assertIn("top-level 'grillmester local'", stderr.getvalue())

    def test_cli_reports_invalid_focused_agent_without_traceback(self) -> None:
        stderr = io.StringIO()
        environment = {**self.environment, "PATH": str(self.bin)}
        with mock.patch.dict(os.environ, environment, clear=True), redirect_stderr(stderr):
            result = LOCAL.main(
                [
                    "setup",
                    "--client",
                    "copilot",
                    "--agent",
                    "designer",
                    "--context",
                    "focused",
                    "--provider-id",
                    "llamacpp",
                    "--base-url",
                    "http://127.0.0.1:8080/v1",
                    "--model-id",
                    "qwen3.8-local",
                ]
            )
        self.assertEqual(2, result)
        self.assertIn("only the barista", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
