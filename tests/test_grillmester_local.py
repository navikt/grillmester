from __future__ import annotations

import hashlib
import http.client
import importlib.util
import io
import json
import os
import shlex
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
        plugin_manifest = json.dumps({"name": "grillmester"}).encode("utf-8")
        plugin_path = self.distribution / "plugin/plugin.json"
        plugin_path.write_bytes(plugin_manifest)
        plugin_path.chmod(0o644)
        (self.distribution / "plugin/manifest.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "target": "copilot-full-v1",
                    "files": {
                        "plugin.json": {
                            "sha256": hashlib.sha256(plugin_manifest).hexdigest(),
                            "mode": "0644",
                        }
                    },
                }
            ),
            encoding="utf-8",
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
        self.system_tools = {
            name: self._binary(name)
            for name in ("git", "sandbox-exec", "uname", "which")
        }
        trusted_tool_patcher = mock.patch.object(
            LOCAL,
            "_trusted_macos_executable",
            side_effect=lambda name: self.system_tools[name].resolve(strict=True),
        )
        trusted_tool_patcher.start()
        self.addCleanup(trusted_tool_patcher.stop)
        state_path_patcher = mock.patch.object(
            LOCAL, "_ensure_cplt_executable_state_path", return_value=None
        )
        state_path_patcher.start()
        self.addCleanup(state_path_patcher.stop)
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
        npm_access: bool = False,
        npm_token_env: str | None = None,
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
            npm_access=npm_access,
            npm_token_env=npm_token_env,
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

    def test_config_persists_model_context_contract(self) -> None:
        config = self._config(context_window=65_536, max_output_tokens=16_384)

        path = LOCAL.save_config(config, environment=self.environment)
        value = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(2, value["schemaVersion"])
        self.assertEqual(65_536, value["contextWindow"])
        self.assertEqual(16_384, value["maxOutputTokens"])
        self.assertEqual(config, LOCAL.load_config(environment=self.environment))

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

        for invalid_version in (True, 1, 1.0, 3):
            value.pop("credential", None)
            value["schemaVersion"] = invalid_version
            path.write_text(json.dumps(value), encoding="utf-8")
            path.chmod(0o600)
            with self.subTest(version=invalid_version), self.assertRaisesRegex(
                LOCAL.LocalModeError, "unsupported schemaVersion"
            ):
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

    def test_context_contract_must_be_positive_and_fit_the_window(self) -> None:
        for context_window in (True, 0, -1, 16_384):
            with self.subTest(context_window=context_window), self.assertRaisesRegex(
                LOCAL.LocalModeError, "contextWindow"
            ):
                LOCAL.validate_config(self._config(context_window=context_window))
        for max_output_tokens in (True, 0, -1, LOCAL.DEFAULT_CONTEXT_WINDOW):
            with self.subTest(
                max_output_tokens=max_output_tokens
            ), self.assertRaisesRegex(LOCAL.LocalModeError, "maxOutputTokens"):
                LOCAL.validate_config(
                    self._config(max_output_tokens=max_output_tokens)
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

    def test_api_key_requires_visible_ascii_before_http_or_state(self) -> None:
        config = self._config(client="copilot", api_key_env="LOCAL_MODEL_TOKEN")
        for token in ("bad😀key", "bad key", "bad\tkey"):
            with self.subTest(token=token), self.assertRaisesRegex(
                LOCAL.LocalModeError, "visible ASCII"
            ):
                LOCAL._read_secret(
                    config,
                    {**self.environment, "LOCAL_MODEL_TOKEN": token},
                )

    def test_probe_maps_malformed_http_to_a_bounded_local_error(self) -> None:
        malformed = "NOT HTTP secret-looking-response"
        opener = mock.Mock()
        opener.open.side_effect = http.client.BadStatusLine(malformed)

        with mock.patch.object(
            LOCAL.urllib.request, "build_opener", return_value=opener
        ), self.assertRaisesRegex(
            LOCAL.LocalModeError, "invalid HTTP response"
        ) as raised:
            LOCAL.probe_model(self._config(), environment=self.environment)

        self.assertNotIn(malformed, str(raised.exception))

    def test_opencode_launch_uses_cplt_connected_policy_and_focused_payload(self) -> None:
        launch = self._launch()
        command = list(launch.command)
        separator = command.index("--")

        self.assertEqual(str(self.cplt.resolve(strict=True)), command[0])
        self.assertEqual(
            str(launch.runtime.trusted_bin),
            launch.environment["PATH"].split(os.pathsep)[0],
        )
        self.assertEqual(
            self.opencode.resolve(strict=True),
            Path(shutil.which("opencode", path=launch.environment["PATH"])).resolve(strict=True),
        )
        trusted_gh = Path(shutil.which("gh", path=launch.environment["PATH"]))
        self.assertEqual(launch.runtime.trusted_bin / "gh", trusted_gh)
        self.assertNotEqual(0, subprocess.run([trusted_gh], check=False).returncode)
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

    def test_homebrew_opencode_alias_may_resolve_to_opencode_exe(self) -> None:
        cellar = self.root / "Cellar/opencode/1.18.20/libexec"
        cellar.mkdir(parents=True)
        executable = cellar / "opencode.exe"
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o700)
        aliases = self.root / "homebrew-bin"
        aliases.mkdir()
        (aliases / "opencode").symlink_to(executable)
        environment = {
            **self.environment,
            "PATH": os.pathsep.join((str(aliases), str(self.bin))),
        }

        launch = LOCAL.build_local_launch(
            self._config(),
            distribution_root=self.distribution,
            project_dir=self.project,
            cplt=self.cplt,
            client=executable,
            environment=environment,
            platform="darwin",
        )

        self.assertEqual(
            executable.resolve(strict=True),
            (launch.runtime.trusted_bin / "opencode").resolve(strict=True),
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

        self.assertEqual(
            str(policy.resolve(strict=False)), launch.environment["CPLT_CONFIG"]
        )
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
        model = provider["models"]["qwen3.8-local"]
        self.assertEqual(
            {
                "context": LOCAL.DEFAULT_CONTEXT_WINDOW,
                "output": LOCAL.DEFAULT_MAX_OUTPUT_TOKENS,
            },
            model["limit"],
        )
        self.assertEqual({"auto": True}, config_content["compaction"])
        self.assertEqual("{}", launch.environment["OPENCODE_AUTH_CONTENT"])
        self.assertEqual("true", launch.environment["OPENCODE_ENABLE_EXA"])

    def test_both_clients_use_the_saved_context_contract(self) -> None:
        config = self._config(context_window=65_536, max_output_tokens=16_384)
        opencode = self._launch(config)
        opencode_config = json.loads(opencode.environment["OPENCODE_CONFIG_CONTENT"])
        self.assertEqual(
            {"context": 65_536, "output": 16_384},
            opencode_config["provider"]["llamacpp"]["models"]["qwen3.8-local"]["limit"],
        )

        copilot = self._launch(
            self._config(
                client="copilot",
                context_window=65_536,
                max_output_tokens=16_384,
            )
        )
        self.assertEqual(
            "49152", copilot.environment["COPILOT_PROVIDER_MAX_PROMPT_TOKENS"]
        )
        self.assertEqual(
            "16384", copilot.environment["COPILOT_PROVIDER_MAX_OUTPUT_TOKENS"]
        )
        effort = copilot.command.index("--effort")
        self.assertEqual("medium", copilot.command[effort + 1])

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

                private_github_config = launch.runtime.xdg_config / "gh"
                self.assertEqual(
                    str(private_github_config.resolve(strict=True)),
                    launch.environment["GH_CONFIG_DIR"],
                )
                self.assertTrue(private_github_config.is_dir())
                self.assertEqual(0o700, stat.S_IMODE(private_github_config.stat().st_mode))
                self.assertEqual([], list(private_github_config.iterdir()))
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
            command = list(launch.command)
            allowed_reads = {
                command[index + 1]
                for index, value in enumerate(command)
                if value == "--allow-read"
            }
            self.assertIn(str(self.gh.resolve(strict=True)), allowed_reads)
            if client == "copilot":
                passed = {
                    command[index + 1]
                    for index, value in enumerate(command)
                    if value == "--pass-env"
                }
                child = command[command.index("--") + 1 :]
                self.assertIn("GH_TOKEN", passed)
                self.assertIn(
                    "--secret-env-vars=COPILOT_PROVIDER_API_KEY,GITHUB_TOKEN,COPILOT_GITHUB_TOKEN,NPM_AUTH_TOKEN,NODE_AUTH_TOKEN,NPM_TOKEN",
                    child,
                )
                self.assertNotIn(
                    "--secret-env-vars=COPILOT_PROVIDER_API_KEY,GH_TOKEN", child
                )

    def test_invalid_github_capability_creates_no_session_state(self) -> None:
        for client, binary in (("opencode", self.opencode), ("copilot", self.copilot)):
            for label, token in (("missing", None), ("invalid", "bad token")):
                with self.subTest(client=client, token=label):
                    state = self.root / f"state-{client}-{label}"
                    environment = {
                        **self.environment,
                        "XDG_STATE_HOME": str(state),
                    }
                    if token is None:
                        environment.pop("GH_TOKEN", None)
                    else:
                        environment["GH_TOKEN"] = token
                    with self.assertRaisesRegex(LOCAL.LocalModeError, "GH_TOKEN"):
                        LOCAL.build_local_launch(
                            self._config(client=client),
                            distribution_root=self.distribution,
                            project_dir=self.project,
                            cplt=self.cplt,
                            client=binary,
                            environment=environment,
                            github_access=True,
                            platform="darwin",
                        )
                    self.assertFalse(state.exists())

    def test_github_access_requires_gh_on_path_before_state_is_created(self) -> None:
        self.gh.unlink()
        for client, binary in (("opencode", self.opencode), ("copilot", self.copilot)):
            state = self.root / f"state-no-gh-{client}"
            environment = {**self.environment, "XDG_STATE_HOME": str(state)}
            with self.subTest(client=client), self.assertRaisesRegex(
                LOCAL.LocalModeError, "brew install gh"
            ):
                LOCAL.build_local_launch(
                    self._config(client=client),
                    distribution_root=self.distribution,
                    project_dir=self.project,
                    cplt=self.cplt,
                    client=binary,
                    environment=environment,
                    github_access=True,
                    platform="darwin",
                )
            self.assertFalse(state.exists())

    def test_early_trust_roots_fail_before_config_read_or_binary_resolution(self) -> None:
        cases = (
            (
                "local-config",
                {**self.environment, "XDG_CONFIG_HOME": str(self.project / "config")},
                "Grillmester local config",
            ),
            (
                "local-state",
                {**self.environment, "XDG_STATE_HOME": str(self.project / "state")},
                "Grillmester local state",
            ),
            (
                "explicit-cplt-config",
                {**self.environment, "CPLT_CONFIG": str(self.project / "cplt.toml")},
                "cplt config",
            ),
            (
                "default-cplt-config",
                {**self.environment, "HOME": str(self.project)},
                "cplt config",
            ),
        )
        for label, environment, expected in cases:
            with self.subTest(label=label), mock.patch.object(
                LOCAL, "load_config", side_effect=AssertionError("must not read config")
            ) as load, mock.patch.object(
                LOCAL,
                "_resolve_path_executable",
                side_effect=AssertionError("must not resolve a client"),
            ) as resolve:
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    result = LOCAL.main(
                        ["launch", "--project-dir", str(self.project)],
                        distribution_root=self.distribution,
                        binary_resolver=lambda *_arguments: (_ for _ in ()).throw(
                            AssertionError("must not resolve binaries")
                        ),
                        environment=environment,
                    )

            self.assertEqual(2, result)
            self.assertIn(expected, stderr.getvalue())
            load.assert_not_called()
            resolve.assert_not_called()

    def test_version_probe_rejects_project_state_before_preparing_tools(self) -> None:
        state = self.project / "state"
        environment = {**self.environment, "XDG_STATE_HOME": str(state)}

        with self.assertRaisesRegex(LOCAL.LocalModeError, "Grillmester local state"):
            LOCAL.prepare_client_version_probe(
                client_name="opencode",
                cplt=self.cplt,
                client=self.opencode,
                distribution_root=self.distribution,
                project_dir=self.project,
                environment=environment,
                platform="darwin",
            )

        self.assertFalse(state.exists())

    def test_build_rejects_distribution_and_executables_inside_project(self) -> None:
        project_cplt = self.project / "cplt"
        project_client = self.project / "opencode"
        for executable in (project_cplt, project_client):
            executable.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
            executable.chmod(0o700)
        cases = (
            ("distribution", self.project, self.cplt, self.opencode),
            ("cplt executable", self.distribution, project_cplt, self.opencode),
            ("opencode executable", self.distribution, self.cplt, project_client),
        )
        for index, (expected, distribution, cplt, client) in enumerate(cases):
            state = self.root / f"rejected-trust-state-{index}"
            environment = {**self.environment, "XDG_STATE_HOME": str(state)}
            with self.subTest(expected=expected), self.assertRaisesRegex(
                LOCAL.LocalModeError, expected
            ):
                LOCAL.build_local_launch(
                    self._config(),
                    distribution_root=distribution,
                    project_dir=self.project,
                    cplt=cplt,
                    client=client,
                    environment=environment,
                    platform="darwin",
                )
            self.assertFalse(state.exists())

    def test_build_rejects_a_project_nested_inside_the_distribution(self) -> None:
        state = self.root / "rejected-nested-project-state"
        environment = {**self.environment, "XDG_STATE_HOME": str(state)}

        with self.assertRaisesRegex(LOCAL.LocalModeError, "Grillmester distribution"):
            LOCAL.build_local_launch(
                self._config(),
                distribution_root=self.distribution,
                project_dir=self.distribution / "plugin",
                cplt=self.cplt,
                client=self.opencode,
                environment=environment,
                platform="darwin",
            )

        self.assertFalse(state.exists())

    def test_build_rejects_opt_in_github_cli_inside_project(self) -> None:
        project_bin = self.project / "bin"
        project_bin.mkdir()
        project_gh = project_bin / "gh"
        project_gh.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
        project_gh.chmod(0o700)
        state = self.root / "rejected-github-state"
        environment = {
            **self.environment,
            "PATH": os.pathsep.join((str(project_bin), str(self.bin))),
            "XDG_STATE_HOME": str(state),
        }

        with self.assertRaisesRegex(LOCAL.LocalModeError, "GitHub CLI executable"):
            LOCAL.build_local_launch(
                self._config(),
                distribution_root=self.distribution,
                project_dir=self.project,
                cplt=self.cplt,
                client=self.opencode,
                environment=environment,
                github_access=True,
                platform="darwin",
            )

        self.assertFalse(state.exists())

    def test_external_cplt_config_is_canonical_and_project_alias_is_rejected(self) -> None:
        policy = self.root / "managed-cplt.toml"
        policy.write_text("[proxy]\nforced = true\n", encoding="utf-8")
        external_alias = self.root / "managed-cplt-link.toml"
        external_alias.symlink_to(policy)
        environment = {**self.environment, "CPLT_CONFIG": str(external_alias)}
        launch = LOCAL.build_local_launch(
            self._config(),
            distribution_root=self.distribution,
            project_dir=self.project,
            cplt=self.cplt,
            client=self.opencode,
            environment=environment,
            platform="darwin",
        )
        self.assertEqual(str(policy.resolve()), launch.environment["CPLT_CONFIG"])

        project_alias = self.project / "cplt-config.toml"
        project_alias.symlink_to(policy)
        rejected_state = self.root / "rejected-cplt-config-state"
        rejected_environment = {
            **self.environment,
            "CPLT_CONFIG": str(project_alias),
            "XDG_STATE_HOME": str(rejected_state),
        }
        with self.assertRaisesRegex(LOCAL.LocalModeError, "cplt config"):
            LOCAL.build_local_launch(
                self._config(),
                distribution_root=self.distribution,
                project_dir=self.project,
                cplt=self.cplt,
                client=self.opencode,
                environment=rejected_environment,
                platform="darwin",
            )
        self.assertFalse(rejected_state.exists())

    def test_cplt_trust_symlink_into_project_is_rejected_before_state(self) -> None:
        policy_root = self.root / "managed-cplt"
        policy_root.mkdir()
        policy = policy_root / "config.toml"
        policy.write_text("[proxy]\nforced = true\n", encoding="utf-8")
        project_trust = self.project / "trust"
        project_trust.mkdir()
        (policy_root / "trust").symlink_to(project_trust, target_is_directory=True)
        state = self.root / "rejected-cplt-trust-state"
        environment = {
            **self.environment,
            "CPLT_CONFIG": str(policy),
            "XDG_STATE_HOME": str(state),
        }

        with self.assertRaisesRegex(LOCAL.LocalModeError, "cplt trust directory"):
            LOCAL.build_local_launch(
                self._config(),
                distribution_root=self.distribution,
                project_dir=self.project,
                cplt=self.cplt,
                client=self.opencode,
                environment=environment,
                platform="darwin",
            )

        self.assertFalse(state.exists())

    def test_actual_runtime_overlap_is_rejected_before_parent_tools_are_staged(self) -> None:
        runtime = LOCAL._runtime_paths(self.project / "runtime")
        with mock.patch.object(
            LOCAL, "_prepare_runtime", return_value=runtime
        ), mock.patch.object(
            LOCAL,
            "_prepare_trusted_parent_tools",
            side_effect=AssertionError("must not stage parent tools"),
        ) as stage, self.assertRaisesRegex(LOCAL.LocalModeError, "Grillmester runtime"):
            LOCAL.build_local_launch(
                self._config(),
                distribution_root=self.distribution,
                project_dir=self.project,
                cplt=self.cplt,
                client=self.opencode,
                environment=self.environment,
                platform="darwin",
            )

        stage.assert_not_called()

    def test_execute_rejects_invalid_run_inputs_before_probe_or_state(self) -> None:
        without_token = {**self.environment}
        without_token.pop("GH_TOKEN", None)
        cases = (
            ("blank-prompt", "   ", False, self.environment, "prompt"),
            ("missing-token", "Create the approved issue", True, without_token, "GH_TOKEN"),
        )
        for label, prompt, github_access, environment, error in cases:
            with self.subTest(case=label), mock.patch.object(
                LOCAL, "probe_model", side_effect=AssertionError("must not probe")
            ) as probe, self.assertRaisesRegex(LOCAL.LocalModeError, error):
                LOCAL.execute_local(
                    self._config(),
                    distribution_root=self.distribution,
                    project_dir=self.project,
                    cplt=self.cplt,
                    client=self.opencode,
                    run_prompt=prompt,
                    github_access=github_access,
                    environment=environment,
                    platform="darwin",
                )
            probe.assert_not_called()
            self.assertFalse((self.root / "state").exists())

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

        run = LOCAL.build_local_launch(
            config,
            distribution_root=self.distribution,
            project_dir=self.project,
            cplt=self.cplt,
            client=self.opencode,
            run_prompt="fix the test",
            environment=self.environment,
            platform="darwin",
        )
        command = list(run.command)
        client = command[command.index("--") + 1 :]
        self.assertEqual("run", client[0])
        self.assertIn("--auto", client)
        self.assertIn("grillmester", client)
        self.assertEqual("fix the test", client[-1])

        for arguments in (("--help",), ("-v",)):
            with self.subTest(arguments=arguments):
                meta = self._launch(arguments=arguments)
                self.assertEqual(
                    list(arguments), list(meta.command[meta.command.index("--") + 1 :])
                )

        for arguments in (("models", "llamacpp"), ("subdir",), ("plugin", "list")):
            with self.subTest(arguments=arguments), self.assertRaisesRegex(
                LOCAL.LocalModeError, "grillmester local run"
            ):
                self._launch(arguments=arguments)

    def test_opencode_run_auto_approves_tools_without_exposing_ambient_github_token(
        self,
    ) -> None:
        launch = LOCAL.build_local_launch(
            self._config(),
            distribution_root=self.distribution,
            project_dir=self.project,
            cplt=self.cplt,
            client=self.opencode,
            run_prompt="Fix the failing test",
            environment=self.environment,
            platform="darwin",
        )

        command = list(launch.command)
        self.assertEqual("cplt", Path(command[0]).name)
        self.assertIn(str(self.project.resolve(strict=True)), command)
        self.assertEqual(
            [
                "run",
                "--agent",
                "barista",
                "--model",
                "llamacpp/qwen3.8-local",
                "--auto",
                "--title",
                "Grillmester local run",
                "--",
                "Fix the failing test",
            ],
            command[command.index("--") + 1 :],
        )
        self.assertNotIn("GH_TOKEN", launch.environment)
        self.assertNotIn("GH_TOKEN", launch.secret_environment)

    def test_run_rejects_nul_in_prompt_before_building_the_client_command(self) -> None:
        with self.assertRaisesRegex(LOCAL.LocalModeError, "must not contain NUL"):
            LOCAL.build_local_launch(
                self._config(),
                distribution_root=self.distribution,
                project_dir=self.project,
                cplt=self.cplt,
                client=self.opencode,
                run_prompt="Fix the test\0and hide this suffix",
                environment=self.environment,
                platform="darwin",
            )

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
        self.assertIn(
            "--secret-env-vars=COPILOT_PROVIDER_API_KEY,GH_TOKEN,GITHUB_TOKEN,COPILOT_GITHUB_TOKEN,NPM_AUTH_TOKEN,NODE_AUTH_TOKEN,NPM_TOKEN",
            client,
        )
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

    def test_copilot_run_is_noninteractive_but_denies_gh_without_explicit_access(
        self,
    ) -> None:
        launch = LOCAL.build_local_launch(
            self._config(client="copilot"),
            distribution_root=self.distribution,
            project_dir=self.project,
            cplt=self.cplt,
            client=self.copilot,
            run_prompt="Fix the failing test",
            environment=self.environment,
            platform="darwin",
        )

        command = list(launch.command)
        client = command[command.index("--") + 1 :]
        self.assertIn("--prompt", client)
        self.assertEqual("Fix the failing test", client[client.index("--prompt") + 1])
        self.assertIn("--allow-all-tools", client)
        self.assertIn("--allow-all-urls", client)
        self.assertIn("--no-ask-user", client)
        self.assertIn("--deny-tool=shell(gh:*)", client)
        self.assertIn(
            "--secret-env-vars=COPILOT_PROVIDER_API_KEY,GH_TOKEN,GITHUB_TOKEN,COPILOT_GITHUB_TOKEN,NPM_AUTH_TOKEN,NODE_AUTH_TOKEN,NPM_TOKEN",
            client,
        )
        self.assertNotIn("--allow-all-paths", client)
        self.assertNotIn("GH_TOKEN", launch.environment)
        self.assertNotIn("GH_TOKEN", launch.secret_environment)
        passed_environment = {
            command[index + 1]
            for index, value in enumerate(command)
            if value == "--pass-env"
        }
        self.assertNotIn("GH_TOKEN", passed_environment)
        trusted_gh = Path(
            shutil.which("gh", path=launch.environment["PATH"])
        )
        self.assertEqual(launch.runtime.trusted_bin / "gh", trusted_gh)
        self.assertEqual(0o500, stat.S_IMODE(trusted_gh.stat().st_mode))
        self.assertNotEqual(0, subprocess.run([trusted_gh], check=False).returncode)
        trusted_git = Path(
            shutil.which("git", path=launch.environment["PATH"])
        )
        self.assertEqual(
            self.system_tools["git"].resolve(strict=True),
            trusted_git.resolve(strict=True),
        )

    def test_local_version_probe_scrubs_credentials_and_stages_exact_parent_tools(
        self,
    ) -> None:
        environment = {
            **self.environment,
            "CUSTOM_LOCAL_SECRET": "must-not-cross",
            "HTTPS_PROXY": "http://must-not-cross.invalid",
            "CPLT_CONFIG": str(self.root / "managed-cplt.toml"),
        }

        probe = LOCAL.prepare_client_version_probe(
            client_name="copilot",
            cplt=SimpleNamespace(path=str(self.cplt), version="reviewed"),
            client=SimpleNamespace(path=str(self.copilot), version="reviewed"),
            distribution_root=self.distribution,
            project_dir=self.project,
            environment=environment,
            platform="darwin",
        )

        rendered = json.dumps(dict(probe.environment), sort_keys=True)
        self.assertNotIn("must-not-cross", rendered)
        self.assertNotIn("HTTPS_PROXY", probe.environment)
        self.assertEqual(
            probe.trusted_bin,
            Path(probe.environment["PATH"].split(os.pathsep)[0]),
        )
        self.assertEqual(
            self.copilot.resolve(strict=True),
            (probe.trusted_bin / "copilot").resolve(strict=True),
        )
        self.assertEqual(
            self.system_tools["git"].resolve(strict=True),
            (probe.trusted_bin / "git").resolve(strict=True),
        )
        self.assertEqual(0o500, stat.S_IMODE((probe.trusted_bin / "gh").stat().st_mode))
        self.assertEqual(
            str(Path(environment["CPLT_CONFIG"]).resolve(strict=False)),
            probe.environment["CPLT_CONFIG"],
        )
        self.assertEqual(str(probe.trusted_bin), probe.cplt_arguments[
            probe.cplt_arguments.index("--allow-read") + 1
        ])
        self.assertIn("--proxy-forced", probe.cplt_arguments)
        self.assertIn("--gh-guard", probe.cplt_arguments)
        self.assertIn("--git-guard", probe.cplt_arguments)
        passed = {
            probe.cplt_arguments[index + 1]
            for index, value in enumerate(probe.cplt_arguments[:-1])
            if value == "--pass-env"
        }
        self.assertIn("COPILOT_HOME", passed)
        self.assertIn("COPILOT_AUTO_UPDATE", passed)
        self.assertIn("COPILOT_OTEL_ENABLED", passed)
        probe_root = probe.root
        LOCAL.cleanup_client_version_probe(probe)
        self.assertFalse(probe_root.exists())

    def test_local_version_probe_cleans_session_when_private_settings_fail(
        self,
    ) -> None:
        with mock.patch.object(
            LOCAL, "_copilot_settings", side_effect=RuntimeError("fixture failure")
        ), self.assertRaisesRegex(RuntimeError, "fixture failure"):
            LOCAL.prepare_client_version_probe(
                client_name="copilot",
                cplt=self.cplt,
                client=self.copilot,
                distribution_root=self.distribution,
                project_dir=self.project,
                environment=self.environment,
                platform="darwin",
            )

        sessions = LOCAL.state_root(self.environment) / "sessions"
        self.assertEqual(
            [],
            [
                path
                for path in sessions.iterdir()
                if path.is_dir() and path.name.startswith("copilot-")
            ],
        )

    def test_copilot_run_with_explicit_github_access_passes_redacted_token_and_removes_gh_deny(
        self,
    ) -> None:
        launch = LOCAL.build_local_launch(
            self._config(client="copilot"),
            distribution_root=self.distribution,
            project_dir=self.project,
            cplt=self.cplt,
            client=self.copilot,
            run_prompt="Create the approved issue",
            github_access=True,
            environment=self.environment,
            platform="darwin",
        )

        client = list(launch.command[launch.command.index("--") + 1 :])
        self.assertNotIn("--deny-tool=shell(gh:*)", client)
        self.assertEqual("must-not-cross", launch.environment["GH_TOKEN"])
        self.assertEqual("<redacted>", launch.redacted_environment["GH_TOKEN"])
        self.assertIn("GH_TOKEN", launch.secret_environment)

    def test_npm_access_is_explicit_redacted_and_passed_to_both_clients(self) -> None:
        (self.project / ".npmrc").write_text(
            "//registry.example/:_authToken=${NPM_AUTH_TOKEN}\n",
            encoding="utf-8",
        )
        self.environment["NPM_AUTH_TOKEN"] = "npm_test_token"

        for client_name in ("opencode", "copilot"):
            with self.subTest(client=client_name):
                launch = self._launch(
                    self._config(client=client_name), npm_access=True
                )
                passed = {
                    launch.command[index + 1]
                    for index, value in enumerate(launch.command[:-1])
                    if value == "--pass-env"
                }
                client = list(launch.command[launch.command.index("--") + 1 :])

                self.assertEqual(
                    "npm_test_token", launch.environment["NPM_AUTH_TOKEN"]
                )
                self.assertEqual(
                    "<redacted>", launch.redacted_environment["NPM_AUTH_TOKEN"]
                )
                self.assertIn("NPM_AUTH_TOKEN", launch.secret_environment)
                self.assertIn("NPM_AUTH_TOKEN", passed)
                if client_name == "copilot":
                    secret_option = next(
                        value
                        for value in client
                        if value.startswith("--secret-env-vars=")
                    )
                    self.assertNotIn(
                        "NPM_AUTH_TOKEN",
                        secret_option.split("=", 1)[1].split(","),
                    )

        copilot_without_access = self._launch(self._config(client="copilot"))
        copilot_client = list(
            copilot_without_access.command[
                copilot_without_access.command.index("--") + 1 :
            ]
        )
        secret_option = next(
            value
            for value in copilot_client
            if value.startswith("--secret-env-vars=")
        )
        self.assertIn(
            "NPM_AUTH_TOKEN",
            secret_option.split("=", 1)[1].split(","),
        )
        self.assertIn(
            "NODE_AUTH_TOKEN",
            secret_option.split("=", 1)[1].split(","),
        )
        self.assertIn(
            "NPM_TOKEN",
            secret_option.split("=", 1)[1].split(","),
        )

    def test_ambient_npm_token_is_scrubbed_without_explicit_access(self) -> None:
        self.environment["NPM_AUTH_TOKEN"] = "must-not-cross"

        launch = self._launch()

        self.assertNotIn("NPM_AUTH_TOKEN", launch.environment)
        self.assertNotIn("NPM_AUTH_TOKEN", launch.secret_environment)
        self.assertNotIn("NPM_AUTH_TOKEN", launch.command)

    def test_local_launch_uses_empty_session_owned_npm_configs(self) -> None:
        host_config = Path(self.environment["HOME"]) / ".npmrc"
        host_config.write_text("//registry.example/:_authToken=ambient\n", encoding="utf-8")

        launch = self._launch()

        user_config = Path(launch.environment["NPM_CONFIG_USERCONFIG"])
        global_config = Path(launch.environment["NPM_CONFIG_GLOBALCONFIG"])
        passed = {
            launch.command[index + 1]
            for index, value in enumerate(launch.command[:-1])
            if value == "--pass-env"
        }
        self.assertTrue(user_config.is_relative_to(launch.runtime.xdg_config))
        self.assertNotEqual(host_config, user_config)
        self.assertEqual("", user_config.read_text(encoding="utf-8"))
        self.assertEqual(0o600, stat.S_IMODE(user_config.stat().st_mode))
        self.assertIn("NPM_CONFIG_USERCONFIG", passed)
        self.assertTrue(global_config.is_relative_to(launch.runtime.xdg_config))
        self.assertNotEqual(user_config, global_config)
        self.assertEqual("", global_config.read_text(encoding="utf-8"))
        self.assertEqual(0o600, stat.S_IMODE(global_config.stat().st_mode))
        self.assertIn("NPM_CONFIG_GLOBALCONFIG", passed)

    def test_npm_access_requires_a_valid_caller_token(self) -> None:
        (self.project / ".npmrc").write_text(
            "//registry.example/:_authToken=${NPM_AUTH_TOKEN}\n",
            encoding="utf-8",
        )
        for label, token in (
            ("missing", None),
            ("empty", ""),
            ("whitespace", "bad token"),
            ("unicode", "bad😀token"),
        ):
            with self.subTest(token=label):
                environment = {**self.environment}
                if token is None:
                    environment.pop("NPM_AUTH_TOKEN", None)
                else:
                    environment["NPM_AUTH_TOKEN"] = token
                with self.assertRaisesRegex(
                    LOCAL.LocalModeError, "NPM_AUTH_TOKEN"
                ):
                    LOCAL.build_local_launch(
                        self._config(),
                        distribution_root=self.distribution,
                        project_dir=self.project,
                        cplt=self.cplt,
                        client=self.opencode,
                        npm_access=True,
                        environment=environment,
                        platform="darwin",
                    )

    def test_npm_access_detects_node_token_and_accepts_printable_symbols(self) -> None:
        (self.project / ".npmrc").write_text(
            "//registry.example/:_authToken=${NODE_AUTH_TOKEN}\n",
            encoding="utf-8",
        )
        self.environment["NODE_AUTH_TOKEN"] = "jwt.part+/="

        launch = self._launch(npm_access=True)

        self.assertEqual("jwt.part+/=", launch.environment["NODE_AUTH_TOKEN"])
        self.assertEqual("<redacted>", launch.redacted_environment["NODE_AUTH_TOKEN"])
        self.assertNotIn("NPM_AUTH_TOKEN", launch.environment)

    def test_custom_npm_token_env_must_be_auth_referenced_and_not_control_state(self) -> None:
        npmrc = self.project / ".npmrc"
        npmrc.write_text(
            "//registry.example/:_authToken=${NAV_PACKAGE_READ_TOKEN}\n",
            encoding="utf-8",
        )
        self.environment["NAV_PACKAGE_READ_TOKEN"] = "custom-token"

        launch = self._launch(npm_token_env="NAV_PACKAGE_READ_TOKEN")

        self.assertEqual(
            "custom-token", launch.environment["NAV_PACKAGE_READ_TOKEN"]
        )
        with self.assertRaisesRegex(LOCAL.LocalModeError, "not referenced"):
            self._launch(npm_token_env="ANOTHER_PACKAGE_TOKEN")

        npmrc.write_text(
            "//registry.example/:_authToken=${NPM_CONFIG_PACKAGE_TOKEN}\n",
            encoding="utf-8",
        )
        self.environment["NPM_CONFIG_PACKAGE_TOKEN"] = "attacker-value"
        with self.assertRaisesRegex(LOCAL.LocalModeError, "control state"):
            self._launch(npm_token_env="NPM_CONFIG_PACKAGE_TOKEN")

        npmrc.write_text(
            "//registry.example/:_authToken=${OPENAI_API_KEY}\n",
            encoding="utf-8",
        )
        self.environment["OPENAI_API_KEY"] = "not-a-package-token"
        with self.assertRaisesRegex(LOCAL.LocalModeError, "package credential"):
            self._launch(npm_token_env="OPENAI_API_KEY")

        npmrc.write_text(
            "//registry.example/:_authToken=${nav_package_read_token}\n",
            encoding="utf-8",
        )
        self.environment["nav_package_read_token"] = "lowercase-custom-token"
        launch = self._launch(npm_token_env="nav_package_read_token")
        self.assertEqual(
            "lowercase-custom-token",
            launch.environment["nav_package_read_token"],
        )

    def test_npm_advice_is_nonblocking_and_never_recommends_unsafe_names(self) -> None:
        npmrc = self.project / ".npmrc"
        victim = self.root / "ambient-npmrc"
        victim.write_text("_authToken=${NPM_AUTH_TOKEN}\n", encoding="utf-8")
        npmrc.symlink_to(victim)

        advice = LOCAL._npm_access_advice(self.project)

        assert advice is not None
        self.assertEqual("warn", advice[0])
        self.assertIn("package access remains off", advice[1])

        npmrc.unlink()
        npmrc.write_text("_authToken=${OPENAI_API_KEY}\n", encoding="utf-8")
        advice = LOCAL._npm_access_advice(self.project)
        assert advice is not None
        self.assertEqual("warn", advice[0])
        self.assertIn("unsupported auth placeholder", advice[1])
        self.assertNotIn("--npm-token-env OPENAI_API_KEY", advice[1])

        npmrc.write_text(
            "//one.example/:_authToken=${OPENAI_API_KEY}\n"
            "//two.example/:_authToken=${GITHUB_TOKEN}\n",
            encoding="utf-8",
        )
        advice = LOCAL._npm_access_advice(self.project)
        assert advice is not None
        self.assertEqual("warn", advice[0])
        self.assertIn("no supported package-token", advice[1])
        self.assertNotIn("--npm-token-env", advice[1])

    @mock.patch.object(LOCAL.sys, "platform", "darwin")
    def test_run_preflight_hints_about_project_npm_token_without_enabling_it(
        self,
    ) -> None:
        (self.project / ".npmrc").write_text(
            "//registry.example/:_authToken=${NODE_AUTH_TOKEN}\n",
            encoding="utf-8",
        )
        LOCAL.save_config(self._config(), environment=self.environment)
        stderr = io.StringIO()
        stdout = io.StringIO()

        def resolve(
            _client: str, checked: bool, _project: Path
        ) -> tuple[Path, Path]:
            self.assertFalse(checked)
            return self.cplt, self.opencode

        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = LOCAL.main(
                [
                    "run",
                    "--print-command",
                    "--project-dir",
                    str(self.project),
                    "task",
                ],
                distribution_root=self.distribution,
                binary_resolver=resolve,
                environment=self.environment,
            )

        self.assertEqual(0, result)
        self.assertIn("use --npm-access", stderr.getvalue())
        self.assertNotIn("--pass-env NODE_AUTH_TOKEN", stdout.getvalue())

    def test_npm_access_fails_closed_on_missing_or_ambiguous_auth_placeholder(self) -> None:
        with self.assertRaisesRegex(LOCAL.LocalModeError, "no .* reference"):
            self._launch(npm_access=True)

        (self.project / ".npmrc").write_text(
            "//one.example/:_authToken=${NPM_AUTH_TOKEN}\n"
            "//two.example/:_authToken=${NODE_AUTH_TOKEN}\n",
            encoding="utf-8",
        )
        self.environment["NPM_AUTH_TOKEN"] = "one"
        self.environment["NODE_AUTH_TOKEN"] = "two"
        with self.assertRaisesRegex(LOCAL.LocalModeError, "multiple npm auth"):
            self._launch(npm_access=True)

        (self.project / ".npmrc").write_text(
            "//one.example/:_authToken=${NPM_AUTH_TOKEN}\n"
            "//two.example/:_authToken=${NAV_PACKAGE_READ_TOKEN}\n",
            encoding="utf-8",
        )
        self.environment["NAV_PACKAGE_READ_TOKEN"] = "two"
        with self.assertRaisesRegex(LOCAL.LocalModeError, "multiple npm auth"):
            self._launch(npm_access=True)

        (self.project / ".npmrc").write_text(
            "//registry.example/:_authToken=${OPENAI_API_KEY}\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(LOCAL.LocalModeError, "map it to NPM_AUTH_TOKEN"):
            self._launch(npm_access=True)

        (self.project / ".npmrc").write_text(
            "//one.example/:_authToken=${OPENAI_API_KEY}\n"
            "//two.example/:_authToken=${GITHUB_TOKEN}\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(LOCAL.LocalModeError, "no supported package-token"):
            self._launch(npm_access=True)

    def test_copilot_without_auth_uses_only_redacted_local_placeholder(self) -> None:
        launch = self._launch(self._config(client="copilot"))
        self.assertEqual("local", launch.environment["COPILOT_PROVIDER_API_KEY"])
        self.assertEqual("<redacted>", launch.redacted_environment["COPILOT_PROVIDER_API_KEY"])
        self.assertNotIn("'COPILOT_PROVIDER_API_KEY': 'local'", repr(launch))

    def test_project_opencode_config_and_extension_surfaces_fail_closed(self) -> None:
        candidates = (
            self.project / "opencode.json",
            self.project / "opencode.jsonc",
            self.project / ".opencode" / "opencode.json",
            self.project / ".opencode" / "opencode.jsonc",
            self.project / ".opencode" / "plugins" / "evil.js",
            self.project / ".opencode" / "plugin" / "evil.js",
            self.project / ".opencode" / "agents" / "evil.md",
            self.project / ".opencode" / "agent" / "evil.md",
            self.project / ".opencode" / "commands" / "evil.md",
            self.project / ".opencode" / "command" / "evil.md",
            self.project / ".opencode" / "modes" / "evil.md",
            self.project / ".opencode" / "mode" / "evil.md",
            self.project / ".opencode" / "mcp.json",
            self.project / ".opencode" / "skills" / "evil" / "SKILL.md",
            self.project / ".opencode" / "skill" / "evil" / "SKILL.md",
            self.project / ".opencode" / "themes" / "evil.json",
            self.project / ".opencode" / "theme" / "evil.json",
            self.project / ".opencode" / "tools" / "evil.ts",
            self.project / ".opencode" / "tool" / "evil.ts",
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

    def test_project_opencode_metadata_and_rules_can_coexist(self) -> None:
        metadata = {
            self.project / ".opencode" / ".gitignore": "node_modules\n",
            self.project / ".opencode" / "AGENTS.md": "# Project guidance\n",
            self.project / ".opencode" / "package.json": "{}\n",
            self.project / ".opencode" / "package-lock.json": "{}\n",
            self.project / ".opencode" / "bun.lock": "",
            self.project
            / ".opencode"
            / "node_modules"
            / "@opencode-ai"
            / "plugin"
            / "package.json": "{}\n",
        }
        for path, content in metadata.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        launch = self._launch()

        self.assertEqual(
            "true", launch.environment["OPENCODE_DISABLE_PROJECT_CONFIG"]
        )
        self.assertEqual("true", launch.environment["OPENCODE_PURE"])

    def test_opencode_alternate_project_cannot_bypass_extension_scan(self) -> None:
        alternate = self.project / "subdir"
        plugin = alternate / ".opencode/plugins/evil.js"
        plugin.parent.mkdir(parents=True)
        plugin.write_text("throw new Error('executed')", encoding="utf-8")

        with self.assertRaisesRegex(LOCAL.LocalModeError, "grillmester local run"):
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

    def test_print_shape_redacts_npm_credential_without_reading_it(self) -> None:
        environment = {**self.environment}
        environment.pop("NPM_AUTH_TOKEN", None)
        (self.project / ".npmrc").write_text(
            "//registry.example/:_authToken=${NPM_AUTH_TOKEN}\n",
            encoding="utf-8",
        )

        launch = LOCAL.build_local_launch(
            self._config(),
            distribution_root=self.distribution,
            project_dir=self.project,
            cplt=self.cplt,
            client=self.opencode,
            environment=environment,
            npm_access=True,
            resolve_credentials=False,
            prepare_state=False,
            platform="darwin",
        )

        self.assertEqual("<redacted>", launch.environment["NPM_AUTH_TOKEN"])
        self.assertIn("NPM_AUTH_TOKEN", launch.secret_environment)
        self.assertFalse((self.root / "state").exists())

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

    def test_opencode_hidden_auto_aliases_are_rejected_in_tui(self) -> None:
        for arguments in (
            ("--yolo",),
            ("--dangerously-skip-permissions=true",),
        ):
            with self.subTest(arguments=arguments), self.assertRaisesRegex(
                LOCAL.LocalModeError, "owned by local mode"
            ):
                self._launch(arguments=arguments)

    def test_opencode_unknown_long_options_fail_closed(self) -> None:
        for arguments in (("--future-mode",),):
            with self.subTest(arguments=arguments), self.assertRaisesRegex(
                LOCAL.LocalModeError, "not supported by local mode"
            ):
                self._launch(arguments=arguments)

    def test_raw_opencode_run_requires_the_public_local_run_command(self) -> None:
        for arguments in (
            ("run", "review"),
            ("run", "--future-mode=true", "review"),
        ):
            with self.subTest(arguments=arguments), self.assertRaisesRegex(
                LOCAL.LocalModeError,
                "grillmester local run.*auto-approves tools and project writes",
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
                LOCAL.LocalModeError, "grillmester local run"
            ):
                self._launch(arguments=arguments)

    def test_opencode_run_only_options_are_rejected_for_interactive_launch(
        self,
    ) -> None:
        for arguments in (
            ("--file", "notes.txt"),
            ("--format", "json"),
            ("--interactive",),
            ("--thinking",),
            ("--title", "task"),
            ("--variant", "fast"),
        ):
            with self.subTest(arguments=arguments), self.assertRaisesRegex(
                LOCAL.LocalModeError, "not supported by local mode"
            ):
                self._launch(arguments=arguments)
        for arguments in (("-f", "notes.txt"), ("-i",), ("-if", "notes.txt")):
            with self.subTest(arguments=arguments), self.assertRaisesRegex(
                LOCAL.LocalModeError, "unknown short option"
            ):
                self._launch(arguments=arguments)

    def test_opencode_reviewed_tui_options_remain_available(self) -> None:
        for arguments in (
            ("--mini", "--no-replay", "--replay-limit", "10"),
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

    def test_full_copilot_payload_tampering_fails_closed(self) -> None:
        plugin = self.distribution / "plugin/plugin.json"
        plugin.write_text('{"name":"tampered"}', encoding="utf-8")

        with self.assertRaisesRegex(LOCAL.LocalModeError, "digest mismatch"):
            self._launch(self._config(client="copilot", context="full"))

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
        separator = command.index("--")
        self.assertEqual("copilot", command[command.index("--agent") + 1])
        self.assertNotIn("exec", command[:separator])
        self.assertNotIn("--allow-cache-exec", command)
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
            str(launch.runtime.github_config.resolve(strict=True)),
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
                        "--context-window",
                        "65536",
                        "--max-output-tokens",
                        "16384",
                        "--api-key-env",
                        "LOCAL_MODEL_TOKEN",
                    ]
                ),
            )
            self.assertEqual(0, LOCAL.main(["status"]))
        self.assertIn("environment LOCAL_MODEL_TOKEN", stdout.getvalue())
        self.assertIn("context window: 65536", stdout.getvalue())
        self.assertIn("max output tokens: 16384", stdout.getvalue())
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
        self.assertEqual(57_344, config.context_window)
        self.assertEqual(8_192, config.max_output_tokens)
        self.assertEqual(
            LOCAL.RECOMMENDED_LOCAL_SERVER_CONTEXT_WINDOW,
            config.context_window + config.max_output_tokens,
        )

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

        def resolve(client: str, checked: bool, project: Path) -> tuple[object, object]:
            self.assertEqual(self.project.resolve(), project)
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
    def test_run_preview_maps_saved_opencode_to_focused_barista_auto_mode(self) -> None:
        LOCAL.save_config(
            self._config(context="full", agent="grillmester"),
            environment=self.environment,
        )
        resolutions: list[tuple[str, bool]] = []

        def resolve(client: str, checked: bool, project: Path) -> tuple[object, object]:
            self.assertEqual(self.project.resolve(), project)
            resolutions.append((client, checked))
            return (
                SimpleNamespace(path=str(self.cplt), version="reviewed"),
                SimpleNamespace(path=str(self.opencode), version="reviewed"),
            )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = LOCAL.main(
                [
                    "run",
                    "--project-dir",
                    str(self.project),
                    "--print-command",
                    "Fix the failing test",
                ],
                distribution_root=self.distribution,
                binary_resolver=resolve,
                environment=self.environment,
            )

        self.assertEqual(0, result)
        self.assertEqual([("opencode", False)], resolutions)
        command = shlex.split(stdout.getvalue())
        self.assertEqual(
            [
                "run",
                "--agent",
                "barista",
                "--model",
                "llamacpp/qwen3.8-local",
                "--auto",
                "--title",
                "Grillmester local run",
                "--",
                "Fix the failing test",
            ],
            command[command.index("--") + 1 :],
        )
        persisted = LOCAL.load_config(environment=self.environment)
        self.assertEqual("full", persisted.context)
        self.assertEqual("grillmester", persisted.agent)

    @mock.patch.object(LOCAL.sys, "platform", "darwin")
    def test_doctor_reports_the_exact_checked_runtime_and_selection(self) -> None:
        with ProbeServer() as server:
            LOCAL.save_config(
                self._config(base_url=server.base_url), environment=self.environment
            )

            def resolve(client: str, checked: bool, project: Path) -> tuple[object, object]:
                self.assertEqual(self.project.resolve(), project)
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
        self.assertIn("ok  context-window 57344", output)
        self.assertIn("ok  max-output-tokens 8192", output)
        self.assertIn("targets/opencode-v1-focused", output)
        self.assertIn(
            "info websearch OpenCode sends approved search queries to Exa "
            "when cplt network policy permits",
            output,
        )
        self.assertIn("skip github credential not exposed", output)
        self.assertFalse((self.root / "state").exists())

    @mock.patch.object(LOCAL.sys, "platform", "darwin")
    def test_doctor_reports_copilot_keychain_residual(self) -> None:
        with ProbeServer() as server:
            LOCAL.save_config(
                self._config(client="copilot", base_url=server.base_url),
                environment=self.environment,
            )

            def resolve(client: str, checked: bool, project: Path) -> tuple[object, object]:
                self.assertEqual(self.project.resolve(), project)
                self.assertEqual("copilot", client)
                self.assertTrue(checked)
                return (
                    SimpleNamespace(path=str(self.cplt), version="cplt reviewed"),
                    SimpleNamespace(path=str(self.copilot), version="1.0.80"),
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
        self.assertIn(
            "warn github env/config credential not exposed; cplt's Copilot "
            "profile can still access macOS Keychain",
            output,
        )
        self.assertFalse((self.root / "state").exists())

    @mock.patch.object(LOCAL.sys, "platform", "darwin")
    def test_doctor_aggregates_explicit_github_capability_errors(self) -> None:
        for label, environment, expected in (
            (
                "missing-token",
                {key: value for key, value in self.environment.items() if key != "GH_TOKEN"},
                "GH_TOKEN",
            ),
            (
                "missing-gh",
                {**self.environment, "PATH": str(self.bin / "without-gh")},
                "GitHub CLI (gh)",
            ),
        ):
            with self.subTest(label=label), ProbeServer() as server:
                LOCAL.save_config(
                    self._config(base_url=server.base_url), environment=environment
                )

                def resolve(client: str, checked: bool, project: Path) -> tuple[object, object]:
                    self.assertEqual(self.project.resolve(), project)
                    self.assertEqual("opencode", client)
                    self.assertTrue(checked)
                    return (
                        SimpleNamespace(path=str(self.cplt), version="cplt reviewed"),
                        SimpleNamespace(path=str(self.opencode), version="1.18.20"),
                    )

                stdout = io.StringIO()
                stderr = io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    result = LOCAL.main(
                        [
                            "doctor",
                            "--github-access",
                            "--project-dir",
                            str(self.project),
                        ],
                        distribution_root=self.distribution,
                        binary_resolver=resolve,
                        environment=environment,
                    )

            self.assertEqual(1, result)
            output = stdout.getvalue()
            self.assertIn("ok  cplt", output)
            self.assertIn("ok  client opencode", output)
            self.assertIn("ok  model qwen3.8-local", output)
            self.assertIn("ok  payload", output)
            self.assertIn("error github", output)
            self.assertIn(expected, output)
            self.assertEqual("", stderr.getvalue())
            self.assertFalse((self.root / "state").exists())

    @mock.patch.object(LOCAL.sys, "platform", "darwin")
    def test_doctor_aggregates_missing_explicit_npm_credential(self) -> None:
        (self.project / ".npmrc").write_text(
            "//registry.example/:_authToken=${NPM_AUTH_TOKEN}\n",
            encoding="utf-8",
        )
        environment = {
            key: value
            for key, value in self.environment.items()
            if key != "NPM_AUTH_TOKEN"
        }
        with ProbeServer() as server:
            LOCAL.save_config(
                self._config(base_url=server.base_url), environment=environment
            )

            def resolve(client: str, checked: bool, project: Path) -> tuple[object, object]:
                self.assertEqual(self.project.resolve(), project)
                self.assertEqual("opencode", client)
                self.assertTrue(checked)
                return (
                    SimpleNamespace(path=str(self.cplt), version="cplt reviewed"),
                    SimpleNamespace(path=str(self.opencode), version="1.18.20"),
                )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = LOCAL.main(
                    [
                        "doctor",
                        "--npm-access",
                        "--project-dir",
                        str(self.project),
                    ],
                    distribution_root=self.distribution,
                    binary_resolver=resolve,
                    environment=environment,
                )

        self.assertEqual(1, result)
        self.assertIn("error npm", stdout.getvalue())
        self.assertIn("NPM_AUTH_TOKEN", stdout.getvalue())
        self.assertFalse((self.root / "state").exists())

    @mock.patch.object(LOCAL.sys, "platform", "darwin")
    def test_doctor_warns_but_stays_green_for_uninspectable_npmrc_without_opt_in(
        self,
    ) -> None:
        victim = self.root / "ambient-npmrc"
        victim.write_text("_authToken=${NPM_AUTH_TOKEN}\n", encoding="utf-8")
        (self.project / ".npmrc").symlink_to(victim)
        with ProbeServer() as server:
            LOCAL.save_config(
                self._config(base_url=server.base_url), environment=self.environment
            )

            def resolve(
                _client: str, checked: bool, _project: Path
            ) -> tuple[object, object]:
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
        self.assertIn("warn npm project .npmrc could not be inspected", stdout.getvalue())

    @mock.patch.object(LOCAL.sys, "platform", "darwin")
    def test_remainder_print_token_cannot_disable_checked_binary_resolution(self) -> None:
        with ProbeServer() as server:
            LOCAL.save_config(
                self._config(base_url=server.base_url), environment=self.environment
            )
            resolutions: list[tuple[str, bool]] = []
            executions: list[tuple[str, ...]] = []

            def resolve(client: str, checked: bool, project: Path) -> tuple[object, object]:
                self.assertEqual(self.project.resolve(), project)
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
        self.assertIn(
            "place 'run' immediately after 'grillmester local'", stderr.getvalue()
        )
        self.assertEqual([("opencode", True)], resolutions)
        self.assertEqual([], executions)

    def test_missing_local_config_points_directly_to_setup(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = LOCAL.main(["status"], environment=self.environment)

        self.assertEqual(2, result)
        self.assertIn("grillmester local setup", stderr.getvalue())

    def test_symlinked_local_config_explains_manual_recovery_before_setup(self) -> None:
        path = LOCAL.config_path(self.environment)
        path.parent.mkdir(parents=True)
        victim = self.root / "victim-local.json"
        victim.write_text("{}", encoding="utf-8")
        path.symlink_to(victim)

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = LOCAL.main(["status"], environment=self.environment)

        self.assertEqual(2, result)
        output = stderr.getvalue()
        self.assertIn(f"remove the symlink {path}", output)
        self.assertIn("then run 'grillmester local setup'", output)
        self.assertNotIn("create or replace it", output)
        self.assertTrue(path.is_symlink())
        self.assertEqual("{}", victim.read_text(encoding="utf-8"))

    def test_run_accepts_exactly_one_prompt_and_exposes_no_raw_permission_flags(
        self,
    ) -> None:
        for arguments in (
            ["run", "first prompt", "second prompt"],
            ["run", "--auto", "task"],
            ["run", "--allow-all-tools", "task"],
            ["run", "--allow-all-urls", "task"],
            ["run", "--no-ask-user", "task"],
            ["run", "--deny-tool=shell(gh:*)", "task"],
        ):
            with self.subTest(arguments=arguments), redirect_stderr(
                io.StringIO()
            ), self.assertRaises(SystemExit) as raised:
                LOCAL._parser().parse_args(arguments)
            self.assertEqual(2, raised.exception.code)

    def test_local_argument_normalizer_and_run_parser_share_one_option_surface(
        self,
    ) -> None:
        parser = LOCAL._parser()
        subparsers = next(
            action
            for action in parser._actions
            if getattr(action, "choices", None) is not None
            and "run" in action.choices
        )
        run_options = {
            option
            for action in subparsers.choices["run"]._actions
            for option in action.option_strings
            if option not in {"-h", "--help"}
        }
        self.assertEqual(
            set(LOCAL.LOCAL_ROUTABLE_VALUE_OPTIONS)
            | set(LOCAL.LOCAL_ROUTABLE_FLAG_OPTIONS),
            run_options,
        )

        cases = (
            (
                [
                    "--project-dir",
                    "/tmp/project",
                    "--client=opencode",
                    "--agent",
                    "barista",
                    "--full",
                    "--print-command",
                    "--github-access",
                    "--npm-access",
                    "run",
                    "task",
                ],
                [
                    "run",
                    "--project-dir",
                    "/tmp/project",
                    "--client=opencode",
                    "--agent",
                    "barista",
                    "--full",
                    "--print-command",
                    "--github-access",
                    "--npm-access",
                    "task",
                ],
            ),
            (["--client", "opencode"], ["launch", "--client", "opencode"]),
            (["help"], ["--help"]),
            ([], ["launch"]),
        )
        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                self.assertEqual(expected, LOCAL.normalize_cli_arguments(arguments))

    def test_launch_rejects_raw_run_remainder_with_actionable_syntax(self) -> None:
        LOCAL.save_config(self._config(), environment=self.environment)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = LOCAL.main(
                [
                    "launch",
                    "--client",
                    "opencode",
                    "--",
                    "run",
                    "Fix the failing test",
                ],
                distribution_root=self.distribution,
                binary_resolver=lambda _client, _checked, _project: (
                    SimpleNamespace(path=str(self.cplt), version="reviewed"),
                    SimpleNamespace(path=str(self.opencode), version="reviewed"),
                ),
                environment=self.environment,
            )

        self.assertEqual(2, result)
        self.assertIn("place 'run' immediately after 'grillmester local'", stderr.getvalue())

    def test_run_help_warns_about_auto_approval_worktrees_and_completion_status(
        self,
    ) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            LOCAL._parser().parse_args(["run", "--help"])

        self.assertEqual(0, raised.exception.code)
        output = stdout.getvalue()
        self.assertIn("foreground", output)
        self.assertIn("auto-approves project writes", output)
        self.assertIn("clean, dedicated worktree", output)
        self.assertIn("exit 0 means client completion", output)
        self.assertIn("fine-grained GH_TOKEN", output)
        self.assertNotIn("--allow-all-tools", output)
        self.assertNotIn("--auto", output)

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
