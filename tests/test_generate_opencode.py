from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_generate_opencode", ROOT / "scripts/generate_opencode.py"
)
assert SPEC and SPEC.loader
GENERATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GENERATOR
SPEC.loader.exec_module(GENERATOR)


class OpenCodeGenerationTest(unittest.TestCase):
    def copy_repository(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name) / "grillmester"
        shutil.copytree(
            ROOT,
            root,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )
        return temporary, root

    def expected(self, relative: str) -> str:
        files, _ = GENERATOR.build_projection(ROOT)
        return files[relative][0].decode("utf-8")

    def test_committed_projection_is_current(self) -> None:
        expected, policy = GENERATOR.build_projection(ROOT)
        output = ROOT / policy["output"]
        self.assertEqual([], GENERATOR.compare_projection(output, expected))

    def test_target_has_native_plural_layout_and_complete_counts(self) -> None:
        files, _ = GENERATOR.build_projection(ROOT)
        manifest = json.loads(files["manifest.json"][0])

        self.assertEqual(
            {"$schema": "https://opencode.ai/config.json"},
            json.loads(files["opencode.json"][0]),
        )
        self.assertEqual(7, manifest["counts"]["agents"])
        self.assertEqual(4, manifest["counts"]["primaryAgents"])
        self.assertEqual(3, manifest["counts"]["subagents"])
        self.assertEqual(42, manifest["counts"]["skills"])
        self.assertEqual(42, manifest["counts"]["commands"])
        self.assertEqual(7, sum(path.startswith("agents/") for path in files))
        self.assertEqual(42, sum(path.startswith("commands/") for path in files))
        self.assertEqual(
            42,
            sum(path.startswith("skills/") and path.endswith("/SKILL.md") for path in files),
        )
        self.assertIn("node_modules/", files[".gitignore"][0].decode("utf-8"))
        self.assertIn("opencode.json", manifest["files"])

    def test_agents_use_native_frontmatter_and_inherit_the_selected_model(self) -> None:
        grillmester = self.expected("agents/grillmester.md")
        kokk = self.expected("agents/kokk.md")
        inspector = self.expected("agents/grill-inspektor.md")
        researcher = self.expected("agents/researcher.md")

        self.assertIn("mode: primary\nhidden: false", grillmester)
        self.assertIn("mode: subagent\nhidden: true", kokk)
        self.assertNotRegex(grillmester.split("---", 2)[1], r"(?m)^model:")
        self.assertNotRegex(kokk.split("---", 2)[1], r"(?m)^model:")
        self.assertIn("  edit: ask\n  bash: ask", kokk)
        self.assertIn("  bash: ask\n  edit: deny", inspector)
        self.assertIn("  webfetch: allow\n  websearch: allow", researcher)
        self.assertIn("    kokk: allow", grillmester)
        self.assertIn("    grill-inspektor: allow", grillmester)
        self.assertIn("    researcher: allow", grillmester)

        designer = self.expected("agents/designer.md")
        self.assertIn(
            '  bash:\n    "*": deny\n'
            '    "node scripts/server.js --project-dir *": ask\n'
            '    "node *grillmester-design-prototype/scripts/server.js --project-dir *": ask',
            designer,
        )
        self.assertIn(
            '    "node scripts/server.js * --cleanup-all*": deny', designer
        )
        self.assertNotIn("  bash: allow", designer)
        bash_policy = designer.split("  bash:\n", 1)[1].split("  skill:\n", 1)[0]
        self.assertLess(
            bash_policy.index('    "*": deny'),
            bash_policy.index('    "node scripts/server.js --project-dir *": ask'),
        )
        self.assertLess(
            bash_policy.index('    "node scripts/server.js --project-dir *": ask'),
            bash_policy.index('    "node scripts/server.js * --cleanup-all*": deny'),
        )
        self.assertNotIn("kill *", bash_policy)

    def test_runtime_vocabulary_is_adapted_fail_closed(self) -> None:
        files, _ = GENERATOR.build_projection(ROOT)
        text = "\n".join(
            data.decode("utf-8")
            for path, (data, _) in files.items()
            if path.endswith(".md")
        )
        for token in (
            "ask_user",
            "`execute`",
            "`web`",
            "agent task tool",
            "`agent` tool",
            "grillmester:kokk",
            "grillmester:researcher",
        ):
            self.assertNotIn(token, text)
        self.assertIsNone(GENERATOR.SLASH_SKILL_REFERENCE.search(text))
        self.assertIn("`question`", text)
        self.assertIn("`task` tool", text)
        self.assertIn("`webfetch` or `websearch`", text)
        self.assertIn("Load them with the native `skill` tool", text)

        grillmester = files["agents/grillmester.md"][0].decode("utf-8")
        review = files["skills/grillmester-review/SKILL.md"][0].decode("utf-8")
        self.assertIn("`grillmester-security-review`", grillmester)
        self.assertIn(GENERATOR.TARGET_INVOCATION_NOTE, grillmester)
        self.assertIn(GENERATOR.TARGET_INVOCATION_NOTE, review)
        for path, (data, _) in files.items():
            if path.startswith("agents/") or (
                path.startswith("skills/") and path.endswith("/SKILL.md")
            ):
                with self.subTest(target=path):
                    self.assertIn(
                        GENERATOR.TARGET_INVOCATION_NOTE, data.decode("utf-8")
                    )
            if path.startswith("commands/"):
                with self.subTest(command=path):
                    command = data.decode("utf-8")
                    self.assertIn("Use the `skill` tool to load", command)
                    self.assertNotIn(GENERATOR.TARGET_INVOCATION_NOTE, command)

    def test_manual_only_source_skills_use_ordered_ask_approximation(self) -> None:
        files, _ = GENERATOR.build_projection(ROOT)
        agent = files["agents/grillmester.md"][0].decode("utf-8")
        manifest = json.loads(files["manifest.json"][0])
        manual = manifest["manualOnlyApproximation"]

        self.assertTrue(manual["lastMatchWins"])
        self.assertTrue(manual["explicitCommandWrapper"])
        wildcard = agent.index('  skill:\n    "*": allow')
        for skill_id in manual["skills"]:
            self.assertGreater(agent.index(f"    {skill_id}: ask"), wildcard)
            command = files[f"commands/{skill_id}.md"][0].decode("utf-8")
            self.assertIn(f"load `{skill_id}`", command)
            self.assertIn("$ARGUMENTS", command)
        self.assertEqual("  skill: deny", self._permission_line(files, "researcher", "skill"))

    def _permission_line(
        self, files: dict[str, tuple[bytes, int]], agent_id: str, tool: str
    ) -> str:
        text = files[f"agents/{agent_id}.md"][0].decode("utf-8")
        return next(line for line in text.splitlines() if line.startswith(f"  {tool}:"))

    def test_copilot_specific_skills_have_explicit_native_overlays(self) -> None:
        files, _ = GENERATOR.build_projection(ROOT)
        manifest = json.loads(files["manifest.json"][0])
        doctor = files["skills/grillmester-doctor/SKILL.md"][0].decode("utf-8")
        creator = files["skills/grillmester-create-a-skill/SKILL.md"][0].decode("utf-8")

        self.assertEqual("overlay", manifest["skillCapabilities"]["grillmester-doctor"])
        self.assertEqual(
            "overlay", manifest["skillCapabilities"]["grillmester-create-a-skill"]
        )
        self.assertIn("Grillmester Doctor for OpenCode v1", doctor)
        self.assertIn("OpenCode-compatible Agent Skill", creator)
        self.assertNotIn("Copilot", doctor)
        self.assertNotIn("Copilot", creator)
        self.assertNotIn(
            "skills/grillmester-create-a-skill/references/copilot-cli-validation.md",
            files,
        )
        self.assertIn(
            "skills/grillmester-create-a-skill/references/opencode-validation.md",
            files,
        )

    def test_skill_tree_resources_are_copied_and_executable_mode_is_preserved(self) -> None:
        files, _ = GENERATOR.build_projection(ROOT)
        source = ROOT / "plugin/skills/grillmester-design-prototype/scripts/server.js"
        target_data, target_mode = files[
            "skills/grillmester-design-prototype/scripts/server.js"
        ]
        self.assertEqual(source.read_bytes(), target_data)
        self.assertEqual(0o644, target_mode)

        script_data, script_mode = files[
            "skills/grillmester-diagnosing-bugs/scripts/hitl-loop.template.sh"
        ]
        self.assertEqual(
            (
                ROOT
                / "plugin/skills/grillmester-diagnosing-bugs/scripts/hitl-loop.template.sh"
            ).read_bytes(),
            script_data,
        )
        self.assertEqual(0o755, script_mode)

    def test_check_detects_drift_without_rewriting_output(self) -> None:
        temporary, root = self.copy_repository()
        try:
            target = root / "targets/opencode-v1/agents/grillmester.md"
            target.write_text("stale\n", encoding="utf-8")
            before = target.read_bytes()
            expected, policy = GENERATOR.build_projection(root)
            differences = GENERATOR.compare_projection(root / policy["output"], expected)
            self.assertTrue(any("grillmester.md" in item for item in differences))
            self.assertEqual(before, target.read_bytes())
        finally:
            temporary.cleanup()

    def test_runtime_dependency_artifacts_are_ignored_and_preserved(self) -> None:
        temporary, root = self.copy_repository()
        try:
            output = root / "targets/opencode-v1"
            (output / "package.json").write_text("{}\n", encoding="utf-8")
            (output / "bun.lock").write_text("runtime\n", encoding="utf-8")
            dependency = output / "node_modules/example/index.js"
            dependency.parent.mkdir(parents=True)
            dependency.write_text("runtime\n", encoding="utf-8")

            expected, policy = GENERATOR.build_projection(root)
            self.assertEqual(
                [], GENERATOR.compare_projection(root / policy["output"], expected)
            )
            self.assertFalse(GENERATOR.update_projection(output, expected))
            self.assertTrue(dependency.is_file())
            self.assertTrue((output / "package.json").is_file())
        finally:
            temporary.cleanup()

    def test_unknown_qualified_agent_reference_is_rejected(self) -> None:
        temporary, root = self.copy_repository()
        try:
            source = root / "plugin/agents/grillmester.agent.md"
            source.write_text(
                source.read_text(encoding="utf-8")
                + "\nDelegate to `grillmester:unknown-role`.\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(GENERATOR.ProjectionError, "unknown qualified agent"):
                GENERATOR.build_projection(root)
        finally:
            temporary.cleanup()

    def test_casefolded_target_collision_is_rejected(self) -> None:
        files: dict[str, tuple[bytes, int]] = {}
        casefolded: dict[str, str] = {}
        GENERATOR.add_file(files, casefolded, "agents/Kokk.md", b"one")
        with self.assertRaisesRegex(GENERATOR.ProjectionError, "collision"):
            GENERATOR.add_file(files, casefolded, "agents/kokk.md", b"two")

    def test_overlay_classification_cannot_silently_drift(self) -> None:
        temporary, root = self.copy_repository()
        try:
            policy_path = root / "policy/opencode-v1.json"
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["skillCapabilities"]["overrides"]["grillmester-doctor"] = "native"
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(
                GENERATOR.ProjectionError, "classification must exactly match"
            ):
                GENERATOR.build_projection(root)
        finally:
            temporary.cleanup()

    def test_plugin_release_version_does_not_change_native_target_bytes(self) -> None:
        temporary, root = self.copy_repository()
        try:
            before, _ = GENERATOR.build_projection(root)
            plugin_path = root / "plugin/plugin.json"
            plugin = json.loads(plugin_path.read_text(encoding="utf-8"))
            plugin["version"] = "99.0.0"
            plugin_path.write_text(json.dumps(plugin), encoding="utf-8")
            after, _ = GENERATOR.build_projection(root)
            self.assertEqual(before, after)
        finally:
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
