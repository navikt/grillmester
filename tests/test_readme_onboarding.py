from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
INSTALLATION = ROOT / "docs/installation.md"
BUG_TEMPLATE = ROOT / ".github/ISSUE_TEMPLATE/bug.yml"
CLIENT_ARTIFACTS = ROOT / "policy/client-artifacts.json"
OPENCODE_GUIDE = ROOT / "docs/opencode.md"


class ReadmeOnboardingContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = README.read_text(encoding="utf-8")
        cls.installation = INSTALLATION.read_text(encoding="utf-8")
        cls.bug_template = BUG_TEMPLATE.read_text(encoding="utf-8")
        cls.opencode_guide = OPENCODE_GUIDE.read_text(encoding="utf-8")
        client_artifacts = json.loads(
            CLIENT_ARTIFACTS.read_text(encoding="utf-8")
        )
        cls.opencode_version = client_artifacts["opencode"]["version"]
        cls.cplt_release = client_artifacts["cplt"]["release"]

    def test_readme_is_a_short_four_agent_onboarding(self) -> None:
        self.assertLessEqual(len(self.text.splitlines()), 110)
        self.assertLessEqual(len(self.text.split()), 550)
        self.assertEqual(
            self.text.split("\n## ", 1)[1].splitlines()[0], "Kom i gang"
        )
        self.assertLess(
            self.text.index("## Kom i gang"), self.text.index("## Velg agent")
        )
        self.assertLess(
            self.text.index("## Velg agent"),
            self.text.index("## Støtte og avgrensninger"),
        )
        self.assertNotIn("\n## Bruk\n", self.text)
        self.assertNotIn("\n## Klientstatus\n", self.text)

        for agent in ("Grillmester", "Barista", "Designer", "Doctor Who"):
            with self.subTest(agent=agent):
                self.assertIn(f"| **{agent}**", self.text)
        self.assertIn(
            "Kokk, Grill-inspektør og Researcher er interne roller",
            " ".join(self.text.split()),
        )

        self.assertNotIn("Status: POC", self.text)
        self.assertNotIn("Copilot app — to bekreftelser", self.text)
        self.assertNotIn("strukturert designunderlag", self.text)

    def test_terminal_install_precedes_the_single_start_flow(self) -> None:
        terminal = self.text.split(
            "### Copilot CLI og OpenCode i terminalen", 1
        )[1].split("### Copilot app", 1)[0]
        normalized = " ".join(terminal.split())
        self.assertLess(
            terminal.index("brew install navikt/tap/grillmester"),
            terminal.index("\ngrillmester\n"),
        )
        for marker in (
            "brew install --cask copilot-cli",
            "GitHub Copilot CLI",
            "OpenCode",
            "grillmester choose",
            "--client copilot --role grillmester",
            "--client opencode --role barista",
            "grillmester doctor",
            "alltid gjennom cplt",
            "--allow-localhost 1234",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, normalized)

        self.assertNotIn('"autoUpdate"', self.text)
        self.assertIn('"autoUpdate"', self.installation)

        self.assertLess(
            self.opencode_guide.index("### Hent og verifiser en Grillmester-bundle"),
            self.opencode_guide.index("## Valgfri lifecycle-manager"),
        )
        native_bundle = self.opencode_guide.split(
            "### Hent og verifiser en Grillmester-bundle", 1
        )[1].split("## Valgfri lifecycle-manager", 1)[0]
        self.assertIn(
            "For vanlig, native cplt-bruk er bundle-en nå klar", native_bundle
        )
        self.assertNotIn("manage_opencode.py install", native_bundle)

        client_install = self.opencode_guide.split(
            "### Installer eksakte klienter manuelt", 1
        )[1].split("### Hent og verifiser en Grillmester-bundle", 1)[0]
        manager = self.opencode_guide.split("## Valgfri lifecycle-manager", 1)[1]
        self.assertNotIn("Python `3.11`", client_install)
        self.assertNotIn("verify_client_artifact.py", client_install)
        self.assertIn("Python `3.11`", manager)
        self.assertIn("verify_client_artifact.py", manager)
        self.assertIn("--allow-localhost 1234", self.opencode_guide)
        self.assertIn("--pass-env MODEL_PROVIDER_API_KEY", self.opencode_guide)

    def test_readme_distinguishes_roles_and_support_compactly(self) -> None:
        self.assertIn("avklarer valg og risiko", self.text)
        self.assertIn("Målet er tydelig", self.text)
        self.assertIn(
            "Tilgang og tillatt bruk styres av Navs gjeldende policy.",
            " ".join(self.text.splitlines()),
        )
        self.assertIn("## Støtte og avgrensninger", self.text)
        normalized = " ".join(self.text.split())
        for marker in (
            "GitHub Copilot CLI er referanseklienten",
            "OpenCode-støtten gjelder den release-gatede klientkombinasjonen",
            "VS Code er ikke en del av første onboarding",
            "docs/trust-and-client-support.md",
            "docs/repository-context.md#samspill-med-naviktcopilot",
            "valgfritt MCP-oppsett",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, normalized)

    def test_readme_local_links_and_anchors_resolve(self) -> None:
        def github_slug(heading: str) -> str:
            plain = re.sub(r"`([^`]*)`", r"\1", heading.strip().lower())
            plain = re.sub(r"[^\w\- ]", "", plain)
            return re.sub(r"\s+", "-", plain)

        targets = re.findall(r"\[[^\]]+\]\(([^)]+)\)", self.text)
        for target in targets:
            if target.startswith(("https://", "http://", "mailto:")):
                continue
            path_text, separator, anchor = target.partition("#")
            path = ROOT / path_text
            with self.subTest(target=target):
                self.assertTrue(path.is_file(), f"missing README link target: {target}")
                if not separator:
                    continue
                headings = (
                    line.lstrip("#").strip()
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if re.match(r"^#{1,6} ", line)
                )
                self.assertIn(anchor, {github_slug(heading) for heading in headings})

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
