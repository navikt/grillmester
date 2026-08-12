from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_preflight_consumer_pilot",
    ROOT / "scripts/preflight_consumer_pilot.py",
)
assert SPEC and SPEC.loader
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def component(path: Path, name: str) -> None:
    write(path, f"---\nname: {name}\ndescription: fixture\n---\n\n# {name}\n")


def json_file(path: Path, value: object) -> None:
    write(path, json.dumps(value, indent=2) + "\n")


def run_git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise AssertionError(
            f"git {' '.join(arguments)} failed: {result.stdout}{result.stderr}"
        )
    return result.stdout.strip()


def init_git(repository: Path) -> None:
    repository.mkdir(parents=True, exist_ok=True)
    run_git(repository, "init", "-q")
    run_git(repository, "config", "user.name", "Fixture")
    run_git(repository, "config", "user.email", "fixture@example.test")


def commit_all(repository: Path, message: str) -> str:
    run_git(repository, "add", "-A")
    run_git(repository, "commit", "-qm", message)
    return run_git(repository, "rev-parse", "HEAD")


def tree_digest(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.parts
    }


class ConsumerPilotPreflightTest(unittest.TestCase):
    ref = "v1.0.0-rc.1"
    hovmester_sha = "b" * 40

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.plugin = self.root / "plugin-repo"
        self.catalog_repo = self.root / "catalog-repo"
        self.consumer = self.root / "consumer"
        self.catalog = self.catalog_repo / ".github/plugin/marketplace.json"
        self.baseline_path = self.root / "pilot-baseline.json"
        self.create_plugin()
        self.create_consumer()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create_plugin(self) -> None:
        init_git(self.plugin)
        # Agent identity is deliberately different from frontmatter `name`.
        component(self.plugin / "plugin/agents/barista.agent.md", "coffee-frontmatter")
        component(self.plugin / "plugin/agents/kokk.md", "cook-frontmatter")
        component(
            self.plugin / "plugin/skills/grillmester-review/SKILL.md",
            "grillmester-review",
        )
        json_file(
            self.plugin / "plugin/plugin.json",
            {
                "name": "grillmester",
                "version": "1.0.0-rc.1",
                "repository": "https://github.com/navikt/grillmester",
            },
        )
        source_sha = commit_all(self.plugin, "plugin source")
        init_git(self.catalog_repo)
        json_file(
            self.catalog,
            {
                "name": "grillmester",
                "metadata": {"version": "1.0.0-rc.1"},
                "plugins": [
                    {
                        "name": "grillmester",
                        "version": "1.0.0-rc.1",
                        "source": {
                            "source": "github",
                            "repo": "navikt/grillmester",
                            "path": "plugin",
                            "sha": source_sha,
                        },
                    }
                ],
            },
        )
        self.catalog_sha = commit_all(self.catalog_repo, "release catalog")
        run_git(self.catalog_repo, "tag", self.ref)

    def create_consumer(self) -> None:
        init_git(self.consumer)
        component(self.consumer / ".github/agents/barista.agent.md", "not-the-id")
        component(self.consumer / ".github/agents/kokk.agent.md", "also-not-the-id")
        component(self.consumer / ".github/agents/local.agent.md", "local")
        component(self.consumer / ".github/skills/review/SKILL.md", "review")
        write(self.consumer / ".github/copilot-instructions.md", "keep me\n")
        write(self.consumer / ".github/instructions/kotlin.instructions.md", "keep\n")
        write(self.consumer / ".github/PULL_REQUEST_TEMPLATE.md", "keep me\n")
        write(self.consumer / ".github/ISSUE_TEMPLATE/task.yml", "name: task\n")
        managed = [
            ".github/agents/barista.agent.md",
            ".github/agents/kokk.agent.md",
            ".github/agents/local.agent.md",
            ".github/skills/review/SKILL.md",
            ".github/copilot-instructions.md",
            ".github/instructions/kotlin.instructions.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
            ".github/ISSUE_TEMPLATE/task.yml",
        ]
        self.write_manifest(managed)
        self.write_caller()
        self.baseline_head = commit_all(self.consumer, "consumer baseline")

    def write_manifest(self, managed: list[str]) -> None:
        json_file(
            self.consumer / ".github/.hovmester-manifest.json",
            {
                "source": "navikt/hovmester",
                "source_sha": self.hovmester_sha,
                "files": managed,
            },
        )

    def write_caller(self, path: str = ".github/workflows/hovmester-sync.yml") -> None:
        write(
            self.consumer / path,
            "name: Hovmester sync\n"
            "on:\n  schedule:\n    - cron: '0 5 * * *'\n  workflow_dispatch:\n"
            "jobs:\n  sync:\n"
            "    uses: navikt/hovmester/.github/workflows/hovmester-sync.yml@main\n"
            "    with:\n"
            "      collections: \"backend\"\n"
            "      exclude: \"legacy\"\n"
            "      github_project: \"navikt/157\"\n"
            "      team_repo: \"navikt/team-esyfo\"\n"
            "      pr_app_id: \"2906300\"\n",
        )

    def activate(self) -> None:
        json_file(
            self.consumer / ".github/copilot/settings.json",
            {
                "extraKnownMarketplaces": {
                    "grillmester": {
                        "source": {
                            "source": "github",
                            "repo": "navikt/grillmester",
                            "ref": self.ref,
                        }
                    }
                },
                "enabledPlugins": {"grillmester@grillmester": True},
            },
        )

    def baseline(self) -> dict[str, object]:
        report = PREFLIGHT.build_baseline_report(
            self.plugin, self.consumer, self.catalog, self.ref
        )
        self.assertTrue(report["baselineWritable"], report["blockers"])
        PREFLIGHT.write_baseline(
            report, self.baseline_path, self.consumer, self.plugin
        )
        return report

    def migrate(self, *, leave_caller: bool = False) -> None:
        (self.consumer / ".github/agents/barista.agent.md").unlink()
        (self.consumer / ".github/agents/kokk.agent.md").unlink()
        if leave_caller:
            self.write_caller()
        else:
            (self.consumer / ".github/workflows/hovmester-sync.yml").unlink()
        manifest = json.loads(
            (self.consumer / ".github/.hovmester-manifest.json").read_text()
        )
        manifest["files"] = [
            path
            for path in manifest["files"]
            if path
            not in {
                ".github/agents/barista.agent.md",
                ".github/agents/kokk.agent.md",
            }
        ]
        json_file(self.consumer / ".github/.hovmester-manifest.json", manifest)
        self.activate()
        commit_all(self.consumer, "pilot migration")

    def postflight(self) -> dict[str, object]:
        return PREFLIGHT.build_postflight_report(
            self.plugin,
            self.consumer,
            self.catalog,
            self.ref,
            self.baseline_path,
        )

    def test_agent_ids_are_filename_derived_in_all_supported_roots(self) -> None:
        component(self.consumer / ".claude/agents/barista.md", "different-name")

        agents, _ = PREFLIGHT.consumer_rosters(self.consumer)
        plugin_agents, _ = PREFLIGHT.plugin_rosters(self.plugin)
        collisions = PREFLIGHT.collisions(plugin_agents, agents, set())

        self.assertEqual("barista", PREFLIGHT.agent_id(Path("barista.agent.md")))
        self.assertEqual("barista", PREFLIGHT.agent_id(Path("barista.md")))
        self.assertEqual(
            [".claude/agents/barista.md", ".github/agents/barista.agent.md"],
            agents["barista"],
        )
        self.assertEqual(2, len([item for item in collisions if item["id"] == "barista"]))

    def test_baseline_binds_release_and_captures_exact_migration_contract(self) -> None:
        report = PREFLIGHT.build_baseline_report(
            self.plugin, self.consumer, self.catalog, self.ref
        )

        self.assertEqual("BLOCKED", report["verdict"])
        self.assertTrue(report["baselineWritable"])
        self.assertEqual(
            ["barista", "kokk", "legacy"],
            report["migrationContract"]["syncInputs"]["exclude"],
        )
        self.assertEqual(
            {
                "collections": ["backend"],
                "exclude": ["barista", "kokk", "legacy"],
                "githubProject": "navikt/157",
                "teamRepo": "navikt/team-esyfo",
                "prAppId": "2906300",
            },
            report["migrationContract"]["syncInputs"],
        )
        self.assertEqual(self.baseline_head, report["migrationContract"]["baselineHead"])
        self.assertEqual(2, len(report["collisions"]["agents"]))
        self.assertEqual([], report["collisions"]["skills"])
        self.assertEqual(2, len(report["preserve"]["instructions"]))
        self.assertEqual(2, len(report["preserve"]["templates"]))
        self.assertEqual(self.catalog_sha, report["release"]["catalogSha"])
        self.assertRegex(report["release"]["catalogSha256"], r"^[0-9a-f]{64}$")

    def test_release_catalog_must_be_the_exact_tagged_catalog_only_commit(self) -> None:
        run_git(self.catalog_repo, "tag", "-d", self.ref)
        with self.assertRaisesRegex(PREFLIGHT.PreflightError, "tag"):
            PREFLIGHT.build_baseline_report(
                self.plugin, self.consumer, self.catalog, self.ref
            )

        run_git(self.catalog_repo, "tag", self.ref)
        write(self.catalog_repo / "unexpected.txt", "not catalog-only\n")
        commit_all(self.catalog_repo, "catalog drift")
        run_git(self.catalog_repo, "tag", "-f", self.ref)
        with self.assertRaisesRegex(PREFLIGHT.PreflightError, "catalog-only"):
            PREFLIGHT.build_baseline_report(
                self.plugin, self.consumer, self.catalog, self.ref
            )

    def test_dirty_or_wrong_release_checkout_blocks_baseline(self) -> None:
        write(self.plugin / "dirty.txt", "dirty\n")

        report = PREFLIGHT.build_baseline_report(
            self.plugin, self.consumer, self.catalog, self.ref
        )

        self.assertFalse(report["baselineWritable"])
        self.assertIn("plugin checkout is dirty", report["blockers"])

    def test_missing_or_multiple_hovmester_callers_blocks_baseline(self) -> None:
        self.write_caller(".github/workflows/second.yaml")
        commit_all(self.consumer, "ambiguous callers")

        report = PREFLIGHT.build_baseline_report(
            self.plugin, self.consumer, self.catalog, self.ref
        )

        self.assertFalse(report["baselineWritable"])
        self.assertIn(
            "baseline requires exactly one unambiguous Hovmester caller",
            report["blockers"],
        )

    def test_manifest_rejects_traversal_outside_owned_roots_and_symlinks(self) -> None:
        self.write_manifest(["../outside"])
        with self.assertRaisesRegex(PREFLIGHT.PreflightError, "unsafe Hovmester"):
            PREFLIGHT.hovmester_state(self.consumer)

        outside = self.root / "outside.md"
        write(outside, "outside\n")
        managed = self.consumer / ".github/agents/linked.agent.md"
        managed.symlink_to(outside)
        self.write_manifest([".github/agents/linked.agent.md"])
        with self.assertRaisesRegex(PREFLIGHT.PreflightError, "symlink"):
            PREFLIGHT.hovmester_state(self.consumer)

    def test_postflight_passes_only_exact_clean_migration_diff(self) -> None:
        self.baseline()
        self.migrate()

        report = self.postflight()

        self.assertEqual("MIGRATION_PREFLIGHT_PASSED", report["verdict"])
        self.assertEqual([], report["blockers"])
        self.assertEqual(
            {
                ".github/.hovmester-manifest.json": "M",
                ".github/agents/barista.agent.md": "D",
                ".github/agents/kokk.agent.md": "D",
                ".github/copilot/settings.json": "A",
                ".github/workflows/hovmester-sync.yml": "D",
            },
            report["gitDiff"]["changes"],
        )
        self.assertTrue(
            all(item["matches"] for item in report["comparisons"].values())
        )

    def test_manual_only_hovmester_caller_is_still_blocked(self) -> None:
        self.baseline()
        self.migrate(leave_caller=True)

        report = self.postflight()

        self.assertEqual("BLOCKED", report["verdict"])
        self.assertIn(
            "baseline comparison failed: callerWorkflowsRemoved", report["blockers"]
        )

    def test_protected_hash_or_unapproved_diff_blocks_postflight(self) -> None:
        self.baseline()
        self.migrate()
        write(self.consumer / ".github/copilot-instructions.md", "drift\n")
        write(self.consumer / "UNAPPROVED.md", "scope creep\n")
        commit_all(self.consumer, "unapproved drift")

        report = self.postflight()

        self.assertEqual("BLOCKED", report["verdict"])
        self.assertIn("baseline comparison failed: protectedFiles", report["blockers"])
        self.assertIn("baseline comparison failed: gitDiff", report["blockers"])

    def test_local_roster_or_manifest_drift_blocks_postflight(self) -> None:
        self.baseline()
        self.migrate()
        component(self.consumer / ".claude/agents/surprise.md", "ignored-name")
        manifest = json.loads(
            (self.consumer / ".github/.hovmester-manifest.json").read_text()
        )
        manifest["files"].remove(".github/agents/local.agent.md")
        json_file(self.consumer / ".github/.hovmester-manifest.json", manifest)
        commit_all(self.consumer, "roster and manifest drift")

        report = self.postflight()

        self.assertIn("baseline comparison failed: localComponents", report["blockers"])
        self.assertIn("baseline comparison failed: manifestFiles", report["blockers"])

    def test_audit_is_read_only_and_baseline_can_only_be_created_outside_consumer(
        self,
    ) -> None:
        before_plugin = tree_digest(self.plugin)
        before_consumer = tree_digest(self.consumer)
        report = PREFLIGHT.build_baseline_report(
            self.plugin, self.consumer, self.catalog, self.ref
        )

        with self.assertRaisesRegex(PREFLIGHT.PreflightError, "outside"):
            PREFLIGHT.write_baseline(
                report,
                self.consumer / ".pilot-baseline.json",
                self.consumer,
                self.plugin,
            )
        with self.assertRaisesRegex(PREFLIGHT.PreflightError, "outside"):
            PREFLIGHT.write_baseline(
                report,
                self.plugin / ".pilot-baseline.json",
                self.consumer,
                self.plugin,
            )
        with self.assertRaisesRegex(PREFLIGHT.PreflightError, "outside"):
            PREFLIGHT.write_baseline(
                report,
                self.catalog_repo / ".pilot-baseline.json",
                self.consumer,
                self.plugin,
            )
        external_git_common = self.root / "external-git-common"
        external_git_common.mkdir()
        with mock.patch.object(
            PREFLIGHT,
            "git_metadata_roots",
            return_value={external_git_common.resolve()},
        ), self.assertRaisesRegex(PREFLIGHT.PreflightError, "Git metadata"):
            PREFLIGHT.write_baseline(
                report,
                external_git_common / "pilot-baseline.json",
                self.consumer,
                self.plugin,
            )
        PREFLIGHT.write_baseline(
            report, self.baseline_path, self.consumer, self.plugin
        )
        with self.assertRaisesRegex(PREFLIGHT.PreflightError, "overwrite"):
            PREFLIGHT.write_baseline(
                report, self.baseline_path, self.consumer, self.plugin
            )

        self.assertEqual(before_plugin, tree_digest(self.plugin))
        self.assertEqual(before_consumer, tree_digest(self.consumer))
        self.assertTrue(self.baseline_path.is_file())


if __name__ == "__main__":
    unittest.main()
