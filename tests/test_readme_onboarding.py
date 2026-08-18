from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
INSTALLATION = ROOT / "docs/installation.md"
BUG_TEMPLATE = ROOT / ".github/ISSUE_TEMPLATE/bug.yml"


class ReadmeOnboardingContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = README.read_text(encoding="utf-8")
        cls.installation = INSTALLATION.read_text(encoding="utf-8")
        cls.bug_template = BUG_TEMPLATE.read_text(encoding="utf-8")

    def test_readme_is_a_short_four_agent_onboarding(self) -> None:
        self.assertLessEqual(len(self.text.splitlines()), 120)
        self.assertLessEqual(len(self.text.split()), 600)
        self.assertEqual(self.text.split("\n## ", 1)[1].splitlines()[0], "Agentene")

        for agent in ("Grillmester", "Barista", "Designer", "Doctor Who"):
            with self.subTest(agent=agent):
                self.assertIn(f"| **{agent}**", self.text)
        self.assertIn(
            "Kokk, Grill-inspektør og Researcher er interne roller", self.text
        )

        self.assertNotIn("Status: POC", self.text)
        self.assertNotIn("Copilot app — to bekreftelser", self.text)
        self.assertNotIn("strukturert designunderlag", self.text)

    def test_cli_install_and_auto_update_are_copyable(self) -> None:
        install = re.search(r"```bash\n(.*?)\n```", self.text, re.DOTALL)
        self.assertIsNotNone(install)
        self.assertEqual(
            install.group(1).splitlines(),
            [
                "copilot plugin marketplace add navikt/grillmester#marketplace",
                "copilot plugin install grillmester@grillmester",
            ],
        )

        settings = re.search(r"```json\n(.*?)\n```", self.text, re.DOTALL)
        self.assertIsNotNone(settings)
        self.assertEqual(
            json.loads(settings.group(1)),
            {
                "extraKnownMarketplaces": {
                    "grillmester": {
                        "source": {
                            "source": "github",
                            "repo": "navikt/grillmester",
                            "ref": "marketplace",
                        },
                        "autoUpdate": True,
                    }
                },
                "enabledPlugins": {"grillmester@grillmester": True},
            },
        )

    def test_readme_distinguishes_roles_and_client_updates_compactly(self) -> None:
        self.assertIn("avklarer valg og risiko", self.text)
        self.assertIn("Målet er tydelig", self.text)
        self.assertIn(
            "Tilgang og tillatt bruk styres av Navs gjeldende policy.",
            " ".join(self.text.splitlines()),
        )
        self.assertIn("### Klientstatus", self.text)
        for marker in (
            "Valgfri automatisk oppdatering i Copilot CLI",
            "Oppdater en installert plugin manuelt med **Update**",
            "VS Code:** Egen oppdateringsmekanisme",
            "valgfritt MCP-oppsett",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.text)

    def test_advanced_installation_details_remain_in_the_guide(self) -> None:
        for marker in (
            "Copilot app",
            "velge **Update** under\n**Settings → Plugins**",
            ".github/copilot/settings.json",
            "strictKnownMarketplaces",
            "scripts/configure_autoupdate.py",
            "NEW_REVIEWED_RELEASE_TAG",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.installation)

    def test_bug_template_has_vs_code_and_safe_evidence_requirements(self) -> None:
        for marker in (
            "- VS Code",
            "Sladdet evidens",
            "Jeg har fjernet secrets, personopplysninger",
            "Dette er ikke en sårbarhetsrapport som bør sendes privat.",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.bug_template)


if __name__ == "__main__":
    unittest.main()
