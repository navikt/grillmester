from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_measure_skill_routing", ROOT / "scripts/measure_skill_routing.py"
)
assert SPEC is not None and SPEC.loader is not None
ROUTING = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ROUTING
SPEC.loader.exec_module(ROUTING)


def result() -> object:
    return ROUTING.RunResult("tdd", 0, "grillmester", "model")


def event(kind: str, data: dict[str, object] | None = None, **fields: object) -> str:
    return json.dumps({"type": kind, "data": data or {}, **fields})


def skill_call(name: str, **fields: object) -> str:
    return event(
        "tool.execution_start",
        {"toolName": "skill", "arguments": {"skill": name}, "model": "model"},
        **fields,
    )


class ReadEventsTest(unittest.TestCase):
    def test_records_each_skill_once_and_stops_when_the_turn_ends(self) -> None:
        run = result()
        stopped = ROUTING.read_events(
            [skill_call("tdd"), skill_call("tdd"), event("assistant.turn_end")], run
        )

        self.assertTrue(stopped)
        self.assertEqual(["tdd"], run.skills)
        self.assertEqual("skill loaded", run.stopped)
        self.assertEqual(["model"], run.used_models)

    def test_a_delegated_agent_does_not_count(self) -> None:
        run = result()
        ROUTING.read_events([skill_call("review", agentId="child")], run)

        self.assertEqual([], run.skills)
        self.assertEqual(0, run.tool_calls)

    def test_a_turn_without_a_skill_keeps_the_session_running(self) -> None:
        run = result()

        self.assertFalse(ROUTING.read_events([event("assistant.turn_end")], run))

    def test_stops_at_the_tool_limit(self) -> None:
        run = result()
        calls = [
            event("tool.execution_start", {"toolName": "view"})
            for _ in range(ROUTING.MAX_TOOL_CALLS + 5)
        ]

        self.assertTrue(ROUTING.read_events(calls, run))
        self.assertEqual("tool limit", run.stopped)
        self.assertEqual(ROUTING.MAX_TOOL_CALLS, run.tool_calls)

    def test_reads_usage_and_skips_other_lines(self) -> None:
        run = result()
        ROUTING.read_events(
            ["not json", "[]", json.dumps({"type": "result", "usage": {"premiumRequests": 2}})],
            run,
        )

        self.assertEqual(2, run.premium_requests)


class ScenarioTest(unittest.TestCase):
    def test_every_expected_skill_and_agent_exists_and_ids_are_unique(self) -> None:
        skills = {path.name for path in (ROOT / "plugin/skills").iterdir()}
        agents = {
            path.name.removesuffix(".agent.md")
            for path in (ROOT / "plugin/agents").glob("*.agent.md")
        }
        ids = [scenario.id for scenario in ROUTING.SCENARIOS]

        self.assertEqual(len(ids), len(set(ids)))
        for scenario in ROUTING.SCENARIOS:
            with self.subTest(scenario=scenario.id):
                self.assertLessEqual(set(scenario.expected), skills)
                self.assertIn(scenario.agent, agents)

    def test_a_hit_is_any_expected_skill_or_none_when_none_is_expected(self) -> None:
        wanted = ROUTING.Scenario("a", "prompt", ("tdd",))
        nothing = ROUTING.Scenario("b", "prompt", ())

        self.assertTrue(ROUTING.scenario_hit(wanted, ["review", "tdd"]))
        self.assertFalse(ROUTING.scenario_hit(wanted, ["review"]))
        self.assertTrue(ROUTING.scenario_hit(nothing, []))
        self.assertFalse(ROUTING.scenario_hit(nothing, ["tdd"]))

    def test_summary_counts_hits_and_loads(self) -> None:
        scenario = ROUTING.Scenario("a", "prompt", ("tdd",))
        runs = [
            ROUTING.RunResult("a", 0, "grillmester", "m", skills=["tdd"]),
            ROUTING.RunResult("a", 1, "grillmester", "m", skills=["review"]),
            ROUTING.RunResult("a", 2, "grillmester", "m"),
        ]

        rows = ROUTING.summarize([scenario], runs)

        self.assertEqual(1, rows[0]["hits"])
        self.assertEqual(1, rows[0]["noSkill"])
        self.assertEqual({"tdd": 1, "review": 1}, rows[0]["loads"])
        self.assertIn("| `a` | grillmester | 1/3 | 1 |", ROUTING.render_table(rows))


class FixtureTest(unittest.TestCase):
    def test_the_fixture_has_a_branch_ahead_of_main(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ROUTING.write_fixture(root)
            changed = subprocess.run(
                ("git", "-C", str(root), "diff", "--name-only", "main...HEAD"),
                check=True,
                capture_output=True,
                text=True,
            ).stdout.split()

        self.assertEqual([ROUTING.FEATURE_FILE], changed)

    def test_model_pins_are_removed_from_a_copy_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "plugin"
            (source / "agents").mkdir(parents=True)
            agent = source / "agents/one.agent.md"
            agent.write_text('---\nname: one\nmodel: "x"\n---\n', encoding="utf-8")
            copy = Path(directory) / "copy"

            ROUTING.copy_plugin_without_model_pins(source, copy)

            self.assertIn("model:", agent.read_text(encoding="utf-8"))
            self.assertEqual(
                "---\nname: one\n---\n",
                (copy / "agents/one.agent.md").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
