from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_validate", ROOT / "scripts/validate.py"
)
assert SPEC and SPEC.loader
VALIDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATE)


class PackageValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "package"
        shutil.copytree(
            ROOT,
            self.root,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def errors(self) -> list[str]:
        return VALIDATE.validate_repo(self.root)

    def load_json(self, relative_path: str) -> dict:
        path = self.root / relative_path
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, relative_path: str, value: dict) -> None:
        path = self.root / relative_path
        path.write_text(json.dumps(value), encoding="utf-8")

    def replace_frontmatter(
        self, relative_path: str, key: str, value: str, *, quoted: bool = False
    ) -> None:
        path = self.root / relative_path
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        closing = lines.index("---", 1)
        for index in range(1, closing):
            if lines[index].startswith(f"{key}:"):
                rendered = json.dumps(value) if quoted else value
                lines[index] = f"{key}: {rendered}"
                path.write_text(
                    "\n".join(lines) + ("\n" if text.endswith("\n") else ""),
                    encoding="utf-8",
                )
                return
        self.fail(f"frontmatter key {key!r} not found in {relative_path}")

    def assert_error(self, fragment: str) -> None:
        errors = self.errors()
        self.assertTrue(
            any(fragment in error for error in errors),
            f"expected {fragment!r} in validation errors: {errors}",
        )

    def test_actual_package_is_valid(self) -> None:
        self.assertEqual([], VALIDATE.validate_repo(ROOT))

    def test_boolean_agent_description_is_rejected(self) -> None:
        self.replace_frontmatter(
            "plugin/agents/designer.agent.md", "description", "true"
        )
        self.assert_error("description must be a non-empty string")

    def test_boolean_skill_description_is_rejected(self) -> None:
        self.replace_frontmatter(
            "plugin/skills/grillmester-domain-modeling/SKILL.md",
            "description",
            "true",
        )
        self.assert_error("description must be a non-empty string")

    def test_aggregate_discovery_budget_is_enforced_independently(self) -> None:
        for skill_id in ("grillmester-grill-me", "grillmester-grill-with-docs"):
            self.replace_frontmatter(
                f"plugin/skills/{skill_id}/SKILL.md",
                "description",
                "x" * (VALIDATE.MAX_DISCOVERY_TEXT_BYTES // 2 + 1),
                quoted=True,
            )

        errors = self.errors()
        self.assertTrue(
            any(
                f"aggregate budget is {VALIDATE.MAX_DISCOVERY_TEXT_BYTES}" in error
                for error in errors
            ),
            errors,
        )

    def test_agent_plugins_schema_is_rejected(self) -> None:
        manifest = self.load_json("plugin/plugin.json")
        manifest["$schema"] = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
        self.write_json("plugin/plugin.json", manifest)
        self.assert_error("must not declare Agent Plugins")

    def test_unreviewed_plugin_component_surface_is_rejected(self) -> None:
        manifest = self.load_json("plugin/plugin.json")
        manifest["hooks"] = "hooks/"
        self.write_json("plugin/plugin.json", manifest)
        self.assert_error("expands the reviewed component surface")

    def test_agent_tool_drift_is_rejected(self) -> None:
        path = self.root / "plugin/agents/grill-inspektor.agent.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "  - search\n", "  - search\n  - edit\n"
            ),
            encoding="utf-8",
        )
        self.assert_error("tools must be exactly")

    def test_stable_version_accepts_reviewed_explicit_tool_policies(self) -> None:
        plugin = self.load_json("plugin/plugin.json")
        plugin["version"] = "0.2.0"
        self.write_json("plugin/plugin.json", plugin)
        marketplace = self.load_json(".github/plugin/marketplace.json")
        marketplace["metadata"]["version"] = "0.2.0"
        for entry in marketplace["plugins"]:
            entry["version"] = "0.2.0"
        self.write_json(".github/plugin/marketplace.json", marketplace)
        self.assertEqual([], self.errors())

    def test_runtime_all_agent_rejects_an_explicit_tool_list(self) -> None:
        path = self.root / "plugin/agents/grillmester.agent.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "disable-model-invocation: true\n",
                "disable-model-invocation: true\ntools:\n  - read\n",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_error("runtime-all policy must omit tools")

    def test_runtime_all_agent_rejects_redundant_deferred_tool_loading(self) -> None:
        path = self.root / "plugin/agents/grillmester.agent.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "disable-model-invocation: true\n",
                "disable-model-invocation: true\ndeferred-tool-loading: true\n",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_error("runtime-all agents already use tool search")

    def test_all_public_agents_use_the_runtime_toolset(self) -> None:
        lock = self.load_json("policy/content-lock.json")
        for agent_id in ("grillmester", "barista", "designer", "doctor-who"):
            with self.subTest(agent=agent_id):
                self.assertEqual("runtime-all", lock["agents"][agent_id]["toolPolicy"])
                self.assertNotIn("tools", lock["agents"][agent_id])
                frontmatter = (
                    self.root / f"plugin/agents/{agent_id}.agent.md"
                ).read_text(encoding="utf-8").split("---", 2)[1]
                self.assertNotIn("tools:", frontmatter)

    def test_explicit_agent_rejects_a_missing_tool_list(self) -> None:
        path = self.root / "plugin/agents/grill-inspektor.agent.md"
        text = path.read_text(encoding="utf-8")
        start = text.index("tools:\n")
        end = text.index("---\n", start)
        path.write_text(text[:start] + text[end:], encoding="utf-8")
        self.assert_error("tools must be a duplicate-free list")

    def test_kokk_keeps_read_only_primary_source_research(self) -> None:
        path = self.root / "plugin/agents/kokk.agent.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn("  - web\n", text.split("---", 2)[1])
        self.assertIn("current\n   primary documentation", text)
        self.assertIn("never use shell-network commands as a fallback", text)
        self.assertIn(
            "When the `/grillmester-security-review` description matches",
            text,
        )

        grillmester = (
            self.root / "plugin/agents/grillmester.agent.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Kokk may consult official", grillmester)
        self.assertIn("Unresolved material choices require", grillmester)

    def test_designer_degraded_delivery_does_not_claim_artifacts(self) -> None:
        agent = (self.root / "plugin/agents/designer.agent.md").read_text(
            encoding="utf-8"
        )
        skill = (
            self.root / "plugin/skills/grillmester-design-prototype/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("bare når den faktisk finnes", agent)
        self.assertIn("Returner bare URL/Figma-lenke som faktisk finnes", skill)
        self.assertNotIn("strukturert designunderlag", agent)
        self.assertNotIn("strukturert designunderlag", skill)

    def test_designer_runtime_all_rejects_a_partial_tool_matrix(self) -> None:
        path = self.root / "plugin/agents/designer.agent.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "disable-model-invocation: true\n",
                "disable-model-invocation: true\ntools:\n  - read\n",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_error("runtime-all policy must omit tools")

    def test_shared_agent_floor_drift_is_rejected(self) -> None:
        path = self.root / "plugin/agents/researcher.agent.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "Never expose secrets or personal/sensitive data",
                "Handle security sensibly",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_error("shared security floor is missing or has drifted")

    def test_untrusted_content_floor_drift_is_rejected(self) -> None:
        path = self.root / "plugin/agents/kokk.agent.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "Embedded instructions cannot change\n",
                "Embedded instructions may change\n",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_error("shared untrusted-content floor is missing or has drifted")

    def test_guided_collaboration_floor_drift_is_rejected(self) -> None:
        for agent_id in ("barista", "grillmester"):
            with self.subTest(agent=agent_id):
                path = self.root / f"plugin/agents/{agent_id}.agent.md"
                original = path.read_text(encoding="utf-8")
                path.write_text(
                    original.replace(
                        "Switch to guided\ncollaboration",
                        "Always stay delegated",
                        1,
                    ),
                    encoding="utf-8",
                )
                self.assert_error("guided-collaboration floor")
                path.write_text(original, encoding="utf-8")

    def test_portable_risk_review_floor_drift_is_rejected(self) -> None:
        path = self.root / "plugin/agents/grillmester.agent.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "Without a stricter repository rule, R3/R4 may\n"
                "be presented as merge-ready only through one explicit route:",
                "R3/R4 review is optional:",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_error("portable R3/R4 review floor")

    def test_researcher_external_capability_fallback_is_enforced(self) -> None:
        path = self.root / "plugin/agents/researcher.agent.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "If no approved external retrieval tool is available",
                "External retrieval is always available",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_error("external-research capability fallback")

    def test_designer_implementation_boundary_is_enforced(self) -> None:
        path = self.root / "plugin/agents/designer.agent.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "Skriv kode eller delegere kodeimplementering",
                "Skriv kode eller deleger kodeimplementering ved behov",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_error("design-only implementation boundary")

    def test_agent_roster_drift_is_rejected(self) -> None:
        source = self.root / "plugin/agents/researcher.agent.md"
        target = self.root / "plugin/agents/unreviewed.agent.md"
        target.write_text(
            source.read_text(encoding="utf-8").replace(
                "name: researcher", "name: unreviewed", 1
            ),
            encoding="utf-8",
        )
        self.assert_error("unexpected agent unreviewed")

    def test_skill_roster_drift_is_rejected(self) -> None:
        source = self.root / "plugin/skills/grillmester-grilling"
        target = self.root / "plugin/skills/unreviewed"
        shutil.copytree(source, target)
        path = target / "SKILL.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "name: grillmester-grilling", "name: unreviewed", 1
            ),
            encoding="utf-8",
        )
        self.assert_error("unexpected skill unreviewed")

    def test_manual_skill_invocation_contract_is_enforced(self) -> None:
        path = self.root / "plugin/skills/grillmester-grill-me/SKILL.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "disable-model-invocation: true\n", ""
            ),
            encoding="utf-8",
        )
        self.assert_error("disable-model-invocation must be True")

    def test_doctor_read_only_boundary_is_enforced(self) -> None:
        path = self.root / "plugin/skills/grillmester-doctor/SKILL.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "Never create, edit, delete, rename, stage, commit,\n"
                "push, install, enable, disable, or update anything while it is active.",
                "Avoid unnecessary changes.",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_error("read-only doctor boundary")

    def test_doctor_surface_boundary_is_enforced(self) -> None:
        path = self.root / "plugin/skills/grillmester-doctor/SKILL.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "An embedded agent floor is not an always-on repository floor.",
                "The agent floor applies everywhere.",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_error("default-agent and code-review boundary")

    def test_doctor_activation_evidence_boundary_is_enforced(self) -> None:
        path = self.root / "plugin/skills/grillmester-doctor/SKILL.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "are configuration evidence only.",
                "prove activation.",
                1,
            ),
            encoding="utf-8",
        )
        self.assert_error("cloud activation evidence boundary")

    def test_diagnosing_skill_redacts_shared_and_hitl_evidence(self) -> None:
        skill = (
            self.root / "plugin/skills/grillmester-diagnosing-bugs/SKILL.md"
        ).read_text(encoding="utf-8")
        hitl = (
            self.root
            / "plugin/skills/grillmester-diagnosing-bugs/scripts/hitl-loop.template.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("Before showing or saving command output", skill)
        self.assertIn("auth headers, cookies, tokens", skill)
        self.assertIn("`<REDACTED>`", skill)
        self.assertIn("approved\nenvironment variables", skill)
        self.assertIn("Status: NEEDS_CONTEXT", skill)
        self.assertIn("capture_signal", hitl)
        self.assertIn("Never enter raw logs, HAR content", hitl)
        self.assertNotIn("Paste the error message", hitl)

    def test_skill_authoring_documents_live_authority(self) -> None:
        skill = (
            self.root / "plugin/skills/grillmester-create-a-skill/SKILL.md"
        ).read_text(encoding="utf-8")
        principles = (
            self.root
            / "plugin/skills/grillmester-create-a-skill/references/principles.md"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "environment, manifests and tool output as\nsource of truth", principles
        )
        self.assertIn("documentation or bundled snapshots as a cache", principles)

    def test_marketplace_owner_is_required(self) -> None:
        manifest = self.load_json(".github/plugin/marketplace.json")
        del manifest["owner"]
        self.write_json(".github/plugin/marketplace.json", manifest)
        self.assert_error("marketplace owner")

    def test_development_marketplace_points_to_plugin_subdirectory(self) -> None:
        manifest = self.load_json(".github/plugin/marketplace.json")
        manifest["plugins"][0]["source"] = "."
        self.write_json(".github/plugin/marketplace.json", manifest)
        self.assert_error("marketplace grillmester source must be 'plugin'")

    def test_immutable_release_marketplace_source_is_valid(self) -> None:
        manifest = self.load_json(".github/plugin/marketplace.json")
        for entry in manifest["plugins"]:
            entry["source"] = {
                "source": "github",
                "repo": "navikt/grillmester",
                "path": VALIDATE.PACKAGE_PATHS[entry["name"]],
                "sha": "a" * 40,
            }
        self.write_json(".github/plugin/marketplace.json", manifest)
        self.assertEqual([], self.errors())

    def test_release_marketplace_requires_full_sha(self) -> None:
        manifest = self.load_json(".github/plugin/marketplace.json")
        manifest["plugins"][0]["source"] = {
            "source": "github",
            "repo": "navikt/grillmester",
            "path": "plugin",
            "sha": "main",
        }
        self.write_json(".github/plugin/marketplace.json", manifest)
        self.assert_error("release marketplace source sha")

    def test_missing_progressive_reference_is_rejected(self) -> None:
        reference = (
            self.root
            / "plugin/skills/grillmester-security-review/references/nav-security-review.md"
        )
        reference.unlink()
        self.assert_error("linked file does not exist")

    def test_broken_link_in_progressive_reference_is_rejected(self) -> None:
        reference = (
            self.root
            / "plugin/skills/grillmester-aksel-design/references/components.md"
        )
        reference.write_text(
            reference.read_text(encoding="utf-8")
            + "\n[Missing sibling](missing.md)\n",
            encoding="utf-8",
        )
        self.assert_error("linked file does not exist")

    def test_legacy_runtime_id_is_rejected(self) -> None:
        path = self.root / "plugin/skills/grillmester-review/SKILL.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "\nDelegate to Hovmester.\n",
            encoding="utf-8",
        )
        self.assert_error("obsolete runtime ID")

    def test_removed_konditor_runtime_id_is_rejected(self) -> None:
        path = self.root / "plugin/skills/grillmester-design-prototype/SKILL.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "\nDelegate to Konditor.\n",
            encoding="utf-8",
        )
        self.assert_error("obsolete runtime ID")

    def test_consumer_identity_is_rejected_from_runtime(self) -> None:
        path = self.root / "plugin/skills/grillmester-review/SKILL.md"
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\nAssume the syfo-budstikka deployment.\n",
            encoding="utf-8",
        )
        self.assert_error("Budstikka identity is not portable plugin content")

    def test_consumer_instruction_paths_are_allowed_only_in_doctor(self) -> None:
        path = self.root / "plugin/skills/grillmester-review/SKILL.md"
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\nInspect `.github/copilot-instructions.md`.\n",
            encoding="utf-8",
        )
        self.assert_error("consumer instruction path is not portable plugin content")

    def test_unfinished_skill_scaffold_is_rejected(self) -> None:
        path = self.root / "plugin/skills/grillmester-review/SKILL.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "\n[TODO: finish this section]\n",
            encoding="utf-8",
        )
        self.assert_error("unfinished skill scaffold is not allowed")

    def test_national_id_shaped_example_is_rejected(self) -> None:
        path = self.root / "README.md"
        shaped_value = "12345" + "678901"
        path.write_text(
            path.read_text(encoding="utf-8") + f"\nExample: {shaped_value}\n",
            encoding="utf-8",
        )
        self.assert_error("looks like a national ID")

    def test_plugin_file_symlink_is_rejected_before_reading_target(self) -> None:
        outside = Path(self.temp.name) / "invalid-agent.md"
        outside.write_bytes(b"---\nname: barista\n---\n\xff")
        link = self.root / "plugin/agents/barista.agent.md"
        link.unlink()
        link.symlink_to(outside)

        errors = self.errors()
        self.assertTrue(
            any("plugin package must not contain symlinks" in error for error in errors),
            errors,
        )

    def test_copyable_figma_keys_are_not_mistaken_for_national_ids(self) -> None:
        catalog_path = self.root / (
            "plugin/skills/grillmester-design-prototype/references/"
            "aksel-figma-katalog.json"
        )
        raw_catalog = catalog_path.read_text(encoding="utf-8")
        self.assertNotIn("\\u003", raw_catalog)
        catalog = json.loads(raw_catalog)
        keys = []
        for component in catalog["komponenter"]:
            component_keys = component.get("keys", {})
            keys.extend(
                component_keys.values()
                if isinstance(component_keys, dict)
                else component_keys
            )
            keys.extend(
                value
                for key, value in component.items()
                if key.startswith("key") and key != "keys"
            )
        self.assertTrue(all(len(key) == 40 for key in keys))
        self.assertTrue(
            all(VALIDATE.FIGMA_COMPONENT_KEY.fullmatch(key) for key in keys)
        )
        self.assertEqual([], self.errors())

        shaped_value = "12345" + "678901"
        catalog_path.write_text(
            raw_catalog + f'\n{{"unsafeExample":"{shaped_value}"}}\n',
            encoding="utf-8",
        )
        self.assert_error("looks like a national ID")

    def test_figma_key_exception_is_limited_to_exact_catalog_paths(self) -> None:
        path = self.root / "docs/aksel-figma-katalog.md"
        shaped_value = "12345" + "678901"
        figma_shaped_value = ("a" * 10) + shaped_value + ("b" * 19)
        self.assertEqual(40, len(figma_shaped_value))
        path.write_text(figma_shaped_value, encoding="utf-8")
        self.assert_error("looks like a national ID")

    def test_source_revision_must_be_a_full_sha(self) -> None:
        lock = self.load_json("policy/content-lock.json")
        lock["sources"]["pilot"]["revision"] = "main"
        self.write_json("policy/content-lock.json", lock)
        self.assert_error("needs a full commit SHA")

    def test_third_party_source_requires_notice_at_reviewed_revision(self) -> None:
        path = self.root / "plugin/THIRD_PARTY_NOTICES.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "44c9b2d6e889982ac18c27d05a19fefe335194e1", "missing-review-pin"
            ),
            encoding="utf-8",
        )
        self.assert_error(
            "third-party source superpowers must ship repository and revision"
        )

    def test_content_lock_assigns_every_skill_to_the_single_plugin(self) -> None:
        lock = self.load_json("policy/content-lock.json")
        locked = set(lock["skills"])
        installed = {
            path.parent.name
            for path in (self.root / "plugin/skills").glob("*/SKILL.md")
        }
        self.assertEqual(43, len(locked))
        self.assertEqual(locked, installed)

    def test_nav_specialist_skill_is_part_of_the_single_plugin(self) -> None:
        path = self.root / "plugin/skills/grillmester-lumi-survey/SKILL.md"
        self.assertTrue(path.is_file())
        self.assertFalse(
            any(path.is_file() for path in (self.root / "plugin-nav").rglob("*"))
        )

    def test_bare_dangling_component_reference_is_rejected(self) -> None:
        path = self.root / "plugin/skills/grillmester-review/SKILL.md"
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\nContinue with grillmester-nonexistent after review.\n",
            encoding="utf-8",
        )
        self.assert_error("dangling Grillmester prose component reference")

    def test_package_counts_are_locked(self) -> None:
        manifest = self.load_json("package-manifest.json")
        manifest["packages"][0]["skills"] = 44
        self.write_json("package-manifest.json", manifest)
        self.assert_error("package roster or counts have drifted")

    def test_component_source_must_be_declared(self) -> None:
        lock = self.load_json("policy/content-lock.json")
        lock["skills"]["grillmester-review"]["source"] = "unknown"
        self.write_json("policy/content-lock.json", lock)
        self.assert_error("references unknown source")

    def test_source_path_must_not_escape_repository(self) -> None:
        lock = self.load_json("policy/content-lock.json")
        lock["skills"]["grillmester-review"]["sourcePath"] = "../review"
        self.write_json("policy/content-lock.json", lock)
        self.assert_error("sourcePath must be repository-relative")

    def test_component_lineage_must_name_a_reviewed_source(self) -> None:
        lock = self.load_json("policy/content-lock.json")
        lock["skills"]["grillmester-design-prototype"]["lineage"][0][
            "source"
        ] = "unknown"
        self.write_json("policy/content-lock.json", lock)
        self.assert_error("lineage references unknown source")

    def test_alternate_manifest_location_is_rejected(self) -> None:
        alternate = self.root / ".plugin/plugin.json"
        alternate.parent.mkdir()
        alternate.write_text("{}", encoding="utf-8")
        self.assert_error("forbidden alternate or generated path")

    def test_missing_visual_identity_asset_is_rejected(self) -> None:
        (self.root / "docs/assets/grillmester-hero.jpg").unlink()
        self.assert_error("missing required regular image asset")

    def test_unrendered_hero_asset_is_rejected(self) -> None:
        path = self.root / "README.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                'src="docs/assets/grillmester-hero.jpg"',
                'src="missing.jpg"',
                1,
            ),
            encoding="utf-8",
        )
        self.assert_error("README must render the reviewed Grillmester hero asset")

    def test_visual_identity_asset_digest_drift_is_rejected(self) -> None:
        path = self.root / "docs/assets/grillmester-avatar.png"
        path.write_bytes(path.read_bytes() + b"drift")
        self.assert_error("differs from the reviewed digest")

    def test_plugin_package_root_symlink_is_rejected(self) -> None:
        target = self.root / "node_modules/plugin-payload"
        target.parent.mkdir()
        (self.root / "plugin").rename(target)
        (self.root / "plugin").symlink_to(target, target_is_directory=True)

        self.assert_error("plugin package root must not be a symlink")


if __name__ == "__main__":
    unittest.main()
