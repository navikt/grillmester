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

    def assert_error(self, fragment: str) -> None:
        errors = self.errors()
        self.assertTrue(
            any(fragment in error for error in errors),
            f"expected {fragment!r} in validation errors: {errors}",
        )

    def test_actual_package_is_valid(self) -> None:
        self.assertEqual([], VALIDATE.validate_repo(ROOT))

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

    def test_stable_version_rejects_ambient_all_tool_policy(self) -> None:
        plugin = self.load_json("plugin/plugin.json")
        plugin["version"] = "0.2.0"
        self.write_json("plugin/plugin.json", plugin)
        marketplace = self.load_json(".github/plugin/marketplace.json")
        marketplace["metadata"]["version"] = "0.2.0"
        marketplace["plugins"][0]["version"] = "0.2.0"
        self.write_json(".github/plugin/marketplace.json", marketplace)
        self.assert_error("stable package cannot leave all runtime tools ambient")

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

    def test_skill_license_is_required(self) -> None:
        path = self.root / "plugin/skills/grillmester-tdd/SKILL.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace("license: MIT\n", "", 1),
            encoding="utf-8",
        )
        self.assert_error("license must be 'MIT'")

    def test_marketplace_owner_is_required(self) -> None:
        manifest = self.load_json(".github/plugin/marketplace.json")
        del manifest["owner"]
        self.write_json(".github/plugin/marketplace.json", manifest)
        self.assert_error("marketplace owner")

    def test_development_marketplace_points_to_plugin_subdirectory(self) -> None:
        manifest = self.load_json(".github/plugin/marketplace.json")
        manifest["plugins"][0]["source"] = "."
        self.write_json(".github/plugin/marketplace.json", manifest)
        self.assert_error("marketplace plugin source must be the development path")

    def test_immutable_release_marketplace_source_is_valid(self) -> None:
        manifest = self.load_json(".github/plugin/marketplace.json")
        manifest["plugins"][0]["source"] = {
            "source": "github",
            "repo": "navikt/grillmester",
            "path": "plugin",
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

    def test_source_revision_must_be_a_full_sha(self) -> None:
        lock = self.load_json("policy/content-lock.json")
        lock["sources"]["pilot"]["revision"] = "main"
        self.write_json("policy/content-lock.json", lock)
        self.assert_error("needs a full commit SHA")

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

    def test_plugin_symlink_is_rejected(self) -> None:
        link = self.root / "plugin/skills/grillmester-review/linked-skill.md"
        link.symlink_to(self.root / "README.md")
        self.assert_error("must not contain symlinks")


if __name__ == "__main__":
    unittest.main()
