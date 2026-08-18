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
        self.assertEqual(1, text.count("contents: write"))
        self.assertLess(
            text.index("Publish catalog-only commit atomically"),
            text.index("GH_TOKEN: ${{ github.token }}"),
        )
        write_job = text.split("\n  publish:\n", maxsplit=1)[1].split(
            "\n  remote-smoke:\n", maxsplit=1
        )[0]
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
        self.assertIn('git ls-remote --heads origin "refs/heads/${MARKETPLACE_BRANCH}"', text)
        self.assertIn("git push origin --atomic", text)

    def test_idempotent_rerun_requires_tip_bytes_to_match_sealed_catalog(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        write_job = text.split("\n  publish:\n", maxsplit=1)[1].split(
            "\n  remote-smoke:\n", maxsplit=1
        )[0]
        source_match = '[[ "${SOURCE_SHA}" == "${previous_source_sha}" ]]'
        digest = (
            'previous_catalog_sha256="$(git show "${base_sha}:${catalog}" '
            '| sha256sum | cut -d\' \' -f1)"'
        )
        identity_match = (
            '[[ "${CATALOG_SHA256}" == "${previous_catalog_sha256}" ]]'
        )
        success = 'echo "Marketplace already publishes ${current_version} at ${SOURCE_SHA}."'
        self.assertIn(digest, write_job)
        self.assertIn(identity_match, write_job)
        self.assertIn(
            "Refusing idempotent marketplace rerun: existing catalog bytes do not match the sealed catalog.",
            write_job,
        )
        self.assertLess(write_job.index(source_match), write_job.index(digest))
        self.assertLess(write_job.index(digest), write_job.index(identity_match))
        self.assertLess(write_job.index(identity_match), write_job.index(success))

    def test_marketplace_promotion_is_explicit_and_not_push_triggered(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        trigger = text.split("\nconcurrency:", maxsplit=1)[0]
        self.assertIn("workflow_dispatch:", trigger)
        self.assertIn("source_sha:", trigger)
        self.assertIn("required: true", trigger)
        self.assertIn("type: string", trigger)
        self.assertNotIn("push:", trigger)
        self.assertNotIn("paths:", trigger)

    def test_promotion_requires_current_main_and_exact_reachable_source_sha(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('SOURCE_SHA: ${{ inputs.source_sha }}', text)
        self.assertIn('DISPATCH_REF: ${{ github.ref }}', text)
        self.assertIn('DISPATCH_SHA: ${{ github.sha }}', text)
        self.assertIn('[[ "${DISPATCH_REF}" == "refs/heads/main" ]]', text)
        self.assertIn('[[ "${SOURCE_SHA}" =~ ^[0-9a-f]{40}$ ]]', text)
        self.assertIn('[[ "${DISPATCH_SHA}" == "$(git rev-parse refs/remotes/origin/main)" ]]', text)
        self.assertIn('git cat-file -e "${SOURCE_SHA}^{commit}"', text)
        self.assertIn('git merge-base --is-ancestor \\\n            "${SOURCE_SHA}" refs/remotes/origin/main', text)
        self.assertIn('WORKFLOW_SHA: ${{ github.sha }}', text)
        self.assertNotIn("needs.validate.outputs.source-sha", text)
        self.assertNotIn("needs.validate.outputs.workflow-sha", text)
        self.assertNotIn("steps.source.outputs.sha", text)
        self.assertNotIn("steps.source.outputs.workflow_sha", text)
        self.assertIn(
            'The selected workflow SHA is no longer current origin/main.', text
        )

    def test_catalog_publisher_revalidates_exact_one_plugin_roster(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        write_job = text.split("\n  publish:\n", maxsplit=1)[1]
        self.assertIn("(.plugins | length) == 1", write_job)
        self.assertIn(
            '[.plugins[].name] == ["grillmester"]',
            write_job,
        )
        self.assertIn('path: "plugin"', write_job)
        self.assertNotIn('path: "plugin-nav"', write_job)
        self.assertIn('[.plugins[].version] == [$version]', write_job)
        self.assertEqual(1, write_job.count("sha: $source_sha"))

    def test_validation_regenerates_and_seals_catalog_from_exact_source_before_write(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('git worktree add --detach "${source_root}" "${SOURCE_SHA}"', text)
        self.assertIn(
            'python3 "${source_root}/scripts/generate_marketplace.py" \\\n            --mode release --sha "${SOURCE_SHA}"',
            text,
        )
        self.assertIn('--mode release --sha "${SOURCE_SHA}" --check', text)
        self.assertIn('python3 "${source_root}/scripts/validate.py"', text)
        self.assertLess(
            text.index("Validate trusted promotion source and generate immutable catalog"),
            text.index("Publish catalog-only commit atomically"),
        )

    def test_manual_validator_is_read_only_and_smokes_exact_local_payload(self) -> None:
        text = PROMOTE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("catalog_sha:", text)
        self.assertIn("refs/remotes/origin/marketplace", text)
        self.assertIn("refs/remotes/origin/main", text)
        self.assertNotIn("--remote-marketplace-ref", text)
        self.assertIn('--source-root "${SOURCE_ROOT}"', text)
        self.assertNotIn("--source-plugin", text)
        self.assertIn(
            '[.plugins[].name] == ["grillmester"]', text
        )
        self.assertNotIn('path: "plugin-nav"', text)
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

    def test_floating_marketplace_remote_smoke_is_read_only(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        publish = text.split("\n  publish:\n", maxsplit=1)[1].split(
            "\n  remote-smoke:\n", maxsplit=1
        )[0]
        remote_smoke = text.split("\n  remote-smoke:\n", maxsplit=1)[1]
        for job in (publish, remote_smoke):
            self.assertIn('SOURCE_SHA: ${{ inputs.source_sha }}', job)
            self.assertIn('WORKFLOW_SHA: ${{ github.sha }}', job)
            self.assertNotIn("needs.validate.outputs.source-sha", job)
            self.assertNotIn("needs.validate.outputs.workflow-sha", job)
        self.assertIn("- publish", remote_smoke)
        self.assertIn("contents: read", remote_smoke)
        self.assertNotIn("contents: write", remote_smoke)
        self.assertNotIn("GH_TOKEN", remote_smoke)
        self.assertIn('ref: ${{ github.sha }}', remote_smoke)
        self.assertIn("refs/remotes/origin/marketplace", remote_smoke)
        self.assertIn('git worktree add --detach \\\n            "${marketplace_root}" refs/remotes/origin/marketplace', remote_smoke)
        self.assertIn(
            '--remote-marketplace-ref "navikt/grillmester#marketplace"', remote_smoke
        )
        self.assertIn("--allow-floating-marketplace", remote_smoke)

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
        write_job = text.split("\n  release:\n", maxsplit=1)[1].split(
            "\n  remote-smoke:\n", maxsplit=1
        )[0]
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
            'cmp -s "${package_manifest_file}" "${rc_package_manifest_file}"',
            write_job,
        )
        self.assertIn(
            'cmp -s "${regenerated_rc_catalog}" "${rc_catalog_file}"', write_job
        )
        self.assertIn("-- plugin ':(exclude)plugin/plugin.json'", write_job)
        self.assertNotIn("plugin-nav", write_job)
        self.assertIn('git ls-tree -r "${RC_CATALOG_SHA}"', write_job)
        self.assertIn("'.tag_name'", write_job)
        self.assertNotIn("git tag -f", write_job)
        self.assertNotIn("git push --force", write_job)
        self.assertNotIn("git push -f", write_job)
        self.assertNotIn("--force-with-lease", write_job)

    def test_release_validates_one_complete_plugin_and_remote_smokes_tag(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('--source-root "${SOURCE_ROOT}"', text)
        self.assertNotIn("--source-plugin", text)
        self.assertGreaterEqual(
            text.count('[.plugins[].name] == ["grillmester"]'),
            3,
        )
        self.assertNotIn('path: "plugin-nav"', text)
        self.assertIn(
            '{name: "grillmester", path: "plugin", agents: 7, skills: 42}',
            text,
        )
        self.assertIn(
            '(keys | sort) == ["marketplace", "packages", "schemaVersion"]',
            text,
        )
        self.assertIn(
            '"agents", "author", "description", "license", "name",', text
        )
        self.assertEqual(1, text.count('(.author | keys) == ["name"]'))
        self.assertIn("Smoke-test published release tag", text)
        self.assertIn(
            '--remote-marketplace-ref "navikt/grillmester#${TAG}"', text
        )


if __name__ == "__main__":
    unittest.main()
