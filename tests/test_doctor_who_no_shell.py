import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def normalized(relative_path: str) -> str:
    return " ".join(read(relative_path).split())


class DoctorWhoNoShellContractTests(unittest.TestCase):
    def test_agent_inherits_runtime_tools_but_keeps_a_behavioral_no_shell_boundary(self) -> None:
        agent = read("plugin/agents/doctor-who.agent.md")
        frontmatter = agent.split("---", 2)[1]

        self.assertNotIn("tools:", frontmatter)
        body = " ".join(agent.split())
        self.assertIn("never replace it with shell or network commands", body)
        self.assertIn("Your role forbids command execution and delegation.", body)
        self.assertIn("never use them, and never route around this boundary", body)

    def test_projects_reference_has_no_cli_fallback(self) -> None:
        reference = read(
            "plugin/skills/team-status/references/projects-v2.md"
        )

        self.assertNotIn("gh project", reference)
        self.assertNotIn("gh api", reference)
        self.assertNotIn("```bash", reference)
        self.assertIn("Status: NEEDS_INPUT", reference)
        self.assertIn("lime inn eller eksportere", reference)

    def test_product_skills_keep_roles_without_execution_on_semantic_tools(self) -> None:
        team_status = read("plugin/skills/team-status/SKILL.md")
        issue_management = normalized("plugin/skills/issue-management/SKILL.md")
        security_review = normalized("plugin/skills/security-review/SKILL.md")
        no_execution = (
            "When your role forbids command execution or the runtime lacks "
            "explicit command-execution capability"
        )

        self.assertIn("Never use `gh`, shell, raw HTTP", team_status)
        self.assertIn("Status: NEEDS_INPUT", team_status)

        self.assertIn(no_execution, issue_management)
        self.assertIn("Never fall back to `gh`, shell, raw HTTP", issue_management)
        self.assertIn("cplt-guarded `gh issue` commands", issue_management)
        self.assertIn("Outside that explicit cplt context", issue_management)
        self.assertIn("Never use raw HTTP for a tracker mutation", issue_management)
        self.assertIn("Status: NEEDS_INPUT", issue_management)

        self.assertIn(no_execution, security_review)
        self.assertIn("Never invoke or prescribe shell, `gh`, raw HTTP", security_review)
        self.assertIn("Status: NEEDS_INPUT", security_review)

        for skill in (issue_management, security_review):
            self.assertNotIn("Doctor Who", skill)

    def test_nav_security_reference_preserves_no_shell_evidence_path(self) -> None:
        reference = normalized(
            "plugin/skills/security-review/references/nav-security-review.md"
        )

        self.assertIn("In a workflow without command execution", reference)
        self.assertIn("never invoke or prescribe shell, `gh`, raw HTTP", reference)
        self.assertIn("Status: NEEDS_INPUT", reference)


if __name__ == "__main__":
    unittest.main()
