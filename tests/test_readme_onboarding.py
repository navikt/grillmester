from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
INSTALLATION = ROOT / "docs/installation.md"
BUG_TEMPLATE = ROOT / ".github/ISSUE_TEMPLATE/bug.yml"
BASELINE_PATH = ROOT / "scripts/release_test_baseline.py"
OPENCODE_GUIDE = ROOT / "docs/opencode.md"


class ReadmeOnboardingContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = README.read_text(encoding="utf-8")
        cls.installation = INSTALLATION.read_text(encoding="utf-8")
        cls.bug_template = BUG_TEMPLATE.read_text(encoding="utf-8")
        cls.opencode_guide = OPENCODE_GUIDE.read_text(encoding="utf-8")
        spec = importlib.util.spec_from_file_location(
            "grillmester_release_test_baseline_for_readme", BASELINE_PATH
        )
        assert spec and spec.loader
        baseline = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = baseline
        spec.loader.exec_module(baseline)
        cls.opencode_version = baseline.CONTRACT["releaseTest"]["opencodeVersion"]
        cls.cplt_release = baseline.CONTRACT["releaseTest"]["cpltRelease"]

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

    def test_native_plugin_precedes_the_checkout_pilot(self) -> None:
        plugin = self.text.split(
            "### Copilot CLI — anbefalt nå", 1
        )[1].split("### Copilot app", 1)[0]
        pilot = self.text.split(
            "### OpenCode og lokale modeller — pilot fra checkout", 1
        )[1].split("## Velg agent", 1)[0]
        normalized = " ".join(pilot.split())
        self.assertLess(
            self.text.index("copilot plugin marketplace add navikt/grillmester#marketplace"),
            self.text.index("### Copilot app"),
        )
        self.assertLess(
            self.text.index("### Copilot app"),
            self.text.index("### OpenCode og lokale modeller — pilot fra checkout"),
        )
        self.assertIn("copilot plugin install grillmester@grillmester", plugin)
        self.assertIn("`grillmester:grillmester`", plugin)
        for marker in (
            "brew install navikt/tap/cplt opencode",
            "brew install --cask copilot-cli",
            "OpenCode",
            "--client opencode --agent barista",
            "python3 /absolute/path/to/grillmester/scripts/grillmester.py local setup",
            "python3 /absolute/path/to/grillmester/scripts/grillmester.py local launch",
            "starter du først en OpenAI-kompatibel modellserver",
            "cd /path/to/consumer-repo",
            "Homebrew-kanalen for Grillmester er ikke aktivert",
            "Videre terminaldistribusjon samordnes med nav-pilot",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, normalized)

        self.assertLess(
            normalized.index("starter du først en OpenAI-kompatibel modellserver"),
            normalized.index(
                "python3 /absolute/path/to/grillmester/scripts/grillmester.py local setup"
            ),
        )

        self.assertNotIn('"autoUpdate"', self.text)
        self.assertIn('"autoUpdate"', self.installation)
        self.assertNotIn("brew install navikt/tap/grillmester", self.text)
        self.assertNotIn("grillmester update", self.text)

        baseline_heading = "### Installer den eksakte testbaselinen manuelt"
        self.assertLess(
            self.opencode_guide.index(baseline_heading),
            self.opencode_guide.index("### Hent og verifiser en Grillmester-bundle"),
        )
        self.assertLess(
            self.opencode_guide.index("### Hent og verifiser en Grillmester-bundle"),
            self.opencode_guide.index("## Hva launcheren faktisk gjør"),
        )
        native_bundle = self.opencode_guide.split(
            "### Hent og verifiser en Grillmester-bundle", 1
        )[1].split("## Hva launcheren faktisk gjør", 1)[0]
        self.assertIn(
            "For vanlig, native cplt-bruk er bundle-en nå klar", native_bundle
        )
        self.assertIn(
            "ingen OpenCode-, Copilot- eller cplt-binær", native_bundle
        )

        standard_setup = self.opencode_guide.split(
            "## Kom i gang", 1
        )[1].split("## Avansert: manuell binding og verifisering", 1)[0]
        baseline = self.opencode_guide.split(
            baseline_heading, 1
        )[1].split("### Hent og verifiser en Grillmester-bundle", 1)[0]
        self.assertIn("brew install navikt/tap/cplt opencode", standard_setup)
        self.assertIn("resolver `opencode` fra `PATH`", " ".join(standard_setup.split()))
        self.assertNotIn("npm install --global opencode-ai@", standard_setup)
        self.assertNotIn("private `trusted-bin`", standard_setup)
        self.assertIn(f"opencode-ai@{self.opencode_version}", baseline)
        self.assertIn(self.cplt_release, baseline)
        self.assertIn("reproduserbar CI-evidens", baseline)
        self.assertIn("ikke som runtimekrav", baseline)
        self.assertNotIn("manage_opencode.py", self.opencode_guide)
        self.assertNotIn("trusted-bin", self.opencode_guide)
        self.assertIn(
            "scripts/grillmester.py local setup --client opencode",
            self.opencode_guide,
        )
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
            "OpenCode og lokale modeller er foreløpig en checkout-pilot på macOS",
            "Linux og VS Code er utenfor release-løftet",
            "Checkout-launcheren støtter OpenCode 1.x fra `1.18.20`",
            "Copilot CLI 1.x fra `1.0.79`",
            "cplt fra testbaselinen",
            "Hver modell må kvalitetsvalideres separat",
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
            "Homebrew-formelen for Grillmester er ferdig",
            "kanalen er ikke aktivert",
            "Copilot app",
            "Valgfritt: automatisk oppdatering i Copilot CLI",
            '"enabledPlugins"',
            '"marketplace"',
            "velge **Update** under\n**Settings → Plugins**",
            ".github/copilot/settings.json",
            "strictKnownMarketplaces",
            "scripts/configure_autoupdate.py",
            "NEW_REVIEWED_RELEASE_TAG",
            "python3 /absolute/path/to/grillmester/scripts/grillmester.py local launch",
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
