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

    def test_agent_tool_drift_is_rejected(self) -> None:
        path = self.root / "plugin/agents/grill-inspektor.agent.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "  - glob\n", "  - glob\n  - edit\n"
            ),
            encoding="utf-8",
        )
        self.assert_error("tools must be exactly")

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

    def test_consumer_identity_is_rejected_from_runtime(self) -> None:
        path = self.root / "plugin/skills/grillmester-review/SKILL.md"
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\nAssume the syfo-budstikka deployment.\n",
            encoding="utf-8",
        )
        self.assert_error("Budstikka identity is not portable plugin content")

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

    def test_plugin_symlink_is_rejected(self) -> None:
        link = self.root / "plugin/skills/grillmester-review/linked-skill.md"
        link.symlink_to(self.root / "README.md")
        self.assert_error("must not contain symlinks")


if __name__ == "__main__":
    unittest.main()
