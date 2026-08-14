import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class RuntimeSafetyContentTests(unittest.TestCase):
    def test_live_pod_evidence_requires_scope_approval_and_redaction(self) -> None:
        reference = read(
            "plugin/skills/grillmester-nav-troubleshoot/references/pod-diagnose.md"
        )

        self.assertIn("Read-only is not a safety classification", reference)
        self.assertIn("exact cluster/context, namespace", reference)
        self.assertIn("obtain explicit approval", reference)
        self.assertIn("--since=<verified-window>", reference)
        self.assertIn("Redact sensitive values", reference)

    def test_auth_guidance_does_not_assign_http_status_to_network_policy(self) -> None:
        troubleshoot = read(
            "plugin/skills/grillmester-nav-troubleshoot/references/auth-diagnose.md"
        )
        overview = read("plugin/skills/grillmester-auth-overview/SKILL.md")

        self.assertIn("verified producer of the HTTP response", troubleshoot)
        self.assertIn(
            "Neither is generally the producer\nof an HTTP 401 or 403",
            troubleshoot,
        )
        self.assertIn("blocked network path normally means", troubleshoot)
        self.assertIn("verified producer of the HTTP response", overview)
        self.assertIn("Do not presume that either produced", overview)
        self.assertNotIn("whether 401/403 comes from ingress/network policy", troubleshoot)

    def test_security_review_traces_sensitive_validation_output(self) -> None:
        skill = read("plugin/skills/grillmester-security-review/SKILL.md")

        self.assertIn("Trace values through validation and diagnostic wrappers", skill)
        self.assertIn("`validatedValue`", skill)
        self.assertIn("can still contain the original sensitive input", skill)


if __name__ == "__main__":
    unittest.main()
