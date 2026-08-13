from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
MARKDOWN_LINK = re.compile(
    r"\[([^]]+)]\((https://github\.com/copilot/app/launch\?[^)]+)\)"
)


class ReadmeOnboardingContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = README.read_text(encoding="utf-8")

    def app_source(self, label: str) -> tuple[str, str]:
        links = dict(MARKDOWN_LINK.findall(self.text))
        launcher = urlparse(links[label])
        self.assertEqual("https", launcher.scheme)
        self.assertEqual("github.com", launcher.netloc)
        self.assertEqual("/copilot/app/launch", launcher.path)

        app_url = parse_qs(launcher.query)["open"][0]
        app = urlparse(app_url)
        self.assertEqual("ghapp", app.scheme)
        self.assertEqual("plugins", app.netloc)
        return app.path, parse_qs(app.query)["source"][0]

    def test_app_links_use_only_the_documented_unpinned_source_shapes(self) -> None:
        self.assertEqual(
            ("/marketplace/add", "navikt/grillmester"),
            self.app_source("Legg til Grillmester-markedsplassen"),
        )
        self.assertEqual(
            ("/install", "grillmester@grillmester"),
            self.app_source("Installer Grillmester"),
        )

    def test_cli_flow_pins_the_reviewed_marketplace_release(self) -> None:
        self.assertIn(
            "copilot plugin marketplace add "
            "navikt/grillmester#REVIEWED_RELEASE_TAG",
            self.text,
        )
        self.assertIn(
            "copilot plugin install grillmester@grillmester",
            self.text,
        )
        self.assertIn("copilot plugin list", self.text)
        self.assertIn(
            "copilot plugin marketplace add "
            "navikt/grillmester#NEW_REVIEWED_RELEASE_TAG",
            self.text,
        )
        self.assertIn(
            "copilot plugin uninstall grillmester@grillmester",
            self.text,
        )
        self.assertIn("copilot plugin marketplace remove grillmester", self.text)

    def test_user_repo_and_managed_scopes_remain_distinct(self) -> None:
        for marker in (
            "~/.copilot/settings.json",
            ".github/copilot/settings.json",
            "extraKnownMarketplaces",
            "enabledPlugins",
            "strictKnownMarketplaces",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.text)


if __name__ == "__main__":
    unittest.main()
