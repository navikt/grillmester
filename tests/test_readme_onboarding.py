from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
INSTALLATION = ROOT / "docs/installation.md"


def first_json_block(text: str) -> dict:
    return json.loads(re.search(r"```json\n(.*?)\n```", text, re.S).group(1))


class ReadmeOnboardingContractTest(unittest.TestCase):
    def test_readme_is_short_and_lists_the_public_agents(self) -> None:
        text = README.read_text(encoding="utf-8")
        # Keep onboarding compact; experimental installation paths live in guides.
        self.assertLessEqual(len(text.splitlines()), 125)
        self.assertLessEqual(len(text.split()), 605)
        for agent in ("Grillmester", "Designer", "Doctor Who"):
            with self.subTest(agent=agent):
                self.assertIn(f"| **{agent}**", text)


    def test_auto_update_example_uses_the_reviewed_marketplace_channel(self) -> None:
        readme_config = first_json_block(README.read_text(encoding="utf-8"))
        installation = INSTALLATION.read_text(encoding="utf-8").split(
            "## Valgfritt: automatisk oppdatering i Copilot CLI", 1
        )[1]
        self.assertEqual(readme_config, first_json_block(installation))
        self.assertTrue(readme_config["enabledPlugins"]["grillmester@grillmester"])
        marketplace = readme_config["extraKnownMarketplaces"]["grillmester"]
        self.assertTrue(marketplace["autoUpdate"])
        self.assertEqual("marketplace", marketplace["source"]["ref"])


if __name__ == "__main__":
    unittest.main()
