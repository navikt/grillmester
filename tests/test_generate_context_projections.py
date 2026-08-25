from __future__ import annotations

import importlib.util
import hashlib
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_generate_context_projections",
    ROOT / "scripts/generate_context_projections.py",
)
assert SPEC and SPEC.loader
GENERATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GENERATOR
SPEC.loader.exec_module(GENERATOR)


class FocusedContextGenerationTest(unittest.TestCase):
    def copy_repository(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name) / "grillmester"
        shutil.copytree(
            ROOT,
            root,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )
        return temporary, root

    def test_focused_targets_have_the_exact_reviewed_roster(self) -> None:
        projections, _ = GENERATOR.build_projections(ROOT)
        opencode = projections["opencode"]
        copilot = projections["copilotCli"]
        opencode_manifest = json.loads(opencode["manifest.json"][0])
        copilot_manifest = json.loads(copilot["manifest.json"][0])

        self.assertEqual(
            {"agents": 2, "skills": 7, "commands": 7},
            opencode_manifest["counts"],
        )
        self.assertEqual(
            {"agents": 2, "skills": 7},
            copilot_manifest["counts"],
        )
        self.assertEqual(
            {
                "agents/barista.md",
                "agents/grill-inspektor.md",
            },
            {path for path in opencode if path.startswith("agents/")},
        )
        self.assertEqual(
            {
                "commands/grillmester-diagnosing-bugs.md",
                "commands/grillmester-integration-tests.md",
                "commands/grillmester-issue-management.md",
                "commands/grillmester-pull-request.md",
                "commands/grillmester-review.md",
                "commands/grillmester-security-review.md",
                "commands/grillmester-tdd.md",
            },
            {path for path in opencode if path.startswith("commands/")},
        )
        self.assertEqual(
            {
                "agents/barista.agent.md",
                "agents/grill-inspektor.agent.md",
            },
            {path for path in copilot if path.startswith("agents/")},
        )
        expected_skills = {
            "grillmester-diagnosing-bugs",
            "grillmester-integration-tests",
            "grillmester-issue-management",
            "grillmester-pull-request",
            "grillmester-review",
            "grillmester-security-review",
            "grillmester-tdd",
        }
        for target, files in (("opencode", opencode), ("copilotCli", copilot)):
            with self.subTest(target=target):
                self.assertEqual(
                    expected_skills,
                    {
                        path.split("/", 2)[1]
                        for path in files
                        if path.startswith("skills/")
                    },
                )

    def test_focused_content_is_derived_with_only_the_reviewed_transforms(self) -> None:
        projections, _ = GENERATOR.build_projections(ROOT)
        opencode = projections["opencode"]
        copilot = projections["copilotCli"]

        changed_opencode: set[str] = set()
        for relative, (data, mode) in opencode.items():
            if relative == "manifest.json":
                continue
            source = ROOT / "targets/opencode-v1" / relative
            with self.subTest(target="opencode", path=relative):
                self.assertEqual(source.stat().st_mode & 0o7777, mode)
                if source.read_bytes() != data:
                    changed_opencode.add(relative)
        self.assertEqual(
            {
                "agents/barista.md",
                "agents/grill-inspektor.md",
                "commands/grillmester-integration-tests.md",
                "commands/grillmester-tdd.md",
                "skills/grillmester-diagnosing-bugs/SKILL.md",
                "skills/grillmester-integration-tests/SKILL.md",
                "skills/grillmester-issue-management/SKILL.md",
                "skills/grillmester-review/SKILL.md",
                "skills/grillmester-tdd/SKILL.md",
                "skills/grillmester-tdd/tests.md",
            },
            changed_opencode,
        )

        self.assertEqual(
            (ROOT / "plugin/plugin.json").read_bytes(), copilot["plugin.json"][0]
        )
        changed_copilot: set[str] = set()
        for relative, (data, mode) in copilot.items():
            if relative == "manifest.json":
                continue
            source = ROOT / "plugin" / relative
            with self.subTest(target="copilotCli", path=relative):
                self.assertEqual(source.stat().st_mode & 0o7777, mode)
                if source.read_bytes() != data:
                    changed_copilot.add(relative)
        self.assertEqual(
            {
                "agents/barista.agent.md",
                "agents/grill-inspektor.agent.md",
                "skills/grillmester-diagnosing-bugs/SKILL.md",
                "skills/grillmester-integration-tests/SKILL.md",
                "skills/grillmester-issue-management/SKILL.md",
                "skills/grillmester-review/SKILL.md",
                "skills/grillmester-tdd/SKILL.md",
                "skills/grillmester-tdd/tests.md",
            },
            changed_copilot,
        )

        for agent in ("barista", "grill-inspektor"):
            relative = f"agents/{agent}.agent.md"
            source = (ROOT / "plugin" / relative).read_text(encoding="utf-8")
            focused = copilot[relative][0].decode("utf-8")
            self.assertRegex(source.split("---", 2)[1], r'(?m)^model: "gpt-5\.6-sol"$')
            self.assertNotRegex(focused.split("---", 2)[1], r"(?m)^model:")

        opencode_manifest = json.loads(opencode["manifest.json"][0])
        self.assertEqual(
            {
                "agentEscalation": "full-context-handoff",
                "excludedSkillReferences": "full-context-guidance",
                "skillPermissionEntriesRemoved": [
                    "grillmester-doctor",
                    "grillmester-grill-me",
                    "grillmester-grill-with-docs",
                    "grillmester-guided-review",
                    "grillmester-handoff",
                ],
            },
            opencode_manifest["transformations"],
        )
        copilot_manifest = json.loads(copilot["manifest.json"][0])
        self.assertEqual("private-cli-only", copilot_manifest["distribution"])
        self.assertEqual(
            {
                "plugin": "plugin",
                "payloadManifest": "plugin/manifest.json",
                "payloadManifestSha256": hashlib.sha256(
                    (ROOT / "plugin/manifest.json").read_bytes()
                ).hexdigest(),
                "policy": "policy/focused-context-v1.json",
                "policySha256": hashlib.sha256(
                    (ROOT / "policy/focused-context-v1.json").read_bytes()
                ).hexdigest(),
            },
            copilot_manifest["source"],
        )
        self.assertEqual(
            {
                "agentFrontmatterRemoved": ["model"],
                "agentEscalation": "full-context-handoff",
                "excludedSkillReferences": "full-context-guidance",
            },
            copilot_manifest["transformations"],
        )

    def test_committed_focused_targets_are_current(self) -> None:
        projections, policy = GENERATOR.build_projections(ROOT)

        for key, expected in projections.items():
            output = ROOT / policy["outputs"][key]
            with self.subTest(target=key):
                self.assertEqual([], GENERATOR.compare_projection(output, expected))

    def test_tampered_full_opencode_source_is_rejected(self) -> None:
        temporary, root = self.copy_repository()
        try:
            source = root / "targets/opencode-v1/agents/barista.md"
            source.write_text(source.read_text(encoding="utf-8") + "tampered\n")

            with self.assertRaisesRegex(
                GENERATOR.ProjectionError,
                "OpenCode source differs from its manifest.*agents/barista.md",
            ):
                GENERATOR.build_projections(root)
        finally:
            temporary.cleanup()

    def test_tampered_or_unmanifested_full_copilot_source_is_rejected(self) -> None:
        temporary, root = self.copy_repository()
        try:
            source = root / "plugin/skills/grillmester-okr/SKILL.md"
            source.write_text(source.read_text(encoding="utf-8") + "tampered\n")
            with self.assertRaisesRegex(
                GENERATOR.ProjectionError,
                "Copilot full payload source differs from its manifest.*grillmester-okr",
            ):
                GENERATOR.build_projections(root)

            shutil.copy2(ROOT / "plugin/skills/grillmester-okr/SKILL.md", source)
            (root / "plugin/unmanifested.md").write_text(
                "unexpected\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                GENERATOR.ProjectionError,
                "Copilot full payload source differs from its manifest.*unmanifested",
            ):
                GENERATOR.build_projections(root)
        finally:
            temporary.cleanup()

    def test_policy_cannot_redirect_a_focused_output_over_a_canonical_source(self) -> None:
        temporary, root = self.copy_repository()
        try:
            policy_path = root / "policy/focused-context-v1.json"
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["outputs"]["copilotCli"] = "plugin"
            policy_path.write_text(
                json.dumps(policy, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                GENERATOR.ProjectionError,
                "policy outputs must name the reviewed focused target paths",
            ):
                GENERATOR.build_projections(root)
        finally:
            temporary.cleanup()

    def test_focused_references_resolve_inside_the_focused_roster(self) -> None:
        projections, _ = GENERATOR.build_projections(ROOT)
        allowed_agents = {"barista", "grill-inspektor"}
        allowed_skills = {
            "grillmester-diagnosing-bugs",
            "grillmester-integration-tests",
            "grillmester-issue-management",
            "grillmester-pull-request",
            "grillmester-review",
            "grillmester-security-review",
            "grillmester-tdd",
        }
        agent_reference = re.compile(r"(?<![a-z0-9-])grillmester:([a-z][a-z0-9-]*)")
        skill_reference = re.compile(r"(?<![a-z0-9-])(grillmester-[a-z][a-z0-9-]*)")

        for target, files in projections.items():
            for relative, (data, _) in files.items():
                if relative in {"manifest.json", "plugin.json"}:
                    continue
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                with self.subTest(target=target, path=relative):
                    self.assertLessEqual(
                        set(agent_reference.findall(text)), allowed_agents
                    )
                    self.assertLessEqual(
                        set(skill_reference.findall(text)), allowed_skills
                    )

        for target, relative in (
            ("opencode", "agents/barista.md"),
            ("copilotCli", "agents/barista.agent.md"),
        ):
            body = projections[target][relative][0].decode("utf-8")
            self.assertIn("Status: NEEDS_FULL_CONTEXT", body)
            self.assertIn("grillmester local --full", body)


if __name__ == "__main__":
    unittest.main()
