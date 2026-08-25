from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "smoke_grillmester_local", ROOT / "scripts/smoke_grillmester_local.py"
)
assert SPEC is not None and SPEC.loader is not None
SMOKE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SMOKE
SPEC.loader.exec_module(SMOKE)


def executable(path: Path, output: str = "") -> Path:
    path.write_text(
        "#!/bin/sh\n" + f"printf '%b\\n' {output!r}\n",
        encoding="utf-8",
    )
    path.chmod(0o700)
    return path


def post_completion(base_url: str, payload: dict[str, object]) -> str:
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        request, timeout=5
    ) as response:
        return response.read().decode("utf-8")


class LoopbackProviderTests(unittest.TestCase):
    def test_models_and_chat_completions_stream_have_exact_contract(self) -> None:
        scenario = SMOKE.Scenario("opencode", "focused")
        with SMOKE.LoopbackProvider(scenario) as provider:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                f"{provider.base_url}/models", timeout=5
            ) as response:
                models = json.load(response)
            stream = post_completion(
                provider.base_url,
                {
                    "model": SMOKE.MODEL_ID,
                    "stream": True,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "# Barista ☕\nStatus: NEEDS_FULL_CONTEXT\n"
                                "Resume with: grillmester local --full"
                            ),
                        }
                    ],
                    "tools": [],
                },
            )

        self.assertEqual(SMOKE.MODEL_ID, models["data"][0]["id"])
        self.assertIn("text/event-stream", provider.last_content_type)
        self.assertIn(SMOKE.sentinel_for(scenario), stream)
        self.assertTrue(stream.endswith("data: [DONE]\n\n"))
        self.assertEqual(1, len(provider.state.model_requests))
        self.assertEqual(1, len(provider.state.completions))
        self.assertEqual([], provider.state.violations)

    def test_unknown_path_and_wrong_model_are_recorded_as_protocol_failures(self) -> None:
        scenario = SMOKE.Scenario("copilot", "full")
        with SMOKE.LoopbackProvider(scenario) as provider:
            with self.assertRaises(urllib.error.HTTPError) as unknown:
                urllib.request.urlopen(f"{provider.base_url}/responses", timeout=5)
            self.assertEqual(404, unknown.exception.code)
            with self.assertRaises(urllib.error.HTTPError) as wrong:
                post_completion(
                    provider.base_url,
                    {
                        "model": "wrong-model",
                        "stream": True,
                        "messages": [{"role": "system", "content": "# Barista ☕"}],
                    },
                )
            self.assertEqual(400, wrong.exception.code)

        self.assertTrue(
            any("unsupported GET /v1/responses" in item for item in provider.state.violations)
        )
        self.assertTrue(
            any("exact model" in item for item in provider.state.violations)
        )


class MatrixTests(unittest.TestCase):
    def test_tree_snapshot_detects_same_size_content_rewrites(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / "result.txt"
            candidate.write_bytes(b"before")
            before = SMOKE._tree_snapshot(root)

            candidate.write_bytes(b"after!")

            self.assertNotEqual(before, SMOKE._tree_snapshot(root))

    def test_matrix_uses_local_launcher_and_proves_payload_prompt_and_scrubbing(self) -> None:
        observed: list[tuple[str, str, tuple[str, ...]]] = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binaries = root / "bin"
            home = root / "source-home"
            state = root / "state"
            binaries.mkdir()
            home.mkdir()
            state.mkdir()
            cplt = executable(binaries / "cplt")
            opencode = executable(binaries / "opencode")
            copilot = executable(binaries / "copilot")
            ripgrep = executable(binaries / "rg")
            executable(binaries / "gh", "AMBIENT_GH_MUST_NOT_RUN")
            environment = {
                "HOME": str(home),
                "XDG_STATE_HOME": str(state),
                "CPLT_CONFIG": str(root / "ambient-cplt-config.toml"),
                "PATH": str(binaries),
                "LANG": "en_US.UTF-8",
                **{
                    name: f"{SMOKE.CREDENTIAL_CANARY_PREFIX}{name}"
                    for name in SMOKE.CREDENTIAL_ENVIRONMENT
                },
            }

            def run_command(
                command: tuple[str, ...],
                cwd: Path,
                child_environment: dict[str, str],
                timeout: float,
            ) -> SMOKE.CommandResult:
                self.assertGreater(timeout, 0)
                client = command[command.index("--client") + 1]
                expected_entries = {".git"}
                if client == "opencode":
                    expected_entries.update({".opencode", "AGENTS.md"})
                    self.assertTrue((cwd / ".opencode" / ".gitignore").is_file())
                    self.assertTrue((cwd / ".opencode" / "AGENTS.md").is_file())
                    self.assertTrue((cwd / ".opencode" / "package.json").is_file())
                self.assertEqual(expected_entries, {entry.name for entry in cwd.iterdir()})
                self.assertEqual(("-I", "-S"), command[1:3])
                self.assertEqual("grillmester.py", Path(command[3]).name)
                self.assertEqual(("local", "run"), command[4:6])
                self.assertEqual(SMOKE.PROMPT, command[-1])
                self.assertNotIn("--github-access", command)
                self.assertNotIn("--npm-access", command)
                self.assertNotIn("CPLT_CONFIG", child_environment)
                for name in SMOKE.GITHUB_CREDENTIAL_ENVIRONMENT:
                    self.assertNotIn(name, child_environment)
                context = "full" if "--full" in command else "focused"
                config = SMOKE.LOCAL.load_config(environment=child_environment)
                self.assertIsNotNone(config)
                assert config is not None
                self.assertEqual(client, config.client)
                self.assertEqual(context, config.context)
                base_url = config.base_url
                with urllib.request.build_opener(
                    urllib.request.ProxyHandler({})
                ).open(f"{base_url}/models", timeout=5) as response:
                    self.assertEqual(200, response.status)
                scenario = SMOKE.Scenario(client, context)
                prompt = "# Barista ☕\n"
                if context == "focused":
                    prompt += (
                        "Status: NEEDS_FULL_CONTEXT\n"
                        "Resume with: grillmester local --full"
                    )
                else:
                    prompt += (
                        "Select grillmester:grillmester for complex work"
                        if client == "copilot"
                        else "Select Grillmester (`grillmester`) for complex work"
                    )
                stream = post_completion(
                    base_url,
                    {
                        "model": SMOKE.MODEL_ID,
                        "stream": True,
                        "messages": [{"role": "system", "content": prompt}],
                        "tools": [
                            {
                                "type": "function",
                                "function": {"name": "bash"},
                            }
                        ],
                    },
                )
                if client == "opencode" and context == "focused":
                    stream += post_completion(
                        base_url,
                        {
                            "model": SMOKE.MODEL_ID,
                            "stream": True,
                            "messages": [
                                {
                                    "role": "tool",
                                    "content": SMOKE.TOOL_SENTINEL,
                                }
                            ],
                            "tools": [{"type": "function"}],
                        },
                    )
                elif client == "copilot":
                    stream += post_completion(
                        base_url,
                        {
                            "model": SMOKE.MODEL_ID,
                            "stream": True,
                            "messages": [
                                {"role": "user", "content": SMOKE.SUBAGENT_PROMPT}
                            ],
                            "tools": [{"type": "function"}],
                        },
                    )
                    stream += post_completion(
                        base_url,
                        {
                            "model": SMOKE.MODEL_ID,
                            "stream": True,
                            "messages": [
                                {
                                    "role": "tool",
                                    "content": "SUBAGENT_LOCAL_ONLY",
                                }
                            ],
                            "tools": [{"type": "function"}],
                        },
                    )
                observed.append((client, context, command))
                return SMOKE.CommandResult(0, stream)

            reports = SMOKE.run_matrix(
                distribution_root=ROOT,
                cplt=cplt,
                opencode=opencode,
                copilot=copilot,
                ripgrep=ripgrep,
                environment=environment,
                run_command=run_command,
                platform="darwin",
            )

        self.assertEqual(
            [
                ("opencode", "focused"),
                ("opencode", "full"),
                ("copilot", "focused"),
                ("copilot", "full"),
            ],
            [(report.scenario.client, report.scenario.context) for report in reports],
        )
        self.assertEqual(4, len(observed))
        self.assertTrue(all(report.consumer_clean for report in reports))
        self.assertTrue(all(report.credentials_scrubbed for report in reports))
        self.assertEqual(
            {
                ROOT / "targets/opencode-v1-focused",
                ROOT / "targets/opencode-v1",
                ROOT / "targets/copilot-cli-focused-v1",
                ROOT / "plugin",
            },
            {report.payload for report in reports},
        )

    def test_github_guard_matrix_uses_sandbox_path_lookup_and_fake_gh(self) -> None:
        observed: list[tuple[str, ...]] = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binaries = root / "bin"
            home = root / "home"
            state = root / "state"
            for path in (binaries, home, state):
                path.mkdir()
            cplt = executable(binaries / "cplt")
            opencode = executable(binaries / "opencode")
            for name in ("git", "sandbox-exec", "uname", "which"):
                executable(binaries / name)
            environment = {
                "HOME": str(home),
                "XDG_STATE_HOME": str(state),
                "PATH": str(binaries),
                "LANG": "en_US.UTF-8",
            }

            def run_process(
                command: tuple[str, ...],
                cwd: Path,
                child_environment: dict[str, str],
                timeout: float,
            ) -> SMOKE.CommandResult:
                self.assertGreater(timeout, 0)
                self.assertEqual(("exec", "-c"), command[-3:-1])
                arguments = tuple(SMOKE.shlex.split(command[-1]))
                self.assertEqual("gh", arguments[0])
                observed.append(arguments)
                if arguments[:3] == ("gh", "issue", "create") and "--repo" not in arguments:
                    completed = subprocess.run(
                        arguments,
                        cwd=cwd,
                        env=child_environment,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        timeout=timeout,
                        check=False,
                    )
                    return SMOKE.CommandResult(completed.returncode, completed.stdout)
                return SMOKE.CommandResult(1, "blocked by fixture")

            with mock.patch.object(
                SMOKE.LOCAL,
                "_trusted_macos_executable",
                side_effect=lambda name: (binaries / name).resolve(strict=True),
            ), mock.patch.object(
                SMOKE.LOCAL, "_ensure_cplt_executable_state_path"
            ):
                SMOKE.run_github_guard_matrix(
                    distribution_root=ROOT,
                    cplt=cplt,
                    opencode=opencode,
                    environment=environment,
                    run_process=run_process,
                    platform="darwin",
                )

        self.assertEqual(4, len(observed))
        self.assertIn("--repo", observed[1])
        self.assertEqual(("gh", "issue", "delete", "1"), observed[2])
        self.assertEqual(("gh", "auth", "token"), observed[3])

    def test_provider_validation_rejects_the_wrong_context_projection(self) -> None:
        scenario = SMOKE.Scenario("copilot", "focused")
        state = SMOKE.ProviderState(scenario)
        state.model_requests.append({})
        state.completions.append(
            SMOKE.CompletionRecord(
                path="/v1/chat/completions",
                headers={},
                payload={
                    "model": SMOKE.MODEL_ID,
                    "stream": True,
                    "messages": [
                        {
                            "role": "system",
                            "content": "# Barista ☕\nSelect grillmester:grillmester",
                        }
                    ],
                    "tools": [{"type": "function"}],
                },
            )
        )
        state.completions.extend(
            (
                SMOKE.CompletionRecord(
                    path="/v1/chat/completions",
                    headers={},
                    payload={
                        "model": SMOKE.MODEL_ID,
                        "stream": True,
                        "messages": [
                            {"role": "user", "content": SMOKE.SUBAGENT_PROMPT}
                        ],
                    },
                ),
                SMOKE.CompletionRecord(
                    path="/v1/chat/completions",
                    headers={},
                    payload={
                        "model": SMOKE.MODEL_ID,
                        "stream": True,
                        "messages": [
                            {"role": "tool", "content": "SUBAGENT_LOCAL_ONLY"}
                        ],
                    },
                ),
            )
        )
        with self.assertRaisesRegex(SMOKE.LocalSmokeError, "focused handoff"):
            SMOKE.validate_provider_state(state)

    def test_provider_validation_rejects_a_delegated_cloud_model(self) -> None:
        scenario = SMOKE.Scenario("copilot", "full")
        state = SMOKE.ProviderState(scenario)
        state.model_requests.append({})
        state.completions.extend(
            (
                SMOKE.CompletionRecord(
                    path="/v1/chat/completions",
                    headers={},
                    payload={
                        "model": SMOKE.MODEL_ID,
                        "stream": True,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "# Barista ☕\n"
                                    "Select grillmester:grillmester for complex work"
                                ),
                            }
                        ],
                        "tools": [
                            {"type": "function", "function": {"name": "bash"}}
                        ],
                    },
                ),
                SMOKE.CompletionRecord(
                    path="/v1/chat/completions",
                    headers={},
                    payload={
                        "model": "gpt-5.6-sol",
                        "stream": True,
                        "messages": [
                            {"role": "user", "content": SMOKE.SUBAGENT_PROMPT}
                        ],
                    },
                ),
                SMOKE.CompletionRecord(
                    path="/v1/chat/completions",
                    headers={},
                    payload={
                        "model": SMOKE.MODEL_ID,
                        "stream": True,
                        "messages": [
                            {"role": "tool", "content": "SUBAGENT_LOCAL_ONLY"}
                        ],
                    },
                ),
            )
        )

        with self.assertRaisesRegex(SMOKE.LocalSmokeError, "request 2 escaped"):
            SMOKE.validate_provider_state(state)

    def test_provider_validation_requires_the_bash_tool_result_not_its_arguments(
        self,
    ) -> None:
        scenario = SMOKE.Scenario("opencode", "focused")
        state = SMOKE.ProviderState(scenario)
        state.model_requests.append({})
        state.completions.extend(
            (
                SMOKE.CompletionRecord(
                    path="/v1/chat/completions",
                    headers={},
                    payload={
                        "model": SMOKE.MODEL_ID,
                        "stream": True,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "# Barista ☕\nStatus: NEEDS_FULL_CONTEXT\n"
                                    "Resume with: grillmester local --full"
                                ),
                            }
                        ],
                        "tools": [
                            {"type": "function", "function": {"name": "bash"}}
                        ],
                    },
                ),
                SMOKE.CompletionRecord(
                    path="/v1/chat/completions",
                    headers={},
                    payload={
                        "model": SMOKE.MODEL_ID,
                        "stream": True,
                        "messages": [
                            {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "bash",
                                            "arguments": json.dumps(
                                                {
                                                    "command": (
                                                        "/usr/bin/printf "
                                                        f"{SMOKE.TOOL_SENTINEL}"
                                                    )
                                                }
                                            ),
                                        }
                                    }
                                ],
                            },
                            {"role": "tool", "content": "permission denied"},
                        ],
                    },
                ),
            )
        )

        with self.assertRaisesRegex(SMOKE.LocalSmokeError, "auto-approved bash"):
            SMOKE.validate_provider_state(state)

    def test_provider_validation_names_missing_bash_tool(self) -> None:
        scenario = SMOKE.Scenario("opencode", "focused")
        state = SMOKE.ProviderState(scenario)
        state.model_requests.append({})
        state.completions.append(
            SMOKE.CompletionRecord(
                path="/v1/chat/completions",
                headers={},
                payload={
                    "model": SMOKE.MODEL_ID,
                    "stream": True,
                    "messages": [{"role": "system", "content": "# Barista ☕"}],
                    "tools": [
                        {"type": "function", "function": {"name": "shell"}},
                        {"type": "function", "function": {"name": "read"}},
                    ],
                },
            )
        )

        with self.assertRaisesRegex(
            SMOKE.LocalSmokeError,
            "required 'bash' tool; advertised function tools: shell, read",
        ):
            SMOKE.validate_provider_state(state)


class PrerequisiteTests(unittest.TestCase):
    def test_exact_versions_are_accepted_in_isolated_home(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binaries = root / "bin"
            state = root / "version-state"
            binaries.mkdir()
            state.mkdir()
            cplt = executable(
                binaries / "cplt", f"cplt {SMOKE.EXPECTED_CPLT_RELEASE}"
            )
            opencode = executable(
                binaries / "opencode", SMOKE.EXPECTED_OPENCODE_VERSION
            )
            copilot = executable(
                binaries / "copilot",
                "Package extraction took 11579ms\\n"
                f"GitHub Copilot CLI {SMOKE.EXPECTED_COPILOT_VERSION}.\\n"
                "Run 'copilot update' to check for updates.",
            )
            ripgrep = executable(binaries / "rg")

            result = SMOKE.inspect_prerequisites(
                cplt=cplt,
                opencode=opencode,
                copilot=copilot,
                ripgrep=ripgrep,
                state=state,
                environment={"PATH": str(binaries), "LANG": "en_US.UTF-8"},
                platform="darwin",
            )

            self.assertEqual((), result.problems)

    def test_duplicate_expected_version_line_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binaries = root / "bin"
            state = root / "version-state"
            binaries.mkdir()
            state.mkdir()
            cplt = executable(
                binaries / "cplt", f"cplt {SMOKE.EXPECTED_CPLT_RELEASE}"
            )
            opencode = executable(
                binaries / "opencode", SMOKE.EXPECTED_OPENCODE_VERSION
            )
            line = f"GitHub Copilot CLI {SMOKE.EXPECTED_COPILOT_VERSION}."
            copilot = executable(binaries / "copilot", f"{line}\\n{line}")
            ripgrep = executable(binaries / "rg")

            result = SMOKE.inspect_prerequisites(
                cplt=cplt,
                opencode=opencode,
                copilot=copilot,
                ripgrep=ripgrep,
                state=state,
                environment={"PATH": str(binaries), "LANG": "en_US.UTF-8"},
                platform="darwin",
            )

        self.assertTrue(
            any(
                "expected exactly one copilot version line" in problem
                for problem in result.problems
            ),
            result.problems,
        )
        self.assertEqual(cplt.resolve(), result.cplt)
        self.assertEqual(opencode.resolve(), result.opencode)
        self.assertEqual(copilot.resolve(), result.copilot)
        self.assertEqual(ripgrep.resolve(), result.ripgrep)

    def test_missing_prerequisites_skip_by_default_and_fail_when_required(self) -> None:
        missing = "/definitely/missing/grillmester-local-smoke"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = SMOKE.main(
                [
                    "--cplt",
                    missing,
                    "--opencode",
                    missing,
                    "--copilot",
                    missing,
                ]
            )
        self.assertEqual(0, result)
        self.assertIn("SKIP:", stdout.getvalue())
        self.assertIn("cplt", stdout.getvalue())

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = SMOKE.main(
                [
                    "--cplt",
                    missing,
                    "--opencode",
                    missing,
                    "--copilot",
                    missing,
                    "--require-binaries",
                ]
            )
        self.assertEqual(1, result)
        self.assertIn("ERROR:", stderr.getvalue())
        self.assertIn("No scenario was executed", stderr.getvalue())

    def test_runtime_failure_is_never_reported_as_a_skip(self) -> None:
        prerequisite = SMOKE.PrerequisiteResult(
            Path("/bin/cplt"),
            Path("/bin/opencode"),
            Path("/bin/copilot"),
            Path("/bin/rg"),
            (),
        )
        stderr = io.StringIO()
        with mock.patch.object(
            SMOKE, "resolve_and_inspect_prerequisites", return_value=prerequisite
        ), mock.patch.object(
            SMOKE, "run_matrix", side_effect=SMOKE.LocalSmokeError("protocol drift")
        ), contextlib.redirect_stderr(stderr):
            result = SMOKE.main([])

        self.assertEqual(1, result)
        self.assertIn("protocol drift", stderr.getvalue())
        self.assertNotIn("SKIP", stderr.getvalue())

    def test_invalid_home_is_a_clear_prerequisite_skip_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "not-a-directory"
            home.write_text("not a home\n", encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = SMOKE.main([], environment={"HOME": str(home), "PATH": ""})

        self.assertEqual(0, result)
        self.assertIn("SKIP:", stdout.getvalue())
        self.assertIn("HOME must be a directory", stdout.getvalue())


class BinaryResolutionTests(unittest.TestCase):
    def test_bare_command_names_resolve_from_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "cplt"
            binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            binary.chmod(0o755)
            environment = {"PATH": str(root)}

            resolved = SMOKE._resolve_binary(
                "cplt", name="cplt", environment=environment
            )

            self.assertEqual(binary, resolved)

    def test_explicit_paths_are_never_reinterpreted_as_path_lookups(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            on_path = root / "bin/cplt"
            on_path.parent.mkdir()
            on_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            on_path.chmod(0o755)
            explicit = root / "cplt"
            environment = {"PATH": str(on_path.parent)}

            resolved = SMOKE._resolve_binary(
                str(explicit), name="cplt", environment=environment
            )

            self.assertEqual(explicit, resolved)


class ProcessBoundaryTests(unittest.TestCase):
    def test_process_output_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "noisy"
            script.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    print("x" * 4096)
                    """
                ),
                encoding="utf-8",
            )
            script.chmod(0o700)
            with self.assertRaisesRegex(SMOKE.LocalSmokeError, "output limit"):
                SMOKE.run_command(
                    (str(script),),
                    root,
                    {"PATH": "/usr/bin:/bin"},
                    5,
                    max_output_bytes=32,
                )


if __name__ == "__main__":
    unittest.main()
