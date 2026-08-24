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
        self.assertLessEqual(len(self.text.splitlines()), 115)
        self.assertLessEqual(len(self.text.split()), 575)
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
            terminal.index("ikke tilgjengelig ennå"),
            terminal.index("brew install navikt/tap/grillmester"),
        )
        self.assertLess(
            terminal.index("brew install navikt/tap/grillmester"),
            terminal.index("brew install opencode"),
        )
        self.assertLess(
            terminal.index("brew install opencode"),
            terminal.index("\ngrillmester\n"),
        )
        for marker in (
            "cplt som ekstern Homebrew-avhengighet",
            "fra `PATH` uten å endre dem",
            "brew install opencode",
            "brew install --cask copilot-cli",
            "GitHub Copilot CLI",
            "OpenCode",
            "grillmester choose",
            "En manglende klient gir installasjonskommando, aldri fallback",
            "--client copilot --agent grillmester",
            "--client opencode --agent barista",
            "grillmester doctor",
            "alltid gjennom cplt",
            "grillmester local setup",
            "grillmester local --full",
            "grillmester update",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, normalized)

        self.assertNotIn('"autoUpdate"', self.text)
        self.assertIn('"autoUpdate"', self.installation)

        baseline_heading = "### Installer den eksakte testbaselinen manuelt"
        self.assertLess(
            self.opencode_guide.index(baseline_heading),
            self.opencode_guide.index("### Hent og verifiser en Grillmester-bundle"),
        )
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

        standard_setup = self.opencode_guide.split(
            "## Kom i gang", 1
        )[1].split("## Avansert: manuell binding og verifisering", 1)[0]
        baseline = self.opencode_guide.split(
            baseline_heading, 1
        )[1].split("### Hent og verifiser en Grillmester-bundle", 1)[0]
        manager = self.opencode_guide.split("## Valgfri lifecycle-manager", 1)[1]
        self.assertIn("brew install opencode", standard_setup)
        self.assertIn("resolver `opencode` fra `PATH`", standard_setup)
        self.assertNotIn("npm install --global opencode-ai@", standard_setup)
        self.assertNotIn("private `trusted-bin`", standard_setup)
        self.assertIn(f"opencode-ai@{self.opencode_version}", baseline)
        self.assertIn(self.cplt_release, baseline)
        self.assertNotIn("Python `3.11`", baseline)
        self.assertNotIn("verify_client_artifact.py", baseline)
        self.assertIn("Python `3.11`", manager)
        self.assertIn("verify_client_artifact.py", manager)
        self.assertIn(self.opencode_version, manager)
        self.assertIn(self.cplt_release, manager)
        self.assertIn("grillmester local setup --client opencode", self.opencode_guide)
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
            "Homebrew støttes på macOS",
            "Linux og VS Code er utenfor release-løftet",
            "Standardlauncheren støtter OpenCode 1.x fra `1.18.20`",
            "Copilot CLI 1.x fra `1.0.79`",
            "cplt fra testbaselinen",
            "High-assurance-manageren har eksakte pinner",
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
            "Homebrew-terminalflyten støttes bare på macOS i denne releasen",
            "Copilot app",
            "Alternativ: native Copilot CLI-installasjon med automatisk oppdatering",
            '"enabledPlugins"',
            '"marketplace"',
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
