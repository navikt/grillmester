from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_GUIDE = (
    ROOT
    / "plugin/skills/grillmester-improve-codebase-architecture/HTML-REPORT.md"
)
SKILL = (
    ROOT / "plugin/skills/grillmester-improve-codebase-architecture/SKILL.md"
)


class ArchitectureHtmlReportTest(unittest.TestCase):
    def test_html_examples_are_offline_and_inert(self) -> None:
        guide = REPORT_GUIDE.read_text(encoding="utf-8")
        examples = re.findall(r"```html\n(.*?)```", guide, flags=re.DOTALL)

        self.assertTrue(examples, "the report guide must contain an HTML scaffold")
        for example in examples:
            with self.subTest(example=example[:40]):
                self.assertNotRegex(
                    example, re.compile(r"https?://|//[A-Za-z0-9]", re.IGNORECASE)
                )
                self.assertNotRegex(
                    example,
                    re.compile(
                        r"<\s*(?:script|link|img|iframe|object|embed|form|svg|"
                        r"video|audio|source|base)\b",
                        re.IGNORECASE,
                    ),
                )
                self.assertNotRegex(
                    example, re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)
                )
                self.assertNotRegex(
                    example,
                    re.compile(r"\b(?:src|srcset)\s*=|\sstyle\s*=", re.IGNORECASE),
                )
                self.assertNotRegex(
                    example, re.compile(r"@import\b|\burl\s*\(", re.IGNORECASE)
                )
                self.assertNotRegex(
                    example,
                    re.compile(r"http-equiv\s*=\s*[\"']refresh[\"']", re.IGNORECASE),
                )

                hrefs = re.findall(
                    r"\bhref\s*=\s*[\"']([^\"']+)[\"']",
                    example,
                    flags=re.IGNORECASE,
                )
                self.assertTrue(all(href.startswith("#") for href in hrefs))
                for tag in re.findall(r"<[^>]+>", example):
                    self.assertNotIn("{{", tag, "dynamic values must stay in text nodes")

        self.assertNotIn("securityLevel", guide)
        self.assertIn("default-src 'none'", guide)
        self.assertIn("base-uri 'none'", guide)
        self.assertIn("form-action 'none'", guide)

    def test_dynamic_content_contract_is_fail_closed(self) -> None:
        guide = REPORT_GUIDE.read_text(encoding="utf-8")

        for escaped in ("&amp;", "&lt;", "&gt;", "&quot;", "&#39;"):
            with self.subTest(entity=escaped):
                self.assertIn(f"`{escaped}`", guide)
        self.assertIn("only into text nodes", guide)
        self.assertIn("Never insert dynamic content into tag names, attributes", guide)
        self.assertIn("Generate candidate IDs from their ordinal position", guide)
        self.assertIn("Do not include source snippets", guide)

    def test_skill_does_not_auto_open_generated_report(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        normalized = " ".join(skill.split())

        self.assertIn("offline, self-contained, script-free HTML file", skill)
        self.assertIn("secure temporary-file API or `mktemp -d`", normalized)
        self.assertIn("mode `0700`", normalized)
        self.assertIn("exclusive-create/no-follow", normalized)
        self.assertIn("mode `0600`", normalized)
        self.assertNotIn("architecture-candidates-<timestamp>", skill)
        self.assertRegex(skill, r"Do not\s+run `open` or `xdg-open`")
        self.assertIn("only if the user explicitly asks", skill)
        self.assertNotIn("Open it for the user", skill)


if __name__ == "__main__":
    unittest.main()
