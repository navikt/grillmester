from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs/macos-client-validation-protocol.md"
TEMPLATE = ROOT / "docs/release-evidence-template.json"
DRY_RUN = ROOT / "docs/release-evidence-0.3.0-dry-run.json"
TRUST_AND_CLIENT_SUPPORT = ROOT / "docs/trust-and-client-support.md"

CLIENTS = ("Copilot CLI", "Copilot App", "VS Code")
SCENARIOS = {
    "installation-discovery",
    "update",
    "rollback",
    "restart-after-rollback",
    "role-grillmester",
    "role-barista",
    "role-designer",
    "role-doctor-who",
    "harness-parity",
}
PARITY_CHECKS = {
    "/grillmester-grilling",
    "automatic-skill-routing",
    "wayfinder-delegation",
    "grillmester-kokk-grill-inspektor",
    "visual-companion",
    "approved-write",
    "rejected-write",
}
SCENARIO_FIELDS = {
    "scenario",
    "result",
    "observedTools",
    "observedApprovals",
    "sideEffects",
    "deviations",
}


class MacosClientValidationProtocolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol = PROTOCOL.read_text(encoding="utf-8")
        cls.template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        cls.dry_run = json.loads(DRY_RUN.read_text(encoding="utf-8"))
        cls.trust_and_client_support = TRUST_AND_CLIENT_SUPPORT.read_text(
            encoding="utf-8"
        )

    def test_protocol_has_required_sections_and_macos_client_scope(self) -> None:
        for section in (
            "## 1. Scope and exclusions",
            "## 2. Prepare the run",
            "## 3. Per-client validation",
            "## 4. Harness-parity core",
            "## 5. Evidence and disposition",
        ):
            with self.subTest(section=section):
                self.assertIn(section, self.protocol)

        for client in CLIENTS:
            with self.subTest(client=client):
                self.assertIn(client, self.protocol)

        self.assertIn("**macOS only**", self.protocol)
        self.assertIn("one disposable synthetic fixture", self.protocol)
        self.assertIn("one frontend repository", self.protocol)
        self.assertIn("one backend repository", self.protocol)
        self.assertIn("clean, isolated worktree", self.protocol)
        self.assertIn("consumer-pilot runbook](consumer-pilot-runbook.md)", self.protocol)
        self.assertIn("sections 5 and 6", self.protocol)
        self.assertIn("section 7", self.protocol)
        self.assertRegex(self.protocol, r"exit gate \(section\s+8\)")
        self.assertIn("does not run model scenarios in CI", self.protocol)
        self.assertIn("[installation guide](installation.md)", self.protocol)
        self.assertIn("[release runbook](release-runbook.md)", self.protocol)
        self.assertIn(
            "[macOS-klientvalideringsprotokollen](macos-client-validation-protocol.md)",
            self.trust_and_client_support,
        )

    def test_protocol_names_all_parity_checks_and_hard_blockers(self) -> None:
        for check in (
            "/grillmester-grilling",
            "automatic skill routing",
            "Wayfinder discovery and delegation",
            "Grillmester → Kokk → Grill-inspektør",
            "Visual Companion",
            "approved, harmless write",
            "rejected write",
        ):
            with self.subTest(check=check):
                self.assertIn(check, self.protocol)

        for blocker in (
            "unexpected write",
            "approval or stop-boundary violation",
            "sensitive data",
            "wrong plugin or agent identity",
            "failed rollback",
        ):
            with self.subTest(blocker=blocker):
                self.assertIn(blocker, self.protocol)

    def test_template_has_one_evidence_contract_for_all_clients(self) -> None:
        self.assertEqual(1, self.template["schemaVersion"])
        self.assertEqual("1.0", self.template["protocolVersion"])
        self.assertEqual("macos-client-validation", self.template["evidenceType"])
        self.assertEqual("macOS", self.template["platform"])
        self.assertFalse(self.template["synthetic"])
        self.assertEqual("0.3.0", self.template["releaseVersion"])
        self.assertEqual(list(CLIENTS), [item["client"] for item in self.template["clientResults"]])

        for client in self.template["clientResults"]:
            with self.subTest(client=client["client"]):
                self.assertTrue(
                    {
                        "clientVersion",
                        "rcTag",
                        "catalogSha",
                        "sourceSha",
                        "resolvedModel",
                    }.issubset(client)
                )
                scenarios = client["scenarioResults"]
                self.assertEqual(SCENARIOS, {item["scenario"] for item in scenarios})
                for scenario in scenarios:
                    self.assertTrue(SCENARIO_FIELDS.issubset(scenario))

                parity = next(
                    item
                    for item in scenarios
                    if item["scenario"] == "harness-parity"
                )
                self.assertEqual(PARITY_CHECKS, set(parity["parityChecks"]))

    def test_synthetic_dry_run_is_safe_and_complete(self) -> None:
        self.assertEqual("0.3.0", self.dry_run["releaseVersion"])
        self.assertEqual("1.0", self.dry_run["protocolVersion"])
        self.assertEqual("macOS", self.dry_run["platform"])
        self.assertTrue(self.dry_run["synthetic"])
        self.assertEqual(list(CLIENTS), [item["client"] for item in self.dry_run["clientResults"]])
        self.assertIn(
            "synthetic dry run only",
            self.dry_run["aggregate"]["maintainerDisposition"],
        )
        self.assertEqual("UNVERIFIED", self.dry_run["aggregate"]["result"])

        forbidden = set(self.dry_run["evidencePolicy"]["forbidden"])
        self.assertTrue(
            {"prompts", "transcripts", "secrets", "personal data", "sensitive diagnostics"}.issubset(
                forbidden
            )
        )
        self.assertEqual(40, len(self.dry_run["release"]["sourceSha"]))

        for client in self.dry_run["clientResults"]:
            with self.subTest(client=client["client"]):
                self.assertTrue(client["clientVersion"].startswith("synthetic-"))
                self.assertTrue(client["resolvedModel"].startswith("synthetic-model-"))
                self.assertEqual(self.dry_run["release"]["rcTag"], client["rcTag"])
                self.assertEqual(
                    self.dry_run["release"]["catalogSha"], client["catalogSha"]
                )
                self.assertEqual(
                    self.dry_run["release"]["sourceSha"], client["sourceSha"]
                )
                self.assertEqual(
                    SCENARIOS,
                    {item["scenario"] for item in client["scenarioResults"]},
                )
                for scenario in client["scenarioResults"]:
                    self.assertTrue(SCENARIO_FIELDS.issubset(scenario))


if __name__ == "__main__":
    unittest.main()
