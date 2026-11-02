from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_validate_for_documentation", ROOT / "scripts/validate.py"
)
assert SPEC and SPEC.loader
VALIDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATE)


class ReadmeLinkTest(unittest.TestCase):
    def test_readme_local_links_resolve_inside_the_repository(self) -> None:
        readme = ROOT / "README.md"
        errors: list[str] = []
        VALIDATE.validate_skill_links(
            readme, readme.read_text(encoding="utf-8"), ROOT, errors
        )
        self.assertEqual([], errors)


class DocumentationAnchorIntegrityTest(unittest.TestCase):
    """Every intra-repository markdown fragment link must hit a real heading."""

    LINK = re.compile(r"\]\(([^)#\s]*\.md)?#([^)\s]+)\)")

    @staticmethod
    def _slugify(heading: str) -> str:
        text = heading.strip().lower()
        text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
        return re.sub(r"\s+", "-", text)

    def test_internal_documentation_anchors_resolve(self) -> None:
        documents = [
            ROOT / "README.md",
            *sorted((ROOT / "docs").rglob("*.md")),
        ]
        anchors: dict[Path, set[str]] = {}
        for document in documents:
            headings = re.findall(
                r"^#{1,6}\s+(.*)$",
                document.read_text(encoding="utf-8"),
                flags=re.MULTILINE,
            )
            anchors[document] = {self._slugify(heading) for heading in headings}
        for document in documents:
            content = document.read_text(encoding="utf-8")
            for target_name, fragment in self.LINK.findall(content):
                if target_name.startswith(("http://", "https://")):
                    continue
                target = (
                    (document.parent / target_name).resolve()
                    if target_name
                    else document
                )
                if (
                    target not in anchors
                    and target.is_relative_to(ROOT)
                    and target.is_file()
                ):
                    headings = re.findall(
                        r"^#{1,6}\s+(.*)$",
                        target.read_text(encoding="utf-8"),
                        flags=re.MULTILINE,
                    )
                    anchors[target] = {
                        self._slugify(heading) for heading in headings
                    }
                with self.subTest(source=document.name, link=f"{target_name}#{fragment}"):
                    self.assertIn(
                        target,
                        anchors,
                        f"{document} links to unknown document {target_name}",
                    )
                    self.assertIn(
                        fragment,
                        anchors[target],
                        f"{document} links to missing anchor #{fragment} in "
                        f"{target.name}",
                    )


if __name__ == "__main__":
    unittest.main()
