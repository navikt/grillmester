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

                permission = {{"read": "allow", "skill": "allow"}}

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
                            "permission": permission,
                            "prompt": f"Prompt for {{name}}.",
                        }}
                        for name in AGENTS
                    }}
                    print(json.dumps({{"agent": agents, "command": commands, "plugin": []}}))
                    raise SystemExit(0)

                if args[:2] == ["agent", "list"]:
                    print("build (primary)")
                    for name in AGENTS:
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
                    rules = [
                        {{"permission": key, "pattern": "*", "action": action}}
                        for key, action in permission.items()
                    ]
                    payload = {{
                        "name": name,
                        "description": name,
                        "options": {{}},
                        "permission": rules,
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

            with self.assertRaisesRegex(SMOKE.SmokeError, "42 commands"):
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
        self.assertEqual(42, report.skills)
        self.assertEqual(42, report.commands)


if __name__ == "__main__":
    unittest.main()
