"""Guardrail phrases and agent floors are enforced by the package validator.

Each check edits one file in memory or in a small temporary plugin root, so
the whole repository is never copied.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_validate_for_guardrails", ROOT / "scripts/validate.py"
)
assert SPEC and SPEC.loader
VALIDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATE)

FLOORS = (
    ("agents/researcher.agent.md", "LANGUAGE_FLOOR", "shared language floor"),
    ("agents/researcher.agent.md", "SECURITY_FLOOR", "shared security floor"),
    (
        "agents/grill-inspektor.agent.md",
        "UNTRUSTED_CONTENT_FLOOR",
        "shared untrusted-content floor",
    ),
    (
        "agents/grillmester.agent.md",
        "GUIDED_COLLABORATION_FLOOR",
        "guided-collaboration floor",
    ),
    (
        "agents/grillmester.agent.md",
        "GRILLMESTER_RISK_REVIEW_FLOOR",
        "portable R3/R4 review floor",
    ),
    (
        "agents/researcher.agent.md",
        "RESEARCHER_EXTERNAL_FALLBACK",
        "external-research capability fallback",
    ),
    (
        "agents/designer.agent.md",
        "DESIGNER_INLINE_IMPLEMENTATION_FLOOR",
        "inline-implementation boundary",
    ),
    (
        "agents/perspektiv.agent.md",
        "PERSPEKTIV_PERSONA_FLOOR",
        "synthetic-persona boundary",
    ),
    ("skills/doctor/SKILL.md", "DOCTOR_READ_ONLY_FLOOR", "read-only doctor boundary"),
    (
        "skills/doctor/SKILL.md",
        "DOCTOR_SURFACE_BOUNDARY_FLOOR",
        "default-agent and code-review boundary",
    ),
    (
        "skills/doctor/SKILL.md",
        "DOCTOR_ACTIVATION_EVIDENCE_FLOOR",
        "cloud activation evidence boundary",
    ),
)


def without(text: str, phrase: str) -> str:
    """Remove every occurrence of ``phrase``, also when it is wrapped.

    A guardrail requires a phrase at least once, so the check is proven by
    removing all of its occurrences.
    """

    pattern = r"\s+".join(re.escape(word) for word in phrase.split())
    updated, count = re.subn(pattern, "", text)
    if not count:
        raise AssertionError(f"phrase not present: {phrase}")
    return updated


class GuardrailTableTest(unittest.TestCase):
    def test_validate_repo_runs_the_guardrails_on_the_real_package(self) -> None:
        with mock.patch.object(
            VALIDATE, "validate_guardrails", wraps=VALIDATE.validate_guardrails
        ) as spy:
            self.assertEqual([], VALIDATE.validate_repo(ROOT))
        spy.assert_called_once()

    def test_repository_satisfies_every_guardrail(self) -> None:
        errors: list[str] = []
        VALIDATE.validate_guardrails(ROOT, errors)
        self.assertEqual([], errors)

    def test_a_missing_guarded_file_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            errors: list[str] = []
            VALIDATE.validate_guardrails(Path(temporary), errors)
        self.assertTrue(errors)
        self.assertTrue(all("file is missing" in error for error in errors))

    def test_each_required_phrase_is_enforced(self) -> None:
        for guardrail in VALIDATE.GUARDRAILS:
            for relative in guardrail.paths:
                text = (ROOT / relative).read_text(encoding="utf-8")
                for phrase in guardrail.required:
                    with self.subTest(guardrail=guardrail.name, path=relative, phrase=phrase):
                        errors = VALIDATE.guardrail_errors(
                            guardrail, relative, without(text, phrase)
                        )
                        self.assertIn(
                            f"{relative}: guardrail {guardrail.name} is missing: {phrase}",
                            errors,
                        )

    def test_each_forbidden_phrase_is_rejected(self) -> None:
        for guardrail in VALIDATE.GUARDRAILS:
            for relative in guardrail.paths:
                text = (ROOT / relative).read_text(encoding="utf-8")
                for phrase in guardrail.forbidden:
                    with self.subTest(guardrail=guardrail.name, path=relative, phrase=phrase):
                        errors = VALIDATE.guardrail_errors(
                            guardrail, relative, f"{text}\n{phrase}\n"
                        )
                        self.assertIn(
                            f"{relative}: guardrail {guardrail.name} forbids: {phrase}",
                            errors,
                        )


class DocumentedCommandTest(unittest.TestCase):
    def test_manual_byok_never_starts_a_bare_copilot(self) -> None:
        local_models = (ROOT / "docs/local-models.md").read_text(encoding="utf-8")
        self.assertNotRegex(local_models, r"(?m)^copilot\s*$")

    def test_opencode_guide_names_the_exact_release_test_baseline(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "grillmester_release_test_baseline_for_guardrails",
            ROOT / "scripts/release_test_baseline.py",
        )
        assert spec and spec.loader
        baseline = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = baseline
        spec.loader.exec_module(baseline)
        release_test = baseline.CONTRACT["releaseTest"]
        guide = (ROOT / "docs/opencode.md").read_text(encoding="utf-8")
        self.assertIn(f"opencode-ai@{release_test['opencodeVersion']}", guide)
        self.assertIn(release_test["cpltRelease"], guide)


class AgentFloorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        errors: list[str] = []
        _, cls.agent_contracts, cls.skill_contracts = VALIDATE.load_content_lock(
            ROOT, errors
        )
        if errors:
            raise AssertionError(errors)

    def floor_errors(self, relative: str, text: str) -> list[str]:
        with tempfile.TemporaryDirectory() as temporary:
            plugin = Path(temporary)
            target = plugin / relative
            target.parent.mkdir(parents=True)
            target.write_text(text, encoding="utf-8")
            errors: list[str] = []
            if relative.startswith("agents/"):
                VALIDATE.validate_agents(plugin, self.agent_contracts, errors)
            else:
                VALIDATE.validate_skills(
                    plugin, self.skill_contracts, errors, package_name="grillmester"
                )
            return errors

    def test_each_floor_is_enforced(self) -> None:
        for relative, constant, message in FLOORS:
            text = (ROOT / "plugin" / relative).read_text(encoding="utf-8")
            with self.subTest(floor=constant, path=relative):
                intact = self.floor_errors(relative, text)
                self.assertFalse(any(message in error for error in intact), intact)
                drifted = self.floor_errors(
                    relative, without(text, getattr(VALIDATE, constant))
                )
                self.assertTrue(any(message in error for error in drifted), drifted)


if __name__ == "__main__":
    unittest.main()
