from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_validate_evals", ROOT / "scripts/validate_evals.py"
)
assert SPEC and SPEC.loader
VALIDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATE)


class EvalContractValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "package"
        shutil.copytree(
            ROOT,
            self.root,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def corpus(self) -> dict:
        return json.loads(
            (self.root / "evals/corpus.v1.json").read_text(encoding="utf-8")
        )

    def write_corpus(self, corpus: dict) -> None:
        (self.root / "evals/corpus.v1.json").write_text(
            json.dumps(corpus), encoding="utf-8"
        )

    def write_schema(self, schema: dict) -> None:
        (self.root / "evals/schema.v1.json").write_text(
            json.dumps(schema), encoding="utf-8"
        )

    def errors(self) -> list[str]:
        return VALIDATE.validate_repo(self.root)

    def assert_error(self, fragment: str) -> None:
        errors = self.errors()
        self.assertTrue(
            any(fragment in error for error in errors),
            f"expected {fragment!r} in validation errors: {errors}",
        )

    def test_actual_eval_contract_is_valid(self) -> None:
        self.assertEqual([], VALIDATE.validate_repo(ROOT))

    def test_unknown_top_level_field_is_rejected(self) -> None:
        corpus = self.corpus()
        corpus["aggregateF1"] = 0.95
        self.write_corpus(corpus)
        self.assert_error("unknown field aggregateF1")

    def test_unknown_case_field_is_rejected(self) -> None:
        corpus = self.corpus()
        corpus["cases"][0]["expectedMagic"] = True
        self.write_corpus(corpus)
        self.assert_error("unknown field expectedMagic")

    def test_case_without_positive_assertion_is_rejected(self) -> None:
        corpus = self.corpus()
        corpus["cases"][0]["assertions"]["positive"] = []
        self.write_corpus(corpus)
        self.assert_error("needs at least one positive assertion")

    def test_missing_assertion_contract_is_rejected(self) -> None:
        corpus = self.corpus()
        del corpus["cases"][0]["assertions"]
        self.write_corpus(corpus)
        self.assert_error("missing required field assertions")

    def test_case_without_negative_assertion_is_rejected(self) -> None:
        corpus = self.corpus()
        corpus["cases"][0]["assertions"]["negative"] = []
        self.write_corpus(corpus)
        self.assert_error("needs at least one negative assertion")

    def test_weakened_safety_threshold_is_rejected(self) -> None:
        corpus = self.corpus()
        corpus["policies"]["thresholds"]["safety"]["minimumPasses"] = 2
        self.write_corpus(corpus)
        self.assert_error("safety threshold must be 3/3")

    def test_behavioral_and_deterministic_threshold_drift_is_rejected(self) -> None:
        corpus = self.corpus()
        corpus["policies"]["thresholds"]["behavioral"] = {
            "repetitions": 4,
            "minimumPasses": 2,
        }
        corpus["policies"]["thresholds"]["deterministic"] = {
            "minimumPassRate": 0.99
        }
        self.write_corpus(corpus)
        self.assert_error("behavioral threshold must be 2/3")
        self.assert_error("deterministic threshold must be 100%")

    def test_invalid_ai_credit_caps_are_rejected(self) -> None:
        corpus = self.corpus()
        corpus["policies"]["aiCreditCaps"]["maxPerRun"] = 0
        corpus["policies"]["aiCreditCaps"]["maxPerSuite"] = 1
        corpus["cases"][4]["execution"]["maxAiCreditsTotal"] = 74
        self.write_corpus(corpus)
        self.assert_error("maxPerRun must be a positive integer")
        self.assert_error("must equal repetitions times maxAiCreditsPerRun")
        self.assert_error("declared case budgets exceed maxPerSuite")

    def test_reference_to_absent_agent_is_rejected(self) -> None:
        corpus = self.corpus()
        corpus["statusContracts"][0]["agent"] = "ghost-agent"
        self.write_corpus(corpus)
        self.assert_error("references absent agent ghost-agent")

    def test_reference_to_absent_skill_is_rejected(self) -> None:
        corpus = self.corpus()
        corpus["confusablePairs"][0]["skillIds"][0] = "grillmester-ghost"
        self.write_corpus(corpus)
        self.assert_error("references absent skill grillmester-ghost")

    def test_eval_roster_includes_optional_nav_add_on_skills(self) -> None:
        nav_skill = self.root / "plugin-nav/skills/grillmester-nav-troubleshoot"
        shutil.rmtree(nav_skill)
        self.assert_error("references absent skill grillmester-nav-troubleshoot")

    def test_case_assertion_and_topology_references_are_checked(self) -> None:
        corpus = self.corpus()
        corpus["cases"][4]["assertions"]["positive"][0]["target"] = (
            "grillmester-ghost"
        )
        corpus["cases"][12]["topology"]["edges"][0]["to"] = "ghost-agent"
        self.write_corpus(corpus)
        self.assert_error("assertion references absent skill grillmester-ghost")
        self.assert_error("topology references absent agent ghost-agent")

    def test_unsafe_case_requires_zero_side_effects(self) -> None:
        corpus = self.corpus()
        unsafe_case = next(case for case in corpus["cases"] if case["unsafe"])
        unsafe_case["assertions"]["sideEffects"]["maxExternalWrites"] = 1
        self.write_corpus(corpus)
        self.assert_error("unsafe case requires zero side-effect ceilings")

    def test_unknown_case_tool_and_assertion_ids_are_rejected(self) -> None:
        corpus = self.corpus()
        corpus["confusablePairs"][0]["caseIds"][0] = "missing-case"
        corpus["cases"][0]["assertions"]["tools"]["required"] = ["telepathy"]
        corpus["cases"][0]["assertions"]["positive"][0]["kind"] = "magic"
        self.write_corpus(corpus)
        self.assert_error("references unknown case missing-case")
        self.assert_error("references unknown tool telepathy")
        self.assert_error("unknown assertion kind magic")

    def test_unknown_nested_field_is_rejected(self) -> None:
        corpus = self.corpus()
        corpus["cases"][0]["assertions"]["positive"][0]["weight"] = 0.5
        self.write_corpus(corpus)
        self.assert_error("unknown field weight")

    def test_unknown_policy_field_is_rejected(self) -> None:
        corpus = self.corpus()
        corpus["policies"]["weightedAverage"] = True
        self.write_corpus(corpus)
        self.assert_error("unknown field weightedAverage")

    def test_case_repetitions_must_match_evaluation_class(self) -> None:
        corpus = self.corpus()
        corpus["cases"][0]["execution"]["repetitions"] = 2
        unsafe_case = next(case for case in corpus["cases"] if case["unsafe"])
        unsafe_case["execution"] = {
            "repetitions": 2,
            "maxAiCreditsPerRun": 25,
            "maxAiCreditsTotal": 50,
        }
        self.write_corpus(corpus)
        self.assert_error("behavioral case must declare 3 repetitions")
        self.assert_error("safety case must declare 3 repetitions")

    def test_unknown_status_contract_and_status_are_rejected(self) -> None:
        corpus = self.corpus()
        delegation = next(
            case
            for case in corpus["cases"]
            if case["id"] == "delegation-grillmester-one-writer"
        )
        degradation = next(
            case
            for case in corpus["cases"]
            if case["id"] == "degradation-researcher-no-web"
        )
        delegation["assertions"]["positive"][1]["target"] = "ghost-result/DONE"
        degradation["assertions"]["positive"][0]["target"] = (
            "researcher-result/TEAPOT"
        )
        self.write_corpus(corpus)
        self.assert_error("references unknown status contract ghost-result")
        self.assert_error("references unknown status TEAPOT")

    def test_duplicate_case_and_assertion_ids_are_rejected(self) -> None:
        corpus = self.corpus()
        corpus["cases"][1]["id"] = corpus["cases"][0]["id"]
        corpus["cases"][12]["assertions"]["negative"][1]["id"] = (
            corpus["cases"][12]["assertions"]["negative"][0]["id"]
        )
        self.write_corpus(corpus)
        self.assert_error("duplicate case id")
        self.assert_error("duplicate assertion id")

    def test_schema_version_and_reference_are_enforced(self) -> None:
        corpus = self.corpus()
        corpus["schemaVersion"] = 2
        corpus["$schema"] = "./schema.v2.json"
        self.write_corpus(corpus)
        self.assert_error("schemaVersion must be 1")
        self.assert_error("$schema must reference ./schema.v1.json")

    def test_empty_schema_is_rejected(self) -> None:
        self.write_schema({})
        self.assert_error("schema.v1.json must define the v1 corpus contract")

    def test_incomplete_corpus_is_rejected(self) -> None:
        self.write_corpus({"$schema": "./schema.v1.json", "schemaVersion": 1})
        self.assert_error("corpus missing required field cases")
        self.assert_error("corpus missing required field policies")

    def test_invalid_case_enums_and_missing_delegation_topology_are_rejected(self) -> None:
        corpus = self.corpus()
        delegation = next(
            case for case in corpus["cases"] if case["kind"] == "delegation-topology"
        )
        del delegation["topology"]
        invalid = corpus["cases"][0]
        invalid["kind"] = "magic-routing"
        invalid["runner"] = "automatic"
        invalid["unsafe"] = "false"
        self.write_corpus(corpus)
        self.assert_error("unknown case kind magic-routing")
        self.assert_error("unknown runner automatic")
        self.assert_error("unsafe must be a boolean")
        self.assert_error("delegation case requires topology")

    def test_wrong_nested_contract_types_are_rejected(self) -> None:
        corpus = self.corpus()
        corpus["cases"][0]["assertions"] = []
        corpus["cases"][1]["assertions"]["tools"] = []
        corpus["cases"][2]["assertions"]["sideEffects"] = []
        corpus["cases"][3]["execution"] = []
        delegation = next(
            case for case in corpus["cases"] if case["kind"] == "delegation-topology"
        )
        delegation["topology"] = []
        self.write_corpus(corpus)
        self.assert_error("assertions must be an object")
        self.assert_error("assertions.tools must be an object")
        self.assert_error("assertions.sideEffects must be an object")
        self.assert_error("execution must be an object")
        self.assert_error("topology must be an object")

    def test_wrong_top_level_contract_types_are_rejected(self) -> None:
        corpus = self.corpus()
        corpus["policies"] = []
        corpus["statusContracts"] = {}
        corpus["confusablePairs"] = {}
        corpus["cases"] = {}
        self.write_corpus(corpus)
        self.assert_error("policies must be an object")
        self.assert_error("statusContracts must be an array")
        self.assert_error("confusablePairs must be an array")
        self.assert_error("cases must be an array")

    def test_future_sdk_case_requires_current_subject_agent(self) -> None:
        corpus = self.corpus()
        case = next(case for case in corpus["cases"] if case["runner"] == "future-sdk")
        case.pop("subjectAgent", None)
        self.write_corpus(corpus)
        self.assert_error("future-sdk case requires subjectAgent")

    def test_response_signal_requires_registered_oracle(self) -> None:
        corpus = self.corpus()
        corpus["responseSignals"] = []
        self.write_corpus(corpus)
        self.assert_error("response-signal target has no registered oracle")

    def test_status_contract_drift_from_agent_is_rejected(self) -> None:
        corpus = self.corpus()
        kokk = next(
            contract
            for contract in corpus["statusContracts"]
            if contract["id"] == "kokk-result"
        )
        kokk["statuses"].remove("NEEDS_DECISION")
        self.write_corpus(corpus)
        self.assert_error("kokk-result drifts from agent kokk")

    def test_confusable_pair_requires_both_routing_directions(self) -> None:
        corpus = self.corpus()
        generic_case = next(
            case
            for case in corpus["cases"]
            if case["id"] == "skill-generic-architecture-review"
        )
        generic_case["assertions"]["negative"][0]["target"] = (
            "grillmester-e2e-tests"
        )
        self.write_corpus(corpus)
        self.assert_error("must exercise both routing directions")

    def test_doctor_adr_routing_covers_review_and_post_choice_stages(self) -> None:
        corpus = self.corpus()
        pair = next(
            (
                pair
                for pair in corpus["confusablePairs"]
                if pair["id"] == "doctor-nav-review-vs-adr-authoring"
            ),
            None,
        )
        self.assertIsNotNone(pair, "missing Doctor ADR stage-routing contract")
        assert pair is not None
        self.assertEqual(
            {
                "grillmester-nav-architecture-review",
                "grillmester-domain-modeling",
            },
            set(pair["skillIds"]),
        )

        cases = {case["id"]: case for case in corpus["cases"]}
        expected = {
            "doctor-nav-review-before-adr": (
                "grillmester-nav-architecture-review",
                "grillmester-domain-modeling",
            ),
            "doctor-domain-modeling-after-adr-choice": (
                "grillmester-domain-modeling",
                "grillmester-nav-architecture-review",
            ),
        }
        self.assertEqual(set(expected), set(pair["caseIds"]))
        for case_id, (positive_skill, negative_skill) in expected.items():
            case = cases[case_id]
            positive = {
                (assertion["kind"], assertion["target"])
                for assertion in case["assertions"]["positive"]
            }
            negative = {
                (assertion["kind"], assertion["target"])
                for assertion in case["assertions"]["negative"]
            }
            self.assertIn(("agent-selected", "doctor-who"), positive)
            self.assertIn(("skill-invoked", positive_skill), positive)
            self.assertIn(("skill-invoked", negative_skill), negative)


if __name__ == "__main__":
    unittest.main()
