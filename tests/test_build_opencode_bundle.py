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
ARCHIVE_ROOT = "grillmester-opencode-v1"
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
        manager = source / "scripts/manage_opencode.py"
        manager.parent.mkdir(parents=True)
        manager.write_bytes(
            b"#!/usr/bin/env python3\n"
            b"SUPPORTED_OPENCODE_VERSION = \"1.18.20\"\n"
            b"SUPPORTED_CPLT_RELEASE = \"2026.08.17-062831-1008a92\"\n"
            b"PERMISSION_COMPOSER_SHA256 = "
            + repr(sha256(b"# permission composer fixture\n")).encode()
            + b"\n"
            b"PINNED_CPLT_BINARY_SHA256 = "
            + repr(
                {
                    ("darwin", "arm64"): "423af2ce6166b0ddc1939d2e4d1340837daa23a29ccc58024ec0a849051becb2",
                    ("darwin", "x86_64"): "36592c1b2bcfd7ab2d9083842b0aa7f51737cdf12ec1752d351bd9467dab5c02",
                    ("linux", "aarch64"): "56715bc8c63d4dd7323d17a48d3c8d64fdfa3450848651a9ac360f6124d12789",
                    ("linux", "x86_64"): "115fff00248f0c170388e11f2a05cc9914f5ba589f2ca87817ed96de2c6eedb5",
                }
            ).encode()
            + b"\n"
            b"PINNED_OPENCODE_BINARY_SHA256 = "
            + repr(
                {
                    ("darwin", "arm64", "default"): "9598c27bda0e2d88ce4db5f853e25504c20ac6152e10205785a1cf8f45559952",
                    ("darwin", "x86_64", "default"): "96e4a9ecd931a059515fb2126cf59a4a3b56d9a66f9d4dbdf1361d1b4cd5ef60",
                    ("linux", "aarch64", "glibc"): "cc9923aa75f8817261326e81fc56f9cb8203d282c0fab9bff7845cae9f6fe740",
                    ("linux", "aarch64", "musl"): "556ca2125cba1c1508052d055ee87ada1f28dde8a501986edbdbdf476083e4a6",
                    ("linux", "x86_64", "glibc"): "5dce99ea079d925736e332b20f5bf869fe9a1fa67dc0a09027156b0ed8e41b16",
                    ("linux", "x86_64", "musl"): "ca872f52047dd9e56b0a7a14da5cda064c3249a4a1116e71b31cab11864a3967",
                }
            ).encode()
            + b"\n"
            b"print('manager')\n"
        )
        manager.chmod(0o644)
        composer = source / "scripts/compose_opencode_permissions.py"
        composer.write_text("# permission composer fixture\n", encoding="utf-8")
        composer.chmod(0o644)
        verifier = source / "scripts/verify_client_artifact.py"
        verifier.write_bytes(
            (ROOT / "scripts/verify_client_artifact.py").read_bytes()
        )
        verifier.chmod(0o644)
        launcher = source / "scripts/grillmester.py"
        launcher.write_bytes((ROOT / "scripts/grillmester.py").read_bytes())
        launcher.chmod(0o644)

        shutil.copytree(ROOT / "plugin", source / "plugin")

        for source_relative, destination_relative in (
            ("policy/client-artifacts.json", "policy/client-artifacts.json"),
            ("policy/content-lock.json", "policy/content-lock.json"),
            ("LICENSE", "LICENSE"),
            ("PROVENANCE.md", "PROVENANCE.md"),
            ("THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md"),
        ):
            destination = source / destination_relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / source_relative).read_bytes())
            destination.chmod(0o644)

        profiles = source / "profiles/opencode"
        profiles.mkdir(parents=True)
        base_environment = {
            "OPENCODE_CONFIG_CONTENT": '{"autoupdate":false,"share":"disabled"}',
            "OPENCODE_DISABLE_AUTOUPDATE": "true",
            "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "true",
            "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT": "true",
            "OPENCODE_DISABLE_DEFAULT_PLUGINS": "true",
            "OPENCODE_DISABLE_EXTERNAL_SKILLS": "true",
            "OPENCODE_DISABLE_SHARE": "true",
            "OPENCODE_DISABLE_MODELS_FETCH": "true",
            "OPENCODE_DISABLE_LSP_DOWNLOAD": "true",
            "OPENCODE_DISABLE_PROJECT_CONFIG": "true",
            "OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER": "true",
            "OPENCODE_EXPERIMENTAL": "false",
            "OPENCODE_EXPERIMENTAL_CODE_MODE": "false",
            "OPENCODE_PURE": "true",
            "OPENCODE_DB": ":memory:",
        }
        profile_shapes = {
            "local": ("strict", "required", "forbidden"),
            "cloud-open-weight": ("strict", "forbidden", "required"),
            "hybrid": ("strict", "required", "required"),
            "local-only": ("local-only", "required", "forbidden"),
        }
        for profile_id, (
            cplt_policy,
            local_ports,
            provider_domains,
        ) in profile_shapes.items():
            profile = {
                "schemaVersion": 1,
                "id": profile_id,
                "description": f"Test profile {profile_id}",
                "cpltPolicy": cplt_policy,
                "cpltRelease": "2026.08.17-062831-1008a92",
                "localPorts": local_ports,
                "providerDomains": provider_domains,
                "environment": dict(base_environment),
            }
            if profile_id == "local-only":
                profile["environment"].update(
                    {
                        "OPENCODE_DISABLE_MODELS_FETCH": "true",
                        "OPENCODE_DISABLE_LSP_DOWNLOAD": "true",
                        "OPENCODE_AUTO_SHARE": "false",
                        "OPENCODE_ENABLE_EXA": "false",
                    }
                )
                profile["allowedDomain"] = "grillmester-local-only.invalid"
                profile["blockedDomains"] = sorted(
                    BUILDER.LOCAL_ONLY_BLOCKED_DOMAINS
                )
            (profiles / f"{profile_id}.json").write_text(
                json.dumps(profile, sort_keys=True) + "\n", encoding="utf-8"
            )
        for profile in profiles.iterdir():
            profile.chmod(0o644)

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
                "skills": 42,
                "commands": 42,
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
                f"{ARCHIVE_ROOT}/policy/client-artifacts.json",
                f"{ARCHIVE_ROOT}/policy/content-lock.json",
                f"{ARCHIVE_ROOT}/scripts/manage_opencode.py",
                f"{ARCHIVE_ROOT}/scripts/grillmester.py",
                f"{ARCHIVE_ROOT}/scripts/compose_opencode_permissions.py",
                f"{ARCHIVE_ROOT}/scripts/verify_client_artifact.py",
                f"{ARCHIVE_ROOT}/profiles/opencode/cloud-open-weight.json",
                f"{ARCHIVE_ROOT}/profiles/opencode/hybrid.json",
                f"{ARCHIVE_ROOT}/profiles/opencode/local.json",
                f"{ARCHIVE_ROOT}/profiles/opencode/local-only.json",
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
            self.assertEqual(distribution["target"], "opencode-v1")
            self.assertEqual(distribution["opencodeVersion"], "1.18.20")
            self.assertEqual(
                distribution["cpltRelease"], "2026.08.17-062831-1008a92"
            )
            self.assertEqual(
                distribution["targetManifestSha256"],
                sha256(target_manifest_bytes),
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
                files[f"{ARCHIVE_ROOT}/scripts/manage_opencode.py"].mode, 0o755
            )
            self.assertEqual(
                files[f"{ARCHIVE_ROOT}/scripts/grillmester.py"].mode, 0o755
            )
            self.assertEqual(
                files[f"{ARCHIVE_ROOT}/scripts/verify_client_artifact.py"].mode,
                0o755,
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

    def test_rejects_launcher_client_pin_drift(self) -> None:
        source = self.make_source("launcher-pin-drift")
        launcher = source / "scripts/grillmester.py"
        launcher.write_text(
            launcher.read_text(encoding="utf-8").replace("1.18.20", "1.18.21"),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            BUILDER.BundleBuildError, "launcher must pin SUPPORTED_OPENCODE_VERSION"
        ):
            BUILDER.build_bundle(
                source,
                SOURCE_SHA,
                self.root / "launcher-pin-drift.tar.gz",
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
        manager = source / "scripts/manage_opencode.py"
        with manager.open("r+b") as output:
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

    def test_distribution_manifest_cannot_exceed_the_manager_json_limit(self) -> None:
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
            *(path.stat().st_size for path in (source / "profiles/opencode").iterdir()),
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

        with self.assertRaisesRegex(BUILDER.BundleBuildError, "portable USTAR"):
            BUILDER.build_bundle(source, SOURCE_SHA, self.root / "long-path.tar.gz")

        unsafe_profile = self.make_source("unsafe-profile")
        (unsafe_profile / "profiles/opencode/bad\\name.json").write_text("{}\n")
        with self.assertRaisesRegex(BUILDER.BundleBuildError, "safe portable path"):
            BUILDER.build_bundle(
                unsafe_profile, SOURCE_SHA, self.root / "unsafe-profile.tar.gz"
            )

    def test_output_cannot_alias_or_overwrite_any_source_input(self) -> None:
        source = self.make_source("protected-source")
        manager = source / "scripts/manage_opencode.py"
        original = manager.read_bytes()

        with self.assertRaisesRegex(BUILDER.BundleBuildError, "outside.*source root"):
            BUILDER.build_bundle(source, SOURCE_SHA, manager)
        self.assertEqual(manager.read_bytes(), original)

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
        manager = source / "scripts/manage_opencode.py"
        original = manager.read_bytes()

        with self.assertRaisesRegex(BUILDER.BundleBuildError, "outside.*source root"):
            BUILDER.build_bundle(
                source,
                SOURCE_SHA,
                alias / "scripts/manage_opencode.py",
            )

        self.assertEqual(manager.read_bytes(), original)

    def test_required_profiles_and_client_contract_are_exact(self) -> None:
        missing = self.make_source("missing-profile")
        (missing / "profiles/opencode/hybrid.json").unlink()
        with self.assertRaisesRegex(BUILDER.BundleBuildError, "profiles must be exactly"):
            BUILDER.build_bundle(missing, SOURCE_SHA, self.root / "missing.tar.gz")

        wrong_id = self.make_source("wrong-profile-id")
        profile_path = wrong_id / "profiles/opencode/local.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile["id"] = "hybrid"
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        with self.assertRaisesRegex(BUILDER.BundleBuildError, "invalid schema or id"):
            BUILDER.build_bundle(wrong_id, SOURCE_SHA, self.root / "wrong-id.tar.gz")

        wrong_pin = self.make_source("wrong-profile-pin")
        profile_path = wrong_pin / "profiles/opencode/hybrid.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile["cpltRelease"] += "-unreviewed"
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        with self.assertRaisesRegex(BUILDER.BundleBuildError, "must pin cplt"):
            BUILDER.build_bundle(wrong_pin, SOURCE_SHA, self.root / "wrong-pin.tar.gz")

        wrong_manager = self.make_source("wrong-manager-pin")
        manager = wrong_manager / "scripts/manage_opencode.py"
        manager.write_text(
            manager.read_text(encoding="utf-8").replace("1.18.20", "1.18.21"),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            BUILDER.BundleBuildError, "SUPPORTED_OPENCODE_VERSION"
        ):
            BUILDER.build_bundle(
                wrong_manager, SOURCE_SHA, self.root / "wrong-manager.tar.gz"
            )

    def test_artifact_and_legal_distribution_inputs_are_required_and_validated(
        self,
    ) -> None:
        missing_artifacts = self.make_source("missing-artifacts")
        (missing_artifacts / "policy/client-artifacts.json").unlink()
        with self.assertRaisesRegex(BUILDER.BundleBuildError, "client artifact lock"):
            BUILDER.build_bundle(
                missing_artifacts,
                SOURCE_SHA,
                self.root / "missing-artifacts.tar.gz",
            )

        mismatched_integrity = self.make_source("mismatched-integrity")
        artifacts_path = mismatched_integrity / "policy/client-artifacts.json"
        artifacts = json.loads(artifacts_path.read_text(encoding="utf-8"))
        artifacts["opencode"]["artifacts"][0]["archive"]["sha512"] = "0" * 128
        artifacts_path.write_text(json.dumps(artifacts), encoding="utf-8")
        with self.assertRaisesRegex(BUILDER.BundleBuildError, "integrity does not match"):
            BUILDER.build_bundle(
                mismatched_integrity,
                SOURCE_SHA,
                self.root / "mismatched-integrity.tar.gz",
            )

        missing_homebrew_digest = self.make_source("missing-homebrew-digest")
        artifacts_path = missing_homebrew_digest / "policy/client-artifacts.json"
        artifacts = json.loads(artifacts_path.read_text(encoding="utf-8"))
        artifacts["opencode"]["artifacts"][0]["archive"].pop("sha256")
        artifacts_path.write_text(json.dumps(artifacts), encoding="utf-8")
        with self.assertRaisesRegex(BUILDER.BundleBuildError, "contain exactly"):
            BUILDER.build_bundle(
                missing_homebrew_digest,
                SOURCE_SHA,
                self.root / "missing-homebrew-digest.tar.gz",
            )

        false_github_evidence = self.make_source("false-github-evidence")
        artifacts_path = false_github_evidence / "policy/client-artifacts.json"
        artifacts = json.loads(artifacts_path.read_text(encoding="utf-8"))
        artifacts["cplt"]["artifacts"][0]["archive"]["digestEvidence"][
            "reportedDigest"
        ] = "sha256:" + "0" * 64
        artifacts_path.write_text(json.dumps(artifacts), encoding="utf-8")
        with self.assertRaisesRegex(BUILDER.BundleBuildError, "GitHub asset digest"):
            BUILDER.build_bundle(
                false_github_evidence,
                SOURCE_SHA,
                self.root / "false-github-evidence.tar.gz",
            )

        false_checksum_row = self.make_source("false-checksum-row")
        artifacts_path = false_checksum_row / "policy/client-artifacts.json"
        artifacts = json.loads(artifacts_path.read_text(encoding="utf-8"))
        checksum = artifacts["cplt"]["checksumManifest"]
        checksum["content"] = checksum["content"].replace(
            "fb1fd69f5ff42deb1cf2e510d97a58ff5f7ddf913e1cd4f7533815a16588eeda",
            "0" * 64,
            1,
        )
        checksum["sha256"] = sha256(checksum["content"].encode("utf-8"))
        artifacts_path.write_text(json.dumps(artifacts), encoding="utf-8")
        with mock.patch.object(
            BUILDER, "CPLT_CHECKSUMS_SHA256", checksum["sha256"]
        ), self.assertRaisesRegex(BUILDER.BundleBuildError, "SHA256SUMS rows"):
            BUILDER.build_bundle(
                false_checksum_row,
                SOURCE_SHA,
                self.root / "false-checksum-row.tar.gz",
            )

        manager_digest_drift = self.make_source("manager-digest-drift")
        manager_path = manager_digest_drift / "scripts/manage_opencode.py"
        manager_path.write_text(
            manager_path.read_text(encoding="utf-8").replace(
                "423af2ce6166b0ddc1939d2e4d1340837daa23a29ccc58024ec0a849051becb2",
                "0" * 64,
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            BUILDER.BundleBuildError, "PINNED_CPLT_BINARY_SHA256 must match"
        ):
            BUILDER.build_bundle(
                manager_digest_drift,
                SOURCE_SHA,
                self.root / "manager-digest-drift.tar.gz",
            )

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
        with self.assertRaisesRegex(BUILDER.BundleBuildError, "complete 7-agent/42-skill"):
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
