from __future__ import annotations

import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_generate_copilot_manifest",
    ROOT / "scripts/generate_copilot_manifest.py",
)
assert SPEC and SPEC.loader
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


class CopilotManifestGenerationTest(unittest.TestCase):
    def copy_repository(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name) / "grillmester"
        shutil.copytree(
            ROOT,
            root,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )
        return temporary, root

    def test_committed_manifest_is_current_and_binds_exact_payload(self) -> None:
        expected = GENERATOR.build_manifest(ROOT)
        self.assertEqual([], GENERATOR.compare_manifest(ROOT, expected))
        manifest = json.loads(expected)
        actual = GENERATOR.collect_payload_files(ROOT / "plugin")

        self.assertEqual("copilot-full-v1", manifest["target"])
        self.assertEqual({"agents": 7, "skills": 42}, manifest["counts"])
        self.assertNotIn("manifest.json", manifest["files"])
        self.assertEqual(set(actual), set(manifest["files"]))
        for relative, (content, mode) in actual.items():
            with self.subTest(path=relative):
                self.assertEqual(
                    GENERATOR.hashlib.sha256(content).hexdigest(),
                    manifest["files"][relative]["sha256"],
                )
                self.assertEqual(f"{mode:04o}", manifest["files"][relative]["mode"])

    def test_unmanifested_file_makes_check_stale_until_regenerated(self) -> None:
        temporary, root = self.copy_repository()
        try:
            extra = root / "plugin/extra.md"
            extra.write_text("new payload\n", encoding="utf-8")
            expected = GENERATOR.build_manifest(root)

            self.assertIn("generated Copilot full payload manifest is stale", GENERATOR.compare_manifest(root, expected))
            self.assertTrue(GENERATOR.update_manifest(root, expected))
            self.assertEqual([], GENERATOR.compare_manifest(root, expected))
            self.assertIn("extra.md", json.loads(expected)["files"])
        finally:
            temporary.cleanup()

    def test_symlink_and_special_node_are_rejected(self) -> None:
        temporary, root = self.copy_repository()
        try:
            link = root / "plugin/linked.md"
            try:
                link.symlink_to(root / "README.md")
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable")
            with self.assertRaisesRegex(
                GENERATOR.CopilotManifestError, "contains symlink"
            ):
                GENERATOR.build_manifest(root)
            link.unlink()

            fifo = root / "plugin/special"
            try:
                os.mkfifo(fifo)
            except (AttributeError, OSError):
                self.skipTest("FIFO nodes are unavailable")
            with self.assertRaisesRegex(
                GENERATOR.CopilotManifestError, "non-regular node"
            ):
                GENERATOR.build_manifest(root)
        finally:
            temporary.cleanup()

    def test_unsupported_mode_is_rejected_and_manifest_mode_is_repaired(self) -> None:
        temporary, root = self.copy_repository()
        try:
            payload = root / "plugin/LICENSE"
            payload.chmod(0o600)
            with self.assertRaisesRegex(
                GENERATOR.CopilotManifestError, "unsupported mode 0600"
            ):
                GENERATOR.build_manifest(root)

            payload.chmod(0o644)
            manifest = root / "plugin/manifest.json"
            manifest.chmod(0o600)
            expected = GENERATOR.build_manifest(root)
            self.assertTrue(GENERATOR.update_manifest(root, expected))
            self.assertEqual(0o644, manifest.stat().st_mode & 0o7777)
        finally:
            temporary.cleanup()

    def test_manifest_is_byte_deterministic(self) -> None:
        self.assertEqual(
            GENERATOR.build_manifest(ROOT),
            GENERATOR.build_manifest(ROOT),
        )

    def test_duplicate_plugin_manifest_keys_are_rejected(self) -> None:
        temporary, root = self.copy_repository()
        try:
            (root / "plugin/plugin.json").write_text(
                '{"name":"grillmester","name":"other","version":"1.0.0"}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                GENERATOR.CopilotManifestError, "duplicate key 'name'"
            ):
                GENERATOR.build_manifest(root)
        finally:
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
