from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/publish-marketplace.yml"
PROMOTE_WORKFLOW = ROOT / ".github/workflows/promote-release.yml"
RELEASE_WORKFLOW = ROOT / ".github/workflows/publish-release.yml"


class PublishWorkflowContractTest(unittest.TestCase):
    def test_write_credentials_exist_only_in_final_publish_step(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("persist-credentials: false", text)
        self.assertEqual(1, text.count("GH_TOKEN: ${{ github.token }}"))
        self.assertLess(
            text.index("Publish catalog-only commit atomically"),
            text.index("GH_TOKEN: ${{ github.token }}"),
        )
        write_job = text.split("\n  publish:\n", maxsplit=1)[1]
        self.assertIn("contents: write", write_job)
        self.assertEqual(1, write_job.count("      - name:"))
        self.assertNotIn("uses:", write_job)
        self.assertNotIn("python3", write_job)
        self.assertNotIn("--force-with-lease", write_job)
        self.assertLess(
            text.index("Seal validated catalog for publication"),
            text.index("Install pinned GitHub Copilot CLI"),
        )

    def test_publisher_rejects_marketplace_version_reuse(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Refusing to reuse marketplace version", text)
        self.assertIn("Refusing to reuse previously published marketplace version", text)
        self.assertIn("git rev-list --skip=1", text)

    def test_unrelated_main_changes_do_not_republish_plugin(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('- "package-manifest.json"', text)
        self.assertIn('- "plugin/**"', text)
        self.assertIn('- "plugin-nav/**"', text)
        self.assertNotIn("workflow_dispatch", text)
        self.assertNotIn('- "scripts/generate_marketplace.py"', text)
        self.assertNotIn('- ".github/workflows/publish-marketplace.yml"', text)

    def test_catalog_publisher_revalidates_exact_two_package_roster(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        write_job = text.split("\n  publish:\n", maxsplit=1)[1]
        self.assertIn("(.plugins | length) == 2", write_job)
        self.assertIn(
            '[.plugins[].name] == ["grillmester", "grillmester-nav"]',
            write_job,
        )
        self.assertIn('path: "plugin"', write_job)
        self.assertIn('path: "plugin-nav"', write_job)
        self.assertIn('[.plugins[].version] == [$version, $version]', write_job)
        self.assertEqual(2, write_job.count("sha: $source_sha"))

    def test_manual_validator_is_read_only_and_smokes_exact_remote_ref(self) -> None:
        text = PROMOTE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("catalog_sha:", text)
        self.assertIn("refs/remotes/origin/marketplace", text)
        self.assertIn("refs/remotes/origin/main", text)
        self.assertIn("--remote-marketplace-ref", text)
        self.assertIn('--source-root "${SOURCE_ROOT}"', text)
        self.assertNotIn("--source-plugin", text)
        self.assertIn(
            '[.plugins[].name] == ["grillmester", "grillmester-nav"]', text
        )
        self.assertIn('path: "plugin-nav"', text)
        self.assertIn("api.github.com/repos/${GITHUB_REPOSITORY}/releases/tags/${RC_TAG}", text)
        self.assertIn("contents: read", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("GH_TOKEN", text)
        self.assertNotIn("release create", text)

    def test_promoter_and_publisher_share_concurrency_lock(self) -> None:
        publish = WORKFLOW.read_text(encoding="utf-8")
        promote = PROMOTE_WORKFLOW.read_text(encoding="utf-8")
        release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        lock = "group: publish-grillmester-marketplace"
        self.assertIn(lock, publish)
        self.assertIn(lock, promote)
        self.assertIn(lock, release)

    def test_promoter_has_a_real_failing_main_guard(self) -> None:
        text = PROMOTE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('DISPATCH_REF: ${{ github.ref }}', text)
        self.assertIn('[[ "${DISPATCH_REF}" == "refs/heads/main" ]]', text)
        self.assertNotIn("if: github.ref == 'refs/heads/main'", text)

    def test_release_requires_reviewed_request_on_main(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('branches:\n      - main', text)
        self.assertIn('- ".github/release-request.json"', text)
        self.assertNotIn("workflow_dispatch", text)
        self.assertIn(
            '(keys | sort) == ["catalogSha", "channel", "rcTag", "requestId", "schemaVersion"]',
            text,
        )
        self.assertIn('git show "${MAIN_SHA}:.github/release-request.json"', text)
        self.assertIn("request_id=${request_id}", text)
        self.assertIn('BEFORE_SHA: ${{ github.event.before }}', text)
        self.assertEqual(
            2,
            text.count('git diff --name-only "${BEFORE_SHA}" "${MAIN_SHA}"'),
        )
        self.assertEqual(
            2,
            text.count('git merge-base --is-ancestor "${BEFORE_SHA}" "${MAIN_SHA}"'),
        )

    def test_release_write_token_is_confined_to_one_protected_step(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(1, text.count("GH_TOKEN: ${{ github.token }}"))
        self.assertLess(
            text.index("Publish exact reviewed release idempotently"),
            text.index("GH_TOKEN: ${{ github.token }}"),
        )
        write_job = text.split("\n  release:\n", maxsplit=1)[1]
        self.assertIn("environment: grillmester-release", write_job)
        self.assertIn("contents: write", write_job)
        self.assertEqual(1, write_job.count("      - name:"))
        self.assertNotIn("uses:", write_job)
        self.assertNotIn("python3", write_job)
        self.assertIn("origin/main", write_job)
        self.assertIn("origin/marketplace", write_job)
        self.assertIn("--verify-tag", write_job)
        self.assertIn('cmp -s "${regenerated_catalog}" "${catalog_file}"', write_job)
        self.assertIn("jq -cS 'del(.version)'", write_job)
        self.assertIn(
            'cmp -s "${normalized_standard_manifest}" "${rc_standard_manifest_file}"',
            write_job,
        )
        self.assertIn(
            'cmp -s "${normalized_nav_manifest}" "${rc_nav_manifest_file}"',
            write_job,
        )
        self.assertIn(
            'cmp -s "${package_manifest_file}" "${rc_package_manifest_file}"',
            write_job,
        )
        self.assertIn(
            'cmp -s "${regenerated_rc_catalog}" "${rc_catalog_file}"', write_job
        )
        self.assertIn(
            "-- plugin plugin-nav", write_job
        )
        self.assertIn("':(exclude)plugin-nav/plugin.json'", write_job)
        self.assertIn('git ls-tree -r "${RC_CATALOG_SHA}"', write_job)
        self.assertIn("'.tag_name'", write_job)
        self.assertNotIn("git tag -f", write_job)
        self.assertNotIn("git push --force", write_job)
        self.assertNotIn("git push -f", write_job)
        self.assertNotIn("--force-with-lease", write_job)

    def test_release_validates_and_smokes_both_packages(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('--source-root "${SOURCE_ROOT}"', text)
        self.assertNotIn("--source-plugin", text)
        self.assertGreaterEqual(
            text.count('[.plugins[].name] == ["grillmester", "grillmester-nav"]'),
            3,
        )
        self.assertGreaterEqual(text.count('path: "plugin-nav"'), 4)
        self.assertIn(
            'git show "${SOURCE_SHA}:plugin-nav/plugin.json"', text
        )
        self.assertIn(
            'git show "${RC_SOURCE_SHA}:plugin-nav/plugin.json"', text
        )
        self.assertIn(
            '{name: "grillmester-nav", path: "plugin-nav", agents: 0, skills: 10}',
            text,
        )
        self.assertIn(
            '(keys | sort) == ["marketplace", "packages", "schemaVersion"]',
            text,
        )
        self.assertIn(
            '"agents", "author", "description", "license", "name",', text
        )
        self.assertIn(
            '"author", "description", "license", "name", "repository",', text
        )
        self.assertEqual(2, text.count('(.author | keys) == ["name"]'))


if __name__ == "__main__":
    unittest.main()
