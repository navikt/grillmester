from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("grillmester_validate", ROOT / "scripts/validate.py")
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

    def test_actual_package_is_valid(self) -> None:
        self.assertEqual([], VALIDATE.validate_repo(ROOT))

    def test_agent_plugins_schema_is_rejected(self) -> None:
        path = self.root / "plugin.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["$schema"] = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertTrue(any("must not declare Agent Plugins" in error for error in self.errors()))

    def test_agent_tool_drift_is_rejected(self) -> None:
        path = self.root / "agents/grillmester-reviewer.agent.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace("  - skill\n", "  - skill\n  - edit\n"),
            encoding="utf-8",
        )
        self.assertTrue(any("tools must be exactly" in error for error in self.errors()))

    def test_marketplace_owner_is_required(self) -> None:
        path = self.root / ".github/plugin/marketplace.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        del manifest["owner"]
        path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertTrue(any("marketplace owner" in error for error in self.errors()))

    def test_missing_progressive_reference_is_rejected(self) -> None:
        reference = self.root / "skills/grillmester-security-review/references/nav-security-review.md"
        reference.unlink()
        self.assertTrue(any("linked file does not exist" in error for error in self.errors()))

    def test_legacy_runtime_id_is_rejected(self) -> None:
        path = self.root / "skills/grillmester-review/SKILL.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nDelegate to Kokk.\n", encoding="utf-8")
        self.assertTrue(any("legacy runtime ID" in error for error in self.errors()))

    def test_national_id_shaped_example_is_rejected(self) -> None:
        path = self.root / "README.md"
        shaped_value = "12345" + "678901"
        path.write_text(
            path.read_text(encoding="utf-8") + f"\nExample: {shaped_value}\n",
            encoding="utf-8",
        )
        self.assertTrue(any("looks like a national ID" in error for error in self.errors()))


if __name__ == "__main__":
    unittest.main()
