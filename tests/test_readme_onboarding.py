from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
INSTALLATION = ROOT / "docs/installation.md"


class ReadmeOnboardingContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = README.read_text(encoding="utf-8")
        cls.installation = INSTALLATION.read_text(encoding="utf-8")

    def test_readme_is_a_short_four_agent_onboarding(self) -> None:
        self.assertLessEqual(len(self.text.splitlines()), 120)
        self.assertLessEqual(len(self.text.split()), 600)
        for agent in ("Grillmester", "Barista", "Designer", "Doctor Who"):
            with self.subTest(agent=agent):
                self.assertIn(f"**{agent}**", self.text)

        self.assertNotIn("Status: POC", self.text)
        self.assertNotIn("Copilot app — to bekreftelser", self.text)
        self.assertNotIn("strukturert designunderlag", self.text)

    def test_cli_install_and_auto_update_are_copyable(self) -> None:
        for marker in (
            "copilot plugin marketplace add navikt/grillmester#marketplace",
            "copilot plugin install grillmester@grillmester",
            "~/.copilot/settings.json",
            '"ref": "marketplace"',
            '"autoUpdate": true',
            '"grillmester@grillmester": true',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.text)

    def test_advanced_installation_details_remain_in_the_guide(self) -> None:
        for marker in (
            "Copilot app",
            ".github/copilot/settings.json",
            "strictKnownMarketplaces",
            "scripts/configure_autoupdate.py",
            "NEW_REVIEWED_RELEASE_TAG",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.installation)


if __name__ == "__main__":
    unittest.main()
