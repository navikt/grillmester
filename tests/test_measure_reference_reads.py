from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_measure_reference_reads", ROOT / "scripts/measure_reference_reads.py"
)
assert SPEC is not None and SPEC.loader is not None
READS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = READS
SPEC.loader.exec_module(READS)

PROOF = "A sentence long enough to prove that this reference reached the model."
PROOFS = {"references/a.md": (PROOF,), "references/b.md": ("Another long proof line.",)}


def event(kind: str, data: dict[str, object] | None = None, **fields: object) -> str:
    return json.dumps({"type": kind, "data": data or {}, **fields})


def call(tool: str, call_id: str = "call", **arguments: object) -> str:
    return event(
        "tool.execution_start",
        {"toolName": tool, "toolCallId": call_id, "arguments": arguments},
    )


def output(text: str = "", success: bool = True, **fields: object) -> str:
    return event(
        "tool.execution_complete",
        {"toolCallId": "call", "success": success, "result": {"content": text}},
        **fields,
    )


def result() -> object:
    return READS.ReadResult("skill/references/a.md", 0)


class CoverageTests(unittest.TestCase):
    def test_every_reference_has_a_case_and_every_case_a_reference(self) -> None:
        references = {
            f"{skill.name}/{path.relative_to(skill).as_posix()}"
            for skill in (ROOT / "plugin/skills").iterdir()
            if (skill / "SKILL.md").is_file()
            for path in READS.SKILLS.disclosed_references(skill)
        }
        self.assertEqual(references, {case.id for case in READS.CASES})

    def test_cases_never_name_their_reference(self) -> None:
        for case in READS.CASES:
            with self.subTest(case=case.id):
                self.assertNotIn(Path(case.reference).name, case.prompt)

    def test_every_reference_can_be_proven_read(self) -> None:
        for case in READS.CASES:
            with self.subTest(case=case.id):
                path = ROOT / "plugin/skills" / case.skill / case.reference
                self.assertTrue(READS.fingerprints(path))


class EventTests(unittest.TestCase):
    def test_a_view_counts_as_a_read_of_that_reference(self) -> None:
        run = result()
        READS.read_events(
            [call("view", path="/plugin/skills/skill/references/a.md"), output()],
            run,
            "skill",
            PROOFS,
        )
        self.assertEqual(["references/a.md"], run.references)

    def test_a_failed_view_is_not_a_read(self) -> None:
        run = result()
        READS.read_events(
            [
                call("view", path="/plugin/skills/skill/references/a.md"),
                output("Permission denied", success=False),
            ],
            run,
            "skill",
            PROOFS,
        )
        self.assertEqual([], run.references)

    def test_text_in_a_tool_result_proves_a_read_through_the_shell(self) -> None:
        run = result()
        READS.read_events(
            [call("bash", command="cat references/*"), output(f"1. {PROOF}\n")],
            run,
            "skill",
            PROOFS,
        )
        self.assertEqual(["references/a.md"], run.references)

    def test_a_subagent_read_does_not_count(self) -> None:
        run = result()
        READS.read_events([output(PROOF, agentId="child")], run, "skill", PROOFS)
        self.assertEqual([], run.references)

    def test_the_read_must_come_before_the_first_edit(self) -> None:
        early, late = result(), result()
        view = call("view", path="/skills/skill/references/a.md")
        edit = call("edit", "edit", path="README.md")
        READS.read_events([view, output(), edit], early, "skill", PROOFS)
        READS.read_events([edit, view, output()], late, "skill", PROOFS)
        self.assertTrue(READS.read_before_edit(early, "references/a.md"))
        self.assertFalse(READS.read_before_edit(late, "references/a.md"))

    def test_each_reference_keeps_its_own_first_read(self) -> None:
        run = result()
        view_b = call("view", path="/skills/skill/references/b.md")
        view_a = call("view", path="/skills/skill/references/a.md")
        edit = call("edit", "edit", path="README.md")
        READS.read_events(
            [view_b, output(), edit, view_a, output()], run, "skill", PROOFS
        )
        self.assertTrue(READS.read_before_edit(run, "references/b.md"))
        self.assertFalse(READS.read_before_edit(run, "references/a.md"))

    def test_str_replace_editor_view_is_a_read_and_not_an_edit(self) -> None:
        run = result()
        READS.read_events(
            [
                call(
                    "str_replace_editor",
                    command="view",
                    path="/skills/skill/references/a.md",
                ),
                output(),
            ],
            run,
            "skill",
            PROOFS,
        )
        self.assertEqual(["references/a.md"], run.references)
        self.assertIsNone(run.first_edit)

    def test_the_last_allowed_call_still_counts(self) -> None:
        run = result()
        READS.read_events(
            [call("view", path="/skills/skill/references/a.md"), output()],
            run,
            "skill",
            PROOFS,
            limit=1,
        )
        self.assertEqual(["references/a.md"], run.references)

    def test_the_tool_limit_stops_a_run(self) -> None:
        run = result()
        stopped = READS.read_events(
            [call("view", path="README.md"), output()] * 3,
            run,
            "skill",
            PROOFS,
            limit=2,
        )
        self.assertTrue(stopped)
        self.assertEqual("tool limit", run.stopped)
        self.assertEqual(2, run.tool_calls)

    def test_loading_is_seen_from_the_tool_and_the_skill_event(self) -> None:
        tool, invoked = result(), result()
        READS.read_events([call("skill", skill="skill")], tool, "skill", PROOFS)
        READS.read_events(
            [event("skill.invoked", {"name": "skill"})], invoked, "skill", PROOFS
        )
        self.assertTrue(tool.loaded)
        self.assertTrue(invoked.loaded)


class FixtureTests(unittest.TestCase):
    def test_a_manual_skill_is_opened_only_in_the_measured_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            plugin = Path(temporary)
            skill = plugin / "skills/manual/SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(
                "---\nname: manual\ndisable-model-invocation: true\n---\n\nBody\n",
                encoding="utf-8",
            )
            READS.open_manual_skills(plugin)
            self.assertNotIn("disable-model-invocation", skill.read_text(encoding="utf-8"))

    def test_table_counts_reads_and_other_references(self) -> None:
        case = READS.Case("skill", "references/a.md", "Prompt")
        hit = READS.ReadResult(
            case.id,
            0,
            loaded=True,
            references=["references/a.md", "references/b.md"],
            first_reads={"references/a.md": 1},
        )
        miss = READS.ReadResult(case.id, 1, first_edit=1)
        table = READS.render_table((case,), (hit, miss))
        self.assertIn("| `skill/references/a.md` | 1/2 | 1/2 | 1/2 | `b.md` 1 |", table)
        self.assertIn("**1/2**", table)


if __name__ == "__main__":
    unittest.main()
