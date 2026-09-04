from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_release_contract", ROOT / "scripts/release_contract.py"
)
assert SPEC and SPEC.loader
CONTRACT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CONTRACT
SPEC.loader.exec_module(CONTRACT)


def catalog(version: str, sha: str) -> dict[str, object]:
    return {
        "name": "grillmester",
        "metadata": {"version": version},
        "plugins": [
            {
                "name": name,
                "version": version,
                "source": {
                    "source": "github",
                    "repo": "navikt/grillmester",
                    "path": path,
                    "sha": sha,
                },
            }
            for name, path in CONTRACT.PLUGIN_PATHS.items()
        ],
    }


def write_opencode_distribution_inputs(root: Path, content: str = "reviewed\n") -> None:
    (root / "LICENSE").write_text(content)
    (root / "PROVENANCE.md").write_text(content)
    (root / "THIRD_PARTY_NOTICES.md").write_text(content)
    notices = root / "plugin/THIRD_PARTY_NOTICES.md"
    notices.parent.mkdir(parents=True, exist_ok=True)
    notices.write_text(content)
    policy = root / "policy"
    policy.mkdir(parents=True, exist_ok=True)
    (policy / "content-lock.json").write_text(content)
    (policy / "focused-context-v1.json").write_text(content)
    scripts = root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    for name in (
        "build_opencode_bundle.py",
        "generate_copilot_manifest.py",
        "generate_context_projections.py",
        "grillmester.py",
        "grillmester_local.py",
        "release_test_baseline.py",
        "release_contract.py",
        "smoke_grillmester_tui.py",
        "smoke_grillmester_local.py",
        "smoke_plugin_install.py",
        "smoke_opencode.py",
        "smoke_opencode_runtime.py",
    ):
        (scripts / name).write_text(content)

    focused_opencode = root / "targets/opencode-v1-focused"
    focused_opencode.mkdir(parents=True, exist_ok=True)
    (focused_opencode / "manifest.json").write_text(content)

    canonical_plugin = root / "plugin/plugin.json"
    if canonical_plugin.is_file():
        plugin_bytes = canonical_plugin.read_bytes()
        plugin_digest = hashlib.sha256(plugin_bytes).hexdigest()
        plugin_root = root / "plugin"
        full_files = {
            path.relative_to(plugin_root).as_posix(): {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "mode": f"{path.stat().st_mode & 0o7777:04o}",
            }
            for path in sorted(plugin_root.rglob("*"))
            if path.is_file() and path != plugin_root / "manifest.json"
        }
        full_manifest = {
            "schemaVersion": 1,
            "target": "copilot-full-v1",
            "generator": {
                "path": "scripts/generate_copilot_manifest.py",
                "version": 1,
            },
            "counts": {"agents": 0, "skills": 0},
            "agents": [],
            "skills": [],
            "files": full_files,
        }
        full_manifest_path = plugin_root / "manifest.json"
        full_manifest_path.write_text(
            json.dumps(full_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        full_manifest_digest = hashlib.sha256(
            full_manifest_path.read_bytes()
        ).hexdigest()
        focused_copilot = root / CONTRACT.FOCUSED_COPILOT_DIRECTORY
        focused_copilot.mkdir(parents=True, exist_ok=True)
        (focused_copilot / "plugin.json").write_bytes(plugin_bytes)
        (focused_copilot / "payload.txt").write_text(content)
        (focused_copilot / "manifest.json").write_text(
            json.dumps(
                {
                    "source": {
                        "payloadManifest": "plugin/manifest.json",
                        "payloadManifestSha256": full_manifest_digest,
                    },
                    "files": {"plugin.json": {"sha256": plugin_digest}},
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )


def write_stable_rights_fixture(root: Path) -> dict[str, object]:
    policy = root / "policy"
    policy.mkdir(parents=True, exist_ok=True)
    content_lock = {
        "schemaVersion": 1,
        "sources": {
            "hovmester": {
                "repository": CONTRACT.HOVMESTER_REPOSITORY,
                "revision": CONTRACT.HOVMESTER_REVISION,
            }
        },
        "agents": {
            "designer": {"source": "hovmester"},
            "doctor-who": {"source": "hovmester"},
        },
        "skills": {
            "grillmester-aksel-design": {"source": ["pilot", "hovmester"]},
        },
    }
    (policy / "content-lock.json").write_text(
        json.dumps(content_lock, sort_keys=True) + "\n"
    )
    (root / "PROVENANCE.md").write_text("Reviewed provenance.\n")
    agents = root / "plugin/agents"
    agents.mkdir(parents=True, exist_ok=True)
    (agents / "designer.agent.md").write_text("designer\n")
    (agents / "doctor-who.agent.md").write_text("doctor who\n")
    skill = root / "plugin/skills/grillmester-aksel-design"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text("aksel\n")
    approval: dict[str, object] = {
        "schemaVersion": 1,
        "scope": {
            "hovmester": {
                "repository": CONTRACT.HOVMESTER_REPOSITORY,
                "revision": CONTRACT.HOVMESTER_REVISION,
            },
            "contentLockSha256": CONTRACT.distribution_file_digest(
                policy / "content-lock.json"
            ),
            "provenanceSha256": CONTRACT.distribution_file_digest(
                root / "PROVENANCE.md"
            ),
            "components": CONTRACT._hovmester_component_digests(root),
        },
        "decisions": {
            "organizationalRights": {
                "status": "approved",
                "decisionReference": "NAV legal decision NAV-2026-1234",
                "authority": {"role": "rights holder", "team": "NAV legal"},
                "date": "2026-08-13",
            },
            "doctorWhoBrand": {
                "status": "approved",
                "decisionReference": "NAV brand decision NAV-2026-1235",
                "authority": {"role": "brand counsel", "team": "NAV legal"},
                "date": "2026-08-13",
            },
        },
    }
    (policy / "stable-rights-approval.json").write_text(
        json.dumps(approval, indent=2, sort_keys=True) + "\n"
    )
    return approval


class ReleaseContractTest(unittest.TestCase):
    def test_read_object_rejects_nonstandard_json_and_invalid_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            candidate = Path(temp) / "invalid.json"
            candidate.write_text('{"value": NaN}', encoding="utf-8")
            with self.assertRaisesRegex(
                CONTRACT.ReleaseContractError, "non-standard JSON constant"
            ):
                CONTRACT.read_object(candidate)

            candidate.write_bytes(b'{"value":"\xff"}')
            with self.assertRaisesRegex(CONTRACT.ReleaseContractError, "not UTF-8"):
                CONTRACT.read_object(candidate)

    def test_read_object_rejects_excessive_json_nesting(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            candidate = Path(temp) / "deep.json"
            nested: object = "leaf"
            for _ in range(CONTRACT.MAX_JSON_DEPTH + 2):
                nested = {"child": nested}
            candidate.write_text(json.dumps({"root": nested}), encoding="utf-8")

            with self.assertRaisesRegex(
                CONTRACT.ReleaseContractError, "nesting limit"
            ):
                CONTRACT.read_object(candidate)

    def test_payload_manifest_rejects_a_symlinked_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = root / "payload"
            payload.mkdir()
            (payload / "file.txt").write_text("bytes\n")
            alias = root / "alias"
            alias.symlink_to(payload, target_is_directory=True)

            with self.assertRaisesRegex(
                CONTRACT.ReleaseContractError, "payload is missing"
            ):
                CONTRACT.payload_manifest(alias)

    def test_copilot_full_manifest_rejects_unmanifested_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plugin = root / "plugin"
            plugin.mkdir()
            payload = plugin / "plugin.json"
            payload.write_text('{"name":"grillmester","version":"1.0.0"}\n')
            manifest = {
                "schemaVersion": 1,
                "target": "copilot-full-v1",
                "generator": {
                    "path": "scripts/generate_copilot_manifest.py",
                    "version": 1,
                },
                "counts": {"agents": 0, "skills": 0},
                "agents": [],
                "skills": [],
                "files": {
                    "plugin.json": {
                        "sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
                        "mode": "0644",
                    }
                },
            }
            (plugin / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n"
            )
            CONTRACT._validate_copilot_full_payload_manifest(root, label="test")

            (plugin / "extra.md").write_text("unmanifested\n")
            with self.assertRaisesRegex(
                CONTRACT.ReleaseContractError, "differs from its manifest"
            ):
                CONTRACT._validate_copilot_full_payload_manifest(root, label="test")

    def run_git(self, repo: Path, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()

    def test_rc_tag_is_derived_from_strict_prerelease_version(self) -> None:
        sha = "0123456789abcdef0123456789abcdef01234567"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "marketplace.json"
            path.write_text(json.dumps(catalog("0.2.0-poc.4", sha)))

            result = CONTRACT.inspect_catalog(path)

        self.assertEqual("v0.2.0-poc.4", result.version.tag)
        self.assertEqual((0, 2, 0), result.version.core)
        self.assertEqual(sha, result.source_sha)

    def test_release_version_rejects_build_metadata_and_leading_zeroes(self) -> None:
        for version in (
            "01.2.3",
            "1.2.3+rebuilt",
            "1.2.3-rc.01",
            "1.2.3-" + "a" * CONTRACT.MAX_VERSION_LENGTH,
        ):
            with self.subTest(version=version), self.assertRaises(
                CONTRACT.ReleaseContractError
            ):
                CONTRACT.parse_version(version)

    def test_catalog_source_must_be_exact_expected_shape(self) -> None:
        sha = "0123456789abcdef0123456789abcdef01234567"
        value = catalog("1.2.3-rc.1", sha)
        value["plugins"][0]["source"]["ref"] = "main"  # type: ignore[index]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "marketplace.json"
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(
                CONTRACT.ReleaseContractError, "exact SHA"
            ):
                CONTRACT.inspect_catalog(path)

    def test_tag_target_must_be_an_exact_catalog_only_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            self.run_git(repo, "init", "-q")
            self.run_git(repo, "config", "user.name", "Test")
            self.run_git(repo, "config", "user.email", "test@example.com")
            catalog_path = repo / CONTRACT.CATALOG_PATH
            catalog_path.parent.mkdir(parents=True)
            catalog_path.write_text("{}\n")
            self.run_git(repo, "add", CONTRACT.CATALOG_PATH)
            self.run_git(repo, "commit", "-qm", "catalog")
            sha = self.run_git(repo, "rev-parse", "HEAD")

            CONTRACT.validate_catalog_checkout(repo, sha)

            (repo / "unexpected.txt").write_text("not catalog-only\n")
            self.run_git(repo, "add", "unexpected.txt")
            self.run_git(repo, "commit", "-qm", "drift")
            drift_sha = self.run_git(repo, "rev-parse", "HEAD")
            with self.assertRaisesRegex(
                CONTRACT.ReleaseContractError, "catalog-only commit"
            ):
                CONTRACT.validate_catalog_checkout(repo, drift_sha)

    def test_inspected_catalog_bytes_are_bound_to_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "repo"
            checkout_catalog = repo / CONTRACT.CATALOG_PATH
            checkout_catalog.parent.mkdir(parents=True)
            checkout_catalog.write_text('{"version": "expected"}\n')
            inspected = root / "marketplace.json"
            inspected.write_text('{"version": "different"}\n')

            with self.assertRaisesRegex(
                CONTRACT.ReleaseContractError, "catalog commit"
            ):
                CONTRACT.bind_catalog_bytes(inspected, repo)

    def test_regenerated_catalog_must_be_byte_identical(self) -> None:
        sha = "0123456789abcdef0123456789abcdef01234567"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            (source / "scripts").mkdir(parents=True)
            package_definitions = []
            for name, path in CONTRACT.PLUGIN_PATHS.items():
                (source / path).mkdir()
                (source / path / "plugin.json").write_text(
                    json.dumps(
                        {
                            "name": name,
                            "version": "0.2.0-rc.1",
                            "description": f"Description for {name}",
                            "author": {"name": "Team eSyfo"},
                            "repository": "https://github.com/navikt/grillmester",
                        }
                    )
                )
                package_definitions.append({"name": name, "path": path})
            (source / "package-manifest.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "marketplace": {
                            "name": "grillmester",
                            "description": "Description",
                            "owner": "Team eSyfo",
                        },
                        "packages": package_definitions,
                    }
                )
            )
            generator = ROOT / "scripts/generate_marketplace.py"
            (source / "scripts/generate_marketplace.py").write_bytes(
                generator.read_bytes()
            )
            expected = root / "marketplace.json"
            subprocess.run(
                [
                    sys.executable,
                    str(source / "scripts/generate_marketplace.py"),
                    "--mode",
                    "release",
                    "--sha",
                    sha,
                    "--output",
                    str(expected),
                ],
                cwd=source,
                check=True,
                stdout=subprocess.PIPE,
            )
            (source / "scripts/generate_marketplace.py").write_text(
                "raise SystemExit('selected-source generator must not execute')\n"
            )

            CONTRACT.validate_regenerated_catalog(
                catalog_path=expected,
                source_repo=source,
                source_sha=sha,
            )
            expected.write_text("{}\n")
            with self.assertRaisesRegex(
                CONTRACT.ReleaseContractError, "byte-identical"
            ):
                CONTRACT.validate_regenerated_catalog(
                    catalog_path=expected,
                    source_repo=source,
                    source_sha=sha,
                )

    def test_source_checkout_requires_the_native_opencode_target(self) -> None:
        release = CONTRACT.Catalog(
            version=CONTRACT.parse_version("1.4.0-rc.2"), source_sha="1" * 40
        )
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            for name, path in CONTRACT.PLUGIN_PATHS.items():
                package = source / path
                package.mkdir(parents=True)
                (package / "plugin.json").write_text(
                    json.dumps(
                        {
                            "name": name,
                            "version": release.version.text,
                            "repository": "https://github.com/navikt/grillmester",
                        }
                    )
                )
            with mock.patch.object(
                CONTRACT, "git_output", return_value=release.source_sha
            ), self.assertRaisesRegex(
                CONTRACT.ReleaseContractError, "opencode-v1"
            ):
                CONTRACT.validate_source_checkout(source, release)

            for target_path in CONTRACT.NATIVE_TARGET_PATHS:
                target = source / target_path
                target.mkdir(parents=True)
                (target / "opencode.json").write_text("{}\n")
            write_opencode_distribution_inputs(source)
            with mock.patch.object(
                CONTRACT, "git_output", return_value=release.source_sha
            ):
                CONTRACT.validate_source_checkout(source, release)

    def test_stable_rights_gate_fails_closed_when_record_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp, self.assertRaisesRegex(
            CONTRACT.ReleaseContractError, "stable-rights-approval.json"
        ):
            CONTRACT.validate_stable_rights_approval(Path(temp))

    def test_stable_rights_gate_binds_scope_components_and_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            approval = write_stable_rights_fixture(source)
            CONTRACT.validate_stable_rights_approval(source)

            approval["decisions"]["organizationalRights"][  # type: ignore[index]
                "decisionReference"
            ] = "UNVERIFIED"
            (source / CONTRACT.STABLE_RIGHTS_APPROVAL_PATH).write_text(
                json.dumps(approval) + "\n"
            )
            with self.assertRaisesRegex(
                CONTRACT.ReleaseContractError, "placeholder"
            ):
                CONTRACT.validate_stable_rights_approval(source)

    def test_stable_rights_scope_rejects_an_invalid_component_source_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            write_stable_rights_fixture(source)
            content_lock_path = source / CONTRACT.CONTENT_LOCK_PATH
            content_lock = json.loads(content_lock_path.read_text())
            content_lock["skills"]["grillmester-aksel-design"]["source"] = {
                "hovmester": True
            }
            content_lock_path.write_text(json.dumps(content_lock) + "\n")

            with self.assertRaisesRegex(
                CONTRACT.ReleaseContractError, "source must name one or more sources"
            ):
                CONTRACT._hovmester_component_digests(source)

    def test_release_notes_explain_both_immutable_links(self) -> None:
        notes = CONTRACT.render_notes(
            tag="v0.2.0-poc.4",
            catalog_sha="1" * 40,
            source_sha="2" * 40,
        )
        normalized_notes = " ".join(notes.split())

        self.assertIn("v0.2.0-poc.4` → catalog commit", notes)
        self.assertIn("catalog source →", notes)
        self.assertIn("navikt/grillmester#v0.2.0-poc.4", notes)
        self.assertIn("grillmester@grillmester", notes)
        self.assertIn("Install the terminal launcher", notes)
        self.assertIn("Run with Copilot CLI from PATH", notes)
        self.assertIn("Run with OpenCode from PATH", notes)
        self.assertIn("Grillmester terminal bundle (no client binaries)", notes)
        self.assertIn("`grillmester-terminal-v1`", notes)
        self.assertIn("release-test metadata, not runtime pins", normalized_notes)
        self.assertIn("inner native OpenCode target remains `opencode-v1`", normalized_notes)
        self.assertIn(
            "shasum -a 256 -c grillmester-terminal-v0.2.0-poc.4.tar.gz.sha256", notes
        )
        self.assertIn("tar -xzf grillmester-terminal-v0.2.0-poc.4.tar.gz", notes)
        self.assertIn("`scripts/grillmester.py` is the launcher", notes)
        self.assertNotIn("grillmester.rb", notes)
        self.assertNotIn("Homebrew", notes)
        self.assertIn("brew install opencode", notes)
        self.assertIn("brew install --cask copilot-cli", notes)
        self.assertIn("grillmester doctor --client copilot", notes)
        self.assertIn("grillmester --client copilot --agent grillmester", notes)
        self.assertIn("Install directly in Copilot CLI", notes)
        self.assertIn(
            "uses the OpenCode and GitHub Copilot CLI executables from `PATH`",
            normalized_notes,
        )
        self.assertIn("does not package either client binary", normalized_notes)
        self.assertIn(CONTRACT.SUPPORTED_OPENCODE_RANGE, notes)
        self.assertIn("tested cplt baseline", normalized_notes)
        self.assertIn("or a newer release", normalized_notes)
        self.assertIn(
            "Newer compatible clients are not the exact bytes covered by the release gate",
            normalized_notes,
        )
        self.assertIn(
            "release-test inputs, not client binaries shipped in the bundle",
            normalized_notes,
        )
        self.assertIn("executable release-test baseline", normalized_notes)
        self.assertIn(
            "Users remain in control of the compatible client versions",
            normalized_notes,
        )
        self.assertIn(
            f"/blob/{'2' * 40}/docs/local-models.md"
            "#avansert-manuell-opencode-binding",
            notes,
        )
        self.assertIn(
            f"/blob/{'2' * 40}/docs/opencode.md#kom-i-gang",
            notes,
        )
        self.assertIn("### Verify Copilot", notes)
        self.assertIn("copilot plugin list", notes)
        self.assertIn("### Verify OpenCode", notes)
        self.assertIn(
            "without starting an interactive session or contacting a model",
            normalized_notes,
        )
        self.assertIn("grillmester doctor --client opencode", notes)
        self.assertIn(
            "grillmester --client opencode --agent grillmester --print-command",
            notes,
        )
        self.assertIn("does not create a separate lifecycle", normalized_notes)
        self.assertNotIn("manage_opencode.py", notes)
        self.assertNotIn("profiles/opencode", notes)
        self.assertNotIn("verify_client_artifact.py", notes)
        self.assertNotIn("policy/client-artifacts.json", notes)
        self.assertNotIn("Optional managed hardening", notes)
        self.assertNotIn("grillmester-nav@grillmester", notes)
        self.assertIn("never\nmoved", notes)

    def test_stable_release_notes_use_the_direct_bundle_install(self) -> None:
        notes = CONTRACT.render_notes(
            tag="v0.2.0",
            catalog_sha="1" * 40,
            source_sha="2" * 40,
        )

        self.assertIn("Install the terminal launcher", notes)
        self.assertIn(
            "shasum -a 256 -c grillmester-terminal-v0.2.0.tar.gz.sha256", notes
        )
        self.assertIn("tar -xzf grillmester-terminal-v0.2.0.tar.gz", notes)
        self.assertNotIn("navikt/tap/grillmester", notes)
        self.assertNotIn("Homebrew", notes)

    def test_release_notes_keep_a_range_for_standard_use_and_exact_gate_input(
        self,
    ) -> None:
        self.assertEqual("1.18.20", CONTRACT.SUPPORTED_OPENCODE_VERSION)
        self.assertEqual(">=1.18.20,<2.0.0", CONTRACT.SUPPORTED_OPENCODE_RANGE)
        self.assertEqual("1.0.79", CONTRACT.SUPPORTED_COPILOT_VERSION)
        self.assertEqual(">=1.0.79,<2.0.0", CONTRACT.SUPPORTED_COPILOT_RANGE)
        self.assertEqual("1.18.20", CONTRACT.RELEASE_TEST_OPENCODE_VERSION)
        self.assertEqual("1.0.80", CONTRACT.RELEASE_TEST_COPILOT_VERSION)

if __name__ == "__main__":
    unittest.main()
