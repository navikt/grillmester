from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/publish-marketplace.yml"


class PublishWorkflowContractTest(unittest.TestCase):
    def test_write_credentials_exist_only_in_final_publish_step(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("persist-credentials: false", text)
        self.assertEqual(1, text.count("GH_TOKEN: ${{ github.token }}"))
        self.assertLess(
            text.index("Publish catalog-only commit atomically"),
            text.index("GH_TOKEN: ${{ github.token }}"),
        )

    def test_publisher_rejects_marketplace_version_reuse(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Refusing to reuse marketplace version", text)
        self.assertIn("Refusing to reuse previously published marketplace version", text)
        self.assertIn("git rev-list --skip=1", text)

    def test_unrelated_main_changes_do_not_republish_plugin(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('- "plugin/**"', text)
        self.assertNotIn('- "scripts/generate_marketplace.py"', text)
        self.assertNotIn('- ".github/workflows/publish-marketplace.yml"', text)


if __name__ == "__main__":
    unittest.main()
