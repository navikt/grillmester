from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import signal
import stat
import sys
import tempfile
import time
import types
import unittest
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_manage_opencode",
    ROOT / "scripts/manage_opencode.py",
)
assert SPEC and SPEC.loader
MANAGER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MANAGER
SPEC.loader.exec_module(MANAGER)
CONTENT_LOCK = json.loads((ROOT / "policy/content-lock.json").read_text(encoding="utf-8"))
AGENT_IDS = tuple(sorted(CONTENT_LOCK["agents"]))
SKILL_IDS = tuple(sorted(CONTENT_LOCK["skills"]))
FIXTURE_SKILL = SKILL_IDS[0]


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class ManageOpenCodeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.account_home = self.root / "account"
        self.home = self.account_home / ".local/share/grillmester/opencode"
        self.runtime = self.home / "runtime"
        self.source = self.root / "source"
        self.target = self.source / "targets/opencode-v1"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_bundle(self, marker: str = "one") -> Path:
        files = {"opencode.json": b'{"$schema":"https://opencode.ai/config.json"}\n'}
        primary_agents = {"barista", "designer", "doctor-who", "grillmester"}
        for agent_id in AGENT_IDS:
            mode = "primary" if agent_id in primary_agents else "subagent"
            heading = marker if agent_id == "grillmester" else agent_id
            permission = "  edit: ask\n"
            if agent_id == "designer":
                permission += (
                    "  bash:\n"
                    '    "*": deny\n'
                    '    "node scripts/server.js --project-dir *": ask\n'
                    '    "node *grillmester-design-prototype/scripts/server.js --project-dir *": ask\n'
                    '    "node scripts/server.js * --cleanup-all*": deny\n'
                    '    "node *grillmester-design-prototype/scripts/server.js * --cleanup-all*": deny\n'
                )
            files[f"agents/{agent_id}.md"] = (
                "---\n"
                f"description: test {agent_id}\n"
                f"mode: {mode}\n"
                f"hidden: {'false' if mode == 'primary' else 'true'}\n"
                "permission:\n"
                f"{permission}"
                "---\n"
                f"# {heading}\n"
            ).encode()
        for skill_id in SKILL_IDS:
            files[f"commands/{skill_id}.md"] = (
                "---\n"
                f"description: test command for {skill_id}\n"
                "---\n"
                "Run the test command.\n"
            ).encode()
            files[f"skills/{skill_id}/SKILL.md"] = (
                "---\n"
                f"name: {skill_id}\n"
                "description: test skill\n"
                "---\n"
                "# Test skill\n"
            ).encode()
        files[f"skills/{FIXTURE_SKILL}/helper.sh"] = b"#!/bin/sh\nexit 0\n"
        manifest_files: dict[str, dict[str, str]] = {}
        self.target = self.source / "targets/opencode-v1"
        self.target.mkdir(parents=True, exist_ok=True)
        for relative, content in files.items():
            path = self.target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            mode = 0o755 if relative.endswith(".sh") else 0o644
            path.chmod(mode)
            manifest_files[relative] = {
                "sha256": sha256(content),
                "mode": f"{mode:04o}",
            }
        manifest = {
            "schemaVersion": 1,
            "target": "opencode-v1",
            "generatorVersion": 1,
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
                    if skill_id in MANAGER.OPENCODE_OVERLAY_SKILL_IDS
                    else "native"
                )
                for skill_id in SKILL_IDS
            },
            "files": manifest_files,
        }
        (self.target / "manifest.json").write_text(
            json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
        )
        manager = self.source / "scripts/manage_opencode.py"
        manager.parent.mkdir(parents=True, exist_ok=True)
        manager.write_bytes((ROOT / "scripts/manage_opencode.py").read_bytes())
        manager.chmod(0o755)
        composer = self.source / "scripts/compose_opencode_permissions.py"
        composer.write_bytes(
            (ROOT / "scripts/compose_opencode_permissions.py").read_bytes()
        )
        composer.chmod(0o644)
        for source_relative, destination_relative, mode in (
            ("scripts/verify_client_artifact.py", "scripts/verify_client_artifact.py", 0o755),
            ("policy/client-artifacts.json", "policy/client-artifacts.json", 0o644),
            ("policy/content-lock.json", "policy/content-lock.json", 0o644),
            ("LICENSE", "LICENSE", 0o644),
            ("PROVENANCE.md", "PROVENANCE.md", 0o644),
            ("plugin/THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md", 0o644),
        ):
            destination = self.source / destination_relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / source_relative).read_bytes())
            destination.chmod(mode)
        profiles = self.source / "profiles/opencode"
        profiles.mkdir(parents=True, exist_ok=True)
        for profile in (ROOT / "profiles/opencode").glob("*.json"):
            destination = profiles / profile.name
            destination.write_bytes(profile.read_bytes())
            destination.chmod(0o644)
        self.seal_distribution()
        return self.source

    def seal_distribution(self) -> None:
        outer = self.source / "DISTRIBUTION-MANIFEST.json"
        entries: dict[str, dict[str, str]] = {}
        for path in sorted(self.source.rglob("*")):
            if not path.is_file() or path == outer:
                continue
            relative = path.relative_to(self.source).as_posix()
            entries[relative] = {
                "sha256": sha256(path.read_bytes()),
                "mode": f"{stat.S_IMODE(path.stat().st_mode):04o}",
            }
        target_manifest = (self.target / "manifest.json").read_bytes()
        manifest = {
            "schemaVersion": 1,
            "sourceSha": "1" * 40,
            "target": "opencode-v1",
            "opencodeVersion": "1.18.20",
            "cpltRelease": "2026.08.17-062831-1008a92",
            "targetManifestSha256": sha256(target_manifest),
            "files": entries,
        }
        outer.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        outer.chmod(0o644)

    def run_cli(
        self,
        *arguments: str,
        environment: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        pinned_digests = dict(MANAGER.PINNED_CPLT_BINARY_SHA256)
        pinned_opencode_digests = dict(MANAGER.PINNED_OPENCODE_BINARY_SHA256)
        fake_cplt = self.root / "bin/cplt"
        if fake_cplt.is_file():
            system, architecture = MANAGER._host_platform_tuple()
            pinned_digests[(system, architecture)] = sha256(fake_cplt.read_bytes())
        fake_opencode = self.root / "bin/opencode"
        if fake_opencode.is_file():
            system, architecture = MANAGER._host_platform_tuple()
            pinned_opencode_digests[(system, architecture, "test-fixture")] = sha256(
                fake_opencode.read_bytes()
            )
        with mock.patch.object(MANAGER, "_account_home", return_value=self.account_home):
            with mock.patch.object(
                MANAGER, "PINNED_CPLT_BINARY_SHA256", pinned_digests
            ):
                with mock.patch.object(
                    MANAGER,
                    "PINNED_OPENCODE_BINARY_SHA256",
                    pinned_opencode_digests,
                ):
                    # Keep lifecycle tests independent of the developer machine's
                    # ambient tool-manager roots (for example NVM_DIR).  Tests
                    # that exercise inherited values pass them explicitly.
                    with mock.patch.dict(os.environ, environment or {}, clear=True):
                        with redirect_stdout(stdout), redirect_stderr(stderr):
                            result = MANAGER.main(list(arguments))
        return result, stdout.getvalue(), stderr.getvalue()

    def install(self, source: Path | None = None) -> str:
        result, stdout, stderr = self.run_cli(
            "install",
            "--source",
            str(source or self.source),
            "--home",
            str(self.home),
        )
        self.assertEqual(result, 0, stderr)
        payload = json.loads(stdout)
        return payload["activeRelease"]

    def make_fake_client(
        self,
        name: str,
        *,
        opencode_version: str = "1.18.20",
        cplt_version: str = "cplt 2026.08.17-062831-1008a92",
    ) -> Path:
        executable = self.root / "bin" / name
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_text(
            """#!__PYTHON__
import json
import os
import pathlib
import sys

executable = pathlib.Path(sys.argv[0]).name
client_args = (
    sys.argv[sys.argv.index("--") + 1 :]
    if executable == "cplt" and "--" in sys.argv
    else sys.argv[1:]
)
if executable == "cplt" and "--" in sys.argv and client_args == ["--version"]:
    print(__OPENCODE_VERSION__)
    raise SystemExit(0)

if sys.argv[1:] == ["--version"]:
    if "TEST_PROVIDER_TOKEN" in os.environ:
        print("secret leaked to version check", file=sys.stderr)
        raise SystemExit(9)
    if executable == "cplt":
        print(__CPLT_VERSION__)
    else:
        print(__OPENCODE_VERSION__)
    raise SystemExit(0)

config = pathlib.Path(os.environ["OPENCODE_CONFIG_DIR"])
runtime_gitignore = "node_modules\\npackage.json\\npackage-lock.json\\nbun.lock\\n.gitignore\\n"
if executable == "cplt" and client_args[:1] == ["debug"]:
    project = pathlib.Path(sys.argv[sys.argv.index("--project-dir") + 1])
    if project.name != "preflight-project":
        print("debug probe used the writable consumer project", file=sys.stderr)
        raise SystemExit(16)
    try:
        observed_gitignore = (config / ".gitignore").read_text()
    except OSError as exc:
        print(f"missing sealed runtime .gitignore: {exc}", file=sys.stderr)
        raise SystemExit(17)
    if observed_gitignore != runtime_gitignore:
        print("unexpected sealed runtime .gitignore", file=sys.stderr)
        raise SystemExit(17)
    if config.name != "permission-input":
        isolated_gitignore = (
            pathlib.Path(os.environ["XDG_CONFIG_HOME"]) / "opencode/.gitignore"
        )
        try:
            observed_isolated_gitignore = isolated_gitignore.read_text()
        except OSError as exc:
            print(f"missing isolated XDG .gitignore: {exc}", file=sys.stderr)
            raise SystemExit(18)
        if observed_isolated_gitignore != runtime_gitignore:
            print("unexpected isolated XDG .gitignore", file=sys.stderr)
            raise SystemExit(18)

def document(path):
    text = path.read_text()
    end = text.index("\\n---\\n", 4)
    fields = {}
    for line in text[4:end].splitlines():
        if not line or line == "permission:" or line.startswith("  "):
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value in ("true", "false"):
            fields[key] = value == "true"
        elif value.startswith('"'):
            fields[key] = json.loads(value)
        else:
            fields[key] = value
    return fields, text[end + 5 :].strip()

def permission_rules(permission):
    rules = []
    for key, value in permission.items():
        if isinstance(value, str):
            rules.append({"permission": key, "pattern": "*", "action": value})
        else:
            for pattern, action in value.items():
                rules.append(
                    {"permission": key, "pattern": pattern, "action": action}
                )
    return rules

content = json.loads(
    os.environ.get(
        "OPENCODE_CONFIG_CONTENT",
        '{"autoupdate":false,"share":"disabled"}',
    )
)
if client_args == ["debug", "config"]:
    if config.name != "permission-input":
        if config.name != "config-probe":
            print("final config probe did not use a bounded clone", file=sys.stderr)
            raise SystemExit(19)
        for agent_path in (config / "agents").glob("*.md"):
            configured = content.get("agent", {}).get(agent_path.stem, {})
            if "permission" in configured:
                print(
                    "final structure probe retained generated permission bulk",
                    file=sys.stderr,
                )
                raise SystemExit(19)
        for agent_path in (config / "agents").glob("*.md"):
            agent_text = agent_path.read_text()
            frontmatter_end = agent_text.index("\\n---\\n", 4)
            if not agent_text[frontmatter_end + 5 :].strip().startswith(
                "Managed OpenCode config probe for "
            ):
                print("config probe retained an unbounded agent body", file=sys.stderr)
                raise SystemExit(19)
    output = {
        "autoupdate": content.get("autoupdate", False),
        "share": content.get("share", "disabled"),
        "plugin": [],
        "mcp": {},
        **content,
    }
    commands = {}
    for path in sorted((config / "commands").glob("*.md")):
        fields, template = document(path)
        commands[path.stem] = {"template": template, **fields}
    if commands:
        output["command"] = commands
    print(json.dumps(output))
    raise SystemExit(0)

if len(client_args) == 3 and client_args[:2] == ["debug", "agent"]:
    if config.name != "config":
        print("effective agent probe did not use the full config", file=sys.stderr)
        raise SystemExit(20)
    tool_output_rule = {
        "permission": "external_directory",
        "pattern": str(
            pathlib.Path(os.environ["XDG_DATA_HOME"])
            / "opencode/tool-output/*"
        ),
        "action": "allow",
    }
    agent_id = client_args[2]
    configured = content.get("agent", {}).get(agent_id, {})
    if configured.get("disable") is True:
        print(f"Agent {agent_id} not found", file=sys.stderr)
        raise SystemExit(1)
    if agent_id in ("compaction", "summary", "title"):
        print(
            json.dumps(
                {
                    "name": agent_id,
                    "description": "native housekeeping",
                    "mode": "primary",
                    "hidden": True,
                    "native": True,
                    "prompt": "native",
                    "options": {},
                    "permission": [
                        *permission_rules(content.get("permission", {})),
                        *permission_rules(configured.get("permission", {})),
                        tool_output_rule,
                    ],
                    "tools": {},
                }
            )
        )
        raise SystemExit(0)
    path = config / "agents" / (agent_id + ".md")
    fields, prompt = document(path)
    if not isinstance(configured.get("permission"), dict):
        print("effective agent probe omitted composed permissions", file=sys.stderr)
        raise SystemExit(20)
    intended = content["agent"][agent_id]["permission"]
    output = {
        "name": agent_id,
        "description": fields["description"],
        "mode": fields["mode"],
        "hidden": fields["hidden"],
        "prompt": prompt,
        "options": {},
        "permission": [
            *permission_rules(content.get("permission", {})),
            *permission_rules(intended),
            tool_output_rule,
        ],
        "tools": {},
    }
    print(json.dumps(output))
    raise SystemExit(0)

if client_args == ["debug", "skill"]:
    if config.name != "config-probe":
        print("skill probe did not use the bounded clone", file=sys.stderr)
        raise SystemExit(21)
    skill_output = [
        {
            "name": "customize-opencode",
            "description": "Pinned fake built-in skill",
            "location": "<built-in>",
            "content": "Pinned fake built-in content.\\n",
        }
    ]
    for path in sorted((config / "skills").glob("*/SKILL.md")):
        fields, body = document(path)
        expected = f"Managed OpenCode skill probe for {path.parent.name}."
        if body != expected:
            print("skill probe retained an unbounded skill body", file=sys.stderr)
            raise SystemExit(21)
        skill_output.append(
            {
                "name": fields["name"],
                "description": fields["description"],
                "location": str(path.resolve()),
                "content": body + "\\n",
            }
        )
    print(json.dumps(skill_output))
    raise SystemExit(0)

capture = {
    "executable": sys.argv[0],
    "argv": sys.argv[1:],
    "config": str(config),
    "configExists": config.is_dir(),
    "files": sorted(
        str(path.relative_to(config))
        for path in config.rglob("*")
        if path.is_file()
    ),
    "agent": (config / "agents/grillmester.md").read_text(),
    "ambientSecret": os.environ.get("AMBIENT_SECRET"),
    "cpltConfig": os.environ.get("CPLT_CONFIG"),
    "policyFiles": {
        flag: pathlib.Path(sys.argv[sys.argv.index(flag) + 1]).read_text()
        for flag in ("--allowed-domains", "--blocked-domains")
        if flag in sys.argv
    },
    "environment": {
        key: os.environ.get(key)
        for key in (
            "OPENCODE_CONFIG_DIR",
            "OPENCODE_CONFIG_CONTENT",
            "OPENCODE_DISABLE_AUTOUPDATE",
            "OPENCODE_PURE",
            "OPENCODE_DISABLE_MODELS_FETCH",
            "OPENCODE_DISABLE_LSP_DOWNLOAD",
            "OPENCODE_DISABLE_DEFAULT_PLUGINS",
            "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT",
            "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS",
            "OPENCODE_DISABLE_EXTERNAL_SKILLS",
            "OPENCODE_DISABLE_SHARE",
            "OPENCODE_AUTO_SHARE",
            "OPENCODE_ENABLE_EXA",
            "OPENCODE_EXPERIMENTAL",
            "OPENCODE_EXPERIMENTAL_CODE_MODE",
            "OPENCODE_MODELS_PATH",
            "OPENCODE_DB",
            "OPENCODE_AUTH_CONTENT",
            "OPENCODE_TEST_HOME",
            "XDG_CACHE_HOME",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "XDG_STATE_HOME",
            "PATH",
        )
    },
}
pathlib.Path(os.environ["FAKE_CAPTURE"]).write_text(json.dumps(capture))
"""
            .replace("__CPLT_VERSION__", repr(cplt_version))
            .replace("__OPENCODE_VERSION__", repr(opencode_version))
            .replace("__PYTHON__", str(Path(sys.executable).resolve())),
            encoding="utf-8",
        )
        executable.chmod(0o755)
        return executable

    def client_environment(self, **values: str) -> dict[str, str]:
        return {
            "PATH": str(self.root / "bin") + os.pathsep + os.environ.get("PATH", ""),
            **values,
        }

    def read_state(self) -> dict[str, object]:
        return json.loads((self.home / "state.json").read_text(encoding="utf-8"))

    def test_install_is_verified_immutable_and_idempotent(self) -> None:
        self.make_bundle()

        release_id = self.install()
        distribution = self.home / "releases" / release_id / "distribution"
        release = distribution / "targets/opencode-v1"
        state_before = (self.home / "state.json").read_bytes()
        inode_before = release.stat().st_ino

        self.assertTrue(
            (release / "agents/grillmester.md").read_text().endswith("# one\n")
        )
        self.assertEqual(
            stat.S_IMODE((release / "agents/grillmester.md").stat().st_mode),
            0o444,
        )
        self.assertEqual(
            stat.S_IMODE(
                (release / f"skills/{FIXTURE_SKILL}/helper.sh").stat().st_mode
            ),
            0o555,
        )
        self.assertEqual(
            stat.S_IMODE((release / "manifest.json").stat().st_mode), 0o444
        )

        same_release = self.install()

        self.assertEqual(same_release, release_id)
        self.assertEqual(release.stat().st_ino, inode_before)
        self.assertEqual((self.home / "state.json").read_bytes(), state_before)

    def test_install_rejects_tampering_extras_and_symlinks_without_state(self) -> None:
        self.make_bundle()
        (self.target / "agents/grillmester.md").write_text("tampered\n")

        result, _, stderr = self.run_cli(
            "install", "--source", str(self.source), "--home", str(self.home)
        )

        self.assertEqual(result, 2)
        self.assertIn("checksum", stderr)
        self.assertFalse((self.home / "state.json").exists())

        self.source = self.root / "source-extra"
        self.make_bundle()
        (self.target / "unmanifested.txt").write_text("unexpected\n")
        result, _, stderr = self.run_cli(
            "install", "--source", str(self.source), "--home", str(self.home)
        )
        self.assertEqual(result, 2)
        self.assertIn("unmanifested", stderr)
        self.assertFalse((self.home / "state.json").exists())

        if hasattr(os, "symlink"):
            self.source = self.root / "source-link"
            self.make_bundle()
            os.symlink(self.target / "opencode.json", self.target / "linked.json")
            result, _, stderr = self.run_cli(
                "install", "--source", str(self.source), "--home", str(self.home)
            )
            self.assertEqual(result, 2)
            self.assertIn("symlink", stderr)
            self.assertFalse((self.home / "state.json").exists())

    def test_install_rejects_a_re_manifested_component_omission(self) -> None:
        self.make_bundle()
        omitted = f"agents/{AGENT_IDS[0]}.md"
        (self.target / omitted).unlink()
        manifest_path = self.target / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"].pop(omitted)
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
        )
        self.seal_distribution()

        result, _, stderr = self.run_cli(
            "install", "--source", str(self.source), "--home", str(self.home)
        )

        self.assertEqual(result, 2)
        self.assertIn("exact reviewed 7-agent/42-skill/42-command roster", stderr)
        self.assertFalse((self.home / "state.json").exists())

    def test_install_rejects_re_manifested_skill_capability_drift(self) -> None:
        self.make_bundle()
        manifest_path = self.target / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        current = manifest["skillCapabilities"][FIXTURE_SKILL]
        manifest["skillCapabilities"][FIXTURE_SKILL] = (
            "overlay" if current == "native" else "native"
        )
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
        )
        self.seal_distribution()

        result, _, stderr = self.run_cli(
            "install", "--source", str(self.source), "--home", str(self.home)
        )

        self.assertEqual(result, 2)
        self.assertIn("reviewed classification", stderr)
        self.assertFalse((self.home / "state.json").exists())

    def test_install_rejects_oversized_sparse_input_before_reading_it(self) -> None:
        self.make_bundle()
        oversized = self.target / "agents/grillmester.md"
        with oversized.open("r+b") as output:
            output.truncate(MANAGER.MAX_FILE_BYTES + 1)

        result, _, stderr = self.run_cli(
            "install", "--source", str(self.source), "--home", str(self.home)
        )

        self.assertEqual(result, 2)
        self.assertIn("safety limit", stderr)
        self.assertFalse((self.home / "state.json").exists())

    def test_install_rejects_source_and_lifecycle_home_overlap_without_writes(self) -> None:
        self.make_bundle()
        source_snapshot = {
            path.relative_to(self.source): path.read_bytes()
            for path in self.source.rglob("*")
            if path.is_file()
        }
        nested_home = self.source / "managed-home"

        result, _, stderr = self.run_cli(
            "install",
            "--source",
            str(self.source),
            "--home",
            str(nested_home),
        )

        self.assertEqual(result, 2)
        self.assertIn("must not overlap the verified distribution source", stderr)
        self.assertFalse(nested_home.exists())
        self.assertEqual(
            source_snapshot,
            {
                path.relative_to(self.source): path.read_bytes()
                for path in self.source.rglob("*")
                if path.is_file()
            },
        )

        containing_home = self.root / "containing-home"
        self.source = containing_home / "source"
        self.make_bundle()
        result, _, stderr = self.run_cli(
            "install",
            "--source",
            str(self.source),
            "--home",
            str(containing_home),
        )

        self.assertEqual(result, 2)
        self.assertIn("must not overlap the verified distribution source", stderr)
        self.assertFalse((containing_home / "releases").exists())

    def test_resource_limits_and_reads_stay_bounded_after_fstat(self) -> None:
        self.assertEqual(MANAGER.MAX_FILE_BYTES, 5_000_000)
        self.assertEqual(MANAGER.MAX_EXECUTABLE_BYTES, 256 * 1024 * 1024)
        self.assertEqual(MANAGER.MAX_DISTRIBUTION_BYTES, 50_000_000)
        self.assertEqual(MANAGER.MAX_DISTRIBUTION_MEMBERS, 10_000)

        growing = self.root / "grew-after-fstat.bin"
        growing.write_bytes(b"123456789")
        initially_small = mock.Mock(st_mode=stat.S_IFREG | 0o644, st_size=1)
        with mock.patch.object(MANAGER.os, "fstat", return_value=initially_small):
            with self.assertRaisesRegex(MANAGER.LifecycleError, "safety limit"):
                MANAGER._regular_file(growing, label="growing input", max_bytes=8)

    def test_distribution_member_limit_includes_the_root(self) -> None:
        bundle = self.root / "too-many-members"
        bundle.mkdir()
        (bundle / "one").write_bytes(b"")
        (bundle / "two").write_bytes(b"")

        with mock.patch.object(MANAGER, "MAX_DISTRIBUTION_MEMBERS", 2):
            with self.assertRaisesRegex(MANAGER.LifecycleError, "member safety limit"):
                MANAGER._bundle_inventory(bundle)

        self.make_bundle()
        target_manifest = json.loads(
            (self.target / "manifest.json").read_text(encoding="utf-8")
        )
        with mock.patch.object(
            MANAGER,
            "MAX_DISTRIBUTION_MEMBERS",
            len(target_manifest["files"]) + 1,
        ):
            with self.assertRaisesRegex(
                MANAGER.LifecycleError, "target manifest.*member safety limit"
            ):
                MANAGER._parse_manifest(self.target)

        distribution_manifest = json.loads(
            (self.source / MANAGER.DISTRIBUTION_MANIFEST).read_text(encoding="utf-8")
        )
        with mock.patch.object(
            MANAGER,
            "MAX_DISTRIBUTION_MEMBERS",
            len(distribution_manifest["files"]) + 1,
        ):
            with self.assertRaisesRegex(
                MANAGER.LifecycleError,
                "distribution manifest.*member safety limit",
            ):
                MANAGER._parse_distribution_manifest(
                    self.source, require_current_contract=True
                )

    def test_installing_a_new_release_and_rollback_swap_active_releases(self) -> None:
        self.make_bundle("one")
        release_one = self.install()
        source_two = self.root / "source-two"
        self.source = source_two
        self.make_bundle("two")

        release_two = self.install(source_two)
        self.assertNotEqual(release_two, release_one)
        self.assertEqual(
            self.read_state(),
            {
                "schemaVersion": 1,
                "active": release_two,
                "previous": release_one,
            },
        )

        result, stdout, stderr = self.run_cli(
            "rollback", "--home", str(self.home)
        )

        self.assertEqual(result, 0, stderr)
        self.assertEqual(json.loads(stdout)["activeRelease"], release_one)
        self.assertEqual(
            self.read_state(),
            {
                "schemaVersion": 1,
                "active": release_one,
                "previous": release_two,
            },
        )

    def test_profile_only_change_gets_a_new_distribution_release_id(self) -> None:
        self.make_bundle("same-target")
        first = self.install()

        self.source = self.root / "profile-only-source"
        self.make_bundle("same-target")
        profile = self.source / "profiles/opencode/local.json"
        value = json.loads(profile.read_text(encoding="utf-8"))
        value["description"] += " Reviewed wording update."
        profile.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        profile.chmod(0o644)
        self.seal_distribution()

        second = self.install()

        self.assertNotEqual(first, second)
        installed = (
            self.home
            / "releases"
            / second
            / "distribution/profiles/opencode/local.json"
        )
        self.assertIn("Reviewed wording update", installed.read_text(encoding="utf-8"))

    def test_manifest_parser_rejects_ambiguous_json_paths_and_modes(self) -> None:
        cases = ("duplicate-key", "portable-collision", "unsafe-mode", "non-finite")
        for case in cases:
            with self.subTest(case=case):
                self.source = self.root / f"source-{case}"
                self.home = self.root / f"home-{case}"
                self.make_bundle()
                manifest_path = self.target / "manifest.json"
                if case == "duplicate-key":
                    content = manifest_path.read_text(encoding="utf-8")
                    manifest_path.write_text(
                        content.replace(
                            "{", '{"schemaVersion":1,', 1
                        ),
                        encoding="utf-8",
                    )
                    expected = "duplicate JSON key"
                elif case == "portable-collision":
                    value = json.loads(manifest_path.read_text(encoding="utf-8"))
                    value["files"]["agents/Grillmester.md"] = value["files"][
                        "agents/grillmester.md"
                    ]
                    manifest_path.write_text(
                        json.dumps(value, sort_keys=True) + "\n", encoding="utf-8"
                    )
                    expected = "portable manifest path collision"
                elif case == "unsafe-mode":
                    value = json.loads(manifest_path.read_text(encoding="utf-8"))
                    value["files"]["opencode.json"]["mode"] = "0666"
                    (self.target / "opencode.json").chmod(0o666)
                    manifest_path.write_text(
                        json.dumps(value, sort_keys=True) + "\n", encoding="utf-8"
                    )
                    expected = "unsupported mode"
                else:
                    content = manifest_path.read_text(encoding="utf-8")
                    manifest_path.write_text(
                        content.replace("{", '{"unexpected":NaN,', 1),
                        encoding="utf-8",
                    )
                    expected = "non-standard JSON constant"

                self.seal_distribution()

                result, _, stderr = self.run_cli(
                    "install",
                    "--source",
                    str(self.source),
                    "--home",
                    str(self.home),
                )
                self.assertEqual(result, 2)
                self.assertIn(expected, stderr)
                self.assertFalse((self.home / "state.json").exists())

    def test_install_refuses_to_chain_from_a_corrupted_active_release(self) -> None:
        self.make_bundle("one")
        active = self.install()
        state_before = (self.home / "state.json").read_bytes()
        releases_before = sorted((self.home / "releases").iterdir())
        installed = (
            self.home
            / "releases"
            / active
            / "distribution/targets/opencode-v1/agents/grillmester.md"
        )
        installed.chmod(0o644)

        self.source = self.root / "source-two"
        self.make_bundle("two")
        result, _, stderr = self.run_cli(
            "install", "--source", str(self.source), "--home", str(self.home)
        )

        self.assertEqual(result, 2)
        self.assertIn("mode mismatch", stderr)
        self.assertEqual((self.home / "state.json").read_bytes(), state_before)
        self.assertEqual(sorted((self.home / "releases").iterdir()), releases_before)

    def test_state_is_strict_private_and_rejects_duplicate_fields(self) -> None:
        self.make_bundle()
        active = self.install()
        state_path = self.home / "state.json"

        state_path.chmod(0o644)
        result, _, stderr = self.run_cli("rollback", "--home", str(self.home))
        self.assertEqual(result, 2)
        self.assertIn("mode 0600", stderr)

        state_path.write_text(
            (
                '{"schemaVersion":1,"active":"'
                + active
                + '","active":"'
                + active
                + '","previous":null}\n'
            ),
            encoding="utf-8",
        )
        state_path.chmod(0o600)
        result, _, stderr = self.run_cli("rollback", "--home", str(self.home))
        self.assertEqual(result, 2)
        self.assertIn("duplicate JSON key", stderr)

    def test_hybrid_launch_stages_bundle_and_passes_explicit_cplt_policy(self) -> None:
        self.make_bundle()
        release_id = self.install()
        cplt = self.make_fake_client("cplt")
        self.make_fake_client("opencode")
        hostile_git_marker = self.root / "hostile-git-executed"
        hostile_git = self.root / "bin/git"
        hostile_git.write_text(
            f"#!/bin/sh\ntouch {str(hostile_git_marker)!r}\nexit 1\n",
            encoding="utf-8",
        )
        hostile_git.chmod(0o755)
        capture = self.root / "cplt-capture.json"
        consumer = self.root / "consumer"
        consumer.mkdir()
        ambient_auth = self.account_home / ".local/share/opencode/auth.json"
        ambient_auth.parent.mkdir(parents=True)
        ambient_auth.write_text(
            '{"provider":{"type":"api","key":"ambient-secret"}}\n',
            encoding="utf-8",
        )
        ambient_auth.chmod(0o600)
        ambient_auth_before = ambient_auth.read_bytes()
        (consumer / ".git").mkdir()
        unrelated = self.root / "unrelated-repository"
        (unrelated / ".git").mkdir(parents=True)
        before = sorted(consumer.iterdir())
        previous_cwd = Path.cwd()
        try:
            os.chdir(consumer)
            result, _, stderr = self.run_cli(
                "launch",
                "--home",
                str(self.home),
                "--runtime-root",
                str(self.runtime),
                "--profile",
                "hybrid",
                "--local-port",
                "1234",
                "--provider-domain",
                "inference.example.org",
                "--private-provider-domain",
                "inference.example.org",
                "--pass-env",
                "TEST_PROVIDER_TOKEN",
                "--pass-env",
                "FAKE_CAPTURE",
                "--runtime-agent",
                "barista",
                "--cplt",
                str(cplt),
                "--",
                "run",
                "safe prompt",
                environment=self.client_environment(
                    FAKE_CAPTURE=str(capture),
                    TEST_PROVIDER_TOKEN="secret-not-written-to-bundle",
                    GIT_DIR=str(unrelated / ".git"),
                    GIT_WORK_TREE=str(unrelated),
                ),
            )
        finally:
            os.chdir(previous_cwd)

        self.assertEqual(result, 0, stderr)
        self.assertEqual(sorted(consumer.iterdir()), before)
        payload = json.loads(capture.read_text(encoding="utf-8"))
        argv = payload["argv"]
        config = Path(payload["config"])
        staged_cplt = Path(payload["executable"])
        release = (
            self.home / "releases" / release_id / "distribution/targets/opencode-v1"
        )
        self.assertTrue(payload["configExists"])
        self.assertFalse(config.exists(), "per-launch staging should be cleaned up")
        self.assertNotEqual(staged_cplt, cplt)
        self.assertIn(str(self.runtime), str(staged_cplt))
        self.assertFalse(staged_cplt.exists(), "trusted cplt stage should be cleaned up")
        self.assertNotEqual(config, self.source)
        self.assertNotEqual(config, release)
        self.assertIn(str(self.runtime), str(config))
        self.assertTrue(payload["agent"].endswith("# one\n"))
        target_manifest = json.loads((release / "manifest.json").read_text())
        self.assertEqual(
            set(payload["files"]),
            {".gitignore", "manifest.json", *target_manifest["files"]},
        )
        self.assertEqual(
            argv[argv.index("--agent") : argv.index("--agent") + 2],
            ["--agent", "opencode"],
        )
        self.assertIn("--project-dir", argv)
        self.assertEqual(
            argv[argv.index("--project-dir") + 1], str(consumer.resolve())
        )
        managed_path = payload["environment"]["PATH"].split(os.pathsep)
        self.assertEqual("trusted-bin", Path(managed_path[0]).name)
        self.assertNotIn(str(self.root / "bin"), managed_path)
        self.assertFalse(
            hostile_git_marker.exists(),
            "repo/PATH-controlled git must never execute before cplt isolation",
        )
        self.assertIn("--preset", argv)
        self.assertIn("strict", argv)
        self.assertIn("--allow-read", argv)
        self.assertIn(str(config), argv)
        self.assertNotIn(str(release), argv)
        self.assertNotIn("--allow-write", argv)
        self.assertIn("--pass-env", argv)
        self.assertIn("OPENCODE_CONFIG_DIR", argv)
        self.assertIn("OPENCODE_CONFIG_CONTENT", argv)
        self.assertIn("OPENCODE_PURE", argv)
        self.assertEqual("true", payload["environment"]["OPENCODE_PURE"])
        self.assertEqual(":memory:", payload["environment"]["OPENCODE_DB"])
        self.assertEqual({}, json.loads(payload["environment"]["OPENCODE_AUTH_CONTENT"]))
        self.assertEqual(ambient_auth_before, ambient_auth.read_bytes())
        self.assertIn("OPENCODE_AUTH_CONTENT", argv)
        isolated_test_home = Path(payload["environment"]["OPENCODE_TEST_HOME"])
        self.assertIn(str(self.runtime), str(isolated_test_home))
        self.assertFalse(
            isolated_test_home.exists(),
            "per-process OpenCode test home must be removed",
        )
        self.assertIn("OPENCODE_TEST_HOME", argv)
        for name in (
            "XDG_CACHE_HOME",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "XDG_STATE_HOME",
        ):
            isolated = Path(payload["environment"][name])
            self.assertIn(str(self.runtime), str(isolated))
            self.assertFalse(isolated.exists(), "per-process XDG stage must be removed")
            self.assertIn(name, argv)
        self.assertIn("TEST_PROVIDER_TOKEN", argv)
        self.assertIn("--allow-localhost", argv)
        self.assertIn("1234", argv)
        self.assertEqual(
            argv[argv.index("--allow-private-domain") + 1],
            "inference.example.org",
        )
        allowed_path = Path(argv[argv.index("--allowed-domains") + 1])
        self.assertFalse(allowed_path.exists(), "ephemeral policy should be cleaned up")
        self.assertEqual(
            argv[-5:],
            ["--", "run", "--agent", "barista", "safe prompt"],
        )

    def test_cplt_launch_uses_private_opencode_copy_without_executing_source(
        self,
    ) -> None:
        self.make_bundle()
        self.install()
        original = self.root / "bin/opencode"
        original.parent.mkdir(parents=True, exist_ok=True)
        original_marker = self.root / "original-opencode-executed"
        original.write_text(
            f"""#!{str(Path(sys.executable).resolve())}
import pathlib
import sys

original = pathlib.Path({str(original)!r}).resolve()
if pathlib.Path(sys.argv[0]).resolve() == original:
    pathlib.Path({str(original_marker)!r}).write_text("executed\\n")
if sys.argv[1:] == ["--version"]:
    print("1.18.20")
    raise SystemExit(0)
raise SystemExit(97)
""",
            encoding="utf-8",
        )
        original.chmod(0o755)
        original_before = (
            original.read_bytes(),
            stat.S_IMODE(original.stat().st_mode),
            original.stat().st_ino,
        )

        capture = self.root / "selected-opencode.json"
        cplt = self.root / "bin/cplt"
        cplt.write_text(
            f"""#!{str(Path(sys.executable).resolve())}
import hashlib
import json
import pathlib
import shutil
import stat
import subprocess
import sys

if sys.argv[1:] == ["--version"]:
    print("cplt 2026.08.17-062831-1008a92")
    raise SystemExit(0)
selected = shutil.which("opencode")
if selected is None:
    raise SystemExit(96)
if sys.argv[-1] == "--version":
    result = subprocess.run(
        [selected, "--version"], text=True, capture_output=True, check=False
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    raise SystemExit(result.returncode)
path = pathlib.Path(selected).resolve()
content = path.read_bytes()
replacement_blocked = False
try:
    path.write_bytes(b"replacement")
except OSError:
    replacement_blocked = True
pathlib.Path({str(capture)!r}).write_text(
    json.dumps(
        {{
            "selected": str(path),
            "sha256": hashlib.sha256(content).hexdigest(),
            "mode": stat.S_IMODE(path.stat().st_mode),
            "directoryMode": stat.S_IMODE(path.parent.stat().st_mode),
            "replacementBlocked": replacement_blocked,
        }}
    )
)
""",
            encoding="utf-8",
        )
        cplt.chmod(0o755)

        with mock.patch.object(
            MANAGER,
            "_run_cplt_json_probe",
            return_value=(
                b'{"autoupdate":false,"share":"disabled","plugin":[],"mcp":{}}'
            ),
        ), mock.patch.object(
            MANAGER,
            "_validate_composed_opencode_session",
            return_value={"fixture": "stable"},
        ):
            result, _, stderr = self.run_cli(
                "launch",
                "--home",
                str(self.home),
                "--runtime-root",
                str(self.runtime),
                "--profile",
                "local",
                "--local-port",
                "1234",
                "--cplt",
                str(cplt),
                environment=self.client_environment(),
            )

        self.assertEqual(result, 0, stderr)
        self.assertFalse(original_marker.exists(), "source OpenCode was executed")
        self.assertEqual(
            original_before,
            (
                original.read_bytes(),
                stat.S_IMODE(original.stat().st_mode),
                original.stat().st_ino,
            ),
            "source OpenCode must remain byte-for-byte unchanged",
        )
        payload = json.loads(capture.read_text(encoding="utf-8"))
        selected = Path(payload["selected"])
        self.assertNotEqual(selected, original.resolve())
        self.assertEqual(selected.name, "opencode")
        self.assertEqual(selected.parent.name, "trusted-bin")
        self.assertIn(str(self.runtime / "sessions"), str(selected))
        self.assertEqual(payload["mode"], 0o500)
        self.assertEqual(payload["directoryMode"], 0o500)
        self.assertTrue(payload["replacementBlocked"])
        self.assertEqual(payload["sha256"], sha256(original_before[0]))
        self.assertFalse(selected.exists(), "trusted OpenCode stage should be cleaned up")

    def test_cplt_rejects_oversized_opencode_before_execution(self) -> None:
        self.make_bundle()
        self.install()
        opencode = self.root / "bin/opencode"
        opencode.parent.mkdir(parents=True, exist_ok=True)
        with opencode.open("wb") as output:
            output.truncate(MANAGER.MAX_EXECUTABLE_BYTES + 1)
        opencode.chmod(0o755)
        cplt = self.make_fake_client("cplt")
        capture = self.root / "must-not-exist.json"

        result, _, stderr = self.run_cli(
            "launch",
            "--home",
            str(self.home),
            "--runtime-root",
            str(self.runtime),
            "--profile",
            "local",
            "--local-port",
            "1234",
            "--opencode",
            str(opencode),
            "--cplt",
            str(cplt),
            environment=self.client_environment(FAKE_CAPTURE=str(capture)),
        )

        self.assertEqual(result, 2)
        self.assertIn("opencode executable exceeds", stderr.lower())
        self.assertIn("safety limit", stderr.lower())
        self.assertFalse(capture.exists())

    def test_direct_launch_uses_same_stage_without_cplt(self) -> None:
        self.make_bundle()
        self.install()
        opencode = self.make_fake_client("opencode")
        opencode_before = (
            opencode.read_bytes(),
            stat.S_IMODE(opencode.stat().st_mode),
            opencode.stat().st_ino,
        )
        capture = self.root / "opencode-capture.json"

        result, _, stderr = self.run_cli(
            "launch",
            "--home",
            str(self.home),
            "--runtime-root",
            str(self.runtime),
            "--profile",
            "local",
            "--local-port",
            "8080",
            "--direct",
            "--pass-env",
            "FAKE_CAPTURE",
            "--opencode",
            str(opencode),
            "--",
            "agent",
            "list",
            environment={
                "FAKE_CAPTURE": str(capture),
                "AMBIENT_SECRET": "must-not-leak-without-pass-env",
                "OPENCODE_PURE": "0",
            },
        )

        self.assertEqual(result, 0, stderr)
        payload = json.loads(capture.read_text(encoding="utf-8"))
        self.assertEqual(Path(payload["executable"]).resolve(), opencode.resolve())
        self.assertNotIn("trusted-bin", Path(payload["executable"]).parts)
        self.assertEqual(
            opencode_before,
            (
                opencode.read_bytes(),
                stat.S_IMODE(opencode.stat().st_mode),
                opencode.stat().st_ino,
            ),
        )
        self.assertEqual(payload["argv"], ["agent", "list"])
        self.assertIsNone(payload["ambientSecret"])
        self.assertEqual("true", payload["environment"]["OPENCODE_PURE"])
        self.assertFalse(Path(payload["config"]).exists())

    def test_cloud_profile_never_adds_direct_any_host_provider_port(self) -> None:
        self.make_bundle()
        self.install()
        cplt = self.make_fake_client("cplt")
        self.make_fake_client("opencode")
        capture = self.root / "cloud-capture.json"
        cplt_config = self.root / "normal-cplt.toml"
        cplt_config.write_text(
            "[proxy]\nupstream = 'http://corporate.example:8080'\n",
            encoding="utf-8",
        )

        result, _, stderr = self.run_cli(
            "launch",
            "--home",
            str(self.home),
            "--runtime-root",
            str(self.runtime),
            "--profile",
            "cloud-open-weight",
            "--provider-domain",
            "inference.example.org",
            "--provider-port",
            "443",
            "--pass-env",
            "FAKE_CAPTURE",
            "--cplt",
            str(cplt),
            environment=self.client_environment(
                FAKE_CAPTURE=str(capture), CPLT_CONFIG=str(cplt_config)
            ),
        )

        self.assertEqual(result, 0, stderr)
        payload = json.loads(capture.read_text(encoding="utf-8"))
        self.assertEqual(payload["cpltConfig"], str(cplt_config))
        argv = payload["argv"]
        self.assertNotIn("--allow-port", argv)
        self.assertNotIn("--allow-private-domain", argv)

        result, _, stderr = self.run_cli(
            "launch",
            "--home",
            str(self.home),
            "--runtime-root",
            str(self.runtime),
            "--profile",
            "cloud-open-weight",
            "--provider-domain",
            "inference.example.org",
            "--provider-port",
            "8443",
            "--cplt",
            str(cplt),
            environment=self.client_environment(CPLT_CONFIG=str(cplt_config)),
        )
        self.assertEqual(2, result)
        self.assertIn("direct egress to every host", stderr)

    def test_normal_profile_rejects_ambient_secret_passthrough(self) -> None:
        self.make_bundle()
        self.install()
        config = self.root / "inherit-env-cplt.toml"
        config.write_text("[sandbox]\ninherit_env = true\n", encoding="utf-8")
        capture = self.root / "must-not-exist.json"

        result, _, stderr = self.run_cli(
            "launch",
            "--home",
            str(self.home),
            "--runtime-root",
            str(self.runtime),
            "--profile",
            "local",
            "--local-port",
            "1234",
            "--cplt",
            str(self.root / "must-not-run"),
            environment={
                "CPLT_CONFIG": str(config),
                "AMBIENT_SECRET": "must-not-leak",
                "FAKE_CAPTURE": str(capture),
            },
        )

        self.assertEqual(result, 2)
        self.assertIn("inherit_env=true is forbidden", stderr)
        self.assertFalse(capture.exists())

    def test_normal_profile_rejects_disabled_proxy_guards(self) -> None:
        self.make_bundle()
        self.install()
        for key in ("default_allowlist", "enabled", "forced"):
            with self.subTest(key=key):
                config = self.root / f"disabled-{key}.toml"
                config.write_text(f"[proxy]\n{key} = false\n", encoding="utf-8")
                result, _, stderr = self.run_cli(
                    "launch",
                    "--home",
                    str(self.home),
                    "--runtime-root",
                    str(self.runtime),
                    "--profile",
                    "local",
                    "--local-port",
                    "1234",
                    "--cplt",
                    str(self.root / "must-not-run"),
                    environment={"CPLT_CONFIG": str(config)},
                )

                self.assertEqual(result, 2)
                self.assertIn(f"proxy.{key}=false", stderr)

    def test_cplt_launch_rejects_user_write_policy_covering_lifecycle_home(self) -> None:
        self.make_bundle()
        self.install()
        config = self.root / "unsafe-cplt.toml"
        config.write_text(
            f"[allow]\nwrite = [{str(self.home.parent)!r}]\n",
            encoding="utf-8",
        )

        result, _, stderr = self.run_cli(
            "launch",
            "--home",
            str(self.home),
            "--runtime-root",
            str(self.runtime),
            "--profile",
            "local",
            "--local-port",
            "1234",
            "--cplt",
            str(self.root / "must-not-run"),
            environment={"CPLT_CONFIG": str(config)},
        )

        self.assertEqual(result, 2)
        self.assertIn("write policy overlaps", stderr)

    def test_cplt_write_overlap_uses_portable_case_and_unicode_identity(self) -> None:
        self.assertTrue(
            MANAGER._paths_overlap(
                Path("/private/tmp/CaseHome/runtime"),
                Path("/PRIVATE/TMP/casehome"),
            )
        )
        self.assertTrue(
            MANAGER._paths_overlap(
                Path("/private/tmp/CAFE\u0301/runtime"),
                Path("/private/tmp/caf\xe9"),
            )
        )

        self.make_bundle()
        self.install()
        config = self.root / "case-alias-cplt.toml"
        config.write_text(
            f"[allow]\nwrite = [{str(self.home.parent).swapcase()!r}]\n",
            encoding="utf-8",
        )
        result, _, stderr = self.run_cli(
            "launch",
            "--home",
            str(self.home),
            "--runtime-root",
            str(self.runtime),
            "--profile",
            "local",
            "--local-port",
            "1234",
            "--cplt",
            str(self.root / "must-not-run"),
            environment={"CPLT_CONFIG": str(config)},
        )

        self.assertEqual(result, 2)
        self.assertIn("write policy overlaps", stderr)

    def test_cplt_host_output_cannot_overwrite_lifecycle_state(self) -> None:
        self.make_bundle()
        self.install()
        for section, key in (("proxy", "log_file"), ("audit", "destination")):
            with self.subTest(section=section, key=key):
                config = self.root / f"unsafe-{section}.toml"
                config.write_text(
                    f"[{section}]\n{key} = {str(self.home / 'state.json')!r}\n",
                    encoding="utf-8",
                )
                result, _, stderr = self.run_cli(
                    "launch",
                    "--home",
                    str(self.home),
                    "--runtime-root",
                    str(self.runtime),
                    "--profile",
                    "local",
                    "--local-port",
                    "1234",
                    "--cplt",
                    str(self.root / "must-not-run"),
                    environment={"CPLT_CONFIG": str(config)},
                )
                self.assertEqual(result, 2)
                self.assertIn("host output path overlaps", stderr)

    def test_local_only_is_cplt_only_and_pins_the_audited_network_contract(self) -> None:
        self.make_bundle()
        self.install()
        cplt = self.make_fake_client("cplt")
        self.make_fake_client("opencode")
        capture = self.root / "local-only-capture.json"
        environment = self.client_environment(
            FAKE_CAPTURE=str(capture),
            CPLT_CONFIG=str(self.root / "no-cplt-config.toml"),
        )

        with mock.patch.object(MANAGER, "_check_local_only_platform"), mock.patch.object(
            MANAGER,
            "_snapshot_opencode_auth",
            side_effect=AssertionError("auth-free local-only must not read auth.json"),
        ) as snapshot:
            result, _, stderr = self.run_cli(
                "launch",
                "--home",
                str(self.home),
                "--runtime-root",
                str(self.runtime),
                "--profile",
                "local-only",
                "--local-port",
                "1234",
                "--pass-env",
                "FAKE_CAPTURE",
                "--cplt",
                str(cplt),
                environment=environment,
            )
        snapshot.assert_not_called()

        self.assertEqual(result, 0, stderr)
        payload = json.loads(capture.read_text(encoding="utf-8"))
        argv = payload["argv"]
        self.assertIn("--with-proxy", argv)
        self.assertIn("--proxy-forced", argv)
        self.assertIn("--allowed-domains", argv)
        self.assertIn("--blocked-domains", argv)
        self.assertIn("--preset", argv)
        self.assertIn("strict", argv)
        self.assertIn("--no-allow-localhost-any", argv)
        self.assertIn("--no-allow-env-files", argv)
        self.assertIn("--no-allow-tmp-exec", argv)
        self.assertIn("--no-allow-docker", argv)
        self.assertIn("--no-allow-lifecycle-scripts", argv)
        self.assertNotEqual(payload["cpltConfig"], environment["CPLT_CONFIG"])
        self.assertFalse(Path(payload["cpltConfig"]).exists())
        self.assertIn(
            "grillmester-local-only.invalid\n",
            payload["policyFiles"]["--allowed-domains"],
        )
        self.assertIn(
            "grillmester-local-only.invalid\n",
            payload["policyFiles"]["--blocked-domains"],
        )
        expected_environment = {
            "OPENCODE_CONFIG_DIR": payload["config"],
            "OPENCODE_DISABLE_AUTOUPDATE": "true",
            "OPENCODE_PURE": "true",
            "OPENCODE_DISABLE_MODELS_FETCH": "true",
            "OPENCODE_DISABLE_LSP_DOWNLOAD": "true",
            "OPENCODE_DISABLE_DEFAULT_PLUGINS": "true",
            "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT": "true",
            "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "true",
            "OPENCODE_DISABLE_EXTERNAL_SKILLS": "true",
            "OPENCODE_DISABLE_SHARE": "true",
            "OPENCODE_AUTO_SHARE": "false",
            "OPENCODE_ENABLE_EXA": "false",
            "OPENCODE_EXPERIMENTAL": "false",
            "OPENCODE_EXPERIMENTAL_CODE_MODE": "false",
        }
        for name, value in expected_environment.items():
            self.assertEqual(payload["environment"][name], value)
        self.assertIn('"permission":{"*":"ask"}', payload["environment"]["OPENCODE_CONFIG_CONTENT"])
        self.assertTrue(payload["environment"]["OPENCODE_MODELS_PATH"].endswith("/policy/models.json"))
        for variable in payload["environment"]:
            if variable != "PATH":
                self.assertIn(variable, argv)

        result, _, stderr = self.run_cli(
            "launch",
            "--home",
            str(self.home),
            "--runtime-root",
            str(self.runtime),
            "--profile",
            "local-only",
            "--local-port",
            "1234",
            "--direct",
            "--opencode",
            str(self.root / "does-not-run"),
        )
        self.assertEqual(result, 2)
        self.assertIn("cannot enforce local-only", stderr)

    def test_local_only_fails_closed_off_macos(self) -> None:
        self.make_bundle()
        self.install()
        with mock.patch.object(MANAGER.sys, "platform", "linux"):
            result, _, stderr = self.run_cli(
                "launch",
                "--home",
                str(self.home),
                "--runtime-root",
                str(self.runtime),
                "--profile",
                "local-only",
                "--local-port",
                "1234",
                "--cplt",
                str(self.root / "must-not-run"),
            )

        self.assertEqual(result, 2)
        self.assertIn("requires macOS Seatbelt", stderr)

    @unittest.skipUnless(sys.platform == "darwin", "macOS manager contract")
    def test_macos_local_only_manager_builds_launch_without_live_clients(self) -> None:
        self.make_bundle()
        self.install()
        cplt = self.make_fake_client("cplt")
        opencode = self.make_fake_client("opencode")
        consumer = self.root / "macos-consumer"
        consumer.mkdir()
        calls: list[tuple[list[str], dict[str, object]]] = []

        def fake_run(command: list[str], **kwargs: object) -> object:
            argv = [str(value) for value in command]
            calls.append((argv, dict(kwargs)))
            if argv[0] == "git":
                return MANAGER.subprocess.CompletedProcess(argv, 1, "", "")
            if argv[-1] == "--version":
                output = (
                    "cplt 2026.08.17-062831-1008a92\n"
                    if argv == [argv[0], "--version"]
                    else "1.18.20\n"
                )
                return MANAGER.subprocess.CompletedProcess(argv, 0, output, "")
            return MANAGER.subprocess.CompletedProcess(argv, 0, "", "")

        previous = Path.cwd()
        try:
            os.chdir(consumer)
            with mock.patch.object(MANAGER.subprocess, "run", side_effect=fake_run):
                result, _, stderr = self.run_cli(
                    "launch",
                    "--home",
                    str(self.home),
                    "--runtime-root",
                    str(self.runtime),
                    "--profile",
                    "local-only",
                    "--local-port",
                    "1234",
                    "--cplt",
                    str(cplt),
                    "--opencode",
                    str(opencode),
                    environment=self.client_environment(),
                )
        finally:
            os.chdir(previous)

        self.assertEqual(result, 0, stderr)
        client_calls = [call for call in calls if call[0][0] != "git"]
        self.assertEqual(len(client_calls), 1)
        command, launch_options = client_calls[0]
        self.assertIn("--proxy-forced", command)
        self.assertIn("--no-allow-localhost-any", command)
        self.assertEqual(command[command.index("--allow-localhost") + 1], "1234")
        self.assertIn("--allowed-domains", command)
        self.assertIn("--blocked-domains", command)
        environment = launch_options["env"]
        self.assertIsInstance(environment, dict)
        assert isinstance(environment, dict)
        self.assertEqual(environment["OPENCODE_PURE"], "true")
        trusted_directory = Path(str(environment["PATH"]).split(os.pathsep)[0])
        self.assertEqual(trusted_directory.name, "trusted-bin")
        self.assertEqual(Path(command[0]).parent, trusted_directory)
        self.assertFalse(trusted_directory.exists(), "session must be cleaned up")

    def test_profile_inputs_fail_closed_before_starting_a_client(self) -> None:
        self.make_bundle()
        self.install()
        missing = self.root / "must-not-run"

        cases = [
            ("local", [], "local port"),
            ("local", ["--local-port", "1234", "--provider-domain", "x.dev"], "provider domain"),
            ("cloud-open-weight", [], "provider domain"),
            ("cloud-open-weight", ["--provider-domain", "https://bad.example/v1"], "bare domain"),
            ("hybrid", ["--local-port", "1234"], "provider domain"),
            ("hybrid", ["--provider-domain", "inference.example"], "local port"),
        ]
        for profile, extra, expected in cases:
            with self.subTest(profile=profile, extra=extra):
                result, _, stderr = self.run_cli(
                    "launch",
                    "--home",
                    str(self.home),
                    "--runtime-root",
                    str(self.runtime),
                    "--profile",
                    profile,
                    "--cplt",
                    str(missing),
                    *extra,
                )
                self.assertEqual(result, 2)
                self.assertIn(expected, stderr.lower())

    def test_cloud_provider_rejects_ip_literals_and_localhost_names(self) -> None:
        self.make_bundle()
        self.install()
        missing = self.root / "must-not-run"
        cases = (
            ("127.0.0.1", "ip literal"),
            ("127.1", "ip literal"),
            ("::1", "ip literal"),
            ("[::1]", "ip literal"),
            ("localhost", "localhost"),
            ("api.localhost", "localhost"),
        )

        for domain, expected in cases:
            with self.subTest(domain=domain):
                result, _, stderr = self.run_cli(
                    "launch",
                    "--home",
                    str(self.home),
                    "--runtime-root",
                    str(self.runtime),
                    "--profile",
                    "cloud-open-weight",
                    "--provider-domain",
                    domain,
                    "--cplt",
                    str(missing),
                )

                self.assertEqual(result, 2)
                self.assertIn(expected, stderr.lower())
                self.assertFalse(missing.exists())

    def test_cloud_provider_rejects_private_domain_relaxation(self) -> None:
        self.make_bundle()
        self.install()
        missing = self.root / "must-not-run"

        result, _, stderr = self.run_cli(
            "launch",
            "--home",
            str(self.home),
            "--runtime-root",
            str(self.runtime),
            "--profile",
            "cloud-open-weight",
            "--provider-domain",
            "inference.internal.example",
            "--private-provider-domain",
            "inference.internal.example",
            "--cplt",
            str(missing),
        )

        self.assertEqual(result, 2)
        self.assertIn("public provider hostnames", stderr.lower())
        self.assertIn("hybrid", stderr.lower())
        self.assertFalse(missing.exists())

    def test_launch_rejects_runtime_outside_home_and_home_inside_consumer(self) -> None:
        self.make_bundle()
        self.install()

        ambient_cache = self.root / "ambient-cache"
        result, _, stderr = self.run_cli(
            "install",
            "--source",
            str(self.source),
            "--home",
            str(ambient_cache / "grillmester"),
            environment={"XDG_CACHE_HOME": str(ambient_cache)},
        )
        self.assertEqual(result, 2)
        self.assertIn("ambient cplt/opencode write area", stderr.lower())

        result, _, stderr = self.run_cli(
            "launch",
            "--home",
            str(self.home),
            "--runtime-root",
            str(self.root / "cache"),
            "--profile",
            "local",
            "--local-port",
            "1234",
            "--direct",
            "--opencode",
            str(self.root / "must-not-run"),
        )
        self.assertEqual(result, 2)
        self.assertIn("runtime root must be inside", stderr)

        consumer = self.root / "consumer-project"
        consumer.mkdir()
        (consumer / ".git").mkdir()
        nested_home = consumer / ".grillmester"
        previous_cwd = Path.cwd()
        try:
            os.chdir(consumer)
            result, _, stderr = self.run_cli(
                "launch",
                "--home",
                str(nested_home),
                "--runtime-root",
                str(nested_home / "runtime"),
                "--profile",
                "local",
                "--local-port",
                "1234",
                "--direct",
                "--opencode",
                str(self.root / "must-not-run"),
            )
        finally:
            os.chdir(previous_cwd)
        self.assertEqual(result, 2)
        self.assertIn("writable project directory", stderr)

    def test_missing_or_unowned_lifecycle_home_is_not_created_or_chmodded(self) -> None:
        missing = self.root / "missing-home"
        result, _, stderr = self.run_cli("rollback", "--home", str(missing))
        self.assertEqual(result, 2)
        self.assertIn("existing lifecycle home", stderr.lower())
        self.assertFalse(missing.exists())

        arbitrary = self.root / "arbitrary-home"
        arbitrary.mkdir(mode=0o755)
        before = stat.S_IMODE(arbitrary.stat().st_mode)
        result, _, stderr = self.run_cli(
            "launch",
            "--home",
            str(arbitrary),
            "--runtime-root",
            str(arbitrary / "runtime"),
            "--profile",
            "local",
            "--local-port",
            "1234",
            "--direct",
            "--opencode",
            str(self.root / "must-not-run"),
        )
        self.assertEqual(result, 2)
        self.assertIn("mode 0700", stderr.lower())
        self.assertEqual(stat.S_IMODE(arbitrary.stat().st_mode), before)
        self.assertFalse((arbitrary / ".lock").exists())

    def test_forged_home_cannot_hide_account_opencode_roots(self) -> None:
        self.make_bundle()
        forged = self.root / "forged-home"
        real_cache = self.account_home / ".cache"
        lifecycle = real_cache / "grillmester"

        result, _, stderr = self.run_cli(
            "install",
            "--source",
            str(self.source),
            "--home",
            str(lifecycle),
            environment={"HOME": str(forged)},
        )

        self.assertEqual(result, 2)
        self.assertIn("ambient cplt/opencode write area", stderr.lower())
        self.assertFalse(lifecycle.exists())

    def test_relative_explicit_xdg_root_is_rejected_before_writes(self) -> None:
        self.make_bundle()
        result, _, stderr = self.run_cli(
            "install",
            "--source",
            str(self.source),
            "--home",
            str(self.home),
            environment={"XDG_CACHE_HOME": "../relative-cache"},
        )
        self.assertEqual(result, 2)
        self.assertIn("xdg_cache_home must be absolute", stderr.lower())
        self.assertFalse(self.home.exists())

    def test_local_only_rejects_every_repo_proposal_and_ignores_global_config(self) -> None:
        self.make_bundle()
        self.install()
        cplt_config = self.root / "cplt.toml"
        cplt_config.write_text(
            "[sandbox]\ninherit_env = true\n[allow]\nwrite = ['/']\n",
            encoding="utf-8",
        )
        consumer = self.root / "repo-with-proposal"
        consumer.mkdir()
        (consumer / ".cplt.toml").write_text(
            "[propose.allow]\nlocalhost = [9999]\n",
            encoding="utf-8",
        )
        previous = Path.cwd()
        try:
            os.chdir(consumer)
            with mock.patch.object(MANAGER.sys, "platform", "darwin"):
                result, _, stderr = self.run_cli(
                    "launch",
                    "--home",
                    str(self.home),
                    "--runtime-root",
                    str(self.runtime),
                    "--profile",
                    "local-only",
                    "--local-port",
                    "1234",
                    "--cplt",
                    str(self.root / "must-not-run"),
                    environment={"CPLT_CONFIG": str(cplt_config)},
                )
        finally:
            os.chdir(previous)

        self.assertEqual(result, 2)
        self.assertIn("rejects every repository", stderr)

    def test_launch_rejects_inexact_opencode_and_cplt_versions(self) -> None:
        self.make_bundle()
        self.install()
        wrong_opencode = self.make_fake_client(
            "opencode", opencode_version="1.18.20-unreviewed"
        )

        result, _, stderr = self.run_cli(
            "launch",
            "--home",
            str(self.home),
            "--runtime-root",
            str(self.runtime),
            "--profile",
            "local",
            "--local-port",
            "1234",
            "--direct",
            "--opencode",
            str(wrong_opencode),
            environment={"FAKE_CAPTURE": str(self.root / "unused.json")},
        )
        self.assertEqual(result, 2)
        self.assertIn("OpenCode must be exactly '1.18.20'", stderr)

        self.make_fake_client("opencode")
        wrong_cplt = self.make_fake_client(
            "cplt",
            cplt_version="cplt 2026.08.17-062831-1008a92-unreviewed",
        )
        result, _, stderr = self.run_cli(
            "launch",
            "--home",
            str(self.home),
            "--runtime-root",
            str(self.runtime),
            "--profile",
            "hybrid",
            "--local-port",
            "1234",
            "--provider-domain",
            "inference.example.org",
            "--cplt",
            str(wrong_cplt),
            environment=self.client_environment(
                FAKE_CAPTURE=str(self.root / "unused.json")
            ),
        )
        self.assertEqual(result, 2)
        self.assertIn(
            "cplt must be exactly 'cplt 2026.08.17-062831-1008a92'", stderr
        )

        self.make_fake_client(
            "opencode", opencode_version="1.18.20-unreviewed"
        )
        self.make_fake_client(
            "cplt", opencode_version="1.18.20-unreviewed"
        )
        result, _, stderr = self.run_cli(
            "launch",
            "--home",
            str(self.home),
            "--runtime-root",
            str(self.runtime),
            "--profile",
            "local",
            "--local-port",
            "1234",
            "--cplt",
            str(self.root / "bin/cplt"),
            environment=self.client_environment(
                FAKE_CAPTURE=str(self.root / "unused.json")
            ),
        )
        self.assertEqual(result, 2)
        self.assertIn("OpenCode must be exactly '1.18.20' inside cplt", stderr)
        self.assertNotIn("1.18.20-unreviewed", stderr)

    def test_untrusted_cplt_checksum_is_rejected_without_execution(self) -> None:
        marker = self.root / "host-marker"
        executable = self.root / "untrusted-cplt"
        executable.write_text(
            f"#!/bin/sh\ntouch {str(marker)!r}\necho 'cplt 2026.08.17-062831-1008a92'\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)
        session = self.root / "session"
        session.mkdir()

        with self.assertRaisesRegex(MANAGER.LifecycleError, "checksum"):
            MANAGER._stage_pinned_cplt_binary(executable, session)

        self.assertFalse(marker.exists())
        self.assertFalse((session / "trusted-bin").exists())

    def test_platform_digest_selection_is_exact_architecture(self) -> None:
        with mock.patch.object(MANAGER.sys, "platform", "darwin"), mock.patch.object(
            MANAGER.platform, "machine", return_value="arm64"
        ):
            self.assertEqual(
                MANAGER._expected_cplt_binary_digests(),
                frozenset(
                    {
                        MANAGER.PINNED_CPLT_BINARY_SHA256[("darwin", "arm64")]
                    }
                ),
            )
            self.assertEqual(
                MANAGER._expected_opencode_binary_digests(),
                frozenset(
                    {
                        MANAGER.PINNED_OPENCODE_BINARY_SHA256[
                            ("darwin", "arm64", "default")
                        ]
                    }
                ),
            )

        with mock.patch.object(MANAGER.sys, "platform", "linux"), mock.patch.object(
            MANAGER.platform, "machine", return_value="AMD64"
        ):
            self.assertEqual(
                MANAGER._expected_cplt_binary_digests(),
                frozenset(
                    {
                        MANAGER.PINNED_CPLT_BINARY_SHA256[("linux", "x86_64")]
                    }
                ),
            )
            self.assertEqual(len(MANAGER._expected_opencode_binary_digests()), 2)

        with mock.patch.object(MANAGER.platform, "machine", return_value="ppc64"):
            with self.assertRaisesRegex(MANAGER.LifecycleError, "architecture"):
                MANAGER._expected_cplt_binary_digests()

        with mock.patch.object(MANAGER.sys, "platform", "linux"), mock.patch.object(
            MANAGER.platform, "machine", return_value="x86_64"
        ), mock.patch.object(
            MANAGER.platform, "libc_ver", return_value=("musl", "1.2.5")
        ), self.assertRaisesRegex(MANAGER.LifecycleError, "glibc.*musl"):
            MANAGER._require_managed_cplt_libc()

        with mock.patch.object(MANAGER.sys, "platform", "linux"), mock.patch.object(
            MANAGER.platform, "machine", return_value="x86_64"
        ), mock.patch.object(
            MANAGER.platform, "libc_ver", return_value=("glibc", "2.39")
        ):
            MANAGER._require_managed_cplt_libc()

    def test_unpinned_opencode_is_rejected_without_execution(self) -> None:
        marker = self.root / "host-marker"
        executable = self.root / "untrusted-opencode"
        executable.write_text(
            f"#!/bin/sh\ntouch {str(marker)!r}\necho 1.18.20\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)
        session = self.root / "session"
        session.mkdir()

        with self.assertRaisesRegex(MANAGER.LifecycleError, "checksum"):
            MANAGER._stage_opencode_binary(executable, session)

        self.assertFalse(marker.exists())
        self.assertFalse((session / "trusted-bin").exists())

    def test_cplt_rejects_opencode_from_its_writable_project(self) -> None:
        self.make_bundle()
        self.install()
        consumer = self.root / "consumer-with-client"
        consumer.mkdir()
        (consumer / ".git").mkdir()
        opencode = consumer / "opencode"
        opencode.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
        opencode.chmod(0o755)
        previous = Path.cwd()
        try:
            os.chdir(consumer)
            result, _, stderr = self.run_cli(
                "launch",
                "--home",
                str(self.home),
                "--runtime-root",
                str(self.runtime),
                "--profile",
                "local",
                "--local-port",
                "1234",
                "--opencode",
                str(opencode),
                "--cplt",
                str(self.root / "must-not-run"),
            )
        finally:
            os.chdir(previous)

        self.assertEqual(result, 2)
        self.assertIn("writable project directory", stderr)

    def test_profiles_pin_the_complete_enforcement_contract(self) -> None:
        source_profiles = ROOT / "profiles/opencode"
        profile_root = self.root / "profiles"
        profile_root.mkdir()
        for source in source_profiles.glob("*.json"):
            (profile_root / source.name).write_bytes(source.read_bytes())

        local_path = profile_root / "local.json"
        local = json.loads(local_path.read_text(encoding="utf-8"))
        local["cpltRelease"] = "2026.08.17-062831-1008a92-unreviewed"
        local_path.write_text(json.dumps(local), encoding="utf-8")
        with self.assertRaisesRegex(MANAGER.LifecycleError, "must pin cplt"):
            MANAGER.load_profile("local", profile_root=profile_root)

        local = json.loads(
            (source_profiles / "local.json").read_text(encoding="utf-8")
        )
        local["environment"]["OPENCODE_CONFIG_CONTENT"] = (
            '{"autoupdate":false,"share":"manual"}'
        )
        local_path.write_text(json.dumps(local), encoding="utf-8")
        with self.assertRaisesRegex(
            MANAGER.LifecycleError, "invalid immutable environment overlay"
        ):
            MANAGER.load_profile("local", profile_root=profile_root)

        local_only_path = profile_root / "local-only.json"
        local_only = json.loads(local_only_path.read_text(encoding="utf-8"))
        local_only["blockedDomains"] = local_only["blockedDomains"][:-1]
        local_only_path.write_text(json.dumps(local_only), encoding="utf-8")
        with self.assertRaisesRegex(
            MANAGER.LifecycleError, "exactly match the audited cplt defaults"
        ):
            MANAGER.load_profile("local-only", profile_root=profile_root)

        local_only = json.loads(
            (source_profiles / "local-only.json").read_text(encoding="utf-8")
        )
        local_only["cpltPolicy"] = "strict"
        local_only.pop("allowedDomain")
        local_only.pop("blockedDomains")
        local_only_path.write_text(json.dumps(local_only), encoding="utf-8")
        with self.assertRaisesRegex(MANAGER.LifecycleError, "invalid policy shape"):
            MANAGER.load_profile("local-only", profile_root=profile_root)

    def test_managed_cplt_cli_pins_noninteractive_security_boundary(self) -> None:
        environment: dict[str, str] = {}
        inputs = MANAGER._resolve_runtime_inputs(
            "local",
            [1234],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            environment,
            profile_root=ROOT / "profiles/opencode",
        )
        policy = self.root / "policy"
        policy.mkdir()
        command = MANAGER._build_cplt_command(
            "/trusted/cplt",
            self.root / "config",
            self.root / "models.json",
            self.root / "opencode-home",
            policy,
            self.root / "consumer",
            inputs,
            ("run", "--agent", "grillmester"),
        )
        for flag in (
            "--yes",
            "--scratch-dir",
            "--deny-clipboard",
            "--no-audit",
            "--no-quiet",
            "--gh-guard",
            "--git-guard",
        ):
            self.assertIn(flag, command)

    def test_cplt_config_cannot_disable_scratch_or_strip_managed_env(self) -> None:
        with self.assertRaisesRegex(MANAGER.LifecycleError, "scratch"):
            MANAGER._validate_normal_cplt_configuration(
                {"sandbox": {"scratch_dir": False}}, label="global cplt config"
            )

        repo_config = {
            "deny": {
                "env": ["OPENCODE_MODELS_PATH", "OPENCODE_DISABLE_EXTERNAL_SKILLS"]
            }
        }
        with mock.patch.object(
            MANAGER, "_global_cplt_configuration", return_value=(None, self.root)
        ), mock.patch.object(
            MANAGER, "_effective_repo_cplt_configuration", return_value=repo_config
        ), self.assertRaisesRegex(MANAGER.LifecycleError, "deny.env"):
            MANAGER._check_cplt_stage_write_overlap(
                self.home, self.root / "consumer", {}
            )

        with mock.patch.object(
            MANAGER,
            "_global_cplt_configuration",
            return_value=({"deny": {"env": ["MODEL_PROVIDER_API_KEY"]}}, self.root),
        ), mock.patch.object(
            MANAGER, "_effective_repo_cplt_configuration", return_value=None
        ), self.assertRaisesRegex(MANAGER.LifecycleError, "MODEL_PROVIDER_API_KEY"):
            MANAGER._check_cplt_stage_write_overlap(
                self.home,
                self.root / "consumer",
                {},
                protected_environment=("MODEL_PROVIDER_API_KEY",),
            )

        with mock.patch.object(
            MANAGER,
            "_effective_repo_cplt_configuration",
            return_value={"deny": {"env": ["OPENCODE_DB"]}},
        ), self.assertRaisesRegex(MANAGER.LifecycleError, "OPENCODE_DB"):
            MANAGER._check_local_only_cplt_configuration(
                self.root / "consumer",
                {},
            )

    def test_cplt_configuration_snapshot_detects_live_config_changes(self) -> None:
        first_global = {"proxy": {"upstream": "http://proxy.example:8080"}}
        second_global = {"proxy": {"upstream": "http://other.example:8080"}}
        repo = {"deny": {"env": ["SECRET"]}}
        with mock.patch.object(
            MANAGER,
            "_global_cplt_configuration",
            side_effect=[(first_global, self.root), (second_global, self.root)],
        ), mock.patch.object(
            MANAGER, "_effective_repo_cplt_configuration", return_value=repo
        ):
            snapshot = MANAGER._cplt_configuration_snapshot(
                self.root / "consumer", {}
            )
            with self.assertRaisesRegex(
                MANAGER.LifecycleError, "cplt configuration changed"
            ):
                MANAGER._require_cplt_configuration_unchanged(
                    self.root / "consumer", {}, snapshot
                )

        first_global["proxy"]["upstream"] = "http://mutated.example:8080"
        self.assertEqual(
            "http://proxy.example:8080",
            snapshot[0]["proxy"]["upstream"],
            "snapshot must not alias the parsed configuration",
        )

    def test_cplt_deny_paths_cannot_hide_managed_project_instructions(self) -> None:
        consumer = self.root / "consumer"
        consumer.mkdir()
        instruction = consumer / "AGENTS.md"
        instruction.write_text("reviewed instructions\n", encoding="utf-8")

        with mock.patch.object(
            MANAGER,
            "_global_cplt_configuration",
            return_value=(
                {"deny": {"paths": [str(consumer)]}},
                self.root / "global-config",
            ),
        ), mock.patch.object(
            MANAGER, "_effective_repo_cplt_configuration", return_value=None
        ), self.assertRaisesRegex(MANAGER.LifecycleError, "hides.*instruction"):
            MANAGER._check_cplt_stage_write_overlap(
                self.home,
                consumer,
                {},
                instruction_paths=(str(instruction.resolve()),),
            )

        with mock.patch.object(
            MANAGER, "_global_cplt_configuration", return_value=(None, self.root)
        ), mock.patch.object(
            MANAGER,
            "_effective_repo_cplt_configuration",
            return_value={"deny": {"paths": ["AGENTS.md"]}},
        ), self.assertRaisesRegex(MANAGER.LifecycleError, "hides.*instruction"):
            MANAGER._check_cplt_stage_write_overlap(
                self.home,
                consumer,
                {},
                instruction_paths=(str(instruction.resolve()),),
            )

    def test_repository_cplt_schema_cannot_fail_open_and_drop_denies(self) -> None:
        invalid = (
            {"deny": {"paths": ["secrets"], "typo": True}},
            {"deny": {"env": ["INVALID-NAME"]}},
            {"deny": {"paths": ["../AGENTS.md"]}},
            {"deny": {"paths": ['safe\" ) (allow file-read*)']}},
            {"deny": {"env": ["SECRET"]}, "unknown": {}},
        )
        for config in invalid:
            with self.subTest(config=config), self.assertRaises(
                MANAGER.LifecycleError
            ):
                MANAGER._validate_repo_cplt_configuration(config)

        valid = {"deny": {"env": ["SECRET_1"], "paths": ["AGENTS.md"]}}
        self.assertIs(valid, MANAGER._validate_repo_cplt_configuration(valid))

    def test_managed_script_bootstrap_requires_isolated_python(self) -> None:
        unsafe_flags = types.SimpleNamespace(isolated=0, no_site=0)
        with mock.patch.object(
            MANAGER.sys, "flags", unsafe_flags
        ), self.assertRaisesRegex(MANAGER.LifecycleError, "-I -S"):
            MANAGER._require_isolated_python()

        isolated_flags = types.SimpleNamespace(isolated=1, no_site=1)
        with mock.patch.object(MANAGER.sys, "flags", isolated_flags):
            MANAGER._require_isolated_python()

    def test_managed_auth_snapshot_rejects_remote_and_malformed_entries(self) -> None:
        auth_path = self.account_home / ".local/share/opencode/auth.json"
        auth_path.parent.mkdir(parents=True)
        auth_path.write_text(
            json.dumps(
                {
                    "local-provider": {
                        "type": "api",
                        "key": "secret",
                        "metadata": {"tenant": "reviewed"},
                    },
                    "oauth-provider": {
                        "type": "oauth",
                        "refresh": "refresh",
                        "access": "access",
                        "expires": 1,
                        "accountId": "account",
                    },
                }
            ),
            encoding="utf-8",
        )
        auth_path.chmod(0o600)
        with mock.patch.object(
            MANAGER, "_account_home", return_value=self.account_home
        ):
            serialized = MANAGER._snapshot_opencode_auth({})
            snapshot = json.loads(serialized)
        self.assertEqual("secret", snapshot["local-provider"]["key"])
        self.assertEqual("oauth", snapshot["oauth-provider"]["type"])
        self.assertEqual(
            {"local-provider": {"type": "api", "key": "secret"}},
            json.loads(
                MANAGER._select_opencode_auth_for_resolved_providers(
                    serialized,
                    {
                        "provider": {
                            "local-provider": {"npm": "safe"},
                            "oauth-provider": {"npm": "safe"},
                        }
                    },
                    ["local-provider"],
                )
            ),
        )
        self.assertNotIn(
            "reviewed",
            MANAGER._select_opencode_auth_for_resolved_providers(
                serialized,
                {"provider": {"local-provider": {"npm": "safe"}}},
                ["local-provider"],
            ),
        )
        with self.assertRaisesRegex(MANAGER.LifecycleError, "one credential source"):
            MANAGER._select_opencode_auth_for_resolved_providers(
                serialized,
                {
                    "provider": {
                        "local-provider": {
                            "npm": "safe",
                            "options": {"apiKey": "{env:PROVIDER_KEY}"},
                        }
                    }
                },
                ["local-provider"],
            )
        self.assertEqual(
            "{}",
            MANAGER._select_opencode_auth_for_resolved_providers(
                serialized,
                {
                    "provider": {
                        "local-provider": {"npm": "safe"},
                        "oauth-provider": {"npm": "safe"},
                    }
                },
                [],
            ),
        )
        with self.assertRaisesRegex(MANAGER.LifecycleError, "OAuth"):
            MANAGER._select_opencode_auth_for_resolved_providers(
                serialized,
                {"provider": {"oauth-provider": {"npm": "safe"}}},
                ["oauth-provider"],
            )

        cases = (
            {
                "https://enterprise.example": {
                    "type": "wellknown",
                    "key": "TOKEN",
                    "token": "secret",
                }
            },
            {"provider": {"type": "unknown", "key": "secret"}},
            {"provider": {"type": "api", "key": 7}},
            {"provider": {"type": "oauth", "refresh": "r", "access": "a", "expires": -1}},
        )
        for value in cases:
            with self.subTest(value=value):
                auth_path.write_text(json.dumps(value), encoding="utf-8")
                with mock.patch.object(
                    MANAGER, "_account_home", return_value=self.account_home
                ):
                    candidate = MANAGER._snapshot_opencode_auth({})
                self.assertEqual(
                    "{}",
                    MANAGER._select_opencode_auth_for_resolved_providers(
                        candidate, {"provider": {}}, []
                    ),
                )
                selected_id = next(iter(value))
                with self.assertRaises(MANAGER.LifecycleError):
                    MANAGER._select_opencode_auth_for_resolved_providers(
                        candidate,
                        {"provider": {selected_id: {}}},
                        [selected_id],
                    )

        with self.assertRaisesRegex(MANAGER.LifecycleError, "local-only.*forbids"):
            MANAGER._resolve_runtime_inputs(
                "local-only",
                [1234],
                [],
                [],
                [],
                [],
                ["local-provider"],
                [],
                [],
                [],
                {},
                profile_root=ROOT / "profiles/opencode",
            )

        with self.assertRaisesRegex(MANAGER.LifecycleError, "owned by"):
            MANAGER._snapshot_opencode_auth(
                {"OPENCODE_AUTH_CONTENT": '{"provider":{}}'}
            )

    def test_managed_provider_selection_is_explicit_secret_safe_and_route_bound(
        self,
    ) -> None:
        environment = {"MODEL_PROVIDER_API_KEY": "selected-secret"}
        inputs = MANAGER._resolve_runtime_inputs(
            "local",
            [1234],
            [],
            [],
            [],
            ["MODEL_PROVIDER_API_KEY"],
            [],
            ["local-provider"],
            ["local-provider=http://127.0.0.1:1234/v1"],
            ["local-provider/model"],
            environment,
            profile_root=ROOT / "profiles/opencode",
        )
        resolved = {
            "provider": {
                "local-provider": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "provider-file-secret-sentinel",
                    "options": {
                        "baseURL": "http://127.0.0.1:1234/v1",
                        "apiKey": "selected-secret",
                    },
                    "models": {
                        "model": {
                            "name": "model-file-secret-sentinel",
                            "tool_call": True,
                            "modalities": {"input": ["text"], "output": ["text"]},
                            "limit": {"context": 32768, "output": 8192},
                        }
                    },
                },
                "unrelated-remote": {
                    "npm": "@ai-sdk/openai-compatible",
                    "options": {
                        "baseURL": "https://remote.example/v1",
                        "apiKey": "unrelated-secret",
                    },
                    "models": {"model": {}},
                },
            }
        }
        filtered = MANAGER._select_resolved_providers(
            resolved, inputs=inputs, environment=environment
        )
        self.assertEqual(["local-provider"], list(filtered["provider"]))
        serialized = json.dumps(filtered, sort_keys=True)
        self.assertNotIn("unrelated", serialized)
        self.assertNotIn("selected-secret", serialized)
        self.assertNotIn("file-secret-sentinel", serialized)
        self.assertEqual(
            "{env:MODEL_PROVIDER_API_KEY}",
            filtered["provider"]["local-provider"]["options"]["apiKey"],
        )
        self.assertEqual(
            {"context": 32768, "output": 8192},
            filtered["provider"]["local-provider"]["models"]["model"]["limit"],
        )

        expanded = json.loads(json.dumps(filtered))
        expanded["provider"]["local-provider"]["options"]["apiKey"] = (
            "selected-secret"
        )
        normalized = MANAGER._normalize_resolved_provider_credentials(
            expanded, filtered["provider"], environment
        )
        self.assertEqual(filtered["provider"], normalized["provider"])
        wrong_expanded = json.loads(json.dumps(expanded))
        wrong_expanded["provider"]["local-provider"]["options"]["apiKey"] = (
            "credential-mismatch-sentinel"
        )
        with self.assertRaises(MANAGER.LifecycleError) as credential_failure:
            MANAGER._normalize_resolved_provider_credentials(
                wrong_expanded, filtered["provider"], environment
            )
        credential_error = str(credential_failure.exception)
        self.assertNotIn("credential-mismatch-sentinel", credential_error)
        self.assertNotIn(
            hashlib.sha256(b"credential-mismatch-sentinel").hexdigest(),
            credential_error,
        )

        literal_secret = json.loads(json.dumps(resolved))
        literal_secret["provider"]["local-provider"]["options"]["apiKey"] = (
            "not-from-pass-env"
        )
        with self.assertRaisesRegex(MANAGER.LifecycleError, "--pass-env"):
            MANAGER._select_resolved_providers(
                literal_secret, inputs=inputs, environment=environment
            )

        wrong_route = json.loads(json.dumps(resolved))
        wrong_route["provider"]["local-provider"]["options"]["baseURL"] = (
            "https://remote.example/v1"
        )
        with self.assertRaises(MANAGER.LifecycleError) as route_failure:
            MANAGER._select_resolved_providers(
                wrong_route, inputs=inputs, environment=environment
            )
        self.assertNotIn("remote.example", str(route_failure.exception))

        wrong_model = json.loads(json.dumps(resolved))
        wrong_model["agent"] = {
            "kokk": {"model": "local-provider/file-secret-sentinel"}
        }
        with self.assertRaisesRegex(MANAGER.LifecycleError, "provider-model") as failure:
            MANAGER._select_resolved_providers(
                wrong_model, inputs=inputs, environment=environment
            )
        self.assertNotIn("file-secret-sentinel", str(failure.exception))

        secret_agent_id = "expanded-agent-key-secret-sentinel"
        secret_agent = json.loads(json.dumps(resolved))
        secret_agent["agent"] = {secret_agent_id: {"variant": "unsafe"}}
        with self.assertRaises(MANAGER.LifecycleError) as agent_failure:
            MANAGER._select_resolved_providers(
                secret_agent, inputs=inputs, environment=environment
            )
        agent_error = str(agent_failure.exception)
        self.assertNotIn(secret_agent_id, agent_error)
        self.assertNotIn(
            hashlib.sha256(secret_agent_id.encode()).hexdigest(), agent_error
        )

        missing_limits = json.loads(json.dumps(resolved))
        missing_limits["provider"]["local-provider"]["models"]["model"].pop(
            "limit"
        )
        with self.assertRaisesRegex(MANAGER.LifecycleError, "positive limit"):
            MANAGER._select_resolved_providers(
                missing_limits, inputs=inputs, environment=environment
            )

        secret_key = "expanded-config-key-secret-sentinel"
        unsupported_key = json.loads(json.dumps(resolved))
        unsupported_key["provider"]["local-provider"]["options"][secret_key] = True
        with self.assertRaises(MANAGER.LifecycleError) as key_failure:
            MANAGER._select_resolved_providers(
                unsupported_key, inputs=inputs, environment=environment
            )
        key_error = str(key_failure.exception)
        self.assertNotIn(secret_key, key_error)
        self.assertNotIn(hashlib.sha256(secret_key.encode()).hexdigest(), key_error)

    def test_untrusted_config_diagnostics_never_echo_keys_or_values(self) -> None:
        sentinel = "ambient-config-key-secret-sentinel"
        sentinel_digest = hashlib.sha256(sentinel.encode()).hexdigest()
        checks = (
            lambda: MANAGER._reject_declared_opencode_extensions(
                {"mcp": {sentinel: {"type": "remote"}}}, label="ambient config"
            ),
            lambda: MANAGER._reject_unsafe_provider_npm(
                {sentinel: {"npm": "file:///tmp/provider.js"}},
                label="ambient provider",
            ),
            lambda: MANAGER._reject_unsafe_provider_npm(
                {
                    "safe-provider": {
                        "npm": MANAGER.SAFE_PROVIDER_NPM,
                        "models": {
                            sentinel: {"provider": {"npm": "file:///tmp/model.js"}}
                        },
                    }
                },
                label="ambient provider",
            ),
            lambda: MANAGER._reject_executable_opencode_commands(
                {sentinel: {"command": ["/tmp/evil"]}}, label="ambient lsp"
            ),
            lambda: MANAGER._validated_opencode_auth_entry(
                "selected-provider", {"type": sentinel}
            ),
            lambda: MANAGER._parse_json_object(
                ('{"' + sentinel + '":1,"' + sentinel + '":2}').encode(),
                label="ambient JSON",
            ),
        )
        for check in checks:
            with self.subTest(check=check), self.assertRaises(
                MANAGER.LifecycleError
            ) as failure:
                check()
            chain = " | ".join(
                str(error)
                for error in (failure.exception, failure.exception.__cause__)
                if error is not None
            )
            self.assertNotIn(sentinel, chain)
            self.assertNotIn(sentinel_digest, chain)

    def test_profiles_do_not_select_a_provider_model_or_credentials(self) -> None:
        expected = {"local", "cloud-open-weight", "hybrid", "local-only"}
        profile_paths = sorted((ROOT / "profiles/opencode").glob("*.json"))
        profiles = [json.loads(path.read_text(encoding="utf-8")) for path in profile_paths]

        self.assertEqual({profile["id"] for profile in profiles}, expected)
        forbidden_keys = {"model", "provider", "credential", "apiKey", "token"}

        def walk(value: object) -> None:
            if isinstance(value, dict):
                self.assertTrue(forbidden_keys.isdisjoint(value))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        for profile in profiles:
            with self.subTest(profile=profile["id"]):
                walk(profile)

    def test_all_pinned_management_commands_are_forwarded_without_tui_agent_flags(
        self,
    ) -> None:
        for command in ("completion", "providers", "plug"):
            with self.subTest(command=command):
                arguments = [command, "example"]
                self.assertEqual(
                    MANAGER._opencode_client_arguments("grillmester", arguments),
                    arguments,
                )

    def test_caller_cannot_replace_profile_owned_pure_mode_with_cli_flags(self) -> None:
        for arguments in (
            ["--pure"],
            ["--no-pure"],
            ["run", "--pure=false", "prompt"],
            ["run", "--no-pure=true", "prompt"],
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(
                    MANAGER.LifecycleError, "controlled by the managed runtime profile"
                ):
                    MANAGER._opencode_client_arguments("grillmester", arguments)

    def test_managed_environment_scrubs_ambient_controls_and_pins_pwd(self) -> None:
        consumer = self.root / "consumer-env"
        consumer.mkdir()
        previous = Path.cwd()
        try:
            os.chdir(consumer)
            environment = {
                "PATH": os.environ.get("PATH", os.defpath),
                "PWD": str(self.root / "hostile-project"),
                "OPENCODE_TEST_HOME": str(self.root / "hostile-home"),
                "DYLD_INSERT_LIBRARIES": str(self.root / "inject.dylib"),
                "LD_PRELOAD": str(self.root / "inject.so"),
                "NODE_OPTIONS": "--require=/tmp/inject.js",
                "CPLT_CONFIG": str(self.root / "cplt.toml"),
                "TEST_PROVIDER_TOKEN": "credential",
            }
            inputs = MANAGER._resolve_runtime_inputs(
                "local",
                [1234],
                [],
                [],
                [],
                ["TEST_PROVIDER_TOKEN"],
                [],
                [],
                [],
                [],
                environment,
                profile_root=ROOT / "profiles/opencode",
            )
            with mock.patch.object(
                MANAGER, "_account_home", return_value=self.account_home
            ):
                child = MANAGER._runtime_environment(
                    environment,
                    inputs,
                    direct=False,
                    project_root=consumer,
                    home=self.home,
                    runtime_root=self.runtime,
                )
        finally:
            os.chdir(previous)

        self.assertEqual(str(consumer.resolve()), child["PWD"])
        self.assertEqual("credential", child["TEST_PROVIDER_TOKEN"])
        self.assertEqual(environment["CPLT_CONFIG"], child["CPLT_CONFIG"])
        for name in (
            "OPENCODE_TEST_HOME",
            "DYLD_INSERT_LIBRARIES",
            "LD_PRELOAD",
            "NODE_OPTIONS",
        ):
            self.assertNotIn(name, child)

        forbidden = (
            "OPENCODE_TEST_HOME",
            "NODE_OPTIONS",
            "CPLT_UNSAFE",
            "__CPLT_OVERRIDE",
            "Npm_Config_Ignore_Scripts",
            "YARN_ENABLE_SCRIPTS",
            "GIT_TERMINAL_PROMPT",
            "GIT_CONFIG_NOSYSTEM",
            "GIT_CONFIG_COUNT",
            "GIT_CONFIG_KEY_0",
            "GIT_CONFIG_VALUE_0",
            "GIT_DIR",
            "GIT_WORK_TREE",
            "DISABLE_AUTOUPDATER",
            "OPENSSL_CONF",
            "OPENSSL_MODULES",
            "OPENSSL_ENGINES",
            "GCONV_PATH",
            "BASH_ENV",
            "ENV",
            "ZDOTDIR",
            "PERL5OPT",
            "RUBYOPT",
            "LUA_INIT",
            "DOTNET_STARTUP_HOOKS",
            "CORECLR_ENABLE_PROFILING",
            "COR_PROFILER",
            "JAVA_TOOL_OPTIONS",
            "JDK_JAVA_OPTIONS",
            "_JAVA_OPTIONS",
            "MAVEN_OPTS",
            "GRADLE_OPTS",
            "GH_TOKEN",
            "GITHUB_TOKEN",
            "COPILOT_GITHUB_TOKEN",
            "COPILOT_PROVIDER_TOKEN",
        )
        for name in forbidden:
            with self.subTest(name=name), self.assertRaisesRegex(
                MANAGER.LifecycleError, "controlled by the launcher"
            ):
                MANAGER._resolve_runtime_inputs(
                    "local",
                    [1234],
                    [],
                    [],
                    [],
                    [name],
                    [],
                    [],
                    [],
                    [],
                    {name: "value"},
                    profile_root=ROOT / "profiles/opencode",
                )

    def test_managed_path_keeps_safe_toolchains_after_system_tools(self) -> None:
        consumer = self.root / "consumer-path"
        consumer.mkdir()
        safe_nvm = self.account_home / ".nvm/versions/node/v24/bin"
        safe_brew = self.root / "opt/homebrew/bin"
        project_bin = consumer / "bin"
        volatile_bin = self.root / "volatile/bin"
        for directory in (safe_nvm, safe_brew, project_bin, volatile_bin):
            directory.mkdir(parents=True)
        environment = {
            "PATH": os.pathsep.join(
                (
                    "",
                    "relative/bin",
                    str(project_bin),
                    str(volatile_bin),
                    str(safe_nvm),
                    str(safe_brew),
                )
            )
        }
        with mock.patch.object(
            MANAGER, "_account_home", return_value=self.account_home
        ), mock.patch.object(
            MANAGER,
            "_temporary_write_roots",
            return_value=(self.root / "volatile",),
        ):
            managed = MANAGER._managed_subprocess_path(
                None,
                environment=environment,
                project_root=consumer,
                home=self.home,
                runtime_root=self.runtime,
            ).split(os.pathsep)

        system = MANAGER._trusted_system_path().split(os.pathsep)
        self.assertEqual(system, managed[: len(system)])
        self.assertIn(str(safe_nvm.resolve()), managed)
        self.assertIn(str(safe_brew.resolve()), managed)
        self.assertNotIn(str(project_bin.resolve()), managed)
        self.assertNotIn(str(volatile_bin.resolve()), managed)
        self.assertNotIn("relative/bin", managed)

    def test_managed_environment_preserves_validated_tool_roots(self) -> None:
        consumer = self.root / "consumer-tools"
        consumer.mkdir()
        java_home = self.account_home / ".sdkman/candidates/java/current"
        go_path = self.account_home / "go"
        pnpm_home = self.account_home / "Library/pnpm"
        java_home.mkdir(parents=True)
        go_path.mkdir(parents=True)
        pnpm_home.mkdir(parents=True)
        environment = {
            "PATH": os.environ.get("PATH", os.defpath),
            "JAVA_HOME": str(java_home),
            "GOPATH": str(go_path),
            "PNPM_HOME": str(pnpm_home),
        }
        inputs = MANAGER._resolve_runtime_inputs(
            "local",
            [1234],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            environment,
            profile_root=ROOT / "profiles/opencode",
        )
        previous = Path.cwd()
        try:
            os.chdir(consumer)
            with mock.patch.object(
                MANAGER, "_account_home", return_value=self.account_home
            ), mock.patch.object(
                MANAGER,
                "_temporary_write_roots",
                return_value=(self.root / "volatile",),
            ):
                child = MANAGER._runtime_environment(
                    environment,
                    inputs,
                    direct=False,
                    project_root=consumer,
                    home=self.home,
                    runtime_root=self.runtime,
                )
        finally:
            os.chdir(previous)
        self.assertEqual(str(java_home), child["JAVA_HOME"])
        self.assertEqual(str(go_path), child["GOPATH"])
        self.assertNotIn("PNPM_HOME", child)

        with mock.patch.object(
            MANAGER, "_account_home", return_value=self.account_home
        ):
            mixed = MANAGER._validated_tool_environment(
                {"GOPATH": os.pathsep.join((str(go_path), str(pnpm_home)))},
                project_root=consumer,
                home=self.home,
                runtime_root=self.runtime,
            )
        self.assertNotIn(
            "GOPATH",
            mixed,
            "one unsafe list entry must drop the complete tool-root variable",
        )
        with self.assertRaisesRegex(MANAGER.LifecycleError, "must be absolute"):
            MANAGER._validated_tool_environment(
                {"JAVA_HOME": "relative-java"},
                project_root=consumer,
                home=self.home,
                runtime_root=self.runtime,
            )
        with self.assertRaisesRegex(MANAGER.LifecycleError, "empty tool path"):
            MANAGER._validated_tool_environment(
                {"GOPATH": str(go_path) + os.pathsep},
                project_root=consumer,
                home=self.home,
                runtime_root=self.runtime,
            )

        custom_gradle = self.root / "custom-gradle"
        custom_gradle.mkdir()
        with mock.patch.object(
            MANAGER, "_account_home", return_value=self.account_home
        ), self.assertRaisesRegex(MANAGER.LifecycleError, "not sandbox-granted"):
            MANAGER._validated_tool_environment(
                {"GRADLE_USER_HOME": str(custom_gradle)},
                project_root=consumer,
                home=self.home,
                runtime_root=self.runtime,
            )

        default_gradle = self.account_home / ".gradle"
        default_gradle.mkdir()
        with mock.patch.object(
            MANAGER, "_account_home", return_value=self.account_home
        ):
            validated = MANAGER._validated_tool_environment(
                {"GRADLE_USER_HOME": str(default_gradle)},
                project_root=consumer,
                home=self.home,
                runtime_root=self.runtime,
            )
        self.assertEqual(str(default_gradle), validated["GRADLE_USER_HOME"])

    def test_bounded_subprocess_capture_limits_both_streams(self) -> None:
        for stream in ("stdout", "stderr"):
            code = (
                "import sys; "
                + ("sys.stdout" if stream == "stdout" else "sys.stderr")
                + ".buffer.write(b'x' * 4096)"
            )
            with self.subTest(stream=stream), self.assertRaisesRegex(
                MANAGER.LifecycleError, "output exceeds"
            ):
                MANAGER._bounded_subprocess_output(
                    [sys.executable, "-I", "-c", code],
                    environment={},
                    label=f"{stream} flood",
                    max_bytes=64,
                    timeout_seconds=2,
                )

    def test_failed_json_probe_never_echoes_resolved_config_credentials(self) -> None:
        sentinel = "provider-secret-must-not-be-logged"
        sentinel_digest = hashlib.sha256(sentinel.encode()).hexdigest()
        with mock.patch.object(
            MANAGER, "_recheck_managed_command_executables"
        ), mock.patch.object(
            MANAGER,
            "_bounded_subprocess_output",
            return_value=(1, sentinel.encode(), sentinel.encode()),
        ), self.assertRaises(MANAGER.LifecycleError) as failure:
            MANAGER._run_cplt_json_probe(
                [
                    "/trusted/cplt",
                    "--allow-read",
                    "/old",
                    "--project-dir",
                    "/old-project",
                    "--",
                    "debug",
                ],
                config=self.root,
                preflight_project=self.root / "preflight-project",
                client_arguments=("debug", "config"),
                environment={},
                label="credential-bearing probe",
            )
        self.assertNotIn(sentinel, str(failure.exception))
        self.assertNotIn(sentinel_digest, str(failure.exception))
        self.assertIn("suppressed", str(failure.exception))
        self.assertNotIn(str(len(sentinel)), str(failure.exception))

        class SecretBearingComposerError(Exception):
            pass

        def fail_with_secret() -> None:
            raise SecretBearingComposerError(sentinel)

        composer = types.SimpleNamespace(
            PermissionCompositionError=SecretBearingComposerError,
            validate=fail_with_secret,
        )
        with self.assertRaises(MANAGER.LifecycleError) as opaque_failure:
            MANAGER._composer_call(composer, "validate")
        self.assertNotIn(sentinel, str(opaque_failure.exception))
        self.assertNotIn(sentinel_digest, str(opaque_failure.exception))

    def test_cplt_probes_replace_no_quiet_and_accept_startup_stderr(self) -> None:
        launch = [
            "/trusted/cplt",
            "--allow-read",
            "/old",
            "--project-dir",
            "/old-project",
            "--no-quiet",
            "--no-audit",
            "--",
            "run",
        ]
        with mock.patch.object(
            MANAGER, "_recheck_managed_command_executables"
        ), mock.patch.object(
            MANAGER,
            "_bounded_subprocess_output",
            return_value=(0, b'{"share":"disabled"}\n', b"[cplt] Starting OpenCode\n"),
        ) as capture:
            output = MANAGER._run_cplt_json_probe(
                launch,
                config=self.root,
                preflight_project=self.root,
                client_arguments=("debug", "config"),
                environment={},
                label="legitimate cplt probe",
                additional_read=self.root / "launch-config",
            )
        self.assertEqual(b'{"share":"disabled"}\n', output)
        command = capture.call_args.args[0]
        delimiter = command.index("--")
        self.assertIn("--quiet", command[:delimiter])
        self.assertNotIn("--no-quiet", command[:delimiter])
        self.assertEqual(command[:delimiter].count("--no-audit"), 1)
        self.assertIn(str(self.root / "launch-config"), command[:delimiter])
        self.assertEqual(command[:delimiter].count("--allow-read"), 2)
        self.assertEqual(
            command[command.index("--project-dir") + 1], str(self.root)
        )

        with mock.patch.object(
            MANAGER, "_recheck_managed_command_executables"
        ), mock.patch.object(
            MANAGER,
            "_bounded_subprocess_output",
            return_value=(0, b"1.18.20\n", b"[cplt] Starting OpenCode\n"),
        ) as version_capture:
            MANAGER._check_opencode_version_inside_cplt(
                launch,
                preflight_project=self.root,
                environment={},
            )
        version_command = version_capture.call_args.args[0]
        version_delimiter = version_command.index("--")
        self.assertIn("--quiet", version_command[:version_delimiter])
        self.assertNotIn("--no-quiet", version_command[:version_delimiter])
        self.assertEqual(
            version_command[:version_delimiter].count("--no-audit"), 1
        )

        with mock.patch.object(
            MANAGER, "_recheck_managed_command_executables"
        ), mock.patch.object(
            MANAGER,
            "_bounded_subprocess_output",
            return_value=(
                0,
                b"x" * MANAGER.PINNED_BUN_PIPE_FLUSH_BOUNDARY,
                b"",
            ),
        ), self.assertRaisesRegex(MANAGER.LifecycleError, "truncation boundary"):
            MANAGER._run_cplt_json_probe(
                launch,
                config=self.root,
                preflight_project=self.root,
                client_arguments=("debug", "config"),
                environment={},
                label="truncated cplt probe",
            )

        for client_arguments in (
            ("debug", "config"),
            ("debug", "agent", "grillmester"),
            ("debug", "skill"),
        ):
            with self.subTest(client_arguments=client_arguments), mock.patch.object(
                MANAGER, "_recheck_managed_command_executables"
            ), mock.patch.object(
                MANAGER,
                "_bounded_subprocess_output",
                return_value=(
                    0,
                    b"x" * (MANAGER.PINNED_BUN_PIPE_SAFE_OUTPUT_BUDGET + 1),
                    b"",
                ),
            ), self.assertRaisesRegex(MANAGER.LifecycleError, "48 KiB"):
                MANAGER._run_cplt_json_probe(
                    launch,
                    config=self.root,
                    preflight_project=self.root,
                    client_arguments=client_arguments,
                    environment={},
                    label="oversized cplt projection probe",
                )

    @unittest.skipUnless(hasattr(os, "killpg"), "POSIX process groups required")
    def test_bounded_subprocess_timeout_kills_descendants_and_reaps(self) -> None:
        marker = self.root / "descendant-survived"
        child = (
            "import pathlib,time; time.sleep(.8); "
            f"pathlib.Path({str(marker)!r}).write_text('survived')"
        )
        parent = (
            "import subprocess,sys; "
            f"subprocess.Popen([sys.executable,'-I','-c',{child!r}])"
        )
        started = time.monotonic()
        with self.assertRaisesRegex(MANAGER.LifecycleError, "timed out"):
            MANAGER._bounded_subprocess_output(
                [sys.executable, "-I", "-c", parent],
                environment={},
                label="process tree",
                timeout_seconds=0.1,
            )
        self.assertLess(time.monotonic() - started, 0.7)
        time.sleep(0.9)
        self.assertFalse(marker.exists())

    def test_process_group_termination_has_portable_fallback(self) -> None:
        process = mock.Mock(pid=1234)
        process.poll.return_value = None
        with mock.patch.object(
            MANAGER.os, "killpg", side_effect=OSError("unsupported"), create=True
        ):
            MANAGER._terminate_subprocess(process, process_group=True)
        process.kill.assert_called_once_with()
        process.wait.assert_called_once_with()

    def test_managed_arguments_keep_agent_cwd_and_ask_contract_fixed(self) -> None:
        commands = {"grillmester-review"}
        MANAGER._validate_managed_opencode_arguments(
            ["run", "--model", "local/model", "prompt"],
            command_ids=commands,
        )
        MANAGER._validate_managed_opencode_arguments(
            ["run", "--command=grillmester-review", "prompt"],
            command_ids=commands,
        )
        MANAGER._validate_managed_opencode_arguments(
            ["agent", "list"], command_ids=commands
        )
        for arguments in (
            ["--model", "local/model"],
            ["run", "--agent", "evil", "prompt"],
            ["run", "--dir=/tmp/other", "prompt"],
            ["run", "--auto", "prompt"],
            ["run", "--yolo", "prompt"],
            ["serve"],
            ["plugin", "install", "evil"],
            ["run", "--command=external", "prompt"],
            ["run", "--session", "ambient", "prompt"],
            ["run", "--session=ambient", "prompt"],
            ["run", "--continue", "prompt"],
            ["run", "-c", "prompt"],
            ["run", "--fork", "prompt"],
        ):
            with self.subTest(arguments=arguments), self.assertRaises(
                MANAGER.LifecycleError
            ):
                MANAGER._validate_managed_opencode_arguments(
                    arguments, command_ids=commands
                )

    def test_static_scan_rejects_code_and_loads_only_project_restrictions(self) -> None:
        consumer = self.root / "consumer-scan"
        consumer.mkdir()
        (consumer / "opencode.jsonc").write_text(
            """
            {
              // only these fields are imported while project discovery is off
              "permission": {"edit": "deny"},
              "agent": {"kokk": {"permission": {"bash": "deny"}}},
            }
            """,
            encoding="utf-8",
        )
        previous = Path.cwd()
        try:
            os.chdir(consumer)
            overlays = MANAGER._load_project_permission_overlays(consumer)
            self.assertEqual("deny", overlays[0]["permission"]["edit"])
            (consumer / "opencode.jsonc").write_text(
                '{"permission":{"bash":{"{file:/tmp/secret}":"deny"}}}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                MANAGER.LifecycleError, "substitution tokens"
            ):
                MANAGER._load_project_permission_overlays(consumer)
            tools = consumer / ".opencode/tools"
            tools.mkdir(parents=True)
            (tools / "evil.ts").write_text("throw new Error('must not load')\n")
            with mock.patch.object(
                MANAGER, "_account_home", return_value=self.account_home
            ), self.assertRaisesRegex(
                MANAGER.LifecycleError, "unmanaged project OpenCode entry"
            ):
                MANAGER._scan_managed_opencode_extensions(
                    consumer,
                    {"XDG_CONFIG_HOME": str(self.root / "xdg")},
                )
        finally:
            os.chdir(previous)

    def test_static_scan_accepts_only_restriction_only_project_config(self) -> None:
        consumer = self.root / "consumer-restrictions"
        consumer.mkdir()
        previous = Path.cwd()
        os.chdir(consumer)
        self.addCleanup(os.chdir, previous)
        xdg = self.root / "xdg-restrictions"
        environment = {"XDG_CONFIG_HOME": str(xdg)}
        safe = consumer / "opencode.jsonc"
        safe.write_text(
            '{"$schema":"https://opencode.ai/config.json",'
            '"permission":{"edit":"ask","bash":"deny"},'
            '"tools":{"write":false},'
            '"agent":{"kokk":{"permission":{"bash":"deny"},'
            '"tools":{"write":false}}}}\n',
            encoding="utf-8",
        )
        with mock.patch.object(
            MANAGER, "_account_home", return_value=self.account_home
        ):
            MANAGER._scan_managed_opencode_extensions(consumer, environment)

        unsafe_documents = (
            '{"share":"auto"}\n',
            '{"tools":{"write":true}}\n',
            '{"permission":{"edit":"allow"}}\n',
            '{"agent":{"kokk":{"model":"hostile/model"}}}\n',
        )
        for document in unsafe_documents:
            with self.subTest(document=document):
                safe.write_text(document, encoding="utf-8")
                with mock.patch.object(
                    MANAGER, "_account_home", return_value=self.account_home
                ), self.assertRaisesRegex(
                    MANAGER.LifecycleError, "restriction-only"
                ):
                    MANAGER._scan_managed_opencode_extensions(
                        consumer, environment
                    )

        safe.unlink()
        project_agents = consumer / ".opencode/agents"
        project_agents.mkdir(parents=True)
        (project_agents / "evil.md").write_text("# shadow\n", encoding="utf-8")
        with mock.patch.object(
            MANAGER, "_account_home", return_value=self.account_home
        ), self.assertRaisesRegex(
            MANAGER.LifecycleError, "unmanaged project OpenCode entry"
        ):
            MANAGER._scan_managed_opencode_extensions(consumer, environment)

    def test_static_scan_rejects_separately_loaded_ambient_tui_config(self) -> None:
        consumer = self.root / "consumer-tui"
        consumer.mkdir()
        xdg = self.root / "xdg"
        previous = Path.cwd()
        try:
            os.chdir(consumer)
            for tui in (
                xdg / "opencode/tui.jsonc",
                self.account_home / ".opencode/tui.json",
            ):
                with self.subTest(tui=tui):
                    tui.parent.mkdir(parents=True, exist_ok=True)
                    tui.write_text('{"theme":"system"}\n', encoding="utf-8")
                    with mock.patch.object(
                        MANAGER, "_account_home", return_value=self.account_home
                    ), self.assertRaisesRegex(
                        MANAGER.LifecycleError, "ambient OpenCode TUI"
                    ):
                        MANAGER._scan_managed_opencode_extensions(
                            consumer, {"XDG_CONFIG_HOME": str(xdg)}
                        )
                    tui.unlink()
        finally:
            os.chdir(previous)

    def test_opencode_jsonc_nesting_fails_closed_without_recursion_traceback(self) -> None:
        config = self.root / "deep-opencode.jsonc"
        payloads = (
            '{"nested":' + "[" * 41 + "0" + "]" * 41 + "}\n",
            '{"nested":' + "[" * 1200 + "0" + "]" * 1200 + "}\n",
        )
        for payload in payloads:
            with self.subTest(depth=payload.count("[")):
                config.write_text(payload, encoding="utf-8")
                with self.assertRaisesRegex(
                    MANAGER.LifecycleError, "too deeply nested"
                ):
                    MANAGER._parse_opencode_jsonc(config)

    def test_project_instruction_snapshot_preserves_agents_and_detects_changes(self) -> None:
        consumer = self.root / "consumer-instructions"
        nested = consumer / "nested"
        nested.mkdir(parents=True)
        root_agents = consumer / "AGENTS.md"
        nested_agents = nested / "AGENTS.md"
        root_agents.write_text("root instructions\n", encoding="utf-8")
        nested_agents.write_text("nested instructions\n", encoding="utf-8")
        previous = Path.cwd()
        try:
            os.chdir(nested)
            paths, before = MANAGER._project_instruction_snapshot(consumer)
            self.assertEqual(
                (str(nested_agents.resolve()), str(root_agents.resolve())),
                paths,
            )
            bundle = MANAGER.verify_bundle(
                ROOT / "targets/opencode-v1", immutable=False
            )
            config = self.root / "instruction-stage"
            MANAGER._copy_bundle(bundle, config, immutable=False)
            runtime_files = MANAGER._stage_opencode_runtime_support(config)
            staged_paths, staged_files = MANAGER._stage_project_instruction_snapshot(
                consumer,
                config,
                expected_paths=paths,
                expected_fingerprint=before,
            )
            sealed_files = {**runtime_files, **staged_files}
            MANAGER._seal_composed_runtime_config(config, bundle, sealed_files)
            sealed_fingerprint = MANAGER._validate_staged_config_extras(
                config, sealed_files
            )
            root_agents.write_text("changed instructions\n", encoding="utf-8")
            self.assertNotEqual(
                before, MANAGER._project_instruction_snapshot(consumer)[1]
            )
            self.assertEqual("nested instructions\n", Path(staged_paths[0]).read_text())
            self.assertEqual("root instructions\n", Path(staged_paths[1]).read_text())
            self.assertEqual(0o444, stat.S_IMODE(Path(staged_paths[0]).stat().st_mode))
            self.assertEqual(
                MANAGER.OPENCODE_RUNTIME_GITIGNORE,
                (config / ".gitignore").read_bytes(),
            )
            self.assertEqual(
                0o444, stat.S_IMODE((config / ".gitignore").stat().st_mode)
            )
            self.assertEqual(0o555, stat.S_IMODE(config.stat().st_mode))
            self.assertEqual(
                sealed_fingerprint,
                MANAGER._validate_staged_config_extras(config, sealed_files),
            )
        finally:
            os.chdir(previous)

    def test_bounded_config_probe_preserves_frontmatter_and_is_sealed(self) -> None:
        bundle = MANAGER.verify_bundle(
            ROOT / "targets/opencode-v1", immutable=False
        )
        source = self.root / "probe-source"
        MANAGER._copy_bundle(bundle, source, immutable=False)
        support_files = MANAGER._stage_opencode_runtime_support(source)
        MANAGER._seal_composed_runtime_config(source, bundle, support_files)
        probe = self.root / "config-probe"
        expected_inventory = frozenset(
            {
                *(entry.relative for entry in bundle.entries),
                *support_files,
            }
        )
        source_files, files, fingerprint = MANAGER._stage_bounded_config_probe(
            source,
            probe,
            expected_inventory=expected_inventory,
        )

        source_agent = (source / "agents/grillmester.md").read_text()
        probe_agent = (probe / "agents/grillmester.md").read_text()
        source_frontmatter = source_agent.split("\n---\n", 1)[0]
        probe_frontmatter, probe_body = probe_agent.split("\n---\n", 1)
        self.assertEqual(source_frontmatter, probe_frontmatter)
        self.assertEqual(
            "Managed OpenCode config probe for grillmester.", probe_body.strip()
        )
        self.assertEqual(0o555, stat.S_IMODE(probe.stat().st_mode))
        self.assertEqual(
            fingerprint,
            MANAGER._validate_config_probe_projection(
                source,
                probe,
                expected_inventory=expected_inventory,
                expected_source_files=source_files,
                expected_probe_files=files,
            ),
        )

        source_skill_path = source / "skills/grillmester-review/SKILL.md"
        probe_skill_path = probe / "skills/grillmester-review/SKILL.md"
        source_skill = source_skill_path.read_text()
        probe_skill = probe_skill_path.read_text()
        source_skill_frontmatter = source_skill.split("\n---\n", 1)[0]
        probe_skill_frontmatter, probe_skill_body = probe_skill.split(
            "\n---\n", 1
        )
        self.assertEqual(source_skill_frontmatter, probe_skill_frontmatter)
        self.assertEqual(
            "Managed OpenCode skill probe for grillmester-review.",
            probe_skill_body.strip(),
        )
        source_asset = source / "skills/grillmester-postgresql-review/references"
        asset = next(path for path in source_asset.rglob("*") if path.is_file())
        relative_asset = asset.relative_to(source)
        self.assertEqual(asset.read_bytes(), (probe / relative_asset).read_bytes())

        (source / "agents/grillmester.md").chmod(0o644)
        with self.assertRaisesRegex(MANAGER.LifecycleError, "became writable"):
            MANAGER._validate_config_probe_projection(
                source,
                probe,
                expected_inventory=expected_inventory,
                expected_source_files=source_files,
                expected_probe_files=files,
            )
        (source / "agents/grillmester.md").chmod(0o444)

        source_skill_path.chmod(0o644)
        source_skill_path.write_text(
            source_skill.replace("\n---\n", "\n---\nchanged\n", 1),
            encoding="utf-8",
        )
        source_skill_path.chmod(0o444)
        with self.assertRaisesRegex(MANAGER.LifecycleError, "source changed"):
            MANAGER._validate_config_probe_projection(
                source,
                probe,
                expected_inventory=expected_inventory,
                expected_source_files=source_files,
                expected_probe_files=files,
            )
        source_skill_path.chmod(0o644)
        source_skill_path.write_text(source_skill, encoding="utf-8")
        source_skill_path.chmod(0o444)

        (probe / "agents/grillmester.md").chmod(0o644)
        with self.assertRaisesRegex(MANAGER.LifecycleError, "probe file changed"):
            MANAGER._validate_sealed_config_probe(probe, files)

    def test_project_root_ignores_hostile_git_environment(self) -> None:
        consumer = self.root / "consumer-root"
        nested = consumer / "nested"
        unrelated = self.root / "unrelated"
        nested.mkdir(parents=True)
        unrelated.mkdir()
        (consumer / ".git").mkdir()
        (unrelated / ".git").mkdir()
        hostile = {
            "GIT_DIR": str(unrelated / ".git"),
            "GIT_WORK_TREE": str(unrelated),
            "GIT_CONFIG_GLOBAL": str(unrelated / "hostile.gitconfig"),
        }
        previous = Path.cwd()
        try:
            os.chdir(nested)
            with mock.patch.object(
                MANAGER.subprocess,
                "run",
                side_effect=AssertionError("project discovery must not execute git"),
            ):
                self.assertEqual(consumer.resolve(), MANAGER._project_root(hostile))
        finally:
            os.chdir(previous)

    def test_project_root_accepts_worktree_file_but_rejects_symlink_marker(self) -> None:
        consumer = self.root / "consumer-worktree"
        nested = consumer / "nested"
        nested.mkdir(parents=True)
        marker = consumer / ".git"
        marker.write_text("gitdir: ../metadata\n", encoding="utf-8")
        previous = Path.cwd()
        try:
            os.chdir(nested)
            self.assertEqual(consumer.resolve(), MANAGER._project_root({}))
            marker.unlink()
            marker.symlink_to(self.root / "external-git")
            with self.assertRaisesRegex(
                MANAGER.LifecycleError, "symlinked repository marker"
            ):
                MANAGER._project_root({})
        finally:
            os.chdir(previous)

    def test_cross_version_delegation_does_not_load_new_composer(self) -> None:
        old_root = self.root / "old-distribution"
        active_manager = old_root / MANAGER.MANAGER_RELATIVE
        active_manager.parent.mkdir(parents=True)
        active_manager.write_bytes(b"old manager\n")
        entry = MANAGER.ManifestEntry(
            MANAGER.MANAGER_RELATIVE,
            sha256(active_manager.read_bytes()),
            0o755,
        )
        distribution = types.SimpleNamespace(
            root=old_root,
            entries=(entry,),
        )
        loader = mock.Mock(side_effect=AssertionError("composer loaded"))

        class Delegated(RuntimeError):
            pass

        with mock.patch.object(
            MANAGER, "_lifecycle_lock", return_value=nullcontext()
        ), mock.patch.object(
            MANAGER,
            "_load_state",
            return_value={"active": "1" * 64, "previous": None},
        ), mock.patch.object(
            MANAGER, "_release_distribution", return_value=distribution
        ), mock.patch.object(
            MANAGER, "_load_verified_permission_composer", loader
        ), mock.patch.object(
            MANAGER.os, "execv", side_effect=Delegated("delegated")
        ) as execv, self.assertRaises(Delegated):
            MANAGER._delegate_to_active_manager_if_needed(
                self.home, ["launch"]
            )

        loader.assert_not_called()
        execv.assert_called_once_with(
            MANAGER.sys.executable,
            [
                MANAGER.sys.executable,
                "-I",
                "-S",
                str(active_manager),
                "launch",
            ],
        )


if __name__ == "__main__":
    unittest.main()
