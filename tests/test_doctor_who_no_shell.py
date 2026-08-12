import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class DoctorWhoNoShellContractTests(unittest.TestCase):
    def test_agent_frontmatter_has_no_execute_or_delegation(self) -> None:
        agent = read("plugin/agents/doctor-who.agent.md")
        frontmatter = agent.split("---", 2)[1]

        self.assertNotIn("  - execute\n", frontmatter)
        self.assertNotIn("  - agent\n", frontmatter)
        self.assertIn("  - edit\n", frontmatter)
        self.assertIn("github/projects_write", frontmatter)
        self.assertIn("github/issue_write", frontmatter)

    def test_projects_reference_has_no_cli_fallback(self) -> None:
        reference = read(
            "plugin/skills/grillmester-team-status/references/projects-v2.md"
        )

        self.assertNotIn("gh project", reference)
        self.assertNotIn("gh api", reference)
        self.assertNotIn("```bash", reference)
        self.assertIn("Status: NEEDS_INPUT", reference)
        self.assertIn("lime inn eller eksportere", reference)

    def test_product_skills_keep_doctor_who_on_semantic_tools(self) -> None:
        team_status = read("plugin/skills/grillmester-team-status/SKILL.md")
        issue_management = read("plugin/skills/grillmester-issue-management/SKILL.md")
        security_review = read("plugin/skills/grillmester-security-review/SKILL.md")

        self.assertIn("Bruk aldri `gh`, shell, rå HTTP", team_status)
        self.assertIn("Status: NEEDS_INPUT", team_status)

        self.assertIn("does **not** apply to Doctor Who", issue_management)
        self.assertIn("Never\nfall back to `gh`, shell, raw HTTP", issue_management)
        self.assertIn("Status: NEEDS_INPUT", issue_management)

        self.assertIn("agent is Doctor Who", security_review)
        self.assertIn("Never invoke or prescribe shell, `gh`, raw HTTP", security_review)
        self.assertIn("Status: NEEDS_INPUT", security_review)

    def test_nav_security_reference_preserves_no_shell_evidence_path(self) -> None:
        reference = read(
            "plugin/skills/grillmester-security-review/references/nav-security-review.md"
        )

        self.assertIn("Doctor Who or other product/read-only workflow", reference)
        self.assertIn("never invoke or prescribe shell, `gh`, raw HTTP", reference)
        self.assertIn("Status: NEEDS_INPUT", reference)


if __name__ == "__main__":
    unittest.main()
