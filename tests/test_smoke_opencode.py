from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_opencode_smoke", ROOT / "scripts/smoke_opencode.py"
)
assert SPEC is not None and SPEC.loader is not None
SMOKE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SMOKE
SPEC.loader.exec_module(SMOKE)

TARGET = Path("/distribution/targets/opencode-v1")
POLICY = {
    "grillmester": {"mode": "primary", "hidden": False, "permission": {"bash": "ask"}},
    "doctor-who": {
        "mode": "primary",
        "hidden": False,
        "permission": {"bash": "deny", "task": "deny"},
    },
}


def rule(action: str, effect: str, resource: str = "*") -> dict[str, str]:
    return {"action": action, "resource": resource, "effect": effect}


def agent(agent_id: str, *extra: dict[str, str]) -> dict[str, Any]:
    return {
        "id": agent_id,
        "mode": "primary",
        "hidden": False,
        "permissions": [
            rule("external_directory", "ask"),
            rule("external_directory", "allow", f"{TARGET}/skills/*"),
            rule("execute", "deny"),
            rule("opencode_*", "deny"),
            *extra,
        ],
    }


def agents() -> list[dict[str, Any]]:
    return [
        agent("grillmester", rule("shell", "ask")),
        agent("doctor-who", rule("shell", "deny"), rule("subagent", "deny")),
    ]


def tool_result(index: int, content: str) -> dict[str, str]:
    return {"role": "tool", "tool_call_id": SMOKE.call_id(index), "content": content}


def session(**changes: Any) -> list[dict[str, Any]]:
    results = {
        "skill": f'<skill_content name="{SMOKE.SKILL_ID}">body',
        "reference": "Read file: # Reference heading",
        "outside": '{"error":{"type":"permission.rejected"}}',
        "write": '{"error":{"type":"permission.rejected"}}',
    }
    results.update({key: value for key, value in changes.items() if key in results})
    system = changes.get(
        "system", f"# Grillmester\n{SMOKE.CONSUMER_MARKER}\ntdd\nreview\n"
    )
    tools = changes.get("tools", sorted(SMOKE.REVIEWED_TOOLS))
    first = {
        "messages": [{"role": "system", "content": system}],
        "tools": [{"function": {"name": name}} for name in tools],
    }
    last = {
        "messages": [
            tool_result(index, content)
            for index, content in enumerate(
                (
                    results["skill"],
                    results["reference"],
                    results["outside"],
                    results["write"],
                )
            )
        ],
        "tools": first["tools"],
    }
    return [first, {}, {}, {}, last]


def validate(requests: list[dict[str, Any]]) -> None:
    SMOKE.validate_session(
        requests,
        steps=4,
        skills=("tdd", "review"),
        reference_line="# Reference heading",
    )


class AgentValidationTests(unittest.TestCase):
    def check(self, observed: list[dict[str, Any]]) -> None:
        SMOKE.validate_agents(observed, policy=POLICY, target=TARGET)

    def test_reviewed_agents_pass(self) -> None:
        self.check(agents())

    def test_every_policy_agent_must_load(self) -> None:
        with self.assertRaisesRegex(SMOKE.SmokeError, "did not load agent"):
            self.check(agents()[:1])

    def test_mode_and_hidden_must_match_the_policy(self) -> None:
        for field, value, message in (
            ("mode", "subagent", "has mode"),
            ("hidden", True, "hidden flag"),
        ):
            observed = agents()
            observed[0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                SMOKE.SmokeError, message
            ):
                self.check(observed)

    def test_each_target_rule_must_survive_into_the_agent(self) -> None:
        for removed, message in (
            (rule("external_directory", "ask"), "ask before leaving"),
            (
                rule("external_directory", "allow", f"{TARGET}/skills/*"),
                "bundled skills",
            ),
            (rule("execute", "deny"), "Code Mode"),
            (rule("opencode_*", "deny"), "own tools"),
        ):
            observed = agents()
            observed[0]["permissions"].remove(removed)
            with self.subTest(removed=removed), self.assertRaisesRegex(
                SMOKE.SmokeError, message
            ):
                self.check(observed)

    def test_a_later_rule_decides_the_effect(self) -> None:
        observed = agents()
        observed[1]["permissions"].append(rule("shell", "allow"))

        with self.assertRaisesRegex(SMOKE.SmokeError, "lost its shell deny"):
            self.check(observed)


class SessionValidationTests(unittest.TestCase):
    def test_complete_session_passes(self) -> None:
        validate(session())

    def test_session_must_finish_every_step(self) -> None:
        with self.assertRaisesRegex(SMOKE.SmokeError, "expected 5 agent requests"):
            validate(session()[:4])

    def test_system_prompt_must_carry_our_content(self) -> None:
        for system, message in (
            (f"{SMOKE.CONSUMER_MARKER}\ntdd\nreview\n", "Grillmester prompt"),
            ("# Grillmester\ntdd\nreview\n", "consumer's AGENTS.md"),
            (f"# Grillmester\n{SMOKE.CONSUMER_MARKER}\ntdd\n", "catalog lacks: review"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(
                SMOKE.SmokeError, message
            ):
                validate(session(system=system))

    def test_tools_must_match_the_reviewed_surface(self) -> None:
        with self.assertRaisesRegex(SMOKE.SmokeError, "tools are missing"):
            validate(session(tools=["read"]))
        with self.assertRaisesRegex(SMOKE.SmokeError, "Code Mode"):
            validate(session(tools=[*SMOKE.REVIEWED_TOOLS, "execute"]))

    def test_each_tool_result_is_checked(self) -> None:
        for changes, message in (
            ({"skill": "no such skill"}, "did not load"),
            ({"reference": "permission.rejected"}, "reference was not read"),
            ({"outside": SMOKE.OUTSIDE_MARKER}, "outside the project"),
            ({"write": "Wrote file"}, "without approval"),
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(
                SMOKE.SmokeError, message
            ):
                validate(session(**changes))

    def test_reference_path_follows_the_directory_the_skill_reports(self) -> None:
        skill = "body\nBase directory for this skill: /session/copy/skills/x\nmore\n"
        request = {"messages": [tool_result(0, skill)]}

        self.assertEqual(
            {"path": f"/session/copy/skills/x/{SMOKE.SKILL_REFERENCE}"},
            SMOKE._skill_reference(request),
        )


class ProbeProviderTests(unittest.TestCase):
    @staticmethod
    def post(port: int, body: dict[str, Any]) -> str:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            data=json.dumps(body).encode(),
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=5) as response:
            return response.read().decode()

    def test_script_runs_in_order_and_title_requests_do_not_consume_it(self) -> None:
        def later(request: dict[str, Any]) -> dict[str, str]:
            return {"path": request["seen"]}

        steps = (("skill", {"id": "tdd"}), ("read", later))
        agent_request = {"tools": [{}]}
        with SMOKE.ProbeProvider(steps) as provider:
            threading.Thread(target=provider.serve_forever, daemon=True).start()
            title = self.post(provider.port, {"tools": []})
            first = self.post(provider.port, agent_request)
            second = self.post(provider.port, {**agent_request, "seen": "/computed"})
            final = self.post(provider.port, agent_request)
            provider.shutdown()

        self.assertIn("Grillmester smoke", title)
        self.assertIn("skill", first)
        self.assertIn("/computed", second)
        self.assertIn(SMOKE.FINAL_TEXT, final)
        self.assertEqual(3, len(provider.requests))


class BinaryTests(unittest.TestCase):
    @staticmethod
    def executable(directory: Path, output: str) -> Path:
        binary = directory / "opencode"
        binary.write_text(f"#!/bin/sh\nprintf '%s\\n' '{output}'\n", encoding="utf-8")
        binary.chmod(0o700)
        return binary

    def test_only_the_exact_release_test_version_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            binary = self.executable(
                Path(directory), f"opencode v{SMOKE.EXPECTED_VERSION}"
            )
            SMOKE.verify_version(binary)
            binary = self.executable(Path(directory), "opencode v0.0.1")
            with self.assertRaisesRegex(SMOKE.SmokeError, "found 'opencode v0.0.1'"):
                SMOKE.verify_version(binary)

    def test_missing_binary_skips_unless_it_is_required(self) -> None:
        with mock.patch.object(SMOKE.shutil, "which", return_value=None):
            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(0, SMOKE.main([]))
            self.assertIn("Skipped", stdout.getvalue())
            with redirect_stderr(StringIO()):
                self.assertEqual(1, SMOKE.main(["--require-binary"]))

    def test_a_named_cplt_that_is_missing_is_an_error(self) -> None:
        def which(name: str) -> str | None:
            return "/bin/sh" if name == "opencode" else None

        stderr = StringIO()
        with mock.patch.object(SMOKE.shutil, "which", side_effect=which), mock.patch.object(
            SMOKE, "smoke"
        ) as smoke, redirect_stderr(stderr):
            self.assertEqual(1, SMOKE.main(["--cplt", "cplt"]))

        smoke.assert_not_called()
        self.assertIn("cplt not found", stderr.getvalue())

    def test_tree_digest_sees_content_but_not_git_bookkeeping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()
            (root / "file.txt").write_text("one", encoding="utf-8")
            before = SMOKE.tree_digest(root)
            (root / ".git/index").write_text("changed", encoding="utf-8")
            self.assertEqual(before, SMOKE.tree_digest(root))
            (root / "file.txt").write_text("two", encoding="utf-8")
            self.assertNotEqual(before, SMOKE.tree_digest(root))


if __name__ == "__main__":
    unittest.main()
