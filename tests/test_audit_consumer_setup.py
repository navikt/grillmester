from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("consumer_setup_audit", ROOT / "scripts/audit_consumer_setup.py")
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def skill(name: str, body: str = "Portable workflow.") -> str:
    return f"---\nname: {name}\ndescription: fixture\n---\n\n{body}\n"


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()


class ConsumerSetupAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.plugin = self.root / "plugin-source"
        self.consumer = self.root / "consumer"
        self.consumer.mkdir()
        self.source = self.root / "hovmester-source"
        self.source.mkdir()
        git(self.source, "init", "-q")
        git(self.source, "config", "user.name", "Fixture")
        git(self.source, "config", "user.email", "fixture@example.test")
        write(self.source / ".github/skills/review/SKILL.md", skill("review", "Old reviewed workflow."))
        write(self.source / ".github/skills/review/references/checklist.md", "Original reference\n")
        write(self.source / ".github/agents/hovmester.agent.md", "Original agent\n")
        git(self.source, "add", ".")
        git(self.source, "commit", "-qm", "Original setup")
        self.source_sha = git(self.source, "rev-parse", "HEAD")
        write(self.plugin / "plugin/skills/review/SKILL.md", skill("review"))
        write(self.plugin / "plugin/skills/doctor/SKILL.md", skill("doctor"))
        write(self.plugin / "plugin/agents/grillmester.agent.md", "Current agent\n")
        self.lock = {
            "sources": {"hovmester": {"repository": "navikt/hovmester", "revision": self.source_sha}},
            "agents": {"grillmester": {"source": "hovmester", "sourcePath": ".github/agents/hovmester.agent.md"}},
            "skills": {
                "review": {"source": "hovmester", "sourcePath": ".github/skills/review"},
                "doctor": {"source": "hovmester", "sourcePath": ".github/copilot-instructions.md"},
            },
        }
        write(self.plugin / "policy/content-lock.json", json.dumps(self.lock))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def report(self, **kwargs: object) -> dict:
        return AUDIT.audit(self.consumer, self.plugin, **kwargs)

    def component(self, report: dict, path: str) -> dict:
        return next(item for item in report["components"] if item["path"] == path)

    def manifest(self, paths: list[str]) -> None:
        write(self.consumer / AUDIT.MANIFEST, json.dumps({"source": "navikt/hovmester", "source_sha": self.source_sha, "files": paths}))

    def old_review(self) -> None:
        for path in (self.source / ".github/skills/review").rglob("*"):
            if path.is_file():
                write(self.consumer / path.relative_to(self.source), path.read_text())

    def distribution_fixture(self, team_repo: str | None) -> tuple[str, str]:
        # A top-level exception proves that the historical reader is never run.
        write(self.source / "scripts/sync.py", 'raise RuntimeError("historical sync must never execute")\n')
        write(self.source / ".github/workflows/hovmester-sync.yml", "on:\n  workflow_call:\n    inputs:\n      team_repo:\n        default: ''\n# Reviewed fixture passes the input unchanged to the reader.\n")
        template = skill("review", "Review the domain.\nTeam repository: ${TEAM_REPO}\nKeep local rules.")
        write(self.source / "dist/skills/review/SKILL.md", template)
        write(self.source / "dist/skills/review/references/rules.md", "Rules for ${TEAM_REPO}\nPortable rule.\n")
        git(self.source, "add", ".")
        git(self.source, "commit", "-qm", "Distributed setup")
        revision = git(self.source, "rev-parse", "HEAD")
        reader = git(self.source, "rev-parse", "HEAD:scripts/sync.py")
        self.workflow_blob = git(self.source, "rev-parse", "HEAD:.github/workflows/hovmester-sync.yml")
        content = template.replace("${TEAM_REPO}", team_repo) if team_repo else template.replace("Team repository: ${TEAM_REPO}\n", "")
        write(self.consumer / ".github/skills/review/SKILL.md", content)
        reference = f"Rules for {team_repo}\nPortable rule.\n" if team_repo else "Portable rule.\n"
        write(self.consumer / ".github/skills/review/references/rules.md", reference)
        write(self.consumer / AUDIT.MANIFEST, json.dumps({"source": "navikt/hovmester", "source_sha": revision, "files": [".github/skills/review/SKILL.md", ".github/skills/review/references/rules.md"]}))
        caller = "jobs:\n  sync:\n    uses: navikt/hovmester/.github/workflows/hovmester-sync.yml@main\n    with:\n      collections: backend\n"
        if team_repo is not None:
            caller += f'      team_repo: "{team_repo}"\n'
        write(self.consumer / ".github/workflows/sync.yml", caller)
        return revision, reader

    def test_manifest_revision_and_team_repo_substitution_verify_complete_dist_copy(self) -> None:
        revision, reader = self.distribution_fixture("navikt/team-fixture")
        with mock.patch.multiple(AUDIT, REVIEWED_HOVMESTER_SYNC_BLOB=reader, REVIEWED_HOVMESTER_WORKFLOW_BLOB=self.workflow_blob):
            report = self.report(source_roots={"hovmester": self.source})
        entry = self.component(report, ".github/skills/review")
        self.assertEqual(entry["classification"], "OBSOLETE_UNMODIFIED")
        self.assertEqual(entry["matches"][0]["sourcePath"], "dist/skills/review")
        self.assertEqual(entry["matches"][0]["revision"], revision)
        self.assertNotEqual(revision, self.lock["sources"]["hovmester"]["revision"])
        self.assertEqual(entry["matches"][0]["teamRepoTransform"]["value"], "navikt/team-fixture")
        self.assertEqual(len(entry["files"]), 2)

    def test_reviewed_default_strips_entire_placeholder_lines(self) -> None:
        _, reader = self.distribution_fixture(None)
        with mock.patch.multiple(AUDIT, REVIEWED_HOVMESTER_SYNC_BLOB=reader, REVIEWED_HOVMESTER_WORKFLOW_BLOB=self.workflow_blob):
            report = self.report(source_roots={"hovmester": self.source})
        entry = self.component(report, ".github/skills/review")
        self.assertEqual(entry["classification"], "OBSOLETE_UNMODIFIED")
        self.assertEqual(report["distributionEvidence"]["teamRepoTransform"]["value"], "")

    def test_unrecognized_historical_reader_preserves_component(self) -> None:
        self.distribution_fixture("navikt/team-fixture")
        report = self.report(source_roots={"hovmester": self.source})
        self.assertEqual(report["distributionEvidence"]["status"], "UNVERIFIED")
        self.assertEqual(report["plan"][0]["action"], "PRESERVE_AND_RECONCILE")

    def test_changed_workflow_default_or_passthrough_preserves_component(self) -> None:
        _, reader = self.distribution_fixture(None)
        workflow = self.source / ".github/workflows/hovmester-sync.yml"
        workflow.write_text(workflow.read_text().replace("default: ''", "default: navikt/team-default"))
        git(self.source, "add", ".")
        git(self.source, "commit", "-qm", "Change reusable workflow default")
        manifest_path = self.consumer / AUDIT.MANIFEST
        manifest = json.loads(manifest_path.read_text())
        manifest["source_sha"] = git(self.source, "rev-parse", "HEAD")
        manifest_path.write_text(json.dumps(manifest))
        with mock.patch.multiple(AUDIT, REVIEWED_HOVMESTER_SYNC_BLOB=reader, REVIEWED_HOVMESTER_WORKFLOW_BLOB=self.workflow_blob):
            report = self.report(source_roots={"hovmester": self.source})
        self.assertEqual(report["distributionEvidence"]["status"], "UNVERIFIED")
        self.assertIn("workflow defaults or argument pass-through", report["distributionEvidence"]["reason"])
        self.assertEqual(report["plan"][0]["action"], "PRESERVE_AND_RECONCILE")

    def test_dynamic_ambiguous_or_absent_team_repo_input_preserves_transformed_copy(self) -> None:
        _, reader = self.distribution_fixture("navikt/team-fixture")
        workflow = self.consumer / ".github/workflows/sync.yml"
        original = workflow.read_text()
        for caller in (
            original.replace('"navikt/team-fixture"', '"${{ vars.TEAM_REPO }}"'),
            original + '      team_repo: "navikt/second"\n',
            original.replace('    with:\n      collections: backend\n      team_repo: "navikt/team-fixture"', '    with: ${{ inputs.settings }}'),
            "jobs: {}\n",
        ):
            with self.subTest(caller=caller):
                workflow.write_text(caller)
                with mock.patch.multiple(AUDIT, REVIEWED_HOVMESTER_SYNC_BLOB=reader, REVIEWED_HOVMESTER_WORKFLOW_BLOB=self.workflow_blob):
                    report = self.report(source_roots={"hovmester": self.source})
                self.assertEqual(report["distributionEvidence"]["teamRepoTransform"]["status"], "UNVERIFIED")
                self.assertEqual(report["plan"][0]["action"], "PRESERVE_AND_RECONCILE")

    def test_transformed_copy_with_local_extra_file_is_preserved(self) -> None:
        _, reader = self.distribution_fixture("navikt/team-fixture")
        write(self.consumer / ".github/skills/review/team-rules.md", "Local policy\n")
        with mock.patch.multiple(AUDIT, REVIEWED_HOVMESTER_SYNC_BLOB=reader, REVIEWED_HOVMESTER_WORKFLOW_BLOB=self.workflow_blob):
            report = self.report(source_roots={"hovmester": self.source})
        self.assertEqual(report["plan"][0]["action"], "PRESERVE_AND_RECONCILE")

    def test_absent_manifest_and_caller_are_valid_and_deterministic(self) -> None:
        first, second = self.report(), self.report()
        self.assertEqual(first, second)
        self.assertEqual(first["manifest"]["status"], "ABSENT")
        self.assertEqual(first["summary"]["components"], 0)
        self.assertEqual(first["runtimeResolution"], "UNVERIFIED")

    def test_known_source_bytes_identify_unmodified_copy_without_manifest(self) -> None:
        self.old_review()
        report = self.report(source_roots={"hovmester": self.source})
        entry = self.component(report, ".github/skills/review")
        self.assertEqual(entry["classification"], "OBSOLETE_UNMODIFIED")
        self.assertTrue(entry["idCollision"])
        self.assertFalse(entry["manifestOwned"])
        self.assertEqual(entry["matches"][0]["revision"], self.source_sha)
        self.assertEqual(len(report["plan"][0]["expectedFiles"]), 2)
        self.assertEqual(report["plan"][0]["action"], "REVIEW_REMOVE_EXACT_COPY")

    def test_locked_revision_not_dirty_checkout_is_used(self) -> None:
        self.old_review()
        write(self.source / ".github/skills/review/SKILL.md", "Dirty source change\n")
        entry = self.component(self.report(source_roots={"hovmester": self.source}), ".github/skills/review")
        self.assertEqual(entry["classification"], "OBSOLETE_UNMODIFIED")

    def test_manifest_ownership_is_not_proof_of_unmodified_content(self) -> None:
        self.old_review()
        self.manifest([".github/skills/review/SKILL.md"])
        entry = self.component(self.report(), ".github/skills/review")
        self.assertEqual(entry["classification"], "OWNED_CONTENT_UNVERIFIED")
        write(self.consumer / ".github/skills/review/SKILL.md", skill("review", "Consumer-specific rules."))
        report = self.report(source_roots={"hovmester": self.source})
        entry = self.component(report, ".github/skills/review")
        self.assertEqual(entry["classification"], "OWNED_CUSTOMIZED_OR_TRANSFORMED")
        self.assertEqual(report["plan"][0]["action"], "PRESERVE_AND_RECONCILE")

    def test_extra_reference_prevents_whole_directory_removal(self) -> None:
        self.old_review()
        write(self.consumer / ".github/skills/review/team-rules.md", "Local domain rules\n")
        report = self.report(source_roots={"hovmester": self.source})
        entry = self.component(report, ".github/skills/review")
        self.assertNotEqual(entry["classification"], "OBSOLETE_UNMODIFIED")
        self.assertEqual(report["plan"][0]["action"], "PRESERVE_AND_RECONCILE")

    def test_same_name_local_skill_and_old_instruction_are_preserved(self) -> None:
        write(self.consumer / ".github/skills/doctor/SKILL.md", skill("doctor", "Local operations runbook"))
        old_instruction = "Hovmester context: retain domain vocabulary and all production invariants.\n"
        write(self.consumer / ".github/copilot-instructions.md", old_instruction)
        self.manifest([".github/copilot-instructions.md"])
        report = self.report(source_roots={"hovmester": self.source})
        entry = self.component(report, ".github/skills/doctor")
        self.assertEqual(entry["classification"], "LOCAL_OR_UNKNOWN")
        self.assertTrue(entry["idCollision"])
        self.assertEqual(report["plan"][0]["action"], "PRESERVE_AND_RECONCILE")
        instruction = next(item for item in report["references"] if item["path"] == ".github/copilot-instructions.md")
        self.assertEqual(instruction["action"], "REVIEW_EDIT_PRESERVE_LOCAL_RULES")
        self.assertEqual((self.consumer / instruction["path"]).read_text(), old_instruction)

    def test_old_prefixed_alias_requires_content_evidence(self) -> None:
        write(self.consumer / ".github/skills/grillmester-review/SKILL.md", skill("grillmester-review"))
        report = self.report()
        entry = self.component(report, ".github/skills/grillmester-review")
        self.assertEqual(entry["classification"], "LEGACY_ID_CONTENT_UNVERIFIED")
        self.assertEqual(entry["replacementIds"], ["review"])
        self.assertTrue(entry["legacyPrefixedId"])
        self.assertFalse(entry["idCollision"])

    def test_retired_plugin_ref_can_verify_prefixed_copy(self) -> None:
        git(self.plugin, "init", "-q")
        git(self.plugin, "config", "user.name", "Fixture")
        git(self.plugin, "config", "user.email", "fixture@example.test")
        old = skill("grillmester-review", "Retired portable workflow")
        write(self.plugin / "plugin/skills/grillmester-review/SKILL.md", old)
        git(self.plugin, "add", ".")
        git(self.plugin, "commit", "-qm", "Earlier skill names")
        sha = git(self.plugin, "rev-parse", "HEAD")
        write(self.consumer / ".github/skills/grillmester-review/SKILL.md", old)
        entry = self.component(self.report(retired_ref=sha), ".github/skills/grillmester-review")
        self.assertEqual(entry["classification"], "OBSOLETE_UNMODIFIED")
        self.assertEqual(entry["matches"][0]["source"], "retired-plugin")

    def test_user_scope_is_explicit_and_reported_separately(self) -> None:
        user = self.root / "user-config"
        write(user / "skills/review/SKILL.md", skill("review", "Personal review rules"))
        self.assertEqual(self.report()["components"], [])
        report = self.report(user_roots=[user])
        entry = self.component(report, "skills/review")
        self.assertEqual(entry["scope"], "user")
        self.assertTrue(entry["idCollision"])
        self.assertEqual(entry["classification"], "LOCAL_OR_UNKNOWN")

    def test_workflows_and_instruction_references_report_lines_without_contents(self) -> None:
        write(self.consumer / ".github/workflows/weekly.yml", "jobs:\n  sync:\n    uses: navikt/hovmester/.github/workflows/hovmester-sync.yml@main\n")
        write(self.consumer / "AGENTS.md", "Domain rules.\nUse /grillmester-review for this repo.\n")
        report = self.report()
        workflow = next(item for item in report["references"] if item["category"] == "LEGACY_WORKFLOW")
        self.assertEqual(workflow["matches"][0]["line"], 3)
        self.assertNotIn("uses:", json.dumps(workflow))
        reference = next(item for item in report["references"] if item["path"] == "AGENTS.md")
        self.assertEqual(reference["matches"], [{"line": 2, "terms": ["grillmester-review"]}])
        self.assertEqual(len(reference["sha256"]), 64)

    def test_symlinks_are_unknown_and_never_read(self) -> None:
        outside = self.root / "outside"
        write(outside / "SKILL.md", skill("review"))
        (self.consumer / ".github/skills").mkdir(parents=True)
        (self.consumer / ".github/skills/review").symlink_to(outside, target_is_directory=True)
        report = self.report()
        entry = self.component(report, ".github/skills/review")
        self.assertEqual(entry["classification"], "UNKNOWN_SYMLINK")
        self.assertEqual(entry["files"], {"<symlink>": None})
        self.assertEqual(report["plan"][0]["action"], "PRESERVE_AND_RECONCILE")
        result = subprocess.run(["python3", str(ROOT / "scripts/audit_consumer_setup.py"), str(self.consumer), "--plugin-root", str(self.plugin)], capture_output=True, text=True, check=True)
        self.assertIn("REVIEW_REQUIRED", result.stdout)

    def test_entire_symlinked_skill_root_requires_review(self) -> None:
        outside = self.root / "outside-skills"
        write(outside / "review/SKILL.md", skill("review"))
        (self.consumer / ".github").mkdir()
        (self.consumer / ".github/skills").symlink_to(outside, target_is_directory=True)
        report = self.report()
        entry = self.component(report, ".github/skills")
        self.assertEqual(entry["classification"], "UNKNOWN_SYMLINK")
        self.assertEqual(entry["files"], {"<symlink>": None})
        self.assertEqual(report["plan"][0]["action"], "PRESERVE_AND_RECONCILE")
        result = subprocess.run(["python3", str(ROOT / "scripts/audit_consumer_setup.py"), str(self.consumer), "--plugin-root", str(self.plugin)], capture_output=True, text=True, check=True)
        self.assertIn("REVIEW_REQUIRED", result.stdout)

    def test_audit_does_not_change_consumer_files(self) -> None:
        self.old_review()
        write(self.consumer / "README.md", "Hovmester migration\n")
        before = AUDIT.inventory(self.consumer)
        self.report(source_roots={"hovmester": self.source})
        self.assertEqual(AUDIT.inventory(self.consumer), before)

    def test_invalid_manifest_paths_do_not_establish_ownership(self) -> None:
        self.manifest(["../outside/SKILL.md"])
        self.assertEqual(self.report()["manifest"]["status"], "UNVERIFIED")

    def test_cli_json_is_read_only_and_does_not_offer_apply(self) -> None:
        result = subprocess.run(["python3", str(ROOT / "scripts/audit_consumer_setup.py"), str(self.consumer), "--plugin-root", str(self.plugin), "--json"], capture_output=True, text=True, check=True)
        self.assertTrue(json.loads(result.stdout)["readOnly"])
        result = subprocess.run(["python3", str(ROOT / "scripts/audit_consumer_setup.py"), "--help"], capture_output=True, text=True, check=True)
        self.assertNotIn("--apply", result.stdout)


if __name__ == "__main__":
    unittest.main()
