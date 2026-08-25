from __future__ import annotations

import importlib.util
import os
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_smoke_opencode", ROOT / "scripts/smoke_opencode.py"
)
assert SPEC and SPEC.loader
SMOKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SMOKE)


class OpenCodeSmokeTest(unittest.TestCase):
    def create_target(self, root: Path) -> Path:
        target = root / "target"
        for agent_id in sorted(SMOKE.EXPECTED_AGENTS):
            agent = target / "agents" / f"{agent_id}.md"
            agent.parent.mkdir(parents=True, exist_ok=True)
            agent.write_text(
                f"---\ndescription: {agent_id}\n---\n\nPrompt for {agent_id}.\n",
                encoding="utf-8",
            )
        for index in range(SMOKE.EXPECTED_SKILLS):
            skill_id = f"grillmester-fixture-{index:02d}"
            skill = target / "skills" / skill_id / "SKILL.md"
            skill.parent.mkdir(parents=True, exist_ok=True)
            skill.write_text(
                f"---\nname: {skill_id}\ndescription: Fixture {index}\n---\n",
                encoding="utf-8",
            )
            command = target / "commands" / f"{skill_id}.md"
            command.parent.mkdir(parents=True, exist_ok=True)
            command.write_text(
                f"---\ndescription: Fixture {index}\n---\n\n"
                f"Load {skill_id} with $ARGUMENTS.\n",
                encoding="utf-8",
            )
        (target / "manifest.json").write_text("{}\n", encoding="utf-8")
        return target

    def create_fake_binary(self, root: Path) -> Path:
        binary = root / "fake-opencode"
        binary.write_text(
            textwrap.dedent(
                f"""\
                #!/usr/bin/env python3
                import json
                import os
                import sys
                from pathlib import Path

                PRIMARY = {sorted(SMOKE.PRIMARY_AGENTS)!r}
                SUBAGENTS = {sorted(SMOKE.SUBAGENTS)!r}
                AGENTS = PRIMARY + SUBAGENTS
                args = sys.argv[1:]
                config = Path(os.environ["OPENCODE_CONFIG_DIR"])
                user_config = Path(os.environ["XDG_CONFIG_HOME"]) / "opencode/opencode.json"

                for secret in (
                    "GH_TOKEN",
                    "GITHUB_TOKEN",
                    "OPENAI_API_KEY",
                    "AWS_SECRET_ACCESS_KEY",
                ):
                    if secret in os.environ:
                        raise SystemExit(91)
                if os.environ.get("OPENCODE_PURE") != "1":
                    raise SystemExit(92)
                if os.environ.get("OPENCODE_DISABLE_MODELS_FETCH") != "true":
                    raise SystemExit(93)
                if not (Path.cwd() / ".git").is_dir():
                    raise SystemExit(94)

                declared_permission = {{"skill": "allow"}}

                def resolved_permissions():
                    rules = [
                        {{"permission": "*", "pattern": "*", "action": "allow"}},
                        {{"permission": "external_directory", "pattern": "*", "action": "ask"}},
                    ]
                    rules.extend(
                        {{
                            "permission": "external_directory",
                            "pattern": str(path / "*"),
                            "action": "allow",
                        }}
                        for path in (config / "skills").glob("*")
                    )
                    rules.extend([
                        {{"permission": "read", "pattern": "*", "action": "allow"}},
                        {{"permission": "read", "pattern": "*.env", "action": "ask"}},
                        {{"permission": "read", "pattern": "*.env.*", "action": "ask"}},
                        {{"permission": "read", "pattern": "*.env.example", "action": "allow"}},
                    ])
                    if user_config.is_file():
                        rules.append({{
                            "permission": "read",
                            "pattern": {SMOKE.USER_DENIED_READ_PATTERN!r},
                            "action": "deny",
                        }})
                    rules.append({{
                        "permission": "skill",
                        "pattern": "*",
                        "action": "allow",
                    }})
                    return rules

                if args == ["--version"]:
                    print({SMOKE.EXPECTED_OPENCODE_VERSION!r})
                    raise SystemExit(0)

                if args[:2] == ["debug", "config"]:
                    commands = {{
                        path.stem: {{
                            "description": path.stem,
                            "template": f"Load {{path.stem}} with $ARGUMENTS",
                        }}
                        for path in (config / "commands").glob("*.md")
                    }}
                    agents = {{
                        name: {{
                            "description": name,
                            "mode": "primary" if name in PRIMARY else "subagent",
                            "hidden": name in SUBAGENTS,
                            "permission": declared_permission,
                            "prompt": f"Prompt for {{name}}.",
                        }}
                        for name in AGENTS
                    }}
                    print(json.dumps({{
                        "agent": agents,
                        "command": commands,
                        "plugin": [],
                        "share": "disabled",
                        "autoupdate": False,
                    }}))
                    raise SystemExit(0)

                if args[:2] == ["agent", "list"]:
                    print("build (primary)")
                    # OpenCode 1.18.20 can lose the tail of this human-formatted
                    # output when a complete skill tree expands every agent's
                    # resolved external-directory permissions beyond the pipe
                    # flush boundary. A discovery probe must therefore omit
                    # skills while retaining every agent definition.
                    listed_agents = (
                        AGENTS[:2]
                        if any((config / "skills").glob("*/SKILL.md"))
                        else AGENTS
                    )
                    for name in listed_agents:
                        mode = "primary" if name in PRIMARY else "subagent"
                        print(f"{{name}} ({{mode}})")
                    raise SystemExit(0)

                if args[:2] == ["debug", "agent"]:
                    name = args[2]
                    if "--tool" in args:
                        path = (Path.cwd() / "AGENTS.md").resolve()
                        print(json.dumps({{
                            "tool": "read",
                            "input": {{"filePath": "AGENTS.md"}},
                            "result": {{"output": f"<path>{{path}}</path>\\n" + path.read_text()}},
                        }}))
                        raise SystemExit(0)
                    payload = {{
                        "name": name,
                        "description": name,
                        "options": {{}},
                        "permission": resolved_permissions(),
                        "mode": "primary" if name in PRIMARY else "subagent",
                        "native": False,
                        "tools": {{"read": True, "skill": True}},
                    }}
                    if name == "kokk" and user_config.is_file():
                        payload["model"] = {{
                            "providerID": {SMOKE.HYBRID_PROVIDER_ID!r},
                            "modelID": {SMOKE.HYBRID_MODEL_ID!r},
                        }}
                    print(json.dumps(payload))
                    raise SystemExit(0)

                if args[:2] == ["debug", "skill"]:
                    skills = [{{
                        "name": "customize-opencode",
                        "description": "Built in",
                        "location": "<built-in>",
                    }}]
                    skills.extend(
                        {{
                            "name": path.parent.name,
                            "description": path.parent.name,
                            "location": str(path.resolve()),
                        }}
                        for path in (config / "skills").glob("*/SKILL.md")
                    )
                    print(json.dumps(skills))
                    raise SystemExit(0)

                raise SystemExit(95)
                """
            ),
            encoding="utf-8",
        )
        binary.chmod(0o755)
        return binary

    def test_isolated_environment_drops_credentials_and_blocks_network(self) -> None:
        root = Path("/tmp/grillmester-opencode-env")
        env = SMOKE.isolated_environment(
            {
                "PATH": "/usr/bin",
                "LANG": "nb_NO.UTF-8",
                "GH_TOKEN": "secret-gh",
                "GITHUB_TOKEN": "secret-github",
                "OPENAI_API_KEY": "secret-openai",
                "AWS_SECRET_ACCESS_KEY": "secret-aws",
                "HTTPS_PROXY": "http://ambient-proxy.invalid",
            },
            sandbox=root,
            config_dir=root / "config",
        )

        self.assertEqual("/usr/bin", env["PATH"])
        self.assertEqual("nb_NO.UTF-8", env["LANG"])
        self.assertEqual("http://127.0.0.1:9", env["HTTPS_PROXY"])
        self.assertEqual("true", env["OPENCODE_DISABLE_MODELS_FETCH"])
        self.assertEqual("1", env["OPENCODE_PURE"])
        for key in (
            "GH_TOKEN",
            "GITHUB_TOKEN",
            "OPENAI_API_KEY",
            "AWS_SECRET_ACCESS_KEY",
        ):
            self.assertNotIn(key, env)

    def test_target_inventory_rejects_command_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = self.create_target(Path(temp))
            (target / "commands/grillmester-fixture-00.md").unlink()

            with self.assertRaisesRegex(SMOKE.SmokeError, "43 commands"):
                SMOKE.target_inventory(target)

    def test_missing_binary_skips_unless_required(self) -> None:
        missing = "/definitely/missing/grillmester-opencode"
        stdout = StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(0, SMOKE.main(["--opencode", missing]))
        self.assertIn("SKIP:", stdout.getvalue())

        stderr = StringIO()
        with redirect_stderr(stderr):
            self.assertEqual(
                1, SMOKE.main(["--opencode", missing, "--require-binary"])
            )
        self.assertIn("ERROR:", stderr.getvalue())

    def test_agent_detail_rejects_an_effective_env_allow(self) -> None:
        config_agent = {
            "permission": {
                "*": "ask",
                "read": "allow",
            }
        }
        detail = {
            "name": "grillmester",
            "mode": "primary",
            "native": False,
            "permission": [
                {"permission": "*", "pattern": "*", "action": "allow"},
                {"permission": "read", "pattern": "*", "action": "allow"},
                {"permission": "read", "pattern": "*.env", "action": "ask"},
                {"permission": "read", "pattern": "*.env.*", "action": "ask"},
                {"permission": "read", "pattern": "*.env.example", "action": "allow"},
                {"permission": "*", "pattern": "*", "action": "ask"},
                {"permission": "read", "pattern": "*", "action": "allow"},
            ],
        }

        with self.assertRaisesRegex(
            SMOKE.SmokeError, "must not allow environment files"
        ):
            SMOKE.validate_agent_detail(
                detail,
                agent_id="grillmester",
                config_agent=config_agent,
            )

    def test_agent_detail_rejects_a_denied_bundled_skill_path(self) -> None:
        config_dir = Path("/tmp/grillmester-opencode-permission-fixture")
        skill_glob = str(config_dir / "skills/grillmester-doctor/*")
        config_agent = {
            "permission": {
                "*": "deny",
                "read": {
                    "*": "allow",
                    "*.env": "ask",
                    "*.env.*": "ask",
                    "*.env.example": "allow",
                },
            }
        }
        detail = {
            "name": "kokk",
            "mode": "subagent",
            "native": False,
            "permission": [
                {"permission": "*", "pattern": "*", "action": "allow"},
                {"permission": "external_directory", "pattern": "*", "action": "ask"},
                {
                    "permission": "external_directory",
                    "pattern": skill_glob,
                    "action": "allow",
                },
                {"permission": "read", "pattern": "*", "action": "allow"},
                {"permission": "read", "pattern": "*.env", "action": "ask"},
                {"permission": "read", "pattern": "*.env.*", "action": "ask"},
                {"permission": "read", "pattern": "*.env.example", "action": "allow"},
                {"permission": "*", "pattern": "*", "action": "deny"},
                {"permission": "read", "pattern": "*", "action": "allow"},
                {"permission": "read", "pattern": "*.env", "action": "ask"},
                {"permission": "read", "pattern": "*.env.*", "action": "ask"},
                {"permission": "read", "pattern": "*.env.example", "action": "allow"},
            ],
        }

        with self.assertRaisesRegex(
            SMOKE.SmokeError, "must allow bundled skill paths"
        ):
            SMOKE.validate_agent_detail(
                detail,
                agent_id="kokk",
                config_agent=config_agent,
                config_dir=config_dir,
                skill_ids=frozenset({"grillmester-doctor"}),
            )

    def test_agent_detail_requires_environment_examples_to_remain_readable(self) -> None:
        config_agent = {
            "permission": {
                "read": {
                    "*.env": "ask",
                    "*.env.*": "ask",
                    "*.env.example": "ask",
                }
            }
        }
        detail = {
            "name": "grillmester",
            "mode": "primary",
            "native": False,
            "permission": [
                {"permission": "*", "pattern": "*", "action": "allow"},
                {"permission": "read", "pattern": "*", "action": "allow"},
                {"permission": "read", "pattern": "*.env", "action": "ask"},
                {"permission": "read", "pattern": "*.env.*", "action": "ask"},
                {"permission": "read", "pattern": "*.env.example", "action": "allow"},
                {"permission": "read", "pattern": "*.env", "action": "ask"},
                {"permission": "read", "pattern": "*.env.*", "action": "ask"},
                {"permission": "read", "pattern": "*.env.example", "action": "ask"},
            ],
        }

        with self.assertRaisesRegex(
            SMOKE.SmokeError, "must allow environment examples"
        ):
            SMOKE.validate_agent_detail(
                detail,
                agent_id="grillmester",
                config_agent=config_agent,
            )

    def test_hybrid_override_rejects_an_expanded_top_level_read_deny(self) -> None:
        denied_rule = {
            "permission": "read",
            "pattern": "*.user-denied",
            "action": "deny",
        }
        kokk = {
            "model": {
                "providerID": SMOKE.HYBRID_PROVIDER_ID,
                "modelID": SMOKE.HYBRID_MODEL_ID,
            },
            "permission": [
                denied_rule,
                {"permission": "*", "pattern": "*", "action": "deny"},
                {"permission": "read", "pattern": "*", "action": "allow"},
            ],
        }
        grillmester = {
            "permission": [
                denied_rule,
                {"permission": "*", "pattern": "*", "action": "ask"},
            ]
        }

        with self.assertRaisesRegex(
            SMOKE.SmokeError, "top-level read deny was expanded"
        ):
            SMOKE.validate_hybrid_override(kokk, grillmester)

    @unittest.skipUnless(os.name == "posix", "fake executable fixture is POSIX-only")
    def test_full_offline_discovery_with_fake_binary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = self.create_target(root)
            binary = self.create_fake_binary(root)

            report = SMOKE.smoke(
                binary=binary,
                target=target,
                base_env={
                    "PATH": os.environ["PATH"],
                    "GH_TOKEN": "secret-gh",
                    "OPENAI_API_KEY": "secret-openai",
                },
            )

        self.assertEqual(SMOKE.EXPECTED_OPENCODE_VERSION, report.version)
        self.assertEqual(4, report.primary_agents)
        self.assertEqual(3, report.subagents)
        self.assertEqual(43, report.skills)
        self.assertEqual(43, report.commands)


if __name__ == "__main__":
    unittest.main()
