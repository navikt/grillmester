from __future__ import annotations

import importlib.util
import json
import os
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

    def test_json_loading_rejects_duplicate_keys_and_nonstandard_constants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate.json"
            cases = (
                ('{"field": 1, "field": 2}', "duplicate JSON key"),
                ('{"field": NaN}', "non-standard JSON constant"),
                ('{"field": Infinity}', "non-standard JSON constant"),
                ('{"field": -Infinity}', "non-standard JSON constant"),
            )
            for content, pattern in cases:
                with self.subTest(content=content):
                    candidate.write_text(content, encoding="utf-8")
                    with self.assertRaisesRegex(GENERATOR.ProjectionError, pattern):
                        GENERATOR.load_object(candidate, label="test JSON")
            candidate.write_bytes(b'{"field":"\xff"}')
            with self.assertRaisesRegex(GENERATOR.ProjectionError, "not UTF-8"):
                GENERATOR.load_object(candidate, label="test JSON")

    def test_json_loading_rejects_excessive_nesting_without_a_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "deep.json"
            nested: object = "leaf"
            for _ in range(GENERATOR.MAX_JSON_DEPTH + 2):
                nested = {"child": nested}
            candidate.write_text(json.dumps({"root": nested}), encoding="utf-8")

            with self.assertRaisesRegex(GENERATOR.ProjectionError, "nesting limit"):
                GENERATOR.load_object(candidate, label="deep JSON")

    def test_policy_top_level_fields_are_exact(self) -> None:
        temporary, root = self.copy_repository()
        try:
            policy_path = root / "policy/opencode-v1.json"
            original = json.loads(policy_path.read_text(encoding="utf-8"))
            cases = (
                (
                    {**original, "forbiddenRuntimeToken": []},
                    "unexpected.*forbiddenRuntimeToken",
                ),
                (
                    {
                        key: value
                        for key, value in original.items()
                        if key != "forbiddenRuntimeTokens"
                    },
                    "missing.*forbiddenRuntimeTokens",
                ),
            )
            for policy, pattern in cases:
                with self.subTest(pattern=pattern):
                    policy_path.write_text(
                        json.dumps(policy, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(GENERATOR.ProjectionError, pattern):
                        GENERATOR.build_projection(root)
        finally:
            temporary.cleanup()

    def test_committed_projection_is_current(self) -> None:
        expected, policy = GENERATOR.build_projection(ROOT)
        output = ROOT / policy["output"]
        self.assertEqual([], GENERATOR.compare_projection(output, expected))

    def test_target_has_native_plural_layout_and_complete_counts(self) -> None:
        files, _ = GENERATOR.build_projection(ROOT)
        manifest = json.loads(files["manifest.json"][0])

        self.assertEqual(
            {
                "$schema": "https://opencode.ai/config.json",
                "autoupdate": False,
                "share": "disabled",
            },
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
        self.assertNotIn(".gitignore", files)
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
        self.assertNotRegex(researcher.split("---", 2)[1], r"(?m)^  webfetch:")
        self.assertNotRegex(researcher.split("---", 2)[1], r"(?m)^  websearch:")
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

    def test_agents_leave_runtime_read_and_external_guards_unshadowed(self) -> None:
        files, _ = GENERATOR.build_projection(ROOT)

        for agent_id in (
            "barista",
            "designer",
            "doctor-who",
            "grill-inspektor",
            "grillmester",
            "kokk",
            "researcher",
        ):
            with self.subTest(agent=agent_id):
                frontmatter = files[f"agents/{agent_id}.md"][0].decode("utf-8").split(
                    "---", 2
                )[1]
                self.assertNotRegex(frontmatter, r'(?m)^  "\*":')
                self.assertNotRegex(frontmatter, r"(?m)^  read:")
                self.assertNotRegex(frontmatter, r"(?m)^  external_directory:")

    def test_policy_cannot_shadow_runtime_read_rules(self) -> None:
        temporary, root = self.copy_repository()
        try:
            policy_path = root / "policy/opencode-v1.json"
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["agents"]["barista"]["permission"]["read"] = "allow"
            policy_path.write_text(
                json.dumps(policy, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                GENERATOR.ProjectionError, "must leave read to OpenCode"
            ):
                GENERATOR.build_projection(root)
        finally:
            temporary.cleanup()

    def test_policy_cannot_shadow_runtime_guards_with_a_permission_wildcard(self) -> None:
        temporary, root = self.copy_repository()
        try:
            policy_path = root / "policy/opencode-v1.json"
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["agents"]["kokk"]["permission"]["*"] = "deny"
            policy_path.write_text(
                json.dumps(policy, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                GENERATOR.ProjectionError,
                "must not use a wildcard that shadows OpenCode runtime guards",
            ):
                GENERATOR.build_projection(root)
        finally:
            temporary.cleanup()

    def test_policy_cannot_replace_dynamic_external_directory_guards(self) -> None:
        temporary, root = self.copy_repository()
        try:
            policy_path = root / "policy/opencode-v1.json"
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["agents"]["researcher"]["permission"][
                "external_directory"
            ] = "allow"
            policy_path.write_text(
                json.dumps(policy, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                GENERATOR.ProjectionError,
                "must leave external_directory to OpenCode",
            ):
                GENERATOR.build_projection(root)
        finally:
            temporary.cleanup()

    def test_policy_permission_patterns_cannot_be_nested(self) -> None:
        temporary, root = self.copy_repository()
        try:
            policy_path = root / "policy/opencode-v1.json"
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["agents"]["barista"]["permission"]["bash"] = {
                "git *": {"status": "allow"}
            }
            policy_path.write_text(
                json.dumps(policy, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                GENERATOR.ProjectionError, "git \\*.*must be one of"
            ):
                GENERATOR.build_projection(root)
        finally:
            temporary.cleanup()

    def test_policy_rejects_unknown_and_generator_owned_permission_tools(self) -> None:
        temporary, root = self.copy_repository()
        try:
            policy_path = root / "policy/opencode-v1.json"
            original = json.loads(policy_path.read_text(encoding="utf-8"))
            for tool, pattern in (
                ("webftech", "unsupported permission tools.*webftech"),
                ("skill", "skill policy through skillAccess"),
            ):
                with self.subTest(tool=tool):
                    policy = json.loads(json.dumps(original))
                    policy["agents"]["barista"]["permission"][tool] = "allow"
                    policy_path.write_text(
                        json.dumps(policy, indent=2) + "\n", encoding="utf-8"
                    )
                    with self.assertRaisesRegex(GENERATOR.ProjectionError, pattern):
                        GENERATOR.build_projection(root)
        finally:
            temporary.cleanup()

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

    def test_check_detects_exact_mode_drift_and_special_nodes(self) -> None:
        temporary, root = self.copy_repository()
        try:
            output = root / "targets/opencode-v1"
            expected, _ = GENERATOR.build_projection(root)
            target = output / "agents/grillmester.md"
            target.chmod(0o600)
            differences = GENERATOR.compare_projection(output, expected)
            self.assertTrue(
                any("mode differs" in item and "0600" in item for item in differences)
            )

            if not hasattr(os, "mkfifo"):
                self.skipTest("FIFO fixture is not supported on this platform")
            fifo = output / "unexpected.fifo"
            os.mkfifo(fifo)
            differences = GENERATOR.compare_projection(output, expected)
            self.assertTrue(any("non-regular node" in item for item in differences))
            with self.assertRaisesRegex(GENERATOR.ProjectionError, "non-regular nodes"):
                GENERATOR.update_projection(output, expected)
        finally:
            temporary.cleanup()

    def test_runtime_dependency_artifacts_are_rejected_and_removed(self) -> None:
        temporary, root = self.copy_repository()
        try:
            output = root / "targets/opencode-v1"
            (output / "package.json").write_text("{}\n", encoding="utf-8")
            (output / "bun.lock").write_text("runtime\n", encoding="utf-8")
            dependency = output / "node_modules/example/index.js"
            dependency.parent.mkdir(parents=True)
            dependency.write_text("runtime\n", encoding="utf-8")

            expected, policy = GENERATOR.build_projection(root)
            differences = GENERATOR.compare_projection(
                root / policy["output"], expected
            )
            self.assertTrue(any("package.json" in item for item in differences))
            self.assertTrue(any("bun.lock" in item for item in differences))
            self.assertTrue(any("node_modules" in item for item in differences))

            self.assertTrue(GENERATOR.update_projection(output, expected))
            self.assertFalse(dependency.exists())
            self.assertFalse((output / "node_modules").exists())
            self.assertFalse((output / "package.json").exists())
            self.assertFalse((output / "bun.lock").exists())
            self.assertEqual([], GENERATOR.compare_projection(output, expected))
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

    def test_unicode_normalized_target_collision_is_rejected(self) -> None:
        files: dict[str, tuple[bytes, int]] = {}
        casefolded: dict[str, str] = {}
        GENERATOR.add_file(files, casefolded, "skills/caf\u00e9/SKILL.md", b"one")
        with self.assertRaisesRegex(GENERATOR.ProjectionError, "collision"):
            GENERATOR.add_file(
                files,
                casefolded,
                "skills/cafe\u0301/SKILL.md",
                b"two",
            )

    def test_unicode_normalized_path_index_can_be_removed_and_reused(self) -> None:
        files: dict[str, tuple[bytes, int]] = {}
        casefolded: dict[str, str] = {}
        decomposed = "skills/cafe\u0301/reference.md"
        precomposed = "skills/caf\u00e9/reference.md"

        GENERATOR.add_file(files, casefolded, decomposed, b"first")
        GENERATOR.remove_file(files, casefolded, decomposed)
        self.assertEqual({}, files)
        self.assertEqual({}, casefolded)

        GENERATOR.add_file(files, casefolded, precomposed, b"replacement")
        self.assertEqual(precomposed, casefolded[GENERATOR.portable_path_key(decomposed)])

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
