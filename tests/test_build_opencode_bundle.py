from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import json
import os
import shutil
import stat
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_build_opencode_bundle",
    ROOT / "scripts/build_opencode_bundle.py",
)
assert SPEC and SPEC.loader
BUILDER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BUILDER
SPEC.loader.exec_module(BUILDER)

SOURCE_SHA = "0123456789abcdef0123456789abcdef01234567"
ARCHIVE_ROOT = "grillmester-terminal-v1"
CONTENT_LOCK = json.loads((ROOT / "policy/content-lock.json").read_text(encoding="utf-8"))
AGENT_IDS = tuple(sorted(CONTENT_LOCK["agents"]))
SKILL_IDS = tuple(sorted(CONTENT_LOCK["skills"]))
FIXTURE_SKILL = SKILL_IDS[0]


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class BuildOpenCodeBundleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_source(self, name: str = "source") -> Path:
        source = self.root / name
        scripts = source / "scripts"
        scripts.mkdir(parents=True)
        launcher = source / "scripts/grillmester.py"
        launcher.write_bytes((ROOT / "scripts/grillmester.py").read_bytes())
        launcher.chmod(0o644)
        for name in (
            "grillmester_local.py",
            "generate_copilot_manifest.py",
            "generate_context_projections.py",
            "release_test_baseline.py",
            "smoke_grillmester_local.py",
        ):
            support = source / "scripts" / name
            support.write_bytes((ROOT / "scripts" / name).read_bytes())
            support.chmod(0o644)

        shutil.copytree(ROOT / "plugin", source / "plugin")

        for source_relative, destination_relative in (
            ("policy/content-lock.json", "policy/content-lock.json"),
            ("policy/focused-context-v1.json", "policy/focused-context-v1.json"),
            ("LICENSE", "LICENSE"),
            ("PROVENANCE.md", "PROVENANCE.md"),
            ("THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md"),
        ):
            destination = source / destination_relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / source_relative).read_bytes())
            destination.chmod(0o644)

        target = source / "targets/opencode-v1"
        target.mkdir(parents=True)
        target_files = {
            "opencode.json": (b'{"$schema":"https://opencode.ai/config.json"}\n', 0o644),
        }
        primary_agents = {"barista", "designer", "doctor-who", "grillmester"}
        for agent_id in AGENT_IDS:
            mode = "primary" if agent_id in primary_agents else "subagent"
            target_files[f"agents/{agent_id}.md"] = (
                f"---\nmode: {mode}\n---\n".encode(),
                0o644,
            )
        for skill_id in SKILL_IDS:
            target_files[f"commands/{skill_id}.md"] = (b"Run the skill.\n", 0o644)
            target_files[f"skills/{skill_id}/SKILL.md"] = (
                f"---\nname: {skill_id}\ndescription: fixture\n---\n# Fixture\n".encode(),
                0o644,
            )
        target_files[f"skills/{FIXTURE_SKILL}/helper.sh"] = (
            b"#!/bin/sh\nexit 0\n",
            0o755,
        )
        manifest_files: dict[str, dict[str, str]] = {}
        for relative, (content, mode) in target_files.items():
            path = target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            path.chmod(mode)
            manifest_files[relative] = {
                "sha256": sha256(content),
                "mode": f"{mode:04o}",
            }
        manifest = {
            "schemaVersion": 1,
            "target": "opencode-v1",
            "counts": {
                "agents": 7,
                "primaryAgents": 4,
                "subagents": 3,
                "skills": 43,
                "commands": 43,
            },
            "skillCapabilities": {
                skill_id: (
                    "overlay"
                    if skill_id in BUILDER.OPENCODE_OVERLAY_SKILL_IDS
                    else "native"
                )
                for skill_id in SKILL_IDS
            },
            "files": manifest_files,
        }
        (target / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (target / "manifest.json").chmod(0o644)

        for focused_name in ("opencode-v1-focused", "copilot-cli-focused-v1"):
            shutil.copytree(
                ROOT / "targets" / focused_name,
                source / "targets" / focused_name,
            )
        focused_manifest_path = source / "targets/opencode-v1-focused/manifest.json"
        focused_manifest = json.loads(focused_manifest_path.read_text(encoding="utf-8"))
        focused_manifest["source"]["targetManifestSha256"] = sha256(
            (target / "manifest.json").read_bytes()
        )
        focused_manifest_path.write_text(
            json.dumps(focused_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        focused_manifest_path.chmod(0o644)
        focused_copilot_manifest_path = (
            source / "targets/copilot-cli-focused-v1/manifest.json"
        )
        focused_copilot_manifest = json.loads(
            focused_copilot_manifest_path.read_text(encoding="utf-8")
        )
        focused_copilot_manifest["source"]["payloadManifestSha256"] = sha256(
            (source / "plugin/manifest.json").read_bytes()
        )
        focused_copilot_manifest_path.write_text(
            json.dumps(focused_copilot_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        focused_copilot_manifest_path.chmod(0o644)
        return source

    def test_build_is_byte_reproducible_and_manifested_exactly(self) -> None:
        source = self.make_source()
        first = self.root / "one/first.tar.gz"
        second = self.root / "two/different-name.tar.gz"

        BUILDER.build_bundle(source, SOURCE_SHA, first)
        BUILDER.build_bundle(source, SOURCE_SHA, second)

        first_bytes = first.read_bytes()
        self.assertEqual(first_bytes, second.read_bytes())
        self.assertEqual(first_bytes[:3], b"\x1f\x8b\x08")
        self.assertEqual(first_bytes[3] & 0x08, 0, "gzip must not contain a filename")
        self.assertEqual(first_bytes[4:8], b"\0\0\0\0")
        self.assertEqual(stat.S_IMODE(first.stat().st_mode), 0o644)

        with tarfile.open(first, "r:gz") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            self.assertEqual(names, sorted(names))
            self.assertEqual(len(names), len(set(names)))
            for member in members:
                self.assertEqual(member.uid, 0)
                self.assertEqual(member.gid, 0)
                self.assertEqual(member.uname, "")
                self.assertEqual(member.gname, "")
                self.assertEqual(member.mtime, 0)
                if member.isdir():
                    self.assertEqual(member.mode, 0o755)
                else:
                    self.assertTrue(member.isfile())

            files = {member.name: member for member in members if member.isfile()}
            expected_files = {
                f"{ARCHIVE_ROOT}/DISTRIBUTION-MANIFEST.json",
                f"{ARCHIVE_ROOT}/LICENSE",
                f"{ARCHIVE_ROOT}/PROVENANCE.md",
                f"{ARCHIVE_ROOT}/THIRD_PARTY_NOTICES.md",
                f"{ARCHIVE_ROOT}/policy/content-lock.json",
                f"{ARCHIVE_ROOT}/policy/focused-context-v1.json",
                f"{ARCHIVE_ROOT}/scripts/grillmester.py",
                f"{ARCHIVE_ROOT}/scripts/grillmester_local.py",
                f"{ARCHIVE_ROOT}/targets/opencode-v1/manifest.json",
            }
            target_manifest = json.loads(
                (source / "targets/opencode-v1/manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            expected_files.update(
                f"{ARCHIVE_ROOT}/targets/opencode-v1/{relative}"
                for relative in target_manifest["files"]
            )
            expected_files.update(
                f"{ARCHIVE_ROOT}/{path.relative_to(source).as_posix()}"
                for path in (source / "plugin").rglob("*")
                if path.is_file()
            )
            for focused_name in ("opencode-v1-focused", "copilot-cli-focused-v1"):
                expected_files.update(
                    f"{ARCHIVE_ROOT}/{path.relative_to(source).as_posix()}"
                    for path in (source / "targets" / focused_name).rglob("*")
                    if path.is_file()
                )
            self.assertEqual(set(files), expected_files)

            manifest_member = files[f"{ARCHIVE_ROOT}/DISTRIBUTION-MANIFEST.json"]
            manifest_stream = archive.extractfile(manifest_member)
            assert manifest_stream is not None
            distribution = json.load(manifest_stream)
            target_manifest_member = files[
                f"{ARCHIVE_ROOT}/targets/opencode-v1/manifest.json"
            ]
            target_manifest_stream = archive.extractfile(target_manifest_member)
            assert target_manifest_stream is not None
            target_manifest_bytes = target_manifest_stream.read()

            self.assertEqual(distribution["schemaVersion"], 1)
            self.assertEqual(distribution["sourceSha"], SOURCE_SHA)
            self.assertEqual(
                distribution["distribution"], "grillmester-terminal-v1"
            )
            self.assertEqual(
                distribution["releaseTest"],
                {
                    "opencodeVersion": "1.18.20",
                    "copilotVersion": "1.0.80",
                    "cpltRelease": "2026.08.17-062831-1008a92",
                },
            )
            self.assertEqual(
                distribution["targetManifestSha256"],
                sha256(target_manifest_bytes),
            )
            self.assertEqual(
                distribution["copilotFullManifestSha256"],
                sha256((source / "plugin/manifest.json").read_bytes()),
            )
            self.assertEqual(
                distribution["focusedContextPolicySha256"],
                sha256((source / "policy/focused-context-v1.json").read_bytes()),
            )
            for field, relative in (
                ("focusedOpenCodeManifestSha256", "opencode-v1-focused"),
                ("focusedCopilotManifestSha256", "copilot-cli-focused-v1"),
            ):
                self.assertEqual(
                    distribution[field],
                    sha256((source / "targets" / relative / "manifest.json").read_bytes()),
                )

            expected_manifest_paths = {
                name.removeprefix(f"{ARCHIVE_ROOT}/")
                for name in expected_files
                if not name.endswith("/DISTRIBUTION-MANIFEST.json")
            }
            self.assertEqual(set(distribution["files"]), expected_manifest_paths)
            for relative, metadata in distribution["files"].items():
                member = files[f"{ARCHIVE_ROOT}/{relative}"]
                stream = archive.extractfile(member)
                assert stream is not None
                self.assertEqual(metadata["sha256"], sha256(stream.read()))
                self.assertEqual(metadata["mode"], f"{member.mode:04o}")

            self.assertEqual(
                files[f"{ARCHIVE_ROOT}/scripts/grillmester.py"].mode, 0o755
            )
            self.assertEqual(
                files[
                    f"{ARCHIVE_ROOT}/targets/opencode-v1/skills/"
                    f"{FIXTURE_SKILL}/helper.sh"
                ].mode,
                0o755,
            )

        # Decompression also succeeds without consulting a filename or external state.
        self.assertTrue(gzip.decompress(first_bytes).endswith(b"\0" * 1024))

    def test_rejects_invalid_source_sha_without_creating_output(self) -> None:
        source = self.make_source()
        for index, invalid in enumerate(
            ("abc", "A" * 40, "g" * 40, "0" * 39, "0" * 41)
        ):
            output = self.root / f"invalid-{index}.tar.gz"
            with self.subTest(source_sha=invalid), self.assertRaisesRegex(
                BUILDER.BundleBuildError, "40 lowercase hex"
            ):
                BUILDER.build_bundle(source, invalid, output)
            self.assertFalse(output.exists())

    def test_rejects_target_tampering_extra_files_and_symlinks(self) -> None:
        tampered = self.make_source("tampered")
        (tampered / "targets/opencode-v1/opencode.json").write_text("tampered\n")
        with self.assertRaisesRegex(BUILDER.BundleBuildError, "checksum mismatch"):
            BUILDER.build_bundle(tampered, SOURCE_SHA, self.root / "tampered.tar.gz")

        extra = self.make_source("extra")
        (extra / "targets/opencode-v1/unmanifested.txt").write_text("extra\n")
        with self.assertRaisesRegex(BUILDER.BundleBuildError, "unmanifested"):
            BUILDER.build_bundle(extra, SOURCE_SHA, self.root / "extra.tar.gz")

        if hasattr(os, "symlink"):
            linked = self.make_source("linked")
            os.symlink(
                linked / "targets/opencode-v1/opencode.json",
                linked / "targets/opencode-v1/linked.json",
            )
            with self.assertRaisesRegex(BUILDER.BundleBuildError, "symlink"):
                BUILDER.build_bundle(linked, SOURCE_SHA, self.root / "linked.tar.gz")

    def test_rejects_plugin_roster_drift_and_symlinks(self) -> None:
        missing_agent = self.make_source("missing-plugin-agent")
        (missing_agent / f"plugin/agents/{AGENT_IDS[0]}.agent.md").unlink()
        with self.assertRaisesRegex(BUILDER.BundleBuildError, "plugin agent roster"):
            BUILDER.build_bundle(
                missing_agent,
                SOURCE_SHA,
                self.root / "missing-plugin-agent.tar.gz",
            )

        if hasattr(os, "symlink"):
            linked = self.make_source("linked-plugin")
            os.symlink(
                linked / "plugin/plugin.json",
                linked / "plugin/linked.json",
            )
            with self.assertRaisesRegex(BUILDER.BundleBuildError, "symlinked Copilot plugin"):
                BUILDER.build_bundle(
                    linked,
                    SOURCE_SHA,
                    self.root / "linked-plugin.tar.gz",
                )

    def test_rejects_copilot_full_payload_manifest_drift_and_extras(self) -> None:
        tampered = self.make_source("tampered-copilot-full")
        license_path = tampered / "plugin/LICENSE"
        license_path.write_text(
            license_path.read_text(encoding="utf-8") + "tampered\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            BUILDER.BundleBuildError,
            "Copilot full payload differs from its manifest: LICENSE",
        ):
            BUILDER.build_bundle(
                tampered,
                SOURCE_SHA,
                self.root / "tampered-copilot-full.tar.gz",
            )

        unmanifested = self.make_source("unmanifested-copilot-full")
        (unmanifested / "plugin/unmanifested.md").write_text(
            "unexpected\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(
            BUILDER.BundleBuildError,
            "Copilot full payload tree differs from its manifest.*unmanifested",
        ):
            BUILDER.build_bundle(
                unmanifested,
                SOURCE_SHA,
                self.root / "unmanifested-copilot-full.tar.gz",
            )

    def test_rejects_launcher_opencode_minimum_drift(self) -> None:
        source = self.make_source("launcher-pin-drift")
        launcher = source / "scripts/grillmester.py"
        launcher.write_text(
            launcher.read_text(encoding="utf-8").replace(
                'MINIMUM_OPENCODE_VERSION_TEXT = "1.18.20"',
                'MINIMUM_OPENCODE_VERSION_TEXT = "1.18.21"',
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            BUILDER.BundleBuildError,
            "launcher must pin MINIMUM_OPENCODE_VERSION_TEXT",
        ):
            BUILDER.build_bundle(
                source,
                SOURCE_SHA,
                self.root / "launcher-pin-drift.tar.gz",
            )

    def test_release_test_opencode_bump_does_not_raise_runtime_minimum(self) -> None:
        source = self.make_source("independent-opencode-baselines")
        original_contract = BUILDER._release_test_contract(source)
        changed_contract = json.loads(json.dumps(original_contract))
        changed_contract["releaseTest"]["opencodeVersion"] = "1.99.0"

        with mock.patch.object(
            BUILDER, "_release_test_contract", return_value=changed_contract
        ):
            files = BUILDER.collect_bundle_files(source, SOURCE_SHA)

        manifest = json.loads(
            next(
                entry.content
                for entry in files
                if entry.path == BUILDER.OUTER_MANIFEST
            )
        )
        self.assertEqual("1.99.0", manifest["releaseTest"]["opencodeVersion"])
        launcher = next(
            entry.content.decode("utf-8")
            for entry in files
            if entry.path == BUILDER.LAUNCHER_PATH
        )
        self.assertIn('MINIMUM_OPENCODE_VERSION_TEXT = "1.18.20"', launcher)

    def test_rejects_launcher_copilot_minimum_drift(self) -> None:
        source = self.make_source("launcher-copilot-pin-drift")
        launcher = source / "scripts/grillmester.py"
        launcher.write_text(
            launcher.read_text(encoding="utf-8").replace(
                "MINIMUM_COPILOT_VERSION = (1, 0, 79)",
                "MINIMUM_COPILOT_VERSION = (1, 0, 80)",
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            BUILDER.BundleBuildError,
            "launcher must pin MINIMUM_COPILOT_VERSION",
        ):
            BUILDER.build_bundle(
                source,
                SOURCE_SHA,
                self.root / "launcher-copilot-pin-drift.tar.gz",
            )

    def test_rejects_re_manifested_agent_skill_and_command_roster_drift(self) -> None:
        cases = (
            ("agent", f"agents/{AGENT_IDS[0]}.md", "agents/replacement-agent.md"),
            (
                "skill",
                f"skills/{SKILL_IDS[0]}/SKILL.md",
                "skills/replacement-skill/SKILL.md",
            ),
            (
                "command",
                f"commands/{SKILL_IDS[0]}.md",
                "commands/replacement-skill.md",
            ),
        )
        for label, old_relative, new_relative in cases:
            with self.subTest(component=label):
                source = self.make_source(f"renamed-{label}")
                target = source / "targets/opencode-v1"
                old_path = target / old_relative
                new_path = target / new_relative
                new_path.parent.mkdir(parents=True, exist_ok=True)
                old_path.rename(new_path)
                manifest_path = target / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["files"][new_relative] = manifest["files"].pop(old_relative)
                if label == "skill":
                    manifest["skillCapabilities"]["replacement-skill"] = (
                        manifest["skillCapabilities"].pop(SKILL_IDS[0])
                    )
                manifest_path.write_text(
                    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )

                with self.assertRaisesRegex(
                    BUILDER.BundleBuildError,
                    f"target {label} roster differs",
                ):
                    BUILDER.build_bundle(
                        source,
                        SOURCE_SHA,
                        self.root / f"renamed-{label}.tar.gz",
                    )

    def test_rejects_re_manifested_skill_capability_drift(self) -> None:
        source = self.make_source("capability-drift")
        manifest_path = source / "targets/opencode-v1/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        skill_id = SKILL_IDS[0]
        current = manifest["skillCapabilities"][skill_id]
        manifest["skillCapabilities"][skill_id] = (
            "overlay" if current == "native" else "native"
        )
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            BUILDER.BundleBuildError, "reviewed classification"
        ):
            BUILDER.build_bundle(
                source,
                SOURCE_SHA,
                self.root / "capability-drift.tar.gz",
            )

    def test_rejects_oversized_sparse_input_before_reading_it(self) -> None:
        source = self.make_source("oversized")
        notices = source / "THIRD_PARTY_NOTICES.md"
        with notices.open("r+b") as output:
            output.truncate(BUILDER.MAX_FILE_BYTES + 1)

        with self.assertRaisesRegex(BUILDER.BundleBuildError, "safety limit"):
            BUILDER.build_bundle(source, SOURCE_SHA, self.root / "oversized.tar.gz")

        self.assertFalse((self.root / "oversized.tar.gz").exists())

    def test_resource_limits_are_decimal_and_reads_remain_bounded_after_fstat(
        self,
    ) -> None:
        self.assertEqual(BUILDER.MAX_FILE_BYTES, 5_000_000)
        self.assertEqual(BUILDER.MAX_DISTRIBUTION_BYTES, 50_000_000)
        self.assertEqual(BUILDER.MAX_ARCHIVE_MEMBERS, 10_000)

        growing = self.root / "grew-after-fstat.bin"
        growing.write_bytes(b"123456789")
        initially_small = mock.Mock(st_mode=stat.S_IFREG | 0o644, st_size=1)
        with mock.patch.object(BUILDER.os, "fstat", return_value=initially_small):
            with self.assertRaisesRegex(BUILDER.BundleBuildError, "safety limit"):
                BUILDER._read_regular(growing, label="growing input", max_bytes=8)

    def test_read_regular_rejects_same_inode_mutation_during_read(self) -> None:
        source = self.root / "mutated-during-read.bin"
        source.write_bytes(b"unchanged length\n")
        before = source.stat()
        after = os.stat_result(
            (
                before.st_mode,
                before.st_ino,
                before.st_dev,
                before.st_nlink,
                before.st_uid,
                before.st_gid,
                before.st_size,
                before.st_atime,
                before.st_mtime,
                before.st_ctime + 1,
            )
        )
        self.assertEqual(
            (before.st_dev, before.st_ino), (after.st_dev, after.st_ino)
        )
        self.assertEqual(before.st_size, after.st_size)

        with mock.patch.object(BUILDER.os, "fstat", side_effect=(before, after)):
            with self.assertRaisesRegex(
                BUILDER.BundleBuildError, "changed while being read"
            ):
                BUILDER._read_regular(source, label="mutable input")

    def test_read_regular_rejects_torn_short_read_with_stable_metadata(self) -> None:
        source = self.root / "torn-read.bin"
        source.write_bytes(b"short")
        actual = source.stat()
        claimed_size = actual.st_size + 1
        stable = os.stat_result(
            (
                actual.st_mode,
                actual.st_ino,
                actual.st_dev,
                actual.st_nlink,
                actual.st_uid,
                actual.st_gid,
                claimed_size,
                actual.st_atime,
                actual.st_mtime,
                actual.st_ctime,
            )
        )

        with mock.patch.object(BUILDER.os, "fstat", return_value=stable) as fstat:
            with self.assertRaisesRegex(
                BUILDER.BundleBuildError, "changed while being read"
            ):
                BUILDER._read_regular(source, label="torn input")

        self.assertEqual(fstat.call_count, 2)

    def test_archive_member_limit_is_enforced_before_compression(self) -> None:
        files = [
            BUILDER.BundleFile(BUILDER.PurePosixPath("one"), b"", 0o644),
            BUILDER.BundleFile(BUILDER.PurePosixPath("two"), b"", 0o644),
        ]
        output = io.BytesIO()
        with mock.patch.object(BUILDER, "MAX_ARCHIVE_MEMBERS", 2):
            with self.assertRaisesRegex(BUILDER.BundleBuildError, "member safety limit"):
                BUILDER._write_archive(output, files)
        self.assertEqual(output.getvalue(), b"")

        source = self.make_source("manifest-member-limit")
        target_manifest = json.loads(
            (source / "targets/opencode-v1/manifest.json").read_text(
                encoding="utf-8"
            )
        )
        minimum_target_members = len(target_manifest["files"]) + 2
        with mock.patch.object(
            BUILDER, "MAX_ARCHIVE_MEMBERS", minimum_target_members - 1
        ):
            with self.assertRaisesRegex(
                BUILDER.BundleBuildError, "target manifest.*member safety limit"
            ):
                BUILDER.collect_bundle_files(source, SOURCE_SHA)

    def test_distribution_limit_includes_the_outer_manifest(self) -> None:
        source = self.make_source("aggregate-limit")
        files = BUILDER.collect_bundle_files(source, SOURCE_SHA)
        total_size = sum(len(entry.content) for entry in files)
        payload_size = sum(
            len(entry.content)
            for entry in files
            if entry.path != BUILDER.OUTER_MANIFEST
        )
        self.assertLess(payload_size, total_size - 1)

        with mock.patch.object(BUILDER, "MAX_DISTRIBUTION_BYTES", total_size - 1):
            with self.assertRaisesRegex(
                BUILDER.BundleBuildError, "plus distribution manifest"
            ):
                BUILDER.collect_bundle_files(source, SOURCE_SHA)

    def test_distribution_manifest_cannot_exceed_the_json_limit(self) -> None:
        source = self.make_source("distribution-manifest-limit")
        files = BUILDER.collect_bundle_files(source, SOURCE_SHA)
        manifest_size = len(
            next(
                entry.content
                for entry in files
                if entry.path == BUILDER.OUTER_MANIFEST
            )
        )
        support_files = BUILDER._distribution_support_files(source)
        input_json_sizes = [
            (source / "targets/opencode-v1/manifest.json").stat().st_size,
            (source / "targets/opencode-v1-focused/manifest.json").stat().st_size,
            (source / "targets/copilot-cli-focused-v1/manifest.json").stat().st_size,
            (source / "plugin/manifest.json").stat().st_size,
            (source / "policy/content-lock.json").stat().st_size,
            (source / "policy/focused-context-v1.json").stat().st_size,
        ]
        self.assertGreater(manifest_size, max(input_json_sizes))

        with mock.patch.object(
            BUILDER, "MAX_JSON_BYTES", manifest_size - 1
        ), mock.patch.object(
            BUILDER, "_distribution_support_files", return_value=support_files
        ):
            with self.assertRaisesRegex(
                BUILDER.BundleBuildError, "distribution manifest.*JSON safety limit"
            ):
                BUILDER.collect_bundle_files(source, SOURCE_SHA)

    def test_rejects_nonportable_archive_paths(self) -> None:
        source = self.make_source("long-path")
        target = source / "targets/opencode-v1"
        relative = f"{'a' * 150}/{'b' * 100}.md"
        added = target / relative
        added.parent.mkdir()
        added.write_bytes(b"long\n")
        added.chmod(0o644)
        manifest_path = target / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"][relative] = {
            "sha256": sha256(b"long\n"),
            "mode": "0644",
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        focused_manifest_path = source / "targets/opencode-v1-focused/manifest.json"
        focused_manifest = json.loads(focused_manifest_path.read_text(encoding="utf-8"))
        focused_manifest["source"]["targetManifestSha256"] = sha256(
            manifest_path.read_bytes()
        )
        focused_manifest_path.write_text(
            json.dumps(focused_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(BUILDER.BundleBuildError, "portable USTAR"):
            BUILDER.build_bundle(source, SOURCE_SHA, self.root / "long-path.tar.gz")

    def test_output_cannot_alias_or_overwrite_any_source_input(self) -> None:
        source = self.make_source("protected-source")
        launcher = source / "scripts/grillmester.py"
        original = launcher.read_bytes()

        with self.assertRaisesRegex(BUILDER.BundleBuildError, "outside.*source root"):
            BUILDER.build_bundle(source, SOURCE_SHA, launcher)
        self.assertEqual(launcher.read_bytes(), original)

        nested_output = source / "dist/bundle.tar.gz"
        with self.assertRaisesRegex(BUILDER.BundleBuildError, "outside.*source root"):
            BUILDER.build_bundle(source, SOURCE_SHA, nested_output)
        self.assertFalse(nested_output.exists())

        if hasattr(os, "symlink"):
            alias = self.root / "source-alias"
            os.symlink(source, alias)
            with self.assertRaisesRegex(
                BUILDER.BundleBuildError, "outside.*source root"
            ):
                BUILDER.build_bundle(
                    source, SOURCE_SHA, alias / "targets/opencode-v1/opencode.json"
                )
            self.assertEqual(
                (source / "targets/opencode-v1/opencode.json").read_bytes(),
                b'{"$schema":"https://opencode.ai/config.json"}\n',
            )

    def test_source_containment_uses_portable_case_and_unicode_identity(self) -> None:
        self.assertTrue(
            BUILDER._is_within(
                Path("/private/tmp/CaseSource/output.tar.gz"),
                Path("/PRIVATE/TMP/casesource"),
            )
        )
        self.assertTrue(
            BUILDER._is_within(
                Path("/private/tmp/CAFE\u0301/output.tar.gz"),
                Path("/private/tmp/caf\xe9"),
            )
        )

    def test_case_insensitive_source_alias_cannot_be_overwritten(self) -> None:
        source = self.make_source("CaseProtectedSource")
        alias = source.with_name("caseprotectedsource")
        if not alias.exists():
            self.skipTest("filesystem is case-sensitive")
        launcher = source / "scripts/grillmester.py"
        original = launcher.read_bytes()

        with self.assertRaisesRegex(BUILDER.BundleBuildError, "outside.*source root"):
            BUILDER.build_bundle(
                source,
                SOURCE_SHA,
                alias / "scripts/grillmester.py",
            )

        self.assertEqual(launcher.read_bytes(), original)

    def test_legal_and_content_distribution_inputs_are_required_and_validated(
        self,
    ) -> None:
        missing_notices = self.make_source("missing-notices")
        (missing_notices / "THIRD_PARTY_NOTICES.md").unlink()
        with self.assertRaisesRegex(BUILDER.BundleBuildError, "third-party notices"):
            BUILDER.build_bundle(
                missing_notices,
                SOURCE_SHA,
                self.root / "missing-notices.tar.gz",
            )

        incomplete_bom = self.make_source("incomplete-bom")
        content_lock_path = incomplete_bom / "policy/content-lock.json"
        content_lock = json.loads(content_lock_path.read_text(encoding="utf-8"))
        content_lock["agents"].pop(next(iter(content_lock["agents"])))
        content_lock_path.write_text(json.dumps(content_lock), encoding="utf-8")
        with self.assertRaisesRegex(BUILDER.BundleBuildError, "complete 7-agent/43-skill"):
            BUILDER.build_bundle(
                incomplete_bom,
                SOURCE_SHA,
                self.root / "incomplete-bom.tar.gz",
            )

    def test_rejects_unsafe_modes_collisions_and_nonstandard_json(self) -> None:
        unsafe_mode = self.make_source("unsafe-mode")
        target = unsafe_mode / "targets/opencode-v1"
        manifest_path = target / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["opencode.json"]["mode"] = "0666"
        (target / "opencode.json").chmod(0o666)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(BUILDER.BundleBuildError, "unsupported mode"):
            BUILDER.build_bundle(
                unsafe_mode, SOURCE_SHA, self.root / "unsafe-mode.tar.gz"
            )

        collision = self.make_source("collision")
        manifest_path = collision / "targets/opencode-v1/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["agents/Grillmester.md"] = manifest["files"][
            "agents/grillmester.md"
        ]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(
            BUILDER.BundleBuildError, "portable target manifest path collision"
        ):
            BUILDER.build_bundle(collision, SOURCE_SHA, self.root / "collision.tar.gz")

        nonstandard = self.make_source("nonstandard-json")
        manifest_path = nonstandard / "targets/opencode-v1/manifest.json"
        content = manifest_path.read_text(encoding="utf-8")
        manifest_path.write_text(
            content.replace("{", '{"unexpected":NaN,', 1), encoding="utf-8"
        )
        with self.assertRaisesRegex(
            BUILDER.BundleBuildError, "non-standard JSON constant"
        ):
            BUILDER.build_bundle(
                nonstandard, SOURCE_SHA, self.root / "nonstandard.tar.gz"
            )

        boolean_schema = self.make_source("boolean-schema")
        manifest_path = boolean_schema / "targets/opencode-v1/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["schemaVersion"] = True
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(BUILDER.BundleBuildError, "schemaVersion"):
            BUILDER.build_bundle(
                boolean_schema, SOURCE_SHA, self.root / "boolean-schema.tar.gz"
            )

    def test_rejects_excessively_nested_json_without_a_recursion_traceback(self) -> None:
        source = self.make_source("deep-json")
        manifest_path = source / "targets/opencode-v1/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        nested: object = "leaf"
        for _ in range(BUILDER.MAX_JSON_DEPTH + 2):
            nested = {"child": nested}
        manifest["unexpected"] = nested
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with self.assertRaisesRegex(BUILDER.BundleBuildError, "nesting limit"):
            BUILDER.build_bundle(source, SOURCE_SHA, self.root / "deep-json.tar.gz")

    def test_failed_build_preserves_existing_output_and_cleans_temporary_file(self) -> None:
        source = self.make_source("atomic")
        output = self.root / "atomic-output/bundle.tar.gz"
        output.parent.mkdir()
        output.write_bytes(b"old output\n")

        with mock.patch.object(
            BUILDER, "_write_archive", side_effect=OSError("injected write failure")
        ), self.assertRaisesRegex(BUILDER.BundleBuildError, "could not write bundle"):
            BUILDER.build_bundle(source, SOURCE_SHA, output)

        self.assertEqual(output.read_bytes(), b"old output\n")
        self.assertEqual(list(output.parent.glob(".bundle.tar.gz.*.tmp")), [])

    def test_cli_needs_no_git_network_or_ambient_repository(self) -> None:
        source = self.make_source()
        output = self.root / "cli.tar.gz"
        previous = Path.cwd()
        empty_cwd = self.root / "empty-cwd"
        empty_cwd.mkdir()
        try:
            os.chdir(empty_cwd)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = BUILDER.main(
                    [
                        "--source-root",
                        str(source),
                        "--source-sha",
                        SOURCE_SHA,
                        "--output",
                        str(output),
                    ]
                )
        finally:
            os.chdir(previous)

        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue(), f"{output}\n")
        self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
