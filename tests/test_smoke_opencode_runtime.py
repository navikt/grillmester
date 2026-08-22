from __future__ import annotations

import importlib.util
import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_smoke_opencode_runtime",
    ROOT / "scripts/smoke_opencode_runtime.py",
)
assert SPEC and SPEC.loader
RUNTIME = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNTIME
SPEC.loader.exec_module(RUNTIME)


def request(*, system: str, tools: bool = True, called: tuple[str, ...] = ()) -> dict:
    messages: list[dict] = [{"role": "system", "content": system}]
    for index, name in enumerate(called):
        messages.append(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": f"call-{index}",
                        "type": "function",
                        "function": {"name": name, "arguments": "{}"},
                    }
                ],
            }
        )
        messages.append({"role": "tool", "content": f"result-{name}"})
    return {"messages": messages, "tools": [{"function": {"name": "task"}}] if tools else []}


def response_text(body: bytes) -> str:
    return body.decode("utf-8")


class OpenCodeRuntimeSmokeTest(unittest.TestCase):
    def state(self, action: str) -> object:
        scenario = RUNTIME.Scenario(
            name="fixture",
            subagent="kokk",
            action=action,
            target=Path("/tmp/runtime-smoke-fixture"),
        )
        return RUNTIME.ProviderState(scenario=scenario)

    def test_primary_delegates_once_then_finishes(self) -> None:
        state = self.state("read-env")
        first = response_text(
            RUNTIME.provider_response(state, request(system="# Grillmester"))
        )
        self.assertIn('"name":"task"', first)
        self.assertIn('\\"subagent_type\\":\\"kokk\\"', first)
        self.assertEqual({"task"}, state.requested_tool_names())

        final = response_text(
            RUNTIME.provider_response(
                state, request(system="# Grillmester", called=("task",))
            )
        )
        self.assertNotIn("tool_calls", final)
        self.assertIn("runtime smoke complete", final)

    def test_skill_reference_scenario_loads_skill_before_reading_reference(self) -> None:
        state = self.state("skill-reference")
        load = response_text(RUNTIME.provider_response(state, request(system="# Kokk")))
        self.assertIn('"name":"skill"', load)
        self.assertIn("grillmester-create-a-skill", load)
        self.assertEqual({"skill"}, state.requested_tool_names())

        read = response_text(
            RUNTIME.provider_response(
                state, request(system="# Kokk", called=("skill",))
            )
        )
        self.assertIn('"name":"read"', read)
        self.assertIn("runtime-smoke-fixture", read)
        self.assertEqual({"skill", "read"}, state.requested_tool_names())

        final = response_text(
            RUNTIME.provider_response(
                state, request(system="# Kokk", called=("skill", "read"))
            )
        )
        self.assertNotIn("tool_calls", final)

    def test_env_and_write_scenarios_request_only_the_expected_native_tool(self) -> None:
        cases = {
            "read-env": "read",
            "deny-write": "write",
            "allow-write": "write",
        }
        for action, tool in cases.items():
            with self.subTest(action=action):
                body = response_text(
                    RUNTIME.provider_response(self.state(action), request(system="# Kokk"))
                )
                self.assertIn(f'"name":"{tool}"', body)

    def test_rejected_tool_is_not_requested_twice_or_counted_as_executed(self) -> None:
        state = self.state("deny-write")
        first = response_text(RUNTIME.provider_response(state, request(system="# Kokk")))
        second = response_text(RUNTIME.provider_response(state, request(system="# Kokk")))

        self.assertIn('"name":"write"', first)
        self.assertNotIn("tool_calls", second)
        self.assertEqual({"write"}, state.requested_tool_names())
        self.assertNotIn("write", state.called_tools())

    def test_environment_isolated_from_credentials_and_remote_proxies(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            old = dict(os.environ)
            try:
                os.environ.update(
                    {
                        "GH_TOKEN": "secret",
                        "OPENAI_API_KEY": "secret",
                        "HTTPS_PROXY": "http://remote-proxy.invalid",
                    }
                )
                environment = RUNTIME.isolated_environment(
                    sandbox=Path(temp),
                    config_dir=Path(temp) / "target",
                    consumer=Path(temp) / "consumer",
                )
            finally:
                os.environ.clear()
                os.environ.update(old)

        self.assertNotIn("GH_TOKEN", environment)
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("HTTPS_PROXY", environment)
        self.assertEqual("127.0.0.1,localhost,::1", environment["NO_PROXY"])
        self.assertEqual("true", environment["OPENCODE_DISABLE_AUTOUPDATE"])
        self.assertEqual("true", environment["OPENCODE_PURE"])
        self.assertEqual("true", environment["OPENCODE_DISABLE_PROJECT_CONFIG"])
        self.assertEqual(":memory:", environment["OPENCODE_DB"])
        self.assertEqual(str((Path(temp) / "consumer").resolve()), environment["PWD"])
        self.assertEqual("false", environment["OPENCODE_AUTO_SHARE"])
        config_content = __import__("json").loads(environment["OPENCODE_CONFIG_CONTENT"])
        self.assertEqual(False, config_content["autoupdate"])
        self.assertEqual("disabled", config_content["share"])
        self.assertEqual(
            [str((Path(temp) / "consumer/AGENTS.md").resolve())],
            config_content["instructions"],
        )
        self.assertIn("OPENCODE_PURE", RUNTIME.CPLT_PASSTHROUGH_ENV)

    def test_cplt_wrapper_uses_pinned_strict_read_only_contract(self) -> None:
        command = RUNTIME.cplt_command(
            cplt=Path("/opt/bin/cplt"),
            opencode_command=[
                "/opt/bin/opencode",
                "run",
                "--agent",
                "grillmester",
                "prompt",
            ],
            consumer=Path("/work/consumer"),
            config_dir=Path("/data/grillmester/session/config"),
            local_port=1234,
        )

        self.assertEqual(
            [
                "/opt/bin/cplt",
                "--agent",
                "opencode",
                "--preset",
                "strict",
                "--yes",
                "--scratch-dir",
                "--deny-clipboard",
                "--no-audit",
                "--no-quiet",
                "--project-dir",
                "/work/consumer",
                "--allow-read",
                "/data/grillmester/session/config",
                "--allow-localhost",
                "1234",
            ],
            command[:16],
        )
        self.assertNotIn("--allow-write", command)
        for name in RUNTIME.CPLT_PASSTHROUGH_ENV:
            index = command.index(name)
            self.assertEqual("--pass-env", command[index - 1])
        separator = command.index("--")
        self.assertEqual(
            ["run", "--agent", "grillmester", "prompt"],
            command[separator + 1 :],
        )

    def test_missing_binary_skips_or_fails_when_required(self) -> None:
        missing = "/definitely/missing/grillmester-opencode"
        stdout = StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(0, RUNTIME.main(["--opencode", missing]))
        self.assertIn("SKIP:", stdout.getvalue())

        stderr = StringIO()
        with redirect_stderr(stderr):
            self.assertEqual(
                1, RUNTIME.main(["--opencode", missing, "--require-binary"])
            )
        self.assertIn("ERROR:", stderr.getvalue())

    def test_probe_server_binds_only_to_loopback(self) -> None:
        self.assertEqual("127.0.0.1", RUNTIME.SERVER_HOST)

    def test_project_plugin_canary_models_the_stock_import_hazard(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            consumer = Path(temp)
            marker = RUNTIME.write_project_plugin_canary(consumer)
            plugin = consumer / ".opencode/plugins/grillmester-runtime-canary.js"

            self.assertTrue(plugin.is_file())
            self.assertFalse(marker.exists())
            source = plugin.read_text(encoding="utf-8")
            self.assertIn("writeFileSync", source)
            self.assertIn(str(marker), source)
            self.assertIn("export default", source)

    def test_staged_target_is_immutable_and_can_be_cleaned_up(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "target"
            script = root / "skills/example/helper.sh"
            config = root / "opencode.json"
            script.parent.mkdir(parents=True)
            script.write_text("#!/bin/sh\n", encoding="utf-8")
            script.chmod(0o755)
            config.write_text("{}\n", encoding="utf-8")

            RUNTIME.make_tree_immutable(root)

            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o555)
            self.assertEqual(stat.S_IMODE(script.stat().st_mode), 0o555)
            self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o444)

            RUNTIME.make_tree_writable(root)
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o755)
            self.assertEqual(stat.S_IMODE(script.stat().st_mode), 0o755)
            self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o644)


if __name__ == "__main__":
    unittest.main()
