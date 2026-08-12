from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


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
                "name": "grillmester",
                "version": version,
                "source": {
                    "source": "github",
                    "repo": "navikt/grillmester",
                    "path": "plugin",
                    "sha": sha,
                },
            }
        ],
    }


class ReleaseContractTest(unittest.TestCase):
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

            result = CONTRACT.inspect_catalog(path, channel="rc")

        self.assertEqual("v0.2.0-poc.4", result.version.tag)
        self.assertEqual((0, 2, 0), result.version.core)
        self.assertEqual(sha, result.source_sha)

    def test_rc_rejects_stable_version_and_stable_rejects_prerelease(self) -> None:
        sha = "0123456789abcdef0123456789abcdef01234567"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "marketplace.json"
            path.write_text(json.dumps(catalog("0.2.0", sha)))
            with self.assertRaisesRegex(
                CONTRACT.ReleaseContractError, "prerelease version"
            ):
                CONTRACT.inspect_catalog(path, channel="rc")

            path.write_text(json.dumps(catalog("0.2.0-rc.1", sha)))
            with self.assertRaisesRegex(
                CONTRACT.ReleaseContractError, "stable version"
            ):
                CONTRACT.inspect_catalog(path, channel="stable")

    def test_release_version_rejects_build_metadata_and_leading_zeroes(self) -> None:
        for version in ("01.2.3", "1.2.3+rebuilt", "1.2.3-rc.01"):
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
                CONTRACT.inspect_catalog(path, channel="rc")

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
            (source / "plugin").mkdir()
            (source / "plugin/plugin.json").write_text(
                json.dumps(
                    {
                        "name": "grillmester",
                        "version": "0.2.0-rc.1",
                        "description": "Description",
                        "author": {"name": "Team eSyfo"},
                        "repository": "https://github.com/navikt/grillmester",
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

    def test_stable_payload_may_differ_only_by_manifest_version(self) -> None:
        stable = CONTRACT.Catalog(
            version=CONTRACT.parse_version("1.4.0"),
            source_sha="1" * 40,
        )
        rc = CONTRACT.Catalog(
            version=CONTRACT.parse_version("1.4.0-rc.2"),
            source_sha="2" * 40,
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stable_plugin = root / "stable"
            rc_plugin = root / "rc"
            for plugin, version in (
                (stable_plugin, "1.4.0"),
                (rc_plugin, "1.4.0-rc.2"),
            ):
                plugin.mkdir()
                (plugin / "plugin.json").write_text(
                    json.dumps({"name": "grillmester", "version": version})
                )
                (plugin / "payload.txt").write_text("reviewed bytes\n")

            CONTRACT.validate_stable_promotion(
                stable,
                stable_plugin,
                "v1.4.0-rc.2",
                rc,
                rc_plugin,
            )

    def test_stable_promotion_rejects_payload_drift(self) -> None:
        stable = CONTRACT.Catalog(
            version=CONTRACT.parse_version("1.4.0"), source_sha="1" * 40
        )
        rc = CONTRACT.Catalog(
            version=CONTRACT.parse_version("1.4.0-rc.2"), source_sha="2" * 40
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stable_plugin = root / "stable"
            rc_plugin = root / "rc"
            for plugin, version, payload in (
                (stable_plugin, "1.4.0", "changed\n"),
                (rc_plugin, "1.4.0-rc.2", "reviewed\n"),
            ):
                plugin.mkdir()
                (plugin / "plugin.json").write_text(
                    json.dumps({"name": "grillmester", "version": version})
                )
                (plugin / "payload.txt").write_text(payload)

            with self.assertRaisesRegex(
                CONTRACT.ReleaseContractError, "payload differs"
            ):
                CONTRACT.validate_stable_promotion(
                    stable,
                    stable_plugin,
                    "v1.4.0-rc.2",
                    rc,
                    rc_plugin,
                )

    def test_stable_promotion_rejects_manifest_format_drift(self) -> None:
        stable = CONTRACT.Catalog(
            version=CONTRACT.parse_version("1.4.0"), source_sha="1" * 40
        )
        rc = CONTRACT.Catalog(
            version=CONTRACT.parse_version("1.4.0-rc.2"), source_sha="2" * 40
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stable_plugin = root / "stable"
            rc_plugin = root / "rc"
            stable_plugin.mkdir()
            rc_plugin.mkdir()
            (stable_plugin / "plugin.json").write_text(
                '{"name":"grillmester","version":"1.4.0"}\n'
            )
            (rc_plugin / "plugin.json").write_text(
                '{\n  "name": "grillmester",\n  "version": "1.4.0-rc.2"\n}\n'
            )
            for plugin in (stable_plugin, rc_plugin):
                (plugin / "payload.txt").write_text("reviewed\n")

            with self.assertRaisesRegex(
                CONTRACT.ReleaseContractError, "byte-for-byte"
            ):
                CONTRACT.validate_stable_promotion(
                    stable,
                    stable_plugin,
                    "v1.4.0-rc.2",
                    rc,
                    rc_plugin,
                )

    def test_release_notes_explain_both_immutable_links(self) -> None:
        notes = CONTRACT.render_notes(
            channel="rc",
            tag="v0.2.0-poc.4",
            catalog_sha="1" * 40,
            source_sha="2" * 40,
            rc_tag=None,
        )

        self.assertIn("v0.2.0-poc.4` → catalog commit", notes)
        self.assertIn("catalog `source.sha`", notes)
        self.assertIn("navikt/grillmester#v0.2.0-poc.4", notes)
        self.assertIn("never\nmoved", notes)

    def test_stable_release_notes_require_matching_rc_parent(self) -> None:
        with self.assertRaisesRegex(
            CONTRACT.ReleaseContractError, "same base version"
        ):
            CONTRACT.render_notes(
                channel="stable",
                tag="v1.2.3",
                catalog_sha="1" * 40,
                source_sha="2" * 40,
                rc_tag="v1.2.2-rc.1",
            )


if __name__ == "__main__":
    unittest.main()
