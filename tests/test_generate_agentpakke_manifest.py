from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_generate_agentpakke_manifest",
    ROOT / "scripts/generate_agentpakke_manifest.py",
)
assert SPEC and SPEC.loader
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


class AgentpakkeManifestGenerationTest(unittest.TestCase):
    def copy_repository(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name) / "grillmester"
        shutil.copytree(
            ROOT,
            root,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )
        return temporary, root

    def test_committed_manifest_is_current_and_maps_all_payloads(self) -> None:
        GENERATOR.check_manifest(ROOT)
        manifest = GENERATOR.build_manifest(ROOT)

        self.assertEqual("1", manifest["contractVersion"])
        self.assertEqual("grillmester", manifest["name"])
        self.assertEqual(
            ["grillmester", "barista", "designer", "doctor-who"],
            manifest["clients"]["copilot"]["primaryAgents"],
        )
        self.assertEqual(
            manifest["clients"]["copilot"]["primaryAgents"],
            manifest["clients"]["opencode"]["primaryAgents"],
        )
        self.assertEqual(
            ">=1.0.79,<2", manifest["clients"]["copilot"]["compatibility"]
        )
        self.assertEqual(
            ">=1.18.20,<2", manifest["clients"]["opencode"]["compatibility"]
        )
        self.assertEqual(
            {
                "full": {"path": "plugin"},
                "focused": {"path": "targets/copilot-cli-focused-v1"},
            },
            manifest["clients"]["copilot"]["payloads"],
        )
        self.assertEqual(
            {
                "full": {"path": "targets/opencode-v1"},
                "focused": {"path": "targets/opencode-v1-focused"},
            },
            manifest["clients"]["opencode"]["payloads"],
        )
        for client in manifest["clients"].values():
            self.assertEqual("inherit", client["defaultModel"])
            self.assertEqual("full", client["defaultContext"])
        self.assertNotIn("minNavPilotVersion", manifest)
        self.assertNotIn("provenance", manifest)

    def test_standard_support_ranges_are_derived_from_release_contract(self) -> None:
        temporary, root = self.copy_repository()
        try:
            baseline = root / "scripts/release_test_baseline.py"
            text = baseline.read_text(encoding="utf-8")
            text = text.replace(
                '"opencodeMinimum": "1.18.20"',
                '"opencodeMinimum": "1.99.1"',
            )
            text = text.replace(
                '"copilotMinimum": "1.0.79"',
                '"copilotMinimum": "1.42.0"',
            )
            baseline.write_text(text, encoding="utf-8")

            manifest = GENERATOR.build_manifest(root)
            self.assertEqual(">=1.42.0,<2", manifest["clients"]["copilot"]["compatibility"])
            self.assertEqual(">=1.99.1,<2", manifest["clients"]["opencode"]["compatibility"])
        finally:
            temporary.cleanup()

    def test_public_agent_drift_is_rejected(self) -> None:
        temporary, root = self.copy_repository()
        try:
            content_lock_path = root / "policy/content-lock.json"
            content_lock = json.loads(content_lock_path.read_text(encoding="utf-8"))
            content_lock["agents"]["barista"]["user-invocable"] = False
            content_lock_path.write_text(
                json.dumps(content_lock, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                GENERATOR.AgentpakkeManifestError,
                "PUBLIC_AGENTS differs",
            ):
                GENERATOR.build_manifest(root)
        finally:
            temporary.cleanup()

    def test_payload_target_drift_and_symlink_are_rejected(self) -> None:
        temporary, root = self.copy_repository()
        try:
            payload_manifest = root / "targets/opencode-v1/manifest.json"
            data = json.loads(payload_manifest.read_text(encoding="utf-8"))
            data["target"] = "unexpected"
            payload_manifest.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(
                GENERATOR.AgentpakkeManifestError,
                "target must be 'opencode-v1'",
            ):
                GENERATOR.build_manifest(root)

            payload_manifest.unlink()
            try:
                payload_manifest.symlink_to(root / "plugin/manifest.json")
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable")
            with self.assertRaisesRegex(
                GENERATOR.AgentpakkeManifestError,
                "cannot open regular file",
            ):
                GENERATOR.build_manifest(root)
        finally:
            temporary.cleanup()

    def test_duplicate_canonical_json_keys_are_rejected(self) -> None:
        temporary, root = self.copy_repository()
        try:
            content_lock = root / "policy/content-lock.json"
            text = content_lock.read_text(encoding="utf-8")
            content_lock.write_text(
                text.replace(
                    '"schemaVersion": 1,',
                    '"schemaVersion": 1,\n  "schemaVersion": 1,',
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                GENERATOR.AgentpakkeManifestError,
                "duplicate JSON key",
            ):
                GENERATOR.build_manifest(root)
        finally:
            temporary.cleanup()

    def test_update_is_deterministic_and_rejects_symlink_output(self) -> None:
        temporary, root = self.copy_repository()
        try:
            output = root / GENERATOR.OUTPUT
            output.write_text("{}\n", encoding="utf-8")
            self.assertTrue(GENERATOR.update_manifest(root))
            first = output.read_bytes()
            self.assertFalse(GENERATOR.update_manifest(root))
            self.assertEqual(first, output.read_bytes())
            self.assertEqual(0o644, output.stat().st_mode & 0o777)

            output.unlink()
            try:
                output.symlink_to(root / "README.md")
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable")
            with self.assertRaisesRegex(
                GENERATOR.AgentpakkeManifestError,
                "output must be a regular file",
            ):
                GENERATOR.update_manifest(root)
        finally:
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
